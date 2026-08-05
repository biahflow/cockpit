"""Middlewares de observabilidade (FDD 020, ADR 0012).

A ordem no `MIDDLEWARE` é parte do desenho, não acaso — os três ficam **antes** do
`SecurityMiddleware`:

    RequestIdMiddleware → HealthProbeMiddleware → RequestLogMiddleware → SecurityMiddleware → ...

- o request-id primeiro, para que tudo o que vier depois (inclusive um 400 de `DisallowedHost`)
  já saia com id no log;
- a sonda em seguida, porque ela precisa responder **antes** de `ALLOWED_HOSTS` e do
  `SECURE_SSL_REDIRECT` (ver `HealthProbeMiddleware`);
- o log de acesso por último dos três, e depois da sonda de propósito: assim a sonda, que roda a
  cada 15 s, nunca entra no log — sem precisar de um `if path in (...)` dentro do logger.
"""

from __future__ import annotations

import logging
import time
from collections.abc import Callable

from django.http import HttpRequest, HttpResponse, JsonResponse

from . import healthchecks
from .observability import (
    REQUEST_ID_HEADER,
    REQUEST_ID_META,
    get_request_id,
    new_request_id,
    reset_request_id,
    sanitize_request_id,
    set_request_id,
    tag_request,
)

logger = logging.getLogger("biahflow.request")


class RequestIdMiddleware:
    """Toda requisição ganha um identificador, e ele volta na resposta.

    O id nasce na borda (o nginx manda o `$request_id` dele) e é **aproveitado**, não substituído:
    é o que permite seguir uma requisição do log do nginx até o log do gunicorn e o evento do
    Sentry. Mas ele vem de fora, então passa por `sanitize_request_id` — sem isso um header com
    quebra de linha injeta uma entrada falsa no log.

    O header também volta ao cliente: é assim que o SPA consegue mostrar "erro <id>" e alguém
    achar a requisição exata no log (ADR 0012).
    """

    def __init__(self, get_response: Callable[[HttpRequest], HttpResponse]) -> None:
        self.get_response = get_response

    def __call__(self, request: HttpRequest) -> HttpResponse:
        request_id = sanitize_request_id(request.META.get(REQUEST_ID_META, "")) or new_request_id()
        token = set_request_id(request_id)
        tag_request(request_id)
        try:
            response = self.get_response(request)
        finally:
            # `reset` no `finally` porque o worker é reaproveitado: sem isto, uma exceção deixaria
            # o id da requisição morta grudado no `ContextVar` e ele apareceria na próxima.
            reset_request_id(token)
        response[REQUEST_ID_HEADER] = request_id
        return response


class HealthProbeMiddleware:
    """Responde `/healthz` e `/readyz` sem descer o resto da cadeia.

    Middleware e não rota, por duas razões que uma view em `urls.py` não resolve:

    1. **`ALLOWED_HOSTS`.** A sonda do container fala com `127.0.0.1`, e em produção
       `DJANGO_ALLOWED_HOSTS` é o domínio (o `check --deploy` recusa subir com hosts de
       desenvolvimento). Qualquer view chega depois de `request.get_host()`, que levanta
       `DisallowedHost` → 400 → container eternamente *unhealthy*. Era o defeito da sonda anterior.
    2. **`SECURE_SSL_REDIRECT`.** O `SecurityMiddleware` responderia 301 a uma sonda http, e um
       balanceador lê 301 como falha.

    É seguro ignorar o `Host` aqui porque a resposta é constante e não deriva nada dele — não há
    link, redirect nem cookie para envenenar.
    """

    PATHS = {
        healthchecks.LIVENESS_PATH: healthchecks.liveness,
        healthchecks.READINESS_PATH: healthchecks.readiness,
    }

    def __init__(self, get_response: Callable[[HttpRequest], HttpResponse]) -> None:
        self.get_response = get_response

    def __call__(self, request: HttpRequest) -> HttpResponse:
        # `rstrip("/")` porque o `APPEND_SLASH` do `CommonMiddleware` só roda mais abaixo: sem
        # isto, `/healthz/` (com barra) cairia no SPA/404 dependendo de quem sondou.
        probe = self.PATHS.get(request.path.rstrip("/") or "/")
        if probe is None:
            return self.get_response(request)
        status, payload = probe()
        response = JsonResponse(payload, status=status)
        # Sonda não pode ser servida de cache por proxy nenhum: uma resposta velha esconde a queda.
        response["Cache-Control"] = "no-store"
        return response


class RequestLogMiddleware:
    """Uma linha por requisição, com o que o access log do gunicorn não sabe: usuário e duração.

    O access log do gunicorn continua ligado porque ele enxerga o que morre antes do Django
    (timeout de worker, corpo inválido); os dois se cruzam pelo mesmo `X-Request-ID`.
    """

    def __init__(self, get_response: Callable[[HttpRequest], HttpResponse]) -> None:
        self.get_response = get_response

    def __call__(self, request: HttpRequest) -> HttpResponse:
        started = time.monotonic()
        response = self.get_response(request)
        # `request.user` só existe depois do `AuthenticationMiddleware`, que roda mais abaixo — e
        # numa requisição que morre antes dele (host inválido, 301 de https) o atributo não está lá.
        user = getattr(request, "user", None)
        logger.info(
            "%s %s %s",
            request.method,
            request.get_full_path(),
            response.status_code,
            extra={
                "method": request.method,
                "path": request.path,
                "status": response.status_code,
                "duration_ms": round((time.monotonic() - started) * 1000, 1),
                "user_id": getattr(user, "id", None),
                "request_id": get_request_id(),
            },
        )
        return response
