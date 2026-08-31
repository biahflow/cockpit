import { AlertTriangle, ArrowLeft, Bot, UsersRound, CalendarDays, CalendarPlus, CheckCircle2, ChevronRight, Circle, ExternalLink, Flag, FlaskConical, Gauge, History, Hourglass, Inbox, ListTodo, Lock, MapPin, Microscope, Pencil, Plus, Save, Scale, ShieldAlert, Sparkles, Trash2, Trophy, Video, Workflow, X } from "lucide-react";
import { type FormEvent, type ReactNode, useCallback, useEffect, useState } from "react";

import { api, listFeasibilityAssessments, listKpis, listMeasurements, listProveExperiments, listUsers, registerProveGapWaiver, startProveExperiment } from "../api";
import { useAuth } from "../auth";
import { ArtifactsPanel } from "../components/ArtifactsPanel";
import { ConfirmDialog, Modal } from "../components/Modal";
import { HealthBadge } from "../components/StatusDot";
import { mensagemDeFalha } from "../erros";
import { CANONICAL_STAGE_LABEL, GATE_DECISION_LABEL, GATE_EFFECT, gateDecisionByEffect, gateDecisions, PHASE_EVENT_LABEL, SITUATION_LABEL, situationVariant, WAITING_PARTY_LABEL, WAITING_PARTY_OPTIONS } from "../journey";
import type { DigitalEmployee, DigitalEmployeeBlueprint, DigitalEmployeeStatus, FeasibilityAssessment, FeasibilityVerdict, GateDecision, GithubCiState, GithubDeliveryProjection, GithubIssueState, GithubProjectionState, GithubPullState, GithubReviewState, HealthAssessment, KPI, KpiDirection, KpiUnit, Measurement, Meeting, Milestone, Party, Decisao, Pendencia, Project, ProjectMember, ProjectPhase, ProjectTimeline, ProveExperiment, ProveExperimentStatus, ProveMissingRequirement, Risco, RiscoNivel, RiscoStatus, RiskAssessment, Service, SessionUser, SolutionHypothesis, Task, WaitingParty, WorkItemStatus } from "../types";

const money = new Intl.NumberFormat("pt-BR", { style: "currency", currency: "BRL", maximumFractionDigits: 0 });
const roleLabel: Record<string, string> = { admin: "Administrador", sales: "Vendas", delivery: "Entrega" };
const projectStatusLabel: Record<string, string> = { planning: "Planejamento", active: "Ativo", on_hold: "Em espera", completed: "Concluído" };
const workStatusLabel: Record<WorkItemStatus, string> = { todo: "A fazer", in_progress: "Em andamento", done: "Concluído" };
const partyLabel: Record<Party, string> = { provider: "Fornecedor", client: "Cliente" };
const blankMeeting = { title: "", date: "", meeting_url: "", recording_url: "", transcript: "" };
const employeeStatusLabel: Record<DigitalEmployeeStatus, string> = { building: "Em construção", active: "Ativo", paused: "Pausado" };
// "A, B e C". A copy do gate nomeia as saídas da fase ativa, e são três ou duas conforme o
// vocabulário (ADR 0053) — juntar com vírgula seca deixaria "CONDITIONAL GO, REDESIGN, NO-GO".
const listar = (itens: string[]) => itens.length > 1 ? `${itens.slice(0, -1).join(", ")} e ${itens[itens.length - 1]}` : itens.join("");
// Variante, nunca a cor: uma segunda definição de "aprovado" diverge da primeira em silêncio
// (ADR 0026). CONDITIONAL GO e REDESIGN dividem o âmbar porque os dois dizem a mesma coisa ao
// olho — "seguiu, mas há dívida" —, e só o NO-GO é o vermelho de fato. As três saídas do PROVE
// herdam a variante do efeito (ADR 0053): SCALE pinta como GO, ITERATE como REDESIGN e STOP como
// NO-GO — a mesma leitura, porque é a mesma consequência.
const gateVariant: Record<GateDecision, string> = { go: "state--1", conditional_go: "state--2", redesign: "state--2", no_go: "state--3", scale: "state--1", iterate: "state--2", stop: "state--3" };
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
// Projeção de entrega GitHub (FDD 041). O estado *visível* vira selo com variante de `.state` — a
// cor sai do mapa, nunca escrita à mão (ADR 0026). `pending` é **neutro** (`--off`): "ainda não
// observamos" não é aviso; `stale`/`unavailable` avisam; sem permissão / referência ausente doem.
const projectionStateLabel: Record<GithubProjectionState, string> = { pending: "Aguardando", current: "Atual", stale: "Desatualizado", unavailable: "Indisponível", permission_denied: "Sem permissão", reference_missing: "Referência ausente" };
const projectionStateVariant: Record<GithubProjectionState, string> = { pending: "state--off", current: "state--1", stale: "state--2", unavailable: "state--2", permission_denied: "state--3", reference_missing: "state--3" };
const issueStateLabel: Record<GithubIssueState, string> = { unknown: "—", open: "Aberta", closed: "Fechada" };
const pullStateLabel: Record<GithubPullState, string> = { unknown: "—", none: "Sem PR", draft: "Rascunho", open: "Aberto", closed: "Fechado", merged: "Mesclado" };
const reviewStateLabel: Record<GithubReviewState, string> = { unknown: "—", pending: "Em revisão", approved: "Aprovada", changes_requested: "Mudanças pedidas" };
const ciStateLabel: Record<GithubCiState, string> = { unknown: "—", pending: "Em execução", success: "Verde", failure: "Vermelho" };
// **Sem `kpi_baseline`/`kpi_current` desde a decisão C1** do DAP `dap-prove-e-valor-r1`: a medição
// saiu do ativo de solução e virou `Measurement` de um `KPI` (ADR 0055). Enquanto os dois campos
// ficassem aqui, existiriam **dois lugares escrevendo o mesmo número** e valeria o último salvo —
// que é o defeito que a fase inteira desfaz. As duas chaves continuam **saindo** no `GET`
// (derivadas), e é por isso que o painel abaixo as lê; o que sai é a escrita.
const blankEmployeeEdit = { name: "", area: "", status: "building" as DigitalEmployeeStatus, description: "", kpi_label: "", kpi_value: "", kpi_unit: "" as KpiUnit, kpi_direction: "up" as KpiDirection, hours_saved_month: "", roi_month: "" };
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
  const [projections, setProjections] = useState<GithubDeliveryProjection[]>([]);
  const [timeline, setTimeline] = useState<ProjectTimeline | null>(null);
  const [error, setError] = useState("");
  // O que a extração acabou de mapear. Fica na tela porque o **resultado mora em outro lugar**: o
  // processo é ancorado no cliente (FDD 039), não no projeto, então sem esta linha o sucesso seria
  // silêncio — a pessoa clica, nada muda aqui, e não há como distinguir isso de uma falha.
  const [processosMapeados, setProcessosMapeados] = useState(0);
  const [milestoneDraft, setMilestoneDraft] = useState({ title: "", due_date: "" });
  const [taskDraft, setTaskDraft] = useState({ title: "", due_date: "", milestone: "" });
  const [meetingDraft, setMeetingDraft] = useState(blankMeeting);
  const [pendenciaDraft, setPendenciaDraft] = useState<{ title: string; party: Party }>({ title: "", party: "provider" });
  const [decisaoDraft, setDecisaoDraft] = useState({ title: "", rationale: "", decided_by: "", project_phase: "" });
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
  const [showArchivedEmployees, setShowArchivedEmployees] = useState(false);
  const [editingEmployee, setEditingEmployee] = useState<DigitalEmployee | null>(null);
  const [employeeEdit, setEmployeeEdit] = useState(blankEmployeeEdit);
  const [archivingEmployee, setArchivingEmployee] = useState<DigitalEmployee | null>(null);
  const [employeeBusy, setEmployeeBusy] = useState(false);
  const [editing, setEditing] = useState(false);
  const [editDraft, setEditDraft] = useState({ name: "", description: "", status: "", start_date: "", due_date: "", service: "", actual_value: "", cost: "" });
  // ---- Feasibility, PROVE, KPI e medições (FDD 049, DAP `dap-prove-e-valor-r1`) ----
  // Carga própria, como a do roster e a das projeções do GitHub: um tropeço aqui não pode derrubar
  // o resto do detalhe do projeto, e o erro destes painéis é o deles — o board o desenha dentro do
  // painel, com o texto do backend.
  const [laudos, setLaudos] = useState<FeasibilityAssessment[]>([]);
  const [experimentos, setExperimentos] = useState<ProveExperiment[]>([]);
  const [kpis, setKpis] = useState<KPI[]>([]);
  const [medicoes, setMedicoes] = useState<Record<number, Measurement[]>>({});
  const [hipoteses, setHipoteses] = useState<Record<number, SolutionHypothesis>>({});
  const [proveErro, setProveErro] = useState("");
  const [proveCarregadoEm, setProveCarregadoEm] = useState("");
  const [proveBusy, setProveBusy] = useState(false);
  const [lacunaDe, setLacunaDe] = useState<ProveExperiment | null>(null);
  const [lacunaDraft, setLacunaDraft] = useState({ gap_waiver: "", gap_waiver_by: "" });

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
  const loadTimeline = useCallback(
    () => api<ProjectTimeline>(`/projects/${id}/timeline/`).then(setTimeline).catch(() => setTimeline(null)),
    [id],
  );
  useEffect(() => { void load(); }, [load]);
  useEffect(() => { void loadTimeline(); }, [loadTimeline]);

  // Projeção de entrega GitHub (FDD 041): leitura à parte da carga principal, para uma folga do
  // GitHub não derrubar o resto do detalhe do projeto. A listagem não depende da flag — só o
  // mapeamento e a reconciliação (503 fail-closed); vazio quando não há referência.
  const loadProjections = useCallback(() => api<GithubDeliveryProjection[]>(`/github-projections/?project=${id}`).then(setProjections).catch(() => setProjections([])), [id]);
  useEffect(() => { void loadProjections(); }, [loadProjections]);

  /**
   * Os dois painéis da Fase 5, e **o que decide se eles existem é a jornada**.
   *
   * Decisão **A1** do DAP: visíveis só quando o projeto tem a fase canônica correspondente
   * (`JourneyPhase.canonical_stage` ∈ `feasibility`/`prove`) — um projeto de Discovery Sprint não
   * mostra painel de PROVE, e a página só cresce onde a fase existe. A condição também evita a
   * requisição: não há por que buscar laudo de um projeto que não tem gate de Feasibility.
   *
   * Os KPIs, esses, são buscados **sempre**: o painel do Time Digital precisa deles para nomear o
   * indicador que o ativo referencia (decisão C1), e o KPI migrado da era anterior pende do
   * projeto sem experimento nenhum (ADR 0055).
   */
  const temFaseFeasibility = phases.some(phase => phase.canonical_stage === "feasibility");
  const temFaseProve = phases.some(phase => phase.canonical_stage === "prove");
  /**
   * "Carregando" é **derivado**, e não um `setState(true)` no começo da carga: ligar a bandeira
   * sincronicamente de dentro do efeito é renderização em cascata, que é o que o
   * `react-hooks/set-state-in-effect` cobra. A chave é a combinação que decide *o que* buscar —
   * quando ela muda (as fases chegam depois do primeiro `load`), a tela volta ao esqueleto em vez
   * de piscar o estado vazio de dados que ainda não foram pedidos.
   *
   * Recarga disparada por ação (iniciar, registrar lacuna) **não** volta ao esqueleto: a chave não
   * mudou, e trocar a lista por barras cinzentas a cada clique esconderia o que acabou de mudar.
   */
  const chaveDaCargaProve = `${id}:${temFaseFeasibility}:${temFaseProve}`;
  const proveCarregando = proveCarregadoEm !== chaveDaCargaProve && !proveErro;
  const carregarProve = useCallback(() => Promise.all([
    listKpis(id),
    temFaseFeasibility ? listFeasibilityAssessments(id) : Promise.resolve([]),
    temFaseProve ? listProveExperiments(id) : Promise.resolve([]),
  ]).then(async ([loadedKpis, loadedLaudos, loadedExperimentos]) => {
    // A hipótese avaliada chega por id nos dois recursos, e é o texto dela que o board mostra
    // ("Hipótese de solução avaliada: …"). Buscar uma por id, deduplicado, custa menos que varrer
    // as oportunidades da conta — e o laudo sem a aposta que ele avalia é um veredito sobre coisa
    // nenhuma.
    const idsDeHipoteses = [...new Set([...loadedLaudos, ...loadedExperimentos].map(item => item.solution_hypothesis))];
    const [carregadas, leituras] = await Promise.all([
      Promise.all(idsDeHipoteses.map(hipoteseId => api<SolutionHypothesis>(`/solution-hypotheses/${hipoteseId}/`))),
      Promise.all(loadedKpis.map(kpi => listMeasurements(kpi.id))),
    ]);
    setProveErro("");
    setKpis(loadedKpis); setLaudos(loadedLaudos); setExperimentos(loadedExperimentos);
    setHipoteses(Object.fromEntries(carregadas.map(hipotese => [hipotese.id, hipotese])));
    setMedicoes(Object.fromEntries(loadedKpis.map((kpi, indice) => [kpi.id, leituras[indice]])));
    setProveCarregadoEm(`${id}:${temFaseFeasibility}:${temFaseProve}`);
  }).catch((cause: unknown) => setProveErro(mensagemDeFalha(cause))),
  [id, temFaseFeasibility, temFaseProve]);
  useEffect(() => { void carregarProve(); }, [carregarProve]);

  async function iniciarProve(experimento: ProveExperiment) {
    setProveErro(""); setProveBusy(true);
    try { await startProveExperiment(experimento.id); await carregarProve(); }
    catch (cause) { setProveErro(mensagemDeFalha(cause)); }
    finally { setProveBusy(false); }
  }
  async function registrarLacuna(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!lacunaDe) return;
    setProveErro(""); setProveBusy(true);
    try {
      await registerProveGapWaiver(lacunaDe.id, {
        gap_waiver: lacunaDraft.gap_waiver, gap_waiver_by: Number(lacunaDraft.gap_waiver_by),
      });
      setLacunaDe(null); setLacunaDraft({ gap_waiver: "", gap_waiver_by: "" });
      await carregarProve();
    } catch (cause) { setProveErro(mensagemDeFalha(cause)); }
    finally { setProveBusy(false); }
  }

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
    try { const updated = await api<ProjectPhase[]>(`/projects/${id}/advance-phase/`, { method: "POST" }); setPhases(updated); await loadTimeline(); }
    catch (cause) { setError((cause as Error).message); }
  }
  async function applyGate(decision: GateDecision, notes: string) {
    setError("");
    try { const updated = await api<ProjectPhase[]>(`/projects/${id}/apply-gate/`, { method: "POST", body: JSON.stringify({ decision, notes }) }); setPhases(updated); await loadTimeline(); }
    catch (cause) { setError((cause as Error).message); }
  }
  // A espera é ação de detalhe do projeto (POST), como avançar fase: a Entrega alcança no projeto
  // de que participa, Vendas toma 403. O backend grava um `PhaseEvent` — por isso a lista de fases
  // volta e o histórico é recarregado (FDD 042).
  async function setWaiting(waitingParty: WaitingParty, note: string) {
    setError("");
    try { const updated = await api<ProjectPhase[]>(`/projects/${id}/set-waiting/`, { method: "POST", body: JSON.stringify({ waiting_party: waitingParty, note }) }); setPhases(updated); await loadTimeline(); }
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
    try { await api("/decisoes/", { method: "POST", body: JSON.stringify({ project: id, ...decisaoDraft, project_phase: Number(decisaoDraft.project_phase) }) }); setDecisaoDraft({ title: "", rationale: "", decided_by: "", project_phase: "" }); await load(); }
    catch (cause) { setError((cause as Error).message); }
  }
  async function setDecisaoPhase(decisaoId: number, projectPhase: string) {
    try { await api(`/decisoes/${decisaoId}/`, { method: "PATCH", body: JSON.stringify({ project_phase: Number(projectPhase) }) }); await load(); }
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
    // **Sem `kpi_baseline`** (ADR 0055): o backend deixou de aceitá-lo, e o "antes" passou a ser
    // uma `Measurement(kind=baseline)` registrada no PROVE. O ativo nasce sem KPI e depois
    // referencia um.
    try { await api(`/projects/${id}/digital-employees/from-blueprint/`, { method: "POST", body: JSON.stringify({ blueprint: Number(blueprintDraft) }) }); setBlueprintDraft(""); await loadEmployees(); }
    catch (cause) { setError((cause as Error).message); }
  }
  function openEmployeeEdit(employee: DigitalEmployee) {
    setEmployeeEdit({
      name: employee.name, area: employee.area, status: employee.status, description: employee.description,
      kpi_label: employee.kpi_label, kpi_value: employee.kpi_value,
      kpi_unit: employee.kpi_unit, kpi_direction: employee.kpi_direction,
      hours_saved_month: employee.hours_saved_month, roi_month: employee.roi_month,
    });
    setEditingEmployee(employee);
  }
  async function saveEmployee(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!editingEmployee) return;
    setEmployeeBusy(true);
    try {
      // Os campos que nenhuma tela alcançava — e que o snapshot leva à tela do cliente.
      // Vazio vira "0" nos decimais porque o serializer os recusa em branco.
      //
      // **`kpi_baseline`/`kpi_current` não vão mais no corpo** (decisão C1). O servidor já os
      // ignora desde a ADR 0055, então continuar enviando-os não quebraria nada — e é exatamente
      // por isso que a linha precisa sair aqui: campo morto que o servidor aceita em silêncio é o
      // que faz a próxima pessoa acreditar que a tela ainda escreve a medição.
      await api(`/digital-employees/${editingEmployee.id}/`, { method: "PATCH", body: JSON.stringify({
        ...employeeEdit,
        hours_saved_month: employeeEdit.hours_saved_month || "0",
        roi_month: employeeEdit.roi_month || "0",
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

  /**
   * Quem pode assinar uma lacuna aprovada.
   *
   * `/users/` é fechado a admin (RFC 0003), então a Entrega — que é quem toca o PROVE — não tem a
   * lista completa. A equipe do projeto é a lista que ela **já** tem carregada, e é a resposta
   * certa para a pergunta na prática: quem aprova uma lacuna de um experimento participa dele.
   * Admin, que tem as duas, usa a lista cheia.
   */
  const aprovadores = people.length
    ? people.map(person => ({ id: person.id, nome: person.first_name || person.username }))
    : members.map(member => ({ id: member.user, nome: member.user_name || member.user_username }));
  const nomeDoAprovador = (userId: number | null) =>
    aprovadores.find(pessoa => pessoa.id === userId)?.nome ?? "alguém não identificado";

  return <section className="space-y-7">
    {editingEmployee && <Modal title={`Editar ${editingEmployee.name}`} onClose={() => setEditingEmployee(null)}>
      {/* Os seis campos, e não os dois do formulário rápido: eles cruzam ao painel "Seu Time
          Digital" do cliente pelo snapshot (ADR 0003) e nenhuma tela os alcançava. Eram oito até a
          decisão C1 — o par medido saiu, e agora ele se lê no painel, vindo do PROVE. */}
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
        {/* **"Antes (base)" e "Depois (atual)" saíram daqui** (decisão C1 do DAP
            `dap-prove-e-valor-r1`). Quem media pelo formulário passa a medir pelo PROVE: o antes e
            o depois são o *mesmo* KPI em momentos diferentes, e enquanto o ativo os possuísse eles
            seriam duas colunas afirmando ser dois fatos. Unidade e direção também são do `KPI`
            agora — os campos abaixo sobrevivem porque o One ainda os lê do ativo
            (`portal.build_snapshot`), e mexer nisso é outro gate. */}
        <div className="form-grid">
          <label className="form-label">Unidade do KPI<select className="field" value={employeeEdit.kpi_unit} onChange={event => setEmployeeEdit({ ...employeeEdit, kpi_unit: event.target.value as KpiUnit })}>{kpiUnits.map(unit => <option key={unit.value} value={unit.value}>{unit.label}</option>)}</select></label>
          <label className="form-label">Direção<select className="field" value={employeeEdit.kpi_direction} onChange={event => setEmployeeEdit({ ...employeeEdit, kpi_direction: event.target.value as KpiDirection })}><option value="up">Maior é melhor</option><option value="down">Menor é melhor</option></select></label>
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
    {/* A saída explícita da decisão **E1**: "registrar lacuna aprovada" pede **quem aprovou e por
        quê**. É um ato assinado — o servidor recusa `gap_waiver` sem `gap_waiver_by` com 400 —, e
        o autor vem do corpo e não da sessão porque quem aprova pode não ser quem digita. */}
    {lacunaDe && <Modal title="Registrar lacuna aprovada" onClose={() => setLacunaDe(null)}>
      <form className="grid gap-4" onSubmit={event => void registrarLacuna(event)}>
        <p className="text-sm text-slate-600">O PROVE começa sem um dos três requisitos, e o registro fica com nome e motivo. Sem isso, a invariante viraria sugestão.</p>
        <label className="form-label">Quem aprovou
          <select className="field" value={lacunaDraft.gap_waiver_by} onChange={event => setLacunaDraft({ ...lacunaDraft, gap_waiver_by: event.target.value })} required>
            <option value="">Selecione uma pessoa</option>
            {aprovadores.map(pessoa => <option key={pessoa.id} value={pessoa.id}>{pessoa.nome}</option>)}
          </select>
        </label>
        <label className="form-label">Por quê
          <textarea className="field min-h-20" value={lacunaDraft.gap_waiver} onChange={event => setLacunaDraft({ ...lacunaDraft, gap_waiver: event.target.value })} placeholder="O que falta, e por que começar assim mesmo é a decisão certa" required />
        </label>
        <div className="flex flex-wrap justify-end gap-3">
          <button type="button" className="btn btn--secondary" onClick={() => setLacunaDe(null)}>Cancelar</button>
          <button type="submit" className="btn" disabled={proveBusy}><Save className="size-4" />{proveBusy ? "Registrando…" : "Registrar lacuna"}</button>
        </div>
      </form>
    </Modal>}
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
      onApplyGate={(decision, notes) => void applyGate(decision, notes)}
    />

    {/* Os dois painéis da Fase 5, **logo abaixo da Jornada** (decisão A1 do DAP
        `dap-prove-e-valor-r1`): a decisão que eles sustentam é a decisão de gate da fase, e ela
        mora ali em cima. Visíveis só quando a fase canônica correspondente existe — um projeto de
        Discovery Sprint não mostra painel de PROVE. */}
    {temFaseFeasibility && <PainelDeFeasibility laudos={laudos} hipoteses={hipoteses} carregando={proveCarregando} erro={proveErro} />}
    {temFaseProve && <PainelDeProve
      experimentos={experimentos} kpis={kpis} medicoes={medicoes} hipoteses={hipoteses}
      carregando={proveCarregando} erro={proveErro} canManage={canManageJourney} busy={proveBusy}
      nomeDe={nomeDoAprovador}
      onIniciar={experimento => void iniciarProve(experimento)}
      onLacuna={experimento => { setLacunaDe(experimento); setLacunaDraft({ gap_waiver: experimento.gap_waiver, gap_waiver_by: experimento.gap_waiver_by ? String(experimento.gap_waiver_by) : "" }); }}
    />}

    {timeline && Array.isArray(timeline.events) && <DeliveryTimelinePanel timeline={timeline} canManage={canManageJourney} onSetWaiting={(party, note) => void setWaiting(party, note)} />}

    {health &&<div className="flex items-center gap-2 text-sm"><span className="font-medium text-slate-600">Saúde do projeto:</span><HealthBadge level={health.level} score={health.score} />{health.signals.length === 0 && <span className="text-slate-600">sem sinais de alerta</span>}</div>}

    {project?.ai_scored_at && <AiScorePanel project={project} canManage={canManageJourney} onTogglePublish={next => void toggleAiScorePublish(next)} />}

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
        <div className="flex items-center justify-between gap-2"><p className="text-sm font-semibold text-ink">{employee.name}</p><span className={`state ${employee.status === "active" ? "state--1" : employee.status === "paused" ? "state--off" : "state--2"}`}>{employeeStatusLabel[employee.status]}</span></div>
        {employee.area && <p className="mt-0.5 text-xs text-accent">{employee.area}</p>}
        {employee.description && <p className="mt-1 text-xs text-slate-600">{employee.description}</p>}
        <div className="mt-2 flex flex-wrap gap-x-4 gap-y-1 text-xs text-slate-600">{employee.kpi_label && <span><strong className="text-ink">{employee.kpi_label}:</strong> {employee.kpi_value}</span>}{Number(employee.hours_saved_month) > 0 && <span>{Number(employee.hours_saved_month)}h/mês</span>}{Number(employee.roi_month) > 0 && <span>ROI {money.format(Number(employee.roi_month))}/mês</span>}</div>
        {/* **Decisão C1**: o ativo *referencia* o KPI, não o possui. O que aparece aqui é
            leitura — `kpi_baseline` e `kpi_current` continuam saindo no `GET`, derivados da
            baseline viva e do Outcome mais recente (ADR 0055) —, e a escrita mora no PROVE. */}
        {employee.kpi !== null && (() => {
          const kpiDoAtivo = kpis.find(kpi => kpi.id === employee.kpi);
          return <div className="mt-3 border-t border-dashed border-line pt-3">
            <p className="text-xs font-semibold text-ink">KPI referenciado</p>
            <p className="mt-0.5 text-xs text-slate-600">{kpiDoAtivo?.name || employee.kpi_label || "Indicador"}{kpiDoAtivo?.prove_experiment != null ? " · medido no PROVE" : " · sem experimento"}</p>
            <ParDeMedicao antes={employee.kpi_baseline} depois={employee.kpi_current} direcao={kpiDoAtivo?.direction ?? employee.kpi_direction} />
            {temFaseProve && kpiDoAtivo?.prove_experiment != null && <a className="back-link mt-1 text-xs" href="#prove">Ver no PROVE<ChevronRight className="size-3.5" /></a>}
          </div>;
        })()}
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
      <div className="flex items-center gap-3"><span className={`state ${risk.level === "alto" ? "state--3" : risk.level === "médio" ? "state--2" : "state--1"}`}>Risco {risk.level}</span><h2 className="font-semibold text-ink">Sinais de atraso</h2></div>
      <ul className="mt-3 space-y-1.5 text-sm text-slate-600">{risk.signals.map((signal, index) => <li className="flex gap-2" key={index}><AlertTriangle className="mt-0.5 size-4 shrink-0 text-danger" /><span><strong className="text-ink">{signal.label}:</strong> {signal.detail}</span></li>)}</ul>
      {risk.forecast && <p className={`mt-3 text-sm font-medium ${risk.forecast.delay_days > 0 ? "text-danger" : "text-slate-600"}`}>Previsão de término: {formatDate(risk.forecast.predicted_finish_date)}{risk.forecast.delay_days > 0 ? ` — atraso previsto de ${risk.forecast.delay_days} dia(s)` : " — dentro do prazo"} <span className="text-slate-600">({risk.forecast.basis})</span></p>}
    </section>}

    {/* Projeção de entrega GitHub (FDD 041, ADR 0046): leitura do estado de engenharia. Distingue
        estado confirmado de desatualizado/indisponível — nunca inventa status. Somente-leitura: o
        Pulse não é a fonte da verdade de Issue/PR/CI. */}
    <section className="panel sm:p-6">
      <div className="flex items-center gap-3"><span className="metric-icon"><Workflow className="size-4" /></span><div><h2 className="font-semibold text-ink">Entrega de engenharia (GitHub)</h2><p className="text-sm text-slate-600">Estado projetado de Issue, PR e CI. O Pulse lê do GitHub e não é a fonte da verdade.</p></div></div>
      {projections.length ? <div className="mt-4 space-y-3">{projections.map(proj => <article className="rounded-xl border bg-slate-50/50 p-4" key={proj.id}>
        <div className="flex flex-wrap items-center justify-between gap-2">
          <a className="inline-flex items-center gap-1.5 text-sm font-semibold text-ink hover:text-accent" href={proj.issue_url || `https://github.com/${proj.repository}/issues/${proj.issue_number}`} target="_blank" rel="noreferrer">{proj.repository}#{proj.issue_number}<ExternalLink className="size-3.5 text-accent" /></a>
          <span className={`state ${projectionStateVariant[proj.state]}`}>{projectionStateLabel[proj.state]}</span>
        </div>
        <div className="mt-2 flex flex-wrap gap-x-4 gap-y-1 text-xs text-slate-600">
          <span><strong className="text-ink">Issue:</strong> {issueStateLabel[proj.issue_state]}</span>
          <span><strong className="text-ink">PR:</strong> {pullStateLabel[proj.pr_state]}{proj.pr_number ? ` #${proj.pr_number}` : ""}</span>
          <span><strong className="text-ink">Revisão:</strong> {reviewStateLabel[proj.review_state]}</span>
          <span><strong className="text-ink">CI:</strong> {ciStateLabel[proj.ci_state]}</span>
          {proj.head_sha && <span><strong className="text-ink">SHA:</strong> {proj.head_sha.slice(0, 7)}</span>}
        </div>
        <p className="mt-2 text-xs text-slate-600">{proj.observed_at ? `Confirmado em ${new Date(proj.observed_at).toLocaleString("pt-BR")}` : "Ainda não confirmado pelo GitHub."}{proj.last_error_message ? ` · ${proj.last_error_message}` : ""}</p>
      </article>)}</div> : <p className="mt-4 empty-state">Nenhuma referência de engenharia mapeada.</p>}
    </section>

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
            <button type="button" onClick={() => void toggleMeeting(meeting)} aria-label={meeting.status === "held" ? `Marcar ${meeting.title} como agendada` : `Marcar ${meeting.title} como realizada`} className={`state shrink-0 transition hover:ring-2 hover:ring-accent/30 ${meeting.status === "held" ? "state--1" : "state--off"}`}>{meeting.status === "held" ? "Realizada" : "Agendada"}</button>
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
        {phases.length ? <form className="grid gap-3" onSubmit={event => void createDecisao(event)}>
          <div className="grid gap-3 sm:grid-cols-[1fr_0.8fr]">
            <label className="form-label">Título<input className="field" placeholder="O que foi decidido" value={decisaoDraft.title} onChange={event => setDecisaoDraft({ ...decisaoDraft, title: event.target.value })} required /></label>
            <label className="form-label">Fase da jornada<select className="field" value={decisaoDraft.project_phase} onChange={event => setDecisaoDraft({ ...decisaoDraft, project_phase: event.target.value })} required><option value="">Selecione a fase</option>{phases.map(phase => <option key={phase.id} value={phase.id}>{phase.phase_name}</option>)}</select></label>
          </div>
          <div className="flex gap-2"><input className="field min-w-0 flex-1" placeholder="Quem decidiu (opcional)" value={decisaoDraft.decided_by} onChange={event => setDecisaoDraft({ ...decisaoDraft, decided_by: event.target.value })} /><button className="btn btn--icon" aria-label="Adicionar decisão" type="submit"><Plus className="size-4" /></button></div>
          <textarea className="field min-h-20" placeholder="Por quê — o que pesou, e o que foi descartado" value={decisaoDraft.rationale} onChange={event => setDecisaoDraft({ ...decisaoDraft, rationale: event.target.value })} />
        </form> : <div className="empty-state"><p className="font-semibold text-ink">Configure a jornada antes de publicar decisões</p><p className="mt-1">Uma decisão precisa apontar para uma fase existente.</p><a className="btn btn--secondary mt-3" href="/jornada">Ver jornada</a></div>}
        {decisoes.length ? <div className="divide-y">{decisoes.map(decisao => {
          const published = decisao.status === "published";
          const decisionPhase = phases.find(phase => phase.id === decisao.project_phase);
          return <div className="py-3" key={decisao.id}>
            <div className="flex items-start gap-3">
              <span className="metric-icon shrink-0"><Scale className="size-4" /></span>
              <div className="min-w-0 flex-1">
                <p className="text-sm font-medium text-ink">{decisao.title}</p>
                {decisao.rationale && <p className="mt-0.5 text-xs text-slate-600">{decisao.rationale}</p>}
                <p className="mt-0.5 text-xs text-slate-600">{[decisao.decided_by, decisao.decided_on && formatDate(decisao.decided_on)].filter(Boolean).join(" · ") || "Sem autoria registrada"}</p>
                {decisionPhase && <p className="mt-1"><span className="state state--off">Fase · {decisionPhase.phase_name}</span></p>}
                {!decisao.project_phase && <div className="mt-2 grid gap-2 sm:grid-cols-[1fr_auto] sm:items-end"><label className="form-label">Vincular à fase<select className="field" aria-label={`Fase de ${decisao.title}`} defaultValue="" onChange={event => { if (event.target.value) void setDecisaoPhase(decisao.id, event.target.value); }}><option value="">Selecione a fase</option>{phases.map(phase => <option key={phase.id} value={phase.id}>{phase.phase_name}</option>)}</select></label><span className="state state--2">Ação necessária</span></div>}
              </div>
              <button type="button" disabled={!published && !decisao.project_phase} onClick={() => void toggleDecisao(decisao.id, published)} aria-label={published ? `Despublicar ${decisao.title}` : `Publicar ${decisao.title}`} className={`state shrink-0 transition hover:ring-2 hover:ring-accent/30 disabled:cursor-not-allowed disabled:opacity-50 ${published ? "state--1" : "state--off"}`}>{published ? "Publicada" : "Rascunho"}</button>
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
      <ScoreBar label="Oportunidade" value={project.ai_potential} tone="positive" />
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
  onApplyGate: (decision: GateDecision, notes: string) => void;
};

function JourneySection({ phases, canManage, onAdvance, onMark, onSetTarget, onToggleChecklist, onSaveWaiver, onApplyGate }: JourneySectionProps) {
  const [gateNotes, setGateNotes] = useState("");
  const [waiverDraft, setWaiverDraft] = useState<string | null>(null);
  const [confirming, setConfirming] = useState<GateDecision | null>(null);
  if (!phases.length) return null;
  const done = phases.filter(phase => phase.status === "done").length;
  const active = phases.find(phase => phase.status === "active");
  const next = active ? phases.find(phase => phase.phase_position > active.phase_position) : undefined;
  const pct = Math.round((done / phases.length) * 100);
  const checklist = active?.checklist_items ?? [];
  const pending = checklist.filter(item => !item.checked).length;
  // O vocabulário do gate sai da fase ativa (ADR 0053), de um mapa só em `journey.ts`.
  const stage = active?.canonical_stage ?? "";
  const decisoes = gateDecisions(stage);
  const reabre = gateDecisionByEffect(stage, "reopen");
  const para = gateDecisionByEffect(stage, "halt");

  return <section id="jornada" className="panel space-y-5 sm:p-6">
    <div className="flex flex-wrap items-center gap-3">
      <span className="metric-icon"><MapPin className="size-4" /></span>
      <div className="flex-1"><h2 className="font-semibold text-ink">Jornada de Transformação</h2><p className="text-sm text-slate-600">{done} de {phases.length} fases concluídas</p></div>
      <span className="eyebrow">{pct}%</span>
    </div>

    <div className="h-2 rounded-full bg-slate-100"><div className="h-2 rounded-full bg-ink transition-all" style={{ width: `${pct}%` }} /></div>

    <div className="flex flex-wrap gap-2">{phases.map(phase => {
      const isDone = phase.status === "done"; const isActive = phase.status === "active";
      return <span key={phase.id} className="inline-flex items-center gap-1.5">
        <span className={`state ${isDone ? "state--1" : isActive ? "state--active" : "state--off"}`}>{isDone ? <CheckCircle2 className="size-3.5" /> : isActive ? <MapPin className="size-3.5" /> : <Lock className="size-3.5" />}{phase.phase_name}</span>
        {/* O selo do gate acompanha a fase e não some quando ela fecha: é o registro de *como* a
            jornada passou por ali — inclusive na fase que o REDESIGN trancou. */}
        {phase.gate_decision && <span className={`state ${gateVariant[phase.gate_decision]}`} title={phase.gate_notes || undefined}>{GATE_DECISION_LABEL[phase.gate_decision]}</span>}
      </span>;
    })}</div>

    {active ? <div className="rounded-2xl border bg-slate-50/60 p-4 sm:p-5">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div className="min-w-0"><p className="eyebrow">Você está aqui</p><h3 className="mt-0.5 text-lg font-semibold text-ink">{active.phase_name}</h3>{active.phase_description && <p className="mt-1 text-sm text-slate-600">{active.phase_description}</p>}</div>
        {next && <p className="shrink-0 text-right text-xs text-slate-600">Próxima<span className="mt-0.5 flex items-center gap-1 font-semibold text-slate-600"><ChevronRight className="size-3.5" />{next.phase_name}</span></p>}
      </div>

      {active.deliverables.length > 0 && <div className="mt-4">
        <p className="section-label mb-1">Entregáveis · {active.deliverables.filter(item => item.status === "delivered").length}/{active.deliverables.length}</p>
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
        <p className="section-label mb-1">Checklist de qualidade · {checklist.length - pending}/{checklist.length}</p>
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
        {/* O decision gate (ADR 0030, FDD 033) — e o vocabulário é o da fase (ADR 0053): quatro
            saídas na Feasibility, três no PROVE. Ficam lado a lado porque a metodologia pede uma
            escolha entre elas, não um "avançar" com ressalva escondida atrás de um menu. Quem
            decide o conjunto é `gateDecisions`, o mesmo mapa que a tela de Jornada lê. */}
        <p className="eyebrow">Decision gate</p>
        <p className="mt-1 text-sm text-slate-600">Esta fase termina em decisão. {GATE_DECISION_LABEL[reabre]} reabre a fase anterior; {GATE_DECISION_LABEL[para]} para a jornada aqui.</p>
        <label className="form-label mt-3">Ressalvas, motivo ou condições
          <textarea className="field min-h-16" placeholder={`O que pesou na decisão — obrigatório na prática para ${listar(decisoes.slice(1).map(decision => GATE_DECISION_LABEL[decision]))}`} value={gateNotes} onChange={event => setGateNotes(event.target.value)} />
        </label>
        <div className="mt-3 flex flex-wrap gap-2">{decisoes.map((decision, index) => {
          // A pele sai do efeito, não do valor: a primeira saída de continuidade é a primária
          // (GO, SCALE), a que para pede o vermelho de hover, e as duas irreversíveis passam pela
          // confirmação — clique de descuido em REDESIGN/ITERATE/NO-GO/STOP não pode valer o
          // mesmo que um clique em GO.
          const efeito = GATE_EFFECT[decision];
          const primaria = efeito === "advance" && index === 0;
          const classe = primaria ? "btn" : efeito === "halt" ? "btn btn--secondary btn--secondary-danger" : "btn btn--secondary";
          const confirma = efeito !== "advance";
          return <button key={decision} type="button" className={classe} onClick={() => confirma ? setConfirming(decision) : onApplyGate(decision, gateNotes)}>{primaria && <CheckCircle2 className="size-4" />}{GATE_DECISION_LABEL[decision]}</button>;
        })}</div>
      </div>}

      <div className="mt-4 flex flex-wrap items-end justify-between gap-3">
        {canManage ? <label className="grid gap-1 text-xs font-medium text-slate-600">Previsão desta fase<input className="field w-44" type="date" value={active.target_date ?? ""} onChange={event => onSetTarget(active.id, event.target.value)} /></label> : active.target_date ? <p className="text-sm text-slate-600">Previsão: {formatDate(active.target_date)}</p> : <span />}
        {/* O botão de avançar continua onde estava, e é ele que encosta nos dois gates: quando a
            fase exige decisão ou tem checklist pendente, o 409 do backend vira o alerta da página. */}
        {canManage && <button type="button" className="btn" onClick={onAdvance}><CheckCircle2 className="size-4" />Concluir fase e avançar</button>}
      </div>
    </div> : <div className="flex items-center gap-3 rounded-2xl border border-emerald-100 bg-emerald-50 p-4 text-sm font-medium text-emerald-700"><Trophy className="size-5 shrink-0" />Jornada de transformação concluída — todas as fases entregues.</div>}

    {confirming && <ConfirmDialog
      title={`Registrar ${GATE_DECISION_LABEL[confirming]}`}
      message={GATE_EFFECT[confirming] === "reopen"
        ? <>A fase <strong className="text-ink">{active?.phase_name}</strong> volta para <strong className="text-ink">a fase anterior</strong>, que é reaberta para ser testada de novo. A decisão e o motivo ficam registrados nesta fase.</>
        : <>A jornada <strong className="text-ink">para nesta fase</strong>. Nada é apagado e a fase continua em andamento — o que muda é o registro de que a hipótese não se sustentou.</>}
      confirmLabel={`Registrar ${GATE_DECISION_LABEL[confirming]}`}
      onCancel={() => setConfirming(null)}
      onConfirm={() => { onApplyGate(confirming, gateNotes); setConfirming(null); }}
    />}
  </section>;
}

const eventTime = (iso: string) => new Date(iso).toLocaleString("pt-BR", { day: "2-digit", month: "short", hour: "2-digit", minute: "2-digit" });

type DeliveryTimelinePanelProps = {
  timeline: ProjectTimeline;
  canManage: boolean;
  onSetWaiting: (party: WaitingParty, note: string) => void;
};

// A linha do tempo operacional da entrega (FDD 042): a situação corrente, quem/o quê está sendo
// esperado, o próximo gate e o **histórico append-only**. Distinta da Jornada logo acima: aquela é
// o tracker de fases e os gates; esta é a auditoria — *quando* e *por quê* a jornada se moveu,
// inclusive o que o REDESIGN apaga do estado corrente mas o evento preserva.
function DeliveryTimelinePanel({ timeline, canManage, onSetWaiting }: DeliveryTimelinePanelProps) {
  const current = timeline.current_phase;
  const [party, setParty] = useState<WaitingParty>("");
  const [note, setNote] = useState("");

  return <section className="panel space-y-5 sm:p-6">
    <div className="flex flex-wrap items-center gap-3">
      <span className="metric-icon"><History className="size-4" /></span>
      <div className="flex-1"><h2 className="font-semibold text-ink">Linha do tempo da entrega</h2><p className="text-sm text-slate-600">Situação, bloqueios e histórico auditável</p></div>
      {current && <span className={`state ${situationVariant(current.situation)}`}>{SITUATION_LABEL[current.situation]}</span>}
    </div>

    <div className="grid gap-3 sm:grid-cols-3">
      <div><p className="eyebrow">Fase corrente</p><p className="mt-1 text-sm font-semibold text-ink">{current ? current.phase_name : "Jornada concluída"}</p>{current?.canonical_stage && <p className="text-xs text-slate-600">{CANONICAL_STAGE_LABEL[current.canonical_stage]}</p>}</div>
      <div><p className="eyebrow">Próximo gate</p><p className="mt-1 text-sm font-semibold text-ink">{timeline.next_gate ? timeline.next_gate.phase_name : "Nenhum previsto"}</p></div>
      <div><p className="eyebrow">Próxima fase</p><p className="mt-1 text-sm font-semibold text-ink">{timeline.next_phase ? timeline.next_phase.phase_name : "—"}</p></div>
    </div>

    {/* Quem/o quê a fase corrente espera — legível sem abrir a nota crua (FDD 042). */}
    {current && (current.waiting_party
      ? <div className="rounded-2xl border bg-slate-50/60 p-4">
          <div className="flex flex-wrap items-center gap-2"><Hourglass className="size-4 text-slate-600" /><span className="text-sm font-semibold text-ink">Aguardando {WAITING_PARTY_LABEL[current.waiting_party as Exclude<WaitingParty, "">]}</span></div>
          {current.blocker_note && <p className="mt-1 text-sm text-slate-600">{current.blocker_note}</p>}
          {canManage && <button type="button" className="btn btn--secondary mt-3" onClick={() => onSetWaiting("", "")}><CheckCircle2 className="size-4" />Resolver bloqueio</button>}
        </div>
      : canManage && <div className="rounded-2xl border border-dashed p-4">
          <p className="eyebrow">Registrar espera</p>
          <p className="mt-1 text-sm text-slate-600">De quem ou do quê esta fase depende agora? Fica no histórico.</p>
          <div className="mt-3 grid gap-2 sm:grid-cols-[minmax(0,12rem)_1fr_auto] sm:items-end">
            <label className="form-label">Aguardando<select className="field" value={party} onChange={event => setParty(event.target.value as WaitingParty)}><option value="">Selecione…</option>{WAITING_PARTY_OPTIONS.map(option => <option key={option} value={option}>{WAITING_PARTY_LABEL[option]}</option>)}</select></label>
            <label className="form-label">Nota (opcional)<input className="field" value={note} onChange={event => setNote(event.target.value)} placeholder="O que trava a fase" /></label>
            <button type="button" className="btn" disabled={!party} onClick={() => { onSetWaiting(party, note); setParty(""); setNote(""); }}><Save className="size-4" />Registrar</button>
          </div>
        </div>)}

    <div>
      <p className="section-label mb-1">Histórico · {timeline.events.length} evento(s)</p>
      {timeline.events.length ? <ol className="divide-y">{timeline.events.map(event => <li className="flex flex-wrap items-baseline justify-between gap-x-3 gap-y-1 py-2.5" key={event.id}>
        <div className="min-w-0"><p className="text-sm font-medium text-ink">{PHASE_EVENT_LABEL[event.kind]}{event.phase_name ? ` · ${event.phase_name}` : ""}</p>{(event.note || event.gate_decision || event.waiting_party) && <p className="mt-0.5 text-xs text-slate-600">{event.gate_decision ? `${GATE_DECISION_LABEL[event.gate_decision]}. ` : ""}{event.waiting_party ? `${WAITING_PARTY_LABEL[event.waiting_party as Exclude<WaitingParty, "">]}. ` : ""}{event.note}</p>}</div>
        <time className="shrink-0 text-xs text-slate-600">{eventTime(event.created_at)}{event.actor_name ? ` · ${event.actor_name}` : " · sistema"}</time>
      </li>)}</ol> : <p className="empty-state">Sem eventos ainda.</p>}
    </div>
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

// -----------------------------------------------------------------------------------------------
// Feasibility, PROVE e a linha do KPI — FDD 049, ADR 0055
//
// Governados pelo DAP `docs/design/dap-prove-e-valor-r1/`, revisão 1, decisões
// **A1 · B1 · C1 · D1 · E1**. Mudar a superfície exige revisão nova do pacote, não julgamento na
// hora.
//
// **A1 — painéis do projeto, e não tela própria.** O laudo de Feasibility existe para sustentar um
// `GO`/`CONDITIONAL GO`/`REDESIGN`/`NO-GO` e o PROVE um `SCALE`/`ITERATE`/`STOP` (ADR 0053).
// Separar o conteúdo da decisão em outra tela faria a pessoa decidir num lugar e ler a prova em
// outro — que é como se decide sem ler. O custo (esta é a tela mais longa do produto) é pago pela
// visibilidade condicional: a fase canônica é que diz se o painel existe.
//
// **A decisão de gate nunca aparece rotulada como resultado** (`language-map` §6.3). Ela é a
// mesma pílula que a Jornada já desenha, com o mesmo `gateVariant` e o mesmo
// `GATE_DECISION_LABEL` de `journey.ts` — um segundo mapa aqui divergiria do primeiro em silêncio.
// -----------------------------------------------------------------------------------------------

/**
 * O símbolo da unidade é **copy da tela**, não dado da API: o servidor publica a chave (`hours`) e
 * o rótulo (`Horas`), e é a superfície que decide escrever "h" ao lado do número. É a mesma razão
 * de `prove.o_que_falta_para_iniciar` devolver chaves em vez de frases.
 */
const KPI_UNIT_SYMBOL: Record<KpiUnit, string> = { "": "", percent: "%", hours: "h", minutes: "min", currency: "R$", count: "un" };

// Variante, nunca a cor (ADR 0026). Os três rótulos são os do board — que abrevia "Com ressalva"
// para "Ressalva", porque a pílula divide a linha com o texto do eixo.
const VERDICT_VARIANT: Record<FeasibilityVerdict, string> = { favorable: "state--1", caveat: "state--2", unfavorable: "state--3" };
const VERDICT_LABEL: Record<FeasibilityVerdict, string> = { favorable: "Favorável", caveat: "Ressalva", unfavorable: "Desfavorável" };

// `planned` é o **neutro**: um experimento que ainda não começou não é aviso, no molde de
// "Arquivado" e da fase `pending` da jornada.
const PROVE_STATUS_VARIANT: Record<ProveExperimentStatus, string> = { planned: "state--off", running: "state--0", concluded: "state--1" };

/**
 * Os três requisitos da invariante, **na ordem de `prove.REQUISITOS`** — e os rótulos são daqui.
 *
 * A tela desenha as pastilhas a partir de `missing_to_start`, que o servidor deriva da mesma
 * função que a action `start/` usa para recusar. Recalcular a regra aqui habilitaria o botão de um
 * `POST` que o servidor nega, e nada ficaria vermelho (decisão E1).
 */
const REQUISITOS_DO_PROVE: ReadonlyArray<readonly [ProveMissingRequirement, string]> = [
  ["kpi", "KPI definido"],
  ["success_criteria", "Critério de sucesso"],
  ["baseline", "Baseline medida"],
];

const dataCurta = (iso: string) => new Date(iso).toLocaleDateString("pt-BR");

/**
 * O número de uma medição. **`null` é "não medido", e sai como `—` — nunca `0`.**
 *
 * Zero afirmaria que o processo não custava nada antes; a lacuna admitida é sempre melhor que a
 * lacuna disfarçada de medição. É a mesma regra de `Process.custo_do_estado_atual` com
 * `nao_apurado`, e a razão de ser do pacote inteiro.
 */
const numeroDoKpi = (valor: string | null | undefined) =>
  valor === null || valor === undefined || valor === ""
    ? "—"
    : Number(valor).toLocaleString("pt-BR", { maximumFractionDigits: 2 });

/**
 * A variação entre baseline e outcome, ou `null` quando ela **não existe**.
 *
 * Não existe em três casos, e os três viram "variação —" na tela: falta a baseline, falta o
 * outcome, ou a baseline é zero — de zero não se calcula variação percentual, e um `∞` ali seria
 * pior que a lacuna. O sinal do bem e do mal sai da **direção do KPI**: cair 74% é sucesso quando
 * menor é melhor e é o contrário quando não é.
 */
function variacaoDoKpi(antes: string | null, depois: string | null, direcao: KpiDirection): { texto: string; variante: string } | null {
  if (antes === null || depois === null) return null;
  const base = Number(antes); const atual = Number(depois);
  if (!Number.isFinite(base) || !Number.isFinite(atual) || base === 0) return null;
  const percentual = Math.round(((atual - base) / Math.abs(base)) * 100);
  if (percentual === 0) return { texto: "0%", variante: "state--off" };
  const melhorou = direcao === "up" ? percentual > 0 : percentual < 0;
  // O sinal de menos é o tipográfico (U+2212), como no board: o hífen do teclado quebra a linha
  // em coluna estreita, e a tabela de números do `.metric-card` já usa `tabular-nums` por isso.
  return { texto: `${percentual > 0 ? "+" : "−"}${Math.abs(percentual)}%`, variante: melhorou ? "state--1" : "state--3" };
}

/**
 * `Baseline → Outcome · variação` — a decisão **B1**, num componente só.
 *
 * Baseline e outcome **são o mesmo KPI em momentos diferentes**, e é essa a frase central da
 * fatia: mostrar só a leitura vigente reintroduziria na leitura a fusão que o modelo desfaz na
 * escrita — sem o par, "1h05" não diz se melhorou.
 *
 * Mora em `.row-meta` e não em irmãos soltos dentro do `.row-main`: a primitiva sobrescreve
 * `display` e cor de qualquer `span`/`strong` aninhado, e o cluster viraria três linhas empilhadas
 * em cinza. `.row-meta` é posicionamento puro e força a própria linha dentro da mesma `.row`, que
 * é justamente o que a linha do KPI precisa em 390px.
 */
function ParDeMedicao({ antes, depois, direcao }: { antes: string | null; depois: string | null; direcao: KpiDirection }) {
  const variacao = variacaoDoKpi(antes, depois, direcao);
  return <div className="row-meta tabular-nums">
    <span className="sr-only">Baseline:</span>
    <span className="type-body text-muted">{numeroDoKpi(antes)}</span>
    <span aria-hidden="true" className="text-muted">→</span>
    <span className="sr-only">atual:</span>
    <span className="type-title text-ink">{numeroDoKpi(depois)}</span>
    {variacao
      ? <span className={`state ${variacao.variante}`}>{variacao.texto}</span>
      : <span className="type-body text-muted">variação —</span>}
  </div>;
}

/**
 * O histórico completo de leituras, colapsado (decisão **B1**).
 *
 * As medições vêm do servidor em ordem decrescente (`-measured_at`) e aqui sobem em ordem
 * cronológica: o histórico é uma série, e ler uma série de trás para a frente esconde justamente o
 * movimento que ela existe para mostrar. A baseline e a leitura mais recente ganham sufixo — são
 * os dois números que a linha acima compara.
 */
function HistoricoDeMedicoes({ medicoes }: { medicoes: Measurement[] }) {
  if (!medicoes.length) return null;
  const emOrdem = [...medicoes].sort((a, b) => a.measured_at.localeCompare(b.measured_at) || a.id - b.id);
  const ultimoOutcome = [...emOrdem].reverse().find(medicao => medicao.kind === "outcome");
  return <details className="basis-full">
    <summary className="type-meta cursor-pointer text-brand-600">Ver histórico de medições ({emOrdem.length})</summary>
    <ul className="mt-2 grid gap-1">{emOrdem.map(medicao => <li className="flex justify-between gap-3 border-t border-line pt-1 first:border-t-0 first:pt-0" key={medicao.id}>
      <span className="type-meta text-muted">{dataCurta(medicao.measured_at)}{medicao.kind === "baseline" ? " · baseline" : medicao.id === ultimoOutcome?.id ? " · atual" : ""}</span>
      <span className="type-meta tabular-nums text-muted">{numeroDoKpi(medicao.value)}</span>
    </li>)}</ul>
  </details>;
}

/** O mesmo esqueleto de `animate-pulse`/`bg-slate-200` que a página já usa — não um terceiro. */
function EsqueletoDoPainel() {
  return <div className="animate-pulse space-y-3"><div className="h-5 w-2/3 rounded-xl bg-slate-200" /><div className="h-16 rounded-xl bg-slate-200" /></div>;
}

function CabecalhoVazio({ icone, titulo, apoio, children }: { icone: ReactNode; titulo: string; apoio: string; children: ReactNode }) {
  return <section className="panel space-y-4 sm:p-6">
    <div className="flex min-w-0 items-center gap-3">
      <span className="metric-icon">{icone}</span>
      <div><h2 className="font-semibold text-ink">{titulo}</h2><p className="text-sm text-slate-600">{apoio}</p></div>
    </div>
    {children}
  </section>;
}

type PainelDeFeasibilityProps = {
  laudos: FeasibilityAssessment[];
  hipoteses: Record<number, SolutionHypothesis>;
  carregando: boolean;
  erro: string;
};

/**
 * O laudo de Feasibility — os três eixos, a amostra, as classes de erro e a decisão.
 *
 * **Os três eixos não colapsam num veredito só**: "funciona, mas o time não opera" e "funciona e
 * não fecha a conta" acabam no mesmo `CONDITIONAL GO`, e é a diferença entre os dois que a próxima
 * conversa precisa. A amostra e as classes de erro ficam visíveis mesmo vazias, com `—`: um laudo
 * sem amostra não é reproduzível, e esconder a linha esconderia exatamente essa lacuna.
 */
function PainelDeFeasibility({ laudos, hipoteses, carregando, erro }: PainelDeFeasibilityProps) {
  if (carregando || erro || !laudos.length) return <CabecalhoVazio
    icone={<Microscope className="size-4" />} titulo="Technical Feasibility"
    apoio="O laudo que sustenta a decisão de gate desta fase."
  >
    {carregando ? <EsqueletoDoPainel />
      : erro ? <p role="alert" className="alert--error">{erro}</p>
      : <p className="empty-state">Nenhum laudo. A Feasibility responde se a tecnologia consegue fazer a tarefa.</p>}
  </CabecalhoVazio>;

  return <>{laudos.map(laudo => {
    const eixos = [
      ["Eixo técnico", laudo.technical_verdict, laudo.technical_note],
      ["Eixo operacional", laudo.operational_verdict, laudo.operational_note],
      ["Eixo econômico", laudo.economic_verdict, laudo.economic_note],
    ] as const;
    const hipotese = hipoteses[laudo.solution_hypothesis];
    return <section className="panel panel--flush" key={laudo.id}>
      <div className="panel-heading flex-wrap">
        <div className="flex min-w-0 items-center gap-3">
          <span className="metric-icon"><Microscope className="size-4" /></span>
          <div className="min-w-0"><h2>Technical Feasibility</h2><p className="text-sm text-slate-600">Laudo avaliado em {dataCurta(laudo.created_at)}</p></div>
        </div>
        {/* A decisão fica **ao lado** do laudo, nunca no lugar dele: é a mesma pílula da Jornada,
            com o mesmo mapa de `journey.ts`. Ela não se grava aqui — o gate é da fase. */}
        {laudo.gate_decision && <span className={`state ${gateVariant[laudo.gate_decision]} shrink-0`}>{GATE_DECISION_LABEL[laudo.gate_decision]}</span>}
      </div>
      <div className="border-b border-line px-5 py-4 sm:px-6">
        <p className="type-body text-slate-700"><strong className="text-ink">Hipótese de solução avaliada:</strong> {hipotese ? hipotese.statement : "—"}</p>
      </div>
      <div className="panel-rows">
        {eixos.map(([rotulo, veredito, nota]) => <div className="row" key={rotulo}>
          <div className="row-main"><strong>{rotulo}</strong><span>{nota || "Sem nota registrada."}</span></div>
          <div className="row-meta"><span className={`state ${VERDICT_VARIANT[veredito]}`}>{VERDICT_LABEL[veredito]}</span></div>
        </div>)}
        <div className="row"><div className="row-main"><strong>Amostra usada</strong><span>{laudo.sample || "—"}</span></div></div>
        <div className="row"><div className="row-main"><strong>Classes de erro observadas</strong><span>{laudo.error_classes || "—"}</span></div></div>
        <div className="row"><div className="row-main">
          <strong>Evidência</strong>
          <span>{laudo.evidence.length
            ? `${laudo.evidence.length} ${laudo.evidence.length === 1 ? "Evidence vinculada" : "Evidence vinculadas"}`
            : "Nenhuma Evidence vinculada."}</span>
        </div></div>
      </div>
    </section>;
  })}</>;
}

type PainelDeProveProps = {
  experimentos: ProveExperiment[];
  kpis: KPI[];
  medicoes: Record<number, Measurement[]>;
  hipoteses: Record<number, SolutionHypothesis>;
  carregando: boolean;
  erro: string;
  canManage: boolean;
  busy: boolean;
  nomeDe: (userId: number | null) => string;
  onIniciar: (experimento: ProveExperiment) => void;
  onLacuna: (experimento: ProveExperiment) => void;
};

/** `Medido em horas · h`. Sem unidade, a ausência é dita — não se inventa símbolo. */
const medidoEm = (kpi: KPI) => kpi.unit ? `Medido em ${kpi.unit_display.toLowerCase()} · ${KPI_UNIT_SYMBOL[kpi.unit]}` : "Sem unidade definida";

/** A leitura viva de um `kind`. **Medição sem valor e ausência de medição são a mesma coisa: `—`.** */
function valorDe(leituras: Measurement[], kind: Measurement["kind"]): string | null {
  const doTipo = leituras.filter(medicao => medicao.kind === kind);
  if (!doTipo.length) return null;
  // "Mais recente" é por `measured_at`, como no servidor: quem digita a leitura de outubro em
  // novembro está registrando outubro. O id desempata para a ordem ser estável.
  return doTipo.reduce((maior, atual) =>
    atual.measured_at > maior.measured_at || (atual.measured_at === maior.measured_at && atual.id > maior.id) ? atual : maior).value;
}

/**
 * O experimento do PROVE, seus KPIs e a invariante de início (decisões **B1** e **E1**).
 *
 * **A lista do que falta vem do servidor** (`missing_to_start`), e não de uma segunda expressão da
 * regra aqui: as três pastilhas e a recusa da action `start/` saem da mesma função pura
 * (`prove.o_que_falta_para_iniciar`). Duas expressões divergiriam, e a tela habilitaria o botão
 * que o servidor nega — sem nada ficar vermelho.
 */
function PainelDeProve({ experimentos, kpis, medicoes, hipoteses, carregando, erro, canManage, busy, nomeDe, onIniciar, onLacuna }: PainelDeProveProps) {
  if (carregando || erro || !experimentos.length) return <CabecalhoVazio
    icone={<FlaskConical className="size-4" />} titulo="PROVE"
    apoio="O experimento em produção controlada, com critério de sucesso prévio."
  >
    {carregando ? <EsqueletoDoPainel />
      : erro ? <p role="alert" className="alert--error">{erro}</p>
      : <p className="empty-state">Nenhum experimento. O PROVE responde se funcionou em produção controlada.</p>}
  </CabecalhoVazio>;

  return <>{experimentos.map((experimento, indice) => {
    const doExperimento = kpis.filter(kpi => kpi.prove_experiment === experimento.id);
    const hipotese = hipoteses[experimento.solution_hypothesis];
    const janela = experimento.started_at
      ? `${formatDate(experimento.started_at)} → ${experimento.ended_at ? formatDate(experimento.ended_at) : "em aberto"}`
      : "janela ainda não definida";
    const lacuna = experimento.gap_waiver.trim();
    // O espelho exato das três recusas da action, e nada além: a lista do que falta é do servidor,
    // e as duas condições da lacuna aprovada são as mesmas que ele confere antes de gravar.
    const podeIniciar = experimento.missing_to_start.length === 0
      || (lacuna !== "" && experimento.gap_waiver_by !== null);
    return <section className="panel panel--flush" id={indice === 0 ? "prove" : undefined} key={experimento.id}>
      <div className="panel-heading flex-wrap">
        <div className="flex min-w-0 items-center gap-3">
          <span className="metric-icon"><FlaskConical className="size-4" /></span>
          <div className="min-w-0"><h2>PROVE</h2><p className="text-sm text-slate-600">Experimento em produção controlada · {janela}</p></div>
        </div>
        <div className="flex shrink-0 flex-wrap items-center gap-2">
          <span className={`state ${PROVE_STATUS_VARIANT[experimento.status]}`}>{experimento.status_display}</span>
          {/* A decisão do PROVE fala o vocabulário dele — `SCALE`/`ITERATE`/`STOP` (ADR 0053) —,
              e aparece **ao lado** do resultado, nunca no lugar dele. */}
          {experimento.gate_decision && <span className={`state ${gateVariant[experimento.gate_decision]}`}>{GATE_DECISION_LABEL[experimento.gate_decision]}</span>}
        </div>
      </div>
      <div className="grid gap-2 border-b border-line px-5 py-4 sm:px-6">
        <p className="type-body text-slate-700"><strong className="text-ink">Hipótese avaliada:</strong> {hipotese ? hipotese.statement : "—"}</p>
        <p className="type-body text-slate-700"><strong className="text-ink">Escopo controlado:</strong> {experimento.controlled_scope || "—"}</p>
        {/* O critério é **prévio**, e é metade da invariante de início: um experimento que define o
            que é sucesso depois de ver o resultado não prova nada. */}
        <p className="type-body text-slate-700"><strong className="text-ink">Critério de sucesso:</strong> {experimento.success_criteria || "—"}</p>
      </div>

      {doExperimento.length ? <div className="panel-rows">{doExperimento.map(kpi => {
        const leituras = medicoes[kpi.id] ?? [];
        return <div className="row" key={kpi.id}>
          <span className="metric-icon"><Gauge className="size-4" /></span>
          <div className="row-main"><strong>{kpi.name}</strong><span>{medidoEm(kpi)}</span></div>
          <ParDeMedicao antes={valorDe(leituras, "baseline")} depois={valorDe(leituras, "outcome")} direcao={kpi.direction} />
          <HistoricoDeMedicoes medicoes={leituras} />
        </div>;
      })}</div> : <div className="px-5 py-4 sm:px-6"><p className="empty-state">Sem KPI definido. O PROVE não começa sem indicador, critério e baseline.</p></div>}

      {/* Decisão **E1**: bloqueia, com a lista do que falta e uma saída que custa um nome e uma
          justificativa. Uma tela que só avisasse transformaria a invariante em sugestão, e a
          "lacuna aprovada" deixaria de ser um ato registrado para virar um clique que ninguém
          assina. As pastilhas aparecem para quem só lê; os botões, não. */}
      {experimento.status === "planned" && <div className="border-t border-line px-5 py-4 sm:px-6">
        <p className="type-label text-muted">Falta para iniciar o PROVE:</p>
        <ul className="mt-2 grid gap-1.5">{REQUISITOS_DO_PROVE.map(([chave, rotulo]) => {
          const falta = experimento.missing_to_start.includes(chave);
          return <li className="flex items-center gap-2 text-sm text-slate-700" key={chave}>
            <span className={`state ${falta ? "state--2" : "state--1"}`}>{falta ? "Falta" : "Pronto"}</span>{rotulo}
          </li>;
        })}</ul>
        {lacuna && <p className="mt-3 text-sm text-slate-600"><strong className="text-ink">Lacuna aprovada por {nomeDe(experimento.gap_waiver_by)}:</strong> {lacuna}</p>}
        {canManage && <div className="mt-3 flex flex-wrap gap-2">
          <button type="button" className="btn" disabled={!podeIniciar || busy} onClick={() => onIniciar(experimento)}>{busy ? "Iniciando…" : "Iniciar PROVE"}</button>
          <button type="button" className="btn btn--secondary" onClick={() => onLacuna(experimento)}>Registrar lacuna aprovada</button>
        </div>}
      </div>}
    </section>;
  })}</>;
}
