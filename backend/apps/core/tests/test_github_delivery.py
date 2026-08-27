"""Projeção de entrega GitHub (FDD 041): parsing, idempotência, out-of-order e reconciliação.

Tudo determinístico e sem LLM. O I/O é injetado por um cliente fake; a lógica pura é testada
diretamente. Cobre os estados degradados exigidos: unavailable, permission_denied, reference_missing
e stale, distintos de um estado confirmado.
"""

from __future__ import annotations

import hashlib
import hmac
import urllib.error
from datetime import timedelta

import pytest
from django.test import override_settings
from django.utils import timezone

from apps.core import github_delivery as gd
from apps.core.github_issues import GitHubIssuesError
from apps.core.models import GithubDeliveryProjection, GithubWebhookDelivery

from .factories import GithubDeliveryProjectionFactory

_ON = dict(
    GITHUB_DELIVERY_ENABLED=True,
    GITHUB_TOKEN="ghp_test",
    GITHUB_WEBHOOK_SECRET="whsec_test",
)

_PStatus = GithubDeliveryProjection.ProjectionStatus
_IState = GithubDeliveryProjection.IssueState
_PState = GithubDeliveryProjection.PullState
_RState = GithubDeliveryProjection.ReviewState
_CiState = GithubDeliveryProjection.CiState


# --- Assinatura --------------------------------------------------------------


@override_settings(GITHUB_WEBHOOK_SECRET="whsec_test")
def test_verify_signature_valida_e_recusa() -> None:
    body = b'{"hello":"world"}'
    good = "sha256=" + hmac.new(b"whsec_test", body, hashlib.sha256).hexdigest()
    assert gd.verify_signature(body, {"X-Hub-Signature-256": good}) is True
    assert gd.verify_signature(body, {"X-Hub-Signature-256": "sha256=deadbeef"}) is False
    assert gd.verify_signature(body, {"X-Hub-Signature-256": "sha1=abc"}) is False
    assert gd.verify_signature(body, {}) is False


@override_settings(GITHUB_WEBHOOK_SECRET="")
def test_verify_signature_sem_segredo_recusa() -> None:
    assert gd.verify_signature(b"x", {"X-Hub-Signature-256": "sha256=abc"}) is False


# --- Parsing -----------------------------------------------------------------


def test_parse_tipo_desconhecido_e_none() -> None:
    assert gd.parse_event("push", "d1", {"repository": {"full_name": "a/b"}}) is None


def test_parse_issues() -> None:
    event = gd.parse_event(
        "issues",
        "d1",
        {
            "repository": {"full_name": "acme/repo"},
            "issue": {
                "number": 7,
                "state": "closed",
                "html_url": "https://github.com/acme/repo/issues/7",
                "updated_at": "2026-08-27T10:00:00Z",
            },
        },
    )
    assert event is not None
    assert event.issue_number == 7
    assert event.issue_state == _IState.CLOSED
    assert event.occurred_at is not None


def test_parse_issues_incompleto_e_none() -> None:
    assert gd.parse_event("issues", "d1", {"repository": {"full_name": "a/b"}}) is None
    assert gd.parse_event("issues", "d1", {"issue": {"number": 1}}) is None


def test_parse_pull_request_liga_por_closes() -> None:
    event = gd.parse_event(
        "pull_request",
        "d2",
        {
            "repository": {"full_name": "acme/repo"},
            "pull_request": {
                "number": 42,
                "state": "open",
                "draft": False,
                "merged": False,
                "body": "Implements the thing. Closes #7",
                "html_url": "https://github.com/acme/repo/pull/42",
                "updated_at": "2026-08-27T11:00:00Z",
                "head": {"sha": "abc123", "ref": "feature/x"},
            },
        },
    )
    assert event is not None
    assert event.issue_number == 7  # ligado pela âncora, sem LLM
    assert event.pr_number == 42
    assert event.pr_state == _PState.OPEN
    assert event.head_sha == "abc123"
    assert event.head_ref == "feature/x"


def test_parse_pull_request_merged_e_draft() -> None:
    def pr_state(**pr: object) -> str | None:
        event = gd.parse_event(
            "pull_request",
            "d",
            {"repository": {"full_name": "a/b"}, "pull_request": {"number": 1, **pr}},
        )
        assert event is not None
        return event.pr_state

    assert pr_state(state="closed", merged=True) == _PState.MERGED
    assert pr_state(state="open", draft=True) == _PState.DRAFT
    assert pr_state(state="closed") == _PState.CLOSED
    assert pr_state(state="weird") is None


def test_parse_review_so_aprovado_ou_mudancas() -> None:
    def review(state: str) -> gd.DeliveryEvent | None:
        return gd.parse_event(
            "pull_request_review",
            "d",
            {
                "repository": {"full_name": "a/b"},
                "review": {"state": state, "submitted_at": "2026-08-27T12:00:00Z"},
                "pull_request": {"number": 5, "head": {"sha": "s"}},
            },
        )

    assert review("approved").review_state == _RState.APPROVED  # type: ignore[union-attr]
    assert review("changes_requested").review_state == _RState.CHANGES_REQUESTED  # type: ignore[union-attr]
    assert review("commented") is None  # não move a projeção


def test_parse_check_suite_e_status() -> None:
    suite = gd.parse_event(
        "check_suite",
        "d",
        {
            "repository": {"full_name": "a/b"},
            "check_suite": {"head_sha": "sha1", "status": "completed", "conclusion": "success"},
        },
    )
    assert suite is not None and suite.ci_state == _CiState.SUCCESS and suite.head_sha == "sha1"

    failing = gd.parse_event(
        "status",
        "d",
        {"repository": {"full_name": "a/b"}, "sha": "sha2", "state": "failure"},
    )
    assert failing is not None and failing.ci_state == _CiState.FAILURE


def test_ci_state_mapa() -> None:
    assert gd._ci_state("in_progress", None) == _CiState.PENDING
    assert gd._ci_state("completed", "success") == _CiState.SUCCESS
    assert gd._ci_state("completed", "timed_out") == _CiState.FAILURE
    assert gd._ci_state("completed", "neutral") == _CiState.PENDING


# --- apply_event -------------------------------------------------------------


@pytest.mark.django_db
def test_apply_resolve_por_issue_e_confirma() -> None:
    GithubDeliveryProjectionFactory(repository="acme/repo", issue_number=7)
    event = gd.parse_event(
        "issues",
        "d1",
        {
            "repository": {"full_name": "acme/repo"},
            "issue": {"number": 7, "state": "open", "updated_at": "2026-08-27T10:00:00Z"},
        },
    )
    applied = gd.apply_event(event)  # type: ignore[arg-type]
    assert applied is not None
    assert applied.projection_status == _PStatus.CURRENT
    assert applied.issue_state == _IState.OPEN
    assert applied.observed_at is not None


@pytest.mark.django_db
def test_apply_sem_projecao_correspondente_e_none() -> None:
    event = gd.parse_event(
        "issues",
        "d1",
        {"repository": {"full_name": "acme/repo"}, "issue": {"number": 999, "state": "open"}},
    )
    assert gd.apply_event(event) is None  # type: ignore[arg-type]


@pytest.mark.django_db
def test_apply_pull_liga_pr_a_projecao_da_issue() -> None:
    projection = GithubDeliveryProjectionFactory(repository="acme/repo", issue_number=7)
    event = gd.parse_event(
        "pull_request",
        "d2",
        {
            "repository": {"full_name": "acme/repo"},
            "pull_request": {
                "number": 42,
                "state": "open",
                "body": "Closes #7",
                "head": {"sha": "abc", "ref": "f/x"},
                "updated_at": "2026-08-27T11:00:00Z",
            },
        },
    )
    gd.apply_event(event)  # type: ignore[arg-type]
    projection.refresh_from_db()
    assert projection.pr_number == 42
    assert projection.pr_state == _PState.OPEN
    assert projection.head_sha == "abc"


@pytest.mark.django_db
def test_apply_out_of_order_nao_regride() -> None:
    projection = GithubDeliveryProjectionFactory(repository="acme/repo", issue_number=7)
    novo = {
        "repository": {"full_name": "acme/repo"},
        "issue": {"number": 7, "state": "closed", "updated_at": "2026-08-27T12:00:00Z"},
    }
    velho = {
        "repository": {"full_name": "acme/repo"},
        "issue": {"number": 7, "state": "open", "updated_at": "2026-08-27T09:00:00Z"},
    }
    gd.apply_event(gd.parse_event("issues", "d-new", novo))  # type: ignore[arg-type]
    gd.apply_event(gd.parse_event("issues", "d-old", velho))  # type: ignore[arg-type]
    projection.refresh_from_db()
    assert projection.issue_state == _IState.CLOSED  # o evento velho não sobrescreveu


@pytest.mark.django_db
def test_apply_sha_novo_zera_ci() -> None:
    projection = GithubDeliveryProjectionFactory(repository="acme/repo", issue_number=7)
    projection.pr_number = 42
    projection.head_sha = "old_sha"
    projection.ci_state = _CiState.SUCCESS
    projection.save()
    event = gd.parse_event(
        "pull_request",
        "d3",
        {
            "repository": {"full_name": "acme/repo"},
            "pull_request": {
                "number": 42,
                "state": "open",
                "head": {"sha": "new_sha", "ref": "f/x"},
                "updated_at": "2026-08-27T13:00:00Z",
            },
        },
    )
    gd.apply_event(event)  # type: ignore[arg-type]
    projection.refresh_from_db()
    assert projection.head_sha == "new_sha"
    assert projection.ci_state == _CiState.UNKNOWN  # verde do commit velho não vale para o novo


# --- ingest (inbox idempotente) ----------------------------------------------


@pytest.mark.django_db
def test_ingest_aplica_e_deduplica() -> None:
    projection = GithubDeliveryProjectionFactory(repository="acme/repo", issue_number=7)
    payload = {
        "repository": {"full_name": "acme/repo"},
        "issue": {"number": 7, "state": "closed", "updated_at": "2026-08-27T10:00:00Z"},
    }
    outcome1, p1 = gd.ingest("issues", "delivery-1", payload)
    outcome2, p2 = gd.ingest("issues", "delivery-1", payload)  # reentrega literal
    assert outcome1 == "applied"
    assert outcome2 == "duplicate"
    assert p1 is not None and p2 is not None and p1.pk == p2.pk == projection.pk
    assert GithubWebhookDelivery.objects.filter(delivery_id="delivery-1").count() == 1


@pytest.mark.django_db
def test_ingest_evento_ignorado_e_invalido() -> None:
    assert gd.ingest("push", "d", {"repository": {"full_name": "a/b"}}) == ("ignored", None)
    assert gd.ingest("issues", "", {}) == ("invalid", None)


@pytest.mark.django_db
def test_ingest_evento_sem_projecao_e_ignorado() -> None:
    payload = {
        "repository": {"full_name": "acme/repo"},
        "issue": {"number": 404, "state": "open"},
    }
    assert gd.ingest("issues", "d-unmapped", payload) == ("ignored", None)


# --- Reconciliação -----------------------------------------------------------


class FakeReadClient:
    def __init__(
        self,
        *,
        issue: gd.FetchedIssue | None = None,
        pull: gd.FetchedPull | None = None,
        ci: str = _CiState.SUCCESS,
        issue_error: Exception | None = None,
    ) -> None:
        self.issue = issue or gd.FetchedIssue(state=_IState.OPEN, url="https://gh/issue")
        self.pull = pull
        self.ci = ci
        self.issue_error = issue_error

    def fetch_issue(self, repository: str, issue_number: int) -> gd.FetchedIssue:
        if self.issue_error:
            raise self.issue_error
        return self.issue

    def fetch_pull_request(self, repository: str, pr_number: int) -> gd.FetchedPull:
        assert self.pull is not None
        return self.pull

    def fetch_check_state(self, repository: str, head_sha: str) -> str:
        return self.ci


def _http_error(code: int) -> GitHubIssuesError:
    exc = GitHubIssuesError(f"GitHub HTTP {code}")
    exc.__cause__ = urllib.error.HTTPError("http://x", code, "err", None, None)  # type: ignore[arg-type]
    return exc


@pytest.mark.django_db
@override_settings(**_ON)
def test_reconcile_confirma_issue() -> None:
    projection = GithubDeliveryProjectionFactory()
    gd.reconcile(projection, client=FakeReadClient())
    projection.refresh_from_db()
    assert projection.projection_status == _PStatus.CURRENT
    assert projection.issue_state == _IState.OPEN
    assert projection.observed_at is not None


@pytest.mark.django_db
@override_settings(**_ON)
def test_reconcile_com_pr_e_ci() -> None:
    projection = GithubDeliveryProjectionFactory()
    projection.pr_number = 42
    projection.save()
    client = FakeReadClient(
        pull=gd.FetchedPull(state=_PState.OPEN, url="https://gh/pr", head_sha="sha", head_ref="f"),
        ci=_CiState.FAILURE,
    )
    gd.reconcile(projection, client=client)
    projection.refresh_from_db()
    assert projection.pr_state == _PState.OPEN
    assert projection.head_sha == "sha"
    assert projection.ci_state == _CiState.FAILURE


@pytest.mark.django_db
@override_settings(**_ON)
def test_reconcile_404_reference_missing() -> None:
    projection = GithubDeliveryProjectionFactory()
    gd.reconcile(projection, client=FakeReadClient(issue_error=_http_error(404)))
    projection.refresh_from_db()
    assert projection.projection_status == _PStatus.REFERENCE_MISSING
    assert projection.last_error_code == "not_found"


@pytest.mark.django_db
@override_settings(**_ON)
def test_reconcile_403_permission_denied() -> None:
    projection = GithubDeliveryProjectionFactory()
    gd.reconcile(projection, client=FakeReadClient(issue_error=_http_error(403)))
    projection.refresh_from_db()
    assert projection.projection_status == _PStatus.PERMISSION_DENIED


@pytest.mark.django_db
@override_settings(**_ON)
def test_reconcile_500_unavailable() -> None:
    projection = GithubDeliveryProjectionFactory()
    gd.reconcile(projection, client=FakeReadClient(issue_error=_http_error(500)))
    projection.refresh_from_db()
    assert projection.projection_status == _PStatus.UNAVAILABLE


@pytest.mark.django_db
@override_settings(GITHUB_DELIVERY_ENABLED=False)
def test_reconcile_desligado_unavailable() -> None:
    projection = GithubDeliveryProjectionFactory()
    gd.reconcile(projection, client=FakeReadClient())
    projection.refresh_from_db()
    assert projection.projection_status == _PStatus.UNAVAILABLE
    assert projection.last_error_code == "disabled"


@pytest.mark.django_db
@override_settings(**_ON)
def test_reconcile_degradado_preserva_observed_at_anterior() -> None:
    projection = GithubDeliveryProjectionFactory()
    gd.reconcile(projection, client=FakeReadClient())  # confirma
    projection.refresh_from_db()
    bom = projection.observed_at
    gd.reconcile(projection, client=FakeReadClient(issue_error=_http_error(500)))
    projection.refresh_from_db()
    assert projection.observed_at == bom  # a última confirmação boa é preservada
    assert projection.projection_status == _PStatus.UNAVAILABLE


# --- display_state / frescor -------------------------------------------------


@pytest.mark.django_db
def test_display_state_pending_current_stale() -> None:
    projection = GithubDeliveryProjectionFactory()
    assert projection.display_state(3600) == "pending"

    projection.projection_status = _PStatus.CURRENT
    projection.observed_at = timezone.now()
    assert projection.display_state(3600) == "current"

    projection.observed_at = timezone.now() - timedelta(hours=2)
    assert projection.display_state(3600) == "stale"


@pytest.mark.django_db
def test_display_state_degradado_passa_direto() -> None:
    projection = GithubDeliveryProjectionFactory()
    projection.projection_status = _PStatus.PERMISSION_DENIED
    assert projection.display_state(3600) == "permission_denied"


# --- helpers de payload ------------------------------------------------------


def test_check_state_agrega_runs() -> None:
    assert gd._check_state_from_payload({"check_runs": []}) == _CiState.UNKNOWN
    assert (
        gd._check_state_from_payload(
            {"check_runs": [{"status": "completed", "conclusion": "success"}]}
        )
        == _CiState.SUCCESS
    )
    assert (
        gd._check_state_from_payload(
            {
                "check_runs": [
                    {"status": "completed", "conclusion": "success"},
                    {"status": "completed", "conclusion": "failure"},
                ]
            }
        )
        == _CiState.FAILURE
    )
    assert (
        gd._check_state_from_payload(
            {
                "check_runs": [
                    {"status": "completed", "conclusion": "success"},
                    {"status": "in_progress", "conclusion": None},
                ]
            }
        )
        == _CiState.PENDING
    )


def test_issue_e_pull_from_payload() -> None:
    issue = gd._issue_from_payload({"state": "open", "html_url": "u"})
    assert issue.state == _IState.OPEN and issue.url == "u"
    pull = gd._pull_from_payload(
        {"state": "closed", "merged": True, "html_url": "p", "head": {"sha": "s", "ref": "r"}}
    )
    assert pull.state == _PState.MERGED and pull.head_sha == "s" and pull.head_ref == "r"
