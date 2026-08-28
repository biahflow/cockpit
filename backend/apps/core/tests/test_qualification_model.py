"""A qualificação como entidade, e o que ela passa a impedir (ADR 0049, FDD 044).

Arquivo separado de `test_qualification.py`, que testa a **qualificação por IA** do lead
(`qualification.py`, FDD 013) — nome parecido, assunto diferente: lá a IA sugere, aqui alguém
decide.
"""

from datetime import timedelta
from decimal import Decimal

import pytest
from django.core.exceptions import ValidationError
from django.urls import reverse
from django.utils import timezone
from rest_framework.test import APIClient

from apps.core.models import (
    Client,
    Contact,
    Lead,
    Opportunity,
    PipelineStage,
    Project,
    Qualification,
    Service,
    User,
)

from .factories import (
    ClientFactory,
    LeadFactory,
    OpportunityFactory,
    QualificationFactory,
    ServiceFactory,
    UserFactory,
)

pytestmark = pytest.mark.django_db


@pytest.fixture
def vendas() -> User:
    return UserFactory(role=User.Role.SALES)


@pytest.fixture
def api(vendas: User) -> APIClient:
    client = APIClient()
    client.force_authenticate(vendas)
    return client


# --- POST /leads/{id}/convert/ ----------------------------------------------


def test_convert_cria_conta_e_qualificacao_sem_oportunidade(api: APIClient) -> None:
    """O defeito que a fatia corrige: a conversa de qualificação virava venda registrada."""
    lead = LeadFactory(company="ACME")

    response = api.post(reverse("lead-convert", args=[lead.pk]), format="json")

    assert response.status_code == 201
    corpo = response.json()
    assert corpo["qualification"]["outcome"] == Qualification.Outcome.QUALIFIED
    assert corpo["lead"]["status"] == Lead.Status.QUALIFIED
    lead.refresh_from_db()
    assert lead.client is not None
    assert lead.client.name == "ACME"
    assert lead.client.status == Client.Status.PROSPECT
    assert lead.opportunity_id is None
    assert Opportunity.objects.count() == 0
    assert lead.qualifications.get().account_id == lead.client_id


def test_convert_funciona_sem_pipeline_nem_servico_de_entrada(api: APIClient) -> None:
    """Qualificar não depende mais de o pipeline estar configurado — os dois 400 saíram."""
    PipelineStage.objects.all().delete()
    Service.objects.all().update(active=False)
    lead = LeadFactory()

    assert api.post(reverse("lead-convert", args=[lead.pk]), format="json").status_code == 201


def test_convert_nurture_sem_data_recusa(api: APIClient) -> None:
    lead = LeadFactory()

    response = api.post(
        reverse("lead-convert", args=[lead.pk]), {"outcome": "nurture"}, format="json"
    )

    assert response.status_code == 400
    assert "nurture_until" in response.json()
    assert Qualification.objects.count() == 0
    lead.refresh_from_db()
    assert not lead.is_archived  # a recusa não deixa o lead num estado meio-convertido


def test_convert_nurture_com_data_nao_arquiva_o_lead(api: APIClient) -> None:
    """O ponto do `nurture`: quem volta ao radar continua na lista ativa."""
    lead = LeadFactory()
    volta = timezone.localdate() + timedelta(days=180)

    response = api.post(
        reverse("lead-convert", args=[lead.pk]),
        {"outcome": "nurture", "nurture_until": str(volta)},
        format="json",
    )

    assert response.status_code == 201
    lead.refresh_from_db()
    assert not lead.is_archived
    assert lead.status == Lead.Status.CONTACTED
    assert lead.qualifications.get().nurture_until == volta


def test_convert_disqualified_descarta_e_arquiva(api: APIClient) -> None:
    lead = LeadFactory()

    response = api.post(
        reverse("lead-convert", args=[lead.pk]),
        {"outcome": "disqualified", "rationale": "Sem orçamento e sem urgência."},
        format="json",
    )

    assert response.status_code == 201
    lead.refresh_from_db()
    assert lead.status == Lead.Status.DISCARDED
    assert lead.is_archived
    assert lead.qualifications.get().rationale == "Sem orçamento e sem urgência."


def test_convert_reusa_a_conta_informada(api: APIClient) -> None:
    conta = ClientFactory(name="Conta que já existe")
    lead = LeadFactory()

    response = api.post(
        reverse("lead-convert", args=[lead.pk]), {"account_id": conta.pk}, format="json"
    )

    assert response.status_code == 201
    lead.refresh_from_db()
    assert lead.client_id == conta.pk
    assert Client.objects.count() == 1  # não criou uma segunda para a mesma empresa


def test_convert_recusa_conta_arquivada(api: APIClient) -> None:
    conta = ClientFactory()
    conta.archive()
    lead = LeadFactory()

    response = api.post(
        reverse("lead-convert", args=[lead.pk]), {"account_id": conta.pk}, format="json"
    )

    assert response.status_code == 400
    assert Qualification.objects.count() == 0


def test_convert_recusa_mudar_a_conta_de_um_lead_ja_vinculado(api: APIClient) -> None:
    """Trocar a conta deixaria a avaliação anterior apontando para a antiga."""
    lead = LeadFactory()
    api.post(
        reverse("lead-convert", args=[lead.pk]),
        {"outcome": "nurture", "nurture_until": str(timezone.localdate() + timedelta(days=30))},
        format="json",
    )

    response = api.post(
        reverse("lead-convert", args=[lead.pk]),
        {"account_id": ClientFactory().pk},
        format="json",
    )

    assert response.status_code == 400
    assert lead.qualifications.count() == 1


def test_segunda_qualificacao_de_lead_ja_qualificado_recusa(api: APIClient) -> None:
    """O lead qualificado sai da lista; restaurado, ele ainda não volta a ser qualificável.

    O caminho é real e é o único que alcança esta recusa: `qualified` arquiva, e a lista ativa já
    não o mostra — mas `POST /leads/{id}/unarchive/` existe desde a FDD 025, e sem a guarda a
    restauração devolveria o botão de converter e criaria uma segunda conta para a mesma empresa.
    """
    lead = LeadFactory()
    api.post(reverse("lead-convert", args=[lead.pk]), format="json")
    api.post(reverse("lead-unarchive", args=[lead.pk]), format="json")

    segunda = api.post(reverse("lead-convert", args=[lead.pk]), format="json")

    assert segunda.status_code == 409
    assert lead.qualifications.count() == 1


def test_lead_nutrido_pode_ser_reavaliado_reusando_a_conta(api: APIClient) -> None:
    """O `nurture` de hoje vira `qualified` em seis meses, na mesma conta (não em outra)."""
    lead = LeadFactory()
    api.post(
        reverse("lead-convert", args=[lead.pk]),
        {"outcome": "nurture", "nurture_until": str(timezone.localdate() + timedelta(days=30))},
        format="json",
    )
    conta = Client.objects.get()

    segunda = api.post(reverse("lead-convert", args=[lead.pk]), format="json")

    assert segunda.status_code == 201
    assert Client.objects.count() == 1
    assert lead.qualifications.count() == 2
    assert lead.qualifications.filter(account=conta).count() == 2


# --- Invariantes do modelo ---------------------------------------------------


def test_nurture_exige_data_de_retorno() -> None:
    qualification = QualificationFactory.build(outcome=Qualification.Outcome.NURTURE)
    with pytest.raises(ValidationError) as exc:
        qualification.clean()
    assert "nurture_until" in exc.value.message_dict


def test_data_de_retorno_sem_nurture_recusa() -> None:
    qualification = QualificationFactory.build(
        outcome=Qualification.Outcome.QUALIFIED, nurture_until=timezone.localdate()
    )
    with pytest.raises(ValidationError) as exc:
        qualification.clean()
    assert "nurture_until" in exc.value.message_dict


def test_conta_precisa_ser_a_do_lead() -> None:
    """Fronteira de conta: sem isto a avaliação pende da organização de outro lead."""
    lead = LeadFactory(client=ClientFactory())
    qualification = QualificationFactory.build(
        lead=lead, account=ClientFactory(), outcome=Qualification.Outcome.QUALIFIED
    )
    with pytest.raises(ValidationError) as exc:
        qualification.clean()
    assert "account" in exc.value.message_dict


# --- POST /qualifications/{id}/open-opportunity/ -----------------------------


def _abrir(api: APIClient, qualification: Qualification, **corpo: object):
    return api.post(
        reverse("qualification-open-opportunity", args=[qualification.pk]), corpo, format="json"
    )


@pytest.mark.parametrize("outcome", ["nurture", "disqualified"])
def test_qualificacao_nao_qualificada_nao_abre_oportunidade(
    api: APIClient, outcome: str
) -> None:
    """Invariante 5 do mapa de linguagem, na porta que existe para a venda."""
    extras = (
        {"nurture_until": timezone.localdate() + timedelta(days=30)}
        if outcome == "nurture"
        else {}
    )
    qualification = QualificationFactory(outcome=outcome, **extras)

    assert _abrir(api, qualification).status_code == 409
    assert Opportunity.objects.count() == 0


def test_open_opportunity_cria_a_venda_com_a_origem(api: APIClient, vendas: User) -> None:
    stage = PipelineStage.objects.filter(kind=PipelineStage.Kind.OPEN).order_by("position").first()
    qualification = QualificationFactory(rationale="Faturamento manual, 3 pessoas.")

    response = _abrir(api, qualification, estimated_value="45000.00")

    assert response.status_code == 201
    corpo = response.json()
    assert corpo["origin_qualification"] == qualification.pk
    opportunity = Opportunity.objects.get()
    assert opportunity.client_id == qualification.account_id
    assert opportunity.owner_id == vendas.pk
    assert opportunity.stage_id == stage.pk
    assert opportunity.scope == "Faturamento manual, 3 pessoas."
    assert opportunity.estimated_value == Decimal("45000.00")
    # Segunda chamada não duplica a venda.
    assert _abrir(api, qualification).status_code == 409
    assert Opportunity.objects.count() == 1


def test_open_opportunity_recusa_oferta_de_aquisicao(api: APIClient) -> None:
    porta = Service.objects.get(tier=Service.Tier.QUALIFICATION_CALL)
    qualification = QualificationFactory()

    response = _abrir(api, qualification, service=porta.pk)

    assert response.status_code == 400
    assert Opportunity.objects.count() == 0


def test_open_opportunity_sem_conta_recusa(api: APIClient) -> None:
    qualification = QualificationFactory(account=None)

    assert _abrir(api, qualification).status_code == 400


def test_open_opportunity_recusa_contato_de_outro_cliente(api: APIClient) -> None:
    """Fronteira de conta: um campo opcional é a pior forma de vazar entre clientes."""
    qualification = QualificationFactory()
    alheio = Contact.objects.create(client=ClientFactory(), first_name="Alguém", email="a@x.com")

    response = _abrir(api, qualification, contact=alheio.pk)

    assert response.status_code == 400
    assert Opportunity.objects.count() == 0


def test_open_opportunity_sem_estagio_aberto_recusa(api: APIClient) -> None:
    """O 400 que saiu do `convert` continua existindo — no ato que de fato precisa do pipeline."""
    qualification = QualificationFactory()
    PipelineStage.objects.filter(kind=PipelineStage.Kind.OPEN).delete()

    assert _abrir(api, qualification).status_code == 400


def test_lead_convertido_pelo_caminho_antigo_nao_reconverte(api: APIClient) -> None:
    """Guarda herdada: a linha antiga já tem venda, e converter de novo duplicaria a conta."""
    antigo = LeadFactory(opportunity=OpportunityFactory())

    response = api.post(reverse("lead-convert", args=[antigo.pk]), format="json")

    assert response.status_code == 409
    assert Qualification.objects.count() == 0


# --- Oferta de aquisição nunca vira projeto (invariante 6) -------------------


def test_convert_to_project_recusa_oferta_de_aquisicao(api: APIClient, vendas: User) -> None:
    porta = Service.objects.get(tier=Service.Tier.QUALIFICATION_CALL)
    opportunity = OpportunityFactory(
        stage=PipelineStage.objects.get(kind="won"), owner=vendas, service=porta
    )

    response = api.post(reverse("opportunity-convert-to-project", args=[opportunity.pk]), {
        "client": opportunity.client_id,
        "name": "Projeto que não deveria existir",
        "start_date": str(timezone.localdate()),
        "due_date": str(timezone.localdate() + timedelta(days=30)),
    }, format="json")

    assert response.status_code == 400
    assert Project.objects.count() == 0


def test_project_clean_recusa_oferta_de_aquisicao() -> None:
    porta = Service.objects.get(tier=Service.Tier.QUALIFICATION_CALL)
    project = Project(
        client=ClientFactory(), name="Projeto", owner=UserFactory(), service=porta,
        start_date=timezone.localdate(), due_date=timezone.localdate() + timedelta(days=10),
    )
    with pytest.raises(ValidationError) as exc:
        project.clean()
    assert "service" in exc.value.message_dict


def test_opportunity_clean_recusa_origem_nao_qualificada() -> None:
    """Invariante 5 no modelo: shell, admin e migração não passam pela view."""
    qualification = QualificationFactory(
        outcome=Qualification.Outcome.NURTURE,
        nurture_until=timezone.localdate() + timedelta(days=30),
    )
    opportunity = OpportunityFactory.build(
        client=qualification.account,
        stage=PipelineStage.objects.filter(kind="open").first(),
        owner=UserFactory(),
        origin_qualification=qualification,
    )
    with pytest.raises(ValidationError) as exc:
        opportunity.clean()
    assert "origin_qualification" in exc.value.message_dict


# --- Categoria do serviço ----------------------------------------------------


def test_qualification_call_e_aquisicao_e_o_resto_e_comercial() -> None:
    porta = Service.objects.get(tier=Service.Tier.QUALIFICATION_CALL)
    assert porta.category == Service.Category.ACQUISITION
    outros = Service.objects.exclude(tier=Service.Tier.QUALIFICATION_CALL)
    assert set(outros.values_list("category", flat=True)) == {Service.Category.COMMERCIAL}


def test_servico_novo_nasce_comercial() -> None:
    assert ServiceFactory().category == Service.Category.COMMERCIAL


# --- Permissões --------------------------------------------------------------


def test_entrega_nao_alcanca_qualificacoes() -> None:
    """Espelha `lead`: a qualificação nunca aparece no portal do cliente (mapa §3)."""
    client = APIClient()
    client.force_authenticate(UserFactory(role=User.Role.DELIVERY))
    assert client.get(reverse("qualification-list")).status_code == 403


@pytest.mark.parametrize("role", [User.Role.SALES, User.Role.ADMIN])
def test_vendas_e_admin_listam_qualificacoes(role: str) -> None:
    QualificationFactory()
    client = APIClient()
    client.force_authenticate(UserFactory(role=role))

    response = client.get(reverse("qualification-list"))

    assert response.status_code == 200


def test_criar_qualificacao_pela_api_grava_o_avaliador(api: APIClient, vendas: User) -> None:
    lead = LeadFactory()

    response = api.post(reverse("qualification-list"), {
        "lead": lead.pk, "outcome": "qualified", "fit": "high",
    }, format="json")

    assert response.status_code == 201
    assert Qualification.objects.get().assessor_id == vendas.pk


def test_api_recusa_nutrir_sem_data(api: APIClient) -> None:
    lead = LeadFactory()

    response = api.post(
        reverse("qualification-list"), {"lead": lead.pk, "outcome": "nurture"}, format="json"
    )

    assert response.status_code == 400
    assert "nurture_until" in response.json()


def test_filtro_por_lead_e_outcome(api: APIClient) -> None:
    lead = LeadFactory()
    QualificationFactory(lead=lead, outcome=Qualification.Outcome.QUALIFIED)
    QualificationFactory(
        lead=lead, outcome=Qualification.Outcome.NURTURE,
        nurture_until=timezone.localdate() + timedelta(days=10),
    )
    QualificationFactory()

    por_lead = api.get(reverse("qualification-list"), {"lead": lead.pk}).json()
    por_outcome = api.get(reverse("qualification-list"), {"outcome": "nurture"}).json()

    assert len(por_lead) == 2
    assert len(por_outcome) == 1
