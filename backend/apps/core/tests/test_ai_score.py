import pytest
from django.test import override_settings
from django.urls import reverse
from rest_framework.test import APIClient

from apps.core import ai, ai_score
from apps.core.models import AiInteraction

from .factories import MeetingFactory, UserFactory

_GOOD = (
    '{"maturity": 40, "opportunity": 85, '
    '"dimensions": [{"label": "Dados", "score": 30}, {"label": "Processos", "score": 55}], '
    '"summary": "Muito espaço para automação de faturamento."}'
)


@pytest.mark.django_db
def test_score_meeting_persists_on_project_and_audits(monkeypatch):
    monkeypatch.setattr(ai, "complete", lambda system, user, **_: (_GOOD, {"prompt_tokens": 5, "completion_tokens": 3}))
    meeting = MeetingFactory()
    user = UserFactory()

    result = ai_score.score_meeting(meeting, user=user)

    project = meeting.project
    project.refresh_from_db()
    assert project.ai_maturity == 40
    assert project.ai_opportunity == 85
    assert project.ai_dimensions == [
        {"label": "Dados", "score": 30},
        {"label": "Processos", "score": 55},
    ]
    assert project.ai_score_summary.startswith("Muito espaço")
    assert project.ai_scored_at is not None
    assert project.ai_score_reviewed is False  # rascunho até revisão humana
    assert project.ai_score_meeting_id == meeting.id
    assert result["maturity"] == 40 and result["reviewed"] is False

    interaction = AiInteraction.objects.get(feature="ai_score")
    assert interaction.user_id == user.id and interaction.project_id == project.id


@pytest.mark.django_db
def test_score_meeting_clamps_and_drops_invalid_dimensions(monkeypatch):
    payload = (
        '{"maturity": 150, "opportunity": -10, '
        '"dimensions": [{"label": "Dados", "score": 200}, {"label": "", "score": 40}, '
        '{"score": 10}, "lixo"], "summary": "x"}'
    )
    monkeypatch.setattr(ai, "complete", lambda s, u, **_: (payload, {"prompt_tokens": 1, "completion_tokens": 1}))
    meeting = MeetingFactory()

    ai_score.score_meeting(meeting)

    project = meeting.project
    project.refresh_from_db()
    assert project.ai_maturity == 100 and project.ai_opportunity == 0
    assert project.ai_dimensions == [{"label": "Dados", "score": 100}]  # só a entrada válida


@pytest.mark.django_db
def test_score_meeting_tolerates_garbage_output(monkeypatch):
    monkeypatch.setattr(ai, "complete", lambda s, u, **_: ("desculpe, não sei", {"prompt_tokens": 0, "completion_tokens": 0}))
    meeting = MeetingFactory()

    ai_score.score_meeting(meeting)

    project = meeting.project
    project.refresh_from_db()
    assert project.ai_maturity is None and project.ai_opportunity is None
    assert project.ai_dimensions == []
    assert project.ai_scored_at is not None  # registrou a tentativa mesmo sem dados


@pytest.mark.django_db
def test_parses_json_inside_code_fence(monkeypatch):
    monkeypatch.setattr(ai, "complete", lambda s, u, **_: (
        'Claro!\n```json\n{"maturity": 20, "opportunity": 60, "dimensions": [], "summary": "ok"}\n```',
        {"prompt_tokens": 1, "completion_tokens": 1},
    ))
    meeting = MeetingFactory()

    result = ai_score.score_meeting(meeting)
    assert result["maturity"] == 20 and result["opportunity"] == 60


@pytest.fixture
def api_client() -> APIClient:
    return APIClient()


@pytest.mark.django_db
@override_settings(AI_ENABLED=True, OPENAI_API_KEY="sk-x")
def test_ai_score_action_returns_payload(api_client, monkeypatch):
    monkeypatch.setattr(ai, "complete", lambda s, u, **_: (_GOOD, {"prompt_tokens": 1, "completion_tokens": 1}))
    meeting = MeetingFactory()
    api_client.force_authenticate(UserFactory())

    response = api_client.post(reverse("meeting-ai-score", args=[meeting.id]), {}, format="json")

    assert response.status_code == 200
    assert response.data["maturity"] == 40 and response.data["opportunity"] == 85


@pytest.mark.django_db
def test_ai_score_requires_transcript(api_client):
    meeting = MeetingFactory(transcript="")
    api_client.force_authenticate(UserFactory())

    response = api_client.post(reverse("meeting-ai-score", args=[meeting.id]), {}, format="json")
    assert response.status_code == 400


@pytest.mark.django_db
@override_settings(AI_ENABLED=False)
def test_ai_score_disabled_returns_503(api_client):
    meeting = MeetingFactory()
    api_client.force_authenticate(UserFactory())

    response = api_client.post(reverse("meeting-ai-score", args=[meeting.id]), {}, format="json")
    assert response.status_code == 503


@pytest.mark.django_db
@override_settings(AI_ENABLED=True, OPENAI_API_KEY="sk-x", AI_DAILY_LIMIT=1)
def test_ai_score_respects_daily_limit(api_client):
    user = UserFactory()
    AiInteraction.objects.create(user=user, feature="ai_score")  # já bateu o limite do dia
    meeting = MeetingFactory()
    api_client.force_authenticate(user)

    response = api_client.post(reverse("meeting-ai-score", args=[meeting.id]), {}, format="json")
    assert response.status_code == 429
