"""Gateway de pagamento atrás de flag (`payments`), agnóstico de fornecedor (FDD 028, ADR 0007).

Dois lados, o mesmo molde de `esign.py`:

- **SAÍDA** (Biahflow → fornecedor): `issue_charge()` cria a cobrança no gateway e devolve a
  referência que liga a `Invoice` à fatura de lá, mais o link pagável.
- **ENTRADA** (fornecedor → Biahflow): o webhook (`/api/v1/payments/webhook/`) valida a assinatura
  do corpo cru, normaliza o evento (`parse_event`) e aplica a baixa (`apply_event`). O `mark-paid`
  do `InvoiceViewSet` segue como caminho manual — e, **sem `PAYMENTS_PROVIDER` configurado, é o
  único caminho de baixa que existe**.

O fornecedor em uso é o **Stripe**, e ele ainda **não foi homologado** contra conta real — as
quatro rodadas da FDD 024 acharam defeito cada uma, e não há razão para supor que esta seja
diferente. `docs/runbooks/homologacao-de-integracoes.md` traz o roteiro.

**Por que a API de Invoices do Stripe e não uma Checkout Session.** A sessão de checkout é uma
chamada só e devolve `url` de imediato, o que a torna a escolha óbvia — e ela **expira em no máximo
24 h**. Um link para uma fatura que vence em quinze dias estaria morto antes de o cliente abrir. A
Invoice do Stripe *é* um recebível: tem vencimento, número, página hospedada que não expira e os
eventos que interessam. O preço é precisar de um `Customer`, guardado em
`Account.payment_customer_ref` e reusado — um cliente novo por fatura quebraria a deduplicação e os
relatórios do próprio fornecedor.

As chamadas HTTP reais ficam fora da cobertura (`# pragma: no cover`), como em `esign.py`.
"""

from __future__ import annotations

import hmac
import json
import logging
import time
import urllib.error
import urllib.parse
import urllib.request
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import UTC, datetime
from decimal import Decimal
from typing import TYPE_CHECKING, Protocol

from django.conf import settings
from django.utils import timezone

from . import flags, invoices
from .portal import sign

if TYPE_CHECKING:
    from .models import Invoice

logger = logging.getLogger(__name__)


def is_enabled() -> bool:
    return flags.is_enabled("payments")


@dataclass(frozen=True)
class Event:
    """Evento do gateway já normalizado para o vocabulário do Biahflow."""

    status: str  # Invoice.Status
    external_reference: str = ""
    paid_at: datetime | None = None  # a data do fornecedor, quando o evento a traz
    amount: Decimal | None = None
    method: str = ""
    detail: str = ""


class PaymentProviderError(Exception):
    """O gateway não devolveu uma cobrança utilizável.

    Existe pela mesma razão que `EsignProviderError`, e o estrago aqui é maior: uma fatura marcada
    como emitida sem link pagável é uma cobrança que **ninguém consegue pagar**, que o webhook nunca
    poderá fechar (não há referência para casar) e que ainda assim contaria como recebível em aberto
    no total que alguém vai olhar para decidir alguma coisa.
    """


@dataclass(frozen=True)
class ChargeRef:
    """O que o gateway devolve ao criar a cobrança."""

    external_reference: str = ""  # id da fatura no fornecedor; chave de busca do webhook
    payment_url: str = ""  # página hospedada de pagamento (não expira)
    provider: str = ""  # de quem é a referência acima


class Provider(Protocol):
    """Contrato do adaptador de gateway (Stripe hoje)."""

    def charge(self, invoice: Invoice) -> ChargeRef:
        """Cria a cobrança no fornecedor e devolve a referência dela."""

    def verify(self, body: bytes, headers: Mapping[str, str]) -> bool:
        """A entrega veio mesmo do fornecedor?"""

    def parse_event(self, payload: dict) -> Event | None:
        """Normaliza a entrega; `None` quando o evento não interessa ao portal."""


class NullProvider:
    """Sem gateway configurado: a fatura vive só no portal e a baixa é manual.

    Não é um modo degradado — é um modo previsto. A camada 0 inteira (emitir, acompanhar, vencer,
    baixar à mão) funciona sem fornecedor nenhum, e é assim que a FDD 028 quer.
    """

    def charge(self, invoice: Invoice) -> ChargeRef:
        logger.info("Emissão sem gateway configurado: fatura=%s", invoice.pk)
        return ChargeRef()

    def verify(self, body: bytes, headers: Mapping[str, str]) -> bool:
        return False

    def parse_event(self, payload: dict) -> Event | None:
        return None


# De-para explícito de eventos do Stripe.
#
# `invoice.payment_succeeded` chega **junto** com `invoice.paid` para o mesmo pagamento. Mapear os
# dois para o mesmo alvo e deixar a idempotência absorver o segundo é mais honesto que eleger um e
# ignorar o outro: se a ordem de entrega inverter, a baixa ainda acontece.
#
# `voided`/`marked_uncollectible` entram para os dois sistemas não divergirem em silêncio — sem
# eles, a lista de recebíveis seguiria cobrando uma fatura que um humano matou no painel do Stripe.
#
# `invoice.payment_failed` mapeia para **nada**, de propósito: uma tentativa recusada não muda nosso
# estado, a fatura continua emitida ou vencida. É aqui que se costuma ligar um estado por engano.
_STRIPE_EVENTS: dict[str, str] = {
    "invoice.paid": "paid",
    "invoice.payment_succeeded": "paid",
    "invoice.voided": "cancelled",
    "invoice.marked_uncollectible": "cancelled",
}


class StripeProvider:
    """Adaptador do Stripe em HTTP cru — a API é form-encoded e não pede SDK."""

    DEFAULT_BASE = "https://api.stripe.com"

    @property
    def base(self) -> str:
        return settings.PAYMENTS_API_BASE or self.DEFAULT_BASE

    # --- Saída ---------------------------------------------------------------

    @staticmethod
    def _cents(amount: Decimal) -> int:
        """Reais → centavos, **sem passar por float**.

        `int(float(amount) * 100)` é o clássico R$ 18,99 → 1898: erra por um centavo, em silêncio,
        em valores perfeitamente comuns.
        """
        return int((Decimal(amount).quantize(Decimal("0.01")) * 100).to_integral_value())

    @staticmethod
    def _days_until_due(invoice: Invoice) -> int:
        """Dias até vencer, **nunca negativo**.

        Emitir uma fatura já vencida é legítimo (a cobrança atrasou, não o combinado), e o Stripe
        responde 400 a um `days_until_due` negativo.
        """
        return max(0, (invoice.due_date - timezone.localdate()).days)

    def _customer(self, invoice: Invoice) -> str:  # pragma: no cover - I/O com o fornecedor
        """O `Customer` do cliente no Stripe, criado na primeira emissão e reusado depois."""
        account = invoice.account
        if account.payment_customer_ref:
            return account.payment_customer_ref
        contato = account.contacts.exclude(email="").first()
        created = self._post(
            "/v1/customers",
            {
                "name": account.name,
                "email": contato.email if contato else "",
                "metadata[client_id]": str(account.pk),
            },
            idempotency_key=f"client-{account.pk}-customer",
        )
        ref = str((created or {}).get("id", ""))
        if ref:
            account.payment_customer_ref = ref
            account.save(update_fields=["payment_customer_ref", "updated_at"])
        return ref

    def charge(self, invoice: Invoice) -> ChargeRef:  # pragma: no cover - I/O com o fornecedor
        customer = self._customer(invoice)
        if not customer:
            return ChargeRef()
        chave = f"invoice-{invoice.pk}-issue"
        self._post(
            "/v1/invoiceitems",
            {
                "customer": customer,
                "amount": str(self._cents(invoice.amount)),
                "currency": "brl",
                "description": invoice.description or f"Fatura {invoice.pk}",
            },
            idempotency_key=f"{chave}-item",
        )
        created = self._post(
            "/v1/invoices",
            {
                "customer": customer,
                "collection_method": "send_invoice",
                "days_until_due": str(self._days_until_due(invoice)),
                "metadata[invoice_id]": str(invoice.pk),
            },
            idempotency_key=f"{chave}-invoice",
        )
        stripe_id = str((created or {}).get("id", ""))
        if not stripe_id:
            return ChargeRef()
        return self._parse_finalized(
            self._post(f"/v1/invoices/{stripe_id}/finalize", {}, idempotency_key=f"{chave}-final")
        )

    @staticmethod
    def _parse_finalized(data: dict | None) -> ChargeRef:
        """Lê a resposta do `finalize` (separada do I/O para ficar testável)."""
        finalized = data or {}
        stripe_id = str(finalized.get("id", ""))
        url = str(finalized.get("hosted_invoice_url", ""))
        if not stripe_id or not url:
            return ChargeRef()
        return ChargeRef(external_reference=stripe_id, payment_url=url, provider="stripe")

    # --- Sonda ---------------------------------------------------------------

    @staticmethod
    def _parse_ping(data: dict | None) -> tuple[bool, str]:
        if data is None or "livemode" not in data:
            return False, "o Stripe não reconheceu a chave"
        modo = "produção" if data.get("livemode") else "teste"
        return True, f"chave válida, modo {modo}"

    def ping(self) -> tuple[bool, str]:  # pragma: no cover - I/O com o fornecedor
        """Consulta o saldo: leitura pura, sem efeito colateral e sem custo (regra da FDD 024).

        Confirma a chave **e** de que modo ela é — uma credencial de teste apontada para produção
        passa em qualquer verificação que só olhe se a variável está preenchida.
        """
        return self._parse_ping(_http_raw(f"{self.base}/v1/balance", None, self._headers(), "GET"))

    # --- Entrada -------------------------------------------------------------

    def verify(self, body: bytes, headers: Mapping[str, str]) -> bool:
        secret = settings.PAYMENTS_WEBHOOK_SECRET
        header = headers.get("Stripe-Signature", "") or headers.get("stripe-signature", "")
        if not secret or not header:
            return False
        timestamp, assinaturas = "", []
        for parte in header.split(","):
            chave, _, valor = parte.partition("=")
            if chave.strip() == "t":
                timestamp = valor.strip()
            elif chave.strip() == "v1":
                # Lista, e não dict: durante uma **rotação de segredo** o Stripe manda mais de um
                # `v1` no mesmo header. Guardar só o último recusaria entrega legítima.
                assinaturas.append(valor.strip())
        if not timestamp or not assinaturas:
            return False
        try:
            idade = abs(time.time() - int(timestamp))
        except ValueError:
            return False
        # A tolerância é o que faz uma entrega **capturada** parar de valer. É a única coisa em que
        # o esquema do Stripe é mais forte que o do Autentique e o do Clicksign, e descartá-la em
        # nome de "consistência entre adaptadores" seria trocar segurança por simetria.
        if idade > settings.PAYMENTS_WEBHOOK_TOLERANCE_SECONDS:
            return False
        # Concatenação de **bytes**: `f"{t}.{body.decode()}"` estoura em qualquer byte não-UTF-8,
        # e estourar dentro de um `verify` é o pior lugar possível para uma exceção.
        esperado = sign(secret, timestamp.encode() + b"." + body)
        return any(hmac.compare_digest(esperado, a) for a in assinaturas)

    def parse_event(self, payload: dict) -> Event | None:
        status = _STRIPE_EVENTS.get(str(payload.get("type", "")).strip().lower())
        if status is None:
            return None
        obj = ((payload.get("data") or {}).get("object")) or {}
        pago = obj.get("status_transitions", {}).get("paid_at") or payload.get("created")
        centavos = obj.get("amount_paid")
        return Event(
            status=status,
            external_reference=str(obj.get("id", "")),
            paid_at=(datetime.fromtimestamp(int(pago), tz=UTC) if pago else None),
            amount=(Decimal(int(centavos)) / 100 if centavos else None),
            detail=str(payload.get("type", "")),
        )

    # --- HTTP ----------------------------------------------------------------

    @staticmethod
    def _headers(idempotency_key: str = "") -> dict[str, str]:
        headers = {
            "Authorization": f"Bearer {settings.PAYMENTS_API_TOKEN}",
            "Content-Type": "application/x-www-form-urlencoded",
        }
        if idempotency_key:
            # O Stripe honra a chave por 24 h em POST: um duplo clique em "Emitir" não cria duas
            # cobranças, e a segunda chamada devolve a mesma fatura.
            headers["Idempotency-Key"] = idempotency_key
        return headers

    def _post(  # pragma: no cover - I/O com o fornecedor
        self, path: str, fields: Mapping[str, str], idempotency_key: str = ""
    ) -> dict | None:
        return _http_raw(
            f"{self.base}{path}",
            urllib.parse.urlencode({k: v for k, v in fields.items() if v != ""}).encode(),
            self._headers(idempotency_key),
        )


_PROVIDERS: dict[str, type] = {"stripe": StripeProvider}


def get_provider() -> Provider:
    """Adaptador escolhido por `PAYMENTS_PROVIDER`; sem um reconhecido, o `NullProvider`."""
    provider = _PROVIDERS.get(settings.PAYMENTS_PROVIDER.strip().lower())
    return provider() if provider else NullProvider()


def has_provider() -> bool:
    """Há gateway configurado, ou estamos no registro local do `NullProvider`?"""
    return not isinstance(get_provider(), NullProvider)


# --- Saída (Biahflow → fornecedor) ------------------------------------------


def issue_charge(invoice: Invoice) -> ChargeRef:
    """Cria a cobrança e devolve a referência — **falhando fechado**.

    Levanta `PaymentProviderError` quando **havia um gateway** e ele não devolveu referência. Sem
    isso a fatura seria emitida com link vazio: ninguém pagaria, o webhook nunca a fecharia, e ela
    seguiria contando como recebível — a mesma "linha órfã" que a rodada 4 da FDD 024 achou na
    assinatura, agora com dinheiro em cima.

    Sem gateway, referência vazia é **correta**: o `NullProvider` registra a intenção e o
    `mark-paid` manual é o caminho previsto. A distinção é toda esta função.
    """
    ref = get_provider().charge(invoice)
    if has_provider() and not ref.external_reference:
        raise PaymentProviderError(
            f"{settings.PAYMENTS_PROVIDER} não devolveu referência para a fatura {invoice.pk}"
        )
    return ref


# --- Entrada (fornecedor → Biahflow) ----------------------------------------


def find_invoice(event: Event) -> Invoice | None:
    from .models import Invoice as InvoiceModel

    if not event.external_reference:
        return None
    return InvoiceModel.objects.filter(external_reference=event.external_reference).first()


def apply_event(event: Event) -> Invoice | None:
    """Aplica o evento do gateway à fatura. Idempotente e **respeitando o mapa de transições**.

    A igualdade de status resolve a reentrega simples, como em `esign.apply_event`. Só que ali o
    alvo é sempre alcançável, e aqui não: um `paid` chegando numa fatura **cancelada** é
    exatamente o "reabrir fatura fechada" que a FDD 028 lista como regressão crítica, e a
    igualdade sozinha não o cobre. Por isso a segunda guarda — é a divergência deliberada em
    relação ao molde do e-sign.
    """
    from .models import Invoice as InvoiceModel

    invoice = find_invoice(event)
    if invoice is None:
        # `warning` e não silêncio, ao contrário do e-sign: pagamento sem fatura correspondente é
        # dinheiro que entrou e não foi conciliado. Ignorar calado é pior aqui.
        logger.warning("pagamento sem fatura correspondente: ref=%s", event.external_reference)
        return None
    if invoice.status == event.status:
        return invoice
    from .models import INVOICE_TRANSITIONS

    if event.status not in INVOICE_TRANSITIONS[invoice.status]:
        logger.warning(
            "evento %s recusado: a fatura %s está %s", event.status, invoice.pk, invoice.status
        )
        return invoice
    if event.status == InvoiceModel.Status.PAID:
        return invoices.settle(invoice, at=event.paid_at, method=event.method or "")
    return invoices.cancel(invoice, None, f"Cancelada no gateway ({event.detail}).")


def _http_raw(  # pragma: no cover - I/O com o fornecedor
    url: str, body: bytes | None, headers: Mapping[str, str], method: str = "POST"
) -> dict | None:
    request = urllib.request.Request(url, data=body, method=method, headers=dict(headers))
    try:
        with urllib.request.urlopen(request, timeout=15) as response:  # noqa: S310
            raw = response.read()
        return json.loads(raw) if raw else None
    except (urllib.error.URLError, TimeoutError, ValueError) as exc:
        logger.warning("Falha ao falar com o gateway de pagamento (%s): %s", url, exc)
        return None
