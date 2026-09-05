import { ArrowLeft, ChevronDown, ChevronUp, Coins, FlaskConical, Flame, Gauge, Plus, Target } from "lucide-react";
import { type FormEvent, useCallback, useEffect, useState } from "react";

import {
  api,
  createBusinessCase,
  createImprovementOpportunity,
  createPriorityAssessment,
  createSolutionHypothesis,
  decideBusinessCase,
  listBusinessCases,
  listImprovementOpportunities,
  listPainPointsByAccount,
  listPriorityAssessments,
  listSolutionHypotheses,
  updateBusinessCase,
  updateImprovementOpportunity,
  updateSolutionHypothesis,
} from "../api";
import { useAuth } from "../auth";
import { moeda } from "../dinheiro";
import { mensagemDeFalha } from "../erros";
import type {
  Account,
  BusinessCase,
  BusinessCaseStatus,
  ImprovementOpportunity,
  ImprovementOpportunityStatus,
  PainPoint,
  PriorityAssessment,
  Process,
  SolutionHypothesis,
  SolutionHypothesisStatus,
} from "../types";

/**
 * A tela do PRIORITIZE — *"onde devemos atuar?"* (`docs/metodologia-fde.md`).
 *
 * Governada pelo DAP `docs/design/dap-priorizacao-r1/`, revisão 1, decisões
 * **A1 · B1 · C1 · D1 · E1** mais a primitiva `.row-meta`. Mudar a superfície exige revisão nova
 * do pacote, não julgamento na hora.
 *
 * **A1 — tela própria, e não a nona seção do detalhe da conta.** A lista ranqueada é a que precisa
 * ser lida do topo, porque a ordem *é* o conteúdo; empurrá-la para o rodapé de uma página com oito
 * seções seria escondê-la. O mandato é cadastro que se consulta, o backlog é lista de trabalho que
 * se percorre.
 *
 * **A lacuna é `—`, nunca `0`.** Zero afirma que a oportunidade foi avaliada e vale zero; o traço
 * diz que ninguém avaliou. `score`, `assessment_version` e `rank` vêm nulos **juntos** do servidor
 * (FDD 048), e é a mesma regra que `Process.custo_do_estado_atual` já aplica com `nao_apurado`.
 */

/** Mapa de **variante**, nunca de cor (ADR 0026): `"state--1"`, jamais `"bg-emerald-50 …"`.
 *
 * `open` é o neutro — uma oportunidade recém-aberta não é aviso nem sucesso, é a ausência de
 * avaliação. `discarded` é o vermelho porque descartar é uma conclusão, e ela precisa se distinguir
 * de "ainda não olhamos" à distância de um relance. */
const OPORTUNIDADE_BADGE: Record<ImprovementOpportunityStatus, string> = {
  open: "state--off", assessing: "state--0", prioritized: "state--1", discarded: "state--3",
};
const OPORTUNIDADE_LABEL: Record<ImprovementOpportunityStatus, string> = {
  open: "Aberta", assessing: "Em avaliação", prioritized: "Priorizada", discarded: "Descartada",
};

/** Decisão **D1**: a competição entre hipóteses fica legível pela pílula e pela ordem, numa lista
 * vertical que sobrevive a 390px sem um segundo layout. */
const HIPOTESE_BADGE: Record<SolutionHypothesisStatus, string> = {
  proposed: "state--off", chosen: "state--1", discarded: "state--3",
};
const HIPOTESE_LABEL: Record<SolutionHypothesisStatus, string> = {
  proposed: "Proposta", chosen: "Escolhida", discarded: "Descartada",
};

/** O Business Case (FDD 053), governado pelo DAP `dap-discovery-session-e-business-case-r2` —
 * decisões **A1** e **F1**. Mapa de **variante**, nunca de cor (ADR 0026): rascunho é o neutro de
 * sempre, aprovado é o mesmo verde de "Escolhida", recusado o mesmo vermelho de "Descartada". */
const BUSINESS_CASE_BADGE: Record<BusinessCaseStatus, string> = {
  draft: "state--off", approved: "state--1", rejected: "state--3",
};

/**
 * O rascunho do business case abre **sem número escolhido**, pelo mesmo argumento de
 * `blankAvaliacao`: um investimento pré-preenchido é a casa inventando o que ninguém orçou ainda.
 */
const blankBusinessCaseDraft = { investment: "", expected_return_year: "", payback_months: "", rationale: "" };

/**
 * Sincroniza o rascunho local com o que o servidor tem gravado — só para um rascunho vivo
 * (decidido não se edita, e o formulário nem aparece nesse estado). Sem business case nenhum, o
 * formulário de criação abre em branco, pelo mesmo argumento de `blankAvaliacao`.
 */
function rascunhoDoBusinessCase(businessCase: BusinessCase | undefined) {
  if (!businessCase || businessCase.status !== "draft") return blankBusinessCaseDraft;
  return {
    investment: businessCase.investment ?? "",
    expected_return_year: businessCase.expected_return_year ?? "",
    payback_months: businessCase.payback_months === null ? "" : String(businessCase.payback_months),
    rationale: businessCase.rationale,
  };
}

/**
 * As cinco dimensões do Opportunity Score, **na ordem em que a pergunta é feita** — a mesma de
 * `backend/apps/core/priority.py`. Ela não se reordena: é ela que permite conferir "avaliei tudo?"
 * olhando a tela, como o P-S-D-T-E-R do processo.
 *
 * Os rótulos ficam em inglês porque são o vocabulário canônico do critério, e é assim que o board
 * os desenha nos cinco cartões — traduzi-los faria a tela e a fórmula falarem nomes diferentes do
 * mesmo eixo.
 */
const DIMENSOES = [
  ["impact", "Impact"],
  ["evidence_strength", "Evidence strength"],
  ["feasibility", "Feasibility"],
  ["time_to_value", "Time to value"],
  ["economics", "Economics"],
] as const satisfies ReadonlyArray<readonly [keyof CamposDaAvaliacao, string]>;

type CamposDaAvaliacao = Pick<
  PriorityAssessment, "impact" | "evidence_strength" | "feasibility" | "time_to_value" | "economics"
>;

const NOTAS = [1, 2, 3, 4, 5];

/**
 * O rascunho da avaliação abre **sem nota escolhida**, e o vazio é a decisão.
 *
 * É o mesmo argumento da ADR 0034 para o rótulo da evidência: um select que já abre em "3" é a
 * casa escolhendo por quem não escolheu, sempre para o mesmo lado — e aqui o lado errado vira um
 * score que alguém leva para uma reunião. As cinco dimensões não têm default no modelo, e não
 * podem ganhar um na tela.
 */
const blankAvaliacao: Record<string, string> = {
  impact: "", evidence_strength: "", feasibility: "", time_to_value: "", economics: "",
};

const dataCurta = (iso: string) => new Date(iso).toLocaleDateString("pt-BR");

/** O score sai do servidor como `"78.00"` — texto, como todo decimal desta API. Um `—` aqui é a
 * ausência de avaliação, e nunca o número zero. */
const scoreLegivel = (score: string | null) =>
  score === null ? "—" : Number(score).toLocaleString("pt-BR", { maximumFractionDigits: 1 });

/**
 * O custo do estado atual congelado — decisão **F1**. `null` é "não apurado", nunca zero: a mesma
 * regra do `nao_apurado` de `Process`, um nível acima. Nenhum caminho desta função pode devolver
 * `moeda("0")` no lugar do `—`.
 */
const custoCongeladoLegivel = (custo: string | null) => custo === null ? "—" : `${moeda(custo)} / mês`;

/** `investment`/`expected_return_year` nulos são "ninguém orçou ainda", nunca zero — a mesma regra
 * um degrau acima, para o resumo do business case decidido. */
const dinheiroOuTraco = (valor: string | null) => valor === null ? "—" : moeda(valor);

/** Data **e** hora — a decisão é um carimbo, e "05/09/2026" sozinho não distingue duas decisões no
 * mesmo dia. */
const dataHoraCurta = (iso: string | null) =>
  iso === null ? "—" : new Date(iso).toLocaleString("pt-BR", { dateStyle: "short", timeStyle: "short" });

/**
 * A frase da lacuna (decisão **F1**), no vocabulário da própria decisão aprovada — não uma
 * composição por processo: a proveniência (`current_state_cost_source`) existe para quem precisar
 * conferir processo a processo, e esta frase é só o resumo que a decisão F1 já escreveu por
 * extenso: *"`—`, com a frase do servidor dizendo por que, quando nenhum processo da oportunidade
 * tem custo sustentado por fato."*
 */
const FRASE_DO_CUSTO_NAO_APURADO = "Nenhum processo desta oportunidade tem custo sustentado por fato. O número não é zero — não há insumo para dizer.";

export function PriorizacaoPage({ accountId }: { accountId: number }) {
  const { user } = useAuth();
  const [account, setAccount] = useState<Account>();
  const [dores, setDores] = useState<PainPoint[]>([]);
  const [oportunidades, setOportunidades] = useState<ImprovementOpportunity[]>([]);
  const [processos, setProcessos] = useState<Process[]>([]);
  const [avaliacoes, setAvaliacoes] = useState<PriorityAssessment[]>([]);
  const [hipoteses, setHipoteses] = useState<SolutionHypothesis[]>([]);
  const [businessCases, setBusinessCases] = useState<BusinessCase[]>([]);
  const [businessCaseDraft, setBusinessCaseDraft] = useState(blankBusinessCaseDraft);
  const [montandoBusinessCase, setMontandoBusinessCase] = useState(false);
  const [aberta, setAberta] = useState<number | null>(null);
  const [selecionadas, setSelecionadas] = useState<number[]>([]);
  const [agrupando, setAgrupando] = useState(false);
  const [tituloDaOportunidade, setTituloDaOportunidade] = useState("");
  const [avaliacaoDraft, setAvaliacaoDraft] = useState(blankAvaliacao);
  const [rationale, setRationale] = useState("");
  const [hipoteseDraft, setHipoteseDraft] = useState("");
  const [error, setError] = useState("");
  const [semAcesso, setSemAcesso] = useState(false);
  const [busy, setBusy] = useState(false);

  const load = useCallback(() => Promise.all([
    api<Account>(`/accounts/${accountId}/`),
    listPainPointsByAccount(accountId),
    listImprovementOpportunities(accountId),
    // Os processos entram só para nomear onde a dor foi observada: `PainPoint` carrega o id do
    // processo e não o nome dele, e "Observado em: 12" não diz nada a quem lê.
    api<Process[]>(`/processes/?account=${accountId}`),
  ]).then(([loadedAccount, loadedDores, loadedOportunidades, loadedProcessos]) => {
    setAccount(loadedAccount); setDores(loadedDores);
    setOportunidades(loadedOportunidades); setProcessos(loadedProcessos);
    setSemAcesso(false);
  }).catch((cause: unknown) => {
    // O recorte da Entrega (RFC 0003) chega como 404 na conta: quem não participa de projeto
    // nenhum dela não a alcança pela rota. Só quem é da Entrega vê a frase — para admin e Vendas
    // um 404 significa mesmo "esta conta não existe", e trocar as duas mensagens mandaria alguém
    // procurar uma permissão que não é o problema.
    const status = (cause as { status?: number }).status;
    if (user?.role === "delivery" && (status === 403 || status === 404)) { setSemAcesso(true); return; }
    setError(mensagemDeFalha(cause));
  }), [accountId, user?.role]);
  useEffect(() => { void load(); }, [load]);

  /**
   * O detalhe da oportunidade carrega **sob demanda**, e as duas listas juntas.
   *
   * Buscar histórico e hipóteses de toda oportunidade no `load()` custaria duas requisições por
   * linha numa tela cuja lista é justamente o que se percorre. O detalhe é um por vez (decisão do
   * acordeão), então o custo é o de uma abertura.
   */
  const abrirDetalhe = useCallback(async (id: number) => {
    setError("");
    if (aberta === id) { setAberta(null); return; }
    setAberta(id); setAvaliacoes([]); setHipoteses([]); setBusinessCases([]);
    setAvaliacaoDraft(blankAvaliacao); setRationale(""); setHipoteseDraft("");
    setBusinessCaseDraft(blankBusinessCaseDraft); setMontandoBusinessCase(false);
    try {
      const [loadedAvaliacoes, loadedHipoteses, loadedBusinessCases] = await Promise.all([
        listPriorityAssessments(id), listSolutionHypotheses(id), listBusinessCases(id),
      ]);
      setAvaliacoes(loadedAvaliacoes); setHipoteses(loadedHipoteses);
      setBusinessCases(loadedBusinessCases);
      setBusinessCaseDraft(rascunhoDoBusinessCase(loadedBusinessCases[0]));
    } catch (cause) { setError(mensagemDeFalha(cause)); }
  }, [aberta]);

  const recarregarDetalhe = useCallback(async (id: number) => {
    const [loadedAvaliacoes, loadedHipoteses, loadedBusinessCases] = await Promise.all([
      listPriorityAssessments(id), listSolutionHypotheses(id), listBusinessCases(id),
    ]);
    setAvaliacoes(loadedAvaliacoes); setHipoteses(loadedHipoteses);
    setBusinessCases(loadedBusinessCases);
    setBusinessCaseDraft(rascunhoDoBusinessCase(loadedBusinessCases[0]));
  }, []);

  async function agrupar(event: FormEvent<HTMLFormElement>) {
    event.preventDefault(); setError(""); setBusy(true);
    try {
      await createImprovementOpportunity({
        account: accountId, title: tituloDaOportunidade, pain_points: selecionadas,
      });
      setTituloDaOportunidade(""); setSelecionadas([]); setAgrupando(false);
      await load();
    } catch (cause) { setError(mensagemDeFalha(cause)); }
    finally { setBusy(false); }
  }

  /**
   * Avaliar **cria a versão seguinte**; não existe editar (a rota nem expõe `PATCH`).
   *
   * É a razão de o modelo ser versionado: uma avaliação que se reescreve apaga o critério
   * anterior, e com ele a única resposta possível para "por que este item subiu?".
   */
  async function avaliar(event: FormEvent<HTMLFormElement>, id: number) {
    event.preventDefault(); setError(""); setBusy(true);
    try {
      await createPriorityAssessment({
        improvement_opportunity: id,
        impact: Number(avaliacaoDraft.impact),
        evidence_strength: Number(avaliacaoDraft.evidence_strength),
        feasibility: Number(avaliacaoDraft.feasibility),
        time_to_value: Number(avaliacaoDraft.time_to_value),
        economics: Number(avaliacaoDraft.economics),
        rationale,
      });
      setAvaliacaoDraft(blankAvaliacao); setRationale("");
      await recarregarDetalhe(id);
      // O score, a versão e o rank da linha são derivados: quem os recalcula é o servidor, e a
      // tela relê em vez de adivinhar o número novo.
      await load();
    } catch (cause) { setError(mensagemDeFalha(cause)); }
    finally { setBusy(false); }
  }

  async function mudarSituacao(oportunidade: ImprovementOpportunity, status: ImprovementOpportunityStatus) {
    setError("");
    try { await updateImprovementOpportunity(oportunidade.id, { status }); await load(); }
    catch (cause) { setError(mensagemDeFalha(cause)); }
  }

  async function registrarHipotese(event: FormEvent<HTMLFormElement>, id: number) {
    event.preventDefault(); setError(""); setBusy(true);
    try {
      await createSolutionHypothesis({ improvement_opportunity: id, statement: hipoteseDraft });
      setHipoteseDraft("");
      await recarregarDetalhe(id);
    } catch (cause) { setError(mensagemDeFalha(cause)); }
    finally { setBusy(false); }
  }

  async function mudarHipotese(hipotese: SolutionHypothesis, status: SolutionHypothesisStatus) {
    setError("");
    try {
      await updateSolutionHypothesis(hipotese.id, { status });
      await recarregarDetalhe(hipotese.improvement_opportunity);
    } catch (cause) { setError(mensagemDeFalha(cause)); }
  }

  /** Alterna o formulário em branco — é a mesma porta do estado 2 ("Montar business case") e do
   * estado 6 ("Montar outro business case"): a oportunidade aceita outro depois de um recusado. */
  function alternarFormularioDeBusinessCase() {
    if (!montandoBusinessCase) setBusinessCaseDraft(blankBusinessCaseDraft);
    setMontandoBusinessCase(!montandoBusinessCase);
  }

  function payloadDoBusinessCaseDraft() {
    return {
      investment: businessCaseDraft.investment.trim() === "" ? null : businessCaseDraft.investment,
      expected_return_year: businessCaseDraft.expected_return_year.trim() === "" ? null : businessCaseDraft.expected_return_year,
      payback_months: businessCaseDraft.payback_months.trim() === "" ? null : Number(businessCaseDraft.payback_months),
      rationale: businessCaseDraft.rationale,
    };
  }

  async function criarBusinessCase(event: FormEvent<HTMLFormElement>, oportunidadeId: number, hipoteseId: number, avaliacaoId: number) {
    event.preventDefault(); setError(""); setBusy(true);
    try {
      await createBusinessCase({
        improvement_opportunity: oportunidadeId, solution_hypothesis: hipoteseId,
        priority_assessment: avaliacaoId, ...payloadDoBusinessCaseDraft(),
      });
      setMontandoBusinessCase(false);
      await recarregarDetalhe(oportunidadeId);
    } catch (cause) { setError(mensagemDeFalha(cause)); }
    finally { setBusy(false); }
  }

  /**
   * Aprovar ou rejeitar é **action**, nunca um `PATCH` de `status` (FDD 053) — mas os dois números
   * que a aprovação exige moram no rascunho local até este clique, porque o board não desenha um
   * "Salvar" separado das duas portas de decisão. Por isso o `PATCH` do que foi digitado acontece
   * **antes** da decisão, e com o mesmo corpo para as duas saídas: rejeitar não exige os números,
   * mas salva o que a pessoa escreveu do mesmo jeito.
   */
  async function decidirBusinessCase(oportunidadeId: number, businessCase: BusinessCase, outcome: "approved" | "rejected") {
    setError(""); setBusy(true);
    try {
      await updateBusinessCase(businessCase.id, payloadDoBusinessCaseDraft());
      await decideBusinessCase(businessCase.id, outcome);
      await recarregarDetalhe(oportunidadeId);
    } catch (cause) { setError(mensagemDeFalha(cause)); }
    finally { setBusy(false); }
  }

  if (semAcesso) return <section className="space-y-7">
    <a href={`/contas/${accountId}`} className="back-link"><ArrowLeft className="size-4" />Voltar para a conta</a>
    <section className="panel"><p className="empty-state">Você não participa de nenhum projeto desta conta.</p></section>
  </section>;
  if (error && !account) return <div role="alert" className="alert--error">{error}</div>;
  // O mesmo esqueleto de `ProcessDetailPage` — não um estado de carregamento novo.
  if (!account) return <div className="animate-pulse space-y-6"><div className="h-10 w-64 rounded-xl bg-slate-200" /><div className="h-56 rounded-2xl bg-white" /></div>;

  const nomeDoProcesso = (id: number | null) => processos.find(processo => processo.id === id)?.name ?? "";
  const agrupadas = new Set(oportunidades.flatMap(oportunidade => oportunidade.pain_points));
  // Descartada não é trabalho a fazer: ela some do topo da tela pelo mesmo motivo que sai do
  // ranking no servidor — uma lista de trabalho que aponta para lugar nenhum.
  const soltas = dores.filter(dor => !agrupadas.has(dor.id) && dor.status !== "discarded");
  /** Ranqueadas primeiro, e as **sem avaliação** no fim: elas não têm por onde ser ordenadas.
   *  O desempate é pelo id, para a ordem ser estável entre duas leituras — como no servidor. */
  const ranqueadas = [...oportunidades].sort((a, b) =>
    (a.rank ?? Number.MAX_SAFE_INTEGER) - (b.rank ?? Number.MAX_SAFE_INTEGER) || a.id - b.id);
  const vigente = avaliacoes.length
    ? avaliacoes.reduce((maior, atual) => (atual.version > maior.version ? atual : maior))
    : null;
  const anteriores = avaliacoes.filter(avaliacao => avaliacao.id !== vigente?.id)
    .sort((a, b) => b.version - a.version);
  // Uma só `chosen` viva por oportunidade (invariante da FDD 048) — é a porta do Business Case
  // (decisão A1). `businessCases[0]` é o mais recente (o servidor já ordena por
  // `-created_at, -id`): rejeitado não trava a próxima tentativa, e é o mais novo que a tela mostra.
  const hipoteseEscolhida = hipoteses.find(candidata => candidata.status === "chosen") ?? null;
  const businessCase = businessCases[0] ?? null;

  const notasDaAvaliacao = (avaliacao: PriorityAssessment) => DIMENSOES
    .map(([campo, rotulo]) => `${rotulo} ${avaliacao[campo]}`).join(" · ");

  return <section className="space-y-7">
    <a href={`/contas/${accountId}`} className="back-link"><ArrowLeft className="size-4" />Voltar para a conta</a>
    <header className="page-head">
      {/* "PRIORITIZE" é a fase da escada FDE, e o nome dela não se traduz. */}
      <p className="eyebrow">PRIORITIZE</p>
      <h1>Priorização — {account.name}</h1>
      <p>{soltas.length} {soltas.length === 1 ? "pain point sem oportunidade" : "pain points sem oportunidade"} · {oportunidades.length} {oportunidades.length === 1 ? "Improvement Opportunity" : "Improvement Opportunities"}</p>
    </header>
    {error && <p role="alert" className="alert--error">{error}</p>}

    {/* Decisão **E1**, a outra ponta: a dor se **registra** na tela do processo, ao lado da
        evidência que a sustenta, e se **agrupa** aqui. É neste painel que "o que ainda não foi
        olhado" fica visível — o único lugar do produto onde ele fica. */}
    <section className="panel space-y-4 sm:p-6">
      {/* `flex-wrap` e o botão em largura cheia abaixo de `sm`: `.panel-heading` é
          `justify-between` sem quebra, e em 390px o rótulo "Agrupar em oportunidade" — que o
          `.btn` não hifeniza — empurrava a página 44px para fora. É o que `e2e/responsive.spec.ts`
          mede, e é a mesma quebra que o board desenha na seção de mobile. */}
      <div className="panel-heading flex-wrap">
        <div className="flex min-w-0 items-center gap-3">
          <span className="metric-icon"><Flame className="size-4" /></span>
          <div>
            <h2 className="font-semibold text-ink">Pain points sem oportunidade</h2>
            <p className="text-sm text-slate-600">{soltas.length} {soltas.length === 1 ? "dor observada, ainda não agrupada" : "dores observadas, ainda não agrupadas"} em nenhuma oportunidade</p>
          </div>
        </div>
        <button type="button" className="btn btn--secondary w-full shrink-0 sm:w-auto" disabled={!selecionadas.length} onClick={() => setAgrupando(!agrupando)}>
          <Target className="size-4" />Agrupar em oportunidade
        </button>
      </div>
      {agrupando && selecionadas.length > 0 && <form className="form-grid" onSubmit={event => void agrupar(event)}>
        <label className="form-label sm:col-span-2">
          Título da oportunidade
          <input className="field" value={tituloDaOportunidade} maxLength={200} onChange={event => setTituloDaOportunidade(event.target.value)} placeholder="A mudança desejada, na frase de quem vai defendê-la" required />
        </label>
        <p className="text-sm text-slate-600 sm:col-span-2">{selecionadas.length} {selecionadas.length === 1 ? "dor entra" : "dores entram"} nesta oportunidade. Ela nasce sem Opportunity Score: avaliar registra a versão 1 do critério.</p>
        <button className="btn sm:col-span-2" type="submit" disabled={busy}><Plus className="size-4" />{busy ? "Criando…" : "Criar a oportunidade"}</button>
      </form>}
      {soltas.length ? <div className="panel-rows">{soltas.map(dor => <div className="row" key={dor.id}>
        <input
          type="checkbox" className="size-4 shrink-0 rounded border-slate-300 text-brand-500"
          aria-label={`Selecionar ${dor.title}`}
          checked={selecionadas.includes(dor.id)}
          onChange={event => setSelecionadas(event.target.checked
            ? [...selecionadas, dor.id]
            : selecionadas.filter(id => id !== dor.id))}
        />
        <span className="metric-icon"><Flame className="size-4" /></span>
        <div className="row-main">
          <strong>{dor.title}</strong>
          <span>{nomeDoProcesso(dor.process) ? `Observado em: ${nomeDoProcesso(dor.process)} · ` : ""}Impacto: {dor.impact_type_display}</span>
          {/* O achado é o que sustenta a dor: sem nenhum, ela não pode ser confirmada — e a
              contagem é o que faz isso ficar visível antes de alguém tentar. */}
          <span>{dor.findings.length ? `${dor.findings.length} ${dor.findings.length === 1 ? "achado" : "achados"} de sustentação` : "Nenhum achado de sustentação"}</span>
        </div>
      </div>)}</div> : <p className="empty-state">Nenhum pain point registrado. A dor entra pela tela do processo, ao lado da evidência que a sustenta.</p>}
    </section>

    <section className="panel space-y-4 sm:p-6">
      <div className="flex min-w-0 items-center gap-3">
        <span className="metric-icon"><Target className="size-4" /></span>
        <div>
          <h2 className="font-semibold text-ink">Improvement Opportunities</h2>
          <p className="text-sm text-slate-600">{oportunidades.length} {oportunidades.length === 1 ? "oportunidade, ranqueada" : "oportunidades, ranqueadas"} por Opportunity Score</p>
        </div>
      </div>
      {ranqueadas.length ? <div className="panel-rows">{ranqueadas.map(oportunidade => <div key={oportunidade.id}>
        <div className={`row ${aberta === oportunidade.id ? "bg-slate-50" : ""}`}>
          {/* O rank vem **derivado** do servidor e é nulo sem avaliação vigente. Escrever a
              posição da linha aqui inventaria um número que o backend recusa a produzir — e a
              lista passaria a afirmar uma ordem que nenhuma avaliação sustenta. */}
          <div className="row-main"><strong>{oportunidade.rank === null ? "—" : `#${oportunidade.rank}`} · {oportunidade.title}</strong></div>
          {/* Decisão **B1**: score e versão sempre visíveis, um ao lado do outro. Um score sem a
              versão é um número que não se pode comparar com o da semana passada.
              `.row-meta` e não irmãos soltos: `.row-main` é `flex-basis:0` e um título longo sem
              hífen vaza por cima do selo em 390px (DAP priorização r1, a sexta decisão). */}
          <div className="row-meta">
            <span className="type-label text-ink">Opportunity Score <strong className="tabular-nums">{scoreLegivel(oportunidade.score)}</strong></span>
            {oportunidade.assessment_version !== null && <span className="state state--off">v{oportunidade.assessment_version}</span>}
            <span className={`state ${OPORTUNIDADE_BADGE[oportunidade.status]}`}>{oportunidade.status_display}</span>
            <button
              type="button" className="btn btn--secondary btn--icon ml-auto"
              aria-label={`${aberta === oportunidade.id ? "Recolher" : "Abrir"} detalhe: ${oportunidade.title}`}
              onClick={() => void abrirDetalhe(oportunidade.id)}
            >{aberta === oportunidade.id ? <ChevronUp className="size-4" /> : <ChevronDown className="size-4" />}</button>
          </div>
        </div>
        {aberta === oportunidade.id && <div className="space-y-5 border-t border-dashed border-line bg-canvas px-5 py-6 sm:px-6">
          {vigente
            ? <>
                <p className="type-label text-muted">Opportunity Score — versão {vigente.version}</p>
                <div className="grid grid-cols-2 gap-3 sm:grid-cols-3 lg:grid-cols-5">
                  {DIMENSOES.map(([campo, rotulo]) => <div className="metric-card" key={campo}>
                    <span>{rotulo}</span><strong>{vigente[campo]}/5</strong>
                  </div>)}
                </div>
                {vigente.rationale && <p className="text-sm"><strong className="text-ink">Rationale:</strong> {vigente.rationale}</p>}
                {/* A data sai; o nome de quem avaliou, não: `PriorityAssessment` publica
                    `assessed_by` como id e a rota de usuários é fechada à Entrega — resolver o
                    nome aqui exigiria mudar o contrato, que é decisão e não conserto. */}
                <p className="type-meta text-muted">{vigente.assessed_by_name
                  ? `Avaliado por ${vigente.assessed_by_name} em ${dataCurta(vigente.created_at)}`
                  : `Avaliado em ${dataCurta(vigente.created_at)}`}</p>
              </>
            : <p className="empty-state">Sem Opportunity Score. Avaliar registra a versão 1 do critério.</p>}

          {/* Decisão **C1**: repriorizar cria uma versão nova e **não sobrescreve**. Uma tela que
              mostrasse só a vigente faria o produto parecer que sobrescreve, e quem reprioriza não
              teria como ver que o critério mudou. Custa um `<details>`. */}
          {avaliacoes.length > 0 && <>
            <h3 className="type-title text-ink">Avaliações</h3>
            <div className="panel panel--flush">
              <div className="panel-rows">
                {vigente && <div className="row bg-brand-50">
                  <div className="row-main">
                    <strong>Versão {vigente.version} — vigente</strong>
                    <span>{notasDaAvaliacao(vigente)} → Score {scoreLegivel(vigente.score)}</span>
                    <span>{dataCurta(vigente.created_at)}</span>
                  </div>
                  <div className="row-meta"><span className="state state--1">Vigente</span></div>
                </div>}
              </div>
              {anteriores.length > 0 && <details className="border-t border-line">
                <summary className="type-label cursor-pointer px-5 py-3.5 text-muted sm:px-6">Ver {anteriores.length} {anteriores.length === 1 ? "avaliação anterior" : "avaliações anteriores"}</summary>
                <div className="panel-rows border-t border-line">{anteriores.map(avaliacao => <div className="row" key={avaliacao.id}>
                  <div className="row-main">
                    <strong>Versão {avaliacao.version}</strong>
                    <span>{notasDaAvaliacao(avaliacao)} → Score {scoreLegivel(avaliacao.score)}</span>
                    <span>{dataCurta(avaliacao.created_at)}</span>
                  </div>
                  <div className="row-meta"><span className="state state--off">Substituída</span></div>
                </div>)}</div>
              </details>}
            </div>
          </>}

          <form className="form-grid" onSubmit={event => void avaliar(event, oportunidade.id)}>
            {DIMENSOES.map(([campo, rotulo]) => <label className="form-label" key={campo}>
              {rotulo}
              {/* Abre **sem nota escolhida** — ver `blankAvaliacao`. */}
              <select className="field" value={avaliacaoDraft[campo]} required onChange={event => setAvaliacaoDraft({ ...avaliacaoDraft, [campo]: event.target.value })}>
                <option value="" disabled>Selecione…</option>
                {NOTAS.map(nota => <option key={nota} value={nota}>{nota}</option>)}
              </select>
            </label>)}
            <label className="form-label sm:col-span-2">
              Rationale
              <textarea className="field min-h-20" value={rationale} onChange={event => setRationale(event.target.value)} placeholder="Por que estas notas, e o que faria elas mudarem" />
            </label>
            <button className="btn sm:col-span-2" type="submit" disabled={busy}>
              <Gauge className="size-4" />{avaliacoes.length ? "Repriorizar — cria a versão seguinte" : "Avaliar"}
            </button>
          </form>

          <label className="form-label">
            Situação
            <select className="field" value={oportunidade.status} onChange={event => void mudarSituacao(oportunidade, event.target.value as ImprovementOpportunityStatus)}>
              {(Object.keys(OPORTUNIDADE_LABEL) as ImprovementOpportunityStatus[]).map(status =>
                <option key={status} value={status}>{OPORTUNIDADE_LABEL[status]}</option>)}
            </select>
          </label>

          <h3 className="type-title text-ink">Pain points vinculados</h3>
          {oportunidade.pain_points.length ? <div className="panel panel--flush"><div className="panel-rows">
            {oportunidade.pain_points.map(id => {
              const dor = dores.find(candidata => candidata.id === id);
              return <div className="row" key={id}>
                <span className="metric-icon"><Flame className="size-4" /></span>
                <div className="row-main">
                  <strong>{dor?.title ?? "Dor arquivada"}</strong>
                  <span>{dor ? nomeDoProcesso(dor.process) || "Sem processo mapeado" : "Fora da listagem ativa"}</span>
                </div>
              </div>;
            })}
          </div></div> : <p className="empty-state">Nenhum pain point vinculado a esta oportunidade.</p>}

          <h3 className="type-title text-ink">Hipóteses</h3>
          {/* Hipóteses **concorrentes são o estado normal**: a mesma dor costuma admitir automação,
              redesenho e mudança de política, e escolher antes de escrever as três é decidir sem
              alternativa. O que não pode haver é duas escolhidas ao mesmo tempo — o servidor
              recusa com 400, e a mensagem dele chega inteira à faixa de erro. */}
          {hipoteses.length ? <div className="panel panel--flush"><div className="panel-rows">
            {hipoteses.map(hipotese => <div className="row" key={hipotese.id}>
              <span className="metric-icon"><FlaskConical className="size-4" /></span>
              <div className="row-main"><strong>{hipotese.statement}</strong></div>
              <div className="row-meta">
                <span className={`state ${HIPOTESE_BADGE[hipotese.status]}`}>{hipotese.status_display}</span>
                {/* O select **não repete** o que a pílula ao lado já diz: ele abre em "Mudar
                    para…" e lista só os outros dois estados. Selo e select mostrando o mesmo
                    rótulo lado a lado é a mesma informação em dois lugares, e quem lê fica sem
                    saber qual dos dois manda — a pílula é a leitura (o que o board aprovou na
                    decisão D1), o select é a ação. */}
                <select
                  className="field ml-auto w-auto shrink-0" value=""
                  aria-label={`Mudar a situação da hipótese: ${hipotese.statement}`}
                  onChange={event => void mudarHipotese(hipotese, event.target.value as SolutionHypothesisStatus)}
                >
                  <option value="" disabled>Mudar para…</option>
                  {(Object.keys(HIPOTESE_LABEL) as SolutionHypothesisStatus[])
                    .filter(status => status !== hipotese.status)
                    .map(status => <option key={status} value={status}>{HIPOTESE_LABEL[status]}</option>)}
                </select>
              </div>
            </div>)}
          </div></div> : <p className="empty-state">Nenhuma hipótese registrada para esta oportunidade.</p>}
          <form className="form-grid" onSubmit={event => void registrarHipotese(event, oportunidade.id)}>
            <label className="form-label sm:col-span-2">
              Hipótese
              <textarea className="field min-h-20" value={hipoteseDraft} onChange={event => setHipoteseDraft(event.target.value)} placeholder="A aposta, na frase de quem vai defendê-la" required />
            </label>
            <button className="btn sm:col-span-2" type="submit" disabled={busy}><Plus className="size-4" />Registrar hipótese</button>
          </form>

          {/* O Business Case (FDD 053, ADR 0069) — DAP `dap-discovery-session-e-business-case-r2`,
              decisões **A1** e **F1**. Nasce dentro do próprio `.panel` (não `--flush`), como o
              board desenha: um cartão próprio, com o selo de status no cabeçalho, e não mais uma
              linha da lista. Os seis estados: sem hipótese escolhida a porta nem existe; hipótese
              escolhida sem business case abre a porta; rascunho mostra os dois números com o custo
              do estado atual congelado ao lado; custo não apurado é `—` com o alerta (nunca
              `R$ 0,00`); decidido é leitura, com a decisão como ato — nunca um `PATCH` de `status`
              —; e recusado aceita outro. */}
          <div className="panel space-y-4">
            <div className="panel-heading">
              <h2 className="font-semibold text-ink">Business Case</h2>
              {businessCase && !montandoBusinessCase && <span className={`state ${BUSINESS_CASE_BADGE[businessCase.status]}`}>{businessCase.status_display}</span>}
            </div>
            {!hipoteseEscolhida
              ? <p className="empty-state">Escolha uma hipótese de solução para montar o business case — é sobre a intervenção escolhida que se orça.</p>
              : montandoBusinessCase
                ? <form className="form-grid" onSubmit={event => void criarBusinessCase(event, oportunidade.id, hipoteseEscolhida.id, vigente?.id ?? 0)}>
                    <label className="form-label">
                      Investimento
                      <input className="field" type="number" min="0" step="0.01" inputMode="decimal" placeholder="Não orçado" value={businessCaseDraft.investment} onChange={event => setBusinessCaseDraft({ ...businessCaseDraft, investment: event.target.value })} />
                    </label>
                    <label className="form-label">
                      Retorno esperado (12 meses)
                      <input className="field" type="number" min="0" step="0.01" inputMode="decimal" placeholder="Não orçado" value={businessCaseDraft.expected_return_year} onChange={event => setBusinessCaseDraft({ ...businessCaseDraft, expected_return_year: event.target.value })} />
                    </label>
                    <label className="form-label">
                      Payback (meses)
                      <input className="field" type="number" min="0" step="1" inputMode="numeric" placeholder="Não orçado" value={businessCaseDraft.payback_months} onChange={event => setBusinessCaseDraft({ ...businessCaseDraft, payback_months: event.target.value })} />
                    </label>
                    <label className="form-label sm:col-span-2">
                      Justificativa
                      <textarea className="field min-h-20" value={businessCaseDraft.rationale} onChange={event => setBusinessCaseDraft({ ...businessCaseDraft, rationale: event.target.value })} placeholder="Por que este investimento, e o que ele assume" required />
                    </label>
                    {/* `priority_assessment` é obrigatório no servidor e não tem valor sem avaliação
                        vigente — caso que a decisão A1 não previu porque, na prática, priorizar vem
                        antes de escolher hipótese. A guarda é defensiva: nunca manda `0`. */}
                    {!vigente && <p className="type-meta text-muted sm:col-span-2">Avalie esta oportunidade antes de registrar o business case — a avaliação vigente é o critério que ele cita.</p>}
                    <button className="btn sm:col-span-2" type="submit" disabled={busy || !vigente}>
                      <Coins className="size-4" />Registrar o business case
                    </button>
                  </form>
                : !businessCase
                  // Estado 2 — hipótese escolhida, sem business case: a porta aparece.
                  ? <>
                      <p className="text-sm text-slate-600">Nenhum registrado.</p>
                      <button type="button" className="btn btn--secondary" onClick={alternarFormularioDeBusinessCase}><Coins className="size-4" />Montar business case</button>
                    </>
                  : businessCase.status === "draft"
                    // Estados 3 e 4 — rascunho, com o custo congelado apurado ou `—` (F1).
                    ? <>
                        <div className="form-grid">
                          <label className="form-label">
                            Investimento
                            <input className="field" type="number" min="0" step="0.01" inputMode="decimal" placeholder="Não orçado" value={businessCaseDraft.investment} onChange={event => setBusinessCaseDraft({ ...businessCaseDraft, investment: event.target.value })} />
                          </label>
                          <label className="form-label">
                            Retorno esperado (12 meses)
                            <input className="field" type="number" min="0" step="0.01" inputMode="decimal" placeholder="Não orçado" value={businessCaseDraft.expected_return_year} onChange={event => setBusinessCaseDraft({ ...businessCaseDraft, expected_return_year: event.target.value })} />
                          </label>
                          <label className="form-label">
                            Payback (meses)
                            <input className="field" type="number" min="0" step="1" inputMode="numeric" placeholder="Não orçado" value={businessCaseDraft.payback_months} onChange={event => setBusinessCaseDraft({ ...businessCaseDraft, payback_months: event.target.value })} />
                          </label>
                          {/* `disabled`, no molde do `select` de origem contratual do Engagement:
                              o serializer não expõe caminho de escrita para este campo, e por isso
                              a tela também não oferece um — não há por onde, em vez de haver um
                              caminho que ninguém usa. */}
                          <label className="form-label">
                            Custo do estado atual · congelado
                            <input className="field" type="text" value={custoCongeladoLegivel(businessCase.current_state_cost)} disabled />
                          </label>
                        </div>
                        {/* Decisão F1: `—` nunca é silencioso — o alerta diz por quê, e não é o
                            `.alert--error` (nada falhou) nem um selo (isto interrompe a leitura). */}
                        {businessCase.current_state_cost === null
                          ? <p role="alert" className="alert--warn">{FRASE_DO_CUSTO_NAO_APURADO}</p>
                          : <p className="type-meta text-muted">Congelado na criação, a partir de {businessCase.current_state_cost_source.somados.length} {businessCase.current_state_cost_source.somados.length === 1 ? "processo sustentado" : "processos sustentados"} por fato. Editar os insumos depois não muda este número.</p>}
                        <label className="form-label">
                          Justificativa
                          <textarea className="field min-h-20" value={businessCaseDraft.rationale} onChange={event => setBusinessCaseDraft({ ...businessCaseDraft, rationale: event.target.value })} required />
                        </label>
                        {/* Aprovar exige os dois números; recusar nunca fica bloqueado — recusa-se
                            justamente o que não fechou conta (FDD 053). Os dois botões salvam o
                            rascunho digitado antes de decidir: o board não desenha um "Salvar"
                            próprio, e `decide/` lê os números já gravados, não o corpo da action. */}
                        <div className="flex flex-wrap gap-3">
                          <button type="button" className="btn" disabled={busy || !businessCaseDraft.investment.trim() || !businessCaseDraft.expected_return_year.trim()} onClick={() => void decidirBusinessCase(oportunidade.id, businessCase, "approved")}>Aprovar o investimento</button>
                          <button type="button" className="btn btn--secondary" disabled={busy} onClick={() => void decidirBusinessCase(oportunidade.id, businessCase, "rejected")}>Recusar</button>
                        </div>
                      </>
                    // Estados 5 e 6 — decidido: campos em leitura, botões de decisão somem (a tela
                    // não oferece o que o servidor recusaria com 409).
                    : <>
                        <p className="text-sm font-semibold text-ink">{dinheiroOuTraco(businessCase.investment)} investidos · {dinheiroOuTraco(businessCase.expected_return_year)} esperados em 12 meses</p>
                        <p className="type-meta text-muted">Payback em {businessCase.payback_months === null ? "—" : `${businessCase.payback_months} meses`} · custo do estado atual {custoCongeladoLegivel(businessCase.current_state_cost)}</p>
                        <p className="type-label text-muted">Decisão registrada</p>
                        {/* **Com autor**, como o board aprovado mostra: decidir investir é ato com
                            autor e carimbo — é o que o `clean()` do modelo protege ao recusar
                            `approved` sem `decided_by`. `decided_by_name` é derivado no servidor
                            (o mesmo `get_full_name` de `assessed_by_name` logo acima nesta tela),
                            e cai para a forma sem nome quando o autor foi removido: `SET_NULL`
                            existe, e "por ninguém" seria pior que não dizer. */}
                        <p className="text-sm text-ink">{businessCase.status === "approved" ? "Aprovado" : "Recusado"}{businessCase.decided_by_name ? ` por ${businessCase.decided_by_name}` : ""} em {dataHoraCurta(businessCase.decided_at)}.</p>
                        {businessCase.status === "approved"
                          ? <p className="type-meta text-muted">Business case decidido não se edita. Repensar o investimento é montar outro.</p>
                          : <button type="button" className="btn btn--secondary" onClick={alternarFormularioDeBusinessCase}><Coins className="size-4" />Montar outro business case</button>}
                      </>}
          </div>
        </div>}
      </div>)}</div> : <p className="empty-state">Nenhuma Improvement Opportunity. Agrupe pain points para abrir a primeira.</p>}
    </section>
  </section>;
}
