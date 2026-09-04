import { AlertTriangle, CalendarDays, FolderKanban, Plus, RotateCcw } from "lucide-react";
import { useCallback, useEffect, useState } from "react";

import { api } from "../api";
import { useAuth } from "../auth";
import { AgentPanel } from "../components/AgentPanel";
import { isDeliveryOnly } from "../roles";
import type { Project } from "../types";

const statusLabel: Record<string, string> = { planning: "Planejamento", active: "Ativo", on_hold: "Em espera", completed: "Concluído" };

export function ProjectsPage() {
  // Entrega não converte oportunidade nem cria projeto (RFC 0003) — e a lista vazia dela
  // significa "ninguém te pôs numa equipe ainda", não "não há projetos".
  const { user } = useAuth();
  // "Entrega" aqui quer dizer **Entrega restrita**: um superusuário com papel `delivery` não é,
  // e mandá-lo "pedir a um administrador" seria mandá-lo pedir a si mesmo.
  const isDelivery = isDeliveryOnly(user);
  const [projects, setProjects] = useState<Project[]>([]);
  const [error, setError] = useState("");
  const [showArchived, setShowArchived] = useState(false);
  const [restoring, setRestoring] = useState<number | null>(null);
  const load = useCallback(
    () => api<Project[]>(`/projects/${showArchived ? "?archived=1" : ""}`).then(setProjects).catch((cause: Error) => setError(cause.message)),
    [showArchived],
  );
  useEffect(() => { void load(); }, [load]);
  async function restore(id: number) {
    setError(""); setRestoring(id);
    try { await api(`/projects/${id}/unarchive/`, { method: "POST" }); await load(); }
    catch (cause) { setError((cause as Error).message); }
    finally { setRestoring(null); }
  }
  return <section className="space-y-7"><header className="page-head flex flex-col justify-between gap-4 sm:flex-row sm:items-end"><div><p className="eyebrow">Entrega</p><h1>Projetos</h1><p>Visibilidade sobre cada compromisso em andamento.</p></div>{!isDelivery && <a href="/comercial" className="btn btn--secondary self-start sm:self-auto" title="Projetos nascem de oportunidades ganhas no Comercial"><Plus className="size-4 text-brand-500" />Converter oportunidade (ir ao Comercial)</a>}</header>{error && <p role="alert" className="alert--error">{error}</p>}
    <AgentPanel agentKey="entrega" title="Agente de Entrega" roles={["delivery"]} placeholder="Ex.: quais projetos estão em risco?" />
    <section className="panel panel--flush"><div className="panel-heading justify-between py-5"><div><h2>{showArchived ? "Arquivados" : "Em acompanhamento"}</h2><p className="mt-1 text-sm text-muted">{showArchived ? "Projetos fora das listagens ativas. Restaurar devolve o projeto ao acompanhamento." : "Prazos, estado atual e atenção necessária."}</p></div><div className="flex items-center gap-3"><div className="filter-bar"><button className={`filter-chip ${showArchived ? "" : "filter-chip--on"}`} onClick={() => setShowArchived(false)}>Ativos</button><button className={`filter-chip ${showArchived ? "filter-chip--on" : ""}`} onClick={() => setShowArchived(true)}>Arquivados</button></div><span className="state state--0">{projects.length} projetos</span></div></div>{projects.length ? <div className="overflow-x-auto" tabIndex={0} role="region" aria-label="Projetos em acompanhamento"><table className="min-w-full text-left"><thead className="bg-slate-50 text-xs uppercase tracking-wide text-muted"><tr><th className="px-5 py-3 font-semibold sm:px-6">Projeto</th><th className="px-5 py-3 font-semibold">Prazo</th><th className="px-5 py-3 font-semibold">Status</th>{showArchived && <th className="px-5 py-3 font-semibold">Ação</th>}</tr></thead><tbody className="divide-y divide-line">{projects.map(project => <tr className="transition hover:bg-slate-50/70" key={project.id}><td className="px-5 py-4 sm:px-6"><a href={`/projetos/${project.id}`} className="flex items-center gap-3"><span className="metric-icon"><FolderKanban className="size-4" /></span><span className="text-sm font-semibold text-ink hover:text-brand-600">{project.name}</span></a></td><td className={`px-5 py-4 text-sm ${project.is_overdue ? "font-semibold text-danger" : "text-muted"}`}><span className="inline-flex items-center gap-2">{project.is_overdue ? <AlertTriangle className="size-4" /> : <CalendarDays className="size-4 text-muted" />}{new Date(`${project.due_date}T12:00:00`).toLocaleDateString("pt-BR")}</span></td><td className="px-5 py-4"><span className={`state ${project.status === "active" ? "state--1" : project.status === "completed" ? "state--off" : "state--2"}`}>{statusLabel[project.status] || project.status}</span></td>{showArchived && <td className="px-5 py-4"><button className="btn btn--secondary" disabled={restoring === project.id} onClick={() => void restore(project.id)}><RotateCcw className="size-4" />{restoring === project.id ? "Restaurando…" : "Restaurar"}</button></td>}</tr>)}</tbody></table></div> : <div className="empty-state grid min-h-72 place-items-center"><div><span className="metric-icon mx-auto size-12 rounded-2xl"><FolderKanban className="size-5" /></span><h3 className="mt-4 font-semibold text-ink">{showArchived ? "Nada arquivado" : isDelivery ? "Você ainda não participa de nenhum projeto" : "Nenhum projeto em andamento"}</h3><p className="mt-1 max-w-sm text-sm text-muted">{showArchived ? "Projetos arquivados aparecem aqui e podem voltar ao acompanhamento." : isDelivery ? "Peça a um administrador para incluir você na equipe do projeto." : "Quando uma oportunidade for ganha, você poderá transformá-la em projeto."}</p></div></div>}</section>
  </section>;
}
