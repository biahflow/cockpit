// Mapas da linha do tempo operacional da entrega (FDD 042). Moram aqui, num só lugar, pela razão
// da ADR 0026: **duas telas leem os mesmos valores** — o detalhe do projeto e o dashboard —, e uma
// cópia por tela é a segunda definição que diverge sem nada ficar vermelho. Situação → **variante**
// de `.state`, nunca a cor: um `bg-emerald-50` escrito aqui seria uma segunda definição de
// "concluída". A regra de qual situação vale sai do backend (`ProjectPhase.situation`); a tela só a
// pinta.
import type { CanonicalStage, GateDecision, PhaseEventKind, PhaseSituation, WaitingParty } from "./types";

// `blocked`/`cancelled` são `state--3` (alerta real: algo travou ou a jornada parou);
// `waiting_decision`/`replanned` são `state--2` (aviso, não falha); `pending` é `state--off`, o
// neutro — uma fase futura da jornada não é aviso, no molde de "Arquivado".
const SITUATION_VARIANT: Record<PhaseSituation, string> = {
  active: "state--0",
  completed: "state--1",
  blocked: "state--3",
  waiting_decision: "state--2",
  cancelled: "state--3",
  replanned: "state--2",
  pending: "state--off",
};

export const SITUATION_LABEL: Record<PhaseSituation, string> = {
  active: "Em andamento",
  completed: "Concluída",
  blocked: "Bloqueada",
  waiting_decision: "Aguardando decisão",
  cancelled: "Cancelada",
  replanned: "Replanejada",
  pending: "Pendente",
};

export function situationVariant(situation: PhaseSituation): string {
  return SITUATION_VARIANT[situation];
}

export const WAITING_PARTY_LABEL: Record<Exclude<WaitingParty, "">, string> = {
  biahflow: "Biahflow",
  client: "Cliente",
  engineering: "Engenharia",
  external: "Dependência externa",
  human_gate: "Human Gate",
};

export const CANONICAL_STAGE_LABEL: Record<Exclude<CanonicalStage, "">, string> = {
  discover: "Discover",
  prioritize: "Prioritize",
  feasibility: "Feasibility",
  prove: "Prove",
  scale: "Scale",
  optimize: "Optimize",
};

export const PHASE_EVENT_LABEL: Record<PhaseEventKind, string> = {
  started: "Fase iniciada",
  completed: "Fase concluída",
  reopened: "Fase reaberta",
  locked_by_redesign: "Trancada por REDESIGN",
  gate_recorded: "Decision gate registrado",
  waiting_set: "Aguardando definido",
  waiting_cleared: "Aguardando resolvido",
};

// As opções que a tela oferece para "quem estamos esperando" — a ordem é a da API.
export const WAITING_PARTY_OPTIONS: Exclude<WaitingParty, "">[] = [
  "biahflow",
  "client",
  "engineering",
  "external",
  "human_gate",
];

// ---------------------------------------------------------------------------
// Os dois vocabulários de gate (ADR 0053)
// ---------------------------------------------------------------------------

// Os rótulos são os da metodologia, em maiúsculas, e **não se traduzem**: são o vocabulário da
// casa, não identificadores de UI.
export const GATE_DECISION_LABEL: Record<GateDecision, string> = {
  go: "GO",
  conditional_go: "CONDITIONAL GO",
  redesign: "REDESIGN",
  no_go: "NO-GO",
  scale: "SCALE",
  iterate: "ITERATE",
  stop: "STOP",
};

// O efeito de cada saída sobre a jornada. As duas famílias caem nos mesmos três, e é por isso que
// o backend ramifica por efeito e não por valor (`models.CONCLUEM_E_AVANCAM` e irmãs). A tela usa
// o mesmo mapa para decidir a pele do botão e o que pede confirmação — SCALE se parece com GO,
// ITERATE com REDESIGN, STOP com NO-GO.
export type GateEffect = "advance" | "reopen" | "halt";
export const GATE_EFFECT: Record<GateDecision, GateEffect> = {
  go: "advance",
  conditional_go: "advance",
  scale: "advance",
  redesign: "reopen",
  iterate: "reopen",
  no_go: "halt",
  stop: "halt",
};

const DECISOES_DA_FEASIBILITY: GateDecision[] = ["go", "conditional_go", "redesign", "no_go"];
const DECISOES_DO_PROVE: GateDecision[] = ["scale", "iterate", "stop"];

/**
 * O vocabulário do gate desta fase — **um mapa só, e as duas telas o consomem**.
 *
 * Espelha `models.decisoes_do_gate` no backend, inclusive na regra do branco: fase de gate sem
 * `canonical_stage` recebe as quatro da Feasibility, que são as saídas de propósito geral. Uma
 * cópia por tela seria a segunda definição que diverge sem nada ficar vermelho (ADR 0026), e o
 * servidor recusa com 400 o que a tela oferecer fora daqui.
 */
export function gateDecisions(stage: CanonicalStage): GateDecision[] {
  return stage === "prove" ? DECISOES_DO_PROVE : DECISOES_DA_FEASIBILITY;
}

/** A saída que reabre a fase anterior, e a que para a jornada — para a copy de apoio. */
export function gateDecisionByEffect(stage: CanonicalStage, effect: GateEffect): GateDecision {
  return gateDecisions(stage).find(decision => GATE_EFFECT[decision] === effect)!;
}
