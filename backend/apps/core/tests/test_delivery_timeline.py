"""Linha do tempo operacional da entrega (FDD 042).

Constrói sobre a Jornada de Transformação (FDD 011/033) sem duplicá-la: o histórico append-only
(`PhaseEvent`), a parte aguardada (`waiting_party`), o estado semântico derivado (`situation`), a
classificação canônica (`canonical_stage`) e os dois agregadores da linha do tempo.
"""

import pytest
from django.urls import reverse
from rest_framework.test import APIClient

from apps.core import journey
from apps.core.exceptions import StateConflict
from apps.core.models import PhaseEvent, Project, ProjectPhase, User

from .factories import ProjectFactory, ProjectMemberFactory, UserFactory


@pytest.fixture
def client() -> APIClient:
    return APIClient()


def _phase_at(project: Project, index: int) -> ProjectPhase:
    return project.phases.select_related("phase").order_by("phase__position", "id")[index]


def _requires_gate(project: Project, index: int) -> ProjectPhase:
    project_phase = _phase_at(project, index)
    project_phase.phase.requires_gate = True
    project_phase.phase.save(update_fields=["requires_gate"])
    return project_phase


# --- histórico append-only -------------------------------------------------


@pytest.mark.django_db
def test_materialization_logs_the_first_phase_started() -> None:
    """A jornada nasce com um evento de origem: a 1ª fase iniciada, sem autor (sistema)."""
    project = ProjectFactory()

    events = list(PhaseEvent.objects.filter(project=project))
    assert len(events) == 1
    assert events[0].kind == PhaseEvent.Kind.STARTED
    assert events[0].source == PhaseEvent.Source.SYSTEM
    assert events[0].actor is None
    assert events[0].phase_name == _phase_at(project, 0).phase.name


@pytest.mark.django_db
def test_advance_logs_completed_and_started_with_actor() -> None:
    project = ProjectFactory()
    actor = UserFactory(role=User.Role.DELIVERY)

    journey.advance_phase(project, actor=actor)

    kinds = list(
        PhaseEvent.objects.filter(project=project).order_by("id").values_list("kind", flat=True)
    )
    assert kinds == [
        PhaseEvent.Kind.STARTED,  # materialização
        PhaseEvent.Kind.COMPLETED,  # 1ª concluída
        PhaseEvent.Kind.STARTED,  # 2ª iniciada
    ]
    last_two = PhaseEvent.objects.filter(project=project).order_by("-id")[:2]
    assert all(e.actor == actor and e.source == PhaseEvent.Source.USER for e in last_two)


@pytest.mark.django_db
def test_redesign_history_survives_even_after_the_outcome_is_cleared() -> None:
    """REDESIGN apaga o `gate_outcome` da fase que reabre — mas o histórico continua lá (FDD 042)."""
    project = ProjectFactory()
    actor = UserFactory(role=User.Role.DELIVERY)
    _requires_gate(project, 1)
    journey.advance_phase(project, actor=actor)  # fase 1 vira ativa, fase 0 concluída

    journey.apply_gate(project, ProjectPhase.GateOutcome.REDESIGN, "abordagem mudou", actor=actor)

    reopened = _phase_at(project, 0)
    locked = _phase_at(project, 1)
    assert reopened.status == ProjectPhase.Status.ACTIVE
    assert reopened.gate_outcome == ""  # o carimbo foi apagado no estado corrente
    assert locked.status == ProjectPhase.Status.LOCKED
    # ...mas a auditoria sobrevive:
    kinds = set(
        PhaseEvent.objects.filter(project=project).values_list("kind", flat=True)
    )
    assert PhaseEvent.Kind.GATE_RECORDED in kinds
    assert PhaseEvent.Kind.REOPENED in kinds
    assert PhaseEvent.Kind.LOCKED_BY_REDESIGN in kinds
    gate_event = PhaseEvent.objects.get(
        project=project, kind=PhaseEvent.Kind.GATE_RECORDED
    )
    assert gate_event.gate_outcome == ProjectPhase.GateOutcome.REDESIGN
    assert gate_event.note == "abordagem mudou"


# --- situação (estado semântico derivado) ----------------------------------


@pytest.mark.django_db
def test_situation_is_derived_deterministically() -> None:
    project = ProjectFactory()
    active = _phase_at(project, 0)
    assert active.situation == "active"

    future = _phase_at(project, 1)
    assert future.situation == "pending"

    # bloqueada: aguardando alguém
    journey.set_phase_waiting(project, ProjectPhase.WaitingParty.CLIENT, "aguardando acesso")
    assert _phase_at(project, 0).situation == "blocked"

    # aguardando decisão: human gate
    journey.set_phase_waiting(project, ProjectPhase.WaitingParty.HUMAN_GATE)
    assert _phase_at(project, 0).situation == "waiting_decision"


@pytest.mark.django_db
def test_situation_waiting_decision_when_gate_pending() -> None:
    project = ProjectFactory()
    _requires_gate(project, 0)
    assert _phase_at(project, 0).situation == "waiting_decision"


@pytest.mark.django_db
def test_situation_completed_cancelled_and_replanned() -> None:
    project = ProjectFactory()
    _requires_gate(project, 1)
    # completed
    journey.advance_phase(project)
    assert _phase_at(project, 0).situation == "completed"
    # cancelled: NO-GO na fase de gate ativa
    journey.apply_gate(project, ProjectPhase.GateOutcome.NO_GO, "risco alto")
    assert _phase_at(project, 1).situation == "cancelled"


@pytest.mark.django_db
def test_situation_replanned_after_redesign() -> None:
    project = ProjectFactory()
    _requires_gate(project, 1)
    journey.advance_phase(project)
    journey.apply_gate(project, ProjectPhase.GateOutcome.REDESIGN, "voltar")
    # a fase trancada guarda o outcome redesign -> "replanejada"
    assert _phase_at(project, 1).situation == "replanned"


# --- set-waiting -----------------------------------------------------------


@pytest.mark.django_db
def test_set_waiting_sets_and_clears_with_events(client: APIClient) -> None:
    delivery = UserFactory(role=User.Role.DELIVERY)
    project = ProjectFactory()
    ProjectMemberFactory(project=project, user=delivery)
    client.force_authenticate(delivery)
    url = reverse("project-set-waiting", args=[project.id])

    response = client.post(
        url, {"waiting_party": "engineering", "note": "espera merge da issue"}, format="json"
    )
    assert response.status_code == 200
    active = _phase_at(project, 0)
    assert active.waiting_party == "engineering"
    assert active.blocker_note == "espera merge da issue"
    assert PhaseEvent.objects.filter(
        project=project, kind=PhaseEvent.Kind.WAITING_SET, actor=delivery
    ).exists()

    # limpar
    response = client.post(url, {"waiting_party": ""}, format="json")
    assert response.status_code == 200
    active = _phase_at(project, 0)
    assert active.waiting_party == ""
    assert active.blocker_note == ""
    assert PhaseEvent.objects.filter(
        project=project, kind=PhaseEvent.Kind.WAITING_CLEARED
    ).exists()


@pytest.mark.django_db
def test_set_waiting_rejects_invalid_party() -> None:
    project = ProjectFactory()
    with pytest.raises(StateConflict):  # -> 409
        journey.set_phase_waiting(project, "ninguem")


@pytest.mark.django_db
def test_waiting_party_is_read_only_on_patch(client: APIClient) -> None:
    """PATCH direto não grava a espera — como o `gate_outcome`, ela só entra pela action."""
    delivery = UserFactory(role=User.Role.DELIVERY)
    project = ProjectFactory()
    ProjectMemberFactory(project=project, user=delivery)
    client.force_authenticate(delivery)
    active = _phase_at(project, 0)

    response = client.patch(
        reverse("projectphase-detail", args=[active.id]),
        {"waiting_party": "client", "blocker_note": "x"},
        format="json",
    )
    assert response.status_code == 200
    active.refresh_from_db()
    assert active.waiting_party == ""  # ignorado
    assert active.blocker_note == ""


# --- endpoints da linha do tempo ------------------------------------------


@pytest.mark.django_db
def test_timeline_returns_history_current_next_gate_and_blockers(client: APIClient) -> None:
    delivery = UserFactory(role=User.Role.DELIVERY)
    project = ProjectFactory()
    ProjectMemberFactory(project=project, user=delivery)
    _requires_gate(project, 1)
    client.force_authenticate(delivery)
    journey.set_phase_waiting(project, ProjectPhase.WaitingParty.CLIENT, "aguardando dados")

    response = client.get(reverse("project-timeline", args=[project.id]))

    assert response.status_code == 200
    body = response.json()
    assert body["project"] == project.id
    assert body["current_phase"]["situation"] == "blocked"
    assert body["current_phase"]["canonical_stage"] == "discover"  # Welcome, semeado
    assert body["next_gate"]["phase_name"] == _phase_at(project, 1).phase.name
    assert body["blockers"][0]["waiting_party"] == "client"
    assert len(body["events"]) >= 2  # started + waiting_set
    assert body["next_phase"]["phase_name"] == _phase_at(project, 1).phase.name


@pytest.mark.django_db
def test_timeline_overview_is_scoped_to_visible_projects(client: APIClient) -> None:
    delivery = UserFactory(role=User.Role.DELIVERY)
    mine = ProjectFactory()
    ProjectMemberFactory(project=mine, user=delivery)
    other = ProjectFactory()  # delivery não participa
    ProjectMemberFactory(project=other, user=UserFactory(role=User.Role.DELIVERY))
    client.force_authenticate(delivery)

    response = client.get(reverse("project-timeline-overview"))

    assert response.status_code == 200
    ids = {row["project_id"] for row in response.json()}
    assert mine.id in ids
    assert other.id not in ids
    row = next(r for r in response.json() if r["project_id"] == mine.id)
    assert row["current_phase_name"] == _phase_at(mine, 0).phase.name
    assert row["situation"] == "active"


@pytest.mark.django_db
def test_timeline_overview_excludes_completed_projects(client: APIClient) -> None:
    admin = UserFactory(role=User.Role.ADMIN, is_superuser=True)
    done = ProjectFactory(status=Project.Status.COMPLETED)
    client.force_authenticate(admin)

    response = client.get(reverse("project-timeline-overview"))

    assert response.status_code == 200
    assert done.id not in {row["project_id"] for row in response.json()}


# --- RBAC ------------------------------------------------------------------


@pytest.mark.django_db
def test_sales_reads_timeline_but_cannot_set_waiting(client: APIClient) -> None:
    sales = UserFactory(role=User.Role.SALES)
    project = ProjectFactory()
    client.force_authenticate(sales)

    assert client.get(reverse("project-timeline", args=[project.id])).status_code == 200
    blocked = client.post(
        reverse("project-set-waiting", args=[project.id]),
        {"waiting_party": "client"},
        format="json",
    )
    assert blocked.status_code == 403


@pytest.mark.django_db
def test_delivery_cannot_set_waiting_on_foreign_project(client: APIClient) -> None:
    delivery = UserFactory(role=User.Role.DELIVERY)
    project = ProjectFactory()  # delivery não é membro
    client.force_authenticate(delivery)

    response = client.post(
        reverse("project-set-waiting", args=[project.id]),
        {"waiting_party": "client"},
        format="json",
    )
    assert response.status_code in {403, 404}
    assert not PhaseEvent.objects.filter(
        project=project, kind=PhaseEvent.Kind.WAITING_SET
    ).exists()
