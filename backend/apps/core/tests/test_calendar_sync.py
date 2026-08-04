import pytest
from django.core.management import call_command
from django.test import override_settings
from django.urls import reverse
from django.utils import timezone
from rest_framework.test import APIClient

from apps.core import calendar_sync
from apps.core.models import Task, User

from .factories import ProjectFactory, UserFactory


def _event(pk: int, project_id: int | None, **overrides) -> dict:
    event: dict = {"id": f"ev-{pk}"}
    if project_id is not None:
        event["summary"] = f"Reunião de acompanhamento #proj-{project_id}"
    else:
        event["summary"] = overrides.pop("summary", "Reunião sem projeto")
    event["start"] = overrides.pop("start", {"date": timezone.localdate().isoformat()})
    event.update(overrides)
    return event


# --- event_to_taskspec (puro) ---------------------------------------------------------------

def test_taskspec_extracts_marker_from_summary() -> None:
    spec = calendar_sync.event_to_taskspec(_event(1, 42))
    assert spec is not None
    assert spec["project_id"] == 42
    assert spec["external_id"] == "ev-1"
    assert "#proj-42" not in spec["title"]
    assert spec["due_date"] == timezone.localdate()


def test_taskspec_extracts_marker_from_description() -> None:
    event = _event(2, None, summary="Call", description="pauta no #proj-7")
    spec = calendar_sync.event_to_taskspec(event)
    assert spec is not None and spec["project_id"] == 7


def test_taskspec_parses_timed_event() -> None:
    when = f"{timezone.localdate().isoformat()}T14:30:00-03:00"
    spec = calendar_sync.event_to_taskspec(_event(3, 5, start={"dateTime": when}))
    assert spec is not None
    assert spec["due_date"] == timezone.localdate()


def test_taskspec_skips_biahflow_origin() -> None:
    event = _event(4, 5, extendedProperties={"private": {calendar_sync.ORIGIN_KEY: "task:9"}})
    assert calendar_sync.event_to_taskspec(event) is None


def test_taskspec_skips_without_marker() -> None:
    assert calendar_sync.event_to_taskspec(_event(5, None)) is None


def test_taskspec_skips_without_date() -> None:
    assert calendar_sync.event_to_taskspec(_event(6, 5, start={})) is None


def test_taskspec_skips_without_id() -> None:
    event = _event(7, 5)
    del event["id"]
    assert calendar_sync.event_to_taskspec(event) is None


# --- sync_calendar (orquestração) -----------------------------------------------------------

@pytest.mark.django_db
@override_settings(CALENDAR_ENABLED=True, GOOGLE_CALENDAR_ID="cal")
def test_sync_creates_task_for_marked_event(monkeypatch) -> None:
    project = ProjectFactory()
    monkeypatch.setattr(calendar_sync, "list_events", lambda *a: [_event(1, project.id)])

    created, skipped = calendar_sync.sync_calendar()

    assert (created, skipped) == (1, 0)
    task = Task.objects.get(source="calendar", external_id="ev-1")
    assert task.project_id == project.id
    assert task.owner_id == project.owner_id
    assert task.due_date == timezone.localdate()


@pytest.mark.django_db
@override_settings(CALENDAR_ENABLED=True, GOOGLE_CALENDAR_ID="cal")
def test_sync_is_idempotent(monkeypatch) -> None:
    project = ProjectFactory()
    monkeypatch.setattr(calendar_sync, "list_events", lambda *a: [_event(1, project.id)])

    assert calendar_sync.sync_calendar() == (1, 0)
    assert calendar_sync.sync_calendar() == (0, 1)
    assert Task.objects.filter(source="calendar", external_id="ev-1").count() == 1


@pytest.mark.django_db
@override_settings(CALENDAR_ENABLED=True, GOOGLE_CALENDAR_ID="cal")
def test_sync_skips_unknown_and_archived_project(monkeypatch) -> None:
    archived = ProjectFactory()
    archived.archive()
    events = [_event(1, 999999), _event(2, archived.id)]
    monkeypatch.setattr(calendar_sync, "list_events", lambda *a: events)

    assert calendar_sync.sync_calendar() == (0, 2)
    assert not Task.objects.filter(source="calendar").exists()


@pytest.mark.django_db
@override_settings(CALENDAR_ENABLED=False)
def test_sync_noop_when_disabled(monkeypatch) -> None:
    called = False

    def _boom(*a):  # pragma: no cover - não deve ser chamado
        nonlocal called
        called = True
        return []

    monkeypatch.setattr(calendar_sync, "list_events", _boom)
    assert calendar_sync.sync_calendar() == (0, 0)
    assert called is False


@pytest.mark.django_db
@override_settings(CALENDAR_ENABLED=True, GOOGLE_CALENDAR_ID="cal")
def test_sync_command_prints_counts(monkeypatch, capsys) -> None:
    project = ProjectFactory()
    monkeypatch.setattr(calendar_sync, "list_events", lambda *a: [_event(1, project.id)])

    call_command("sync_calendar")

    assert "Tarefas criadas: 1" in capsys.readouterr().out


# --- CalendarSyncView (endpoint admin) ------------------------------------------------------

@pytest.mark.django_db
@override_settings(CALENDAR_ENABLED=True, GOOGLE_CALENDAR_ID="cal")
def test_sync_endpoint_admin_runs(monkeypatch) -> None:
    project = ProjectFactory()
    monkeypatch.setattr(calendar_sync, "list_events", lambda *a: [_event(1, project.id)])
    client = APIClient()
    client.force_authenticate(UserFactory(role=User.Role.ADMIN))

    resp = client.post(reverse("config-sync-calendar"))

    assert resp.status_code == 200
    assert resp.json() == {"created": 1, "skipped": 0}


@pytest.mark.django_db
def test_sync_endpoint_forbidden_for_non_admin() -> None:
    client = APIClient()
    client.force_authenticate(UserFactory(role=User.Role.DELIVERY))
    assert client.post(reverse("config-sync-calendar")).status_code == 403


@pytest.mark.django_db
@override_settings(CALENDAR_ENABLED=False)
def test_sync_endpoint_503_when_disabled() -> None:
    client = APIClient()
    client.force_authenticate(UserFactory(role=User.Role.ADMIN))
    assert client.post(reverse("config-sync-calendar")).status_code == 503
