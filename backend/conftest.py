"""Configuração compartilhada da suíte (apps/core/tests/ e tests/regression/).

O throttle do DRF conta requisições no cache. Como não há `CACHES` configurado, o Django
usa `LocMemCache` — um dicionário de processo que sobrevive de um teste para o outro. E o
`AnonRateThrottle` chaveia por IP, que na suíte é sempre `127.0.0.1`: sem limpar, o contador
de um teste de limite estoura o teste seguinte, e a ordem dos testes passa a importar.
"""

import pytest
from django.core.cache import cache


@pytest.fixture(autouse=True)
def clear_throttle_cache() -> None:
    cache.clear()
