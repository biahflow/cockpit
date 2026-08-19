import type { HealthLevel, SatisfacaoNivel } from "../types";

// Semáforo de saúde 🟢🟡🔴 reutilizável (eleva o mapa antes duplicado em IndicadoresPage).
// Variantes de `.state`, não as cores delas (ADR 0026): um `bg-emerald-50` escrito aqui é uma
// segunda definição de "saudável", e ela diverge da primeira sem nada ficar vermelho.
const HEALTH_BADGE: Record<HealthLevel, string> = {
  "saudável": "state--1",
  "atenção": "state--2",
  "crítico": "state--3",
};
const HEALTH_DOT: Record<HealthLevel, string> = {
  "saudável": "bg-emerald-500",
  "atenção": "bg-amber-500",
  "crítico": "bg-danger",
};

export function healthBadgeClass(level: HealthLevel): string {
  return HEALTH_BADGE[level];
}

// A satisfação do cliente (FDD 037, ADR 0032). Duas telas leem o mesmo nível — a de detalhe do
// cliente e a de Cobrança —, e o mapa mora aqui, ao lado do de saúde, pela mesma razão: uma cópia
// por tela é a segunda definição que diverge sem nada ficar vermelho. `neutro` é `state--off` de
// propósito — é o nível que não é alerta, no molde de "Desligada"/"Arquivado". `insatisfeito` é o
// único que muda comportamento (Health Score e escada da régua) e é o único em `state--3`.
const SATISFACAO_BADGE: Record<SatisfacaoNivel, string> = {
  promotor: "state--0",
  satisfeito: "state--1",
  neutro: "state--off",
  insatisfeito: "state--3",
};

export function satisfacaoBadgeClass(nivel: SatisfacaoNivel): string {
  return SATISFACAO_BADGE[nivel];
}

export function StatusDot({ level, title }: { level: HealthLevel | null; title?: string }) {
  const cls = level ? HEALTH_DOT[level] : "bg-slate-300";
  return (
    <span
      className={`inline-block size-2.5 rounded-full ${cls}`}
      title={title ?? (level ? `Saúde: ${level}` : "Sem projeto ativo")}
      aria-label={level ? `Saúde ${level}` : "Sem projeto ativo"}
    />
  );
}

export function HealthBadge({ level, score }: { level: HealthLevel; score?: number }) {
  return (
    <span className={`rounded-full px-2.5 py-1 text-xs font-semibold ${HEALTH_BADGE[level]}`}>
      {level}{score !== undefined ? ` · ${score}` : ""}
    </span>
  );
}
