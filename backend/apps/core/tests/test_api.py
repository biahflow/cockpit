import io
from datetime import timedelta

import pytest
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import override_settings
from django.urls import reverse
from django.utils import timezone
from rest_framework.test import APIClient

from apps.core.models import (
    Artifact,
    Contact,
    Document,
    Milestone,
    PipelineStage,
    Project,
    Service,
    Task,
    User,
)

from .factories import (
    AccountFactory,
    ArtifactFactory,
    CommercialOpportunityFactory,
    MeetingFactory,
    ProjectFactory,
    UserFactory,
)


@pytest.fixture
def api_client() -> APIClient:
    return APIClient()


@pytest.fixture
def admin_user() -> User:
    return UserFactory(role=User.Role.ADMIN)


@pytest.mark.django_db
def test_sales_can_convert_won_opportunity_once(api_client: APIClient):
    sales = UserFactory(role=User.Role.SALES)
    won = PipelineStage.objects.get(kind=PipelineStage.Kind.WON)
    opportunity = CommercialOpportunityFactory(stage=won, owner=sales)
    api_client.force_authenticate(sales)
    payload = {
        "client": opportunity.account_id,
        "name": "Projeto gerado",
        "description": "",
        "owner": sales.id,
        "start_date": str(timezone.localdate()),
        "due_date": str(timezone.localdate() + timedelta(days=30)),
        "status": "planning",
    }
    url = reverse("opportunity-convert-to-project", args=[opportunity.id])

    created = api_client.post(url, payload, format="json")
    duplicate = api_client.post(url, payload, format="json")

    assert created.status_code == 201
    assert Project.objects.get().originating_commercial_opportunity_id == opportunity.id
    assert duplicate.status_code == 409


@pytest.mark.django_db
def test_cannot_convert_opportunity_that_is_not_won(api_client: APIClient):
    sales = UserFactory(role=User.Role.SALES)
    opportunity = CommercialOpportunityFactory(owner=sales)
    api_client.force_authenticate(sales)
    response = api_client.post(
        reverse("opportunity-convert-to-project", args=[opportunity.id]), {}, format="json"
    )
    assert response.status_code == 400


@pytest.mark.django_db
def test_conversion_seeds_kickoff_schedule_and_emails_owner(api_client: APIClient, mailoutbox):
    from apps.core import kickoff
    from apps.core.models import Milestone, Notification, Task

    sales = UserFactory(role=User.Role.SALES, email="vendas@example.test")
    won = PipelineStage.objects.get(kind=PipelineStage.Kind.WON)
    opportunity = CommercialOpportunityFactory(stage=won, owner=sales)
    api_client.force_authenticate(sales)
    payload = {
        "client": opportunity.account_id, "name": "Projeto gerado",
        "start_date": str(timezone.localdate()),
        "due_date": str(timezone.localdate() + timedelta(days=90)),
    }

    response = api_client.post(reverse("opportunity-convert-to-project", args=[opportunity.id]), payload, format="json")

    assert response.status_code == 201
    project_id = response.data["id"]
    assert Milestone.objects.filter(project_id=project_id).count() == len(kickoff.KICKOFF_TEMPLATE)
    assert Task.objects.filter(project_id=project_id).exists()
    assert any("Kickoff" in mail.subject for mail in mailoutbox)
    assert Notification.objects.filter(user=sales, kind="kickoff").count() == 1


@pytest.mark.django_db
def test_delivery_cannot_edit_opportunities(api_client: APIClient):
    delivery = UserFactory(role=User.Role.DELIVERY)
    opportunity = CommercialOpportunityFactory()
    api_client.force_authenticate(delivery)
    response = api_client.patch(
        reverse("opportunity-detail", args=[opportunity.id]), {"title": "Alterado"}, format="json"
    )
    assert response.status_code == 403


@pytest.mark.django_db
@override_settings(MEDIA_ROOT="/tmp/biahflow-test-media")
def test_document_requires_exactly_one_link_and_keeps_private_access(api_client: APIClient, admin_user: User):
    account = AccountFactory(owner=admin_user)
    api_client.force_authenticate(admin_user)
    file = SimpleUploadedFile("proposta.pdf", b"conteudo", content_type="application/pdf")
    response = api_client.post(reverse("document-list"), {"account": account.id, "file": file})
    assert response.status_code == 201
    document = Document.objects.get()
    assert document.original_name == "proposta.pdf"

    api_client.force_authenticate(user=None)
    unauthorized = api_client.get(reverse("document-download", args=[document.id]))
    assert unauthorized.status_code == 403

    no_link_file = SimpleUploadedFile("sem-vinculo.pdf", b"conteudo", content_type="application/pdf")
    api_client.force_authenticate(admin_user)
    invalid = api_client.post(reverse("document-list"), {"file": no_link_file})
    assert invalid.status_code == 400


@pytest.mark.django_db
@override_settings(MEDIA_ROOT="/tmp/biahflow-test-media", GOOGLE_DRIVE_ENABLED=True,
                   GOOGLE_DRIVE_ROOT_FOLDER_ID="pasta-raiz")
def test_document_upload_goes_to_drive_when_enabled(api_client: APIClient, admin_user: User, monkeypatch):
    from apps.core import drive

    monkeypatch.setattr(drive, "upload_document", lambda document, uploaded: ("fileid-123", "https://drive.example/view"))
    account = AccountFactory(owner=admin_user)
    api_client.force_authenticate(admin_user)
    file = SimpleUploadedFile("proposta.pdf", b"conteudo", content_type="application/pdf")

    response = api_client.post(reverse("document-list"), {"account": account.id, "file": file})

    assert response.status_code == 201
    assert response.data["drive_link"] == "https://drive.example/view"
    document = Document.objects.get()
    assert document.drive_file_id == "fileid-123"
    assert not document.file  # não guardou cópia local

    monkeypatch.setattr(drive, "download_document", lambda document: io.BytesIO(b"conteudo-drive"))
    downloaded = api_client.get(reverse("document-download", args=[document.id]))
    assert downloaded.status_code == 200
    assert b"".join(downloaded.streaming_content) == b"conteudo-drive"


@pytest.mark.django_db
def test_admin_lists_invitations_and_users_others_blocked(api_client: APIClient, admin_user: User):
    from apps.core.models import Invitation

    Invitation.objects.create(
        email="x@y.z", role="delivery", invited_by=admin_user,
        expires_at=timezone.now() + timedelta(days=7),
    )
    sales = UserFactory(role=User.Role.SALES)

    api_client.force_authenticate(admin_user)
    invitations = api_client.get(reverse("invitation"))
    assert invitations.status_code == 200
    assert len(invitations.data) == 1
    assert api_client.get(reverse("user-list")).status_code == 200

    api_client.force_authenticate(sales)
    assert api_client.get(reverse("user-list")).status_code == 403
    assert api_client.get(reverse("invitation")).status_code == 403


@pytest.mark.django_db
def test_admin_can_invite_and_acceptance_creates_role_user(api_client: APIClient, admin_user: User, mailoutbox):
    api_client.force_authenticate(admin_user)
    invite = api_client.post(reverse("invitation"), {"email": "entrega@example.test", "role": "delivery"})
    assert invite.status_code == 201
    assert len(mailoutbox) == 1

    from apps.core.models import Invitation

    invitation = Invitation.objects.get(email="entrega@example.test")
    api_client.force_authenticate(user=None)
    accepted = api_client.post(reverse("accept-invitation"), {
        "token": str(invitation.token), "username": "entrega", "password": "SenhaSegura123!"
    }, format="json")
    assert accepted.status_code == 201
    assert User.objects.get(username="entrega").role == User.Role.DELIVERY


@pytest.mark.django_db
def test_task_list_filters_by_project(api_client: APIClient, admin_user: User):
    project = ProjectFactory(owner=admin_user)
    other = ProjectFactory(owner=admin_user)
    Task.objects.create(
        project=project, title="Da consulta", owner=admin_user, due_date=timezone.localdate()
    )
    Task.objects.create(
        project=other, title="De outro", owner=admin_user, due_date=timezone.localdate()
    )
    api_client.force_authenticate(admin_user)

    response = api_client.get(reverse("task-list"), {"project": project.id})

    assert response.status_code == 200
    assert [task["title"] for task in response.data] == ["Da consulta"]


@pytest.mark.django_db
def test_contact_list_filters_by_client(api_client: APIClient, admin_user: User):
    account = AccountFactory(owner=admin_user)
    other = AccountFactory(owner=admin_user)
    Contact.objects.create(account=account, first_name="Contato certo")
    Contact.objects.create(account=other, first_name="Contato errado")
    api_client.force_authenticate(admin_user)

    response = api_client.get(reverse("contact-list"), {"account": account.id})

    assert [contact["name"] for contact in response.data] == ["Contato certo"]


# --- edição de contato (issue #55, FDD 001) -------------------------------------------------


@pytest.mark.django_db
@pytest.mark.parametrize("role", [User.Role.SALES, User.Role.ADMIN])
def test_contact_patch_altera_nome_e_sobrenome_por_sales_e_admin(api_client: APIClient, role: str):
    user = UserFactory(role=role)
    account = AccountFactory(owner=user)
    contact = Contact.objects.create(account=account, first_name="Ana", last_name="Silva")
    api_client.force_authenticate(user)

    response = api_client.patch(
        reverse("contact-detail", args=[contact.id]),
        {"first_name": "Ana Paula", "last_name": "Souza"}, format="json",
    )

    assert response.status_code == 200, response.data
    contact.refresh_from_db()
    assert contact.first_name == "Ana Paula"
    assert contact.last_name == "Souza"
    assert response.data["name"] == "Ana Paula Souza"


@pytest.mark.django_db
def test_contact_patch_e_negado_para_delivery(api_client: APIClient):
    delivery = UserFactory(role=User.Role.DELIVERY)
    account = AccountFactory()
    contact = Contact.objects.create(account=account, first_name="Ana", last_name="Silva")
    api_client.force_authenticate(delivery)

    response = api_client.patch(
        reverse("contact-detail", args=[contact.id]), {"first_name": "Outro"}, format="json",
    )

    assert response.status_code == 403


@pytest.mark.django_db
def test_contact_sem_sobrenome_e_aceito_e_name_nao_sobra_espaco(api_client: APIClient, admin_user: User):
    account = AccountFactory(owner=admin_user)
    api_client.force_authenticate(admin_user)

    response = api_client.post(
        reverse("contact-list"), {"account": account.id, "first_name": "Madonna"}, format="json",
    )

    assert response.status_code == 201, response.data
    assert response.data["name"] == "Madonna"
    assert not response.data["name"].endswith(" ")


@pytest.mark.django_db
def test_contact_name_e_somente_leitura(api_client: APIClient, admin_user: User):
    account = AccountFactory(owner=admin_user)
    api_client.force_authenticate(admin_user)

    response = api_client.post(
        reverse("contact-list"),
        {"account": account.id, "first_name": "Ana", "last_name": "Silva", "name": "Nome Ignorado"},
        format="json",
    )

    assert response.status_code == 201, response.data
    contact = Contact.objects.get(pk=response.data["id"])
    assert contact.first_name == "Ana"
    assert contact.last_name == "Silva"
    assert response.data["name"] == "Ana Silva"

    patch_response = api_client.patch(
        reverse("contact-detail", args=[contact.id]), {"name": "Ainda Ignorado"}, format="json",
    )
    contact.refresh_from_db()
    assert patch_response.status_code == 200, patch_response.data
    assert contact.first_name == "Ana"
    assert contact.last_name == "Silva"


@pytest.mark.django_db
def test_contact_arquivado_nao_aparece_na_listagem_padrao(api_client: APIClient, admin_user: User):
    account = AccountFactory(owner=admin_user)
    contact = Contact.objects.create(account=account, first_name="Ana")
    contact.archive()
    api_client.force_authenticate(admin_user)

    response = api_client.get(reverse("contact-list"), {"account": account.id})

    assert response.data == []


@pytest.mark.django_db
def test_creating_milestone_defaults_owner_to_request_user(api_client: APIClient, admin_user: User):
    project = ProjectFactory(owner=admin_user)
    api_client.force_authenticate(admin_user)

    response = api_client.post(reverse("milestone-list"), {
        "project": project.id, "title": "Marco inicial", "due_date": str(timezone.localdate())
    }, format="json")

    assert response.status_code == 201
    assert Milestone.objects.get().owner_id == admin_user.id


@pytest.mark.django_db
@override_settings(LEAD_INTAKE_TOKEN="secret-token")
def test_lead_intake_requires_token_and_creates_lead(api_client: APIClient):
    from apps.core.models import Lead

    payload = {"name": "Fulano", "email": "f@x.com", "company": "ACME", "message": "quero ajuda"}

    unauthorized = api_client.post(reverse("lead-intake"), payload, format="json")
    assert unauthorized.status_code == 401

    ok = api_client.post(reverse("lead-intake"), payload, format="json", HTTP_X_INTAKE_TOKEN="secret-token")
    assert ok.status_code == 201
    lead = Lead.objects.get()
    assert lead.email == "f@x.com" and lead.source == "site" and lead.status == Lead.Status.NEW


@pytest.mark.django_db
@override_settings(LEAD_INTAKE_TOKEN="secret-token")
def test_lead_intake_honeypot_is_silently_dropped(api_client: APIClient):
    from apps.core.models import Lead

    response = api_client.post(
        reverse("lead-intake"),
        {"name": "Bot", "email": "b@x.com", "website": "http://spam"},
        format="json", HTTP_X_INTAKE_TOKEN="secret-token",
    )
    assert response.status_code == 201
    assert Lead.objects.count() == 0


@pytest.mark.django_db
def test_sales_converts_lead_into_client_and_qualification(api_client: APIClient):
    """Converter registra a **avaliação** e a conta — a venda é um segundo ato (ADR 0049).

    Antes esta ação criava direto uma `CommercialOpportunity` no degrau gratuito: a conversa de qualificação
    entrava no funil como venda registrada. A sequência normativa é
    `Lead → Qualification → (qualified) → CommercialOpportunity`.
    """
    from apps.core.models import CommercialOpportunity, Lead, Qualification

    sales = UserFactory(role=User.Role.SALES)
    lead = Lead.objects.create(name="Fulano", email="f@x.com", company="ACME", message="olá")
    api_client.force_authenticate(sales)

    response = api_client.post(reverse("lead-convert", args=[lead.id]), format="json")

    assert response.status_code == 201
    lead.refresh_from_db()
    assert lead.status == Lead.Status.QUALIFIED
    assert lead.account is not None
    assert lead.account.name == "ACME"
    assert lead.commercial_opportunity is None
    assert CommercialOpportunity.objects.count() == 0
    qualification = lead.qualifications.get()
    assert qualification.outcome == Qualification.Outcome.QUALIFIED
    assert qualification.assessor_id == sales.pk


@pytest.mark.django_db
def test_delivery_cannot_access_leads(api_client: APIClient):
    delivery = UserFactory(role=User.Role.DELIVERY)
    api_client.force_authenticate(delivery)
    assert api_client.get(reverse("lead-list")).status_code == 403


@pytest.mark.django_db
def test_new_lead_notifies_sales_and_admin(api_client: APIClient, admin_user: User):
    from apps.core.models import Lead, Notification

    sales = UserFactory(role=User.Role.SALES)
    delivery = UserFactory(role=User.Role.DELIVERY)
    Lead.objects.create(name="Fulano", email="f@x.com")

    assert Notification.objects.filter(user=admin_user, kind="lead").count() == 1
    assert Notification.objects.filter(user=sales, kind="lead").count() == 1
    assert Notification.objects.filter(user=delivery).count() == 0  # entrega não recebe


@pytest.mark.django_db
def test_notifications_are_per_user_and_can_be_marked_read(api_client: APIClient, admin_user: User):
    from apps.core.models import Notification

    Notification.objects.create(user=admin_user, kind="lead", message="Novo lead: A")
    other = UserFactory(role=User.Role.SALES)
    Notification.objects.create(user=other, kind="lead", message="Novo lead: B")
    api_client.force_authenticate(admin_user)

    listing = api_client.get(reverse("notification-list"))
    assert listing.status_code == 200
    assert len(listing.data) == 1  # só as próprias

    notification_id = listing.data[0]["id"]
    marked = api_client.post(reverse("notification-read", args=[notification_id]))
    assert marked.status_code == 200 and marked.data["read"] is True

    api_client.post(reverse("notification-read-all"))
    assert Notification.objects.filter(user=admin_user, read=False).count() == 0


@pytest.mark.django_db
@override_settings(AI_ENABLED=True, OPENAI_API_KEY="sk-x")
def test_project_assistant_returns_answer_and_logs_interaction(api_client: APIClient, admin_user: User, monkeypatch):
    from apps.core import ai
    from apps.core.models import AiInteraction

    monkeypatch.setattr(ai, "complete", lambda system, user: ("Resposta da IA", {"prompt_tokens": 10, "completion_tokens": 5}))
    project = ProjectFactory(owner=admin_user)
    api_client.force_authenticate(admin_user)

    response = api_client.post(reverse("project-assistant", args=[project.id]), {"question": "Qual o status?"}, format="json")

    assert response.status_code == 200
    assert response.data["text"] == "Resposta da IA"
    assert AiInteraction.objects.filter(feature="project_chat", project=project).count() == 1


@pytest.mark.django_db
def test_ai_action_returns_503_when_disabled(api_client: APIClient, admin_user: User):
    project = ProjectFactory(owner=admin_user)
    api_client.force_authenticate(admin_user)
    response = api_client.post(reverse("project-summary", args=[project.id]), {}, format="json")
    assert response.status_code == 503


@pytest.mark.django_db
@override_settings(AI_ENABLED=True, OPENAI_API_KEY="sk-x", AI_DAILY_LIMIT=0)
def test_ai_action_returns_429_over_daily_limit(api_client: APIClient, admin_user: User):
    opportunity = CommercialOpportunityFactory(owner=admin_user)
    api_client.force_authenticate(admin_user)
    response = api_client.post(reverse("opportunity-proposal", args=[opportunity.id]), {}, format="json")
    assert response.status_code == 429


@pytest.mark.django_db
@override_settings(AI_ENABLED=True, OPENAI_API_KEY="sk-x")
def test_contract_action_returns_draft_and_logs_interaction(api_client: APIClient, admin_user: User, monkeypatch):
    from apps.core import ai
    from apps.core.models import AiInteraction

    monkeypatch.setattr(ai, "complete", lambda system, user: ("CONTRATO...", {"prompt_tokens": 4, "completion_tokens": 3}))
    opportunity = CommercialOpportunityFactory(owner=admin_user)
    api_client.force_authenticate(admin_user)

    response = api_client.post(reverse("opportunity-contract", args=[opportunity.id]), {}, format="json")

    assert response.status_code == 200
    assert response.data["text"] == "CONTRATO..."
    assert AiInteraction.objects.filter(feature="contract", commercial_opportunity=opportunity).count() == 1


@pytest.mark.django_db
@override_settings(AI_ENABLED=True, OPENAI_API_KEY="sk-x")
@pytest.mark.parametrize(("action", "feature"), [
    ("meeting-discovery", "meeting_discovery"),
    ("meeting-assessment", "meeting_assessment"),
])
def test_meeting_ai_returns_text_and_logs_interaction(api_client, admin_user, monkeypatch, action, feature):
    from apps.core import ai
    from apps.core.models import AiInteraction

    monkeypatch.setattr(ai, "complete", lambda system, user: ("Saída da IA", {"prompt_tokens": 3, "completion_tokens": 2}))
    meeting = MeetingFactory(transcript="Cliente descreveu dores no faturamento.")
    api_client.force_authenticate(admin_user)

    response = api_client.post(reverse(action, args=[meeting.id]), {}, format="json")

    assert response.status_code == 200
    assert response.data["text"] == "Saída da IA"
    assert AiInteraction.objects.filter(feature=feature, project=meeting.project).count() == 1


@pytest.mark.django_db
@override_settings(AI_ENABLED=True, OPENAI_API_KEY="sk-x")
def test_meeting_ai_requires_transcript(api_client, admin_user):
    meeting = MeetingFactory(transcript="   ")
    api_client.force_authenticate(admin_user)
    response = api_client.post(reverse("meeting-discovery", args=[meeting.id]), {}, format="json")
    assert response.status_code == 400


@pytest.mark.django_db
def test_meeting_ai_returns_503_when_disabled(api_client, admin_user):
    meeting = MeetingFactory()
    api_client.force_authenticate(admin_user)
    response = api_client.post(reverse("meeting-assessment", args=[meeting.id]), {}, format="json")
    assert response.status_code == 503


@pytest.mark.django_db
# `ESIGN_ENABLED=False` explícito: desde a ADR 0018 a assinatura nasce ligada, e o valor deste teste
# está em conferir que o endpoint reporta ligada e desligada — não em herdar o default.
@override_settings(AI_ENABLED=True, OPENAI_API_KEY="sk-x", ESIGN_ENABLED=False)
def test_config_exposes_feature_flags(api_client: APIClient, admin_user: User):
    api_client.force_authenticate(admin_user)
    response = api_client.get(reverse("config"))
    assert response.data["ai_enabled"] is True
    assert response.data["calendar_enabled"] is False
    assert response.data["esign_enabled"] is False


@pytest.mark.django_db
def test_add_to_calendar_returns_503_when_disabled(api_client: APIClient, admin_user: User):
    project = ProjectFactory(owner=admin_user)
    milestone = Milestone.objects.create(project=project, title="M", owner=admin_user, due_date=timezone.localdate())
    api_client.force_authenticate(admin_user)
    response = api_client.post(reverse("milestone-add-to-calendar", args=[milestone.id]))
    assert response.status_code == 503


@pytest.mark.django_db
@override_settings(MEDIA_ROOT="/tmp/biahflow-test-media", ESIGN_ENABLED=False)
def test_request_signature_flag_gated(api_client: APIClient, admin_user: User):
    from apps.core.models import SignatureRequest

    account = AccountFactory(owner=admin_user)
    api_client.force_authenticate(admin_user)
    file = SimpleUploadedFile("contrato.pdf", b"x", content_type="application/pdf")
    document = api_client.post(reverse("document-list"), {"account": account.id, "file": file}).data

    off = api_client.post(reverse("document-request-signature", args=[document["id"]]), {"signer_email": "a@b.com"}, format="json")
    assert off.status_code == 503

    with override_settings(ESIGN_ENABLED=True):  # sem provedor: registro local + mark-signed
        on = api_client.post(reverse("document-request-signature", args=[document["id"]]), {"signer_email": "a@b.com"}, format="json")
    assert on.status_code == 201
    assert SignatureRequest.objects.filter(document_id=document["id"]).count() == 1


@pytest.mark.django_db
@override_settings(MEDIA_ROOT="/tmp/biahflow-test-media")
def test_remind_signature_and_mark_signed_close_the_loop(api_client: APIClient, admin_user: User, mailoutbox):
    from apps.core.models import SignatureRequest

    account = AccountFactory(owner=admin_user)
    api_client.force_authenticate(admin_user)
    file = SimpleUploadedFile("contrato.pdf", b"x", content_type="application/pdf")
    document = api_client.post(reverse("document-list"), {"account": account.id, "file": file}).data
    with override_settings(ESIGN_ENABLED=True):  # sem provedor: registro local + mark-signed
        api_client.post(reverse("document-request-signature", args=[document["id"]]), {"signer_email": "quem@assina.test"}, format="json")

        remind_off = api_client.post(reverse("document-remind-signature", args=[document["id"]]))
        assert remind_off.status_code == 200
        assert remind_off.data["reminded"] == 1
        assert len(mailoutbox) == 1

        signature = SignatureRequest.objects.get(document_id=document["id"])
        signed = api_client.post(reverse("document-mark-signed", args=[document["id"]]), {"signature": signature.id}, format="json")
        assert signed.status_code == 200
        assert signed.data["status"] == "signed"
        assert signed.data["signed_at"] is not None
        # `mark-signed` passou a passar por `esign.apply_decision`, o mesmo caminho do webhook —
        # ela notifica quem subiu o documento, e a flag `email` (ligada por padrão) espelha isso
        # por e-mail. Antes desta tarefa o fallback manual não fazia nenhum dos dois.
        assert len(mailoutbox) == 2

        # Já assinado: um novo lembrete não envia nada.
        again = api_client.post(reverse("document-remind-signature", args=[document["id"]]))
    assert again.data["reminded"] == 0
    assert len(mailoutbox) == 2


@pytest.mark.django_db
@override_settings(MEDIA_ROOT="/tmp/biahflow-test-media", ESIGN_ENABLED=True)
def test_mark_signed_unknown_signature_returns_404(api_client: APIClient, admin_user: User):
    account = AccountFactory(owner=admin_user)
    api_client.force_authenticate(admin_user)
    file = SimpleUploadedFile("contrato.pdf", b"x", content_type="application/pdf")
    document = api_client.post(reverse("document-list"), {"account": account.id, "file": file}).data
    response = api_client.post(reverse("document-mark-signed", args=[document["id"]]), {"signature": 999999}, format="json")
    assert response.status_code == 404


@pytest.mark.django_db
def test_risk_and_recommendations_endpoints(api_client: APIClient, admin_user: User):
    ProjectFactory(owner=admin_user, due_date=timezone.localdate() - timedelta(days=3))
    api_client.force_authenticate(admin_user)

    risk_response = api_client.get(reverse("risk"))
    assert risk_response.status_code == 200 and "projects" in risk_response.data

    recs_response = api_client.get(reverse("recommendations"))
    assert recs_response.status_code == 200 and "items" in recs_response.data


@pytest.mark.django_db
@override_settings(AI_ENABLED=True, OPENAI_API_KEY="sk-x")
def test_project_next_steps_agent_uses_ai_and_logs(api_client: APIClient, admin_user: User, monkeypatch):
    from apps.core import ai
    from apps.core.models import AiInteraction

    monkeypatch.setattr(ai, "complete", lambda system, user: ("Passo 1: ...", {"prompt_tokens": 1, "completion_tokens": 1}))
    project = ProjectFactory(owner=admin_user)
    api_client.force_authenticate(admin_user)

    response = api_client.post(reverse("project-next-steps", args=[project.id]))

    assert response.status_code == 200
    assert AiInteraction.objects.filter(feature="project_next_steps", project=project).count() == 1


@pytest.mark.django_db
def test_next_steps_returns_503_when_ai_disabled(api_client: APIClient, admin_user: User):
    project = ProjectFactory(owner=admin_user)
    api_client.force_authenticate(admin_user)
    response = api_client.post(reverse("project-next-steps", args=[project.id]))
    assert response.status_code == 503


@pytest.mark.django_db
def test_analytics_computes_win_rate_and_roi(api_client: APIClient, admin_user: User):
    won = PipelineStage.objects.get(kind=PipelineStage.Kind.WON)
    lost = PipelineStage.objects.get(kind=PipelineStage.Kind.LOST)
    CommercialOpportunityFactory(stage=won, owner=admin_user, estimated_value=1000)
    CommercialOpportunityFactory(stage=lost, owner=admin_user)
    ProjectFactory(owner=admin_user, actual_value=1000, cost=400)
    api_client.force_authenticate(admin_user)

    response = api_client.get(reverse("analytics"))

    assert response.status_code == 200
    assert response.data["win_rate"] == 0.5
    assert response.data["roi"]["roi"] == 1.5  # (1000 - 400) / 400


@pytest.mark.django_db
def test_analytics_breaks_the_funnel_down_by_product_tier(api_client: APIClient, admin_user: User):
    won = PipelineStage.objects.get(kind=PipelineStage.Kind.WON)
    lost = PipelineStage.objects.get(kind=PipelineStage.Kind.LOST)
    sprint = Service.objects.get(tier=Service.Tier.DISCOVERY_SPRINT)
    CommercialOpportunityFactory(stage=won, owner=admin_user, service=sprint, estimated_value=0)
    CommercialOpportunityFactory(stage=lost, owner=admin_user, service=sprint, estimated_value=0)
    api_client.force_authenticate(admin_user)

    response = api_client.get(reverse("analytics"))

    assert response.status_code == 200
    by_tier = {row["tier"]: row for row in response.data["funnel"]["by_tier"]}
    assert set(by_tier) == {tier for tier, _ in Service.Tier.choices}
    assert by_tier["discovery_sprint"]["total"] == 2
    assert by_tier["discovery_sprint"]["win_rate"] == 0.5
    assert by_tier["prove"]["total"] == 0
    assert by_tier["prove"]["win_rate"] is None


@pytest.mark.django_db
def test_analytics_breaks_the_funnel_down_by_journey_stage(api_client: APIClient, admin_user: User):
    account = AccountFactory(owner=admin_user)
    # Duas propostas para o mesmo cliente: dois artefatos, um só cliente alcançado.
    ArtifactFactory(commercial_opportunity=CommercialOpportunityFactory(account=account, owner=admin_user),
                    status=Artifact.Status.ACCEPTED)
    ArtifactFactory(commercial_opportunity=CommercialOpportunityFactory(account=account, owner=admin_user),
                    status=Artifact.Status.REJECTED)
    ArtifactFactory(commercial_opportunity=None, project=ProjectFactory(engagement__account=account, owner=admin_user),
                    kind=Artifact.Kind.ASSESSMENT, status=Artifact.Status.SENT)
    api_client.force_authenticate(admin_user)

    response = api_client.get(reverse("analytics"))

    assert response.status_code == 200
    by_stage = {row["kind"]: row for row in response.data["funnel"]["by_stage"]}
    assert set(by_stage) == {kind for kind, _ in Artifact.Kind.choices}
    assert by_stage["proposal"]["total"] == 2
    assert by_stage["proposal"]["reached"] == 1
    assert by_stage["proposal"]["acceptance_rate"] == 0.5
    assert by_stage["assessment"]["sent"] == 1
    assert by_stage["assessment"]["acceptance_rate"] is None
    assert by_stage["contract"]["total"] == 0
    assert by_stage["contract"]["reached"] == 0


@pytest.mark.django_db
def test_roi_handles_zero_cost_without_error(api_client: APIClient, admin_user: User):
    ProjectFactory(owner=admin_user, actual_value=500, cost=0)
    api_client.force_authenticate(admin_user)
    response = api_client.get(reverse("analytics"))
    assert response.status_code == 200
    assert response.data["roi"]["roi"] is None  # custo 0 → sem divisão


@pytest.mark.django_db
def test_service_write_is_admin_only_but_readable(api_client: APIClient, admin_user: User):
    api_client.force_authenticate(admin_user)
    assert api_client.post(reverse("service-list"), {"name": "Consultoria"}, format="json").status_code == 201

    sales = UserFactory(role=User.Role.SALES)
    api_client.force_authenticate(sales)
    assert api_client.get(reverse("service-list")).status_code == 200  # leitura ok
    assert api_client.post(reverse("service-list"), {"name": "X"}, format="json").status_code == 403
    assert api_client.get(reverse("analytics")).status_code == 200  # vendas vê indicadores


@pytest.mark.django_db
def test_dashboard_returns_overdue_count(api_client: APIClient, admin_user: User):
    project = ProjectFactory(owner=admin_user)
    Task.objects.create(
        project=project, title="Atrasada", owner=admin_user,
        due_date=timezone.localdate() - timedelta(days=2),
    )
    api_client.force_authenticate(admin_user)
    response = api_client.get(reverse("dashboard"))
    assert response.status_code == 200
    assert response.data["overdue_count"] == 1


@pytest.mark.django_db
def test_dashboard_ignores_completed_items_and_returns_upcoming_tasks(
    api_client: APIClient, admin_user: User
):
    project = ProjectFactory(owner=admin_user)
    Task.objects.create(
        project=project,
        title="Concluída",
        owner=admin_user,
        due_date=timezone.localdate() - timedelta(days=1),
        status=Task.Status.DONE,
    )
    Task.objects.create(
        project=project,
        title="Próxima",
        owner=admin_user,
        due_date=timezone.localdate() + timedelta(days=1),
    )
    api_client.force_authenticate(admin_user)

    response = api_client.get(reverse("dashboard"))

    assert response.data["overdue_count"] == 0
    assert [task["title"] for task in response.data["upcoming_tasks"]] == ["Próxima"]


@pytest.mark.django_db
def test_client_status_is_declared_on_creation(api_client: APIClient, admin_user: User):
    api_client.force_authenticate(admin_user)
    url = reverse("client-list")

    declared = api_client.post(url, {"name": "Já é cliente", "status": "active"}, format="json")
    omitted = api_client.post(url, {"name": "Ainda não é"}, format="json")

    assert declared.status_code == 201
    assert declared.data["status"] == "active"
    # Sem o campo, o cadastro não alega uma venda que não houve.
    assert omitted.status_code == 201
    assert omitted.data["status"] == "prospect"


@pytest.mark.django_db
def test_opportunity_exposes_the_project_it_became(api_client: APIClient, admin_user: User):
    won = PipelineStage.objects.get(kind=PipelineStage.Kind.WON)
    converted = CommercialOpportunityFactory(stage=won, owner=admin_user)
    pending = CommercialOpportunityFactory(stage=won, owner=admin_user)
    api_client.force_authenticate(admin_user)
    api_client.post(
        reverse("opportunity-convert-to-project", args=[converted.pk]),
        {"client": converted.account_id, "name": "Projeto", "start_date": "2026-08-01",
         "due_date": "2026-09-01", "status": "planning"},
        format="json",
    )

    rows = {row["id"]: row["project"] for row in api_client.get(reverse("opportunity-list")).data}

    # Sem este campo a tela do pipeline não sabe que já converteu e oferece "Criar projeto" de novo.
    assert rows[converted.pk] == Project.objects.get(
        originating_commercial_opportunity=converted
    ).pk
    assert rows[pending.pk] is None


@pytest.mark.django_db
def test_meeting_keeps_room_link_and_recording_apart(api_client: APIClient, admin_user: User):
    project = ProjectFactory(owner=admin_user)
    api_client.force_authenticate(admin_user)

    response = api_client.post(
        reverse("meeting-list"),
        {"project": project.pk, "title": "Kickoff", "date": "2026-08-20",
         "meeting_url": "https://meet.example/abc", "recording_url": "https://rec.example/abc"},
        format="json",
    )

    assert response.status_code == 201
    assert response.data["meeting_url"] == "https://meet.example/abc"
    assert response.data["recording_url"] == "https://rec.example/abc"
