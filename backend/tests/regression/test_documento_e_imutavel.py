"""Regressão: `Document` não aceita `PUT`/`PATCH` (achado na revisão da #120).

`DocumentViewSet` era `ModelViewSet` puro e expunha o `update`/`partial_update` padrão do DRF.
Trocar o `file` por `PATCH` não fareja o conteúdo novo (`content_is_pdf` ficava carimbado do
arquivo **anterior**, e a tela de assinatura passava a mentir sobre o posicionamento), não sobe ao
Drive (`drive_file_id`/`drive_link` continuavam apontando para o arquivo velho) e não passa pelas
guardas de extensão/tamanho que só o caminho de criação tem. Sem chamador na SPA nem em teste — era
porta aberta sem guarda. O fechamento é no molde de `PriorityAssessmentViewSet`
(`http_method_names` sem `put`/`patch`): 405, não 400 — o método não existe aqui, o corpo nem
chega a ser lido.
"""

import pytest
from django.core.files.uploadedfile import SimpleUploadedFile
from django.urls import reverse
from rest_framework.test import APIClient

from apps.core.models import Document, User
from apps.core.tests.factories import ProjectFactory, UserFactory

pytestmark = pytest.mark.django_db


@pytest.fixture(autouse=True)
def media_root(settings) -> None:  # type: ignore[no-untyped-def]
    settings.MEDIA_ROOT = "/tmp/biahflow-test-media"


@pytest.fixture
def api() -> APIClient:
    client = APIClient()
    client.force_authenticate(UserFactory(role=User.Role.ADMIN))
    return client


def _documento() -> Document:
    return Document.objects.create(
        original_name="proposta.pdf",
        file=SimpleUploadedFile("proposta.pdf", b"conteudo original", content_type="application/pdf"),
        uploaded_by=UserFactory(),
        project=ProjectFactory(),
    )


def test_documento_recusa_put_e_patch_na_v1(api: APIClient) -> None:
    documento = _documento()

    patch_ = api.patch(reverse("document-detail", args=[documento.pk]), {"kind": "contract"}, format="json")
    put = api.put(
        reverse("document-detail", args=[documento.pk]),
        {"project": documento.project_id, "kind": "contract"},
        format="json",
    )

    assert patch_.status_code == 405, patch_.data
    assert put.status_code == 405, put.data
    documento.refresh_from_db()
    assert documento.original_name == "proposta.pdf"


def test_documento_recusa_put_e_patch_na_v2(api: APIClient) -> None:
    documento = _documento()

    patch_ = api.patch(
        reverse("v2-document-detail", args=[documento.pk]), {"kind": "contract"}, format="json"
    )
    put = api.put(
        reverse("v2-document-detail", args=[documento.pk]),
        {"project": documento.project_id, "kind": "contract"},
        format="json",
    )

    assert patch_.status_code == 405, patch_.data
    assert put.status_code == 405, put.data
