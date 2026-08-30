"""Activities do CRM: interação comercial com o cliente (FDD 035, ADR 0030)."""

from datetime import timedelta

import pytest
from django.urls import reverse
from django.utils import timezone
from rest_framework.test import APIClient

from apps.core.models import Activity, User

from .factories import (
    AccountFactory,
    ActivityFactory,
    CommercialOpportunityFactory,
    ProjectFactory,
    ProjectMemberFactory,
    UserFactory,
)


@pytest.fixture
def client() -> APIClient:
    return APIClient()


@pytest.mark.django_db
def test_sales_cria_le_edita_e_arquiva_activity(client: APIClient) -> None:
    sales = UserFactory(role=User.Role.SALES)
    cliente = AccountFactory()
    client.force_authenticate(sales)

    created = client.post(
        reverse("activity-list"),
        {
            "account": cliente.id,
            "kind": Activity.Kind.CALL,
            "happened_on": str(timezone.localdate()),
            "summary": "Ligação de alinhamento",
        },
        format="json",
    )
    assert created.status_code == 201
    assert created.data["owner"] == sales.id
    activity_id = created.data["id"]

    updated = client.patch(
        reverse("activity-detail", args=[activity_id]), {"summary": "Ligação remarcada"}, format="json"
    )
    assert updated.status_code == 200
    assert updated.data["summary"] == "Ligação remarcada"

    archived = client.delete(reverse("activity-detail", args=[activity_id]))
    assert archived.status_code == 204
    assert activity_id not in [item["id"] for item in client.get(reverse("activity-list")).data]

    restored = client.post(reverse("activity-unarchive", args=[activity_id]))
    assert restored.status_code == 200
    assert activity_id in [item["id"] for item in client.get(reverse("activity-list")).data]


@pytest.mark.django_db
def test_delivery_le_mas_nao_escreve(client: APIClient) -> None:
    delivery = UserFactory(role=User.Role.DELIVERY)
    project = ProjectFactory()
    ProjectMemberFactory(project=project, user=delivery)
    activity = ActivityFactory(account=project.engagement.account)
    client.force_authenticate(delivery)

    listed = client.get(reverse("activity-list"))
    rejected_create = client.post(
        reverse("activity-list"),
        {
            "account": project.engagement.account_id,
            "kind": Activity.Kind.NOTE,
            "happened_on": str(timezone.localdate()),
            "summary": "Nota indevida",
        },
        format="json",
    )
    rejected_update = client.patch(
        reverse("activity-detail", args=[activity.id]), {"summary": "Alteração indevida"}, format="json"
    )
    rejected_archive = client.delete(reverse("activity-detail", args=[activity.id]))

    assert listed.status_code == 200
    assert [item["id"] for item in listed.data] == [activity.id]
    assert rejected_create.status_code == 403
    assert rejected_update.status_code == 403
    assert rejected_archive.status_code == 403


@pytest.mark.django_db
def test_delivery_nao_ve_activity_de_cliente_fora_do_seu_projeto(client: APIClient) -> None:
    delivery = UserFactory(role=User.Role.DELIVERY)
    ActivityFactory()
    client.force_authenticate(delivery)

    listed = client.get(reverse("activity-list"))

    assert listed.status_code == 200
    assert listed.data == []


@pytest.mark.django_db
def test_admin_gerencia_activity_de_qualquer_cliente(client: APIClient) -> None:
    admin = UserFactory(role=User.Role.ADMIN)
    activity = ActivityFactory()
    client.force_authenticate(admin)

    response = client.get(reverse("activity-list"))

    assert response.status_code == 200
    assert activity.id in [item["id"] for item in response.data]


@pytest.mark.django_db
def test_activity_com_oportunidade_de_outro_cliente_e_recusada(client: APIClient) -> None:
    sales = UserFactory(role=User.Role.SALES)
    cliente = AccountFactory()
    oportunidade_de_outro_cliente = CommercialOpportunityFactory()
    client.force_authenticate(sales)

    response = client.post(
        reverse("activity-list"),
        {
            "account": cliente.id,
            "commercial_opportunity": oportunidade_de_outro_cliente.id,
            "kind": Activity.Kind.EMAIL,
            "happened_on": str(timezone.localdate()),
            "summary": "E-mail de follow-up",
        },
        format="json",
    )

    assert response.status_code == 400
    assert "commercial_opportunity" in response.data


@pytest.mark.django_db
def test_activity_com_oportunidade_do_mesmo_cliente_e_aceita(client: APIClient) -> None:
    sales = UserFactory(role=User.Role.SALES)
    oportunidade = CommercialOpportunityFactory()
    client.force_authenticate(sales)

    response = client.post(
        reverse("activity-list"),
        {
            "account": oportunidade.account_id,
            "commercial_opportunity": oportunidade.id,
            "kind": Activity.Kind.MEETING,
            "happened_on": str(timezone.localdate()),
            "summary": "Reunião de descoberta",
        },
        format="json",
    )

    assert response.status_code == 201


@pytest.mark.django_db
def test_filtro_por_client_e_opportunity(client: APIClient) -> None:
    admin = UserFactory(role=User.Role.ADMIN)
    oportunidade = CommercialOpportunityFactory()
    da_oportunidade = ActivityFactory(account=oportunidade.account, commercial_opportunity=oportunidade)
    do_mesmo_cliente_sem_oportunidade = ActivityFactory(account=oportunidade.account)
    de_outro_cliente = ActivityFactory()
    client.force_authenticate(admin)

    by_client = client.get(reverse("activity-list"), {"account": oportunidade.account_id})
    by_opportunity = client.get(
        reverse("activity-list"), {"commercial_opportunity": oportunidade.id}
    )

    assert {item["id"] for item in by_client.data} == {
        da_oportunidade.id,
        do_mesmo_cliente_sem_oportunidade.id,
    }
    assert de_outro_cliente.id not in {item["id"] for item in by_client.data}
    assert [item["id"] for item in by_opportunity.data] == [da_oportunidade.id]


@pytest.mark.django_db
def test_clean_recusa_oportunidade_de_outro_cliente_no_model() -> None:
    from django.core.exceptions import ValidationError

    cliente = AccountFactory()
    oportunidade_de_outro_cliente = CommercialOpportunityFactory()
    activity = Activity(
        account=cliente,
        commercial_opportunity=oportunidade_de_outro_cliente,
        kind=Activity.Kind.NOTE,
        happened_on=timezone.localdate() - timedelta(days=1),
        summary="Nota inválida",
    )

    with pytest.raises(ValidationError):
        activity.clean()
