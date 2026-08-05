"""Regressão: o arquivo do documento só sai pela rota autenticada (FDD 017, ADR 0002).

`config/urls.py` montava `static(MEDIA_URL, document_root=MEDIA_ROOT)` sob `if DEBUG`. Como o
`.env.example` e o `docker-compose.yml` trazem `DJANGO_DEBUG=true`, essa era a configuração
real de desenvolvimento e homologação — e os caminhos em `documents/%Y/%m/` são previsíveis o
bastante para adivinhar. Qualquer anônimo baixava contrato e proposta por `/media/...`,
contornando o gate de acesso inteiro.

O SPA nunca usou `/media/`: baixa por `documents/{id}/download/`.
"""

import pytest
from django.test import Client

pytestmark = pytest.mark.django_db


def test_media_url_is_not_routed() -> None:
    response = Client().get("/media/documents/2026/08/contrato.pdf")

    assert response.status_code == 404


def test_no_url_pattern_serves_the_media_root() -> None:
    """O `URLConf` é montado no import, então travar a intenção vale mais que o status."""
    from django.urls import get_resolver

    from config import urls

    assert not hasattr(urls, "static"), "config/urls.py voltou a importar o servidor de mídia"
    patterns = [str(getattr(pattern, "pattern", "")) for pattern in get_resolver().url_patterns]
    assert not any("media" in pattern for pattern in patterns)
