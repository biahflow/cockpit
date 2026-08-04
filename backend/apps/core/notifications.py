"""Criação de notificações in-app (e e-mail espelhado quando ligado)."""

from __future__ import annotations

from collections.abc import Iterable
from typing import TYPE_CHECKING

from django.core.mail import send_mail

from . import flags

if TYPE_CHECKING:
    from .models import User


def notify(users: Iterable[User], kind: str, message: str, url: str = "") -> None:
    from .models import Notification

    recipients = list(users)
    Notification.objects.bulk_create(
        [Notification(user=user, kind=kind, message=message, url=url) for user in recipients]
    )
    if flags.is_enabled("email"):
        _email(recipients, message)


def _email(users: Iterable[User], message: str) -> None:
    addresses = [user.email for user in users if user.email]
    for address in addresses:
        send_mail("Portal Biahflow — notificação", message, None, [address], fail_silently=True)
