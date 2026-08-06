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
    ProjectDeliverable,
    ProjectMember,
    ProjectPhase,
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


@receiver(post_save, sender=Project)
def _owner_is_always_a_member(
    sender: type[Project], instance: Project, **kwargs: Any
) -> None:
    """Invariante: quem responde pelo projeto participa dele (RFC 0003, ADR 0010).

    Fica no signal, e não no `perform_create` da view, porque precisa valer nos três caminhos
    que criam projeto — API, admin do Django e as factories dos testes. Sem isso, transferir a
    titularidade deixaria o novo dono sem acesso ao próprio projeto.
    """
    ProjectMember.objects.get_or_create(
        project=instance, user_id=instance.owner_id, archived_at=None
    )


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


# A jornada é justamente o que a barra "Você está aqui" do portal mostra, e era a única parte do
# projeto que mudava em silêncio: avançar fase e marcar entregável não salvam o `Project`, então
# nenhum dos emissores acima disparava e a fase nova só chegava ao cliente de carona no próximo
# salvamento de outro objeto.
#
# O `created` não é zelo excessivo: `journey.materialize_journey` cria as fases e os entregáveis
# num laço de `.objects.create()`, e sem o guarda **criar um projeto** dispararia dezenas de
# webhooks — cada um provocando um snapshot inteiro do lado do portal — todos redundantes com o
# `_emit_project` do mesmo commit. Criação já está coberta; o que faltava era a mudança de estado.
@receiver(post_save, sender=ProjectPhase)
def _emit_project_phase(
    sender: type[ProjectPhase], instance: ProjectPhase, created: bool, **kwargs: Any
) -> None:
    if created:
        return
    portal.emit("updated", "project_phase", instance.project_id)


@receiver(post_save, sender=ProjectDeliverable)
def _emit_project_deliverable(
    sender: type[ProjectDeliverable], instance: ProjectDeliverable, created: bool, **kwargs: Any
) -> None:
    if created:
        return
    portal.emit("updated", "project_deliverable", instance.project_phase.project_id)


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
