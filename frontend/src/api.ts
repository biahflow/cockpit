import { reportError, setLastRequestId } from "./observability";
import type { AgentReply, AppConfig, IntegrationFlag, Invitation, Notification, SessionUser } from "./types";

const baseUrl = import.meta.env.VITE_API_URL || "/api/v1";

// Erro de API que carrega o `X-Request-ID` da resposta — o mesmo id que está na linha de log do
// servidor e na tag do evento do Sentry (FDD 020). É o que transforma "deu erro" em uma
// requisição localizável.
export class ApiError extends Error {
  constructor(message: string, readonly status: number, readonly requestId: string) {
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
    const erro = new ApiError(detail.detail || fieldErrors(detail) || "Não foi possível concluir a operação.", response.status, requestId);
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

export function acceptInvitation(payload: { token: string; username: string; password: string; first_name?: string; last_name?: string }): Promise<SessionUser> {
  return api<SessionUser>("/invitations/accept/", { method: "POST", body: JSON.stringify(payload) });
}
