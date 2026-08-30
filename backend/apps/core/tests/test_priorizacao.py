"""A cadeia do PRIORITIZE: dor → oportunidade de melhoria → avaliação → hipótese (FDD 048).

O PRIORITIZE é a segunda pergunta da escada FDE — *"onde devemos atuar?"* — e até aqui ela não
tinha entidade nenhuma: existia como fase configurável e como prosa. O que se exercita aqui é o
que os quatro modelos passam a permitir afirmar:

- **dor confirmada tem achado vivo por baixo**, nas três pontas em que a invariante pode vazar: a
  criação, o `PATCH` e o arquivamento do último achado;
- **a avaliação é imutável**: repriorizar cria a versão seguinte, e `PUT`/`PATCH` não existem;
- **os pesos ficam congelados na linha** — mudar o catálogo amanhã não reescreve o score de ontem;
- **o rank é derivado**, e quem não foi avaliado sai com `null`, nunca zero;
- **uma escolhida por oportunidade**: concorrer é o normal, escolher duas é contradição;
- **a fronteira da conta vale nas quatro pontas**, como em `test_evidence_finding.py`.
"""

from decimal import Decimal
from unittest.mock import patch

import pytest
from django.core.exceptions import ValidationError
from django.db.models.query import QuerySet
from django.urls import reverse
from rest_framework.test import APIClient

from apps.core.models import (
    ImprovementOpportunity,
    PainPoint,
    PipelineStage,
    PriorityAssessment,
    SolutionHypothesis,
    User,
)
from apps.core.priority import FORMULAS, calcular_score
from apps.core.recommendations import build_recommendations

from .factories import (
    AccountFactory,
    EngagementFactory,
    EvidenceFactory,
    FindingFactory,
    ImprovementOpportunityFactory,
    PainPointFactory,
    PriorityAssessmentFactory,
    ProcessFactory,
    ProcessStepFactory,
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


def _payload_dor(account_id: int, **overrides: object) -> dict:
    base: dict = {
        "account": account_id,
        "title": "Conferência manual de nota trava o fechamento",
        "impact_type": PainPoint.ImpactType.OPERATIONAL,
    }
    base.update(overrides)
    return base


def _payload_avaliacao(oportunidade_id: int, **overrides: object) -> dict:
    base: dict = {
        "improvement_opportunity": oportunidade_id,
        "impact": 5,
        "evidence_strength": 4,
        "feasibility": 3,
        "time_to_value": 2,
        "economics": 1,
    }
    base.update(overrides)
    return base


# --- A invariante do `confirmed`: dor confirmada tem achado vivo ------------------------------


def test_dor_confirmada_sem_achado_e_recusada_na_criacao(api: APIClient) -> None:
    conta = AccountFactory()
    arquivado = FindingFactory(account=conta)
    arquivado.archive()

    sem_nenhum = api.post(
        reverse("painpoint-list"),
        _payload_dor(conta.pk, status=PainPoint.Status.CONFIRMED),
        format="json",
    )
    so_arquivado = api.post(
        reverse("painpoint-list"),
        _payload_dor(
            conta.pk, status=PainPoint.Status.CONFIRMED, findings=[arquivado.pk]
        ),
        format="json",
    )

    assert sem_nenhum.status_code == 400, sem_nenhum.data
    assert so_arquivado.status_code == 400, so_arquivado.data
    assert "findings" in so_arquivado.data
    assert not PainPoint.objects.filter(status=PainPoint.Status.CONFIRMED).exists()


def test_dor_confirmada_com_achado_vivo_passa(api: APIClient) -> None:
    """Controle positivo, sem o qual o teste acima passaria por recusar toda confirmação."""
    conta = AccountFactory()

    resposta = api.post(
        reverse("painpoint-list"),
        _payload_dor(
            conta.pk,
            status=PainPoint.Status.CONFIRMED,
            findings=[FindingFactory(account=conta).pk],
        ),
        format="json",
    )

    assert resposta.status_code == 201, resposta.data


def test_confirmar_pela_patch_cobra_a_mesma_invariante(api: APIClient) -> None:
    """No `PATCH` que não mexe no M2M, a pergunta é sobre o que já está ligado."""
    conta = AccountFactory()
    dor = PainPointFactory(account=conta)

    sem_achado = api.patch(
        reverse("painpoint-detail", args=[dor.pk]),
        {"status": PainPoint.Status.CONFIRMED},
        format="json",
    )
    dor.findings.add(FindingFactory(account=conta))
    com_achado = api.patch(
        reverse("painpoint-detail", args=[dor.pk]),
        {"status": PainPoint.Status.CONFIRMED},
        format="json",
    )

    assert sem_achado.status_code == 400, sem_achado.data
    assert com_achado.status_code == 200, com_achado.data


def test_arquivar_o_ultimo_achado_de_uma_dor_confirmada_e_recusado(api: APIClient) -> None:
    """A terceira metade da invariante: sem ela, a regra vaza pelo `DELETE`."""
    conta = AccountFactory()
    achado = FindingFactory(account=conta)
    dor = PainPointFactory(account=conta, status=PainPoint.Status.CONFIRMED)
    dor.findings.add(achado)

    resposta = api.delete(reverse("finding-detail", args=[achado.pk]))

    assert resposta.status_code == 409, resposta.data
    achado.refresh_from_db()
    assert achado.archived_at is None
    dor.refresh_from_db()
    assert dor.status == PainPoint.Status.CONFIRMED


def test_arquivar_o_penultimo_achado_de_uma_dor_confirmada_passa(api: APIClient) -> None:
    conta = AccountFactory()
    primeiro = FindingFactory(account=conta)
    segundo = FindingFactory(account=conta)
    dor = PainPointFactory(account=conta, status=PainPoint.Status.CONFIRMED)
    dor.findings.add(primeiro, segundo)

    resposta = api.delete(reverse("finding-detail", args=[primeiro.pk]))

    assert resposta.status_code == 204
    primeiro.refresh_from_db()
    assert primeiro.archived_at is not None


def test_arquivar_o_unico_achado_de_uma_dor_observada_passa(api: APIClient) -> None:
    """A recusa é sobre a dor **confirmada**: observada sem achado continua honesta."""
    conta = AccountFactory()
    achado = FindingFactory(account=conta)
    PainPointFactory(account=conta).findings.add(achado)

    assert api.delete(reverse("finding-detail", args=[achado.pk])).status_code == 204


def test_arquivar_achado_de_dor_ja_arquivada_passa(api: APIClient) -> None:
    """Dor arquivada não afirma mais nada — segurar o achado dela seria segurar por nada."""
    conta = AccountFactory()
    achado = FindingFactory(account=conta)
    dor = PainPointFactory(account=conta, status=PainPoint.Status.CONFIRMED)
    dor.findings.add(achado)
    dor.archive()

    assert api.delete(reverse("finding-detail", args=[achado.pk])).status_code == 204


def test_a_evidencia_de_um_fato_continua_recusando_o_arquivamento(api: APIClient) -> None:
    """A guarda da FDD 045 não foi trocada pela nova — as duas convivem no mesmo `perform_destroy`
    de recursos diferentes, e um teste só aqui evita que a segunda coma a primeira."""
    conta = AccountFactory()
    evidencia = EvidenceFactory(account=conta)
    achado = FindingFactory(account=conta, epistemic_status="fact", reviewed_by=UserFactory())
    achado.evidences.add(evidencia)

    assert api.delete(reverse("evidence-detail", args=[evidencia.pk])).status_code == 409


# --- O impacto que ninguém estimou -------------------------------------------------------------


def test_impacto_ausente_fica_nulo_e_nao_vira_zero(api: APIClient) -> None:
    """Nulo é "não estimado"; zero afirma que a dor não custa nada."""
    resposta = api.post(
        reverse("painpoint-list"), _payload_dor(AccountFactory().pk), format="json"
    )

    assert resposta.status_code == 201, resposta.data
    assert resposta.data["impact_estimate"] is None
    assert PainPoint.objects.get(pk=resposta.data["id"]).impact_estimate is None


def test_impacto_zero_informado_e_preservado(api: APIClient) -> None:
    """O outro lado da mesma distinção: quem mediu e achou zero grava zero."""
    resposta = api.post(
        reverse("painpoint-list"),
        _payload_dor(AccountFactory().pk, impact_estimate="0.00"),
        format="json",
    )

    assert resposta.status_code == 201, resposta.data
    assert PainPoint.objects.get(pk=resposta.data["id"]).impact_estimate == Decimal("0.00")


# --- A fronteira da conta na dor ---------------------------------------------------------------


def test_o_processo_da_dor_precisa_ser_da_mesma_conta(api: APIClient) -> None:
    resposta = api.post(
        reverse("painpoint-list"),
        _payload_dor(
            AccountFactory().pk, process=ProcessFactory(account=AccountFactory()).pk
        ),
        format="json",
    )

    assert resposta.status_code == 400, resposta.data
    assert "process" in resposta.data


def test_a_etapa_da_dor_precisa_ser_do_mesmo_processo(api: APIClient) -> None:
    conta = AccountFactory()
    processo = ProcessFactory(account=conta)
    outra_etapa = ProcessStepFactory(process=ProcessFactory(account=conta))

    resposta = api.post(
        reverse("painpoint-list"),
        _payload_dor(conta.pk, process=processo.pk, step=outra_etapa.pk),
        format="json",
    )

    assert resposta.status_code == 400, resposta.data
    assert "step" in resposta.data


def test_o_achado_da_dor_precisa_ser_da_mesma_conta(api: APIClient) -> None:
    """A mesma classe de vínculo cruzado dos quatro campos opcionais da `Evidence` (FDD 045)."""
    resposta = api.post(
        reverse("painpoint-list"),
        _payload_dor(
            AccountFactory().pk, findings=[FindingFactory(account=AccountFactory()).pk]
        ),
        format="json",
    )

    assert resposta.status_code == 400, resposta.data
    assert "findings" in resposta.data


def test_o_modelo_tambem_recusa_processo_de_outra_conta() -> None:
    """A guarda do modelo, para quem entra pelo admin ou pelo shell."""
    dor = PainPointFactory()
    dor.process = ProcessFactory(account=AccountFactory())

    with pytest.raises(ValidationError) as erro:
        dor.full_clean()

    assert "process" in erro.value.message_dict


# --- A oportunidade de melhoria, que não é venda -----------------------------------------------


def test_a_oportunidade_de_melhoria_nao_referencia_o_pipeline() -> None:
    """Critério de aceite da issue #68, e a razão está no `language-map` §5: `Opportunity` sem
    qualificador colidia entre venda e melhoria operacional. Um campo de etapa aqui traria o funil
    comercial para dentro do backlog de melhoria."""
    campos = ImprovementOpportunity._meta.get_fields()
    assert PipelineStage not in {campo.related_model for campo in campos}
    assert not [campo.name for campo in campos if "stage" in campo.name.lower()]


def test_o_engajamento_precisa_ser_da_mesma_conta(api: APIClient) -> None:
    conta = AccountFactory()
    de_outra = EngagementFactory(account=AccountFactory())

    resposta = api.post(
        reverse("improvementopportunity-list"),
        {"account": conta.pk, "title": "Automatizar a conferência", "engagement": de_outra.pk},
        format="json",
    )

    assert resposta.status_code == 400, resposta.data
    assert "engagement" in resposta.data


def test_o_engajamento_da_propria_conta_passa(api: APIClient) -> None:
    """Controle positivo: sem ele o teste acima passaria por recusar todo engajamento."""
    conta = AccountFactory()

    resposta = api.post(
        reverse("improvementopportunity-list"),
        {
            "account": conta.pk,
            "title": "Automatizar a conferência",
            "engagement": EngagementFactory(account=conta).pk,
        },
        format="json",
    )

    assert resposta.status_code == 201, resposta.data


def test_o_modelo_tambem_recusa_engajamento_de_outra_conta() -> None:
    oportunidade = ImprovementOpportunityFactory()
    oportunidade.engagement = EngagementFactory(account=AccountFactory())

    with pytest.raises(ValidationError) as erro:
        oportunidade.full_clean()

    assert "engagement" in erro.value.message_dict


# --- A avaliação: versão, fórmula e imutabilidade ----------------------------------------------


def test_a_avaliacao_nova_incrementa_a_versao(api: APIClient) -> None:
    oportunidade = ImprovementOpportunityFactory()

    primeira = api.post(
        reverse("priorityassessment-list"), _payload_avaliacao(oportunidade.pk), format="json"
    )
    segunda = api.post(
        reverse("priorityassessment-list"),
        _payload_avaliacao(oportunidade.pk, impact=2),
        format="json",
    )

    assert primeira.status_code == 201, primeira.data
    assert segunda.status_code == 201, segunda.data
    assert primeira.data["version"] == 1
    assert segunda.data["version"] == 2
    # A vigente é a de maior versão, e é ela que a oportunidade publica.
    oportunidade.refresh_from_db()
    assert oportunidade.current_assessment is not None
    assert oportunidade.current_assessment.version == 2


def test_a_versao_e_atribuida_sob_trava_da_oportunidade(api: APIClient) -> None:
    """A concorrência real não é exercida aqui — a suíte roda em SQLite, onde `FOR UPDATE` é
    no-op. O que este teste afirma é que a trava está **no caminho**: sem ela, duas requisições
    simultâneas leem `max(version)` juntas, gravam a mesma versão e a constraint estoura como 500
    em vez de produzir a sequência. É o mesmo raciocínio do `convert-to-project` (ADR 0050)."""
    oportunidade = ImprovementOpportunityFactory()
    original = QuerySet.select_for_update
    travados: list[type] = []

    def espiao(self, *args, **kwargs):  # type: ignore[no-untyped-def]
        travados.append(self.model)
        return original(self, *args, **kwargs)

    with patch.object(QuerySet, "select_for_update", espiao):
        resposta = api.post(
            reverse("priorityassessment-list"), _payload_avaliacao(oportunidade.pk), format="json"
        )

    assert resposta.status_code == 201, resposta.data
    assert ImprovementOpportunity in travados


def test_a_avaliacao_arquivada_nao_devolve_o_numero_da_versao(api: APIClient) -> None:
    """A constraint é incondicional de propósito: duas linhas chamadas "v2" fariam a comparação
    com a semana passada depender de qual delas alguém abriu."""
    oportunidade = ImprovementOpportunityFactory()
    primeira = PriorityAssessmentFactory(improvement_opportunity=oportunidade)
    segunda = PriorityAssessmentFactory(improvement_opportunity=oportunidade)
    segunda.archive()

    assert primeira.version == 1
    assert segunda.version == 2
    # Arquivada sai da vigência, mas continua ocupando o número.
    assert oportunidade.current_assessment == primeira

    terceira = api.post(
        reverse("priorityassessment-list"), _payload_avaliacao(oportunidade.pk), format="json"
    )

    assert terceira.status_code == 201, terceira.data
    assert terceira.data["version"] == 3


def test_a_avaliacao_e_imutavel(api: APIClient) -> None:
    """Repriorizar cria versão nova; editar não existe — 405, e não 400."""
    avaliacao = PriorityAssessmentFactory()

    patch_ = api.patch(
        reverse("priorityassessment-detail", args=[avaliacao.pk]), {"impact": 5}, format="json"
    )
    put = api.put(
        reverse("priorityassessment-detail", args=[avaliacao.pk]),
        _payload_avaliacao(avaliacao.improvement_opportunity_id),
        format="json",
    )

    assert patch_.status_code == 405, patch_.data
    assert put.status_code == 405, put.data
    avaliacao.refresh_from_db()
    assert avaliacao.impact == 3


def test_o_score_sai_da_formula_e_nao_do_corpo(api: APIClient) -> None:
    """Caso escrito à mão: 5·0,30 + 4·0,20 + 3·0,20 + 2·0,15 + 1·0,15 = 3,35 → 67,00."""
    oportunidade = ImprovementOpportunityFactory()

    resposta = api.post(
        reverse("priorityassessment-list"),
        _payload_avaliacao(oportunidade.pk, score="99.00"),
        format="json",
    )

    assert resposta.status_code == 201, resposta.data
    assert Decimal(resposta.data["score"]) == Decimal("67.00")
    assert resposta.data["weights"] == {
        "impact": "0.30",
        "evidence_strength": "0.20",
        "feasibility": "0.20",
        "time_to_value": "0.15",
        "economics": "0.15",
    }


def test_os_pesos_ficam_congelados_na_linha(api: APIClient, monkeypatch) -> None:  # type: ignore[no-untyped-def]
    """Mudar `FORMULAS` amanhã não pode reescrever o score de uma avaliação de ontem — inclusive
    o de uma que já foi apresentada ao cliente."""
    oportunidade = ImprovementOpportunityFactory()
    resposta = api.post(
        reverse("priorityassessment-list"), _payload_avaliacao(oportunidade.pk), format="json"
    )
    assert resposta.status_code == 201, resposta.data
    avaliacao = PriorityAssessment.objects.get(pk=resposta.data["id"])

    monkeypatch.setitem(
        FORMULAS,
        "v1",
        {
            "impact": Decimal("0.90"),
            "evidence_strength": Decimal("0.025"),
            "feasibility": Decimal("0.025"),
            "time_to_value": Decimal("0.025"),
            "economics": Decimal("0.025"),
        },
    )
    dimensoes = {
        "impact": avaliacao.impact,
        "evidence_strength": avaliacao.evidence_strength,
        "feasibility": avaliacao.feasibility,
        "time_to_value": avaliacao.time_to_value,
        "economics": avaliacao.economics,
    }

    avaliacao.refresh_from_db()
    assert avaliacao.score == Decimal("67.00")
    assert calcular_score(dimensoes, avaliacao.weights) == Decimal("67.00")
    # Controle: com os pesos novos o número **seria** outro — é isso que torna a cópia necessária.
    assert calcular_score(dimensoes, FORMULAS["v1"]) != Decimal("67.00")


def test_formula_desconhecida_e_recusada(api: APIClient) -> None:
    resposta = api.post(
        reverse("priorityassessment-list"),
        _payload_avaliacao(ImprovementOpportunityFactory().pk, formula_key="v99"),
        format="json",
    )

    assert resposta.status_code == 400, resposta.data
    assert "formula_key" in resposta.data


def test_nota_fora_da_escala_e_recusada(api: APIClient) -> None:
    resposta = api.post(
        reverse("priorityassessment-list"),
        _payload_avaliacao(ImprovementOpportunityFactory().pk, impact=6),
        format="json",
    )

    assert resposta.status_code == 400, resposta.data
    assert "impact" in resposta.data


def test_quem_avaliou_sai_da_sessao(api: APIClient) -> None:
    avaliador = UserFactory(role=User.Role.SALES)
    cliente = APIClient()
    cliente.force_authenticate(avaliador)

    resposta = cliente.post(
        reverse("priorityassessment-list"),
        _payload_avaliacao(ImprovementOpportunityFactory().pk),
        format="json",
    )

    assert resposta.status_code == 201, resposta.data
    assert PriorityAssessment.objects.get(pk=resposta.data["id"]).assessed_by == avaliador


# --- O rank derivado ----------------------------------------------------------------------------


def test_o_rank_sai_da_ordem_por_score_e_a_sem_avaliacao_fica_nula(api: APIClient) -> None:
    """`rank` não é campo: um número gravado que precisa concordar com a ordenação por score é
    uma segunda definição da mesma coisa. E a que ninguém avaliou sai com `null`, nunca zero."""
    conta = AccountFactory()
    alta = ImprovementOpportunityFactory(account=conta, title="Alta")
    media = ImprovementOpportunityFactory(account=conta, title="Média")
    baixa = ImprovementOpportunityFactory(account=conta, title="Baixa")
    sem_avaliacao = ImprovementOpportunityFactory(account=conta, title="Sem avaliação")
    PriorityAssessmentFactory(improvement_opportunity=alta, impact=5, evidence_strength=5,
                              feasibility=5, time_to_value=5, economics=5)
    PriorityAssessmentFactory(improvement_opportunity=media)
    PriorityAssessmentFactory(improvement_opportunity=baixa, impact=1, evidence_strength=1,
                              feasibility=1, time_to_value=1, economics=1)

    linhas = {linha["id"]: linha for linha in api.get(reverse("improvementopportunity-list")).data}

    assert [linhas[o.pk]["rank"] for o in (alta, media, baixa)] == [1, 2, 3]
    assert Decimal(linhas[alta.pk]["score"]) == Decimal("100.00")
    assert Decimal(linhas[baixa.pk]["score"]) == Decimal("20.00")
    assert linhas[sem_avaliacao.pk]["rank"] is None
    assert linhas[sem_avaliacao.pk]["score"] is None
    assert linhas[sem_avaliacao.pk]["assessment_version"] is None


def test_a_versao_acompanha_o_score_na_linha(api: APIClient) -> None:
    """Decisão B1 do DAP: um score sem a versão ao lado não se compara com o da semana passada."""
    oportunidade = ImprovementOpportunityFactory()
    PriorityAssessmentFactory(improvement_opportunity=oportunidade)
    PriorityAssessmentFactory(improvement_opportunity=oportunidade, impact=5)

    linha = api.get(reverse("improvementopportunity-detail", args=[oportunidade.pk])).data

    assert linha["assessment_version"] == 2
    assert Decimal(linha["score"]) == Decimal("72.00")


def test_a_descartada_sai_do_ranking(api: APIClient) -> None:
    """Uma descartada ocupando o #1 seria uma lista de trabalho que aponta para lugar nenhum."""
    conta = AccountFactory()
    descartada = ImprovementOpportunityFactory(
        account=conta, status=ImprovementOpportunity.Status.DISCARDED
    )
    viva = ImprovementOpportunityFactory(account=conta)
    PriorityAssessmentFactory(improvement_opportunity=descartada, impact=5, evidence_strength=5,
                              feasibility=5, time_to_value=5, economics=5)
    PriorityAssessmentFactory(improvement_opportunity=viva)

    linhas = {linha["id"]: linha for linha in api.get(reverse("improvementopportunity-list")).data}

    assert linhas[viva.pk]["rank"] == 1
    assert linhas[descartada.pk]["rank"] is None
    # O score continua saindo: descartar não apaga a avaliação que houve.
    assert linhas[descartada.pk]["score"] is not None


# --- As hipóteses concorrentes ------------------------------------------------------------------


def test_duas_hipoteses_escolhidas_na_mesma_oportunidade_sao_recusadas(api: APIClient) -> None:
    oportunidade = ImprovementOpportunityFactory()
    SolutionHypothesisFactory(
        improvement_opportunity=oportunidade, status=SolutionHypothesis.Status.CHOSEN
    )

    resposta = api.post(
        reverse("solutionhypothesis-list"),
        {
            "improvement_opportunity": oportunidade.pk,
            "statement": "Trocar o ERP resolve.",
            "status": SolutionHypothesis.Status.CHOSEN,
        },
        format="json",
    )

    assert resposta.status_code == 400, resposta.data
    assert "status" in resposta.data
    assert oportunidade.hypotheses.filter(status=SolutionHypothesis.Status.CHOSEN).count() == 1


def test_varias_propostas_convivem_e_a_escolha_e_uma(api: APIClient) -> None:
    """Concorrer é o estado normal — o que não pode é escolher duas."""
    oportunidade = ImprovementOpportunityFactory()
    for texto in ("Leitor de nota", "Redesenho do fluxo", "Mudança de política"):
        resposta = api.post(
            reverse("solutionhypothesis-list"),
            {"improvement_opportunity": oportunidade.pk, "statement": texto},
            format="json",
        )
        assert resposta.status_code == 201, resposta.data

    primeira = oportunidade.hypotheses.order_by("id").first()
    assert primeira is not None
    escolha = api.patch(
        reverse("solutionhypothesis-detail", args=[primeira.pk]),
        {"status": SolutionHypothesis.Status.CHOSEN},
        format="json",
    )

    assert escolha.status_code == 200, escolha.data
    assert oportunidade.hypotheses.count() == 3


def test_a_escolhida_arquivada_libera_a_proxima(api: APIClient) -> None:
    """A constraint é parcial pelo motivo de `unique_active_project_member`: uma escolha desfeita
    não pode travar a escolha seguinte."""
    oportunidade = ImprovementOpportunityFactory()
    anterior = SolutionHypothesisFactory(
        improvement_opportunity=oportunidade, status=SolutionHypothesis.Status.CHOSEN
    )
    anterior.archive()

    resposta = api.post(
        reverse("solutionhypothesis-list"),
        {
            "improvement_opportunity": oportunidade.pk,
            "statement": "Leitor de nota com revisão por exceção.",
            "status": SolutionHypothesis.Status.CHOSEN,
        },
        format="json",
    )

    assert resposta.status_code == 201, resposta.data


# --- O recomendador -----------------------------------------------------------------------------


def test_o_recomendador_aponta_a_priorizada_de_maior_score() -> None:
    """Critério de aceite da issue: o próximo passo sai da `PriorityAssessment` vigente, e não de
    um campo opaco — `Lead.ai_score` e `Project.ai_potential` medem outra coisa (§5)."""
    conta = AccountFactory()
    campea = ImprovementOpportunityFactory(
        account=conta, title="Campeã", status=ImprovementOpportunity.Status.PRIORITIZED
    )
    segunda = ImprovementOpportunityFactory(
        account=conta, title="Segunda", status=ImprovementOpportunity.Status.PRIORITIZED
    )
    aberta = ImprovementOpportunityFactory(account=conta, title="Ainda aberta")
    PriorityAssessmentFactory(improvement_opportunity=campea, impact=5, evidence_strength=5,
                              feasibility=5, time_to_value=5, economics=5)
    PriorityAssessmentFactory(improvement_opportunity=segunda)
    PriorityAssessmentFactory(improvement_opportunity=aberta, impact=5, evidence_strength=5,
                              feasibility=5, time_to_value=5, economics=5)

    do_prioritize = [rec for rec in build_recommendations() if rec["kind"] == "prioritization"]

    assert len(do_prioritize) == 1
    assert "Campeã" in do_prioritize[0]["label"]
    assert do_prioritize[0]["url"] == f"/contas/{conta.pk}/priorizacao"
    assert "100.00" in do_prioritize[0]["detail"]


def test_o_recomendador_para_quando_a_hipotese_foi_escolhida() -> None:
    """"Ainda não virou trabalho" é o que a fase permite observar: hipótese escolhida é o passo
    seguinte, e continuar cobrando o mesmo item viraria ruído."""
    oportunidade = ImprovementOpportunityFactory(
        status=ImprovementOpportunity.Status.PRIORITIZED
    )
    PriorityAssessmentFactory(improvement_opportunity=oportunidade)
    SolutionHypothesisFactory(
        improvement_opportunity=oportunidade, status=SolutionHypothesis.Status.CHOSEN
    )

    assert [rec for rec in build_recommendations() if rec["kind"] == "prioritization"] == []


def test_o_recomendador_ignora_a_priorizada_sem_avaliacao() -> None:
    ImprovementOpportunityFactory(status=ImprovementOpportunity.Status.PRIORITIZED)

    assert [rec for rec in build_recommendations() if rec["kind"] == "prioritization"] == []


# --- A fronteira: Entrega fora do projeto -------------------------------------------------------


def test_entrega_nao_ve_os_quatro_recursos_de_outra_conta() -> None:
    """Espelha `test_evidence_finding.py`: a listagem recorta pela participação."""
    minha = AccountFactory()
    alheia = AccountFactory()
    entrega = UserFactory(role=User.Role.DELIVERY)
    ProjectMemberFactory(project=ProjectFactory(engagement__account=minha), user=entrega)

    for conta in (minha, alheia):
        PainPointFactory(account=conta)
        oportunidade = ImprovementOpportunityFactory(account=conta)
        PriorityAssessmentFactory(improvement_opportunity=oportunidade)
        SolutionHypothesisFactory(improvement_opportunity=oportunidade)

    api = APIClient()
    api.force_authenticate(entrega)

    for rota in (
        "painpoint-list",
        "improvementopportunity-list",
        "priorityassessment-list",
        "solutionhypothesis-list",
    ):
        resposta = api.get(reverse(rota))
        assert resposta.status_code == 200, (rota, resposta.data)
        assert len(resposta.data) == 1, (rota, resposta.data)


def test_entrega_nao_escreve_dor_em_conta_alheia() -> None:
    """Sem a guarda de escrita, uma requisição bastaria para escrever dentro do cliente oculto."""
    alheia = AccountFactory()
    entrega = UserFactory(role=User.Role.DELIVERY)
    ProjectMemberFactory(project=ProjectFactory(), user=entrega)
    api = APIClient()
    api.force_authenticate(entrega)

    resposta = api.post(reverse("painpoint-list"), _payload_dor(alheia.pk), format="json")

    assert resposta.status_code == 403, resposta.data
    assert not PainPoint.objects.filter(account=alheia).exists()


def test_entrega_nao_escreve_oportunidade_de_melhoria_em_conta_alheia() -> None:
    alheia = AccountFactory()
    entrega = UserFactory(role=User.Role.DELIVERY)
    ProjectMemberFactory(project=ProjectFactory(), user=entrega)
    api = APIClient()
    api.force_authenticate(entrega)

    resposta = api.post(
        reverse("improvementopportunity-list"),
        {"account": alheia.pk, "title": "Automatizar a conferência"},
        format="json",
    )

    assert resposta.status_code == 403, resposta.data
    assert not ImprovementOpportunity.objects.filter(account=alheia).exists()


def test_entrega_nao_pendura_avaliacao_nem_hipotese_em_oportunidade_alheia() -> None:
    """A conta chega pela oportunidade, e é ela que decide — não o projeto de quem escreve."""
    entrega = UserFactory(role=User.Role.DELIVERY)
    ProjectMemberFactory(project=ProjectFactory(), user=entrega)
    alheia = ImprovementOpportunityFactory(account=AccountFactory())
    api = APIClient()
    api.force_authenticate(entrega)

    avaliacao = api.post(
        reverse("priorityassessment-list"), _payload_avaliacao(alheia.pk), format="json"
    )
    hipotese = api.post(
        reverse("solutionhypothesis-list"),
        {"improvement_opportunity": alheia.pk, "statement": "Trocar o ERP resolve."},
        format="json",
    )

    assert avaliacao.status_code == 403, avaliacao.data
    assert hipotese.status_code == 403, hipotese.data
    assert not PriorityAssessment.objects.exists()
    assert not SolutionHypothesis.objects.exists()


def test_entrega_escreve_dentro_do_proprio_cliente() -> None:
    """Controle positivo dos três acima: o levantamento é das duas áreas (FDD 039, FDD 045)."""
    minha = AccountFactory()
    entrega = UserFactory(role=User.Role.DELIVERY)
    ProjectMemberFactory(project=ProjectFactory(engagement__account=minha), user=entrega)
    api = APIClient()
    api.force_authenticate(entrega)

    resposta = api.post(reverse("painpoint-list"), _payload_dor(minha.pk), format="json")

    assert resposta.status_code == 201, resposta.data


# --- Arquivar e restaurar, o básico da FDD 025 --------------------------------------------------


def test_a_dor_arquivada_sai_da_lista_e_volta_pelo_unarchive(api: APIClient) -> None:
    dor = PainPointFactory()

    assert api.delete(reverse("painpoint-detail", args=[dor.pk])).status_code == 204
    assert api.get(reverse("painpoint-list")).data == []
    assert len(api.get(f"{reverse('painpoint-list')}?archived=1").data) == 1
    assert api.post(reverse("painpoint-unarchive", args=[dor.pk])).status_code == 200
    assert len(api.get(reverse("painpoint-list")).data) == 1


def test_as_listas_filtram_por_conta_e_por_estado(api: APIClient) -> None:
    conta = AccountFactory()
    PainPointFactory(account=conta, status=PainPoint.Status.OBSERVED)
    PainPointFactory(account=conta, status=PainPoint.Status.DISCARDED)
    PainPointFactory(account=AccountFactory())
    oportunidade = ImprovementOpportunityFactory(account=conta)
    ImprovementOpportunityFactory(
        account=conta, status=ImprovementOpportunity.Status.PRIORITIZED
    )
    PriorityAssessmentFactory(improvement_opportunity=oportunidade)
    PriorityAssessmentFactory(improvement_opportunity=ImprovementOpportunityFactory())

    por_conta = api.get(f"{reverse('painpoint-list')}?account={conta.pk}")
    por_estado = api.get(f"{reverse('painpoint-list')}?account={conta.pk}&status=discarded")
    priorizadas = api.get(f"{reverse('improvementopportunity-list')}?status=prioritized")
    por_oportunidade = api.get(
        f"{reverse('priorityassessment-list')}?improvement_opportunity={oportunidade.pk}"
    )

    assert len(por_conta.data) == 2
    assert len(por_estado.data) == 1
    assert len(priorizadas.data) == 1
    assert len(por_oportunidade.data) == 1


def test_a_avaliacao_publica_o_nome_de_quem_avaliou(api: APIClient) -> None:
    """`assessed_by` é id, e id não diz quem é.

    O board aprovado (`docs/design/dap-priorizacao-r1/`) escreve "Avaliado por {nome} em {data}",
    e a tela não tem como resolver o nome sozinha: `/users/` é fechada à Entrega, então metade de
    quem lê veria um número. `assessed_by_name` é campo derivado e só de leitura, no molde de
    `owner_name` (`KnowledgeArea`) e `user_name` (`ProjectMember`) — aditivo à `/api/v1/`.
    """
    oportunidade = ImprovementOpportunityFactory()

    criada = api.post(
        reverse("priorityassessment-list"), _payload_avaliacao(oportunidade.pk), format="json"
    )

    assert criada.status_code == 201, criada.data
    autor = User.objects.get(pk=criada.data["assessed_by"])
    assert criada.data["assessed_by_name"] == autor.get_full_name()
    # E o campo é derivado: o corpo não o escreve.
    assert "assessed_by_name" not in _payload_avaliacao(oportunidade.pk)


def test_a_avaliacao_sem_avaliador_devolve_nome_vazio_e_nao_quebra(api: APIClient) -> None:
    """Avaliação de shell, de migração ou de usuário removido tem `assessed_by` nulo.

    O `default=""` do serializer é o que impede o `source="assessed_by.get_full_name"` de estourar
    no nulo — e a tela degrada para "Avaliado em {data}" em vez de escrever "Avaliado por  em".
    """
    avaliacao = PriorityAssessmentFactory(assessed_by=None)

    lida = api.get(reverse("priorityassessment-detail", args=[avaliacao.pk]))

    assert lida.status_code == 200, lida.data
    assert lida.data["assessed_by"] is None
    assert lida.data["assessed_by_name"] == ""
