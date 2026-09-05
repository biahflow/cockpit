"""Regressão: `/recommendations/` continua emitindo `prioritization` com as mesmas quatro chaves.

A decisão **B1** do DAP `docs/design/dap-discovery-session-e-business-case-r2/` mandou a
recomendação passar a ler `next_step.proximo_passo_da_conta` — a mesma função do painel do detalhe
da conta —, e mandou que **o `kind`, o `label`, o `detail` e a `url` não mudassem**: a lista de
`/indicadores` já é consumida por `IndicadoresPage`, e o pacote registra por escrito que mudar o
contrato de `recommendations.py` não está aprovado.

Este arquivo existe pelo motivo do `test_a_medicao_do_ativo_sobrevive_na_v1.py`: a troca do leitor
é invisível do lado de fora **enquanto alguém a mantiver invisível**. O `label` e o `detail` são
strings montadas à mão dentro de um módulo que ninguém mais lê de dentro do repositório; sem uma
asserção sobre o texto exato, a próxima refatoração as reescreve "porque ficou melhor assim" e a
tela do outro lado passa a mostrar outra frase sem nada ficar vermelho.

A metade que **mudou** de propósito — a recomendação sai só no primeiro degrau, porque o `detail`
afirma "ainda sem hipótese de solução escolhida" — está em
`apps/core/tests/test_proximo_passo.py`. Aqui só o contrato, que é o que a decisão congelou.
"""

import pytest
from django.urls import reverse
from rest_framework.test import APIClient

from apps.core.models import ImprovementOpportunity, User
from apps.core.tests.factories import (
    AccountFactory,
    ImprovementOpportunityFactory,
    PriorityAssessmentFactory,
    UserFactory,
)

pytestmark = pytest.mark.django_db


@pytest.fixture
def api() -> APIClient:
    client = APIClient()
    client.force_authenticate(UserFactory(role=User.Role.ADMIN))
    return client


def test_a_recomendacao_de_priorizacao_sai_com_as_quatro_chaves_de_sempre(api: APIClient) -> None:
    conta = AccountFactory(name="Rio Home Care")
    oportunidade = ImprovementOpportunityFactory(
        account=conta,
        title="Reconciliação manual de repasses",
        status=ImprovementOpportunity.Status.PRIORITIZED,
    )
    PriorityAssessmentFactory(
        improvement_opportunity=oportunidade,
        impact=5,
        evidence_strength=4,
        feasibility=4,
        time_to_value=3,
        economics=3,
    )

    resposta = api.get(reverse("recommendations"))

    assert resposta.status_code == 200, resposta.data
    prioritizacao = [
        item for item in resposta.data["items"] if item["kind"] == "prioritization"
    ]
    assert prioritizacao == [
        {
            "kind": "prioritization",
            "label": "Próximo passo em Rio Home Care: Reconciliação manual de repasses",
            "detail": (
                "Opportunity Score 80.00 (v1) — priorizada e ainda sem hipótese de solução "
                "escolhida."
            ),
            "url": f"/contas/{conta.pk}/priorizacao",
        }
    ]


def test_os_quatro_tipos_de_recomendacao_continuam_com_a_mesma_forma(api: APIClient) -> None:
    """A forma do item, e não só o conteúdo de um deles: quatro chaves, todas texto, sem chave
    nova por carona. `IndicadoresPage` lê `kind` como string livre de propósito — o que ela não
    tolera é o item mudar de esqueleto."""
    conta = AccountFactory()
    oportunidade = ImprovementOpportunityFactory(
        account=conta, status=ImprovementOpportunity.Status.PRIORITIZED
    )
    PriorityAssessmentFactory(improvement_opportunity=oportunidade)

    resposta = api.get(reverse("recommendations"))

    itens = resposta.data["items"]
    assert itens, "sem item nenhum o teste não afirma nada sobre a forma"
    for item in itens:
        assert set(item) == {"kind", "label", "detail", "url"}
        assert all(isinstance(valor, str) for valor in item.values())
