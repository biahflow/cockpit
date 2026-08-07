"""Regressão: case anonimizado não expõe nome, razão social nem CNPJ (FDD 027).

`anonymized` é a autorização de usar o resultado **sem** a marca — "uma imobiliária de médio
porte". Se o nome vazar por qualquer projeção, a permissão que o cliente deu vira a permissão que
ele não deu, e o estrago é o de sempre nesta classe: irreversível, porque já foi lido.

Dois vazamentos são fáceis de deixar passar e por isso estão nomeados aqui: o **título**, que o
congelamento monta como "Cliente — Projeto", e o **contexto da proposta**, que é texto solto onde
ninguém está olhando para campos.
"""

from decimal import Decimal

import pytest
from rest_framework.test import APIClient

from apps.core import ai, cases
from apps.core.models import Case, Client, Opportunity, Project, Vertical
from apps.core.tests.factories import (
    ClientFactory,
    OpportunityFactory,
    ProjectFactory,
    UserFactory,
)

NOME = "Imobiliária Aurora Participações"
RAZAO = "Aurora Participações Ltda."
CNPJ = "12.345.678/0001-90"


def _case_publicado_anonimo(vertical: Vertical) -> Case:
    client = ClientFactory(name=NOME, legal_name=RAZAO, tax_id=CNPJ, vertical=vertical)
    project = ProjectFactory(
        client=client, name="Implantação de agentes",
        actual_value=Decimal("100.00"), cost=Decimal("50.00"),
    )
    project.status = Project.Status.COMPLETED
    project.save()
    case = Case.objects.get(project=project)
    case.anonymized = True
    case.summary = "Ganho relevante em qualificação de leads."
    case.save()
    cases.record_consent(case, UserFactory(role="admin"))
    case.status = Case.Status.PUBLISHED
    case.save()
    return case


@pytest.mark.django_db
def test_a_serializacao_do_case_anonimo_nao_traz_o_cliente() -> None:
    vertical = Vertical.objects.create(name="Imobiliárias", slug="imobiliarias")
    case = _case_publicado_anonimo(vertical)
    api = APIClient()
    api.force_authenticate(UserFactory(role="admin"))

    corpo = str(api.get(f"/api/v1/cases/{case.pk}/").data)

    assert NOME not in corpo
    assert RAZAO not in corpo
    assert CNPJ not in corpo


@pytest.mark.django_db
def test_a_listagem_de_cases_tambem_nao_traz_o_cliente() -> None:
    vertical = Vertical.objects.create(name="Imobiliárias", slug="imobiliarias")
    _case_publicado_anonimo(vertical)
    api = APIClient()
    api.force_authenticate(UserFactory(role="admin"))

    assert NOME not in str(api.get("/api/v1/cases/").data)


@pytest.mark.django_db
def test_a_proposta_cita_o_setor_e_nunca_o_nome() -> None:
    vertical = Vertical.objects.create(name="Imobiliárias", slug="imobiliarias")
    _case_publicado_anonimo(vertical)
    outra: Opportunity = OpportunityFactory(
        client=ClientFactory(name="Cliente novo", vertical=vertical)
    )

    contexto = ai.build_opportunity_context(outra)

    assert "Uma empresa do setor Imobiliárias" in contexto
    assert NOME not in contexto
    assert RAZAO not in contexto
    assert CNPJ not in contexto


@pytest.mark.django_db
def test_case_nao_anonimizado_continua_dizendo_quem_e() -> None:
    """A contraprova: a omissão é do anonimato, não um apagão geral."""
    vertical = Vertical.objects.create(name="Imobiliárias", slug="imobiliarias")
    case = _case_publicado_anonimo(vertical)
    Case.objects.filter(pk=case.pk).update(anonymized=False)
    api = APIClient()
    api.force_authenticate(UserFactory(role="admin"))

    corpo = api.get(f"/api/v1/cases/{case.pk}/").data

    assert corpo["client_name"] == NOME
    # Razão social e CNPJ nunca são projetados: o case não precisa deles em caso nenhum.
    assert RAZAO not in str(corpo)
    assert CNPJ not in str(corpo)


@pytest.mark.django_db
def test_o_cliente_do_case_continua_intacto_no_cadastro() -> None:
    """Anonimizar é uma decisão de publicação, não uma edição do cliente."""
    vertical = Vertical.objects.create(name="Imobiliárias", slug="imobiliarias")
    case = _case_publicado_anonimo(vertical)

    cliente = Client.objects.get(pk=case.project.client_id)

    assert (cliente.name, cliente.legal_name, cliente.tax_id) == (NOME, RAZAO, CNPJ)
