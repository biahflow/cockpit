"""A projeção somente-leitura do estado de engenharia do GitHub (FDD 041, ADR 0046).

Duas entradas para o mesmo estado, e as duas são necessárias:

- **Webhook** (`POST /api/v1/github/webhook/`): o caminho rápido. Assinado, deduplicado por
  identidade de entrega e protegido contra reentrega fora de ordem.
- **Reconciliação** (`manage.py reconcile_github_projections`, no agendador): a rede de baixo.
  Entrega perdida, hook desligado por engano e janela de indisponibilidade do GitHub **só** se
  recuperam por releitura — um webhook que não chegou não avisa que não chegou.

O Pulse projeta; o GitHub decide (ADR 0040). Nada aqui escreve de volta, e `merge` não vira
`DONE` em lugar nenhum deste arquivo.
"""

from __future__ import annotations

import hmac
import logging
import re
from collections.abc import Mapping
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from hashlib import sha256

from django.conf import settings
from django.db import IntegrityError, transaction
from django.utils import timezone

from .github_issues import (
    CI_FAILURE,
    CI_NONE,
    CI_PENDING,
    CI_SUCCESS,
    GithubIssuesApi,
    GitHubIssuesError,
    GithubReadClient,
    aggregate_check_runs,
    http_status_from_error,
    parse_github_datetime,
)
from .models import EngineeringHandoff, GithubDelivery, GithubProjection

logger = logging.getLogger(__name__)

SIGNATURE_HEADER = "X-Hub-Signature-256"
DELIVERY_HEADER = "X-GitHub-Delivery"
EVENT_HEADER = "X-GitHub-Event"

# Os cinco tratados. Qualquer outro cai no 200 "ignorado" — um erro faria o GitHub reentregar em
# laço e, depois de uma sequência de respostas ruins, **desabilitar o hook**.
HANDLED_EVENTS = frozenset({"issues", "pull_request", "check_suite", "check_run", "status"})

# As palavras com que o GitHub liga um PR a uma Issue. Ligar por convenção de nome de branch
# seria adivinhar; estas são o mecanismo que o próprio fornecedor documenta.
_CLOSING_KEYWORDS = re.compile(
    r"(?i)\b(?:close[sd]?|fix(?:e[sd])?|resolve[sd]?)\s*:?\s+"
    r"(?:(?P<repo>[\w.\-]+/[\w.\-]+))?#(?P<number>\d+)"
)

_STATUS_TO_CI = {
    "success": CI_SUCCESS,
    "pending": CI_PENDING,
    "failure": CI_FAILURE,
    "error": CI_FAILURE,
}


class NotConfigured(Exception):
    """Sem `GITHUB_WEBHOOK_SECRET`. Falha fechada: não se aceita o que não se verifica."""


def is_configured() -> bool:
    return bool(str(getattr(settings, "GITHUB_WEBHOOK_SECRET", "") or "").strip())


def verify_signature(body: bytes, headers: Mapping[str, str]) -> bool:
    """HMAC-SHA256 do **corpo cru** contra `X-Hub-Signature-256`.

    Duas coisas do esquema do Stripe (`payments.py`) **não** foram copiadas, e não por descuido:

    - **Tolerância de timestamp.** O header do GitHub não carrega carimbo nenhum, então não há o
      que tolerar. O que fecha a janela de replay aqui é outra coisa: `X-GitHub-Delivery` é
      único, e uma entrega capturada e reenviada bate na unicidade de `GithubDelivery`.
    - **Múltiplas assinaturas.** Lá elas existem porque o Stripe manda dois `v1` durante a
      rotação de segredo; o GitHub manda exatamente uma. Aceitar uma lista aqui seria carregar
      complexidade que o fornecedor não produz.
    """
    secret = str(getattr(settings, "GITHUB_WEBHOOK_SECRET", "") or "").strip()
    if not secret:
        raise NotConfigured
    provided = headers.get(SIGNATURE_HEADER, "") or headers.get(SIGNATURE_HEADER.lower(), "")
    prefixo, _, assinatura = provided.strip().partition("=")
    if prefixo.lower() != "sha256" or not assinatura:
        return False
    esperado = hmac.new(secret.encode(), body, sha256).hexdigest()
    return hmac.compare_digest(esperado, assinatura.strip().lower())


@dataclass(frozen=True)
class ProjectionEvent:
    """Um evento do GitHub já normalizado para o vocabulário da projeção.

    `issue_numbers`, `pr_numbers` e `match_sha` são os três caminhos até a linha que o evento
    descreve, em ordem de precisão: o número da Issue é o vínculo; o número do PR e o SHA são o
    que sobra quando o evento não fala de Issue nenhuma (é o caso de todo evento de CI).
    """

    repository: str
    source_updated_at: datetime | None
    issue_numbers: tuple[int, ...] = ()
    pr_numbers: tuple[int, ...] = ()
    match_sha: str = ""
    changes: dict[str, object] = field(default_factory=dict)


def linked_issue_numbers(text: str, repository: str) -> tuple[int, ...]:
    """Os números de Issue que o texto de um PR fecha, no **mesmo** repositório."""
    numeros: list[int] = []
    for achado in _CLOSING_KEYWORDS.finditer(text or ""):
        repo = (achado.group("repo") or "").strip().lower()
        if repo and repo != repository.strip().lower():
            continue
        numero = int(achado.group("number"))
        if numero not in numeros:
            numeros.append(numero)
    return tuple(numeros)


def parse_event(event: str, payload: dict) -> ProjectionEvent | None:
    """Payload bruto → `ProjectionEvent`, ou `None` quando não há o que projetar."""
    repositorio = str(((payload.get("repository") or {}).get("full_name")) or "").strip()
    if not repositorio:
        return None
    if event == "issues":
        return _parse_issues(repositorio, payload)
    if event == "pull_request":
        return _parse_pull_request(repositorio, payload)
    if event == "check_suite":
        return _parse_check_suite(repositorio, payload)
    if event == "check_run":
        return _parse_check_run(repositorio, payload)
    if event == "status":
        return _parse_status(repositorio, payload)
    return None


def _parse_issues(repositorio: str, payload: dict) -> ProjectionEvent | None:
    issue = payload.get("issue") or {}
    numero = issue.get("number")
    estado = str(issue.get("state") or "").strip().lower()
    if not isinstance(numero, int) or isinstance(numero, bool) or estado not in {"open", "closed"}:
        return None
    return ProjectionEvent(
        repository=repositorio,
        source_updated_at=parse_github_datetime(issue.get("updated_at")),
        issue_numbers=(numero,),
        changes={"issue_state": estado, "issue_title": str(issue.get("title") or "")[:255]},
    )


def _parse_pull_request(repositorio: str, payload: dict) -> ProjectionEvent | None:
    pr = payload.get("pull_request") or {}
    numero = pr.get("number")
    if not isinstance(numero, int) or isinstance(numero, bool):
        return None
    estado = str(pr.get("state") or "").strip().lower()
    if pr.get("merged"):
        projetado = GithubProjection.PrState.MERGED
    elif estado == "open":
        projetado = GithubProjection.PrState.OPEN
    elif estado == "closed":
        projetado = GithubProjection.PrState.CLOSED
    else:
        return None
    cabeca = pr.get("head") or {}
    texto = f"{pr.get('title') or ''}\n{pr.get('body') or ''}"
    return ProjectionEvent(
        repository=repositorio,
        source_updated_at=parse_github_datetime(pr.get("updated_at")),
        issue_numbers=linked_issue_numbers(texto, repositorio),
        pr_numbers=(numero,),
        changes={
            "pr_number": numero,
            "pr_state": projetado,
            "head_sha": str(cabeca.get("sha") or "")[:40],
        },
    )


def _parse_check_suite(repositorio: str, payload: dict) -> ProjectionEvent | None:
    suite = payload.get("check_suite") or {}
    sha = str(suite.get("head_sha") or "").strip()
    if not sha:
        return None
    ci = aggregate_check_runs(
        [
            (
                str(suite.get("status") or "").strip().lower(),
                str(suite.get("conclusion") or "").strip().lower(),
            )
        ]
    )
    return ProjectionEvent(
        repository=repositorio,
        source_updated_at=parse_github_datetime(suite.get("updated_at")),
        pr_numbers=_pull_request_numbers(suite.get("pull_requests")),
        match_sha=sha,
        changes={"ci_state": ci},
    )


def _parse_check_run(repositorio: str, payload: dict) -> ProjectionEvent | None:
    """Um check run **não** promove o conjunto a verde, e só ele tem essa assimetria.

    Um job que passou não diz nada sobre os outros doze; um que reprovou, ou que ainda está
    rodando, já basta para o conjunto não estar verde. Quem afirma "tudo passou" é o
    `check_suite`, que é o evento agregado — e é dele que o verde sai.
    """
    run = payload.get("check_run") or {}
    sha = str(run.get("head_sha") or "").strip()
    if not sha:
        return None
    ci = aggregate_check_runs(
        [
            (
                str(run.get("status") or "").strip().lower(),
                str(run.get("conclusion") or "").strip().lower(),
            )
        ]
    )
    mudancas: dict[str, object] = {} if ci in {CI_SUCCESS, CI_NONE} else {"ci_state": ci}
    return ProjectionEvent(
        repository=repositorio,
        source_updated_at=parse_github_datetime(run.get("completed_at") or run.get("started_at")),
        pr_numbers=_pull_request_numbers(run.get("pull_requests")),
        match_sha=sha,
        changes=mudancas,
    )


def _parse_status(repositorio: str, payload: dict) -> ProjectionEvent | None:
    sha = str(payload.get("sha") or "").strip()
    ci = _STATUS_TO_CI.get(str(payload.get("state") or "").strip().lower())
    if not sha or ci is None:
        return None
    return ProjectionEvent(
        repository=repositorio,
        source_updated_at=parse_github_datetime(payload.get("updated_at")),
        match_sha=sha,
        changes={"ci_state": ci},
    )


def _pull_request_numbers(raw: object) -> tuple[int, ...]:
    if not isinstance(raw, list):
        return ()
    numeros: list[int] = []
    for item in raw:
        numero = item.get("number") if isinstance(item, dict) else None
        if isinstance(numero, int) and not isinstance(numero, bool):
            numeros.append(numero)
    return tuple(numeros)


# --- Aplicação -----------------------------------------------------------------


@dataclass(frozen=True)
class DeliveryResult:
    detail: str
    duplicate: bool = False
    applied: int = 0
    discarded: int = 0


def receive(event: str, delivery_id: str, payload: dict) -> DeliveryResult:
    """Registra a entrega e aplica o evento, **na mesma transação**.

    Os dois níveis de idempotência que a ADR 0037 pede vivem aqui e no `_apply_to`:

    1. **Por identidade de entrega.** `X-GitHub-Delivery` é único; a reentrega bate na unicidade
       e vira no-op. É o nível que os webhooks anteriores deste repositório não têm — eles
       deduplicam por *igualdade de estado*, o que resolve a reentrega idêntica e não resolve
       nem a reentrega atrasada nem o replay de uma entrega capturada.
    2. **Por ordem.** Um evento mais velho que o já persistido é descartado (ver `_apply_to`).

    Registrar e aplicar na mesma transação é o que impede a pior combinação: entrega marcada
    como processada e efeito nenhum gravado, com o GitHub sem motivo para reentregar.
    """
    if event not in HANDLED_EVENTS:
        return DeliveryResult(detail="Evento ignorado.")
    try:
        with transaction.atomic():
            GithubDelivery.objects.create(delivery_id=delivery_id, event=event)
            resultado = _apply(event, payload)
    except IntegrityError:
        if GithubDelivery.objects.filter(delivery_id=delivery_id).exists():
            logger.info("webhook do GitHub: entrega %s já processada", delivery_id)
            return DeliveryResult(detail="Entrega já processada.", duplicate=True)
        raise
    return resultado


def _apply(event: str, payload: dict) -> DeliveryResult:
    parsed = parse_event(event, payload)
    if parsed is None:
        return DeliveryResult(detail="Evento ignorado.")
    alvos = _targets(parsed)
    if not alvos:
        return DeliveryResult(detail="Nenhuma referência correspondente.")
    aplicados = descartados = 0
    for projecao in alvos:
        if _apply_to(projecao, parsed):
            aplicados += 1
        else:
            descartados += 1
    if aplicados:
        return DeliveryResult(detail="Projeção atualizada.", applied=aplicados, discarded=descartados)
    return DeliveryResult(detail="Entrega fora de ordem descartada.", discarded=descartados)


def _targets(event: ProjectionEvent) -> list[GithubProjection]:
    """A(s) linha(s) que o evento descreve.

    **Só um evento que observou o estado da Issue cria projeção.** Um `pull_request` ou um
    `check_suite` sabem do PR e do CI e não sabem se a Issue está aberta — criar a linha a partir
    deles carimbaria o default do modelo como se fosse observação, e é justamente isso que o
    painel não pode fazer. Quem cria o que falta sem webhook é a reconciliação, que lê.
    """
    base = GithubProjection.objects.select_related("handoff").filter(
        handoff__repository__iexact=event.repository, handoff__archived_at__isnull=True
    )
    if event.issue_numbers:
        existentes = list(base.filter(handoff__github_issue_number__in=event.issue_numbers))
        if "issue_state" in event.changes:
            conhecidos = {projecao.handoff.github_issue_number for projecao in existentes}
            for numero in event.issue_numbers:
                if numero in conhecidos:
                    continue
                criada = _create_for_issue(event.repository, numero)
                if criada is not None:
                    existentes.append(criada)
        if existentes:
            return existentes
    if event.pr_numbers:
        por_pr = list(base.filter(pr_number__in=event.pr_numbers))
        if por_pr:
            return por_pr
    if event.match_sha:
        return list(base.filter(head_sha=event.match_sha))
    return []


def _create_for_issue(repository: str, number: int) -> GithubProjection | None:
    handoff = EngineeringHandoff.objects.filter(
        repository__iexact=repository,
        github_issue_number=number,
        archived_at__isnull=True,
        projection__isnull=True,
    ).first()
    if handoff is None:
        return None
    return GithubProjection.objects.create(handoff=handoff, observed_at=timezone.now())


def _apply_to(projection: GithubProjection, event: ProjectionEvent) -> bool:
    """Grava o evento na projeção, ou o descarta por ser mais velho que o que já está lá.

    **A reentrega atrasada é o defeito que esta função existe para impedir.** O GitHub entrega
    ao menos uma vez e não garante ordem: um `pull_request` de dez minutos atrás pode chegar
    depois do de agora, carregando o SHA anterior. Sem esta guarda, o painel mostraria com
    confiança um `head` que já não é o `head` — que é exatamente a afirmação que o DAP GH-41
    proíbe.
    """
    anterior = projection.source_updated_at
    if anterior and event.source_updated_at and event.source_updated_at < anterior:
        logger.info(
            "webhook do GitHub fora de ordem descartado ref=%s evento=%s persistido=%s",
            projection.reference,
            event.source_updated_at.isoformat(),
            anterior.isoformat(),
        )
        return False

    campos: list[str] = []
    for campo, valor in event.changes.items():
        # SHA novo apaga o CI do SHA velho. Sem isto o painel mostraria o verde da revisão
        # anterior ao lado do endereço da nova — um selo certo sobre a coisa errada.
        if campo == "head_sha" and valor and valor != projection.head_sha:
            projection.ci_state = GithubProjection.CiState.NONE
            campos.append("ci_state")
        setattr(projection, campo, valor)
        campos.append(campo)

    projection.observed_at = timezone.now()
    projection.observed_via = GithubProjection.ObservedVia.WEBHOOK
    projection.last_error_kind = ""
    projection.last_error_at = None
    if event.source_updated_at:
        projection.source_updated_at = event.source_updated_at
    projection.save(
        update_fields=[
            *dict.fromkeys(campos),
            "observed_at",
            "observed_via",
            "last_error_kind",
            "last_error_at",
            "source_updated_at",
            "updated_at",
        ]
    )
    return True


# --- Reconciliação -------------------------------------------------------------


@dataclass(frozen=True)
class ReconcileReport:
    created: int = 0
    refreshed: int = 0
    failed: int = 0
    skipped: int = 0

    def __str__(self) -> str:
        return (
            f"projeções: {self.created} criada(s), {self.refreshed} atualizada(s), "
            f"{self.failed} com erro, {self.skipped} ainda fresca(s)"
        )


def error_kind_for(exc: GitHubIssuesError) -> str:
    """Os três erros do painel, separados pela **ação corretiva** e não pela severidade.

    GitHub fora do ar passa sozinho; permissão negada exige alguém mexer no token; referência
    ausente exige consertar o vínculo. Uma copy única esconderia a diferença que decide quem age.
    """
    status = http_status_from_error(exc)
    if status in {401, 403}:
        return GithubProjection.ErrorKind.FORBIDDEN
    if status == 404:
        return GithubProjection.ErrorKind.MISSING
    return GithubProjection.ErrorKind.UNAVAILABLE


def reconcile(
    client: GithubReadClient | None = None, now: datetime | None = None
) -> ReconcileReport:
    """Relê no GitHub o que envelheceu, e cria a projeção que nunca chegou por webhook."""
    agora = now or timezone.now()
    if client is None:
        client = GithubIssuesApi()

    criadas = atualizadas = falhas = 0

    for handoff in _handoffs_without_projection():
        if _refresh(GithubProjection(handoff=handoff, observed_at=agora), client, agora, novo=True):
            criadas += 1
        else:
            falhas += 1

    vivas, envelhecidas = _projections_to_refresh(agora)
    for projecao in envelhecidas:
        if _refresh(projecao, client, agora, novo=False):
            atualizadas += 1
        else:
            falhas += 1

    return ReconcileReport(
        created=criadas,
        refreshed=atualizadas,
        failed=falhas,
        skipped=vivas - len(envelhecidas),
    )


def _handoffs_without_projection() -> list[EngineeringHandoff]:
    return list(
        EngineeringHandoff.objects.filter(
            status=EngineeringHandoff.Status.PROVISIONED,
            archived_at__isnull=True,
            github_issue_number__isnull=False,
            projection__isnull=True,
        ).exclude(repository="")
    )


def _projections_to_refresh(now: datetime) -> tuple[int, list[GithubProjection]]:
    """As projeções que envelheceram, e quantas existem ao todo.

    O recorte é o **mesmo limiar** que a tela usa para dizer "obsoleto", e de propósito: se a
    reconciliação usasse um número próprio, existiria uma janela em que o painel diz que não sabe
    mais e o job ainda acha cedo para reler. Limiar zero desliga a regra e faz a reconciliação
    reler tudo a cada tique — não é o default, e não deveria ser o de nenhuma instalação viva.
    """
    base = GithubProjection.objects.select_related("handoff").filter(
        handoff__archived_at__isnull=True
    )
    total = base.count()
    limiar = int(getattr(settings, "GITHUB_PROJECTION_STALE_AFTER_SECONDS", 0) or 0)
    if limiar <= 0:
        return total, list(base)
    return total, list(base.filter(observed_at__lt=now - timedelta(seconds=limiar)))


def _refresh(
    projection: GithubProjection,
    client: GithubReadClient,
    now: datetime,
    *,
    novo: bool,
) -> bool:
    """Uma releitura. Devolve se ela produziu estado observado.

    **Erro nunca apaga a projeção anterior.** Numa projeção que já existe, a falha só carimba
    `last_error_kind`/`last_error_at` — os campos de estado continuam valendo como último estado
    conhecido, e a tela passa a tratá-los como tal. Numa projeção que ainda não existe, a falha
    **não cria linha**: uma linha sem estado observado mostraria os defaults do modelo como se
    fossem observação, que é a única coisa que este painel não pode fazer.
    """
    repositorio = projection.handoff.repository
    numero = projection.handoff.github_issue_number or 0
    try:
        issue = client.get_issue(repositorio, numero)
        carimbos = [issue.updated_at]
        if projection.pr_number:
            pr = client.get_pull_request(repositorio, projection.pr_number)
            projection.pr_state = _pr_state(pr.state, pr.merged)
            if pr.head_sha:
                projection.head_sha = pr.head_sha[:40]
            carimbos.append(pr.updated_at)
        if projection.head_sha:
            projection.ci_state = client.get_check_state(repositorio, projection.head_sha)
    except GitHubIssuesError as exc:
        return _record_error(projection, exc, now, novo=novo)

    if issue.state in {GithubProjection.IssueState.OPEN, GithubProjection.IssueState.CLOSED}:
        projection.issue_state = issue.state
    if issue.title:
        projection.issue_title = issue.title[:255]
    projection.observed_at = now
    projection.observed_via = GithubProjection.ObservedVia.RECONCILIATION
    projection.last_error_kind = ""
    projection.last_error_at = None
    # `max` e não atribuição: baixar o carimbo reabriria a janela que a guarda de ordem fecha —
    # um webhook antigo voltaria a parecer novo.
    projection.source_updated_at = max(
        [carimbo for carimbo in [*carimbos, projection.source_updated_at] if carimbo],
        default=None,
    )
    projection.save()
    return True


def _record_error(
    projection: GithubProjection, exc: GitHubIssuesError, now: datetime, *, novo: bool
) -> bool:
    kind = error_kind_for(exc)
    logger.warning(
        "reconciliação do GitHub falhou ref=%s motivo=%s",
        projection.reference,
        kind,
    )
    if novo:
        return False
    projection.last_error_kind = kind
    projection.last_error_at = now
    projection.save(update_fields=["last_error_kind", "last_error_at", "updated_at"])
    return False


def _pr_state(state: str, merged: bool) -> str:
    if merged:
        return GithubProjection.PrState.MERGED
    if state == "open":
        return GithubProjection.PrState.OPEN
    return GithubProjection.PrState.CLOSED
