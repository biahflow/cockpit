import { AlertTriangle, ArrowUpRight, BriefcaseBusiness, CalendarDays, CircleDollarSign } from "lucide-react";
import { useEffect, useState } from "react";

import { api } from "../api";
import { useAuth } from "../auth";
import type { Dashboard } from "../types";

const money = new Intl.NumberFormat("pt-BR", { style: "currency", currency: "BRL", maximumFractionDigits: 0 });

const metricCards = [
  ["Projetos ativos", BriefcaseBusiness, "active_projects"],
  ["Itens em atraso", AlertTriangle, "overdue_count"],
] as const;

export function DashboardPage() {
  // Entrega não recebe o funil (RFC 0003): o backend devolve `pipeline` vazio, e mostrar
  // "R$ 0" com uma seção vazia seria pior do que não mostrar.
  const { user } = useAuth();
  // O backend já manda o pipeline preenchido para quem é admin (`views.py:151`); filtrar só por
  // `role` fazia o SPA **descartar dado que chegou** na tela de um superusuário.
  const showPipeline = !!user?.is_admin || user?.role !== "delivery";
  const [data, setData] = useState<Dashboard>();
  const [error, setError] = useState("");
  useEffect(() => { api<Dashboard>("/dashboard/").then(setData).catch((cause: Error) => setError(cause.message)); }, []);
  if (error) return <div role="alert" className="alert--error">{error}</div>;
  if (!data) return <div className="animate-pulse space-y-6"><div className="h-10 w-64 rounded-xl bg-slate-200" /><div className="grid gap-4 md:grid-cols-3">{[1, 2, 3].map(item => <div className="h-32 rounded-2xl bg-white" key={item} />)}</div></div>;
  const pipelineValue = data.pipeline.reduce((sum, stage) => sum + Number(stage.estimated_total || 0), 0);

  return <section className="space-y-7"><header className="page-head flex flex-col justify-between gap-4 sm:flex-row sm:items-end"><div><p className="eyebrow">Visão geral</p><h1 className="sm:text-4xl">Sua operação, em movimento.</h1><p>Acompanhe a saúde comercial e as entregas que pedem atenção.</p></div><a href="/comercial" className="btn self-start sm:self-auto">Ver pipeline <ArrowUpRight className="size-4" /></a></header>
    <div className="grid gap-4 md:grid-cols-3">{metricCards.map(([label, Icon, key]) => <article key={label} className="metric-card p-5"><div className="flex items-start justify-between"><span className="text-sm font-medium text-muted">{label}</span><span className={`metric-icon ${key === "overdue_count" ? "bg-red-50 text-danger" : ""}`}><Icon className="size-4" /></span></div><strong className={`mt-6 block text-3xl ${key === "overdue_count" && data[key] > 0 ? "text-danger" : "text-ink"}`}>{data[key]}</strong><span className="mt-1 block">Atualizado em tempo real</span></article>)}{showPipeline && <article className="rounded-2xl bg-ink p-5 text-white shadow-lg shadow-ink/10"><div className="flex items-start justify-between"><span className="text-sm font-medium text-white/65">Pipeline estimado</span><span className="grid size-9 place-items-center rounded-xl bg-white/10 text-brand-200"><CircleDollarSign className="size-4" /></span></div><strong className="mt-6 block text-3xl font-semibold tracking-tight">{money.format(pipelineValue)}</strong><p className="mt-1 text-xs text-white/50">Potencial em negociação</p></article>}</div>
    <div className={`grid gap-5 ${showPipeline ? "lg:grid-cols-[1.25fr_.75fr]" : ""}`}>{showPipeline && <section className="panel sm:p-6"><div className="panel-heading items-center"><div><h2>Pipeline comercial</h2><p className="mt-1 text-sm text-muted">Volume e valor por etapa</p></div><a className="back-link" href="/comercial">Abrir comercial</a></div><div className="space-y-4">{data.pipeline.map(stage => <div key={stage.id}><div className="mb-2 flex items-center justify-between text-sm"><span className="font-medium text-slate-700">{stage.name}</span><span className="text-muted">{stage.opportunity_count || 0} oportunidades</span></div><div className="h-2 overflow-hidden rounded-full bg-slate-100"><div className="h-full rounded-full bg-brand-500" style={{ width: `${pipelineValue ? Math.max(7, Number(stage.estimated_total || 0) / pipelineValue * 100) : 7}%` }} /></div></div>)}</div></section>}
      <section className="panel sm:p-6"><div className="panel-heading panel-heading--icon"><span className="metric-icon"><CalendarDays className="size-4" /></span><div><h2>Próximas entregas</h2><p className="text-sm text-muted">O que vem a seguir</p></div></div><div className="divide-y divide-line">{data.upcoming_tasks.length ? data.upcoming_tasks.map(task => <div className="flex items-center justify-between gap-4 py-3" key={task.id}><span className="text-sm font-medium text-slate-700">{task.title}</span><time className="shrink-0 text-xs text-muted">{new Date(`${task.due_date}T12:00:00`).toLocaleDateString("pt-BR", { day: "2-digit", month: "short" })}</time></div>) : <p className="py-7 text-center text-sm text-muted">Nenhuma tarefa próxima.</p>}</div></section></div>
  </section>;
}
