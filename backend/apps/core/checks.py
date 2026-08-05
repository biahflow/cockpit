"""Verificações de produção (FDD 019).

São `deploy=True`, então só rodam em `manage.py check --deploy` — nunca no `check` comum nem na
suíte de testes, que roda sem `DJANGO_SECRET_KEY` e com `LocMemCache`. É por isso que a recusa
de configuração insegura mora aqui e não em um `raise` no import de `config/settings.py`: lá ela
quebraria todo teste.

Cada item cobre um buraco que os checks nativos do Django não pegam. O que ele já pega — segredo
curto, `DEBUG`, cookie sem `Secure`, HSTS ausente, `ALLOWED_HOSTS` vazio — não se repete aqui.
"""

from __future__ import annotations

from typing import Any

from django.conf import settings
from django.core.checks import CheckMessage, Error, Tags, register

ID_SECRET_KEY = "biahflow.E001"
ID_PROXY_HEADER = "biahflow.E002"
ID_SHARED_CACHE = "biahflow.E003"
ID_CSRF_ORIGINS = "biahflow.E004"
ID_ALLOWED_HOSTS = "biahflow.E005"
ID_SQLITE = "biahflow.E006"
ID_STATIC_FILES = "biahflow.E007"

DEV_HOSTS = {"localhost", "127.0.0.1", "api", "[::1]"}


@register(Tags.security, deploy=True)
def check_secret_key_is_not_the_development_one(
    app_configs: Any = None, **kwargs: Any
) -> list[CheckMessage]:
    if settings.SECRET_KEY != getattr(settings, "INSECURE_SECRET_KEY", None):
        return []
    return [
        Error(
            "DJANGO_SECRET_KEY não foi definida: a aplicação está usando o segredo de "
            "desenvolvimento, que está no repositório.",
            hint="Gere um segredo e ponha no cofre do ambiente: "
            "python -c 'import secrets; print(secrets.token_urlsafe(64))'",
            id=ID_SECRET_KEY,
        )
    ]


@register(Tags.security, deploy=True)
def check_proxy_header_has_proxy_count(
    app_configs: Any = None, **kwargs: Any
) -> list[CheckMessage]:
    """Confiar no `X-Forwarded-Proto` sem saber quantos proxies existem é contradição."""
    if not getattr(settings, "TRUST_X_FORWARDED_PROTO", False):
        return []
    if settings.REST_FRAMEWORK.get("NUM_PROXIES") is not None:
        return []
    return [
        Error(
            "TRUST_X_FORWARDED_PROTO está ligado sem NUM_PROXIES. O Django passa a acreditar no "
            "que o proxy diz sobre o esquema, mas continua contando requisição pelo IP do último "
            "salto — logo todo mundo que passa pelo mesmo proxy divide um balde de teto.",
            hint="Defina NUM_PROXIES com o número de proxies confiáveis do ingress (1 no "
            "docker-compose.prod.yml, onde o nginx é o único salto).",
            id=ID_PROXY_HEADER,
        )
    ]


@register(Tags.security, deploy=True)
def check_cache_is_shared(app_configs: Any = None, **kwargs: Any) -> list[CheckMessage]:
    backend = settings.CACHES["default"]["BACKEND"]
    if not backend.endswith("locmem.LocMemCache"):
        return []
    return [
        Error(
            "O cache default é LocMemCache, que é um dicionário por processo. O contador de teto "
            "de requisição do DRF vive nele: com N workers, cada limite da ADR 0009 passa a valer "
            "N vezes o configurado.",
            hint="Defina REDIS_URL apontando para um Redis compartilhado.",
            id=ID_SHARED_CACHE,
        )
    ]


@register(Tags.security, deploy=True)
def check_csrf_trusted_origins_are_https(
    app_configs: Any = None, **kwargs: Any
) -> list[CheckMessage]:
    insecure = [o for o in settings.CSRF_TRUSTED_ORIGINS if o.startswith("http://")]
    if not insecure:
        return []
    return [
        Error(
            "CSRF_TRUSTED_ORIGINS ainda tem origem http://: "
            f"{', '.join(insecure)}. São os defaults de desenvolvimento.",
            hint="Ponha DJANGO_CSRF_TRUSTED_ORIGINS com as origens https:// do portal.",
            id=ID_CSRF_ORIGINS,
        )
    ]


@register(Tags.security, deploy=True)
def check_allowed_hosts_is_production(
    app_configs: Any = None, **kwargs: Any
) -> list[CheckMessage]:
    """O `security.W020` nativo só reclama de lista vazia — nem de `*`, nem dos hosts de dev."""
    hosts = [host.strip() for host in settings.ALLOWED_HOSTS if host.strip()]
    if "*" in hosts:
        return [
            Error(
                "ALLOWED_HOSTS contém '*', o que aceita qualquer Host e abre a porta para "
                "envenenamento de cabeçalho Host nos links de convite e de assinatura.",
                hint="Liste os hosts do portal em DJANGO_ALLOWED_HOSTS.",
                id=ID_ALLOWED_HOSTS,
            )
        ]
    if hosts and set(hosts) <= DEV_HOSTS:
        return [
            Error(
                f"ALLOWED_HOSTS só tem hosts de desenvolvimento ({', '.join(hosts)}): "
                "DJANGO_ALLOWED_HOSTS não foi definida no ambiente.",
                hint="Liste os hosts do portal em DJANGO_ALLOWED_HOSTS.",
                id=ID_ALLOWED_HOSTS,
            )
        ]
    return []


@register(Tags.security, deploy=True)
def check_database_is_not_sqlite(app_configs: Any = None, **kwargs: Any) -> list[CheckMessage]:
    """Sem `DATABASE_URL`, o portal sobe em SQLite, migra e parece saudável — até reiniciar."""
    engine = str(settings.DATABASES["default"].get("ENGINE", ""))
    if not engine.endswith("sqlite3"):
        return []
    return [
        Error(
            "O banco default é SQLite, o fallback de desenvolvimento. Em container ele é um "
            "arquivo efêmero: a aplicação sobe, migra, atende — e perde tudo no primeiro restart.",
            hint="Defina DATABASE_URL apontando para o Postgres.",
            id=ID_SQLITE,
        )
    ]


@register(Tags.security, deploy=True)
def check_static_files_were_collected(
    app_configs: Any = None, **kwargs: Any
) -> list[CheckMessage]:
    """Sem `collectstatic`, o WhiteNoise nem entra no MIDDLEWARE e o admin fica sem CSS."""
    if settings.STATIC_ROOT.is_dir() and any(settings.STATIC_ROOT.iterdir()):
        return []
    return [
        Error(
            f"STATIC_ROOT ({settings.STATIC_ROOT}) está vazio ou não existe, então o WhiteNoise "
            "não serve nada e o Django admin abre sem CSS atrás do gunicorn.",
            hint="Rode `manage.py collectstatic --noinput` (a imagem de produção faz isso no build).",
            id=ID_STATIC_FILES,
        )
    ]
