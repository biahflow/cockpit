"""Assinatura eletrônica atrás de flag (`esign`), agnóstica de fornecedor (ADR 0007).

Dois lados, no mesmo molde do `tasksync.py`:

- **SAÍDA** (Biahflow → fornecedor): `send_for_signature()` cria a solicitação no provedor e
  devolve as referências que ligam a `SignatureRequest` ao documento/signatário de lá.
- **ENTRADA** (fornecedor → Biahflow): o webhook (`/api/v1/esign/webhook/`) valida o HMAC do
  corpo cru, normaliza o evento (`parse_event`) e aplica o status (`apply_event`) — é a
  transição `pending → signed/declined` de verdade. O `mark-signed` do `DocumentViewSet`
  segue como fallback manual para quando não há provedor configurado.

Uma solicitação tem **N signatários numa rodada só** (issue #115, ADR 0065): a casa, a parte
contratante e as testemunhas assinam o mesmo documento, então o fornecedor é chamado uma vez com a
lista inteira. A rodada é o `document_ref` que ele devolve, e é ela — não "todas as solicitações do
documento" — que responde se o instrumento está assinado. Onde cada assinatura aparece na página é
propriedade da solicitação (`positions`), não do arquivo: a Autentique não lê âncora de texto.

O fornecedor em uso é o **Autentique**; o Clicksign fica como segundo adaptador.
`ESIGN_PROVIDER` escolhe qual vale e, sem um reconhecido, cai no `NullProvider` (só registra
a intenção). Cada fornecedor traz seu próprio esquema de assinatura do webhook — header e
formato do HMAC diferem —, por isso `verify()` pertence ao adaptador e não à view. As
chamadas HTTP reais ficam fora da cobertura (`# pragma: no cover`), como em `tasksync.py`.
"""

from __future__ import annotations

import base64
import hmac
import io
import json
import logging
import urllib.error
import urllib.request
import uuid
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, replace
from typing import TYPE_CHECKING, Protocol

import pypdf
from django.conf import settings
from django.core.mail import send_mail
from django.db import transaction
from django.utils import timezone

from . import drive, flags, notifications
from .exceptions import DriveUnavailable
from .portal import sign

if TYPE_CHECKING:
    from .models import Document, SignatureRequest

logger = logging.getLogger(__name__)


def is_enabled() -> bool:
    return flags.is_enabled("esign")


@dataclass(frozen=True)
class Event:
    """Evento do fornecedor já normalizado para o vocabulário do Biahflow."""

    status: str  # SignatureRequest.Status
    provider_ref: str = ""
    document_ref: str = ""
    signer_email: str = ""


class EsignProviderError(Exception):
    """O fornecedor de assinatura não devolveu uma solicitação utilizável.

    `_http_raw` engole a falha de rede e devolve `None` de propósito — o portal não pode cair
    porque o fornecedor caiu. O problema era o degrau seguinte: `None` virava um `SignatureRef`
    vazio, **indistinguível de sucesso**, e a solicitação era gravada assim mesmo. Este tipo existe
    para separar as duas coisas.
    """


@dataclass(frozen=True)
class SignatureRef:
    """O que o fornecedor devolve ao criar a solicitação."""

    provider_ref: str = ""  # identifica o signatário; chave de busca do webhook
    document_ref: str = ""  # identifica o documento; fallback junto com o e-mail
    sign_url: str = ""  # link para o signatário assinar (vai no lembrete)


@dataclass(frozen=True)
class Signer:
    """Um signatário da rodada: quem assina e **em que papel** (issue #115).

    O papel é `SignatureRequest.SignerRole` — o vocabulário mora lá, num lugar só, e aqui só se
    carrega o valor. Ele decide três coisas distintas, e nenhuma delas é derivável do e-mail: onde
    a assinatura aparece na página (`POSICAO_POR_PAPEL`), qual `action` vai para o fornecedor
    (testemunha assina como testemunha) e, na volta, para quem sai o convite do Discovery.
    """

    email: str
    role: str


class Provider(Protocol):
    """Contrato do adaptador de fornecedor (Autentique e Clicksign hoje)."""

    def send(self, document: Document, signers: Sequence[Signer]) -> list[SignatureRef]:
        """Cria **uma** solicitação com todos os signatários e devolve uma referência por signatário.

        A lista é o contrato, e não um laço do chamador: os três signatários de um contrato assinam
        **o mesmo** documento. Chamar o fornecedor uma vez por pessoa criaria três documentos
        separados lá dentro, cada um com uma assinatura — o defeito exato que a issue #115 existe
        para não ter, e que não faz barulho nenhum ao acontecer.
        """

    def verify(self, body: bytes, headers: Mapping[str, str]) -> bool:
        """A entrega veio mesmo do fornecedor?"""

    def parse_event(self, payload: dict) -> Event | None:
        """Normaliza a entrega; `None` quando o evento não interessa ao portal."""


class NullProvider:
    """Sem fornecedor homologado: registra a intenção e não promete nada."""

    def send(self, document: Document, signers: Sequence[Signer]) -> list[SignatureRef]:
        for signer in signers:
            logger.info(
                "Solicitação de assinatura sem provedor homologado doc=%s signer=%s papel=%s",
                document.pk, signer.email, signer.role,
            )
        return [SignatureRef() for _ in signers]

    def verify(self, body: bytes, headers: Mapping[str, str]) -> bool:
        return False

    def parse_event(self, payload: dict) -> Event | None:
        return None


# De-para explícito de eventos do Autentique (o ADR exige não perder informação). Só estes
# dois movem a assinatura; `signature.viewed`, os biométricos e os de documento
# (`document.finished` etc.) não mudam o estado de nenhum signatário.
_AUTENTIQUE_EVENTS: dict[str, str] = {
    "signature.accepted": "signed",
    "signature.rejected": "declined",
}

# `sandbox` é argumento do `createDocument` (não campo do `DocumentInput` — confirmado por
# introspecção do schema; a documentação sugere o contrário).
_AUTENTIQUE_CREATE = """
mutation CreateDocument(
  $document: DocumentInput!, $signers: [SignerInput!]!, $file: Upload!, $sandbox: Boolean!
) {
  createDocument(document: $document, signers: $signers, file: $file, sandbox: $sandbox) {
    id
    signatures { public_id email link { short_link } }
  }
}
"""


def delivers_by_link() -> bool:
    """O portal entrega o link de assinatura (em vez de o fornecedor mandar o convite)?"""
    return settings.ESIGN_DELIVERY == "link"


# Frase escrita num lugar só (issue #112): nomeia o que foi **observado** — a combinação não
# entregou o convite numa rodada de homologação —, nunca a causa. Três hipóteses sobrevivem
# (sandbox não dispara convite; o signatário era o dono da conta; atraso maior que a janela do
# teste) e nenhuma está provada; escrever "o sandbox não manda e-mail" aqui seria inventar causa.
_AVISO_SANDBOX_COM_ENTREGA_POR_EMAIL = (
    "sandbox com entrega por e-mail: combinação não observada entregando o convite (issue #112)"
)


def aviso_de_entrega() -> str:
    """Vazio quando não há o que avisar; a frase quando a combinação é a não observada."""
    if settings.ESIGN_SANDBOX and not delivers_by_link():
        return _AVISO_SANDBOX_COM_ENTREGA_POR_EMAIL
    return ""


# --- Onde a assinatura aparece na página (issue #115, ADR 0065) ---------------------------------
#
# A Autentique **não tem** detecção de âncora por texto: a linha "Assinatura: ____" do documento
# não é lida por ninguém. Onde a assinatura aparece é propriedade da *solicitação*, e se declara em
# `positions` dentro de cada signatário do `createDocument`. Sem esse campo, o painel do fornecedor
# diz o que disse na primeira assinatura real (03/09/2026): *"esse signatário não possui campos de
# assinatura visíveis, a assinatura dele aparecerá somente na última página ao baixar o arquivo"*.
#
# Cada posição é `{x, y, z, element}`: `x`/`y` em **percentual 0–100** da largura/altura da página,
# com origem no **topo**, e `z` é o **número da página** — não existe "última página", nem `z: -1`,
# nem repetição em todas. Por isso a contagem de páginas (`paginas_do_pdf`) é pré-requisito, e não
# refinamento.
#
# Os três valores vão como **string**, que é a forma que a documentação do fornecedor mostra nos
# exemplos de `positions`; mandar número onde o exemplo mostra texto é a diferença entre uma
# solicitação aceita e uma recusada por um detalhe que ninguém lembra de conferir.

# ⚠️ ESTIMATIVA NÃO MEDIDA. Estas coordenadas **não puderam ser medidas**: não há conversor de
# `.docx` para PDF nesta máquina, e o que vale é a geometria do PDF que a *Autentique* produz, não
# a do Word. O primeiro envio real é a medição — abra o documento no painel do fornecedor, veja
# onde cada campo caiu e ajuste os números aqui; é uma linha por papel. Elas colocam as quatro
# assinaturas empilhadas na coluna da esquerda do bloco final do template, na ordem em que ele as
# desenha: a casa, a parte contratante, e as duas linhas de testemunha.
_POSICAO_POR_PAPEL: dict[str, tuple[str, str]] = {
    # `SignatureRequest.SignerRole.HOUSE` — a linha "BIAHFLOW INOVA SIMPLES I.S."
    "house": ("14", "56"),
    # `…SignerRole.COUNTERPARTY` — "[RAZÃO SOCIAL DA PARTE B]" / "[RAZÃO SOCIAL DO PARCEIRO]"
    "counterparty": ("14", "68"),
}
# As duas linhas de "Testemunhas:". Elas são **de quem for** — o template não reserva uma por lado
# —, então a primeira testemunha da lista ocupa a linha 1 e a segunda, a linha 2. Da terceira em
# diante não há linha, e ela vai **sem posição**: empilhar duas assinaturas no mesmo ponto produz um
# documento ilegível, que é pior que uma assinatura na página anexa.
_POSICOES_DA_TESTEMUNHA: tuple[tuple[str, str], ...] = (("14", "80"), ("14", "88"))

# Os `Document.Kind` que têm bloco de assinatura desenhado. A Proposta não tem, e o `kind` vazio
# não diz nada — nos dois casos a solicitação sai **sem** posição, com o motivo no log, em vez de
# carimbar uma assinatura no meio de um texto corrido. Molde de `DOCUMENT_KINDS_QUE_ABREM_ENGAGEMENT`
# (`models.py`): a decisão mora numa constante, não numa condição espalhada.
DOCUMENT_KINDS_COM_BLOCO_DE_ASSINATURA = frozenset(
    {"design_partner_agreement", "nda", "commercial_contract"}
)


def _acao_do_papel(role: str) -> str:
    """`SIGN`, ou `SIGN_AS_A_WITNESS` para quem testemunha (valores do `SignerInput`)."""
    return "SIGN_AS_A_WITNESS" if role == "witness" else "SIGN"


def posicoes_da_rodada(
    document: Document, signers: Sequence[Signer], conteudo: bytes
) -> list[dict[str, str] | None]:
    """Uma posição por signatário, alinhada com `signers` — `None` para quem vai sem posição.

    Sem posição **manda assim mesmo** e registra o motivo. Não recusa: o fluxo real de hoje usa
    `.docx`, e recusar quebraria o que funciona hoje para ganhar um posicionamento que aquele
    formato não permite calcular.
    """
    sem_posicao: list[dict[str, str] | None] = [None for _ in signers]
    if document.kind not in DOCUMENT_KINDS_COM_BLOCO_DE_ASSINATURA:
        logger.info(
            "documento %s (kind=%r) não tem bloco de assinatura; assinaturas sem posição",
            document.pk, document.kind,
        )
        return sem_posicao
    paginas = paginas_do_pdf(conteudo)
    if paginas is None:
        logger.info(
            "documento %s não é um PDF legível; assinaturas sem posição", document.pk
        )
        return sem_posicao

    pagina = str(paginas)  # a última página, que é onde o bloco de assinatura do template mora
    testemunhas = 0
    posicoes: list[dict[str, str] | None] = []
    for signer in signers:
        if signer.role == "witness":
            if testemunhas >= len(_POSICOES_DA_TESTEMUNHA):
                logger.info(
                    "documento %s tem só %d linhas de testemunha; %s assina sem posição",
                    document.pk, len(_POSICOES_DA_TESTEMUNHA), signer.email,
                )
                posicoes.append(None)
                continue
            x, y = _POSICOES_DA_TESTEMUNHA[testemunhas]
            testemunhas += 1
        else:
            ponto = _POSICAO_POR_PAPEL.get(signer.role)
            if ponto is None:  # pragma: no cover - a view recusa papel desconhecido com 400
                logger.info(
                    "papel %r sem posição declarada; %s assina sem posição",
                    signer.role, signer.email,
                )
                posicoes.append(None)
                continue
            x, y = ponto
        posicoes.append({"x": x, "y": y, "z": pagina, "element": "SIGNATURE"})
    return posicoes


def _autentique_signer(
    signer: Signer, position: dict[str, str] | None = None
) -> dict[str, object]:
    """Signatário no formato do Autentique, conforme quem avisa (ver `ESIGN_DELIVERY`).

    Na entrega por link o fornecedor não manda convite — e exige `name`, que derivamos do
    e-mail — mas devolve o `short_link`, que o portal usa no convite e no lembrete.

    Sem posição o formato é **o mesmo de antes da issue #115**, chave por chave: é o que mantém o
    modo `link` e o contrato da `/api/v1/` idênticos para o documento que não é PDF.
    """
    if delivers_by_link():
        dados: dict[str, object] = {
            "email": signer.email,
            "name": signer.email.split("@")[0],
            "action": _acao_do_papel(signer.role),
            "delivery_method": "DELIVERY_METHOD_LINK",
        }
    else:
        dados = {"email": signer.email, "action": _acao_do_papel(signer.role)}
    if position is not None:
        dados["positions"] = [position]
    return dados


class AutentiqueProvider:
    """Adaptador Autentique: GraphQL (multipart) na saída, `x-autentique-signature` na entrada."""

    DEFAULT_BASE = "https://api.autentique.com.br/v2/graphql"

    def send(self, document: Document, signers: Sequence[Signer]) -> list[SignatureRef]:
        if not settings.ESIGN_API_TOKEN:
            logger.info("Autentique sem ESIGN_API_TOKEN; solicitação só registrada localmente")
            return [SignatureRef() for _ in signers]
        content = _document_bytes(document)
        if not content:
            logger.warning("Documento %s sem conteúdo; nada enviado ao Autentique", document.pk)
            return [SignatureRef() for _ in signers]
        posicoes = posicoes_da_rodada(document, signers, content)
        operations = json.dumps(
            {
                "query": _AUTENTIQUE_CREATE,
                "variables": {
                    "document": {"name": document.original_name},
                    # Um `createDocument` com N signatários, nunca N chamadas: é a mesma folha de
                    # papel que os três assinam.
                    "signers": [
                        _autentique_signer(signer, posicao)
                        for signer, posicao in zip(signers, posicoes, strict=True)
                    ],
                    "file": None,
                    "sandbox": bool(settings.ESIGN_SANDBOX),
                },
            }
        )
        body, content_type = _multipart(
            {"operations": operations, "map": '{"file": ["variables.file"]}'},
            document.original_name,
            content,
        )
        data = self._post(body, content_type)
        return self._parse_created(data, signers)

    @staticmethod
    def _parse_ping(data: dict | None) -> tuple[bool, str]:
        """Lê a resposta do `me` (separada do I/O para ficar testável, como `_parse_created`)."""
        me = ((data or {}).get("data") or {}).get("me") or {}
        email = str(me.get("email", ""))
        if not email:
            return False, "o Autentique não reconheceu o token"
        return True, f"conta {email} acessível"

    def ping(self) -> tuple[bool, str]:  # pragma: no cover - I/O com o fornecedor
        """Pergunta de quem é o token, sem criar documento nem cobrar nada.

        O gancho existe em `integrations._probe_esign` desde a FDD 024, mas nenhum adaptador o
        implementava — e o e-sign era a única integração configurada que dizia "sem sonda
        disponível". A rodada 4 confirmou que a query `me` serve.
        """
        # `_http_raw` e não `_http`: este último é o helper do **Clicksign**, que leva o token na
        # URL e por isso não manda header de autorização — usá-lo aqui rende um 401 com um token
        # perfeitamente válido. Foi o que aconteceu na primeira versão desta sonda, e só apareceu
        # porque ela foi rodada contra o fornecedor de verdade.
        return self._parse_ping(
            _http_raw(
                settings.ESIGN_API_BASE or self.DEFAULT_BASE,
                json.dumps({"query": "{ me { email } }"}).encode(),
                {
                    "Content-Type": "application/json",
                    "Authorization": f"Bearer {settings.ESIGN_API_TOKEN}",
                },
            )
        )

    def verify(self, body: bytes, headers: Mapping[str, str]) -> bool:
        secret = settings.ESIGN_WEBHOOK_SECRET
        provided = headers.get("x-autentique-signature", "")
        if not secret or not provided:
            return False
        return hmac.compare_digest(provided, sign(secret, body))  # hex puro, sem prefixo

    def parse_event(self, payload: dict) -> Event | None:
        event = payload.get("event") or {}
        status = _AUTENTIQUE_EVENTS.get(str(event.get("type", "")).strip().lower())
        if status is None:
            return None
        data = event.get("data") or {}
        return Event(
            status=status,
            provider_ref=str(data.get("public_id", "")),
            document_ref=str(data.get("document", "")),
            signer_email=str((data.get("user") or {}).get("email", "")),
        )

    @staticmethod
    def _parse_created(
        data: dict | None, signers: Sequence[Signer]
    ) -> list[SignatureRef]:
        """Lê a resposta do `createDocument` (separada do I/O para ficar testável).

        Uma referência por signatário **pedido**, casada por e-mail, e nenhuma inventada. A versão
        anterior escolhia *um* signatário e caía num fallback `signatures[0]` quando o e-mail não
        casava: com um signatário só ele acertava por sorte, mas numa lista de três pegaria calado
        a referência de outra pessoa — e o webhook passaria a fechar a assinatura errada.

        O `document_ref` é o mesmo para todos (é o `id` do documento criado) e **é a rodada**: as
        solicitações que o compartilham são as que precisam estar todas assinadas para o documento
        contar como assinado (`Document.is_signed`).
        """
        created = ((data or {}).get("data") or {}).get("createDocument") or {}
        document_ref = str(created.get("id", ""))
        por_email = {
            str(assinatura.get("email", "")).lower(): assinatura
            for assinatura in created.get("signatures") or []
        }
        refs: list[SignatureRef] = []
        for signer in signers:
            assinatura = por_email.get(signer.email.lower())
            if assinatura is None:
                logger.warning(
                    "Autentique não devolveu assinatura para %s no documento %s",
                    signer.email, document_ref or "(sem referência)",
                )
                # Sem `provider_ref` — e é `send_for_signature` que transforma isso em falha alta,
                # em vez de gravar uma solicitação que o webhook nunca poderá fechar.
                refs.append(SignatureRef(document_ref=document_ref))
                continue
            refs.append(
                SignatureRef(
                    provider_ref=str(assinatura.get("public_id", "")),
                    document_ref=document_ref,
                    sign_url=str((assinatura.get("link") or {}).get("short_link", "")),
                )
            )
        return refs

    def _post(self, body: bytes, content_type: str) -> dict | None:  # pragma: no cover - I/O
        return _http_raw(
            settings.ESIGN_API_BASE or self.DEFAULT_BASE,
            body,
            {
                "Content-Type": content_type,
                "Authorization": f"Bearer {settings.ESIGN_API_TOKEN}",
            },
        )


# De-para explícito de eventos do Clicksign (o ADR exige não perder informação).
# `deadline` e os eventos de upload/visualização não movem a assinatura: ficam pendentes.
_CLICKSIGN_EVENTS: dict[str, str] = {
    "sign": "signed",
    "auto_close": "signed",
    "document_closed": "signed",
    "refusal": "declined",
    "cancel": "declined",
}


class ClicksignProvider:
    """Adaptador Clicksign: API REST para a saída, webhook `Content-Hmac` para a entrada."""

    DEFAULT_BASE = "https://sandbox.clicksign.com"

    def send(self, document: Document, signers: Sequence[Signer]) -> list[SignatureRef]:
        if len(signers) > 1:
            # **Recusa, e não laço.** `_create_signature_request` faz um upload por chamada, então
            # repeti-la produziria N documentos separados no Clicksign, cada um com uma assinatura —
            # e nenhum deles seria o contrato que as três pessoas pensam ter assinado. Falhar alto
            # aqui é a diferença entre um adaptador incompleto e um adaptador que mente.
            raise EsignProviderError(
                "o adaptador Clicksign não implementa múltiplos signatários numa solicitação"
            )
        if not settings.ESIGN_API_TOKEN:
            logger.info("Clicksign sem ESIGN_API_TOKEN; solicitação só registrada localmente")
            return [SignatureRef() for _ in signers]
        content = _document_bytes(document)
        if not content:
            logger.warning("Documento %s sem conteúdo; nada enviado ao Clicksign", document.pk)
            return [SignatureRef() for _ in signers]
        return [self._create_signature_request(document, signers[0].email, content)]

    def verify(self, body: bytes, headers: Mapping[str, str]) -> bool:
        secret = settings.ESIGN_WEBHOOK_SECRET
        provided = headers.get("Content-Hmac", "")
        if not secret or not provided:
            return False
        return hmac.compare_digest(provided, f"sha256={sign(secret, body)}")

    def parse_event(self, payload: dict) -> Event | None:
        event = payload.get("event") or {}
        status = _CLICKSIGN_EVENTS.get(str(event.get("name", "")).strip().lower())
        if status is None:
            return None
        document = payload.get("document") or {}
        signer = (event.get("data") or {}).get("user") or {}
        # A chave da lista (`request_signature_key`) é o que casa 1:1 com a SignatureRequest;
        # quando ela não vem, o par documento + e-mail do signatário resolve.
        signature_key = ""
        for entry in document.get("signers") or []:
            if str(entry.get("email", "")).lower() == str(signer.get("email", "")).lower():
                signature_key = str(entry.get("request_signature_key", ""))
                break
        return Event(
            status=status,
            provider_ref=signature_key,
            document_ref=str(document.get("key", "")),
            signer_email=str(signer.get("email", "")),
        )

    def _create_signature_request(  # pragma: no cover - I/O com o fornecedor
        self, document: Document, signer_email: str, content: bytes
    ) -> SignatureRef:
        base = (settings.ESIGN_API_BASE or self.DEFAULT_BASE).rstrip("/")
        token = settings.ESIGN_API_TOKEN
        mime = "application/pdf" if document.original_name.lower().endswith(".pdf") else "text/plain"
        encoded = base64.b64encode(content).decode()
        created = _http(
            f"{base}/api/v1/documents?access_token={token}",
            {
                "document": {
                    "path": f"/{document.original_name}",
                    "content_base64": f"data:{mime};base64,{encoded}",
                }
            },
            method="POST",
        )
        document_ref = str(((created or {}).get("document") or {}).get("key", ""))
        if not document_ref:
            return SignatureRef()
        signer = _http(
            f"{base}/api/v1/signers?access_token={token}",
            {"signer": {"email": signer_email, "auths": ["email"]}},
            method="POST",
        )
        signer_key = str(((signer or {}).get("signer") or {}).get("key", ""))
        if not signer_key:
            return SignatureRef(document_ref=document_ref)
        linked = _http(
            f"{base}/api/v1/lists?access_token={token}",
            {"list": {"document_key": document_ref, "signer_key": signer_key, "sign_as": "sign"}},
            method="POST",
        )
        listed = (linked or {}).get("list") or {}
        return SignatureRef(
            provider_ref=str(listed.get("request_signature_key", "")),
            document_ref=document_ref,
            sign_url=str(listed.get("url", "")),
        )


_PROVIDERS: dict[str, type] = {
    "autentique": AutentiqueProvider,
    "clicksign": ClicksignProvider,
}


def get_provider() -> Provider:
    """Adaptador escolhido por `ESIGN_PROVIDER`; sem um reconhecido, o `NullProvider`."""
    provider = _PROVIDERS.get(settings.ESIGN_PROVIDER.strip().lower())
    return provider() if provider else NullProvider()


# --- Saída (Biahflow → fornecedor) ------------------------------------------


def has_provider() -> bool:
    """Há fornecedor homologado, ou estamos no registro local do `NullProvider`?"""
    return not isinstance(get_provider(), NullProvider)


def send_for_signature(document: Document, signers: Sequence[Signer]) -> list[SignatureRef]:
    """Envia o documento para assinatura e devolve uma referência **por signatário**.

    Levanta `EsignProviderError` quando **havia um fornecedor** e ele não devolveu referência: sem
    `provider_ref` a solicitação não existe do lado dele, e gravá-la aqui produziria uma assinatura
    que ninguém assina, que o webhook nunca fecha (não há o que casar) e que o lembrete ainda
    cobraria de uma pessoa de verdade — sem link, porque `sign_url` também vem vazio.

    A guarda vale **por signatário** desde a issue #115: numa rodada de três, dois voltarem e um não
    é exatamente o caso em que gravar o que voltou deixa o documento pendente para sempre — a rodada
    nunca fecha, porque a solicitação que falta não tem como ser assinada.

    Sem fornecedor, referência vazia é **correta**: o `NullProvider` registra a intenção e o
    `mark-signed` manual é o caminho previsto. A distinção é toda esta função.

    **A rodada é um fato nosso, e por isso ela é cunhada aqui quando o fornecedor não a dá.** Ela
    nasce no instante em que a casa pede as assinaturas, e só *coincide* com o `id` do
    `createDocument` quando existe um fornecedor para emiti-lo. Deixar `document_ref` vazio jogaria
    todas as solicitações do documento na mesma rodada (`Document.rodada_assinada`), e um documento
    recusado, reenviado e assinado à mão nunca mais contaria como assinado — no modo que o
    `mark-signed` manual existe para servir.
    """
    refs = list(get_provider().send(document, signers))
    if has_provider():
        # `strict=True`: adaptador que devolve lista de tamanho diferente do pedido é defeito de
        # programação, e o par signatário↔referência abaixo já estaria trocado.
        for signer, ref in zip(signers, refs, strict=True):
            if not ref.provider_ref:
                raise EsignProviderError(
                    f"{settings.ESIGN_PROVIDER} não devolveu referência para {document.pk} "
                    f"({signer.role})"
                )
    if refs and not any(ref.document_ref for ref in refs):
        # O prefixo é o que torna a referência auto-explicativa no banco e impede colisão com um
        # id de fornecedor. `not any`, e não `not all`: os signatários de uma chamada vêm do mesmo
        # `createDocument` e ou todos têm a referência, ou nenhum tem.
        rodada = f"local:{uuid.uuid4().hex}"
        refs = [replace(ref, document_ref=rodada) for ref in refs]
    return refs


def paginas_do_pdf(conteudo: bytes) -> int | None:
    """Quantas páginas o PDF tem — `None` quando não é PDF ou não se consegue ler.

    **Nunca levanta**, e essa é a decisão inteira: ela é auxílio de posicionamento, não a operação.
    Um PDF corrompido tem de produzir uma assinatura sem posição — que é o comportamento de hoje,
    ruim mas funcional —, e não uma solicitação de assinatura que falha.

    O reconhecimento é pelo **conteúdo** (`%PDF`) e não pela extensão do nome: `Document.original_name`
    é digitado por gente, e `ALLOWED_DOCUMENT_EXTENSIONS` (`serializers.py`) aceita muito mais
    formatos que PDF — inclusive o `.docx` que o fluxo real usa hoje.
    """
    if not conteudo.startswith(b"%PDF"):
        logger.debug("conteúdo do documento não é PDF; nada a contar")
        return None
    try:
        return len(pypdf.PdfReader(io.BytesIO(conteudo)).pages)
    except Exception as exc:  # noqa: BLE001 - ver a docstring: contar página não derruba o envio
        logger.info("PDF ilegível ao contar páginas (%s); a assinatura vai sem posição", exc)
        return None


def _document_bytes(document: Document) -> bytes:
    """Conteúdo do arquivo, venha ele do Drive ou do storage local (mesma regra do download)."""
    if document.drive_file_id:
        # Mesmo download da action de documento, mesmo tratamento: falha do Drive é do fornecedor.
        try:
            return drive.download_document(document).read()
        except drive.DriveProviderError as exc:
            raise DriveUnavailable() from exc
    if not document.file:
        return b""
    with document.file.open("rb") as handle:
        return handle.read()


def _mail_signer(document: Document, signature: SignatureRequest, subject: str, lead: str) -> None:
    """E-mail do portal ao signatário, com o link quando somos nós que entregamos."""
    link = f"\nAssine aqui: {signature.sign_url}" if signature.sign_url else ""
    send_mail(
        f"{subject} — {document.original_name}",
        f"{lead}{link}",
        None,
        [signature.signer_email],
        fail_silently=True,
    )


def invite_signer(document: Document, signature: SignatureRequest) -> bool:
    """Convida o signatário quando a entrega é nossa (`ESIGN_DELIVERY=link`).

    Na entrega por e-mail quem convida é o fornecedor — o portal não duplica o aviso.
    """
    if not delivers_by_link() or not signature.sign_url:
        return False
    _mail_signer(
        document,
        signature,
        "Documento para assinatura",
        f"Você tem um documento para assinar: '{document.original_name}'.",
    )
    return True


def remind_pending(document: Document) -> int:
    """Envia lembrete a cada signatário ainda pendente do documento e retorna quantos.

    Com provedor homologado o status chega por webhook; o lembrete continua sendo a
    ferramenta de quem acompanha a assinatura (e o único laço quando não há provedor).
    """
    from .models import SignatureRequest

    pending = document.signature_requests.filter(status=SignatureRequest.Status.PENDING)
    reminded = 0
    for signature in pending:
        _mail_signer(
            document,
            signature,
            "Lembrete de assinatura",
            f"Consta pendente a sua assinatura do documento '{document.original_name}'.\n"
            f"Por favor, conclua a assinatura eletrônica.",
        )
        signature.reminded_at = timezone.now()
        signature.save(update_fields=["reminded_at"])
        reminded += 1
    return reminded


# --- Entrada (fornecedor → Biahflow) ----------------------------------------


def find_signature(event: Event) -> SignatureRequest | None:
    """Casa o evento com a solicitação: pela referência do fornecedor, ou documento + e-mail."""
    from .models import SignatureRequest

    if event.provider_ref:
        found = SignatureRequest.objects.filter(provider_ref=event.provider_ref).first()
        if found is not None:
            return found
    if event.document_ref and event.signer_email:
        return SignatureRequest.objects.filter(
            document_ref=event.document_ref, signer_email__iexact=event.signer_email
        ).first()
    return None


def email_da_contraparte(document: Document, document_ref: str | None) -> str:
    """O e-mail da **parte contratante** de uma rodada — nunca o de quem assinou por último.

    Enquanto o único signatário era o cliente, "quem assinou por último" e "o cliente" eram a mesma
    pessoa. Com a casa e uma testemunha na mesma rodada deixaram de ser, e o que dependia daquele
    atalho passava a apontar para quem não vai marcar Discovery nenhum. São **dois** os sítios que
    dependiam: o convite por e-mail (`apply_decision`, abaixo) e o convidado do evento no Google
    (`views._discovery_attendee`) — daí esta função ser pública e não haver duas consultas parecidas.

    Sem `counterparty` na rodada — o que não deveria acontecer, porque a view sempre cria ao menos
    um — devolve vazio e diz por quê no log: quem chama trata a ausência, e nenhum dos dois pode
    levantar por causa disso.
    """
    from .models import SignatureRequest

    if document_ref is None:
        return ""
    contraparte = (
        document.signature_requests.filter(
            document_ref=document_ref,
            signer_role=SignatureRequest.SignerRole.COUNTERPARTY,
        )
        .order_by("id")
        .first()
    )
    if contraparte is None:
        logger.warning(
            "rodada %s do documento %s não tem signatário «counterparty»; "
            "quem depende do endereço da contraparte fica sem ele",
            document_ref or "(sem referência)", document.pk,
        )
        return ""
    return contraparte.signer_email


def _close_contract_artifacts(document, signature_status: str) -> None:  # type: ignore[no-untyped-def]
    """Fecha o artefato de contrato ligado ao documento com a decisão do signatário (FDD 016).

    **A assimetria é deliberada: aceitar exige todos, recusar exige um.** Uma assinatura basta para
    o contrato estar recusado — não há o que esperar depois de alguém dizer não. Aceitar, não: com
    a casa, o cliente e a testemunha na mesma rodada, marcar `ACCEPTED` na primeira assinatura faria
    o contrato ser aceito pela assinatura da **própria casa**, antes de o cliente abrir o link.
    """
    from .models import Artifact, SignatureRequest

    if signature_status == SignatureRequest.Status.SIGNED:
        if not document.is_signed:
            return
        decision = Artifact.Status.ACCEPTED
    elif signature_status == SignatureRequest.Status.DECLINED:
        decision = Artifact.Status.REJECTED
    else:
        return
    contracts = document.artifacts.filter(
        kind=Artifact.Kind.CONTRACT, archived_at__isnull=True
    ).exclude(status=decision)
    for contract in contracts:
        contract.status = decision
        contract.save(update_fields=["status", "decided_at", "updated_at"])


def apply_decision(signature_pk: int, new_status: str) -> SignatureRequest:
    """Aplica a decisão do signatário — o único lugar onde uma assinatura se conclui.

    Recebe **pk** e não a instância já lida, de propósito: a trava é parte da operação, e uma
    API que aceitasse o objeto já carregado permitiria chamá-la sem travar nada. Mesmo par
    `atomic` + `select_for_update` de `convert_to_project` (`views.py`) — o lock na linha é o
    que substitui a unicidade que o banco dava de graça, e é o que serializa duas entregas
    simultâneas do mesmo evento em vez de deixar as duas passarem pela guarda de idempotência
    ao mesmo tempo.

    Idempotente: reentrega do webhook, ou um segundo clique em "marcar como assinado", não muda
    nada e não repete efeito nenhum.
    """
    from . import design_partner, discovery_booking
    from .models import SignatureRequest

    engagement = None
    with transaction.atomic():
        signature = SignatureRequest.objects.select_for_update().get(pk=signature_pk)
        if signature.status == new_status:
            return signature
        signature.status = new_status
        if new_status == SignatureRequest.Status.SIGNED:
            signature.signed_at = timezone.now()
        signature.save(update_fields=["status", "signed_at"])
        document = signature.document
        # O contrato do documento acompanha a decisão do signatário (FDD 016), ainda dentro da
        # transação: é escrita no banco, não efeito externo — mesmo lugar de `seed_work_items`
        # em `convert_to_project`, pelo mesmo motivo.
        _close_contract_artifacts(document, new_status)
        # O mandato de Design Partner nasce do mesmo jeito, e pelo mesmo motivo: assinatura de
        # recusa não abre engagement nenhum.
        if new_status == SignatureRequest.Status.SIGNED:
            engagement = design_partner.abrir_engagement_do_acordo(document)

    # Fora da transação: `notifications.notify` espelha por e-mail quando a flag `email` está
    # ligada, o mesmo padrão de `kickoff.finalize` (chamado fora do `atomic` em `views.py`).
    label = "assinou" if new_status == SignatureRequest.Status.SIGNED else "recusou assinar"
    notifications.notify(
        [document.uploaded_by],
        "esign",
        f"{signature.signer_email} {label} o documento {document.original_name}.",
        "/documentos",
    )
    if engagement is not None:
        notifications.notify(
            [document.uploaded_by],
            "engagement",
            f"O acordo assinado por {engagement.account.name} abriu um mandato de Design Partner.",
            f"/contas/{document.account_id}",
        )
        # E o cliente recebe o link para marcar o Discovery — aqui, fora da transação e junto do
        # aviso interno, porque é o mesmo degrau: o mandato nasceu. Best-effort de propósito
        # (`discovery_booking.enviar_convite` nunca levanta): a assinatura já está aplicada e o
        # webhook do fornecedor reentregaria em laço um evento que já teve efeito.
        discovery_booking.enviar_convite(
            engagement, email_da_contraparte(document, signature.document_ref)
        )
    return signature


def apply_event(event: Event) -> SignatureRequest | None:
    """Aplica o status do fornecedor à solicitação. Idempotente: reentrega não muda nada.

    Retorna a `SignatureRequest` afetada (mesmo quando já estava no status alvo) ou `None`
    quando o evento não corresponde a nenhuma solicitação conhecida.
    """
    signature = find_signature(event)
    if signature is None:
        return None
    return apply_decision(signature.pk, event.status)


def _http(  # pragma: no cover - I/O com o fornecedor
    url: str, payload: dict, method: str
) -> dict | None:
    return _http_raw(
        url, json.dumps(payload).encode(), {"Content-Type": "application/json"}, method=method
    )


def _multipart(fields: Mapping[str, str], filename: str, content: bytes) -> tuple[bytes, str]:
    """Corpo `multipart/form-data` (upload GraphQL) e o Content-Type com o boundary.

    Formato do graphql-multipart-request-spec: os campos `operations` e `map` descrevem a
    mutation e onde o arquivo entra nas variáveis.
    """
    boundary = uuid.uuid4().hex
    parts: list[bytes] = []
    for name, value in fields.items():
        parts.append(
            f'--{boundary}\r\nContent-Disposition: form-data; name="{name}"\r\n\r\n'.encode()
            + value.encode()
            + b"\r\n"
        )
    parts.append(
        f'--{boundary}\r\nContent-Disposition: form-data; name="file"; filename="{filename}"\r\n'
        f"Content-Type: application/octet-stream\r\n\r\n".encode()
    )
    parts.append(content + b"\r\n")
    parts.append(f"--{boundary}--\r\n".encode())
    return b"".join(parts), f"multipart/form-data; boundary={boundary}"


def _http_raw(  # pragma: no cover - I/O com o fornecedor
    url: str, body: bytes, headers: Mapping[str, str], method: str = "POST"
) -> dict | None:
    request = urllib.request.Request(url, data=body, method=method, headers=dict(headers))
    try:
        with urllib.request.urlopen(request, timeout=15) as response:  # noqa: S310
            raw = response.read()
        return json.loads(raw) if raw else None
    except (urllib.error.URLError, TimeoutError, ValueError) as exc:
        logger.warning("Falha ao falar com o fornecedor de assinatura (%s): %s", url, exc)
        return None
