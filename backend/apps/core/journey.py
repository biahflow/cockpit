"""Materialização e transição da Jornada de Transformação (FDD 011).

A jornada é um template global e configurável (`JourneyPhase` + `PhaseDeliverable`, no
mesmo espírito de `PipelineStage`). Cada projeto recebe uma cópia por instância
(`ProjectPhase` + `ProjectDeliverable`) para carregar seu próprio estado — qual fase está
ativa, quais entregáveis já saíram — sem que editar o template reescreva o histórico.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from django.utils import timezone

if TYPE_CHECKING:
    from .models import Project, ProjectPhase


def materialize_journey(project: Project) -> None:
    """Cria os `ProjectPhase`/`ProjectDeliverable` do template para o projeto.

    Idempotente: se o projeto já tem fases, não faz nada (seguro para chamada defensiva
    na leitura de projetos antigos). A primeira fase nasce `active`; as demais `locked`.
    """
    from .models import JourneyPhase, ProjectDeliverable, ProjectPhase

    if ProjectPhase.objects.filter(project=project).exists():
        return
    # `active=True`: fase aposentada não entra em projeto novo. Os projetos que já a
    # materializaram continuam com a delas — desativar é sobre o futuro (FDD 011).
    phases = list(
        JourneyPhase.objects.filter(active=True)
        .prefetch_related("deliverables")
        .order_by("position", "id")
    )
    now = timezone.now()
    for index, phase in enumerate(phases):
        project_phase = ProjectPhase.objects.create(
            project=project,
            phase=phase,
            status=ProjectPhase.Status.ACTIVE if index == 0 else ProjectPhase.Status.LOCKED,
            started_at=now if index == 0 else None,
        )
        for deliverable in phase.deliverables.all():
            ProjectDeliverable.objects.create(
                project_phase=project_phase, name=deliverable.name, position=deliverable.position
            )


def advance_phase(project: Project) -> ProjectPhase | None:
    """Conclui a fase ativa e ativa a próxima. Retorna a nova fase ativa (ou `None`).

    Não bloqueia por entregáveis pendentes — o avanço é uma decisão da equipe. Se não
    houver fase ativa (projeto no fim, ou estado incomum), tenta ativar a próxima
    bloqueada.
    """
    from .models import ProjectPhase

    materialize_journey(project)
    phases = list(
        ProjectPhase.objects.filter(project=project, archived_at__isnull=True)
        .select_related("phase")
        .order_by("phase__position", "id")
    )
    now = timezone.now()
    current = next((p for p in phases if p.status == ProjectPhase.Status.ACTIVE), None)
    if current is not None:
        current.status = ProjectPhase.Status.DONE
        current.completed_at = now
        current.save(update_fields=["status", "completed_at", "updated_at"])
        remaining = phases[phases.index(current) + 1 :]
    else:
        remaining = phases

    nxt = next((p for p in remaining if p.status == ProjectPhase.Status.LOCKED), None)
    if nxt is not None:
        nxt.status = ProjectPhase.Status.ACTIVE
        nxt.started_at = now
        nxt.save(update_fields=["status", "started_at", "updated_at"])
    return nxt
