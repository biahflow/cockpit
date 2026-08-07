/**
 * A matriz de telas — rota × papel — que alimenta `a11y.spec.ts` e `responsive.spec.ts` (FDD 022).
 *
 * Uma tela nova entra na matriz por **uma linha** em `ROUTES`, não por um arquivo de teste novo.
 * É o que impede a matriz de envelhecer: o custo de cobrir a próxima página é uma linha.
 *
 * O mock é um `route` único sobre `/api/v1/**`, resolvido por `pathname` — mesmo padrão dos e2e
 * que já existem (`login.spec.ts`, `dashboard.spec.ts`), que também não sobem backend.
 */

import type { Page, Route } from "@playwright/test";

import type { Role } from "../src/types";

export type Screen = { path: string; name: string; role: Role | null };

export const ROUTES: readonly Screen[] = [
  { path: "/", name: "Visão geral", role: "admin" },
  { path: "/comercial", name: "Comercial", role: "admin" },
  { path: "/clientes", name: "Clientes", role: "admin" },
  { path: "/clientes/1", name: "Detalhe do cliente", role: "admin" },
  { path: "/projetos", name: "Projetos", role: "admin" },
  { path: "/projetos/1", name: "Detalhe do projeto", role: "admin" },
  { path: "/documentos", name: "Documentos", role: "admin" },
  { path: "/leads", name: "Leads", role: "admin" },
  { path: "/indicadores", name: "Indicadores", role: "admin" },
  { path: "/pipeline", name: "Pipeline", role: "admin" },
  { path: "/jornada", name: "Jornada", role: "admin" },
  { path: "/servicos", name: "Serviços", role: "admin" },
  { path: "/equipe", name: "Equipe", role: "admin" },
  { path: "/configuracoes", name: "Configurações", role: "admin" },
  // Entrega sem projeto: o estado vazio é uma tela de verdade e tem seu próprio texto.
  { path: "/projetos", name: "Projetos (Entrega, sem equipe)", role: "delivery" },
  { path: "/", name: "Login", role: null },
  { path: "/aceitar-convite", name: "Aceitar convite", role: null },
];

/**
 * Nome longo de propósito: conteúdo curto cabe em qualquer largura, e uma matriz de
 * responsividade alimentada com "Cliente 1" passaria sem provar nada. Este é o comprimento
 * de uma razão social real.
 */
const NOME_LONGO = "Indústria Metalúrgica São Bernardo do Campo Participações S.A.";
const HOJE = "2026-08-05";
const VENCIDO = "2026-07-01";

const usuarios: Record<Role, unknown> = {
  admin: { id: 1, username: "ana", first_name: "Ana", last_name: "Souza", email: "ana@example.test", role: "admin", is_admin: true },
  sales: { id: 2, username: "bruno", first_name: "Bruno", last_name: "Lima", email: "bruno@example.test", role: "sales", is_admin: false },
  delivery: { id: 3, username: "carla", first_name: "Carla", last_name: "Reis", email: "carla@example.test", role: "delivery", is_admin: false },
};

const serie = <T,>(quantos: number, molde: (indice: number) => T): T[] =>
  Array.from({ length: quantos }, (_, indice) => molde(indice + 1));

const clientes = serie(8, index => ({
  id: index, name: `${NOME_LONGO} — unidade ${index}`, legal_name: NOME_LONGO,
  tax_id: "12.345.678/0001-90", owner: 1, status: index % 2 ? "active" : "prospect",
}));

const projetos = serie(8, index => ({
  id: index, name: `Implantação de agentes no faturamento — frente ${index}`, description: "",
  client: index, owner: 1, start_date: "2026-05-01", due_date: VENCIDO, status: "active",
  service: null, actual_value: "180000.00", cost: "90000.00", is_overdue: true,
  ai_maturity: 62, ai_opportunity: 78, ai_dimensions: [{ label: "Dados", score: 55 }],
  ai_score_summary: "Base de dados fragmentada entre ERP e planilhas.",
  ai_scored_at: `${HOJE}T12:00:00Z`, ai_score_reviewed: true,
}));

const etapas = ["Qualificação", "Proposta enviada", "Negociação", "Ganha", "Perdida"].map((name, i) => ({
  id: i + 1, name, kind: i === 3 ? "won" : i === 4 ? "lost" : "open",
  position: i, opportunity_count: 3, estimated_total: "450000.00",
}));

const oportunidades = serie(8, index => ({
  id: index, client: index, contact: null,
  title: `Discovery e assessment de automação — ${NOME_LONGO}`,
  scope: "Mapeamento de processos e desenho de agentes.", estimated_value: "150000.00",
  stage: (index % 3) + 1, stage_name: etapas[(index % 3)].name, owner: 1,
  expected_close_date: HOJE, service: 1, service_name: "Discovery + Assessment",
  service_tier: "discovery_assessment",
}));

const itensDeTrabalho = serie(8, index => ({
  id: index, project: 1, title: `Entrevistar área de faturamento — bloco ${index}`,
  description: "", owner: 1, due_date: VENCIDO, completed_at: null,
  status: "todo", party: "provider", is_overdue: true, milestone: null,
}));

const riscos = serie(8, index => ({
  project_id: index, name: projetos[index - 1].name, score: 70, level: "alto",
  signals: [{ label: "Itens atrasados", detail: "3 item(ns) vencido(s)", weight: 30 }],
  forecast: { predicted_finish_date: "2026-09-30", delay_days: 45, basis: "40% concluído em 60 dia(s)" },
}));

const saude = serie(8, index => ({
  project_id: index, name: projetos[index - 1].name, score: 42, level: "crítico",
  signals: [{ label: "Decisões pendentes", detail: "4 em aberto · 2 aguardando o cliente", weight: 25 }],
}));

/** Rotas exatas → resposta. O que não casar cai no default por método (lista vazia). */
const FIXTURES: Record<string, unknown> = {
  "/api/v1/auth/csrf/": { csrfToken: "test" },
  // As sete flags que `flags.FLAGS` serve, e **com `missing`** — o campo nasceu na ADR 0018, a
  // `SettingsPage` passou a fazer `flag.missing.join()` e esta fixture ficou para trás, estourando
  // a tela em toda varredura. Passou despercebido porque o `ErrorBoundary` também tem `<h1>` e a
  // matriz media o cartão de erro; a trava de `fixtures.ts` existe por causa disto. Duas
  // integrações ficam sem credencial de propósito: é o caminho que estourava, e é o que exercita o
  // texto "Falta no ambiente: X" — o mais longo da tela, que é o que a largura precisa aguentar.
  "/api/v1/config/": {
    ai_enabled: true, calendar_enabled: false, esign_enabled: true,
    integrations: [
      { key: "ai", label: "Assistente de IA", enabled: true, configured: true, toggleable: true, missing: [] },
      { key: "drive", label: "Documentos no Google Drive", enabled: false, configured: false, toggleable: true, missing: ["GOOGLE_DRIVE_ROOT_FOLDER_ID"] },
      { key: "calendar", label: "Calendário (Google)", enabled: false, configured: false, toggleable: true, missing: ["GOOGLE_CALENDAR_ID", "GOOGLE_OAUTH_REFRESH_TOKEN"] },
      { key: "esign", label: "Assinatura eletrônica", enabled: true, configured: true, toggleable: true, missing: [] },
      { key: "email", label: "Notificações por e-mail e digest", enabled: true, configured: true, toggleable: true, missing: [] },
      { key: "tasksync", label: "Sincronia de tarefas (Linear/GitHub)", enabled: false, configured: true, toggleable: true, missing: [] },
      { key: "portal", label: "Portal do cliente", enabled: true, configured: true, toggleable: true, missing: [] },
    ],
  },
  "/api/v1/dashboard/": {
    pipeline: etapas, active_projects: 12, overdue_count: 5,
    upcoming_tasks: itensDeTrabalho.slice(0, 5).map(item => ({
      id: item.id, title: item.title, due_date: item.due_date, project_id: 1,
    })),
  },
  "/api/v1/clients/": clientes,
  "/api/v1/clients/1/": clientes[0],
  "/api/v1/clients/overview/": {
    clients: clientes.map(cliente => ({
      client_id: cliente.id, name: cliente.name, status: cliente.status,
      roi: { revenue: 180000, cost: 90000, roi: 1 },
      health: { score: 42, level: "crítico", project_id: cliente.id },
      risk_level: "alto", phase: { name: "Implantação assistida", status: "active" },
      next_meeting: { title: "Comitê quinzenal de acompanhamento", date: HOJE },
      ai_score: { maturity: 62, opportunity: 78, dimensions: [{ label: "Dados", score: 55 }],
        summary: "Base fragmentada.", scored_at: `${HOJE}T12:00:00Z` },
    })),
  },
  "/api/v1/clients/1/overview/": {
    client_id: 1, name: clientes[0].name, status: "active",
    roi: { revenue: 180000, cost: 90000, roi: 1 },
    health: { score: 42, level: "crítico", project_id: 1 },
    risk_level: "alto", phase: { name: "Implantação assistida", status: "active" },
    next_meeting: { title: "Comitê quinzenal de acompanhamento", date: HOJE },
    ai_score: null,
  },
  "/api/v1/projects/": projetos,
  "/api/v1/projects/1/": projetos[0],
  "/api/v1/projects/1/risk/": riscos[0],
  "/api/v1/projects/1/health/": saude[0],
  "/api/v1/opportunities/": oportunidades,
  "/api/v1/pipeline-stages/": etapas,
  "/api/v1/milestones/": itensDeTrabalho,
  "/api/v1/tasks/": itensDeTrabalho,
  "/api/v1/risk/": { projects: riscos },
  "/api/v1/health/": { projects: saude },
  "/api/v1/recommendations/": {
    items: serie(5, index => ({
      kind: "followup", label: `Retomar contato com ${NOME_LONGO}`,
      detail: "Sem interação registrada há 21 dias.", url: `/clientes/${index}`,
    })),
  },
  "/api/v1/services/": serie(4, index => ({
    id: index, name: index === 1 ? "Discovery Express" : `Serviço avulso ${index}`,
    active: true, tier: index === 1 ? "discovery_express" : "",
    tier_display: index === 1 ? "Discovery Express" : "", list_price: "0.00",
    summary: "Diagnóstico inicial gratuito de oportunidades de automação.",
  })),
  "/api/v1/leads/": serie(8, index => ({
    id: index, name: `Contato ${index}`, email: `contato${index}@empresa.test`,
    company: NOME_LONGO, phone: "(11) 99999-0000",
    message: "Gostaria de entender como reduzir o retrabalho no faturamento.",
    source: "site", status: "new", ai_fit: "high", ai_score: 82,
    ai_summary: "Dor clara em processo manual, porte compatível.",
    ai_recommended_action: "Agendar discovery express.",
    qualified_at: null, client: null, opportunity: null, created_at: `${HOJE}T09:00:00Z`,
  })),
  "/api/v1/documents/": serie(6, index => ({
    id: index, client: index, opportunity: null, project: null, file: "/media/x.pdf",
    drive_link: "", original_name: `Contrato de prestação de serviços — ${NOME_LONGO}.pdf`,
    uploaded_by: 1, created_at: `${HOJE}T09:00:00Z`,
    signature_requests: index === 1
      ? [{ id: 1, signer_email: "juridico@empresa.test", status: "pending", sign_url: "https://exemplo.test/s/1", reminded_at: null, signed_at: null, created_at: `${HOJE}T09:00:00Z` }]
      : [],
  })),
  "/api/v1/journey-phases/": serie(5, index => ({
    id: index, name: `Fase ${index} — implantação assistida`, description: "", active: true,
    position: index, deliverables: serie(3, d => ({ id: d, phase: index, name: `Entregável ${d}`, position: d })),
  })),
  "/api/v1/analytics/": {
    funnel: {
      leads: { total: 40, by_status: { new: 12, contacted: 10, qualified: 14, discarded: 4 } },
      opportunities: { open: 9, won: 6, lost: 3 },
      projects: { total: 12, by_status: { active: 8, completed: 4 } },
      by_tier: [
        { tier: "discovery_express", label: "Discovery Express", total: 10, open: 4, won: 5, lost: 1, estimated_total: 0, win_rate: 0.83 },
        { tier: "discovery_assessment", label: "Discovery + Assessment", total: 8, open: 3, won: 4, lost: 1, estimated_total: 320000, win_rate: 0.8 },
        { tier: "implantacao", label: "Implantação", total: 5, open: 2, won: 2, lost: 1, estimated_total: 900000, win_rate: 0.67 },
      ],
      by_stage: [
        { kind: "discovery", label: "Discovery", total: 12, sent: 10, accepted: 8, rejected: 1, acceptance_rate: 0.8, reached: 12 },
        { kind: "assessment", label: "Assessment", total: 9, sent: 8, accepted: 6, rejected: 2, acceptance_rate: 0.75, reached: 9 },
        { kind: "proposal", label: "Proposta", total: 7, sent: 7, accepted: 5, rejected: 2, acceptance_rate: 0.71, reached: 7 },
        { kind: "contract", label: "Contrato", total: 5, sent: 5, accepted: 5, rejected: 0, acceptance_rate: 1, reached: 5 },
      ],
    },
    win_rate: 0.67, avg_ticket: 150000, avg_cycle_days: 38, pipeline: etapas,
    roi: {
      revenue: 1440000, cost: 720000, roi: 1,
      by_client: clientes.map(c => ({ label: c.name, revenue: 180000, cost: 90000, roi: 1 })),
      by_service: [{ label: "Discovery + Assessment", revenue: 640000, cost: 300000, roi: 1.13 }],
    },
  },
  "/api/v1/notifications/": serie(4, index => ({
    id: index, kind: "task", message: `Tarefa "Entrevistar área de faturamento" vence hoje (${index})`,
    url: "/projetos/1", read: index > 2, created_at: `${HOJE}T08:00:00Z`,
  })),
  "/api/v1/users/": Object.values(usuarios),
  "/api/v1/invitations/": serie(3, index => ({
    id: index, email: `convidado${index}@empresa.test`, role: "delivery",
    expires_at: "2026-08-12T00:00:00Z", accepted_at: null, created_at: `${HOJE}T08:00:00Z`,
  })),
  "/api/v1/project-members/": serie(4, index => ({
    id: index, project: 1, user: index, user_name: `Pessoa ${index}`,
    user_username: `pessoa${index}`, user_role: "delivery", added_by: 1,
    created_at: `${HOJE}T08:00:00Z`,
  })),
  "/api/v1/project-phases/": serie(4, index => ({
    id: index, project: 1, phase: index, phase_name: `Fase ${index} — implantação assistida`,
    phase_description: "", phase_position: index, status: index === 1 ? "active" : "locked",
    started_at: null, completed_at: null, target_date: HOJE,
    deliverables: serie(2, d => ({ id: d, project_phase: index, name: `Entregável ${d}`, status: "pending", document: null, position: d, delivered_at: null })),
  })),
  "/api/v1/digital-employees/": serie(3, index => ({
    id: index, project: 1, name: `Agente de conciliação ${index}`, area: "Financeiro",
    description: "Concilia notas fiscais com o extrato bancário.", status: "active",
    kpi_label: "Horas poupadas", kpi_value: "120", hours_saved_month: "120.0", roi_month: "18000.00",
  })),
  "/api/v1/meetings/": serie(4, index => ({
    id: index, project: 1, title: `Comitê quinzenal de acompanhamento ${index}`,
    date: HOJE, recording_url: "", transcript: "Cliente relatou processo manual.", status: "held",
  })),
  "/api/v1/pendencias/": serie(4, index => ({
    id: index, project: 1, title: `Liberar acesso ao ERP para a equipe ${index}`,
    description: "", status: "open", party: "client", owner: null, resolved_at: null,
  })),
  "/api/v1/contacts/": serie(4, index => ({
    id: index, client: 1, name: `Pessoa de contato ${index}`,
    email: `pessoa${index}@empresa.test`, phone: "(11) 98888-0000", job_title: "Gerente de operações",
  })),
  "/api/v1/artifacts/": serie(4, index => ({
    id: index, kind: "proposal", kind_display: "Proposta", status: "draft",
    status_display: "Rascunho", title: `Proposta — ${NOME_LONGO}`,
    content: "Rascunho gerado por IA para revisão humana.", opportunity: 1, project: null,
    source_meeting: null, document: null, ai_interaction: 1, created_by: 1,
    sent_at: null, decided_at: null, created_at: `${HOJE}T09:00:00Z`, updated_at: `${HOJE}T09:00:00Z`,
  })),
};

/**
 * Intercepta toda a API com um handler só.
 *
 * `role: null` responde 403 em `/auth/me/` — que é como o SPA decide mostrar a tela de login.
 * `role: "delivery"` devolve listas vazias de projeto, porque é exatamente o que a Entrega vê
 * sem estar em nenhuma equipe (RFC 0003) — o estado vazio faz parte da matriz.
 */
export async function mockApi(page: Page, role: Role | null): Promise<void> {
  await page.route("**/api/v1/**", (route: Route) => {
    const { pathname } = new URL(route.request().url());
    if (pathname === "/api/v1/auth/me/") {
      return role
        ? route.fulfill({ json: usuarios[role] })
        : route.fulfill({ status: 403, json: { detail: "Credenciais ausentes." } });
    }
    if (role === "delivery" && (pathname === "/api/v1/projects/" || pathname === "/api/v1/clients/")) {
      return route.fulfill({ json: [] });
    }
    const fixture = FIXTURES[pathname];
    if (fixture !== undefined) return route.fulfill({ json: fixture });
    // Rota não mapeada: lista vazia em vez de 404, para uma tela nova na matriz renderizar
    // seu estado vazio em vez de estourar antes de o axe chegar nela.
    return route.fulfill({ json: [] });
  });
}

/**
 * Abre a tela já com sessão e API mockadas, e espera o conteúdo **assentar**.
 *
 * Esperar só pelo `<h1>` não basta e chega a ser pior que não esperar: painéis que carregam
 * depois (o de artefatos, no detalhe do projeto) entram na tela **após** o título, e a medição
 * pegava a página pela metade. O resultado seria um teste que passa ou reprova conforme a
 * máquina do dia — e foi exatamente assim que o estouro horizontal do painel de artefatos quase
 * passou despercebido. `networkidle` fecha a janela: com toda a API mockada, ele significa
 * "nenhuma requisição pendente", isto é, o React já renderizou tudo o que ia buscar.
 */
export async function abrir(page: Page, screen: Screen): Promise<void> {
  await mockApi(page, screen.role);
  await page.goto(screen.path);
  await page.locator("h1").first().waitFor({ state: "visible" });
  await page.waitForLoadState("networkidle");
}
