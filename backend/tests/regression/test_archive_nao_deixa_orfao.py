"""Arquivar um pai não podia deixar filho visível apontando para ele (FDD 025).

O soft delete do repo é por registro: `ArchiveModelViewSet.get_queryset` filtra o próprio
`archived_at` e nada mais. Como `ProjectViewSet` e `OpportunityViewSet` nunca olham
`client__archived_at`, arquivar um cliente sumia com ele da tela de Clientes e **mantinha** os
projetos e as oportunidades dele na lista — cada um exibindo o nome de um cliente que a interface
já não mostra, e sem caminho para descobrir por quê.

A conversão tem a mesma forma: `Project.opportunity` é `OneToOneField` com `PROTECT`, e arquivar a
oportunidade convertida deixava o projeto ligado a um registro escondido.

Nos dois casos o backend respondia **204**, em silêncio.
"""

from datetime import timedelta

import pytest
from django.urls import reverse
from django.utils import timezone
from rest_framework.test import APIClient

from apps.core.models import Contact, Opportunity, PipelineStage, Project, User
from apps.core.tests.factories import (
    ClientFactory,
    OpportunityFactory,
    ProjectFactory,
    UserFactory,
)


@pytest.fixture
def admin_client() -> APIClient:
    client = APIClient()
    client.force_authenticate(UserFactory(role=User.Role.ADMIN))
    return client


@pytest.mark.django_db
def test_cliente_com_projeto_aberto_nao_arquiva(admin_client: APIClient) -> None:
    project = ProjectFactory()

    resposta = admin_client.delete(reverse("client-detail", args=[project.client.pk]))

    assert resposta.status_code == 409
    assert "1 projeto(s)" in resposta.data["detail"]
    project.client.refresh_from_db()
    assert project.client.archived_at is None


@pytest.mark.django_db
def test_cliente_com_oportunidade_aberta_nao_arquiva(admin_client: APIClient) -> None:
    opportunity = OpportunityFactory()

    resposta = admin_client.delete(reverse("client-detail", args=[opportunity.client.pk]))

    assert resposta.status_code == 409
    assert "1 oportunidade(s)" in resposta.data["detail"]


@pytest.mark.django_db
def test_cliente_limpo_arquiva_e_leva_os_contatos_junto(admin_client: APIClient) -> None:
    cliente = ClientFactory()
    contato = Contact.objects.create(client=cliente, name="Quem decide", email="a@b.test")

    resposta = admin_client.delete(reverse("client-detail", args=[cliente.pk]))

    assert resposta.status_code == 204
    cliente.refresh_from_db()
    contato.refresh_from_db()
    assert cliente.is_archived
    # O contato acompanha em vez de bloquear: ninguém o lista fora do cliente, então deixá-lo ativo
    # não produziria órfão visível — mas restauraria um cliente com contatos "vivos" pela metade.
    assert contato.is_archived


@pytest.mark.django_db
def test_oportunidade_convertida_nao_arquiva(admin_client: APIClient) -> None:
    opportunity = OpportunityFactory(stage=PipelineStage.objects.get(kind="won"))
    converted = admin_client.post(
        reverse("opportunity-convert-to-project", args=[opportunity.pk]),
        {
            "client": opportunity.client_id,
            "name": "Projeto convertido",
            "start_date": str(timezone.localdate()),
            "due_date": str(timezone.localdate() + timedelta(days=10)),
        },
        format="json",
    )
    assert converted.status_code == 201

    resposta = admin_client.delete(reverse("opportunity-detail", args=[opportunity.pk]))

    assert resposta.status_code == 409
    assert "já virou o projeto" in resposta.data["detail"]
    opportunity.refresh_from_db()
    assert opportunity.archived_at is None


@pytest.mark.django_db
def test_arquivar_o_projeto_libera_o_cliente(admin_client: APIClient) -> None:
    """O caminho de saída existe: arquivado o trabalho, o cliente arquiva."""
    project = ProjectFactory()
    assert admin_client.delete(reverse("project-detail", args=[project.pk])).status_code == 204

    resposta = admin_client.delete(reverse("client-detail", args=[project.client.pk]))

    assert resposta.status_code == 204
    assert Project.objects.filter(pk=project.pk, archived_at__isnull=False).exists()
    assert Opportunity.objects.filter(client=project.client).count() == 0
