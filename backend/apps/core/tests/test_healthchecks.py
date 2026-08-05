"""Sondas `/healthz` e `/readyz` (FDD 020)."""

from unittest import mock

import pytest
from django.test import Client


def test_healthz_responde_sem_tocar_no_banco() -> None:
    """Sem `django_db` de propósito: qualquer acesso ao banco aqui estouraria no bloqueador.

    É a diferença entre vivo e pronto: com o banco fora, reiniciar o container não resolve nada.
    """
    response = Client().get("/healthz")

    assert response.status_code == 200
    assert response.json() == {"status": "ok"}
    assert response["Cache-Control"] == "no-store"


def test_healthz_aceita_a_barra_no_fim() -> None:
    """O `APPEND_SLASH` do `CommonMiddleware` roda depois da sonda, então ela resolve sozinha."""
    assert Client().get("/healthz/").status_code == 200


@pytest.mark.django_db
def test_readyz_confere_banco_e_cache() -> None:
    response = Client().get("/readyz")

    assert response.status_code == 200
    assert response.json() == {"status": "ok", "checks": {"db": "ok", "cache": "ok"}}


@pytest.mark.django_db
def test_readyz_responde_503_com_o_banco_fora() -> None:
    with mock.patch("apps.core.healthchecks._check_database", side_effect=OSError("sem banco")):
        response = Client().get("/readyz")

    assert response.status_code == 503
    assert response.json() == {"status": "degraded", "checks": {"db": "error", "cache": "ok"}}


@pytest.mark.django_db
def test_readyz_responde_503_com_o_cache_mudo() -> None:
    """`set` que aceita e `get` que devolve `None` é um Redis quebrado — e o teto de requisição
    depende dele."""
    with mock.patch("apps.core.healthchecks.cache.get", return_value=None):
        response = Client().get("/readyz")

    assert response.status_code == 503
    assert response.json()["checks"]["cache"] == "error"


@pytest.mark.django_db
def test_readyz_nao_expoe_detalhe_da_falha() -> None:
    """O endpoint é anônimo e alcançável pela borda: traceback e nome de host ficam no log."""
    with mock.patch(
        "apps.core.healthchecks._check_database", side_effect=OSError("host=db-interno-01 senha=x")
    ):
        corpo = Client().get("/readyz").content.decode()

    assert "db-interno-01" not in corpo
    assert "Traceback" not in corpo
