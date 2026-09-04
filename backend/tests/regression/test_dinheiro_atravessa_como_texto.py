"""Regressão: dinheiro atravessa a API como **texto**, inclusive nos agregadores (ADR 0068).

Todo `ModelSerializer` do produto já emitia string (`COERCE_DECIMAL_TO_STRING`): `Invoice.amount`,
`Project.actual_value`, `CommercialOpportunity.estimated_value`. Quem escapava eram os agregadores
— `/analytics/`, `/dashboard/`, `/clients/overview/` e `/invoices/summary/` devolvem `dict` cru, sem
serializer que converta nada, e o encoder JSON do DRF transforma `Decimal` em `float`. O sintoma é
silencioso por construção: `40000.00` vira `40000.0` e a tela continua desenhando.

**Estes testes afirmam sobre o JSON renderizado, e sobre o tipo.** As duas coisas, e nenhuma é
redundante:

* `response.data` **não pega isto**. Ali o valor ainda é `Decimal`; a conversão para `float`
  acontece só na renderização. É a armadilha que `ProcessSerializer.get_custo` documenta e que
  `apps/core/tests/test_processos.py` já respeitava — este arquivo aplica a mesma disciplina aos
  agregadores.
* comparar valor sem comparar tipo também não pega. `Decimal("100.00") == 100` é `True`, então um
  teste escrito contra o `Decimal` do modelo passa nas **duas** representações e não distingue
  nenhuma. Foi assim que `test_delivery_aggregates_are_scoped` ficou agnóstico sem que ninguém
  notasse. Por isso cada asserção aqui é sobre `isinstance(..., str)` e sobre a string exata, com
  as duas casas visíveis.

O que **não** é dinheiro e continua número: `roi`, `win_rate`, `acceptance_rate` e `avg_ticket`.
São quocientes, não somas de valores gravados — o critério está na ADR 0068, e há asserção sobre
isso aqui para que trocá-los seja um ato e não um efeito colateral da próxima varredura.
"""

from decimal import Decimal
from types import SimpleNamespace

import pytest
from django.urls import reverse
from rest_framework.test import APIClient

from apps.core.models import Invoice, PipelineStage, Service, User
from apps.core.tests.factories import (
    AccountFactory,
    CommercialOpportunityFactory,
    InvoiceFactory,
    ProjectFactory,
    UserFactory,
)

pytestmark = pytest.mark.django_db


@pytest.fixture
def api() -> APIClient:
    client = APIClient()
    client.force_authenticate(UserFactory(role=User.Role.ADMIN))
    return client


@pytest.fixture
def cenario():
    """Uma conta com projeto faturado e uma venda aberta num degrau da escada.

    O projeto dá receita e custo aos três recortes do ROI e à linha de origem; a venda dá valor
    estimado a uma etapa do funil e a um degrau de produto. Os valores têm centavo **diferente de
    zero** de propósito: com `.00`, a asserção sobre a string passaria a medir só o zero à direita
    que o `float` come (`40000.00` → `40000.0`), e não que as duas casas chegam preservadas.
    """
    conta = AccountFactory(name="Conta da Régua")
    ProjectFactory(
        engagement__account=conta,
        service=Service.objects.get(tier=Service.Tier.PROVE),
        actual_value=Decimal("120000.07"),
        cost=Decimal("80000.03"),
    )
    # A primeira etapa aberta das quatro semeadas. `get(kind=OPEN)` traria `MultipleObjectsReturned`
    # — e as demais etapas abertas são justamente o que dá a este cenário a linha **sem**
    # oportunidade que o teste do nulo mede.
    etapa = PipelineStage.objects.filter(kind=PipelineStage.Kind.OPEN).order_by("position").first()
    CommercialOpportunityFactory(
        account=conta,
        stage=etapa,
        service=Service.objects.get(tier=Service.Tier.DISCOVERY_SPRINT),
        estimated_value=Decimal("3000.01"),
    )
    return SimpleNamespace(conta=conta, etapa=etapa)


def _etapa_de(linhas: list[dict], etapa_id: int) -> dict:
    return next(linha for linha in linhas if linha["id"] == etapa_id)


def test_o_dinheiro_da_analytics_sai_como_texto(api: APIClient, cenario) -> None:
    """Os sete campos que a ADR 0068 converteu, medidos no corpo renderizado."""
    corpo = api.get(reverse("analytics")).json()

    roi = corpo["roi"]
    assert roi["revenue"] == "120000.07"
    assert roi["cost"] == "80000.03"
    assert isinstance(roi["revenue"], str) and isinstance(roi["cost"], str)

    (por_conta,) = roi["by_client"]
    assert por_conta["revenue"] == "120000.07"
    assert por_conta["cost"] == "80000.03"
    assert isinstance(por_conta["revenue"], str) and isinstance(por_conta["cost"], str)

    (por_servico,) = roi["by_service"]
    assert isinstance(por_servico["revenue"], str) and isinstance(por_servico["cost"], str)

    degrau = next(
        linha for linha in corpo["funnel"]["by_tier"] if linha["tier"] == "discovery_sprint"
    )
    assert degrau["estimated_total"] == "3000.01"
    assert isinstance(degrau["estimated_total"], str)

    (origem,) = corpo["funnel"]["by_source"]
    assert origem["revenue"] == "120000.07"
    assert isinstance(origem["revenue"], str)

    aberta = _etapa_de(corpo["pipeline"], cenario.etapa.pk)
    assert aberta["estimated_total"] == "3000.01"
    assert isinstance(aberta["estimated_total"], str)


def test_o_indice_calculado_continua_numero(api: APIClient, cenario) -> None:
    """`roi` e as taxas são quocientes e ficam `float` — o outro lado do critério da ADR 0068.

    Sem esta metade, a próxima varredura atrás de "dinheiro que virou texto" converteria a razão
    junto, e `roi < 0` na tela passaria a comparar string com número — em JavaScript, em silêncio.
    """
    corpo = api.get(reverse("analytics")).json()

    assert isinstance(corpo["roi"]["roi"], float)
    # `avg_ticket` é o caso que testa o critério: é um valor em reais e mesmo assim fica número,
    # porque é `Avg` e não `Sum` — convertê-lo arredondaria uma estatística a duas casas, o que é
    # decisão de produto. `(int, float)` porque um ticket redondo renderiza como inteiro no JSON.
    assert isinstance(corpo["avg_ticket"], (int, float))
    degrau = next(
        linha for linha in corpo["funnel"]["by_tier"] if linha["tier"] == "discovery_sprint"
    )
    assert degrau["win_rate"] is None or isinstance(degrau["win_rate"], float)


def test_a_etapa_sem_oportunidade_continua_nula(api: APIClient, cenario) -> None:
    """`null` e `"0.00"` são fatos diferentes, e a conversão não pode confundi-los.

    `Sum` de queryset vazio é `NULL`: a etapa "Ganho" deste cenário não tem oportunidade nenhuma,
    e "não há o que somar" não é "somou zero". É a mesma regra do `nao_apurado` do custo do
    processo — preencher a ausência com zero apagaria a distinção nas duas telas que leem esta
    linha.
    """
    ganho = PipelineStage.objects.get(kind=PipelineStage.Kind.WON)
    analytics = api.get(reverse("analytics")).json()
    dashboard = api.get(reverse("dashboard")).json()

    assert _etapa_de(analytics["pipeline"], ganho.pk)["estimated_total"] is None
    assert _etapa_de(dashboard["pipeline"], ganho.pk)["estimated_total"] is None


def test_o_dashboard_emite_a_mesma_linha_de_etapa_que_a_analytics(api: APIClient, cenario) -> None:
    """A forma é declarada uma vez (`PipelineStageRowSerializer`) e convertida uma vez.

    O painel filtra diferente da análise (ele não esconde oportunidade arquivada), mas a linha é
    a mesma — e duas conversões paralelas divergiriam no dia em que alguém mexesse em só uma.
    """
    aberta = _etapa_de(api.get(reverse("dashboard")).json()["pipeline"], cenario.etapa.pk)

    assert aberta["estimated_total"] == "3000.01"
    assert isinstance(aberta["estimated_total"], str)


def test_o_roi_da_visao_de_conta_para_de_mentir(api: APIClient, cenario) -> None:
    """`AccountOverviewRoi` sempre declarou `type: string`; era o corpo que emitia número.

    O contrato desta rota **não muda** com a ADR 0068 — o que muda é passar a cumpri-lo. As duas
    portas (o grid e o detalhe) leem o mesmo `build_account_overview`, e as duas são medidas: sem
    a segunda, converter só na lista passaria despercebido.
    """
    (linha,) = api.get(reverse("client-overview")).json()["clients"]
    detalhe = api.get(f"/api/v1/clients/{cenario.conta.pk}/overview/").json()

    for corpo in (linha, detalhe):
        assert corpo["roi"]["revenue"] == "120000.07"
        assert corpo["roi"]["cost"] == "80000.03"
        assert isinstance(corpo["roi"]["revenue"], str)
        assert isinstance(corpo["roi"]["cost"], str)
        assert isinstance(corpo["roi"]["roi"], float)


def test_os_totais_do_summary_de_faturas_saem_como_texto(api: APIClient) -> None:
    """As três faixas na mesma forma de `Invoice.amount`, que a listagem ao lado já emitia.

    Aqui a faixa vazia **é** zero, e não nulo: `Sum(..., default=Decimal("0"))` responde "nenhuma
    fatura nesta faixa" com o total que ela de fato tem. É o contraste com a etapa do funil, onde
    a ausência de linha a somar é `null`.
    """
    conta = AccountFactory()
    InvoiceFactory(
        account=conta, status=Invoice.Status.ISSUED, number="2026-9001", amount=Decimal("100.01")
    )
    InvoiceFactory(
        account=conta, status=Invoice.Status.OVERDUE, number="2026-9002", amount=Decimal("200.02")
    )

    corpo = api.get("/api/v1/invoices/summary/").json()

    assert corpo["open"] == "100.01"
    assert corpo["overdue"] == "200.02"
    assert corpo["paid"] == "0.00"
    assert all(isinstance(corpo[faixa], str) for faixa in ("open", "overdue", "paid"))
    assert corpo["overdue_count"] == 1
