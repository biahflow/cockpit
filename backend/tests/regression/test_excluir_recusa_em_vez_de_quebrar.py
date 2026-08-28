"""Excluir de verdade recusa com 409 — nunca quebra com 500 (FDD 025, FDD 011).

A FDD 025 deu botão e confirmação aos **dois** recursos que realmente excluem — etapa do pipeline
e fase da jornada — e não lhes deu caminho de recusa. Os dois batem em FK `PROTECT`
(`CommercialOpportunity.stage`, `ProjectPhase.phase`), e o `ProtectedError` não era tratado em lugar nenhum:
saía **500**, que o SPA mostra como "Não foi possível concluir a operação." e ainda reporta ao
Sentry (`api.ts`), transformando uso legítimo da interface em incidente.

O caso da fase era pior que intermitente: `materialize_journey` instancia **todas** as fases do
template em **todo** projeto, então bastava um projeto na base para o botão "Excluir" da tela
Jornada estar morto para qualquer fase — enquanto o diálogo prometia que "projetos que já
materializaram esta fase não são afetados".

E a recusa precisa ter saída (FDD 025): quem quer aposentar uma fase da metodologia agora a
**desativa** — ela deixa de ser herdada por projeto novo e os antigos ficam com a delas.
"""

import pytest
from django.conf import settings
from django.db.models import ProtectedError
from django.urls import reverse
from rest_framework.test import APIClient

from apps.core.exceptions import api_exception_handler
from apps.core.models import JourneyPhase, PipelineStage, ProjectPhase, User, Vertical
from apps.core.tests.factories import (
    ClientFactory,
    CommercialOpportunityFactory,
    PipelineStageFactory,
    ProjectFactory,
    UserFactory,
)


@pytest.fixture
def admin_client() -> APIClient:
    client = APIClient()
    client.force_authenticate(UserFactory(role=User.Role.ADMIN))
    return client


@pytest.mark.django_db
def test_fase_em_uso_recusa_com_409_em_vez_de_500(admin_client: APIClient) -> None:
    """O defeito: com um projeto na base, excluir qualquer fase devolvia 500."""
    ProjectFactory()  # materializa o template inteiro
    fase = JourneyPhase.objects.order_by("position").first()
    assert fase is not None

    resposta = admin_client.delete(reverse("journeyphase-detail", args=[fase.pk]))

    assert resposta.status_code == 409
    assert "1 projeto(s)" in resposta.data["detail"]
    assert "Desative" in resposta.data["detail"]  # a saída, e ela existe
    assert JourneyPhase.objects.filter(pk=fase.pk).exists()


@pytest.mark.django_db
def test_fase_conta_o_projeto_arquivado_junto(admin_client: APIClient) -> None:
    """`PROTECT` não sabe o que é `archived_at`, e a mensagem não pode fingir que sabe.

    Contar só o ativo produziria "0 projeto(s)" numa recusa — ou pior, a promessa de que arquivar
    o projeto libera a exclusão, que é a classe de mentira que a FDD 025 existe para consertar.
    """
    projeto = ProjectFactory()
    projeto.archive()
    fase = JourneyPhase.objects.order_by("position").first()
    assert fase is not None

    resposta = admin_client.delete(reverse("journeyphase-detail", args=[fase.pk]))

    assert resposta.status_code == 409
    assert "1 projeto(s)" in resposta.data["detail"]


@pytest.mark.django_db
def test_desativar_a_fase_e_a_saida_da_recusa(admin_client: APIClient) -> None:
    """A saída que a recusa oferece precisa funcionar: fase inativa não é mais herdada."""
    ProjectFactory()
    fase = JourneyPhase.objects.order_by("-position").first()
    assert fase is not None

    patch = admin_client.patch(
        reverse("journeyphase-detail", args=[fase.pk]), {"active": False}, format="json"
    )
    assert patch.status_code == 200 and patch.data["active"] is False

    novo = ProjectFactory()
    assert not ProjectPhase.objects.filter(project=novo, phase=fase).exists()
    assert novo.phases.count() == JourneyPhase.objects.filter(active=True).count()


@pytest.mark.django_db
def test_projeto_antigo_mantem_a_fase_desativada(admin_client: APIClient) -> None:
    """Desativar é sobre o futuro. Reescrever o histórico seria outro estrago."""
    projeto = ProjectFactory()
    fase = JourneyPhase.objects.order_by("-position").first()
    assert fase is not None

    admin_client.patch(
        reverse("journeyphase-detail", args=[fase.pk]), {"active": False}, format="json"
    )

    assert ProjectPhase.objects.filter(project=projeto, phase=fase).exists()


@pytest.mark.django_db
def test_fase_que_ninguem_materializou_ainda_e_excluida(admin_client: APIClient) -> None:
    """A exclusão continua existindo — para a fase criada por engano, que é o caso dela."""
    ProjectFactory()
    engano = JourneyPhase.objects.create(name="Fase criada por engano", position=99)

    resposta = admin_client.delete(reverse("journeyphase-detail", args=[engano.pk]))

    assert resposta.status_code == 204
    assert not JourneyPhase.objects.filter(pk=engano.pk).exists()


@pytest.mark.django_db
def test_etapa_com_oportunidade_recusa_com_409(admin_client: APIClient) -> None:
    etapa = PipelineStageFactory()
    CommercialOpportunityFactory(stage=etapa)

    resposta = admin_client.delete(reverse("pipelinestage-detail", args=[etapa.pk]))

    assert resposta.status_code == 409
    assert "1 oportunidade(s)" in resposta.data["detail"]
    assert PipelineStage.objects.filter(pk=etapa.pk).exists()


@pytest.mark.django_db
def test_etapa_com_oportunidade_so_arquivada_diz_que_ela_existe(admin_client: APIClient) -> None:
    """O caso que a contagem ingênua erraria — e que deixaria a pessoa sem saber o que fazer.

    A oportunidade arquivada sumiu do quadro, mas continua segurando a etapa. Mandar "mova as
    oportunidades para outra etapa" sem dizer que uma delas está arquivada é mandar procurar o
    que a interface esconde.
    """
    etapa = PipelineStageFactory()
    oportunidade = CommercialOpportunityFactory(stage=etapa)
    oportunidade.archive()

    resposta = admin_client.delete(reverse("pipelinestage-detail", args=[etapa.pk]))

    assert resposta.status_code == 409
    assert "1 oportunidade(s)" in resposta.data["detail"]
    assert "arquivada" in resposta.data["detail"]


@pytest.mark.django_db
def test_etapa_sem_oportunidade_e_excluida(admin_client: APIClient) -> None:
    etapa = PipelineStageFactory()

    assert admin_client.delete(reverse("pipelinestage-detail", args=[etapa.pk])).status_code == 204
    assert not PipelineStage.objects.filter(pk=etapa.pk).exists()


@pytest.mark.django_db
def test_vertical_em_uso_nao_apaga_calada_o_setor_dos_clientes(admin_client: APIClient) -> None:
    """A rede global **não** cobre este caso, e é por isso que ele está aqui (FDD 026).

    Todo dependente deste arquivo até agora era `PROTECT`: o banco recusava e o único defeito era o
    status. `Client.vertical` é `SET_NULL` — o banco aceita de bom grado e zera o setor de **todos**
    os clientes que a tinham, com 204 na tela e nada dizendo o que se perdeu. Aqui a guarda
    explícita do viewset não é a mensagem boa sobre uma recusa que existiria de qualquer jeito: ela
    é a recusa.
    """
    vertical = Vertical.objects.create(name="Igrejas", slug="igrejas")
    cliente = ClientFactory(vertical=vertical)

    resposta = admin_client.delete(reverse("vertical-detail", args=[vertical.pk]))

    assert resposta.status_code == 409
    assert "Desative" in resposta.data["detail"]
    cliente.refresh_from_db()
    assert cliente.vertical_id == vertical.pk


def test_a_rede_global_traduz_qualquer_protecterror() -> None:
    """As guardas acima recusam antes; esta é a rede que impede o 500 de voltar.

    São doze FKs `PROTECT` no `models.py` e nada garante que a próxima rota de exclusão lembre de
    contar seus dependentes. A rede não substitui a mensagem específica — dá o status certo.
    """
    resposta = api_exception_handler(ProtectedError("protegido", set()), {})

    assert resposta is not None and resposta.status_code == 409


def test_a_rede_esta_ligada_na_api() -> None:
    """Sem o registro nas settings o handler seria código morto — e o 500 continuaria saindo."""
    assert (
        settings.REST_FRAMEWORK["EXCEPTION_HANDLER"] == "apps.core.exceptions.api_exception_handler"
    )
