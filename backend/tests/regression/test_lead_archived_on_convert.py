"""Regressão: converter um lead o arquiva (sai da lista ativa) e cria cliente prospect."""

import pytest
from django.urls import reverse
from rest_framework.test import APIClient

from apps.core.models import Client, Lead, User
from apps.core.tests.factories import UserFactory


@pytest.mark.django_db
def test_convert_archives_lead_and_creates_prospect_client() -> None:
    sales = UserFactory(role=User.Role.SALES)
    lead = Lead.objects.create(name="Fulano", email="f@x.com", company="ACME")
    client = APIClient()
    client.force_authenticate(sales)

    resp = client.post(reverse("lead-convert", args=[lead.pk]), format="json")
    assert resp.status_code == 201

    lead.refresh_from_db()
    assert lead.is_archived  # sai da lista ativa
    assert Client.objects.get(pk=lead.client_id).status == Client.Status.PROSPECT

    # a lista ativa de leads não traz mais o convertido
    listed = client.get(reverse("lead-list")).json()
    ids = [item["id"] for item in (listed if isinstance(listed, list) else listed["results"])]
    assert lead.pk not in ids
