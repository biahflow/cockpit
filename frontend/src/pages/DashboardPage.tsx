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
  // O esqueleto usa tokens de superfície e o **raio do cartão real** (12px): um bloco vazio com
  // outro raio anuncia uma forma que não é a que vai chegar.
  if (!data) return <div className="animate-pulse space-y-6"><div className="h-10 w-64 rounded-xl bg-surface-subtle" /><div className="grid gap-4 md:grid-cols-3">{[1, 2, 3].map(item => <div className="h-32 rounded-xl border border-line bg-surface" key={item} />)}</div></div>;
  const pipelineValue = data.pipeline.reduce((sum, stage) => sum + Number(stage.estimated_total || 0), 0);

  return <section className="space-y-7"><header className="page-head flex flex-col justify-between gap-4 sm:flex-row sm:items-end"><div><p className="eyebrow">Visão geral</p><h1 className="sm:text-4xl">Sua operação, em movimento.</h1><p>Acompanhe a saúde comercial e as entregas que pedem atenção.</p></div><a href="/comercial" className="btn self-start sm:self-auto">Ver pipeline <ArrowUpRight className="size-4" /></a></header>
    <div className="grid gap-4 md:grid-cols-3">{metricCards.map(([label, Icon, key]) => <article key={label} className="metric-card p-5"><div className="flex items-start justify-between"><span className="text-sm font-medium text-muted">{label}</span><span className={`metric-icon ${key === "overdue_count" ? "metric-icon--danger" : ""}`}><Icon className="size-4" /></span></div><strong className={`mt-6 block ${key === "overdue_count" && data[key] > 0 ? "text-danger" : "text-ink"}`}>{data[key]}</strong><span className="mt-1 block">Atualizado em tempo real</span></article>)}{showPipeline && <article className="metric-card metric-card--dark p-5"><div className="flex items-start justify-between"><span className="text-sm font-medium">Pipeline estimado</span><span className="metric-icon metric-icon--dark"><CircleDollarSign className="size-4" /></span></div><strong className="mt-6 block">{money.format(pipelineValue)}</strong><p className="mt-1">Potencial em negociação</p></article>}</div>
    <div className={`grid gap-5 ${showPipeline ? "lg:grid-cols-[1.25fr_.75fr]" : ""}`}>{showPipeline && <section className="panel sm:p-6"><div className="panel-heading items-center"><div><h2>Pipeline comercial</h2><p className="mt-1 text-sm text-muted">Volume e valor por etapa</p></div><a className="back-link" href="/comercial">Abrir comercial</a></div><div className="space-y-4">{data.pipeline.map(stage => <div key={stage.id}><div className="type-body mb-2 flex items-center justify-between"><span className="font-medium text-ink">{stage.name}</span><span className="text-muted">{stage.opportunity_count || 0} oportunidades</span></div><div className="h-2 overflow-hidden rounded-full bg-line"><div className="h-full rounded-full bg-brand-500" style={{ width: `${pipelineValue ? Math.max(7, Number(stage.estimated_total || 0) / pipelineValue * 100) : 7}%` }} /></div></div>)}</div></section>}
      <section className="panel sm:p-6"><div className="panel-heading panel-heading--icon"><span className="metric-icon"><CalendarDays className="size-4" /></span><div><h2>Próximas entregas</h2><p className="text-sm text-muted">O que vem a seguir</p></div></div><div className="divide-y divide-line">{data.upcoming_tasks.length ? data.upcoming_tasks.map(task => <div className="flex items-center justify-between gap-4 py-3" key={task.id}><span className="type-body font-medium text-ink">{task.title}</span><time className="shrink-0 text-xs text-muted">{new Date(`${task.due_date}T12:00:00`).toLocaleDateString("pt-BR", { day: "2-digit", month: "short" })}</time></div>) : <p className="py-7 text-center text-sm text-muted">Nenhuma tarefa próxima.</p>}</div></section></div>
  </section>;
}
