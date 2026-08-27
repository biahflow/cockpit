"""Projeção de entrega: lê o estado de engenharia do GitHub para dentro do Pulse (FDD 041).

Direção de **leitura**, complementar ao provisionamento (FDD 040 / `engineering_provisioning`, que é
a de escrita). Aqui o Pulse observa Issue/PR/CI e projeta o estado, sem virar fonte da verdade
(ADR 0046, que herda a fronteira da ADR 0040): uma edição normal do Pulse **não** reescreve o
estado de engenharia — quem o move é o webhook ou a reconciliação.

Tudo determinístico e **zero LLM** (FinOps): verificação de assinatura, parsing de evento,
comparação de SHA/status, idempotência e reconciliação. A entrada é webhook-first e idempotente
(inbox por `X-GitHub-Delivery`, guarda de out-of-order por marca d'água de tempo); a reconciliação
por poll recupera eventos perdidos e nunca inventa status — falha do GitHub vira
`unavailable`/`permission_denied`/`reference_missing`, distinta de um estado confirmado.
"""

from __future__ import annotations

import hashlib
import hmac
import logging
import re
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from datetime import datetime
from typing import Protocol

from django.conf import settings
from django.db import transaction
from django.utils import timezone
from django.utils.dateparse import parse_datetime

from . import flags, github_issues
from .github_issues import GitHubIssuesError, redact_secrets
from .models import GithubDeliveryProjection, GithubWebhookDelivery

logger = logging.getLogger(__name__)

_ERROR_MESSAGE_MAX = 2000

_IState = GithubDeliveryProjection.IssueState
_PState = GithubDeliveryProjection.PullState
_RState = GithubDeliveryProjection.ReviewState
_CiState = GithubDeliveryProjection.CiState
_PStatus = GithubDeliveryProjection.ProjectionStatus

# "Closes #12", "fixes #7", "resolved #99" — o vínculo determinístico PR→Issue, sem LLM.
_LINK_RE = re.compile(r"(?i)\b(?:close[sd]?|fix(?:e[sd])?|resolve[sd]?)\s+#(\d+)")

# Conclusões de check que contam como vermelho. `neutral`/`skipped` não são falha nem verde:
# ficam em `pending` para não inventar um verde que a suíte não afirmou.
_CI_FAILURE = {"failure", "timed_out", "cancelled", "action_required", "stale", "startup_failure"}


def is_enabled() -> bool:
    return flags.is_enabled("github_delivery")


def stale_after_seconds() -> int:
    return int(getattr(settings, "GITHUB_PROJECTION_STALE_AFTER_SECONDS", 3600))


# --- Autenticação do webhook -------------------------------------------------


def verify_signature(body: bytes, headers: Mapping[str, str]) -> bool:
    """HMAC-SHA256 do corpo cru contra `X-Hub-Signature-256` (o esquema do GitHub).

    Sobre os bytes originais, nunca sobre `request.data`: qualquer reserialização muda o digest.
    Sem segredo configurado, recusa — é o `fail closed` da ADR 0018 aplicado à porta de entrada.
    """
    secret = str(getattr(settings, "GITHUB_WEBHOOK_SECRET", "") or "")
    if not secret:
        return False
    header = headers.get("X-Hub-Signature-256") or headers.get("x-hub-signature-256") or ""
    if not header.startswith("sha256="):
        return False
    expected = "sha256=" + hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()
    return hmac.compare_digest(expected, header)


# --- Evento canônico ---------------------------------------------------------


@dataclass(frozen=True)
class DeliveryEvent:
    """Recorte determinístico de um webhook. Campo `None` = "este evento não fala disso"."""

    event_type: str
    delivery_id: str
    repository: str
    occurred_at: datetime | None = None
    issue_number: int | None = None
    issue_state: str | None = None
    issue_url: str | None = None
    pr_number: int | None = None
    pr_state: str | None = None
    pr_url: str | None = None
    head_sha: str | None = None
    head_ref: str | None = None
    review_state: str | None = None
    ci_state: str | None = None


def _repo(payload: Mapping[str, object]) -> str:
    repository = payload.get("repository")
    if isinstance(repository, Mapping):
        return str(repository.get("full_name") or "").strip()
    return ""


def _dt(value: object) -> datetime | None:
    if not isinstance(value, str) or not value:
        return None
    return parse_datetime(value)


def _int(value: object) -> int | None:
    return value if isinstance(value, int) and not isinstance(value, bool) else None


def _pull_state(pr: Mapping[str, object]) -> str | None:
    if pr.get("merged"):
        return _PState.MERGED
    if pr.get("draft"):
        return _PState.DRAFT
    state = str(pr.get("state") or "")
    if state == "open":
        return _PState.OPEN
    if state == "closed":
        return _PState.CLOSED
    return None


def _ci_state(status: object, conclusion: object) -> str | None:
    if str(status or "") != "completed":
        return _CiState.PENDING
    verdict = str(conclusion or "")
    if verdict == "success":
        return _CiState.SUCCESS
    if verdict in _CI_FAILURE:
        return _CiState.FAILURE
    return _CiState.PENDING


def _commit_status_state(state: object) -> str | None:
    text = str(state or "")
    if text == "success":
        return _CiState.SUCCESS
    if text in {"failure", "error"}:
        return _CiState.FAILURE
    if text == "pending":
        return _CiState.PENDING
    return None


def _linked_issue(body: object) -> int | None:
    match = _LINK_RE.search(str(body or ""))
    return int(match.group(1)) if match else None


def _parse_issues(delivery_id: str, payload: Mapping[str, object]) -> DeliveryEvent | None:
    issue = payload.get("issue")
    repo = _repo(payload)
    if not isinstance(issue, Mapping) or not repo:
        return None
    number = _int(issue.get("number"))
    if number is None:
        return None
    state = str(issue.get("state") or "")
    return DeliveryEvent(
        event_type="issues",
        delivery_id=delivery_id,
        repository=repo,
        occurred_at=_dt(issue.get("updated_at")),
        issue_number=number,
        issue_state=state if state in {_IState.OPEN, _IState.CLOSED} else None,
        issue_url=str(issue.get("html_url") or "") or None,
    )


def _parse_pull_request(delivery_id: str, payload: Mapping[str, object]) -> DeliveryEvent | None:
    pr = payload.get("pull_request")
    repo = _repo(payload)
    if not isinstance(pr, Mapping) or not repo:
        return None
    number = _int(pr.get("number"))
    if number is None:
        return None
    head_raw = pr.get("head")
    head = head_raw if isinstance(head_raw, Mapping) else {}
    return DeliveryEvent(
        event_type="pull_request",
        delivery_id=delivery_id,
        repository=repo,
        occurred_at=_dt(pr.get("updated_at")),
        issue_number=_linked_issue(pr.get("body")),
        pr_number=number,
        pr_state=_pull_state(pr),
        pr_url=str(pr.get("html_url") or "") or None,
        head_sha=str(head.get("sha") or "") or None,
        head_ref=str(head.get("ref") or "") or None,
    )


def _parse_review(delivery_id: str, payload: Mapping[str, object]) -> DeliveryEvent | None:
    review = payload.get("review")
    pr = payload.get("pull_request")
    repo = _repo(payload)
    if not isinstance(review, Mapping) or not isinstance(pr, Mapping) or not repo:
        return None
    number = _int(pr.get("number"))
    state = str(review.get("state") or "").lower()
    # `commented`/`dismissed` não movem a projeção de forma determinística — ignoramos.
    mapped = {"approved": _RState.APPROVED, "changes_requested": _RState.CHANGES_REQUESTED}.get(state)
    if number is None or mapped is None:
        return None
    head_raw = pr.get("head")
    head = head_raw if isinstance(head_raw, Mapping) else {}
    return DeliveryEvent(
        event_type="pull_request_review",
        delivery_id=delivery_id,
        repository=repo,
        occurred_at=_dt(review.get("submitted_at")),
        pr_number=number,
        review_state=mapped,
        head_sha=str(head.get("sha") or "") or None,
    )


def _parse_check_suite(delivery_id: str, payload: Mapping[str, object]) -> DeliveryEvent | None:
    suite = payload.get("check_suite")
    repo = _repo(payload)
    if not isinstance(suite, Mapping) or not repo:
        return None
    sha = str(suite.get("head_sha") or "")
    if not sha:
        return None
    return DeliveryEvent(
        event_type="check_suite",
        delivery_id=delivery_id,
        repository=repo,
        occurred_at=_dt(suite.get("updated_at")),
        head_sha=sha,
        ci_state=_ci_state(suite.get("status"), suite.get("conclusion")),
    )


def _parse_status(delivery_id: str, payload: Mapping[str, object]) -> DeliveryEvent | None:
    repo = _repo(payload)
    sha = str(payload.get("sha") or "")
    if not repo or not sha:
        return None
    return DeliveryEvent(
        event_type="status",
        delivery_id=delivery_id,
        repository=repo,
        occurred_at=_dt(payload.get("updated_at")),
        head_sha=sha,
        ci_state=_commit_status_state(payload.get("state")),
    )


_PARSERS: dict[str, Callable[[str, Mapping[str, object]], DeliveryEvent | None]] = {
    "issues": _parse_issues,
    "pull_request": _parse_pull_request,
    "pull_request_review": _parse_review,
    "check_suite": _parse_check_suite,
    "status": _parse_status,
}


def parse_event(
    event_type: str, delivery_id: str, payload: Mapping[str, object]
) -> DeliveryEvent | None:
    """Traduz um webhook num `DeliveryEvent`. Tipo desconhecido ou corpo incompleto vira `None`."""
    parser = _PARSERS.get(event_type)
    if parser is None:
        return None
    return parser(delivery_id, payload)


# --- Aplicação idempotente ---------------------------------------------------


def _resolve(event: DeliveryEvent) -> GithubDeliveryProjection | None:
    """Encontra a projeção que este evento toca. Nunca cria — não inventa referência.

    A âncora é a Issue; o `issue_number` (inclusive o `Closes #N` de um PR) resolve primeiro e é o
    que **liga** um PR à projeção da Issue. Depois disso, eventos de PR/CI casam por `pr_number` e
    por `head_sha`.
    """
    base = GithubDeliveryProjection.objects.filter(
        repository=event.repository, archived_at__isnull=True
    )
    if event.issue_number is not None:
        found = base.filter(issue_number=event.issue_number).first()
        if found is not None:
            return found
    if event.pr_number is not None:
        found = base.filter(pr_number=event.pr_number).first()
        if found is not None:
            return found
    if event.head_sha:
        found = base.filter(head_sha=event.head_sha).first()
        if found is not None:
            return found
    return None


def apply_event(event: DeliveryEvent) -> GithubDeliveryProjection | None:
    """Aplica um evento à projeção. Idempotente e seguro a out-of-order.

    A reentrega literal é barrada antes daqui, no inbox (`ingest`). Aqui a guarda é temporal: um
    evento **mais antigo** que a marca d'água (`last_event_at`) é replay atrasado e não regride o
    estado — a reconciliação recupera o que tiver realmente faltado. Reaplicar o mesmo estado é
    naturalmente idempotente.
    """
    projection = _resolve(event)
    if projection is None:
        return None
    if (
        event.occurred_at is not None
        and projection.last_event_at is not None
        and event.occurred_at < projection.last_event_at
    ):
        return projection
    return _apply_fields(projection, event)


def _apply_fields(
    projection: GithubDeliveryProjection, event: DeliveryEvent
) -> GithubDeliveryProjection:
    now = timezone.now()
    fields = {
        "projection_status",
        "observed_at",
        "last_delivery_id",
        "last_event_type",
        "last_error_code",
        "last_error_message",
        "updated_at",
    }
    projection.projection_status = _PStatus.CURRENT
    projection.observed_at = now
    projection.last_delivery_id = (event.delivery_id or "")[:128]
    projection.last_event_type = (event.event_type or "")[:64]
    projection.last_error_code = ""
    projection.last_error_message = ""
    if event.occurred_at is not None and (
        projection.last_event_at is None or event.occurred_at > projection.last_event_at
    ):
        projection.last_event_at = event.occurred_at
        fields.add("last_event_at")
    # Commit novo invalida o CI do commit velho: um verde de outro SHA não vale para este.
    if event.head_sha and event.head_sha != projection.head_sha:
        projection.ci_state = _CiState.UNKNOWN
        fields.add("ci_state")
    for attr, value in (
        ("issue_state", event.issue_state),
        ("issue_url", event.issue_url),
        ("pr_state", event.pr_state),
        ("pr_number", event.pr_number),
        ("pr_url", event.pr_url),
        ("head_sha", event.head_sha),
        ("head_ref", event.head_ref),
        ("review_state", event.review_state),
        ("ci_state", event.ci_state),
    ):
        if value is not None and value != "":
            setattr(projection, attr, value)
            fields.add(attr)
    projection.save(update_fields=list(fields))
    return projection


def ingest(
    event_type: str, delivery_id: str, payload: Mapping[str, object]
) -> tuple[str, GithubDeliveryProjection | None]:
    """Ponto de entrada do webhook: dedup no inbox, depois parse+apply, numa transação só.

    Devolve o desfecho (`applied`/`duplicate`/`ignored`/`invalid`) e a projeção afetada. O inbox e
    a aplicação commitam juntos: se `apply` estourar, o inbox reverte junto e a reentrega pode
    reprocessar — sem isso, uma linha de inbox sobreviveria a um apply que falhou e engoliria o
    retry.
    """
    delivery_id = (delivery_id or "").strip()
    if not delivery_id:
        return "invalid", None
    with transaction.atomic():
        record, created = GithubWebhookDelivery.objects.get_or_create(
            delivery_id=delivery_id, defaults={"event_type": (event_type or "")[:64]}
        )
        if not created:
            return "duplicate", record.projection
        event = parse_event(event_type, delivery_id, payload)
        if event is None:
            return "ignored", None
        projection = apply_event(event)
        if projection is None:
            return "ignored", None
        record.projection = projection
        record.save(update_fields=["projection"])
        return "applied", projection


# --- Reconciliação por poll (recupera eventos perdidos) ----------------------


@dataclass(frozen=True)
class FetchedIssue:
    state: str
    url: str


@dataclass(frozen=True)
class FetchedPull:
    state: str
    url: str
    head_sha: str
    head_ref: str


class GithubDeliveryReadClient(Protocol):
    """Protocolo do cliente de leitura (o teste injeta um fake estruturalmente compatível)."""

    def fetch_issue(self, repository: str, issue_number: int) -> FetchedIssue: ...

    def fetch_pull_request(self, repository: str, pr_number: int) -> FetchedPull: ...

    def fetch_check_state(self, repository: str, head_sha: str) -> str: ...


def _issue_from_payload(payload: Mapping[str, object]) -> FetchedIssue:
    state = str(payload.get("state") or "")
    return FetchedIssue(
        state=state if state in {_IState.OPEN, _IState.CLOSED} else _IState.UNKNOWN,
        url=str(payload.get("html_url") or ""),
    )


def _pull_from_payload(payload: Mapping[str, object]) -> FetchedPull:
    head_raw = payload.get("head")
    head = head_raw if isinstance(head_raw, Mapping) else {}
    return FetchedPull(
        state=_pull_state(payload) or _PState.UNKNOWN,
        url=str(payload.get("html_url") or ""),
        head_sha=str(head.get("sha") or ""),
        head_ref=str(head.get("ref") or ""),
    )


def _check_state_from_payload(payload: Mapping[str, object]) -> str:
    """Agrega check-runs de um SHA: qualquer falha manda; qualquer pendente segura o verde."""
    runs = payload.get("check_runs")
    if not isinstance(runs, list) or not runs:
        return _CiState.UNKNOWN
    states: list[str | None] = []
    for run in runs:
        if isinstance(run, Mapping):
            states.append(_ci_state(run.get("status"), run.get("conclusion")))
    if _CiState.FAILURE in states:
        return _CiState.FAILURE
    if _CiState.PENDING in states:
        return _CiState.PENDING
    return _CiState.SUCCESS if states else _CiState.UNKNOWN


class GithubDeliveryApi:
    """Cliente concreto de leitura da REST API do GitHub, sobre o transporte de `github_issues`."""

    def fetch_issue(self, repository: str, issue_number: int) -> FetchedIssue:  # pragma: no cover - I/O
        owner, repo = repository.split("/", 1)
        payload = github_issues.api_request(
            "GET", f"{github_issues._API_ROOT}/repos/{owner}/{repo}/issues/{issue_number}"
        )
        return _issue_from_payload(payload)

    def fetch_pull_request(self, repository: str, pr_number: int) -> FetchedPull:  # pragma: no cover - I/O
        owner, repo = repository.split("/", 1)
        payload = github_issues.api_request(
            "GET", f"{github_issues._API_ROOT}/repos/{owner}/{repo}/pulls/{pr_number}"
        )
        return _pull_from_payload(payload)

    def fetch_check_state(self, repository: str, head_sha: str) -> str:  # pragma: no cover - I/O
        owner, repo = repository.split("/", 1)
        payload = github_issues.api_request(
            "GET",
            f"{github_issues._API_ROOT}/repos/{owner}/{repo}/commits/{head_sha}/check-runs",
        )
        return _check_state_from_payload(payload)


def reconcile(
    projection: GithubDeliveryProjection, client: GithubDeliveryReadClient | None = None
) -> GithubDeliveryProjection:
    """Poll determinístico que confirma a projeção e recupera eventos perdidos (FDD 041).

    Confirma a Issue sempre; PR e CI são best-effort quando já há `pr_number` conhecido. Falha do
    GitHub **não** vira estado inventado: 404 é `reference_missing`, 401/403 é `permission_denied`,
    o resto é `unavailable`, e os valores já projetados são preservados para leitura, agora
    sinalizados como não confirmados.
    """
    if not is_enabled():
        return _mark_degraded(
            projection, _PStatus.UNAVAILABLE, "disabled", "Projeção GitHub desativada."
        )
    read_client: GithubDeliveryReadClient = client or GithubDeliveryApi()
    try:
        issue = read_client.fetch_issue(projection.repository, projection.issue_number)
    except GitHubIssuesError as exc:
        return _degrade_from_error(projection, exc)

    now = timezone.now()
    fields = {
        "projection_status",
        "observed_at",
        "issue_state",
        "issue_url",
        "last_error_code",
        "last_error_message",
        "updated_at",
    }
    if issue.state != _IState.UNKNOWN:
        projection.issue_state = issue.state
    if issue.url:
        projection.issue_url = issue.url

    if projection.pr_number:
        try:
            pull = read_client.fetch_pull_request(projection.repository, projection.pr_number)
            if pull.state != _PState.UNKNOWN:
                projection.pr_state = pull.state
                fields.add("pr_state")
            if pull.url:
                projection.pr_url = pull.url
                fields.add("pr_url")
            if pull.head_sha:
                projection.head_sha = pull.head_sha
                fields.add("head_sha")
            if pull.head_ref:
                projection.head_ref = pull.head_ref
                fields.add("head_ref")
            if pull.head_sha:
                projection.ci_state = read_client.fetch_check_state(
                    projection.repository, pull.head_sha
                )
                fields.add("ci_state")
        except GitHubIssuesError:
            # PR/CI é best-effort: a Issue foi confirmada, então a projeção é `current`. Um tropeço
            # aqui não deve degradar o todo — só não atualiza PR/CI nesta rodada.
            logger.warning("reconcile: PR/CI indisponível para %s", projection)

    projection.projection_status = _PStatus.CURRENT
    projection.observed_at = now
    projection.last_error_code = ""
    projection.last_error_message = ""
    projection.save(update_fields=list(fields))
    return projection


def _degrade_from_error(
    projection: GithubDeliveryProjection, exc: GitHubIssuesError
) -> GithubDeliveryProjection:
    status = github_issues.http_status_from_error(exc)
    if status == 404:
        return _mark_degraded(projection, _PStatus.REFERENCE_MISSING, "not_found", str(exc))
    if status in {401, 403}:
        return _mark_degraded(projection, _PStatus.PERMISSION_DENIED, "forbidden", str(exc))
    return _mark_degraded(projection, _PStatus.UNAVAILABLE, "github_http", str(exc))


def _mark_degraded(
    projection: GithubDeliveryProjection, status: str, code: str, message: str
) -> GithubDeliveryProjection:
    """Sinaliza a projeção como não confirmada, **sem** mexer em `observed_at`.

    `observed_at` é a última confirmação boa; mantê-lo é o que deixa a tela dizer "não conferimos
    agora, e a última vez foi há X". Os valores de engenharia já projetados ficam como estavam.
    """
    projection.projection_status = status
    projection.last_error_code = code[:64]
    projection.last_error_message = redact_secrets(message)[:_ERROR_MESSAGE_MAX]
    projection.save(
        update_fields=[
            "projection_status",
            "last_error_code",
            "last_error_message",
            "updated_at",
        ]
    )
    return projection
