"""A Discovery Session — a tela usada **durante** a reunião, e o backend que a sustenta (FDD 055).

O que se exercita aqui:

- **o id estável**, que é a decisão do módulo `discovery_questions`: reordenar a base não move
  resposta gravada, e o teste que prova isso reordena a constante de verdade;
- **o bloco como unidade de escrita**, que é o que torna a decisão H3 do DAP administrável —
  gravar um bloco preserva os outros, e `notes` não tem caminho de escrita por `PATCH`;
- **a recusa que não é descarte**: bloco desconhecido e pergunta desconhecida são 400, com o nome
  do que não existe;
- **a estruturação como ato à parte** (decisão C1): ela é a única porta que grava `Finding`, e o
  que a tela faz é gravar texto. A invariante "todo achado nasce hipótese" mora na regressão
  `tests/regression/test_a_extracao_nasce_hipotese.py`, com as duas origens;
- **o recorte por projeto**, que é o do próprio `DiscoverySessionViewSet`.
"""

import json

import pytest
from django.test import override_settings
from django.urls import reverse
from django.utils import timezone
from rest_framework.test import APIClient

from apps.core import ai, discovery_questions
from apps.core.discovery_questions import DiscoveryBlock, DiscoveryQuestion
from apps.core.models import DiscoverySession, Finding, Process, ProcessObservation, User

from .factories import (
    DiscoveryFactory,
    DiscoverySessionFactory,
    ProcessFactory,
    ProcessObservationFactory,
    ProjectFactory,
    ProjectMemberFactory,
    UserFactory,
)

pytestmark = pytest.mark.django_db

MAPA_EXTRAIDO = json.dumps([{
    "name": "Conferência de repasse",
    "etapas": [{"name": "Conferir o extrato", "tempo": "Dois dias"}],
    "achados": ["São quatrocentas notas por mês.", "O fechamento leva dois dias."],
}])


@pytest.fixture
def sessao() -> DiscoverySession:
    return DiscoverySessionFactory(discovery=DiscoveryFactory())


@pytest.fixture
def api(sessao: DiscoverySession) -> APIClient:
    """Entrega **de dentro** do projeto: o recorte é o do viewset, e o caso comum é quem participa."""
    usuario = UserFactory(role=User.Role.DELIVERY)
    ProjectMemberFactory(project=sessao.discovery.project, user=usuario)
    client = APIClient()
    client.force_authenticate(usuario)
    return client


def _gravar(api: APIClient, sessao: DiscoverySession, bloco: str, respostas: dict):
    return api.post(
        reverse("discoverysession-notes", args=[sessao.pk]),
        {"block": bloco, "answers": respostas},
        format="json",
    )


# --------------------------------------------------------------------------------------------
# A base de perguntas (decisão E1)
# --------------------------------------------------------------------------------------------


def test_a_base_sai_pela_rota_com_os_seis_blocos(api: APIClient) -> None:
    resposta = api.get(reverse("discovery-questions"))

    assert resposta.status_code == 200, resposta.data
    blocos = resposta.data["blocks"]
    assert [bloco["id"] for bloco in blocos] == ["a", "b", "c", "d", "e", "f"]
    assert all(bloco["label"] and bloco["short_label"] for bloco in blocos)
    # Toda pergunta tem id e texto — uma sem id seria uma resposta sem onde ser gravada.
    assert all(
        pergunta["id"] and pergunta["text"]
        for bloco in blocos
        for pergunta in bloco["questions"]
    )


def test_a_rota_da_base_existe_nas_duas_versoes(api: APIClient) -> None:
    v1 = api.get(reverse("discovery-questions"))
    v2 = api.get(reverse("v2-discovery-questions"))

    assert v1.status_code == v2.status_code == 200
    assert v1.data == v2.data


def test_o_id_de_pergunta_e_unico_na_base_inteira() -> None:
    """Único no bloco basta para a gravação; único na base inteira é o que permite migrar depois.

    Uma pergunta que sobe de vertical para a base genérica pode mudar de bloco (é o que a ficha do
    Notion descreve em "Como esta base evolui"), e id repetido entre blocos faria essa mudança
    parecer uma pergunta nova quando é a mesma.
    """
    ids = [
        pergunta.id
        for bloco in discovery_questions.BLOCKS
        for pergunta in bloco.questions
    ]

    assert len(ids) == len(set(ids))
    assert all(id_.islower() and " " not in id_ for id_ in ids)


def test_bloco_desconhecido_nao_tem_pergunta_nem_bloco() -> None:
    assert discovery_questions.block("z") is None
    assert discovery_questions.question_ids("z") == frozenset()


# --------------------------------------------------------------------------------------------
# O id estável — o teste que a decisão do módulo existe para permitir
# --------------------------------------------------------------------------------------------


def test_reordenar_a_base_nao_move_resposta_gravada(
    api: APIClient, sessao: DiscoverySession, monkeypatch: pytest.MonkeyPatch
) -> None:
    """O defeito que o slug impede, encenado.

    Grava-se a resposta de uma pergunta; insere-se **outra** no começo do mesmo bloco; lê-se de
    novo. Guardada por índice, a citação de reunião passaria a responder a pergunta errada — sem
    erro, sem log, sem nada vermelho. Guardada por id, ela continua onde estava.

    O controle positivo é a segunda asserção: a posição da pergunta **mudou de verdade**, senão o
    teste passaria por a reordenação não ter acontecido.
    """
    original = discovery_questions.BLOCK_BY_ID["b"]
    _gravar(api, sessao, "b", {"casos-por-mes": "Umas quatrocentas, e no fechamento passa de 600."})

    nova = DiscoveryQuestion(id="quem-abre-o-caso", text="Quem abre o caso?")
    reordenado = DiscoveryBlock(
        id=original.id, label=original.label, short_label=original.short_label,
        note=original.note, questions=(nova, *original.questions),
    )
    monkeypatch.setitem(discovery_questions.BLOCK_BY_ID, "b", reordenado)

    # Controle positivo: a pergunta **mudou mesmo** de lugar. Sem isto o teste passaria por a
    # reordenação não ter acontecido.
    assert [p.id for p in reordenado.questions].index("casos-por-mes") != [
        p.id for p in original.questions
    ].index("casos-por-mes")

    gravado = api.get(reverse("discoverysession-detail", args=[sessao.pk])).data["notes"]
    # O pareamento que a tela faz: percorre a base atual e busca a resposta pelo id da pergunta.
    pareado = {p.text: gravado["b"].get(p.id, "") for p in reordenado.questions}
    assert pareado["Quantos casos desse tipo passam por aqui num mês?"] == (
        "Umas quatrocentas, e no fechamento passa de 600."
    )
    # E a pergunta que passou a ocupar a posição de antes continua sem resposta, em vez de herdar
    # a de outra — que é exatamente o que o índice teria feito.
    assert pareado["Quem abre o caso?"] == ""


def test_a_resposta_de_pergunta_removida_da_base_continua_gravada(
    api: APIClient, sessao: DiscoverySession, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A consequência declarada da remoção: ela some da tela e **não** é apagada do registro.

    E o bloco vizinho continua salvável — revalidar o conjunto inteiro a cada escrita faria uma
    edição de catálogo travar o registro de uma reunião que não se repete.
    """
    _gravar(api, sessao, "b", {"casos-por-mes": "Umas quatrocentas."})
    original = discovery_questions.BLOCK_BY_ID["b"]
    sem_a_pergunta = DiscoveryBlock(
        id=original.id, label=original.label, short_label=original.short_label,
        note=original.note,
        questions=tuple(p for p in original.questions if p.id != "casos-por-mes"),
    )
    monkeypatch.setitem(discovery_questions.BLOCK_BY_ID, "b", sem_a_pergunta)

    outro = _gravar(api, sessao, "a", {"o-que-mais-incomoda": "O fechamento atrasa."})

    assert outro.status_code == 200, outro.data
    sessao.refresh_from_db()
    assert sessao.notes["b"] == {"casos-por-mes": "Umas quatrocentas."}


# --------------------------------------------------------------------------------------------
# A escrita: o bloco é a unidade
# --------------------------------------------------------------------------------------------


def test_gravar_um_bloco_preserva_os_outros(api: APIClient, sessao: DiscoverySession) -> None:
    """A metade que a decisão H3 depende: a mitigação de uso é *um bloco por pessoa*."""
    _gravar(api, sessao, "a", {"o-que-mais-incomoda": "O fechamento atrasa todo mês."})
    resposta = _gravar(api, sessao, "b", {"casos-por-mes": "Umas quatrocentas."})

    assert resposta.status_code == 200, resposta.data
    assert resposta.data["notes"] == {
        "a": {"o-que-mais-incomoda": "O fechamento atrasa todo mês."},
        "b": {"casos-por-mes": "Umas quatrocentas."},
    }
    # O carimbo que a tela mostra como "última versão salva às 14:38" vem no corpo da resposta.
    assert resposta.data["updated_at"]


def test_regravar_o_mesmo_bloco_troca_o_conteudo_dele(
    api: APIClient, sessao: DiscoverySession
) -> None:
    """Última escrita vence **dentro** do bloco — é literalmente a decisão H3, e sem aviso."""
    _gravar(api, sessao, "b", {"casos-por-mes": "Umas quatrocentas."})
    _gravar(api, sessao, "b", {"casos-por-mes": "Quatrocentas, e 600 no fechamento."})

    sessao.refresh_from_db()
    assert sessao.notes["b"] == {"casos-por-mes": "Quatrocentas, e 600 no fechamento."}


def test_texto_em_branco_e_gravado_como_veio(api: APIClient, sessao: DiscoverySession) -> None:
    """Apagar o que se escreveu é uma escrita como outra — não um pedido para não gravar."""
    _gravar(api, sessao, "b", {"casos-por-mes": "Umas quatrocentas."})
    _gravar(api, sessao, "b", {"casos-por-mes": ""})

    sessao.refresh_from_db()
    assert sessao.notes["b"] == {"casos-por-mes": ""}


def test_bloco_desconhecido_e_recusado_dizendo_os_que_existem(
    api: APIClient, sessao: DiscoverySession
) -> None:
    resposta = _gravar(api, sessao, "z", {"casos-por-mes": "…"})

    assert resposta.status_code == 400, resposta.data
    assert "z" in str(resposta.data)
    sessao.refresh_from_db()
    assert sessao.notes == {}


def test_pergunta_desconhecida_e_recusada_nomeando_a_chave(
    api: APIClient, sessao: DiscoverySession
) -> None:
    """400 e não descarte silencioso: gravar assim mesmo produziria resposta que nenhuma tela lê."""
    resposta = _gravar(api, sessao, "b", {"pergunta-inventada": "…"})

    assert resposta.status_code == 400, resposta.data
    assert "pergunta-inventada" in str(resposta.data)
    sessao.refresh_from_db()
    assert sessao.notes == {}


def test_a_pergunta_do_bloco_vizinho_nao_entra_neste(
    api: APIClient, sessao: DiscoverySession
) -> None:
    """Id que existe na base, mas não neste bloco: a validação é **por bloco**, não pela base."""
    resposta = _gravar(api, sessao, "b", {"o-que-mais-incomoda": "…"})

    assert resposta.status_code == 400, resposta.data


def test_notes_nao_tem_caminho_de_escrita_por_patch(
    api: APIClient, sessao: DiscoverySession
) -> None:
    """Um `PATCH` do campo inteiro apagaria os cinco blocos que não vieram — e em silêncio."""
    _gravar(api, sessao, "b", {"casos-por-mes": "Umas quatrocentas."})

    resposta = api.patch(
        reverse("discoverysession-detail", args=[sessao.pk]),
        {"notes": {"b": {"casos-por-mes": "outra coisa"}}},
        format="json",
    )

    assert resposta.status_code == 200, resposta.data
    sessao.refresh_from_db()
    assert sessao.notes["b"] == {"casos-por-mes": "Umas quatrocentas."}


def test_entrega_de_fora_do_projeto_nao_alcanca_a_sessao(sessao: DiscoverySession) -> None:
    de_fora = UserFactory(role=User.Role.DELIVERY)
    ProjectMemberFactory(project=ProjectFactory(), user=de_fora)
    client = APIClient()
    client.force_authenticate(de_fora)

    resposta = _gravar(client, sessao, "b", {"casos-por-mes": "…"})

    assert resposta.status_code == 404, resposta.data


# --------------------------------------------------------------------------------------------
# A estruturação — ato à parte, depois da sessão (decisão C1)
# --------------------------------------------------------------------------------------------


@override_settings(AI_ENABLED=True, OPENAI_API_KEY="sk-teste")
def test_estruturar_a_sessao_mapeia_processo_achado_e_observacao(
    api: APIClient, sessao: DiscoverySession, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(ai, "complete", lambda s, u, **_: (MAPA_EXTRAIDO, {"prompt_tokens": 1}))
    _gravar(api, sessao, "b", {"casos-por-mes": "Umas quatrocentas, e 600 no fechamento."})

    resposta = api.post(reverse("discoverysession-estruturar", args=[sessao.pk]))

    assert resposta.status_code == 200, resposta.data
    assert [p["name"] for p in resposta.data["processos"]] == ["Conferência de repasse"]
    assert Finding.objects.count() == 2
    # A observação é o que faz "esta sessão já foi estruturada" ser fato no schema — inclusive
    # para o processo que não rendeu achado nenhum e por isso não tem `Evidence`.
    observacao = ProcessObservation.objects.get()
    assert observacao.source_session_id == sessao.pk
    assert observacao.discovery_id == sessao.discovery_id
    assert observacao.observed_at == timezone.localtime(sessao.happened_at).date()


@override_settings(AI_ENABLED=True, OPENAI_API_KEY="sk-teste")
def test_a_extracao_entra_depois_do_que_foi_mapeado_a_mao(
    api: APIClient, sessao: DiscoverySession, monkeypatch: pytest.MonkeyPatch
) -> None:
    """`position` é a ordem em que a operação acontece — o modelo não intercala o que alguém montou."""
    monkeypatch.setattr(ai, "complete", lambda s, u, **_: (MAPA_EXTRAIDO, {"prompt_tokens": 1}))
    conta = sessao.discovery.project.engagement.account
    ProcessFactory(account=conta, name="Cadastro de prestador", position=7)
    _gravar(api, sessao, "b", {"casos-por-mes": "Umas quatrocentas."})

    api.post(reverse("discoverysession-estruturar", args=[sessao.pk]))

    assert Process.objects.get(name="Conferência de repasse").position == 8


@override_settings(AI_ENABLED=True, OPENAI_API_KEY="sk-teste")
def test_sessao_sem_nada_anotado_nao_vai_a_ia(
    api: APIClient, sessao: DiscoverySession, monkeypatch: pytest.MonkeyPatch
) -> None:
    """400 **antes** do provedor: a cota de quem clicou não se gasta lendo seis blocos em branco."""
    def nao_deveria(*_args: object, **_kwargs: object) -> None:  # pragma: no cover
        raise AssertionError("a IA foi chamada para uma sessão vazia")

    monkeypatch.setattr(ai, "complete", nao_deveria)
    _gravar(api, sessao, "b", {"casos-por-mes": "   "})

    resposta = api.post(reverse("discoverysession-estruturar", args=[sessao.pk]))

    assert resposta.status_code == 400, resposta.data


@override_settings(AI_ENABLED=True, OPENAI_API_KEY="sk-teste")
def test_estruturar_duas_vezes_e_recusado_com_409(
    api: APIClient, sessao: DiscoverySession, monkeypatch: pytest.MonkeyPatch
) -> None:
    """`Process` não tem rascunho: a segunda extração dobraria o mapa da operação em silêncio."""
    monkeypatch.setattr(ai, "complete", lambda s, u, **_: (MAPA_EXTRAIDO, {"prompt_tokens": 1}))
    _gravar(api, sessao, "b", {"casos-por-mes": "Umas quatrocentas."})
    api.post(reverse("discoverysession-estruturar", args=[sessao.pk]))

    de_novo = api.post(reverse("discoverysession-estruturar", args=[sessao.pk]))

    assert de_novo.status_code == 409, de_novo.data
    assert Process.objects.count() == 1


def test_a_sessao_publica_quantos_achados_sairam_dela(
    api: APIClient, sessao: DiscoverySession, monkeypatch: pytest.MonkeyPatch
) -> None:
    """O número que a tela mostra no estado "já estruturada", contado pelo servidor."""
    with override_settings(AI_ENABLED=True, OPENAI_API_KEY="sk-teste"):
        monkeypatch.setattr(ai, "complete", lambda s, u, **_: (MAPA_EXTRAIDO, {"prompt_tokens": 1}))
        _gravar(api, sessao, "b", {"casos-por-mes": "Umas quatrocentas."})
        api.post(reverse("discoverysession-estruturar", args=[sessao.pk]))

    detalhe = api.get(reverse("discoverysession-detail", args=[sessao.pk]))

    assert detalhe.data["structured_finding_count"] == 2
    # Achado arquivado sai da conta: o painel diz o que está vivo.
    Finding.objects.first().archive()  # type: ignore[union-attr]
    assert api.get(
        reverse("discoverysession-detail", args=[sessao.pk])
    ).data["structured_finding_count"] == 1


def test_sessao_recem_criada_nao_tem_achado_nem_anotacao(
    api: APIClient, sessao: DiscoverySession
) -> None:
    """A criação responde com a instância recém-salva, que não passa pela queryset anotada."""
    discovery = sessao.discovery

    resposta = api.post(
        reverse("discoverysession-list"),
        {"discovery": discovery.pk, "happened_at": timezone.now().isoformat()},
        format="json",
    )

    assert resposta.status_code == 201, resposta.data
    assert resposta.data["notes"] == {}
    assert resposta.data["structured_finding_count"] == 0


def test_a_observacao_da_sessao_sai_com_o_nome_do_processo(
    api: APIClient, sessao: DiscoverySession
) -> None:
    """O caminho para os processos, no estado "já estruturada" — sem uma chamada por linha."""
    processo = ProcessFactory(account=sessao.discovery.project.engagement.account)
    ProcessObservationFactory(
        discovery=sessao.discovery, process=processo, source_session=sessao
    )

    resposta = api.get(
        reverse("processobservation-list"), {"source_session": sessao.pk}
    )

    assert resposta.status_code == 200, resposta.data
    assert [linha["process_name"] for linha in resposta.data] == [processo.name]


# --------------------------------------------------------------------------------------------
# O contexto que vai ao modelo
# --------------------------------------------------------------------------------------------


def test_o_contexto_leva_a_pergunta_junto_da_resposta(sessao: DiscoverySession) -> None:
    """Sem a pergunta, o modelo receberia frases soltas e teria de adivinhar o que cada uma responde."""
    sessao.notes = {"b": {"casos-por-mes": "Umas quatrocentas.", "o-que-volta-para-refazer": ""}}

    contexto = ai.build_discovery_session_context(sessao)

    assert "Quantos casos desse tipo passam por aqui num mês?" in contexto
    assert "Umas quatrocentas." in contexto
    # Pergunta sem resposta não entra: mandar as 36 com trinta vazias gastaria o prompt à toa.
    assert "O que volta para refazer" not in contexto


def test_o_contexto_leva_a_transcricao_atras_das_anotacoes(sessao: DiscoverySession) -> None:
    sessao.notes = {"b": {"casos-por-mes": "Umas quatrocentas."}}
    sessao.transcript = "Fala do coordenador sobre o fechamento."

    contexto = ai.build_discovery_session_context(sessao)

    assert contexto.index("Umas quatrocentas.") < contexto.index("Transcrição:")
