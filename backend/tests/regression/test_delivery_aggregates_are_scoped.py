"""Regressão: os agregados também respeitam a equipe (RFC 0003, FDD 018).

Esconder o projeto não adianta se o painel conta os projetos de todo mundo, se `/risk/` lista
o nome e o diagnóstico de cada um, ou se a visão por cliente soma ROI de projeto alheio. Estes
caminhos não passam por queryset de viewset — cada um precisou ser estreitado à mão, e é por
isso que cada um tem teste próprio.
"""

import pytest
from django.urls import reverse
from django.utils import timezone
from rest_framework.test import APIClient

from apps.core.models import Task, User
from apps.core.tests.factories import (
    ClientFactory,
    ProjectFactory,
    ProjectMemberFactory,
    UserFactory,
)

pytestmark = pytest.mark.django_db


@pytest.fixture
def delivery() -> User:
    return UserFactory(role=User.Role.DELIVERY)


@pytest.fixture
def api(delivery: User) -> APIClient:
    client = APIClient()
    client.force_authenticate(delivery)
    return client


@pytest.fixture
def mine(delivery: User):  # type: ignore[no-untyped-def]
    project = ProjectFactory(name="Projeto da equipe")
    ProjectMemberFactory(project=project, user=delivery)
    return project


@pytest.fixture
def theirs():  # type: ignore[no-untyped-def]
    return ProjectFactory(name="Projeto alheio")


def test_risk_only_lists_my_projects(api: APIClient, mine, theirs) -> None:  # type: ignore[no-untyped-def]
    names = {row["name"] for row in api.get(reverse("risk")).data["projects"]}

    assert names == {mine.name}


def test_health_only_lists_my_projects(api: APIClient, mine, theirs) -> None:  # type: ignore[no-untyped-def]
    names = {row["name"] for row in api.get(reverse("health")).data["projects"]}

    assert names == {mine.name}


def test_dashboard_counts_and_tasks_are_scoped(api: APIClient, delivery, mine, theirs) -> None:  # type: ignore[no-untyped-def]
    yesterday = timezone.localdate() - timezone.timedelta(days=1)
    Task.objects.create(project=mine, title="Minha tarefa", owner=delivery, due_date=yesterday)
    Task.objects.create(
        project=theirs, title="Tarefa alheia", owner=theirs.owner, due_date=yesterday
    )

    data = api.get(reverse("dashboard")).data

    assert data["active_projects"] == 1
    titles = {task["title"] for task in data["upcoming_tasks"]}
    assert "Tarefa alheia" not in titles


def test_dashboard_hides_the_commercial_pipeline(api: APIClient, mine) -> None:  # type: ignore[no-untyped-def]
    """Valor de pipeline não pode vazar por canal lateral: as não-ganhas já são escondidas."""
    assert api.get(reverse("dashboard")).data["pipeline"] == []


def test_client_list_only_shows_clients_i_work_for(api: APIClient, mine, theirs) -> None:  # type: ignore[no-untyped-def]
    listed = {row["id"] for row in api.get(reverse("client-list")).data}

    assert listed == {mine.client_id}


def test_client_overview_aggregates_only_my_projects(api: APIClient, delivery) -> None:  # type: ignore[no-untyped-def]
    """O agregado é por cliente: estreitar a lista de clientes não bastaria."""
    shared = ClientFactory()
    mine = ProjectFactory(client=shared, actual_value=100, cost=40)
    ProjectMemberFactory(project=mine, user=delivery)
    ProjectFactory(client=shared, actual_value=900, cost=300)

    rows = api.get(reverse("client-overview")).data["clients"]

    assert len(rows) == 1
    assert rows[0]["roi"]["revenue"] == mine.actual_value
    assert rows[0]["roi"]["cost"] == mine.cost


def test_delivery_agent_context_only_mentions_my_projects(delivery, mine, theirs) -> None:  # type: ignore[no-untyped-def]
    from apps.core import agents

    context = agents.build_delivery_context(delivery)

    assert mine.name in context
    assert theirs.name not in context


def test_delivery_agent_context_does_not_leak_items_from_other_projects(delivery, mine, theirs) -> None:  # type: ignore[no-untyped-def]
    """O contexto passou a listar **quais** itens estão atrasados, e não só o escore de risco.

    Com isso o vazamento possível deixou de ser só o nome do projeto e passou a ser o título do
    item — que é onde mora o conteúdo. O teste irmão acima já travava o nome; este trava o item.
    """
    from datetime import timedelta

    from apps.core import agents

    vencido = timezone.localdate() - timedelta(days=3)
    Task.objects.create(project=mine, title="Consolidar entrevistas", owner=delivery, due_date=vencido)
    Task.objects.create(project=theirs, title="Segredo do projeto alheio", owner=UserFactory(), due_date=vencido)

    context = agents.build_delivery_context(delivery)

    assert "Consolidar entrevistas" in context
    assert "Segredo do projeto alheio" not in context


def test_delivery_agent_context_does_not_leak_risks_from_other_projects(delivery, mine, theirs) -> None:  # type: ignore[no-untyped-def]
    """Terceiro conteúdo no mesmo contexto, terceiro teste (FDD 034).

    O Risk Register é texto escrito por gente sobre o que pode dar errado num cliente — o bloco
    mais sensível dos três que este contexto carrega. Só os abertos entram, e só os dos projetos
    de que a pessoa participa.
    """
    from apps.core import agents
    from apps.core.models import Risco

    Risco.objects.create(project=mine, title="Dependência do ERP do cliente")
    Risco.objects.create(project=mine, title="Risco já mitigado", status=Risco.Status.MITIGATED)
    Risco.objects.create(project=theirs, title="Risco secreto do projeto alheio")

    context = agents.build_delivery_context(delivery)

    assert "Dependência do ERP do cliente" in context
    assert "Risco secreto do projeto alheio" not in context
    assert "Risco já mitigado" not in context  # encerrado não pede ação


def test_analytics_and_recommendations_stay_forbidden(api: APIClient) -> None:
    """Trava contra afrouxamento futuro: os dois varrem tudo e não foram parametrizados."""
    assert api.get(reverse("analytics")).status_code == 403
    assert api.get(reverse("recommendations")).status_code == 403


def test_admin_still_sees_every_project_in_the_aggregates(mine, theirs) -> None:  # type: ignore[no-untyped-def]
    admin = APIClient()
    admin.force_authenticate(UserFactory(role=User.Role.ADMIN))

    assert len(admin.get(reverse("risk")).data["projects"]) == 2
    assert admin.get(reverse("dashboard")).data["active_projects"] == 2
