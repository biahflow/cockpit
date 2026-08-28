"""Regressão: converter arquiva o lead — **exceto** quando o resultado é nutrir (ADR 0049).

A asserção original continua valendo para `qualified`: o lead sai da lista ativa e a conta nasce
prospect. O que a fatia da `Qualification` acrescenta é o outro lado — quem foi marcado para
nutrição **não** é arquivado, porque o ponto do `nurture` é justamente voltar ao radar em
`nurture_until`, e um lead escondido é um lead que ninguém retoma.
"""

import pytest
from django.urls import reverse
from django.utils import timezone
from rest_framework.test import APIClient

from apps.core.models import Account, Lead, User
from apps.core.tests.factories import UserFactory


@pytest.fixture
def api() -> APIClient:
    client = APIClient()
    client.force_authenticate(UserFactory(role=User.Role.SALES))
    return client


def _ids_da_lista_ativa(api: APIClient) -> list[int]:
    listed = api.get(reverse("lead-list")).json()
    return [item["id"] for item in (listed if isinstance(listed, list) else listed["results"])]


@pytest.mark.django_db
def test_convert_archives_lead_and_creates_prospect_client(api: APIClient) -> None:
    lead = Lead.objects.create(name="Fulano", email="f@x.com", company="ACME")

    resp = api.post(reverse("lead-convert", args=[lead.pk]), format="json")
    assert resp.status_code == 201

    lead.refresh_from_db()
    assert lead.is_archived  # sai da lista ativa
    assert Account.objects.get(pk=lead.account_id).lifecycle_status == Account.LifecycleStatus.PROSPECT

    # a lista ativa de leads não traz mais o convertido
    assert lead.pk not in _ids_da_lista_ativa(api)


@pytest.mark.django_db
def test_convert_com_nurture_mantem_o_lead_na_lista_ativa(api: APIClient) -> None:
    lead = Lead.objects.create(name="Sicrano", email="s@x.com", company="Beta")

    resp = api.post(
        reverse("lead-convert", args=[lead.pk]),
        {"outcome": "nurture", "nurture_until": str(timezone.localdate())},
        format="json",
    )
    assert resp.status_code == 201

    lead.refresh_from_db()
    assert not lead.is_archived
    assert lead.status == Lead.Status.CONTACTED
    assert Account.objects.get(pk=lead.account_id).lifecycle_status == Account.LifecycleStatus.PROSPECT
    assert lead.pk in _ids_da_lista_ativa(api)
