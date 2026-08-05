"""Regressão: `check --deploy` recusa configuração insegura de produção (FDD 019).

Antes, nada impedia o portal de subir com o segredo de desenvolvimento que está no repositório,
com `ALLOWED_HOSTS` de localhost, em SQLite efêmero ou com o cache por processo — e o CI rodava
`manage.py check` sem `--deploy`, que não olha nada disso.

A recusa mora em checks com `deploy=True` (nunca em um `raise` no import) porque a suíte e o CI
rodam sem `DJANGO_SECRET_KEY`: um `raise` lá quebraria todo teste, e em produção mataria também
`migrate` e `shell`, os comandos de que se precisa durante um incidente.
"""

from pathlib import Path

import pytest
from django.core.management import call_command
from django.core.management.base import SystemCheckError
from django.test import override_settings

from apps.core import checks

# Configuração de produção que precisa passar limpa. Serve de espelho do bloco `env` do CI e do
# que o `docker-compose.prod.yml` monta.
PROD = {
    "DEBUG": False,
    # Precisa parecer aleatório de verdade: o `security.W009` reprova chave com menos de
    # 50 caracteres **ou** menos de 5 caracteres distintos.
    "SECRET_KEY": "9fK2pQ7wZr4Lx8Nv3Bt6Ys1Hd5Jm0Cg-aEu_iOq+RyTnWbXzVkPlSh",
    "ALLOWED_HOSTS": ["portal.exemplo.com"],
    "CSRF_TRUSTED_ORIGINS": ["https://portal.exemplo.com"],
    "SESSION_COOKIE_SECURE": True,
    "CSRF_COOKIE_SECURE": True,
    "SECURE_SSL_REDIRECT": True,
    "SECURE_HSTS_SECONDS": 31_536_000,
    "SECURE_HSTS_INCLUDE_SUBDOMAINS": True,
    "TRUST_X_FORWARDED_PROTO": False,
    "CACHES": {"default": {"BACKEND": "django.core.cache.backends.redis.RedisCache",
                           "LOCATION": "redis://redis:6379/0"}},
    "DATABASES": {"default": {"ENGINE": "django.db.backends.postgresql", "NAME": "biahflow"}},
}


@pytest.fixture
def static_root(tmp_path: Path) -> Path:
    """O check exige `collectstatic` feito, então o diretório precisa existir e ter conteúdo."""
    (tmp_path / "admin.css").write_text("body{}")
    return tmp_path


def test_configuracao_de_producao_passa_limpa(static_root: Path) -> None:
    """Este teste é o gate do CI codificado: se ele passa, `check --deploy` sai com 0."""
    with override_settings(STATIC_ROOT=static_root, **PROD):
        # `--fail-level WARNING` e `--tag security`: sem o filtro, os avisos de schema do
        # drf-spectacular derrubariam um gate que é sobre estar pronto para produção.
        call_command("check", deploy=True, fail_level="WARNING", tags=["security"])


def test_segredo_de_desenvolvimento_e_recusado(static_root: Path) -> None:
    with override_settings(STATIC_ROOT=static_root, **{**PROD, "SECRET_KEY": "unsafe-development-key"}):
        with pytest.raises(SystemCheckError, match=checks.ID_SECRET_KEY):
            call_command("check", deploy=True, fail_level="WARNING", tags=["security"])


def test_cada_check_aponta_o_proprio_problema() -> None:
    """Um erro por defeito, com o id certo — para a mensagem dizer o que corrigir."""
    casos = [
        (checks.check_secret_key_is_not_the_development_one,
         {"SECRET_KEY": "unsafe-development-key"}, checks.ID_SECRET_KEY),
        (checks.check_allowed_hosts_is_production,
         {"ALLOWED_HOSTS": ["*"]}, checks.ID_ALLOWED_HOSTS),
        (checks.check_allowed_hosts_is_production,
         {"ALLOWED_HOSTS": ["localhost", "127.0.0.1", "api"]}, checks.ID_ALLOWED_HOSTS),
        (checks.check_csrf_trusted_origins_are_https,
         {"CSRF_TRUSTED_ORIGINS": ["http://localhost:19173"]}, checks.ID_CSRF_ORIGINS),
        (checks.check_cache_is_shared,
         {"CACHES": {"default": {"BACKEND": "django.core.cache.backends.locmem.LocMemCache"}}},
         checks.ID_SHARED_CACHE),
        (checks.check_database_is_not_sqlite,
         {"DATABASES": {"default": {"ENGINE": "django.db.backends.sqlite3", "NAME": ":memory:"}}},
         checks.ID_SQLITE),
    ]
    for check, quebra, esperado in casos:
        with override_settings(**{**PROD, **quebra}):
            erros = check()
        assert [erro.id for erro in erros] == [esperado], f"{check.__name__} não apontou {esperado}"


def test_header_de_proxy_sem_num_proxies_e_recusado() -> None:
    """Acreditar no esquema que o proxy informa e contar requisição pelo IP dele é contradição."""
    quebrado = {**PROD, "TRUST_X_FORWARDED_PROTO": True, "REST_FRAMEWORK": {"NUM_PROXIES": None}}
    with override_settings(**quebrado):
        erros = checks.check_proxy_header_has_proxy_count()
    assert [erro.id for erro in erros] == [checks.ID_PROXY_HEADER]

    with override_settings(**{**quebrado, "REST_FRAMEWORK": {"NUM_PROXIES": 1}}):
        assert checks.check_proxy_header_has_proxy_count() == []


def test_estatico_nao_coletado_e_recusado(tmp_path: Path) -> None:
    """Sem `collectstatic`, o WhiteNoise nem entra no MIDDLEWARE e o admin abre sem CSS."""
    with override_settings(STATIC_ROOT=tmp_path / "nao-existe"):
        assert [e.id for e in checks.check_static_files_were_collected()] == [checks.ID_STATIC_FILES]

    with override_settings(STATIC_ROOT=tmp_path):  # existe, mas vazio
        assert [e.id for e in checks.check_static_files_were_collected()] == [checks.ID_STATIC_FILES]


def test_os_checks_nao_rodam_sem_deploy() -> None:
    """`manage.py check` comum tem de continuar limpo — é ele que roda no dia a dia e na suíte."""
    call_command("check")
