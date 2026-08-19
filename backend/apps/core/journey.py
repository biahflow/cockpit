"""Materialização e transição da Jornada de Transformação (FDD 011, FDD 033).

A jornada é um template global e configurável (`JourneyPhase` + `PhaseDeliverable` +
`PhaseChecklistItem`, no mesmo espírito de `PipelineStage`). Cada projeto recebe uma cópia
por instância (`ProjectPhase` + `ProjectDeliverable` + `ProjectChecklistItem`) para carregar
seu próprio estado — qual fase está ativa, quais entregáveis já saíram, o que já foi
conferido — sem que editar o template reescreva o histórico.

**As duas recusas moram aqui, e não nas views** (FDD 033). O decision gate de quatro saídas e
o quality gate são regra de domínio: quem concluir uma fase por qualquer caminho tem de passar
por elas, e uma guarda escrita na view só vale para a rota que a chamou. `StateConflict` vem de
`exceptions`, que não importa nada do domínio — é o que mantém este módulo importável sem
request (`views` importa `journey`; o contrário fecharia o ciclo).
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from django.db import transaction
from django.utils import timezone

from .exceptions import StateConflict

if TYPE_CHECKING:
    from .models import Project, ProjectPhase


def materialize_journey(project: Project) -> None:
    """Cria os `ProjectPhase`/`ProjectDeliverable`/`ProjectChecklistItem` do template.

    Idempotente: se o projeto já tem fases, não faz nada (seguro para chamada defensiva
    na leitura de projetos antigos). A primeira fase nasce `active`; as demais `locked`.
    """
    from .models import (
        JourneyPhase,
        ProjectChecklistItem,
        ProjectDeliverable,
        ProjectPhase,
    )

    if ProjectPhase.objects.filter(project=project).exists():
        return
    # `active=True`: fase aposentada não entra em projeto novo. Os projetos que já a
    # materializaram continuam com a delas — desativar é sobre o futuro (FDD 011).
    phases = list(
        JourneyPhase.objects.filter(active=True)
        .prefetch_related("deliverables", "checklist_items")
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
        # O checklist copia junto e pelo mesmo motivo: editar a pergunta no template não pode
        # reescrever o que um projeto em andamento já respondeu (FDD 033).
        for item in phase.checklist_items.all():
            ProjectChecklistItem.objects.create(
                project_phase=project_phase, text=item.text, position=item.position
            )


def _pending_checklist_count(project_phase: ProjectPhase) -> int:
    """Itens de qualidade ainda não conferidos na fase (arquivados não contam)."""
    return project_phase.checklist_items.filter(
        archived_at__isnull=True, checked=False
    ).count()


def _assert_checklist_allows_completion(project_phase: ProjectPhase) -> None:
    """Quality gate: checklist completa **ou** justificativa registrada (FDD 033).

    Zero itens passa, e isso é deliberado: as fases semeadas antes desta FDD não têm checklist
    nenhuma, e travá-las quebraria a jornada de todo projeto existente. O gate vale onde alguém
    configurou o que precisa ser conferido.
    """
    if project_phase.checklist_waiver.strip():
        return
    pending = _pending_checklist_count(project_phase)
    if pending:
        raise StateConflict(
            f"Faltam {pending} item(ns) do checklist de qualidade desta fase. Marque os itens "
            "que faltam ou registre a justificativa para concluir mesmo assim."
        )


def _assert_gate_allows_advance(project_phase: ProjectPhase) -> None:
    """Decision gate: a fase marcada não avança sem uma das quatro saídas (FDD 033)."""
    from .models import ProjectPhase

    if not project_phase.phase.requires_gate:
        return
    if not project_phase.gate_outcome:
        raise StateConflict(
            "Esta fase termina em decision gate; registre GO / CONDITIONAL GO / REDESIGN / NO-GO "
            "antes de concluí-la."
        )
    blocking = {ProjectPhase.GateOutcome.REDESIGN, ProjectPhase.GateOutcome.NO_GO}
    if project_phase.gate_outcome in blocking:
        raise StateConflict(
            f"O decision gate desta fase registrou "
            f"{project_phase.get_gate_outcome_display()} — a jornada não segue adiante por aqui."
        )


def advance_phase(project: Project) -> ProjectPhase | None:
    """Conclui a fase ativa e ativa a próxima. Retorna a nova fase ativa (ou `None`).

    Não bloqueia por entregáveis pendentes — o avanço é uma decisão da equipe. Bloqueia, sim,
    pelos dois gates da FDD 033: o decision gate da fase marcada e o checklist de qualidade.
    Se não houver fase ativa (projeto no fim, ou estado incomum), tenta ativar a próxima
    bloqueada — e aí não há o que travar, porque não há fase se concluindo.
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
        _assert_gate_allows_advance(current)
        _assert_checklist_allows_completion(current)
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


def apply_gate(project: Project, outcome: str, notes: str = "") -> ProjectPhase | None:
    """Registra o decision gate da fase ativa e aplica o que ele decidiu (FDD 033).

    Devolve a fase que ficou ativa depois da decisão: a próxima no GO/CONDITIONAL GO, a
    **anterior** no REDESIGN, a própria no NO-GO.

    As quatro saídas não são quatro variações de "avançar":

    - `go`/`conditional_go` concluem a fase e ativam a seguinte — a diferença entre elas está
      nas ressalvas gravadas, que é justamente o que se perderia colapsando as duas;
    - `redesign` volta à fase anterior (a abordagem muda e se testa de novo) e **tranca** a
      corrente, mantendo `started_at` e o `gate_outcome` como registro do porquê;
    - `no_go` só registra: a fase continua ativa e a jornada para ali. Mudar o status do
      projeto é ato humano, fora desta função.

    Tudo é validado antes de qualquer escrita, e o que escreve roda em transação: um gate
    recusado no meio não pode deixar o outcome gravado sem o efeito dele.
    """
    from .models import ProjectPhase

    materialize_journey(project)
    phases = list(
        ProjectPhase.objects.filter(project=project, archived_at__isnull=True)
        .select_related("phase")
        .order_by("phase__position", "id")
    )
    current = next((p for p in phases if p.status == ProjectPhase.Status.ACTIVE), None)
    if current is None:
        raise StateConflict("Não há fase ativa nesta jornada para receber um decision gate.")
    if not current.phase.requires_gate:
        raise StateConflict(
            f"A fase {current.phase.name} não termina em decision gate. Marque-a como fase de "
            "gate na configuração da Jornada, se for o caso."
        )

    previous: ProjectPhase | None = None
    if outcome == ProjectPhase.GateOutcome.REDESIGN:
        previous = next(
            (
                p
                for p in reversed(phases[: phases.index(current)])
                if p.status == ProjectPhase.Status.DONE
            ),
            None,
        )
        if previous is None:
            raise StateConflict(
                "REDESIGN volta à fase anterior, e esta é a primeira fase concluída da jornada — "
                "não há para onde voltar."
            )
    elif outcome in {ProjectPhase.GateOutcome.GO, ProjectPhase.GateOutcome.CONDITIONAL_GO}:
        # Antes de gravar o outcome: um GO que esbarra no quality gate não pode deixar o gate
        # registrado sem a conclusão que ele autoriza.
        _assert_checklist_allows_completion(current)

    with transaction.atomic():
        current.gate_outcome = outcome
        current.gate_notes = notes
        current.save(update_fields=["gate_outcome", "gate_notes", "updated_at"])

        if outcome in {ProjectPhase.GateOutcome.GO, ProjectPhase.GateOutcome.CONDITIONAL_GO}:
            return advance_phase(project)

        if previous is not None:  # REDESIGN, com a fase anterior já resolvida acima
            # Reabrir limpa o carimbo e o gate da fase que volta — precedente do `resolved_at`
            # da `Pendencia`: "concluída em" e "decidido" são estado corrente, e uma fase que
            # voltou a estar em andamento não tem nem um nem outro. É o oposto do `published_at`
            # da `Decisao`, que é fato histórico e sobrevive à despublicação (FDD 032).
            previous.status = ProjectPhase.Status.ACTIVE
            previous.completed_at = None
            previous.gate_outcome = ""
            previous.gate_notes = ""
            previous.save(
                update_fields=["status", "completed_at", "gate_outcome", "gate_notes", "updated_at"]
            )
            # A corrente tranca **mantendo** `started_at` e o outcome: é o registro de que se
            # passou por aqui e do porquê de ter voltado.
            current.status = ProjectPhase.Status.LOCKED
            current.save(update_fields=["status", "updated_at"])
            return previous

        return current  # NO-GO: a fase fica ativa e a jornada para ali
