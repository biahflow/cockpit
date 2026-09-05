"""O Business Case: a justificativa do investimento (FDD 053, ADR 0069).

A decisão de investir não tinha onde morar. O que se exercita aqui é o que o modelo passa a
permitir afirmar:

- **o custo do estado atual é congelado na criação**, e só entra na soma o processo *sustentado*
  (ADR 0034) — nenhum sustentado devolve `null`, nunca zero;
- **a proveniência diz o que ficou de fora**, processo por processo, para a lacuna ser dita em vez
  de silenciada;
- **decidir é ato com autor e carimbo**, numa action e não num `PATCH` de `status`;
- **decidido é imutável**, e a recusa é 409 porque o que impede é o estado;
- **um aprovado vivo por oportunidade**, com a constraint por baixo e um 409 legível por cima;
- **a fronteira da conta** vale como nos quatro vizinhos da Fase 4;
- **dinheiro sai como texto** no JSON renderizado (ADR 0068).
"""

from decimal import Decimal

import pytest
from django.core.exceptions import ValidationError
from django.db.utils import IntegrityError
from django.urls import reverse
from django.utils import timezone
from rest_framework.test import APIClient

from apps.core.business_case import custo_congelavel
from apps.core.models import BusinessCase, Finding, User

from .factories import (
    AccountFactory,
    BusinessCaseFactory,
    FindingFactory,
    ImprovementOpportunityFactory,
    PainPointFactory,
    PriorityAssessmentFactory,
    ProcessFactory,
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


def _processo_com_custo(conta, **overrides: object):
    """Processo com os quatro fatores do núcleo preenchidos — 100 × 0,50 × 1 × R$ 80 = R$ 4.000."""
    base: dict = {
        "account": conta,
        "volume_mes": 100,
        "tempo_horas": Decimal("0.50"),
        "pessoas": 1,
        "custo_hora": Decimal("80.00"),
    }
    base.update(overrides)
    return ProcessFactory(**base)


def _sustenta(processo, conta) -> Finding:
    """Um `Finding` vivo classificado como fato — é ele que muda a `sustentacao` do custo."""
    return FindingFactory(
        account=conta,
        process=processo,
        epistemic_status=Finding.EpistemicStatus.FACT,
        reviewed_by=UserFactory(),
        reviewed_at=timezone.now(),
    )


def _oportunidade_com(processo, conta):
    """Oportunidade de melhoria que alcança um processo por uma dor viva."""
    oportunidade = ImprovementOpportunityFactory(account=conta)
    dor = PainPointFactory(account=conta, process=processo)
    oportunidade.pain_points.add(dor)
    return oportunidade


def _payload(oportunidade, **overrides: object) -> dict:
    hipotese = SolutionHypothesisFactory(improvement_opportunity=oportunidade)
    avaliacao = PriorityAssessmentFactory(improvement_opportunity=oportunidade)
    base: dict = {
        "improvement_opportunity": oportunidade.pk,
        "solution_hypothesis": hipotese.pk,
        "priority_assessment": avaliacao.pk,
        "investment": "30000.00",
        "expected_return_year": "120000.00",
        "rationale": "O leitor de nota se paga no primeiro trimestre.",
    }
    base.update(overrides)
    return base


# --- O congelamento do custo -------------------------------------------------------------------


def test_o_business_case_nasce_em_rascunho_e_congela_o_custo_sustentado(api: APIClient) -> None:
    conta = AccountFactory()
    processo = _processo_com_custo(conta)
    _sustenta(processo, conta)
    oportunidade = _oportunidade_com(processo, conta)

    criado = api.post(reverse("businesscase-list"), _payload(oportunidade), format="json")

    assert criado.status_code == 201, criado.data
    corpo = criado.json()
    assert corpo["status"] == "draft"
    assert corpo["current_state_cost"] == "4000.00"
    assert corpo["current_state_cost_source"]["somados"] == [processo.pk]
    assert corpo["decided_at"] is None and corpo["decided_by"] is None


def test_sem_processo_sustentado_o_custo_e_nulo_e_a_lacuna_fica_registrada(api: APIClient) -> None:
    """`null`, e nunca `Decimal("0")` — a regra do `nao_apurado` (ADR 0034).

    O processo existe, tem os quatro fatores e a conta fecha em R$ 4.000; o que falta é fato vivo
    por baixo. Somar aquele número afirmaria como medido o que ainda é hipótese, e devolver zero
    afirmaria que operar assim não custa nada. A proveniência guarda as duas informações: o
    processo apareceu, e apareceu como hipótese.
    """
    conta = AccountFactory()
    processo = _processo_com_custo(conta)
    oportunidade = _oportunidade_com(processo, conta)

    criado = api.post(reverse("businesscase-list"), _payload(oportunidade), format="json")

    assert criado.status_code == 201, criado.data
    corpo = criado.json()
    assert corpo["current_state_cost"] is None
    proveniencia = corpo["current_state_cost_source"]
    assert proveniencia["somados"] == []
    assert proveniencia["processos"] == [
        {
            "id": processo.pk,
            "sustentacao": "hipotese",
            "total": "4000.00",
            "nao_apurado": ["Retrabalho", "Erros", "Perdas", "Espera", "Risco"],
        }
    ]


def test_a_oportunidade_sem_dor_nenhuma_congela_lacuna_vazia(api: APIClient) -> None:
    """Controle do caso extremo: nada a apurar continua sendo `null`, não zero."""
    oportunidade = ImprovementOpportunityFactory()

    criado = api.post(reverse("businesscase-list"), _payload(oportunidade), format="json")

    assert criado.status_code == 201, criado.data
    corpo = criado.json()
    assert corpo["current_state_cost"] is None
    assert corpo["current_state_cost_source"] == {"processos": [], "somados": []}


def test_o_processo_alcancado_por_duas_dores_conta_uma_vez() -> None:
    """Agrupar dores é o que a `ImprovementOpportunity` faz; somar o processo duas vezes dobraria
    o número sem nada ficar vermelho."""
    conta = AccountFactory()
    processo = _processo_com_custo(conta)
    _sustenta(processo, conta)
    oportunidade = ImprovementOpportunityFactory(account=conta)
    oportunidade.pain_points.add(
        PainPointFactory(account=conta, process=processo),
        PainPointFactory(account=conta, process=processo, title="Outra dor, mesmo processo"),
    )

    total, proveniencia = custo_congelavel(oportunidade)

    assert total == Decimal("4000.00")
    assert proveniencia["somados"] == [processo.pk]


def test_dor_arquivada_processo_arquivado_e_dor_sem_processo_nao_entram() -> None:
    """As três formas de um processo não chegar à conta — e o controle positivo ao lado."""
    conta = AccountFactory()
    vivo = _processo_com_custo(conta)
    _sustenta(vivo, conta)
    por_dor_arquivada = _processo_com_custo(conta, name="Expedição")
    _sustenta(por_dor_arquivada, conta)
    arquivado = _processo_com_custo(conta, name="Cobrança")
    _sustenta(arquivado, conta)
    arquivado.archive()

    oportunidade = ImprovementOpportunityFactory(account=conta)
    dor_arquivada = PainPointFactory(account=conta, process=por_dor_arquivada)
    dor_arquivada.archive()
    oportunidade.pain_points.add(
        PainPointFactory(account=conta, process=vivo),
        dor_arquivada,
        PainPointFactory(account=conta, process=arquivado),
        PainPointFactory(account=conta, process=None, title="Dor sem processo mapeado"),
    )

    total, proveniencia = custo_congelavel(oportunidade)

    assert total == Decimal("4000.00")
    assert proveniencia["somados"] == [vivo.pk]
    assert [linha["id"] for linha in proveniencia["processos"]] == [vivo.pk]


def test_dois_processos_sustentados_somam_e_o_de_hipotese_fica_de_fora() -> None:
    conta = AccountFactory()
    primeiro = _processo_com_custo(conta)
    _sustenta(primeiro, conta)
    segundo = _processo_com_custo(conta, name="Expedição", retrabalho_mes=Decimal("250.00"))
    _sustenta(segundo, conta)
    hipotese = _processo_com_custo(conta, name="Cobrança")

    oportunidade = ImprovementOpportunityFactory(account=conta)
    oportunidade.pain_points.add(
        PainPointFactory(account=conta, process=primeiro),
        PainPointFactory(account=conta, process=segundo, title="Dor da expedição"),
        PainPointFactory(account=conta, process=hipotese, title="Dor da cobrança"),
    )

    total, proveniencia = custo_congelavel(oportunidade)

    assert total == Decimal("8250.00")
    assert proveniencia["somados"] == sorted([primeiro.pk, segundo.pk])
    fora = next(linha for linha in proveniencia["processos"] if linha["id"] == hipotese.pk)
    assert fora["sustentacao"] == "hipotese"


def test_o_custo_congelado_nao_e_escrito_pelo_corpo(api: APIClient) -> None:
    """Não há caminho de escrita, em vez de haver um caminho que ninguém usa."""
    conta = AccountFactory()
    processo = _processo_com_custo(conta)
    _sustenta(processo, conta)
    oportunidade = _oportunidade_com(processo, conta)

    criado = api.post(
        reverse("businesscase-list"),
        _payload(
            oportunidade,
            current_state_cost="999999.00",
            current_state_cost_source={"processos": [], "somados": [1]},
        ),
        format="json",
    )

    assert criado.status_code == 201, criado.data
    assert criado.json()["current_state_cost"] == "4000.00"
    assert criado.json()["current_state_cost_source"]["somados"] == [processo.pk]


# --- A decisão ---------------------------------------------------------------------------------


def test_decidir_grava_autor_e_carimbo(api: APIClient) -> None:
    business_case = BusinessCaseFactory()

    decidido = api.post(
        reverse("businesscase-decide", args=[business_case.pk]),
        {"outcome": "approved"},
        format="json",
    )

    assert decidido.status_code == 200, decidido.data
    corpo = decidido.json()
    assert corpo["status"] == "approved"
    assert corpo["decided_by"] is not None
    assert corpo["decided_at"] is not None
    business_case.refresh_from_db()
    assert business_case.decided_at is not None


def test_a_segunda_decisao_e_409(api: APIClient) -> None:
    business_case = BusinessCaseFactory()
    rota = reverse("businesscase-decide", args=[business_case.pk])
    assert api.post(rota, {"outcome": "rejected"}, format="json").status_code == 200

    segunda = api.post(rota, {"outcome": "approved"}, format="json")

    assert segunda.status_code == 409, segunda.data
    business_case.refresh_from_db()
    assert business_case.status == BusinessCase.Status.REJECTED


def test_decisao_fora_do_vocabulario_e_400(api: APIClient) -> None:
    business_case = BusinessCaseFactory()

    recusado = api.post(
        reverse("businesscase-decide", args=[business_case.pk]),
        {"outcome": "talvez"},
        format="json",
    )

    assert recusado.status_code == 400, recusado.data
    business_case.refresh_from_db()
    assert business_case.status == BusinessCase.Status.DRAFT


@pytest.mark.parametrize("faltando", ["investment", "expected_return_year"])
def test_nao_se_decide_investimento_sem_os_dois_numeros(api: APIClient, faltando: str) -> None:
    business_case = BusinessCaseFactory(**{faltando: None})

    recusado = api.post(
        reverse("businesscase-decide", args=[business_case.pk]),
        {"outcome": "approved"},
        format="json",
    )

    assert recusado.status_code == 400, recusado.data
    assert faltando in str(recusado.data)
    business_case.refresh_from_db()
    assert business_case.status == BusinessCase.Status.DRAFT


def test_editar_business_case_decidido_e_409(api: APIClient) -> None:
    business_case = BusinessCaseFactory()
    api.post(
        reverse("businesscase-decide", args=[business_case.pk]),
        {"outcome": "approved"},
        format="json",
    )

    editado = api.patch(
        reverse("businesscase-detail", args=[business_case.pk]),
        {"investment": "1.00"},
        format="json",
    )

    assert editado.status_code == 409, editado.data
    business_case.refresh_from_db()
    assert business_case.investment == Decimal("30000.00")


def test_editar_rascunho_continua_passando(api: APIClient) -> None:
    """Controle positivo, sem o qual o teste acima passaria por recusar toda edição."""
    business_case = BusinessCaseFactory()

    editado = api.patch(
        reverse("businesscase-detail", args=[business_case.pk]),
        {"investment": "42000.00", "payback_months": 9},
        format="json",
    )

    assert editado.status_code == 200, editado.data
    assert editado.json()["investment"] == "42000.00"
    assert editado.json()["payback_months"] == 9


def test_o_status_nao_muda_por_patch(api: APIClient) -> None:
    """A decisão mora na action, e um `PATCH` de `status` não é um atalho para ela."""
    business_case = BusinessCaseFactory()

    editado = api.patch(
        reverse("businesscase-detail", args=[business_case.pk]),
        {"status": "approved"},
        format="json",
    )

    assert editado.status_code == 200, editado.data
    business_case.refresh_from_db()
    assert business_case.status == BusinessCase.Status.DRAFT
    assert business_case.decided_by_id is None


# --- Um aprovado vivo por oportunidade ---------------------------------------------------------


def test_o_segundo_aprovado_da_mesma_oportunidade_e_409(api: APIClient) -> None:
    oportunidade = ImprovementOpportunityFactory()
    primeiro = BusinessCaseFactory(improvement_opportunity=oportunidade)
    segundo = BusinessCaseFactory(improvement_opportunity=oportunidade)
    api.post(
        reverse("businesscase-decide", args=[primeiro.pk]), {"outcome": "approved"}, format="json"
    )

    recusado = api.post(
        reverse("businesscase-decide", args=[segundo.pk]), {"outcome": "approved"}, format="json"
    )

    assert recusado.status_code == 409, recusado.data
    segundo.refresh_from_db()
    assert segundo.status == BusinessCase.Status.DRAFT


def test_rejeitar_o_segundo_continua_passando(api: APIClient) -> None:
    """Rejeitar não concorre: recusar é resultado repetível, aprovar duas vezes é contradição."""
    oportunidade = ImprovementOpportunityFactory()
    primeiro = BusinessCaseFactory(improvement_opportunity=oportunidade)
    segundo = BusinessCaseFactory(improvement_opportunity=oportunidade)
    api.post(
        reverse("businesscase-decide", args=[primeiro.pk]), {"outcome": "approved"}, format="json"
    )

    rejeitado = api.post(
        reverse("businesscase-decide", args=[segundo.pk]), {"outcome": "rejected"}, format="json"
    )

    assert rejeitado.status_code == 200, rejeitado.data


def test_o_aprovado_arquivado_libera_o_proximo(api: APIClient) -> None:
    oportunidade = ImprovementOpportunityFactory()
    primeiro = BusinessCaseFactory(improvement_opportunity=oportunidade)
    segundo = BusinessCaseFactory(improvement_opportunity=oportunidade)
    api.post(
        reverse("businesscase-decide", args=[primeiro.pk]), {"outcome": "approved"}, format="json"
    )
    primeiro.refresh_from_db()
    primeiro.archive()

    aprovado = api.post(
        reverse("businesscase-decide", args=[segundo.pk]), {"outcome": "approved"}, format="json"
    )

    assert aprovado.status_code == 200, aprovado.data


def test_a_constraint_e_a_garantia_e_nao_a_view() -> None:
    """A checagem da action produz o 409 legível; quem impede de verdade é o banco."""
    oportunidade = ImprovementOpportunityFactory()
    autor = UserFactory()
    BusinessCaseFactory(
        improvement_opportunity=oportunidade,
        status=BusinessCase.Status.APPROVED,
        decided_by=autor,
        decided_at=timezone.now(),
    )

    with pytest.raises(IntegrityError):
        BusinessCaseFactory(
            improvement_opportunity=oportunidade,
            status=BusinessCase.Status.APPROVED,
            decided_by=autor,
            decided_at=timezone.now(),
        )


# --- As invariantes do modelo ------------------------------------------------------------------


def test_a_hipotese_de_outra_oportunidade_e_recusada(api: APIClient) -> None:
    oportunidade = ImprovementOpportunityFactory()
    intrusa = SolutionHypothesisFactory()

    recusado = api.post(
        reverse("businesscase-list"),
        _payload(oportunidade, solution_hypothesis=intrusa.pk),
        format="json",
    )

    assert recusado.status_code == 400, recusado.data
    assert "solution_hypothesis" in recusado.data


def test_a_avaliacao_de_outra_oportunidade_e_recusada(api: APIClient) -> None:
    oportunidade = ImprovementOpportunityFactory()
    intrusa = PriorityAssessmentFactory()

    recusado = api.post(
        reverse("businesscase-list"),
        _payload(oportunidade, priority_assessment=intrusa.pk),
        format="json",
    )

    assert recusado.status_code == 400, recusado.data
    assert "priority_assessment" in recusado.data


def test_o_clean_recusa_as_duas_pontas_fora_da_rota() -> None:
    """Shell, admin e migração não passam por serializer — é a porta dupla do `PainPoint`."""
    oportunidade = ImprovementOpportunityFactory()
    business_case = BusinessCase(
        improvement_opportunity=oportunidade,
        solution_hypothesis=SolutionHypothesisFactory(),
        priority_assessment=PriorityAssessmentFactory(improvement_opportunity=oportunidade),
        rationale="…",
    )

    with pytest.raises(ValidationError) as erro:
        business_case.clean()

    assert "solution_hypothesis" in erro.value.message_dict


def test_aprovar_sem_autor_e_carimbo_e_recusado_pelo_clean() -> None:
    business_case = BusinessCaseFactory()
    business_case.status = BusinessCase.Status.APPROVED

    with pytest.raises(ValidationError) as erro:
        business_case.clean()

    assert "status" in erro.value.message_dict


# --- Contrato ----------------------------------------------------------------------------------


def test_dinheiro_atravessa_como_texto(api: APIClient) -> None:
    """`response.data` ainda traz `Decimal`; o que o cliente lê é o JSON renderizado (ADR 0068)."""
    conta = AccountFactory()
    processo = _processo_com_custo(conta)
    _sustenta(processo, conta)
    oportunidade = _oportunidade_com(processo, conta)
    business_case = api.post(
        reverse("businesscase-list"), _payload(oportunidade), format="json"
    ).json()

    lido = api.get(reverse("businesscase-detail", args=[business_case["id"]])).json()

    assert lido["investment"] == "30000.00"
    assert lido["expected_return_year"] == "120000.00"
    assert lido["current_state_cost"] == "4000.00"
    assert lido["current_state_cost_source"]["processos"][0]["total"] == "4000.00"


def test_a_conta_sai_derivada_da_oportunidade(api: APIClient) -> None:
    conta = AccountFactory()
    oportunidade = ImprovementOpportunityFactory(account=conta)
    business_case = BusinessCaseFactory(improvement_opportunity=oportunidade)

    lido = api.get(reverse("businesscase-detail", args=[business_case.pk]))

    assert lido.data["account"] == conta.pk


def test_as_listas_filtram_por_conta_por_oportunidade_e_por_estado(api: APIClient) -> None:
    conta = AccountFactory()
    oportunidade = ImprovementOpportunityFactory(account=conta)
    BusinessCaseFactory(improvement_opportunity=oportunidade)
    outro = BusinessCaseFactory(
        improvement_opportunity=ImprovementOpportunityFactory(account=conta)
    )
    BusinessCaseFactory()
    api.post(reverse("businesscase-decide", args=[outro.pk]), {"outcome": "approved"}, format="json")

    por_conta = api.get(f"{reverse('businesscase-list')}?account={conta.pk}")
    por_oportunidade = api.get(
        f"{reverse('businesscase-list')}?improvement_opportunity={oportunidade.pk}"
    )
    por_estado = api.get(f"{reverse('businesscase-list')}?account={conta.pk}&status=approved")

    assert len(por_conta.data) == 2
    assert len(por_oportunidade.data) == 1
    assert len(por_estado.data) == 1


def test_arquivar_e_restaurar_pela_interface(api: APIClient) -> None:
    business_case = BusinessCaseFactory()

    assert api.delete(reverse("businesscase-detail", args=[business_case.pk])).status_code == 204
    assert api.get(reverse("businesscase-list")).data == []
    assert len(api.get(f"{reverse('businesscase-list')}?archived=1").data) == 1
    assert api.post(reverse("businesscase-unarchive", args=[business_case.pk])).status_code == 200
    assert len(api.get(reverse("businesscase-list")).data) == 1


# --- A fronteira da conta ----------------------------------------------------------------------


def test_a_entrega_fora_da_conta_nao_le_nem_escreve() -> None:
    minha = AccountFactory()
    alheia = AccountFactory()
    entrega = UserFactory(role=User.Role.DELIVERY)
    ProjectMemberFactory(project=ProjectFactory(engagement__account=minha), user=entrega)
    de_fora = BusinessCaseFactory(
        improvement_opportunity=ImprovementOpportunityFactory(account=alheia)
    )
    api = APIClient()
    api.force_authenticate(entrega)

    listado = api.get(reverse("businesscase-list"))
    detalhe = api.get(reverse("businesscase-detail", args=[de_fora.pk]))
    criado = api.post(
        reverse("businesscase-list"),
        _payload(ImprovementOpportunityFactory(account=alheia)),
        format="json",
    )

    assert listado.data == []
    assert detalhe.status_code == 404
    assert criado.status_code == 403, criado.data


def test_a_entrega_da_conta_le_e_escreve() -> None:
    """Controle positivo do recorte acima."""
    minha = AccountFactory()
    entrega = UserFactory(role=User.Role.DELIVERY)
    ProjectMemberFactory(project=ProjectFactory(engagement__account=minha), user=entrega)
    oportunidade = ImprovementOpportunityFactory(account=minha)
    api = APIClient()
    api.force_authenticate(entrega)

    criado = api.post(reverse("businesscase-list"), _payload(oportunidade), format="json")

    assert criado.status_code == 201, criado.data
    assert len(api.get(reverse("businesscase-list")).data) == 1


def test_vendas_escreve_e_decide() -> None:
    """`business_case` é escrita das duas áreas — e não é o `case`, que Vendas só lê."""
    business_case = BusinessCaseFactory()
    api = APIClient()
    api.force_authenticate(UserFactory(role=User.Role.SALES))

    decidido = api.post(
        reverse("businesscase-decide", args=[business_case.pk]),
        {"outcome": "approved"},
        format="json",
    )

    assert decidido.status_code == 200, decidido.data


@pytest.mark.django_db
def test_o_processo_sustentado_sem_insumo_nenhum_nao_vira_custo_zero() -> None:
    """Sustentado **e** não apurado é lacuna, não zero — e este é o caso comum, não um canto.

    O processo tem achado promovido a fato (revisor e evidência viva, §6.9) e **nenhum dos nove
    insumos preenchido**, que é exatamente o estado de um processo recém-mapeado numa reunião de
    Discovery: alguém confirmou o que acontece ali antes de alguém medir quanto custa.

    `custo_do_estado_atual` devolve `total = 0` com `nao_apurado` cheio, e a docstring dele diz o
    que isso significa: *"não há insumo para dizer"*, e quem consome distingue **pelo
    `nao_apurado`, não pelo total**. Somar esse zero grava `current_state_cost = 0`, e a tela
    (DAP r2, decisão F1) mostra "R$ 0,00" em vez de `—` — a casa afirmando ao aprovador o oposto
    do que ela sabe, embaixo de um investimento que ele está prestes a autorizar.
    """
    conta = AccountFactory()
    processo = ProcessFactory(account=conta)  # sem nenhum dos nove insumos
    _sustenta(processo, conta)
    oportunidade = _oportunidade_com(processo, conta)

    total, proveniencia = custo_congelavel(oportunidade)

    assert total is None
    assert proveniencia["somados"] == []
    assert proveniencia["processos"][0]["sustentacao"] == "sustentado"
    assert proveniencia["processos"][0]["nao_apurado"]


@pytest.mark.django_db
def test_decidir_o_que_ja_foi_decidido_e_409_mesmo_sem_os_numeros(api: APIClient) -> None:
    """O estado é perguntado antes do corpo, e a ordem é o que torna a recusa cumprível.

    Um business case **rejeitado** que nunca teve os dois valores é o caso que separa as duas
    ordens: perguntando pelos números primeiro, a resposta seria 400 mandando registrá-los — e
    quem tentasse cumprir tomaria 409 no `PATCH`, porque decidido não se edita. A recusa certa é
    a que diz a verdade sobre o que aconteceu: já foi decidido.
    """
    oportunidade = ImprovementOpportunityFactory()
    criado = api.post(
        reverse("businesscase-list"),
        _payload(oportunidade, investment=None, expected_return_year=None),
        format="json",
    )
    assert criado.status_code == 201, criado.data
    identificador = criado.json()["id"]
    url = reverse("businesscase-decide", args=[identificador])

    assert api.post(url, {"outcome": "rejected"}, format="json").status_code == 200

    repetido = api.post(url, {"outcome": "approved"}, format="json")

    assert repetido.status_code == 409, repetido.data
    assert "já está rejeitado" in str(repetido.data).lower()


@pytest.mark.django_db
def test_rejeitar_nao_exige_os_numeros_que_aprovar_exige(api: APIClient) -> None:
    """Recusar o que nem chegou a ser orçado é o caso comum, e não pede número nenhum.

    A assimetria é a decisão: aprovar sem saber quanto e para quê é exatamente o que a exigência
    impede; rejeitar sem os valores é como a maior parte das recusas acontece. Cobrá-los aqui
    obrigaria a inventar dois números para registrar que **não** se vai investir.
    """
    oportunidade = ImprovementOpportunityFactory()
    criado = api.post(
        reverse("businesscase-list"),
        _payload(oportunidade, investment=None, expected_return_year=None),
        format="json",
    )
    url = reverse("businesscase-decide", args=[criado.json()["id"]])

    recusado = api.post(url, {"outcome": "rejected"}, format="json")

    assert recusado.status_code == 200, recusado.data
    assert recusado.json()["status"] == "rejected"
    assert recusado.json()["decided_by"] is not None
