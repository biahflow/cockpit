from datetime import timedelta
from unittest.mock import patch

import pytest
from django.core.exceptions import ValidationError
from django.core.files.uploadedfile import SimpleUploadedFile
from django.db import IntegrityError
from django.test import override_settings
from django.urls import reverse
from django.utils import timezone
from rest_framework.test import APIClient

from apps.core.models import Document, Milestone, PipelineStage, Service, User

from .factories import (
    AccountFactory,
    CommercialOpportunityFactory,
    EngagementFactory,
    ProjectFactory,
    ServiceFactory,
    UserFactory,
)


@pytest.fixture
def sales_client() -> tuple[APIClient, User]:
    user = UserFactory(role=User.Role.SALES)
    client = APIClient()
    client.force_authenticate(user)
    return client, user


@pytest.mark.django_db
def test_opportunity_rejects_contact_from_different_client(sales_client: tuple[APIClient, User]) -> None:
    client, _ = sales_client
    first = AccountFactory()
    second = AccountFactory()
    contact = second.contacts.create(first_name="Contato externo")
    response = client.post(reverse("opportunity-list"), {
        "account": first.id,
        "contact": contact.id,
        "title": "Escopo",
        "estimated_value": "1000.00",
        "stage": PipelineStage.objects.filter(kind="open").first().id,
        "expected_close_date": str(timezone.localdate()),
    }, format="json")

    assert response.status_code == 400
    assert "contact" in response.data


@pytest.mark.django_db
def test_project_rejects_end_date_before_start() -> None:
    # Criar projeto passou a ser de admin/Vendas (RFC 0003): Entrega recebe 403 antes da
    # validação de datas, então o caso de borda precisa de quem realmente cria projeto.
    admin = UserFactory(role=User.Role.ADMIN)
    project_client = AccountFactory()
    # `engagement` é obrigatório desde a ADR 0050; sem ele o 400 seria do campo faltando e este
    # teste passaria sem nunca exercitar a validação de datas que ele existe para cobrir.
    engagement = EngagementFactory(account=project_client)
    client = APIClient()
    client.force_authenticate(admin)

    response = client.post(reverse("project-list"), {
        "client": project_client.id,
        "engagement": engagement.id,
        "name": "Datas inválidas",
        "start_date": "2026-08-10",
        "due_date": "2026-08-09",
    }, format="json")

    assert response.status_code == 400
    assert "due_date" in response.data


@pytest.mark.django_db
def test_task_rejects_milestone_from_another_project() -> None:
    delivery = UserFactory(role=User.Role.DELIVERY)
    first_project = ProjectFactory()
    second_project = ProjectFactory()
    milestone = Milestone.objects.create(
        project=first_project, title="Marco", owner=delivery, due_date=timezone.localdate()
    )
    client = APIClient()
    client.force_authenticate(delivery)

    response = client.post(reverse("task-list"), {
        "project": second_project.id,
        "milestone": milestone.id,
        "title": "Tarefa inválida",
        "owner": delivery.id,
        "due_date": str(timezone.localdate()),
    }, format="json")

    assert response.status_code == 400
    assert "milestone" in response.data


@pytest.mark.django_db
@override_settings(MEDIA_ROOT="/tmp/biahflow-test-media")
def test_document_rejects_multiple_links_and_excessive_size() -> None:
    admin = UserFactory(role=User.Role.ADMIN)
    first = AccountFactory(owner=admin)
    second = AccountFactory(owner=admin)
    client = APIClient()
    client.force_authenticate(admin)

    linked_twice = client.post(reverse("document-list"), {
        "account": first.id,
        "project": ProjectFactory(engagement__account=second).id,
        "file": SimpleUploadedFile("duplicado.pdf", b"ok"),
    })
    oversized = client.post(reverse("document-list"), {
        "account": first.id,
        "file": SimpleUploadedFile("grande.pdf", b"x" * (10 * 1024 * 1024 + 1)),
    })

    assert linked_twice.status_code == 400
    assert oversized.status_code == 400
    assert "file" in oversized.data


@pytest.mark.django_db
@override_settings(MEDIA_ROOT="/tmp/biahflow-test-media")
def test_document_rejects_file_types_outside_the_allowlist() -> None:
    """Nome de arquivo é entrada do usuário e viaja para o Drive e para o fornecedor de assinatura."""
    admin = UserFactory(role=User.Role.ADMIN)
    linked = AccountFactory(owner=admin)
    client = APIClient()
    client.force_authenticate(admin)

    for name in ("payload.html", "icone.svg", "instalador.exe", "sem-extensao"):
        rejected = client.post(reverse("document-list"), {
            "account": linked.id,
            "file": SimpleUploadedFile(name, b"conteudo"),
        })
        assert rejected.status_code == 400, name
        assert "file" in rejected.data

    for name in ("proposta.pdf", "planilha.XLSX", "notas.txt", "print.png"):
        accepted = client.post(reverse("document-list"), {
            "account": linked.id,
            "file": SimpleUploadedFile(name, b"conteudo"),
        })
        assert accepted.status_code == 201, name


@pytest.mark.django_db
@override_settings(MEDIA_ROOT="/tmp/biahflow-test-media")
def test_document_original_name_never_carries_a_path() -> None:
    """`original_name` é repassado cru ao Drive, ao fornecedor de assinatura e ao portal."""
    admin = UserFactory(role=User.Role.ADMIN)
    linked = AccountFactory(owner=admin)
    client = APIClient()
    client.force_authenticate(admin)

    response = client.post(reverse("document-list"), {
        "account": linked.id,
        "file": SimpleUploadedFile("../../etc/passwd.pdf", b"conteudo"),
    })

    assert response.status_code == 201
    original_name = Document.objects.get(id=response.data["id"]).original_name
    assert "/" not in original_name and ".." not in original_name


@pytest.mark.django_db
@override_settings(MEDIA_ROOT="/tmp/biahflow-test-media")
def test_document_without_kind_keeps_working() -> None:
    """`kind` é opcional — o caminho de upload que já existia antes dele não pode quebrar."""
    admin = UserFactory(role=User.Role.ADMIN)
    linked = AccountFactory(owner=admin)
    client = APIClient()
    client.force_authenticate(admin)

    response = client.post(reverse("document-list"), {
        "account": linked.id,
        "file": SimpleUploadedFile("proposta.pdf", b"conteudo"),
    })

    assert response.status_code == 201
    assert response.data["kind"] == ""


@pytest.mark.django_db
@override_settings(MEDIA_ROOT="/tmp/biahflow-test-media")
def test_design_partner_agreement_accepts_account_link() -> None:
    admin = UserFactory(role=User.Role.ADMIN)
    linked = AccountFactory(owner=admin)
    client = APIClient()
    client.force_authenticate(admin)

    response = client.post(reverse("document-list"), {
        "account": linked.id,
        "kind": Document.Kind.DESIGN_PARTNER_AGREEMENT,
        "file": SimpleUploadedFile("acordo.pdf", b"conteudo"),
    })

    assert response.status_code == 201
    assert response.data["kind"] == Document.Kind.DESIGN_PARTNER_AGREEMENT


@pytest.mark.django_db
@override_settings(MEDIA_ROOT="/tmp/biahflow-test-media")
def test_design_partner_agreement_rejects_project_link() -> None:
    """Um acordo pendurado num projeto jamais poderia originar um `Engagement` (models.py:376-380)
    — é melhor recusar no upload do que falhar obscuro lá na frente.
    """
    admin = UserFactory(role=User.Role.ADMIN)
    account = AccountFactory(owner=admin)
    project = ProjectFactory(engagement__account=account)
    client = APIClient()
    client.force_authenticate(admin)

    response = client.post(reverse("document-list"), {
        "project": project.id,
        "kind": Document.Kind.DESIGN_PARTNER_AGREEMENT,
        "file": SimpleUploadedFile("acordo.pdf", b"conteudo"),
    })

    assert response.status_code == 400
    assert "kind" in response.data


@pytest.mark.django_db
def test_design_partner_agreement_model_requires_account() -> None:
    """A metade da invariante que protege shell, admin e migração — não passa pelo serializer."""
    admin = UserFactory(role=User.Role.ADMIN)
    account = AccountFactory(owner=admin)
    project = ProjectFactory(engagement__account=account)
    document = Document(
        kind=Document.Kind.DESIGN_PARTNER_AGREEMENT,
        project=project,
        original_name="acordo.pdf",
        uploaded_by=admin,
    )

    with pytest.raises(ValidationError):
        document.full_clean()


@pytest.mark.parametrize(("raw", "expected"), [
    ("../../etc/passwd.pdf", "passwd.pdf"),
    (r"C:\Users\alguem\contrato.pdf", "contrato.pdf"),
    ("nota\r\nfiscal.pdf", "notafiscal.pdf"),
    (".oculto.pdf", "oculto.pdf"),
    ("", "documento"),
    (None, "documento"),
])
def test_safe_original_name(raw: str | None, expected: str) -> None:
    """Casos que o multipart não consegue carregar, mas o Drive e o e-sign conseguem."""
    from apps.core.serializers import _safe_original_name

    assert _safe_original_name(raw) == expected


@pytest.mark.django_db
def test_conversion_rejects_delivery_foreign_engagement_and_invalid_dates() -> None:
    sales = UserFactory(role=User.Role.SALES)
    opportunity = CommercialOpportunityFactory(stage=PipelineStage.objects.get(kind="won"), owner=sales)
    endpoint = reverse("opportunity-convert-to-project", args=[opportunity.id])

    delivery_client = APIClient()
    delivery_client.force_authenticate(UserFactory(role=User.Role.DELIVERY))
    forbidden = delivery_client.post(endpoint, {}, format="json")

    sales_client = APIClient()
    sales_client.force_authenticate(sales)
    # Fase 6: `Project.client` saiu e a conta do projeto é a do engagement. A invariante que
    # sobrevive é "o engagement tem de ser da mesma conta da oportunidade" (view l. 1031), 400.
    foreign = sales_client.post(endpoint, {
        "engagement": EngagementFactory().id,
        "name": "Conta incorreta",
        "start_date": "2026-08-01",
        "due_date": "2026-08-10",
    }, format="json")
    invalid_dates = sales_client.post(endpoint, {
        "account": opportunity.account_id,
        "name": "Datas inválidas",
        "start_date": "2026-08-10",
        "due_date": "2026-08-01",
    }, format="json")

    assert forbidden.status_code == 403
    assert foreign.status_code == 400
    assert invalid_dates.status_code == 400


@pytest.mark.django_db
def test_conversion_returns_conflict_without_partial_project_on_integrity_error() -> None:
    sales = UserFactory(role=User.Role.SALES)
    opportunity = CommercialOpportunityFactory(stage=PipelineStage.objects.get(kind="won"), owner=sales)
    client = APIClient()
    client.force_authenticate(sales)
    payload = {
        "client": opportunity.account_id,
        "name": "Projeto",
        "start_date": str(timezone.localdate()),
        "due_date": str(timezone.localdate() + timedelta(days=10)),
    }

    with patch("apps.core.views.ProjectSerializer.save", side_effect=IntegrityError):
        response = client.post(
            reverse("opportunity-convert-to-project", args=[opportunity.id]), payload, format="json"
        )

    assert response.status_code == 409
    # A transação inteira desfeita: nem projeto parcial, nem o engajamento de escopo único que a
    # conversão cria quando o payload não traz um (ADR 0050).
    assert not opportunity.projects.exists()
    assert not opportunity.account.engagements.exists()


@pytest.mark.django_db
def test_conversion_inherits_the_opportunity_product_tier() -> None:
    """O primeiro degrau **vendável**, e não a Qualification Call: aquela é oferta de aquisição
    desde a ADR 0049 e a conversão a recusa (invariante 6)."""
    sales = UserFactory(role=User.Role.SALES)
    porta = Service.objects.get(tier=Service.Tier.DISCOVERY_SPRINT)
    opportunity = CommercialOpportunityFactory(
        stage=PipelineStage.objects.get(kind="won"), owner=sales, service=porta
    )
    client = APIClient()
    client.force_authenticate(sales)

    response = client.post(reverse("opportunity-convert-to-project", args=[opportunity.id]), {
        "client": opportunity.account_id,
        "name": "Discovery do cliente",
        "start_date": str(timezone.localdate()),
        "due_date": str(timezone.localdate() + timedelta(days=30)),
    }, format="json")

    assert response.status_code == 201
    assert response.json()["service"] == porta.pk
    # O cronograma segue o degrau, não o template genérico: o Discovery Sprint semeia três
    # marcos e fecha em Executive Readout, e o padrão semearia quatro genéricos.
    assert Milestone.objects.filter(project_id=response.json()["id"]).count() == 3


@pytest.mark.django_db
def test_conversion_payload_overrides_the_inherited_service() -> None:
    sales = UserFactory(role=User.Role.SALES)
    chosen = ServiceFactory(name="Serviço combinado")
    opportunity = CommercialOpportunityFactory(
        stage=PipelineStage.objects.get(kind="won"), owner=sales,
        service=Service.objects.get(tier=Service.Tier.QUALIFICATION_CALL),
    )
    client = APIClient()
    client.force_authenticate(sales)

    response = client.post(reverse("opportunity-convert-to-project", args=[opportunity.id]), {
        "client": opportunity.account_id,
        "name": "Projeto",
        "start_date": str(timezone.localdate()),
        "due_date": str(timezone.localdate() + timedelta(days=30)),
        "service": chosen.pk,
    }, format="json")

    assert response.status_code == 201
    assert response.json()["service"] == chosen.pk
