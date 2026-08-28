"""Integração com o portal do cliente (ADR 0003).

O Biahflow é a fonte da verdade do status do projeto. Aqui ficam os utilitários que
notificam o portal externo (webhook assinado) e que montam o snapshot read-only que o
portal consome para backfill/reconciliação. Nenhum dado comercial é exposto.

A única coisa que a linha acima precisa qualificar é `artifact_accepted_at` (emenda de
07/08/2026 na ADR 0003): o que sai é o **instante** da primeira aceitação do cliente, para o
funil de onboarding do portal — nunca `kind`, `title`, `content`, valor ou contagem. Nenhuma
das três coisas que a ADR nomeia (CommercialOpportunity, PipelineStage, valores) cruza; o que
cruza é a data em que o próprio cliente aprovou alguma coisa.

A segunda qualificação é o `rationale` das decisões (emenda de 12/08/2026 na ADR 0003, FDD 032).
Ele é **texto** e atravessa, o que contrasta de propósito com a `Pendencia`: dela sai título e
estado, e o `description` fica de fora. A assimetria tem motivo — uma pendência é um item de
acompanhamento, e uma decisão sem o porquê é um título. O porquê é justamente o que o cliente não
consegue reconstituir sozinho, e é o que ele volta para consultar meses depois. O limite continua
onde estava: sai o racional da decisão **publicada**, nunca o rascunho e nunca anotação interna.

Desde a ADR 0051 este módulo também **escreve**, e num lugar só: `emit` carimba
`projection_version`/`projection_observed_at` no projeto. É a inversão que o desenho exige —
quem muda o estado carimba, quem lê não —, e ela está escrita em detalhe no próprio `emit`.
"""

from __future__ import annotations

import hashlib
import hmac
import json
import logging
import threading
import urllib.error
import urllib.request
from typing import Any

from django.conf import settings
from django.db import transaction
from django.db.models import F, Min, Q
from django.utils import timezone

from . import flags, health, service_identity
from .models import (
    Artifact,
    Decisao,
    DigitalEmployee,
    Document,
    Meeting,
    Milestone,
    Pendencia,
    Project,
    ProjectPhase,
)

logger = logging.getLogger(__name__)

# Saúde interna → rótulo amigável + cor para o portal do cliente (sem expor score/sinais).
_HEALTH_LABEL: dict[str, tuple[str, str]] = {
    "saudável": ("No prazo", "green"),
    "atenção": ("Requer atenção", "amber"),
    "crítico": ("Atrasado", "red"),
}


def sign(secret: str, body: bytes) -> str:
    """Assinatura HMAC-SHA256 do corpo do webhook."""
    return hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()


def _doc_type(name: str) -> str:
    """Tipo do documento derivado da extensão (para o portal exibir PDF/Planilha/…)."""
    _, _, ext = name.rpartition(".")
    return ext.upper() if ext and ext != name else "Arquivo"


def _artifact_accepted_at(project: Project) -> str | None:
    """Quando este cliente aprovou um artefato pela **primeira** vez, ou ``None``.

    O degrau que faltava no funil de onboarding do portal (RFC 001 de lá). O `Artifact`
    guarda a jornada comercial e o docstring dele já dizia para que serve — *"permite medir
    onde a jornada trava entre uma etapa e a seguinte"* —, mas nada disso atravessava: nem
    o snapshot levava artefato, nem `signals.py` tinha receiver. Do outro lado o degrau
    estava declarado ausente no enum, com a razão escrita: *"ele entra quando o outro lado o
    afirmar"*.

    **Sai a data e nada mais** — nem `kind`, nem `title`, nem `content`, nem contagem, nem
    valor. O `content` é o texto comercial que a IA daqui redige e é dado interno da casa;
    o `kind` diria em que etapa do funil comercial o cliente está. O que o portal precisa é
    de um instante, e a linha do módulo acima ("nenhum dado comercial é exposto") continua
    valendo com a precisão de sempre: a data em que **o próprio cliente aprovou** alguma
    coisa é um fato dele sobre ele, e é o único que atravessa.

    Escopado pelo **cliente** e não pelo projeto, porque o funil de lá é por organização e
    um cliente pode ter vários projetos: os dois lados do vínculo do artefato (`project` e
    `commercial_opportunity`) chegam à mesma `Account`, e a aceitação do contrato quase sempre
    está no lado da oportunidade, antes de existir projeto algum.
    """
    first = Artifact.objects.filter(
        Q(project__client=project.client_id)
        | Q(commercial_opportunity__account=project.client_id),
        status=Artifact.Status.ACCEPTED,
        archived_at__isnull=True,
        decided_at__isnull=False,
    ).aggregate(first=Min("decided_at"))["first"]
    return first.isoformat() if first else None


def _journey(project: Project) -> list[dict[str, Any]]:
    """Fases da jornada de transformação do projeto, com seus entregáveis (ADR 0003).

    O portal do cliente usa `status` (locked/active/done) para montar o "Você está aqui" e
    para "desbloquear" os entregáveis fase a fase. Só o vocabulário da metodologia e o estado
    cruzam — nada técnico (tasks/PRs) vai para o cliente.

    Três chaves falam o vocabulário canônico (Issue #71, ADR 0051):

    * `canonical_stage` classifica a fase configurável sobre a escada FDE, e **vazio é
      legítimo** — é a fase operacional Biahflow sem equivalente (`Activation`), não dado
      faltando. Nenhum default é inventado aqui.
    * `requires_gate` vem do **template**, não da instância, e é ele que permite ao One
      distinguir "exige gate e ninguém decidiu" de "não tem gate": sem ele os dois casos são o
      mesmo `gate_decision` vazio.
    * `gate_decision` é o nome do D7, lido direto do campo canônico de `ProjectPhase` desde a
      ADR 0052 — antes dela era uma propriedade-alias, porque o campo ainda se chamava pelo nome
      antigo. A chave emitida nunca mudou, e é essa a razão de o alias ter existido: a projeção
      emite canônico porque *o One nunca renomeia* (`language-map` §3).

    **`situation` fica de fora, e isso é escolha.** Ela colapsa `waiting_party`, que é
    classificação interna de delivery ("estamos esperando engenharia") e não atravessa a
    fronteira do cliente (`language-map` §3). O One deriva o que precisa do par acima.
    """
    phases = (
        ProjectPhase.objects.filter(project=project, archived_at__isnull=True)
        .select_related("phase")
        .prefetch_related("deliverables", "deliverables__document")
        .order_by("phase__position", "id")
    )
    return [
        {
            "id": phase.pk,
            "name": phase.phase.name,
            "description": phase.phase.description,
            "position": phase.phase.position,
            "status": phase.status,
            "canonical_stage": phase.phase.canonical_stage,
            "requires_gate": phase.phase.requires_gate,
            "gate_decision": phase.gate_decision,
            "target_date": phase.target_date.isoformat() if phase.target_date else None,
            "started_at": phase.started_at.isoformat() if phase.started_at else None,
            "completed_at": phase.completed_at.isoformat() if phase.completed_at else None,
            "deliverables": [
                {
                    "id": deliverable.pk,
                    "name": deliverable.name,
                    "status": deliverable.status,
                    "delivered_at": (
                        deliverable.delivered_at.isoformat() if deliverable.delivered_at else None
                    ),
                    "link": deliverable.document.drive_link if deliverable.document else None,
                }
                for deliverable in phase.deliverables.all()
            ],
        }
        for phase in phases
    ]


def ai_score_snapshot(project: Project) -> dict[str, Any] | None:
    """AI Score de maturidade/oportunidade de IA para o portal (FDD 014).

    Só cruza ao cliente depois da revisão humana (`ai_score_reviewed`) — é a narrativa de valor,
    não dado comercial. Sem revisão, retorna None e o portal simplesmente não mostra o índice.
    """
    if not project.ai_score_reviewed or project.ai_scored_at is None:
        return None
    return {
        "maturity": project.ai_maturity,
        # A colisão de nome com a venda é **léxica**: esta chave é o AI Score de maturidade
        # (`Project.ai_opportunity`), escalar, e o papel dela vira `PriorityAssessment` na
        # Fase 4. Renomeá-la aqui seria mudança de contrato do snapshot que o One consome.
        "opportunity": project.ai_opportunity,
        "dimensions": project.ai_dimensions,
        "summary": project.ai_score_summary,
        "scored_at": project.ai_scored_at.isoformat(),
    }


def build_snapshot(project: Project) -> dict[str, Any]:
    """Projeção read-only e segura do projeto para o portal do cliente."""
    milestones = [
        {
            "id": milestone.pk,
            "title": milestone.title,
            "status": milestone.status,
            "party": milestone.party,
            "due_date": milestone.due_date.isoformat(),
            "completed_at": milestone.completed_at.isoformat() if milestone.completed_at else None,
            "is_overdue": milestone.is_overdue,
        }
        for milestone in Milestone.objects.filter(project=project, archived_at__isnull=True)
    ]
    documents = [
        {
            "id": document.pk,
            "name": document.original_name,
            "type": _doc_type(document.original_name),
            "author": document.uploaded_by.get_full_name() or document.uploaded_by.username,
            "link": document.drive_link,
            "created_at": document.created_at.isoformat(),
        }
        for document in Document.objects.filter(
            project=project, archived_at__isnull=True
        ).select_related("uploaded_by")
    ]
    meetings = [
        {
            "id": meeting.pk,
            "title": meeting.title,
            "date": meeting.date.isoformat(),
            "recording_url": meeting.recording_url,
            "has_transcript": bool(meeting.transcript),
            "status": meeting.status,
        }
        for meeting in Meeting.objects.filter(project=project, archived_at__isnull=True)
    ]
    pendencias = [
        {
            "id": pendencia.pk,
            "title": pendencia.title,
            "status": pendencia.status,
            "party": pendencia.party,
            "created_at": pendencia.created_at.isoformat(),
            "resolved_at": pendencia.resolved_at.isoformat() if pendencia.resolved_at else None,
        }
        for pendencia in Pendencia.objects.filter(project=project, archived_at__isnull=True)
    ]
    # Decisões (FDD 032). **Só as publicadas**, e o filtro é a peça que faz a extração por IA ser
    # aceitável: o rascunho que o modelo propôs é interno até uma pessoa publicar. Arquivado para
    # de contar, como todo filho no snapshot.
    #
    # `rationale` atravessa, e isso é decisão registrada e não descuido: a `Pendencia` acima leva
    # título e estado, e o `description` dela fica de fora de propósito. Uma decisão sem o porquê é
    # um título — e o porquê é justamente o que o cliente não tem como reconstituir sozinho. Ver a
    # emenda de agosto/2026 na ADR 0003.
    decisions = [
        {
            "id": decisao.pk,
            "title": decisao.title,
            "rationale": decisao.rationale,
            "decided_on": decisao.decided_on.isoformat() if decisao.decided_on else None,
            "decided_by": decisao.decided_by,
            # A pk da reunião, não a nossa chave interna: é por ela que o portal recasa a
            # proveniência com a reunião que ele acabou de espelhar.
            "meeting_id": decisao.source_meeting_id,
        }
        for decisao in Decisao.objects.filter(
            project=project, archived_at__isnull=True, status=Decisao.Status.PUBLISHED
        )
    ]
    done = sum(1 for milestone in milestones if milestone["status"] == Milestone.Status.DONE)
    completion = round(done / len(milestones) * 100) if milestones else 0
    overdue = sum(1 for milestone in milestones if milestone["is_overdue"])
    on_time_pct = round((len(milestones) - overdue) / len(milestones) * 100) if milestones else 100

    journey = _journey(project)
    current_phase = next(
        (phase["name"] for phase in journey if phase["status"] == ProjectPhase.Status.ACTIVE), None
    )
    health_label, health_level = _HEALTH_LABEL.get(
        health.assess_project_health(project)["level"], ("Em acompanhamento", "amber")
    )
    digital_employees = [
        {
            "id": employee.pk,
            "name": employee.name,
            "area": employee.area,
            "description": employee.description,
            "status": employee.status,
            "kpi_label": employee.kpi_label,
            "kpi_value": employee.kpi_value,
            "hours_saved_month": float(employee.hours_saved_month),
            "roi_month": float(employee.roi_month),
        }
        for employee in DigitalEmployee.objects.filter(project=project, archived_at__isnull=True)
    ]
    revenue, cost = project.actual_value, project.cost
    next_meeting = (
        Meeting.objects.filter(
            project=project, archived_at__isnull=True, status=Meeting.Status.SCHEDULED
        )
        .order_by("date", "id")
        .first()
    )
    return {
        "project": {
            "id": project.pk,
            "name": project.name,
            "description": project.description,
            "status": project.status,
            "start_date": project.start_date.isoformat(),
            "due_date": project.due_date.isoformat(),
            "is_overdue": (
                project.status != Project.Status.COMPLETED
                and project.due_date < timezone.localdate()
            ),
            # O arquivamento é um fato desta base, e quem o declara é ela. Antes, arquivar um
            # projeto o fazia sumir do snapshot inteiro, e o portal só via um 404 —
            # indistinguível de "projeto inexistente", que é o que travava o read model dele no
            # último estado bom. `None` quando ativo, e o portal desfaz igual ao restaurar.
            "archived_at": project.archived_at.isoformat() if project.archived_at else None,
            # **`client` é alias com data** e continua saindo inalterado: ele morre na
            # `/api/v2/`, junto com a rota (`docs/ontology/aliases.md`). Quebrar o consumidor
            # antes disso não é o que a fatia se propõe.
            "client": {"id": project.client_id, "name": project.client.name},
            # A conta canônica sai do **engajamento**, não de `Project.client`. Os dois são
            # iguais por construção — `Project.clean()` amarra `engagement.account_id ==
            # client_id` —, e ainda assim a projeção lê a fonte e não o alias: `Project.client`
            # é projeção temporária que a Fase 6 remove, e quem já lê pelo lado canônico não
            # precisa mudar quando ela sair.
            "account": {
                "id": project.engagement.account_id,
                "name": project.engagement.account.name,
            },
            # Sempre presente: `Project.engagement` é NOT NULL desde a migração `0057`.
            "engagement": {
                "id": project.engagement_id,
                "name": project.engagement.name,
                "status": project.engagement.status,
            },
        },
        # A primeira aprovação deste cliente, e só o instante dela — o degrau que faltava no
        # funil de onboarding do portal. Ver `_artifact_accepted_at`.
        "artifact_accepted_at": _artifact_accepted_at(project),
        # O carimbo da projeção (ADR 0051), **lido e nunca calculado aqui**. Quem carimba é
        # `emit`, porque quem muda o estado é que sabe que ele mudou; esta rota é um `GET` e
        # `timezone.now()` neste ponto seria a hora do *envio*, não a da observação.
        #
        # Duas leituras seguidas sem mudança devolvem a mesma versão, e isso é o caso comum
        # deste desenho, não sintoma: a projeção não mudou. O `sync_snapshot` do lado de lá
        # trata empate aplicando o snapshot, porque é idempotente por substituição.
        "observed_at": (
            project.projection_observed_at.isoformat()
            if project.projection_observed_at
            else None
        ),
        "projection_version": project.projection_version,
        "completion": completion,
        "health": {"label": health_label, "level": health_level},
        "digital_employees": digital_employees,
        "journey": {"current_phase": current_phase, "phases": journey},
        "ai_score": ai_score_snapshot(project),
        "milestones": milestones,
        "documents": documents,
        "meetings": meetings,
        "pendencias": pendencias,
        "decisions": decisions,
        "next_meeting": (
            {"id": next_meeting.pk, "title": next_meeting.title, "date": next_meeting.date.isoformat()}
            if next_meeting
            else None
        ),
        "roi": {
            "revenue": float(revenue),
            "cost": float(cost),
            "net": float(revenue - cost),
            "roi": float((revenue - cost) / cost) if cost else None,
        },
        "resultados": {
            "conclusao_pct": completion,
            "marcos_total": len(milestones),
            "marcos_done": done,
            "atrasados": overdue,
            "no_prazo_pct": on_time_pct,
            "status": project.status,
        },
    }


def _post(url: str, body: bytes, signature: str) -> None:
    headers = {
        "Content-Type": "application/json",
        "X-Biahflow-Signature": f"sha256={signature}",
    }
    # Em homologação o portal do cliente sobe com ingress interno **e** IAM: sem
    # identidade, o Cloud Run responde 403 antes de a aplicação existir, e o webhook
    # some sem log nosso (ADR 0029). Fora do Cloud Run não há token, e a ausência é o
    # caso normal — o compose fala com `host.docker.internal`, onde não há barreira.
    #
    # `Authorization` puro e não `X-Serverless-Authorization`: aqui ele está livre,
    # porque quem autentica esta rota é a assinatura HMAC no header próprio.
    token = service_identity.id_token_para(url)
    if token:
        headers["Authorization"] = f"Bearer {token}"

    request = urllib.request.Request(
        url,
        data=body,
        headers=headers,
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=5) as response:  # noqa: S310
            response.read()
    except (urllib.error.URLError, TimeoutError, ValueError) as exc:  # pragma: no cover
        logger.warning("Falha ao entregar webhook ao portal do cliente: %s", exc)


def emit(event: str, object_type: str, project_id: int | None) -> None:
    """Agenda a entrega de um webhook fino ao portal após o commit da transação.

    Best-effort e não bloqueante — mas **sem rede de segurança automática**: o portal tem a task
    de backfill (`sync_biahflow_project`) e não a agenda, então uma entrega perdida só se recupera
    pelo próximo evento do mesmo projeto ou por backfill manual. Vale a pena emitir em todo caminho
    que muda o projeto, e não contar com reconciliação. Não faz nada quando a integração não está
    configurada nem quando o admin a desligou pela tela.

    **Carimba a projeção antes de qualquer guarda** (ADR 0051). Este é o estrangulamento único
    por onde passam os onze receivers `_emit_*`, e é o lugar certo de dizer "o estado mudou".
    """
    # Três razões para o carimbo estar exatamente aqui:
    #
    # 1. `F(...) + 1` resolve a concorrência **no banco**. Ler em Python e somar perderia
    #    incremento sob escrita simultânea — e versão que anda para trás é o pior defeito
    #    possível para um comparador de obsolescência, que passaria a recusar estado novo.
    #    Não há precedente de `F() + 1` no repositório; este é o primeiro.
    # 2. **Antes da guarda de flag**, e não depois. A projeção mudou de fato mesmo com o webhook
    #    desligado (ADR 0018): carimbar só quando o aviso sai faria o One, ao religar a flag,
    #    receber estado novo com versão velha e **recusá-lo**.
    # 3. `.update()` **não dispara signal**, então carimbar o `Project` de dentro do `post_save`
    #    do próprio `Project` não recursa. É a primeira pergunta de quem revisa isto.
    #
    # `_emit_project_deleted` (`post_delete`) chega aqui com a pk de um projeto que já não
    # existe: o filtro casa zero linhas e o `update` é inócuo. Não é caso especial.
    if project_id:
        Project.objects.filter(pk=project_id).update(
            projection_version=F("projection_version") + 1,
            projection_observed_at=timezone.now(),
        )
    # A flag passou a ser alternável (ADR 0018) e este é o ponto que a aplica: ler as settings direto,
    # como antes, ignoraria o desligamento feito pela tela — e o portal continuaria recebendo evento
    # durante o incidente que motivou desligá-lo.
    if not flags.is_enabled("portal"):
        return
    url = settings.PORTAL_WEBHOOK_URL
    secret = settings.PORTAL_WEBHOOK_SECRET
    if not url or not secret or not project_id:
        return
    body = json.dumps({"event": event, "object_type": object_type, "project_id": project_id}).encode()
    signature = sign(secret, body)
    transaction.on_commit(
        lambda: threading.Thread(target=_post, args=(url, body, signature), daemon=True).start()
    )
