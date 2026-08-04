import pytest
from django.test import override_settings

from apps.core import ai, qualification
from apps.core.models import AiInteraction, Lead


def _lead():
    return Lead.objects.create(name="Fulano", email="f@x.com", company="ACME", message="Quero IA")


@pytest.mark.django_db
@override_settings(AI_ENABLED=True, OPENAI_API_KEY="sk-x", BOOKING_MIN_FIT="medium")
def test_qualify_persists_and_audits(monkeypatch):
    monkeypatch.setattr(ai, "complete", lambda system, user: (
        '{"fit": "high", "score": 88, "summary": "Bom fit", "recommended_action": "Agendar"}',
        {"prompt_tokens": 3, "completion_tokens": 2},
    ))
    lead = _lead()

    qualified = qualification.qualify_lead(lead, {"Orçamento": "R$ 50k"})

    lead.refresh_from_db()
    assert qualified is True
    assert lead.ai_fit == "high"
    assert lead.ai_score == 88
    assert lead.ai_summary == "Bom fit"
    assert lead.status == Lead.Status.QUALIFIED
    assert lead.qualified_at is not None
    interaction = AiInteraction.objects.get(feature="lead_qualification")
    assert interaction.user is None and interaction.lead_id == lead.id


@pytest.mark.django_db
@override_settings(AI_ENABLED=True, OPENAI_API_KEY="sk-x", BOOKING_MIN_FIT="medium")
def test_low_fit_does_not_qualify_for_booking(monkeypatch):
    monkeypatch.setattr(ai, "complete", lambda s, u: (
        '{"fit": "low", "score": 10, "summary": "Fora do perfil", "recommended_action": "Descartar"}',
        {"prompt_tokens": 1, "completion_tokens": 1},
    ))
    lead = _lead()

    assert qualification.qualify_lead(lead) is False
    lead.refresh_from_db()
    assert lead.ai_fit == "low"
    assert lead.status == Lead.Status.CONTACTED


@pytest.mark.django_db
@override_settings(AI_ENABLED=True, OPENAI_API_KEY="sk-x")
def test_qualify_parses_json_inside_code_fence(monkeypatch):
    monkeypatch.setattr(ai, "complete", lambda s, u: (
        'Claro!\n```json\n{"fit": "medium", "score": 55}\n```',
        {"prompt_tokens": 1, "completion_tokens": 1},
    ))
    lead = _lead()

    assert qualification.qualify_lead(lead) is True
    lead.refresh_from_db()
    assert lead.ai_fit == "medium" and lead.ai_score == 55


@pytest.mark.django_db
@override_settings(AI_ENABLED=True, OPENAI_API_KEY="sk-x")
def test_qualify_tolerates_garbage_output(monkeypatch):
    monkeypatch.setattr(ai, "complete", lambda s, u: ("desculpe, não sei", {"prompt_tokens": 0, "completion_tokens": 0}))
    lead = _lead()

    assert qualification.qualify_lead(lead) is False
    lead.refresh_from_db()
    assert lead.ai_fit == "" and lead.ai_score is None


@pytest.mark.django_db
@override_settings(AI_ENABLED=False)
def test_qualify_noop_when_ai_disabled():
    lead = _lead()
    assert qualification.qualify_lead(lead) is False
    lead.refresh_from_db()
    assert lead.qualified_at is None
    assert not AiInteraction.objects.exists()
