"""Regressão: a origem do lead sobrevive à conversão em oportunidade e em projeto (FDD 030).

O desperdício de demanda mora em canal que gera lead e não gera cliente, e a FDD 030 pede a
pergunta inteira: **que canal produz negócio fechado**, não quantos leads entraram. A travessia
`projeto → oportunidade → lead → source` já existia em chaves desde a FDD 013; o que faltava era
o leitor. Este arquivo é o que impede a travessia de se romper sem ninguém notar — ela é feita de
duas relações que uma migração distraída pode afrouxar, e o sintoma seria silencioso: a tabela
continuaria renderizando, com todo negócio caindo em "Cadastro direto".

Desde a ADR 0049 a travessia tem **um elo a mais**: converter o lead registra uma `Qualification`,
e a venda só nasce em `POST /qualifications/{id}/open-opportunity/`. É essa ação que religa
`Lead.opportunity` — sem isso, todo negócio nascido de lead cairia em "Cadastro direto" e esta
tela erraria em silêncio, que é exatamente o que os testes abaixo medem.

As duas armadilhas medidas, cada uma com seu teste:

* **o lead convertido está arquivado.** `LeadViewSet.convert` chama `lead.archive()`, então o
  reflexo do resto de `AnalyticsView` — filtrar `archived_at__isnull=True` — apagaria da conta
  exatamente os leads que fecharam, e a coluna "entraram" ficaria **menor** que a coluna "ganhas"
  ao lado dela;
* **oportunidade sem lead precisa de nome.** Cadastro direto é um canal como qualquer outro, e
  sem uma linha própria os totais por origem não reconciliam com `funnel.opportunities.won` —
  uma tabela que não bate com a de cima ensina a não confiar nas duas.
"""

from datetime import timedelta

import pytest
from django.urls import reverse
from django.utils import timezone
from rest_framework.test import APIClient

from apps.core.models import Lead, Opportunity, PipelineStage, Qualification, User
from apps.core.tests.factories import OpportunityFactory, UserFactory

pytestmark = pytest.mark.django_db


def _converter_e_abrir(api: APIClient, lead: Lead) -> Opportunity:
    """Os dois atos da sequência normativa: qualificar o lead e então abrir a venda (ADR 0049)."""
    convertido = api.post(reverse("lead-convert", args=[lead.id]), {}, format="json")
    assert convertido.status_code == 201, convertido.data
    qualification = Qualification.objects.get(pk=convertido.data["qualification"]["id"])
    aberta = api.post(
        reverse("qualification-open-opportunity", args=[qualification.pk]), {}, format="json"
    )
    assert aberta.status_code == 201, aberta.data
    lead.refresh_from_db()
    return Opportunity.objects.get(pk=aberta.data["id"])


def _fechar(api: APIClient, opportunity: Opportunity, owner: User) -> None:
    """Leva a oportunidade a Ganho e converte em projeto pela rota real."""
    opportunity.stage = PipelineStage.objects.get(kind=PipelineStage.Kind.WON)
    opportunity.save(update_fields=["stage"])
    response = api.post(
        reverse("opportunity-convert-to-project", args=[opportunity.id]),
        {
            "client": opportunity.client_id,
            "name": f"Projeto {opportunity.id}",
            "owner": owner.id,
            "start_date": str(timezone.localdate()),
            "due_date": str(timezone.localdate() + timedelta(days=10)),
            "status": "planning",
        },
        format="json",
    )
    assert response.status_code == 201, response.data


@pytest.fixture
def sales() -> User:
    return UserFactory(role=User.Role.SALES)


@pytest.fixture
def api(sales: User) -> APIClient:
    client = APIClient()
    client.force_authenticate(sales)
    return client


def _by_source(api: APIClient) -> dict[str, dict]:
    response = api.get("/api/v1/analytics/")
    assert response.status_code == 200
    return {row["source"]: row for row in response.data["funnel"]["by_source"]}


def test_origem_atravessa_as_duas_conversoes(api: APIClient, sales: User) -> None:
    """O `source` do lead chega ao negócio fechado, pelas duas rotas de conversão."""
    lead = Lead.objects.create(name="Ana", email="ana@exemplo.com", source="indicacao")
    opportunity = _converter_e_abrir(api, lead)

    assert lead.opportunity_id == opportunity.pk
    _fechar(api, opportunity, sales)

    linha = _by_source(api)["indicacao"]
    assert linha["won"] == 1
    assert linha["projects"] == 1


def test_lead_arquivado_pela_conversao_continua_contando_como_entrada(
    api: APIClient, sales: User
) -> None:
    """A entrada é contada sobre `Lead.objects` inteiro — senão quem fecha some da conta.

    É a armadilha central: converter **arquiva** o lead, de modo que o filtro `active` que o
    resto de `AnalyticsView` aplica produziria uma origem com mais negócios ganhos do que leads
    recebidos. O teste afirma a desigualdade que precisa valer.
    """
    lead = Lead.objects.create(name="Bruno", email="bruno@exemplo.com", source="indicacao")
    opportunity = _converter_e_abrir(api, lead)
    assert lead.archived_at is not None, "a conversão deixou de arquivar; o teste perdeu o alvo"
    _fechar(api, opportunity, sales)

    linha = _by_source(api)["indicacao"]
    assert linha["leads"] == 1
    assert linha["won"] == 1
    assert linha["leads"] >= linha["won"]


def test_negocio_sem_lead_tem_origem_propria_e_os_totais_reconciliam(
    api: APIClient, sales: User
) -> None:
    """Oportunidade cadastrada à mão vira "direto", e a soma bate com o funil de cima."""
    lead = Lead.objects.create(name="Carla", email="carla@exemplo.com", source="site")
    _fechar(api, _converter_e_abrir(api, lead), sales)
    _fechar(api, OpportunityFactory(owner=sales), sales)

    funnel = api.get("/api/v1/analytics/").data["funnel"]
    por_origem = {row["source"]: row for row in funnel["by_source"]}
    assert por_origem["direto"]["won"] == 1
    assert por_origem["site"]["won"] == 1
    assert sum(row["won"] for row in funnel["by_source"]) == funnel["opportunities"]["won"]


def test_receita_nao_dobra_quando_dois_leads_apontam_o_mesmo_negocio(
    api: APIClient, sales: User
) -> None:
    """`Opportunity.leads` é reverso de FK: agrupar por `join` somaria a receita duas vezes.

    É a razão de a origem sair de `Subquery` e não de `join`, e o modo de falha é o pior tipo —
    um número de dinheiro maior que o verdadeiro, numa tela cujo propósito é decidir onde
    investir. Dois leads no mesmo negócio é o que acontece quando a mesma pessoa preenche o
    formulário duas vezes e alguém liga os dois à mesma oportunidade.
    """
    primeiro = Lead.objects.create(name="Dora", email="dora@exemplo.com", source="indicacao")
    opportunity = _converter_e_abrir(api, primeiro)
    Lead.objects.create(
        name="Dora (2)",
        email="dora@exemplo.com",
        source="indicacao",
        opportunity=opportunity,
    )
    _fechar(api, opportunity, sales)

    projeto = opportunity.projects.get()
    projeto.actual_value = 50000
    projeto.save(update_fields=["actual_value"])

    linha = _by_source(api)["indicacao"]
    assert linha["projects"] == 1
    assert float(linha["revenue"]) == 50000.0
