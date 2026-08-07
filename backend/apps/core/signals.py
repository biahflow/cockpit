"""Sinais que notificam o portal do cliente quando o status muda (ADR 0003)."""

from __future__ import annotations

from typing import Any

from django.db.models.signals import post_delete, post_save
from django.dispatch import receiver

from . import journey, notifications, portal, tasksync
from .models import (
    Client,
    DigitalEmployee,
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


# O único `post_delete` do repositório, e é deliberado que seja único.
#
# Exclusão de **filho** não é alcançável pelo produto: os nove viewsets que o portal enxerga são
# `ArchiveModelViewSet`, cujo `perform_destroy` chama `archive()` — um `save()`, que emite —, o
# Django admin não registra entidade de projeto nenhuma, e `retention.executar()` só alcança linha
# já arquivada, que a essa altura já saiu do snapshot e já foi propagada. Sobra o projeto, apagado
# por shell ou migração de dados, e aí o portal ficava com um projeto morto marcado como **ativo**
# para sempre: o webhook não saía, e mesmo que saísse a rota de snapshot responde 404, que ele não
# distingue de "id de outra base" (a FDD 025 corrigiu isso para o arquivamento, não para a
# exclusão).
#
# Registrar `post_delete` nos filhos além deste teria um custo medido e nenhum ganho: numa cascata
# o coletor do Django apaga filho primeiro e `on_commit` roda na ordem de registro, então cada
# filho agendaria um webhook **antes** do webhook do projeto — todos provocando um `fetch_snapshot`
# que já responde 404. Um projeto inteiro sai daqui como **um** aviso.
@receiver(post_delete, sender=Project)
def _emit_project_deleted(sender: type[Project], instance: Project, **kwargs: Any) -> None:
    portal.emit("deleted", "project", instance.pk)


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


# "O que entra no snapshot precisa de emissor" (ADR 0003) valia para o funcionário digital desde
# que ele entrou nele, e ele era o único que não tinha nenhum — nem para criação, nem para KPI, nem
# para arquivamento. O roster é o produto central e chegava à tela do cliente **de carona** no
# próximo salvamento de outra coisa, quando chegava.
#
# Sem guarda de `created`, ao contrário da jornada: o funcionário digital é cadastrado um a um pela
# tela, não materializado em laço, então não há enxurrada a conter.
@receiver(post_save, sender=DigitalEmployee)
def _emit_digital_employee(
    sender: type[DigitalEmployee], instance: DigitalEmployee, **kwargs: Any
) -> None:
    portal.emit("updated", "digital_employee", instance.project_id)


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


# `project=` na notificação: quando o item nasce pela API o dono é o próprio autor, já validado
# por `_assert_in_scope`, e a guarda é no-op. Mas `calendar_sync` e `kickoff` criam item com
# `owner=project.owner` de dentro de um job — dono que ninguém validou e cuja participação pode ter
# sido arquivada desde então. Ver FDD 010 e FDD 018.
@receiver(post_save, sender=Task)
def _notify_task_owner(sender: type[Task], instance: Task, created: bool, **kwargs: Any) -> None:
    if created and instance.owner_id:
        notifications.notify([instance.owner], "task", f"Nova tarefa: {instance.title}", f"/projetos/{instance.project_id}", project=instance.project)


@receiver(post_save, sender=Milestone)
def _notify_milestone_owner(sender: type[Milestone], instance: Milestone, created: bool, **kwargs: Any) -> None:
    if created and instance.owner_id:
        notifications.notify([instance.owner], "milestone", f"Novo marco: {instance.title}", f"/projetos/{instance.project_id}", project=instance.project)


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
