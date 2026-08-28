"""Uma recusa de arquivamento precisa ter saída — e a instrução dela precisa ser verdade (FDD 025).

A guarda da oportunidade convertida testava `hasattr(instance, "project")`, que é verdadeiro
enquanto o `Project` existir na tabela — arquivado ou não, porque a relação reversa não some com o
`archived_at`. E a mensagem dizia "Arquive o projeto se quiser encerrar este trabalho".

O resultado era um beco sem saída completo, encontrado no primeiro uso real:

- a oportunidade **não arquivava**, nem depois de arquivado o projeto;
- **não reconvertia**, porque `Project.opportunity` era `OneToOneField` sem condição de
  arquivamento e o slot continuava ocupado;
- e a oportunidade viva **bloqueava o cliente**, que também não arquivava.

Ou seja: a recusa mandava a pessoa fazer uma coisa que não desbloqueava nada. Recusa assim é pior
que nenhuma recusa, porque manda trabalhar à toa.

A FDD 025 fechou o primeiro e o terceiro furos. O segundo só fechou na ADR 0050, quando a origem
comercial deixou de ser 1-1: sem slot, projeto arquivado não ocupa mais nada, e a instrução
"arquive o projeto" passou a desbloquear **as duas** saídas — encerrar a oportunidade e
reconverter. O que continua barrado é o que sempre importou, e é o outro teste desta suíte:
projeto **vivo** recusa a segunda conversão, para o duplo clique não duplicar projeto.
"""

from datetime import timedelta

import pytest
from django.urls import reverse
from django.utils import timezone
from rest_framework.test import APIClient

from apps.core.models import CommercialOpportunity, PipelineStage, Project, User
from apps.core.tests.factories import CommercialOpportunityFactory, UserFactory


@pytest.fixture
def admin_client() -> APIClient:
    client = APIClient()
    client.force_authenticate(UserFactory(role=User.Role.ADMIN))
    return client


def _converter(admin_client: APIClient, opportunity: CommercialOpportunity) -> int:
    resposta = admin_client.post(
        reverse("opportunity-convert-to-project", args=[opportunity.pk]),
        {
            "client": opportunity.account_id,
            "name": "Projeto convertido",
            "start_date": str(timezone.localdate()),
            "due_date": str(timezone.localdate() + timedelta(days=10)),
        },
        format="json",
    )
    assert resposta.status_code == 201
    return int(resposta.data["id"])


@pytest.fixture
def convertida(admin_client: APIClient) -> tuple[CommercialOpportunity, int]:
    opportunity = CommercialOpportunityFactory(stage=PipelineStage.objects.get(kind="won"))
    return opportunity, _converter(admin_client, opportunity)


@pytest.mark.django_db
def test_arquivar_o_projeto_libera_a_oportunidade(
    admin_client: APIClient, convertida: tuple[CommercialOpportunity, int]
) -> None:
    """O defeito: a instrução da mensagem de erro não desbloqueava nada."""
    opportunity, projeto_id = convertida
    assert admin_client.delete(reverse("project-detail", args=[projeto_id])).status_code == 204

    resposta = admin_client.delete(reverse("opportunity-detail", args=[opportunity.pk]))

    assert resposta.status_code == 204
    opportunity.refresh_from_db()
    assert opportunity.is_archived


@pytest.mark.django_db
def test_com_projeto_ativo_a_recusa_continua(
    admin_client: APIClient, convertida: tuple[CommercialOpportunity, int]
) -> None:
    """A correção não pode afrouxar a guarda: projeto vivo segue bloqueando."""
    opportunity, _ = convertida

    resposta = admin_client.delete(reverse("opportunity-detail", args=[opportunity.pk]))

    assert resposta.status_code == 409
    assert "já virou o projeto" in resposta.data["detail"]


@pytest.mark.django_db
def test_a_corrente_inteira_fecha(
    admin_client: APIClient, convertida: tuple[CommercialOpportunity, int]
) -> None:
    """Projeto → oportunidade → cliente, que é o caminho de quem quer encerrar um trabalho.

    Antes, o cliente ficava impossível de arquivar: a oportunidade travada o mantinha "em aberto"
    para sempre.
    """
    opportunity, projeto_id = convertida
    cliente_id = opportunity.account_id

    # Antes de limpar a oportunidade, o cliente é recusado — e a mensagem diz o que falta.
    bloqueado = admin_client.delete(reverse("client-detail", args=[cliente_id]))
    assert bloqueado.status_code == 409
    assert "oportunidade(s)" in bloqueado.data["detail"]

    assert admin_client.delete(reverse("project-detail", args=[projeto_id])).status_code == 204
    assert admin_client.delete(reverse("opportunity-detail", args=[opportunity.pk])).status_code == 204
    assert admin_client.delete(reverse("client-detail", args=[cliente_id])).status_code == 204


@pytest.mark.django_db
def test_com_o_projeto_arquivado_a_oportunidade_reconverte(
    admin_client: APIClient, convertida: tuple[CommercialOpportunity, int]
) -> None:
    """A última saída do beco, e ela **mudou de resposta** na ADR 0050.

    Antes: 409, com uma mensagem que mandava restaurar o projeto — a única saída que existia,
    porque o `OneToOneField` mantinha o slot ocupado mesmo com o projeto fora da tela. Restaurar
    era a saída errada para quem arquivou de propósito e quer recomeçar o trabalho.

    Agora a origem é 1-N: projeto arquivado não ocupa lugar nenhum, e reconverter cria um projeto
    novo. **A guarda que importa não afrouxou** — quem barra a segunda conversão é o projeto
    *vivo*, e é o `test_com_projeto_ativo_a_recusa_continua` acima que fixa isso, junto de
    `tests/regression/test_conversion_is_single_use.py`.
    """
    opportunity, projeto_id = convertida
    admin_client.delete(reverse("project-detail", args=[projeto_id]))

    resposta = admin_client.post(
        reverse("opportunity-convert-to-project", args=[opportunity.pk]),
        {
            "client": opportunity.account_id,
            "name": "Outra tentativa",
            "start_date": str(timezone.localdate()),
            "due_date": str(timezone.localdate() + timedelta(days=10)),
        },
        format="json",
    )

    assert resposta.status_code == 201
    assert resposta.data["id"] != projeto_id
    # O card do pipeline volta a apontar para o projeto vivo, e deixa de se dizer arquivado.
    card = admin_client.get(reverse("opportunity-detail", args=[opportunity.pk])).data
    assert card["project"] == resposta.data["id"] and card["project_archived"] is False


@pytest.mark.django_db
def test_o_projeto_vivo_ainda_recusa_a_segunda_conversao(
    admin_client: APIClient, convertida: tuple[CommercialOpportunity, int]
) -> None:
    """O par do teste acima: a 1-N não pode virar licença para o duplo clique duplicar projeto."""
    opportunity, _ = convertida

    resposta = admin_client.post(
        reverse("opportunity-convert-to-project", args=[opportunity.pk]),
        {
            "client": opportunity.account_id,
            "name": "Duplo clique",
            "start_date": str(timezone.localdate()),
            "due_date": str(timezone.localdate() + timedelta(days=10)),
        },
        format="json",
    )

    assert resposta.status_code == 409
    assert Project.objects.filter(originating_commercial_opportunity=opportunity).count() == 1


@pytest.mark.django_db
def test_serializer_avisa_que_o_projeto_esta_arquivado(
    admin_client: APIClient, convertida: tuple[CommercialOpportunity, int]
) -> None:
    """Sem isto o card do pipeline oferece "Ver projeto" para um 404.

    `project` **continua** preenchido de propósito: anulá-lo faria a tela voltar a oferecer "Criar
    projeto", que responde 409 — trocaria um link morto por um botão morto.
    """
    opportunity, projeto_id = convertida

    ativo = admin_client.get(reverse("opportunity-detail", args=[opportunity.pk])).data
    assert ativo["project"] == projeto_id and ativo["project_archived"] is False

    admin_client.delete(reverse("project-detail", args=[projeto_id]))

    arquivado = admin_client.get(reverse("opportunity-detail", args=[opportunity.pk])).data
    assert arquivado["project"] == projeto_id and arquivado["project_archived"] is True
