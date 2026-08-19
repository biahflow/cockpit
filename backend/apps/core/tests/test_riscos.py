"""Risk Register do projeto (FDD 034, ADR 0030).

O recurso é `risco` — o registro **declarado**, que uma pessoa escreve. Não confundir com `risk`,
a avaliação **calculada** de `risk.py`: são dois recursos com nomes vizinhos e políticas
diferentes, e um teste que os trocasse passaria por engano.
"""

import pytest
from django.urls import reverse
from rest_framework.test import APIClient

from apps.core.models import Risco, User

from .factories import ProjectFactory, ProjectMemberFactory, UserFactory


@pytest.fixture
def client() -> APIClient:
    return APIClient()


def _payload(project_id: int, **overrides: object) -> dict:
    base: dict = {
        "project": project_id,
        "title": "Fornecedor de dados pode atrasar a carga",
        "description": "A extração depende de um ERP de terceiro.",
        "probability": Risco.Probability.HIGH,
        "impact": Risco.Impact.HIGH,
        "mitigation": "Negociar janela alternativa com o time de TI do cliente.",
    }
    base.update(overrides)
    return base


@pytest.mark.django_db
def test_delivery_cria_le_edita_e_arquiva_risco_do_proprio_projeto(client: APIClient) -> None:
    delivery = UserFactory(role=User.Role.DELIVERY)
    project = ProjectFactory()
    ProjectMemberFactory(project=project, user=delivery)
    client.force_authenticate(delivery)

    created = client.post(reverse("risco-list"), _payload(project.id), format="json")
    assert created.status_code == 201
    # O dono sai da sessão, não do corpo: quem registra o risco é quem o viu.
    assert created.data["owner"] == delivery.id
    assert created.data["status"] == Risco.Status.OPEN
    risco_id = created.data["id"]

    listed = client.get(reverse("risco-list"), {"project": project.id})
    assert listed.status_code == 200
    assert [item["id"] for item in listed.data] == [risco_id]

    updated = client.patch(
        reverse("risco-detail", args=[risco_id]),
        {"mitigation": "Carga manual como plano B."},
        format="json",
    )
    assert updated.status_code == 200
    assert updated.data["mitigation"] == "Carga manual como plano B."

    archived = client.delete(reverse("risco-detail", args=[risco_id]))
    assert archived.status_code == 204
    assert Risco.objects.get(pk=risco_id).archived_at is not None
    assert risco_id not in [item["id"] for item in client.get(reverse("risco-list")).data]

    restored = client.post(reverse("risco-unarchive", args=[risco_id]))
    assert restored.status_code == 200
    assert risco_id in [item["id"] for item in client.get(reverse("risco-list")).data]


@pytest.mark.django_db
def test_delivery_nao_alcanca_risco_de_projeto_alheio(client: APIClient) -> None:
    """As duas metades da fronteira: não lê o risco alheio e não cria risco lá dentro."""
    delivery = UserFactory(role=User.Role.DELIVERY)
    meu = ProjectFactory()
    ProjectMemberFactory(project=meu, user=delivery)
    alheio = ProjectFactory(name="Projeto alheio")
    risco_alheio = Risco.objects.create(project=alheio, title="Segredo do projeto alheio")
    client.force_authenticate(delivery)

    listed = client.get(reverse("risco-list"))
    detalhe = client.get(reverse("risco-detail", args=[risco_alheio.id]))
    criacao = client.post(reverse("risco-list"), _payload(alheio.id), format="json")

    assert [item["id"] for item in listed.data] == []
    assert detalhe.status_code == 404  # fora da queryset: nem existe, do ponto de vista dela
    assert criacao.status_code == 403  # criar lá dentro seria virar dona do que não é sua
    assert not Risco.objects.filter(project=alheio, title__startswith="Fornecedor").exists()


@pytest.mark.django_db
def test_delivery_nao_move_risco_proprio_para_projeto_alheio(client: APIClient) -> None:
    delivery = UserFactory(role=User.Role.DELIVERY)
    meu = ProjectFactory()
    ProjectMemberFactory(project=meu, user=delivery)
    alheio = ProjectFactory()
    risco = Risco.objects.create(project=meu, title="Risco meu")
    client.force_authenticate(delivery)

    response = client.patch(
        reverse("risco-detail", args=[risco.id]), {"project": alheio.id}, format="json"
    )

    assert response.status_code == 403
    risco.refresh_from_db()
    assert risco.project_id == meu.id


@pytest.mark.django_db
def test_vendas_nao_alcanca_o_registro_de_riscos(client: APIClient) -> None:
    """Fechado pelo deny-by-default, como `pendencia`: risco é linguagem de entrega."""
    sales = UserFactory(role=User.Role.SALES)
    project = ProjectFactory()
    risco = Risco.objects.create(project=project, title="Risco de escopo")
    client.force_authenticate(sales)

    assert client.get(reverse("risco-list")).status_code == 403
    assert client.get(reverse("risco-detail", args=[risco.id])).status_code == 403
    assert client.post(reverse("risco-list"), _payload(project.id), format="json").status_code == 403


@pytest.mark.django_db
def test_admin_gerencia_risco_de_qualquer_projeto(client: APIClient) -> None:
    admin = UserFactory(role=User.Role.ADMIN)
    project = ProjectFactory()
    client.force_authenticate(admin)

    created = client.post(reverse("risco-list"), _payload(project.id), format="json")

    assert created.status_code == 201
    assert created.data["id"] in [item["id"] for item in client.get(reverse("risco-list")).data]


@pytest.mark.django_db
def test_resolved_at_carimba_no_encerramento_e_some_na_reabertura(client: APIClient) -> None:
    admin = UserFactory(role=User.Role.ADMIN)
    project = ProjectFactory()
    client.force_authenticate(admin)
    risco_id = client.post(reverse("risco-list"), _payload(project.id), format="json").data["id"]
    url = reverse("risco-detail", args=[risco_id])

    mitigado = client.patch(url, {"status": Risco.Status.MITIGATED}, format="json")
    assert mitigado.data["resolved_at"] is not None

    reaberto = client.patch(url, {"status": Risco.Status.OPEN}, format="json")
    assert reaberto.data["resolved_at"] is None

    aceito = client.patch(url, {"status": Risco.Status.ACCEPTED}, format="json")
    assert aceito.data["resolved_at"] is not None


@pytest.mark.django_db
def test_risco_materializado_nao_ganha_carimbo_de_resolvido() -> None:
    """Materializar não é resolver: o risco aconteceu, e "resolvido em" mentiria sobre isso."""
    project = ProjectFactory()
    risco = Risco.objects.create(
        project=project, title="Chave de API expira", status=Risco.Status.MITIGATED
    )
    assert risco.resolved_at is not None

    risco.status = Risco.Status.MATERIALIZED
    risco.save()

    assert risco.resolved_at is None


@pytest.mark.django_db
def test_filtro_por_status_separa_aberto_de_encerrado(client: APIClient) -> None:
    admin = UserFactory(role=User.Role.ADMIN)
    project = ProjectFactory()
    aberto = Risco.objects.create(project=project, title="Aberto")
    Risco.objects.create(project=project, title="Mitigado", status=Risco.Status.MITIGATED)
    client.force_authenticate(admin)

    abertos = client.get(reverse("risco-list"), {"status": Risco.Status.OPEN})

    assert abertos.status_code == 200
    assert [item["id"] for item in abertos.data] == [aberto.id]


@pytest.mark.django_db
def test_dono_e_carimbo_nao_entram_pelo_corpo(client: APIClient) -> None:
    admin = UserFactory(role=User.Role.ADMIN)
    outro = UserFactory(role=User.Role.DELIVERY)
    project = ProjectFactory()
    client.force_authenticate(admin)

    created = client.post(
        reverse("risco-list"),
        _payload(project.id, owner=outro.id, resolved_at="2020-01-01T00:00:00Z"),
        format="json",
    )

    assert created.status_code == 201
    assert created.data["owner"] == admin.id
    assert created.data["resolved_at"] is None
