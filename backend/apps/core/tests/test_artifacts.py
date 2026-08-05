import pytest
from django.test import override_settings
from rest_framework.test import APIClient

from apps.core import ai
from apps.core.models import Artifact

from .factories import (
    ArtifactFactory,
    MeetingFactory,
    OpportunityFactory,
    ProjectFactory,
    UserFactory,
)


def _mock_ai(monkeypatch, text="Rascunho gerado pela IA."):
    monkeypatch.setattr(ai, "complete", lambda s, u: (text, {"prompt_tokens": 4, "completion_tokens": 2}))


@pytest.mark.django_db
def test_sales_can_create_and_list_artifacts():
    opportunity = OpportunityFactory()
    client = APIClient()
    client.force_authenticate(UserFactory(role="sales"))

    created = client.post("/api/v1/artifacts/", {
        "kind": "proposal", "title": "Proposta — Acme", "content": "Escopo e investimento.",
        "opportunity": opportunity.pk,
    }, format="json")
    assert created.status_code == 201
    assert created.json()["status"] == "draft"
    assert created.json()["kind_display"] == "Proposta"

    listed = client.get(f"/api/v1/artifacts/?opportunity={opportunity.pk}")
    assert listed.status_code == 200
    assert [row["title"] for row in listed.json()] == ["Proposta — Acme"]


@pytest.mark.django_db
def test_created_by_comes_from_the_session_not_the_payload():
    opportunity = OpportunityFactory()
    author = UserFactory(role="sales")
    other = UserFactory(role="sales")
    client = APIClient()
    client.force_authenticate(author)

    created = client.post("/api/v1/artifacts/", {
        "kind": "proposal", "title": "Proposta", "opportunity": opportunity.pk,
        "created_by": other.pk,
    }, format="json")

    assert created.status_code == 201
    assert Artifact.objects.get(pk=created.json()["id"]).created_by_id == author.pk


@pytest.mark.django_db
def test_artifact_must_link_to_exactly_one_resource():
    client = APIClient()
    client.force_authenticate(UserFactory(role="sales"))

    loose = client.post("/api/v1/artifacts/", {"kind": "proposal", "title": "Solta"}, format="json")
    assert loose.status_code == 400

    both = client.post("/api/v1/artifacts/", {
        "kind": "proposal", "title": "Dupla",
        "opportunity": OpportunityFactory().pk, "project": ProjectFactory().pk,
    }, format="json")
    assert both.status_code == 400


@pytest.mark.django_db
def test_filters_by_kind_and_status():
    opportunity = OpportunityFactory()
    ArtifactFactory(opportunity=opportunity, kind=Artifact.Kind.PROPOSAL)
    ArtifactFactory(opportunity=opportunity, kind=Artifact.Kind.CONTRACT, status=Artifact.Status.SENT)
    client = APIClient()
    client.force_authenticate(UserFactory(role="sales"))

    by_kind = client.get(f"/api/v1/artifacts/?opportunity={opportunity.pk}&kind=contract")
    assert [row["kind"] for row in by_kind.json()] == ["contract"]

    by_status = client.get(f"/api/v1/artifacts/?opportunity={opportunity.pk}&status=draft")
    assert [row["kind"] for row in by_status.json()] == ["proposal"]


@pytest.mark.django_db
def test_status_walks_the_journey_and_stamps_the_dates():
    artifact = ArtifactFactory()
    client = APIClient()
    client.force_authenticate(UserFactory(role="sales"))
    url = f"/api/v1/artifacts/{artifact.pk}/"

    sent = client.patch(url, {"status": "sent"}, format="json")
    assert sent.status_code == 200
    assert sent.json()["sent_at"] is not None
    assert sent.json()["decided_at"] is None

    accepted = client.patch(url, {"status": "accepted"}, format="json")
    assert accepted.status_code == 200
    assert accepted.json()["decided_at"] is not None


@pytest.mark.django_db
def test_invalid_status_transition_is_rejected():
    artifact = ArtifactFactory()  # nasce em rascunho
    client = APIClient()
    client.force_authenticate(UserFactory(role="sales"))

    response = client.patch(f"/api/v1/artifacts/{artifact.pk}/", {"status": "accepted"}, format="json")

    assert response.status_code == 400
    artifact.refresh_from_db()
    assert artifact.status == Artifact.Status.DRAFT


@pytest.mark.django_db
def test_decided_artifact_is_terminal():
    artifact = ArtifactFactory(status=Artifact.Status.ACCEPTED)
    client = APIClient()
    client.force_authenticate(UserFactory(role="sales"))

    response = client.patch(f"/api/v1/artifacts/{artifact.pk}/", {"status": "draft"}, format="json")

    assert response.status_code == 400


@pytest.mark.django_db
def test_archived_artifact_is_hidden_from_list():
    opportunity = OpportunityFactory()
    ArtifactFactory(opportunity=opportunity).archive()
    client = APIClient()
    client.force_authenticate(UserFactory(role="sales"))

    assert client.get(f"/api/v1/artifacts/?opportunity={opportunity.pk}").json() == []


@pytest.mark.django_db
def test_delete_archives_instead_of_erasing():
    artifact = ArtifactFactory()
    client = APIClient()
    client.force_authenticate(UserFactory(role="sales"))

    assert client.delete(f"/api/v1/artifacts/{artifact.pk}/").status_code == 204
    artifact.refresh_from_db()
    assert artifact.is_archived


@pytest.mark.django_db
def test_delivery_sees_project_artifacts_but_not_commercial_ones():
    project = ProjectFactory()
    ArtifactFactory(opportunity=None, project=project, kind=Artifact.Kind.ASSESSMENT,
                    title="Assessment — Acme")
    ArtifactFactory(title="Proposta — Acme")  # ligada a oportunidade
    client = APIClient()
    client.force_authenticate(UserFactory(role="delivery"))

    titles = [row["title"] for row in client.get("/api/v1/artifacts/").json()]

    assert titles == ["Assessment — Acme"]


@pytest.mark.django_db
def test_anonymous_cannot_reach_artifacts():
    assert APIClient().get("/api/v1/artifacts/").status_code in {401, 403}


@pytest.mark.django_db
@override_settings(AI_ENABLED=True)
def test_generating_a_proposal_persists_a_draft_artifact(monkeypatch):
    _mock_ai(monkeypatch, "Proposta em três frentes.")
    opportunity = OpportunityFactory()
    user = UserFactory(role="sales")
    client = APIClient()
    client.force_authenticate(user)

    response = client.post(f"/api/v1/opportunities/{opportunity.pk}/proposal/", {}, format="json")

    assert response.status_code == 200
    body = response.json()
    assert body["text"] == "Proposta em três frentes."  # contrato antigo preservado
    assert body["interaction"] is not None

    artifact = Artifact.objects.get(pk=body["artifact"]["id"])
    assert artifact.kind == Artifact.Kind.PROPOSAL
    assert artifact.status == Artifact.Status.DRAFT
    assert artifact.content == "Proposta em três frentes."
    assert artifact.opportunity_id == opportunity.pk
    assert artifact.created_by_id == user.pk
    assert artifact.ai_interaction_id == body["interaction"]


@pytest.mark.django_db
@override_settings(AI_ENABLED=True)
def test_generating_a_contract_persists_a_draft_artifact(monkeypatch):
    _mock_ai(monkeypatch)
    opportunity = OpportunityFactory()
    client = APIClient()
    client.force_authenticate(UserFactory(role="sales"))

    response = client.post(f"/api/v1/opportunities/{opportunity.pk}/contract/", {}, format="json")

    assert response.json()["artifact"]["kind"] == "contract"
    assert Artifact.objects.filter(kind=Artifact.Kind.CONTRACT, opportunity=opportunity).exists()


@pytest.mark.django_db
@override_settings(AI_ENABLED=True)
@pytest.mark.parametrize(("action", "kind"), [("discovery", "discovery"), ("assessment", "assessment")])
def test_meeting_analysis_survives_the_page(monkeypatch, action, kind):
    _mock_ai(monkeypatch, "Diagnóstico da transcrição.")
    meeting = MeetingFactory()
    client = APIClient()
    client.force_authenticate(UserFactory(role="delivery"))

    response = client.post(f"/api/v1/meetings/{meeting.pk}/{action}/", {}, format="json")

    assert response.status_code == 200
    artifact = Artifact.objects.get(kind=kind)
    assert artifact.content == "Diagnóstico da transcrição."
    assert artifact.project_id == meeting.project_id
    assert artifact.opportunity_id is None
    assert artifact.source_meeting_id == meeting.pk


@pytest.mark.django_db
@override_settings(AI_ENABLED=False)
def test_disabled_ai_creates_no_artifact():
    opportunity = OpportunityFactory()
    client = APIClient()
    client.force_authenticate(UserFactory(role="sales"))

    response = client.post(f"/api/v1/opportunities/{opportunity.pk}/proposal/", {}, format="json")

    assert response.status_code == 503
    assert Artifact.objects.count() == 0
