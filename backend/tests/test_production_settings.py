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
from pathlib import Path
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


def test_sem_bucket_o_documento_fica_no_sistema_de_arquivos() -> None:
    """O compose é este caminho, e é o que faz o teste de mesa do backup seguir válido."""
    cfg = _reload(PROD_ENV)
    assert cfg.STORAGES["default"]["BACKEND"] == "django.core.files.storage.FileSystemStorage"


def test_com_bucket_o_documento_vai_para_o_cloud_storage() -> None:
    cfg = _reload({**PROD_ENV, "GCS_MEDIA_BUCKET": "biahflow-hml-midia"})
    default = cfg.STORAGES["default"]
    assert default["BACKEND"] == "storages.backends.gcloud.GoogleCloudStorage"
    assert default["OPTIONS"]["bucket_name"] == "biahflow-hml-midia"
    # As duas opções não são preferência. `default_acl` não nulo faz o GCS recusar a escrita
    # num bucket de acesso uniforme; e `querystring_auth` ligado devolveria URL assinada em
    # `file.url`, que é um caminho para o arquivo sem passar por `check_object_permissions`.
    assert default["OPTIONS"]["default_acl"] is None
    assert default["OPTIONS"]["querystring_auth"] is False


def test_smtp_de_producao() -> None:
    cfg = _reload(PROD_ENV)

    assert cfg.EMAIL_USE_TLS is True
    assert cfg.EMAIL_TIMEOUT == 20


# Monitoramento (FDD 020)


def test_log_em_json_e_opcional_e_o_request_id_nunca_e() -> None:
    """JSON no terminal de quem desenvolve é hostil; o request-id vale nos dois formatos."""
    texto = _reload({})
    assert texto.LOGGING["handlers"]["stderr"]["formatter"] == "padrao"
    assert "{request_id}" in texto.LOGGING["formatters"]["padrao"]["format"]

    json_ = _reload({**PROD_ENV, "DJANGO_LOG_FORMAT": "json"})
    assert json_.LOGGING["handlers"]["stderr"]["formatter"] == "json"
    assert json_.LOGGING["handlers"]["stderr"]["filters"] == ["request_id"]


def test_sentry_nasce_desligado_e_vem_todo_do_ambiente() -> None:
    """O fornecedor é opcional: sem DSN nada é inicializado (ADR 0012)."""
    assert _reload({}).SENTRY_DSN == ""

    cfg = _reload(
        {
            **PROD_ENV,
            "SENTRY_DSN": "https://chave@o0.ingest.sentry.io/1",
            "SENTRY_ENVIRONMENT": "producao",
            "SENTRY_RELEASE": "2026.08.05",
            "SENTRY_TRACES_SAMPLE_RATE": "0.1",
        }
    )
    assert cfg.SENTRY_ENVIRONMENT == "producao"
    assert cfg.SENTRY_RELEASE == "2026.08.05"
    assert cfg.SENTRY_TRACES_SAMPLE_RATE == 0.1


def test_tracing_do_sentry_nasce_em_zero() -> None:
    """Amostrar requisição saudável custa cota e não é o problema deste item."""
    assert _reload(PROD_ENV).SENTRY_TRACES_SAMPLE_RATE == 0.0


def test_whitenoise_fica_logo_depois_do_middleware_de_seguranca(tmp_path: Path) -> None:
    """Os middlewares da FDD 020 passaram na frente: um `insert(1)` fixo serviria estático
    **antes** do `SecurityMiddleware`, sem os headers de segurança."""
    (tmp_path / "algo.css").write_text("body{}")
    cfg = _reload({**PROD_ENV, "DJANGO_STATIC_ROOT": str(tmp_path)})

    seguranca = cfg.MIDDLEWARE.index("django.middleware.security.SecurityMiddleware")
    assert cfg.MIDDLEWARE[seguranca + 1] == "whitenoise.middleware.WhiteNoiseMiddleware"
    assert cfg.MIDDLEWARE[0] == "apps.core.middleware.RequestIdMiddleware"


def test_log_de_acesso_da_aplicacao_pode_ser_desligado() -> None:
    """Quem já coleta o access log do gunicorn ou do ingress dispensa o daqui."""
    assert "apps.core.middleware.RequestLogMiddleware" in _reload({}).MIDDLEWARE
    desligado = _reload({**PROD_ENV, "DJANGO_LOG_REQUESTS": "false"})
    assert "apps.core.middleware.RequestLogMiddleware" not in desligado.MIDDLEWARE
    # A sonda e o request-id não são opcionais.
    assert "apps.core.middleware.RequestIdMiddleware" in desligado.MIDDLEWARE
    assert "apps.core.middleware.HealthProbeMiddleware" in desligado.MIDDLEWARE
