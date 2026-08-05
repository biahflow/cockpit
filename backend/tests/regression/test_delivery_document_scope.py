"""Regressão: Entrega só enxerga documentos dos projetos em que atua (FDD 017, ADR 0009).

O `Document` era o furo que sobrava do recorte da FDD 016: proposta e contrato salvos pelo
painel de artefatos nascem ligados à **oportunidade**, e a lista de documentos não estreitava
por função — então quem é da Entrega baixava valor, custo e condição comercial pelo
`download`, exatamente o conteúdo que o `ArtifactViewSet` esconde dela.

"Atuar no projeto" era ser dono dele ou de um item de trabalho; desde o RFC 0003 é participar
da equipe (`ProjectMember`). Admin e Vendas não são afetados.
"""

import pytest
from django.core.files.uploadedfile import SimpleUploadedFile
from django.urls import reverse
from rest_framework.test import APIClient

from apps.core.models import Document, Task, User
from apps.core.tests.factories import (
    ClientFactory,
    OpportunityFactory,
    ProjectFactory,
    ProjectMemberFactory,
    UserFactory,
)

pytestmark = pytest.mark.django_db


@pytest.fixture(autouse=True)
def media_root(settings) -> None:  # type: ignore[no-untyped-def]
    settings.MEDIA_ROOT = "/tmp/biahflow-test-media"


def _document(**links: object) -> Document:
    return Document.objects.create(
        original_name="proposta.pdf",
        file=SimpleUploadedFile("proposta.pdf", b"valor e margem", content_type="application/pdf"),
        uploaded_by=UserFactory(),
        **links,
    )


def test_delivery_outside_the_project_sees_no_documents() -> None:
    delivery = UserFactory(role=User.Role.DELIVERY)
    commercial = _document(opportunity=OpportunityFactory())
    other_project = _document(project=ProjectFactory())

    api = APIClient()
    api.force_authenticate(delivery)

    assert api.get(reverse("document-list")).data == []
    for document in (commercial, other_project):
        assert api.get(reverse("document-detail", args=[document.id])).status_code == 404
        assert api.get(reverse("document-download", args=[document.id])).status_code == 404


def test_delivery_sees_documents_of_the_project_it_owns() -> None:
    delivery = UserFactory(role=User.Role.DELIVERY)
    project = ProjectFactory(owner=delivery)
    document = _document(project=project)

    api = APIClient()
    api.force_authenticate(delivery)

    assert [row["id"] for row in api.get(reverse("document-list")).data] == [document.id]
    assert api.get(reverse("document-download", args=[document.id])).status_code == 200


def test_delivery_sees_documents_of_the_project_it_works_on() -> None:
    """Participar da equipe é o critério — ser dono de uma tarefa deixou de bastar (RFC 0003)."""
    delivery = UserFactory(role=User.Role.DELIVERY)
    project = ProjectFactory()
    ProjectMemberFactory(project=project, user=delivery)
    Task.objects.create(
        project=project, title="Configurar ambiente", owner=delivery,
        due_date=project.due_date,
    )
    document = _document(project=project)

    api = APIClient()
    api.force_authenticate(delivery)

    assert [row["id"] for row in api.get(reverse("document-list")).data] == [document.id]
    assert api.get(reverse("document-download", args=[document.id])).status_code == 200


def test_delivery_cannot_upload_a_document_linked_to_an_opportunity() -> None:
    """Sem isso, Entrega criaria um documento comercial que some da própria lista."""
    delivery = UserFactory(role=User.Role.DELIVERY)
    opportunity = OpportunityFactory()

    api = APIClient()
    api.force_authenticate(delivery)
    response = api.post(reverse("document-list"), {
        "opportunity": opportunity.id,
        "file": SimpleUploadedFile("contrato.pdf", b"conteudo", content_type="application/pdf"),
    })

    assert response.status_code == 403
    assert not Document.objects.filter(opportunity=opportunity).exists()


def test_sales_keeps_full_access_to_documents() -> None:
    sales = UserFactory(role=User.Role.SALES)
    commercial = _document(opportunity=OpportunityFactory())
    operational = _document(project=ProjectFactory())
    institutional = _document(client=ClientFactory())

    api = APIClient()
    api.force_authenticate(sales)

    listed = {row["id"] for row in api.get(reverse("document-list")).data}
    assert listed == {commercial.id, operational.id, institutional.id}
