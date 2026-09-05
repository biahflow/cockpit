"""Recomendações heurísticas (sempre revisáveis por uma pessoa).

Sugestões derivadas dos dados atuais; nunca executam ação — só apontam onde agir.
"""

from __future__ import annotations

from datetime import timedelta
from typing import Any

from django.utils import timezone

from .next_step import (
    DEGRAU_ABRIR_VENDA,
    DEGRAU_DECIDIR_INVESTIMENTO,
    DEGRAU_ESCOLHER_HIPOTESE,
    DEGRAU_MONTAR_BUSINESS_CASE,
    proximo_passo_da_conta,
    tem_venda_aberta,
)

#: A frase de cada degrau, na lista de `/indicadores`. Uma por chave de `next_step.DEGRAUS`, e o
#: `KeyError` é deliberado: degrau novo sem frase quebra o teste em vez de sair como recomendação
#: muda. Elas descrevem **o que falta**, nunca o que fazer — quem transforma isso em ação é o
#: `label`, que já nomeia a conta e a oportunidade.
_DETALHE_POR_DEGRAU: dict[str, str] = {
    DEGRAU_ESCOLHER_HIPOTESE: "priorizada e ainda sem hipótese de solução escolhida.",
    DEGRAU_MONTAR_BUSINESS_CASE: "hipótese escolhida e ainda sem business case.",
    DEGRAU_DECIDIR_INVESTIMENTO: "business case em rascunho, aguardando decisão de investimento.",
    DEGRAU_ABRIR_VENDA: "investimento aprovado e nenhuma venda aberta nesta conta.",
}


def build_recommendations() -> list[dict[str, Any]]:
    from .models import Account, CommercialOpportunity, PipelineStage, Project

    today = timezone.localdate()
    recs: list[dict[str, Any]] = []
    # `conta -> próximo passo`, para a recomendação sair no mesmo lugar da lista de antes.
    proximos: list[tuple[Account, dict[str, Any]]] = []

    # Clientes com projetos mas sem oportunidade aberta → oportunidade de novo negócio.
    for account in Account.objects.filter(archived_at__isnull=True):
        has_project = Project.objects.filter(engagement__account=account, archived_at__isnull=True).exists()
        has_open = tem_venda_aberta(account)
        if has_project and not has_open:
            recs.append({
                "kind": "upsell",
                "label": f"Novo negócio com {account.name}",
                "detail": "Cliente ativo sem oportunidade aberta — vale um contato.",
                "url": f"/contas/{account.pk}",
            })
        # O próximo passo da conta é lido **aqui**, na varredura que já existe, e não numa segunda
        # passagem sobre as contas: a rota já custa uma consulta por conta, e uma segunda iteração
        # dobraria o piso sem responder nada a mais.
        proximo = proximo_passo_da_conta(account)
        if proximo is not None:
            proximos.append((account, proximo))

    # Oportunidades abertas paradas há mais de 30 dias → follow-up.
    open_kind = PipelineStage.Kind.OPEN
    stale_before = timezone.now() - timedelta(days=30)
    for opportunity in CommercialOpportunity.objects.filter(
        archived_at__isnull=True, stage__kind=open_kind, created_at__lt=stale_before
    ).select_related("account"):
        recs.append({
            "kind": "followup",
            "label": f"Follow-up: {opportunity.title}",
            "detail": "Oportunidade aberta parada há mais de 30 dias.",
            "url": "/comercial",
        })

    # O próximo passo da conta → recomendação de priorização.
    #
    # **A oportunidade é escolhida por `next_step.proximo_passo_da_conta`, e não por uma query
    # daqui** (ADR 0069, decisão B1 do DAP `dap-discovery-session-e-business-case-r2`). A mesma
    # pergunta passou a ter dois leitores — o painel do detalhe da conta e esta lista —, e o
    # contra-argumento registrado da decisão foi exatamente este: dois lugares mostrando a mesma
    # recomendação divergem, e nada fica vermelho quando divergem. A metade que evita isso é uma
    # função só, lida pelos dois.
    #
    # **Ela lê a `PriorityAssessment` vigente, e não um campo opaco** (issue #68): o número que
    # ordena esta recomendação é o mesmo que a tela mostra, com a fórmula e a versão que o
    # produziram gravadas na linha. `Lead.ai_score` e `Project.ai_potential` não servem aqui e
    # o mapa de linguagem §5 explica por quê — o primeiro é score de aquisição, o segundo é
    # maturidade de IA da conta, e nenhum dos dois mede melhoria operacional.
    #
    # **Todo degrau pendente vira recomendação, e é o `detail` que varia.** A primeira versão desta
    # fatia emitia só o primeiro degrau, para não tornar falsa a frase "ainda sem hipótese de solução
    # escolhida" — e o efeito era uma conta com trabalho pendente **sumir da lista**: bastava a de
    # maior score estar no degrau 3 para a conta inteira desaparecer de `/indicadores`, enquanto o
    # painel do detalhe dela mostrava o passo. Os dois leitores passavam a discordar por omissão, que
    # é o que a decisão B1 comprou a função única para evitar. Presa ao primeiro degrau estava a
    # frase, não a recomendação.
    #
    # As frases moram **aqui**, e não em `next_step.py`: aquela função devolve chave e nunca copy (é
    # a regra de `prove.o_que_falta_para_iniciar`), e este endpoint sempre entregou texto pronto —
    # os quatro `kind` têm `label` e `detail` em português desde a FDD 006. Cada superfície escreve a
    # sua: o painel tem o mapa dele em TypeScript, esta lista tem o dela aqui.
    for account, proximo in proximos:
        recs.append({
            "kind": "prioritization",
            "label": f"Próximo passo em {account.name}: {proximo['title']}",
            "detail": (
                f"Opportunity Score {proximo['score']} (v{proximo['assessment_version']}) — "
                f"{_DETALHE_POR_DEGRAU[proximo['missing']]}"
            ),
            "url": f"/contas/{account.pk}/priorizacao",
        })

    # Projetos ativos vencendo em até 7 dias → atenção.
    soon = today + timedelta(days=7)
    for project in Project.objects.filter(
        archived_at__isnull=True, due_date__gte=today, due_date__lte=soon
    ).exclude(status="completed"):
        recs.append({
            "kind": "deadline",
            "label": f"Prazo próximo: {project.name}",
            "detail": f"Vence em {(project.due_date - today).days} dia(s).",
            "url": f"/projetos/{project.pk}",
        })

    return recs
