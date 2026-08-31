import { ArrowLeft, BadgeCheck, Coins, Flame, Plus, Quote, Trash2, Workflow } from "lucide-react";
import { type FormEvent, useCallback, useEffect, useState } from "react";

import { api, createPainPoint, listImprovementOpportunities, listPainPointsByProcess, updatePainPoint } from "../api";
import { useAuth } from "../auth";
import { ConfirmDialog } from "../components/Modal";
import { SUSTENTACAO_LABEL, sustentacaoBadgeClass } from "../components/StatusDot";
import { moeda } from "../dinheiro";
import { mensagemDeFalha } from "../erros";
import type { Evidence, EvidenceKind, EpistemicStatus, Finding, ImprovementOpportunity, PainPoint, PainPointImpactType, Process, ProcessStep } from "../types";

/**
 * As seis letras do P-S-D-T-E-R (`docs/metodologia-fde.md:106-110`), **rotuladas pela pergunta**.
 *
 * O rótulo é a pergunta e não o nome do campo porque é assim que ela é feita na reunião: "quem
 * faz?", "onde faz?". Um formulário que dissesse só "Sistema" faria quem preenche escrever o nome
 * do ERP e parar — a pergunta é o que lembra de anotar onde a etapa acontece de verdade.
 *
 * Uma lista só, lida pelo formulário **e** pela exibição: são as mesmas seis perguntas, na mesma
 * ordem, e duas cópias divergiriam na primeira vez que alguém reescrevesse uma delas. A ordem é a
 * do material e não se reordena — é ela que permite conferir "perguntei tudo?" olhando a tela.
 */
const PSDTER = [
  ["pessoas", "Pessoas — quem faz"],
  ["sistema", "Sistema — onde faz"],
  ["dados", "Dados — o que entra e sai"],
  ["tempo", "Tempo — quanto demora"],
  ["erro", "Erro — o que pode dar errado"],
  ["retrabalho", "Retrabalho — o que acontece quando dá errado"],
] as const satisfies ReadonlyArray<readonly [keyof CamposPsdter, string]>;

type CamposPsdter = Pick<ProcessStep, "pessoas" | "sistema" | "dados" | "tempo" | "erro" | "retrabalho">;

/**
 * Os nove insumos da fórmula do custo, na ordem em que ela é escrita.
 *
 * Os quatro primeiros são o **núcleo multiplicativo** — basta um faltar para a parcela inteira
 * não poder ser apurada, porque produto com fator desconhecido é desconhecido. Os cinco últimos
 * são aditivos em reais por mês, e cada um que falta sai da soma sozinho.
 *
 * A unidade vai no rótulo e não em placeholder: "Custo/hora" sem o "R$" faz alguém digitar o
 * salário mensal, e o erro só aparece no total, multiplicado por volume e por pessoas.
 */
const INSUMOS = [
  ["volume_mes", "Volume — ocorrências por mês", "núcleo"],
  ["tempo_horas", "Tempo — horas por ocorrência", "núcleo"],
  ["pessoas", "Pessoas — quantas por ocorrência", "núcleo"],
  ["custo_hora", "Custo/hora — R$", "núcleo"],
  ["retrabalho_mes", "Retrabalho — R$/mês", "aditivo"],
  ["erros_mes", "Erros — R$/mês", "aditivo"],
  ["perdas_mes", "Perdas — R$/mês", "aditivo"],
  ["espera_mes", "Espera — R$/mês", "aditivo"],
  ["risco_mes", "Risco — R$/mês", "aditivo"],
] as const satisfies ReadonlyArray<readonly [keyof CamposDeCusto, string, string]>;

type CamposDeCusto = Pick<
  Process,
  "volume_mes" | "tempo_horas" | "pessoas" | "custo_hora"
  | "retrabalho_mes" | "erros_mes" | "perdas_mes" | "espera_mes" | "risco_mes"
>;

const blankEtapa: { name: string } & CamposPsdter = {
  name: "", pessoas: "", sistema: "", dados: "", tempo: "", erro: "", retrabalho: "",
};

/**
 * O rascunho do achado — o `Finding` do split (FDD 045) e a `Evidence` que o sustenta, num
 * formulário só, e os vazios são a decisão inteira dele.
 *
 * `epistemic_status` e `kind` **não têm default no banco** (ADR 0034) e não podem ganhar um aqui.
 * Um select que já abre em "Hipótese" reintroduz na tela o default que a ADR recusou no modelo: a
 * casa escolhendo por quem não escolheu, sempre para o mesmo lado.
 *
 * **`fato` não é opção de criação** — é o que a promoção faz, com revisor e evidência viva (§6.9).
 * Oferecê-lo aqui produziria o 400 que quem clica não entende: criar já como fato exigiria as duas
 * coisas que só a promoção reúne. O achado nasce hipótese ou desconhecido, e sobe por ato de gente.
 */
const blankFinding: {
  epistemic_status: Exclude<EpistemicStatus, "fact"> | "";
  kind: EvidenceKind | ""; raw_excerpt: string; statement: string; step: string;
} = {
  epistemic_status: "", kind: "", raw_excerpt: "", statement: "", step: "",
};

const STATUS_LABEL: Record<EpistemicStatus, string> = {
  fact: "Fato", hypothesis: "Hipótese", unknown: "Desconhecido",
};
// As cinco formas, com o exemplo junto (`docs/metodologia-fde.md:112-115`). O parêntese não é
// decoração: "nunca só entrevista" é a regra, e ela só se cumpre se quem registra enxergar as
// outras quatro como opções concretas em vez de sinônimos abstratos de "fonte".
const KIND_LABEL: Record<EvidenceKind, string> = {
  interview: "Entrevista (o que dizem)",
  observation: "Observação (o que fazem)",
  artifact: "Artefato (planilha, PDF, croqui)",
  system: "Sistema (ERP, CRM, CAD, WhatsApp)",
  data: "Dado (volume, tempo, custo, erro)",
};
// Variante, nunca a cor (ADR 0026): um `bg-emerald-50` escrito aqui é a segunda definição de
// "fato", e ela diverge da primeira sem nada ficar vermelho. `unknown` é `state--off` — o neutro de
// "Desligada"/"Arquivado" —, porque nomear o que ainda não se sabe **não é falha**: é o Discovery
// fazendo o trabalho. Pintá-lo de vermelho mandaria apagar a linha mais honesta do mapa.
const STATUS_BADGE: Record<EpistemicStatus, string> = {
  fact: "state--1", hypothesis: "state--2", unknown: "state--off",
};

/**
 * O rascunho do pain point (FDD 048, DAP priorização r1 — decisão **E1**).
 *
 * `impact_type` abre **sem escolha feita**, pela razão que `blankFinding` já escreve acima: o
 * campo não tem default no modelo, e um select que já abre em "Financeiro" é a casa escolhendo por
 * quem não escolheu — sempre para o mesmo lado. Aqui o lado errado classifica como custo o que era
 * risco, e o tipo é o que separa as dores quando alguém for agrupá-las.
 */
const blankPainPoint: { title: string; impact_type: PainPointImpactType | ""; step: string } = {
  title: "", impact_type: "", step: "",
};
const impactoLabels: Record<PainPointImpactType, string> = {
  financial: "Financeiro", operational: "Operacional", experience: "Experiência", risk: "Risco",
};

export function ProcessDetailPage({ clientId, id }: { clientId: number; id: number }) {
  const { user } = useAuth();
  const [processo, setProcesso] = useState<Process>();
  const [etapas, setEtapas] = useState<ProcessStep[]>([]);
  const [findings, setFindings] = useState<Finding[]>([]);
  // As evidências ficam à parte, indexadas por id: o `Finding` guarda só as chaves em `evidences`,
  // e é aqui que a linha do achado descobre de que **forma** ele veio para exibir na tela.
  const [evidencePorId, setEvidencePorId] = useState<Map<number, Evidence>>(new Map());
  const [dores, setDores] = useState<PainPoint[]>([]);
  const [oportunidades, setOportunidades] = useState<ImprovementOpportunity[]>([]);
  const [etapaDraft, setEtapaDraft] = useState(blankEtapa);
  const [findingDraft, setFindingDraft] = useState(blankFinding);
  const [painPointDraft, setPainPointDraft] = useState(blankPainPoint);
  const [error, setError] = useState("");
  const [isArchiving, setArchiving] = useState(false);
  const [busy, setBusy] = useState(false);
  const [promovendo, setPromovendo] = useState<number | null>(null);
  // O rascunho guarda **texto**, inclusive para os campos numéricos: é `""` que representa "não
  // apurado", e um `number` não tem como dizer isso — `0` já é uma medição. A conversão para
  // `null` acontece no envio.
  const [insumoDraft, setInsumoDraft] = useState<Record<string, string>>({});
  const [salvandoInsumos, setSalvandoInsumos] = useState(false);

  const load = useCallback(() => Promise.all([
    // A **rota** de processo e etapa continua sendo `/processos/` e `/processo-etapas/` — ela morre
    // na `/api/v2/` (`docs/ontology/aliases.md`). O achado é o split `Evidence`/`Finding` (FDD 045),
    // que nasceu já com a rota canônica: `/findings/` e `/evidence/`. As chaves de corpo aqui já são
    // as canônicas.
    api<Process>(`/processos/${id}/`),
    api<ProcessStep[]>(`/processo-etapas/?process=${id}`),
    api<Finding[]>(`/findings/?process=${id}`),
    api<Evidence[]>(`/evidence/?process=${id}`),
    listPainPointsByProcess(id),
    // As oportunidades da conta entram só para o selo "Agrupado": é a outra ponta da decisão E1 —
    // quem registra a dor aqui vê, na mesma tela, se ela já virou trabalho de priorização, sem
    // precisar abrir a outra tela para descobrir.
    listImprovementOpportunities(clientId),
  ]).then(([loadedProcesso, loadedEtapas, loadedFindings, loadedEvidence, loadedDores, loadedOportunidades]) => {
    setProcesso(loadedProcesso); setEtapas(loadedEtapas); setFindings(loadedFindings);
    setEvidencePorId(new Map(loadedEvidence.map(e => [e.id, e])));
    setDores(loadedDores); setOportunidades(loadedOportunidades);
    setInsumoDraft(Object.fromEntries(
      INSUMOS.map(([campo]) => [campo, loadedProcesso[campo] === null ? "" : String(loadedProcesso[campo])])
    ));
  }).catch((cause: unknown) => setError(mensagemDeFalha(cause))), [clientId, id]);
  useEffect(() => { void load(); }, [load]);

  async function createEtapa(event: FormEvent<HTMLFormElement>) {
    event.preventDefault(); setError("");
    try { await api("/processo-etapas/", { method: "POST", body: JSON.stringify({ process: id, ...etapaDraft }) }); setEtapaDraft(blankEtapa); await load(); }
    catch (cause) { setError(mensagemDeFalha(cause)); }
  }
  /**
   * Registra o achado como o par do split: uma `Evidence` (de onde veio) e um `Finding` (o que
   * afirma), ligados (FDD 045). São duas gravações porque são dois fatos — o trecho bruto e a
   * conclusão que a casa tirou dele —, e é justamente a fusão dos dois numa linha só que o split
   * desfaz. A `Evidence` vem primeiro porque o `Finding` precisa da chave dela para nascer ligado:
   * é essa evidência viva que uma promoção futura vai exigir (§6.9).
   *
   * `step` vazio vira `null`, e não fica de fora do corpo: o vínculo é opcional por decisão da
   * FDD 039 — vínculo errado é pior que vínculo nenhum, e quem sabe é quem estava na reunião.
   */
  async function createFinding(event: FormEvent<HTMLFormElement>) {
    event.preventDefault(); setError("");
    if (!processo) return;
    const step = findingDraft.step ? Number(findingDraft.step) : null;
    try {
      const evidence = await api<Evidence>("/evidence/", { method: "POST", body: JSON.stringify({
        account: processo.account, process: id, step, kind: findingDraft.kind,
        raw_excerpt: findingDraft.raw_excerpt,
      }) });
      await api("/findings/", { method: "POST", body: JSON.stringify({
        account: processo.account, process: id, step, statement: findingDraft.statement,
        epistemic_status: findingDraft.epistemic_status, evidences: [evidence.id],
      }) });
      setFindingDraft(blankFinding); await load();
    } catch (cause) { setError(mensagemDeFalha(cause)); }
  }
  /**
   * Registra a dor **onde ela foi observada** — decisão **E1** do DAP priorização r1.
   *
   * A dor é vista no processo, junto do trecho que a sustenta e do custo do estado atual. Obrigar
   * quem está lendo a evidência a trocar de tela para registrá-la é a fricção que faz o registro
   * não acontecer — e um pain point que não é registrado no instante em que é visto vira memória
   * de reunião, que é o defeito que a FDD 039 existe para corrigir.
   *
   * A **conta** vem do processo e não do formulário: a dor ancora na conta (como `Process`,
   * `Evidence` e `Finding`), e quem a resolve é o registro que já está na tela.
   */
  async function createPainPointDaqui(event: FormEvent<HTMLFormElement>) {
    event.preventDefault(); setError("");
    if (!processo) return;
    const corpo = {
      account: processo.account, title: painPointDraft.title,
      impact_type: painPointDraft.impact_type as PainPointImpactType,
      process: id, step: painPointDraft.step ? Number(painPointDraft.step) : null,
    };
    try { await createPainPoint(corpo); setPainPointDraft(blankPainPoint); await load(); }
    catch (cause) { setError(mensagemDeFalha(cause)); }
  }
  /**
   * Descarta a dor, ou a traz de volta a observada.
   *
   * **`confirmed` não é oferecido**, e a ausência é a decisão: confirmar exige ao menos um
   * `Finding` vivo ligado à dor (FDD 048), o produto ainda não tem tela de achados, e um select
   * que oferecesse o valor produziria um 400 que quem clicou não entende. É o mesmo cuidado que
   * fez `blankFinding` abrir sem escolha feita.
   */
  async function mudarSituacaoDaDor(dor: PainPoint) {
    setError("");
    const status = dor.status === "discarded" ? "observed" : "discarded";
    try { await updatePainPoint(dor.id, { status }); await load(); }
    catch (cause) { setError(mensagemDeFalha(cause)); }
  }
  /**
   * Promove o achado a fato — e é **ato humano por decisão** (ADR 0034, §6.9).
   *
   * Tudo que a extração de reunião cria nasce como hipótese, porque um modelo lendo transcrição
   * produz *o que foi dito*, não prova. Só o fato sustenta número: é esta chamada que faz o custo
   * do estado atual deixar de ser hipótese da casa. O backend exige quem revisou — vai o usuário
   * autenticado, `reviewed_by` — e ao menos uma evidência viva ligada, que o achado já tem desde a
   * criação. Sem uma das duas, o servidor recusa com 400, e a mensagem sobe para a tela.
   */
  async function promover(finding: Finding) {
    if (!user) return;
    setError(""); setPromovendo(finding.id);
    try { await api(`/findings/${finding.id}/`, { method: "PATCH", body: JSON.stringify({ epistemic_status: "fact", reviewed_by: user.id }) }); await load(); }
    catch (cause) { setError(mensagemDeFalha(cause)); }
    finally { setPromovendo(null); }
  }
  /**
   * Grava os insumos do custo — e a regra inteira está no `|| null`.
   *
   * **Campo em branco vira `null`, nunca `0`.** É a metade de tela da decisão que o
   * `process.py` toma no cálculo: "não medimos o retrabalho" e "não há retrabalho" são
   * conclusões opostas, e um formulário que mandasse zero por omissão apagaria a primeira,
   * transformando toda ausência em medição. O `nao_apurado` deixaria de existir, o total
   * pareceria fechado, e a tela inteira passaria a afirmar mais do que se sabe.
   */
  async function salvarInsumos(event: FormEvent<HTMLFormElement>) {
    event.preventDefault(); setError(""); setSalvandoInsumos(true);
    const corpo = Object.fromEntries(
      INSUMOS.map(([campo]) => [campo, insumoDraft[campo]?.trim() || null])
    );
    try { await api(`/processos/${id}/`, { method: "PATCH", body: JSON.stringify(corpo) }); await load(); }
    catch (cause) { setError(mensagemDeFalha(cause)); }
    finally { setSalvandoInsumos(false); }
  }
  async function archiveProcesso() {
    setBusy(true);
    try {
      await api(`/processos/${id}/`, { method: "DELETE" });
      window.location.assign(`/contas/${clientId}`);
    } catch (cause) {
      setArchiving(false); setError(mensagemDeFalha(cause)); setBusy(false);
    }
  }

  if (error && !processo) return <div role="alert" className="alert--error">{error}</div>;
  if (!processo) return <div className="animate-pulse space-y-6"><div className="h-10 w-64 rounded-xl bg-slate-200" /><div className="h-56 rounded-2xl bg-white" /></div>;

  const { custo } = processo;
  const naoApurado = custo.nao_apurado;

  return <section className="space-y-7">
    <a href={`/contas/${clientId}`} className="back-link"><ArrowLeft className="size-4" />Voltar para o cliente</a>
    {isArchiving && <ConfirmDialog
      title="Arquivar processo"
      // A mensagem diz o que `Process.archive()` faz de verdade: arquivar **leva junto** as etapas,
      // no mesmo instante. Os achados não vão junto — são da conta, não do processo (Fase 6), e
      // seguem listáveis por ela. Quem clica precisa saber o que está guardando e o que fica.
      message={<>O processo <strong className="text-ink">{processo.name}</strong> sai das listagens ativas <strong className="text-ink">levando junto as {etapas.length} etapa(s) dele</strong>. Os achados ficam com a conta. Nada é apagado: restaurar depois traz de volta exatamente o que este arquivamento levou.</>}
      confirmLabel="Arquivar" busy={busy}
      onCancel={() => setArchiving(false)} onConfirm={() => void archiveProcesso()}
    />}
    <header className="page-head flex flex-col justify-between gap-4 sm:flex-row sm:items-end">
      <div><p className="eyebrow">Discovery estruturado</p><h1>{processo.name}</h1><p>O mapa da operação de {processo.client_name} — o dado que se soma, não a narrativa que se entrega.</p></div>
      <button type="button" className="btn btn--secondary btn--secondary-danger shrink-0 self-start sm:self-auto" onClick={() => setArchiving(true)}><Trash2 className="size-4" />Arquivar processo</button>
    </header>
    {error && <p role="alert" className="alert--error">{error}</p>}

    {/* O custo do estado atual, **com a conta à vista** — é o centro da tela. Um número sem as
        parcelas que o produziram não se discute numa reunião: aceita-se ou rejeita-se. */}
    <section className="panel space-y-4 sm:p-6">
      <div className="flex flex-wrap items-center gap-3">
        <span className="metric-icon"><Coins className="size-4" /></span>
        <div><h2 className="font-semibold text-ink">Custo do estado atual</h2><p className="text-sm text-slate-600">Volume × Tempo × Pessoas × Custo + Retrabalho + Erros + Perdas + Espera + Risco</p></div>
        {/* Irmão do bloco de título, e não filho dele: o selo diz se o número acima se apresenta
            ao cliente como número ou como suposição da casa, e essa é a primeira coisa a ler. */}
        <span className={`state ${sustentacaoBadgeClass(custo.sustentacao)} shrink-0 sm:ml-auto`}>{SUSTENTACAO_LABEL[custo.sustentacao]}</span>
      </div>
      <div className="metric-card">
        <span>Por mês, com o processo como ele é hoje</span>
        <strong>{moeda(custo.total)}</strong>
        {/* **Dentro do mesmo cartão do total, e no mesmo corpo de texto.** Um total parcial
            mostrado sozinho vira "custo zero" na leitura rápida, e "não medimos o retrabalho" e
            "não há retrabalho" são conclusões opostas. Em rodapé ou em `<small>` o aviso continua
            existindo e deixa de ser lido — que é o mesmo que não existir. */}
        {naoApurado.length > 0 && <p className="text-sm font-medium text-ink">
          O total é parcial: {naoApurado.join(", ")} {naoApurado.length === 1 ? "não foi apurado e está" : "não foram apurados e estão"} fora desta soma.
        </p>}
      </div>
      {custo.parcelas.length
        ? <div className="panel-rows">{custo.parcelas.map(parcela => <div className="row" key={parcela.label}>
            <div className="row-main"><strong>{parcela.label}</strong></div>
            <div className="row-meta justify-end"><span className="text-sm font-semibold text-ink">{moeda(parcela.valor)}</span></div>
          </div>)}</div>
        : <p className="empty-state">Nenhuma parcela apurada ainda — sem volume, tempo, pessoas e custo/hora não há conta a mostrar, e zero não seria a resposta.</p>}

      {/* Os insumos, na mesma seção do resultado de propósito: o que a extração traz é o mapa, e
          os números são levantados por gente depois. Sem este formulário a conta acima ficaria
          zerada para sempre, e a tela mostraria um total que nunca poderia ser outra coisa.

          Deixar em branco é resposta legítima e é como se diz "ainda não medimos" — o campo vazio
          vira `null`, entra em `nao_apurado` e sai do total. */}
      <form className="form-grid" onSubmit={event => void salvarInsumos(event)}>
        {INSUMOS.map(([campo, rotulo]) => <label className="form-label" key={campo}>
          {rotulo}
          <input
            className="field" type="number" min="0" step="0.01" inputMode="decimal"
            placeholder="Não apurado"
            value={insumoDraft[campo] ?? ""}
            onChange={event => setInsumoDraft({ ...insumoDraft, [campo]: event.target.value })}
          />
        </label>)}
        <p className="text-sm text-slate-600 sm:col-span-2">
          Deixe em branco o que ainda não foi medido: em branco é <strong>não apurado</strong>, e
          sai da soma. Zero é uma medição — significa que se olhou e não havia perda.
        </p>
        <button className="btn sm:col-span-2" type="submit" disabled={salvandoInsumos}>
          <Coins className="size-4" />{salvandoInsumos ? "Salvando…" : "Salvar os insumos do custo"}
        </button>
      </form>
    </section>

    <section className="panel space-y-4 sm:p-6">
      <div className="flex items-center gap-3"><span className="metric-icon"><Workflow className="size-4" /></span><div><h2 className="font-semibold text-ink">Etapas</h2><p className="text-sm text-slate-600">{etapas.length} {etapas.length === 1 ? "etapa" : "etapas"} · as seis perguntas do P-S-D-T-E-R, na ordem em que se pergunta</p></div></div>
      <form className="form-grid" onSubmit={event => void createEtapa(event)}>
        <label className="form-label sm:col-span-2">Nome da etapa<input className="field" value={etapaDraft.name} onChange={event => setEtapaDraft({ ...etapaDraft, name: event.target.value })} placeholder="O que acontece nesta etapa" required /></label>
        {PSDTER.map(([campo, pergunta]) => <label className="form-label" key={campo}>{pergunta}<textarea className="field min-h-16" value={etapaDraft[campo]} onChange={event => setEtapaDraft({ ...etapaDraft, [campo]: event.target.value })} /></label>)}
        <button className="btn sm:col-span-2" type="submit"><Plus className="size-4" />Adicionar etapa</button>
      </form>
      {etapas.length ? <div className="panel-rows">{etapas.map(etapa => <div className="row" key={etapa.id}>
        <div className="row-main">
          <strong>{etapa.name}</strong>
          {/* As seis aparecem **sempre**, inclusive vazias. A lacuna é o produto aqui: uma etapa
              sem "o que pode dar errado" é uma pergunta que não foi feita, e escondê-la faria a
              tela parecer completa justamente onde o levantamento não está. `<dt>`/`<dd>` e não
              `<span>`: `.row-main span` já define `block`/`text-xs`/`muted` e achataria o par. */}
          <dl className="mt-2 grid gap-2 sm:grid-cols-2">{PSDTER.map(([campo, pergunta]) => <div key={campo}>
            <dt className="text-xs font-semibold text-ink">{pergunta}</dt>
            <dd className="text-xs text-muted">{etapa[campo] || "Não levantado"}</dd>
          </div>)}</dl>
        </div>
      </div>)}</div> : <p className="empty-state">Nenhuma etapa mapeada ainda.</p>}
    </section>

    {/* Os achados, e é aqui que a classificação governa (ADR 0034): **só o fato sustenta número**.
        A lista não é um histórico — é a razão pela qual o custo acima vale ou não vale. Cada achado
        é um `Finding` (o que se afirma) apoiado na `Evidence` que diz de onde veio (FDD 045). */}
    <section className="panel space-y-4 sm:p-6">
      <div className="flex items-center gap-3"><span className="metric-icon"><Quote className="size-4" /></span><div><h2 className="font-semibold text-ink">Achados</h2><p className="text-sm text-slate-600">{findings.length} {findings.length === 1 ? "achado" : "achados"} · nunca só entrevista, e nunca hipótese apresentada como fato</p></div></div>
      <form className="form-grid" data-testid="finding-form" onSubmit={event => void createFinding(event)}>
        {/* Os selects abrem **sem escolha feita** de propósito — ver `blankFinding`. A classificação
            não oferece "Fato": ele é o que a promoção faz, com revisor e evidência viva. */}
        <label className="form-label">Classificação<select className="field" value={findingDraft.epistemic_status} onChange={event => setFindingDraft({ ...findingDraft, epistemic_status: event.target.value as Exclude<EpistemicStatus, "fact"> })} required><option value="" disabled>Selecione…</option><option value="hypothesis">{STATUS_LABEL.hypothesis}</option><option value="unknown">{STATUS_LABEL.unknown}</option></select></label>
        <label className="form-label">Forma da fonte<select className="field" value={findingDraft.kind} onChange={event => setFindingDraft({ ...findingDraft, kind: event.target.value as EvidenceKind })} required><option value="" disabled>Selecione…</option>{Object.entries(KIND_LABEL).map(([value, label]) => <option key={value} value={value}>{label}</option>)}</select></label>
        {/* O vínculo com a etapa, que a extração deixa sempre vazio de propósito. A FDD 039 diz que
            `step` existe "para ser preenchida por gente depois", e "depois" precisa de um lugar. */}
        <label className="form-label sm:col-span-2">
          Etapa (opcional)
          <select className="field" value={findingDraft.step} onChange={event => setFindingDraft({ ...findingDraft, step: event.target.value })} disabled={!etapas.length}>
            <option value="">{etapas.length ? "O achado é do processo inteiro" : "Nenhuma etapa mapeada ainda"}</option>
            {etapas.map(etapa => <option key={etapa.id} value={etapa.id}>{etapa.name}</option>)}
          </select>
        </label>
        {/* Dois campos porque são dois fatos: o **trecho** como foi dito ou observado (a `Evidence`)
            e a **conclusão** que a casa tirou dele (o `Finding`). Juntá-los numa caixa só refaria a
            fusão que o split desfaz — editar a redação do achado apagaria a prova que o sustenta. */}
        <label className="form-label sm:col-span-2">Trecho da fonte<textarea className="field min-h-16" value={findingDraft.raw_excerpt} onChange={event => setFindingDraft({ ...findingDraft, raw_excerpt: event.target.value })} placeholder="O que foi dito ou observado, com as palavras da fonte" required /></label>
        <label className="form-label sm:col-span-2">Achado<textarea className="field min-h-20" value={findingDraft.statement} onChange={event => setFindingDraft({ ...findingDraft, statement: event.target.value })} placeholder="A conclusão que a casa tirou disso, na frase de quem levantou" required /></label>
        <button className="btn sm:col-span-2" type="submit"><Plus className="size-4" />Registrar achado</button>
      </form>
      {findings.length ? <div className="panel-rows">{findings.map(finding => {
        const fonte = finding.evidences.map(eid => evidencePorId.get(eid)).find(Boolean);
        return <div className="row" key={finding.id}>
          <span className="grid size-9 shrink-0 place-items-center rounded-xl bg-slate-100 text-slate-600"><Quote className="size-4" /></span>
          <div className="row-main">
            <strong>{finding.statement}</strong>
            {fonte && <span>{fonte.kind_display}</span>}
          </div>
          {/* Fora de `.row-main`: `.row-main span`/`strong` sobrescrevem display e cor de qualquer
              primitiva aninhada ali dentro, e o `.state` perderia a própria pele em silêncio. */}
          <div className="row-meta">
            <span className={`state ${STATUS_BADGE[finding.epistemic_status]}`}>{finding.epistemic_status_display}</span>
            {/* Some quando já é fato: não há para onde promover, e um botão inerte na linha diria que
                existe um grau acima. O `aria-label` nomeia o achado porque a tela tem um botão destes
                por linha, e "Promover a fato" repetido cinco vezes não localiza nenhum deles. */}
            {finding.epistemic_status !== "fact" && <button type="button" className="btn btn--secondary ml-auto" disabled={promovendo === finding.id} aria-label={`Promover a fato: ${finding.statement}`} onClick={() => void promover(finding)}><BadgeCheck className="size-4" />Promover a fato</button>}
          </div>
        </div>;
      })}</div> : <p className="empty-state">Nenhum achado registrado — sem achado classificado, o custo acima é hipótese da casa.</p>}
    </section>

    {/* Os pain points, **abaixo das evidências e de propósito** (DAP priorização r1, decisão E1):
        a dor se registra ao lado do trecho que a sustenta. Aqui é o registro; o agrupamento em
        Improvement Opportunity e o ranking moram em `/contas/:id/priorizacao`. */}
    <section className="panel space-y-4 sm:p-6">
      <div className="flex items-center gap-3"><span className="metric-icon"><Flame className="size-4" /></span><div><h2 className="font-semibold text-ink">Pain points</h2><p className="text-sm text-slate-600">{dores.length ? `${dores.length} ${dores.length === 1 ? "dor observada" : "dores observadas"} neste processo` : "Nenhum pain point"}</p></div></div>
      <form className="form-grid" data-testid="pain-point-form" onSubmit={event => void createPainPointDaqui(event)}>
        <label className="form-label sm:col-span-2">Descrição<textarea className="field min-h-16" maxLength={200} value={painPointDraft.title} onChange={event => setPainPointDraft({ ...painPointDraft, title: event.target.value })} placeholder="A dor, na frase de quem observou" required /></label>
        {/* Abre **sem escolha feita** — ver `blankPainPoint`. */}
        <label className="form-label">Tipo de impacto<select className="field" value={painPointDraft.impact_type} onChange={event => setPainPointDraft({ ...painPointDraft, impact_type: event.target.value as PainPointImpactType })} required><option value="" disabled>Selecione…</option>{Object.entries(impactoLabels).map(([value, label]) => <option key={value} value={value}>{label}</option>)}</select></label>
        <label className="form-label">
          Etapa (opcional)
          <select className="field" value={painPointDraft.step} onChange={event => setPainPointDraft({ ...painPointDraft, step: event.target.value })} disabled={!etapas.length}>
            <option value="">{etapas.length ? "O pain point é do processo inteiro" : "Nenhuma etapa mapeada ainda"}</option>
            {etapas.map(etapa => <option key={etapa.id} value={etapa.id}>{etapa.name}</option>)}
          </select>
        </label>
        <button className="btn sm:col-span-2" type="submit"><Plus className="size-4" />Registrar pain point</button>
      </form>
      {dores.length ? <div className="panel-rows">{dores.map(dor => {
        const oportunidade = oportunidades.find(candidata => candidata.pain_points.includes(dor.id));
        return <div className="row" key={dor.id}>
          <span className="metric-icon"><Flame className="size-4" /></span>
          <div className="row-main">
            <strong>{dor.title}</strong>
            <span>Impacto: {dor.impact_type_display}{oportunidade ? ` · agrupado em "${oportunidade.title}"` : ""}</span>
          </div>
          {/* `.row-meta` e não irmãos soltos: `.row-main` é `flex-basis:0`, e sem isto um título
              longo sem hífen vaza por cima do selo em 390px (DAP priorização r1). O selo diz se a
              dor já virou trabalho de priorização; "sem oportunidade" é o neutro, não um aviso. */}
          <div className="row-meta">
            <span className={`state ${dor.status === "discarded" ? "state--3" : oportunidade ? "state--1" : "state--off"}`}>{dor.status === "discarded" ? dor.status_display : oportunidade ? "Agrupado" : "Sem oportunidade"}</span>
            <button type="button" className="btn btn--secondary ml-auto" aria-label={`${dor.status === "discarded" ? "Reabrir" : "Descartar"} pain point: ${dor.title}`} onClick={() => void mudarSituacaoDaDor(dor)}>{dor.status === "discarded" ? "Reabrir" : "Descartar"}</button>
          </div>
        </div>;
      })}</div> : <p className="empty-state">Nenhum pain point registrado. A dor entra pela tela do processo, ao lado da evidência que a sustenta.</p>}
    </section>
  </section>;
}
