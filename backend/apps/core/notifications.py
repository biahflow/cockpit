"""Criação de notificações in-app (e e-mail espelhado quando ligado).

Quem notifica sobre algo de um projeto **passa `project=`** — e aí quem não alcança aquele projeto
é descartado antes de qualquer linha ser gravada (FDD 010, FDD 018, ADR 0010).

A guarda existe porque nada reatribui item quando alguém sai de uma equipe: o `ProjectMember` é
arquivado e o `WorkItem.owner` fica. Sem ela, `tasksync.apply_inbound` — que dispara por webhook do
fornecedor, muito depois da criação e sem `request.user` nenhum para consultar — seguia mandando o
título da tarefa e um link `/projetos/<id>` para quem já leva 404 ao clicar.

Sem `project`, nada muda: é o caso das notificações escolhidas por **papel** (lead novo, booking),
que não falam de projeto e para as quais um recorte por participação seria simplesmente errado.
"""

from __future__ import annotations

from collections.abc import Iterable
from typing import TYPE_CHECKING

from django.core.mail import send_mail

from . import flags

if TYPE_CHECKING:
    from .models import Project, User


def notify(
    users: Iterable[User],
    kind: str,
    message: str,
    url: str = "",
    project: Project | None = None,
) -> None:
    from .models import Notification, can_access_project

    recipients = list(users)
    if project is not None:
        # Um `exists()` por destinatário. Os chamadores com projeto notificam **uma** pessoa, e o
        # único que notifica muitos (lead → admin/vendas) não passa projeto — então não vale
        # trocar isto por uma consulta só reexpressando a regra em SQL, que é o que `visible_to`
        # existe para impedir (models.py).
        recipients = [user for user in recipients if can_access_project(user, project)]
        if not recipients:
            return
    # `message` é `CharField(max_length=255)`, e quem chama monta a frase com nome de projeto e de
    # mandato — dois campos de 255 cada. Estourar aqui **trunca em silêncio no SQLite e levanta no
    # Postgres**, e quem levanta é um efeito de pós-commit (`kickoff.finalize` roda fora da
    # transação): o projeto já existe, e a rota devolve 500 por causa do aviso. Cortar no ponto de
    # escrita resolve para todo chamador de uma vez — a alternativa era cada um lembrar do limite.
    message = message if len(message) <= 255 else f"{message[:254]}…"
    Notification.objects.bulk_create(
        [Notification(user=user, kind=kind, message=message, url=url) for user in recipients]
    )
    if flags.is_enabled("email"):
        _email(recipients, message)


def _email(users: Iterable[User], message: str) -> None:
    addresses = [user.email for user in users if user.email]
    for address in addresses:
        send_mail("Portal Biahflow — notificação", message, None, [address], fail_silently=True)
