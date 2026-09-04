import { AlertTriangle, HeartPulse, Layers, Lightbulb, Percent, PiggyBank, Share2, SlidersHorizontal, Sparkles, Target, Timer, TrendingUp } from "lucide-react";
import { type ReactNode, useEffect, useState } from "react";

import { api } from "../api";
import { useAuth } from "../auth";
import { AgentPanel } from "../components/AgentPanel";
import { HealthBadge } from "../components/StatusDot";
import type { Analytics, HealthAssessment, Recommendation, RiskAssessment, RoiRow } from "../types";

const riskCls: Record<string, string> = { alto: "state--3", "médio": "state--2", baixo: "state--1" };

const money = new Intl.NumberFormat("pt-BR", { style: "currency", currency: "BRL", maximumFractionDigits: 0 });
const pct = (value: number | null) => value == null ? "—" : `${Math.round(value * 100)}%`;

// `Lead.source` é texto livre — o intake pode gravar o que quiser. O mapa nomeia o que a casa
// já produz e o resto passa como veio, porque origem desconhecida com o nome cru ainda é
// informação; trocada por "Outros" viraria um balde onde canais distintos se escondem juntos.
const sourceLabels: Record<string, string> = { site: "Site", direto: "Cadastro direto", indicacao: "Indicação" };
const sourceLabel = (source: string) => sourceLabels[source] || source;

export function IndicadoresPage() {
  const { user } = useAuth();
  const [data, setData] = useState<Analytics>();
  const [risks, setRisks] = useState<RiskAssessment[]>([]);
  const [healths, setHealths] = useState<HealthAssessment[]>([]);
  const [recommendations, setRecommendations] = useState<Recommendation[]>([]);
  const [error, setError] = useState("");
  useEffect(() => {
    api<Analytics>("/analytics/").then(setData).catch((cause: Error) => setError(cause.message));
    api<{ projects: RiskAssessment[] }>("/risk/").then(result => setRisks(result.projects)).catch(() => undefined);
    api<{ projects: HealthAssessment[] }>("/health/").then(result => setHealths(result.projects)).catch(() => undefined);
    api<{ items: Recommendation[] }>("/recommendations/").then(result => setRecommendations(result.items)).catch(() => undefined);
  }, []);

  if (error) return <div role="alert" className="alert--error">{error}</div>;
  if (!data) return <div className="animate-pulse space-y-6"><div className="h-10 w-64 rounded-xl bg-slate-200" /><div className="grid gap-4 md:grid-cols-4">{[1, 2, 3, 4].map(item => <div className="h-28 rounded-2xl bg-white" key={item} />)}</div></div>;

  const pipelineValue = data.pipeline.reduce((sum, stage) => sum + Number(stage.estimated_total || 0), 0);
  const opp = data.funnel.opportunities;

  return <section className="space-y-7">
    <header className="page-head flex flex-col justify-between gap-4 sm:flex-row sm:items-end"><div><p className="eyebrow">Gestão</p><h1>Indicadores</h1><p>Comercial, entrega e ROI da operação.</p></div>{user?.is_admin && <a href="/servicos" className="btn btn--secondary self-start sm:self-auto"><SlidersHorizontal className="size-4 text-brand-500" />Gerir serviços</a>}</header>

    <div className="grid gap-4 md:grid-cols-4">
      <Kpi icon={<Target className="size-4" />} label="Taxa de ganho" value={pct(data.win_rate)} />
      <Kpi icon={<Percent className="size-4" />} label="Ticket médio" value={money.format(Number(data.avg_ticket))} />
      <Kpi icon={<Timer className="size-4" />} label="Tempo de ciclo" value={data.avg_cycle_days == null ? "—" : `${Math.round(data.avg_cycle_days)} d`} />
      <Kpi icon={<TrendingUp className="size-4" />} label="ROI total" value={pct(data.roi.roi)} accent={data.roi.roi != null && data.roi.roi < 0 ? "danger" : "default"} />
    </div>

    <div className="grid gap-5 lg:grid-cols-[1fr_1fr]">
      <section className="panel sm:p-6">
        <h2 className="font-semibold text-ink">Funil</h2>
        <div className="mt-5 space-y-3">
          <FunnelRow label="Leads recebidos" value={data.funnel.leads.total} />
          <FunnelRow label="Oportunidades abertas" value={opp.open} />
          <FunnelRow label="Ganhas" value={opp.won} tone="win" />
          <FunnelRow label="Perdidas" value={opp.lost} tone="lost" />
          <FunnelRow label="Projetos" value={data.funnel.projects.total} />
        </div>
      </section>
      <section className="panel sm:p-6">
        <h2 className="font-semibold text-ink">Financeiro</h2>
        <div className="mt-5 grid grid-cols-2 gap-4">
          <div><p className="text-xs text-slate-600">Receita realizada</p><p className="mt-1 text-2xl font-semibold text-ink">{money.format(data.roi.revenue)}</p></div>
          <div><p className="text-xs text-slate-600">Custo</p><p className="mt-1 text-2xl font-semibold text-ink">{money.format(data.roi.cost)}</p></div>
          <div><p className="text-xs text-slate-600">Pipeline estimado</p><p className="mt-1 text-2xl font-semibold text-accent">{money.format(pipelineValue)}</p></div>
          <div className="flex items-center gap-2"><PiggyBank className="size-5 text-accent" /><span className="text-sm text-slate-600">ROI = (receita − custo) / custo</span></div>
        </div>
      </section>
    </div>

    <section className="panel panel--flush">
      <div className="flex items-center gap-2 border-b px-5 py-4 sm:px-6"><Layers className="size-4 text-accent" /><h2 className="font-semibold text-ink">Conversão por nível de produto</h2></div>
      <div className="divide-y">{data.funnel.by_tier.map(row => <div className="px-5 py-3 sm:px-6" key={row.tier}>
        <div className="flex items-center justify-between gap-3 text-sm"><span className="font-medium text-ink">{row.label}</span><span className="font-semibold text-accent">Ganho {pct(row.win_rate)}</span></div>
        <p className="mt-1 text-xs text-slate-600">{row.total} oportunidade(s) · {row.open} aberta(s) · {row.won} ganha(s) · {row.lost} perdida(s) · {money.format(Number(row.estimated_total))} estimados</p>
      </div>)}</div>
    </section>

    <section className="panel panel--flush">
      <div className="flex items-center gap-2 border-b px-5 py-4 sm:px-6"><Sparkles className="size-4 text-accent" /><h2 className="font-semibold text-ink">Conversão por etapa da jornada</h2></div>
      <div className="divide-y">{data.funnel.by_stage.map(row => <div className="px-5 py-3 sm:px-6" key={row.kind}>
        <div className="flex items-center justify-between gap-3 text-sm"><span className="font-medium text-ink">{row.label}</span><span className="font-semibold text-accent">{row.reached} cliente(s)</span></div>
        <p className="mt-1 text-xs text-slate-600">{row.total} artefato(s) · {row.sent} enviado(s) · {row.accepted} aceito(s) · {row.rejected} recusado(s) · aceitação {pct(row.acceptance_rate)}</p>
      </div>)}</div>
    </section>

    <section className="panel panel--flush">
      <div className="flex items-center gap-2 border-b px-5 py-4 sm:px-6"><Share2 className="size-4 text-accent" /><h2 className="font-semibold text-ink">Origem do negócio</h2><span className="text-xs text-slate-600">medida até o fechado</span></div>
      {data.funnel.by_source.length ? <div className="divide-y">{data.funnel.by_source.map(row => <div className="px-5 py-3 sm:px-6" key={row.source}>
        <div className="flex items-center justify-between gap-3 text-sm"><span className="font-medium text-ink">{sourceLabel(row.source)}</span><span className="font-semibold text-accent">{row.won} ganha(s)</span></div>
        <p className="mt-1 text-xs text-slate-600">{row.leads} lead(s) · {row.projects} projeto(s) · {money.format(Number(row.revenue))} de receita{row.leads > 0 && <> · fecha {pct(row.won / row.leads)}</>}</p>
      </div>)}</div> : <p className="px-6 py-6 text-center text-sm text-slate-600">Nenhum negócio registrado ainda.</p>}
    </section>

    <RoiTable title="ROI por cliente" rows={data.roi.by_account} />
    <RoiTable title="ROI por serviço" rows={data.roi.by_service} />

    <AgentPanel agentKey="financeiro" title="Agente Financeiro" roles={[]} placeholder="Ex.: qual cliente tem o pior ROI?" />

    <section className="panel panel--flush">
      <div className="flex items-center gap-2 border-b px-5 py-4 sm:px-6"><AlertTriangle className="size-4 text-danger" /><h2 className="font-semibold text-ink">Riscos de atraso</h2></div>
      {risks.length ? <div className="divide-y">{risks.slice(0, 8).map(assessment => <a href={`/projetos/${assessment.project_id}`} className="block px-5 py-3 hover:bg-slate-50/70 sm:px-6" key={assessment.project_id}>
        <div className="flex items-center justify-between gap-3"><span className="text-sm font-semibold text-ink">{assessment.name}</span><span className={`state shrink-0 ${riskCls[assessment.level] || "state--off"}`}>Risco {assessment.level}</span></div>
        {assessment.signals.length > 0 && <p className="mt-1 text-xs text-slate-600">{assessment.signals.map(signal => `${signal.label} (${signal.detail})`).join(" · ")}</p>}
        {assessment.forecast && <p className={`mt-1 text-xs font-medium ${assessment.forecast.delay_days > 0 ? "text-danger" : "text-slate-600"}`}>Previsão: término em {new Date(`${assessment.forecast.predicted_finish_date}T12:00:00`).toLocaleDateString("pt-BR")}{assessment.forecast.delay_days > 0 ? ` · atraso previsto de ${assessment.forecast.delay_days} dia(s)` : " · dentro do prazo"}</p>}
      </a>)}</div> : <p className="px-6 py-6 text-center text-sm text-slate-600">Nenhum projeto ativo em risco.</p>}
    </section>

    <section className="panel panel--flush">
      <div className="flex items-center gap-2 border-b px-5 py-4 sm:px-6"><HeartPulse className="size-4 text-accent" /><h2 className="font-semibold text-ink">Saúde dos projetos</h2></div>
      {healths.length ? <div className="divide-y">{healths.slice(0, 8).map(assessment => <a href={`/projetos/${assessment.project_id}`} className="block px-5 py-3 hover:bg-slate-50/70 sm:px-6" key={assessment.project_id}>
        <div className="flex items-center justify-between gap-3"><span className="text-sm font-semibold text-ink">{assessment.name}</span><HealthBadge level={assessment.level} score={assessment.score} /></div>
        {assessment.signals.length > 0 && <p className="mt-1 text-xs text-slate-600">{assessment.signals.map(signal => `${signal.label} (${signal.detail})`).join(" · ")}</p>}
      </a>)}</div> : <p className="px-6 py-6 text-center text-sm text-slate-600">Nenhum projeto ativo.</p>}
    </section>

    <section className="panel panel--flush">
      <div className="flex items-center gap-2 border-b px-5 py-4 sm:px-6"><Lightbulb className="size-4 text-accent" /><h2 className="font-semibold text-ink">Recomendações</h2><span className="text-xs text-slate-600">revise antes de agir</span></div>
      {recommendations.length ? <div className="divide-y">{recommendations.map((rec, index) => <a href={rec.url} className="block px-5 py-3 hover:bg-slate-50/70 sm:px-6" key={`${rec.kind}-${index}`}><p className="text-sm font-semibold text-ink">{rec.label}</p><p className="mt-0.5 text-xs text-slate-600">{rec.detail}</p></a>)}</div> : <p className="px-6 py-6 text-center text-sm text-slate-600">Sem recomendações no momento.</p>}
    </section>
  </section>;
}

function Kpi({ icon, label, value, accent = "default" }: { icon: ReactNode; label: string; value: string; accent?: "default" | "danger" }) {
  return <article className="panel"><div className="flex items-start justify-between"><span className="text-sm font-medium text-slate-600">{label}</span><span className={`grid size-9 place-items-center rounded-xl ${accent === "danger" ? "state--3" : "state--0"}`}>{icon}</span></div><strong className={`mt-6 block text-3xl font-semibold tracking-tight ${accent === "danger" ? "text-danger" : "text-ink"}`}>{value}</strong></article>;
}

function FunnelRow({ label, value, tone = "default" }: { label: string; value: number; tone?: "default" | "win" | "lost" }) {
  const color = tone === "win" ? "text-emerald-700" : tone === "lost" ? "text-slate-600" : "text-ink";
  return <div className="flex items-center justify-between text-sm"><span className="text-slate-600">{label}</span><span className={`font-semibold ${color}`}>{value}</span></div>;
}

function RoiTable({ title, rows }: { title: string; rows: RoiRow[] }) {
  const max = Math.max(1, ...rows.map(row => row.revenue));
  return <section className="panel panel--flush">
    <div className="border-b px-5 py-4 sm:px-6"><h2 className="font-semibold text-ink">{title}</h2></div>
    {rows.length ? <div className="divide-y">{rows.map(row => <div className="px-5 py-3 sm:px-6" key={row.label}>
      <div className="flex items-center justify-between text-sm"><span className="font-medium text-ink">{row.label}</span><span className={`font-semibold ${row.roi != null && row.roi < 0 ? "text-danger" : "text-accent"}`}>ROI {row.roi == null ? "—" : `${Math.round(row.roi * 100)}%`}</span></div>
      <div className="mt-2 h-2 overflow-hidden rounded-full bg-slate-100"><div className="h-full rounded-full bg-ink" style={{ width: `${Math.max(4, row.revenue / max * 100)}%` }} /></div>
      <div className="mt-1 flex justify-between text-xs text-slate-600"><span>Receita {money.format(row.revenue)}</span><span>Custo {money.format(row.cost)}</span></div>
    </div>)}</div> : <p className="px-6 py-6 text-center text-sm text-slate-600">Sem dados financeiros ainda. Preencha receita/custo nos projetos.</p>}
  </section>;
}
