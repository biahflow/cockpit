from datetime import timedelta

import pytest
from django.test import override_settings
from django.urls import reverse
from django.utils import timezone
from rest_framework.test import APIClient

from apps.core import tasksync
from apps.core.models import Notification, Task, User

from .factories import ProjectFactory, UserFactory


def _task(project, source="linear", external_id="ENG-1", status=Task.Status.TODO) -> Task:
    return Task.objects.create(
        project=project,
        title="Tarefa",
        owner=project.owner,
        due_date=timezone.localdate() + timedelta(days=5),
        status=status,
        source=source,
        external_id=external_id,
    )


# --- de-para de status -------------------------------------------------------


def test_inbound_status_mapping() -> None:
    assert tasksync.inbound_status("github", "closed") == Task.Status.DONE
    assert tasksync.inbound_status("github", "open") == Task.Status.TODO
    assert tasksync.inbound_status("linear", "started") == Task.Status.IN_PROGRESS
    assert tasksync.inbound_status("linear", "completed") == Task.Status.DONE
    assert tasksync.inbound_status("linear", "desconhecido") is None


@override_settings(LINEAR_STATE_DONE="state-done", LINEAR_STATE_TODO="state-todo")
def test_outbound_state_mapping() -> None:
    assert tasksync.outbound_state("github", Task.Status.DONE) == "closed"
    assert tasksync.outbound_state("github", Task.Status.TODO) == "open"
    assert tasksync.outbound_state("linear", Task.Status.DONE) == "state-done"
    assert tasksync.outbound_state("linear", Task.Status.TODO) == "state-todo"


@pytest.mark.django_db
def test_eligible_only_for_linked_provider_tasks() -> None:
    project = ProjectFactory()
    assert tasksync.eligible(_task(project)) is True
    native = Task.objects.create(
        project=project, title="nativa", owner=project.owner, due_date=timezone.localdate()
    )
    assert tasksync.eligible(native) is False  # source=biahflow, sem external_id


# --- entrada -----------------------------------------------------------------


@pytest.mark.django_db
def test_apply_inbound_updates_linked_task() -> None:
    project = ProjectFactory()
    task = _task(project, external_id="ENG-9", status=Task.Status.TODO)
    result = tasksync.apply_inbound("linear", "ENG-9", "completed")
    task.refresh_from_db()
    assert result == task
    assert task.status == Task.Status.DONE
    assert task.completed_at is not None


def _notificacoes_de_atualizacao(user) -> list[Notification]:  # type: ignore[no-untyped-def]
    """Só as da sincronia — criar a tarefa já dispara a sua própria notificação (`signals.py`)."""
    return list(Notification.objects.filter(user=user, message__startswith="Tarefa atualizada"))


@pytest.mark.django_db
def test_apply_inbound_notifies_the_owner() -> None:
    """O efeito colateral que ninguém cobria — e onde morava o vazamento (FDD 010, FDD 018)."""
    project = ProjectFactory()
    task = _task(project, external_id="ENG-11", status=Task.Status.TODO)

    tasksync.apply_inbound("linear", "ENG-11", "completed")

    notificacoes = _notificacoes_de_atualizacao(task.owner)
    assert len(notificacoes) == 1
    assert "via linear" in notificacoes[0].message
    assert notificacoes[0].url == f"/projetos/{project.id}"


@pytest.mark.django_db
def test_apply_inbound_nao_notifica_quando_o_status_nao_muda() -> None:
    project = ProjectFactory()
    task = _task(project, external_id="ENG-12", status=Task.Status.DONE)

    tasksync.apply_inbound("linear", "ENG-12", "completed")

    assert _notificacoes_de_atualizacao(task.owner) == []


@pytest.mark.django_db
def test_apply_inbound_returns_none_without_link() -> None:
    assert tasksync.apply_inbound("github", "999", "closed") is None


@pytest.mark.django_db
def test_apply_inbound_raises_on_unknown_status() -> None:
    project = ProjectFactory()
    _task(project, source="github", external_id="7")
    with pytest.raises(ValueError):
        tasksync.apply_inbound("github", "7", "banana")


@pytest.mark.django_db
def test_apply_inbound_does_not_trigger_outbound(monkeypatch: pytest.MonkeyPatch) -> None:
    """Guard de eco: aplicar a entrada não repropaga para o fornecedor."""
    project = ProjectFactory()
    _task(project, external_id="ENG-3", status=Task.Status.TODO)
    calls: list = []
    monkeypatch.setattr(tasksync, "push_update", lambda task: calls.append(task))
    with override_settings(TASKSYNC_ENABLED=True, TASKSYNC_TOKEN="t", GITHUB_TOKEN="gh"):
        tasksync.apply_inbound("linear", "ENG-3", "started")
    assert calls == []


@pytest.mark.django_db
def test_saving_linked_task_triggers_outbound(monkeypatch: pytest.MonkeyPatch) -> None:
    calls: list = []
    monkeypatch.setattr(tasksync, "push_update", lambda task: calls.append(task))
    project = ProjectFactory()
    task = _task(project, source="github", external_id="42")
    assert task in calls  # o post_save chama a saída (sem guard ativo)


# --- saída (agendamento) -----------------------------------------------------


@pytest.mark.django_db
def test_push_update_schedules_delivery_when_configured(monkeypatch: pytest.MonkeyPatch) -> None:
    project = ProjectFactory()
    task = _task(project, source="github", external_id="42", status=Task.Status.DONE)

    updated: dict[str, object] = {}

    def fake_update(source: str, external_id: str, state: str) -> None:
        updated.update(source=source, external_id=external_id, state=state)

    class FakeThread:
        def __init__(self, target, args, daemon):  # type: ignore[no-untyped-def]
            self._target, self._args = target, args

        def start(self) -> None:
            self._target(*self._args)

    callbacks: list = []
    monkeypatch.setattr(tasksync, "_update_issue", fake_update)
    monkeypatch.setattr(tasksync.threading, "Thread", FakeThread)
    monkeypatch.setattr(tasksync.transaction, "on_commit", lambda fn: callbacks.append(fn))

    with override_settings(TASKSYNC_ENABLED=True, TASKSYNC_TOKEN="t", GITHUB_TOKEN="gh"):
        tasksync.push_update(task)

    assert len(callbacks) == 1
    callbacks[0]()
    assert updated == {"source": "github", "external_id": "42", "state": "closed"}


@pytest.mark.django_db
def test_push_update_noop_when_disabled(monkeypatch: pytest.MonkeyPatch) -> None:
    project = ProjectFactory()
    task = _task(project, source="github", external_id="42")
    callbacks: list = []
    monkeypatch.setattr(tasksync.transaction, "on_commit", lambda fn: callbacks.append(fn))
    with override_settings(TASKSYNC_ENABLED=False):
        tasksync.push_update(task)
    assert callbacks == []


# --- endpoint de entrada -----------------------------------------------------


@pytest.mark.django_db
@override_settings(TASKSYNC_TOKEN="sync-token")
def test_intake_requires_token_and_updates_task() -> None:
    project = ProjectFactory()
    task = _task(project, source="github", external_id="7", status=Task.Status.TODO)
    client = APIClient()
    url = reverse("task-sync")
    payload = {"source": "github", "external_id": "7", "external_status": "closed"}
    assert client.post(url, payload, format="json").status_code == 401
    ok = client.post(url, payload, format="json", HTTP_X_SYNC_TOKEN="sync-token")
    assert ok.status_code == 200
    task.refresh_from_db()
    assert task.status == Task.Status.DONE


@pytest.mark.django_db
@override_settings(TASKSYNC_TOKEN="sync-token")
def test_intake_404_when_no_linked_task() -> None:
    client = APIClient()
    r = client.post(
        reverse("task-sync"),
        {"source": "github", "external_id": "nope", "external_status": "closed"},
        format="json",
        HTTP_X_SYNC_TOKEN="sync-token",
    )
    assert r.status_code == 404


@pytest.mark.django_db
@override_settings(TASKSYNC_TOKEN="sync-token")
def test_intake_422_on_unknown_status() -> None:
    project = ProjectFactory()
    _task(project, source="github", external_id="8")
    client = APIClient()
    r = client.post(
        reverse("task-sync"),
        {"source": "github", "external_id": "8", "external_status": "weird"},
        format="json",
        HTTP_X_SYNC_TOKEN="sync-token",
    )
    assert r.status_code == 422


# --- ações de vínculo --------------------------------------------------------


@pytest.mark.django_db
def test_link_external_binds_and_conflicts_on_duplicate() -> None:
    admin = UserFactory(role=User.Role.ADMIN)
    project = ProjectFactory()
    t1 = Task.objects.create(
        project=project, title="a", owner=project.owner, due_date=timezone.localdate()
    )
    t2 = Task.objects.create(
        project=project, title="b", owner=project.owner, due_date=timezone.localdate()
    )
    client = APIClient()
    client.force_authenticate(admin)
    body = {"source": "linear", "external_id": "ENG-1"}
    ok = client.post(reverse("task-link-external", args=[t1.pk]), body, format="json")
    assert ok.status_code == 200
    t1.refresh_from_db()
    assert t1.source == "linear" and t1.external_id == "ENG-1"
    dup = client.post(reverse("task-link-external", args=[t2.pk]), body, format="json")
    assert dup.status_code == 409


@pytest.mark.django_db
def test_push_external_creates_and_links(monkeypatch: pytest.MonkeyPatch) -> None:
    admin = UserFactory(role=User.Role.ADMIN)
    project = ProjectFactory()
    task = Task.objects.create(
        project=project, title="a", owner=project.owner, due_date=timezone.localdate()
    )
    monkeypatch.setattr(tasksync, "push_create", lambda t: "NEW-99")
    client = APIClient()
    client.force_authenticate(admin)
    with override_settings(TASKSYNC_ENABLED=True, TASKSYNC_TOKEN="t", GITHUB_TOKEN="gh"):
        r = client.post(
            reverse("task-push-external", args=[task.pk]), {"source": "github"}, format="json"
        )
    assert r.status_code == 201
    task.refresh_from_db()
    assert task.external_id == "NEW-99" and task.source == "github"


@pytest.mark.django_db
def test_push_external_503_when_disabled() -> None:
    admin = UserFactory(role=User.Role.ADMIN)
    project = ProjectFactory()
    task = Task.objects.create(
        project=project, title="a", owner=project.owner, due_date=timezone.localdate()
    )
    client = APIClient()
    client.force_authenticate(admin)
    with override_settings(TASKSYNC_ENABLED=False):
        r = client.post(
            reverse("task-push-external", args=[task.pk]), {"source": "github"}, format="json"
        )
    assert r.status_code == 503
