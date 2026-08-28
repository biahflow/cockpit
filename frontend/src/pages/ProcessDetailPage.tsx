import { ArrowLeft, BadgeCheck, Coins, Plus, Quote, Trash2, Workflow } from "lucide-react";
import { type FormEvent, useCallback, useEffect, useState } from "react";

import { api } from "../api";
import { ConfirmDialog } from "../components/Modal";
import { SUSTENTACAO_LABEL, sustentacaoBadgeClass } from "../components/StatusDot";
import { moeda } from "../dinheiro";
import { mensagemDeFalha } from "../erros";
import type { Evidencia, EvidenciaForma, EvidenciaRotulo, Process, ProcessStep } from "../types";

/**
 * As seis letras do P-S-D-T-E-R (`docs/metodologia-fde.md:75-79`), **rotuladas pela pergunta**.
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
 * O rascunho da evidência — e os dois vazios são a decisão inteira do formulário.
 *
 * `rotulo` e `forma` **não têm default no banco** (ADR 0034) e não podem ganhar um aqui. Um select
 * que já abre em "Hipótese" reintroduz na tela exatamente o default que a ADR recusou no modelo: a
 * casa escolhendo por quem não escolheu, sempre para o mesmo lado. E o lado errado é caro — é o que
 * faz suposição virar fato, que é a única coisa que a metodologia proíbe nominalmente
 * (`docs/metodologia-fde.md:86`). Escolher "desconhecido" é um ato; recebê-lo por omissão não diz
 * nada sobre o achado.
 */
const blankEvidencia: {
  rotulo: EvidenciaRotulo | ""; forma: EvidenciaForma | ""; content: string; step: string;
} = {
  rotulo: "", forma: "", content: "", step: "",
};

const rotuloLabels: Record<EvidenciaRotulo, string> = {
  fato: "Fato", hipotese: "Hipótese", desconhecido: "Desconhecido",
};
// As cinco formas, com o exemplo junto (`docs/metodologia-fde.md:81-84`). O parêntese não é
// decoração: "nunca só entrevista" é a regra, e ela só se cumpre se quem registra enxergar as
// outras quatro como opções concretas em vez de sinônimos abstratos de "fonte".
const formaLabels: Record<EvidenciaForma, string> = {
  entrevista: "Entrevista (o que dizem)",
  observacao: "Observação (o que fazem)",
  artefato: "Artefato (planilha, PDF, croqui)",
  sistema: "Sistema (ERP, CRM, CAD, WhatsApp)",
  dado: "Dado (volume, tempo, custo, erro)",
};
// Variante, nunca a cor (ADR 0026): um `bg-emerald-50` escrito aqui é a segunda definição de
// "fato", e ela diverge da primeira sem nada ficar vermelho. `desconhecido` é `state--off` — o
// neutro de "Desligada"/"Arquivado" —, porque nomear o que ainda não se sabe **não é falha**: é o
// Discovery fazendo o trabalho. Pintá-lo de vermelho mandaria apagar a linha mais honesta do mapa.
const ROTULO_BADGE: Record<EvidenciaRotulo, string> = {
  fato: "state--1", hipotese: "state--2", desconhecido: "state--off",
};

export function ProcessDetailPage({ clientId, id }: { clientId: number; id: number }) {
  const [processo, setProcesso] = useState<Process>();
  const [etapas, setEtapas] = useState<ProcessStep[]>([]);
  const [evidencias, setEvidencias] = useState<Evidencia[]>([]);
  const [etapaDraft, setEtapaDraft] = useState(blankEtapa);
  const [evidenciaDraft, setEvidenciaDraft] = useState(blankEvidencia);
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
    // A **rota** continua sendo `/processos/` e `/processo-etapas/` — ela morre na `/api/v2/`
    // (`docs/ontology/aliases.md`). O **query param** e as chaves de corpo aqui já são os
    // canônicos: a chave antiga fica na v1 para quem integrou de fora, não para a SPA.
    api<Process>(`/processos/${id}/`),
    api<ProcessStep[]>(`/processo-etapas/?process=${id}`),
    api<Evidencia[]>(`/evidencias/?process=${id}`),
  ]).then(([loadedProcesso, loadedEtapas, loadedEvidencias]) => {
    setProcesso(loadedProcesso); setEtapas(loadedEtapas); setEvidencias(loadedEvidencias);
    setInsumoDraft(Object.fromEntries(
      INSUMOS.map(([campo]) => [campo, loadedProcesso[campo] === null ? "" : String(loadedProcesso[campo])])
    ));
  }).catch((cause: unknown) => setError(mensagemDeFalha(cause))), [id]);
  useEffect(() => { void load(); }, [load]);

  async function createEtapa(event: FormEvent<HTMLFormElement>) {
    event.preventDefault(); setError("");
    try { await api("/processo-etapas/", { method: "POST", body: JSON.stringify({ process: id, ...etapaDraft }) }); setEtapaDraft(blankEtapa); await load(); }
    catch (cause) { setError(mensagemDeFalha(cause)); }
  }
  async function createEvidencia(event: FormEvent<HTMLFormElement>) {
    event.preventDefault(); setError("");
    // `step` vazio vira `null`, e não fica de fora do corpo: o vínculo é opcional por decisão da
    // FDD 039 — o modelo não sabe a qual etapa um achado pertence, e vínculo errado é pior que
    // vínculo nenhum. Quem sabe é quem estava na reunião, e é aqui que ele diz.
    const corpo = { process: id, ...evidenciaDraft, step: evidenciaDraft.step || null };
    try { await api("/evidencias/", { method: "POST", body: JSON.stringify(corpo) }); setEvidenciaDraft(blankEvidencia); await load(); }
    catch (cause) { setError(mensagemDeFalha(cause)); }
  }
  /**
   * Promove o achado a fato — e é **ato humano por decisão** (ADR 0034).
   *
   * Tudo que a extração de reunião cria nasce como hipótese vinda de entrevista, porque um modelo
   * lendo transcrição produz *o que foi dito*, não prova. Só o fato sustenta número: é esta
   * chamada que faz o custo do estado atual deixar de ser hipótese da casa. Não há caminho
   * automático para cá, pela mesma razão que a ADR 0032 recusou à IA gravar satisfação.
   */
  async function promover(evidencia: Evidencia) {
    setError(""); setPromovendo(evidencia.id);
    try { await api(`/evidencias/${evidencia.id}/`, { method: "PATCH", body: JSON.stringify({ rotulo: "fato" }) }); await load(); }
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
      // A mensagem diz o que `Process.archive()` faz de verdade: arquivar **leva junto** etapas e
      // evidências, no mesmo instante. Um mapa de processo se guarda inteiro — mas quem clica
      // precisa saber que não está guardando só o cabeçalho.
      message={<>O processo <strong className="text-ink">{processo.name}</strong> sai das listagens ativas <strong className="text-ink">levando junto as {etapas.length} etapa(s) e as {evidencias.length} evidência(s) dele</strong>. Nada é apagado: restaurar depois traz de volta exatamente o que este arquivamento levou.</>}
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
            <span className="shrink-0 text-sm font-semibold text-ink">{moeda(parcela.valor)}</span>
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

    {/* As evidências, e é aqui que o rótulo governa (ADR 0034): **só o fato sustenta número**.
        A lista não é um histórico — é a razão pela qual o custo acima vale ou não vale. */}
    <section className="panel space-y-4 sm:p-6">
      <div className="flex items-center gap-3"><span className="metric-icon"><Quote className="size-4" /></span><div><h2 className="font-semibold text-ink">Evidências</h2><p className="text-sm text-slate-600">{evidencias.length} {evidencias.length === 1 ? "achado" : "achados"} · nunca só entrevista, e nunca hipótese apresentada como fato</p></div></div>
      <form className="form-grid" onSubmit={event => void createEvidencia(event)}>
        {/* Os dois selects abrem **sem escolha feita** de propósito — ver `blankEvidencia`. */}
        <label className="form-label">Rótulo<select className="field" value={evidenciaDraft.rotulo} onChange={event => setEvidenciaDraft({ ...evidenciaDraft, rotulo: event.target.value as EvidenciaRotulo })} required><option value="" disabled>Selecione…</option>{Object.entries(rotuloLabels).map(([value, label]) => <option key={value} value={value}>{label}</option>)}</select></label>
        <label className="form-label">Forma<select className="field" value={evidenciaDraft.forma} onChange={event => setEvidenciaDraft({ ...evidenciaDraft, forma: event.target.value as EvidenciaForma })} required><option value="" disabled>Selecione…</option>{Object.entries(formaLabels).map(([value, label]) => <option key={value} value={value}>{label}</option>)}</select></label>
        {/* O vínculo com a etapa, que a extração deixa sempre vazio de propósito. Sem este campo
            a `Evidencia.step` seria coluna sem caminho de preenchimento — a FDD 039 diz que ela
            existe "para ser preenchida por gente depois", e "depois" precisa de um lugar. */}
        <label className="form-label sm:col-span-2">
          Etapa (opcional)
          <select className="field" value={evidenciaDraft.step} onChange={event => setEvidenciaDraft({ ...evidenciaDraft, step: event.target.value })} disabled={!etapas.length}>
            <option value="">{etapas.length ? "O achado é do processo inteiro" : "Nenhuma etapa mapeada ainda"}</option>
            {etapas.map(etapa => <option key={etapa.id} value={etapa.id}>{etapa.name}</option>)}
          </select>
        </label>
        <label className="form-label sm:col-span-2">Achado<textarea className="field min-h-20" value={evidenciaDraft.content} onChange={event => setEvidenciaDraft({ ...evidenciaDraft, content: event.target.value })} placeholder="O que foi levantado, na frase de quem levantou" required /></label>
        <button className="btn sm:col-span-2" type="submit"><Plus className="size-4" />Registrar evidência</button>
      </form>
      {evidencias.length ? <div className="panel-rows">{evidencias.map(evidencia => <div className="row" key={evidencia.id}>
        <span className="grid size-9 shrink-0 place-items-center rounded-xl bg-slate-100 text-slate-600"><Quote className="size-4" /></span>
        <div className="row-main">
          <strong>{evidencia.content}</strong>
          <span>{evidencia.forma_display}</span>
        </div>
        {/* Fora de `.row-main`: `.row-main span`/`strong` sobrescrevem display e cor de qualquer
            primitiva aninhada ali dentro, e o `.state` perderia a própria pele em silêncio. */}
        <span className={`state ${ROTULO_BADGE[evidencia.rotulo]} shrink-0`}>{evidencia.rotulo_display}</span>
        {/* Some quando já é fato: não há para onde promover, e um botão inerte na linha diria que
            existe um grau acima. O `aria-label` nomeia o achado porque a tela tem um botão destes
            por linha, e "Promover a fato" repetido cinco vezes não localiza nenhum deles. */}
        {evidencia.rotulo !== "fato" && <button type="button" className="btn btn--secondary shrink-0" disabled={promovendo === evidencia.id} aria-label={`Promover a fato: ${evidencia.content}`} onClick={() => void promover(evidencia)}><BadgeCheck className="size-4" />Promover a fato</button>}
      </div>)}</div> : <p className="empty-state">Nenhuma evidência registrada — sem achado rotulado, o custo acima é hipótese da casa.</p>}
    </section>
  </section>;
}
