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

A terceira é a cadeia de medição (emenda de 01/09/2026 na ADR 0003, FDD 050): `kpis` e
`value_ledger`. Uma entrada do Value Ledger carrega dinheiro, e ainda assim não é dado comercial —
é o **valor entregue e aprovado**, com o método de atribuição que o sustenta, e a §3 do
`language-map` já a lista entre o que o One mostra. O que continua não cruzando é o outro lado do
dinheiro: preço, margem, `Service.price`, valor e probabilidade da venda. E só a entrada
`approved` com método de atribuição atravessa — rascunho e pendente são deliberação interna.

A quarta é o Discovery como **dado** (emenda de 01/09/2026 na ADR 0003, FDD 051): `processes`,
`findings`, `pain_points` e `improvement_opportunities`. Ele chegava ao cliente como documento, e o
que separa o One de um Drive compartilhado é chegar navegável. A linha "nenhum dado comercial é
exposto" continua inteira — nada disto é venda —, e o que a governa é outra coisa: **nada
atravessa sem a marca de publicável**, que é o ato de revisão humana que a regra 1 da §3 do
`language-map` exige. **Não há exceção, e o mapa do AS-IS não é uma**: a §3 o qualifica como
*validado*, e "validado" era um qualificador sem lastro nenhum no schema — exatamente como
"revisada e publicável" era para a evidência. Ele atravessa porque alguém o publicou, e publicar
é a validação com o cliente que a §3 pressupõe. Nunca cruzam o trecho bruto de uma evidência, o
carimbo de integridade dele, o racional interno da priorização e os nove insumos do cálculo do
custo do processo.

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

from . import flags, health, prove, service_identity
from .models import (
    KPI,
    Artifact,
    Decisao,
    DigitalEmployee,
    Document,
    Finding,
    ImprovementOpportunity,
    Measurement,
    Meeting,
    Milestone,
    PainPoint,
    Pendencia,
    Process,
    Project,
    ProjectPhase,
    SolutionHypothesis,
    ValueLedgerEntry,
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
    account_id = project.engagement.account_id
    first = Artifact.objects.filter(
        Q(project__engagement__account=account_id)
        | Q(commercial_opportunity__account=account_id),
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
        "opportunity": project.ai_potential,
        "dimensions": project.ai_dimensions,
        "summary": project.ai_score_summary,
        "scored_at": project.ai_scored_at.isoformat(),
    }


def _medicao(medicao: Measurement | None) -> dict[str, Any] | None:
    """A forma de uma leitura de KPI no snapshot (FDD 050).

    **Duas nulidades distintas, e as duas são necessárias.** `None` aqui — a chave inteira nula —
    diz *não há medição desta natureza*; um dicionário com `"value": None` diz *a janela existe e a
    medição não foi feita*. Colapsar as duas em zero é o defeito que `Measurement.value` guarda
    sendo nulável: zero afirma que se mediu e deu zero.

    Não saem `id`, `kind` nem `source_evidence`. Os dois primeiros porque o aninhamento **é** a
    identidade e o papel da leitura — ela é *a* baseline daquele KPI —, e o terceiro porque o
    material bruto do levantamento, antes de revisão humana, não atravessa a fronteira do cliente
    (`language-map` §3, regra 1). Há regressão sobre o **vocabulário desta fonte**, e não só sobre o
    dicionário emitido: as palavras do levantamento não têm por que aparecer aqui, e a guarda toma a
    presença delas como intenção de levar o mapa ao cliente.
    """
    if medicao is None:
        return None
    return {
        "value": float(medicao.value) if medicao.value is not None else None,
        # A janela a que a leitura se refere, que não é o instante em que ela foi tomada:
        # "outubro" medido em novembro é uma coisa só, e sem as três datas não dá para dizer isso.
        "period_start": medicao.period_start.isoformat(),
        "period_end": medicao.period_end.isoformat(),
        "measured_at": medicao.measured_at.isoformat(),
        "confidence": medicao.confidence,
    }


def _kpis(project: Project) -> list[dict[str, Any]]:
    """Os KPIs vivos do projeto, **com as leituras aninhadas dentro de cada um** (FDD 050).

    O aninhamento é a decisão da fatia, e não arrumação: o que torna duas leituras comparáveis é
    serem do *mesmo* KPI, com a mesma unidade e o mesmo método (`KPI.unit`, `definition`,
    `formula` — invariante §6.11 do `language-map`). Numa lista irmã de medições, parear baseline e
    outcome viraria trabalho do leitor, e um pareamento errado não deixaria nada vermelho.

    `owner` **não** atravessa: é pessoa interna (`language-map` §3).
    """
    resultado = []
    for kpi in KPI.objects.filter(project=project, archived_at__isnull=True).prefetch_related(
        "measurements"
    ):
        # `prefetch_related` acima e `.all()` lá dentro: `prove._medicoes_vivas` filtra em Python
        # justamente para reusar o prefetch. Um `.filter()` por KPI emitiria consulta nova a cada
        # volta, e este bloco roda a cada `GET` do snapshot.
        baseline = prove.medicao_de_baseline(kpi)
        # **Nenhum outcome é emitido sem baseline do mesmo KPI.** O critério de aceite do outro
        # lado é "todo Outcome renderizado tem Baseline no mesmo componente" (§6.11): emitir o
        # outcome sozinho e deixar o One recusá-lo faz o cliente ver lacuna onde há dado, que é
        # pior que a lacuna honesta. Quem tem a baseline é quem sabe disso — aqui.
        outcome = prove.medicao_de_outcome(kpi) if baseline is not None else None
        resultado.append(
            {
                "id": kpi.pk,
                "name": kpi.name,
                "definition": kpi.definition,
                "formula": kpi.formula,
                "unit": kpi.unit,
                "direction": kpi.direction,
                "data_source": kpi.data_source,
                "cadence": kpi.cadence,
                "target": float(kpi.target) if kpi.target is not None else None,
                "baseline": _medicao(baseline),
                "outcome": _medicao(outcome),
                "monitoring": [
                    _medicao(medicao) for medicao in prove.medicoes_de_monitoramento(kpi)
                ],
            }
        )
    return resultado


def _value_ledger(project: Project) -> list[dict[str, Any]]:
    """O Value Ledger do **mandato**, não do projeto (FDD 050).

    A leitura é por `Engagement`, como a da tela `/contas/:id/valor`: valor é do mandato, e
    `ValueLedgerEntry.project` é opcional de propósito — um resultado que atravessa dois projetos
    do mesmo programa é uma entrada só. A consequência é que a mesma entrada sai no snapshot de
    todos os projetos do mandato, e o `_emit_value_ledger_entry` faz fan-out por isso.

    **Dois filtros além do arquivamento, e nenhum é zelo excessivo:**

    - só `approved`. Rascunho e pendente não atravessam (regra 1 da §3 do `language-map`), e aqui
      isso pesa mais que no resto do snapshot: é a linha que o cliente lê como *valor gerado*.
    - `attribution_method` não-vazio. O `clean()` já o exige, mas `clean()` não roda em shell nem
      em migração de dados — e este é exatamente o campo cuja ausência transforma a linha num
      número sem procedência. "ROI" como resultado é termo banido (§5) por isto.

    **Não há campo de moeda, e não se cria um aqui.** Toda entrada é BRL hoje; uma coluna para o
    caso hipotético seria especulação, e o `roi` que já atravessa tem a mesma ausência. Quando
    houver a primeira entrada em outra moeda, ela nasce no modelo — não na projeção.

    `approved_by` e `status` **não** atravessam: o primeiro é pessoa interna, e o segundo diria ao
    cliente que existe uma fila de aprovação da qual ele não participa.
    """
    entradas = ValueLedgerEntry.objects.filter(
        engagement_id=project.engagement_id,
        archived_at__isnull=True,
        status=ValueLedgerEntry.Status.APPROVED,
    ).select_related("outcome_measurement")
    return [
        {
            "id": entry.pk,
            "value_type": entry.value_type,
            "amount": float(entry.amount) if entry.amount is not None else None,
            "quantity": float(entry.quantity) if entry.quantity is not None else None,
            "period_start": entry.period_start.isoformat(),
            "period_end": entry.period_end.isoformat(),
            "attribution_method": entry.attribution_method,
            # O resultado que sustenta a entrada, por referência: o KPI que o One já recebeu em
            # `kpis[]` e o instante da leitura. Recasar é dele; afirmar o vínculo é nosso.
            "kpi_id": entry.outcome_measurement.kpi_id,
            "outcome_measured_at": entry.outcome_measurement.measured_at.isoformat(),
        }
        for entry in entradas
        # Em Python e não no queryset porque a regra é uma só — "método de atribuição ausente" —, e
        # `""` e `"   "` são a mesma ausência. Duas metades em SQL e em Python divergiriam na
        # primeira correção; o conjunto já veio estreito a um mandato.
        if entry.attribution_method.strip()
    ]


def _processes(account_id: int) -> list[dict[str, Any]]:
    """O AS-IS mapeado da conta, com os `ProcessStep` vivos dentro de cada um (FDD 051).

    **Escopo de conta, e é a decisão que destravou a fatia.** `Process` pende da `Account` desde a
    FDD 039, porque o que se levantou sobre a operação de uma empresa sobrevive à venda que o
    descobriu. Consequência: o mesmo bloco sai no snapshot de **todos** os projetos da conta, e o
    One deduplica por id — que ele já sabe fazer. Recortar pelo projeto que levantou perderia
    exatamente a propriedade que motivou a FK de conta, e uma rota de escopo Account seria um
    segundo canal de ingestão, a única coisa desta fatia que não seria aditiva.

    **Só o publicado e vivo atravessa** (ADR 0060). A §3 do `language-map` qualifica este par como
    *validado* — e "validado" era, até aqui, um qualificador sem lastro no schema: nenhum campo
    dizia que este mapa tinha sido conferido com o cliente. O AS-IS chega ao One porque **alguém o
    publicou**, e publicar é a validação que a §3 pressupõe. O que a marca protege é concreto: as
    letras E e R de cada passo são a caracterização da casa sobre onde o time do cliente erra e o
    que acontece quando erra, e isso não pode subir sem decisão de gente.

    A etapa **não** tem marca própria e anda com o pai: as seis letras do P-S-D-T-E-R são um
    formulário só, e publicar meia etapa não é estado que alguém queira.

    **Os nove insumos do cálculo de custo não saem.** São conta interna, não estão na §3, e um
    total parcial lido sem quem o levantou por perto vira "vocês disseram que eu perco tanto por
    mês". `registered_by` e as duas procedências também não: pessoa e origem internas.

    As seis chaves do passo ficam **em português**, e não é descuido: elas *são* as seis letras do
    P-S-D-T-E-R, nessa ordem, e o docstring de `ProcessStep` explica que renomear ou juntar faria o
    levantamento da reunião deixar de casar com o formulário. A §5 do mapa de linguagem bane
    português em nome de **modelo**, não em nome de campo — e este snapshot já leva `pendencias`
    pelo mesmo tipo de razão.
    """
    return [
        {
            "id": item.pk,
            "name": item.name,
            "position": item.position,
            "updated_at": item.updated_at.isoformat(),
            "steps": [
                {
                    "id": passo.pk,
                    "position": passo.position,
                    "name": passo.name,
                    "pessoas": passo.pessoas,
                    "sistema": passo.sistema,
                    "dados": passo.dados,
                    "tempo": passo.tempo,
                    "erro": passo.erro,
                    "retrabalho": passo.retrabalho,
                }
                # `.all()` sobre o `prefetch_related`, filtrando em Python: um `.filter()` por
                # item emitiria consulta nova a cada volta, e este bloco roda a cada `GET`. É o
                # cuidado que `_kpis` toma e que `current_assessment` documenta.
                for passo in item.steps.all()
                if passo.archived_at is None
            ],
        }
        for item in Process.objects.filter(
            account_id=account_id, archived_at__isnull=True, published_at__isnull=False
        ).prefetch_related("steps")
    ]


def _findings(account_id: int) -> list[dict[str, Any]]:
    """Os achados **publicados e vivos** da conta, com as fontes publicadas de cada um (FDD 051).

    **Metadado, nunca conteúdo bruto.** `raw_excerpt` e `content_hash` não atravessam — a §3 do
    `language-map` proíbe transcrição e material não revisado. `reference` atravessa porque é a
    citação, *de onde veio* e não *o que foi dito*, e é o que torna a fonte conferível pelo
    cliente; o precedente é o `has_transcript` que `meetings` já usa. `captured_by` e `reviewed_by`
    ficam fora: pessoa interna.

    **A fonte só entra se ela própria estiver publicada e viva**, mesmo estando no M2M de um achado
    publicado. Sem esse recorte a lista apontaria para o que não atravessou, e o cliente leria uma
    afirmação com nada atrás — que é a invariante de cadeia inteira desta fatia.

    **`unknown` atravessa e não é omitido.** O One o renderiza como lacuna declarada; sumir com ele
    é o que faz o cliente achar que não há pergunta em aberto. `fact` e `hypothesis` saem
    rotulados, e é o rótulo que os torna honestos.
    """
    return [
        {
            "id": achado.pk,
            "statement": achado.statement,
            "epistemic_status": achado.epistemic_status,
            "confidence": achado.confidence,
            "process_id": achado.process_id,
            "step_id": achado.step_id,
            "evidences": [
                {
                    "id": fonte.pk,
                    "kind": fonte.kind,
                    "reference": fonte.reference,
                    "captured_at": fonte.captured_at.isoformat(),
                }
                for fonte in achado.evidences.all()
                if fonte.archived_at is None and fonte.published_at is not None
            ],
        }
        for achado in Finding.objects.filter(
            account_id=account_id, archived_at__isnull=True, published_at__isnull=False
        ).prefetch_related("evidences")
    ]


def _pain_points(account_id: int) -> list[dict[str, Any]]:
    """As dores **publicadas e vivas** da conta (FDD 051).

    `finding_ids` vem **filtrado aos achados publicados e vivos**, e nunca o M2M cru: a lista crua
    apontaria para o que não atravessou em `findings[]`, e o One renderizaria referência quebrada.

    `impact_estimate` sai `None` quando ninguém quantificou — **nunca `0`**. Zero afirma que a dor
    não custa nada, e é a distinção que o campo guarda sendo nulável (a regra do não apurado).
    """
    return [
        {
            "id": dor.pk,
            "title": dor.title,
            "description": dor.description,
            "impact_type": dor.impact_type,
            "impact_estimate": (
                float(dor.impact_estimate) if dor.impact_estimate is not None else None
            ),
            "finding_ids": [
                achado.pk
                for achado in dor.findings.all()
                if achado.archived_at is None and achado.published_at is not None
            ],
            "status": dor.status,
        }
        for dor in PainPoint.objects.filter(
            account_id=account_id, archived_at__isnull=True, published_at__isnull=False
        ).prefetch_related("findings")
    ]


def _improvement_opportunities(account_id: int) -> list[dict[str, Any]]:
    """As oportunidades de melhoria **publicadas e vivas**, com score e apostas (FDD 051).

    A chave é `improvement_opportunities` e **não** `opportunities`: a §5 do `language-map` bane
    `Opportunity` sem qualificador — melhoria operacional e venda colidiam nesse nome —, e o One
    tem lint derivado dela do outro lado.

    **`priority_assessment` é só a versão vigente**, lida de `ImprovementOpportunity.current_assessment`,
    que é onde "vigente" está definido; reexpressar o recorte aqui seria a segunda definição do
    mesmo fato. `None` quando não houver avaliação — nunca zero, pela mesma regra do não apurado.

    **`rationale` nunca atravessa**: é proibição literal da §3, e o outro lado já tem portão para
    ela. `assessed_by` também não (pessoa interna). `weights` e `formula_key` também não — são o
    critério interno, e é justamente a mudança de critério que a versão existe para não confundir
    quem lê sem contexto.

    **`rank` não é emitido, e é desvio consciente do que a issue pediu.** Dois motivos, e cada um
    bastaria: `priority.ranking_da_conta` ordena **todas** as oportunidades vivas da conta,
    publicadas ou não, então emitir esse número entregaria ao cliente `2, 4, 7` e a dedução de que
    existem itens escondidos que o superam; e recalcular o rank só entre as publicadas criaria uma
    **segunda definição de rank**, exatamente o que este repositório recusou ao não persistir o
    campo. O que o rank queria dizer — que o backlog é ordenável — é entregue por `score`, que é o
    fato de onde ele sai.

    `solution_hypotheses` vai **aninhada**, e não como lista irmã: as apostas de uma oportunidade
    são concorrentes entre si, e soltá-las perderia a concorrência, que é a informação. Sem as
    `discarded` e sem as arquivadas. `assumptions` não atravessa — é a nota interna do que se está
    supondo.
    """
    resultado: list[dict[str, Any]] = []
    for oportunidade in ImprovementOpportunity.objects.filter(
        account_id=account_id, archived_at__isnull=True, published_at__isnull=False
    ).prefetch_related("pain_points", "assessments", "hypotheses"):
        vigente = oportunidade.current_assessment
        resultado.append(
            {
                "id": oportunidade.pk,
                "title": oportunidade.title,
                "desired_change": oportunidade.desired_change,
                "impact_hypothesis": oportunidade.impact_hypothesis,
                "pain_point_ids": [
                    dor.pk
                    for dor in oportunidade.pain_points.all()
                    if dor.archived_at is None and dor.published_at is not None
                ],
                "status": oportunidade.status,
                "priority_assessment": (
                    {
                        "version": vigente.version,
                        "score": float(vigente.score),
                        "dimensions": {
                            "impact": vigente.impact,
                            "evidence_strength": vigente.evidence_strength,
                            "feasibility": vigente.feasibility,
                            "time_to_value": vigente.time_to_value,
                            "economics": vigente.economics,
                        },
                    }
                    if vigente is not None
                    else None
                ),
                "solution_hypotheses": [
                    {
                        "id": aposta.pk,
                        "statement": aposta.statement,
                        "intervention": aposta.intervention,
                        "expected_effect": aposta.expected_effect,
                        "status": aposta.status,
                    }
                    for aposta in oportunidade.hypotheses.all()
                    if aposta.archived_at is None
                    and aposta.status != SolutionHypothesis.Status.DISCARDED
                ],
            }
        )
    return resultado


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
            # Mesma identidade de `journey.phases[].id`: o consumidor só recasa duas chaves que
            # o Pulse afirmou, sem inferir pela data nem pelo nome da fase (ADR 0057).
            "phase_ref": decisao.project_phase_id,
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
            # **Aditivo, e os quatro acima ficam onde estão** — mesma convivência de
            # `account`/`client`: o legado sai quando o One parar de ler, não antes. Lista porque o
            # contrato do outro lado é lista e porque a FK singular de hoje é o estado atual, não a
            # forma final; hoje ela tem zero ou um elemento. Aponta para `kpis[]`, onde estão a
            # unidade, o método e as leituras — o que estes quatro campos nunca souberam dizer.
            "kpi_ids": [employee.kpi_id] if employee.kpi_id else [],
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
            # **`client` é alias com data** — o One consome esta chave, e ela morre na
            # `/api/v2/`. Desde a Fase 6 os dois caminhos são o mesmo: `engagement.account`.
            "client": {
                "id": project.engagement.account_id,
                "name": project.engagement.account.name,
            },
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
        # A cadeia de medição (FDD 050). `kpis` leva o indicador com as leituras **dentro** dele, e
        # `value_ledger` leva o valor aprovado do mandato. As duas eram o buraco que a FDD 049
        # adiou explicitamente: o cliente via `roi` — receita menos custo do projeto — e nenhum
        # indicador do trabalho que ele contratou.
        "kpis": _kpis(project),
        "value_ledger": _value_ledger(project),
        # O Discovery como dado (FDD 051). Os quatro blocos são de escopo **conta**, alcançada
        # por `engagement.account_id`, e por isso saem iguais no snapshot de todos os projetos
        # dela — ver `_processes`. **Nada entra sem a marca de publicável**, sem exceção, e as
        # listas de id vêm filtradas ao que atravessou: uma referência para o que ficou de fora
        # faria o cliente ler afirmação com nada atrás.
        "processes": _processes(project.engagement.account_id),
        "findings": _findings(project.engagement.account_id),
        "pain_points": _pain_points(project.engagement.account_id),
        "improvement_opportunities": _improvement_opportunities(
            project.engagement.account_id
        ),
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
