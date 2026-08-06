"""Sincronia bidirecional de tarefas com Linear/GitHub (ADR 0004), atrás de flag.

O Biahflow é a fonte da verdade. A ENTRADA (webhook do fornecedor → Biahflow) atualiza o
status de uma `Task` vinculada por `(source, external_id)`. A SAÍDA (Biahflow → fornecedor)
atualiza/cria a issue quando a tarefa vinculada muda. Um guard de eco (`suppress_outbound`)
evita o loop entrada→save→saída→fornecedor→entrada.

De-para de status explícito (o ADR exige não perder informação). As chamadas HTTP reais
seguem o padrão do `portal.py` (`urllib`, entrega assíncrona best-effort) e ficam fora da
cobertura (`# pragma: no cover`).
"""

from __future__ import annotations

import contextvars
import json
import logging
import threading
import urllib.error
import urllib.request
from collections.abc import Iterator
from contextlib import contextmanager

from django.conf import settings
from django.db import transaction

from . import flags, notifications
from .models import Task

logger = logging.getLogger(__name__)

SOURCES = ("linear", "github")

_suppress: contextvars.ContextVar[bool] = contextvars.ContextVar("tasksync_suppress", default=False)


def is_enabled() -> bool:
    return flags.is_enabled("tasksync")


@contextmanager
def suppress_outbound() -> Iterator[None]:
    """Suprime a saída durante a aplicação da entrada (evita eco/loop)."""
    token = _suppress.set(True)
    try:
        yield
    finally:
        _suppress.reset(token)


def outbound_suppressed() -> bool:
    return _suppress.get()


def eligible(task: Task) -> bool:
    return task.source in SOURCES and bool(task.external_id)


# --- De-para de status -------------------------------------------------------

_GITHUB_INBOUND = {
    "open": Task.Status.TODO,
    "reopened": Task.Status.TODO,
    "closed": Task.Status.DONE,
}
_LINEAR_INBOUND = {
    "backlog": Task.Status.TODO,
    "unstarted": Task.Status.TODO,
    "todo": Task.Status.TODO,
    "started": Task.Status.IN_PROGRESS,
    "in_progress": Task.Status.IN_PROGRESS,
    "completed": Task.Status.DONE,
    "done": Task.Status.DONE,
    "canceled": Task.Status.DONE,
}


def inbound_status(source: str, external_status: str) -> Task.Status | None:
    key = (external_status or "").strip().lower()
    table = _GITHUB_INBOUND if source == "github" else _LINEAR_INBOUND
    return table.get(key)


def outbound_state(source: str, status: str) -> str:
    if source == "github":
        return "closed" if status == Task.Status.DONE else "open"
    # Linear: state IDs são específicos do workspace e vêm do ambiente; vazio → no-op logado.
    linear_states: dict[str, str] = {
        Task.Status.TODO: settings.LINEAR_STATE_TODO,
        Task.Status.IN_PROGRESS: settings.LINEAR_STATE_IN_PROGRESS,
        Task.Status.DONE: settings.LINEAR_STATE_DONE,
    }
    return linear_states.get(status, "")


# --- Entrada (fornecedor → Biahflow) ----------------------------------------


def apply_inbound(source: str, external_id: str, external_status: str) -> Task | None:
    """Atualiza a Task vinculada. Retorna a Task, ou None se não houver vínculo.

    Levanta ValueError se o status externo não estiver no de-para (a view responde 422).
    """
    new_status = inbound_status(source, external_status)
    if new_status is None:
        raise ValueError("status externo desconhecido")
    task = Task.objects.filter(
        source=source, external_id=external_id, archived_at__isnull=True
    ).first()
    if task is None:
        return None
    if task.status != new_status:
        task.status = new_status
        with suppress_outbound():  # não repropagar para o fornecedor (evita eco)
            task.save(update_fields=["status", "completed_at", "updated_at"])
        if task.owner_id:
            notifications.notify(
                [task.owner],
                "task",
                f"Tarefa atualizada via {source}: {task.title}",
                f"/projetos/{task.project_id}",
                # O caminho que realmente vazava: isto dispara por webhook do fornecedor,
                # arbitrariamente depois da criação e sem `request.user` para consultar. Quem foi
                # removido da equipe continua `owner` da tarefa e seguia recebendo o título dela,
                # com um link que responde 404 (FDD 010, FDD 018).
                project=task.project,
            )
    return task


# --- Saída (Biahflow → fornecedor) ------------------------------------------


def push_update(task: Task) -> None:
    """Agenda a atualização da issue vinculada após o commit (best-effort, não bloqueante)."""
    if not is_enabled() or not eligible(task):
        return
    source, external_id = task.source, task.external_id
    state = outbound_state(source, task.status)
    transaction.on_commit(
        lambda: threading.Thread(
            target=_update_issue, args=(source, external_id, state), daemon=True
        ).start()
    )


def push_create(task: Task) -> str:
    """Cria a issue no fornecedor e retorna o `external_id`. Vazio se não configurado."""
    if not is_enabled():
        return ""
    return _create_issue(task.source, task)


def _update_issue(source: str, external_id: str, state: str) -> None:  # pragma: no cover - I/O
    if source == "github":
        if not settings.GITHUB_TOKEN or not settings.GITHUB_REPO:
            logger.info("GitHub não configurado; pulando update da issue %s", external_id)
            return
        _http(
            f"https://api.github.com/repos/{settings.GITHUB_REPO}/issues/{external_id}",
            {"state": state},
            {"Authorization": f"Bearer {settings.GITHUB_TOKEN}",
             "Accept": "application/vnd.github+json"},
            method="PATCH",
        )
        return
    if not settings.LINEAR_API_KEY or not state:
        logger.info("Linear não configurado (ou sem state id); pulando update de %s", external_id)
        return
    mutation = "mutation($id:String!,$state:String!){issueUpdate(id:$id,input:{stateId:$state}){success}}"
    _http(
        "https://api.linear.app/graphql",
        {"query": mutation, "variables": {"id": external_id, "state": state}},
        {"Authorization": settings.LINEAR_API_KEY},
        method="POST",
    )


def _create_issue(source: str, task: Task) -> str:  # pragma: no cover - I/O
    if source == "github":
        if not settings.GITHUB_TOKEN or not settings.GITHUB_REPO:
            return ""
        data = _http(
            f"https://api.github.com/repos/{settings.GITHUB_REPO}/issues",
            {"title": task.title, "body": task.description},
            {"Authorization": f"Bearer {settings.GITHUB_TOKEN}",
             "Accept": "application/vnd.github+json"},
            method="POST",
        )
        return str(data.get("number", "")) if data else ""
    if not settings.LINEAR_API_KEY or not settings.LINEAR_TEAM_ID:
        return ""
    mutation = (
        "mutation($teamId:String!,$title:String!,$description:String){"
        "issueCreate(input:{teamId:$teamId,title:$title,description:$description})"
        "{issue{id}}}"
    )
    data = _http(
        "https://api.linear.app/graphql",
        {"query": mutation,
         "variables": {"teamId": settings.LINEAR_TEAM_ID, "title": task.title,
                       "description": task.description}},
        {"Authorization": settings.LINEAR_API_KEY},
        method="POST",
    )
    try:
        return str(data["data"]["issueCreate"]["issue"]["id"]) if data else ""
    except (KeyError, TypeError):
        return ""


def _http(url: str, payload: dict, headers: dict, method: str) -> dict | None:  # pragma: no cover - I/O
    body = json.dumps(payload).encode()
    request = urllib.request.Request(
        url, data=body, method=method, headers={"Content-Type": "application/json", **headers}
    )
    try:
        with urllib.request.urlopen(request, timeout=5) as response:  # noqa: S310
            raw = response.read()
        return json.loads(raw) if raw else None
    except (urllib.error.URLError, TimeoutError, ValueError) as exc:
        logger.warning("Falha ao falar com o fornecedor de tarefas (%s): %s", url, exc)
        return None
