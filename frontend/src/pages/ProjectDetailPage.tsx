import { AlertTriangle, ArrowLeft, Bot, UsersRound, CalendarDays, CalendarPlus, CheckCircle2, ChevronRight, Circle, ExternalLink, Flag, Gauge, Inbox, ListTodo, Lock, MapPin, Pencil, Plus, Save, Sparkles, Trophy, Video, X } from "lucide-react";
import { type FormEvent, type ReactNode, useCallback, useEffect, useState } from "react";

import { api, listUsers } from "../api";
import { useAuth } from "../auth";
import { ArtifactsPanel } from "../components/ArtifactsPanel";
import { HealthBadge } from "../components/StatusDot";
import type { DigitalEmployee, DigitalEmployeeStatus, HealthAssessment, Meeting, Milestone, Party, Pendencia, Project, ProjectMember, ProjectPhase, RiskAssessment, Service, SessionUser, Task, WorkItemStatus } from "../types";

const money = new Intl.NumberFormat("pt-BR", { style: "currency", currency: "BRL", maximumFractionDigits: 0 });
const roleLabel: Record<string, string> = { admin: "Administrador", sales: "Vendas", delivery: "Entrega" };
const projectStatusLabel: Record<string, string> = { planning: "Planejamento", active: "Ativo", on_hold: "Em espera", completed: "Concluído" };
const workStatusLabel: Record<WorkItemStatus, string> = { todo: "A fazer", in_progress: "Em andamento", done: "Concluído" };
const partyLabel: Record<Party, string> = { provider: "Fornecedor", client: "Cliente" };

function formatDate(value: string): string { return new Date(`${value}T12:00:00`).toLocaleDateString("pt-BR"); }

export function ProjectDetailPage({ id }: { id: number }) {
  const { aiEnabled, calendarEnabled, user } = useAuth();
  const canManageJourney = !!user && (user.role === "admin" || user.role === "delivery");
  const [aiQuestion, setAiQuestion] = useState("");
  const [aiAnswer, setAiAnswer] = useState("");
  const [aiLoading, setAiLoading] = useState(false);
  const [artifactsToken, setArtifactsToken] = useState(0);
  const [project, setProject] = useState<Project>();
  const [milestones, setMilestones] = useState<Milestone[]>([]);
  const [tasks, setTasks] = useState<Task[]>([]);
  const [meetings, setMeetings] = useState<Meeting[]>([]);
  const [pendencias, setPendencias] = useState<Pendencia[]>([]);
  const [phases, setPhases] = useState<ProjectPhase[]>([]);
  const [error, setError] = useState("");
  const [milestoneDraft, setMilestoneDraft] = useState({ title: "", due_date: "" });
  const [taskDraft, setTaskDraft] = useState({ title: "", due_date: "", milestone: "" });
  const [meetingDraft, setMeetingDraft] = useState({ title: "", date: "", recording_url: "", transcript: "" });
  const [pendenciaDraft, setPendenciaDraft] = useState<{ title: string; party: Party }>({ title: "", party: "provider" });
  const [services, setServices] = useState<Service[]>([]);
  const [risk, setRisk] = useState<RiskAssessment>();
  const [health, setHealth] = useState<HealthAssessment>();
  const [employees, setEmployees] = useState<DigitalEmployee[]>([]);
  const [members, setMembers] = useState<ProjectMember[]>([]);
  const [people, setPeople] = useState<SessionUser[]>([]);
  const [memberDraft, setMemberDraft] = useState("");
  const [employeeDraft, setEmployeeDraft] = useState({ name: "", area: "", status: "building" as DigitalEmployeeStatus });
  const [editing, setEditing] = useState(false);
  const [editDraft, setEditDraft] = useState({ name: "", description: "", status: "", start_date: "", due_date: "", service: "", actual_value: "", cost: "" });

  const load = useCallback(() => Promise.all([
    api<Project>(`/projects/${id}/`),
    api<Milestone[]>(`/milestones/?project=${id}`),
    api<Task[]>(`/tasks/?project=${id}`),
    api<Service[]>("/services/"),
    api<RiskAssessment>(`/projects/${id}/risk/`),
    api<Meeting[]>(`/meetings/?project=${id}`),
    api<Pendencia[]>(`/pendencias/?project=${id}`),
    api<ProjectPhase[]>(`/project-phases/?project=${id}`),
    api<HealthAssessment>(`/projects/${id}/health/`),
    api<DigitalEmployee[]>(`/digital-employees/?project=${id}`),
    api<ProjectMember[]>(`/project-members/?project=${id}`),
  ]).then(([loadedProject, loadedMilestones, loadedTasks, loadedServices, loadedRisk, loadedMeetings, loadedPendencias, loadedPhases, loadedHealth, loadedEmployees, loadedMembers]) => {
    setProject(loadedProject); setMilestones(loadedMilestones); setTasks(loadedTasks); setServices(loadedServices); setRisk(loadedRisk); setMeetings(loadedMeetings); setPendencias(loadedPendencias); setPhases(loadedPhases); setHealth(loadedHealth); setEmployees(loadedEmployees); setMembers(loadedMembers);
  }).catch((cause: Error) => setError(cause.message)), [id]);
  useEffect(() => { void load(); }, [load]);

  async function advancePhase() {
    try { const updated = await api<ProjectPhase[]>(`/projects/${id}/advance-phase/`, { method: "POST" }); setPhases(updated); }
    catch (cause) { setError((cause as Error).message); }
  }
  async function refreshPhases() {
    try { setPhases(await api<ProjectPhase[]>(`/project-phases/?project=${id}`)); }
    catch (cause) { setError((cause as Error).message); }
  }
  async function markDeliverable(deliverableId: number) {
    try { await api(`/project-deliverables/${deliverableId}/`, { method: "PATCH", body: JSON.stringify({ status: "delivered" }) }); await refreshPhases(); }
    catch (cause) { setError((cause as Error).message); }
  }
  async function setPhaseTarget(phaseId: number, date: string) {
    try { await api(`/project-phases/${phaseId}/`, { method: "PATCH", body: JSON.stringify({ target_date: date || null }) }); await refreshPhases(); }
    catch (cause) { setError((cause as Error).message); }
  }

  async function createMilestone(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    try { await api("/milestones/", { method: "POST", body: JSON.stringify({ project: id, ...milestoneDraft }) }); setMilestoneDraft({ title: "", due_date: "" }); await load(); }
    catch (cause) { setError((cause as Error).message); }
  }
  async function createTask(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    try { await api("/tasks/", { method: "POST", body: JSON.stringify({ project: id, title: taskDraft.title, due_date: taskDraft.due_date, milestone: taskDraft.milestone ? Number(taskDraft.milestone) : null }) }); setTaskDraft({ title: "", due_date: "", milestone: "" }); await load(); }
    catch (cause) { setError((cause as Error).message); }
  }
  async function complete(resource: "milestones" | "tasks", itemId: number) {
    try { await api(`/${resource}/${itemId}/`, { method: "PATCH", body: JSON.stringify({ status: "done" }) }); await load(); }
    catch (cause) { setError((cause as Error).message); }
  }
  async function createMeeting(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    try { await api("/meetings/", { method: "POST", body: JSON.stringify({ project: id, ...meetingDraft }) }); setMeetingDraft({ title: "", date: "", recording_url: "", transcript: "" }); await load(); }
    catch (cause) { setError((cause as Error).message); }
  }
  async function runMeetingAi(meeting: Meeting, kind: "discovery" | "assessment") {
    setAiLoading(true);
    // O texto agora fica registrado como artefato (FDD 016) em vez de sumir ao recarregar.
    try { await api(`/meetings/${meeting.id}/${kind}/`, { method: "POST" }); setArtifactsToken(token => token + 1); }
    catch (cause) { setError((cause as Error).message); } finally { setAiLoading(false); }
  }
  async function runAiScore(meeting: Meeting) {
    setAiLoading(true);
    try { await api(`/meetings/${meeting.id}/ai-score/`, { method: "POST" }); await load(); }
    catch (cause) { setError((cause as Error).message); } finally { setAiLoading(false); }
  }
  async function toggleAiScorePublish(next: boolean) {
    try { await api(`/projects/${id}/`, { method: "PATCH", body: JSON.stringify({ ai_score_reviewed: next }) }); await load(); }
    catch (cause) { setError((cause as Error).message); }
  }
  async function createPendencia(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    try { await api("/pendencias/", { method: "POST", body: JSON.stringify({ project: id, ...pendenciaDraft }) }); setPendenciaDraft({ title: "", party: "provider" }); await load(); }
    catch (cause) { setError((cause as Error).message); }
  }
  async function createEmployee(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    try { await api("/digital-employees/", { method: "POST", body: JSON.stringify({ project: id, ...employeeDraft }) }); setEmployeeDraft({ name: "", area: "", status: "building" }); await load(); }
    catch (cause) { setError((cause as Error).message); }
  }
  // Só admin monta equipe (RFC 0003), e `/users/` também é admin-only — por isso a lista de
  // pessoas só é buscada quando há como usá-la.
  const canManageTeam = user?.role === "admin";
  useEffect(() => {
    if (!canManageTeam) return;
    void listUsers().then(setPeople).catch(() => setPeople([]));
  }, [canManageTeam]);

  async function addMember(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!memberDraft) return;
    try { await api("/project-members/", { method: "POST", body: JSON.stringify({ project: id, user: Number(memberDraft) }) }); setMemberDraft(""); await load(); }
    catch (cause) { setError((cause as Error).message); }
  }
  async function removeMember(memberId: number) {
    try { await api(`/project-members/${memberId}/`, { method: "DELETE" }); await load(); }
    catch (cause) { setError((cause as Error).message); }
  }
  async function resolvePendencia(pendenciaId: number) {
    try { await api(`/pendencias/${pendenciaId}/`, { method: "PATCH", body: JSON.stringify({ status: "resolved" }) }); await load(); }
    catch (cause) { setError((cause as Error).message); }
  }
  async function addToCalendar(resource: "milestones" | "tasks", itemId: number) {
    try { await api(`/${resource}/${itemId}/add-to-calendar/`, { method: "POST" }); }
    catch (cause) { setError((cause as Error).message); }
  }
  function openEdit() {
    if (!project) return;
    setEditDraft({ name: project.name, description: project.description, status: project.status, start_date: project.start_date, due_date: project.due_date, service: project.service ? String(project.service) : "", actual_value: project.actual_value, cost: project.cost });
    setEditing(true);
  }
  async function askAssistant(event: FormEvent<HTMLFormElement>) {
    event.preventDefault(); if (!aiQuestion.trim()) return;
    setAiLoading(true); setAiAnswer("");
    try { const result = await api<{ text: string }>(`/projects/${id}/assistant/`, { method: "POST", body: JSON.stringify({ question: aiQuestion }) }); setAiAnswer(result.text); }
    catch (cause) { setError((cause as Error).message); } finally { setAiLoading(false); }
  }
  async function summarize() {
    setAiLoading(true); setAiAnswer("");
    try { const result = await api<{ text: string }>(`/projects/${id}/summary/`, { method: "POST" }); setAiAnswer(result.text); }
    catch (cause) { setError((cause as Error).message); } finally { setAiLoading(false); }
  }
  async function suggestNextSteps() {
    setAiLoading(true); setAiAnswer("");
    try { const result = await api<{ text: string }>(`/projects/${id}/next-steps/`, { method: "POST" }); setAiAnswer(result.text); }
    catch (cause) { setError((cause as Error).message); } finally { setAiLoading(false); }
  }
  async function saveProject(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    try {
      await api(`/projects/${id}/`, { method: "PATCH", body: JSON.stringify({
        name: editDraft.name, description: editDraft.description, status: editDraft.status,
        start_date: editDraft.start_date, due_date: editDraft.due_date,
        service: editDraft.service ? Number(editDraft.service) : null,
        actual_value: editDraft.actual_value || "0", cost: editDraft.cost || "0",
      }) });
      setEditing(false); await load();
    } catch (cause) { setError((cause as Error).message); }
  }

  if (error && !project) return <div role="alert" className="rounded-2xl border border-red-100 bg-red-50 p-4 text-sm text-signal">{error}</div>;
  if (!project) return <div className="animate-pulse space-y-6"><div className="h-10 w-64 rounded-xl bg-slate-200" /><div className="h-56 rounded-2xl bg-white" /></div>;

  return <section className="space-y-7">
    <a href="/projetos" className="inline-flex items-center gap-2 text-sm font-semibold text-ocean hover:text-ink"><ArrowLeft className="size-4" />Voltar para projetos</a>
    <header className="flex flex-col justify-between gap-4 sm:flex-row sm:items-end"><div><p className="text-sm font-semibold text-ocean">Entrega</p><h1 className="mt-1 text-3xl font-semibold tracking-tight text-ink">{project.name}</h1><p className="mt-2 flex items-center gap-2 text-sm text-slate-600"><CalendarDays className="size-4" />{formatDate(project.start_date)} — {formatDate(project.due_date)}</p></div><div className="flex items-center gap-3 self-start"><span className={`rounded-full px-3 py-1.5 text-sm font-semibold ${project.status === "active" ? "bg-emerald-50 text-emerald-700" : project.status === "completed" ? "bg-slate-100 text-slate-600" : "bg-amber-50 text-amber-700"}`}>{projectStatusLabel[project.status] || project.status}</span><button className="inline-flex items-center gap-2 rounded-xl border bg-white px-3 py-2 text-sm font-semibold text-ink hover:border-ocean" onClick={openEdit}><Pencil className="size-4 text-ocean" />Editar</button></div></header>
    {error && <p role="alert" className="rounded-xl bg-red-50 p-3 text-sm text-signal">{error}</p>}
    {editing && <form className="grid gap-4 rounded-2xl border bg-white p-5 sm:p-6" onSubmit={event => void saveProject(event)}>
      <div className="flex items-center justify-between"><h2 className="font-semibold text-ink">Editar projeto</h2><button type="button" className="grid size-8 place-items-center rounded-lg text-slate-600 hover:bg-slate-100" aria-label="Cancelar edição" onClick={() => setEditing(false)}><X className="size-4" /></button></div>
      <label className="grid gap-2 text-sm font-medium text-slate-700">Nome<input className="field" value={editDraft.name} onChange={event => setEditDraft({ ...editDraft, name: event.target.value })} required /></label>
      <label className="grid gap-2 text-sm font-medium text-slate-700">Descrição<textarea className="field min-h-20" value={editDraft.description} onChange={event => setEditDraft({ ...editDraft, description: event.target.value })} placeholder="Contexto e objetivo do projeto" /></label>
      <div className="grid gap-4 sm:grid-cols-3">
        <label className="grid gap-2 text-sm font-medium text-slate-700">Status<select className="field" aria-label="Status do projeto" value={editDraft.status} onChange={event => setEditDraft({ ...editDraft, status: event.target.value })}>{Object.entries(projectStatusLabel).map(([value, label]) => <option key={value} value={value}>{label}</option>)}</select></label>
        <label className="grid gap-2 text-sm font-medium text-slate-700">Início<input className="field" type="date" value={editDraft.start_date} onChange={event => setEditDraft({ ...editDraft, start_date: event.target.value })} required /></label>
        <label className="grid gap-2 text-sm font-medium text-slate-700">Prazo final<input className="field" type="date" value={editDraft.due_date} onChange={event => setEditDraft({ ...editDraft, due_date: event.target.value })} required /></label>
      </div>
      <div className="grid gap-4 sm:grid-cols-3">
        <label className="grid gap-2 text-sm font-medium text-slate-700">Serviço<select className="field" aria-label="Serviço do projeto" value={editDraft.service} onChange={event => setEditDraft({ ...editDraft, service: event.target.value })}><option value="">Sem serviço</option>{services.map(service => <option key={service.id} value={service.id}>{service.name}</option>)}</select></label>
        <label className="grid gap-2 text-sm font-medium text-slate-700">Receita realizada<input className="field" type="number" min="0" step="0.01" value={editDraft.actual_value} onChange={event => setEditDraft({ ...editDraft, actual_value: event.target.value })} placeholder="0,00" /></label>
        <label className="grid gap-2 text-sm font-medium text-slate-700">Custo<input className="field" type="number" min="0" step="0.01" value={editDraft.cost} onChange={event => setEditDraft({ ...editDraft, cost: event.target.value })} placeholder="0,00" /></label>
      </div>
      <button className="inline-flex items-center gap-2 self-start rounded-xl bg-ocean px-4 py-3 text-sm font-semibold text-white hover:bg-ink" type="submit"><Save className="size-4" />Salvar projeto</button>
    </form>}

    <JourneySection phases={phases} canManage={canManageJourney} onAdvance={() => void advancePhase()} onMark={id => void markDeliverable(id)} onSetTarget={(phaseId, date) => void setPhaseTarget(phaseId, date)} />

    {health && <div className="flex items-center gap-2 text-sm"><span className="font-medium text-slate-600">Saúde do projeto:</span><HealthBadge level={health.level} score={health.score} />{health.signals.length === 0 && <span className="text-slate-600">sem sinais de alerta</span>}</div>}

    {project?.ai_scored_at && <AiScorePanel project={project} canManage={canManageJourney} onTogglePublish={next => void toggleAiScorePublish(next)} />}

    <section className="rounded-2xl border bg-white p-5 sm:p-6">
      <div className="flex items-center gap-3"><span className="grid size-9 place-items-center rounded-xl bg-mint text-ocean"><UsersRound className="size-4" /></span><div><h2 className="font-semibold text-ink">Equipe do projeto</h2><p className="text-sm text-slate-600">Quem participa é quem enxerga este projeto e tudo o que pende dele.</p></div></div>
      {members.length ? <ul className="mt-4 divide-y rounded-xl border">{members.map(member => <li className="flex items-center gap-3 px-4 py-3" key={member.id}>
        <span className="grid size-8 shrink-0 place-items-center rounded-lg bg-mint text-xs font-bold text-ocean">{(member.user_name || member.user_username).slice(0, 2).toUpperCase()}</span>
        <div className="min-w-0 flex-1"><p className="truncate text-sm font-semibold text-ink">{member.user_name || member.user_username}</p><p className="text-xs text-slate-600">{roleLabel[member.user_role] ?? member.user_role}</p></div>
        {canManageTeam && <button className="shrink-0 rounded-lg p-2 text-slate-600 hover:bg-red-50 hover:text-signal" aria-label={`Remover ${member.user_name || member.user_username} da equipe`} onClick={() => void removeMember(member.id)}><X className="size-4" /></button>}
      </li>)}</ul> : <p className="mt-4 rounded-xl border border-dashed bg-slate-50/60 px-4 py-6 text-center text-sm text-slate-600">Ninguém na equipe ainda — o projeto está invisível para a Entrega.</p>}
      {canManageTeam && <form className="mt-4 flex flex-wrap gap-2" onSubmit={event => void addMember(event)}>
        <select className="field flex-1" value={memberDraft} onChange={event => setMemberDraft(event.target.value)} aria-label="Pessoa a adicionar" required>
          <option value="">Selecione uma pessoa</option>
          {people.filter(person => !members.some(member => member.user === person.id)).map(person => <option key={person.id} value={person.id}>{person.first_name || person.username} — {roleLabel[person.role] ?? person.role}</option>)}
        </select>
        <button className="grid size-11 shrink-0 place-items-center rounded-xl bg-ocean text-white hover:bg-ink" aria-label="Adicionar à equipe" type="submit"><Plus className="size-4" /></button>
      </form>}
    </section>

    <section className="rounded-2xl border bg-white p-5 sm:p-6">
      <div className="flex items-center gap-3"><span className="grid size-9 place-items-center rounded-xl bg-mint text-ocean"><Bot className="size-4" /></span><div><h2 className="font-semibold text-ink">Funcionários Digitais</h2><p className="text-sm text-slate-600">Os agentes de IA entregues neste projeto.</p></div></div>
      {employees.length ? <div className="mt-4 grid gap-3 sm:grid-cols-2">{employees.map(employee => <article className="rounded-xl border bg-slate-50/50 p-4" key={employee.id}>
        <div className="flex items-center justify-between gap-2"><p className="text-sm font-semibold text-ink">{employee.name}</p><span className={`rounded-full px-2 py-0.5 text-xs font-semibold ${employee.status === "active" ? "bg-emerald-50 text-emerald-700" : employee.status === "paused" ? "bg-slate-100 text-slate-600" : "bg-amber-50 text-amber-700"}`}>{employee.status === "active" ? "Ativo" : employee.status === "paused" ? "Pausado" : "Em construção"}</span></div>
        {employee.area && <p className="mt-0.5 text-xs text-ocean">{employee.area}</p>}
        {employee.description && <p className="mt-1 text-xs text-slate-600">{employee.description}</p>}
        <div className="mt-2 flex flex-wrap gap-x-4 gap-y-1 text-xs text-slate-600">{employee.kpi_label && <span><strong className="text-ink">{employee.kpi_label}:</strong> {employee.kpi_value}</span>}{Number(employee.hours_saved_month) > 0 && <span>{Number(employee.hours_saved_month)}h/mês</span>}{Number(employee.roi_month) > 0 && <span>ROI {money.format(Number(employee.roi_month))}/mês</span>}</div>
      </article>)}</div> : <p className="mt-4 rounded-xl border border-dashed bg-slate-50/60 px-4 py-6 text-center text-sm text-slate-600">Nenhum funcionário digital ainda.</p>}
      {canManageJourney && <form className="mt-4 flex flex-wrap gap-2" onSubmit={event => void createEmployee(event)}>
        <input className="field flex-1" placeholder="Nome (ex.: Agente Financeiro)" value={employeeDraft.name} onChange={event => setEmployeeDraft({ ...employeeDraft, name: event.target.value })} required />
        <input className="field w-40" placeholder="Área" value={employeeDraft.area} onChange={event => setEmployeeDraft({ ...employeeDraft, area: event.target.value })} />
        <button className="grid size-11 shrink-0 place-items-center rounded-xl bg-ocean text-white hover:bg-ink" aria-label="Adicionar funcionário digital" type="submit"><Plus className="size-4" /></button>
      </form>}
    </section>

    {risk && risk.signals.length > 0 && <section className="rounded-2xl border bg-white p-5 sm:p-6">
      <div className="flex items-center gap-3"><span className={`rounded-full px-3 py-1 text-sm font-semibold ${risk.level === "alto" ? "bg-red-50 text-signal" : risk.level === "médio" ? "bg-amber-50 text-amber-700" : "bg-emerald-50 text-emerald-700"}`}>Risco {risk.level}</span><h2 className="font-semibold text-ink">Sinais de atraso</h2></div>
      <ul className="mt-3 space-y-1.5 text-sm text-slate-600">{risk.signals.map((signal, index) => <li className="flex gap-2" key={index}><AlertTriangle className="mt-0.5 size-4 shrink-0 text-signal" /><span><strong className="text-ink">{signal.label}:</strong> {signal.detail}</span></li>)}</ul>
      {risk.forecast && <p className={`mt-3 text-sm font-medium ${risk.forecast.delay_days > 0 ? "text-signal" : "text-slate-600"}`}>Previsão de término: {formatDate(risk.forecast.predicted_finish_date)}{risk.forecast.delay_days > 0 ? ` — atraso previsto de ${risk.forecast.delay_days} dia(s)` : " — dentro do prazo"} <span className="text-slate-600">({risk.forecast.basis})</span></p>}
    </section>}

    {aiEnabled && <section className="rounded-2xl border bg-white p-5 sm:p-6">
      <div className="flex flex-wrap items-center gap-3"><span className="grid size-9 place-items-center rounded-xl bg-mint text-ocean"><Sparkles className="size-4" /></span><div><h2 className="font-semibold text-ink">Assistente do projeto</h2><p className="text-sm text-slate-600">Pergunte sobre marcos, tarefas e prazos deste projeto.</p></div><button type="button" className="ml-auto rounded-xl border px-3 py-2 text-sm font-semibold text-ink hover:border-ocean disabled:opacity-60" onClick={() => void suggestNextSteps()} disabled={aiLoading}>Sugerir próximos passos</button><button type="button" className="rounded-xl border px-3 py-2 text-sm font-semibold text-ink hover:border-ocean disabled:opacity-60" onClick={() => void summarize()} disabled={aiLoading}>Resumir projeto</button></div>
      <form className="mt-4 flex gap-2" onSubmit={event => void askAssistant(event)}><input className="field" value={aiQuestion} onChange={event => setAiQuestion(event.target.value)} placeholder="Ex.: quais tarefas estão atrasadas?" aria-label="Pergunta ao assistente" /><button className="shrink-0 rounded-xl bg-ocean px-4 py-2 text-sm font-semibold text-white hover:bg-ink disabled:opacity-60" type="submit" disabled={aiLoading}>{aiLoading ? "…" : "Perguntar"}</button></form>
      {aiAnswer && <p className="mt-4 whitespace-pre-wrap rounded-xl bg-slate-50 p-4 text-sm text-slate-700">{aiAnswer}</p>}
    </section>}

    <div className="grid gap-5 lg:grid-cols-2">
      <WorkColumn icon={<Flag className="size-4" />} title="Marcos" count={milestones.length}>
        <form className="grid gap-3 sm:grid-cols-[1fr_auto]" onSubmit={event => void createMilestone(event)}>
          <input className="field" placeholder="Novo marco" value={milestoneDraft.title} onChange={event => setMilestoneDraft({ ...milestoneDraft, title: event.target.value })} required />
          <div className="flex gap-2"><input className="field min-w-0 flex-1" type="date" aria-label="Prazo do marco" value={milestoneDraft.due_date} onChange={event => setMilestoneDraft({ ...milestoneDraft, due_date: event.target.value })} required /><button className="grid size-11 shrink-0 place-items-center rounded-xl bg-ocean text-white hover:bg-ink" aria-label="Adicionar marco" type="submit"><Plus className="size-4" /></button></div>
        </form>
        <WorkList items={milestones} onComplete={itemId => void complete("milestones", itemId)} onCalendar={calendarEnabled ? itemId => void addToCalendar("milestones", itemId) : undefined} emptyLabel="Nenhum marco cadastrado." />
      </WorkColumn>

      <WorkColumn icon={<ListTodo className="size-4" />} title="Tarefas" count={tasks.length}>
        <form className="grid gap-3" onSubmit={event => void createTask(event)}>
          <input className="field" placeholder="Nova tarefa" value={taskDraft.title} onChange={event => setTaskDraft({ ...taskDraft, title: event.target.value })} required />
          <div className="flex gap-2"><input className="field min-w-0 flex-1" type="date" aria-label="Prazo da tarefa" value={taskDraft.due_date} onChange={event => setTaskDraft({ ...taskDraft, due_date: event.target.value })} required /><select className="field min-w-0 flex-1" aria-label="Marco da tarefa" value={taskDraft.milestone} onChange={event => setTaskDraft({ ...taskDraft, milestone: event.target.value })}><option value="">Sem marco</option>{milestones.map(milestone => <option key={milestone.id} value={milestone.id}>{milestone.title}</option>)}</select><button className="grid size-11 shrink-0 place-items-center rounded-xl bg-ocean text-white hover:bg-ink" aria-label="Adicionar tarefa" type="submit"><Plus className="size-4" /></button></div>
        </form>
        <WorkList items={tasks} onComplete={itemId => void complete("tasks", itemId)} onCalendar={calendarEnabled ? itemId => void addToCalendar("tasks", itemId) : undefined} emptyLabel="Nenhuma tarefa cadastrada." />
      </WorkColumn>
    </div>

    <div className="grid gap-5 lg:grid-cols-2">
      <WorkColumn icon={<Video className="size-4" />} title="Reuniões" count={meetings.length}>
        <form className="grid gap-3" onSubmit={event => void createMeeting(event)}>
          <input className="field" placeholder="Título da reunião" value={meetingDraft.title} onChange={event => setMeetingDraft({ ...meetingDraft, title: event.target.value })} required />
          <div className="flex gap-2"><input className="field min-w-0 flex-1" type="date" aria-label="Data da reunião" value={meetingDraft.date} onChange={event => setMeetingDraft({ ...meetingDraft, date: event.target.value })} required /><input className="field min-w-0 flex-1" type="url" placeholder="Link da gravação (opcional)" value={meetingDraft.recording_url} onChange={event => setMeetingDraft({ ...meetingDraft, recording_url: event.target.value })} /><button className="grid size-11 shrink-0 place-items-center rounded-xl bg-ocean text-white hover:bg-ink" aria-label="Adicionar reunião" type="submit"><Plus className="size-4" /></button></div>
          <textarea className="field min-h-20" placeholder="Transcrição da reunião (para Discovery/Assessment por IA)" value={meetingDraft.transcript} onChange={event => setMeetingDraft({ ...meetingDraft, transcript: event.target.value })} />
        </form>
        {meetings.length ? <div className="divide-y">{meetings.map(meeting => <div className="py-3" key={meeting.id}>
          <div className="flex items-center gap-3">
            <span className="grid size-9 shrink-0 place-items-center rounded-xl bg-slate-100 text-slate-600"><Video className="size-4" /></span>
            <div className="min-w-0 flex-1"><p className="truncate text-sm font-medium text-ink">{meeting.title}</p><p className="mt-0.5 text-xs text-slate-600">{formatDate(meeting.date)}</p></div>
            {meeting.recording_url && <a className="shrink-0 rounded-lg p-1.5 text-slate-600 hover:text-ocean" href={meeting.recording_url} target="_blank" rel="noreferrer" aria-label={`Abrir gravação de ${meeting.title}`}><ExternalLink className="size-4" /></a>}
            <span className={`shrink-0 rounded-full px-2.5 py-1 text-xs font-semibold ${meeting.status === "held" ? "bg-emerald-50 text-emerald-700" : "bg-slate-100 text-slate-600"}`}>{meeting.status === "held" ? "Realizada" : "Agendada"}</span>
          </div>
          {aiEnabled && meeting.transcript.trim() && <div className="mt-2 flex gap-2 pl-12">
            <button type="button" className="inline-flex items-center gap-1.5 rounded-lg border px-2.5 py-1.5 text-xs font-semibold text-ink hover:border-ocean disabled:opacity-60" disabled={aiLoading} onClick={() => void runMeetingAi(meeting, "discovery")}><Sparkles className="size-3.5 text-ocean" />Discovery</button>
            <button type="button" className="inline-flex items-center gap-1.5 rounded-lg border px-2.5 py-1.5 text-xs font-semibold text-ink hover:border-ocean disabled:opacity-60" disabled={aiLoading} onClick={() => void runMeetingAi(meeting, "assessment")}><Sparkles className="size-3.5 text-ocean" />Assessment</button>
            <button type="button" className="inline-flex items-center gap-1.5 rounded-lg border px-2.5 py-1.5 text-xs font-semibold text-ink hover:border-ocean disabled:opacity-60" disabled={aiLoading} onClick={() => void runAiScore(meeting)}><Gauge className="size-3.5 text-ocean" />AI Score</button>
          </div>}
        </div>)}</div> : <p className="rounded-xl border border-dashed bg-slate-50/60 px-4 py-6 text-center text-sm text-slate-600">Nenhuma reunião registrada.</p>}
        <ArtifactsPanel project={Number(id)} reloadToken={artifactsToken} />
      </WorkColumn>

      <WorkColumn icon={<Inbox className="size-4" />} title="Pendências" count={pendencias.length}>
        <form className="grid gap-3" onSubmit={event => void createPendencia(event)}>
          <input className="field" placeholder="Nova pendência" value={pendenciaDraft.title} onChange={event => setPendenciaDraft({ ...pendenciaDraft, title: event.target.value })} required />
          <div className="flex gap-2"><select className="field min-w-0 flex-1" aria-label="Responsável pela pendência" value={pendenciaDraft.party} onChange={event => setPendenciaDraft({ ...pendenciaDraft, party: event.target.value as Party })}><option value="provider">Fornecedor</option><option value="client">Cliente</option></select><button className="grid size-11 shrink-0 place-items-center rounded-xl bg-ocean text-white hover:bg-ink" aria-label="Adicionar pendência" type="submit"><Plus className="size-4" /></button></div>
        </form>
        {pendencias.length ? <div className="divide-y">{pendencias.map(pendencia => {
          const resolved = pendencia.status === "resolved";
          return <div className="flex items-center gap-3 py-3" key={pendencia.id}>
            <button className={`shrink-0 ${resolved ? "text-emerald-600" : "text-slate-300 hover:text-ocean"}`} aria-label={resolved ? "Resolvida" : "Resolver"} disabled={resolved} onClick={() => void resolvePendencia(pendencia.id)}>{resolved ? <CheckCircle2 className="size-5" /> : <Circle className="size-5" />}</button>
            <div className="min-w-0 flex-1"><p className={`truncate text-sm font-medium ${resolved ? "text-slate-600 line-through" : "text-ink"}`}>{pendencia.title}</p><p className="mt-0.5 text-xs text-slate-600">{partyLabel[pendencia.party]}</p></div>
            <span className={`shrink-0 rounded-full px-2.5 py-1 text-xs font-semibold ${resolved ? "bg-emerald-50 text-emerald-700" : "bg-amber-50 text-amber-700"}`}>{resolved ? "Resolvida" : "Aberta"}</span>
          </div>;
        })}</div> : <p className="rounded-xl border border-dashed bg-slate-50/60 px-4 py-6 text-center text-sm text-slate-600">Nenhuma pendência.</p>}
      </WorkColumn>
    </div>
  </section>;
}

function ScoreBar({ label, value, tone }: { label: string; value: number | null; tone: "ocean" | "mint" }) {
  const pct = value ?? 0;
  return <div>
    <div className="flex items-baseline justify-between text-sm"><span className="font-medium text-slate-600">{label}</span><span className="font-semibold text-ink">{value === null ? "—" : `${value}/100`}</span></div>
    <div className="mt-1 h-2 rounded-full bg-slate-100"><div className={`h-2 rounded-full transition-all ${tone === "ocean" ? "bg-ocean" : "bg-emerald-500"}`} style={{ width: `${pct}%` }} /></div>
  </div>;
}

function AiScorePanel({ project, canManage, onTogglePublish }: { project: Project; canManage: boolean; onTogglePublish: (next: boolean) => void }) {
  const published = project.ai_score_reviewed;
  return <section className="space-y-4 rounded-2xl border bg-white p-5 sm:p-6">
    <div className="flex flex-wrap items-center gap-3">
      <span className="grid size-9 place-items-center rounded-xl bg-mint text-ocean"><Gauge className="size-4" /></span>
      <div className="flex-1"><h2 className="font-semibold text-ink">AI Score</h2><p className="text-sm text-slate-600">Maturidade e oportunidade de IA a partir do Discovery/Assessment.</p></div>
      <span className={`rounded-full px-2.5 py-1 text-xs font-semibold ${published ? "bg-emerald-50 text-emerald-700" : "bg-amber-50 text-amber-700"}`}>{published ? "Publicado ao cliente" : "Rascunho — revisar"}</span>
    </div>
    <div className="grid gap-3 sm:grid-cols-2">
      <ScoreBar label="Maturidade" value={project.ai_maturity} tone="ocean" />
      <ScoreBar label="Oportunidade" value={project.ai_opportunity} tone="mint" />
    </div>
    {project.ai_dimensions.length > 0 && <div className="grid gap-2 sm:grid-cols-2">{project.ai_dimensions.map((dimension, index) => <ScoreBar key={index} label={dimension.label} value={dimension.score} tone="ocean" />)}</div>}
    {project.ai_score_summary && <p className="whitespace-pre-wrap rounded-xl bg-slate-50 p-4 text-sm text-slate-700">{project.ai_score_summary}</p>}
    {canManage && <label className="flex items-center gap-2 text-sm text-slate-600"><input type="checkbox" className="size-4 rounded border-slate-300 text-ocean" checked={published} onChange={event => onTogglePublish(event.target.checked)} />Publicar ao cliente (revisado)</label>}
  </section>;
}

function JourneySection({ phases, canManage, onAdvance, onMark, onSetTarget }: { phases: ProjectPhase[]; canManage: boolean; onAdvance: () => void; onMark: (id: number) => void; onSetTarget: (phaseId: number, date: string) => void }) {
  if (!phases.length) return null;
  const done = phases.filter(phase => phase.status === "done").length;
  const active = phases.find(phase => phase.status === "active");
  const next = active ? phases.find(phase => phase.phase_position > active.phase_position) : undefined;
  const pct = Math.round((done / phases.length) * 100);

  return <section className="space-y-5 rounded-2xl border bg-white p-5 sm:p-6">
    <div className="flex flex-wrap items-center gap-3">
      <span className="grid size-9 place-items-center rounded-xl bg-mint text-ocean"><MapPin className="size-4" /></span>
      <div className="flex-1"><h2 className="font-semibold text-ink">Jornada de Transformação</h2><p className="text-sm text-slate-600">{done} de {phases.length} fases concluídas</p></div>
      <span className="text-sm font-semibold text-ocean">{pct}%</span>
    </div>

    <div className="h-2 rounded-full bg-slate-100"><div className="h-2 rounded-full bg-ocean transition-all" style={{ width: `${pct}%` }} /></div>

    <div className="flex flex-wrap gap-2">{phases.map(phase => {
      const isDone = phase.status === "done"; const isActive = phase.status === "active";
      return <span key={phase.id} className={`inline-flex items-center gap-1.5 rounded-full px-3 py-1.5 text-xs font-semibold ${isDone ? "bg-emerald-50 text-emerald-700" : isActive ? "bg-ocean text-white" : "bg-slate-100 text-slate-600"}`}>{isDone ? <CheckCircle2 className="size-3.5" /> : isActive ? <MapPin className="size-3.5" /> : <Lock className="size-3.5" />}{phase.phase_name}</span>;
    })}</div>

    {active ? <div className="rounded-2xl border bg-slate-50/60 p-4 sm:p-5">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div className="min-w-0"><p className="text-xs font-semibold uppercase tracking-wide text-ocean">Você está aqui</p><h3 className="mt-0.5 text-lg font-semibold text-ink">{active.phase_name}</h3>{active.phase_description && <p className="mt-1 text-sm text-slate-600">{active.phase_description}</p>}</div>
        {next && <p className="shrink-0 text-right text-xs text-slate-600">Próxima<span className="mt-0.5 flex items-center gap-1 font-semibold text-slate-600"><ChevronRight className="size-3.5" />{next.phase_name}</span></p>}
      </div>

      {active.deliverables.length > 0 && <div className="mt-4">
        <p className="mb-1 text-xs font-semibold uppercase tracking-wide text-slate-600">Entregáveis · {active.deliverables.filter(item => item.status === "delivered").length}/{active.deliverables.length}</p>
        <div className="divide-y">{active.deliverables.map(item => {
          const delivered = item.status === "delivered";
          return <div className="flex items-center gap-3 py-2.5" key={item.id}>
            <button className={`shrink-0 ${delivered ? "text-emerald-600" : canManage ? "text-slate-300 hover:text-ocean" : "text-slate-200"}`} aria-label={delivered ? `${item.name} entregue` : `Marcar ${item.name} como entregue`} disabled={delivered || !canManage} onClick={() => onMark(item.id)}>{delivered ? <CheckCircle2 className="size-5" /> : <Circle className="size-5" />}</button>
            <span className={`flex-1 text-sm font-medium ${delivered ? "text-slate-600 line-through" : "text-ink"}`}>{item.name}</span>
          </div>;
        })}</div>
      </div>}

      <div className="mt-4 flex flex-wrap items-end justify-between gap-3">
        {canManage ? <label className="grid gap-1 text-xs font-medium text-slate-600">Previsão desta fase<input className="field w-44" type="date" value={active.target_date ?? ""} onChange={event => onSetTarget(active.id, event.target.value)} /></label> : active.target_date ? <p className="text-sm text-slate-600">Previsão: {formatDate(active.target_date)}</p> : <span />}
        {canManage && <button type="button" className="inline-flex items-center gap-2 rounded-xl bg-ocean px-4 py-2.5 text-sm font-semibold text-white hover:bg-ink" onClick={onAdvance}><CheckCircle2 className="size-4" />Concluir fase e avançar</button>}
      </div>
    </div> : <div className="flex items-center gap-3 rounded-2xl border border-emerald-100 bg-emerald-50 p-4 text-sm font-medium text-emerald-700"><Trophy className="size-5 shrink-0" />Jornada de transformação concluída — todas as fases entregues.</div>}
  </section>;
}

function WorkColumn({ icon, title, count, children }: { icon: ReactNode; title: string; count: number; children: ReactNode }) {
  // `min-w-0`: item de grade nasce com `min-width: auto` e se recusa a encolher abaixo do
  // conteúdo — no celular a coluna estourava a trilha e a página inteira rolava na horizontal.
  return <section className="min-w-0 space-y-4 rounded-2xl border bg-white p-5 sm:p-6"><div className="flex items-center gap-3"><span className="grid size-9 place-items-center rounded-xl bg-mint text-ocean">{icon}</span><div><h2 className="font-semibold text-ink">{title}</h2><p className="text-sm text-slate-600">{count} {count === 1 ? "item" : "itens"}</p></div></div>{children}</section>;
}

function WorkList({ items, onComplete, onCalendar, emptyLabel }: { items: (Milestone | Task)[]; onComplete: (id: number) => void; onCalendar?: (id: number) => void; emptyLabel: string }) {
  if (!items.length) return <p className="rounded-xl border border-dashed bg-slate-50/60 px-4 py-6 text-center text-sm text-slate-600">{emptyLabel}</p>;
  return <div className="divide-y">{items.map(item => {
    const done = item.status === "done";
    return <div className="flex items-center gap-3 py-3" key={item.id}>
      <button className={`shrink-0 ${done ? "text-emerald-600" : "text-slate-300 hover:text-ocean"}`} aria-label={done ? "Concluído" : "Concluir"} disabled={done} onClick={() => onComplete(item.id)}>{done ? <CheckCircle2 className="size-5" /> : <Circle className="size-5" />}</button>
      <div className="min-w-0 flex-1"><p className={`truncate text-sm font-medium ${done ? "text-slate-600 line-through" : "text-ink"}`}>{item.title}</p><p className={`mt-0.5 flex items-center gap-1.5 text-xs ${item.is_overdue ? "font-semibold text-signal" : "text-slate-600"}`}>{item.is_overdue && <AlertTriangle className="size-3.5" />}{formatDate(item.due_date)}</p></div>
      {onCalendar && <button className="shrink-0 rounded-lg p-1.5 text-slate-600 hover:text-ocean" aria-label={`Adicionar ${item.title} ao calendário`} onClick={() => onCalendar(item.id)}><CalendarPlus className="size-4" /></button>}
      <span className={`shrink-0 rounded-full px-2.5 py-1 text-xs font-semibold ${done ? "bg-emerald-50 text-emerald-700" : item.status === "in_progress" ? "bg-amber-50 text-amber-700" : "bg-slate-100 text-slate-600"}`}>{workStatusLabel[item.status]}</span>
    </div>;
  })}</div>;
}
