from __future__ import annotations

import os
from pathlib import Path
from urllib.parse import urlparse

BASE_DIR = Path(__file__).resolve().parent.parent
SECRET_KEY = os.getenv("DJANGO_SECRET_KEY", "unsafe-development-key")
DEBUG = os.getenv("DJANGO_DEBUG", "false").lower() == "true"
ALLOWED_HOSTS = os.getenv("DJANGO_ALLOWED_HOSTS", "localhost,127.0.0.1,api").split(",")
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
MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "corsheaders.middleware.CorsMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
]
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
    DATABASES = {"default": {
        "ENGINE": "django.db.backends.postgresql",
        "NAME": parsed.path.lstrip("/"),
        "USER": parsed.username,
        "PASSWORD": parsed.password,
        "HOST": parsed.hostname,
        "PORT": parsed.port or 5432,
    }}
else:
    DATABASES = {
        "default": {"ENGINE": "django.db.backends.sqlite3", "NAME": str(BASE_DIR / "db.sqlite3")}
    }

AUTH_PASSWORD_VALIDATORS = [
    {"NAME": "django.contrib.auth.password_validation.MinimumLengthValidator"},
    {"NAME": "django.contrib.auth.password_validation.CommonPasswordValidator"},
]
LANGUAGE_CODE = "pt-br"
TIME_ZONE = "America/Sao_Paulo"
USE_I18N = True
USE_TZ = True
STATIC_URL = "static/"
MEDIA_URL = "/media/"
MEDIA_ROOT = BASE_DIR / "media"
DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"
AUTH_USER_MODEL = "core.User"
EMAIL_BACKEND = "django.core.mail.backends.smtp.EmailBackend"
EMAIL_HOST = os.getenv("EMAIL_HOST", "localhost")
EMAIL_PORT = int(os.getenv("EMAIL_PORT", "1025"))
DEFAULT_FROM_EMAIL = os.getenv("DEFAULT_FROM_EMAIL", "noreply@biahflow.local")
# Notificações por e-mail + digest diário (Go-live/Hypercare) — atrás de flag, desligado por padrão.
EMAIL_NOTIFICATIONS_ENABLED = os.getenv("EMAIL_NOTIFICATIONS_ENABLED", "false").lower() == "true"

REST_FRAMEWORK = {
    "DEFAULT_AUTHENTICATION_CLASSES": ["rest_framework.authentication.SessionAuthentication"],
    "DEFAULT_PERMISSION_CLASSES": ["rest_framework.permissions.IsAuthenticated"],
    "DEFAULT_SCHEMA_CLASS": "drf_spectacular.openapi.AutoSchema",
    "DEFAULT_THROTTLE_RATES": {
        "lead_intake": os.getenv("LEAD_INTAKE_RATE", "20/hour"),
        "task_sync": os.getenv("TASK_SYNC_RATE", "60/hour"),
        "booking": os.getenv("BOOKING_RATE", "60/hour"),
        "esign_webhook": os.getenv("ESIGN_WEBHOOK_RATE", "120/hour"),
    },
}
SPECTACULAR_SETTINGS = {
    "TITLE": "Biahflow API",
    "VERSION": "1.0.0",
    "SERVE_INCLUDE_SCHEMA": False,
    "ENUM_NAME_OVERRIDES": {
        "ProjectStatusEnum": "apps.core.models.Project.Status",
        "WorkItemStatusEnum": "apps.core.models.WorkItem.Status",
    },
}
SESSION_COOKIE_SECURE = not DEBUG
CSRF_COOKIE_SECURE = not DEBUG
SESSION_COOKIE_SAMESITE = "Lax"
CSRF_COOKIE_SAMESITE = "Lax"
CSRF_TRUSTED_ORIGINS = [
    origin
    for origin in os.getenv(
        "DJANGO_CSRF_TRUSTED_ORIGINS",
        "http://localhost:5173,http://127.0.0.1:5173,http://localhost:19173,http://127.0.0.1:19173",
    ).split(",")
    if origin
]
FILE_UPLOAD_MAX_MEMORY_SIZE = 10 * 1024 * 1024
DATA_UPLOAD_MAX_MEMORY_SIZE = 12 * 1024 * 1024

# Portal do cliente — integração (ADR 0003). Vazio = integração desligada.
PORTAL_WEBHOOK_URL = os.getenv("PORTAL_WEBHOOK_URL", "")
PORTAL_WEBHOOK_SECRET = os.getenv("PORTAL_WEBHOOK_SECRET", "")
PORTAL_READ_TOKEN = os.getenv("PORTAL_READ_TOKEN", "")

# Google Drive como armazenamento de documentos (conta de serviço + Shared Drive).
# Desligado por padrão: sem credenciais, os documentos usam o storage local.
GOOGLE_DRIVE_ENABLED = os.getenv("GOOGLE_DRIVE_ENABLED", "false").lower() == "true"
GOOGLE_SERVICE_ACCOUNT_INFO = os.getenv("GOOGLE_SERVICE_ACCOUNT_INFO", "")
GOOGLE_SERVICE_ACCOUNT_FILE = os.getenv("GOOGLE_SERVICE_ACCOUNT_FILE", "")
GOOGLE_DRIVE_ROOT_FOLDER_ID = os.getenv("GOOGLE_DRIVE_ROOT_FOLDER_ID", "")

# IA (OpenAI) atrás de flag. Desligado = app roda sem o SDK/key.
AI_ENABLED = os.getenv("AI_ENABLED", "false").lower() == "true"
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", "")
AI_MODEL = os.getenv("AI_MODEL", "gpt-4o-mini")
AI_BASE_URL = os.getenv("AI_BASE_URL", "")
AI_DAILY_LIMIT = int(os.getenv("AI_DAILY_LIMIT", "50"))

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
ESIGN_ENABLED = os.getenv("ESIGN_ENABLED", "false").lower() == "true"
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

# Captação de leads pelo site: token compartilhado e CORS restrito ao endpoint de intake.
LEAD_INTAKE_TOKEN = os.getenv("LEAD_INTAKE_TOKEN", "")
CORS_URLS_REGEX = r"^/api/v1/leads/intake/$"
CORS_ALLOWED_ORIGINS = [
    origin for origin in os.getenv("CORS_ALLOWED_ORIGINS", "").split(",") if origin
]
