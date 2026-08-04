from datetime import timedelta

import pytest
from django.core.management import call_command
from django.test import override_settings
from django.utils import timezone

from apps.core import digest, notifications
from apps.core.models import AiInteraction, Milestone, Notification, Task

from .factories import ProjectFactory, UserFactory


@pytest.mark.django_db
def test_build_user_digest_context_lists_overdue_and_upcoming():
    owner = UserFactory()
    project = ProjectFactory(owner=owner)
    Milestone.objects.create(project=project, title="Marco atrasado", owner=owner,
                             due_date=timezone.localdate() - timedelta(days=2))
    Task.objects.create(project=project, title="Tarefa a vencer", owner=owner,
                        due_date=timezone.localdate() + timedelta(days=3))

    context = digest.build_user_digest_context(owner)

    assert "Marco atrasado" in context
    assert "Tarefa a vencer" in context


@pytest.mark.django_db
def test_build_user_digest_context_empty_without_items():
    assert digest.build_user_digest_context(UserFactory()) == ""


@pytest.mark.django_db
@override_settings(EMAIL_NOTIFICATIONS_ENABLED=True, AI_ENABLED=True)
def test_send_daily_digest_uses_ai_emails_and_audits(mailoutbox, monkeypatch):
    from apps.core import ai

    monkeypatch.setattr(ai, "complete", lambda system, user: ("Resumo do dia", {"prompt_tokens": 2, "completion_tokens": 1}))
    owner = UserFactory(email="dono@x.test")
    project = ProjectFactory(owner=owner)
    Milestone.objects.create(project=project, title="Atrasado", owner=owner,
                             due_date=timezone.localdate() - timedelta(days=1))

    sent = digest.send_daily_digest()

    assert sent == 1
    assert any("resumo diário" in mail.subject.lower() for mail in mailoutbox)
    assert AiInteraction.objects.filter(user=owner, feature="daily_digest").count() == 1


@pytest.mark.django_db
@override_settings(EMAIL_NOTIFICATIONS_ENABLED=False)
def test_send_daily_digest_noop_when_email_flag_off():
    owner = UserFactory(email="a@x.test")
    project = ProjectFactory(owner=owner)
    Task.objects.create(project=project, title="Pendente", owner=owner,
                        due_date=timezone.localdate() - timedelta(days=1))
    assert digest.send_daily_digest() == 0


@pytest.mark.django_db
@override_settings(EMAIL_NOTIFICATIONS_ENABLED=True, AI_ENABLED=False)
def test_send_daily_digest_command_runs_without_ai(mailoutbox):
    owner = UserFactory(email="dono@x.test")
    project = ProjectFactory(owner=owner)
    Task.objects.create(project=project, title="Pendente", owner=owner,
                        due_date=timezone.localdate() - timedelta(days=1))

    call_command("send_daily_digest")

    assert any("resumo diário" in mail.subject.lower() for mail in mailoutbox)


@pytest.mark.django_db
@override_settings(EMAIL_NOTIFICATIONS_ENABLED=True)
def test_notify_mirrors_to_email_when_flag_on(mailoutbox):
    user = UserFactory(email="u@x.test")
    notifications.notify([user], "test", "Olá")
    assert Notification.objects.filter(user=user, kind="test").count() == 1
    assert any(mail.to == ["u@x.test"] for mail in mailoutbox)


@pytest.mark.django_db
@override_settings(EMAIL_NOTIFICATIONS_ENABLED=False)
def test_notify_skips_email_when_flag_off(mailoutbox):
    notifications.notify([UserFactory(email="u@x.test")], "test", "Olá")
    assert mailoutbox == []
