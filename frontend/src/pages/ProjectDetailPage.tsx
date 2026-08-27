import { AlertTriangle, ArrowLeft, Bot, UsersRound, CalendarDays, CalendarPlus, CheckCircle2, ChevronRight, Circle, ExternalLink, Flag, Gauge, Inbox, ListTodo, Lock, MapPin, Pencil, Plus, Save, Scale, ShieldAlert, Sparkles, Trash2, Trophy, Video, Workflow, X } from "lucide-react";
import { type FormEvent, type ReactNode, useCallback, useEffect, useState } from "react";

import { api, listUsers } from "../api";
import { useAuth } from "../auth";
import { ArtifactsPanel } from "../components/ArtifactsPanel";
import { EngineeringPanel } from "../components/EngineeringPanel";
import { ConfirmDialog, Modal } from "../components/Modal";
import { GATE_LABEL, HealthBadge, gateBadgeClass } from "../components/StatusDot";
import { mensagemDeFalha } from "../erros";
import type { DigitalEmployee, DigitalEmployeeBlueprint, DigitalEmployeeStatus, GateOutcome, HealthAssessment, KpiDirection, KpiUnit, Meeting, Milestone, Party, Decisao, Pendencia, Project, ProjectMember, ProjectPhase, Risco, RiscoNivel, RiscoStatus, RiskAssessment, Service, SessionUser, Task, WorkItemStatus } from "../types";

const money = new Intl.NumberFormat("pt-BR", { style: "currency", currency: "BRL", maximumFractionDigits: 0 });
const roleLabel: Record<string, string> = { admin: "Administrador", sales: "Vendas", delivery: "Entrega" };
const projectStatusLabel: Record<string, string> = { planning: "Planejamento", active: "Ativo", on_hold: "Em espera", completed: "Concluído" };
const workStatusLabel: Record<WorkItemStatus, string> = { todo: "A fazer", in_progress: "Em andamento", done: "Concluído" };
const partyLabel: Record<Party, string> = { provider: "Fornecedor", client: "Cliente" };
const blankMeeting = { title: "", date: "", meeting_url: "", recording_url: "", transcript: "" };
const employeeStatusLabel: Record<DigitalEmployeeStatus, string> = { building: "Em construção", active: "Ativo", paused: "Pausado" };
// O mapa do gate subiu para `components/StatusDot.tsx` na FDD 042, ao lado dos de saúde,
// satisfação e sustentação: a escada FDE da conta exibe o **mesmo** selo, e duas telas lendo o
// mesmo valor é o que trouxe os outros três para lá. Aqui só se consome.
// Risk Register (FDD 034). "Aceito" é **neutro**, não verde: conviver com o risco é uma decisão
// consciente, e não um problema resolvido — a mesma leitura que faz "Arquivado" usar `state--off`.
const riscoNivelLabel: Record<RiscoNivel, { probabilidade: string; impacto: string }> = {
  low: { probabilidade: "Baixa", impacto: "Baixo" },
  medium: { probabilidade: "Média", impacto: "Médio" },
  high: { probabilidade: "Alta", impacto: "Alto" },
};
const riscoStatusLabel: Record<RiscoStatus, string> = { open: "Aberto", mitigated: "Mitigado", accepted: "Aceito", materialized: "Materializado" };
const riscoStatusVariant: Record<RiscoStatus, string> = { open: "state--2", mitigated: "state--1", accepted: "state--off", materialized: "state--3" };
const riscoNiveis: RiscoNivel[] = ["low", "medium", "high"];
const riscoStatuses: RiscoStatus[] = ["open", "mitigated", "accepted", "materialized"];
const blankEmployeeEdit = { name: "", area: "", status: "building" as DigitalEmployeeStatus, description: "", kpi_label: "", kpi_value: "", kpi_unit: "" as KpiUnit, kpi_direction: "up" as KpiDirection, kpi_baseline: "", kpi_current: "", hours_saved_month: "", roi_month: "" };
const kpiUnits: { value: KpiUnit; label: string }[] = [
  { value: "", label: "Sem unidade" }, { value: "percent", label: "Percentual (%)" },
  { value: "hours", label: "Horas" }, { value: "minutes", label: "Minutos" },
  { value: "currency", label: "Moeda (R$)" }, { value: "count", label: "Contagem" },
];

function formatDate(value: string): string { return new Date(`${value}T12:00:00`).toLocaleDateString("pt-BR"); }

export function ProjectDetailPage({ id }: { id: number }) {
  const { aiEnabled, calendarEnabled, user } = useAuth();
  const canManageJourney = !!user && (user.is_admin || user.role === "delivery");
  const [aiQuestion, setAiQuestion] = useState("");
  const [aiAnswer, setAiAnswer] = useState("");
  const [aiLoading, setAiLoading] = useState(false);
  const [artifactsToken, setArtifactsToken] = useState(0);
  const [archivingProject, setArchivingProject] = useState(false);
  const [archiveBusy, setArchiveBusy] = useState(false);
  const [project, setProject] = useState<Project>();
  const [milestones, setMilestones] = useState<Milestone[]>([]);
  const [tasks, setTasks] = useState<Task[]>([]);
  const [meetings, setMeetings] = useState<Meeting[]>([]);
  const [pendencias, setPendencias] = useState<Pendencia[]>([]);
  const [decisoes, setDecisoes] = useState<Decisao[]>([]);
  const [riscos, setRiscos] = useState<Risco[]>([]);
  const [archivingRisco, setArchivingRisco] = useState<Risco | null>(null);
  const [phases, setPhases] = useState<ProjectPhase[]>([]);
  const [error, setError] = useState("");
  // O que a extração acabou de mapear. Fica na tela porque o **resultado mora em outro lugar**: o
  // processo é ancorado no cliente (FDD 039), não no projeto, então sem esta linha o sucesso seria
  // silêncio — a pessoa clica, nada muda aqui, e não há como distinguir isso de uma falha.
  const [processosMapeados, setProcessosMapeados] = useState(0);
  const [milestoneDraft, setMilestoneDraft] = useState({ title: "", due_date: "" });
  const [taskDraft, setTaskDraft] = useState({ title: "", due_date: "", milestone: "" });
  const [meetingDraft, setMeetingDraft] = useState(blankMeeting);
  const [pendenciaDraft, setPendenciaDraft] = useState<{ title: string; party: Party }>({ title: "", party: "provider" });
  const [decisaoDraft, setDecisaoDraft] = useState({ title: "", rationale: "", decided_by: "" });
  const [riscoDraft, setRiscoDraft] = useState<{ title: string; probability: RiscoNivel; impact: RiscoNivel; mitigation: string }>({ title: "", probability: "medium", impact: "medium", mitigation: "" });
  const [services, setServices] = useState<Service[]>([]);
  const [risk, setRisk] = useState<RiskAssessment>();
  const [health, setHealth] = useState<HealthAssessment>();
  const [employees, setEmployees] = useState<DigitalEmployee[]>([]);
  const [members, setMembers] = useState<ProjectMember[]>([]);
  const [people, setPeople] = useState<SessionUser[]>([]);
  const [memberDraft, setMemberDraft] = useState("");
  const [employeeDraft, setEmployeeDraft] = useState({ name: "", area: "", status: "building" as DigitalEmployeeStatus });
  const [catalog, setCatalog] = useState<DigitalEmployeeBlueprint[]>([]);
  const [blueprintDraft, setBlueprintDraft] = useState("");
  const [baselineDraft, setBaselineDraft] = useState("");
  const [showArchivedEmployees, setShowArchivedEmployees] = useState(false);
  const [editingEmployee, setEditingEmployee] = useState<DigitalEmployee | null>(null);
  const [employeeEdit, setEmployeeEdit] = useState(blankEmployeeEdit);
  const [archivingEmployee, setArchivingEmployee] = useState<DigitalEmployee | null>(null);
  const [employeeBusy, setEmployeeBusy] = useState(false);
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
    api<Decisao[]>(`/decisoes/?project=${id}`),
    api<Risco[]>(`/riscos/?project=${id}`),
    api<ProjectPhase[]>(`/project-phases/?project=${id}`),
    api<HealthAssessment>(`/projects/${id}/health/`),
    api<ProjectMember[]>(`/project-members/?project=${id}`),
  ]).then(([loadedProject, loadedMilestones, loadedTasks, loadedServices, loadedRisk, loadedMeetings, loadedPendencias, loadedDecisoes, loadedRiscos, loadedPhases, loadedHealth, loadedMembers]) => {
    setProject(loadedProject); setMilestones(loadedMilestones); setTasks(loadedTasks); setServices(loadedServices); setRisk(loadedRisk); setMeetings(loadedMeetings); setPendencias(loadedPendencias); setDecisoes(loadedDecisoes); setRiscos(loadedRiscos); setPhases(loadedPhases); setHealth(loadedHealth); setMembers(loadedMembers);
  }).catch((cause: Error) => setError(cause.message)), [id]);
  useEffect(() => { void load(); }, [load]);

  // O roster tem carga própria porque o alternador de arquivados muda só a lista dele: pendurá-lo
  // no `load` faria cada clique refazer as dez chamadas da página inteira.
  const loadEmployees = useCallback(
    () => api<DigitalEmployee[]>(`/digital-employees/?project=${id}${showArchivedEmployees ? "&archived=1" : ""}`).then(setEmployees).catch((cause: Error) => setError(cause.message)),
    [id, showArchivedEmployees],
  );
  useEffect(() => { void loadEmployees(); }, [loadEmployees]);

  // O catálogo vem **resolvido** pela vertical do cliente: o que a lista mostra é o que a
  // instanciação vai copiar (FDD 026). Sem vertical, vêm os valores genéricos — e vem tudo, porque
  // filtrar por vertical esconderia justamente o bloco que serve a qualquer setor.
  const vertical = project?.client_vertical;
  useEffect(() => {
    if (!canManageJourney) return;
    const query = vertical ? `&vertical=${vertical}` : "";
    void api<DigitalEmployeeBlueprint[]>(`/digital-employee-blueprints/?active=1${query}`).then(setCatalog).catch(() => setCatalog([]));
  }, [vertical, canManageJourney]);

  // Os dois gates da FDD 033 recusam com **409 e mensagem** ("faltam 2 itens", "registre o
  // decision gate"): limpar o erro antes de tentar é o que faz a recusa anterior sumir quando ela
  // deixa de valer, em vez de acusar um bloqueio que já foi resolvido.
  async function advancePhase() {
    setError("");
    try { const updated = await api<ProjectPhase[]>(`/projects/${id}/advance-phase/`, { method: "POST" }); setPhases(updated); }
    catch (cause) { setError((cause as Error).message); }
  }
  async function applyGate(outcome: GateOutcome, notes: string) {
    setError("");
    try { const updated = await api<ProjectPhase[]>(`/projects/${id}/apply-gate/`, { method: "POST", body: JSON.stringify({ outcome, notes }) }); setPhases(updated); }
    catch (cause) { setError((cause as Error).message); }
  }
  async function toggleChecklistItem(itemId: number, checked: boolean) {
    setError("");
    try { await api(`/project-checklist-items/${itemId}/`, { method: "PATCH", body: JSON.stringify({ checked }) }); await refreshPhases(); }
    catch (cause) { setError((cause as Error).message); }
  }
  async function saveChecklistWaiver(phaseId: number, waiver: string) {
    setError("");
    try { await api(`/project-phases/${phaseId}/`, { method: "PATCH", body: JSON.stringify({ checklist_waiver: waiver }) }); await refreshPhases(); }
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
  // Alterna em vez de só concluir: marcar por engano acontece, e o modelo já sabe reabrir —
  // `WorkItem.save` limpa o `completed_at` quando o status sai de "done".
  async function toggleWorkItem(resource: "milestones" | "tasks", itemId: number, isDone: boolean) {
    try { await api(`/${resource}/${itemId}/`, { method: "PATCH", body: JSON.stringify({ status: isDone ? "todo" : "done" }) }); await load(); }
    catch (cause) { setError((cause as Error).message); }
  }
  async function createMeeting(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    try { await api("/meetings/", { method: "POST", body: JSON.stringify({ project: id, ...meetingDraft }) }); setMeetingDraft(blankMeeting); await load(); }
    catch (cause) { setError((cause as Error).message); }
  }
  async function toggleMeeting(meeting: Meeting) {
    try { await api(`/meetings/${meeting.id}/`, { method: "PATCH", body: JSON.stringify({ status: meeting.status === "held" ? "scheduled" : "held" }) }); await load(); }
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
  async function createDecisao(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    try { await api("/decisoes/", { method: "POST", body: JSON.stringify({ project: id, ...decisaoDraft }) }); setDecisaoDraft({ title: "", rationale: "", decided_by: "" }); await load(); }
    catch (cause) { setError((cause as Error).message); }
  }
  // Publicar é o que faz a decisão atravessar para o cliente: só `published` entra no snapshot
  // (FDD 032). Despublicar volta a escondê-la, e **não** apaga a data em que ela passou a valer.
  async function toggleDecisao(decisaoId: number, isPublished: boolean) {
    try { await api(`/decisoes/${decisaoId}/`, { method: "PATCH", body: JSON.stringify({ status: isPublished ? "draft" : "published" }) }); await load(); }
    catch (cause) { setError((cause as Error).message); }
  }
  async function createRisco(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    try { await api("/riscos/", { method: "POST", body: JSON.stringify({ project: id, ...riscoDraft }) }); setRiscoDraft({ title: "", probability: "medium", impact: "medium", mitigation: "" }); await load(); }
    catch (cause) { setError((cause as Error).message); }
  }
  // O estado do risco entra por seleção e não por alternador: são quatro saídas e três delas
  // encerram por motivos diferentes — mitigado, aceito e materializado não são sinônimos, e um
  // botão de dois estados obrigaria a inventar uma ordem entre eles.
  async function setRiscoStatus(riscoId: number, status: RiscoStatus) {
    try { await api(`/riscos/${riscoId}/`, { method: "PATCH", body: JSON.stringify({ status }) }); await load(); }
    catch (cause) { setError((cause as Error).message); }
  }
  async function archiveRisco() {
    if (!archivingRisco) return;
    try { await api(`/riscos/${archivingRisco.id}/`, { method: "DELETE" }); setArchivingRisco(null); await load(); }
    catch (cause) { setArchivingRisco(null); setError((cause as Error).message); }
  }
  /**
   * Mapeia processos, etapas e achados da transcrição — **tudo como hipótese** (FDD 039).
   *
   * O achado nasce rotulado hipótese e com origem "entrevista", sempre: um modelo lendo
   * transcrição produz *o que foi dito*, que é uma das cinco formas de evidência, não prova.
   * Promover a fato é ato de gente, e acontece na tela do processo.
   *
   * **`mensagemDeFalha` e não o `(cause as Error).message` do resto desta página, de propósito.**
   * A divergência de dialeto é o ponto: esta é a única ação daqui que recusa reexecução com 409, e
   * o corpo desse 409 traz quantos processos a reunião já tem e qual é a saída ("arquive-os ou
   * edite-os"). A tabela de `erros.ts` acrescenta a orientação que falta — "o estado mudou desde
   * que esta tela carregou" —, e é ela que diz a quem clicou duas vezes por que o segundo clique
   * não fez nada. Sem isso a pessoa lê uma frase sobre processos que ela não vê nesta tela, e
   * conclui que quebrou.
   */
  async function estruturarProcessos(meeting: Meeting) {
    setAiLoading(true); setError(""); setProcessosMapeados(0);
    try {
      const { processos } = await api<{ processos: { id: number }[] }>(`/meetings/${meeting.id}/estruturar/`, { method: "POST" });
      setProcessosMapeados(processos.length);
    }
    catch (cause) { setError(mensagemDeFalha(cause)); } finally { setAiLoading(false); }
  }
  async function extrairDecisoes(meeting: Meeting) {
    setAiLoading(true);
    try { await api(`/meetings/${meeting.id}/extrair-decisoes/`, { method: "POST" }); await load(); }
    catch (cause) { setError((cause as Error).message); } finally { setAiLoading(false); }
  }
  async function createEmployee(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    try { await api("/digital-employees/", { method: "POST", body: JSON.stringify({ project: id, ...employeeDraft }) }); setEmployeeDraft({ name: "", area: "", status: "building" }); await loadEmployees(); }
    catch (cause) { setError((cause as Error).message); }
  }
  async function createEmployeeFromBlueprint(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!blueprintDraft) return;
    // Em branco vira `null`, não zero: sem base medida, o case declara a lacuna em vez de
    // afirmar um "antes" que ninguém apurou (FDD 027).
    try { await api(`/projects/${id}/digital-employees/from-blueprint/`, { method: "POST", body: JSON.stringify({ blueprint: Number(blueprintDraft), kpi_baseline: baselineDraft || null }) }); setBlueprintDraft(""); setBaselineDraft(""); await loadEmployees(); }
    catch (cause) { setError((cause as Error).message); }
  }
  function openEmployeeEdit(employee: DigitalEmployee) {
    setEmployeeEdit({
      name: employee.name, area: employee.area, status: employee.status, description: employee.description,
      kpi_label: employee.kpi_label, kpi_value: employee.kpi_value,
      kpi_unit: employee.kpi_unit, kpi_direction: employee.kpi_direction,
      kpi_baseline: employee.kpi_baseline ?? "", kpi_current: employee.kpi_current ?? "",
      hours_saved_month: employee.hours_saved_month, roi_month: employee.roi_month,
    });
    setEditingEmployee(employee);
  }
  async function saveEmployee(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!editingEmployee) return;
    setEmployeeBusy(true);
    try {
      // Os seis campos que nenhuma tela alcançava — e que o snapshot leva à tela do cliente.
      // Vazio vira "0" nos decimais porque o serializer os recusa em branco.
      await api(`/digital-employees/${editingEmployee.id}/`, { method: "PATCH", body: JSON.stringify({
        ...employeeEdit,
        hours_saved_month: employeeEdit.hours_saved_month || "0",
        roi_month: employeeEdit.roi_month || "0",
        // Aqui o vazio é `null` e **não** "0": base e valor atual medem, e um zero inventado
        // vira número no case (FDD 027).
        kpi_baseline: employeeEdit.kpi_baseline || null,
        kpi_current: employeeEdit.kpi_current || null,
      }) });
      setEditingEmployee(null); await loadEmployees();
    } catch (cause) { setError((cause as Error).message); }
    finally { setEmployeeBusy(false); }
  }
  async function archiveEmployee() {
    if (!archivingEmployee) return;
    setEmployeeBusy(true);
    try { await api(`/digital-employees/${archivingEmployee.id}/`, { method: "DELETE" }); setArchivingEmployee(null); await loadEmployees(); }
    catch (cause) { setArchivingEmployee(null); setError((cause as Error).message); }
    finally { setEmployeeBusy(false); }
  }
  async function restoreEmployee(employeeId: number) {
    try { await api(`/digital-employees/${employeeId}/unarchive/`, { method: "POST" }); await loadEmployees(); }
    catch (cause) { setError((cause as Error).message); }
  }
  // Só admin monta equipe (RFC 0003), e `/users/` também é admin-only — por isso a lista de
  // pessoas só é buscada quando há como usá-la.
  const canManageTeam = !!user?.is_admin;
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
  async function archiveProject() {
    setArchiveBusy(true);
    try { await api(`/projects/${id}/`, { method: "DELETE" }); window.location.assign("/projetos"); }
    catch (cause) { setArchivingProject(false); setError((cause as Error).message); setArchiveBusy(false); }
  }
  async function togglePendencia(pendenciaId: number, isResolved: boolean) {
    try { await api(`/pendencias/${pendenciaId}/`, { method: "PATCH", body: JSON.stringify({ status: isResolved ? "open" : "resolved" }) }); await load(); }
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

  if (error && !project) return <div role="alert" className="alert--error">{error}</div>;
  if (!project) return <div className="animate-pulse space-y-6"><div className="h-10 w-64 rounded-xl bg-slate-200" /><div className="h-56 rounded-2xl bg-white" /></div>;

  return <section className="space-y-7">
    {editingEmployee && <Modal title={`Editar ${editingEmployee.name}`} onClose={() => setEditingEmployee(null)}>
      {/* Os oito campos, e não os dois do formulário rápido: seis deles cruzam ao painel "Seu Time
          Digital" do cliente pelo snapshot (ADR 0003) e nenhuma tela os alcançava. */}
      <form className="grid gap-4" onSubmit={event => void saveEmployee(event)}>
        <label className="form-label">Nome<input className="field" value={employeeEdit.name} onChange={event => setEmployeeEdit({ ...employeeEdit, name: event.target.value })} required /></label>
        <div className="form-grid">
          <label className="form-label">Área<input className="field" placeholder="Financeiro, Atendimento…" value={employeeEdit.area} onChange={event => setEmployeeEdit({ ...employeeEdit, area: event.target.value })} /></label>
          <label className="form-label">Status<select className="field" value={employeeEdit.status} onChange={event => setEmployeeEdit({ ...employeeEdit, status: event.target.value as DigitalEmployeeStatus })}>{Object.entries(employeeStatusLabel).map(([value, label]) => <option key={value} value={value}>{label}</option>)}</select></label>
        </div>
        <label className="form-label">O que ele faz<textarea className="field min-h-20" placeholder="Descrição que o cliente lê no portal" value={employeeEdit.description} onChange={event => setEmployeeEdit({ ...employeeEdit, description: event.target.value })} /></label>
        <div className="form-grid">
          <label className="form-label">Rótulo do KPI<input className="field" placeholder="Notas conciliadas/mês" value={employeeEdit.kpi_label} onChange={event => setEmployeeEdit({ ...employeeEdit, kpi_label: event.target.value })} /></label>
          <label className="form-label">Valor do KPI (texto livre)<input className="field" placeholder="312" value={employeeEdit.kpi_value} onChange={event => setEmployeeEdit({ ...employeeEdit, kpi_value: event.target.value })} /></label>
        </div>
        {/* O par medido (FDD 027). É ele que vira o antes/depois do case quando o projeto for
            concluído — o campo de texto acima descreve, este mede. Deixar a base em branco é
            legítimo e diferente de zero: o case dirá que não houve base registrada. */}
        <div className="form-grid">
          <label className="form-label">Unidade do KPI<select className="field" value={employeeEdit.kpi_unit} onChange={event => setEmployeeEdit({ ...employeeEdit, kpi_unit: event.target.value as KpiUnit })}>{kpiUnits.map(unit => <option key={unit.value} value={unit.value}>{unit.label}</option>)}</select></label>
          <label className="form-label">Direção<select className="field" value={employeeEdit.kpi_direction} onChange={event => setEmployeeEdit({ ...employeeEdit, kpi_direction: event.target.value as KpiDirection })}><option value="up">Maior é melhor</option><option value="down">Menor é melhor</option></select></label>
          <label className="form-label">Antes (base)<input className="field" type="number" step="0.01" placeholder="Em branco = sem base medida" value={employeeEdit.kpi_baseline} onChange={event => setEmployeeEdit({ ...employeeEdit, kpi_baseline: event.target.value })} /></label>
          <label className="form-label">Depois (atual)<input className="field" type="number" step="0.01" value={employeeEdit.kpi_current} onChange={event => setEmployeeEdit({ ...employeeEdit, kpi_current: event.target.value })} /></label>
        </div>
        <div className="form-grid">
          <label className="form-label">Horas poupadas/mês<input className="field" type="number" min="0" step="0.1" value={employeeEdit.hours_saved_month} onChange={event => setEmployeeEdit({ ...employeeEdit, hours_saved_month: event.target.value })} /></label>
          <label className="form-label">ROI/mês (R$)<input className="field" type="number" min="0" step="0.01" value={employeeEdit.roi_month} onChange={event => setEmployeeEdit({ ...employeeEdit, roi_month: event.target.value })} /></label>
        </div>
        <div className="flex flex-wrap justify-end gap-3">
          <button type="button" className="btn btn--secondary" onClick={() => setEditingEmployee(null)}>Cancelar</button>
          <button type="submit" className="btn" disabled={employeeBusy}><Save className="size-4" />{employeeBusy ? "Salvando…" : "Salvar"}</button>
        </div>
      </form>
    </Modal>}
    {archivingEmployee && <ConfirmDialog
      title="Arquivar funcionário digital"
      message={<>O agente <strong className="text-ink">{archivingEmployee.name}</strong> sai do roster do projeto e do painel que o cliente vê. Nada é apagado — dá para restaurar em "Mostrar arquivados".</>}
      confirmLabel="Arquivar" busy={employeeBusy}
      onCancel={() => setArchivingEmployee(null)} onConfirm={() => void archiveEmployee()}
    />}
    {archivingRisco && <ConfirmDialog
      title="Arquivar risco"
      message={<>O risco <strong className="text-ink">{archivingRisco.title}</strong> sai do registro do projeto e do contexto do agente de Entrega. Nada é apagado — arquivar é o caminho para o que foi registrado por engano; o que aconteceu de verdade se marca como <strong className="text-ink">Materializado</strong>.</>}
      confirmLabel="Arquivar"
      onCancel={() => setArchivingRisco(null)} onConfirm={() => void archiveRisco()}
    />}
    {archivingProject && <ConfirmDialog
      title="Arquivar projeto"
      message={<>O projeto <strong className="text-ink">{project.name}</strong> sai das listagens ativas, junto com o que pende dele. Nada é apagado — dá para restaurar depois pela aba Arquivados.</>}
      confirmLabel="Arquivar" busy={archiveBusy}
      onCancel={() => setArchivingProject(false)} onConfirm={() => void archiveProject()}
    />}
    <a href="/projetos" className="back-link"><ArrowLeft className="size-4" />Voltar para projetos</a>
    <header className="page-head flex flex-col justify-between gap-4 sm:flex-row sm:items-end"><div><p className="eyebrow">Entrega</p><h1>{project.name}</h1><p className="mt-2 flex items-center gap-2 text-sm text-slate-600"><CalendarDays className="size-4" />{formatDate(project.start_date)} — {formatDate(project.due_date)}</p></div><div className="flex items-center gap-3 self-start"><span className={`state ${project.status === "active" ? "state--1" : project.status === "completed" ? "state--off" : "state--2"}`}>{projectStatusLabel[project.status] || project.status}</span><button className="btn btn--secondary" onClick={openEdit}><Pencil className="size-4 text-brand-500" />Editar</button>{canManageTeam && <button className="btn btn--secondary btn--secondary-danger" onClick={() => setArchivingProject(true)}><Trash2 className="size-4" />Arquivar</button>}</div></header>
    {error && <p role="alert" className="alert--error">{error}</p>}
    {editing && <form className="panel grid gap-4 sm:p-6" onSubmit={event => void saveProject(event)}>
      <div className="flex items-center justify-between"><h2 className="font-semibold text-ink">Editar projeto</h2><button type="button" className="grid size-8 place-items-center rounded-lg text-slate-600 hover:bg-slate-100" aria-label="Cancelar edição" onClick={() => setEditing(false)}><X className="size-4" /></button></div>
      <label className="form-label">Nome<input className="field" value={editDraft.name} onChange={event => setEditDraft({ ...editDraft, name: event.target.value })} required /></label>
      <label className="form-label">Descrição<textarea className="field min-h-20" value={editDraft.description} onChange={event => setEditDraft({ ...editDraft, description: event.target.value })} placeholder="Contexto e objetivo do projeto" /></label>
      <div className="grid gap-4 sm:grid-cols-3">
        <label className="form-label">Status<select className="field" aria-label="Status do projeto" value={editDraft.status} onChange={event => setEditDraft({ ...editDraft, status: event.target.value })}>{Object.entries(projectStatusLabel).map(([value, label]) => <option key={value} value={value}>{label}</option>)}</select></label>
        <label className="form-label">Início<input className="field" type="date" value={editDraft.start_date} onChange={event => setEditDraft({ ...editDraft, start_date: event.target.value })} required /></label>
        <label className="form-label">Prazo final<input className="field" type="date" value={editDraft.due_date} onChange={event => setEditDraft({ ...editDraft, due_date: event.target.value })} required /></label>
      </div>
      <div className="grid gap-4 sm:grid-cols-3">
        <label className="form-label">Serviço<select className="field" aria-label="Serviço do projeto" value={editDraft.service} onChange={event => setEditDraft({ ...editDraft, service: event.target.value })}><option value="">Sem serviço</option>{services.map(service => <option key={service.id} value={service.id}>{service.name}</option>)}</select></label>
        <label className="form-label">Receita realizada<input className="field" type="number" min="0" step="0.01" value={editDraft.actual_value} onChange={event => setEditDraft({ ...editDraft, actual_value: event.target.value })} placeholder="0,00" /></label>
        <label className="form-label">Custo<input className="field" type="number" min="0" step="0.01" value={editDraft.cost} onChange={event => setEditDraft({ ...editDraft, cost: event.target.value })} placeholder="0,00" /></label>
      </div>
      <button className="btn self-start" type="submit"><Save className="size-4" />Salvar projeto</button>
    </form>}

    <JourneySection
      phases={phases} canManage={canManageJourney}
      onAdvance={() => void advancePhase()} onMark={id => void markDeliverable(id)}
      onSetTarget={(phaseId, date) => void setPhaseTarget(phaseId, date)}
      onToggleChecklist={(itemId, checked) => void toggleChecklistItem(itemId, checked)}
      onSaveWaiver={(phaseId, waiver) => void saveChecklistWaiver(phaseId, waiver)}
      onApplyGate={(outcome, notes) => void applyGate(outcome, notes)}
    />

    {health && <div className="flex items-center gap-2 text-sm"><span className="font-medium text-slate-600">Saúde do projeto:</span><HealthBadge level={health.level} score={health.score} />{health.signals.length === 0 && <span className="text-slate-600">sem sinais de alerta</span>}</div>}

    {project?.ai_scored_at && <AiScorePanel project={project} canManage={canManageJourney} onTogglePublish={next => void toggleAiScorePublish(next)} />}

    {/* Depois da Jornada e do AI Score, antes de "Equipe do projeto" (DAP GH-41 r1, decisão 8): a
        faixa de "como a entrega está indo" vem antes do elenco e dos catálogos. O painel carrega
        sozinho porque o recurso é fechado para Vendas — pendurá-lo no `load` da página faria o
        403 dela derrubar as outras onze chamadas. */}
    <EngineeringPanel project={Number(id)} />

    <section className="panel sm:p-6">
      <div className="flex items-center gap-3"><span className="metric-icon"><UsersRound className="size-4" /></span><div><h2 className="font-semibold text-ink">Equipe do projeto</h2><p className="text-sm text-slate-600">Quem participa é quem enxerga este projeto e tudo o que pende dele.</p></div></div>
      {members.length ? <ul className="mt-4 divide-y rounded-xl border">{members.map(member => <li className="flex items-center gap-3 px-4 py-3" key={member.id}>
        <span className="grid size-8 shrink-0 place-items-center rounded-lg bg-accent-50 text-xs font-bold text-accent">{(member.user_name || member.user_username).slice(0, 2).toUpperCase()}</span>
        <div className="min-w-0 flex-1"><p className="truncate text-sm font-semibold text-ink">{member.user_name || member.user_username}</p><p className="text-xs text-slate-600">{roleLabel[member.user_role] ?? member.user_role}</p></div>
        {canManageTeam && <button className="shrink-0 rounded-lg p-2 text-slate-600 hover:bg-red-50 hover:text-danger" aria-label={`Remover ${member.user_name || member.user_username} da equipe`} onClick={() => void removeMember(member.id)}><X className="size-4" /></button>}
      </li>)}</ul> : <p className="mt-4 empty-state">Ninguém na equipe ainda — o projeto está invisível para a Entrega.</p>}
      {canManageTeam && <form className="mt-4 flex flex-wrap gap-2" onSubmit={event => void addMember(event)}>
        <select className="field flex-1" value={memberDraft} onChange={event => setMemberDraft(event.target.value)} aria-label="Pessoa a adicionar" required>
          <option value="">Selecione uma pessoa</option>
          {people.filter(person => !members.some(member => member.user === person.id)).map(person => <option key={person.id} value={person.id}>{person.first_name || person.username} — {roleLabel[person.role] ?? person.role}</option>)}
        </select>
        <button className="btn btn--icon" aria-label="Adicionar à equipe" type="submit"><Plus className="size-4" /></button>
      </form>}
    </section>

    <section className="panel sm:p-6">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div className="flex items-center gap-3"><span className="metric-icon"><Bot className="size-4" /></span><div><h2 className="font-semibold text-ink">Funcionários Digitais</h2><p className="text-sm text-slate-600">Os agentes de IA entregues neste projeto.</p></div></div>
        <label className="flex items-center gap-2 text-sm text-slate-600"><input type="checkbox" className="size-4 rounded border-slate-300 text-accent" checked={showArchivedEmployees} onChange={event => setShowArchivedEmployees(event.target.checked)} />Mostrar arquivados</label>
      </div>
      {employees.length ? <div className="mt-4 grid gap-3 sm:grid-cols-2">{employees.map(employee => <article className="rounded-xl border bg-slate-50/50 p-4" key={employee.id}>
        <div className="flex items-center justify-between gap-2"><p className="text-sm font-semibold text-ink">{employee.name}</p><span className={`rounded-full px-2 py-0.5 text-xs font-semibold ${employee.status === "active" ? "state--1" : employee.status === "paused" ? "state--off" : "state--2"}`}>{employeeStatusLabel[employee.status]}</span></div>
        {employee.area && <p className="mt-0.5 text-xs text-accent">{employee.area}</p>}
        {employee.description && <p className="mt-1 text-xs text-slate-600">{employee.description}</p>}
        <div className="mt-2 flex flex-wrap gap-x-4 gap-y-1 text-xs text-slate-600">{employee.kpi_label && <span><strong className="text-ink">{employee.kpi_label}:</strong> {employee.kpi_value}</span>}{Number(employee.hours_saved_month) > 0 && <span>{Number(employee.hours_saved_month)}h/mês</span>}{Number(employee.roi_month) > 0 && <span>ROI {money.format(Number(employee.roi_month))}/mês</span>}</div>
        {canManageJourney && <div className="mt-3 flex flex-wrap justify-end gap-2">{showArchivedEmployees
          ? <button className="inline-flex items-center gap-1.5 rounded-lg border bg-white px-2.5 py-1.5 text-xs font-semibold text-accent hover:border-accent" onClick={() => void restoreEmployee(employee.id)}>Restaurar</button>
          : <><button className="inline-flex items-center gap-1.5 rounded-lg border bg-white px-2.5 py-1.5 text-xs font-semibold text-ink hover:border-accent" aria-label={`Editar ${employee.name}`} onClick={() => openEmployeeEdit(employee)}><Pencil className="size-3.5 text-accent" />Editar</button>
            <button className="btn btn--secondary btn--secondary-danger" aria-label={`Arquivar ${employee.name}`} onClick={() => setArchivingEmployee(employee)}><Trash2 className="size-3.5" />Arquivar</button></>
        }</div>}
      </article>)}</div> : <p className="mt-4 empty-state">{showArchivedEmployees ? "Nenhum funcionário digital arquivado." : "Nenhum funcionário digital ainda."}</p>}
      {canManageJourney && !showArchivedEmployees && <>
        {/* Instanciar da biblioteca vem primeiro porque é o caminho que a metodologia quer: o
            bloco nasce com nome, descrição, KPI e valores já preenchidos, em vez de um cartão
            vazio para alguém completar à mão depois (FDD 026). O formulário livre continua
            embaixo, para o que ainda não virou catálogo. */}
        {catalog.length > 0 && <form className="mt-4 flex flex-wrap items-end gap-2 rounded-xl border border-dashed bg-accent-50/30 p-3" onSubmit={event => void createEmployeeFromBlueprint(event)}>
          <label className="form-label flex-1">Adicionar da biblioteca<select className="field" value={blueprintDraft} onChange={event => setBlueprintDraft(event.target.value)} required>
            <option value="">Escolha um bloco do catálogo…</option>
            {catalog.map(blueprint => <option key={blueprint.id} value={blueprint.id}>{blueprint.name} — {blueprint.area_display}{blueprint.has_variant ? ` (ajustado a ${project.client_vertical_name})` : ""}</option>)}
          </select></label>
          {/* O "antes" é pedido **aqui**, na instanciação, e não na hora de montar o case: este é
              o único momento em que ele ainda é medição. Preenchido meses depois, na conclusão,
              seria memória — e é exatamente isso que destrói a credibilidade de uma prova (FDD 027). */}
          <label className="form-label">Base do KPI hoje<input className="field w-40" type="number" step="0.01" placeholder="Opcional" value={baselineDraft} onChange={event => setBaselineDraft(event.target.value)} /></label>
          <button className="btn shrink-0" type="submit"><Plus className="size-4" />Instanciar</button>
        </form>}
        <form className="mt-4 flex flex-wrap gap-2" onSubmit={event => void createEmployee(event)}>
          <input className="field flex-1" placeholder="Nome (ex.: Agente Financeiro)" value={employeeDraft.name} onChange={event => setEmployeeDraft({ ...employeeDraft, name: event.target.value })} required />
          <input className="field w-40" placeholder="Área" value={employeeDraft.area} onChange={event => setEmployeeDraft({ ...employeeDraft, area: event.target.value })} />
          <button className="btn btn--icon" aria-label="Adicionar funcionário digital" type="submit"><Plus className="size-4" /></button>
        </form>
      </>}
    </section>

    {risk && risk.signals.length > 0 && <section className="panel sm:p-6">
      <div className="flex items-center gap-3"><span className={`rounded-full px-3 py-1 text-sm font-semibold ${risk.level === "alto" ? "state--3" : risk.level === "médio" ? "state--2" : "state--1"}`}>Risco {risk.level}</span><h2 className="font-semibold text-ink">Sinais de atraso</h2></div>
      <ul className="mt-3 space-y-1.5 text-sm text-slate-600">{risk.signals.map((signal, index) => <li className="flex gap-2" key={index}><AlertTriangle className="mt-0.5 size-4 shrink-0 text-danger" /><span><strong className="text-ink">{signal.label}:</strong> {signal.detail}</span></li>)}</ul>
      {risk.forecast && <p className={`mt-3 text-sm font-medium ${risk.forecast.delay_days > 0 ? "text-danger" : "text-slate-600"}`}>Previsão de término: {formatDate(risk.forecast.predicted_finish_date)}{risk.forecast.delay_days > 0 ? ` — atraso previsto de ${risk.forecast.delay_days} dia(s)` : " — dentro do prazo"} <span className="text-slate-600">({risk.forecast.basis})</span></p>}
    </section>}

    {aiEnabled && <section className="panel sm:p-6">
      <div className="flex flex-wrap items-center gap-3"><span className="metric-icon"><Sparkles className="size-4" /></span><div><h2 className="font-semibold text-ink">Assistente do projeto</h2><p className="text-sm text-slate-600">Pergunte sobre marcos, tarefas e prazos deste projeto.</p></div><button type="button" className="btn btn--secondary ml-auto" onClick={() => void suggestNextSteps()} disabled={aiLoading}>Sugerir próximos passos</button><button type="button" className="btn btn--secondary" onClick={() => void summarize()} disabled={aiLoading}>Resumir projeto</button></div>
      <form className="mt-4 flex gap-2" onSubmit={event => void askAssistant(event)}><input className="field" value={aiQuestion} onChange={event => setAiQuestion(event.target.value)} placeholder="Ex.: quais tarefas estão atrasadas?" aria-label="Pergunta ao assistente" /><button className="btn shrink-0" type="submit" disabled={aiLoading}>{aiLoading ? "…" : "Perguntar"}</button></form>
      {aiAnswer && <p className="mt-4 whitespace-pre-wrap rounded-xl bg-slate-50 p-4 text-sm text-slate-700">{aiAnswer}</p>}
    </section>}

    <div className="grid gap-5 lg:grid-cols-2">
      <WorkColumn icon={<Flag className="size-4" />} title="Marcos" count={milestones.length}>
        <form className="grid gap-3 sm:grid-cols-[1fr_auto]" onSubmit={event => void createMilestone(event)}>
          <input className="field" placeholder="Novo marco" value={milestoneDraft.title} onChange={event => setMilestoneDraft({ ...milestoneDraft, title: event.target.value })} required />
          <div className="flex gap-2"><input className="field min-w-0 flex-1" type="date" aria-label="Prazo do marco" value={milestoneDraft.due_date} onChange={event => setMilestoneDraft({ ...milestoneDraft, due_date: event.target.value })} required /><button className="btn btn--icon" aria-label="Adicionar marco" type="submit"><Plus className="size-4" /></button></div>
        </form>
        <WorkList items={milestones} onToggle={(itemId, isDone) => void toggleWorkItem("milestones", itemId, isDone)} onCalendar={calendarEnabled ? itemId => void addToCalendar("milestones", itemId) : undefined} emptyLabel="Nenhum marco cadastrado." />
      </WorkColumn>

      <WorkColumn icon={<ListTodo className="size-4" />} title="Tarefas" count={tasks.length}>
        <form className="grid gap-3" onSubmit={event => void createTask(event)}>
          <input className="field" placeholder="Nova tarefa" value={taskDraft.title} onChange={event => setTaskDraft({ ...taskDraft, title: event.target.value })} required />
          <div className="flex gap-2"><input className="field min-w-0 flex-1" type="date" aria-label="Prazo da tarefa" value={taskDraft.due_date} onChange={event => setTaskDraft({ ...taskDraft, due_date: event.target.value })} required /><select className="field min-w-0 flex-1" aria-label="Marco da tarefa" value={taskDraft.milestone} onChange={event => setTaskDraft({ ...taskDraft, milestone: event.target.value })}><option value="">Sem marco</option>{milestones.map(milestone => <option key={milestone.id} value={milestone.id}>{milestone.title}</option>)}</select><button className="btn btn--icon" aria-label="Adicionar tarefa" type="submit"><Plus className="size-4" /></button></div>
        </form>
        <WorkList items={tasks} onToggle={(itemId, isDone) => void toggleWorkItem("tasks", itemId, isDone)} onCalendar={calendarEnabled ? itemId => void addToCalendar("tasks", itemId) : undefined} emptyLabel="Nenhuma tarefa cadastrada." />
      </WorkColumn>
    </div>

    <div className="grid gap-5 lg:grid-cols-2">
      <WorkColumn icon={<Video className="size-4" />} title="Reuniões" count={meetings.length}>
        <form className="grid gap-3" onSubmit={event => void createMeeting(event)}>
          <input className="field" placeholder="Título da reunião" value={meetingDraft.title} onChange={event => setMeetingDraft({ ...meetingDraft, title: event.target.value })} required />
          <div className="flex gap-2"><input className="field min-w-0 flex-1" type="date" aria-label="Data da reunião" value={meetingDraft.date} onChange={event => setMeetingDraft({ ...meetingDraft, date: event.target.value })} required /><input className="field min-w-0 flex-1" type="url" aria-label="Link da reunião" placeholder="Link da reunião (opcional)" value={meetingDraft.meeting_url} onChange={event => setMeetingDraft({ ...meetingDraft, meeting_url: event.target.value })} /><input className="field min-w-0 flex-1" type="url" aria-label="Link da gravação" placeholder="Link da gravação (opcional)" value={meetingDraft.recording_url} onChange={event => setMeetingDraft({ ...meetingDraft, recording_url: event.target.value })} /><button className="btn btn--icon" aria-label="Adicionar reunião" type="submit"><Plus className="size-4" /></button></div>
          <textarea className="field min-h-20" placeholder="Transcrição da reunião (para Discovery/Assessment por IA)" value={meetingDraft.transcript} onChange={event => setMeetingDraft({ ...meetingDraft, transcript: event.target.value })} />
        </form>
        {meetings.length ? <div className="divide-y">{meetings.map(meeting => <div className="py-3" key={meeting.id}>
          <div className="flex items-center gap-3">
            <span className="grid size-9 shrink-0 place-items-center rounded-xl bg-slate-100 text-slate-600"><Video className="size-4" /></span>
            <div className="min-w-0 flex-1"><p className="truncate text-sm font-medium text-ink">{meeting.title}</p><p className="mt-0.5 text-xs text-slate-600">{formatDate(meeting.date)}</p></div>
            {meeting.meeting_url && <a className="shrink-0 rounded-lg p-1.5 text-slate-600 hover:text-accent" href={meeting.meeting_url} target="_blank" rel="noreferrer" aria-label={`Abrir reunião de ${meeting.title}`}><Video className="size-4" /></a>}
            {meeting.recording_url && <a className="shrink-0 rounded-lg p-1.5 text-slate-600 hover:text-accent" href={meeting.recording_url} target="_blank" rel="noreferrer" aria-label={`Abrir gravação de ${meeting.title}`}><ExternalLink className="size-4" /></a>}
            <button type="button" onClick={() => void toggleMeeting(meeting)} aria-label={meeting.status === "held" ? `Marcar ${meeting.title} como agendada` : `Marcar ${meeting.title} como realizada`} className={`shrink-0 rounded-full px-2.5 py-1 text-xs font-semibold transition hover:ring-2 hover:ring-accent/30 ${meeting.status === "held" ? "state--1" : "state--off"}`}>{meeting.status === "held" ? "Realizada" : "Agendada"}</button>
          </div>
          {aiEnabled && meeting.transcript.trim() && <div className="mt-2 flex flex-wrap gap-2 pl-12">
            <button type="button" className="inline-flex items-center gap-1.5 rounded-lg border px-2.5 py-1.5 text-xs font-semibold text-ink hover:border-accent disabled:opacity-60" disabled={aiLoading} onClick={() => void runMeetingAi(meeting, "discovery")}><Sparkles className="size-3.5 text-accent" />Discovery</button>
            <button type="button" className="inline-flex items-center gap-1.5 rounded-lg border px-2.5 py-1.5 text-xs font-semibold text-ink hover:border-accent disabled:opacity-60" disabled={aiLoading} onClick={() => void runMeetingAi(meeting, "assessment")}><Sparkles className="size-3.5 text-accent" />Assessment</button>
            <button type="button" className="inline-flex items-center gap-1.5 rounded-lg border px-2.5 py-1.5 text-xs font-semibold text-ink hover:border-accent disabled:opacity-60" disabled={aiLoading} onClick={() => void runAiScore(meeting)}><Gauge className="size-3.5 text-accent" />AI Score</button><button type="button" className="inline-flex items-center gap-1.5 rounded-lg border px-2.5 py-1.5 text-xs font-semibold text-ink hover:border-accent disabled:opacity-60" disabled={aiLoading} onClick={() => void extrairDecisoes(meeting)}><Sparkles className="size-3.5 text-accent" />Decisões</button><button type="button" className="inline-flex items-center gap-1.5 rounded-lg border px-2.5 py-1.5 text-xs font-semibold text-ink hover:border-accent disabled:opacity-60" disabled={aiLoading} onClick={() => void estruturarProcessos(meeting)}><Workflow className="size-3.5 text-accent" />Processos</button>
          </div>}
        </div>)}</div> : <p className="empty-state">Nenhuma reunião registrada.</p>}
        {/* O mapa levantado não aparece nesta tela: ele pende do cliente e sobrevive a este
            projeto. A linha diz quantos vieram e para onde ir revisá-los — todos em hipótese. */}
        {processosMapeados > 0 && <p role="status" className="alert--ok">{processosMapeados} processo(s) mapeado(s) como hipótese. Abra o cliente para revisar e promover o que for fato.</p>}
        <ArtifactsPanel project={Number(id)} reloadToken={artifactsToken} />
      </WorkColumn>

      <WorkColumn icon={<Inbox className="size-4" />} title="Pendências" count={pendencias.length}>
        <form className="grid gap-3" onSubmit={event => void createPendencia(event)}>
          <input className="field" placeholder="Nova pendência" value={pendenciaDraft.title} onChange={event => setPendenciaDraft({ ...pendenciaDraft, title: event.target.value })} required />
          <div className="flex gap-2"><select className="field min-w-0 flex-1" aria-label="Responsável pela pendência" value={pendenciaDraft.party} onChange={event => setPendenciaDraft({ ...pendenciaDraft, party: event.target.value as Party })}><option value="provider">Fornecedor</option><option value="client">Cliente</option></select><button className="btn btn--icon" aria-label="Adicionar pendência" type="submit"><Plus className="size-4" /></button></div>
        </form>
        {pendencias.length ? <div className="divide-y">{pendencias.map(pendencia => {
          const resolved = pendencia.status === "resolved";
          return <div className="flex items-center gap-3 py-3" key={pendencia.id}>
            <button className={`shrink-0 ${resolved ? "text-emerald-600 hover:text-ink" : "text-slate-300 hover:text-accent"}`} aria-label={resolved ? `Reabrir ${pendencia.title}` : `Resolver ${pendencia.title}`} onClick={() => void togglePendencia(pendencia.id, resolved)}>{resolved ? <CheckCircle2 className="size-5" /> : <Circle className="size-5" />}</button>
            <div className="min-w-0 flex-1"><p className={`truncate text-sm font-medium ${resolved ? "text-slate-600 line-through" : "text-ink"}`}>{pendencia.title}</p><p className="mt-0.5 text-xs text-slate-600">{partyLabel[pendencia.party]}</p></div>
            <span className={`state shrink-0 ${resolved ? "state--1" : "state--2"}`}>{resolved ? "Resolvida" : "Aberta"}</span>
          </div>;
        })}</div> : <p className="empty-state">Nenhuma pendência.</p>}
      </WorkColumn>
    </div>

    {/* Decisões (FDD 032). Grade própria e não uma terceira coluna na de cima: o `WorkColumn` tem
        comentário próprio sobre estourar a trilha no celular, e três colunas reabririam aquilo.

        O selo diz o que o cliente vê. Rascunho é interno — é o que a extração por IA grava, e é o
        que faz um palpite de modelo não alcançar a tela do cliente antes de alguém olhar. */}
    <div className="grid gap-5 lg:grid-cols-2">
      <WorkColumn icon={<Scale className="size-4" />} title="Decisões" count={decisoes.length}>
        <form className="grid gap-3" onSubmit={event => void createDecisao(event)}>
          <input className="field" placeholder="O que foi decidido" value={decisaoDraft.title} onChange={event => setDecisaoDraft({ ...decisaoDraft, title: event.target.value })} required />
          <div className="flex gap-2"><input className="field min-w-0 flex-1" placeholder="Quem decidiu (opcional)" value={decisaoDraft.decided_by} onChange={event => setDecisaoDraft({ ...decisaoDraft, decided_by: event.target.value })} /><button className="btn btn--icon" aria-label="Adicionar decisão" type="submit"><Plus className="size-4" /></button></div>
          <textarea className="field min-h-20" placeholder="Por quê — o que pesou, e o que foi descartado" value={decisaoDraft.rationale} onChange={event => setDecisaoDraft({ ...decisaoDraft, rationale: event.target.value })} />
        </form>
        {decisoes.length ? <div className="divide-y">{decisoes.map(decisao => {
          const published = decisao.status === "published";
          return <div className="py-3" key={decisao.id}>
            <div className="flex items-start gap-3">
              <span className="metric-icon shrink-0"><Scale className="size-4" /></span>
              <div className="min-w-0 flex-1">
                <p className="text-sm font-medium text-ink">{decisao.title}</p>
                {decisao.rationale && <p className="mt-0.5 text-xs text-slate-600">{decisao.rationale}</p>}
                <p className="mt-0.5 text-xs text-slate-600">{[decisao.decided_by, decisao.decided_on && formatDate(decisao.decided_on)].filter(Boolean).join(" · ") || "Sem autoria registrada"}</p>
              </div>
              <button type="button" onClick={() => void toggleDecisao(decisao.id, published)} aria-label={published ? `Despublicar ${decisao.title}` : `Publicar ${decisao.title}`} className={`state shrink-0 transition hover:ring-2 hover:ring-accent/30 ${published ? "state--1" : "state--off"}`}>{published ? "Publicada" : "Rascunho"}</button>
            </div>
          </div>;
        })}</div> : <p className="empty-state">Nenhuma decisão registrada.</p>}
      </WorkColumn>

      {/* Risk Register (FDD 034). Ao lado das Decisões porque são o mesmo tipo de registro: o que
          a equipe sabe e não cabe em marco nem em tarefa. E abaixo dos "Sinais de atraso" porque
          aquele painel é o risco **calculado** — o que já escorregou — e este é o declarado, o que
          ainda não aconteceu e por isso ainda dá para evitar. */}
      <WorkColumn icon={<ShieldAlert className="size-4" />} title="Riscos" count={riscos.length}>
        <form className="grid gap-3" onSubmit={event => void createRisco(event)}>
          <input className="field" placeholder="O que pode dar errado" value={riscoDraft.title} onChange={event => setRiscoDraft({ ...riscoDraft, title: event.target.value })} required />
          <div className="flex gap-2">
            <select className="field min-w-0 flex-1" aria-label="Probabilidade do risco" value={riscoDraft.probability} onChange={event => setRiscoDraft({ ...riscoDraft, probability: event.target.value as RiscoNivel })}>{riscoNiveis.map(nivel => <option key={nivel} value={nivel}>Probabilidade {riscoNivelLabel[nivel].probabilidade.toLowerCase()}</option>)}</select>
            <select className="field min-w-0 flex-1" aria-label="Impacto do risco" value={riscoDraft.impact} onChange={event => setRiscoDraft({ ...riscoDraft, impact: event.target.value as RiscoNivel })}>{riscoNiveis.map(nivel => <option key={nivel} value={nivel}>Impacto {riscoNivelLabel[nivel].impacto.toLowerCase()}</option>)}</select>
            <button className="btn btn--icon" aria-label="Adicionar risco" type="submit"><Plus className="size-4" /></button>
          </div>
          <textarea className="field min-h-20" placeholder="Plano de mitigação — o que se faz para o risco não virar fato" value={riscoDraft.mitigation} onChange={event => setRiscoDraft({ ...riscoDraft, mitigation: event.target.value })} />
        </form>
        {riscos.length ? <div className="divide-y">{riscos.map(risco => <div className="py-3" key={risco.id}>
          <div className="flex items-start gap-3">
            <span className="metric-icon shrink-0"><ShieldAlert className="size-4" /></span>
            <div className="min-w-0 flex-1">
              <p className="text-sm font-medium text-ink">{risco.title}</p>
              <p className="mt-0.5 text-xs text-slate-600">Probabilidade {riscoNivelLabel[risco.probability].probabilidade.toLowerCase()} · impacto {riscoNivelLabel[risco.impact].impacto.toLowerCase()}</p>
              <p className="mt-0.5 text-xs text-slate-600">{risco.mitigation || "Sem mitigação registrada"}</p>
            </div>
            <span className={`state shrink-0 ${riscoStatusVariant[risco.status]}`}>{riscoStatusLabel[risco.status]}</span>
          </div>
          <div className="mt-2 flex flex-wrap items-center justify-end gap-2">
            <select className="field w-auto" aria-label={`Estado de ${risco.title}`} value={risco.status} onChange={event => void setRiscoStatus(risco.id, event.target.value as RiscoStatus)}>{riscoStatuses.map(estado => <option key={estado} value={estado}>{riscoStatusLabel[estado]}</option>)}</select>
            <button type="button" className="btn btn--secondary btn--secondary-danger" aria-label={`Arquivar ${risco.title}`} onClick={() => setArchivingRisco(risco)}><Trash2 className="size-3.5" />Arquivar</button>
          </div>
        </div>)}</div> : <p className="empty-state">Nenhum risco registrado.</p>}
      </WorkColumn>
    </div>
  </section>;
}

function ScoreBar({ label, value, tone }: { label: string; value: number | null; tone: "brand" | "positive" }) {
  const pct = value ?? 0;
  return <div>
    <div className="flex items-baseline justify-between text-sm"><span className="font-medium text-slate-600">{label}</span><span className="font-semibold text-ink">{value === null ? "—" : `${value}/100`}</span></div>
    <div className="mt-1 h-2 rounded-full bg-slate-100"><div className={`h-2 rounded-full transition-all ${tone === "brand" ? "bg-ink" : "bg-emerald-500"}`} style={{ width: `${pct}%` }} /></div>
  </div>;
}

function AiScorePanel({ project, canManage, onTogglePublish }: { project: Project; canManage: boolean; onTogglePublish: (next: boolean) => void }) {
  const published = project.ai_score_reviewed;
  return <section className="panel space-y-4 sm:p-6">
    <div className="flex flex-wrap items-center gap-3">
      <span className="metric-icon"><Gauge className="size-4" /></span>
      <div className="flex-1"><h2 className="font-semibold text-ink">AI Score</h2><p className="text-sm text-slate-600">Maturidade e oportunidade de IA a partir do Discovery/Assessment.</p></div>
      <span className={`state ${published ? "state--1" : "state--2"}`}>{published ? "Publicado ao cliente" : "Rascunho — revisar"}</span>
    </div>
    <div className="grid gap-3 sm:grid-cols-2">
      <ScoreBar label="Maturidade" value={project.ai_maturity} tone="brand" />
      <ScoreBar label="Oportunidade" value={project.ai_opportunity} tone="positive" />
    </div>
    {project.ai_dimensions.length > 0 && <div className="grid gap-2 sm:grid-cols-2">{project.ai_dimensions.map((dimension, index) => <ScoreBar key={index} label={dimension.label} value={dimension.score} tone="brand" />)}</div>}
    {project.ai_score_summary && <p className="whitespace-pre-wrap rounded-xl bg-slate-50 p-4 text-sm text-slate-700">{project.ai_score_summary}</p>}
    {canManage && <label className="flex items-center gap-2 text-sm text-slate-600"><input type="checkbox" className="size-4 rounded border-slate-300 text-accent" checked={published} onChange={event => onTogglePublish(event.target.checked)} />Publicar ao cliente (revisado)</label>}
  </section>;
}

type JourneySectionProps = {
  phases: ProjectPhase[]; canManage: boolean;
  onAdvance: () => void; onMark: (id: number) => void;
  onSetTarget: (phaseId: number, date: string) => void;
  onToggleChecklist: (itemId: number, checked: boolean) => void;
  onSaveWaiver: (phaseId: number, waiver: string) => void;
  onApplyGate: (outcome: GateOutcome, notes: string) => void;
};

function JourneySection({ phases, canManage, onAdvance, onMark, onSetTarget, onToggleChecklist, onSaveWaiver, onApplyGate }: JourneySectionProps) {
  const [gateNotes, setGateNotes] = useState("");
  const [waiverDraft, setWaiverDraft] = useState<string | null>(null);
  const [confirming, setConfirming] = useState<GateOutcome | null>(null);
  if (!phases.length) return null;
  const done = phases.filter(phase => phase.status === "done").length;
  const active = phases.find(phase => phase.status === "active");
  const next = active ? phases.find(phase => phase.phase_position > active.phase_position) : undefined;
  const pct = Math.round((done / phases.length) * 100);
  const checklist = active?.checklist_items ?? [];
  const pending = checklist.filter(item => !item.checked).length;

  return <section className="panel space-y-5 sm:p-6">
    <div className="flex flex-wrap items-center gap-3">
      <span className="metric-icon"><MapPin className="size-4" /></span>
      <div className="flex-1"><h2 className="font-semibold text-ink">Jornada de Transformação</h2><p className="text-sm text-slate-600">{done} de {phases.length} fases concluídas</p></div>
      <span className="eyebrow">{pct}%</span>
    </div>

    <div className="h-2 rounded-full bg-slate-100"><div className="h-2 rounded-full bg-ink transition-all" style={{ width: `${pct}%` }} /></div>

    <div className="flex flex-wrap gap-2">{phases.map(phase => {
      const isDone = phase.status === "done"; const isActive = phase.status === "active";
      return <span key={phase.id} className="inline-flex items-center gap-1.5">
        <span className={`inline-flex items-center gap-1.5 rounded-full px-3 py-1.5 text-xs font-semibold ${isDone ? "state--1" : isActive ? "bg-ink text-white" : "state--off"}`}>{isDone ? <CheckCircle2 className="size-3.5" /> : isActive ? <MapPin className="size-3.5" /> : <Lock className="size-3.5" />}{phase.phase_name}</span>
        {/* O selo do gate acompanha a fase e não some quando ela fecha: é o registro de *como* a
            jornada passou por ali — inclusive na fase que o REDESIGN trancou. */}
        {phase.gate_outcome && <span className={`state ${gateBadgeClass(phase.gate_outcome)}`} title={phase.gate_notes || undefined}>{GATE_LABEL[phase.gate_outcome]}</span>}
      </span>;
    })}</div>

    {active ? <div className="rounded-2xl border bg-slate-50/60 p-4 sm:p-5">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div className="min-w-0"><p className="text-xs font-semibold uppercase tracking-wide text-accent">Você está aqui</p><h3 className="mt-0.5 text-lg font-semibold text-ink">{active.phase_name}</h3>{active.phase_description && <p className="mt-1 text-sm text-slate-600">{active.phase_description}</p>}</div>
        {next && <p className="shrink-0 text-right text-xs text-slate-600">Próxima<span className="mt-0.5 flex items-center gap-1 font-semibold text-slate-600"><ChevronRight className="size-3.5" />{next.phase_name}</span></p>}
      </div>

      {active.deliverables.length > 0 && <div className="mt-4">
        <p className="mb-1 text-xs font-semibold uppercase tracking-wide text-slate-600">Entregáveis · {active.deliverables.filter(item => item.status === "delivered").length}/{active.deliverables.length}</p>
        <div className="divide-y">{active.deliverables.map(item => {
          const delivered = item.status === "delivered";
          return <div className="flex items-center gap-3 py-2.5" key={item.id}>
            <button className={`shrink-0 ${delivered ? "text-emerald-600" : canManage ? "text-slate-300 hover:text-accent" : "text-slate-200"}`} aria-label={delivered ? `${item.name} entregue` : `Marcar ${item.name} como entregue`} disabled={delivered || !canManage} onClick={() => onMark(item.id)}>{delivered ? <CheckCircle2 className="size-5" /> : <Circle className="size-5" />}</button>
            <span className={`flex-1 text-sm font-medium ${delivered ? "text-slate-600 line-through" : "text-ink"}`}>{item.name}</span>
          </div>;
        })}</div>
      </div>}

      {checklist.length > 0 && <div className="mt-4">
        {/* O quality gate (FDD 033). Distinto dos entregáveis logo acima: aquilo é o que sai da
            fase, isto é a condição para que possa sair — e é só isto que trava a conclusão. */}
        <p className="mb-1 text-xs font-semibold uppercase tracking-wide text-slate-600">Checklist de qualidade · {checklist.length - pending}/{checklist.length}</p>
        <div className="divide-y">{checklist.map(item => <div className="flex items-center gap-3 py-2.5" key={item.id}>
          <button className={`shrink-0 ${item.checked ? "text-emerald-600 hover:text-ink" : canManage ? "text-slate-300 hover:text-accent" : "text-slate-200"}`} aria-label={item.checked ? `Desmarcar ${item.text}` : `Marcar ${item.text}`} disabled={!canManage} onClick={() => onToggleChecklist(item.id, !item.checked)}>{item.checked ? <CheckCircle2 className="size-5" /> : <Circle className="size-5" />}</button>
          <span className={`flex-1 text-sm font-medium ${item.checked ? "text-slate-600 line-through" : "text-ink"}`}>{item.text}</span>
        </div>)}</div>
        {canManage && pending > 0 && <div className="mt-3 grid gap-2">
          {/* Concluir com pendência é legítimo; fazê-lo em silêncio não é. A justificativa é o
              que o backend aceita no lugar dos itens que faltam. */}
          <label className="form-label">Justificativa para concluir com {pending} item(ns) pendente(s)
            <textarea className="field min-h-16" placeholder="Por que esta fase pode fechar sem o checklist completo?" value={waiverDraft ?? active.checklist_waiver} onChange={event => setWaiverDraft(event.target.value)} />
          </label>
          <button type="button" className="btn btn--secondary justify-self-start" onClick={() => { onSaveWaiver(active.id, waiverDraft ?? active.checklist_waiver); setWaiverDraft(null); }}><Save className="size-4" />Registrar justificativa</button>
        </div>}
      </div>}

      {active.requires_gate && canManage && <div className="mt-4 rounded-2xl border border-dashed p-4">
        {/* O decision gate de quatro saídas (ADR 0030, FDD 033). As quatro ficam lado a lado
            porque a metodologia pede uma escolha entre elas, não um "avançar" com ressalva
            escondida atrás de um menu. */}
        <p className="eyebrow">Decision gate</p>
        <p className="mt-1 text-sm text-slate-600">Esta fase termina em decisão. REDESIGN reabre a fase anterior; NO-GO para a jornada aqui.</p>
        <label className="form-label mt-3">Ressalvas, motivo ou condições
          <textarea className="field min-h-16" placeholder="O que pesou na decisão — obrigatório na prática para CONDITIONAL GO, REDESIGN e NO-GO" value={gateNotes} onChange={event => setGateNotes(event.target.value)} />
        </label>
        <div className="mt-3 flex flex-wrap gap-2">
          <button type="button" className="btn" onClick={() => onApplyGate("go", gateNotes)}><CheckCircle2 className="size-4" />GO</button>
          <button type="button" className="btn btn--secondary" onClick={() => onApplyGate("conditional_go", gateNotes)}>CONDITIONAL GO</button>
          <button type="button" className="btn btn--secondary" onClick={() => setConfirming("redesign")}>REDESIGN</button>
          <button type="button" className="btn btn--secondary btn--secondary-danger" onClick={() => setConfirming("no_go")}>NO-GO</button>
        </div>
      </div>}

      <div className="mt-4 flex flex-wrap items-end justify-between gap-3">
        {canManage ? <label className="grid gap-1 text-xs font-medium text-slate-600">Previsão desta fase<input className="field w-44" type="date" value={active.target_date ?? ""} onChange={event => onSetTarget(active.id, event.target.value)} /></label> : active.target_date ? <p className="text-sm text-slate-600">Previsão: {formatDate(active.target_date)}</p> : <span />}
        {/* O botão de avançar continua onde estava, e é ele que encosta nos dois gates: quando a
            fase exige decisão ou tem checklist pendente, o 409 do backend vira o alerta da página. */}
        {canManage && <button type="button" className="btn" onClick={onAdvance}><CheckCircle2 className="size-4" />Concluir fase e avançar</button>}
      </div>
    </div> : <div className="flex items-center gap-3 rounded-2xl border border-emerald-100 bg-emerald-50 p-4 text-sm font-medium text-emerald-700"><Trophy className="size-5 shrink-0" />Jornada de transformação concluída — todas as fases entregues.</div>}

    {confirming && <ConfirmDialog
      title={confirming === "redesign" ? "Registrar REDESIGN" : "Registrar NO-GO"}
      message={confirming === "redesign"
        ? <>A fase <strong className="text-ink">{active?.phase_name}</strong> volta para <strong className="text-ink">a fase anterior</strong>, que é reaberta para ser testada de novo. A decisão e o motivo ficam registrados nesta fase.</>
        : <>A jornada <strong className="text-ink">para nesta fase</strong>. Nada é apagado e a fase continua em andamento — o que muda é o registro de que a hipótese não se sustentou.</>}
      confirmLabel={confirming === "redesign" ? "Registrar REDESIGN" : "Registrar NO-GO"}
      onCancel={() => setConfirming(null)}
      onConfirm={() => { onApplyGate(confirming, gateNotes); setConfirming(null); }}
    />}
  </section>;
}

function WorkColumn({ icon, title, count, children }: { icon: ReactNode; title: string; count: number; children: ReactNode }) {
  // `min-w-0`: item de grade nasce com `min-width: auto` e se recusa a encolher abaixo do
  // conteúdo — no celular a coluna estourava a trilha e a página inteira rolava na horizontal.
  return <section className="panel min-w-0 space-y-4 sm:p-6"><div className="flex items-center gap-3"><span className="metric-icon">{icon}</span><div><h2 className="font-semibold text-ink">{title}</h2><p className="text-sm text-slate-600">{count} {count === 1 ? "item" : "itens"}</p></div></div>{children}</section>;
}

function WorkList({ items, onToggle, onCalendar, emptyLabel }: { items: (Milestone | Task)[]; onToggle: (id: number, isDone: boolean) => void; onCalendar?: (id: number) => void; emptyLabel: string }) {
  if (!items.length) return <p className="empty-state">{emptyLabel}</p>;
  return <div className="divide-y">{items.map(item => {
    const done = item.status === "done";
    return <div className="flex items-center gap-3 py-3" key={item.id}>
      <button className={`shrink-0 ${done ? "text-emerald-600 hover:text-ink" : "text-slate-300 hover:text-accent"}`} aria-label={done ? `Reabrir ${item.title}` : `Concluir ${item.title}`} onClick={() => onToggle(item.id, done)}>{done ? <CheckCircle2 className="size-5" /> : <Circle className="size-5" />}</button>
      <div className="min-w-0 flex-1"><p className={`truncate text-sm font-medium ${done ? "text-slate-600 line-through" : "text-ink"}`}>{item.title}</p><p className={`mt-0.5 flex items-center gap-1.5 text-xs ${item.is_overdue ? "font-semibold text-danger" : "text-slate-600"}`}>{item.is_overdue && <AlertTriangle className="size-3.5" />}{formatDate(item.due_date)}</p></div>
      {onCalendar && <button className="shrink-0 rounded-lg p-1.5 text-slate-600 hover:text-accent" aria-label={`Adicionar ${item.title} ao calendário`} onClick={() => onCalendar(item.id)}><CalendarPlus className="size-4" /></button>}
      <span className={`state shrink-0 ${done ? "state--1" : item.status === "in_progress" ? "state--2" : "state--off"}`}>{workStatusLabel[item.status]}</span>
    </div>;
  })}</div>;
}
