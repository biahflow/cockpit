"""O módulo de settings traduz o ambiente em configuração de produção (FDD 019).

Cada chave nova vem de uma variável de ambiente, e a única forma de exercitar os dois lados de um
`os.getenv` em um módulo é reexecutá-lo. `importlib.reload` é seguro aqui porque o
`django.conf.settings` copia os atributos maiúsculos na primeira materialização: recarregar o
módulo troca os atributos **do módulo**, não os da configuração viva. Por isso este arquivo não
afirma nada sobre `django.conf.settings` — o que o manteria verdadeiro por construção.
"""

import importlib
import os
from collections.abc import Iterator
from types import ModuleType
from unittest import mock

import pytest

import config.settings

# Um ambiente de produção plausível, igual ao que o runbook manda pôr no cofre.
PROD_ENV = {
    "DJANGO_SECRET_KEY": "x" * 60,
    "DJANGO_DEBUG": "false",
    "DJANGO_ALLOWED_HOSTS": "portal.exemplo.com",
    "DJANGO_CSRF_TRUSTED_ORIGINS": "https://portal.exemplo.com",
    "DJANGO_SSL_REDIRECT": "true",
    "DJANGO_HSTS_SECONDS": "31536000",
    "TRUST_X_FORWARDED_PROTO": "true",
    "SESSION_COOKIE_AGE": "3600",
    "REDIS_URL": "redis://redis:6379/0",
    "DATABASE_URL": "postgresql://usuario:senha@banco:5432/biahflow?sslmode=require",
    "DB_CONN_MAX_AGE": "120",
    "DJANGO_MEDIA_ROOT": "/var/lib/biahflow/media",
    "EMAIL_USE_TLS": "true",
    "EMAIL_TIMEOUT": "20",
}


def _reload(env: dict[str, str]) -> ModuleType:
    with mock.patch.dict(os.environ, env, clear=True):
        return importlib.reload(config.settings)


@pytest.fixture(autouse=True)
def restaura_o_modulo() -> Iterator[None]:
    """Devolve o módulo ao ambiente real, para não vazar configuração para o resto da suíte."""
    yield
    importlib.reload(config.settings)


def test_producao_liga_o_transporte_seguro() -> None:
    cfg = _reload(PROD_ENV)

    assert cfg.DEBUG is False
    assert cfg.SECURE_SSL_REDIRECT is True
    assert cfg.SECURE_HSTS_SECONDS == 31_536_000
    assert cfg.SECURE_HSTS_INCLUDE_SUBDOMAINS is True
    assert cfg.SESSION_COOKIE_SECURE is True
    assert cfg.CSRF_COOKIE_SECURE is True
    assert cfg.SECURE_PROXY_SSL_HEADER == ("HTTP_X_FORWARDED_PROTO", "https")


def test_preload_de_hsts_nao_entra_sozinho() -> None:
    """É quase irreversível: nunca deve vir de carona em outra variável."""
    assert _reload(PROD_ENV).SECURE_HSTS_PRELOAD is False
    assert _reload({**PROD_ENV, "DJANGO_HSTS_PRELOAD": "true"}).SECURE_HSTS_PRELOAD is True


def test_transporte_nasce_desligado_sem_ambiente() -> None:
    """`DEBUG=False` é também o modo da suíte: derivar dele deixaria todo teste em 301."""
    cfg = _reload({})

    assert cfg.DEBUG is False
    assert cfg.SECURE_SSL_REDIRECT is False
    assert cfg.SECURE_HSTS_SECONDS == 0
    assert cfg.SECURE_PROXY_SSL_HEADER is None


def test_header_de_proxy_e_opt_in() -> None:
    """Sem opt-in explícito, qualquer cliente poderia se declarar em https."""
    cfg = _reload({**PROD_ENV, "TRUST_X_FORWARDED_PROTO": "false"})

    assert cfg.TRUST_X_FORWARDED_PROTO is False
    assert cfg.SECURE_PROXY_SSL_HEADER is None


def test_redis_vira_o_cache_compartilhado() -> None:
    com_redis = _reload(PROD_ENV).CACHES["default"]
    assert com_redis["BACKEND"] == "django.core.cache.backends.redis.RedisCache"
    assert com_redis["LOCATION"] == "redis://redis:6379/0"

    sem_redis = _reload({}).CACHES["default"]
    assert sem_redis["BACKEND"] == "django.core.cache.backends.locmem.LocMemCache"


def test_sessao_desliza_e_expira_pelo_ambiente() -> None:
    cfg = _reload(PROD_ENV)

    assert cfg.SESSION_COOKIE_AGE == 3600
    assert cfg.SESSION_SAVE_EVERY_REQUEST is True


def test_a_query_string_do_database_url_chega_ao_banco() -> None:
    """Era descartada, e é assim que um Postgres gerenciado entrega o `sslmode`."""
    banco = _reload(PROD_ENV).DATABASES["default"]

    assert banco["ENGINE"] == "django.db.backends.postgresql"
    assert banco["HOST"] == "banco"
    assert banco["OPTIONS"]["sslmode"] == "require"
    assert banco["CONN_MAX_AGE"] == 120
    assert banco["CONN_HEALTH_CHECKS"] is True


def test_db_sslmode_vence_a_url() -> None:
    banco = _reload({**PROD_ENV, "DB_SSLMODE": "verify-full"}).DATABASES["default"]

    assert banco["OPTIONS"]["sslmode"] == "verify-full"


def test_sem_database_url_o_fallback_e_sqlite() -> None:
    """O check de deploy é que recusa isso em produção; aqui só se registra o comportamento."""
    assert _reload({}).DATABASES["default"]["ENGINE"] == "django.db.backends.sqlite3"


def test_media_root_sai_da_arvore_de_codigo_por_ambiente() -> None:
    assert str(_reload(PROD_ENV).MEDIA_ROOT) == "/var/lib/biahflow/media"


def test_smtp_de_producao() -> None:
    cfg = _reload(PROD_ENV)

    assert cfg.EMAIL_USE_TLS is True
    assert cfg.EMAIL_TIMEOUT == 20
