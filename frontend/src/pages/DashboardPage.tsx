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
  const showPipeline = user?.role !== "delivery";
  const [data, setData] = useState<Dashboard>();
  const [error, setError] = useState("");
  useEffect(() => { api<Dashboard>("/dashboard/").then(setData).catch((cause: Error) => setError(cause.message)); }, []);
  if (error) return <div role="alert" className="rounded-2xl border border-red-100 bg-red-50 p-4 text-sm text-signal">{error}</div>;
  if (!data) return <div className="animate-pulse space-y-6"><div className="h-10 w-64 rounded-xl bg-slate-200" /><div className="grid gap-4 md:grid-cols-3">{[1, 2, 3].map(item => <div className="h-32 rounded-2xl bg-white" key={item} />)}</div></div>;
  const pipelineValue = data.pipeline.reduce((sum, stage) => sum + Number(stage.estimated_total || 0), 0);

  return <section className="space-y-7"><header className="flex flex-col justify-between gap-4 sm:flex-row sm:items-end"><div><p className="text-sm font-semibold text-ocean">Visão geral</p><h1 className="mt-1 text-3xl font-semibold tracking-tight text-ink sm:text-4xl">Sua operação, em movimento.</h1><p className="mt-2 text-sm text-slate-500">Acompanhe a saúde comercial e as entregas que pedem atenção.</p></div><a href="/comercial" className="inline-flex items-center gap-2 self-start rounded-xl bg-ocean px-4 py-2.5 text-sm font-semibold text-white transition hover:bg-ink sm:self-auto">Ver pipeline <ArrowUpRight className="size-4" /></a></header>
    <div className="grid gap-4 md:grid-cols-3">{metricCards.map(([label, Icon, key]) => <article key={label} className="rounded-2xl border bg-white p-5 shadow-sm shadow-slate-200/50"><div className="flex items-start justify-between"><span className="text-sm font-medium text-slate-500">{label}</span><span className={`grid size-9 place-items-center rounded-xl ${key === "overdue_count" ? "bg-red-50 text-signal" : "bg-mint text-ocean"}`}><Icon className="size-4" /></span></div><strong className={`mt-6 block text-3xl font-semibold tracking-tight ${key === "overdue_count" && data[key] > 0 ? "text-signal" : "text-ink"}`}>{data[key]}</strong><p className="mt-1 text-xs text-slate-400">Atualizado em tempo real</p></article>)}{showPipeline && <article className="rounded-2xl bg-ink p-5 text-white shadow-lg shadow-ink/10"><div className="flex items-start justify-between"><span className="text-sm font-medium text-white/65">Pipeline estimado</span><span className="grid size-9 place-items-center rounded-xl bg-white/10 text-mint"><CircleDollarSign className="size-4" /></span></div><strong className="mt-6 block text-3xl font-semibold tracking-tight">{money.format(pipelineValue)}</strong><p className="mt-1 text-xs text-white/50">Potencial em negociação</p></article>}</div>
    <div className={`grid gap-5 ${showPipeline ? "lg:grid-cols-[1.25fr_.75fr]" : ""}`}>{showPipeline && <section className="rounded-2xl border bg-white p-5 sm:p-6"><div className="flex items-center justify-between"><div><h2 className="font-semibold text-ink">Pipeline comercial</h2><p className="mt-1 text-sm text-slate-500">Volume e valor por etapa</p></div><a className="text-sm font-semibold text-ocean hover:text-ink" href="/comercial">Abrir comercial</a></div><div className="mt-6 space-y-4">{data.pipeline.map(stage => <div key={stage.id}><div className="mb-2 flex items-center justify-between text-sm"><span className="font-medium text-slate-700">{stage.name}</span><span className="text-slate-500">{stage.opportunity_count || 0} oportunidades</span></div><div className="h-2 overflow-hidden rounded-full bg-slate-100"><div className="h-full rounded-full bg-ocean" style={{ width: `${pipelineValue ? Math.max(7, Number(stage.estimated_total || 0) / pipelineValue * 100) : 7}%` }} /></div></div>)}</div></section>}
      <section className="rounded-2xl border bg-white p-5 sm:p-6"><div className="flex items-center gap-3"><span className="grid size-9 place-items-center rounded-xl bg-mint text-ocean"><CalendarDays className="size-4" /></span><div><h2 className="font-semibold text-ink">Próximas entregas</h2><p className="text-sm text-slate-500">O que vem a seguir</p></div></div><div className="mt-5 divide-y">{data.upcoming_tasks.length ? data.upcoming_tasks.map(task => <div className="flex items-center justify-between gap-4 py-3" key={task.id}><span className="text-sm font-medium text-slate-700">{task.title}</span><time className="shrink-0 text-xs text-slate-500">{new Date(`${task.due_date}T12:00:00`).toLocaleDateString("pt-BR", { day: "2-digit", month: "short" })}</time></div>) : <p className="py-7 text-center text-sm text-slate-500">Nenhuma tarefa próxima.</p>}</div></section></div>
  </section>;
}
