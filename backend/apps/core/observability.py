"""Identidade de requisição, log estruturado e rastreamento de erro (FDD 020, ADR 0012).

Três peças que só fazem sentido juntas:

- o **request-id**, guardado em `ContextVar` porque o log precisa dele em lugares que não
  recebem o `request` (um `logger.exception` dentro de `ai.py`, um sinal, um comando);
- o `RequestIdFilter`/`JsonFormatter`, que fazem esse id sair em toda linha de log — é o que
  liga o erro que o usuário viu à linha do container;
- o `init_sentry()`, que é opcional: sem `SENTRY_DSN` o SDK nunca é inicializado e o processo
  se comporta exatamente como antes (ADR 0012).

`ContextVar` e não `threading.local` porque o `ContextVar` também acompanha código assíncrono, e
porque o gunicorn recicla worker (`max_requests`) sem limpar `local`.
"""

from __future__ import annotations

import json
import logging
import re
from contextvars import ContextVar
from typing import Any
from uuid import uuid4

REQUEST_ID_HEADER = "X-Request-ID"
# `HttpRequest.META` normaliza o header para este nome.
REQUEST_ID_META = "HTTP_X_REQUEST_ID"
# Fora de uma requisição (comando de management, shell, worker) não há id — e é melhor um marcador
# fixo do que um campo ausente, que quebraria o parser do coletor de log.
NO_REQUEST_ID = "-"

# O id vem de fora (do nginx ou do cliente) e vai parar cru no log. Sem esta trava, um
# `X-Request-ID` com quebra de linha injeta uma entrada falsa no log — a versão em texto do
# log injection. O tamanho é cortado porque um header de 8 KB não pode virar 8 KB por linha.
_ALLOWED = re.compile(r"[^A-Za-z0-9._-]")
MAX_REQUEST_ID_LENGTH = 64

_request_id: ContextVar[str] = ContextVar("request_id", default=NO_REQUEST_ID)


def new_request_id() -> str:
    return uuid4().hex


def sanitize_request_id(raw: str) -> str:
    """Devolve o id utilizável, ou vazio quando o que veio não sobrou nada de aproveitável."""
    return _ALLOWED.sub("", raw or "")[:MAX_REQUEST_ID_LENGTH]


def get_request_id() -> str:
    return _request_id.get()


def set_request_id(request_id: str) -> object:
    """Devolve o token do `ContextVar`, para o middleware restaurar o valor anterior."""
    return _request_id.set(request_id)


def reset_request_id(token: Any) -> None:
    _request_id.reset(token)


class RequestIdFilter(logging.Filter):
    """Injeta `request_id` em todo `LogRecord` — inclusive nos de bibliotecas de terceiros.

    É um filtro e não um adapter porque precisa valer para o log do Django, do gunicorn e de
    qualquer `logging.getLogger(__name__)` espalhado pelo app, sem que nenhum deles saiba disto.
    """

    def filter(self, record: logging.LogRecord) -> bool:
        if not hasattr(record, "request_id"):
            record.request_id = get_request_id()
        return True


# Campos que o `logging` já põe no `LogRecord` e que não devem virar `extra` no JSON.
_RESERVED = set(logging.LogRecord("", 0, "", 0, "", None, None).__dict__) | {
    "asctime",
    "message",
    "request_id",
    "taskName",
}


class JsonFormatter(logging.Formatter):
    """Uma linha = um objeto JSON, que é o que um coletor de log consegue indexar.

    Sem dependência: `json` da stdlib dá conta, e um formatter é o ponto errado para instalar
    biblioteca. `default=str` porque `extra` pode trazer `Decimal`, `datetime` ou model — melhor
    a repr do que perder a linha inteira em `TypeError` dentro do handler.
    """

    def format(self, record: logging.LogRecord) -> str:
        payload: dict[str, Any] = {
            "timestamp": self.formatTime(record, "%Y-%m-%dT%H:%M:%S%z"),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
            "request_id": getattr(record, "request_id", NO_REQUEST_ID),
        }
        if record.exc_info:
            payload["exception"] = self.formatException(record.exc_info)
        payload.update(
            {key: value for key, value in record.__dict__.items() if key not in _RESERVED}
        )
        return json.dumps(payload, default=str, ensure_ascii=False)


def init_sentry(
    dsn: str,
    environment: str = "",
    release: str = "",
    traces_sample_rate: float = 0.0,
) -> bool:
    """Liga o Sentry se houver DSN. Devolve se ligou, para quem chama não precisar re-checar.

    Chamado do fim de `config/settings.py` (e não de um `AppConfig.ready()`) porque erro de
    configuração e de import de app acontecem **antes** do `ready()` — e são exatamente os que
    ninguém vê atrás do gunicorn. Por isso os valores chegam por argumento e não por
    `django.conf.settings`: lê-lo de dentro do próprio módulo de settings, ainda em importação,
    força a materialização da configuração no meio dela mesma.

    `send_default_pii=False` de propósito: com ele ligado o SDK manda cookie de sessão, corpo da
    requisição e e-mail do usuário para um terceiro. Este portal carrega proposta, contrato e dado
    de cliente; o que se quer no Sentry é o stack trace, e o `request_id` para achar o resto no log.
    """
    if not dsn:
        return False

    import sentry_sdk

    sentry_sdk.init(
        dsn=dsn,
        environment=environment or None,
        release=release or None,
        # Zero por default: tracing é amostragem de requisição saudável, que custa cota e não é o
        # problema deste item. Quem quiser liga por env.
        traces_sample_rate=traces_sample_rate,
        send_default_pii=False,
        # As integrações de Django/logging são detectadas sozinhas pelo SDK.
    )
    return True


def tag_request(request_id: str) -> None:
    """Carimba o request-id no escopo do Sentry, quando ele existe. No-op sem DSN."""
    try:
        import sentry_sdk
    except ImportError:  # pragma: no cover - sentry-sdk é dependência declarada
        return
    if sentry_sdk.get_client().is_active():
        sentry_sdk.set_tag("request_id", request_id)
