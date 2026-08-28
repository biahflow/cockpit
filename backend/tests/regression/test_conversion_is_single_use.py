"""Regressão: uma oportunidade não pode criar dois projetos pelo botão "converter".

Até a ADR 0050 quem garantia isso era o banco — `Project.opportunity` era `OneToOneField`, e a
segunda conversão morria num `IntegrityError` que a view traduzia em 409. Essa cardinalidade caiu
porque também impedia o que a casa passou a vender: uma Transformation Partnership é recorrente e
origina vários projetos ao longo do mandato.

**A invariante não caiu junto — ela mudou de lugar**, e é isso que este arquivo protege. O que se
quer impedir nunca foi "dois projetos com a mesma origem" (isso agora é legítimo, e nasce por
`POST /projects/`); é o **duplo clique** criando projeto duplicado sem ninguém pedir. A garantia
virou explícita na action, em duas partes que se cobrem:

1. o guard, que recusa com 409 quando já existe projeto **vivo** com esta origem;
2. o `select_for_update()` na oportunidade dentro da transação, que serializa duas requisições
   simultâneas — sem ele, ambas leem "não há projeto" ao mesmo tempo e ambas criam.

Uma garantia que saiu do banco e virou código é uma garantia que só existe enquanto for testada.
"""

from datetime import timedelta
from unittest.mock import patch

import pytest
from django.db.models import QuerySet
from django.urls import reverse
from django.utils import timezone
from rest_framework.test import APIClient

from apps.core.models import Opportunity, PipelineStage, Project, User
from apps.core.tests.factories import OpportunityFactory, UserFactory


def _corpo(opportunity: Opportunity, sales: User, nome: str = "Projeto") -> dict:
    return {
        "client": opportunity.client_id, "name": nome, "owner": sales.id,
        "start_date": str(timezone.localdate()),
        "due_date": str(timezone.localdate() + timedelta(days=10)),
        "status": "planning",
    }


@pytest.mark.django_db
def test_second_conversion_returns_conflict_without_new_project():
    sales = UserFactory(role=User.Role.SALES)
    opportunity = OpportunityFactory(stage=PipelineStage.objects.get(kind="won"), owner=sales)
    client = APIClient()
    client.force_authenticate(sales)
    endpoint = reverse("opportunity-convert-to-project", args=[opportunity.id])

    assert client.post(endpoint, _corpo(opportunity, sales), format="json").status_code == 201
    assert client.post(endpoint, _corpo(opportunity, sales), format="json").status_code == 409
    assert Project.objects.count() == 1


@pytest.mark.django_db
def test_a_segunda_conversao_nao_cria_um_segundo_mandato():
    """O engajamento de escopo único é criado **dentro** da transação da conversão.

    Fora dela — ou antes do guard — a tentativa recusada ainda deixaria um mandato órfão para
    trás a cada clique, e a listagem de engajamentos encheria de linhas sem projeto nenhum.
    """
    sales = UserFactory(role=User.Role.SALES)
    opportunity = OpportunityFactory(stage=PipelineStage.objects.get(kind="won"), owner=sales)
    client = APIClient()
    client.force_authenticate(sales)
    endpoint = reverse("opportunity-convert-to-project", args=[opportunity.id])

    client.post(endpoint, _corpo(opportunity, sales), format="json")
    client.post(endpoint, _corpo(opportunity, sales, "De novo"), format="json")

    assert opportunity.client.engagements.count() == 1


@pytest.mark.django_db
def test_a_conversao_tranca_a_oportunidade_na_transacao():
    """A trava que substituiu a unicidade do `OneToOneField`.

    Duas requisições concorrentes de verdade exigiriam duas conexões e um banco que bloqueie
    linha; o SQLite da suíte serializa a escrita inteira e nunca reproduziria a corrida. E o SQL
    não serve de prova: o backend SQLite do Django **descarta** o `FOR UPDATE` silenciosamente
    (`has_select_for_update = False`), então a consulta travada e uma `get()` comum saem idênticas.

    O que dá para afirmar de forma determinística — e é o que se perde num refactor distraído — é
    que a conversão **chama** `select_for_update()` sobre `Opportunity`. Django já garante o
    resto: fora de um bloco atômico a chamada levanta `TransactionManagementError`, então observar
    a chamada num 201 é observar a trava dentro da transação.

    Sem esta asserção, remover o `select_for_update()` deixaria a suíte inteira verde e devolveria
    o defeito que o `IntegrityError` cobria de graça até a ADR 0050.
    """
    sales = UserFactory(role=User.Role.SALES)
    opportunity = OpportunityFactory(stage=PipelineStage.objects.get(kind="won"), owner=sales)
    client = APIClient()
    client.force_authenticate(sales)
    travados: list[str] = []
    original = QuerySet.select_for_update

    def espiao(self, *args, **kwargs):  # type: ignore[no-untyped-def]
        travados.append(self.model.__name__)
        return original(self, *args, **kwargs)

    with patch.object(QuerySet, "select_for_update", espiao):
        resposta = client.post(
            reverse("opportunity-convert-to-project", args=[opportunity.id]),
            _corpo(opportunity, sales),
            format="json",
        )

    assert resposta.status_code == 201
    assert "Opportunity" in travados, (
        "a conversão precisa travar a linha da oportunidade — sem o `select_for_update()` "
        "duas conversões simultâneas criam dois projetos"
    )
