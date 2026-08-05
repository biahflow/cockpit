"""Regressão: Entrega não escreve artefato ligado a oportunidade (FDD 016, FDD 017).

A FDD 016 decidiu que proposta e contrato ficam fora do alcance de quem é da Entrega, mas a
segregação só existia no `get_queryset` — ou seja, só na **leitura**. `RolePermission` libera
`POST` de `artifact` para `delivery` e o serializer aceitava `opportunity`, então dava para
gravar um artefato comercial que em seguida sumia da própria lista.
"""

import pytest
from django.urls import reverse
from rest_framework.test import APIClient

from apps.core.models import Artifact, User
from apps.core.tests.factories import (
    ArtifactFactory,
    OpportunityFactory,
    ProjectFactory,
    UserFactory,
)

pytestmark = pytest.mark.django_db


def _delivery_client() -> APIClient:
    api = APIClient()
    api.force_authenticate(UserFactory(role=User.Role.DELIVERY))
    return api


def test_delivery_cannot_create_an_artifact_linked_to_an_opportunity() -> None:
    opportunity = OpportunityFactory()

    response = _delivery_client().post(reverse("artifact-list"), {
        "kind": Artifact.Kind.PROPOSAL,
        "title": "Proposta",
        "content": "Investimento de R$ 120.000.",
        "opportunity": opportunity.id,
    }, format="json")

    assert response.status_code == 403
    assert not Artifact.objects.filter(opportunity=opportunity).exists()


def test_delivery_still_creates_artifacts_linked_to_a_project() -> None:
    project = ProjectFactory()

    response = _delivery_client().post(reverse("artifact-list"), {
        "kind": Artifact.Kind.DISCOVERY,
        "title": "Discovery",
        "content": "Processo manual de faturamento.",
        "project": project.id,
    }, format="json")

    assert response.status_code == 201


def test_delivery_cannot_reach_a_commercial_artifact_by_id() -> None:
    artifact = ArtifactFactory(opportunity=OpportunityFactory())
    api = _delivery_client()

    assert api.get(reverse("artifact-detail", args=[artifact.id])).status_code == 404
    assert api.patch(
        reverse("artifact-detail", args=[artifact.id]), {"content": "editado"}, format="json"
    ).status_code == 404
