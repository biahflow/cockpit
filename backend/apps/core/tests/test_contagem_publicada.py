"""`published_count` — quanto do Discovery desta conta o cliente está vendo agora (issue `#114`).

Arquivar a conta **não** despublica o Discovery, e não deve: a ADR 0060 diz que só um ato humano
publica e só um ato humano despublica. O que faltava era o aviso, e o aviso precisa de um número.

Este arquivo cobra as duas coisas que o número tem de ser:

1. **o mesmo recorte de `portal.py`** — publicado e vivo, somando os cinco marcados. Contar o
   arquivado-mas-publicado mentiria, porque ele não atravessa o snapshot;
2. **a mesma resposta pelos dois caminhos** — `contagem_publicada` sobre o objeto e
   `anotacao_de_contagem_publicada` sobre o queryset são a mesma pergunta, e duas respostas
   divergentes é justamente o defeito que separá-las cria.

O custo tem teste próprio porque `AccountSerializer` serve listagem **e** detalhe: cinco `COUNT`
por linha seria N+1 no grid de contas, e é por isso que a anotação é subconsulta correlacionada e
não cinco `Count` com `JOIN`.
"""

from __future__ import annotations

import pytest
from django.db import connection
from django.test.utils import CaptureQueriesContext
from django.urls import reverse
from django.utils import timezone
from rest_framework.test import APIClient

from apps.core import publication
from apps.core.models import Account, User
from apps.core.tests.factories import (
    AccountFactory,
    EngagementFactory,
    EvidenceFactory,
    FindingFactory,
    ImprovementOpportunityFactory,
    PainPointFactory,
    ProcessFactory,
    ProjectFactory,
    ProjectMemberFactory,
    UserFactory,
)

pytestmark = pytest.mark.django_db


@pytest.fixture
def autor() -> User:
    return UserFactory(role=User.Role.ADMIN)


@pytest.fixture
def api(autor: User) -> APIClient:
    client = APIClient()
    client.force_authenticate(autor)
    return client


def _publica(obj, autor: User):  # type: ignore[no-untyped-def]
    """Carimba a marca direto, como os outros testes de publicação fazem: as actions recusariam
    de propósito alguns dos estados montados aqui (uma dor publicada sem achado embaixo), e o que
    está sob teste é a contagem, não a porta."""
    obj.published_at = timezone.now()
    obj.published_by = autor
    obj.save(update_fields=["published_at", "published_by", "updated_at"])
    return obj


def _anotado(conta: Account) -> int:
    return Account.objects.filter(pk=conta.pk).annotate(
        **publication.anotacao_de_contagem_publicada()
    ).values_list("published_count", flat=True)[0]


# --- O recorte: publicado **e** vivo -------------------------------------------------


def test_conta_so_o_publicado_e_vivo(autor: User) -> None:
    """Dois vivos publicados, um arquivado-mas-publicado e três não publicados → 2.

    O arquivado fica de fora porque `portal._processes` também o deixa: contá-lo diria ao operador
    que o cliente vê algo que o cliente não vê.
    """
    conta = AccountFactory()
    _publica(ProcessFactory(account=conta), autor)
    _publica(ProcessFactory(account=conta), autor)
    _publica(ProcessFactory(account=conta), autor).archive()
    for _ in range(3):
        ProcessFactory(account=conta)

    assert publication.contagem_publicada(conta) == 2
    assert _anotado(conta) == 2


def test_soma_os_cinco_modelos(autor: User) -> None:
    """Um publicado de cada um dos cinco marcados → 5. Se um sair da lista, este teste cai."""
    conta = AccountFactory()
    for fabrica in (
        ProcessFactory,
        EvidenceFactory,
        FindingFactory,
        PainPointFactory,
        ImprovementOpportunityFactory,
    ):
        _publica(fabrica(account=conta), autor)

    assert publication.contagem_publicada(conta) == 5
    assert _anotado(conta) == 5


def test_os_dois_caminhos_concordam(autor: User) -> None:
    """A função e a anotação são a mesma pergunta, e uma base torta é onde elas divergiriam.

    A conta vizinha existe de propósito: uma subconsulta mal correlacionada somaria o Discovery
    dela, e o número continuaria "plausível" sem nada ficar vermelho.
    """
    conta = AccountFactory()
    vizinha = AccountFactory()
    _publica(ProcessFactory(account=conta), autor)
    _publica(FindingFactory(account=conta), autor)
    _publica(FindingFactory(account=conta), autor)
    FindingFactory(account=conta)
    for _ in range(4):
        _publica(EvidenceFactory(account=vizinha), autor)

    assert publication.contagem_publicada(conta) == _anotado(conta) == 3
    assert publication.contagem_publicada(vizinha) == _anotado(vizinha) == 4


def test_conta_sem_nada_publicado_e_zero_e_nunca_none() -> None:
    """`0`, não `None`: é o `Coalesce` da anotação, e é o que a tela precisa para não escrever
    "null registros publicados"."""
    conta = AccountFactory()
    ProcessFactory(account=conta)

    assert publication.contagem_publicada(conta) == 0
    assert _anotado(conta) == 0


# --- A `/api/v1/` --------------------------------------------------------------------


def test_a_listagem_traz_published_count(api: APIClient, autor: User) -> None:
    conta = AccountFactory()
    _publica(ProcessFactory(account=conta), autor)
    _publica(PainPointFactory(account=conta), autor)

    resposta = api.get(reverse("client-list"))

    assert resposta.status_code == 200, resposta.data
    linha = next(item for item in resposta.data if item["id"] == conta.pk)
    assert linha["published_count"] == 2


def test_o_detalhe_traz_published_count(api: APIClient, autor: User) -> None:
    conta = AccountFactory()
    _publica(EvidenceFactory(account=conta), autor)

    resposta = api.get(reverse("client-detail", args=[conta.pk]))

    assert resposta.status_code == 200, resposta.data
    assert resposta.data["published_count"] == 1


def test_o_serializer_sem_anotacao_conta_do_mesmo_jeito(autor: User) -> None:
    """A resposta do `POST` serializa a instância criada, e não uma linha do queryset anotado.

    Sem o caminho de fallback isto seria `AttributeError` — 500 num caminho que hoje funciona.
    """
    from apps.core.serializers import AccountSerializer

    conta = AccountFactory()
    _publica(ProcessFactory(account=conta), autor)

    assert AccountSerializer(conta).data["published_count"] == 1


def test_published_count_e_read_only(api: APIClient, autor: User) -> None:
    """Campo derivado: o DRF o descarta na entrada, sem 400 de campo desconhecido — o mesmo
    comportamento afirmado para `published_at`/`published_by` nos cinco publicáveis."""
    conta = AccountFactory()
    _publica(ProcessFactory(account=conta), autor)

    resposta = api.patch(
        reverse("client-detail", args=[conta.pk]),
        {"published_count": 99, "legal_name": "ACME SA"},
        format="json",
    )

    assert resposta.status_code == 200, resposta.data
    assert resposta.data["published_count"] == 1
    conta.refresh_from_db()
    assert conta.legal_name == "ACME SA"


def test_entrega_com_escopo_ve_a_contagem_certa(autor: User) -> None:
    """O `.distinct()` de `get_queryset` é onde este tipo de anotação costuma quebrar.

    Dois projetos da mesma conta multiplicam a linha no `JOIN` do escopo; a subconsulta
    correlacionada é escalar e não participa dele, então o `distinct` colapsa as duplicatas sem
    dobrar o número — que é exatamente o que cinco `Count` com `JOIN` não conseguiriam.
    """
    conta = AccountFactory()
    mandato = EngagementFactory(account=conta)
    entrega = UserFactory(role=User.Role.DELIVERY)
    for _ in range(2):
        ProjectMemberFactory(project=ProjectFactory(engagement=mandato), user=entrega)
    _publica(ProcessFactory(account=conta), autor)
    _publica(FindingFactory(account=conta), autor)
    _publica(FindingFactory(account=conta), autor).archive()

    client = APIClient()
    client.force_authenticate(entrega)
    resposta = client.get(reverse("client-list"))

    assert resposta.status_code == 200, resposta.data
    assert [linha["id"] for linha in resposta.data] == [conta.pk]
    assert resposta.data[0]["published_count"] == 2


# --- O custo: constante na base, não por linha ---------------------------------------


def test_o_custo_da_listagem_nao_cresce_com_o_numero_de_contas(
    api: APIClient, autor: User
) -> None:
    """Mesma forma do `tests/regression/test_aggregate_query_budget.py`: a asserção é comparativa.

    Cinco `COUNT` por linha passariam com quatro contas e derrubariam o grid com quatrocentas, e
    nenhum número mágico veria isso — o que reprova é a **inclinação**.
    """
    def povoa(quantas: int) -> None:
        for _ in range(quantas):
            conta = AccountFactory()
            _publica(ProcessFactory(account=conta), autor)
            _publica(FindingFactory(account=conta), autor)

    povoa(2)
    with CaptureQueriesContext(connection) as base_pequena:
        pequena = api.get(reverse("client-list"))
    assert pequena.status_code == 200, pequena.data

    povoa(6)
    with CaptureQueriesContext(connection) as base_grande:
        grande = api.get(reverse("client-list"))
    assert grande.status_code == 200, grande.data

    assert len(grande.data) == 4 * len(pequena.data)
    assert len(base_grande.captured_queries) == len(base_pequena.captured_queries), (
        "o custo da listagem de contas passou a crescer com a base"
    )


def test_o_grid_de_contas_nao_paga_pela_contagem_que_nao_le(api: APIClient, autor: User) -> None:
    """`/clients/overview/` monta dicionário próprio e nunca toca no `AccountSerializer`.

    Ele compartilha o `get_queryset` com a listagem, então anotar sempre faria a tela mais
    carregada do produto rodar cinco `COUNT` correlacionados por linha que ninguém lê. A contagem
    de *queries* não mudaria — é uma subconsulta dentro do mesmo `SELECT` —, e é exatamente isso
    que tornaria o desperdício invisível: ele cresce com a carteira sem nada ficar vermelho. Por
    isso a asserção é sobre o **SQL emitido**, e não sobre quantas consultas saíram.
    """
    conta = AccountFactory()
    _publica(ProcessFactory(account=conta), autor)

    with CaptureQueriesContext(connection) as overview:
        resposta = api.get(reverse("client-overview"))
    assert resposta.status_code == 200, resposta.data
    assert not any("published_count" in q["sql"] for q in overview.captured_queries), (
        "o grid de contas voltou a computar a contagem publicada que ele não lê"
    )

    with CaptureQueriesContext(connection) as listagem:
        assert api.get(reverse("client-list")).status_code == 200
    assert any("published_count" in q["sql"] for q in listagem.captured_queries), (
        "a listagem parou de anotar a contagem, e o serializer caiu no ramo de cinco COUNT por linha"
    )
