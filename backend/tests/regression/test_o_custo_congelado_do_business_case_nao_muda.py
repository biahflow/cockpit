"""Regressão: editar os insumos do processo depois não muda o custo já congelado (FDD 053).

É a razão de `current_state_cost` ser coluna copiada em vez de propriedade calculada.
`Process.custo_do_estado_atual` é função pura sobre os nove insumos de **agora**: o mesmo processo,
consultado no mês seguinte, devolve outro número porque alguém corrigiu o volume ou o custo/hora.
Um business case cujo número muda sozinho depois de decidido é pior que nenhum — quem citou a conta
na reunião de investimento passa a estar dizendo outra coisa sem saber.

O teste é o gêmeo de `test_case_congelado_nao_muda.py`, e faz a mesma pergunta nas duas metades:
não confere que ninguém escreveu, confere que **não há por onde**. Mexe no processo pelos caminhos
que alterariam o cálculo (os quatro fatores do núcleo, um aditivo, a sustentação e a composição das
dores) e tenta reescrever os campos congelados pela API.
"""

from decimal import Decimal

import pytest
from django.utils import timezone
from rest_framework.test import APIClient

from apps.core.models import BusinessCase, Finding
from apps.core.tests.factories import (
    AccountFactory,
    BusinessCaseFactory,
    FindingFactory,
    ImprovementOpportunityFactory,
    PainPointFactory,
    ProcessFactory,
    UserFactory,
)


def _cenario_com_custo_sustentado() -> BusinessCase:
    """R$ 4.000 de núcleo, com um `Finding(fact)` vivo sustentando — o caso que soma."""
    conta = AccountFactory()
    processo = ProcessFactory(
        account=conta,
        volume_mes=100,
        tempo_horas=Decimal("0.50"),
        pessoas=1,
        custo_hora=Decimal("80.00"),
    )
    FindingFactory(
        account=conta,
        process=processo,
        epistemic_status=Finding.EpistemicStatus.FACT,
        reviewed_by=UserFactory(),
        reviewed_at=timezone.now(),
    )
    oportunidade = ImprovementOpportunityFactory(account=conta)
    oportunidade.pain_points.add(PainPointFactory(account=conta, process=processo))
    return BusinessCaseFactory(improvement_opportunity=oportunidade)


@pytest.mark.django_db
def test_mexer_no_processo_depois_nao_altera_o_custo_congelado() -> None:
    business_case = _cenario_com_custo_sustentado()
    congelado = (business_case.current_state_cost, business_case.current_state_cost_source)
    assert congelado[0] == Decimal("4000.00")
    processo = business_case.improvement_opportunity.pain_points.first().process

    # Tudo o que aconteceria com um processo mapeado nos meses seguintes.
    processo.volume_mes = 900
    processo.custo_hora = Decimal("250.00")
    processo.retrabalho_mes = Decimal("7000.00")
    processo.save()
    # Inclusive perder a sustentação: arquivar o único fato faria o custo virar hipótese hoje.
    Finding.objects.filter(process=processo).update(archived_at=timezone.now())
    # E ganhar uma dor nova, que traria outro processo para a conta.
    business_case.improvement_opportunity.pain_points.add(
        PainPointFactory(
            account=processo.account,
            process=ProcessFactory(
                account=processo.account,
                name="Expedição",
                volume_mes=10,
                tempo_horas=Decimal("1.00"),
                pessoas=2,
                custo_hora=Decimal("100.00"),
            ),
        )
    )

    business_case.refresh_from_db()
    assert (business_case.current_state_cost, business_case.current_state_cost_source) == congelado


@pytest.mark.django_db
def test_a_api_nao_reescreve_o_custo_congelado() -> None:
    business_case = _cenario_com_custo_sustentado()
    congelado = (business_case.current_state_cost, business_case.current_state_cost_source)
    api = APIClient()
    api.force_authenticate(UserFactory(role="admin"))

    resposta = api.patch(
        f"/api/v1/business-cases/{business_case.pk}/",
        {
            "rationale": "Argumento revisado pelo humano",
            "current_state_cost": "999999.00",
            "current_state_cost_source": {"processos": [], "somados": [1, 2, 3]},
        },
        format="json",
    )

    assert resposta.status_code == 200, resposta.data
    business_case.refresh_from_db()
    # O que é do humano muda; o que é fotografia, não.
    assert business_case.rationale == "Argumento revisado pelo humano"
    assert (business_case.current_state_cost, business_case.current_state_cost_source) == congelado


@pytest.mark.django_db
def test_o_business_case_seguinte_ve_o_numero_novo() -> None:
    """O controle que impede o teste acima de passar por o cálculo estar quebrado.

    Congelar não é ignorar a realidade: um business case **criado depois** da correção lê os
    insumos de então. O que não pode mudar é o número de ontem.
    """
    business_case = _cenario_com_custo_sustentado()
    processo = business_case.improvement_opportunity.pain_points.first().process
    processo.custo_hora = Decimal("160.00")
    processo.save()

    seguinte = BusinessCaseFactory(
        improvement_opportunity=business_case.improvement_opportunity,
        solution_hypothesis=business_case.solution_hypothesis,
        priority_assessment=business_case.priority_assessment,
    )

    assert business_case.current_state_cost == Decimal("4000.00")
    assert seguinte.current_state_cost == Decimal("8000.00")
