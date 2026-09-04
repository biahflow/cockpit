"""Contas a receber: cronograma, numeração, transições e vencimento (FDD 028, RFC 0004).

A regra de dinheiro mora aqui e não na view, no molde de `cases.py` e `kickoff.py`: a viewset, o
job periódico e o webhook do gateway chamam **as mesmas funções**, e é isso que faz "a fatura só
muda de estado por caminho conhecido" ser verdade em vez de disciplina.

O que este módulo deliberadamente **não** faz: falar com fornecedor. Isso é `payments.py`, e a
separação é a mesma que a casa mantém entre `esign.py` (o fornecedor) e o domínio que o usa —
aqui ela importa mais, porque a camada 0 (a fatura) precisa funcionar inteira sem gateway nenhum.
Sem provedor configurado, `mark-paid` à mão é o único caminho de baixa, e é um caminho completo.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from decimal import ROUND_HALF_UP, Decimal
from typing import TYPE_CHECKING

from django.db import IntegrityError, transaction
from django.utils import timezone

if TYPE_CHECKING:
    from .models import Invoice, Project, User
    from .payments import ChargeRef

logger = logging.getLogger(__name__)

CENT = Decimal("0.01")


class InvoiceTransitionError(Exception):
    """Transição de estado recusada pelo mapa. Quem chama decide se vira 400 ou 409."""


@dataclass(frozen=True)
class Parcela:
    """Uma linha do cronograma de cobrança: rótulo, fatia do contratado e prazo em dias."""

    label: str
    share: Decimal
    offset: int


# Um cronograma de cobrança por nível de produto (FDD 015), espelhando `kickoff.KICKOFF_TEMPLATES`.
#
# Os deslocamentos **não são inventados**: são os mesmos `offset` dos marcos que o kickoff já semeia
# para cada nível. Fatura que vence num dia em que nada foi entregue é briga marcada, e alinhar os
# dois cronogramas é o que evita isso sem ninguém precisar lembrar.
#
# `qualification_call` é lista vazia, e não uma parcela de R$ 0,00: o degrau é gratuito por
# definição da metodologia, e semear uma fatura de zero inventaria cobrança onde a casa promete
# gratuidade — além de produzir inadimplência fantasma no primeiro relatório.
#
# `transformation` também é lista vazia, mas por motivo **oposto e mais incômodo**: ele é
# recorrente mensal, e este dicionário só sabe descrever parcelas de um contrato de valor único
# medidas em dias a partir do início do projeto. Semear qualquer coisa aqui cobraria uma vez o
# que se cobra todo mês. Enquanto `Service` não tiver recorrência, quem vende a parceria monta a
# cobrança na tela — que é exatamente o que `schedule_for` já faz com serviço avulso.
#
# O **Design Partner** (ADR 0053) não muda cronograma nenhum, e é de propósito: o subsídio mora no
# `estimated_value` da oportunidade, não aqui. Projeto com valor zero gera parcelas de zero, e é
# assim que o valor concedido continua visível em vez de virar ausência de dado.
INVOICE_SCHEDULES: dict[str, list[Parcela]] = {
    "qualification_call": [],
    "discovery_sprint": [
        Parcela("Discovery Sprint — entrada", Decimal("0.5"), 0),
        Parcela("Discovery Sprint — Executive Readout", Decimal("0.5"), 7),
    ],
    "feasibility": [
        Parcela("Technical Feasibility — entrada", Decimal("0.5"), 0),
        Parcela("Technical Feasibility — decision gate", Decimal("0.5"), 21),
    ],
    "prove": [
        Parcela("PROVE — entrada", Decimal("0.3"), 0),
        Parcela("PROVE — produção controlada", Decimal("0.4"), 60),
        Parcela("PROVE — decision gate", Decimal("0.3"), 90),
    ],
    "scale": [
        Parcela("Scale — entrada", Decimal("0.3"), 14),
        Parcela("Scale — rollout", Decimal("0.4"), 60),
        Parcela("Scale — captura de valor", Decimal("0.3"), 120),
    ],
    "transformation": [],
}


def schedule_for(project: Project) -> list[Parcela]:
    """O cronograma de cobrança do nível de produto do projeto.

    **Sem fallback**, e aqui está a divergência deliberada em relação a `kickoff.template_for`, que
    cai num template padrão: errar um marco custa uma edição, errar uma *cobrança* cria fatura de
    dinheiro que ninguém combinou. Serviço avulso e projeto sem serviço não semeiam nada — quem
    vende fora dos níveis monta a cobrança na tela.
    """
    tier = project.service.tier if project.service else ""
    return INVOICE_SCHEDULES.get(tier, [])


def contracted_value(project: Project) -> Decimal:
    """O valor contratado, na ordem em que a casa o conhece.

    `actual_value` primeiro porque **é** o valor contratado — é a definição que a FDD 028 adota, e
    semear um cronograma que não soma exatamente isso faria os dois números se contradizerem no
    primeiro dia, que é a colisão de verdade que a FDD existe para não cometer por acidente.

    `CommercialOpportunity.estimated_value` em seguida: não tem default e nunca é nulo, então
    é o palpite honesto — o que o pipeline dizia que o negócio valia. `Service.list_price` por último, e na
    prática quase sempre zero: a migração `0020` semeia os níveis pagos com preço a definir.
    """
    if project.actual_value and project.actual_value > 0:
        return Decimal(project.actual_value)
    opportunity = project.originating_commercial_opportunity
    if opportunity is not None and opportunity.estimated_value > 0:
        return Decimal(opportunity.estimated_value)
    if project.service is not None:
        return Decimal(project.service.list_price)
    return Decimal("0")


def _split(base: Decimal, parcelas: list[Parcela]) -> list[Decimal]:
    """Reparte `base` pelas fatias, **com a sobra na última**.

    Divisão percentual sobre dinheiro decimal vaza centavos: 30/40/30 de R$ 10.000,01 não fecha.
    Jogar o resíduo na última parcela é o que garante que a soma das faturas seja *exatamente* o
    contratado — sem isso nasce uma diferença de um centavo que ninguém consegue localizar depois.
    """
    valores: list[Decimal] = []
    for parcela in parcelas[:-1]:
        valores.append((base * parcela.share).quantize(CENT, rounding=ROUND_HALF_UP))
    valores.append(base - sum(valores, Decimal("0")))
    return valores


def seed_invoices(project: Project) -> int:
    """Semeia o cronograma de cobrança **em rascunho** na conversão (FDD 028).

    Nada sai de `draft` sozinho: débito automático não existe neste recorte, e emitir é ato
    deliberado de gente. Idempotente por existência, como `cases.freeze_if_completed`.
    """
    from .models import Engagement, Invoice

    if project.invoices.exists():
        return 0
    # **Design Partner não fatura, e a guarda mora aqui.** É o significado do campo: o mandato
    # recebe o Discovery de graça em troca de servir como caso e prova (ADR 0050). Sem esta linha,
    # um projeto nascido pela rota do mandato (`create-project`, DAP r3) cairia no
    # `Service.list_price` do degrau — o Discovery Sprint vale R$ 3.000 desde a migração `0064` —
    # e a casa emitiria rascunho de cobrança contra quem ela decidiu não cobrar.
    #
    # Aqui e não na action porque é aqui que a cobrança se decide: quem semeia fatura pergunta uma
    # vez só, e a próxima rota que criar projeto herda a resposta em vez de repetir a pergunta.
    if project.engagement.commercial_model == Engagement.CommercialModel.DESIGN_PARTNER:
        return 0
    parcelas = schedule_for(project)
    base = contracted_value(project)
    # As duas guardas, e as duas são necessárias. A lista vazia declara a intenção para a
    # Qualification Call (gratuita) e para a Transformation Partnership (recorrente, que este
    # dicionário não sabe descrever); o `base <= 0` é o que de fato salva, porque a gratuidade é do
    # **valor**, não do degrau — degrau pago pode chegar com `list_price=0` (migração `0020`), e
    # sem esta linha um PROVE vendido a zero produziria três rascunhos de R$ 0,00.
    if not parcelas or base <= 0:
        return 0
    for parcela, valor in zip(parcelas, _split(base, parcelas), strict=True):
        Invoice.objects.create(
            account=project.engagement.account,
            project=project,
            service=project.service,
            amount=valor,
            description=parcela.label,
            # O mesmo grampo de `kickoff.seed_work_items`, pela mesma razão: nada vence depois do
            # fim do projeto.
            due_date=min(project.start_date + timedelta(days=parcela.offset), project.due_date),
        )
    return len(parcelas)


def next_number(today: date | None = None) -> str:
    """O próximo número do ano, formato `AAAA-NNNN`.

    Sequencial dentro do ano civil, calculado por `max + 1` sobre o prefixo. A corrida entre duas
    emissões simultâneas **não** é resolvida aqui: quem arbitra é a `UniqueConstraint` do banco, e
    `finish_issue` tenta de novo. `select_for_update` não serviria — ele não tranca a linha
    fantasma que a transação concorrente está prestes a inserir, o que o faz *parecer* correto sem
    ser.
    """
    from .models import Invoice

    ano = (today or timezone.localdate()).year
    ultimo = (
        Invoice.objects.filter(number__startswith=f"{ano}-")
        .order_by("-number")
        .values_list("number", flat=True)
        .first()
    )
    proximo = int(ultimo.split("-")[1]) + 1 if ultimo else 1
    return f"{ano}-{proximo:04d}"


def transition(invoice: Invoice, to: str) -> None:
    """A guarda única sobre `INVOICE_TRANSITIONS`. Uma regra, uma expressão."""
    from .models import INVOICE_TRANSITIONS
    from .models import Invoice as InvoiceModel

    if to == invoice.status:
        return
    if to not in INVOICE_TRANSITIONS[invoice.status]:
        raise InvoiceTransitionError(
            f"Não é possível ir de {invoice.get_status_display()} para "
            f"{InvoiceModel.Status(to).label}."
        )


def finish_issue(invoice: Invoice, ref: ChargeRef, by: User | None) -> Invoice:
    """Fecha a emissão: número, carimbos e a referência que o gateway devolveu.

    Roda numa transação **curta**, depois de o fornecedor já ter respondido — segurar um
    `select_for_update` aberto durante uma chamada de rede é como se esgota um pool de conexões.
    A releitura sob lock é o que mata o clique duplo; o `Idempotency-Key` do lado do Stripe mata o
    resto.
    """
    from .models import Invoice as InvoiceModel

    provider_ref = getattr(ref, "external_reference", "") or ""
    for tentativa in range(3):
        try:
            with transaction.atomic():
                atual = InvoiceModel.objects.select_for_update().get(pk=invoice.pk)
                transition(atual, InvoiceModel.Status.ISSUED)
                atual.number = next_number()
                atual.status = InvoiceModel.Status.ISSUED
                atual.issued_at = timezone.now()
                atual.issued_by = by
                atual.provider = getattr(ref, "provider", "") or ""
                atual.external_reference = provider_ref
                atual.payment_url = getattr(ref, "payment_url", "") or ""
                atual.save()
                return atual
        except IntegrityError:
            # Outra emissão levou o número entre o `max + 1` e o insert. Cada tentativa tem o
            # próprio `atomic()` de propósito: capturar `IntegrityError` dentro de um bloco
            # externo sem savepoint deixa a transação do Postgres envenenada e tudo o que vier
            # depois falha com "current transaction is aborted" — no SQLite do CI, passa.
            logger.info("número de fatura em disputa, tentativa %s", tentativa + 1)
    raise IntegrityError("Não foi possível alocar um número de fatura.")


def settle(
    invoice: Invoice,
    *,
    at: datetime | None = None,
    amount: Decimal | None = None,
    method: str = "",
    reference: str = "",
    by: User | None = None,
) -> Invoice:
    """A baixa. Idempotente: fatura já paga volta intacta, sem recarimbar nada."""
    from .models import Invoice as InvoiceModel

    if invoice.status == InvoiceModel.Status.PAID:
        return invoice
    transition(invoice, InvoiceModel.Status.PAID)
    invoice.status = InvoiceModel.Status.PAID
    invoice.paid_at = at or timezone.now()
    invoice.settled_by = by
    if method:
        invoice.method = method
    if reference and not invoice.external_reference:
        invoice.external_reference = reference
    if amount is not None:
        invoice.amount = amount
    invoice.save()
    return invoice


def cancel(invoice: Invoice, by: User | None, reason: str) -> Invoice:
    """Cancela — a saída que substitui apagar e arquivar (FDD 028, ADR 0021).

    O número **não** é liberado: a sequência fica com buracos, e isso é correto. Numeração sem
    lacuna é exigência *fiscal* da NFS-e, que este recorte não emite.
    """
    from .models import Invoice as InvoiceModel

    transition(invoice, InvoiceModel.Status.CANCELLED)
    invoice.status = InvoiceModel.Status.CANCELLED
    invoice.cancelled_at = timezone.now()
    invoice.cancelled_by = by
    invoice.cancel_reason = reason
    invoice.save()
    return invoice


def mark_overdue(today: date | None = None) -> int:
    """Fatura emitida cujo vencimento passou vira `vencida` (FDD 028).

    Só toca `issued`: rascunho nunca foi cobrado, e `paid`/`cancelled`/`renegotiated` são terminais.
    **Idempotente por construção**, não por guarda — o filtro exclui exatamente o que a rodada
    anterior mudou, então a segunda execução do dia atualiza zero linhas.

    `due_date__lt` e não `__lte`: vencer hoje não é atrasar hoje.

    **Nenhuma notificação sai daqui**, e a próxima pessoa vai querer adicionar uma. Aviso é camada 3
    da RFC 0004, que só entra depois de a reconciliação estar de pé — cobrar antes de reconciliar
    produz exatamente o agente que importuna quem pagou ontem.
    """
    from .models import Invoice

    return Invoice.objects.filter(
        status=Invoice.Status.ISSUED, due_date__lt=today or timezone.localdate()
    ).update(
        # `.update()` passa por cima de `auto_now`; sem isto uma mudança de estado em massa não
        # deixaria carimbo nenhum.
        status=Invoice.Status.OVERDUE,
        updated_at=timezone.now(),
    )
