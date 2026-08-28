"""Degraus da escada FDE sobre o catálogo de `Service` (FDD 015)."""

import pytest
from rest_framework.test import APIClient

from apps.core.models import Service

from .factories import ServiceFactory, UserFactory


@pytest.mark.django_db
def test_migration_seeds_every_step_of_the_ladder():
    tiers = set(Service.objects.exclude(tier="").values_list("tier", flat=True))
    assert tiers == {t for t, _ in Service.Tier.choices}
    porta = Service.objects.get(tier=Service.Tier.QUALIFICATION_CALL)
    assert porta.is_free
    assert porta.summary


@pytest.mark.django_db
def test_admin_updates_tier_price_and_summary():
    client = APIClient()
    client.force_authenticate(UserFactory(role="admin"))
    service = Service.objects.get(tier=Service.Tier.DISCOVERY_ASSESSMENT)

    response = client.patch(f"/api/v1/services/{service.pk}/", {
        "list_price": "18000.00", "summary": "Discovery aprofundado e assessment.",
    }, format="json")

    assert response.status_code == 200
    assert response.json()["list_price"] == "18000.00"
    assert response.json()["tier_display"] == "Discovery Express + Assessment"
    service.refresh_from_db()
    assert service.summary == "Discovery aprofundado e assessment."


@pytest.mark.django_db
def test_second_active_service_in_the_same_tier_is_rejected():
    client = APIClient()
    client.force_authenticate(UserFactory(role="admin"))

    response = client.post("/api/v1/services/", {
        "name": "Outro Discovery", "tier": Service.Tier.DISCOVERY_SPRINT,
    }, format="json")

    assert response.status_code == 400
    assert "tier" in response.json()


@pytest.mark.django_db
def test_archiving_a_service_frees_its_tier():
    client = APIClient()
    client.force_authenticate(UserFactory(role="admin"))
    seeded = Service.objects.get(tier=Service.Tier.PROVE)

    assert client.delete(f"/api/v1/services/{seeded.pk}/").status_code == 204
    seeded.refresh_from_db()
    assert seeded.is_archived

    response = client.post("/api/v1/services/", {
        "name": "PROVE 2026", "tier": Service.Tier.PROVE, "list_price": "90000.00",
    }, format="json")
    assert response.status_code == 201


@pytest.mark.django_db
def test_moving_a_service_into_a_taken_tier_is_rejected():
    client = APIClient()
    client.force_authenticate(UserFactory(role="admin"))
    loose = ServiceFactory(name="Consultoria avulsa")

    response = client.patch(f"/api/v1/services/{loose.pk}/", {
        "tier": Service.Tier.PROVE,
    }, format="json")

    assert response.status_code == 400
    assert "tier" in response.json()


@pytest.mark.django_db
def test_renaming_a_tier_service_keeps_its_own_tier():
    client = APIClient()
    client.force_authenticate(UserFactory(role="admin"))
    sprint = Service.objects.get(tier=Service.Tier.DISCOVERY_SPRINT)

    response = client.patch(f"/api/v1/services/{sprint.pk}/", {
        "name": "Diagnóstico Sprint", "tier": Service.Tier.DISCOVERY_SPRINT,
    }, format="json")

    assert response.status_code == 200
    assert response.json()["name"] == "Diagnóstico Sprint"


@pytest.mark.django_db
def test_services_without_tier_can_coexist():
    client = APIClient()
    client.force_authenticate(UserFactory(role="admin"))

    assert client.post("/api/v1/services/", {"name": "Avulso A"}, format="json").status_code == 201
    assert client.post("/api/v1/services/", {"name": "Avulso B"}, format="json").status_code == 201
    assert Service.objects.filter(tier="", archived_at__isnull=True).count() == 2


@pytest.mark.django_db
def test_non_admin_reads_but_does_not_write_services():
    client = APIClient()
    client.force_authenticate(UserFactory(role="sales"))

    assert client.get("/api/v1/services/").status_code == 200
    assert client.post("/api/v1/services/", {"name": "Novo"}, format="json").status_code == 403
