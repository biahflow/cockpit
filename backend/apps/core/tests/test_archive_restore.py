"""Arquivar e restaurar pela API (FDD 025).

Antes disto, `DELETE` arquivava e não havia volta pela interface: `archived_at` não aparece em
serializer nenhum e o registro sumia de toda listagem. Desfazer exigia Django admin ou shell — o
que faz de um clique acidental um problema de infraestrutura.
"""

import pytest
from django.urls import reverse
from rest_framework.test import APIClient

from apps.core.models import Lead, User

from .factories import AccountFactory, ProjectFactory, ServiceFactory, UserFactory


@pytest.fixture
def admin_client() -> APIClient:
    client = APIClient()
    client.force_authenticate(UserFactory(role=User.Role.ADMIN))
    return client


@pytest.mark.django_db
def test_arquivado_sai_da_lista_ativa_e_aparece_com_archived(admin_client: APIClient) -> None:
    service = ServiceFactory(name="Consultoria avulsa")

    assert admin_client.delete(reverse("service-detail", args=[service.pk])).status_code == 204

    ativos = admin_client.get(reverse("service-list")).data
    assert service.pk not in [item["id"] for item in ativos]

    arquivados = admin_client.get(reverse("service-list"), {"archived": "1"}).data
    assert service.pk in [item["id"] for item in arquivados]


@pytest.mark.django_db
def test_unarchive_devolve_o_registro_a_lista_ativa(admin_client: APIClient) -> None:
    lead = Lead.objects.create(name="Quem chegou pelo site", email="lead@example.test")
    admin_client.delete(reverse("lead-detail", args=[lead.pk]))
    lead.refresh_from_db()
    assert lead.is_archived

    resposta = admin_client.post(reverse("lead-unarchive", args=[lead.pk]))

    assert resposta.status_code == 200
    assert resposta.data["id"] == lead.pk
    lead.refresh_from_db()
    assert lead.archived_at is None
    assert lead.pk in [item["id"] for item in admin_client.get(reverse("lead-list")).data]


@pytest.mark.django_db
def test_unarchive_encontra_o_arquivado_apesar_do_filtro_padrao(admin_client: APIClient) -> None:
    """O objeto a restaurar é justamente o que o `get_queryset` padrão esconde.

    Resolver pelo queryset filtrado devolveria 404 em todo pedido de restauração — a ação sempre
    procura o que já saiu da lista ativa.
    """
    cliente = AccountFactory()
    admin_client.delete(reverse("client-detail", args=[cliente.pk]))

    assert admin_client.get(reverse("client-detail", args=[cliente.pk])).status_code == 404
    assert admin_client.post(reverse("client-unarchive", args=[cliente.pk])).status_code == 200


@pytest.mark.django_db
def test_unarchive_de_id_inexistente_e_404(admin_client: APIClient) -> None:
    assert admin_client.post(reverse("project-unarchive", args=[999999])).status_code == 404


@pytest.mark.django_db
def test_unarchive_respeita_o_recorte_de_projeto_da_entrega() -> None:
    """Entrega não restaura projeto de que não participa — a mesma fronteira do `destroy`."""
    project = ProjectFactory()
    project.archive()
    client = APIClient()
    client.force_authenticate(UserFactory(role=User.Role.DELIVERY))

    assert client.post(reverse("project-unarchive", args=[project.pk])).status_code == 403
