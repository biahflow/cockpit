"""Orquestração do provisionamento GitHub (FDD 040): idempotente e fail-closed."""

from __future__ import annotations

import pytest
from django.test import override_settings

from apps.core.engineering_provisioning import provision
from apps.core.github_issues import GitHubIssuesError, IssueDraft, IssueRef
from apps.core.models import EngineeringHandoff

from .factories import EngineeringHandoffFactory

CANARY = "ghp_CANARY_TOKEN_DO_NOT_LEAK"


class FakeClient:
    def __init__(
        self,
        *,
        found: IssueRef | None = None,
        created: IssueRef | None = None,
        error: Exception | None = None,
    ) -> None:
        self.found = found
        self.created = created
        self.error = error
        self.create_calls = 0
        self.find_calls = 0

    def find_by_handoff_id(
        self, repository: str, pulse_work_item_id: str
    ) -> IssueRef | None:
        self.find_calls += 1
        return self.found

    def create_issue(self, draft: IssueDraft) -> IssueRef:
        self.create_calls += 1
        if self.error:
            raise self.error
        assert self.created is not None
        return self.created


def _ref(number: int = 42) -> IssueRef:
    return IssueRef(
        number=number,
        url=f"https://github.com/acme/repo/issues/{number}",
        node_id=f"I_{number}",
        repository="acme/repo",
    )


_ON = dict(
    GITHUB_PROVISIONING_ENABLED=True,
    GITHUB_TOKEN="ghp_test",
    GITHUB_REPO="acme/repo",
)


@pytest.mark.django_db
@override_settings(**_ON)
def test_sucesso_create() -> None:
    handoff = EngineeringHandoffFactory()
    client = FakeClient(created=_ref())
    result = provision(handoff, client=client)
    result.refresh_from_db()
    assert result.status == EngineeringHandoff.Status.PROVISIONED
    assert result.github_issue_number == 42
    assert result.github_issue_url.endswith("/issues/42")
    assert result.github_node_id == "I_42"
    assert result.repository == "acme/repo"
    assert result.last_error_code == ""
    assert result.attempt_count == 1
    assert client.create_calls == 1
    assert client.find_calls == 1


@pytest.mark.django_db
@override_settings(**_ON)
def test_ja_provisioned_nao_chama_create() -> None:
    handoff = EngineeringHandoffFactory(
        status=EngineeringHandoff.Status.PROVISIONED,
        github_issue_number=9,
        github_issue_url="https://github.com/acme/repo/issues/9",
        repository="acme/repo",
    )
    client = FakeClient(created=_ref(99))
    result = provision(handoff, client=client)
    assert result.github_issue_number == 9
    assert client.create_calls == 0
    assert client.find_calls == 0


@pytest.mark.django_db
@override_settings(**_ON)
def test_find_reconcilia_janela_201_sem_persistir() -> None:
    """Pending sem number: a busca acha a Issue e create NÃO é chamado."""
    handoff = EngineeringHandoffFactory()
    client = FakeClient(found=_ref(7), created=_ref(99))
    result = provision(handoff, client=client)
    result.refresh_from_db()
    assert result.status == EngineeringHandoff.Status.PROVISIONED
    assert result.github_issue_number == 7
    assert client.create_calls == 0
    assert client.find_calls == 1


@pytest.mark.django_db
@override_settings(**_ON)
def test_erro_remoto_failed_depois_retry_provisioned() -> None:
    handoff = EngineeringHandoffFactory()
    failing = FakeClient(error=GitHubIssuesError("GitHub HTTP 500 for https://api.github.com"))
    failed = provision(handoff, client=failing)
    failed.refresh_from_db()
    assert failed.status == EngineeringHandoff.Status.FAILED
    assert failed.github_issue_number is None
    assert failed.last_error_code == "github_http"
    assert failed.attempt_count == 1

    ok = FakeClient(created=_ref(3))
    result = provision(failed, client=ok)
    result.refresh_from_db()
    assert result.status == EngineeringHandoff.Status.PROVISIONED
    assert result.github_issue_number == 3
    assert result.last_error_code == ""
    assert result.attempt_count == 2


@pytest.mark.django_db
@override_settings(
    GITHUB_PROVISIONING_ENABLED=False, GITHUB_TOKEN="ghp_test", GITHUB_REPO="acme/repo"
)
def test_flag_off_failed_disabled_sem_http() -> None:
    handoff = EngineeringHandoffFactory()
    client = FakeClient(created=_ref())
    result = provision(handoff, client=client)
    result.refresh_from_db()
    assert result.status == EngineeringHandoff.Status.FAILED
    assert result.last_error_code == "disabled"
    assert result.github_issue_number is None
    assert client.create_calls == 0
    assert client.find_calls == 0


@pytest.mark.django_db
@override_settings(
    GITHUB_PROVISIONING_ENABLED=True, GITHUB_TOKEN="ghp_test", GITHUB_REPO="   "
)
def test_repo_em_branco_failed_missing_repo() -> None:
    handoff = EngineeringHandoffFactory(repository="")
    client = FakeClient(created=_ref())
    result = provision(handoff, client=client)
    result.refresh_from_db()
    assert result.status == EngineeringHandoff.Status.FAILED
    assert result.last_error_code == "missing_repo"
    assert client.create_calls == 0


@pytest.mark.django_db
@override_settings(**_ON)
def test_refs_nao_lista_viram_lista_vazia() -> None:
    handoff = EngineeringHandoffFactory(adr_refs="nope", nfr_refs={"x": 1}, fdd_refs=["FDD-040"])
    client = FakeClient(created=_ref())
    result = provision(handoff, client=client)
    assert result.status == EngineeringHandoff.Status.PROVISIONED
    assert client.create_calls == 1


@pytest.mark.django_db
@override_settings(**_ON)
def test_client_default_usa_github_api(monkeypatch: pytest.MonkeyPatch) -> None:
    fake = FakeClient(created=_ref(5))
    monkeypatch.setattr(
        "apps.core.engineering_provisioning.GithubIssuesApi", lambda: fake
    )
    handoff = EngineeringHandoffFactory()
    result = provision(handoff)
    result.refresh_from_db()
    assert result.github_issue_number == 5
    assert fake.create_calls == 1


@pytest.mark.django_db
@override_settings(**_ON)
def test_last_error_message_nao_guarda_token() -> None:
    handoff = EngineeringHandoffFactory()
    leaking = FakeClient(
        error=GitHubIssuesError(f"Bearer {CANARY} rejected by GitHub")
    )
    result = provision(handoff, client=leaking)
    result.refresh_from_db()
    assert CANARY not in result.last_error_message
    assert "Bearer" in result.last_error_message
