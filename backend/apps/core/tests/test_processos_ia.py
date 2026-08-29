"""A extração estruturada do Discovery a partir da transcrição (FDD 039).

Mesma divisão do `test_decisoes_ia.py`: o que dá para exercitar sem chamar o provedor é o
**parser**, e é onde os defeitos moram; a chamada ao modelo é substituída por `ai.complete`
monkeypatchado, como no resto da suíte de IA.

O caso central deste arquivo não é a extração feliz — é o que o modelo **não** decide. Todo achado
nasce hipótese, vindo de entrevista, e o teste que prova isso manda o modelo dizer o contrário.
"""

import json

import pytest
from django.test import override_settings
from django.urls import reverse
from django.utils import timezone
from rest_framework.test import APIClient

from apps.core import ai
from apps.core.models import (
    Evidence,
    Finding,
    Meeting,
    Process,
    ProcessStep,
    User,
)
from apps.core.views import processos_do_texto

from .factories import ProcessFactory, ProjectFactory, ProjectMemberFactory, UserFactory

MAPA = [
    {
        "name": "Faturamento mensal",
        "etapas": [
            {
                "name": "Conferir notas",
                "pessoas": "Analista financeiro",
                "sistema": "ERP e planilha",
                "dados": "Notas do mês entram, relatório sai",
                "tempo": "Dois dias",
                "erro": "Nota com valor divergente",
                "retrabalho": "Refaz a conferência inteira",
            },
            {"name": "Emitir boletos"},
        ],
        "achados": [
            "O fechamento leva dois dias por causa da conferência manual.",
            "Ninguém sabe quantas notas voltam por mês.",
        ],
    },
    {"name": "Atendimento ao cliente", "etapas": [], "achados": []},
]


# --------------------------------------------------------------------------------------------
# O parser, sem banco e sem provedor.
# --------------------------------------------------------------------------------------------


def test_um_array_json_limpo_e_lido() -> None:
    extraidos = processos_do_texto(json.dumps(MAPA))

    assert [p["name"] for p in extraidos] == ["Faturamento mensal", "Atendimento ao cliente"]
    primeiro = extraidos[0]
    assert [e["name"] for e in primeiro["etapas"]] == ["Conferir notas", "Emitir boletos"]
    assert primeiro["etapas"][0]["retrabalho"] == "Refaz a conferência inteira"
    # A etapa que veio só com nome sai com os seis campos em branco, e não com chave faltando:
    # quem grava faz `**etapa` num modelo cujos seis campos são `TextField(blank=True)`.
    assert primeiro["etapas"][1] == {
        "name": "Emitir boletos", "pessoas": "", "sistema": "", "dados": "",
        "tempo": "", "erro": "", "retrabalho": "",
    }
    assert len(primeiro["achados"]) == 2


def test_prosa_e_cerca_de_markdown_em_volta_do_array_sao_recortadas() -> None:
    """A falha típica do modelo não é JSON inválido — é JSON válido dentro de prosa."""
    texto = (
        "Claro! Mapeei os processos a seguir:\n\n```json\n"
        '[{"name": "Faturamento mensal"}]\n```\n\nQuer que eu detalhe algum deles?'
    )

    assert processos_do_texto(texto) == [
        {"name": "Faturamento mensal", "etapas": [], "achados": []}
    ]


def test_processo_sem_nome_e_descartado_e_os_outros_sobrevivem() -> None:
    texto = json.dumps([
        {"name": "Primeiro"}, {"name": "   "}, "isto não é objeto",
        {"etapas": [{"name": "órfã"}]}, {"name": "Último"},
    ])

    assert [p["name"] for p in processos_do_texto(texto)] == ["Primeiro", "Último"]


def test_etapa_sem_nome_e_descartada_sem_derrubar_o_processo() -> None:
    """Perder a quarta etapa de sete não é razão para perder o processo inteiro."""
    texto = json.dumps([{
        "name": "Faturamento",
        "etapas": [{"name": "Conferir"}, {"name": ""}, "texto solto", {"pessoas": "sem nome"},
                   {"name": "Emitir"}],
    }])

    (processo,) = processos_do_texto(texto)
    assert [e["name"] for e in processo["etapas"]] == ["Conferir", "Emitir"]


def test_achado_vazio_ou_que_nao_e_texto_e_descartado() -> None:
    """Achado é frase. Um objeto virado em `str` gravaria o `repr` do dicionário como citação."""
    texto = json.dumps([{
        "name": "Faturamento",
        "achados": ["Vale.", "   ", "", {"content": "não é string"}, 42, "Vale também."],
    }])

    (processo,) = processos_do_texto(texto)
    assert processo["achados"] == ["Vale.", "Vale também."]


def test_sem_array_nenhum_nao_houve_extracao() -> None:
    """Sem lista não houve extração — e quem chama responde 502 em vez de gravar zero em silêncio."""
    assert processos_do_texto("Não identifiquei processos nesta transcrição.") == []
    assert processos_do_texto("") == []
    assert processos_do_texto("[isto não fecha") == []
    # Aspas simples: o recorte acha um array, e o `json` recusa. Descartar é o certo — "quase JSON"
    # remendado a mão viraria um segundo parser, com um segundo conjunto de defeitos.
    assert processos_do_texto("[{'name': 'aspas simples'}]") == []
    assert processos_do_texto('{"name": "um objeto, não uma lista"}') == []


def test_o_modelo_nao_estoura_o_tamanho_das_colunas() -> None:
    """`Process.name` e `ProcessStep.name` são `CharField(255)`, e o modelo não sabe disso."""
    texto = json.dumps([{"name": "p" * 4000, "etapas": [{"name": "e" * 4000}]}])

    (processo,) = processos_do_texto(texto)
    assert len(processo["name"]) == 255
    assert len(processo["etapas"][0]["name"]) == 255


def test_o_parser_ignora_o_que_o_modelo_diz_sobre_o_achado() -> None:
    """A regra da fatia, no nível do parser: o que o modelo mandar sobre o achado não é lido.

    O achado sai daqui como **string pura**; quem grava é que decide o que ele vale. Ver
    `tests/regression/test_a_extracao_nasce_hipotese.py` para a guarda inteira.
    """
    texto = json.dumps([{
        "name": "Faturamento",
        "achados": ["São 400 notas por mês."],
        "rotulo": "fato",
        "forma": "dado",
    }])

    (processo,) = processos_do_texto(texto)
    assert processo == {
        "name": "Faturamento", "etapas": [], "achados": ["São 400 notas por mês."]
    }


# --------------------------------------------------------------------------------------------
# A action, com o provedor substituído.
# --------------------------------------------------------------------------------------------


def _reuniao_de_discovery(delivery: User) -> Meeting:
    project = ProjectFactory()
    ProjectMemberFactory(project=project, user=delivery)
    return Meeting.objects.create(
        project=project, title="Discovery", date=timezone.localdate(),
        transcript="O faturamento é conferido nota a nota.",
    )


def _responde(monkeypatch: pytest.MonkeyPatch, texto: str) -> None:
    monkeypatch.setattr(
        ai, "complete",
        lambda s, u, **_: (texto, {"prompt_tokens": 5, "completion_tokens": 3}),
    )


@pytest.fixture
def delivery() -> User:
    return UserFactory(role=User.Role.DELIVERY)


@pytest.fixture
def api(delivery: User) -> APIClient:
    client = APIClient()
    client.force_authenticate(delivery)
    return client


@pytest.mark.django_db
@override_settings(AI_ENABLED=True, OPENAI_API_KEY="sk-teste")
def test_a_extracao_grava_processos_etapas_e_achados(
    api: APIClient, delivery: User, monkeypatch: pytest.MonkeyPatch
) -> None:
    meeting = _reuniao_de_discovery(delivery)
    _responde(monkeypatch, json.dumps(MAPA))

    resposta = api.post(reverse("meeting-estruturar", args=[meeting.pk]))

    assert resposta.status_code == 200, resposta.data
    assert [p["name"] for p in resposta.json()["processos"]] == [
        "Faturamento mensal", "Atendimento ao cliente"
    ]
    assert Process.objects.count() == 2
    faturamento = Process.objects.get(name="Faturamento mensal")
    # Procedência: de que cliente é o mapa, e de onde ele veio.
    assert faturamento.account_id == meeting.project.client_id
    assert faturamento.source_meeting_id == meeting.pk
    assert faturamento.source_project_id == meeting.project_id
    assert faturamento.registered_by_id == delivery.pk
    assert [(e.name, e.position) for e in faturamento.steps.all()] == [
        ("Conferir notas", 1), ("Emitir boletos", 2)
    ]
    conferir = faturamento.steps.first()
    assert conferir is not None and conferir.tempo == "Dois dias"
    # Um `Finding` por achado, e uma `Evidence` por processo (de onde os achados vieram).
    assert faturamento.findings.count() == 2
    assert faturamento.evidence.count() == 1
    assert ProcessStep.objects.count() == 2
    assert Finding.objects.count() == 2


@pytest.mark.django_db
@override_settings(AI_ENABLED=True, OPENAI_API_KEY="sk-teste")
def test_todo_achado_nasce_hipotese_vinda_de_entrevista(
    api: APIClient, delivery: User, monkeypatch: pytest.MonkeyPatch
) -> None:
    """O teste central da fatia — e ele manda o modelo dizer o contrário.

    Um modelo lendo transcrição produz *o que foi dito*: entrevista, uma das cinco formas de
    evidência (`docs/metodologia-fde.md:112-115`), e nunca prova. Promover a fato é ato de gente.
    """
    meeting = _reuniao_de_discovery(delivery)
    _responde(monkeypatch, json.dumps([{
        "name": "Faturamento mensal",
        "achados": ["São 400 notas por mês.", "O fechamento leva dois dias."],
        "rotulo": "fato",
        "forma": "dado",
    }]))

    resposta = api.post(reverse("meeting-estruturar", args=[meeting.pk]))

    assert resposta.status_code == 200, resposta.data
    achados = list(Finding.objects.all())
    assert len(achados) == 2
    assert {a.epistemic_status for a in achados} == {Finding.EpistemicStatus.HYPOTHESIS}
    # E o achado fica no processo, não na etapa: vínculo errado é pior que vínculo nenhum.
    assert all(a.step_id is None for a in achados)
    # A forma de onde o achado veio mora na `Evidence` do split — entrevista, uma por processo —,
    # e é o autuado da sessão que a captura.
    evidencia = Evidence.objects.get()
    assert evidencia.kind == Evidence.Kind.INTERVIEW
    assert evidencia.source_meeting_id == meeting.pk
    assert evidencia.captured_by_id == delivery.pk
    assert all(list(a.evidences.all()) == [evidencia] for a in achados)


@pytest.mark.django_db
@override_settings(AI_ENABLED=True, OPENAI_API_KEY="sk-teste")
def test_etapa_sem_nome_nao_derruba_o_processo_ponta_a_ponta(
    api: APIClient, delivery: User, monkeypatch: pytest.MonkeyPatch
) -> None:
    meeting = _reuniao_de_discovery(delivery)
    _responde(monkeypatch, json.dumps([
        {"name": "Faturamento", "etapas": [{"name": "Conferir"}, {"name": "  "}]},
        {"etapas": [{"name": "de processo sem nome"}]},
    ]))

    resposta = api.post(reverse("meeting-estruturar", args=[meeting.pk]))

    assert resposta.status_code == 200, resposta.data
    assert [p.name for p in Process.objects.all()] == ["Faturamento"]
    assert [e.name for e in ProcessStep.objects.all()] == ["Conferir"]


@pytest.mark.django_db
@override_settings(AI_ENABLED=True, OPENAI_API_KEY="sk-teste")
def test_resposta_inutilizavel_nao_grava_nada_e_diz_isso(
    api: APIClient, delivery: User, monkeypatch: pytest.MonkeyPatch
) -> None:
    """502 e zero linhas: gravar zero processos e responder 200 diria que a reunião não descreveu
    nenhum, que é uma conclusão diferente de "o modelo não devolveu lista"."""
    meeting = _reuniao_de_discovery(delivery)
    _responde(monkeypatch, "Desculpe, não identifiquei processos.")

    resposta = api.post(reverse("meeting-estruturar", args=[meeting.pk]))

    assert resposta.status_code == 502
    assert Process.objects.count() == 0
    assert Finding.objects.count() == 0


@pytest.mark.django_db
def test_reuniao_sem_transcricao_e_recusada_antes_de_chamar_a_ia(
    api: APIClient, delivery: User
) -> None:
    project = ProjectFactory()
    ProjectMemberFactory(project=project, user=delivery)
    meeting = Meeting.objects.create(
        project=project, title="Discovery", date=timezone.localdate(), transcript="   "
    )

    resposta = api.post(reverse("meeting-estruturar", args=[meeting.pk]))

    assert resposta.status_code == 400
    assert Process.objects.count() == 0


@pytest.mark.django_db
@override_settings(AI_ENABLED=True, OPENAI_API_KEY="sk-teste")
def test_a_segunda_extracao_e_recusada_com_409(
    api: APIClient, delivery: User, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Divergência deliberada do `extrair_decisoes`: `Process` não tem estado de rascunho.

    Lá a segunda rodada dá mais rascunho para revisar; aqui ela dobraria o mapa da operação do
    cliente em silêncio, e um duplo clique bastaria.
    """
    meeting = _reuniao_de_discovery(delivery)
    _responde(monkeypatch, json.dumps(MAPA))
    assert api.post(reverse("meeting-estruturar", args=[meeting.pk])).status_code == 200

    resposta = api.post(reverse("meeting-estruturar", args=[meeting.pk]))

    assert resposta.status_code == 409
    assert "2" in resposta.json()["detail"]  # diz **quantos**, e não só que já houve
    assert Process.objects.count() == 2
    assert Finding.objects.count() == 2


@pytest.mark.django_db
@override_settings(AI_ENABLED=True, OPENAI_API_KEY="sk-teste")
def test_arquivar_o_que_foi_extraido_reabre_a_extracao(
    api: APIClient, delivery: User, monkeypatch: pytest.MonkeyPatch
) -> None:
    """O caminho de saída que o 409 aponta precisa existir de verdade."""
    meeting = _reuniao_de_discovery(delivery)
    _responde(monkeypatch, json.dumps(MAPA))
    api.post(reverse("meeting-estruturar", args=[meeting.pk]))
    for processo in Process.objects.all():
        processo.archive()

    resposta = api.post(reverse("meeting-estruturar", args=[meeting.pk]))

    assert resposta.status_code == 200, resposta.data
    assert Process.objects.filter(archived_at__isnull=True).count() == 2
    assert Process.objects.count() == 4


@pytest.mark.django_db
@override_settings(AI_ENABLED=True, OPENAI_API_KEY="sk-teste")
def test_a_extracao_entra_depois_do_que_foi_mapeado_a_mao(
    api: APIClient, delivery: User, monkeypatch: pytest.MonkeyPatch
) -> None:
    """`position` é a ordem em que a operação acontece; o que veio do modelo não se intercala."""
    meeting = _reuniao_de_discovery(delivery)
    account = meeting.project.client
    ProcessFactory(account=account, name="Compras", position=1)
    ProcessFactory(account=account, name="Expedição", position=7)
    # Arquivado não conta como ocupante da ordem — senão um mapa antigo empurraria o novo sem
    # motivo visível na tela.
    ProcessFactory(account=account, name="Antigo", position=90).archive()
    _responde(monkeypatch, json.dumps(MAPA))

    resposta = api.post(reverse("meeting-estruturar", args=[meeting.pk]))

    assert resposta.status_code == 200, resposta.data
    extraidos = Process.objects.filter(source_meeting=meeting).order_by("position")
    assert [(p.name, p.position) for p in extraidos] == [
        ("Faturamento mensal", 8), ("Atendimento ao cliente", 9)
    ]


@pytest.mark.django_db
@override_settings(AI_ENABLED=True, OPENAI_API_KEY="sk-teste")
def test_falha_no_meio_nao_deixa_nada_para_tras(
    api: APIClient, delivery: User, monkeypatch: pytest.MonkeyPatch
) -> None:
    """O `atomic` em volta: sem estado de rascunho, um mapa pela metade é indistinguível de um
    mapa levantado de verdade."""
    meeting = _reuniao_de_discovery(delivery)
    _responde(monkeypatch, json.dumps(MAPA))

    def explode(*args: object, **kwargs: object) -> None:
        raise RuntimeError("banco fora do ar no meio da gravação")

    # Estoura na gravação do achado, no meio da transação: o `Finding` é criado por processo, e
    # se a transação não cobrisse tudo um `Process` sem achado sobreviveria à falha.
    monkeypatch.setattr(Finding.objects, "create", explode)

    with pytest.raises(RuntimeError):
        api.post(reverse("meeting-estruturar", args=[meeting.pk]))

    # A transação cobre o mapa inteiro: nada do processo, da etapa nem do par do split sobrevive.
    assert Process.objects.count() == 0
    assert ProcessStep.objects.count() == 0
    assert Evidence.objects.count() == 0
    assert Finding.objects.count() == 0


@pytest.mark.django_db
@override_settings(AI_ENABLED=True, OPENAI_API_KEY="sk-teste")
def test_quem_nao_participa_do_projeto_nao_extrai(monkeypatch: pytest.MonkeyPatch) -> None:
    """O recorte é o do `ProjectScopedMixin` do viewset: a reunião alheia nem existe para quem
    não participa do projeto dela."""
    de_fora = UserFactory(role=User.Role.DELIVERY)
    meeting = _reuniao_de_discovery(UserFactory(role=User.Role.DELIVERY))
    _responde(monkeypatch, json.dumps(MAPA))
    api = APIClient()
    api.force_authenticate(de_fora)

    resposta = api.post(reverse("meeting-estruturar", args=[meeting.pk]))

    assert resposta.status_code == 404
    assert Process.objects.count() == 0


@pytest.mark.django_db
def test_vendas_nao_extrai_processos() -> None:
    """A action herda o `resource = "meeting"` do viewset, e o caso trava isso."""
    sales = UserFactory(role=User.Role.SALES)
    meeting = Meeting.objects.create(
        project=ProjectFactory(), title="Discovery", date=timezone.localdate(), transcript="ata"
    )
    api = APIClient()
    api.force_authenticate(sales)

    assert api.post(reverse("meeting-estruturar", args=[meeting.pk])).status_code == 403
