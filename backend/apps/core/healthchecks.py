"""Sondas de processo: `/healthz` (vivo) e `/readyz` (pronto) — FDD 020.

Duas perguntas diferentes, e confundi-las é o defeito clássico de deploy:

- **Vivo** é "este processo responde?". Não toca em nada externo. Se o banco cair e a sonda de
  liveness reprovar, o orquestrador **reinicia** um container que estava perfeitamente saudável —
  e reiniciar não traz o banco de volta.
- **Pronto** é "posso receber tráfego?". Aí sim banco e cache entram, porque sem eles toda
  requisição real falharia; o certo é sair do balanceador, não morrer.

O corpo é deliberadamente pobre. O endpoint é anônimo e alcançável pela borda (o balanceador
precisa sondá-lo), então versão, hostname, nome de banco e traceback ficam de fora: isso é
reconhecimento gratuito para quem estiver varrendo. Quem precisa do detalhe tem o log.

Não é view do DRF nem mora em `/api/v1/`: não é contrato de API (não entra no `openapi.yaml`), não
tem sessão nem teto de requisição — e `/api/v1/health/` já existe e é outra coisa, o *health score*
de projeto (`health.py`). Quem responde é o `HealthProbeMiddleware`, pelas razões que estão lá.
"""

from __future__ import annotations

import logging

from django.core.cache import cache
from django.db import connection

logger = logging.getLogger(__name__)

LIVENESS_PATH = "/healthz"
READINESS_PATH = "/readyz"
_CACHE_PROBE_KEY = "biahflow:readyz"


def liveness() -> tuple[int, dict[str, object]]:
    return 200, {"status": "ok"}


def _check_database() -> bool:
    with connection.cursor() as cursor:
        cursor.execute("SELECT 1")
        return cursor.fetchone() == (1,)


def _check_cache() -> bool:
    # Ida e volta de verdade: um Redis que aceita `set` e devolve `None` no `get` está quebrado de
    # um jeito que só aparece no teto de requisição, horas depois.
    cache.set(_CACHE_PROBE_KEY, "ok", 10)
    return cache.get(_CACHE_PROBE_KEY) == "ok"


def readiness() -> tuple[int, dict[str, object]]:
    checks: dict[str, str] = {}
    for name, probe in (("db", _check_database), ("cache", _check_cache)):
        try:
            checks[name] = "ok" if probe() else "error"
        except Exception:
            # O detalhe vai para o log (com request-id), não para a resposta anônima.
            logger.exception("Sonda de readiness falhou em %s", name)
            checks[name] = "error"
    healthy = all(state == "ok" for state in checks.values())
    return (200 if healthy else 503), {
        "status": "ok" if healthy else "degraded",
        "checks": checks,
    }
