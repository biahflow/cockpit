"""Feasibility, PROVE, KPI/Measurement e Value Ledger — a quinta fatia da ontologia (FDD 049).

O que se exercita aqui é o que os cinco modelos passam a permitir afirmar, e cada bloco existe
porque a regra correspondente pode regredir **sem sintoma visível**:

- **o PROVE não começa sem KPI, critério e baseline** — ou com lacuna aprovada, que é ato assinado
  (decisão E1 do DAP `dap-prove-e-valor-r1`). A recusa diz *o que* falta, e não só que falta algo;
- **uma baseline viva por KPI**: duas fariam a comparação depender de qual alguém abriu;
- **`Measurement.value` ausente fica nulo e nunca vira zero** — a mesma distinção que
  `DigitalEmployee.kpi_baseline` guardava sendo nulável;
- **as invariantes §6.11 e §6.12 do `language-map`**, testáveis pela primeira vez: a entrada de
  valor aponta para um `Outcome`, registra método de atribuição, e aprovar tem autor;
- **cada gate tem seu vocabulário**: a Feasibility recusa `SCALE`, o PROVE recusa `GO`;
- **os dois campos derivados sobrevivem na `/api/v1/`** — a regressão do contrato mora em
  `tests/regression/test_a_medicao_do_ativo_sobrevive_na_v1.py`, e aqui fica a leitura do par;
- **o recorte da Entrega** nos cinco recursos, com controle positivo.
"""

from datetime import timedelta
from decimal import Decimal

import pytest
from django.core.exceptions import ValidationError
from django.db.models import ProtectedError
from django.urls import reverse
from django.utils import timezone
from rest_framework.test import APIClient

from apps.core import prove
from apps.core.models import (
    KPI,
    DigitalEmployee,
    FeasibilityAssessment,
    Measurement,
    ProjectPhase,
    ProveExperiment,
    User,
    ValueLedgerEntry,
)

from .factories import (
    AccountFactory,
    EngagementFactory,
    EvidenceFactory,
    FeasibilityAssessmentFactory,
    ImprovementOpportunityFactory,
    KPIFactory,
    MeasurementFactory,
    ProjectFactory,
    ProjectMemberFactory,
    ProveExperimentFactory,
    SolutionHypothesisFactory,
    UserFactory,
    ValueLedgerEntryFactory,
)

pytestmark = pytest.mark.django_db

HOJE = timezone.localdate()


@pytest.fixture
def api() -> APIClient:
    client = APIClient()
    client.force_authenticate(UserFactory(role=User.Role.ADMIN))
    return client


def _com_baseline(kpi: KPI, valor: str = "4.20") -> Measurement:
    return MeasurementFactory(kpi=kpi, kind=Measurement.Kind.BASELINE, value=Decimal(valor))


def _experimento_pronto(**overrides: object) -> ProveExperiment:
    """Um PROVE que passa nos três requisitos — o controle positivo de toda recusa abaixo."""
    experimento = ProveExperimentFactory(
        success_criteria="Reduzir o tempo de resposta abaixo de 1h em 80% dos casos.", **overrides
    )
    _com_baseline(KPIFactory(project=experimento.project, prove_experiment=experimento))
    return experimento


# --- A invariante de início do PROVE (decisão E1) -----------------------------------------------


def test_iniciar_sem_nada_recusa_dizendo_os_tres_que_faltam(api: APIClient) -> None:
    """Uma recusa que só diz "não pode" obriga quem clicou a adivinhar qual dos três falta."""
    experimento = ProveExperimentFactory()

    resposta = api.post(reverse("proveexperiment-start", args=[experimento.pk]))

    assert resposta.status_code == 400, resposta.data
    detalhe = str(resposta.data["detail"])
    assert "KPI" in detalhe
    assert "critério de sucesso" in detalhe
    assert "baseline" in detalhe
    experimento.refresh_from_db()
    assert experimento.status == ProveExperiment.Status.PLANNED


def test_iniciar_sem_criterio_de_sucesso_recusa_so_por_ele(api: APIClient) -> None:
    experimento = ProveExperimentFactory()
    _com_baseline(KPIFactory(project=experimento.project, prove_experiment=experimento))

    resposta = api.post(reverse("proveexperiment-start", args=[experimento.pk]))

    assert resposta.status_code == 400, resposta.data
    assert "critério de sucesso" in str(resposta.data["detail"])
    assert "baseline" not in str(resposta.data["detail"])


def test_iniciar_com_kpi_sem_baseline_recusa_so_por_ela(api: APIClient) -> None:
    """O KPI existe e o critério existe; o que falta é o "antes" — e é isso que a recusa diz."""
    experimento = ProveExperimentFactory(success_criteria="Cair abaixo de 1h.")
    KPIFactory(project=experimento.project, prove_experiment=experimento)

    resposta = api.post(reverse("proveexperiment-start", args=[experimento.pk]))

    assert resposta.status_code == 400, resposta.data
    assert "baseline" in str(resposta.data["detail"])
    assert "critério de sucesso" not in str(resposta.data["detail"])


def test_um_kpi_sem_baseline_entre_varios_ja_impede_o_inicio(api: APIClient) -> None:
    """"Algum KPI tem baseline" não é a invariante — a comparação é por KPI, e todos precisam."""
    experimento = _experimento_pronto()
    KPIFactory(project=experimento.project, prove_experiment=experimento, name="Retrabalho")

    resposta = api.post(reverse("proveexperiment-start", args=[experimento.pk]))

    assert resposta.status_code == 400, resposta.data
    assert "baseline" in str(resposta.data["detail"])


def test_iniciar_com_os_tres_prontos_poe_o_prove_em_execucao(api: APIClient) -> None:
    experimento = _experimento_pronto()

    resposta = api.post(reverse("proveexperiment-start", args=[experimento.pk]))

    assert resposta.status_code == 200, resposta.data
    experimento.refresh_from_db()
    assert experimento.status == ProveExperiment.Status.RUNNING
    assert experimento.started_at == HOJE
    assert experimento.gap_waiver_at is None  # nada a dispensar, nada a carimbar


def test_baseline_arquivada_nao_conta_como_baseline(api: APIClient) -> None:
    """A constraint é parcial no arquivamento; a invariante de início tem de ler igual."""
    experimento = ProveExperimentFactory(success_criteria="Cair abaixo de 1h.")
    kpi = KPIFactory(project=experimento.project, prove_experiment=experimento)
    _com_baseline(kpi).archive()

    resposta = api.post(reverse("proveexperiment-start", args=[experimento.pk]))

    assert resposta.status_code == 400, resposta.data
    assert "baseline" in str(resposta.data["detail"])


def test_lacuna_aprovada_sem_autor_e_recusada(api: APIClient) -> None:
    """Sem autor não é aprovação, é um campo de texto — a regra do trio do `Case`."""
    experimento = ProveExperimentFactory(gap_waiver="O cliente não tem histórico apurável.")

    resposta = api.post(reverse("proveexperiment-start", args=[experimento.pk]))

    assert resposta.status_code == 400, resposta.data
    assert "gap_waiver_by" in str(resposta.data["detail"])
    experimento.refresh_from_db()
    assert experimento.status == ProveExperiment.Status.PLANNED
    assert experimento.gap_waiver_at is None


def test_lacuna_aprovada_com_autor_destrava_e_carimba(api: APIClient) -> None:
    quem = UserFactory()
    experimento = ProveExperimentFactory(
        gap_waiver="O cliente não tem histórico apurável; medimos a partir da semana 1.",
        gap_waiver_by=quem,
    )

    resposta = api.post(reverse("proveexperiment-start", args=[experimento.pk]))

    assert resposta.status_code == 200, resposta.data
    experimento.refresh_from_db()
    assert experimento.status == ProveExperiment.Status.RUNNING
    assert experimento.gap_waiver_at is not None
    assert experimento.gap_waiver_by_id == quem.pk


def test_iniciar_duas_vezes_e_409(api: APIClient) -> None:
    """O pedido está bem formado e a permissão existe; o que impede é o estado."""
    experimento = _experimento_pronto()
    assert api.post(reverse("proveexperiment-start", args=[experimento.pk])).status_code == 200

    resposta = api.post(reverse("proveexperiment-start", args=[experimento.pk]))

    assert resposta.status_code == 409, resposta.data


def test_patch_nao_poe_o_prove_em_execucao(api: APIClient) -> None:
    """Sem esta recusa a invariante vaza pela porta do formulário — o defeito da decisão C1."""
    experimento = ProveExperimentFactory()

    resposta = api.patch(
        reverse("proveexperiment-detail", args=[experimento.pk]),
        {"status": ProveExperiment.Status.RUNNING},
        format="json",
    )

    assert resposta.status_code == 400, resposta.data
    experimento.refresh_from_db()
    assert experimento.status == ProveExperiment.Status.PLANNED


def test_a_lista_do_que_falta_sai_no_serializer(api: APIClient) -> None:
    """A tela desenha a mesma lista que a action recusa — duas expressões divergiriam."""
    experimento = ProveExperimentFactory()

    resposta = api.get(reverse("proveexperiment-detail", args=[experimento.pk]))

    assert resposta.data["missing_to_start"] == list(prove.REQUISITOS)


def test_a_lista_do_que_falta_esvazia_quando_tudo_esta_pronto(api: APIClient) -> None:
    experimento = _experimento_pronto()

    resposta = api.get(reverse("proveexperiment-detail", args=[experimento.pk]))

    assert resposta.data["missing_to_start"] == []


# --- Os dois vocabulários de gate (ADR 0053) ---------------------------------------------------


@pytest.mark.parametrize("decisao", ["scale", "iterate", "stop"])
def test_o_prove_aceita_o_vocabulario_dele(api: APIClient, decisao: str) -> None:
    experimento = ProveExperimentFactory()

    resposta = api.patch(
        reverse("proveexperiment-detail", args=[experimento.pk]),
        {"gate_decision": decisao},
        format="json",
    )

    assert resposta.status_code == 200, resposta.data


def test_o_prove_recusa_a_decisao_da_feasibility(api: APIClient) -> None:
    experimento = ProveExperimentFactory()

    resposta = api.patch(
        reverse("proveexperiment-detail", args=[experimento.pk]),
        {"gate_decision": ProjectPhase.GateDecision.GO},
        format="json",
    )

    assert resposta.status_code == 400, resposta.data


@pytest.mark.parametrize("decisao", ["go", "conditional_go", "redesign", "no_go"])
def test_a_feasibility_aceita_o_vocabulario_dela(api: APIClient, decisao: str) -> None:
    laudo = FeasibilityAssessmentFactory()

    resposta = api.patch(
        reverse("feasibilityassessment-detail", args=[laudo.pk]),
        {"gate_decision": decisao},
        format="json",
    )

    assert resposta.status_code == 200, resposta.data


def test_a_feasibility_recusa_a_decisao_do_prove(api: APIClient) -> None:
    laudo = FeasibilityAssessmentFactory()

    resposta = api.patch(
        reverse("feasibilityassessment-detail", args=[laudo.pk]),
        {"gate_decision": ProjectPhase.ProveDecision.SCALE},
        format="json",
    )

    assert resposta.status_code == 400, resposta.data


def test_o_laudo_guarda_os_tres_eixos_separados(api: APIClient) -> None:
    """"Funciona, mas o time não opera" e "funciona e não fecha a conta" não colapsam."""
    laudo = FeasibilityAssessmentFactory(
        technical_verdict=FeasibilityAssessment.Verdict.FAVORABLE,
        operational_verdict=FeasibilityAssessment.Verdict.CAVEAT,
        economic_verdict=FeasibilityAssessment.Verdict.UNFAVORABLE,
    )

    dados = api.get(reverse("feasibilityassessment-detail", args=[laudo.pk])).data

    assert dados["technical_verdict_display"] == "Favorável"
    assert dados["operational_verdict_display"] == "Com ressalva"
    assert dados["economic_verdict_display"] == "Desfavorável"


def test_o_laudo_recusa_hipotese_de_outra_conta(api: APIClient) -> None:
    projeto = ProjectFactory()
    alheia = SolutionHypothesisFactory(
        improvement_opportunity=ImprovementOpportunityFactory(account=AccountFactory())
    )

    resposta = api.post(
        reverse("feasibilityassessment-list"),
        {"project": projeto.pk, "solution_hypothesis": alheia.pk,
         "technical_verdict": "favorable", "operational_verdict": "favorable",
         "economic_verdict": "favorable"},
        format="json",
    )

    assert resposta.status_code == 400, resposta.data
    assert "solution_hypothesis" in resposta.data


def test_o_laudo_recusa_hipotese_de_outra_conta_tambem_no_modelo() -> None:
    """Shell, admin e migração não passam por rota — a mesma razão de `Project.clean()`."""
    projeto = ProjectFactory()
    alheia = SolutionHypothesisFactory(
        improvement_opportunity=ImprovementOpportunityFactory(account=AccountFactory())
    )

    with pytest.raises(ValidationError):
        FeasibilityAssessment(
            project=projeto, solution_hypothesis=alheia, technical_verdict="favorable",
            operational_verdict="favorable", economic_verdict="favorable",
        ).full_clean()


# --- KPI: a âncora é o projeto, e o experimento é opcional --------------------------------------


def test_kpi_sem_experimento_e_legitimo(api: APIClient) -> None:
    """O desvio deliberado da issue #69: é o formato do KPI que a migração `0067` cria."""
    projeto = ProjectFactory()

    resposta = api.post(
        reverse("kpi-list"), {"project": projeto.pk, "name": "Tempo de resposta"}, format="json"
    )

    assert resposta.status_code == 201, resposta.data
    assert KPI.objects.get(pk=resposta.data["id"]).prove_experiment_id is None


def test_kpi_recusa_experimento_de_outro_projeto(api: APIClient) -> None:
    projeto = ProjectFactory()
    alheio = ProveExperimentFactory()

    resposta = api.post(
        reverse("kpi-list"),
        {"project": projeto.pk, "prove_experiment": alheio.pk, "name": "Tempo de resposta"},
        format="json",
    )

    assert resposta.status_code == 400, resposta.data
    assert "prove_experiment" in resposta.data


def test_um_prove_carrega_varios_kpis(api: APIClient) -> None:
    """O que a coluna no ativo de solução impedia: um experimento com mais de um indicador."""
    experimento = ProveExperimentFactory()
    KPIFactory(project=experimento.project, prove_experiment=experimento, name="Tempo")
    KPIFactory(project=experimento.project, prove_experiment=experimento, name="Retrabalho")

    dados = api.get(f"{reverse('kpi-list')}?prove_experiment={experimento.pk}").data

    assert {linha["name"] for linha in dados} == {"Tempo", "Retrabalho"}


# --- Measurement: nulo não é zero, e uma baseline viva por KPI ----------------------------------


def test_medicao_sem_valor_fica_nula_e_nao_vira_zero(api: APIClient) -> None:
    """Zero afirmaria que o processo não custava nada antes; nulo diz que ninguém mediu."""
    kpi = KPIFactory()

    resposta = api.post(
        reverse("measurement-list"),
        {"kpi": kpi.pk, "kind": Measurement.Kind.MONITORING, "period_start": str(HOJE),
         "period_end": str(HOJE), "measured_at": timezone.now().isoformat()},
        format="json",
    )

    assert resposta.status_code == 201, resposta.data
    assert resposta.data["value"] is None
    assert Measurement.objects.get(pk=resposta.data["id"]).value is None


def test_zero_informado_e_preservado(api: APIClient) -> None:
    """A metade complementar: sem ela o teste acima passaria transformando zero em nulo."""
    medicao = MeasurementFactory(value=Decimal("0.00"))

    assert api.get(reverse("measurement-detail", args=[medicao.pk])).data["value"] == "0.00"


def test_duas_baselines_vivas_no_mesmo_kpi_sao_recusadas(api: APIClient) -> None:
    kpi = KPIFactory()
    _com_baseline(kpi)

    resposta = api.post(
        reverse("measurement-list"),
        {"kpi": kpi.pk, "kind": Measurement.Kind.BASELINE, "value": "3.10",
         "period_start": str(HOJE), "period_end": str(HOJE),
         "measured_at": timezone.now().isoformat()},
        format="json",
    )

    assert resposta.status_code == 400, resposta.data
    assert "kind" in resposta.data


def test_arquivar_a_baseline_libera_a_proxima(api: APIClient) -> None:
    kpi = KPIFactory()
    primeira = _com_baseline(kpi)
    assert api.delete(reverse("measurement-detail", args=[primeira.pk])).status_code == 204

    resposta = api.post(
        reverse("measurement-list"),
        {"kpi": kpi.pk, "kind": Measurement.Kind.BASELINE, "value": "3.10",
         "period_start": str(HOJE), "period_end": str(HOJE),
         "measured_at": timezone.now().isoformat()},
        format="json",
    )

    assert resposta.status_code == 201, resposta.data


def test_varios_outcomes_no_mesmo_kpi_sao_o_estado_normal(api: APIClient) -> None:
    """A unicidade é só da baseline: medir de novo o "depois" é o que o PROVE faz."""
    kpi = KPIFactory()
    MeasurementFactory(kpi=kpi, kind=Measurement.Kind.OUTCOME, value=Decimal("2.00"))

    resposta = api.post(
        reverse("measurement-list"),
        {"kpi": kpi.pk, "kind": Measurement.Kind.OUTCOME, "value": "1.05",
         "period_start": str(HOJE), "period_end": str(HOJE),
         "measured_at": timezone.now().isoformat()},
        format="json",
    )

    assert resposta.status_code == 201, resposta.data


def test_janela_invertida_e_recusada(api: APIClient) -> None:
    kpi = KPIFactory()

    resposta = api.post(
        reverse("measurement-list"),
        {"kpi": kpi.pk, "kind": Measurement.Kind.OUTCOME, "value": "1.05",
         "period_start": str(HOJE), "period_end": str(HOJE - timedelta(days=7)),
         "measured_at": timezone.now().isoformat()},
        format="json",
    )

    assert resposta.status_code == 400, resposta.data
    assert "period_end" in resposta.data


def test_a_medicao_nao_carrega_unidade(api: APIClient) -> None:
    """A ausência **é** a garantia: unidade e método são do KPI, e é o que torna o par comparável.

    Um leitor futuro pode "consertar" isto acrescentando `unit` aqui, e é exatamente a mudança que
    faria duas leituras divergirem de unidade sem nada ficar vermelho (`language-map` §6.11).
    """
    campos = {campo.name for campo in Measurement._meta.get_fields()}

    assert "unit" not in campos
    assert "direction" not in campos


# --- Value Ledger: as invariantes §6.11 e §6.12 -------------------------------------------------


def _payload_valor(engagement_id: int, medicao_id: int, **overrides: object) -> dict:
    base: dict = {
        "engagement": engagement_id,
        "outcome_measurement": medicao_id,
        "value_type": ValueLedgerEntry.ValueType.COST_SAVING,
        "amount": "12000.00",
        "period_start": str(HOJE - timedelta(days=30)),
        "period_end": str(HOJE),
        "attribution_method": "Diferença entre baseline e outcome, descontada a sazonalidade.",
    }
    base.update(overrides)
    return base


def test_entrada_apontando_para_baseline_e_recusada(api: APIClient) -> None:
    """Afirmaria resultado onde há ponto de partida — e os dois são números do mesmo KPI."""
    baseline = MeasurementFactory(kind=Measurement.Kind.BASELINE)

    resposta = api.post(
        reverse("valueledgerentry-list"),
        _payload_valor(EngagementFactory().pk, baseline.pk),
        format="json",
    )

    assert resposta.status_code == 400, resposta.data
    assert "outcome_measurement" in resposta.data


def test_entrada_apontando_para_outcome_e_aceita(api: APIClient) -> None:
    outcome = MeasurementFactory(kind=Measurement.Kind.OUTCOME)

    resposta = api.post(
        reverse("valueledgerentry-list"),
        _payload_valor(EngagementFactory().pk, outcome.pk),
        format="json",
    )

    assert resposta.status_code == 201, resposta.data


def test_entrada_sem_metodo_de_atribuicao_e_recusada(api: APIClient) -> None:
    outcome = MeasurementFactory(kind=Measurement.Kind.OUTCOME)

    resposta = api.post(
        reverse("valueledgerentry-list"),
        _payload_valor(EngagementFactory().pk, outcome.pk, attribution_method="   "),
        format="json",
    )

    assert resposta.status_code == 400, resposta.data
    assert "attribution_method" in resposta.data


def test_aprovar_sem_autor_e_recusado(api: APIClient) -> None:
    outcome = MeasurementFactory(kind=Measurement.Kind.OUTCOME)

    resposta = api.post(
        reverse("valueledgerentry-list"),
        _payload_valor(
            EngagementFactory().pk, outcome.pk, status=ValueLedgerEntry.Status.APPROVED
        ),
        format="json",
    )

    assert resposta.status_code == 400, resposta.data
    assert "approved_by" in resposta.data


def test_aprovar_com_autor_carimba_a_hora(api: APIClient) -> None:
    entrada = ValueLedgerEntryFactory()
    quem = UserFactory()

    resposta = api.patch(
        reverse("valueledgerentry-detail", args=[entrada.pk]),
        {"status": ValueLedgerEntry.Status.APPROVED, "approved_by": quem.pk},
        format="json",
    )

    assert resposta.status_code == 200, resposta.data
    entrada.refresh_from_db()
    assert entrada.approved_at is not None
    assert entrada.approved_by_id == quem.pk


def test_o_carimbo_de_aprovacao_nao_e_reescrito(api: APIClient) -> None:
    """Como o `published_at` do `Case`: quem aprovou primeiro fixou a data."""
    entrada = ValueLedgerEntryFactory(
        status=ValueLedgerEntry.Status.APPROVED, approved_by=UserFactory()
    )
    primeiro = entrada.approved_at

    entrada.amount = Decimal("13000.00")
    entrada.save()

    entrada.refresh_from_db()
    assert entrada.approved_at == primeiro


def test_apagar_a_medicao_que_sustenta_uma_entrada_e_recusado() -> None:
    """`PROTECT`, como `Case.project`: a entrada de valor sobrevive ao que acontece em volta."""
    entrada = ValueLedgerEntryFactory()

    with pytest.raises(ProtectedError):
        entrada.outcome_measurement.delete()


def test_arquivar_a_medicao_que_sustenta_uma_entrada_e_409(api: APIClient) -> None:
    """A API arquiva em vez de apagar, e sem esta guarda o `PROTECT` não seria alcançado.

    A entrada de valor continuaria na listagem apontando para uma medição que a interface esconde —
    o órfão visível da FDD 025, aqui sustentando um número que a casa afirma ao cliente.
    """
    entrada = ValueLedgerEntryFactory()

    resposta = api.delete(
        reverse("measurement-detail", args=[entrada.outcome_measurement.pk])
    )

    assert resposta.status_code == 409, resposta.data
    entrada.outcome_measurement.refresh_from_db()
    assert entrada.outcome_measurement.archived_at is None


def test_arquivar_o_kpi_leva_as_medicoes_junto(api: APIClient) -> None:
    """A outra saída legítima da regra de órfão: arquivar na mesma transação (FDD 025)."""
    kpi = KPIFactory()
    baseline = _com_baseline(kpi)

    assert api.delete(reverse("kpi-detail", args=[kpi.pk])).status_code == 204

    baseline.refresh_from_db()
    assert baseline.archived_at is not None


def test_arquivar_o_kpi_de_uma_entrada_viva_e_409(api: APIClient) -> None:
    """Arquivar o pai esvaziaria por baixo uma afirmação de valor que alguém pode ter aprovado."""
    entrada = ValueLedgerEntryFactory()

    resposta = api.delete(reverse("kpi-detail", args=[entrada.outcome_measurement.kpi_id]))

    assert resposta.status_code == 409, resposta.data
    assert KPI.objects.get(pk=entrada.outcome_measurement.kpi_id).archived_at is None


def test_entrada_recusa_projeto_de_outro_engajamento(api: APIClient) -> None:
    outcome = MeasurementFactory(kind=Measurement.Kind.OUTCOME)

    resposta = api.post(
        reverse("valueledgerentry-list"),
        _payload_valor(EngagementFactory().pk, outcome.pk, project=ProjectFactory().pk),
        format="json",
    )

    assert resposta.status_code == 400, resposta.data
    assert "project" in resposta.data


# --- O par derivado que a `/api/v1/` continua publicando (ADR 0055) -----------------------------


def test_o_ativo_le_o_par_do_kpi_que_referencia(api: APIClient) -> None:
    projeto = ProjectFactory()
    kpi = KPIFactory(project=projeto)
    _com_baseline(kpi, "12.00")
    MeasurementFactory(
        kpi=kpi, kind=Measurement.Kind.OUTCOME, value=Decimal("48.00"),
        measured_at=timezone.now() - timedelta(days=1),
    )
    MeasurementFactory(kpi=kpi, kind=Measurement.Kind.OUTCOME, value=Decimal("60.00"))
    ativo = DigitalEmployee.objects.create(project=projeto, name="SDR", kpi=kpi)

    dados = api.get(reverse("digitalemployee-detail", args=[ativo.pk])).data

    assert dados["kpi_baseline"] == "12.00"
    # O **mais recente** por `measured_at`, e não o último inserido.
    assert dados["kpi_current"] == "60.00"


def test_o_ativo_sem_kpi_traz_o_par_nulo_e_nunca_zero(api: APIClient) -> None:
    ativo = DigitalEmployee.objects.create(project=ProjectFactory(), name="SDR")

    dados = api.get(reverse("digitalemployee-detail", args=[ativo.pk])).data

    assert dados["kpi_baseline"] is None
    assert dados["kpi_current"] is None


def test_o_ativo_recusa_kpi_de_outro_projeto(api: APIClient) -> None:
    """O `ProjectScopedMixin` olha a chave `project`; sem esta guarda, o `kpi` passaria por baixo."""
    ativo = DigitalEmployee.objects.create(project=ProjectFactory(), name="SDR")
    alheio = KPIFactory(project=ProjectFactory())

    resposta = api.patch(
        reverse("digitalemployee-detail", args=[ativo.pk]), {"kpi": alheio.pk}, format="json"
    )

    assert resposta.status_code == 400, resposta.data
    assert "kpi" in resposta.data


def test_escrever_o_par_pelo_ativo_nao_tem_efeito(api: APIClient) -> None:
    """A quebra deliberada da decisão C1: os dois campos são derivados e a escrita é ignorada.

    A forma é a dos três snapshots congelados do `Case` — "um `PATCH` que os traga no corpo é
    aceito com 200 e os ignora". Dois lugares escrevendo a mesma medição fariam a fonte da verdade
    voltar a ser o ativo de solução.
    """
    projeto = ProjectFactory()
    kpi = KPIFactory(project=projeto)
    _com_baseline(kpi, "12.00")
    ativo = DigitalEmployee.objects.create(project=projeto, name="SDR", kpi=kpi)

    resposta = api.patch(
        reverse("digitalemployee-detail", args=[ativo.pk]),
        {"kpi_baseline": "999.00", "kpi_current": "999.00"},
        format="json",
    )

    assert resposta.status_code == 200, resposta.data
    assert resposta.data["kpi_baseline"] == "12.00"
    assert Measurement.objects.filter(value=Decimal("999.00")).count() == 0


# --- O recorte da Entrega nos cinco recursos ----------------------------------------------------


def _entrega_com_projeto() -> tuple[APIClient, User, object]:
    entrega = UserFactory(role=User.Role.DELIVERY)
    projeto = ProjectFactory()
    ProjectMemberFactory(project=projeto, user=entrega)
    api = APIClient()
    api.force_authenticate(entrega)
    return api, entrega, projeto


def test_entrega_nao_le_os_cinco_fora_dos_projetos_dela() -> None:
    api, _, _ = _entrega_com_projeto()
    alheio = ProjectFactory()
    FeasibilityAssessmentFactory(project=alheio)
    ProveExperimentFactory(project=alheio)
    kpi = KPIFactory(project=alheio)
    MeasurementFactory(kpi=kpi)
    ValueLedgerEntryFactory(engagement=alheio.engagement)

    for rota in ("feasibilityassessment-list", "proveexperiment-list", "kpi-list",
                 "measurement-list", "valueledgerentry-list"):
        assert api.get(reverse(rota)).data == [], rota


def test_entrega_le_os_cinco_dentro_do_projeto_dela() -> None:
    """Controle positivo do teste acima: sem ele, um recorte que esconde tudo passaria igual."""
    api, _, projeto = _entrega_com_projeto()
    FeasibilityAssessmentFactory(project=projeto)
    experimento = ProveExperimentFactory(project=projeto)
    kpi = KPIFactory(project=projeto, prove_experiment=experimento)
    MeasurementFactory(kpi=kpi)
    ValueLedgerEntryFactory(engagement=projeto.engagement)

    for rota in ("feasibilityassessment-list", "proveexperiment-list", "kpi-list",
                 "measurement-list", "valueledgerentry-list"):
        assert len(api.get(reverse(rota)).data) == 1, rota


def test_entrega_nao_escreve_kpi_em_projeto_alheio() -> None:
    """Só a leitura seria contornável em uma requisição — o argumento do `ProjectScopedMixin`."""
    api, _, _ = _entrega_com_projeto()
    alheio = ProjectFactory()

    resposta = api.post(
        reverse("kpi-list"), {"project": alheio.pk, "name": "Tempo"}, format="json"
    )

    assert resposta.status_code == 403, resposta.data
    assert not KPI.objects.filter(project=alheio).exists()


def test_entrega_nao_registra_medicao_em_kpi_alheio() -> None:
    """O projeto chega pelo KPI, e é por isso que `scope_payload_field` aponta para ele."""
    api, _, _ = _entrega_com_projeto()
    alheio = KPIFactory(project=ProjectFactory())

    resposta = api.post(
        reverse("measurement-list"),
        {"kpi": alheio.pk, "kind": Measurement.Kind.OUTCOME, "value": "1.05",
         "period_start": str(HOJE), "period_end": str(HOJE),
         "measured_at": timezone.now().isoformat()},
        format="json",
    )

    assert resposta.status_code == 403, resposta.data
    assert not Measurement.objects.filter(kpi=alheio).exists()


def test_entrega_nao_lanca_valor_em_engajamento_alheio() -> None:
    api, _, _ = _entrega_com_projeto()
    alheio = EngagementFactory()
    outcome = MeasurementFactory(kind=Measurement.Kind.OUTCOME)

    resposta = api.post(
        reverse("valueledgerentry-list"), _payload_valor(alheio.pk, outcome.pk), format="json"
    )

    assert resposta.status_code == 403, resposta.data
    assert not ValueLedgerEntry.objects.filter(engagement=alheio).exists()


def test_entrega_lanca_valor_no_proprio_engajamento() -> None:
    api, _, projeto = _entrega_com_projeto()
    outcome = MeasurementFactory(kind=Measurement.Kind.OUTCOME, kpi=KPIFactory(project=projeto))

    resposta = api.post(
        reverse("valueledgerentry-list"),
        _payload_valor(projeto.engagement_id, outcome.pk),
        format="json",
    )

    assert resposta.status_code == 201, resposta.data


def test_a_entrada_sem_projeto_e_visivel_por_quem_alcanca_o_mandato() -> None:
    """O engajamento **não** é fronteira de acesso: a visibilidade deriva de `visible_to`.

    É a razão de `ValueLedgerEntry` ficar fora de `PROJECT_OF`: um mapa que resolvesse
    `obj.project` devolveria `None` aqui, e a Entrega tomaria 403 no detalhe de uma linha que a
    listagem dela mostra — o defeito que a `SatisfactionRecord` já previu.
    """
    api, _, projeto = _entrega_com_projeto()
    entrada = ValueLedgerEntryFactory(engagement=projeto.engagement, project=None)

    resposta = api.get(reverse("valueledgerentry-detail", args=[entrada.pk]))

    assert resposta.status_code == 200, resposta.data


def test_vendas_le_e_nao_escreve_os_cinco() -> None:
    """A assimetria: o comercial lê o que a casa provou e não escreve a medição que a sustenta."""
    api = APIClient()
    api.force_authenticate(UserFactory(role=User.Role.SALES))
    projeto = ProjectFactory()

    assert api.get(reverse("kpi-list")).status_code == 200
    resposta = api.post(
        reverse("kpi-list"), {"project": projeto.pk, "name": "Tempo"}, format="json"
    )

    assert resposta.status_code == 403, resposta.data


# --- Arquivar e restaurar, o básico da FDD 025 --------------------------------------------------


def test_os_cinco_arquivam_e_voltam_pelo_unarchive(api: APIClient) -> None:
    experimento = ProveExperimentFactory()

    assert api.delete(reverse("proveexperiment-detail", args=[experimento.pk])).status_code == 204
    assert api.get(reverse("proveexperiment-list")).data == []
    assert len(api.get(f"{reverse('proveexperiment-list')}?archived=1").data) == 1
    assert api.post(reverse("proveexperiment-unarchive", args=[experimento.pk])).status_code == 200
    assert len(api.get(reverse("proveexperiment-list")).data) == 1


def test_as_listas_filtram_pelos_parametros_que_a_tela_pede(api: APIClient) -> None:
    experimento = ProveExperimentFactory()
    kpi = KPIFactory(project=experimento.project, prove_experiment=experimento)
    MeasurementFactory(kpi=kpi, kind=Measurement.Kind.BASELINE)
    MeasurementFactory(kpi=KPIFactory(), kind=Measurement.Kind.OUTCOME)
    ProveExperimentFactory(status=ProveExperiment.Status.CONCLUDED)

    assert len(api.get(f"{reverse('kpi-list')}?project={experimento.project_id}").data) == 1
    assert len(api.get(f"{reverse('kpi-list')}?prove_experiment={experimento.pk}").data) == 1
    assert len(api.get(f"{reverse('measurement-list')}?kpi={kpi.pk}").data) == 1
    assert len(api.get(f"{reverse('measurement-list')}?kind=baseline").data) == 1
    assert len(api.get(f"{reverse('proveexperiment-list')}?status=concluded").data) == 1


def test_o_ledger_filtra_por_engajamento_e_estado(api: APIClient) -> None:
    engagement = EngagementFactory()
    ValueLedgerEntryFactory(engagement=engagement)
    ValueLedgerEntryFactory(
        engagement=engagement, status=ValueLedgerEntry.Status.APPROVED, approved_by=UserFactory()
    )
    ValueLedgerEntryFactory()

    assert len(api.get(f"{reverse('valueledgerentry-list')}?engagement={engagement.pk}").data) == 2
    assert len(api.get(f"{reverse('valueledgerentry-list')}?status=approved").data) == 1


# --- O módulo puro --------------------------------------------------------------------------


def test_o_modulo_puro_devolve_chaves_e_nao_frases() -> None:
    """Rótulo é da superfície. Devolver "Baseline" congelaria a copy do board no backend."""
    experimento = ProveExperimentFactory()

    assert prove.o_que_falta_para_iniciar(experimento) == [
        prove.REQUISITO_KPI, prove.REQUISITO_CRITERIO, prove.REQUISITO_BASELINE
    ]


def test_a_evidencia_do_laudo_precisa_ser_da_mesma_conta(api: APIClient) -> None:
    laudo = FeasibilityAssessmentFactory()
    alheia = EvidenceFactory(account=AccountFactory())

    resposta = api.patch(
        reverse("feasibilityassessment-detail", args=[laudo.pk]),
        {"evidence": [alheia.pk]},
        format="json",
    )

    assert resposta.status_code == 400, resposta.data
    assert "evidence" in resposta.data
