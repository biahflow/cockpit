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

from apps.core import cobranca, health, risk
from apps.core.models import (
    Activity,
    Meeting,
    Milestone,
    Pendencia,
    Project,
    Task,
    User,
    WorkItem,
)
from apps.core.tests.factories import AccountFactory, ProjectFactory, UserFactory

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
        account = AccountFactory()
        for _ in range(2):
            project = ProjectFactory(engagement__account=account, due_date=ontem)
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
    projects.append(ProjectFactory(engagement__account=AccountFactory()))

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


def test_overview_de_uma_conta_nao_cresce_com_os_projetos(api: APIClient) -> None:
    """O detalhe usa um queryset próprio; o orçamento da lista não protege este caminho.

    `assess_projects_health` lê `project.engagement.account_id` duas vezes por projeto. Filtrar
    por `engagement__account` faz JOIN para o predicado, mas não preenche a relação no objeto;
    sem `select_related`, cada projeto acrescenta uma query invisível ao gate da lista.
    """
    account = AccountFactory()
    for _ in range(2):
        ProjectFactory(engagement__account=account)
    url = f"/api/v1/clients/{account.pk}/overview/"
    baseline = count_queries(api, url)

    for _ in range(8):
        ProjectFactory(engagement__account=account)

    assert count_queries(api, url) == baseline


def test_entrega_critica_isolada_nao_cresce_com_os_projetos() -> None:
    """O painel usa contexto em lote; chamadas isoladas também precisam custo constante."""
    account = AccountFactory()
    for _ in range(2):
        ProjectFactory(engagement__account=account)
    with CaptureQueriesContext(connection) as capturadas:
        cobranca.entrega_critica(account)
    baseline = len(capturadas.captured_queries)

    for _ in range(8):
        ProjectFactory(engagement__account=account)
    with CaptureQueriesContext(connection) as capturadas:
        cobranca.entrega_critica(account)

    assert len(capturadas.captured_queries) == baseline


# --- O painel de cobrança (FDD 036) -------------------------------------------------------------
#
# Fora da lista `AGGREGATES` de propósito, e não por esquecimento: o `seed` daquele bloco não cria
# fatura nenhuma, então o painel responderia vazio e a constância seria provada sobre lista vazia —
# o teste mais tranquilizador e mais inútil disponível. Dar faturas ao `seed` compartilhado, por sua
# vez, mudaria a base das outras cinco rotas por uma razão que não é delas. Semente própria, então.


def seed_cobranca(clients: int) -> None:
    """Semeia a forma que o painel percorre, com **todas** as dimensões pré-carregadas ocupadas.

    Cada uma existe porque uma dimensão vazia não exercita a pré-carga dela: sem suspensão, um
    `suspensao_ativa` por fatura passaria despercebido; sem fatura paga, o total recebido; sem
    contato gasto, o teto e a idempotência. É o mesmo motivo de o `seed` de cima dar filhos a cada
    projeto.

    As duas últimas entraram com a FDD 038 e pela mesma razão: **dois** projetos ativos por cliente
    (um deles crítico, para a guarda de entrega ter o que percorrer e o "pior nível do cliente"
    precisar escolher) e uma resposta de cobrança classificada e não registrada, que é o sinal
    pendente da linha. Sem elas, a constância seria provada sobre dimensão vazia — o teste mais
    tranquilizador e mais inútil disponível.
    """
    from apps.core.models import (
        Activity,
        CobrancaContato,
        CobrancaSuspensao,
        Contact,
        Invoice,
        Meeting,
        Pendencia,
    )
    from apps.core.tests.factories import ActivityFactory, InvoiceFactory

    hoje = timezone.localdate()
    for _ in range(clients):
        account = AccountFactory()
        project = ProjectFactory(engagement__account=account, due_date=hoje - timedelta(days=1))
        Milestone.objects.create(
            project=project, title="Marco", due_date=hoje - timedelta(days=1), owner=project.owner
        )
        # O segundo projeto, em estado crítico: é ele que troca a escada para `relacao_tensa` e
        # obriga o painel a escolher o pior nível entre os dois.
        critico = ProjectFactory(engagement__account=account, due_date=hoje - timedelta(days=1))
        for indice in range(4):
            Milestone.objects.create(
                project=critico, title=f"Marco {indice}", due_date=hoje - timedelta(days=1),
                owner=critico.owner,
            )
        for indice in range(2):
            Meeting.objects.create(
                project=critico, title=f"Reunião {indice}", date=hoje - timedelta(days=1),
                status=Meeting.Status.SCHEDULED,
            )
        Pendencia.objects.create(
            project=critico, title="Decisão travada", status=Pendencia.Status.OPEN,
            party=WorkItem.Party.CLIENT,
        )
        # A resposta classificada e ainda não registrada: o atalho da linha.
        ActivityFactory(
            account=account, dunning_signal=Activity.DunningSignal.DISSATISFIED,
            happened_on=hoje - timedelta(days=2),
        )
        Contact.objects.create(
            account=account, first_name="Financeiro", email="fin@cliente.test",
            receives_billing=True,
        )
        sequencial = Invoice.objects.count()
        atrasada = InvoiceFactory(
            account=account, project=project, status=Invoice.Status.OVERDUE,
            number=f"2026-{sequencial + 1:05d}", due_date=hoje - timedelta(days=12),
        )
        InvoiceFactory(
            account=account, project=project, status=Invoice.Status.ISSUED,
            number=f"2026-{sequencial + 2:05d}", due_date=hoje - timedelta(days=3),
        )
        InvoiceFactory(
            account=account, status=Invoice.Status.PAID, number=f"2026-{sequencial + 3:05d}",
            due_date=hoje - timedelta(days=200),
            paid_at=timezone.now() - timedelta(days=190),
        )
        CobrancaContato.objects.create(
            invoice=atrasada, account=account, degrau="lembrete",
            canal=CobrancaContato.Canal.EMAIL, sent_on=hoje - timedelta(days=30),
            subject="Fatura em aberto", body="...",
        )
        CobrancaSuspensao.objects.create(
            invoice=atrasada, owner=account.owner, until=hoje - timedelta(days=1),
            reason="Suspensão vencida, para a régua ter voltado sozinha.",
        )


def test_o_painel_de_cobranca_nao_cresce_com_a_base(api: APIClient) -> None:
    """`avaliar` faz quatro perguntas ao banco por fatura — suspensão, reincidência, degrau gasto e
    teto —, e o painel é um laço sobre faturas: sem pré-carga são quatro N+1 simultâneos.

    A asserção é comparativa pelo mesmo motivo do bloco de cima: sobrevive a refatoração que mude o
    número absoluto e continua reprovando exatamente a inclinação.
    """
    seed_cobranca(clients=3)
    baseline = count_queries(api, "/api/v1/cobranca/painel/")

    seed_cobranca(clients=9)  # 4× a base: 3 → 12 clientes, 6 → 24 faturas cobráveis
    from apps.core.models import Invoice

    assert Invoice.objects.filter(status__in=("issued", "overdue")).count() == 24
    # A base cresceu **nas dimensões novas** também: sem isto, a constância continuaria sendo
    # provada sobre a parte antiga do painel.
    assert Project.objects.count() == 24
    assert Activity.objects.exclude(dunning_signal="").count() == 12

    assert count_queries(api, "/api/v1/cobranca/painel/") == baseline, (
        "/api/v1/cobranca/painel/ emitiu mais queries com 4× a base — o custo cresce com o "
        "número de faturas (N+1). Carregue em lote com `cobranca.contexto_do_painel`."
    )
