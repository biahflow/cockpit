"""Regressão FDD 040: o mesmo Pulse-Handoff-ID não cria segunda GitHub Issue."""

from __future__ import annotations

import pytest
from django.test import override_settings
from django.urls import reverse
from rest_framework.test import APIClient

from apps.core.github_issues import IssueDraft, IssueRef
from apps.core.models import EngineeringHandoff, User
from apps.core.tests.factories import ProjectFactory, UserFactory


class FakeClient:
    def __init__(self) -> None:
        self.create_calls = 0

    def find_by_handoff_id(
        self, repository: str, pulse_work_item_id: str
    ) -> IssueRef | None:
        return None

    def create_issue(self, draft: IssueDraft) -> IssueRef:
        self.create_calls += 1
        return IssueRef(
            number=4,
            url="https://github.com/acme/repo/issues/4",
            node_id="I_4",
            repository="acme/repo",
        )


@pytest.mark.django_db
@override_settings(
    GITHUB_PROVISIONING_ENABLED=True,
    GITHUB_TOKEN="ghp_test",
    GITHUB_REPO="acme/repo",
)
def test_reprocessar_o_mesmo_pulse_id_nao_cria_segunda_issue(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fake = FakeClient()
    monkeypatch.setattr(
        "apps.core.engineering_provisioning.GithubIssuesApi", lambda: fake
    )
    admin = UserFactory(role=User.Role.ADMIN)
    project = ProjectFactory()
    client = APIClient()
    client.force_authenticate(admin)
    payload = {
        "project": project.id,
        "pulse_work_item_id": "pulse-reg-1",
        "title": "Idempotent provisioning",
        "objective": "Do not duplicate GitHub Issues.",
        "acceptance_criteria": "A second POST with the same Pulse id returns the same issue.",
    }

    first = client.post(reverse("engineeringhandoff-list"), payload, format="json")
    second = client.post(reverse("engineeringhandoff-list"), payload, format="json")

    assert first.status_code == 201
    assert second.status_code == 200
    assert first.data["github_issue_number"] == 4
    assert second.data["github_issue_number"] == 4
    assert fake.create_calls == 1
    assert EngineeringHandoff.objects.filter(pulse_work_item_id="pulse-reg-1").count() == 1
