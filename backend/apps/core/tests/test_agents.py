import pytest
from django.test import override_settings
from django.urls import reverse
from django.utils import timezone
from rest_framework.test import APIClient

from apps.core import ai
from apps.core.models import AiInteraction, User

from .factories import ProjectFactory, ProjectMemberFactory, UserFactory


@pytest.fixture
def fake_ai(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        ai, "complete",
        lambda system, user: ("Resposta do agente", {"prompt_tokens": 3, "completion_tokens": 5}),
    )


def _post_agent(client: APIClient, key: str) -> object:
    return client.post(reverse("agent", args=[key]), {"question": "Como estamos?"}, format="json")


@pytest.mark.django_db
@override_settings(AI_ENABLED=True, OPENAI_API_KEY="sk-x")
def test_delivery_uses_entrega_agent_and_audits(fake_ai: None) -> None:
    delivery = UserFactory(role=User.Role.DELIVERY)
    ProjectFactory()
    client = APIClient()
    client.force_authenticate(delivery)
    resp = _post_agent(client, "entrega")
    assert resp.status_code == 200
    body = resp.json()
    assert body["text"] == "Resposta do agente" and "interaction" in body
    assert AiInteraction.objects.get(pk=body["interaction"]).feature == "agent_entrega"


@pytest.mark.django_db
def test_o_contexto_de_entrega_leva_as_duas_fontes_de_satisfacao() -> None:
    """O bloco de satisfação (FDD 037) é o único dos quatro que fala do cliente, e é o único que
    lê **as duas fontes**.

    Health Score e régua de cobrança leem só a `declarada`, porque as duas produzem número e
    comportamento (ADR 0032). Aqui nada vira número: é texto para uma pessoa ler, e a leitura de
    quem entrega é justamente o que existe antes de alguém ter perguntado ao cliente. Escondê-la
    aqui apagaria o único uso legítimo dela.
    """
    from apps.core import agents
    from apps.core.models import Satisfacao

    delivery = UserFactory(role=User.Role.DELIVERY)
    um, outro = ProjectFactory(), ProjectFactory()
    for projeto in (um, outro):
        ProjectMemberFactory(project=projeto, user=delivery)
    hoje = timezone.localdate()
    Satisfacao.objects.create(
        account=um.engagement.account, nivel=Satisfacao.Nivel.INSATISFEITO, fonte=Satisfacao.Fonte.DECLARADA,
        happened_on=hoje, note="Disse que o marco 2 atrasou duas vezes.",
    )
    Satisfacao.objects.create(
        account=outro.engagement.account, nivel=Satisfacao.Nivel.NEUTRO, fonte=Satisfacao.Fonte.PERCEBIDA,
        happened_on=hoje,
    )

    context = agents.build_delivery_context(delivery)

    assert "Satisfação registrada" in context
    assert "insatisfeito (declarada pelo cliente" in context
    assert "neutro (percebida por quem entrega" in context
    assert "Disse que o marco 2 atrasou duas vezes." in context
    assert "sem nota" in context  # o registro sem nota aparece dizendo que não tem


@pytest.mark.django_db
@override_settings(AI_ENABLED=True, OPENAI_API_KEY="sk-x")
def test_rbac_per_agent(fake_ai: None) -> None:
    sales = UserFactory(role=User.Role.SALES)
    client = APIClient()
    client.force_authenticate(sales)
    assert _post_agent(client, "comercial").status_code == 200  # vendas usa comercial
    assert _post_agent(client, "entrega").status_code == 403  # mas não entrega
    assert _post_agent(client, "financeiro").status_code == 403  # nem financeiro

    admin = UserFactory(role=User.Role.ADMIN)
    client.force_authenticate(admin)
    assert _post_agent(client, "financeiro").status_code == 200  # admin usa financeiro


@pytest.mark.django_db
@override_settings(AI_ENABLED=False)
def test_agent_503_when_ai_disabled() -> None:
    admin = UserFactory(role=User.Role.ADMIN)
    client = APIClient()
    client.force_authenticate(admin)
    assert _post_agent(client, "comercial").status_code == 503


@pytest.mark.django_db
@override_settings(AI_ENABLED=True, OPENAI_API_KEY="sk-x")
def test_agent_invalid_key_404(fake_ai: None) -> None:
    admin = UserFactory(role=User.Role.ADMIN)
    client = APIClient()
    client.force_authenticate(admin)
    assert _post_agent(client, "inexistente").status_code == 404


@pytest.mark.django_db
@override_settings(AI_ENABLED=True, OPENAI_API_KEY="sk-x")
def test_feedback_sets_rating_and_metrics(fake_ai: None) -> None:
    admin = UserFactory(role=User.Role.ADMIN)
    client = APIClient()
    client.force_authenticate(admin)
    body = _post_agent(client, "comercial").json()

    fb = client.post(reverse("ai-feedback"), {"interaction": body["interaction"], "rating": 1}, format="json")
    assert fb.status_code == 200
    assert AiInteraction.objects.get(pk=body["interaction"]).rating == 1

    metrics = client.get(reverse("ai-metrics")).json()
    assert metrics["total"] >= 1 and metrics["positive_rate"] == 1.0


@pytest.mark.django_db
@override_settings(AI_ENABLED=True, OPENAI_API_KEY="sk-x")
def test_feedback_only_by_owner(fake_ai: None) -> None:
    owner = UserFactory(role=User.Role.ADMIN)
    intruder = UserFactory(role=User.Role.ADMIN)
    owner_client = APIClient()
    owner_client.force_authenticate(owner)
    body = _post_agent(owner_client, "comercial").json()

    intruder_client = APIClient()
    intruder_client.force_authenticate(intruder)
    resp = intruder_client.post(
        reverse("ai-feedback"), {"interaction": body["interaction"], "rating": 1}, format="json"
    )
    assert resp.status_code == 404  # não é dono → nem enxerga a interação


@pytest.mark.django_db
def test_metrics_forbidden_for_non_admin() -> None:
    sales = UserFactory(role=User.Role.SALES)
    client = APIClient()
    client.force_authenticate(sales)
    assert client.get(reverse("ai-metrics")).status_code == 403
