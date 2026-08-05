"""Regressão: o custo dos agregadores não cresce com a base (FDD 022, ADR 0014).

O gate de carga que roda a cada PR é este — não um cronômetro. Latência em runner
compartilhado do GitHub oscila com o vizinho de máquina; contagem de query, não. E o que
derruba um agregador em produção não é a constante, é a **inclinação**: `/clients/overview/`
com 12 clientes emitindo 4× as queries de 12/3 clientes significa que ele emitirá 400× com
1200 clientes, e nenhum teste de latência sobre a base de desenvolvimento veria isso.

Por isso a asserção é comparativa e não um número mágico: mede-se a mesma rota com duas
bases de tamanhos diferentes e cobra-se que a contagem **não mude**. O teste se auto-calibra,
sobrevive a refatoração que troque o número absoluto de queries e continua reprovando
exatamente o que importa.

`/analytics/` está na lista de propósito. Ele é o mais pesado em SQL de todos — mas laça
sobre `Service.Tier` e `Artifact.Kind`, que são **enums de tamanho fixo**, não sobre dados.
Ele é caro e constante, e a diferença entre "caro" e "cresce com a base" é justamente o que
este arquivo existe para preservar.
"""

from datetime import timedelta

import pytest
from django.db import connection
from django.test.utils import CaptureQueriesContext
from django.utils import timezone
from rest_framework.test import APIClient

from apps.core import health, risk
from apps.core.models import (
    Meeting,
    Milestone,
    Pendencia,
    Project,
    Task,
    User,
    WorkItem,
)
from apps.core.tests.factories import ClientFactory, ProjectFactory, UserFactory

pytestmark = pytest.mark.django_db

# As rotas que agregam sobre a base inteira, sem paginação. São exatamente as que a FDD 018
# teve de estreitar à mão por não passarem por queryset de viewset.
AGGREGATES = [
    "/api/v1/clients/overview/",
    "/api/v1/risk/",
    "/api/v1/health/",
    "/api/v1/analytics/",
    "/api/v1/dashboard/",
]


@pytest.fixture
def api() -> APIClient:
    client = APIClient()
    client.force_authenticate(UserFactory(role=User.Role.ADMIN))
    return client


def seed(clients: int) -> None:
    """Semeia uma base com a forma que os agregadores percorrem.

    Cada cliente ganha dois projetos e cada projeto ganha marco, tarefa, reunião e pendência —
    porque um projeto sem filhos não exercita o laço de `assess_project_health`, e uma base de
    projetos vazios passaria em qualquer orçamento de query sem provar nada.
    """
    ontem = timezone.localdate() - timedelta(days=1)
    for _ in range(clients):
        client = ClientFactory()
        for _ in range(2):
            project = ProjectFactory(client=client, due_date=ontem)
            dono = project.owner
            Milestone.objects.create(project=project, title="Marco", due_date=ontem, owner=dono)
            Task.objects.create(project=project, title="Tarefa", due_date=ontem, owner=dono)
            Meeting.objects.create(
                project=project, title="Reunião", date=ontem,
                status=Meeting.Status.SCHEDULED,
            )
            Pendencia.objects.create(
                project=project, title="Pendência",
                status=Pendencia.Status.OPEN, party=WorkItem.Party.CLIENT,
            )


def count_queries(api: APIClient, url: str) -> int:
    with CaptureQueriesContext(connection) as captured:
        response = api.get(url)
    assert response.status_code == 200, f"{url} respondeu {response.status_code}"
    return len(captured.captured_queries)


def test_avaliacao_em_lote_da_o_mesmo_resultado_da_individual() -> None:
    """O risco real de carregar em lote não é a query — é divergir do resultado antigo.

    `assess_projects`/`assess_projects_health` distribuem em memória o que as funções por
    projeto consultavam. Se o agrupamento errar um `project_id`, o portal passa a mostrar a
    saúde do projeto errado — e nenhum orçamento de query perceberia. Daí este teste comparar
    as duas formas item a item, com projetos de estados diferentes para que os escores não
    coincidam por acaso.
    """
    seed(clients=4)
    projects = list(Project.objects.order_by("id"))
    # Um projeto sem nenhum filho: o caso em que o lote precisa devolver lista vazia, e não
    # o dado do vizinho no dicionário.
    projects.append(ProjectFactory(client=ClientFactory()))

    assert risk.assess_projects(projects) == [risk.assess_project(p) for p in projects]
    assert health.assess_projects_health(projects) == [
        health.assess_project_health(p) for p in projects
    ]
    assert risk.assess_projects([]) == []
    assert health.assess_projects_health([]) == []


@pytest.mark.parametrize("url", AGGREGATES)
def test_agregador_nao_cresce_com_a_base(api: APIClient, url: str) -> None:
    seed(clients=3)
    baseline = count_queries(api, url)

    seed(clients=9)  # 4× a base: 3 → 12 clientes, 6 → 24 projetos
    assert Project.objects.count() == 24

    assert count_queries(api, url) == baseline, (
        f"{url} emitiu mais queries com 4× a base — o custo cresce com o número de "
        f"clientes/projetos (N+1). Carregue em lote em vez de consultar dentro do laço."
    )
