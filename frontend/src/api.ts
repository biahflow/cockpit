import { reportError, setLastRequestId } from "./observability";
import type { AgentReply, AppConfig, FeasibilityAssessment, ImprovementOpportunity, IntegrationFlag, Invitation, KPI, Measurement, Notification, PainPoint, PriorityAssessment, Project, ProveExperiment, SessionUser, SolutionHypothesis, ValueLedgerEntry } from "./types";

const baseUrl = import.meta.env.VITE_API_URL || "/api/v1";

// Erro de API que carrega o `X-Request-ID` da resposta — o mesmo id que está na linha de log do
// servidor e na tag do evento do Sentry (FDD 020). É o que transforma "deu erro" em uma
// requisição localizável.
export class ApiError extends Error {
  constructor(message: string, readonly status: number, readonly requestId: string, readonly code: string) {
    super(message);
    this.name = "ApiError";
  }
}

// O DRF devolve erro de validação por campo (`{"tier": ["Já existe..."]}`), sem a chave `detail`.
// Lendo só `detail`, toda mensagem específica virava o genérico "Não foi possível concluir a
// operação." — e quem via não tinha como saber o que corrigir. O caso que denunciou foi o nível de
// produto duplicado em Serviços, mas vale para qualquer formulário do portal.
function fieldErrors(payload: unknown): string {
  if (typeof payload !== "object" || payload === null) return "";
  return Object.values(payload as Record<string, unknown>)
    .flatMap(value => Array.isArray(value) ? value : [value])
    .filter((value): value is string => typeof value === "string")
    .join(" ");
}

async function csrf(): Promise<string> {
  const response = await fetch(`${baseUrl}/auth/csrf/`, { credentials: "include" });
  if (!response.ok) throw new Error("Não foi possível iniciar uma sessão segura.");
  const payload = await response.json() as { csrfToken: string };
  return payload.csrfToken;
}

export async function api<T>(path: string, options: RequestInit = {}): Promise<T> {
  const method = options.method?.toUpperCase() ?? "GET";
  const csrfToken = !["GET", "HEAD", "OPTIONS"].includes(method) ? await csrf() : undefined;
  const response = await fetch(`${baseUrl}${path}`, {
    ...options,
    credentials: "include",
    headers: {
      ...(options.body instanceof FormData ? {} : { "Content-Type": "application/json" }),
      ...(csrfToken ? { "X-CSRFToken": csrfToken } : {}),
      ...options.headers,
    },
  });
  const requestId = response.headers.get("X-Request-ID") ?? "";
  if (requestId) setLastRequestId(requestId);
  if (!response.ok) {
    const detail = await response.json().catch(() => ({}));
    // O `code` distingue estados que o `detail` sozinho não separa — a página de agendamento do
    // Discovery (DAP `dap-agendamento-discovery-r1`) precisa de um deles (`token_expired` vs.
    // `token_invalid`, por exemplo) para escolher a mensagem certa sem comparar string em
    // português.
    const erro = new ApiError(detail.detail || fieldErrors(detail) || "Não foi possível concluir a operação.", response.status, requestId, detail.code ?? "");
    // Só 5xx: 400/403/404 são o app funcionando (validação, permissão, item removido) e
    // encheriam o Sentry de ruído que já está na tela do usuário.
    if (response.status >= 500) reportError(erro, { requestId, status: response.status, path });
    throw erro;
  }
  if (response.status === 204) return undefined as T;
  return response.json() as Promise<T>;
}

export function documentDownloadUrl(id: number): string {
  return `${baseUrl}/documents/${id}/download/`;
}

export function getConfig(): Promise<AppConfig> {
  return api<AppConfig>("/config/");
}

export function setFlag(key: string, enabled: boolean): Promise<IntegrationFlag> {
  return api<IntegrationFlag>("/config/", { method: "PATCH", body: JSON.stringify({ key, enabled }) });
}

export function syncCalendar(): Promise<{ created: number; skipped: number }> {
  return api<{ created: number; skipped: number }>("/config/sync-calendar/", { method: "POST" });
}

export function askAgent(key: string, question: string): Promise<AgentReply> {
  return api<AgentReply>(`/agents/${key}/`, { method: "POST", body: JSON.stringify({ question }) });
}

export function rateInteraction(interaction: number, rating: 1 | -1): Promise<void> {
  return api<void>("/ai/feedback/", { method: "POST", body: JSON.stringify({ interaction, rating }) });
}

export function listNotifications(): Promise<Notification[]> {
  return api<Notification[]>("/notifications/");
}

export function markNotificationRead(id: number): Promise<void> {
  return api<void>(`/notifications/${id}/read/`, { method: "POST" });
}

export function markAllNotificationsRead(): Promise<void> {
  return api<void>("/notifications/read-all/", { method: "POST" });
}

export function currentUser(): Promise<SessionUser> {
  return api<SessionUser>("/auth/me/");
}

export function login(username: string, password: string): Promise<SessionUser> {
  return api<SessionUser>("/auth/login/", {
    method: "POST",
    body: JSON.stringify({ username, password }),
  });
}

export function logout(): Promise<void> {
  return api<void>("/auth/logout/", { method: "POST" });
}

export function listInvitations(): Promise<Invitation[]> {
  return api<Invitation[]>("/invitations/");
}

export function createInvitation(email: string, role: string): Promise<Invitation> {
  return api<Invitation>("/invitations/", { method: "POST", body: JSON.stringify({ email, role }) });
}

export function listUsers(): Promise<SessionUser[]> {
  return api<SessionUser[]>("/users/");
}

// ---------- Meu perfil ----------
// Todas as rotas de escrita ficam sob `/auth/me/` e operam sobre a sessão: **não existe id de
// usuário para mandar**, e é isso que impede a tela de virar caminho para editar outra pessoa.

export function updateProfile(payload: { first_name: string; last_name: string }): Promise<SessionUser> {
  return api<SessionUser>("/auth/me/", { method: "PATCH", body: JSON.stringify(payload) });
}

export function uploadAvatar(file: File): Promise<SessionUser> {
  const body = new FormData();
  body.append("avatar", file);
  return api<SessionUser>("/auth/me/avatar/", { method: "PUT", body });
}

export function removeAvatar(): Promise<SessionUser> {
  return api<SessionUser>("/auth/me/avatar/", { method: "DELETE" });
}

export function changePassword(payload: { current_password: string; new_password: string; new_password_confirm: string }): Promise<void> {
  return api<void>("/auth/me/password/", { method: "POST", body: JSON.stringify(payload) });
}

/** A foto sai por rota autenticada, como o download de documento — nunca por `/media/`.
 *
 * O `?v=` não é cache-busting contra o servidor (o `ETag` da rota já resolve a revalidação): ele
 * existe porque o navegador não refaz um `<img>` cuja `src` não mudou, e sem ele a foto trocada
 * só apareceria depois de um recarregamento da página. */
export function avatarUrl(user: SessionUser): string {
  const versao = user.avatar_updated_at ? `?v=${encodeURIComponent(user.avatar_updated_at)}` : "";
  return `${baseUrl}/users/${user.id}/avatar/${versao}`;
}

export function acceptInvitation(payload: { token: string; username: string; password: string; first_name?: string; last_name?: string }): Promise<SessionUser> {
  return api<SessionUser>("/invitations/accept/", { method: "POST", body: JSON.stringify(payload) });
}

// ---------- Agendamento público do Discovery (DAP `dap-agendamento-discovery-r1`) ----------
// As duas rotas que `AgendarDiscoveryPage` consome, sob `/agendar/<token>`. Públicas no backend
// (`AllowAny`, token no caminho da SPA) — nenhuma passa por sessão; o `POST` ainda passa por
// CSRF porque `api()` decide isso pelo método, não pela autenticação.

export type DiscoveryBookingSlots = { account: string; slots: string[]; scheduled_at: string | null };

export function getDiscoveryBookingSlots(token: string): Promise<DiscoveryBookingSlots> {
  return api<DiscoveryBookingSlots>(`/booking/discovery/slots/?token=${encodeURIComponent(token)}`);
}

export type DiscoveryBookingConfirmation = { starts_at: string; link: string };

export function bookDiscovery(payload: { token: string; slot_start: string }): Promise<DiscoveryBookingConfirmation> {
  return api<DiscoveryBookingConfirmation>("/booking/discovery/", { method: "POST", body: JSON.stringify(payload) });
}

// ---------- A cadeia do PRIORITIZE (FDD 048, ADR 0054) ----------
// Dor → oportunidade de melhoria → avaliação → hipótese, consumidas pela tela
// `/contas/:id/priorizacao` e pela seção de pain points do processo (DAP priorização r1).
//
// As rotas ficam **qualificadas** — `improvement-opportunities`, nunca `opportunities`: a rota da
// venda é `/opportunities/`, e o mapa de linguagem §5 bane `Opportunity` sem qualificador
// exatamente porque as duas colidiam. Uma chamada trocada aqui não estoura, ela lê o funil
// comercial e o mostra como backlog de melhoria.

export type PainPointPayload = {
  account: number;
  title: string;
  impact_type: PainPoint["impact_type"];
  process: number | null;
  step: number | null;
};

/** As dores da conta — inclusive as que não têm processo nenhum, que é o caso do vínculo opcional. */
export function listPainPointsByAccount(account: number): Promise<PainPoint[]> {
  return api<PainPoint[]>(`/pain-points/?account=${account}`);
}

/** As dores observadas **naquele** processo, que é onde a decisão E1 manda registrá-las. */
export function listPainPointsByProcess(process: number): Promise<PainPoint[]> {
  return api<PainPoint[]>(`/pain-points/?process=${process}`);
}

export function createPainPoint(payload: PainPointPayload): Promise<PainPoint> {
  return api<PainPoint>("/pain-points/", { method: "POST", body: JSON.stringify(payload) });
}

/**
 * Edita a dor. **`status: "confirmed"` não sai daqui de graça**: o backend exige ao menos um
 * `Finding` vivo ligado e responde 400 sem ele (FDD 048), e o produto ainda não tem tela de
 * achados — por isso a superfície só oferece observado ↔ descartado.
 */
export function updatePainPoint(id: number, payload: Partial<PainPointPayload> & { status?: PainPoint["status"] }): Promise<PainPoint> {
  return api<PainPoint>(`/pain-points/${id}/`, { method: "PATCH", body: JSON.stringify(payload) });
}

export type ImprovementOpportunityPayload = {
  account: number;
  title: string;
  pain_points: number[];
};

export function listImprovementOpportunities(account: number): Promise<ImprovementOpportunity[]> {
  return api<ImprovementOpportunity[]>(`/improvement-opportunities/?account=${account}`);
}

export function createImprovementOpportunity(payload: ImprovementOpportunityPayload): Promise<ImprovementOpportunity> {
  return api<ImprovementOpportunity>("/improvement-opportunities/", { method: "POST", body: JSON.stringify(payload) });
}

export function updateImprovementOpportunity(id: number, payload: Partial<ImprovementOpportunityPayload> & { status?: ImprovementOpportunity["status"] }): Promise<ImprovementOpportunity> {
  return api<ImprovementOpportunity>(`/improvement-opportunities/${id}/`, { method: "PATCH", body: JSON.stringify(payload) });
}

export type PriorityAssessmentPayload = {
  improvement_opportunity: number;
  impact: number;
  evidence_strength: number;
  feasibility: number;
  time_to_value: number;
  economics: number;
  rationale: string;
};

/**
 * O histórico completo de uma oportunidade — a vigente **e** as substituídas (decisão C1).
 *
 * Não existe `updatePriorityAssessment`, e a ausência é a decisão: a rota não expõe `PUT` nem
 * `PATCH` (405). Repriorizar é criar a versão seguinte, e é `createPriorityAssessment` que faz
 * isso — a anterior fica de pé, que é a razão de o modelo ser versionado.
 */
export function listPriorityAssessments(improvementOpportunity: number): Promise<PriorityAssessment[]> {
  return api<PriorityAssessment[]>(`/priority-assessments/?improvement_opportunity=${improvementOpportunity}`);
}

export function createPriorityAssessment(payload: PriorityAssessmentPayload): Promise<PriorityAssessment> {
  return api<PriorityAssessment>("/priority-assessments/", { method: "POST", body: JSON.stringify(payload) });
}

export type SolutionHypothesisPayload = {
  improvement_opportunity: number;
  statement: string;
};

export function listSolutionHypotheses(improvementOpportunity: number): Promise<SolutionHypothesis[]> {
  return api<SolutionHypothesis[]>(`/solution-hypotheses/?improvement_opportunity=${improvementOpportunity}`);
}

export function createSolutionHypothesis(payload: SolutionHypothesisPayload): Promise<SolutionHypothesis> {
  return api<SolutionHypothesis>("/solution-hypotheses/", { method: "POST", body: JSON.stringify(payload) });
}

/** Trocar para `chosen` com outra já escolhida viva é 400, não 500: a checagem mora no serializer. */
export function updateSolutionHypothesis(id: number, payload: Partial<SolutionHypothesisPayload> & { status?: SolutionHypothesis["status"] }): Promise<SolutionHypothesis> {
  return api<SolutionHypothesis>(`/solution-hypotheses/${id}/`, { method: "PATCH", body: JSON.stringify(payload) });
}

// ---------- Feasibility, PROVE, KPI/Measurement e Value Ledger (FDD 049, ADR 0055) ----------
// Os cinco recursos da Fase 5, consumidos pelos dois painéis de `ProjectDetailPage` e pela tela
// `/contas/:id/valor` (DAP `dap-prove-e-valor-r1`, decisões A1 · B1 · C1 · D1 · E1).
//
// **Nomes canônicos e nenhum alias**: estes cinco nascem com o nome do mapa de linguagem, então
// aqui não há a assimetria de `/clients/` — a rota é a mesma palavra do modelo.

export function listFeasibilityAssessments(project: number): Promise<FeasibilityAssessment[]> {
  return api<FeasibilityAssessment[]>(`/feasibility-assessments/?project=${project}`);
}

export function listProveExperiments(project: number): Promise<ProveExperiment[]> {
  return api<ProveExperiment[]>(`/prove-experiments/?project=${project}`);
}

/**
 * Inicia o PROVE. **A tela nunca decide sozinha que pode iniciar**: quem diz o que falta é
 * `missing_to_start`, que o servidor deriva da mesma função que esta action usa para recusar
 * (`prove.o_que_falta_para_iniciar`). Reexpressar a invariante aqui habilitaria o botão de um
 * `POST` que o servidor nega, e nada ficaria vermelho.
 */
export function startProveExperiment(id: number): Promise<ProveExperiment> {
  return api<ProveExperiment>(`/prove-experiments/${id}/start/`, { method: "POST" });
}

/**
 * Registra a lacuna aprovada — a saída explícita da decisão **E1**, e ela custa um nome e uma
 * justificativa. `gap_waiver` sem `gap_waiver_by` é 400 no servidor: aprovação sem autor é
 * alegação de ninguém. `gap_waiver_at` é carimbado por `start/` e não se envia daqui.
 */
export function registerProveGapWaiver(id: number, payload: { gap_waiver: string; gap_waiver_by: number }): Promise<ProveExperiment> {
  return api<ProveExperiment>(`/prove-experiments/${id}/`, { method: "PATCH", body: JSON.stringify(payload) });
}

export function listKpis(project: number): Promise<KPI[]> {
  return api<KPI[]>(`/kpis/?project=${project}`);
}

export function getKpi(id: number): Promise<KPI> {
  return api<KPI>(`/kpis/${id}/`);
}

/** As leituras de um KPI — baseline, outcome e monitoramento —, que a linha B1 compara. */
export function listMeasurements(kpi: number): Promise<Measurement[]> {
  return api<Measurement[]>(`/measurements/?kpi=${kpi}`);
}

export function getMeasurement(id: number): Promise<Measurement> {
  return api<Measurement>(`/measurements/${id}/`);
}

/**
 * O Value Ledger é **por engajamento**, e é por isso que a tela da conta faz uma chamada por
 * mandato em vez de uma só: a entrada pende do `Engagement` (valor é do mandato, não do projeto),
 * e a rota não expõe filtro por conta. Um `GET` sem filtro traria o ledger inteiro que a pessoa
 * alcança, de todas as contas — que é justamente o consolidado **reservado** no DAP.
 */
export function listValueLedgerEntries(engagement: number): Promise<ValueLedgerEntry[]> {
  return api<ValueLedgerEntry[]>(`/value-ledger-entries/?engagement=${engagement}`);
}

/**
 * Cria um projeto a partir do mandato (DAP `dap-engagement-r3`, decisões A1 · B2 · C1 · D1) — rota
 * própria com guarda de papel, e não `POST /projects/` cru: `RolePermission` hoje só deixa
 * **admin** criar projeto direto, e a seção do mandato é visível a Vendas.
 */
export function createProjectFromEngagement(engagement: number, payload: { name: string; service: number; start_date: string; due_date: string }): Promise<Project> {
  return api<Project>(`/engagements/${engagement}/create-project/`, { method: "POST", body: JSON.stringify(payload) });
}
