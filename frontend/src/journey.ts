// Mapas da linha do tempo operacional da entrega (FDD 042). Moram aqui, num só lugar, pela razão
// da ADR 0026: **duas telas leem os mesmos valores** — o detalhe do projeto e o dashboard —, e uma
// cópia por tela é a segunda definição que diverge sem nada ficar vermelho. Situação → **variante**
// de `.state`, nunca a cor: um `bg-emerald-50` escrito aqui seria uma segunda definição de
// "concluída". A regra de qual situação vale sai do backend (`ProjectPhase.situation`); a tela só a
// pinta.
import type { CanonicalStage, PhaseEventKind, PhaseSituation, WaitingParty } from "./types";

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
