"""Mensagens por WhatsApp atrás de flag (`whatsapp`), com dois provedores e fallback ordenado.

**WhatsApp carrega coordenação. O One carrega conteúdo.**

Coordenação é "estou entrando na sala", "atrasei dez minutos", "quem participa amanhã?". Achado,
decisão, custo apurado e entregável vão para o One, atrás da marca de publicável (ADR 0060) — e
mandá-los por aqui **contornaria o gate de revisão humana** sem ninguém perceber, porque a
publicação é ato com autor e sustentação embaixo, e uma mensagem não é nem uma coisa nem outra.
Este módulo não tem como impedir isso sozinho: quem chamar é quem decide o que escreve, e é por
isso que a regra está escrita aqui, no lugar em que quem for chamar passa antes.

O canal também **não muda o gate**: a ADR 0031 decidiu que "WhatsApp é canal novo, não gate novo",
e a FDD 036 repete. O degrau determinístico sai sozinho; texto gerado por IA continua sendo pedido,
revisado e enviado por uma pessoa — trocar e-mail por WhatsApp não afrouxa nada disso.

**O chamador é o kickoff, e ele só cria grupo** (issue #110). Ao nascer o projeto,
`kickoff.finalize` abre o grupo do cliente e **guarda** a referência em `Project` — mandar
mensagem ao grupo depois de criado (`send_group_text`) segue sem chamador, e isso é deliberado
nesta rodada. O adaptador nasceu antes do chamador de propósito, para o desenho do fallback ser
decidido sozinho e não no meio de outra feature; o preço disso foi uma temporada inteira sem
ninguém exercitá-lo, e o defeito que a primeira chamada real encontrou está na ADR 0064.

**Criar grupo tem teto próprio, e resposta incerta é reconciliada** (ADR 0064). `_request` aceita
`timeout` por operação, porque mandar texto e criar grupo estão em ordens de grandeza diferentes
de latência; e `create_group` que termina em `UNCERTAIN` pergunta ao **mesmo** provedor se o grupo
nasceu, aceitando só o casamento exato e único de nome.

O molde é o de `esign.py` e `payments.py` — `Protocol`, adaptadores, `NullProvider`, `_PROVIDERS`,
flag, sonda —, com **duas divergências deliberadas**:

- **O resultado tem quatro estados, não um booleano.** O `_http_raw` do `esign.py` engole todo erro
  em `None`, e o runbook registra que isso já produziu defeito ali, porque `None` ficou
  indistinguível de sucesso. Para o fallback esse padrão é inutilizável: um booleano não separa
  "não entregou" de "não sei se entregou", e essas duas respostas mandam fazer coisas opostas.
- **A resolução é uma lista ordenada, não um provedor só.** `WHATSAPP_PROVIDERS="zapi,uazapi"`
  tenta em ordem; o resultado diz quem entregou e por onde passou, senão depurar "o cliente não
  recebeu" vira arqueologia.

As chamadas HTTP reais ficam fora da cobertura (`# pragma: no cover`) e passam todas por
`_request`, a única costura de I/O do módulo — é ela que o teste substitui. A suíte não atravessa
a rede para provar um adapter (ADR 0059).
"""

from __future__ import annotations

import http.client
import json
import logging
import re
import socket
import urllib.error
import urllib.request
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass, field, replace
from enum import Enum
from typing import Protocol

from django.conf import settings

from . import flags

logger = logging.getLogger(__name__)

DESLIGADA = "integração desligada"
SEM_PROVEDOR = "sem provedor configurado"


def is_enabled() -> bool:
    return flags.is_enabled("whatsapp")


# --- O resultado, e a decisão que mora nele ---------------------------------


class Delivery(Enum):
    """O que aconteceu com a mensagem — quatro estados, e não um booleano.

    Os nomes dos estados no spec de origem estão em português; aqui eles são o inglês canônico
    que a invariante 15 do `language-map` exige de todo valor novo de enum. O de-para é direto:
    `DELIVERED` = entregue, `UNAVAILABLE` = indisponível, `REFUSED` = recusada,
    `UNCERTAIN` = incerta.

    | Estado        | O que significa                                             | Cai para o próximo? |
    | ------------- | ----------------------------------------------------------- | ------------------- |
    | `DELIVERED`   | o provedor aceitou a mensagem                                | não                 |
    | `UNAVAILABLE` | **este** provedor não pôde aceitar, outro poderia            | **sim**             |
    | `REFUSED`     | a mensagem é inválida em si; o outro recusaria igual         | não                 |
    | `UNCERTAIN`   | timeout, 5xx, conexão cortada — **pode ter entregado**       | não                 |
    """

    DELIVERED = "delivered"
    UNAVAILABLE = "unavailable"
    REFUSED = "refused"
    UNCERTAIN = "uncertain"

    @property
    def tries_the_next_provider(self) -> bool:
        """O fallback assume **só em falha inequívoca** — e este é o lugar único dessa decisão.

        `UNCERTAIN` **não** reenvia. Se a Z-API aceitou e o retorno se perdeu, tentar a UAZAPI
        manda a **mesma mensagem duas vezes** ao cliente; para "sua sessão é amanhã às 10h", dois
        avisos fazem o cliente ligar perguntando qual vale. Aceita-se deixar de enviar para nunca
        duplicar — quem opera vê a tentativa no log e no `attempts`, e decide com a mão.

        `REFUSED` também não cai, por outro motivo: o número mal formado ou o payload inválido
        seriam recusados igual pelo segundo provedor, e a segunda chamada só gastaria tempo.
        """
        return self is Delivery.UNAVAILABLE


@dataclass(frozen=True)
class Attempt:
    """Uma passagem por um provedor — o rastro que responde "por onde isto passou?"."""

    provider: str
    status: Delivery
    detail: str = ""


@dataclass(frozen=True)
class _Result:
    """O que toda operação devolve: o estado, quem respondeu e o caminho até aqui.

    Enum **e** dataclass, e não um dos dois: o estado é um conjunto fechado de quatro valores com
    uma regra pendurada (`tries_the_next_provider`), que é exatamente o que um enum guarda bem; o
    resultado carrega mais do que o estado — quem entregou, a referência da mensagem, a trilha de
    tentativas —, e isso é uma estrutura. Espremer as duas coisas numa só faria o chamador
    comparar strings para decidir o fallback.
    """

    status: Delivery
    provider: str = ""
    detail: str = ""
    attempts: tuple[Attempt, ...] = ()


@dataclass(frozen=True)
class MessageResult(_Result):
    """Envio de mensagem. `reference` é o id da mensagem no provedor, quando ele o devolve."""

    reference: str = ""


@dataclass(frozen=True)
class GroupResult(_Result):
    """Criação de grupo. `DELIVERED` aqui significa "o provedor aceitou e o grupo existe"."""

    group_id: str = ""
    invite_url: str = ""


# --- A costura de I/O -------------------------------------------------------


@dataclass(frozen=True)
class HttpAnswer:
    """O que voltou do provedor — ou o que impediu de voltar.

    Guardar a exceção em vez de classificá-la dentro do I/O é o que torna a classificação
    testável: `_request` é a única função que toca a rede e fica fora da cobertura, e
    `classify` é pura.
    """

    status_code: int = 0
    body: dict = field(default_factory=dict)
    error: BaseException | None = None


def _timeout(timeout: float | None) -> float:
    """O teto efetivo da chamada — **por operação**, e não um só para tudo (ADR 0064).

    Fora de `_request` pelo motivo de `classify`: `_request` é a única função que toca a rede e
    fica fora da cobertura, então uma regra escondida dentro dela é uma regra que nenhum teste
    alcança. Quem não passa nada fica exatamente onde estava, no teto de mensagem.
    """
    return timeout or settings.WHATSAPP_TIMEOUT_SECONDS


def _request(  # pragma: no cover - I/O com o fornecedor
    url: str,
    headers: Mapping[str, str],
    payload: dict | None = None,
    method: str = "POST",
    timeout: float | None = None,
) -> HttpAnswer:
    """Fala com o provedor e devolve o que voltou. **Nunca levanta** — classificar é de quem lê."""
    data = json.dumps(payload).encode() if payload is not None else None
    request = urllib.request.Request(url, data=data, method=method, headers=dict(headers))
    espera = _timeout(timeout)
    try:
        with urllib.request.urlopen(request, timeout=espera) as answer:
            return HttpAnswer(status_code=answer.status, body=_body(answer.read()))
    except urllib.error.HTTPError as exc:
        # 4xx/5xx é resposta, não falha de transporte: o corpo é justamente o que diz o motivo.
        return HttpAnswer(status_code=exc.code, body=_body(exc.read()))
    except Exception as exc:  # noqa: BLE001 - transporte; quem decide o estado é `classify`
        return HttpAnswer(error=exc)


# A chave sob a qual um JSON que não é objeto (uma lista no topo) é entregue a quem lê o corpo.
_ITEMS = "items"


def _body(raw: bytes) -> dict:  # pragma: no cover - só existe para `_request`
    """O corpo do provedor como `dict` — **inclusive quando ele vem como lista**.

    O retorno é `dict` porque `classify`/`_provider_error` dereferenciam `body.get(...)`; devolver
    a lista crua quebraria os dois. Mas descartá-la, que era o que este `return` fazia, é pior e
    mais silencioso: uma listagem de grupos é justamente a resposta que os fornecedores mandam
    como array no topo, e a reconciliação (`find_group`) receberia `{}` — nunca acharia nada, sem
    erro nenhum aparecendo. Embrulhar preserva o dado e mantém o tipo.
    """
    try:
        parsed = json.loads(raw) if raw else {}
    except ValueError:
        return {}
    if isinstance(parsed, dict):
        return parsed
    if isinstance(parsed, list):
        return {_ITEMS: parsed}
    return {}


# --- Classificação: da resposta (ou da falta dela) para um dos quatro estados ---

# Payload inválido em si. É o que a UAZAPI documenta como "requisição inválida" / "payload
# inválido", e é a única família de erro que o segundo provedor recusaria igual.
_REFUSED_CODES = frozenset({400, 422})


def _from_error(error: BaseException) -> tuple[Delivery, str]:
    """Falha de transporte → estado. O caminho conservador é `UNCERTAIN`, nunca `UNAVAILABLE`."""
    if isinstance(error, urllib.error.URLError) and isinstance(error.reason, BaseException):
        return _from_error(error.reason)
    if isinstance(error, TimeoutError):
        # **Sempre incerta, mesmo parecendo falha de conexão.** Distinguir "timeout antes de
        # enviar" de "timeout esperando resposta" não é confiável, e o erro caro é o duplicado.
        return Delivery.UNCERTAIN, "timeout falando com o provedor"
    if isinstance(error, ConnectionRefusedError | socket.gaierror):
        return Delivery.UNAVAILABLE, f"não foi possível alcançar o provedor ({error})"
    if isinstance(error, ConnectionResetError | BrokenPipeError | http.client.IncompleteRead):
        return Delivery.UNCERTAIN, f"conexão cortada no meio ({error})"
    if isinstance(error, urllib.error.URLError):
        return Delivery.UNAVAILABLE, f"não foi possível alcançar o provedor ({error.reason})"
    return Delivery.UNCERTAIN, f"falha não classificada ({error.__class__.__name__}: {error})"


def _from_status_code(code: int, body: dict) -> tuple[Delivery, str]:
    motivo = _provider_error(body)
    if 200 <= code < 300:
        return Delivery.DELIVERED, motivo
    if code in _REFUSED_CODES:
        return Delivery.REFUSED, f"HTTP {code}: {motivo or 'requisição recusada pelo provedor'}"
    if 400 <= code < 500:
        # 401/403 (token), 404 (instância inexistente), 409, 415, 429 (teto de requisição): este
        # provedor não pode aceitar agora, e o outro pode — é o caso que o fallback existe para
        # cobrir. A instância desconectada também mora aqui.
        return Delivery.UNAVAILABLE, f"HTTP {code}: {motivo or 'provedor não aceitou a chamada'}"
    if 500 <= code:
        # 5xx pode ter entregado antes de estourar do lado de lá. Não reenvia.
        return Delivery.UNCERTAIN, f"HTTP {code}: {motivo or 'erro interno do provedor'}"
    return Delivery.UNCERTAIN, f"HTTP {code} inesperado: {motivo or 'resposta não reconhecida'}"


def classify(answer: HttpAnswer) -> tuple[Delivery, str]:
    """A resposta do provedor em um dos quatro estados, com o motivo em texto."""
    if answer.error is not None:
        return _from_error(answer.error)
    return _from_status_code(answer.status_code, answer.body)


def _provider_error(body: dict) -> str:
    """A mensagem de erro do provedor, quando ela vem — os dois usam a chave `error`."""
    return str(body.get("error") or body.get("message") or "")[:200]


# --- Contrato do adaptador --------------------------------------------------


class Provider(Protocol):
    """Contrato do adaptador de WhatsApp (Z-API e UAZAPI hoje)."""

    name: str

    def send_text(self, to: str, body: str) -> MessageResult:
        """Manda uma mensagem 1:1."""

    def create_group(self, name: str, participants: Sequence[str]) -> GroupResult:
        """Cria o grupo e devolve a referência dele (id e link de convite, quando houver)."""

    def send_group_text(self, group_ref: str, body: str) -> MessageResult:
        """Manda uma mensagem ao grupo já criado."""

    def ping(self) -> tuple[bool, str]:
        """A instância está conectada? Leitura pura — **não manda mensagem** (FDD 024)."""

    # **`find_group` não entra aqui, e a ausência é a decisão** (ADR 0064). Listar grupos por nome
    # é capacidade *opcional*: a UAZAPI documenta `GET /group/list`, e a Z-API **não tem endpoint
    # verificado** para isso. Declará-lo obrigatório no Protocol obrigaria a inventar o caminho da
    # Z-API, e endpoint suposto em código de produção é pior do que capacidade ausente — a
    # ausência ao menos aparece no `detail`. Quem consome resolve por
    # `getattr(provider, "find_group", None)`, o mesmo padrão com que `integrations._probe_esign`
    # e `_probe_payments` tratam o `ping` opcional. A Z-API entra no dia em que o endpoint for
    # **verificado** na documentação dela, não suposto.


class NullProvider:
    """Sem provedor configurado: registra a intenção e **não promete nada**.

    É o modo em que o produto roda sem credencial, como o `NullProvider` do e-sign — e aqui ele
    não é modo degradado nem modo previsto de operação: é a ausência do canal. Ninguém recebe
    mensagem, e o resultado diz isso com todas as letras em vez de devolver um sucesso vazio.
    """

    name = "null"

    def send_text(self, to: str, body: str) -> MessageResult:
        logger.info("WhatsApp %s: mensagem para %s não enviada", SEM_PROVEDOR, _mask(to))
        return MessageResult(Delivery.UNAVAILABLE, provider=self.name, detail=SEM_PROVEDOR)

    def create_group(self, name: str, participants: Sequence[str]) -> GroupResult:
        logger.info("WhatsApp %s: grupo '%s' não criado", SEM_PROVEDOR, name)
        return GroupResult(Delivery.UNAVAILABLE, provider=self.name, detail=SEM_PROVEDOR)

    def send_group_text(self, group_ref: str, body: str) -> MessageResult:
        logger.info("WhatsApp %s: mensagem ao grupo %s não enviada", SEM_PROVEDOR, group_ref)
        return MessageResult(Delivery.UNAVAILABLE, provider=self.name, detail=SEM_PROVEDOR)

    def ping(self) -> tuple[bool, str]:
        return True, SEM_PROVEDOR


class ZApiProvider:
    """Adaptador Z-API: instância e token na URL, `Client-Token` da conta no header.

    A URL é `/instances/{id}/token/{token}/{recurso}` e a autenticação da **conta** é um header
    à parte, opcional: o `Client-Token` só existe se quem administra a conta ligou a validação
    por token no painel. Por isso ele não está em `requires` — o código só o dereferencia quando
    está preenchido, e cobrá-lo recusaria uma instalação que está certa.

    Envio devolve `{"zaapId", "messageId", "id"}`; criação de grupo devolve `{"phone",
    "invitationLink", "phonesNotAdded"}`, onde `phone` é o id do grupo (`…-group`) e serve como
    destino de mensagem — que é o motivo de `send_group_text` delegar a `send_text`.
    """

    name = "zapi"
    DEFAULT_BASE = "https://api.z-api.io"

    def _url(self, resource: str) -> str:
        base = (settings.WHATSAPP_ZAPI_API_BASE or self.DEFAULT_BASE).rstrip("/")
        instance = settings.WHATSAPP_ZAPI_INSTANCE_ID
        return f"{base}/instances/{instance}/token/{settings.WHATSAPP_ZAPI_TOKEN}/{resource}"

    def _headers(self) -> dict[str, str]:
        headers = {"Content-Type": "application/json"}
        if settings.WHATSAPP_ZAPI_CLIENT_TOKEN:
            headers["Client-Token"] = settings.WHATSAPP_ZAPI_CLIENT_TOKEN
        return headers

    def send_text(self, to: str, body: str) -> MessageResult:  # pragma: no cover - I/O
        return self.read_message(
            _request(self._url("send-text"), self._headers(), {"phone": _to(to), "message": body})
        )

    def create_group(  # pragma: no cover - I/O com o fornecedor
        self, name: str, participants: Sequence[str]
    ) -> GroupResult:
        return self.read_group(
            _request(
                self._url("create-group"),
                self._headers(),
                # `autoInvite`: quem não pode ser adicionado direto recebe convite privado, em vez
                # de ficar de fora sem ninguém notar.
                {"groupName": name, "phones": [_to(p) for p in participants], "autoInvite": True},
                timeout=settings.WHATSAPP_GROUP_TIMEOUT_SECONDS,
            )
        )

    def send_group_text(self, group_ref: str, body: str) -> MessageResult:  # pragma: no cover
        """O id do grupo entra no mesmo campo `phone` do envio 1:1 — é o contrato da Z-API."""
        return self.send_text(group_ref, body)

    def ping(self) -> tuple[bool, str]:  # pragma: no cover - I/O com o fornecedor
        """Consulta o status da instância. Leitura pura: não manda mensagem e não cria grupo."""
        return self.read_ping(_request(self._url("status"), self._headers(), method="GET"))

    @classmethod
    def read_message(cls, answer: HttpAnswer) -> MessageResult:
        """Lê a resposta do envio (separada do I/O para ficar testável, como no `esign`)."""
        status, detail = classify(answer)
        if status is not Delivery.DELIVERED:
            return MessageResult(status, provider=cls.name, detail=detail)
        reference = str(answer.body.get("messageId") or answer.body.get("zaapId") or "")
        return _delivered_message(cls.name, reference, detail)

    @classmethod
    def read_group(cls, answer: HttpAnswer) -> GroupResult:
        status, detail = classify(answer)
        if status is not Delivery.DELIVERED:
            return GroupResult(status, provider=cls.name, detail=detail)
        return _created_group(
            cls.name,
            str(answer.body.get("phone", "")),
            str(answer.body.get("invitationLink", "")),
            detail,
        )

    @classmethod
    def read_ping(cls, answer: HttpAnswer) -> tuple[bool, str]:
        status, detail = classify(answer)
        if status is not Delivery.DELIVERED:
            return False, detail or "a Z-API não respondeu ao status"
        if not answer.body.get("connected"):
            return False, str(answer.body.get("error") or "instância desconectada")
        return True, "instância conectada"


class UazapiProvider:
    """Adaptador UAZAPI: base por instância (`https://{subdomínio}.uazapi.com`), token no header.

    O token vai no header `token` (é o `apiKey` declarado no OpenAPI do fornecedor). Envio é
    `POST /send/text` com `{"number", "text"}` e devolve a mensagem gravada (`id`/`messageid`);
    grupo é `POST /group/create` com `{"name", "participants"}` e devolve o grupo com `JID` e
    `invite_link`; status é `GET /instance/status`, que traz `status.connected`.

    `number` é "o id do chat", então o JID do grupo cabe no mesmo campo — a mesma delegação de
    `send_group_text` que a Z-API permite, pelo mesmo motivo.
    """

    name = "uazapi"
    DEFAULT_BASE = "https://free.uazapi.com"

    def _url(self, path: str) -> str:
        base = (settings.WHATSAPP_UAZAPI_API_BASE or self.DEFAULT_BASE).rstrip("/")
        return f"{base}/{path}"

    def _headers(self) -> dict[str, str]:
        return {"Content-Type": "application/json", "token": settings.WHATSAPP_UAZAPI_TOKEN}

    def send_text(self, to: str, body: str) -> MessageResult:  # pragma: no cover - I/O
        return self.read_message(
            _request(self._url("send/text"), self._headers(), {"number": _to(to), "text": body})
        )

    def create_group(  # pragma: no cover - I/O com o fornecedor
        self, name: str, participants: Sequence[str]
    ) -> GroupResult:
        return self.read_group(
            _request(
                self._url("group/create"),
                self._headers(),
                {"name": name, "participants": [_to(p) for p in participants]},
                timeout=settings.WHATSAPP_GROUP_TIMEOUT_SECONDS,
            )
        )

    def find_group(self, name: str) -> GroupResult:  # pragma: no cover - I/O com o fornecedor
        """Procura um grupo já existente por nome — a reconciliação depois do `UNCERTAIN`.

        `GET /group/list` é o único endpoint de listagem **verificado** entre os dois provedores
        (issue #111), e é por isso que este método existe aqui e não no Protocol.
        """
        return self.read_group_list(
            name, _request(self._url("group/list"), self._headers(), method="GET")
        )

    def send_group_text(self, group_ref: str, body: str) -> MessageResult:  # pragma: no cover
        """O JID do grupo entra no mesmo campo `number` — `number` é o id do chat, não o telefone."""
        return self.send_text(group_ref, body)

    def ping(self) -> tuple[bool, str]:  # pragma: no cover - I/O com o fornecedor
        return self.read_ping(_request(self._url("instance/status"), self._headers(), method="GET"))

    @classmethod
    def read_message(cls, answer: HttpAnswer) -> MessageResult:
        status, detail = classify(answer)
        if status is not Delivery.DELIVERED:
            return MessageResult(status, provider=cls.name, detail=detail)
        reference = str(answer.body.get("messageid") or answer.body.get("id") or "")
        return _delivered_message(cls.name, reference, detail)

    @classmethod
    def read_group(cls, answer: HttpAnswer) -> GroupResult:
        status, detail = classify(answer)
        if status is not Delivery.DELIVERED:
            return GroupResult(status, provider=cls.name, detail=detail)
        return _created_group(
            cls.name,
            str(answer.body.get("JID", "")),
            str(answer.body.get("invite_link", "")),
            detail,
        )

    @classmethod
    def read_group_list(cls, name: str, answer: HttpAnswer) -> GroupResult:
        """A listagem em um `GroupResult`: `DELIVERED` **só** no casamento exato e único.

        **"Exatamente um" é a regra inteira, e não zelo.** Dois grupos com o mesmo nome significam
        que não se sabe qual é o que acabou de nascer; escolher um seria gravar a referência
        errada, e uma referência errada é pior do que nenhuma — com ela, quem opera acha que sabe.
        Sem ela, sabe que não sabe, e o `detail` diz por quê.

        O nome é comparado com `strip()` dos dois lados e **nada mais**: não se normaliza acento
        nem caixa, porque o nome é o que a casa mandou criar, e "normalizar" abriria casamento
        falso entre dois grupos que o WhatsApp considera diferentes.
        """
        status, detail = classify(answer)
        if status is not Delivery.DELIVERED:
            return GroupResult(status, provider=cls.name, detail=detail)
        procurado = (name or "").strip()
        casaram = [
            grupo
            for grupo in _group_list(answer.body)
            if str(grupo.get("name") or grupo.get("subject") or "").strip() == procurado
        ]
        if len(casaram) != 1:
            achados = "nenhum grupo" if not casaram else f"{len(casaram)} grupos"
            return GroupResult(
                Delivery.UNCERTAIN,
                provider=cls.name,
                detail=f"reconciliação inconclusiva: {achados} com o nome '{procurado}'",
            )
        achado = casaram[0]
        return _created_group(
            cls.name,
            str(achado.get("JID") or achado.get("id") or ""),
            str(achado.get("invite_link") or ""),
            detail,
        )

    @classmethod
    def read_ping(cls, answer: HttpAnswer) -> tuple[bool, str]:
        status, detail = classify(answer)
        if status is not Delivery.DELIVERED:
            return False, detail or "a UAZAPI não respondeu ao status"
        estado = answer.body.get("status")
        conectada = estado.get("connected") if isinstance(estado, dict) else estado == "connected"
        if not conectada:
            return False, "instância desconectada"
        return True, "instância conectada"


def _delivered_message(provider: str, reference: str, detail: str) -> MessageResult:
    """2xx **com** id de mensagem é entrega; 2xx sem id é incerta, e não sucesso.

    Os dois provedores respondem 200 com um corpo de erro em alguns casos, e a documentação de
    nenhum dos dois enumera quais. O caminho conservador é o que não duplica: sem id não se afirma
    entrega, e também não se reenvia por outro provedor.
    """
    if not reference:
        return MessageResult(
            Delivery.UNCERTAIN,
            provider=provider,
            detail=f"200 sem id de mensagem: {detail or 'corpo não reconhecido'}",
        )
    return MessageResult(Delivery.DELIVERED, provider=provider, reference=reference)


def _created_group(provider: str, group_id: str, invite_url: str, detail: str) -> GroupResult:
    if not group_id:
        return GroupResult(
            Delivery.UNCERTAIN,
            provider=provider,
            detail=f"200 sem id de grupo: {detail or 'corpo não reconhecido'}",
        )
    return GroupResult(
        Delivery.DELIVERED, provider=provider, group_id=group_id, invite_url=invite_url
    )


def _group_list(body: dict) -> list[dict]:
    """Os grupos de uma listagem, nas **duas** formas em que ela pode chegar.

    A documentação da UAZAPI não fixa se `GET /group/list` responde um array no topo ou um objeto
    com os grupos numa chave, e adivinhar uma delas faria a reconciliação falhar em silêncio na
    outra. O array no topo chega aqui sob `_ITEMS`, embrulhado por `_body` — que é o motivo de
    aquele embrulho existir.
    """
    for chave in ("groups", _ITEMS):
        valor = body.get(chave)
        if isinstance(valor, list):
            return [item for item in valor if isinstance(item, dict)]
    return []


_SO_DIGITOS = re.compile(r"\D")
_TEM_LETRA = re.compile(r"[^\W\d_]", re.UNICODE)


def _to(destination: str) -> str:
    """Normaliza o destino: telefone vira só dígitos, id de chat passa inteiro.

    Id de grupo (`120363…-group` na Z-API, `…@g.us` na UAZAPI) não é telefone e não pode perder
    caractere — os dois provedores aceitam os dois no mesmo campo, e apagar o sufixo mandaria a
    mensagem para um número que não existe. O que separa os dois é **letra ou `@`**, e não o
    hífen: `+55 (11) 99999-9999` é telefone pontuado e tem hífen também.
    """
    limpo = (destination or "").strip()
    if "@" in limpo or _TEM_LETRA.search(limpo):
        return limpo
    return _SO_DIGITOS.sub("", limpo)


def _mask(destination: str) -> str:
    """Telefone em log é dado pessoal: só os quatro últimos dígitos identificam o suficiente."""
    limpo = _to(destination)
    return f"…{limpo[-4:]}" if len(limpo) > 4 else "…"


# --- Resolução ordenada -----------------------------------------------------

_PROVIDERS: dict[str, type] = {
    "zapi": ZApiProvider,
    "uazapi": UazapiProvider,
}


def provider_names() -> list[str]:
    """Os provedores nomeados em `WHATSAPP_PROVIDERS`, **na ordem em que foram escritos**."""
    return [nome.strip().lower() for nome in settings.WHATSAPP_PROVIDERS.split(",") if nome.strip()]


def get_providers() -> list[Provider]:
    """Os adaptadores na ordem configurada; sem nenhum reconhecido, o `NullProvider` sozinho."""
    escolhidos: list[Provider] = [
        _PROVIDERS[nome]() for nome in provider_names() if nome in _PROVIDERS
    ]
    return escolhidos or [NullProvider()]


def has_provider() -> bool:
    """Há provedor configurado, ou estamos no registro local do `NullProvider`?"""
    return not isinstance(get_providers()[0], NullProvider)


def _attempt(provider: Provider, result: _Result, operation: str) -> Attempt:
    """Registra a passagem por um provedor. `UNCERTAIN` sobe para `warning`, e não é zelo.

    É o único estado em que ninguém sabe se o cliente recebeu **e** o produto decidiu não tentar
    de novo. Ele precisa aparecer para quem opera com a mesma cor de um problema, senão a decisão
    de não duplicar vira a decisão de não avisar. Notificar **quem** é do chamador: só ele sabe de
    quem era a mensagem, e este módulo não tem destinatário para escolher.
    """
    registrar = logger.warning if result.status is Delivery.UNCERTAIN else logger.info
    registrar(
        "WhatsApp %s por %s: %s (%s)",
        operation, provider.name, result.status.value, result.detail or "sem detalhe",
    )
    return Attempt(result.provider or provider.name, result.status, result.detail)


def _first_that_delivers[R: _Result](operation: str, call: Callable[[Provider], R]) -> R:
    """Tenta em ordem e para na primeira que entregar — ou no primeiro estado que manda parar.

    Quem decide continuar é `Delivery.tries_the_next_provider`, e não este laço: a regra de
    fallback tem um lugar só, senão a próxima refatoração a reescreve como "tenta sempre".
    """
    providers = get_providers()
    result = call(providers[0])
    attempts = [_attempt(providers[0], result, operation)]
    for provider in providers[1:]:
        if not result.status.tries_the_next_provider:
            break
        result = call(provider)
        attempts.append(_attempt(provider, result, operation))
    return replace(result, attempts=tuple(attempts))


def send_text(to: str, body: str) -> MessageResult:
    """Manda uma mensagem 1:1 pelo primeiro provedor que entregar."""
    if not is_enabled():
        logger.info("WhatsApp %s: mensagem para %s não enviada", DESLIGADA, _mask(to))
        return MessageResult(Delivery.UNAVAILABLE, detail=DESLIGADA)
    return _first_that_delivers("send_text", lambda provider: provider.send_text(to, body))


RECONCILIADO = "recuperado por reconciliação depois de resposta incerta"


def _reconcile_group(name: str, result: GroupResult) -> GroupResult:
    """Depois de um `UNCERTAIN`, pergunta ao **mesmo** provedor se o grupo nasceu mesmo.

    Um `UNCERTAIN` na criação é o pior estado que existe aqui: o grupo pode estar do outro lado,
    com o id perdido — foi o que aconteceu em 03/09/2026 (issue #111). Reconciliar é a única
    forma de recuperar a referência sem arriscar o erro caro, que é criar o segundo grupo.

    **Contra o provedor da última tentativa, e não contra todos**: um grupo criado pela Z-API não
    existe do lado da UAZAPI — é a mesma razão já escrita na docstring de `send_group_text`.

    A capacidade é **opcional** (`getattr`, no padrão de `integrations._probe_esign`): provedor
    que não sabe listar grupos devolve o resultado intacto, e nada estoura.
    """
    ultimo = result.attempts[-1].provider if result.attempts else result.provider
    provider = next((p for p in get_providers() if p.name == ultimo), None)
    find_group = getattr(provider, "find_group", None)
    if find_group is None:
        return result
    achado: GroupResult = find_group(name)
    attempts = (*result.attempts, Attempt(ultimo, achado.status, f"find_group: {achado.detail}"))
    if achado.status is not Delivery.DELIVERED:
        logger.warning(
            "WhatsApp reconciliação de grupo por %s: %s (%s)",
            ultimo, achado.status.value, achado.detail or "sem detalhe",
        )
        return replace(result, attempts=attempts)
    logger.info("WhatsApp reconciliação de grupo por %s: referência recuperada", ultimo)
    return replace(
        achado,
        # Quem lê o log precisa separar "respondeu na hora" de "achamos depois": os dois chegam
        # como `DELIVERED`, e sem esta frase a diferença some.
        detail=f"{RECONCILIADO} ({result.detail or 'sem detalhe'})",
        attempts=attempts,
    )


def create_group(name: str, participants: Sequence[str]) -> GroupResult:
    """Cria um grupo pelo primeiro provedor que aceitar e devolve a referência dele.

    Desde a issue #110 há um chamador, e ele **guarda** a referência: `kickoff.finalize` grava o
    id e o link de convite no dono do canal — `Engagement.whatsapp_group_id`/
    `whatsapp_group_invite_url` desde a issue #119 (o par homônimo de `Project` é o legado de
    antes). A gravação é de quem chama — este módulo não conhece modelo nenhum —, e é a existência
    dela que torna a reconciliação abaixo útil: recuperar um id que ninguém guardaria não serviria
    para nada.

    Resposta incerta passa por `_reconcile_group` antes de voltar (ADR 0064).
    """
    if not is_enabled():
        logger.info("WhatsApp %s: grupo '%s' não criado", DESLIGADA, name)
        return GroupResult(Delivery.UNAVAILABLE, detail=DESLIGADA)
    result = _first_that_delivers(
        "create_group", lambda provider: provider.create_group(name, participants)
    )
    if result.status is Delivery.UNCERTAIN:
        return _reconcile_group(name, result)
    return result


def send_group_text(group_ref: str, body: str) -> MessageResult:
    """Manda uma mensagem a um grupo já criado.

    A referência é a que **aquele** provedor devolveu, então o fallback aqui é mais estreito do
    que parece: um id de grupo da Z-API não existe do lado da UAZAPI. Ainda assim a ordem é
    respeitada — quem chamar é quem sabe de onde veio a referência.
    """
    if not is_enabled():
        logger.info("WhatsApp %s: mensagem ao grupo %s não enviada", DESLIGADA, group_ref)
        return MessageResult(Delivery.UNAVAILABLE, detail=DESLIGADA)
    return _first_that_delivers(
        "send_group_text", lambda provider: provider.send_group_text(group_ref, body)
    )
