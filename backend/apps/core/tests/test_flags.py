import pytest
from django.test import override_settings
from django.urls import reverse
from rest_framework.test import APIClient

from apps.core import flags
from apps.core.models import AppSetting, User

from .factories import UserFactory


@pytest.mark.django_db
@override_settings(AI_ENABLED=False, OPENAI_API_KEY="sk-x")
def test_db_override_beats_env_default() -> None:
    assert flags.is_enabled("ai") is False
    AppSetting.objects.create(key="ai", enabled=True)
    assert flags.is_enabled("ai") is True


@override_settings(OPENAI_API_KEY="sk-x")
def test_configured_true_when_keys_present() -> None:
    assert flags.configured("ai") is True


@override_settings(OPENAI_API_KEY="")
def test_configured_false_when_keys_missing() -> None:
    assert flags.configured("ai") is False


def test_portal_flag_is_not_toggleable() -> None:
    assert flags.FLAGS["portal"].toggleable is False


@pytest.mark.django_db
@override_settings(TASKSYNC_ENABLED=False, TASKSYNC_TOKEN="t")
def test_patch_config_admin_toggles_flag() -> None:
    admin = UserFactory(role=User.Role.ADMIN)
    client = APIClient()
    client.force_authenticate(admin)
    resp = client.patch(reverse("config"), {"key": "tasksync", "enabled": True}, format="json")
    assert resp.status_code == 200
    assert resp.json()["enabled"] is True
    assert flags.is_enabled("tasksync") is True


@pytest.mark.django_db
def test_patch_config_forbidden_for_non_admin() -> None:
    delivery = UserFactory(role=User.Role.DELIVERY)
    client = APIClient()
    client.force_authenticate(delivery)
    resp = client.patch(reverse("config"), {"key": "ai", "enabled": True}, format="json")
    assert resp.status_code == 403


@pytest.mark.django_db
@override_settings(OPENAI_API_KEY="")
def test_patch_config_blocks_enable_without_credentials() -> None:
    admin = UserFactory(role=User.Role.ADMIN)
    client = APIClient()
    client.force_authenticate(admin)
    resp = client.patch(reverse("config"), {"key": "ai", "enabled": True}, format="json")
    assert resp.status_code == 400


@pytest.mark.django_db
def test_config_get_lists_integrations() -> None:
    admin = UserFactory(role=User.Role.ADMIN)
    client = APIClient()
    client.force_authenticate(admin)
    data = client.get(reverse("config")).json()
    keys = {item["key"] for item in data["integrations"]}
    assert {"ai", "drive", "calendar", "esign", "tasksync", "portal"} <= keys
