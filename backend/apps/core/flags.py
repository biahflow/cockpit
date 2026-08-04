"""Resolução das flags de integração: override em runtime sobre o default do ambiente.

Cada integração tem um default vindo do `.env` (`settings.*_ENABLED` ou a presença de uma
credencial) e pode ser ligada/desligada em runtime por um admin, gravando um `AppSetting`.
Segredos/keys continuam só no ambiente; aqui mora apenas o liga/desliga.

`configured(name)` diz se as credenciais necessárias estão presentes — sem elas o toggle não
deve ligar (a API recusa). A leitura do banco é protegida para não quebrar o boot/migrate
(quando a tabela `AppSetting` ainda não existe, cai no default do ambiente).
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field

from django.conf import settings
from django.db.utils import OperationalError, ProgrammingError


@dataclass(frozen=True)
class Flag:
    label: str
    env_default: Callable[[], bool]
    requires: tuple[str, ...] = field(default_factory=tuple)
    toggleable: bool = True


FLAGS: dict[str, Flag] = {
    "ai": Flag("Assistente de IA", lambda: bool(settings.AI_ENABLED), ("OPENAI_API_KEY",)),
    "drive": Flag(
        "Documentos no Google Drive",
        lambda: bool(settings.GOOGLE_DRIVE_ENABLED),
        ("GOOGLE_DRIVE_ROOT_FOLDER_ID",),
    ),
    "calendar": Flag(
        "Calendário (Google)", lambda: bool(settings.CALENDAR_ENABLED), ("GOOGLE_CALENDAR_ID",)
    ),
    "esign": Flag("Assinatura eletrônica", lambda: bool(settings.ESIGN_ENABLED), ("ESIGN_PROVIDER",)),
    # SMTP já vem configurado por padrão, então não exige credencial extra para ligar.
    "email": Flag("Notificações por e-mail e digest", lambda: bool(settings.EMAIL_NOTIFICATIONS_ENABLED)),
    "tasksync": Flag(
        "Sincronia de tarefas (Linear/GitHub)",
        lambda: bool(settings.TASKSYNC_ENABLED),
        ("TASKSYNC_TOKEN",),
    ),
    # Portal do cliente: "ligado" = URL+secret presentes; não é alternável em runtime.
    "portal": Flag(
        "Portal do cliente",
        lambda: bool(settings.PORTAL_WEBHOOK_URL and settings.PORTAL_WEBHOOK_SECRET),
        ("PORTAL_WEBHOOK_URL", "PORTAL_WEBHOOK_SECRET"),
        toggleable=False,
    ),
}


def _override(name: str) -> bool | None:
    from .models import AppSetting

    try:
        setting = AppSetting.objects.filter(key=name).first()
    except (OperationalError, ProgrammingError):  # pragma: no cover - tabela ainda não migrada
        return None
    return setting.enabled if setting else None


def is_enabled(name: str) -> bool:
    flag = FLAGS[name]
    if flag.toggleable:
        override = _override(name)
        if override is not None:
            return override
    return flag.env_default()


def configured(name: str) -> bool:
    """Todas as credenciais exigidas pela integração estão presentes no ambiente?"""
    return all(getattr(settings, key, "") for key in FLAGS[name].requires)


def status(name: str) -> dict[str, object]:
    flag = FLAGS[name]
    return {
        "key": name,
        "label": flag.label,
        "enabled": is_enabled(name),
        "configured": configured(name),
        "toggleable": flag.toggleable,
    }


def all_status() -> list[dict[str, object]]:
    return [status(name) for name in FLAGS]
