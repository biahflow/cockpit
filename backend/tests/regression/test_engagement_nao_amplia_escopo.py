"""Regressão: o engajamento é camada de leitura, **não** fronteira de acesso (ADR 0050).

A fatia que introduz o `Engagement` cria uma segunda coisa que agrupa projetos, e é aí que mora o
risco: o recorte da Entrega sempre foi `ProjectMember` (RFC 0003, ADR 0010), e uma camada acima do
projeto é a tentação óbvia de o afrouxar — "se a pessoa vê o mandato, deixa ver os projetos dele".

Seria uma ampliação silenciosa de privilégio. O mandato agrupa a conta inteira; participar de um
projeto passaria a dar acesso a todos os outros da mesma conta, e o sintoma seria uma lista um
pouco maior — não um erro.

`project_scope_q` e `ProjectScopedMixin` não mudaram nesta fatia, e estes testes são o que fixa
que continuem assim.
"""

import pytest
from django.urls import reverse
from rest_framework.test import APIClient

from apps.core.models import Milestone, PipelineStage, Project, User
from apps.core.tests.factories import (
    CommercialOpportunityFactory,
    EngagementFactory,
    ProjectFactory,
    ProjectMemberFactory,
    UserFactory,
)

pytestmark = pytest.mark.django_db


@pytest.fixture
def cenario() -> tuple[APIClient, User, Project, Project]:
    """Uma pessoa da Entrega, membro de **um** projeto de um mandato que tem dois."""
    pessoa = UserFactory(role=User.Role.DELIVERY)
    engagement = EngagementFactory()
    meu = ProjectFactory(engagement__account=engagement.account, engagement=engagement)
    vizinho = ProjectFactory(engagement__account=engagement.account, engagement=engagement)
    ProjectMemberFactory(project=meu, user=pessoa)
    api = APIClient()
    api.force_authenticate(pessoa)
    return api, pessoa, meu, vizinho


def test_o_mandato_visivel_nao_lista_o_projeto_alheio(
    cenario: tuple[APIClient, User, Project, Project],
) -> None:
    api, _, meu, vizinho = cenario

    assert api.get(reverse("engagement-detail", args=[meu.engagement_id])).status_code == 200
    listados = [linha["id"] for linha in api.get(reverse("project-list")).data]
    assert listados == [meu.pk]
    assert vizinho.pk not in listados


def test_o_mandato_visivel_nao_abre_o_detalhe_do_projeto_alheio(
    cenario: tuple[APIClient, User, Project, Project],
) -> None:
    api, _, _, vizinho = cenario

    assert api.get(reverse("project-detail", args=[vizinho.pk])).status_code == 404


def test_o_mandato_visivel_nao_alcanca_o_que_pende_do_projeto_alheio(
    cenario: tuple[APIClient, User, Project, Project],
) -> None:
    """O recorte atravessa: marco de projeto alheio continua fora, mandato visível ou não."""
    api, _, _, vizinho = cenario
    marco = Milestone.objects.create(
        project=vizinho, title="Marco alheio", owner=vizinho.owner, due_date=vizinho.due_date
    )

    listados = [linha["id"] for linha in api.get(reverse("milestone-list")).data]

    assert marco.pk not in listados
    assert api.get(reverse("milestone-detail", args=[marco.pk])).status_code == 404


def test_visible_to_continua_sendo_a_unica_expressao_da_regra(
    cenario: tuple[APIClient, User, Project, Project],
) -> None:
    """A pergunta na origem, sem passar por rota: o mandato não entra no critério."""
    _, pessoa, meu, vizinho = cenario

    visiveis = set(Project.objects.visible_to(pessoa).values_list("pk", flat=True))

    assert visiveis == {meu.pk}
    assert vizinho.engagement_id == meu.engagement_id  # mesmo mandato, e ainda assim fora


def test_entrega_sem_projeto_nenhum_no_mandato_nao_ve_o_mandato() -> None:
    """O outro lado: a visibilidade do engajamento **deriva** dos projetos, não os concede."""
    pessoa = UserFactory(role=User.Role.DELIVERY)
    engagement = EngagementFactory()
    ProjectFactory(engagement__account=engagement.account, engagement=engagement)
    api = APIClient()
    api.force_authenticate(pessoa)

    assert api.get(reverse("engagement-list")).data == []
    # 404, não 403: `EngagementViewSet.get_queryset` já deriva a visibilidade dos projetos que a
    # pessoa alcança (ver docstring da viewset), então `get_object()` filtra o mandato antes de
    # `has_object_permission` ser avaliada — o queryset escopado é a camada que responde aqui.
    assert api.get(reverse("engagement-detail", args=[engagement.pk])).status_code == 404


def test_o_contrato_da_oportunidade_mantem_a_forma() -> None:
    """Invariante de contrato: `project`/`project_archived` não mudaram de forma na 1-N.

    `CommercialPage.tsx` lê os dois campos e não mudou nesta fatia. Com vários projetos por
    origem, `project` continua sendo **um id ou nulo** — nunca uma lista —, e é o vivo mais antigo.
    """
    admin = UserFactory(role=User.Role.ADMIN)
    api = APIClient()
    api.force_authenticate(admin)
    engagement = EngagementFactory()
    origem = CommercialOpportunityFactory(
        account=engagement.account, stage=PipelineStage.objects.get(kind="won"), owner=admin
    )
    primeiro = ProjectFactory(
        engagement=engagement,
        originating_commercial_opportunity=origem,
    )
    ProjectFactory(
        engagement=engagement,
        originating_commercial_opportunity=origem,
    )

    linha = api.get(reverse("opportunity-detail", args=[origem.pk])).data

    assert linha["project"] == primeiro.pk
    assert linha["project_archived"] is False
