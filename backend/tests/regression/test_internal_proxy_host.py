import pytest
from django.urls import reverse
from rest_framework.test import APIClient


@pytest.mark.django_db
def test_internal_api_host_can_fetch_csrf_token() -> None:
    """O proxy Vite usa o nome do serviço Docker `api` como Host."""
    response = APIClient().get(reverse("csrf"), HTTP_HOST="api:8000")

    assert response.status_code == 200
    assert response.data["csrfToken"]
