from django.apps import AppConfig


class CoreConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "apps.core"

    def ready(self) -> None:
        # `signals` registra os receivers do portal; `checks`, as verificações de `check --deploy`.
        from . import checks, signals  # noqa: F401

