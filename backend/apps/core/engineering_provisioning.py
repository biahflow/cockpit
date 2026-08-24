"""Provisiona uma GitHub Issue a partir de um EngineeringHandoff (FDD 040).

Idempotente e fail-closed: não cria segunda Issue quando o handoff já tem número, reconcilia a
janela 201-sem-persistir via busca pelo Pulse-Handoff-ID, e nunca marca `provisioned` sem number
e URL. HTTP fica fora de `transaction.atomic` longo. Zero LLM.
"""

from __future__ import annotations

from django.conf import settings
from django.utils import timezone

from . import flags
from .github_issues import (
    GithubIssuesApi,
    GitHubIssuesClient,
    GitHubIssuesError,
    IssueDraft,
    IssueRef,
    redact_secrets,
)
from .models import EngineeringHandoff

_ERROR_MESSAGE_MAX = 2000


def is_enabled() -> bool:
    return flags.is_enabled("github_provisioning")


def provision(
    handoff: EngineeringHandoff, client: GitHubIssuesClient | None = None
) -> EngineeringHandoff:
    if (
        handoff.status == EngineeringHandoff.Status.PROVISIONED
        and handoff.github_issue_number
    ):
        return handoff
    if not is_enabled():
        return _mark_failed(handoff, "disabled", "Provisionamento GitHub desativado.")
    repository = (handoff.repository or "").strip() or str(settings.GITHUB_REPO or "").strip()
    if not repository:
        return _mark_failed(handoff, "missing_repo", "Repositório GitHub não configurado.")
    if client is None:
        client = GithubIssuesApi()

    handoff.attempt_count += 1
    handoff.last_attempt_at = timezone.now()
    handoff.save(update_fields=["attempt_count", "last_attempt_at", "updated_at"])

    draft = _draft_from(handoff, repository)
    try:
        found = client.find_by_handoff_id(repository, handoff.pulse_work_item_id)
        ref = found if found is not None else client.create_issue(draft)
    except GitHubIssuesError as exc:
        return _mark_failed(handoff, "github_http", str(exc))
    return _mark_provisioned(handoff, ref, repository)


def _draft_from(handoff: EngineeringHandoff, repository: str) -> IssueDraft:
    return IssueDraft(
        title=handoff.title,
        objective=handoff.objective,
        context=handoff.context,
        acceptance_criteria=handoff.acceptance_criteria,
        scope=handoff.scope_text,
        out_of_scope=handoff.out_of_scope_text,
        repository=repository,
        milestone_ref=handoff.milestone_ref,
        adr_refs=_as_str_list(handoff.adr_refs),
        nfr_refs=_as_str_list(handoff.nfr_refs),
        fdd_refs=_as_str_list(handoff.fdd_refs),
        pulse_work_item_id=handoff.pulse_work_item_id,
        pulse_project_id=str(handoff.project_id),
        correlation_id=str(handoff.correlation_id),
    )


def _as_str_list(value: object) -> list[str]:
    if not isinstance(value, list):
        return []
    return [str(item) for item in value]


def _mark_provisioned(
    handoff: EngineeringHandoff, ref: IssueRef, repository: str
) -> EngineeringHandoff:
    handoff.repository = repository
    handoff.github_issue_number = ref.number
    handoff.github_issue_url = ref.url
    handoff.github_node_id = ref.node_id
    handoff.status = EngineeringHandoff.Status.PROVISIONED
    handoff.last_error_code = ""
    handoff.last_error_message = ""
    handoff.save(
        update_fields=[
            "repository",
            "github_issue_number",
            "github_issue_url",
            "github_node_id",
            "status",
            "last_error_code",
            "last_error_message",
            "updated_at",
        ]
    )
    return handoff


def _mark_failed(handoff: EngineeringHandoff, code: str, message: str) -> EngineeringHandoff:
    handoff.status = EngineeringHandoff.Status.FAILED
    handoff.last_error_code = code[:64]
    handoff.last_error_message = redact_secrets(message)[:_ERROR_MESSAGE_MAX]
    handoff.save(
        update_fields=["status", "last_error_code", "last_error_message", "updated_at"]
    )
    return handoff
