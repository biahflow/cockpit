"""Regressão: cliente prospect vira ativo quando a oportunidade é ganha."""

import pytest

from apps.core.models import Client, PipelineStage
from apps.core.tests.factories import ClientFactory, CommercialOpportunityFactory


@pytest.mark.django_db
def test_won_opportunity_promotes_prospect_client() -> None:
    client = ClientFactory(status=Client.Status.PROSPECT)
    won = PipelineStage.objects.get(kind=PipelineStage.Kind.WON)

    CommercialOpportunityFactory(client=client, stage=won)

    client.refresh_from_db()
    assert client.status == Client.Status.ACTIVE


@pytest.mark.django_db
def test_open_opportunity_keeps_client_prospect() -> None:
    client = ClientFactory(status=Client.Status.PROSPECT)
    CommercialOpportunityFactory(client=client)  # etapa OPEN por padrão

    client.refresh_from_db()
    assert client.status == Client.Status.PROSPECT
