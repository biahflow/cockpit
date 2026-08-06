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


@pytest.mark.django_db
@override_settings(PORTAL_WEBHOOK_URL="http://portal/hook", PORTAL_WEBHOOK_SECRET="s")
def test_portal_flag_is_toggleable() -> None:
    """O portal deixou de ser só-ambiente (ADR 0018): dá para desligar sem mexer no deploy."""
    assert flags.is_enabled("portal") is True
    AppSetting.objects.create(key="portal", enabled=False)
    assert flags.is_enabled("portal") is False


@pytest.mark.django_db
@override_settings(ESIGN_ENABLED=True, ESIGN_PROVIDER="autentique", ESIGN_API_TOKEN="",
                   ESIGN_WEBHOOK_SECRET="s")
def test_sem_credencial_nao_existe_ligada() -> None:
    """O default do ambiente não basta: faltando credencial a flag resolve para desligada.

    Antes da ADR 0018 este caso passava — o guard de 503 liberava a ação e a falha só aparecia
    dentro do adaptador, como se fosse erro do fornecedor.
    """
    assert flags.desired("esign") is True
    assert flags.is_enabled("esign") is False

    # Nem o override do admin liga o que não está configurado.
    AppSetting.objects.create(key="esign", enabled=True)
    assert flags.is_enabled("esign") is False


@pytest.mark.django_db
@override_settings(EMAIL_NOTIFICATIONS_ENABLED=True)
def test_email_liga_sem_credencial_alguma() -> None:
    """`email` é a única flag sem `requires` — o SMTP tem default, então não há o que cobrar."""
    assert flags.missing("email") == []
    assert flags.is_enabled("email") is True


@override_settings(OPENAI_API_KEY="")
def test_status_nomeia_o_que_falta() -> None:
    assert flags.status("ai")["missing"] == ["OPENAI_API_KEY"]


@pytest.mark.django_db
# `LINEAR_API_KEY` entrou no override porque o `requires` passou a cobrar credencial de fornecedor:
# antes dava para ligar a sincronia só com o segredo de entrada, e a saída ficava muda (FDD 024).
@override_settings(TASKSYNC_ENABLED=False, TASKSYNC_TOKEN="t", LINEAR_API_KEY="k")
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
