"""Regressão: uma oportunidade não pode criar dois projetos."""

from datetime import timedelta

import pytest
from django.urls import reverse
from django.utils import timezone
from rest_framework.test import APIClient

from apps.core.models import PipelineStage, Project, User
from apps.core.tests.factories import OpportunityFactory, UserFactory


@pytest.mark.django_db
def test_second_conversion_returns_conflict_without_new_project():
    sales = UserFactory(role=User.Role.SALES)
    opportunity = OpportunityFactory(stage=PipelineStage.objects.get(kind="won"), owner=sales)
    client = APIClient()
    client.force_authenticate(sales)
    body = {
        "client": opportunity.client_id, "name": "Projeto", "owner": sales.id,
        "start_date": str(timezone.localdate()), "due_date": str(timezone.localdate() + timedelta(days=10)),
        "status": "planning",
    }
    endpoint = reverse("opportunity-convert-to-project", args=[opportunity.id])
    assert client.post(endpoint, body, format="json").status_code == 201
    assert client.post(endpoint, body, format="json").status_code == 409
    assert Project.objects.count() == 1

