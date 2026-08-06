"""Uma recusa de arquivamento precisa ter saída — e a instrução dela precisa ser verdade (FDD 025).

A guarda da oportunidade convertida testava `hasattr(instance, "project")`, que é verdadeiro
enquanto o `Project` existir na tabela — arquivado ou não, porque a relação reversa não some com o
`archived_at`. E a mensagem dizia "Arquive o projeto se quiser encerrar este trabalho".

O resultado era um beco sem saída completo, encontrado no primeiro uso real:

- a oportunidade **não arquivava**, nem depois de arquivado o projeto;
- **não reconvertia**, porque `Project.opportunity` é `OneToOneField` sem condição de arquivamento
  e o slot continua ocupado;
- e a oportunidade viva **bloqueava o cliente**, que também não arquivava.

Ou seja: a recusa mandava a pessoa fazer uma coisa que não desbloqueava nada. Recusa assim é pior
que nenhuma recusa, porque manda trabalhar à toa.
"""

from datetime import timedelta

import pytest
from django.urls import reverse
from django.utils import timezone
from rest_framework.test import APIClient

from apps.core.models import Opportunity, PipelineStage, User
from apps.core.tests.factories import OpportunityFactory, UserFactory


@pytest.fixture
def admin_client() -> APIClient:
    client = APIClient()
    client.force_authenticate(UserFactory(role=User.Role.ADMIN))
    return client


def _converter(admin_client: APIClient, opportunity: Opportunity) -> int:
    resposta = admin_client.post(
        reverse("opportunity-convert-to-project", args=[opportunity.pk]),
        {
            "client": opportunity.client_id,
            "name": "Projeto convertido",
            "start_date": str(timezone.localdate()),
            "due_date": str(timezone.localdate() + timedelta(days=10)),
        },
        format="json",
    )
    assert resposta.status_code == 201
    return int(resposta.data["id"])


@pytest.fixture
def convertida(admin_client: APIClient) -> tuple[Opportunity, int]:
    opportunity = OpportunityFactory(stage=PipelineStage.objects.get(kind="won"))
    return opportunity, _converter(admin_client, opportunity)


@pytest.mark.django_db
def test_arquivar_o_projeto_libera_a_oportunidade(
    admin_client: APIClient, convertida: tuple[Opportunity, int]
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
    admin_client: APIClient, convertida: tuple[Opportunity, int]
) -> None:
    """A correção não pode afrouxar a guarda: projeto vivo segue bloqueando."""
    opportunity, _ = convertida

    resposta = admin_client.delete(reverse("opportunity-detail", args=[opportunity.pk]))

    assert resposta.status_code == 409
    assert "já virou o projeto" in resposta.data["detail"]


@pytest.mark.django_db
def test_a_corrente_inteira_fecha(
    admin_client: APIClient, convertida: tuple[Opportunity, int]
) -> None:
    """Projeto → oportunidade → cliente, que é o caminho de quem quer encerrar um trabalho.

    Antes, o cliente ficava impossível de arquivar: a oportunidade travada o mantinha "em aberto"
    para sempre.
    """
    opportunity, projeto_id = convertida
    cliente_id = opportunity.client_id

    # Antes de limpar a oportunidade, o cliente é recusado — e a mensagem diz o que falta.
    bloqueado = admin_client.delete(reverse("client-detail", args=[cliente_id]))
    assert bloqueado.status_code == 409
    assert "oportunidade(s)" in bloqueado.data["detail"]

    assert admin_client.delete(reverse("project-detail", args=[projeto_id])).status_code == 204
    assert admin_client.delete(reverse("opportunity-detail", args=[opportunity.pk])).status_code == 204
    assert admin_client.delete(reverse("client-detail", args=[cliente_id])).status_code == 204


@pytest.mark.django_db
def test_reconverter_com_projeto_arquivado_aponta_a_restauracao(
    admin_client: APIClient, convertida: tuple[Opportunity, int]
) -> None:
    """Reconverter continua sendo 409 (o `OneToOneField` segue ocupado), mas a mensagem muda.

    "A oportunidade já foi convertida" é enganoso quando o projeto está arquivado e sumiu da tela:
    quem lê procura um projeto que não encontra.
    """
    opportunity, projeto_id = convertida
    admin_client.delete(reverse("project-detail", args=[projeto_id]))

    resposta = admin_client.post(
        reverse("opportunity-convert-to-project", args=[opportunity.pk]),
        {
            "client": opportunity.client_id,
            "name": "Outra tentativa",
            "start_date": str(timezone.localdate()),
            "due_date": str(timezone.localdate() + timedelta(days=10)),
        },
        format="json",
    )

    assert resposta.status_code == 409
    assert "arquivado" in resposta.data["detail"].lower()


@pytest.mark.django_db
def test_serializer_avisa_que_o_projeto_esta_arquivado(
    admin_client: APIClient, convertida: tuple[Opportunity, int]
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
