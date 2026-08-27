import { AlertTriangle, BarChart3, Building2, Check, ChevronDown, Lock, Plug, Slash, UserRound, X } from "lucide-react";
import type { ReactNode } from "react";

import { GATE_LABEL, gateBadgeClass } from "./StatusDot";
import type { AccountLadderRow, AccountRung, AccountRungStatus, AccountRungWaitingOn, GateOutcome, ProjectPhase } from "../types";

/**
 * A escada FDE da conta (FDD 042, ADR 0047, DAP GH-42 r1).
 * ---------------------------------------------------------------------------
 * **O terceiro eixo do produto.** `PipelineStage` é de uma oportunidade, `ProjectPhase` (FDD 011)
 * é de um projeto, e a escada FDE é da **conta**, atravessando várias oportunidades
 * (`docs/metodologia-fde.md:50`). A jornada de entrega fica exatamente onde está: ela aparece
 * **aninhada** sob o degrau ativo, referenciada e nunca redesenhada.
 *
 * Duas superfícies moram aqui de propósito, e não por comodidade: as duas leem os mesmos estados,
 * e uma cópia por tela seria a segunda definição de "concluído" — a que diverge da primeira sem
 * nada ficar vermelho (ADR 0026).
 */

/**
 * Estado do degrau → **variante** de `.timeline-step`, nunca a cor.
 *
 * `not_sold` e `skipped` são a decisão central do DAP: as duas deixam o degrau sem projeto e as
 * duas são neutras — nenhuma é aviso —, e o que as separa é **estrutura**. `--future` desenha
 * marcador oco, corpo tracejado e o trilho tracejado a partir dali (a escada não chegou aqui);
 * `--skipped` desenha marcador sólido e trilho **contínuo** (a conta passou por aqui e alguém
 * decidiu). Distinguir por cor exigiria matiz novo, que o design system proíbe em texto.
 */
const STEP_VARIANT: Record<AccountRungStatus, string> = {
  done: "timeline-step--done",
  active: "timeline-step--active",
  not_sold: "timeline-step--future",
  skipped: "timeline-step--skipped",
  blocked: "timeline-step--blocked",
  awaiting_gate: "timeline-step--gate",
  cancelled: "timeline-step--cancelled",
};

/**
 * Estado do degrau → variante de `.state`. **O ativo não tem entrada aqui, e é deliberado:** quem
 * diz "ativo" é a expansão e o `.eyebrow` "Você está aqui", que já é a palavra do produto para a
 * fase corrente. Um selo azul competiria com o dono *Biahflow*, também azul.
 */
const STATE_VARIANT: Partial<Record<AccountRungStatus, string>> = {
  done: "state--1",
  not_sold: "state--off",
  skipped: "state--off",
  blocked: "state--3",
  awaiting_gate: "state--2",
  cancelled: "state--off",
};

/** Ícone do marcador. Decorativo: o estado vem do texto, e o marcador é `aria-hidden`. */
const STEP_ICON: Partial<Record<AccountRungStatus, ReactNode>> = {
  done: <Check className="size-3" strokeWidth={3.5} />,
  skipped: <Slash className="size-3" strokeWidth={3.5} />,
  blocked: <AlertTriangle className="size-3" strokeWidth={3} />,
  awaiting_gate: <Lock className="size-2.5" strokeWidth={3} />,
  cancelled: <X className="size-2.5" strokeWidth={3.5} />,
};

/**
 * De quem é a bola — **cinco valores, cada um com pele própria** (DAP GH-42 r1).
 *
 * `engineering` é `.eng-ref` e fica deliberadamente **fora** da família `.state`: quando a bola
 * está com a engenharia, o dono é uma projeção de outra fonte, e estado de engenharia não usa a
 * pele do estado de negócio. `external` é neutro porque não é aviso nem falha — é *ausência de
 * agência*, e a gravidade quem diz é o estado do degrau. `human_gate` é a única pastilha sólida
 * do produto.
 *
 * Os cinco são legíveis sem `title` e sem hover: rótulo por extenso e ícone próprio.
 */
const WAITING_SKIN: Record<Exclude<AccountRungWaitingOn, "">, string> = {
  biahflow: "state state--0",
  client: "state state--2",
  engineering: "eng-ref",
  external: "state state--off",
  human_gate: "state state--gate",
};
const WAITING_ICON: Record<Exclude<AccountRungWaitingOn, "">, ReactNode> = {
  biahflow: <Building2 className="size-3" />,
  client: <UserRound className="size-3" />,
  engineering: <span className="size-1.5 shrink-0 rounded-full bg-muted" />,
  external: <Plug className="size-3" />,
  human_gate: <Lock className="size-3" />,
};

/** Estado da fase da jornada de entrega (FDD 011) → variante de `.timeline-step`. */
const PHASE_VARIANT: Record<ProjectPhase["status"], string> = {
  done: "timeline-step--done",
  active: "timeline-step--active",
  locked: "timeline-step--future",
};

/**
 * As quatro saídas do gate como **texto, não como botões**. O gate se decide na tela do projeto
 * (`JourneySection`); desenhar aqui quatro controles inertes seria defeito, não placeholder.
 */
const GATE_OUTCOMES: GateOutcome[] = ["go", "conditional_go", "redesign", "no_go"];

function data(valor: string | null): string {
  return valor ? new Date(valor).toLocaleDateString("pt-BR") : "";
}

/**
 * Data **sem hora** (`YYYY-MM-DD`). O `T12:00:00` é o padrão da casa e não é superstição: sem ele
 * o `Date` lê meia-noite **UTC** e, três horas a oeste, a previsão de 12/09 aparece como 11/09.
 */
function dataSimples(valor: string | null): string {
  return valor ? new Date(`${valor}T12:00:00`).toLocaleDateString("pt-BR") : "";
}

function carimbo(valor: string | null): string {
  return valor ? new Date(valor).toLocaleString("pt-BR", { dateStyle: "short", timeStyle: "short" }) : "";
}

function WaitingChip({ rung }: { rung: Pick<AccountRung, "waiting_on" | "waiting_on_display"> }) {
  if (!rung.waiting_on) return null;
  return <span className={`${WAITING_SKIN[rung.waiting_on]} shrink-0`}>{WAITING_ICON[rung.waiting_on]}{rung.waiting_on_display}</span>;
}

/**
 * A linha de contexto do degrau. **Ela afirma a ausência em vez de ficar vazia** — "Nenhuma
 * decisão registrada" é o que separa o degrau não vendido de um degrau que ninguém preencheu.
 */
function metaDoDegrau(rung: AccountRung): string {
  if (rung.no_access) return "";
  const partes: string[] = [];
  if (rung.status === "not_sold") return "Nenhuma decisão registrada · sem oportunidade · sem projeto · sem datas";
  if (rung.status === "skipped") {
    partes.push(`Motivo registrado: ${rung.skip_reason}`);
    if (rung.skipped_by_name) partes.push(`decidido por ${rung.skipped_by_name}`);
    if (rung.skipped_at) partes.push(`em ${carimbo(rung.skipped_at)}`);
    partes.push("nenhuma venda, por decisão");
    return partes.join(" · ");
  }
  if (rung.opportunity_title) partes.push(`Vendido em ${rung.opportunity_title}`);
  if (rung.project_name) partes.push(`realizado por ${rung.project_name}`);
  if (rung.started_at && rung.completed_at) partes.push(`${data(rung.started_at)} → ${data(rung.completed_at)}`);
  else if (rung.started_at) partes.push(`iniciado em ${data(rung.started_at)} · sem conclusão`);
  return partes.join(" · ");
}

/** A jornada de entrega do projeto que realiza o degrau — **referenciada, não redesenhada**. */
function JornadaAninhada({ phases }: { phases: ProjectPhase[] }) {
  if (!phases.length) return null;
  const concluidas = phases.filter(phase => phase.status === "done").length;
  return <>
    <p className="type-meta mt-3 font-bold uppercase tracking-[0.11em] text-muted">Jornada de entrega do projeto · FDD 011 · {concluidas} de {phases.length} fases</p>
    <ol className="timeline timeline--nested">
      {phases.map(phase => <li className={`timeline-step ${PHASE_VARIANT[phase.status]}`} key={phase.id}>
        <span className="timeline-marker" aria-hidden="true">{phase.status === "done" ? <Check className="size-2" strokeWidth={4} /> : phase.status === "active" ? <span /> : null}</span>
        <div className="timeline-body">
          <div className="flex flex-wrap items-center gap-2">
            <strong className="type-label text-ink">{phase.phase_name}</strong>
            {phase.status === "done" && <span className="state state--1">Concluída</span>}
            {phase.status === "active" && <span className="state state--0">Em andamento · entregáveis {phase.deliverables.filter(item => item.status === "delivered").length}/{phase.deliverables.length}</span>}
          </div>
        </div>
      </li>)}
    </ol>
    <p className="type-meta mt-2 text-muted">Esta jornada é <strong className="font-semibold text-ink">referenciada, não redesenhada</strong>. Quem a opera continua sendo a tela do projeto.</p>
  </>;
}

/** A gaveta de histórico, **por degrau**: a pergunta que se faz olhando um degrau é "o que
 *  aconteceu *aqui*". `<details>` nativo — teclado de graça, nenhum JavaScript novo. */
function HistoricoDoDegrau({ rung }: { rung: AccountRung }) {
  if (!rung.events.length) return null;
  // `group` + `group-open:`: `display:flex` no `<summary>` apaga o triângulo nativo do Chrome, e
  // uma gaveta sem seta é uma gaveta que ninguém sabe que abre. O `<details>` continua nativo —
  // teclado e leitor de tela de graça, nenhum JavaScript novo.
  return <details className="group mt-2.5">
    <summary className="type-label flex cursor-pointer items-center gap-2 text-muted">
      <ChevronDown className="size-3.5 shrink-0 transition-transform group-open:rotate-180" aria-hidden="true" />
      Histórico do degrau {rung.rung_display}
      <span className="state state--off">{rung.events.length} {rung.events.length === 1 ? "transição" : "transições"}</span>
    </summary>
    <div className="panel-rows mt-2 rounded-xl border border-line">
      {rung.events.map(evento => <div className="row" key={evento.id}>
        <span className="type-meta w-32 shrink-0 tabular-nums text-muted">{carimbo(evento.at)}</span>
        <div className="row-main">
          <strong>{evento.to_status_display}</strong>
          <span>de {evento.from_status_display || "—"} para {evento.to_status_display}{evento.note ? ` · ${evento.note}` : ""}</span>
        </div>
        {evento.by_name && <span className="state state--off shrink-0">{evento.by_name}</span>}
      </div>)}
    </div>
  </details>;
}

function Degrau({ rung, phases }: { rung: AccountRung; phases: ProjectPhase[] }) {
  const ativo = rung.status === "active";
  const selo = rung.no_access ? "state--off" : STATE_VARIANT[rung.status];
  const rotulo = rung.no_access ? "Sem acesso" : rung.status_display;
  const meta = metaDoDegrau(rung);
  const rodape = !rung.no_access && (rung.next_gate || rung.waiting_on || rung.status === "awaiting_gate");
  return <li className={`timeline-step ${rung.no_access ? STEP_VARIANT.not_sold : STEP_VARIANT[rung.status]}`}>
    <span className="timeline-marker" aria-hidden="true">{ativo && !rung.no_access ? <span /> : rung.no_access ? null : STEP_ICON[rung.status]}</span>
    <div className="timeline-body">
      {ativo && !rung.no_access && <p className="eyebrow mb-1">Você está aqui</p>}
      <div className="flex flex-wrap items-center gap-2">
        <strong className="type-title text-ink">{rung.rung_display}</strong>
        {selo && <span className={`state ${selo}`}>{rotulo}</span>}
        {!rung.no_access && rung.gate_outcome && <span className={`state ${gateBadgeClass(rung.gate_outcome)}`}>{GATE_LABEL[rung.gate_outcome]}</span>}
        {rung.is_stale && <span className="state state--2">Parado há {rung.days_stalled} dias</span>}
      </div>
      {meta && <p className="type-meta mt-1.5 text-muted">{meta}</p>}
      {/* O impedimento fica **visível sem abrir nota**: o bloqueio é a informação mais cara de
          esconder atrás de um clique. */}
      {!rung.no_access && rung.status === "blocked" && rung.blocker && <p className="type-meta mt-1 text-danger">{rung.blocker}</p>}
      {ativo && !rung.no_access && <JornadaAninhada phases={phases} />}
      {rodape && <div className="mt-2.5 flex flex-wrap items-center gap-2 border-t border-line pt-2.5">
        {rung.next_gate && <>
          <span className="type-meta font-bold uppercase tracking-[0.1em] text-muted">Próximo gate</span>
          <span className="type-label text-ink">{`${rung.next_gate.phase_name}${rung.next_gate.target_date ? ` · previsto ${dataSimples(rung.next_gate.target_date)}` : ""}`}</span>
        </>}
        {rung.status === "awaiting_gate" && <span className="type-meta text-muted">Quatro saídas possíveis: {GATE_OUTCOMES.map(saida => GATE_LABEL[saida]).join(" · ")}</span>}
        {rung.waiting_on && <>
          <span className="type-meta ml-auto font-bold uppercase tracking-[0.1em] text-muted">Esperando</span>
          <WaitingChip rung={rung} />
        </>}
      </div>}
      {!rung.no_access && <HistoricoDoDegrau rung={rung} />}
    </div>
  </li>;
}

type FdeLadderProps = {
  rungs: AccountRung[];
  /** As fases do projeto que realiza o degrau ativo (FDD 011). Vazio quando não há projeto. */
  phases: ProjectPhase[];
  loading: boolean;
  error: string;
};

/** Superfície A — a escada completa em `/clientes/:id`. */
export function FdeLadder({ rungs, phases, loading, error }: FdeLadderProps) {
  if (error) return <p role="alert" className="alert--error">{error}</p>;

  const concluidos = rungs.filter(rung => rung.status === "done").length;
  const pulados = rungs.filter(rung => rung.status === "skipped").length;
  const emGate = rungs.find(rung => rung.status === "awaiting_gate" && !rung.no_access);
  const ativo = rungs.find(rung => rung.status === "active" && !rung.no_access);

  return <section className="panel space-y-4 sm:p-6">
    <div className="panel-heading panel-heading--icon">
      <span className="metric-icon"><BarChart3 className="size-4" /></span>
      <div className="flex-1">
        <h2>Escada FDE</h2>
        {!loading && rungs.length > 0 && <p className="text-sm text-muted">{concluidos} de {rungs.length} {concluidos === 1 ? "degrau concluído" : "degraus concluídos"}{pulados ? ` · ${pulados} pulado` : ""}</p>}
      </div>
      {emGate && <span className="state state--gate shrink-0"><Lock className="size-3" />Human Gate pendente</span>}
    </div>

    {/* Esqueleto em `surface-subtle` e `line`, com o **raio do cartão real**: um bloco vazio com
        outro raio anuncia uma forma que não é a que vai chegar. Nenhum selo colorido — um
        esqueleto com estado anuncia um estado que ainda não se sabe. */}
    {loading
      ? <div className="animate-pulse space-y-3" data-testid="escada-carregando">{[1, 2, 3].map(item => <div className="h-11 rounded-xl border border-line bg-surface-subtle" key={item} />)}</div>
      : rungs.length
        ? <ol className="timeline">{rungs.map(rung => <Degrau rung={rung} phases={rung.id === ativo?.id ? phases : []} key={rung.id} />)}</ol>
        : <p className="empty-state">Nenhum degrau iniciado. A escada começa quando a primeira oportunidade desta conta for ganha e convertida.</p>}
  </section>;
}

/**
 * Superfície B — o bloco compacto na visão geral. **Serve para varrer a carteira, não para
 * operar:** a linha inteira é um link para a conta e não há controle nenhum aqui.
 *
 * A ordem (mais parada primeiro) e o teto de linhas são decididos no backend, junto do limiar de
 * "parado" — reimplementá-los aqui seria a segunda definição da regra.
 */
export function FdeLadderOverview({ rows }: { rows: AccountLadderRow[] }) {
  if (!rows.length) return null;
  return <section className="panel panel--flush">
    <div className="panel-heading panel-heading--icon">
      <span className="metric-icon"><BarChart3 className="size-4" /></span>
      <div className="flex-1"><h2>Escada FDE por conta</h2><p className="text-sm text-muted">Onde cada conta está e de quem é a bola</p></div>
      <a className="back-link shrink-0" href="/clientes">Abrir clientes</a>
    </div>
    <div className="panel-rows">
      {rows.map(row => <a className="row hover:bg-slate-50" href={`/clientes/${row.client_id}`} key={row.client_id}>
        {/* Decorativa: o degrau e o estado vão escritos por extenso na própria linha, logo ao
            lado — nenhuma informação existe só na forma do marcador. */}
        <ol className="timeline timeline--compact" aria-hidden="true">
          {row.steps.map(step => <li className={`timeline-step ${STEP_VARIANT[step.status]}`} key={step.rung}><span className="timeline-marker">{step.status === "active" ? <span /> : null}</span></li>)}
        </ol>
        <div className="row-main">
          <strong>{row.client_name}</strong>
          <span>{row.rung_display} · {row.status_display.toLocaleLowerCase("pt-BR")}</span>
        </div>
        <WaitingChip rung={row} />
        <span className={`type-meta w-24 shrink-0 text-right tabular-nums ${row.is_stale ? "font-bold text-warning" : "text-muted"}`}>{row.days_stalled === null ? "sem registro" : `parado há ${row.days_stalled} ${row.days_stalled === 1 ? "dia" : "dias"}`}</span>
      </a>)}
    </div>
  </section>;
}
