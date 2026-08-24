"""Adaptador GitHub Issues (FDD 040): fail-closed, idempotente na busca, sem vazar token."""

from __future__ import annotations

import json
import urllib.error
from io import BytesIO

import pytest
from django.test import override_settings

from apps.core.github_issues import (
    GithubIssuesApi,
    GitHubIssuesError,
    IssueDraft,
    render_issue_body,
)

CANARY = "ghp_CANARY_TOKEN_DO_NOT_LEAK"


def _draft(**overrides: object) -> IssueDraft:
    base = dict(
        title="Engineer the handoff",
        objective="Provision a GitHub Issue.",
        context="Pulse approved engineering work.",
        acceptance_criteria="Issue exists and is idempotent.",
        scope="Backend provisioning.",
        out_of_scope="Webhooks and PR sync.",
        repository="acme/repo",
        milestone_ref="M1",
        adr_refs=["ADR-0040"],
        nfr_refs=["NFR-003"],
        fdd_refs=["FDD-040"],
        pulse_work_item_id="pulse-work-1",
        pulse_project_id="17",
        correlation_id="11111111-1111-1111-1111-111111111111",
    )
    base.update(overrides)
    return IssueDraft(**base)  # type: ignore[arg-type]


class _FakeResponse:
    def __init__(self, body: bytes, status: int = 201) -> None:
        self._body = body
        self.status = status

    def read(self) -> bytes:
        return self._body

    def __enter__(self) -> _FakeResponse:
        return self

    def __exit__(self, *args: object) -> bool:
        return False


def _http_error(url: str, code: int, body: bytes = b"{}") -> urllib.error.HTTPError:
    return urllib.error.HTTPError(url, code, "error", hdrs=None, fp=BytesIO(body))


def test_render_issue_body_contains_machine_block_and_only_draft_refs() -> None:
    body = render_issue_body(_draft())
    assert "<!-- biahflow-pulse -->" in body
    assert "Pulse-Handoff-ID: pulse-work-1" in body
    assert "Pulse-Project-ID: 17" in body
    assert "Correlation-ID: 11111111-1111-1111-1111-111111111111" in body
    assert "Repository: acme/repo" in body
    assert "<!-- /biahflow-pulse -->" in body
    assert "- ADR: ADR-0040" in body
    assert "- NFR: NFR-003" in body
    assert "- FDD: FDD-040" in body
    assert "docs/adr" not in body


@override_settings(GITHUB_TOKEN=CANARY, GITHUB_REPO="acme/repo")
def test_create_issue_201_returns_ref(monkeypatch: pytest.MonkeyPatch) -> None:
    captured: dict[str, object] = {}

    def fake_urlopen(request: object, timeout: object = None) -> _FakeResponse:
        captured["url"] = getattr(request, "full_url", "")
        captured["timeout"] = timeout
        captured["body"] = json.loads(request.data.decode())  # type: ignore[union-attr]
        captured["headers"] = dict(request.header_items())  # type: ignore[union-attr]
        return _FakeResponse(
            json.dumps(
                {
                    "number": 18,
                    "html_url": "https://github.com/acme/repo/issues/18",
                    "node_id": "I_kwDOA",
                }
            ).encode()
        )

    monkeypatch.setattr("apps.core.github_issues.urllib.request.urlopen", fake_urlopen)
    ref = GithubIssuesApi().create_issue(_draft())
    assert ref.number == 18
    assert ref.url == "https://github.com/acme/repo/issues/18"
    assert ref.node_id == "I_kwDOA"
    assert ref.repository == "acme/repo"
    assert captured["timeout"] == 10
    assert captured["url"] == "https://api.github.com/repos/acme/repo/issues"
    body = captured["body"]
    assert isinstance(body, dict)
    assert "Pulse-Handoff-ID: pulse-work-1" in str(body["body"])


@override_settings(GITHUB_TOKEN=CANARY, GITHUB_REPO="acme/repo")
def test_create_issue_500_raises_without_ref(
    monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    def fake_urlopen(request: object, timeout: object = None) -> _FakeResponse:
        raise _http_error("https://api.github.com/repos/acme/repo/issues", 500)

    monkeypatch.setattr("apps.core.github_issues.urllib.request.urlopen", fake_urlopen)
    caplog.set_level("WARNING", logger="apps.core.github_issues")
    with pytest.raises(GitHubIssuesError) as exc:
        GithubIssuesApi().create_issue(_draft())
    assert "500" in str(exc.value)
    assert CANARY not in str(exc.value)
    assert CANARY not in caplog.text


@override_settings(GITHUB_TOKEN=CANARY, GITHUB_REPO="acme/repo")
def test_create_issue_timeout_raises(monkeypatch: pytest.MonkeyPatch) -> None:
    def fake_urlopen(request: object, timeout: object = None) -> _FakeResponse:
        raise TimeoutError("timed out")

    monkeypatch.setattr("apps.core.github_issues.urllib.request.urlopen", fake_urlopen)
    with pytest.raises(GitHubIssuesError) as exc:
        GithubIssuesApi().create_issue(_draft())
    assert "acme/repo" in str(exc.value)
    assert CANARY not in str(exc.value)


@override_settings(GITHUB_TOKEN=CANARY)
def test_find_by_handoff_id_returns_existing(monkeypatch: pytest.MonkeyPatch) -> None:
    def fake_urlopen(request: object, timeout: object = None) -> _FakeResponse:
        return _FakeResponse(
            json.dumps(
                {
                    "items": [
                        {
                            "number": 7,
                            "html_url": "https://github.com/acme/repo/issues/7",
                            "node_id": "I_existing",
                        }
                    ]
                }
            ).encode(),
            status=200,
        )

    monkeypatch.setattr("apps.core.github_issues.urllib.request.urlopen", fake_urlopen)
    ref = GithubIssuesApi().find_by_handoff_id("acme/repo", "pulse-work-1")
    assert ref is not None
    assert ref.number == 7
    assert ref.url == "https://github.com/acme/repo/issues/7"
    assert ref.node_id == "I_existing"


@override_settings(GITHUB_TOKEN=CANARY)
def test_find_by_handoff_id_empty_returns_none(monkeypatch: pytest.MonkeyPatch) -> None:
    def fake_urlopen(request: object, timeout: object = None) -> _FakeResponse:
        return _FakeResponse(json.dumps({"items": []}).encode(), status=200)

    monkeypatch.setattr("apps.core.github_issues.urllib.request.urlopen", fake_urlopen)
    assert GithubIssuesApi().find_by_handoff_id("acme/repo", "pulse-work-1") is None


@override_settings(GITHUB_TOKEN=CANARY)
def test_find_search_422_returns_none(monkeypatch: pytest.MonkeyPatch) -> None:
    def fake_urlopen(request: object, timeout: object = None) -> _FakeResponse:
        raise _http_error("https://api.github.com/search/issues", 422)

    monkeypatch.setattr("apps.core.github_issues.urllib.request.urlopen", fake_urlopen)
    assert GithubIssuesApi().find_by_handoff_id("acme/repo", "pulse-work-1") is None


@override_settings(GITHUB_TOKEN=CANARY)
def test_find_search_5xx_raises(monkeypatch: pytest.MonkeyPatch) -> None:
    def fake_urlopen(request: object, timeout: object = None) -> _FakeResponse:
        raise _http_error("https://api.github.com/search/issues", 503)

    monkeypatch.setattr("apps.core.github_issues.urllib.request.urlopen", fake_urlopen)
    with pytest.raises(GitHubIssuesError):
        GithubIssuesApi().find_by_handoff_id("acme/repo", "pulse-missing")


@override_settings(GITHUB_TOKEN=CANARY)
def test_find_rejects_quoted_handoff_id(monkeypatch: pytest.MonkeyPatch) -> None:
    called: list[object] = []

    def fake_urlopen(request: object, timeout: object = None) -> _FakeResponse:
        called.append(request)
        raise AssertionError("urlopen não deveria ser chamado")

    monkeypatch.setattr("apps.core.github_issues.urllib.request.urlopen", fake_urlopen)
    with pytest.raises(GitHubIssuesError, match="unsupported"):
        GithubIssuesApi().find_by_handoff_id("acme/repo", 'pulse-"injected"')
    assert called == []


@override_settings(GITHUB_TOKEN=CANARY, GITHUB_REPO="acme/repo")
def test_ping_repository_get_repo(monkeypatch: pytest.MonkeyPatch) -> None:
    captured: dict[str, object] = {}

    def fake_urlopen(request: object, timeout: object = None) -> _FakeResponse:
        captured["url"] = getattr(request, "full_url", "")
        captured["method"] = request.get_method()  # type: ignore[union-attr]
        return _FakeResponse(json.dumps({"full_name": "acme/repo"}).encode(), status=200)

    monkeypatch.setattr("apps.core.github_issues.urllib.request.urlopen", fake_urlopen)
    from apps.core.github_issues import ping_repository

    ok, detail = ping_repository()
    assert ok is True
    assert "acme/repo" in detail
    assert captured["url"] == "https://api.github.com/repos/acme/repo"
    assert captured["method"] == "GET"


@override_settings(GITHUB_TOKEN="", GITHUB_REPO="acme/repo")
def test_render_empty_refs_says_none() -> None:
    body = render_issue_body(_draft(adr_refs=[], nfr_refs=[], fdd_refs=[]))
    assert "- ADR: (none)" in body
    assert "- NFR: (none)" in body
    assert "- FDD: (none)" in body


@override_settings(GITHUB_TOKEN=CANARY)
def test_repo_vazio_ou_invalido_nao_chama_http(monkeypatch: pytest.MonkeyPatch) -> None:
    called: list[object] = []

    def fake_urlopen(request: object, timeout: object = None) -> _FakeResponse:
        called.append(request)
        raise AssertionError("urlopen não deveria ser chamado")

    monkeypatch.setattr("apps.core.github_issues.urllib.request.urlopen", fake_urlopen)
    with pytest.raises(GitHubIssuesError, match="missing"):
        GithubIssuesApi().create_issue(_draft(repository=""))
    with pytest.raises(GitHubIssuesError, match="owner/repo"):
        GithubIssuesApi().create_issue(_draft(repository="only-owner"))
    with pytest.raises(GitHubIssuesError, match="owner/repo"):
        GithubIssuesApi().create_issue(_draft(repository="acme/repo?evil=1"))
    assert called == []


@override_settings(GITHUB_TOKEN=CANARY)
def test_create_issue_resposta_malformada(monkeypatch: pytest.MonkeyPatch) -> None:
    def fake_urlopen(request: object, timeout: object = None) -> _FakeResponse:
        return _FakeResponse(json.dumps({"html_url": "https://github.com/acme/repo/issues/1"}).encode())

    monkeypatch.setattr("apps.core.github_issues.urllib.request.urlopen", fake_urlopen)
    with pytest.raises(GitHubIssuesError, match="number"):
        GithubIssuesApi().create_issue(_draft())


@override_settings(GITHUB_TOKEN=CANARY)
def test_create_issue_number_sem_url(monkeypatch: pytest.MonkeyPatch) -> None:
    def fake_urlopen(request: object, timeout: object = None) -> _FakeResponse:
        return _FakeResponse(json.dumps({"number": 1, "html_url": ""}).encode())

    monkeypatch.setattr("apps.core.github_issues.urllib.request.urlopen", fake_urlopen)
    with pytest.raises(GitHubIssuesError, match="url"):
        GithubIssuesApi().create_issue(_draft())


@override_settings(GITHUB_TOKEN=CANARY)
def test_create_issue_corpo_vazio_ou_nao_json(monkeypatch: pytest.MonkeyPatch) -> None:
    responses = [_FakeResponse(b""), _FakeResponse(b"not-json"), _FakeResponse(b"[1]")]

    def fake_urlopen(request: object, timeout: object = None) -> _FakeResponse:
        return responses.pop(0)

    monkeypatch.setattr("apps.core.github_issues.urllib.request.urlopen", fake_urlopen)
    with pytest.raises(GitHubIssuesError, match="number"):
        GithubIssuesApi().create_issue(_draft())
    with pytest.raises(GitHubIssuesError, match="non-JSON"):
        GithubIssuesApi().create_issue(_draft())
    with pytest.raises(GitHubIssuesError, match="unexpected"):
        GithubIssuesApi().create_issue(_draft())


@override_settings(GITHUB_TOKEN=CANARY)
def test_find_id_vazio_e_items_malformados(monkeypatch: pytest.MonkeyPatch) -> None:
    with pytest.raises(GitHubIssuesError, match="handoff id"):
        GithubIssuesApi().find_by_handoff_id("acme/repo", "  ")

    def fake_urlopen(request: object, timeout: object = None) -> _FakeResponse:
        return _FakeResponse(json.dumps({"items": ["nope"]}).encode(), status=200)

    monkeypatch.setattr("apps.core.github_issues.urllib.request.urlopen", fake_urlopen)
    with pytest.raises(GitHubIssuesError, match="malformed"):
        GithubIssuesApi().find_by_handoff_id("acme/repo", "pulse-work-1")


@override_settings(GITHUB_TOKEN=CANARY)
def test_find_404_returns_none(monkeypatch: pytest.MonkeyPatch) -> None:
    def fake_urlopen(request: object, timeout: object = None) -> _FakeResponse:
        raise _http_error("https://api.github.com/search/issues", 404)

    monkeypatch.setattr("apps.core.github_issues.urllib.request.urlopen", fake_urlopen)
    assert GithubIssuesApi().find_by_handoff_id("acme/repo", "pulse-work-1") is None


@override_settings(GITHUB_TOKEN=CANARY)
def test_find_timeout_raises(monkeypatch: pytest.MonkeyPatch) -> None:
    def fake_urlopen(request: object, timeout: object = None) -> _FakeResponse:
        raise TimeoutError("timed out")

    monkeypatch.setattr("apps.core.github_issues.urllib.request.urlopen", fake_urlopen)
    with pytest.raises(GitHubIssuesError):
        GithubIssuesApi().find_by_handoff_id("acme/repo", "pulse-work-1")


@override_settings(GITHUB_TOKEN="", GITHUB_REPO="acme/repo")
def test_sem_token_nao_chama_urlopen(monkeypatch: pytest.MonkeyPatch) -> None:
    called: list[object] = []

    def fake_urlopen(request: object, timeout: object = None) -> _FakeResponse:
        called.append(request)
        raise AssertionError("urlopen não deveria ser chamado")

    monkeypatch.setattr("apps.core.github_issues.urllib.request.urlopen", fake_urlopen)
    with pytest.raises(GitHubIssuesError, match="token"):
        GithubIssuesApi().create_issue(_draft())
    assert called == []


@override_settings(GITHUB_TOKEN=CANARY)
def test_canary_token_ausente_de_logs_e_excecao(
    monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    def fake_urlopen(request: object, timeout: object = None) -> _FakeResponse:
        raise urllib.error.URLError("cannot reach github with Bearer " + CANARY)

    monkeypatch.setattr("apps.core.github_issues.urllib.request.urlopen", fake_urlopen)
    caplog.set_level("WARNING", logger="apps.core.github_issues")
    with pytest.raises(GitHubIssuesError) as exc:
        GithubIssuesApi().create_issue(_draft())
    assert CANARY not in str(exc.value)
    assert CANARY not in caplog.text
    for record in caplog.records:
        assert CANARY not in record.getMessage()
        if record.args:
            assert CANARY not in str(record.args)
