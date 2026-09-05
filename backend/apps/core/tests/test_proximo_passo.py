"""O próximo passo da conta — o leitor que a ADR 0069 tirou de "adiado" (FDD 054).

O sinal já existia inteiro: `priority.ranking_da_conta` ordena por Opportunity Score e
`recommendations.py` já emitia a recomendação `prioritization`. O que se exercita aqui é o que
`next_step.proximo_passo_da_conta` passa a permitir afirmar:

- **os quatro degraus**, cada um com o controle do degrau seguinte ao lado — sem esse par, um
  degrau que "acerta" por não olhar o estado adiante passaria despercebido;
- **a de maior score já encaminhada não esconde a seguinte**, que é a decisão inteira da função:
  ela devolve a primeira **com pendência**, não a primeira do ranking;
- **os dois vazios não são o mesmo vazio** — nada avaliado e nada pendente chegam ambos como
  `None`, e `ranked_count` é o que a tela usa para dizer qual dos dois;
- **o recorte por papel**, que é o do próprio `AccountViewSet`: Entrega não alcança conta fora do
  escopo dela;
- **o segundo leitor**, que é a metade que a decisão B1 comprou: `recommendations.py` escolhe a
  oportunidade por esta função, e não por uma query própria.
"""

from decimal import Decimal
from unittest.mock import patch

import pytest
from django.urls import reverse
from django.utils import timezone
from rest_framework.test import APIClient

from apps.core import next_step
from apps.core.models import (
    BusinessCase,
    ImprovementOpportunity,
    PipelineStage,
    SolutionHypothesis,
    User,
)
from apps.core.recommendations import build_recommendations

from .factories import (
    AccountFactory,
    BusinessCaseFactory,
    CommercialOpportunityFactory,
    ImprovementOpportunityFactory,
    PipelineStageFactory,
    PriorityAssessmentFactory,
    ProjectFactory,
    ProjectMemberFactory,
    SolutionHypothesisFactory,
    UserFactory,
)

pytestmark = pytest.mark.django_db


@pytest.fixture
def api() -> APIClient:
    client = APIClient()
    client.force_authenticate(UserFactory(role=User.Role.ADMIN))
    return client


def avaliada(conta, titulo: str = "Conferência manual de notas", **notas):
    """Uma oportunidade **ranqueável**: viva, não descartada e com avaliação vigente.

    As cinco dimensões vêm da fábrica (3/3/3/3/3 → 60,00) quando ninguém as informa; quem precisa
    de ordem entre duas passa as notas, porque é o score que ordena — nunca a data de criação.
    """
    oportunidade = ImprovementOpportunityFactory(
        account=conta, title=titulo, status=ImprovementOpportunity.Status.PRIORITIZED
    )
    PriorityAssessmentFactory(improvement_opportunity=oportunidade, **notas)
    return oportunidade


def com_hipotese_escolhida(oportunidade) -> SolutionHypothesis:
    """A hipótese escolhida da oportunidade, criada se ainda não houver.

    Reaproveita em vez de criar sempre porque a constraint parcial recusa a segunda escolhida viva
    — e um teste que a violasse morreria com `IntegrityError` em vez de dizer o que queria dizer.
    """
    existente = oportunidade.hypotheses.filter(
        status=SolutionHypothesis.Status.CHOSEN, archived_at__isnull=True
    ).first()
    return existente or SolutionHypothesisFactory(
        improvement_opportunity=oportunidade, status=SolutionHypothesis.Status.CHOSEN
    )


def decidido(oportunidade, outcome: str) -> BusinessCase:
    """Um business case **decidido**, com autor e carimbo — o `clean()` do modelo exige os dois."""
    return BusinessCaseFactory(
        improvement_opportunity=oportunidade,
        solution_hypothesis=com_hipotese_escolhida(oportunidade),
        status=outcome,
        decided_by=UserFactory(),
        decided_at=timezone.now(),
    )


# --- Os quatro degraus, cada um com o controle do seguinte ---------------------------------------


def test_o_vocabulario_publicado_sao_os_quatro_degraus() -> None:
    """O esquema publica `DEGRAUS` como enum, e a união `AccountNextStepMissing` do TypeScript é o
    espelho dela. Congelar aqui é o que faz um degrau novo — ou renomeado — ficar vermelho deste
    lado antes de a tela cair num `undefined` do outro, que é onde a divergência não avisa."""
    assert next_step.DEGRAUS == (
        "choose_hypothesis",
        "build_business_case",
        "decide_investment",
        "open_commercial_opportunity",
    )


def test_sem_hipotese_escolhida_o_degrau_e_escolher_a_hipotese() -> None:
    """Uma hipótese **proposta** não encerra o degrau: propor é o estado normal de várias
    concorrentes (FDD 048), e escolher é o ato que a fase seguinte espera."""
    conta = AccountFactory()
    oportunidade = avaliada(conta)
    SolutionHypothesisFactory(
        improvement_opportunity=oportunidade, status=SolutionHypothesis.Status.PROPOSED
    )

    passo = next_step.proximo_passo_da_conta(conta)

    assert passo == {
        "improvement_opportunity": oportunidade.pk,
        "title": "Conferência manual de notas",
        "score": "60.00",
        "assessment_version": 1,
        "missing": next_step.DEGRAU_ESCOLHER_HIPOTESE,
    }


def test_a_hipotese_escolhida_e_arquivada_devolve_o_primeiro_degrau() -> None:
    """A constraint parcial é condicional ao arquivamento, e a leitura tem de ser igual: uma
    escolha desfeita volta a ser escolha por fazer."""
    conta = AccountFactory()
    oportunidade = avaliada(conta)
    com_hipotese_escolhida(oportunidade).archive()

    passo = next_step.proximo_passo_da_conta(conta)

    assert passo is not None
    assert passo["missing"] == next_step.DEGRAU_ESCOLHER_HIPOTESE


def test_com_hipotese_escolhida_e_sem_business_case_o_degrau_e_montar_o_business_case() -> None:
    conta = AccountFactory()
    oportunidade = avaliada(conta)
    com_hipotese_escolhida(oportunidade)

    passo = next_step.proximo_passo_da_conta(conta)

    assert passo is not None
    assert passo["missing"] == next_step.DEGRAU_MONTAR_BUSINESS_CASE


def test_o_business_case_arquivado_nao_conta_como_montado() -> None:
    """O controle do degrau 2: arquivar o orçamento devolve a oportunidade ao degrau anterior, em
    vez de deixá-la parada num degrau que já não tem objeto."""
    conta = AccountFactory()
    oportunidade = avaliada(conta)
    hipotese = com_hipotese_escolhida(oportunidade)
    BusinessCaseFactory(
        improvement_opportunity=oportunidade, solution_hypothesis=hipotese
    ).archive()

    passo = next_step.proximo_passo_da_conta(conta)

    assert passo is not None
    assert passo["missing"] == next_step.DEGRAU_MONTAR_BUSINESS_CASE


def test_com_business_case_em_rascunho_o_degrau_e_decidir_o_investimento() -> None:
    conta = AccountFactory()
    oportunidade = avaliada(conta)
    BusinessCaseFactory(
        improvement_opportunity=oportunidade,
        solution_hypothesis=com_hipotese_escolhida(oportunidade),
    )

    passo = next_step.proximo_passo_da_conta(conta)

    assert passo is not None
    assert passo["missing"] == next_step.DEGRAU_DECIDIR_INVESTIMENTO


def test_o_rascunho_vence_o_aprovado_quando_os_dois_existem() -> None:
    """Só a aprovação é única por oportunidade; rascunhos convivem. A ordem da cadeia decide, e o
    degrau que aparece é o da decisão que ainda falta."""
    conta = AccountFactory()
    oportunidade = avaliada(conta)
    decidido(oportunidade, BusinessCase.Status.APPROVED)
    BusinessCaseFactory(
        improvement_opportunity=oportunidade,
        solution_hypothesis=com_hipotese_escolhida(oportunidade),
    )

    passo = next_step.proximo_passo_da_conta(conta)

    assert passo is not None
    assert passo["missing"] == next_step.DEGRAU_DECIDIR_INVESTIMENTO


def test_com_investimento_aprovado_e_sem_venda_aberta_o_degrau_e_abrir_a_venda() -> None:
    conta = AccountFactory()
    oportunidade = avaliada(conta)
    decidido(oportunidade, BusinessCase.Status.APPROVED)

    passo = next_step.proximo_passo_da_conta(conta)

    assert passo is not None
    assert passo["missing"] == next_step.DEGRAU_ABRIR_VENDA


def test_a_venda_aberta_na_conta_encerra_o_quarto_degrau() -> None:
    """A consequência declarada da heurística: **não há FK entre melhoria e venda** (§5), então a
    pergunta é da conta — e qualquer venda aberta encerra o degrau, mesmo sendo de outro assunto."""
    conta = AccountFactory()
    oportunidade = avaliada(conta)
    decidido(oportunidade, BusinessCase.Status.APPROVED)
    CommercialOpportunityFactory(
        account=conta,
        title="Continuidade 2027 — nada a ver com esta melhoria",
        stage=PipelineStageFactory(kind=PipelineStage.Kind.OPEN),
    )

    assert next_step.proximo_passo_da_conta(conta) is None
    assert next_step.oportunidades_ranqueadas(conta) == 1


def test_a_venda_ganha_nao_encerra_o_quarto_degrau() -> None:
    """O controle da regra acima: o degrau pergunta por venda **aberta**, e uma venda já fechada
    não é conversa comercial em curso."""
    conta = AccountFactory()
    oportunidade = avaliada(conta)
    decidido(oportunidade, BusinessCase.Status.APPROVED)
    CommercialOpportunityFactory(
        account=conta, stage=PipelineStage.objects.get(kind=PipelineStage.Kind.WON)
    )

    passo = next_step.proximo_passo_da_conta(conta)

    assert passo is not None
    assert passo["missing"] == next_step.DEGRAU_ABRIR_VENDA


def test_a_venda_aberta_de_outra_conta_nao_encerra_o_degrau() -> None:
    """A fronteira da heurística: ela é da conta, e não da carteira."""
    conta = AccountFactory()
    oportunidade = avaliada(conta)
    decidido(oportunidade, BusinessCase.Status.APPROVED)
    CommercialOpportunityFactory(stage=PipelineStageFactory(kind=PipelineStage.Kind.OPEN))

    passo = next_step.proximo_passo_da_conta(conta)

    assert passo is not None
    assert passo["missing"] == next_step.DEGRAU_ABRIR_VENDA


def test_o_investimento_recusado_nao_e_pendencia() -> None:
    """Recusar é decisão tomada. Insistir seria o produto discordando de quem decidiu — e a
    oportunidade sai da fila, em vez de travá-la."""
    conta = AccountFactory()
    oportunidade = avaliada(conta)
    decidido(oportunidade, BusinessCase.Status.REJECTED)

    assert next_step.proximo_passo_da_conta(conta) is None
    assert next_step.oportunidades_ranqueadas(conta) == 1


# --- A decisão inteira: encaminhada não esconde a seguinte ---------------------------------------


def test_a_de_maior_score_ja_encaminhada_nao_esconde_a_seguinte() -> None:
    """**O critério é "a primeira com pendência", e não "a de maior score".**

    Sem isto, a conta cuja melhor oportunidade já foi decidida ficaria sem próximo passo enquanto
    a segunda espera hipótese — o painel diria "nada pendente" com trabalho por fazer embaixo.
    """
    conta = AccountFactory()
    campea = avaliada(
        conta, "Campeã", impact=5, evidence_strength=5, feasibility=5, time_to_value=5, economics=5
    )
    segunda = avaliada(conta, "Segunda")
    decidido(campea, BusinessCase.Status.REJECTED)
    CommercialOpportunityFactory(
        account=conta, stage=PipelineStageFactory(kind=PipelineStage.Kind.OPEN)
    )

    passo = next_step.proximo_passo_da_conta(conta)

    assert passo is not None
    assert passo["improvement_opportunity"] == segunda.pk
    assert passo["title"] == "Segunda"
    assert passo["score"] == "60.00"
    assert passo["missing"] == next_step.DEGRAU_ESCOLHER_HIPOTESE
    # O controle que impede o teste de passar por acidente de ordenação: a campeã **é** a primeira
    # do ranking, e é justamente por já estar encaminhada que ela não é a resposta.
    assert next_step.oportunidades_ranqueadas(conta) == 2


def test_a_ordem_e_a_do_score_entre_duas_pendentes() -> None:
    """O outro lado do teste acima: com as duas pendentes, quem responde é o ranking."""
    conta = AccountFactory()
    avaliada(conta, "Menor")
    campea = avaliada(
        conta, "Campeã", impact=5, evidence_strength=5, feasibility=5, time_to_value=5, economics=5
    )

    passo = next_step.proximo_passo_da_conta(conta)

    assert passo is not None
    assert passo["improvement_opportunity"] == campea.pk
    assert passo["score"] == "100.00"


# --- Os dois vazios ------------------------------------------------------------------------------


def test_conta_sem_oportunidade_avaliada_nao_tem_proximo_passo() -> None:
    """O vazio honesto: sem avaliação não há por onde ordenar, e a tela diz isso em vez de
    inventar uma fila."""
    conta = AccountFactory()
    ImprovementOpportunityFactory(account=conta)

    assert next_step.proximo_passo_da_conta(conta) is None
    assert next_step.oportunidades_ranqueadas(conta) == 0


def test_a_descartada_nao_entra_na_fila() -> None:
    """Delegado a `ranking_da_conta`, e afirmado aqui porque é o conjunto que esta função percorre:
    uma descartada no topo seria uma lista de trabalho apontando para lugar nenhum."""
    conta = AccountFactory()
    descartada = ImprovementOpportunityFactory(
        account=conta, status=ImprovementOpportunity.Status.DISCARDED
    )
    PriorityAssessmentFactory(
        improvement_opportunity=descartada,
        impact=5,
        evidence_strength=5,
        feasibility=5,
        time_to_value=5,
        economics=5,
    )
    pendente = avaliada(conta, "A que sobra")

    passo = next_step.proximo_passo_da_conta(conta)

    assert passo is not None
    assert passo["improvement_opportunity"] == pendente.pk


def test_a_oportunidade_de_outra_conta_nao_entra() -> None:
    conta = AccountFactory()
    avaliada(AccountFactory(), "De outra conta")

    assert next_step.proximo_passo_da_conta(conta) is None


def test_tudo_encaminhado_e_neutro_e_nao_vazio() -> None:
    """Os dois `None` se distinguem por `ranked_count`: aqui há três avaliadas e nenhuma pendência,
    e a tela mostra "nada pendente" — nunca o vazio de quem não avaliou nada."""
    conta = AccountFactory()
    for indice in range(3):
        decidido(avaliada(conta, f"Encaminhada {indice}"), BusinessCase.Status.APPROVED)
    CommercialOpportunityFactory(
        account=conta, stage=PipelineStageFactory(kind=PipelineStage.Kind.OPEN)
    )

    assert next_step.proximo_passo_da_conta(conta) is None
    assert next_step.oportunidades_ranqueadas(conta) == 3


# --- A rota --------------------------------------------------------------------------------------


def test_a_rota_devolve_o_degrau_e_a_contagem(api: APIClient) -> None:
    conta = AccountFactory()
    oportunidade = avaliada(conta)

    resposta = api.get(reverse("client-next-step", args=[conta.pk]))

    assert resposta.status_code == 200, resposta.data
    assert resposta.data == {
        "next_step": {
            "improvement_opportunity": oportunidade.pk,
            "title": "Conferência manual de notas",
            "score": "60.00",
            "assessment_version": 1,
            "missing": "choose_hypothesis",
        },
        "ranked_count": 1,
    }


def test_a_rota_devolve_nulo_sem_oportunidade_avaliada(api: APIClient) -> None:
    conta = AccountFactory()

    resposta = api.get(reverse("client-next-step", args=[conta.pk]))

    assert resposta.status_code == 200, resposta.data
    assert resposta.data == {"next_step": None, "ranked_count": 0}


def test_a_rota_canonica_da_v2_responde_igual(api: APIClient) -> None:
    """A action nasce nas duas versões de uma vez: o router da v2 é derivado do `registry` da v1
    (`urls.py`), e por isso `/accounts/{id}/next-step/` existe sem nenhuma linha a mais."""
    conta = AccountFactory()
    avaliada(conta)

    v1 = api.get(reverse("client-next-step", args=[conta.pk]))
    v2 = api.get(reverse("v2-client-next-step", args=[conta.pk]))

    assert v2.status_code == 200, v2.data
    assert v2.data == v1.data


def test_entrega_nao_alcanca_o_proximo_passo_de_conta_fora_do_escopo() -> None:
    """O recorte é o do próprio `AccountViewSet` (RFC 0003): `get_object()` filtra pelo escopo, e
    a conta de fora responde 404 — não 403, porque para a Entrega ela não existe."""
    minha = AccountFactory()
    alheia = AccountFactory()
    entrega = UserFactory(role=User.Role.DELIVERY)
    ProjectMemberFactory(project=ProjectFactory(engagement__account=minha), user=entrega)
    avaliada(minha, "Minha")
    avaliada(alheia, "Alheia")
    api = APIClient()
    api.force_authenticate(entrega)

    assert api.get(reverse("client-next-step", args=[alheia.pk])).status_code == 404
    minha_resposta = api.get(reverse("client-next-step", args=[minha.pk]))
    assert minha_resposta.status_code == 200, minha_resposta.data
    assert minha_resposta.data["next_step"]["title"] == "Minha"


# --- O segundo leitor: `recommendations.py` ------------------------------------------------------


def test_a_recomendacao_acompanha_o_degrau_e_a_conta_nao_some_da_lista() -> None:
    """Um leitor só, e **nenhuma conta some por causa do degrau em que ela está**.

    A campeã já escolheu a hipótese: o passo dela é montar o business case, e é ela a resposta da
    conta — a segunda, ainda no degrau 1, não a substitui. A recomendação segue a mesma resposta e
    troca a **frase**, não a existência: emitir só o primeiro degrau fazia a conta inteira
    desaparecer de `/indicadores` enquanto o painel do detalhe dela mostrava o passo, e dois
    leitores que discordam por omissão são o que a decisão B1 comprou a função única para evitar.
    """
    conta = AccountFactory()
    campea = avaliada(
        conta, "Campeã", impact=5, evidence_strength=5, feasibility=5, time_to_value=5, economics=5
    )
    segunda = avaliada(conta, "Segunda")
    com_hipotese_escolhida(campea)

    passo = next_step.proximo_passo_da_conta(conta)
    assert passo is not None
    assert passo["improvement_opportunity"] == campea.pk
    assert passo["missing"] == next_step.DEGRAU_MONTAR_BUSINESS_CASE
    assert segunda.pk != campea.pk

    itens = [rec for rec in build_recommendations() if rec["kind"] == "prioritization"]

    assert len(itens) == 1
    assert itens[0]["label"] == f"Próximo passo em {conta.name}: {campea.title}"
    assert itens[0]["detail"].endswith("hipótese escolhida e ainda sem business case.")
    assert itens[0]["url"] == f"/contas/{conta.pk}/priorizacao"


@pytest.mark.django_db
def test_cada_degrau_tem_a_frase_dele_na_recomendacao() -> None:
    """As quatro frases existem e são distintas — degrau novo sem frase estoura no `KeyError`."""
    from apps.core.recommendations import _DETALHE_POR_DEGRAU

    assert set(_DETALHE_POR_DEGRAU) == set(next_step.DEGRAUS)
    assert len(set(_DETALHE_POR_DEGRAU.values())) == len(next_step.DEGRAUS)


def test_a_recomendacao_usa_o_score_em_texto_com_duas_casas() -> None:
    """O `detail` cita o número como a API o publica (ADR 0068) — nunca `Decimal("60")` cru."""
    conta = AccountFactory()
    avaliada(conta, "Conferência manual de notas")

    prioritizacao = [
        rec for rec in build_recommendations() if rec["kind"] == "prioritization"
    ]

    assert len(prioritizacao) == 1
    assert prioritizacao[0]["detail"].startswith("Opportunity Score 60.00 (v1) —")


def test_a_venda_aberta_e_perguntada_uma_vez_por_conta() -> None:
    """A memoização não é micro-otimização: `build_recommendations` chama esta função **uma vez por
    conta da carteira**, e uma consulta por oportunidade encaminhada cresceria com o histórico da
    relação — justamente nas contas antigas, que são as que têm mais oportunidades ranqueadas."""
    conta = AccountFactory()
    for indice in range(3):
        decidido(avaliada(conta, f"Encaminhada {indice}"), BusinessCase.Status.APPROVED)

    with patch.object(next_step, "tem_venda_aberta", return_value=True) as pergunta:
        assert next_step.proximo_passo_da_conta(conta) is None

    assert pergunta.call_count == 1


def test_a_pergunta_da_venda_aberta_e_a_mesma_do_upsell() -> None:
    """`tem_venda_aberta` é pública porque `build_recommendations` faz a mesma pergunta na regra de
    `upsell`: duas expressões de "esta conta tem venda em aberto" divergiriam."""
    conta = AccountFactory()

    assert next_step.tem_venda_aberta(conta) is False
    CommercialOpportunityFactory(
        account=conta,
        estimated_value=Decimal("10000.00"),
        stage=PipelineStageFactory(kind=PipelineStage.Kind.OPEN),
    )
    assert next_step.tem_venda_aberta(conta) is True
