import { AlertTriangle, CalendarDays, FolderKanban, Plus } from "lucide-react";
import { useEffect, useState } from "react";

import { api } from "../api";
import { useAuth } from "../auth";
import { AgentPanel } from "../components/AgentPanel";
import type { Project } from "../types";

const statusLabel: Record<string, string> = { planning: "Planejamento", active: "Ativo", on_hold: "Em espera", completed: "Concluído" };

export function ProjectsPage() {
  // Entrega não converte oportunidade nem cria projeto (RFC 0003) — e a lista vazia dela
  // significa "ninguém te pôs numa equipe ainda", não "não há projetos".
  const { user } = useAuth();
  // "Entrega" aqui quer dizer **Entrega restrita**: um superusuário com papel `delivery` não é,
  // e mandá-lo "pedir a um administrador" seria mandá-lo pedir a si mesmo.
  const isDelivery = user?.role === "delivery" && !user.is_admin;
  const [projects, setProjects] = useState<Project[]>([]);
  const [error, setError] = useState("");
  useEffect(() => { api<Project[]>("/projects/").then(setProjects).catch((cause: Error) => setError(cause.message)); }, []);
  return <section className="space-y-7"><header className="flex flex-col justify-between gap-4 sm:flex-row sm:items-end"><div><p className="text-sm font-semibold text-ocean">Entrega</p><h1 className="mt-1 text-3xl font-semibold tracking-tight text-ink">Projetos</h1><p className="mt-2 text-sm text-slate-600">Visibilidade sobre cada compromisso em andamento.</p></div>{!isDelivery && <a href="/comercial" className="inline-flex items-center gap-2 self-start rounded-xl border bg-white px-4 py-2.5 text-sm font-semibold text-ink hover:border-ocean sm:self-auto" title="Projetos nascem de oportunidades ganhas no Comercial"><Plus className="size-4 text-ocean" />Converter oportunidade (ir ao Comercial)</a>}</header>{error && <p role="alert" className="rounded-xl bg-red-50 p-3 text-sm text-signal">{error}</p>}
    <AgentPanel agentKey="entrega" title="Agente de Entrega" roles={["delivery"]} placeholder="Ex.: quais projetos estão em risco?" />
    <section className="overflow-hidden rounded-2xl border bg-white"><div className="flex items-center justify-between border-b px-5 py-5 sm:px-6"><div><h2 className="font-semibold text-ink">Em acompanhamento</h2><p className="mt-1 text-sm text-slate-600">Prazos, estado atual e atenção necessária.</p></div><span className="rounded-xl bg-mint px-3 py-1.5 text-sm font-semibold text-ocean">{projects.length} projetos</span></div>{projects.length ? <div className="overflow-x-auto" tabIndex={0} role="region" aria-label="Projetos em acompanhamento"><table className="min-w-full text-left"><thead className="bg-slate-50 text-xs uppercase tracking-wide text-slate-600"><tr><th className="px-5 py-3 font-semibold sm:px-6">Projeto</th><th className="px-5 py-3 font-semibold">Prazo</th><th className="px-5 py-3 font-semibold">Status</th></tr></thead><tbody className="divide-y">{projects.map(project => <tr className="transition hover:bg-slate-50/70" key={project.id}><td className="px-5 py-4 sm:px-6"><a href={`/projetos/${project.id}`} className="flex items-center gap-3"><span className="grid size-9 place-items-center rounded-xl bg-mint text-ocean"><FolderKanban className="size-4" /></span><span className="text-sm font-semibold text-ink hover:text-ocean">{project.name}</span></a></td><td className={`px-5 py-4 text-sm ${project.is_overdue ? "font-semibold text-signal" : "text-slate-600"}`}><span className="inline-flex items-center gap-2">{project.is_overdue ? <AlertTriangle className="size-4" /> : <CalendarDays className="size-4 text-slate-600" />}{new Date(`${project.due_date}T12:00:00`).toLocaleDateString("pt-BR")}</span></td><td className="px-5 py-4"><span className={`rounded-full px-2.5 py-1 text-xs font-semibold ${project.status === "active" ? "bg-emerald-50 text-emerald-700" : project.status === "completed" ? "bg-slate-100 text-slate-600" : "bg-amber-50 text-amber-700"}`}>{statusLabel[project.status] || project.status}</span></td></tr>)}</tbody></table></div> : <div className="grid min-h-72 place-items-center p-6 text-center"><div><span className="mx-auto grid size-12 place-items-center rounded-2xl bg-mint text-ocean"><FolderKanban className="size-5" /></span><h3 className="mt-4 font-semibold text-ink">{isDelivery ? "Você ainda não participa de nenhum projeto" : "Nenhum projeto em andamento"}</h3><p className="mt-1 max-w-sm text-sm text-slate-600">{isDelivery ? "Peça a um administrador para incluir você na equipe do projeto." : "Quando uma oportunidade for ganha, você poderá transformá-la em projeto."}</p></div></div>}</section>
  </section>;
}
