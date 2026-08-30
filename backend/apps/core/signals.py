"""Sinais que notificam o portal do cliente quando o status muda (ADR 0003)."""

from __future__ import annotations

from typing import Any

from django.db.models import ProtectedError
from django.db.models.signals import post_delete, post_save, pre_delete
from django.dispatch import receiver

from . import cases, journey, notifications, portal, tasksync
from .models import (
    Account,
    Artifact,
    CommercialOpportunity,
    Decisao,
    DigitalEmployee,
    Document,
    Engagement,
    Invoice,
    JourneyPhase,
    Lead,
    Meeting,
    Milestone,
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


@receiver(post_save, sender=Project)
def _freeze_case_on_completion(sender: type[Project], instance: Project, **kwargs: Any) -> None:
    """Congela o case quando o projeto é concluído (FDD 027).

    Signal, e não uma ação na tela, porque o valor inteiro está em capturar **aquele instante**:
    um botão "gerar case" clicado semanas depois congelaria um health que já mudou, que é o defeito
    que a FDD existe para evitar. Sem guarda de `created`: um projeto importado já concluído também
    merece case, e `freeze_if_completed` cuida de não duplicar.
    """
    cases.freeze_if_completed(instance)


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


# Sem guarda de `created`, como os quatro acima — e aqui isso importa duas vezes. Publicar uma
# decisão é um `save()` que muda `status`, e arquivar é um `save()` que preenche `archived_at`: as
# duas mudam o que o snapshot mostra sem criar linha nenhuma. Um receiver que ignorasse update
# deixaria o cliente vendo uma decisão que já saiu do snapshot — o defeito exato do funcionário
# digital (emenda de 07/08/2026 na ADR 0003), que é a mudança mais silenciosa das três.
@receiver(post_save, sender=Decisao)
def _emit_decisao(sender: type[Decisao], instance: Decisao, **kwargs: Any) -> None:
    portal.emit("updated", "decisao", instance.project_id)


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


# O engajamento entrou no snapshot (Issue #71) e precisa de emissor, pela regra da ADR 0003.
#
# **Fan-out deliberado, e o contraste com o artefato é o argumento.** `_emit_artifact` escolhe
# **um** projeto de propósito (emenda de 07/08/2026 na ADR 0003), porque só um é afetado: a data
# da primeira aceitação é um fato do cliente, e um aviso basta. Aqui é o oposto — renomear ou
# pausar um mandato muda `project.engagement` no snapshot de **todos** os projetos dele, e um
# projeto que não recebesse o aviso ficaria exibindo o nome antigo até o próximo salvamento de
# outra coisa. É o defeito do funcionário digital por outro eixo.
#
# Sem guarda de `created`: um engajamento recém-criado ainda não tem projeto (a conversão o cria
# antes do projeto), então o laço não itera e a criação já sai de graça. O que importa é o update.
@receiver(post_save, sender=Engagement)
def _emit_engagement(sender: type[Engagement], instance: Engagement, **kwargs: Any) -> None:
    for project_id in instance.projects.values_list("id", flat=True):
        portal.emit("updated", "engagement", project_id)


# O **template** da fase agora atravessa: `canonical_stage` e `requires_gate` saem dele, não da
# instância (Issue #71). Editar a fase pela tela de configuração muda o snapshot de todo projeto
# que a tem materializada, e sem este receiver nenhum deles saberia.
#
# É fan-out maior que o do engajamento — uma fase do template é comum a toda a carteira —, e o
# que o justifica é a raridade: isto é tela de admin da metodologia, não fluxo de operação.
#
# `archived_at__isnull=True` porque a fase arquivada já saiu do snapshot daquele projeto. O
# `distinct()` é defensivo e não corretivo — hoje a `UniqueConstraint(project, phase)` garante uma
# linha por par, e a redundância custa nada; o que ela evita é um webhook duplicado por projeto se
# a restrição um dia mudar de forma.
@receiver(post_save, sender=JourneyPhase)
def _emit_journey_phase(sender: type[JourneyPhase], instance: JourneyPhase, **kwargs: Any) -> None:
    project_ids = (
        ProjectPhase.objects.filter(phase=instance, archived_at__isnull=True)
        .values_list("project_id", flat=True)
        .distinct()
    )
    for project_id in project_ids:
        portal.emit("updated", "journey_phase", project_id)


@receiver(post_save, sender=ProjectDeliverable)
def _emit_project_deliverable(
    sender: type[ProjectDeliverable], instance: ProjectDeliverable, created: bool, **kwargs: Any
) -> None:
    if created:
        return
    portal.emit("updated", "project_deliverable", instance.project_phase.project_id)


# A aceitação de artefato é o degrau que o funil de onboarding do portal declarava ausente por
# falta de produtor daqui (RFC 001 de lá; o enum tinha a razão escrita: "ele entra quando o outro
# lado o afirmar"). É a forma da FDD 023: o que entra no snapshot precisa de emissor.
#
# Só `ACCEPTED` emite. Rascunho, revisão e envio mudam a linha várias vezes e não movem degrau
# nenhum — e `REJECTED` também não, porque o funil mede o que o cliente **recebeu**, não o que ele
# recusou. É a mesma economia do `if created: return` dos dois receivers acima, por outro eixo.
#
# **O projeto tem de ser resolvido, e às vezes não existe.** `portal.emit` não faz nada sem
# `project_id`, e o artefato pode estar preso a uma `CommercialOpportunity` — que é justamente
# onde o contrato vive no caso típico, porque a aceitação dele é o que *cria* o projeto depois. Então:
# o projeto do artefato quando há; senão o projeto vivo mais antigo do mesmo cliente; senão nada,
# e isso é limite declarado e não esquecimento — sem projeto o portal ainda não conhece aquela
# organização, e o fato chega inteiro no primeiro snapshot depois que o projeto nascer, porque
# `build_snapshot` o calcula sobre o cliente e não sobre o evento.
#
# Um projeto só, nunca fan-out, pelo argumento que o `post_delete` de `Project` já escreve acima.
@receiver(post_save, sender=Artifact)
def _emit_artifact(sender: type[Artifact], instance: Artifact, **kwargs: Any) -> None:
    if instance.status != Artifact.Status.ACCEPTED:
        return
    project_id = instance.project_id
    if project_id is None and instance.commercial_opportunity_id is not None:
        project_id = (
            Project.objects.filter(
                engagement__account__opportunities=instance.commercial_opportunity_id,
                archived_at__isnull=True,
            )
            .order_by("created_at", "id")
            .values_list("id", flat=True)
            .first()
        )
    portal.emit("updated", "artifact", project_id)


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


@receiver(post_save, sender=CommercialOpportunity)
def _promote_account_on_won(
    sender: type[CommercialOpportunity], instance: CommercialOpportunity, **kwargs: Any
) -> None:
    """Promove a conta de prospect para "Cliente" quando a oportunidade é ganha (ADR/plano D).

    Só esta transição é automática. `active → inactive` não tem signal e não vai ter: "não tem
    trabalho em andamento" não é fato observável no banco (projeto pausado, mandato em renovação e
    conta que sumiu produzem o mesmo estado), então quem edita a conta é quem afirma.
    """
    if instance.is_won:
        Account.objects.filter(
            pk=instance.account_id, lifecycle_status=Account.LifecycleStatus.PROSPECT
        ).update(lifecycle_status=Account.LifecycleStatus.ACTIVE)


@receiver(pre_delete, sender=Invoice)
def _refuse_deleting_issued_invoice(sender: type[Invoice], instance: Invoice, **kwargs: Any) -> None:
    """A parede, atrás da boa mensagem (FDD 028, ADR 0021).

    `InvoiceViewSet.perform_destroy` já recusa com 409 e aponta o cancelamento — é ele que
    **explica**. Isto aqui existe para os caminhos que não passam pela viewset: shell, migração de
    dados, um `queryset.delete()` em cascata que alguém escreveu sem pensar na fatura. A mesma
    divisão de trabalho que a casa mantém entre `perform_destroy` e a rede de `ProtectedError` do
    `api_exception_handler`: a view diz o que fazer, a camada de baixo garante que não aconteça.
    """
    if instance.status != Invoice.Status.DRAFT:
        # `ProtectedError` e não uma exceção nova: o `api_exception_handler` já a traduz para 409
        # (FDD 025), então até um caminho que escape da viewset responde com o status certo em vez
        # de 500. Reusar a rede existente é o ponto — uma exceção própria precisaria de mais um
        # ramo no handler para dizer a mesma coisa.
        raise ProtectedError(
            f"A fatura {instance.number or instance.pk} está "
            f"{instance.get_status_display().lower()} e não pode ser apagada. "
            "Registro financeiro cancela-se; não se apaga.",
            {instance},
        )
