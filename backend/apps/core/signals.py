"""Sinais que notificam o portal do cliente quando o status muda (ADR 0003)."""

from __future__ import annotations

from typing import Any

from django.db.models.signals import post_save
from django.dispatch import receiver

from . import journey, notifications, portal, tasksync
from .models import (
    Client,
    Document,
    Lead,
    Meeting,
    Milestone,
    Opportunity,
    Pendencia,
    Project,
    Task,
    User,
)


@receiver(post_save, sender=Project)
def _emit_project(sender: type[Project], instance: Project, **kwargs: Any) -> None:
    portal.emit("updated", "project", instance.pk)


@receiver(post_save, sender=Project)
def _materialize_project_journey(
    sender: type[Project], instance: Project, created: bool, **kwargs: Any
) -> None:
    """Ao nascer um projeto, instancia sua Jornada de Transformação a partir do template."""
    if created:
        journey.materialize_journey(instance)


@receiver(post_save, sender=Milestone)
def _emit_milestone(sender: type[Milestone], instance: Milestone, **kwargs: Any) -> None:
    portal.emit("updated", "milestone", instance.project_id)


@receiver(post_save, sender=Task)
def _emit_task(sender: type[Task], instance: Task, **kwargs: Any) -> None:
    portal.emit("updated", "task", instance.project_id)


@receiver(post_save, sender=Document)
def _emit_document(sender: type[Document], instance: Document, **kwargs: Any) -> None:
    portal.emit("updated", "document", instance.project_id)


@receiver(post_save, sender=Meeting)
def _emit_meeting(sender: type[Meeting], instance: Meeting, **kwargs: Any) -> None:
    portal.emit("updated", "meeting", instance.project_id)


@receiver(post_save, sender=Pendencia)
def _emit_pendencia(sender: type[Pendencia], instance: Pendencia, **kwargs: Any) -> None:
    portal.emit("updated", "pendencia", instance.project_id)


@receiver(post_save, sender=Lead)
def _notify_new_lead(sender: type[Lead], instance: Lead, created: bool, **kwargs: Any) -> None:
    if not created:
        return
    recipients = User.objects.filter(role__in=[User.Role.ADMIN, User.Role.SALES], is_active=True)
    notifications.notify(recipients, "lead", f"Novo lead: {instance.name}", "/leads")


@receiver(post_save, sender=Task)
def _notify_task_owner(sender: type[Task], instance: Task, created: bool, **kwargs: Any) -> None:
    if created and instance.owner_id:
        notifications.notify([instance.owner], "task", f"Nova tarefa: {instance.title}", f"/projetos/{instance.project_id}")


@receiver(post_save, sender=Milestone)
def _notify_milestone_owner(sender: type[Milestone], instance: Milestone, created: bool, **kwargs: Any) -> None:
    if created and instance.owner_id:
        notifications.notify([instance.owner], "milestone", f"Novo marco: {instance.title}", f"/projetos/{instance.project_id}")


@receiver(post_save, sender=Task)
def _push_task_external(sender: type[Task], instance: Task, **kwargs: Any) -> None:
    """Saída: replica a mudança da tarefa para o fornecedor (Linear/GitHub) quando ligado.

    Não faz nada durante a aplicação da entrada (guard de eco) nem para tarefas sem vínculo.
    """
    if tasksync.outbound_suppressed():
        return
    tasksync.push_update(instance)


@receiver(post_save, sender=Opportunity)
def _promote_client_on_won(sender: type[Opportunity], instance: Opportunity, **kwargs: Any) -> None:
    """Promove o cliente de prospect para ativo quando a oportunidade é ganha (ADR/plano D)."""
    if instance.is_won:
        Client.objects.filter(pk=instance.client_id, status=Client.Status.PROSPECT).update(
            status=Client.Status.ACTIVE
        )
