"""A escada FDE da conta: materialização, transição e o recorte da visão geral (FDD 042).

**A guarda mora aqui, e não na view** (FDD 033). Quem concluir, pular ou bloquear um degrau por
qualquer caminho tem de passar pelas mesmas recusas; uma guarda escrita na view só vale para a
rota que a chamou — foi por isso que o decision gate da jornada acabou em `journey.py`, e este
módulo é o mesmo molde para o eixo da conta.

O que **não** mora aqui, e não por esquecimento: nenhuma regra que equipare `PR merged` a `DONE`.
Um degrau só fecha por decisão de gate registrada (`docs/metodologia-fde.md:42-48`), e a Issue #42
exclui explicitamente *"automatic phase transitions driven only by PR merge"*. Não existe caminho
automático para `done` neste módulo: toda transição carrega um autor.

`StateConflict` vem de `exceptions`, que não importa nada do domínio — é o que mantém este módulo
importável sem request (`views` importa `ladder`; o contrário fecharia o ciclo).
"""

from __future__ import annotations

from datetime import timedelta
from typing import TYPE_CHECKING, Any

from django.conf import settings
from django.db import transaction
from django.utils import timezone

from .exceptions import StateConflict

if TYPE_CHECKING:
    from .models import AccountRung, Client, User

# Os degraus que a conta pode estar *vivendo agora*. Um degrau nestes três estados é o que faz a
# conta aparecer na visão geral e é sobre ele que se conta o tempo parado.
OPEN_STATUSES = ("active", "blocked", "awaiting_gate")

# Teto de linhas do bloco compacto da visão geral (superfície B). Constante nomeada, e não um
# `[:8]` solto: o número é decisão operacional declarada, não detalhe de fatiamento.
ACCOUNT_LADDER_LIMIT = 8


def rung_positions() -> dict[str, int]:
    """Posição de cada degrau na doutrina. Deriva de `FdeRung`, nunca de uma lista digitada."""
    from .models import FdeRung

    return {value: index for index, value in enumerate(FdeRung.values)}


def materialize_ladder(client: Client) -> None:
    """Cria os seis degraus `not_sold` da conta. Idempotente.

    No molde de `journey.materialize_journey`: seguro para chamada defensiva na leitura de contas
    antigas. **Não emite evento** — de propósito. Materializar não é uma decisão sobre a conta, e
    seis linhas de "não vendido" no histórico afogariam a primeira transição de verdade, que é
    justamente o que a gaveta existe para mostrar. É também o que sustenta a copy do degrau não
    vendido: *"Nenhuma decisão registrada"*.
    """
    from .models import AccountRung, FdeRung

    existentes = set(
        AccountRung.objects.filter(client=client).values_list("rung", flat=True)
    )
    faltando = [value for value in FdeRung.values if value not in existentes]
    if not faltando:
        return
    AccountRung.objects.bulk_create(
        [
            AccountRung(client=client, rung=value, status=AccountRung.Status.NOT_SOLD)
            for value in faltando
        ],
        ignore_conflicts=True,  # duas leituras concorrentes não podem virar 500
    )


def _assert_skip_is_legitimate(rung: AccountRung, skip_reason: str) -> None:
    """Só o Feasibility se pula, e nunca em silêncio (`docs/metodologia-fde.md:38-40`).

    A opcionalidade é do Feasibility e de mais nenhum: *"entra somente quando há dúvida se a
    tecnologia sustenta a tarefa"*. Pular Prove ou Scale não é uma decisão prevista pela
    metodologia — é a escada deixando de ser a escada.

    E o motivo é obrigatório porque é ele que separa *pulada* de *não vendido*: sem motivo, autor e
    carimbo, o degrau pulado vira um degrau que ninguém sabe se foi decidido.
    """
    from .models import FdeRung

    if rung.rung != FdeRung.FEASIBILITY:
        raise StateConflict(
            f"Só o degrau {FdeRung.FEASIBILITY.label} pode ser pulado — a condicionalidade é dele "
            "e de mais nenhum na metodologia FDE."
        )
    if not skip_reason.strip():
        raise StateConflict(
            "Pular o Feasibility exige o motivo registrado: é ele que distingue um degrau "
            "**pulado por decisão** de um degrau que simplesmente não foi vendido."
        )


@transaction.atomic
def transition(
    rung: AccountRung,
    *,
    to_status: str,
    by: User | None,
    note: str = "",
    waiting_on: str | None = None,
    blocker: str | None = None,
    skip_reason: str | None = None,
    opportunity: Any = ...,
    project: Any = ...,
) -> AccountRung:
    """Move o degrau e **grava o evento**. É o único caminho de escrita da escada.

    O evento é append-only: cancelar ou replanejar não apaga a transição anterior nem as datas em
    que o degrau esteve ativo — vira mais uma linha. É o que a Issue #42 pede quando fala em
    *"history with timestamps/provenance rather than only the latest label"*.

    Recusa a transição para o mesmo estado: um evento `ativo → ativo` diria que algo aconteceu sem
    dizer o quê, e é assim que um histórico deixa de ser lido.
    """
    from .models import AccountRung, AccountRungEvent

    valores = set(AccountRung.Status.values)
    if to_status not in valores:
        raise StateConflict(f"Estado de degrau desconhecido: {to_status!r}.")
    if to_status == rung.status:
        raise StateConflict(
            f"Este degrau já está em “{rung.get_status_display()}”. Uma transição para o mesmo "
            "estado não registra o que mudou."
        )

    if to_status == AccountRung.Status.SKIPPED:
        _assert_skip_is_legitimate(rung, skip_reason or "")
    if to_status == AccountRung.Status.BLOCKED and not (blocker or rung.blocker).strip():
        raise StateConflict(
            "Bloquear um degrau exige dizer o quê: o impedimento precisa ser legível na escada, "
            "sem abrir nota nenhuma."
        )

    now = timezone.now()
    anterior = rung.status
    campos = ["status", "updated_at"]
    rung.status = to_status

    if waiting_on is not None:
        rung.waiting_on = waiting_on
        campos.append("waiting_on")
    if blocker is not None:
        rung.blocker = blocker
        campos.append("blocker")
    if opportunity is not ...:
        rung.opportunity = opportunity
        campos.append("opportunity")
    if project is not ...:
        rung.project = project
        campos.append("project")

    # Um degrau que passa a existir de fato ganha `started_at` uma vez e não o perde: o "esteve
    # ativo de X a Y" do estado replanejado depende de a data sobreviver ao cancelamento.
    if to_status in OPEN_STATUSES and rung.started_at is None:
        rung.started_at = now
        campos.append("started_at")
    if to_status in {AccountRung.Status.DONE, AccountRung.Status.CANCELLED}:
        rung.completed_at = now
        campos.append("completed_at")
    if to_status == AccountRung.Status.SKIPPED:
        rung.skip_reason = (skip_reason or "").strip()
        rung.skipped_by = by
        rung.skipped_at = now
        campos += ["skip_reason", "skipped_by", "skipped_at"]

    rung.save(update_fields=sorted(set(campos)))
    AccountRungEvent.objects.create(
        rung=rung, from_status=anterior, to_status=to_status, at=now, by=by, note=note
    )
    return rung


def days_stalled(rung: AccountRung, *, now: Any = None) -> int | None:
    """Há quantos dias o degrau não se mexe. `None` quando nunca houve transição.

    **Calculado aqui e não no SPA**, e a razão é a de sempre nesta casa: duas definições de "parado"
    divergem em silêncio, e esta roteia a atenção de quem varre a carteira. É aritmética sobre o
    último evento — determinística, sem token de modelo (a seção FinOps da Issue #42 proíbe gastar
    modelo nisto).
    """
    # `.all()` e não `.order_by(...)`: o segundo monta uma queryset nova e **fura o
    # `prefetch_related`**, de modo que ler seis degraus custaria seis consultas a mais por conta.
    # A ordem já é a do `Meta` do evento (`at`, `id`), então o último da lista é o mais recente.
    eventos = list(rung.events.all())
    if not eventos:
        return None
    return max((now or timezone.now()) - eventos[-1].at, timedelta(0)).days


def is_stale(dias: int | None) -> bool:
    """Passou do limiar declarado (`ACCOUNT_RUNG_STALE_AFTER_DAYS`, padrão 14)."""
    return dias is not None and dias >= settings.ACCOUNT_RUNG_STALE_AFTER_DAYS


def current_rung(rungs: list[AccountRung]) -> AccountRung | None:
    """O degrau que a conta está vivendo — o primeiro em aberto, na ordem da doutrina."""
    return next((rung for rung in rungs if rung.status in OPEN_STATUSES), None)


def account_ladder_rows(user: User) -> list[dict[str, Any]]:
    """O bloco compacto da visão geral (superfície B): uma linha por conta **em aberto**.

    Só as contas que estão vivendo um degrau — ativo, bloqueado ou aguardando gate. Conta sem
    degrau em aberto não é uma linha em branco: é uma conta que não pede nada de ninguém agora.

    **Ordenada por tempo parado, decrescente, com teto de `ACCOUNT_LADDER_LIMIT`.** As duas coisas
    são decisão operacional declarada (FDD 042): a visão geral serve para varrer a carteira e agir
    sobre o que travou, não para listar tudo — uma lista completa aqui empurraria a linha que
    importa para baixo da dobra.

    O recorte da Entrega vem de `project_scope_q`, derivado de `visible_to` — a regra nunca é
    reescrita (RFC 0003, ADR 0010). A linha não carrega conteúdo comercial nenhum: nome da conta,
    degrau, de quem é a bola e há quanto tempo está parada.
    """
    from .models import AccountRung, Client, project_scope_q

    scope = project_scope_q(user, "projects")
    clients = Client.objects.filter(archived_at__isnull=True)
    if scope:
        clients = clients.filter(scope).distinct()

    posicoes = rung_positions()
    por_conta: dict[int, list[AccountRung]] = {}
    for rung in (
        AccountRung.objects.filter(client__in=clients.values("pk"))
        .select_related("client")
        .prefetch_related("events")
    ):
        por_conta.setdefault(rung.client_id, []).append(rung)

    now = timezone.now()
    linhas: list[dict[str, Any]] = []
    for degraus in por_conta.values():
        degraus.sort(key=lambda rung: posicoes.get(rung.rung, 0))
        atual = current_rung(degraus)
        if atual is None:
            continue
        dias = days_stalled(atual, now=now)
        linhas.append({
            "client_id": atual.client_id,
            "client_name": atual.client.name,
            "rung": atual.rung,
            "rung_display": atual.get_rung_display(),
            "status": atual.status,
            "status_display": atual.get_status_display(),
            "waiting_on": atual.waiting_on,
            "waiting_on_display": (
                AccountRung.WaitingOn(atual.waiting_on).label if atual.waiting_on else ""
            ),
            "days_stalled": dias,
            "is_stale": is_stale(dias),
            # Só a **forma** da escada: o SPA traduz estado em variante de `.timeline-step`, e o
            # backend não nomeia classe de CSS. Uma segunda definição de "concluído" — uma em
            # Python, outra em TypeScript — diverge da primeira em silêncio (ADR 0026).
            "steps": [
                {"rung": rung.rung, "rung_display": rung.get_rung_display(), "status": rung.status}
                for rung in degraus
            ],
        })
    linhas.sort(key=lambda linha: (-(linha["days_stalled"] or 0), linha["client_name"]))
    return linhas[:ACCOUNT_LADDER_LIMIT]
