"""Regressão: o ROI financeiro de um case nunca entra na proposta de outro cliente (FDD 027).

`roi_snapshot` guarda receita, custo e margem do projeto — número interno da casa. O contexto de
`build_opportunity_context` alimenta o texto de uma **proposta**, que o cliente lê: deixar o ROI
escorrer para lá entregaria a margem da casa e o faturamento de um terceiro no mesmo parágrafo.

O que o case leva à proposta é o que o cliente comprou — a métrica operacional do Funcionário
Digital e a saúde da entrega —, não o que a casa ganhou com ele. E só case **publicado com
consentimento**: um rascunho é material de trabalho, não prova autorizada.
"""

from decimal import Decimal

import pytest

from apps.core import ai, cases
from apps.core.models import Case, DigitalEmployee, KpiDirection, KpiUnit, Project, Vertical
from apps.core.tests.factories import (
    ClientFactory,
    CommercialOpportunityFactory,
    ProjectFactory,
    UserFactory,
)

RECEITA = "487500.00"
CUSTO = "212300.00"


def _vertical() -> Vertical:
    return Vertical.objects.create(name="Imobiliárias", slug="imobiliarias")


def _case_entregue(vertical: Vertical) -> Case:
    project = ProjectFactory(
        client=ClientFactory(name="Cliente antigo", vertical=vertical),
        actual_value=Decimal(RECEITA), cost=Decimal(CUSTO),
    )
    DigitalEmployee.objects.create(
        project=project, name="SDR", kpi_label="Leads qualificados/mês",
        kpi_unit=KpiUnit.COUNT, kpi_direction=KpiDirection.UP,
        kpi_baseline=Decimal("12.00"), kpi_current=Decimal("48.00"),
        roi_month=Decimal("8000.00"),
    )
    project.status = Project.Status.COMPLETED
    project.save()
    return Case.objects.get(project=project)


def _publicar(case: Case) -> Case:
    cases.record_consent(case, UserFactory(role="admin"))
    case.status = Case.Status.PUBLISHED
    case.save()
    return case


@pytest.mark.django_db
def test_a_proposta_cita_a_metrica_e_nunca_a_receita_nem_o_custo() -> None:
    vertical = _vertical()
    case = _publicar(_case_entregue(vertical))
    nova = CommercialOpportunityFactory(client=ClientFactory(name="Cliente novo", vertical=vertical))

    contexto = ai.build_opportunity_context(nova)

    assert "Leads qualificados/mês: de 12.00 para 48.00" in contexto
    assert RECEITA not in contexto
    assert CUSTO not in contexto
    assert str(case.roi_snapshot["roi"]) not in contexto


@pytest.mark.django_db
def test_case_em_rascunho_nao_entra_na_proposta() -> None:
    vertical = _vertical()
    _case_entregue(vertical)  # fica em rascunho, sem consentimento
    nova = CommercialOpportunityFactory(client=ClientFactory(name="Cliente novo", vertical=vertical))

    assert "Cases já entregues" not in ai.build_opportunity_context(nova)


@pytest.mark.django_db
def test_case_de_outra_vertical_nao_entra_na_proposta() -> None:
    _publicar(_case_entregue(_vertical()))
    outra = Vertical.objects.create(name="Saúde", slug="saude")
    nova = CommercialOpportunityFactory(client=ClientFactory(name="Cliente novo", vertical=outra))

    assert "Cases já entregues" not in ai.build_opportunity_context(nova)


@pytest.mark.django_db
def test_case_arquivado_nao_entra_na_proposta() -> None:
    vertical = _vertical()
    _publicar(_case_entregue(vertical)).archive()
    nova = CommercialOpportunityFactory(client=ClientFactory(name="Cliente novo", vertical=vertical))

    assert "Cases já entregues" not in ai.build_opportunity_context(nova)


@pytest.mark.django_db
def test_metrica_sem_base_registrada_diz_a_lacuna_em_vez_de_um_zero() -> None:
    vertical = _vertical()
    project = ProjectFactory(client=ClientFactory(vertical=vertical))
    DigitalEmployee.objects.create(
        project=project, name="Cobrador", kpi_label="Dias de atraso",
        kpi_unit=KpiUnit.HOURS, kpi_direction=KpiDirection.DOWN, kpi_current=Decimal("12.00"),
    )
    project.status = Project.Status.COMPLETED
    project.save()
    _publicar(Case.objects.get(project=project))
    nova = CommercialOpportunityFactory(client=ClientFactory(name="Cliente novo", vertical=vertical))

    contexto = ai.build_opportunity_context(nova)

    assert "sem base registrada no início" in contexto
    assert "de 0 para" not in contexto


@pytest.mark.django_db
def test_cliente_sem_vertical_nao_recebe_case_de_setor_nenhum() -> None:
    """Sem setor não há "mesmo setor": citar qualquer case seria prova fraca vendida como forte."""
    _publicar(_case_entregue(_vertical()))
    nova = CommercialOpportunityFactory(client=ClientFactory(name="Sem setor", vertical=None))

    assert "Cases já entregues" not in ai.build_opportunity_context(nova)
