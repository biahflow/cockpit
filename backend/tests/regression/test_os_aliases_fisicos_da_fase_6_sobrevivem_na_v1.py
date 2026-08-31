"""Regressão: os campos renomeados/removidos na Fase 6 preservam a escrita da `/api/v1/`.

`ai_opportunity` virou `ai_potential` e `Project.client` deixou de ser coluna. Os nomes antigos
continuam no contrato v1 até a `/api/v2/`: o primeiro ainda grava o campo canônico; o segundo é
validado contra `engagement.account`, que passou a ser a única fonte da conta do projeto.
"""

from __future__ import annotations

import pytest
from django.urls import reverse
from rest_framework.test import APIClient

from apps.core.models import PipelineStage, User
from apps.core.tests.factories import (
    AccountFactory,
    CommercialOpportunityFactory,
    ProjectFactory,
    UserFactory,
)


@pytest.fixture
def admin_api() -> APIClient:
    api = APIClient()
    api.force_authenticate(UserFactory(role=User.Role.ADMIN))
    return api


@pytest.mark.django_db
def test_ai_opportunity_ainda_grava_ai_potential_na_v1(admin_api: APIClient) -> None:
    projeto = ProjectFactory(ai_potential=10)

    resposta = admin_api.patch(
        reverse("project-detail", args=[projeto.pk]),
        {"ai_opportunity": 73},
        format="json",
    )

    assert resposta.status_code == 200, resposta.data
    projeto.refresh_from_db()
    assert projeto.ai_potential == 73
    assert resposta.data["ai_potential"] == resposta.data["ai_opportunity"] == 73


@pytest.mark.django_db
def test_ai_potential_canonico_vence_quando_as_duas_chaves_chegam(admin_api: APIClient) -> None:
    projeto = ProjectFactory(ai_potential=10)

    resposta = admin_api.patch(
        reverse("project-detail", args=[projeto.pk]),
        {"ai_potential": 64, "ai_opportunity": 73},
        format="json",
    )

    assert resposta.status_code == 200, resposta.data
    projeto.refresh_from_db()
    assert projeto.ai_potential == 64


@pytest.mark.django_db
def test_client_legado_nao_pode_apontar_para_conta_alheia(admin_api: APIClient) -> None:
    projeto = ProjectFactory()

    resposta = admin_api.patch(
        reverse("project-detail", args=[projeto.pk]),
        {"client": AccountFactory().pk},
        format="json",
    )

    assert resposta.status_code == 400
    assert "engagement" in resposta.data


@pytest.mark.django_db
def test_client_legado_divergente_e_recusado_na_conversao_sem_engagement(
    admin_api: APIClient,
) -> None:
    oportunidade = CommercialOpportunityFactory(
        stage=PipelineStage.objects.get(kind=PipelineStage.Kind.WON)
    )

    resposta = admin_api.post(
        reverse("opportunity-convert-to-project", args=[oportunidade.pk]),
        {
            "client": AccountFactory().pk,
            "name": "Projeto na conta errada",
            "start_date": "2026-08-30",
            "due_date": "2026-09-30",
        },
        format="json",
    )

    assert resposta.status_code == 400
    assert "client" in resposta.data
    assert not oportunidade.projects.exists()
