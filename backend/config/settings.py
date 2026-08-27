from __future__ import annotations

import os
from pathlib import Path
from typing import Any
from urllib.parse import parse_qsl, urlparse

from django.core.exceptions import ImproperlyConfigured

BASE_DIR = Path(__file__).resolve().parent.parent


def _env_bool(name: str, default: bool) -> bool:
    raw = os.getenv(name)
    return default if raw is None else raw.strip().lower() in {"1", "true", "yes", "on"}


def _env_int(name: str, default: int) -> int:
    raw = os.getenv(name)
    if raw is None or not raw.strip():
        return default
    try:
        return int(raw)
    except ValueError as exc:
        # Sem isto, um `SESSION_COOKIE_AGE=meia-hora` estoura um traceback de `int()` que não diz
        # qual variável está errada.
        raise ImproperlyConfigured(f"{name} precisa ser um inteiro, e veio {raw!r}.") from exc


def _env_list(name: str, default: str = "") -> list[str]:
    return [item.strip() for item in os.getenv(name, default).split(",") if item.strip()]


# O default é o segredo de desenvolvimento; um system check de deploy recusa subir com ele
# (apps/core/checks.py). Não é `raise` aqui porque a suíte roda sem `DJANGO_SECRET_KEY`.
INSECURE_SECRET_KEY = "unsafe-development-key"
SECRET_KEY = os.getenv("DJANGO_SECRET_KEY", INSECURE_SECRET_KEY)
DEBUG = _env_bool("DJANGO_DEBUG", False)
# `_env_list` apara espaço: `DJANGO_ALLOWED_HOSTS="portal.exemplo.com, www.portal.exemplo.com"`
# gerava um host com espaço na frente, que não casa com nada e devolve 400 sem explicação.
ALLOWED_HOSTS = _env_list("DJANGO_ALLOWED_HOSTS", "localhost,127.0.0.1,api")
FRONTEND_BASE_URL = os.getenv("FRONTEND_ORIGIN", "http://localhost:19173")

INSTALLED_APPS = [
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    "rest_framework",
    "drf_spectacular",
    "corsheaders",
    "apps.core",
]
# Observabilidade na frente de tudo (FDD 020). O request-id precisa existir antes do primeiro
# middleware que pode recusar a requisição, e a sonda precisa responder antes de `ALLOWED_HOSTS`
# e do redirect de https — o porquê de cada um está em `apps/core/middleware.py`.
MIDDLEWARE = [
    "apps.core.middleware.RequestIdMiddleware",
    "apps.core.middleware.HealthProbeMiddleware",
    "apps.core.middleware.RequestLogMiddleware",
    "django.middleware.security.SecurityMiddleware",
    "corsheaders.middleware.CorsMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
]
# Quem já coleta o access log do gunicorn ou do ingress pode dispensar o da aplicação. O
# request-id e a sonda não são opcionais; este é.
if not _env_bool("DJANGO_LOG_REQUESTS", True):
    MIDDLEWARE.remove("apps.core.middleware.RequestLogMiddleware")
ROOT_URLCONF = "config.urls"
TEMPLATES = [{
    "BACKEND": "django.template.backends.django.DjangoTemplates",
    "DIRS": [],
    "APP_DIRS": True,
    "OPTIONS": {"context_processors": [
        "django.template.context_processors.request",
        "django.contrib.auth.context_processors.auth",
        "django.contrib.messages.context_processors.messages",
    ]},
}]
WSGI_APPLICATION = "config.wsgi.application"

database_url = os.getenv("DATABASE_URL")
if database_url:
    parsed = urlparse(database_url)
    # A query string da URL era descartada, então `...?sslmode=require` não fazia nada — e é
    # exatamente assim que um Postgres gerenciado costuma entregar a credencial. `DB_SSLMODE`
    # vence a URL. Sem nenhum dos dois, vale o default do libpq (o compose local não fala TLS).
    options = {key: value for key, value in parse_qsl(parsed.query)}
    if os.getenv("DB_SSLMODE"):
        options["sslmode"] = os.environ["DB_SSLMODE"]
    DATABASES = {"default": {
        "ENGINE": "django.db.backends.postgresql",
        "NAME": parsed.path.lstrip("/"),
        "USER": parsed.username,
        "PASSWORD": parsed.password,
        "HOST": parsed.hostname,
        "PORT": parsed.port or 5432,
        # Conexão persistente: com gunicorn, abrir uma conexão por requisição é o gargalo
        # mais barato de remover. `CONN_HEALTH_CHECKS` descarta a conexão morta em vez de
        # devolver erro na primeira query depois de um restart do banco.
        "CONN_MAX_AGE": _env_int("DB_CONN_MAX_AGE", 60),
        "CONN_HEALTH_CHECKS": True,
        "OPTIONS": options,
    }}
else:
    DATABASES = {
        "default": {"ENGINE": "django.db.backends.sqlite3", "NAME": str(BASE_DIR / "db.sqlite3")}
    }

AUTH_PASSWORD_VALIDATORS = [
    {"NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator"},
    {"NAME": "django.contrib.auth.password_validation.MinimumLengthValidator"},
    {"NAME": "django.contrib.auth.password_validation.CommonPasswordValidator"},
    {"NAME": "django.contrib.auth.password_validation.NumericPasswordValidator"},
]
LANGUAGE_CODE = "pt-br"
TIME_ZONE = "America/Sao_Paulo"
USE_I18N = True
USE_TZ = True
STATIC_URL = "static/"
# `collectstatic` roda no build da imagem de produção; em desenvolvimento o `runserver` serve
# o estático do admin sozinho e este diretório nem existe (está no `.gitignore`).
STATIC_ROOT = Path(os.getenv("DJANGO_STATIC_ROOT", str(BASE_DIR / "staticfiles")))
# Onde o `Document.file` vive. Vazio = sistema de arquivos, que é o compose e a suíte;
# preenchido = o bucket, que é o Cloud Run. A escolha é por **ausência de variável**, como
# `DATABASE_URL` e `REDIS_URL`, e não por uma flag: para onde o arquivo vai não é algo que
# se liga e desliga na tela — os objetos já gravados ficariam órfãos.
#
# Sem isto, no Cloud Run o arquivo ficava na instância que o recebeu: invisível para as
# outras (`max = 4`) e perdido na revisão seguinte. É o arquivo que segue para o Drive, para
# o fornecedor de assinatura e para o portal do cliente.
GCS_MEDIA_BUCKET = os.getenv("GCS_MEDIA_BUCKET", "")
if GCS_MEDIA_BUCKET:
    _default_storage: dict[str, Any] = {
        "BACKEND": "storages.backends.gcloud.GoogleCloudStorage",
        "OPTIONS": {
            "bucket_name": GCS_MEDIA_BUCKET,
            # O bucket tem acesso uniforme; mandar ACL por objeto faz o GCS recusar a
            # escrita inteira, e o erro fala de permissão e não de configuração.
            "default_acl": None,
            # O download é servido pela rota autenticada (`DocumentViewSet.download`), que
            # passa por `check_object_permissions`. URL assinada seria um segundo caminho
            # para o arquivo, sem RBAC — é a premissa da ADR 0002 / FDD 017.
            "querystring_auth": False,
        },
    }
else:
    _default_storage = {"BACKEND": "django.core.files.storage.FileSystemStorage"}

STORAGES = {
    "default": _default_storage,
    # Comprimido, mas **não** `Manifest`: a variante com manifesto levanta em runtime se um
    # `{% static %}` não estiver no `staticfiles.json`, que só existe depois do `collectstatic`.
    # Com `DEBUG=False` na suíte, qualquer template renderizado (API navegável, Swagger) estouraria.
    # O preço é perder o hash no nome de um punhado de arquivos do admin.
    "staticfiles": {"BACKEND": "whitenoise.storage.CompressedStaticFilesStorage"},
}
# Atrás do gunicorn não há `runserver` para servir o estático do admin, então o WhiteNoise entra.
# Só quando o `collectstatic` já rodou: sem o diretório ele avisa a cada boot, e em desenvolvimento
# (e na suíte) o `runserver` já dá conta. Na imagem de produção o `collectstatic` roda no build, e
# um check de deploy recusa subir sem ele.
#
# A posição é calculada, e não fixa: o WhiteNoise precisa vir **logo depois** do
# `SecurityMiddleware` (senão serve estático sem os headers de segurança). Um `insert(1)` literal
# valia enquanto o `SecurityMiddleware` era o primeiro da lista — os middlewares de
# observabilidade da FDD 020 passaram na frente dele e quebrariam essa premissa em silêncio.
if STATIC_ROOT.is_dir():
    _security = MIDDLEWARE.index("django.middleware.security.SecurityMiddleware")
    MIDDLEWARE.insert(_security + 1, "whitenoise.middleware.WhiteNoiseMiddleware")
MEDIA_URL = "/media/"
# Documento é recurso privado e o Django nunca serve este diretório (ADR 0002, FDD 017). Em
# produção ele precisa ser um volume próprio: dentro da árvore de código, um deploy o levaria.
MEDIA_ROOT = Path(os.getenv("DJANGO_MEDIA_ROOT", str(BASE_DIR / "media")))
DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"
AUTH_USER_MODEL = "core.User"
EMAIL_BACKEND = "django.core.mail.backends.smtp.EmailBackend"
EMAIL_HOST = os.getenv("EMAIL_HOST", "localhost")
EMAIL_PORT = _env_int("EMAIL_PORT", 1025)
EMAIL_HOST_USER = os.getenv("EMAIL_HOST_USER", "")
EMAIL_HOST_PASSWORD = os.getenv("EMAIL_HOST_PASSWORD", "")
EMAIL_USE_TLS = _env_bool("EMAIL_USE_TLS", False)
# Sem timeout, um SMTP que não responde pendura o worker que está mandando o e-mail.
EMAIL_TIMEOUT = _env_int("EMAIL_TIMEOUT", 10)
DEFAULT_FROM_EMAIL = os.getenv("DEFAULT_FROM_EMAIL", "noreply@biahflow.local")
# Notificações por e-mail + digest diário (Go-live/Hypercare) — ligado por padrão (ADR 0018).
# Esta é a única flag sem credencial obrigatória: o SMTP tem default (o Mailpit do compose), então
# ligar aqui não pode estourar em lugar nenhum — no pior caso o `send_mail` falha silenciosamente.
EMAIL_NOTIFICATIONS_ENABLED = os.getenv("EMAIL_NOTIFICATIONS_ENABLED", "true").lower() == "true"

REST_FRAMEWORK = {
    "DEFAULT_AUTHENTICATION_CLASSES": ["rest_framework.authentication.SessionAuthentication"],
    "DEFAULT_PERMISSION_CLASSES": ["rest_framework.permissions.IsAuthenticated"],
    "DEFAULT_SCHEMA_CLASS": "drf_spectacular.openapi.AutoSchema",
    # Sem isto, `ProtectedError` sobe como 500 e a recusa de uma exclusão vira incidente no
    # Sentry em vez de instrução na tela (FDD 025). Ver `apps/core/exceptions.py`.
    "EXCEPTION_HANDLER": "apps.core.exceptions.api_exception_handler",
    # Teto de requisições (FDD 017, ADR 0009). `anon`/`user` são a rede de baixo, que vale
    # para toda a API; os escopos nomeados protegem as portas específicas. Tudo por env para
    # afrouxar em produção sem redeploy de código.
    "DEFAULT_THROTTLE_CLASSES": [
        "rest_framework.throttling.AnonRateThrottle",
        "rest_framework.throttling.UserRateThrottle",
    ],
    "DEFAULT_THROTTLE_RATES": {
        "anon": os.getenv("ANON_RATE", "60/min"),
        "user": os.getenv("USER_RATE", "2000/hour"),
        "login": os.getenv("LOGIN_RATE", "10/min"),
        "invitation_accept": os.getenv("INVITATION_ACCEPT_RATE", "20/hour"),
        # Trocar a própria senha exige acertar a atual, então é uma porta de adivinhação como o
        # login — e o teto genérico de `user` (2000/hora) não segura ninguém. Quem tem a sessão
        # mas não a senha é exatamente o cenário que este escopo existe para limitar.
        "password_change": os.getenv("PASSWORD_CHANGE_RATE", "10/min"),
        "portal_read": os.getenv("PORTAL_READ_RATE", "120/hour"),
        "lead_intake": os.getenv("LEAD_INTAKE_RATE", "20/hour"),
        "task_sync": os.getenv("TASK_SYNC_RATE", "60/hour"),
        "booking": os.getenv("BOOKING_RATE", "60/hour"),
        "esign_webhook": os.getenv("ESIGN_WEBHOOK_RATE", "120/hour"),
        # Cinco vezes o teto do e-sign, de propósito: o Stripe trata 429 como falha e faz backoff
        # por até três dias, e cada pagamento chega em **dois** eventos (`invoice.paid` e
        # `invoice.payment_succeeded`). Um 429 aqui não é inofensivo como no e-sign — ele atrasa a
        # conciliação por dias, e é exatamente o atraso que faz a régua cobrar quem já pagou.
        "payments_webhook": os.getenv("PAYMENTS_WEBHOOK_RATE", "600/hour"),
        # Projeção de entrega (FDD 041): teto generoso porque um repositório ativo emite muitos
        # eventos de Issue/PR/CI, e um 429 aqui faz o GitHub re-tentar e atrasar a projeção.
        "github_webhook": os.getenv("GITHUB_WEBHOOK_RATE", "600/hour"),
    },
    # Atrás de proxy, sem isso todo mundo compartilha o IP do container e o limite por IP
    # vira um limite global. Ver docs/operacao.md.
    "NUM_PROXIES": int(os.environ["NUM_PROXIES"]) if os.getenv("NUM_PROXIES") else None,
}
# Cache compartilhado. O contador do throttle vive aqui: com `LocMemCache`, que é um dicionário
# por processo, N workers de gunicorn fazem cada teto valer N vezes o configurado — a ressalva que
# a ADR 0009 registrou como pendente. Sessão continua no banco de propósito: no cache, uma queda
# do Redis deslogaria todo mundo. Vazio = `LocMemCache` (desenvolvimento e suíte de testes).
REDIS_URL = os.getenv("REDIS_URL", "")
if REDIS_URL:
    CACHES = {
        "default": {
            "BACKEND": "django.core.cache.backends.redis.RedisCache",
            "LOCATION": REDIS_URL,
        }
    }
else:
    CACHES = {"default": {"BACKEND": "django.core.cache.backends.locmem.LocMemCache"}}

SPECTACULAR_SETTINGS = {
    "TITLE": "Biahflow API",
    "VERSION": "1.0.0",
    "SERVE_INCLUDE_SCHEMA": False,
    "ENUM_NAME_OVERRIDES": {
        "ProjectStatusEnum": "apps.core.models.Project.Status",
        "WorkItemStatusEnum": "apps.core.models.WorkItem.Status",
        # O gate aparece em dois lugares com conjuntos diferentes: o campo do modelo (que aceita
        # o branco de "ainda não decidido") e o corpo da action `apply-gate` (onde as quatro
        # saídas são obrigatórias). Sem o override, os dois disputam o mesmo nome de enum.
        "GateOutcomeEnum": "apps.core.models.ProjectPhase.GateOutcome",
        # `PhaseEvent.source` (FDD 042) introduz um segundo conjunto `source` no esquema (o
        # primeiro é o `linear/github` da sincronia de tarefas). Sem override, os dois disputam o
        # nome `SourceEnum` e drf-spectacular resolve com um sufixo numérico instável
        # (`Source933Enum`) que faz o `openapi.yaml` divergir a cada geração. Nomear os dois fixa
        # os componentes — o de sincronia mantém o `SourceEnum` que já tinha.
        "SourceEnum": "apps.core.tasksync.SOURCES",
        "PhaseEventSourceEnum": "apps.core.models.PhaseEvent.Source",
    },
}
SESSION_COOKIE_SECURE = not DEBUG
CSRF_COOKIE_SECURE = not DEBUG
SESSION_COOKIE_SAMESITE = "Lax"
CSRF_COOKIE_SAMESITE = "Lax"
# Expiração deslizante: 12h de inatividade encerram a sessão, mas quem está trabalhando não é
# deslogado no meio do expediente porque cada requisição renova o cookie.
SESSION_COOKIE_AGE = _env_int("SESSION_COOKIE_AGE", 12 * 60 * 60)
SESSION_SAVE_EVERY_REQUEST = True

# Transporte (FDD 019) — o que a FDD 017 deixou pendente esperando domínio e HTTPS.
#
# Nada aqui é derivado de `DEBUG`: **`DEBUG=False` não significa produção neste repo**. A suíte e
# o CI rodam com `DJANGO_DEBUG` ausente, e com `SECURE_SSL_REDIRECT` ligado o `SecurityMiddleware`
# devolve 301 para toda requisição do test client — a suíte inteira fica vermelha. Quem garante
# que isto está ligado em produção é o `check --deploy` (o gate do CI), não um default esperto.
#
# `SECURE_CONTENT_TYPE_NOSNIFF`, `SECURE_REFERRER_POLICY` e `X_FRAME_OPTIONS` não aparecem porque
# os defaults do Django 5 já são os seguros; repetir default só convida a divergência.
SECURE_SSL_REDIRECT = _env_bool("DJANGO_SSL_REDIRECT", False)
# Rotas isentas do redirect, por regex (sem a barra inicial). Serve para a sonda HTTP de um
# balanceador que não fala https com o container.
SECURE_REDIRECT_EXEMPT = _env_list("DJANGO_SSL_REDIRECT_EXEMPT")
SECURE_HSTS_SECONDS = _env_int("DJANGO_HSTS_SECONDS", 0)
SECURE_HSTS_INCLUDE_SUBDOMAINS = _env_bool("DJANGO_HSTS_INCLUDE_SUBDOMAINS", True)
# Preload nasce desligado de propósito: entrar na lista é compilado no browser e sair leva meses.
# Ligue só depois de o domínio e todos os subdomínios estarem estáveis em https (ver runbook).
SECURE_HSTS_PRELOAD = _env_bool("DJANGO_HSTS_PRELOAD", False)
# Atrás de um proxy que termina o TLS, o Django só sabe que a requisição era https pelo header.
# É opt-in porque confiar nele sem um proxy que o **sobrescreva** deixa qualquer cliente afirmar
# "já é https" e derrubar o redirect e o `Secure` do cookie. Ver ADR 0011.
# É booleano, e não o nome do header, de propósito: um nome livre transforma erro de digitação em
# buraco de spoofing, e o único par que faz sentido aqui é este.
TRUST_X_FORWARDED_PROTO = _env_bool("TRUST_X_FORWARDED_PROTO", False)
# `None` é o default do Django e diz "não confie em header nenhum" — explícito em vez de ausente.
SECURE_PROXY_SSL_HEADER = (
    ("HTTP_X_FORWARDED_PROTO", "https") if TRUST_X_FORWARDED_PROTO else None
)

# `security.W021` cobra `SECURE_HSTS_PRELOAD=True`, e o gate do CI roda com `--fail-level WARNING`.
# Silenciado porque a recusa é deliberada: preload é submissão a uma lista compilada no binário do
# navegador, que nenhum deploy desfaz. Ligue `DJANGO_HSTS_PRELOAD` quando quiser — o aviso é o
# único que este projeto escolhe não ouvir. Ver ADR 0011 e docs/runbooks/producao.md.
SILENCED_SYSTEM_CHECKS = ["security.W021"]

# Log (FDD 020). O default do Django manda o traceback de 500 para `mail_admins` e só: sem
# `ADMINS`, com `DEBUG=False`, o erro não aparece em lugar nenhum. Tudo vai para stderr, que é o
# que o runtime de container coleta.
#
# `json` é opção e não default: JSON no terminal de quem desenvolve é hostil de ler, e o formato
# só rende quando existe um coletor que indexa campo. O `docker-compose.prod.yml` liga o JSON.
# Nos dois formatos o `request_id` sai em toda linha — é ele que liga o erro que o usuário viu
# (o SPA mostra o id) à requisição no log e ao evento do Sentry.
# Minúsculo de propósito: é um detalhe do `LOGGING` abaixo, não uma setting que alguém deva ler.
_log_format = "json" if os.getenv("DJANGO_LOG_FORMAT", "texto").strip().lower() == "json" else "padrao"
LOGGING = {
    "version": 1,
    "disable_existing_loggers": False,
    "filters": {"request_id": {"()": "apps.core.observability.RequestIdFilter"}},
    "formatters": {
        "padrao": {"format": "{levelname} {asctime} {name} [{request_id}] {message}", "style": "{"},
        "json": {"()": "apps.core.observability.JsonFormatter"},
    },
    "handlers": {
        "stderr": {
            "class": "logging.StreamHandler",
            "formatter": _log_format,
            "filters": ["request_id"],
        },
    },
    "root": {"handlers": ["stderr"], "level": os.getenv("DJANGO_LOG_LEVEL", "INFO")},
    "loggers": {
        # Sem isto o traceback de 500 continuaria indo só para `mail_admins`.
        "django.request": {"handlers": ["stderr"], "level": "ERROR", "propagate": False},
    },
}

# Rastreamento de erro (ADR 0012). Sem `SENTRY_DSN` o SDK nunca é inicializado e nada sai daqui —
# o fornecedor é opcional, como toda integração deste portal. O DSN não é segredo (ele identifica
# o projeto e só aceita escrita), mas mora no ambiente junto com o resto.
SENTRY_DSN = os.getenv("SENTRY_DSN", "")
SENTRY_ENVIRONMENT = os.getenv("SENTRY_ENVIRONMENT", "")
# Marca a versão que gerou o erro. O compose de produção passa o mesmo valor ao build do SPA, para
# um erro de browser e um de API caírem na mesma release.
SENTRY_RELEASE = os.getenv("SENTRY_RELEASE", "")
SENTRY_TRACES_SAMPLE_RATE = float(os.getenv("SENTRY_TRACES_SAMPLE_RATE", "0") or 0)

# Backup (FDD 021, ADR 0013). O portal não faz backup — quem faz é o sidecar `backup`, em outro
# container. O que a aplicação lê é o carimbo que ele deixa, e só para o `manage.py backup_status`
# poder reprovar quando o agendamento parou. Vazio (o default fora do compose de produção) = o
# comando diz que não há nada configurado, em vez de fingir que está tudo bem.
BACKUP_ROOT = os.getenv("BACKUP_ROOT", "")
# 26 h: folga sobre o backup diário, sem deixar passar um dia inteiro sem cópia.
BACKUP_MAX_AGE_HOURS = _env_int("BACKUP_MAX_AGE_HOURS", 26)

# Agendador de trabalho periódico (FDD 023, ADR 0015). Quem roda é o serviço `scheduler` do
# compose (`manage.py run_scheduler`), não a API — a imagem é a mesma, o processo é outro.
# Horários em hora de parede de `TIME_ZONE`, não no `TZ` do container.
SCHEDULER_TICK_SECONDS = _env_int("SCHEDULER_TICK_SECONDS", 60)
# Cedo o bastante para o resumo chegar antes do dia começar, tarde o bastante para não ser
# madrugada de quem o recebe.
SCHEDULER_DIGEST_AT = os.getenv("SCHEDULER_DIGEST_AT", "07:30")
# O calendário é a única entrada de fora que vira tarefa: 15 min é o atraso máximo entre marcar
# uma reunião com `#proj-<id>` e ver a tarefa no portal.
SCHEDULER_CALENDAR_EVERY_MINUTES = _env_int("SCHEDULER_CALENDAR_EVERY_MINUTES", 15)
# Depois do backup das 03:15 e depois do digest: o alerta de backup velho é para o horário
# comercial de quem vai agir sobre ele, não para a madrugada.
SCHEDULER_BACKUP_CHECK_AT = os.getenv("SCHEDULER_BACKUP_CHECK_AT", "09:00")
# **Antes** do digest das 07:30, e a ordem é o ponto: quem lê o dia — tela, resumo, qualquer aviso
# futuro — precisa encontrar o vencimento já apurado, não a apurar.
SCHEDULER_INVOICES_AT = os.getenv("SCHEDULER_INVOICES_AT", "06:00")
# **Depois** do vencimento das 06:00, e a ordem é a entrega: a régua pergunta "que degrau cabe
# hoje?" ao estado da fatura, e rodar antes da apuração faria o D+1 ser lido como D+0. Às 09:30
# porque cobrança é conversa de horário comercial — a RFC 0004 pede "teto duro de frequência e de
# horário", e um e-mail de cobrança na madrugada é lido como robô hostil.
SCHEDULER_DUNNING_AT = os.getenv("SCHEDULER_DUNNING_AT", "09:30")
# A régua de cobrança (FDD 036, camada 3 da RFC 0004). **Nasce desligada, e não por custo nem por
# credencial**: os dois pressupostos da RFC não se cumpriram — a medição pedida ("olhar dois ou
# três meses") tem doze dias, e o gateway que *desarma* a régua nunca foi homologado. Construir
# não é ligar. Ver a seção "O pressuposto que não se cumpriu" da FDD 036.
DUNNING_ENABLED = _env_bool("DUNNING_ENABLED", False)
# Um contato por cliente a cada N dias, somando todas as faturas dele. Quem tem três vencidas
# recebe um e-mail, não três: três e-mails no mesmo minuto é a forma mais rápida de um sistema de
# cobrança parecer um robô hostil, e a relação custa mais que a fatura.
DUNNING_MIN_DAYS_BETWEEN_CONTACTS = _env_int("DUNNING_MIN_DAYS_BETWEEN_CONTACTS", 5)
# Depois do digest, para não competir por atenção com ele, e antes do alerta de backup. Em horário
# comercial de propósito: quem age sobre conhecimento vencido é gente, não um plantão.
SCHEDULER_KNOWLEDGE_AT = os.getenv("SCHEDULER_KNOWLEDGE_AT", "08:00")
CSRF_TRUSTED_ORIGINS = _env_list(
    "DJANGO_CSRF_TRUSTED_ORIGINS",
    "http://localhost:5173,http://127.0.0.1:5173,http://localhost:19173,http://127.0.0.1:19173",
)
FILE_UPLOAD_MAX_MEMORY_SIZE = 10 * 1024 * 1024
DATA_UPLOAD_MAX_MEMORY_SIZE = 12 * 1024 * 1024

# Portal do cliente — integração (ADR 0003). Vazio = integração desligada.
PORTAL_WEBHOOK_URL = os.getenv("PORTAL_WEBHOOK_URL", "")
PORTAL_WEBHOOK_SECRET = os.getenv("PORTAL_WEBHOOK_SECRET", "")
PORTAL_READ_TOKEN = os.getenv("PORTAL_READ_TOKEN", "")

# Google Drive como armazenamento de documentos. Desligado por padrão: sem credenciais, os
# documentos usam o storage local.
GOOGLE_DRIVE_ENABLED = os.getenv("GOOGLE_DRIVE_ENABLED", "false").lower() == "true"
GOOGLE_DRIVE_ROOT_FOLDER_ID = os.getenv("GOOGLE_DRIVE_ROOT_FOLDER_ID", "")

# Como o portal se autentica no Google (ADR 0016). **Nunca por chave de conta de serviço**: ela é
# um segredo de vida longa que vaza em backup, log e imagem, e organizações sérias a proíbem por
# política (`iam.managed.disableServiceAccountKeyCreation`) — foi o que bloqueou a rodada 3.
#
# - `adc` (default): Application Default Credentials. Resolve, nesta ordem, o arquivo apontado por
#   `GOOGLE_APPLICATION_CREDENTIALS` (que pode ser uma configuração de **Workload Identity
#   Federation**, sem chave), as credenciais do `gcloud auth application-default login` e, por fim,
#   o **metadata server** — que é como pod no GKE e serviço no Cloud Run se autenticam sem segredo
#   nenhum no ambiente. É o caminho para container/pod.
# - `oauth`: credencial de **usuário**, por refresh token. É o caminho quando o portal precisa agir
#   *como uma pessoa* — convidar participante em evento, por exemplo, que conta de serviço não faz
#   sem delegação em todo o domínio.
GOOGLE_AUTH_MODE = os.getenv("GOOGLE_AUTH_MODE", "adc").strip().lower()
GOOGLE_OAUTH_CLIENT_ID = os.getenv("GOOGLE_OAUTH_CLIENT_ID", "")
GOOGLE_OAUTH_CLIENT_SECRET = os.getenv("GOOGLE_OAUTH_CLIENT_SECRET", "")
GOOGLE_OAUTH_REFRESH_TOKEN = os.getenv("GOOGLE_OAUTH_REFRESH_TOKEN", "")

# Retenção de dado pessoal arquivado (LGPD). **Zero = nunca expurgar**, e é o default de todas as
# famílias: ninguém perde dado por ter atualizado o portal. O prazo de cada família é decisão de
# negócio com peso jurídico — o portal entrega o mecanismo, não o número. Ver `apps/core/retention.py`.
RETENTION_DAYS = {
    "lead": _env_int("RETENTION_LEAD_DAYS", 0),
    "document": _env_int("RETENTION_DOCUMENT_DAYS", 0),
}

# IA (OpenAI) atrás de flag. Desligado = app roda sem o SDK/key.
AI_ENABLED = os.getenv("AI_ENABLED", "false").lower() == "true"
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", "")
AI_MODEL = os.getenv("AI_MODEL", "gpt-4o-mini")
AI_BASE_URL = os.getenv("AI_BASE_URL", "")
AI_DAILY_LIMIT = int(os.getenv("AI_DAILY_LIMIT", "50"))
# O SDK da OpenAI espera 10 min por padrão. Uma destas chamadas roda dentro do POST público do
# formulário de leads, então sem teto um dia ruim do fornecedor prende o worker e derruba o site
# junto. 30 s é folgado para uma completion curta e curto para não segurar ninguém.
AI_TIMEOUT_SECONDS = _env_int("AI_TIMEOUT_SECONDS", 30)
# Base de conhecimento interna (FDD 029, ADR 0022). Mesma credencial e mesma flag (`ai`) do resto —
# uma flag a mais seria outra tela para a mesma chave. A **dimensão não é setting**: ela é assada na
# migração pelo `VectorField`, e um env var aqui seria promessa que o código não cumpre.
AI_EMBEDDING_MODEL = os.getenv("AI_EMBEDDING_MODEL", "text-embedding-3-small")
# Piso de similaridade para o material entrar no contexto. **Ele não decide correção** — a rodada 5
# de homologação mediu que as faixas de "pergunta sobre método" (51–69%) e "pergunta sobre dados"
# (47–56%) se sobrepõem, então nenhum limiar separa as duas. Quem declara de onde veio a resposta é
# o modelo (ver `knowledge.GROUNDING_RULES`); este número só evita gastar token injetando material
# claramente fora do assunto — o ruído medido ficou entre 22% e 49%.
KB_MIN_SIMILARITY_PERCENT = _env_int("KB_MIN_SIMILARITY_PERCENT", 45)
KB_TOP_K = _env_int("KB_TOP_K", 6)

# Calendário (Google) e assinatura eletrônica — esqueletos atrás de flag (desligados).
CALENDAR_ENABLED = os.getenv("CALENDAR_ENABLED", "false").lower() == "true"
GOOGLE_CALENDAR_ID = os.getenv("GOOGLE_CALENDAR_ID", "")
# Agendamento (booking) por leads qualificados (FDD 013). Calendário dedicado às reservas
# (default: o mesmo do GOOGLE_CALENDAR_ID). Corte de fit para liberar o agendamento e a duração.
GOOGLE_BOOKING_CALENDAR_ID = os.getenv("GOOGLE_BOOKING_CALENDAR_ID", "")
BOOKING_MIN_FIT = os.getenv("BOOKING_MIN_FIT", "medium")
BOOKING_SLOT_MINUTES = int(os.getenv("BOOKING_SLOT_MINUTES", "45"))
# Assinatura eletrônica (ADR 0007): fornecedor homologado + webhook de status assinado.
# `ESIGN_WEBHOOK_SECRET` é o segredo do HMAC da entrega; sem ele o webhook responde 401.
# Ligado por padrão (ADR 0018), mas sem efeito enquanto faltar qualquer uma das três credenciais
# abaixo: `flags.is_enabled` exige `configured()` antes de considerar o default do ambiente.
ESIGN_ENABLED = os.getenv("ESIGN_ENABLED", "true").lower() == "true"
ESIGN_PROVIDER = os.getenv("ESIGN_PROVIDER", "")
ESIGN_API_TOKEN = os.getenv("ESIGN_API_TOKEN", "")
# Vazio = cada adaptador usa a própria URL padrão (`Provider.DEFAULT_BASE`).
ESIGN_API_BASE = os.getenv("ESIGN_API_BASE", "")
ESIGN_WEBHOOK_SECRET = os.getenv("ESIGN_WEBHOOK_SECRET", "")
# Documentos de teste: não consomem crédito e são apagados pelo fornecedor em poucos dias.
ESIGN_SANDBOX = os.getenv("ESIGN_SANDBOX", "true").lower() == "true"
# Quem avisa o signatário: "email" (o fornecedor manda o convite, padrão) ou "link" (o
# fornecedor devolve o link de assinatura e o portal se encarrega de entregar).
ESIGN_DELIVERY = os.getenv("ESIGN_DELIVERY", "email").lower()

# Gateway de pagamento (FDD 028): cobrança emitida no fornecedor + webhook de baixa assinado.
# Ligado por padrão (ADR 0018) e sem provedor nomeado por padrão — o que significa `NullProvider`:
# a fatura vive só no portal e a baixa manual (`mark-paid`) é o único caminho, que é o modo previsto
# pela FDD 028 e não um modo degradado. Nomear `PAYMENTS_PROVIDER` torna token e segredo
# obrigatórios (`flags._payments_missing`), e sem eles `is_enabled()` continua `False`.
# Nome neutro, e não `STRIPE_*`, pela mesma razão que a assinatura é `ESIGN_*` e não `AUTENTIQUE_*`.
PAYMENTS_ENABLED = os.getenv("PAYMENTS_ENABLED", "true").lower() == "true"
PAYMENTS_PROVIDER = os.getenv("PAYMENTS_PROVIDER", "")
PAYMENTS_API_TOKEN = os.getenv("PAYMENTS_API_TOKEN", "")
# Vazio = o adaptador usa a própria URL padrão (`Provider.DEFAULT_BASE`).
PAYMENTS_API_BASE = os.getenv("PAYMENTS_API_BASE", "")
PAYMENTS_WEBHOOK_SECRET = os.getenv("PAYMENTS_WEBHOOK_SECRET", "")
# Janela de aceitação do carimbo do webhook. É o que faz uma entrega **capturada** parar de valer:
# sem ela, um corpo assinado hoje é reproduzível para sempre.
PAYMENTS_WEBHOOK_TOLERANCE_SECONDS = _env_int("PAYMENTS_WEBHOOK_TOLERANCE_SECONDS", 300)

# Enriquecimento de lead (FDD 030): dado cadastral público de CNPJ alimentando a qualificação que
# já existe. Nome neutro pela razão de `PAYMENTS_*` e `ESIGN_*` — o provedor é trocável.
#
# **Desligado por padrão, e não por conservadorismo automático.** O provedor default (BrasilAPI) é
# gratuito e não pede credencial, então a razão que desliga IA e Drive — custo por chamada — não se
# aplica; a que se aplica é outra: isto manda o CNPJ digitado no formulário público para um terceiro,
# e essa é uma decisão de fluxo de dado que a instalação toma, não um default que ela descobre
# depois. `configured()` passa sem exigir nada, no precedente do modo `adc` do Google (ADR 0016):
# não há variável cuja ausência denuncie falta de configuração, e cobrar uma recusaria a instalação
# que está certa. Quem responde "isto funciona?" é a sonda.
ENRICHMENT_ENABLED = os.getenv("ENRICHMENT_ENABLED", "false").lower() == "true"
ENRICHMENT_PROVIDER = os.getenv("ENRICHMENT_PROVIDER", "brasilapi")
# Vazio = o adaptador usa a própria URL padrão (`BrasilApiProvider.DEFAULT_BASE`).
ENRICHMENT_API_BASE = os.getenv("ENRICHMENT_API_BASE", "")
# Teto apertado de propósito: isto roda **dentro do POST público** do formulário, antes da
# qualificação. O mesmo argumento do timeout da OpenAI em `ai._client`, e aqui o prejuízo de
# esperar é maior, porque o enriquecimento é melhoria e a qualificação é o produto.
ENRICHMENT_TIMEOUT_SECONDS = _env_int("ENRICHMENT_TIMEOUT_SECONDS", 5)

# Sincronia de tarefas com ferramentas externas (Linear/GitHub) atrás de flag (ADR 0004).
# Token compartilhado para o webhook de entrada; credenciais/estados por fornecedor.
TASKSYNC_ENABLED = os.getenv("TASKSYNC_ENABLED", "false").lower() == "true"
TASKSYNC_TOKEN = os.getenv("TASKSYNC_TOKEN", "")
LINEAR_API_KEY = os.getenv("LINEAR_API_KEY", "")
LINEAR_TEAM_ID = os.getenv("LINEAR_TEAM_ID", "")
LINEAR_STATE_TODO = os.getenv("LINEAR_STATE_TODO", "")
LINEAR_STATE_IN_PROGRESS = os.getenv("LINEAR_STATE_IN_PROGRESS", "")
LINEAR_STATE_DONE = os.getenv("LINEAR_STATE_DONE", "")
GITHUB_TOKEN = os.getenv("GITHUB_TOKEN", "")
GITHUB_REPO = os.getenv("GITHUB_REPO", "")  # formato "owner/repo"
# Provisionamento de GitHub Issue a partir de um handoff de engenharia (FDD 040, ADR 0040).
# Distinto da sincronia de tarefas (FDD 004). Zero LLM; desligado por padrão.
GITHUB_PROVISIONING_ENABLED = os.getenv("GITHUB_PROVISIONING_ENABLED", "false").lower() == "true"

# Projeção de entrega: lê Issue/PR/CI do GitHub para dentro do Pulse (FDD 041, ADR 0046). Direção
# de leitura, complementar ao provisionamento. Webhook-first (segredo HMAC) com reconciliação por
# poll (token). Zero LLM; desligado por padrão. `GITHUB_REPO` não é exigido aqui: o repositório é
# por-projeção, não global.
GITHUB_DELIVERY_ENABLED = os.getenv("GITHUB_DELIVERY_ENABLED", "false").lower() == "true"
GITHUB_WEBHOOK_SECRET = os.getenv("GITHUB_WEBHOOK_SECRET", "")
# Além deste tempo sem confirmação, uma projeção `current` passa a ser exibida como `stale` — o que
# torna "referência não confirmada" explícito em vez de deixar um estado velho se passar por atual.
GITHUB_PROJECTION_STALE_AFTER_SECONDS = _env_int("GITHUB_PROJECTION_STALE_AFTER_SECONDS", 3600)

# Captação de leads pelo site: token compartilhado e CORS restrito ao endpoint de intake.
LEAD_INTAKE_TOKEN = os.getenv("LEAD_INTAKE_TOKEN", "")
CORS_URLS_REGEX = r"^/api/v1/leads/intake/$"
CORS_ALLOWED_ORIGINS = _env_list("CORS_ALLOWED_ORIGINS")

# Por último, com a configuração toda montada. Aqui e não em `AppConfig.ready()` porque erro de
# import de app e de configuração acontece **antes** do `ready()` — e são justamente os que
# ninguém enxerga atrás do gunicorn. No-op sem `SENTRY_DSN` (ADR 0012).
from apps.core.observability import init_sentry  # noqa: E402  (precisa das settings acima)

init_sentry(SENTRY_DSN, SENTRY_ENVIRONMENT, SENTRY_RELEASE, SENTRY_TRACES_SAMPLE_RATE)
