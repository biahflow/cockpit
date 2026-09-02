"""Regressão: o Discovery atravessa para o One como **dado**, atrás da marca (FDD 051, ADR 0060).

Os onze modelos do levantamento existem com nome canônico desde as Fases 3 e 4 da ontologia
(ADR 0049, ADR 0054) e **nenhum atravessava**: `portal.build_snapshot` não tinha uma chave sequer.
O Discovery chegava ao cliente como documento, e o que separa o One de um Drive compartilhado é
chegar navegável.

O que este arquivo guarda não é a existência das quatro chaves — disso cuidam as duas guardas do
snapshot. É o conjunto de recortes que fazem a projeção ser honesta, e cada um deles falha em
silêncio se for desfeito:

* **Nada atravessa sem `published_at`, e não há exceção.** Publicar é a revisão humana que a
  regra 1 da §3 do `docs/ontology/language-map.md` exige, e ela tem autor. O AS-IS entrou nessa
  regra com os outros quatro: "o AS-IS *validado*" da §3 era um qualificador sem lastro no
  schema, como "revisada e publicável" era para a `Evidence`.
* **As listas de id vêm filtradas ao que atravessou.** `finding_ids` e `pain_point_ids` crus
  apontariam para o que ficou de fora, e o cliente leria afirmação com nada atrás.
* **Metadado, nunca material bruto.** `raw_excerpt`, `content_hash`, `rationale`, os pesos da
  fórmula e os nove insumos de custo não cruzam a fronteira em chave nenhuma.
* **`unknown` atravessa.** É lacuna declarada; sumir com ele faz o cliente achar que não há
  pergunta em aberto.
* **O mesmo Discovery sai em todos os projetos da conta.** É a decisão (a) da fatia — o
  levantamento é da `Account`, e o One deduplica por id.
"""

from decimal import Decimal

import pytest
from django.utils import timezone

from apps.core import portal
from apps.core.models import (
    Evidence,
    Finding,
    ImprovementOpportunity,
    PainPoint,
    PriorityAssessment,
    Process,
    ProcessStep,
    SolutionHypothesis,
    User,
)
from apps.core.tests.factories import (
    AccountFactory,
    EngagementFactory,
    EvidenceFactory,
    FindingFactory,
    ImprovementOpportunityFactory,
    PainPointFactory,
    ProjectFactory,
    UserFactory,
)

pytestmark = pytest.mark.django_db


def _publica(obj, autor: User):  # type: ignore[no-untyped-def]
    """Carimba a marca direto no modelo. A action é exercida na regressão irmã da cadeia."""
    obj.published_at = timezone.now()
    obj.published_by = autor
    obj.save(update_fields=["published_at", "published_by", "updated_at"])
    return obj


@pytest.fixture
def autor() -> User:
    return UserFactory(role=User.Role.ADMIN)


# --- 1 e 2. O AS-IS mapeado ---------------------------------------------------


def test_o_as_is_da_conta_sai_com_os_passos_vivos_e_as_seis_letras(autor: User) -> None:
    """As seis chaves ficam **em português** e isso é deliberado: elas *são* o P-S-D-T-E-R.

    O docstring de `ProcessStep` explica por quê — renomear ou juntar faria o levantamento da
    reunião deixar de casar com o formulário. A §5 do mapa de linguagem bane português em nome de
    **modelo**, não de campo, e o snapshot já leva `pendencias` pelo mesmo tipo de razão.

    O mapa **publicado** é que sai. `outro` está publicado **e** arquivado, e fica de fora: as
    duas condições valem juntas, e é a mesma leitura de `_findings` um bloco acima.
    """
    projeto = ProjectFactory()
    conta = projeto.engagement.account
    mapa = _publica(Process.objects.create(account=conta, name="Faturamento", position=0), autor)
    ProcessStep.objects.create(
        process=mapa,
        name="Conferir pedidos",
        position=0,
        pessoas="Duas analistas",
        sistema="ERP",
        dados="Pedido e tabela de preço",
        tempo="90 minutos",
        erro="Preço desatualizado",
        retrabalho="Nota cancelada e reemitida",
    )
    arquivado = ProcessStep.objects.create(process=mapa, name="Passo removido", position=1)
    arquivado.archive()
    outro = _publica(Process.objects.create(account=conta, name="Expedição", position=1), autor)
    outro.archive()
    Process.objects.create(account=conta, name="Compras", position=2)  # publicado por ninguém

    blocos = portal.build_snapshot(projeto)["processes"]

    assert [bloco["name"] for bloco in blocos] == ["Faturamento"]
    assert blocos[0]["position"] == 0
    assert "updated_at" in blocos[0]
    passos = blocos[0]["steps"]
    assert [passo["name"] for passo in passos] == ["Conferir pedidos"]
    assert passos[0]["pessoas"] == "Duas analistas"
    assert passos[0]["sistema"] == "ERP"
    assert passos[0]["dados"] == "Pedido e tabela de preço"
    assert passos[0]["tempo"] == "90 minutos"
    assert passos[0]["erro"] == "Preço desatualizado"
    assert passos[0]["retrabalho"] == "Nota cancelada e reemitida"


def test_os_nove_insumos_do_custo_nao_atravessam_em_item_nenhum(autor: User) -> None:
    """São o cálculo interno do custo do estado atual, e a §3 não os lista.

    Um total parcial lido sem quem o levantou por perto vira "vocês disseram que eu perco tanto
    por mês" — o argumento que `test_processo_nao_volta_ao_cliente.py` guarda desde a FDD 039 e
    que a abertura do bloco do AS-IS **não** afrouxou.
    """
    projeto = ProjectFactory()
    _publica(
        Process.objects.create(
            account=projeto.engagement.account,
            name="Faturamento",
            volume_mes=400,
            tempo_horas=Decimal("1.50"),
            pessoas=2,
            custo_hora=Decimal("70.00"),
            retrabalho_mes=Decimal("9000.00"),
            erros_mes=Decimal("500.00"),
            perdas_mes=Decimal("200.00"),
            espera_mes=Decimal("100.00"),
            risco_mes=Decimal("50.00"),
        ),
        autor,
    )

    bloco = portal.build_snapshot(projeto)["processes"][0]

    for insumo in ("volume_mes", "tempo_horas", "pessoas", "custo_hora", "retrabalho_mes",
                   "erros_mes", "perdas_mes", "espera_mes", "risco_mes"):
        assert insumo not in bloco, f"'{insumo}' é conta interna e não pode sair"
    assert "registered_by" not in bloco
    assert "source_project" not in bloco


# --- 3. O escopo é a conta ----------------------------------------------------


def test_o_discovery_da_conta_sai_no_snapshot_de_todos_os_projetos_dela(autor: User) -> None:
    """A decisão (a) da fatia: o levantamento pende da `Account`, e o One deduplica por id.

    Dois projetos em **engagements diferentes** da mesma conta, e um projeto de fora. Recortar
    pelo projeto que descobriu perderia exatamente a propriedade que motivou a FK de conta — o
    mapa da operação sobrevive à venda que o levantou.
    """
    conta = AccountFactory()
    um = ProjectFactory(engagement=EngagementFactory(account=conta))
    outro = ProjectFactory(engagement=EngagementFactory(account=conta))
    de_fora = ProjectFactory()
    _publica(Process.objects.create(account=conta, name="Faturamento"), autor)
    _publica(FindingFactory(account=conta, statement="O fechamento leva dois dias."), autor)

    de_um = portal.build_snapshot(um)
    do_outro = portal.build_snapshot(outro)
    alheio = portal.build_snapshot(de_fora)

    assert [b["name"] for b in de_um["processes"]] == ["Faturamento"]
    assert [b["name"] for b in do_outro["processes"]] == ["Faturamento"]
    assert [f["id"] for f in de_um["findings"]] == [f["id"] for f in do_outro["findings"]]
    assert alheio["processes"] == []
    assert alheio["findings"] == []


# --- 4, 5 e 6. Os achados e o que os sustenta ---------------------------------


def test_so_o_achado_publicado_e_vivo_atravessa(autor: User) -> None:
    projeto = ProjectFactory()
    conta = projeto.engagement.account
    publicado = _publica(FindingFactory(account=conta, statement="Publicado."), autor)
    FindingFactory(account=conta, statement="Interno, ainda em deliberação.")
    arquivado = _publica(FindingFactory(account=conta, statement="Publicado e arquivado."), autor)
    arquivado.archive()

    achados = portal.build_snapshot(projeto)["findings"]

    assert [achado["id"] for achado in achados] == [publicado.pk]
    assert achados[0]["statement"] == "Publicado."


def test_o_fato_publicado_sai_com_fonte_e_o_unknown_nao_e_omitido(autor: User) -> None:
    """`unknown` **atravessa e é rotulado**, e é a decisão que o torna útil.

    O One o renderiza como lacuna declarada. Omiti-lo faria o cliente achar que não há pergunta em
    aberto sobre a operação dele — a lacuna disfarçada, que é sempre pior que a lacuna admitida.
    """
    projeto = ProjectFactory()
    conta = projeto.engagement.account
    fonte = _publica(EvidenceFactory(account=conta, reference="Entrevista 12/08, 00:14:32"), autor)
    fato = FindingFactory(
        account=conta,
        statement="O fechamento leva dois dias.",
        epistemic_status=Finding.EpistemicStatus.FACT,
        reviewed_by=autor,
        confidence=80,
    )
    fato.evidences.add(fonte)
    _publica(fato, autor)
    _publica(
        FindingFactory(
            account=conta,
            statement="Não sabemos quantas notas são refeitas.",
            epistemic_status=Finding.EpistemicStatus.UNKNOWN,
        ),
        autor,
    )

    achados = {a["epistemic_status"]: a for a in portal.build_snapshot(projeto)["findings"]}

    assert set(achados) == {"fact", "unknown"}
    assert achados["fact"]["confidence"] == 80
    assert achados["fact"]["evidences"] != []
    assert achados["fact"]["evidences"][0]["reference"] == "Entrevista 12/08, 00:14:32"
    assert achados["fact"]["evidences"][0]["kind"] == Evidence.Kind.INTERVIEW
    assert achados["unknown"]["evidences"] == []


def test_a_fonte_leva_so_o_metadado_e_so_se_ela_mesma_estiver_publicada(autor: User) -> None:
    """Duas regras num cenário só, porque as duas protegem a mesma fronteira.

    `raw_excerpt` e `content_hash` são o material bruto e o carimbo dele — a §3 proíbe transcrição
    e evidência não revisada. `reference` atravessa porque é a **citação**, de onde veio e não o
    que foi dito, e é o que torna a fonte conferível; o precedente é o `has_transcript` de
    `meetings`. E a fonte não publicada fica de fora **mesmo estando no M2M de um achado
    publicado**: senão a lista apontaria para o que não atravessou.
    """
    projeto = ProjectFactory()
    conta = projeto.engagement.account
    publicada = _publica(
        EvidenceFactory(
            account=conta,
            raw_excerpt="A gente confere nota por nota, e no fim do mês são umas quatrocentas.",
            reference="Entrevista 12/08",
        ),
        autor,
    )
    interna = EvidenceFactory(account=conta, raw_excerpt="Comentário fora de ata.")
    achado = FindingFactory(account=conta, statement="Conferência é manual.")
    achado.evidences.add(publicada, interna)
    _publica(achado, autor)

    fontes = portal.build_snapshot(projeto)["findings"][0]["evidences"]

    assert [fonte["id"] for fonte in fontes] == [publicada.pk]
    assert "raw_excerpt" not in fontes[0]
    assert "content_hash" not in fontes[0]
    assert set(fontes[0]) == {"id", "kind", "reference", "captured_at"}


# --- 7. As dores --------------------------------------------------------------


def test_a_dor_filtra_os_ids_e_nao_transforma_lacuna_em_zero(autor: User) -> None:
    """`impact_estimate` nulo sai `None`, **nunca `0`**: zerar afirma que a dor não custa nada."""
    projeto = ProjectFactory()
    conta = projeto.engagement.account
    achado_publicado = _publica(FindingFactory(account=conta, statement="Publicado."), autor)
    achado_interno = FindingFactory(account=conta, statement="Interno.")
    dor = PainPointFactory(account=conta, title="Fechamento trava", description="Dois dias.")
    dor.findings.add(achado_publicado, achado_interno)
    _publica(dor, autor)
    quantificada = PainPointFactory(account=conta, title="Retrabalho", impact_estimate=Decimal("12000.00"))
    quantificada.findings.add(achado_publicado)
    _publica(quantificada, autor)
    PainPointFactory(account=conta, title="Dor interna")

    dores = {d["title"]: d for d in portal.build_snapshot(projeto)["pain_points"]}

    assert set(dores) == {"Fechamento trava", "Retrabalho"}
    assert dores["Fechamento trava"]["finding_ids"] == [achado_publicado.pk]
    assert dores["Fechamento trava"]["impact_estimate"] is None
    assert dores["Fechamento trava"]["description"] == "Dois dias."
    assert dores["Fechamento trava"]["impact_type"] == PainPoint.ImpactType.OPERATIONAL
    assert dores["Fechamento trava"]["status"] == PainPoint.Status.OBSERVED
    assert dores["Retrabalho"]["impact_estimate"] == 12000.0


# --- 8 e 9. As oportunidades de melhoria --------------------------------------


def _oportunidade_publicada(conta, autor: User) -> ImprovementOpportunity:  # type: ignore[no-untyped-def]
    dor = _publica(PainPointFactory(account=conta, title="Fechamento trava"), autor)
    oportunidade = ImprovementOpportunityFactory(account=conta, title="Automatizar conferência")
    oportunidade.pain_points.add(dor)
    return _publica(oportunidade, autor)


def test_a_oportunidade_leva_so_a_versao_vigente_e_nada_do_criterio_interno(autor: User) -> None:
    """O score sai; o **critério** que o produziu, não.

    `weights` e `formula_key` são o critério interno, e é justamente a mudança de critério que a
    versão existe para não confundir quem lê sem contexto. `rationale` é proibição literal da §3
    e `assessed_by` é pessoa interna. **`rank` não é emitido**, e é desvio consciente: emitir o
    rank da conta inteira entregaria `2, 4, 7` e a dedução de que existem itens escondidos que
    superam os mostrados; recalculá-lo só entre os publicados criaria uma segunda definição de
    rank, que é exatamente o que este repositório recusou ao não persistir o campo.
    """
    projeto = ProjectFactory()
    oportunidade = _oportunidade_publicada(projeto.engagement.account, autor)
    PriorityAssessment.objects.create(
        improvement_opportunity=oportunidade,
        impact=2, evidence_strength=2, feasibility=2, time_to_value=2, economics=2,
        rationale="Interno: o cliente ainda não sabe que o time dele é o gargalo.",
        assessed_by=autor,
    )
    vigente = PriorityAssessment.objects.create(
        improvement_opportunity=oportunidade,
        impact=5, evidence_strength=4, feasibility=3, time_to_value=4, economics=5,
        rationale="Interno também.",
        assessed_by=autor,
    )
    antiga = PriorityAssessment.objects.filter(version=1).get()

    bloco = portal.build_snapshot(projeto)["improvement_opportunities"][0]
    avaliacao = bloco["priority_assessment"]

    assert avaliacao["version"] == vigente.version == 2
    assert avaliacao["version"] != antiga.version
    assert avaliacao["score"] == float(vigente.score)
    assert avaliacao["dimensions"] == {
        "impact": 5, "evidence_strength": 4, "feasibility": 3, "time_to_value": 4, "economics": 5
    }
    assert set(avaliacao) == {"version", "score", "dimensions"}
    assert "rank" not in bloco
    assert bloco["title"] == "Automatizar conferência"


def test_sem_avaliacao_a_oportunidade_sai_com_priority_assessment_nulo(autor: User) -> None:
    """`None`, e nunca zero: zero afirma que se avaliou e deu zero (a regra do não apurado)."""
    projeto = ProjectFactory()
    _oportunidade_publicada(projeto.engagement.account, autor)

    bloco = portal.build_snapshot(projeto)["improvement_opportunities"][0]

    assert bloco["priority_assessment"] is None


def test_as_apostas_vao_aninhadas_sem_as_descartadas_e_sem_a_nota_interna(autor: User) -> None:
    """Aninhadas porque as apostas de uma oportunidade são **concorrentes entre si**.

    Soltá-las numa lista irmã perderia a concorrência, que é a informação. `assumptions` fica
    fora: é a nota interna do que se está supondo.
    """
    projeto = ProjectFactory()
    oportunidade = _oportunidade_publicada(projeto.engagement.account, autor)
    escolhida = SolutionHypothesis.objects.create(
        improvement_opportunity=oportunidade,
        statement="Leitor de nota fiscal.",
        intervention="OCR sobre o PDF do fornecedor.",
        expected_effect="Conferência por exceção.",
        assumptions="Supondo que o fornecedor não mude o layout.",
        status=SolutionHypothesis.Status.CHOSEN,
    )
    SolutionHypothesis.objects.create(
        improvement_opportunity=oportunidade,
        statement="Descartada.",
        status=SolutionHypothesis.Status.DISCARDED,
    )
    arquivada = SolutionHypothesis.objects.create(
        improvement_opportunity=oportunidade, statement="Arquivada."
    )
    arquivada.archive()

    apostas = portal.build_snapshot(projeto)["improvement_opportunities"][0]["solution_hypotheses"]

    assert [aposta["id"] for aposta in apostas] == [escolhida.pk]
    assert apostas[0]["intervention"] == "OCR sobre o PDF do fornecedor."
    assert apostas[0]["expected_effect"] == "Conferência por exceção."
    assert apostas[0]["status"] == SolutionHypothesis.Status.CHOSEN
    assert "assumptions" not in apostas[0]


def test_a_oportunidade_filtra_as_dores_ao_que_atravessou(autor: User) -> None:
    projeto = ProjectFactory()
    conta = projeto.engagement.account
    publicada = _publica(PainPointFactory(account=conta, title="Publicada"), autor)
    interna = PainPointFactory(account=conta, title="Interna")
    oportunidade = ImprovementOpportunityFactory(account=conta, title="Automatizar")
    oportunidade.pain_points.add(publicada, interna)
    _publica(oportunidade, autor)

    bloco = portal.build_snapshot(projeto)["improvement_opportunities"][0]

    assert bloco["pain_point_ids"] == [publicada.pk]


# --- 10. O que nunca atravessa, em chave nenhuma ------------------------------


def test_nenhum_bloco_leva_pessoa_interna_racional_nem_material_bruto(autor: User) -> None:
    """A asserção sobre as **chaves**, e não sobre os valores, num cenário cheio.

    Um teste de valor passaria por o campo estar vazio na fábrica; a chave é o que denuncia a
    intenção. Sete nomes, e cada um é uma linha da §3: pessoa interna (`captured_by`,
    `reviewed_by`, `assessed_by`, `published_by`), racional da priorização (`rationale`) e
    material bruto do levantamento (`raw_excerpt`, `content_hash`).
    """
    projeto = ProjectFactory()
    conta = projeto.engagement.account
    fonte = _publica(EvidenceFactory(account=conta, reference="Entrevista"), autor)
    fato = FindingFactory(
        account=conta,
        statement="Fato.",
        epistemic_status=Finding.EpistemicStatus.FACT,
        reviewed_by=autor,
    )
    fato.evidences.add(fonte)
    _publica(fato, autor)
    dor = PainPointFactory(account=conta, title="Dor")
    dor.findings.add(fato)
    _publica(dor, autor)
    oportunidade = ImprovementOpportunityFactory(account=conta, title="Oportunidade")
    oportunidade.pain_points.add(dor)
    _publica(oportunidade, autor)
    PriorityAssessment.objects.create(
        improvement_opportunity=oportunidade,
        impact=3, evidence_strength=3, feasibility=3, time_to_value=3, economics=3,
        rationale="Interno.", assessed_by=autor,
    )
    _publica(Process.objects.create(account=conta, name="Faturamento"), autor)

    snapshot = portal.build_snapshot(projeto)
    proibidas = {
        "reviewed_by", "captured_by", "assessed_by", "published_by", "rationale",
        "raw_excerpt", "content_hash", "weights", "formula_key",
    }
    blocos = [
        *snapshot["processes"],
        *(passo for bloco in snapshot["processes"] for passo in bloco["steps"]),
        *snapshot["findings"],
        *(fonte for achado in snapshot["findings"] for fonte in achado["evidences"]),
        *snapshot["pain_points"],
        *snapshot["improvement_opportunities"],
        *(
            bloco["priority_assessment"]
            for bloco in snapshot["improvement_opportunities"]
            if bloco["priority_assessment"] is not None
        ),
        *(
            aposta
            for bloco in snapshot["improvement_opportunities"]
            for aposta in bloco["solution_hypotheses"]
        ),
    ]

    assert blocos, "o cenário precisa produzir blocos, senão a asserção passa por ausência de dado"
    for bloco in blocos:
        vazadas = proibidas & set(bloco)
        assert not vazadas, f"chave(s) internas no snapshot do cliente: {sorted(vazadas)}"
