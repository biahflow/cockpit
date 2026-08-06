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
    # Grupos "um destes basta" — a credencial do Google chega como JSON inline **ou** como caminho
    # de arquivo, e exigir os dois recusaria uma instalação legítima.
    requires_any: tuple[tuple[str, ...], ...] = field(default_factory=tuple)


def _google_service_account() -> tuple[str, ...]:
    return ("GOOGLE_SERVICE_ACCOUNT_INFO", "GOOGLE_SERVICE_ACCOUNT_FILE")


# `requires` lista o que o código realmente **dereferencia**, não só o que identifica a integração.
# Antes, cinco das sete flags podiam ser ligadas pela tela Configurações faltando a credencial que
# o adaptador usa na primeira chamada: Drive e Calendário pediam o id da pasta/agenda mas não a
# conta de serviço, e-sign pedia o nome do provedor mas não o token. A tela dizia "Ligada" e o
# recurso estourava — enquanto o `docs/operacao.md` promete que "o toggle só não liga uma
# integração cujas credenciais faltem no ambiente". Agora a promessa é verdade.
FLAGS: dict[str, Flag] = {
    "ai": Flag("Assistente de IA", lambda: bool(settings.AI_ENABLED), ("OPENAI_API_KEY",)),
    "drive": Flag(
        "Documentos no Google Drive",
        lambda: bool(settings.GOOGLE_DRIVE_ENABLED),
        ("GOOGLE_DRIVE_ROOT_FOLDER_ID",),
        requires_any=(_google_service_account(),),
    ),
    "calendar": Flag(
        "Calendário (Google)",
        lambda: bool(settings.CALENDAR_ENABLED),
        ("GOOGLE_CALENDAR_ID",),
        requires_any=(_google_service_account(),),
    ),
    "esign": Flag(
        "Assinatura eletrônica",
        lambda: bool(settings.ESIGN_ENABLED),
        # O segredo do webhook entra junto: sem ele o retorno de status do fornecedor leva 401 e a
        # assinatura nunca fecha sozinha — a falha mais silenciosa desta integração.
        ("ESIGN_PROVIDER", "ESIGN_API_TOKEN", "ESIGN_WEBHOOK_SECRET"),
    ),
    # SMTP tem default (`localhost:1025`, o Mailpit do compose), então não há variável cuja ausência
    # denuncie falta de configuração — em produção esse default é "lugar nenhum". Quem cobra aqui é
    # a sonda de `check_integrations`, que abre a conexão de verdade (FDD 024).
    "email": Flag("Notificações por e-mail e digest", lambda: bool(settings.EMAIL_NOTIFICATIONS_ENABLED)),
    "tasksync": Flag(
        "Sincronia de tarefas (Linear/GitHub)",
        # `TASKSYNC_TOKEN` é o segredo de **entrada**; sem credencial de fornecedor a saída fica
        # muda, que é o modo de falha que a ADR 0004 mais quer evitar.
        lambda: bool(settings.TASKSYNC_ENABLED),
        ("TASKSYNC_TOKEN",),
        requires_any=(("LINEAR_API_KEY", "GITHUB_TOKEN"),),
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
    flag = FLAGS[name]
    if not all(getattr(settings, key, "") for key in flag.requires):
        return False
    return all(
        any(getattr(settings, key, "") for key in grupo) for grupo in flag.requires_any
    )


def missing(name: str) -> list[str]:
    """O que falta para a integração poder ser ligada — em nome de variável, para quem vai corrigir."""
    flag = FLAGS[name]
    faltando = [key for key in flag.requires if not getattr(settings, key, "")]
    faltando += [
        " ou ".join(grupo)
        for grupo in flag.requires_any
        if not any(getattr(settings, key, "") for key in grupo)
    ]
    return faltando


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
