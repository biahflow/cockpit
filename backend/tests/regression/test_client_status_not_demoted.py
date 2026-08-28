"""Regressão: um PATCH não desfaz a promoção que a oportunidade ganha causou.

`status` deixou de ser somente-leitura para que quem cadastra declare o que o cliente é. O risco
que isso abre é o inverso da promoção: rebaixar para prospect alguém que já fechou. O signal só
promove na transição, então ele não corrigiria de volta — a recusa é a única proteção.
"""

import pytest
from django.urls import reverse
from rest_framework.test import APIClient

from apps.core.models import Client, PipelineStage, User
from apps.core.tests.factories import ClientFactory, CommercialOpportunityFactory, UserFactory


@pytest.mark.django_db
def test_client_with_won_opportunity_cannot_return_to_prospect() -> None:
    client = ClientFactory(status=Client.Status.PROSPECT)
    won = PipelineStage.objects.get(kind=PipelineStage.Kind.WON)
    CommercialOpportunityFactory(client=client, stage=won)
    api = APIClient()
    api.force_authenticate(UserFactory(role=User.Role.ADMIN))

    response = api.patch(
        reverse("client-detail", args=[client.pk]), {"status": "prospect"}, format="json"
    )

    assert response.status_code == 400
    client.refresh_from_db()
    assert client.status == Client.Status.ACTIVE


@pytest.mark.django_db
def test_client_without_won_opportunity_can_be_corrected() -> None:
    client = ClientFactory(status=Client.Status.ACTIVE)
    CommercialOpportunityFactory(client=client)  # etapa aberta
    api = APIClient()
    api.force_authenticate(UserFactory(role=User.Role.ADMIN))

    response = api.patch(
        reverse("client-detail", args=[client.pk]), {"status": "prospect"}, format="json"
    )

    assert response.status_code == 200
    client.refresh_from_db()
    assert client.status == Client.Status.PROSPECT
