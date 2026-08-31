import pytest
from django.urls import reverse
from django.utils import timezone
from rest_framework.test import APIClient

from apps.core.models import Decisao, Meeting, Pendencia, User

from .factories import ProjectFactory, ProjectMemberFactory, UserFactory


@pytest.mark.django_db
def test_delivery_creates_and_lists_meetings_filtered_by_project() -> None:
    delivery = UserFactory(role=User.Role.DELIVERY)
    project = ProjectFactory()
    ProjectMemberFactory(project=project, user=delivery)
    other = ProjectFactory()
    Meeting.objects.create(project=other, title="Outra", date=timezone.localdate())
    client = APIClient()
    client.force_authenticate(delivery)

    created = client.post(
        reverse("meeting-list"),
        {"project": project.pk, "title": "Kickoff", "date": str(timezone.localdate())},
        format="json",
    )
    assert created.status_code == 201

    listed = client.get(reverse("meeting-list"), {"project": project.pk}).json()
    rows = listed if isinstance(listed, list) else listed["results"]
    assert [row["title"] for row in rows] == ["Kickoff"]  # não traz a reunião do outro projeto


@pytest.mark.django_db
def test_sales_cannot_manage_pendencias() -> None:
    sales = UserFactory(role=User.Role.SALES)
    project = ProjectFactory()
    client = APIClient()
    client.force_authenticate(sales)
    resp = client.post(
        reverse("pendencia-list"),
        {"project": project.pk, "title": "Aprovar escopo"},
        format="json",
    )
    assert resp.status_code == 403


@pytest.mark.django_db
def test_resolving_pendencia_sets_resolved_at() -> None:
    delivery = UserFactory(role=User.Role.DELIVERY)
    project = ProjectFactory()
    ProjectMemberFactory(project=project, user=delivery)
    pendencia = Pendencia.objects.create(project=project, title="Aprovar escopo", owner=delivery)
    assert pendencia.resolved_at is None
    client = APIClient()
    client.force_authenticate(delivery)

    resp = client.patch(
        reverse("pendencia-detail", args=[pendencia.pk]),
        {"status": "resolved"},
        format="json",
    )
    assert resp.status_code == 200
    pendencia.refresh_from_db()
    assert pendencia.status == Pendencia.Status.RESOLVED
    assert pendencia.resolved_at is not None


@pytest.mark.django_db
def test_pendencia_owner_is_set_to_request_user() -> None:
    delivery = UserFactory(role=User.Role.DELIVERY)
    project = ProjectFactory()
    ProjectMemberFactory(project=project, user=delivery)
    client = APIClient()
    client.force_authenticate(delivery)
    resp = client.post(
        reverse("pendencia-list"),
        {"project": project.pk, "title": "Definir alçada", "party": "client"},
        format="json",
    )
    assert resp.status_code == 201
    assert Pendencia.objects.get(pk=resp.json()["id"]).owner_id == delivery.pk


# --- Decisões (FDD 032) -------------------------------------------------------


@pytest.mark.django_db
def test_sales_cannot_manage_decisoes() -> None:
    """Recurso novo nasce fechado, e `decisao` só abre porque entrou nas duas listas.

    O caso existe porque o mecanismo é silencioso nos dois sentidos: esquecer `permissions.py` dá
    403 em tudo, e acrescentar ao set sem acrescentar ao `PROJECT_OF` daria acesso a projeto alheio.
    """
    sales = UserFactory(role=User.Role.SALES)
    project = ProjectFactory()
    client = APIClient()
    client.force_authenticate(sales)
    resp = client.post(
        reverse("decisao-list"),
        {"project": project.pk, "title": "Adotar fila gerenciada"},
        format="json",
    )
    assert resp.status_code == 403


@pytest.mark.django_db
def test_delivery_only_sees_decisoes_of_their_own_projects() -> None:
    delivery = UserFactory(role=User.Role.DELIVERY)
    project = ProjectFactory()
    ProjectMemberFactory(project=project, user=delivery)
    Decisao.objects.create(project=ProjectFactory(), title="De outro projeto")
    Decisao.objects.create(project=project, title="Adotar fila gerenciada")

    client = APIClient()
    client.force_authenticate(delivery)
    listed = client.get(reverse("decisao-list"), {"project": project.pk}).json()
    rows = listed if isinstance(listed, list) else listed["results"]
    assert [row["title"] for row in rows] == ["Adotar fila gerenciada"]


@pytest.mark.django_db
def test_publishing_a_decisao_stamps_and_republishing_never_moves_the_stamp() -> None:
    """O carimbo não se apaga — a divergência deliberada em relação à `Pendencia`.

    O `save()` dela **limpa** `resolved_at` ao reabrir. Copiar isso aqui faria despublicar uma
    decisão apagar a data em que ela passou a valer, que é fato histórico e não estado corrente.
    """
    delivery = UserFactory(role=User.Role.DELIVERY)
    project = ProjectFactory()
    ProjectMemberFactory(project=project, user=delivery)
    project_phase = project.phases.first()
    assert project_phase is not None
    decisao = Decisao.objects.create(
        project=project, project_phase=project_phase, title="Adotar fila gerenciada"
    )
    assert decisao.published_at is None

    client = APIClient()
    client.force_authenticate(delivery)
    resp = client.patch(
        reverse("decisao-detail", args=[decisao.pk]), {"status": "published"}, format="json"
    )
    assert resp.status_code == 200
    decisao.refresh_from_db()
    primeiro = decisao.published_at
    assert primeiro is not None

    # Volta para rascunho: o carimbo **fica**.
    client.patch(reverse("decisao-detail", args=[decisao.pk]), {"status": "draft"}, format="json")
    decisao.refresh_from_db()
    assert decisao.published_at == primeiro

    # E republicar não move o carimbo para a data de hoje.
    client.patch(
        reverse("decisao-detail", args=[decisao.pk]), {"status": "published"}, format="json"
    )
    decisao.refresh_from_db()
    assert decisao.published_at == primeiro


@pytest.mark.django_db
def test_publishing_requires_an_explicit_project_phase() -> None:
    delivery = UserFactory(role=User.Role.DELIVERY)
    project = ProjectFactory()
    ProjectMemberFactory(project=project, user=delivery)
    decisao = Decisao.objects.create(project=project, title="Adotar fila gerenciada")
    client = APIClient()
    client.force_authenticate(delivery)

    resp = client.patch(
        reverse("decisao-detail", args=[decisao.pk]), {"status": "published"}, format="json"
    )

    assert resp.status_code == 400
    assert resp.json()["project_phase"] == [
        "Escolha uma fase da jornada antes de publicar a decisão."
    ]


@pytest.mark.django_db
def test_decision_phase_must_belong_to_the_same_project() -> None:
    delivery = UserFactory(role=User.Role.DELIVERY)
    project = ProjectFactory()
    other = ProjectFactory()
    ProjectMemberFactory(project=project, user=delivery)
    other_phase = other.phases.first()
    assert other_phase is not None
    client = APIClient()
    client.force_authenticate(delivery)

    resp = client.post(
        reverse("decisao-list"),
        {
            "project": project.pk,
            "project_phase": other_phase.pk,
            "title": "Adotar fila gerenciada",
        },
        format="json",
    )

    assert resp.status_code == 400
    assert resp.json()["project_phase"] == [
        "A fase deve pertencer ao mesmo projeto da decisão."
    ]
