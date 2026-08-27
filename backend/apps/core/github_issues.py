"""Adaptador GitHub Issues para o handoff de engenharia (FDD 040, ADR 0040).

Zero LLM: o corpo da Issue é markdown determinístico a partir do `IssueDraft`. Falha fechada —
sem token, sem repositório, 4xx/5xx ou timeout levantam `GitHubIssuesError`; nunca devolvem
`IssueRef` vazio. `str()` do erro e os logs nunca carregam o token (NFR-004).

A FDD 041 acrescentou as **leituras** de que a reconciliação da projeção precisa — Issue, PR e
estado de check por SHA — neste mesmo arquivo e nesta mesma classe. Um segundo cliente HTTP para
o mesmo fornecedor traria uma segunda política de timeout, de erro e de redação de token.
"""

from __future__ import annotations

import json
import logging
import re
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Protocol

from django.conf import settings

logger = logging.getLogger(__name__)

_API_ROOT = "https://api.github.com"
_TIMEOUT_SECONDS = 10
_ACCEPT = "application/vnd.github+json"
_USER_AGENT = "Biahflow-Pulse"

_BEARER_RE = re.compile(r"(?i)(bearer\s+)\S+")
_GITHUB_TOKEN_RE = re.compile(r"(?i)(ghp|gho|ghu|ghs|ghr|github_pat)_[A-Za-z0-9_]+")


def redact_secrets(text: str) -> str:
    """Remove Bearer tokens e prefixos GitHub clássicos de qualquer texto observável."""
    text = _BEARER_RE.sub(r"\1[redacted]", text)
    return _GITHUB_TOKEN_RE.sub("[redacted]", text)


class GitHubIssuesError(Exception):
    """A API do GitHub recusou, expirou ou não estava configurada.

    `str()` **nunca** contém o token — o construtor reda qualquer vazamento do adaptador.
    """

    def __init__(self, message: str) -> None:
        super().__init__(redact_secrets(message))


@dataclass(frozen=True)
class IssueRef:
    number: int
    url: str
    node_id: str
    repository: str


@dataclass(frozen=True)
class IssueDraft:
    title: str
    objective: str
    context: str
    acceptance_criteria: str
    scope: str
    out_of_scope: str
    repository: str
    milestone_ref: str
    adr_refs: list[str]
    nfr_refs: list[str]
    fdd_refs: list[str]
    pulse_work_item_id: str
    pulse_project_id: str
    correlation_id: str


@dataclass(frozen=True)
class IssueSnapshot:
    """O que a projeção precisa saber de uma Issue: estado, título e o carimbo **de lá**."""

    state: str
    title: str
    updated_at: datetime | None


@dataclass(frozen=True)
class PullRequestSnapshot:
    number: int
    state: str
    merged: bool
    head_sha: str
    updated_at: datetime | None


class GitHubIssuesClient(Protocol):
    def create_issue(self, draft: IssueDraft) -> IssueRef: ...
    def find_by_handoff_id(
        self, repository: str, pulse_work_item_id: str
    ) -> IssueRef | None: ...


# Protocolo **separado** do de escrita, e não uma extensão dele: o provisionamento (FDD 040) já
# aceita um cliente de dois métodos, e alargar aquele contrato obrigaria todo dublê existente a
# implementar leituras que ele não usa.
class GithubReadClient(Protocol):
    def get_issue(self, repository: str, number: int) -> IssueSnapshot: ...
    def get_pull_request(self, repository: str, number: int) -> PullRequestSnapshot: ...
    def get_check_state(self, repository: str, sha: str) -> str: ...


def render_issue_body(draft: IssueDraft) -> str:
    """Task Contract em inglês, só com as listas do draft — sem descobrir documentos."""

    def bullets(label: str, refs: list[str]) -> str:
        if not refs:
            return f"- {label}: (none)"
        return "\n".join(f"- {label}: {item}" for item in refs)

    references = "\n".join(
        [
            bullets("ADR", list(draft.adr_refs)),
            bullets("NFR", list(draft.nfr_refs)),
            bullets("FDD", list(draft.fdd_refs)),
        ]
    )
    return (
        f"## Objective\n\n{draft.objective}\n\n"
        f"## Context\n\n{draft.context}\n\n"
        f"## Acceptance Criteria\n\n{draft.acceptance_criteria}\n\n"
        f"## Scope\n\n{draft.scope}\n\n"
        f"## Out of Scope\n\n{draft.out_of_scope}\n\n"
        f"## Milestone\n\n{draft.milestone_ref}\n\n"
        f"## References\n\n{references}\n\n"
        "<!-- biahflow-pulse -->\n"
        f"Pulse-Handoff-ID: {draft.pulse_work_item_id}\n"
        f"Pulse-Project-ID: {draft.pulse_project_id}\n"
        f"Correlation-ID: {draft.correlation_id}\n"
        f"Repository: {draft.repository}\n"
        "<!-- /biahflow-pulse -->\n"
    )


def _token() -> str:
    return str(getattr(settings, "GITHUB_TOKEN", "") or "").strip()


def _require_token_and_repo(repository: str) -> str:
    if not _token():
        raise GitHubIssuesError("GitHub token is missing")
    repo = repository.strip()
    if not repo:
        raise GitHubIssuesError("GitHub repository is missing")
    parts = repo.split("/")
    if len(parts) != 2 or not parts[0] or not parts[1]:
        raise GitHubIssuesError("GitHub repository must be owner/repo")
    if any(ch in repo for ch in " ?&#"):
        raise GitHubIssuesError("GitHub repository must be owner/repo")
    return repo


def _headers() -> dict[str, str]:
    return {
        "Accept": _ACCEPT,
        "Authorization": f"Bearer {_token()}",
        "User-Agent": _USER_AGENT,
        "X-GitHub-Api-Version": "2022-11-28",
    }


def _parse_issue(payload: dict[str, object], repository: str) -> IssueRef:
    raw_number = payload.get("number")
    if isinstance(raw_number, bool) or not isinstance(raw_number, int):
        raise GitHubIssuesError("GitHub response missing issue number")
    number = raw_number
    url = str(payload.get("html_url") or "").strip()
    if number <= 0 or not url:
        raise GitHubIssuesError("GitHub response missing issue number or url")
    return IssueRef(
        number=number,
        url=url,
        node_id=str(payload.get("node_id") or ""),
        repository=repository,
    )


def _request(method: str, url: str, payload: dict[str, object] | None = None) -> dict[str, object]:
    headers = _headers()
    data = None
    if payload is not None:
        data = json.dumps(payload).encode()
        headers = {**headers, "Content-Type": "application/json"}
    request = urllib.request.Request(url, data=data, method=method, headers=headers)
    try:
        with urllib.request.urlopen(request, timeout=_TIMEOUT_SECONDS) as response:  # noqa: S310
            raw = response.read()
    except urllib.error.HTTPError as exc:
        logger.warning("GitHub issues request failed method=%s url=%s status=%s", method, url, exc.code)
        raise GitHubIssuesError(f"GitHub HTTP {exc.code} for {url}") from exc
    except (urllib.error.URLError, TimeoutError, OSError) as exc:
        logger.warning("GitHub issues request failed method=%s url=%s", method, url)
        raise GitHubIssuesError(f"GitHub request failed for {url}: {exc}") from exc
    if not raw:
        return {}
    try:
        decoded = json.loads(raw)
    except ValueError as exc:
        raise GitHubIssuesError(f"GitHub returned non-JSON for {url}") from exc
    if not isinstance(decoded, dict):
        raise GitHubIssuesError(f"GitHub returned unexpected payload for {url}")
    return decoded


def ping_repository() -> tuple[bool, str]:
    """Sonda de leitura: o token alcança o repositório configurado? Sem criar Issue."""
    repository = _require_token_and_repo(str(getattr(settings, "GITHUB_REPO", "") or ""))
    owner, repo = repository.split("/", 1)
    payload = _request("GET", f"{_API_ROOT}/repos/{owner}/{repo}")
    full_name = str(payload.get("full_name") or repository)
    return True, f"repositório {full_name} acessível"


class GithubIssuesApi:
    """Cliente concreto da GitHub REST API. Sem `pragma: no cover` — os testes mockam o I/O."""

    def create_issue(self, draft: IssueDraft) -> IssueRef:
        repository = _require_token_and_repo(draft.repository)
        owner, repo = repository.split("/", 1)
        url = f"{_API_ROOT}/repos/{owner}/{repo}/issues"
        payload = _request(
            "POST",
            url,
            {"title": draft.title, "body": render_issue_body(draft)},
        )
        return _parse_issue(payload, repository)

    def find_by_handoff_id(
        self, repository: str, pulse_work_item_id: str
    ) -> IssueRef | None:
        repository = _require_token_and_repo(repository)
        handoff_id = pulse_work_item_id.strip()
        if not handoff_id:
            raise GitHubIssuesError("Pulse handoff id is missing")
        if any(ch in handoff_id for ch in '"\\'):
            raise GitHubIssuesError("Pulse handoff id contains unsupported characters")
        query = f'repo:{repository} type:issue in:body "Pulse-Handoff-ID: {handoff_id}"'
        url = f"{_API_ROOT}/search/issues?{urllib.parse.urlencode({'q': query})}"
        try:
            payload = _request("GET", url)
        except GitHubIssuesError as exc:
            status = http_status_from_error(exc)
            if status in {404, 422}:
                return None
            raise
        items = payload.get("items") or []
        if not items:
            return None
        if not isinstance(items, list) or not isinstance(items[0], dict):
            raise GitHubIssuesError("GitHub search returned a malformed issue")
        return _parse_issue(items[0], repository)

    # --- Leituras da projeção (FDD 041) --------------------------------------

    def get_issue(self, repository: str, number: int) -> IssueSnapshot:
        repository = _require_token_and_repo(repository)
        owner, repo = repository.split("/", 1)
        payload = _request("GET", f"{_API_ROOT}/repos/{owner}/{repo}/issues/{int(number)}")
        return IssueSnapshot(
            state=str(payload.get("state") or "").strip().lower(),
            title=str(payload.get("title") or "")[:255],
            updated_at=parse_github_datetime(payload.get("updated_at")),
        )

    def get_pull_request(self, repository: str, number: int) -> PullRequestSnapshot:
        repository = _require_token_and_repo(repository)
        owner, repo = repository.split("/", 1)
        payload = _request("GET", f"{_API_ROOT}/repos/{owner}/{repo}/pulls/{int(number)}")
        head = payload.get("head")
        return PullRequestSnapshot(
            number=int(number),
            state=str(payload.get("state") or "").strip().lower(),
            merged=bool(payload.get("merged")),
            head_sha=str((head or {}).get("sha") or "") if isinstance(head, dict) else "",
            updated_at=parse_github_datetime(payload.get("updated_at")),
        )

    def get_check_state(self, repository: str, sha: str) -> str:
        """Agrega os check runs de um commit em **um** dos quatro estados do painel.

        Agregação e não lista: a linha do painel responde "aquela revisão passou?", e enumerar
        jobs ali seria reconstruir a tela do GitHub dentro do Pulse — que é exatamente o que a
        ADR 0040 diz para não fazer.
        """
        repository = _require_token_and_repo(repository)
        owner, repo = repository.split("/", 1)
        commit = urllib.parse.quote(str(sha).strip(), safe="")
        payload = _request(
            "GET", f"{_API_ROOT}/repos/{owner}/{repo}/commits/{commit}/check-runs?per_page=100"
        )
        runs = payload.get("check_runs")
        if not isinstance(runs, list) or not runs:
            return CI_NONE
        return aggregate_check_runs(
            [
                (
                    str(run.get("status") or "").strip().lower(),
                    str(run.get("conclusion") or "").strip().lower(),
                )
                for run in runs
                if isinstance(run, dict)
            ]
        )


CI_NONE = "none"
CI_PENDING = "pending"
CI_SUCCESS = "success"
CI_FAILURE = "failure"

# Conclusões que reprovam. `neutral`, `skipped` e `stale` **não** entram: um job pulado não é uma
# reprovação, e pintá-lo de vermelho ensinaria a ignorar o vermelho.
_CHECK_FAILURE = {"failure", "timed_out", "cancelled", "action_required", "startup_failure"}


def aggregate_check_runs(runs: list[tuple[str, str]]) -> str:
    """`[(status, conclusion)]` → um estado de CI. Separada do I/O para ficar testável."""
    if not runs:
        return CI_NONE
    if any(status != "completed" for status, _ in runs):
        return CI_PENDING
    if any(conclusion in _CHECK_FAILURE for _, conclusion in runs):
        return CI_FAILURE
    return CI_SUCCESS


def parse_github_datetime(value: object) -> datetime | None:
    """ISO 8601 do GitHub (`2026-08-27T10:00:00Z`) em `datetime` ciente de fuso.

    Devolve `None` em vez de levantar: um carimbo ilegível não pode derrubar a entrega inteira
    do webhook — ele só faz a guarda de ordem não ter o que comparar naquele evento.
    """
    if not isinstance(value, str) or not value.strip():
        return None
    try:
        parsed = datetime.fromisoformat(value.strip().replace("Z", "+00:00"))
    except ValueError:
        return None
    return parsed if parsed.tzinfo else parsed.replace(tzinfo=UTC)


def http_status_from_error(exc: GitHubIssuesError) -> int | None:
    """O status HTTP por trás do erro, quando houve um.

    Público desde a FDD 041: é ele que separa "GitHub fora do ar" (sem status) de "permissão
    negada" (401/403) e "referência ausente" (404) — três erros com ações corretivas diferentes,
    e é essa diferença que decide quem age.
    """
    cause = exc.__cause__
    if isinstance(cause, urllib.error.HTTPError):
        return int(cause.code)
    return None
