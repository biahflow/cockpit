"""Configuração compartilhada da suíte (apps/core/tests/ e tests/regression/).

O throttle do DRF conta requisições no cache. Como não há `CACHES` configurado, o Django
usa `LocMemCache` — um dicionário de processo que sobrevive de um teste para o outro. E o
`AnonRateThrottle` chaveia por IP, que na suíte é sempre `127.0.0.1`: sem limpar, o contador
de um teste de limite estoura o teste seguinte, e a ordem dos testes passa a importar.
"""

import pytest
from django.core.cache import cache
from django.test import override_settings

# **A suíte nunca fala com o bucket.** `STORAGES["default"]` passou a ser escolhido por
# `GCS_MEDIA_BUCKET` (FDD 017), e uma variável de ambiente vazada para o ambiente de teste
# faria dezenas de testes gravarem objeto de verdade — os que sobem documento e os nove que
# fazem `override_settings(MEDIA_ROOT=...)`, que com storage remoto viram no-op silencioso.
# Fixar aqui é a única forma de a suíte afirmar sobre disco sem depender de quem a invoca.
_ARMAZENAMENTO_LOCAL = override_settings(
    STORAGES={
        "default": {"BACKEND": "django.core.files.storage.FileSystemStorage"},
        "staticfiles": {"BACKEND": "whitenoise.storage.CompressedStaticFilesStorage"},
    }
)


def pytest_configure() -> None:
    _ARMAZENAMENTO_LOCAL.enable()


def pytest_unconfigure() -> None:
    _ARMAZENAMENTO_LOCAL.disable()


@pytest.fixture(autouse=True)
def clear_throttle_cache() -> None:
    cache.clear()
