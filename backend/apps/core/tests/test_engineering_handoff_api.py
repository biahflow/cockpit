"""API /engineering-handoffs/ (FDD 040): idempotente, fail-closed, escopo de projeto."""

from __future__ import annotations

import urllib.error
from io import BytesIO

import pytest
from django.test import override_settings
from django.urls import reverse
from rest_framework.test import APIClient

from apps.core.github_issues import GitHubIssuesError, IssueDraft, IssueRef
from apps.core.models import EngineeringHandoff, User

from .factories import ProjectFactory, ProjectMemberFactory, UserFactory

CANARY = "ghp_CANARY_TOKEN_DO_NOT_LEAK"

_ON = dict(
    GITHUB_PROVISIONING_ENABLED=True,
    GITHUB_TOKEN="ghp_test",
    GITHUB_REPO="acme/repo",
)


class FakeClient:
    def __init__(
        self,
        *,
        created: IssueRef | None = None,
        error: Exception | None = None,
    ) -> None:
        self.created = created
        self.error = error
        self.create_calls = 0
        self.find_calls = 0

    def find_by_handoff_id(
        self, repository: str, pulse_work_item_id: str
    ) -> IssueRef | None:
        self.find_calls += 1
        return None

    def create_issue(self, draft: IssueDraft) -> IssueRef:
        self.create_calls += 1
        if self.error:
            raise self.error
        assert self.created is not None
        return self.created


@pytest.fixture
def api() -> APIClient:
    return APIClient()


def _payload(project_id: int, **overrides: object) -> dict:
    base: dict = {
        "project": project_id,
        "pulse_work_item_id": "pulse-work-api-1",
        "title": "Provision the engineering issue",
        "objective": "Turn a Pulse handoff into a GitHub Issue.",
        "acceptance_criteria": "Issue exists and the same Pulse id does not create a second one.",
        "context": "Approved by Pulse.",
        "scope_text": "Backend provisioning.",
        "out_of_scope_text": "Webhooks.",
        "repository": "acme/repo",
        "milestone_ref": "M1",
        "adr_refs": ["ADR-0040"],
        "nfr_refs": ["NFR-003"],
        "fdd_refs": ["FDD-040"],
    }
    base.update(overrides)
    return base


def _ref(number: int = 18) -> IssueRef:
    return IssueRef(
        number=number,
        url=f"https://github.com/acme/repo/issues/{number}",
        node_id=f"I_{number}",
        repository="acme/repo",
    )


def _install(monkeypatch: pytest.MonkeyPatch, fake: FakeClient) -> FakeClient:
    monkeypatch.setattr(
        "apps.core.engineering_provisioning.GithubIssuesApi", lambda: fake
    )
    return fake


@pytest.mark.django_db
@override_settings(**_ON)
def test_admin_cria_provisioned(api: APIClient, monkeypatch: pytest.MonkeyPatch) -> None:
    fake = _install(monkeypatch, FakeClient(created=_ref()))
    admin = UserFactory(role=User.Role.ADMIN)
    project = ProjectFactory()
    api.force_authenticate(admin)

    created = api.post(
        reverse("engineeringhandoff-list"), _payload(project.id), format="json"
    )

    assert created.status_code == 201
    assert created.data["status"] == EngineeringHandoff.Status.PROVISIONED
    assert created.data["github_issue_number"] == 18
    assert created.data["github_issue_url"] == "https://github.com/acme/repo/issues/18"
    assert created.data["correlation_id"]
    assert created.data["last_error_code"] == ""
    assert fake.create_calls == 1

    listed = api.get(reverse("engineeringhandoff-list"), {"project": project.id})
    assert listed.status_code == 200
    assert listed.data[0]["github_issue_number"] == 18


@pytest.mark.django_db
@override_settings(**_ON)
def test_mesmo_pulse_id_devolve_200_sem_segunda_issue(
    api: APIClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    fake = _install(monkeypatch, FakeClient(created=_ref()))
    admin = UserFactory(role=User.Role.ADMIN)
    project = ProjectFactory()
    api.force_authenticate(admin)
    url = reverse("engineeringhandoff-list")
    payload = _payload(project.id)

    first = api.post(url, payload, format="json")
    second = api.post(url, payload, format="json")

    assert first.status_code == 201
    assert second.status_code == 200
    assert second.data["id"] == first.data["id"]
    assert fake.create_calls == 1
    assert EngineeringHandoff.objects.filter(pulse_work_item_id="pulse-work-api-1").count() == 1


@pytest.mark.django_db
@override_settings(**_ON)
def test_github_500_persiste_failed_e_retry_provisiona(
    api: APIClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    fake = _install(monkeypatch, FakeClient(error=GitHubIssuesError("GitHub HTTP 500")))
    admin = UserFactory(role=User.Role.ADMIN)
    project = ProjectFactory()
    api.force_authenticate(admin)

    created = api.post(
        reverse("engineeringhandoff-list"), _payload(project.id), format="json"
    )
    assert created.status_code == 201
    assert created.data["status"] == EngineeringHandoff.Status.FAILED
    assert created.data["github_issue_number"] is None
    handoff_id = created.data["id"]

    fake.error = None
    fake.created = _ref(21)
    retried = api.post(reverse("engineeringhandoff-retry", args=[handoff_id]))
    assert retried.status_code == 200
    assert retried.data["status"] == EngineeringHandoff.Status.PROVISIONED
    assert retried.data["github_issue_number"] == 21


@pytest.mark.django_db
@override_settings(GITHUB_PROVISIONING_ENABLED=False, GITHUB_TOKEN="ghp_test", GITHUB_REPO="acme/repo")
def test_flag_off_503_sem_row(api: APIClient, monkeypatch: pytest.MonkeyPatch) -> None:
    fake = _install(monkeypatch, FakeClient(created=_ref()))
    admin = UserFactory(role=User.Role.ADMIN)
    project = ProjectFactory()
    api.force_authenticate(admin)

    response = api.post(
        reverse("engineeringhandoff-list"), _payload(project.id), format="json"
    )
    assert response.status_code == 503
    assert EngineeringHandoff.objects.count() == 0
    assert fake.create_calls == 0


@pytest.mark.django_db
@override_settings(**_ON)
def test_delivery_membro_cria_outsider_e_vendas_nao(
    api: APIClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    _install(monkeypatch, FakeClient(created=_ref()))
    project = ProjectFactory()
    delivery = UserFactory(role=User.Role.DELIVERY)
    ProjectMemberFactory(project=project, user=delivery)
    outsider = UserFactory(role=User.Role.DELIVERY, username="outsider")
    sales = UserFactory(role=User.Role.SALES)
    payload = _payload(project.id)

    api.force_authenticate(delivery)
    created = api.post(reverse("engineeringhandoff-list"), payload, format="json")
    assert created.status_code == 201

    api.force_authenticate(outsider)
    listed = api.get(reverse("engineeringhandoff-list"))
    forbidden = api.post(
        reverse("engineeringhandoff-list"),
        _payload(project.id, pulse_work_item_id="pulse-other"),
        format="json",
    )
    assert listed.data == []
    assert forbidden.status_code == 403

    api.force_authenticate(sales)
    assert api.get(reverse("engineeringhandoff-list")).status_code == 403
    assert api.post(
        reverse("engineeringhandoff-list"),
        _payload(project.id, pulse_work_item_id="pulse-sales"),
        format="json",
    ).status_code == 403


@pytest.mark.django_db
@override_settings(
    GITHUB_PROVISIONING_ENABLED=True,
    GITHUB_TOKEN=CANARY,
    GITHUB_REPO="acme/repo",
)
def test_token_canario_nao_aparece_na_resposta_nem_logs(
    api: APIClient, monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    def fake_urlopen(request: object, timeout: object = None) -> object:
        raise urllib.error.HTTPError(
            "https://api.github.com/repos/acme/repo/issues",
            500,
            "error",
            hdrs=None,
            fp=BytesIO(b'{"message":"boom"}'),
        )

    monkeypatch.setattr("apps.core.github_issues.urllib.request.urlopen", fake_urlopen)
    caplog.set_level("WARNING")
    admin = UserFactory(role=User.Role.ADMIN)
    project = ProjectFactory()
    api.force_authenticate(admin)

    response = api.post(
        reverse("engineeringhandoff-list"), _payload(project.id), format="json"
    )
    assert response.status_code == 201
    assert response.data["status"] == EngineeringHandoff.Status.FAILED
    blob = str(response.data) + caplog.text
    assert CANARY not in blob
    for record in caplog.records:
        assert CANARY not in record.getMessage()


@pytest.mark.django_db
@override_settings(**_ON)
def test_titulo_vazio_e_400(api: APIClient, monkeypatch: pytest.MonkeyPatch) -> None:
    _install(monkeypatch, FakeClient(created=_ref()))
    admin = UserFactory(role=User.Role.ADMIN)
    project = ProjectFactory()
    api.force_authenticate(admin)
    response = api.post(
        reverse("engineeringhandoff-list"),
        _payload(project.id, title=""),
        format="json",
    )
    assert response.status_code == 400
    assert EngineeringHandoff.objects.count() == 0


@pytest.mark.django_db
@override_settings(**_ON)
def test_source_task_de_outro_projeto_e_400(
    api: APIClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    from datetime import timedelta

    from django.utils import timezone

    from apps.core.models import Task

    _install(monkeypatch, FakeClient(created=_ref()))
    admin = UserFactory(role=User.Role.ADMIN)
    projeto = ProjectFactory()
    outro = ProjectFactory()
    tarefa = Task.objects.create(
        project=outro,
        title="Alheia",
        owner=outro.owner,
        due_date=timezone.localdate() + timedelta(days=1),
    )
    api.force_authenticate(admin)
    response = api.post(
        reverse("engineeringhandoff-list"),
        _payload(projeto.id, source_task=tarefa.id),
        format="json",
    )
    assert response.status_code == 400
    assert EngineeringHandoff.objects.count() == 0


@pytest.mark.django_db
@override_settings(**_ON)
def test_pulse_id_nao_muda_depois_de_criado(
    api: APIClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    _install(monkeypatch, FakeClient(created=_ref()))
    admin = UserFactory(role=User.Role.ADMIN)
    project = ProjectFactory()
    api.force_authenticate(admin)
    created = api.post(
        reverse("engineeringhandoff-list"), _payload(project.id), format="json"
    )
    patched = api.patch(
        reverse("engineeringhandoff-detail", args=[created.data["id"]]),
        {"pulse_work_item_id": "pulse-mutado"},
        format="json",
    )
    assert patched.status_code == 400
    handoff = EngineeringHandoff.objects.get(pk=created.data["id"])
    assert handoff.pulse_work_item_id == "pulse-work-api-1"


@pytest.mark.django_db
@override_settings(
    GITHUB_PROVISIONING_ENABLED=False, GITHUB_TOKEN="ghp_test", GITHUB_REPO="acme/repo"
)
def test_retry_flag_off_503(api: APIClient) -> None:
    admin = UserFactory(role=User.Role.ADMIN)
    api.force_authenticate(admin)
    handoff = EngineeringHandoff.objects.create(
        project=ProjectFactory(),
        pulse_work_item_id="pulse-retry-off",
        title="Handoff",
        objective="Obj",
        acceptance_criteria="Aceite",
        status=EngineeringHandoff.Status.FAILED,
    )
    response = api.post(reverse("engineeringhandoff-retry", args=[handoff.id]))
    assert response.status_code == 503
