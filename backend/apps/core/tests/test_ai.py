import pytest
from django.test import override_settings

from apps.core import ai
from apps.core.models import AiInteraction

from .factories import MeetingFactory, OpportunityFactory, ProjectFactory, UserFactory


@pytest.mark.django_db
def test_build_project_context_has_name_and_status():
    project = ProjectFactory()
    context = ai.build_project_context(project)
    assert project.name in context
    assert project.status in context


@pytest.mark.django_db
def test_build_meeting_context_has_title_and_transcript():
    meeting = MeetingFactory(title="Discovery Acme", transcript="Processo manual de faturamento.")
    context = ai.build_meeting_context(meeting)
    assert "Discovery Acme" in context
    assert "Processo manual de faturamento." in context
    assert meeting.project.name in context


@pytest.mark.django_db
def test_build_opportunity_context_has_client_and_value():
    opportunity = OpportunityFactory()
    context = ai.build_opportunity_context(opportunity)
    assert opportunity.client.name in context
    assert opportunity.title in context


@pytest.mark.django_db
@override_settings(AI_DAILY_LIMIT=1)
def test_within_daily_limit_counts_interactions():
    user = UserFactory()
    assert ai.within_daily_limit(user) is True
    AiInteraction.objects.create(user=user, feature="project_chat")
    assert ai.within_daily_limit(user) is False


@pytest.mark.django_db
@override_settings(AI_ENABLED=True)
def test_is_enabled_reflects_setting():
    assert ai.is_enabled() is True
