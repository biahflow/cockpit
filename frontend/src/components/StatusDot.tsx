import type { HealthLevel } from "../types";

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
