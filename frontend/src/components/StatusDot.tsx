import type { HealthLevel } from "../types";

// Semáforo de saúde 🟢🟡🔴 reutilizável (eleva o mapa antes duplicado em IndicadoresPage).
const HEALTH_BADGE: Record<HealthLevel, string> = {
  "saudável": "bg-emerald-50 text-emerald-700",
  "atenção": "bg-amber-50 text-amber-700",
  "crítico": "bg-red-50 text-signal",
};
const HEALTH_DOT: Record<HealthLevel, string> = {
  "saudável": "bg-emerald-500",
  "atenção": "bg-amber-500",
  "crítico": "bg-signal",
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
