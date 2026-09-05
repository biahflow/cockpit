import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, expect, test, vi } from "vitest";

import { ProjectDetailPage } from "./ProjectDetailPage";

const mocks = vi.hoisted(() => ({
  api: vi.fn(),
  auth: { aiEnabled: true } as { aiEnabled: boolean; user?: { role: string; is_admin?: boolean } },
  people: [] as { id: number; username: string; first_name: string; role: string }[],
}));
// A carga da Fase 5 (FDD 049) roda em paralelo ao detalhe do projeto e não é o assunto deste
// arquivo: listas vazias mantêm os dois painéis fora do caminho. Quem os exercita é
// `ProjectDetailProve.test.tsx`. Em `vi.hoisted` porque a fábrica do `vi.mock` roda **antes** do
// corpo do módulo.
const semFase5 = vi.hoisted(() => ({
  listKpis: () => Promise.resolve([]),
  listFeasibilityAssessments: () => Promise.resolve([]),
  listProveExperiments: () => Promise.resolve([]),
  listMeasurements: () => Promise.resolve([]),
  startProveExperiment: () => Promise.resolve({}),
  registerProveGapWaiver: () => Promise.resolve({}),
}));
// A porta da Discovery Session (FDD 055) também é carga paralela ao detalhe, e não é o assunto
// destes arquivos: lista vazia mantém a seção fora do caminho. Quem a exercita é
// `ProjectDetailDiscoverySessions.test.tsx`.
const semSessoesDeDiscovery = vi.hoisted(() => ({
  listDiscoveries: () => Promise.resolve([]),
  listDiscoverySessions: () => Promise.resolve([]),
}));
vi.mock("../api", () => ({ api: mocks.api, listUsers: () => Promise.resolve(mocks.people), ...semFase5, ...semSessoesDeDiscovery }));
vi.mock("../auth", () => ({ useAuth: () => mocks.auth }));

const artifact = () => ({
  id: 5, kind: "discovery", kind_display: "Discovery", status: "draft", status_display: "Rascunho",
  title: "Discovery — Kickoff", content: "Análise da reunião", commercial_opportunity: null, opportunity: null, project: 1,
  source_meeting: 1, document: null, ai_interaction: 9, created_by: 1, sent_at: null,
  decided_at: null, created_at: "2026-08-05T10:00:00Z", updated_at: "2026-08-05T10:00:00Z",
});

const projectPhase = () => ({
  id: 10, project: 1, phase: 2, phase_name: "PROVE", phase_description: "Validar em produção",
  phase_position: 2, requires_gate: false, canonical_stage: "", status: "active",
  situation: "active", started_at: "2026-08-01T10:00:00Z", completed_at: null,
  target_date: null, gate_decision: "", gate_outcome: "", gate_notes: "", checklist_waiver: "",
  waiting_party: "", blocker_note: "", deliverables: [], checklist_items: [],
});

function stub() {
  mocks.api.mockImplementation((path: string) => {
    if (path.includes("/assistant/")) return Promise.resolve({ text: "Resposta da IA" });
    if (path.includes("/summary/") || path.includes("/next-steps/")) return Promise.resolve({ text: "Resumo da IA" });
    if (path.includes("/discovery/") || path.includes("/assessment/")) return Promise.resolve({ text: "Análise da reunião", interaction: 9, artifact: artifact() });
    if (path.includes("/extrair-decisoes/")) return Promise.resolve({ text: "[]", interaction: 9, decisoes: [] });
    if (path.startsWith("/artifacts")) return Promise.resolve([artifact()]);
    if (path.includes("/risk/")) return Promise.resolve({ project_id: 1, name: "Projeto X", score: 0, level: "baixo", signals: [] });
    if (path.includes("/health/")) return Promise.resolve({ project_id: 1, name: "Projeto X", score: 90, level: "saudável", signals: [] });
    if (path.startsWith("/projects/")) return Promise.resolve({ id: 1, name: "Projeto X", description: "", client: 1, owner: 1, start_date: "2026-08-01", due_date: "2026-09-01", status: "active", service: null, actual_value: "0", cost: "0", is_overdue: false, ai_maturity: null, ai_potential: null, ai_opportunity: null, ai_dimensions: [], ai_score_summary: "", ai_scored_at: null, ai_score_reviewed: false, account_vertical: 7, account_vertical_name: "Igrejas" });
    if (path.startsWith("/milestones")) return Promise.resolve([{ id: 1, project: 1, title: "Marco 1", description: "", owner: 1, due_date: "2026-08-15", completed_at: null, status: "todo", party: "provider", is_overdue: true }]);
    if (path.startsWith("/tasks")) return Promise.resolve([{ id: 1, project: 1, title: "Tarefa 1", description: "", owner: 1, due_date: "2026-08-10", completed_at: null, status: "todo", party: "provider", is_overdue: false, milestone: null }]);
    if (path.startsWith("/meetings")) return Promise.resolve([{ id: 1, project: 1, title: "Kickoff", date: "2026-08-05", recording_url: "https://rec/1", transcript: "Cliente descreveu suas dores.", status: "held" }]);
    if (path.startsWith("/pendencias")) return Promise.resolve([{ id: 1, project: 1, title: "Aprovar escopo", description: "", status: "open", party: "client", owner: null, resolved_at: null }]);
    if (path.startsWith("/decisoes")) return Promise.resolve([{ id: 1, project: 1, project_phase: 10, title: "Adotar fila gerenciada", rationale: "Custa menos que o Memorystore.", decided_on: "2026-08-06", decided_by: "Marina", status: "draft", source_meeting: 1, published_at: null }]);
    if (path.startsWith("/riscos")) return Promise.resolve([{ id: 1, project: 1, title: "ERP do cliente pode atrasar a carga", description: "", probability: "high", impact: "medium", mitigation: "Janela alternativa negociada com o TI.", status: "open", owner: 2, resolved_at: null }]);
    if (path.startsWith("/project-members")) return Promise.resolve([{ id: 7, project: 1, user: 3, user_name: "Ana Lima", user_username: "ana", user_role: "delivery", added_by: 1, created_at: "2026-08-05T10:00:00Z" }]);
    if (path.startsWith("/github-projections")) return Promise.resolve([{ id: 3, project: 1, handoff: null, repository: "acme/repo", issue_number: 18, issue_url: "https://github.com/acme/repo/issues/18", projection_status: "current", state: "current", stale_after_seconds: 3600, issue_state: "open", pr_state: "open", pr_number: 42, pr_url: "https://github.com/acme/repo/pull/42", head_sha: "abc1234def", head_ref: "feature/x", review_state: "approved", ci_state: "success", observed_at: "2026-08-27T10:00:00Z", last_event_at: "2026-08-27T10:00:00Z", last_delivery_id: "d1", last_event_type: "issues", last_error_code: "", last_error_message: "", created_at: "2026-08-27T09:00:00Z", updated_at: "2026-08-27T10:00:00Z" }]);
    return Promise.resolve([]);
  });
}

function comFase() {
  const anterior = mocks.api.getMockImplementation()!;
  mocks.api.mockImplementation((path: string, options?: { method?: string }) =>
    path.startsWith("/project-phases") && !options?.method
      ? Promise.resolve([projectPhase()])
      : anterior(path, options));
}

beforeEach(() => { mocks.api.mockReset(); mocks.auth = { aiEnabled: true }; mocks.people = []; stub(); });
afterEach(cleanup);

test("mostra projeto com marcos e tarefas", async () => {
  render(<ProjectDetailPage id={1} />);
  expect(await screen.findByText("Projeto X")).toBeInTheDocument();
  expect(screen.getAllByText("Marco 1").length).toBeGreaterThan(0);
  expect(screen.getByText("Tarefa 1")).toBeInTheDocument();
});

test("projeta o estado de entrega do GitHub (FDD 041)", async () => {
  render(<ProjectDetailPage id={1} />);
  await screen.findByText("Projeto X");
  expect(await screen.findByText("acme/repo#18")).toBeInTheDocument();
  // O estado visível é o confirmado, distinto de desatualizado/indisponível.
  expect(screen.getByText("Atual")).toBeInTheDocument();
  expect(screen.getByText("Verde")).toBeInTheDocument();
});

test("pergunta ao assistente de IA e mostra a resposta", async () => {
  const user = userEvent.setup();
  render(<ProjectDetailPage id={1} />);
  await screen.findByText("Projeto X");
  await user.type(screen.getByLabelText("Pergunta ao assistente"), "Qual o status?");
  await user.click(screen.getByRole("button", { name: "Perguntar" }));
  expect(await screen.findByText("Resposta da IA")).toBeInTheDocument();
});

test("resume o projeto com IA", async () => {
  const user = userEvent.setup();
  render(<ProjectDetailPage id={1} />);
  await screen.findByText("Projeto X");
  await user.click(screen.getByRole("button", { name: "Resumir projeto" }));
  expect(await screen.findByText("Resumo da IA")).toBeInTheDocument();
});

test("edita status e prazo do projeto", async () => {
  const user = userEvent.setup();
  render(<ProjectDetailPage id={1} />);
  await user.click(await screen.findByRole("button", { name: "Editar" }));
  const status = screen.getByLabelText("Status do projeto");
  await user.selectOptions(status, "completed");
  await user.click(screen.getByRole("button", { name: "Salvar projeto" }));
  await waitFor(() => expect(mocks.api).toHaveBeenCalledWith("/projects/1/", expect.objectContaining({ method: "PATCH" })));
});

test("cria marco e tarefa e conclui um item", async () => {
  const user = userEvent.setup();
  const { container } = render(<ProjectDetailPage id={1} />);
  await screen.findByText("Projeto X");

  await user.type(screen.getByPlaceholderText("Novo marco"), "Marco novo");
  await user.type(screen.getByPlaceholderText("Nova tarefa"), "Tarefa nova");
  const dateInputs = container.querySelectorAll('input[type="date"]');
  fireEvent.change(dateInputs[0], { target: { value: "2026-08-20" } });
  fireEvent.change(dateInputs[1], { target: { value: "2026-08-22" } });

  await user.click(screen.getByLabelText("Adicionar marco"));
  await waitFor(() => expect(mocks.api).toHaveBeenCalledWith("/milestones/", expect.objectContaining({ method: "POST" })));

  await user.click(screen.getByLabelText("Adicionar tarefa"));
  await waitFor(() => expect(mocks.api).toHaveBeenCalledWith("/tasks/", expect.objectContaining({ method: "POST" })));

  await user.click(screen.getByLabelText("Concluir Marco 1"));
  await waitFor(() => expect(mocks.api).toHaveBeenCalledWith("/milestones/1/", expect.objectContaining({ method: "PATCH" })));
});

test("reabre o que foi concluído por engano", async () => {
  // Antes o círculo era `disabled` depois de concluir: marcação errada não tinha volta pela tela.
  stub();
  const base = mocks.api.getMockImplementation()!;
  mocks.api.mockImplementation((path: string, options?: { method?: string }) =>
    path.startsWith("/tasks") && !options?.method
      ? Promise.resolve([{ id: 2, project: 1, title: "Tarefa feita", description: "", owner: 1, due_date: "2026-08-20", completed_at: "2026-08-06T12:00:00Z", status: "done", party: "provider", is_overdue: false, milestone: null }])
      : base(path, options));
  const user = userEvent.setup();
  render(<ProjectDetailPage id={1} />);
  await screen.findByText("Tarefa feita");

  await user.click(screen.getByLabelText("Reabrir Tarefa feita"));

  await waitFor(() => expect(mocks.api).toHaveBeenCalledWith("/tasks/2/", expect.objectContaining({
    method: "PATCH", body: expect.stringContaining("\"status\":\"todo\""),
  })));
});

test("cria reunião e resolve pendência", async () => {
  const user = userEvent.setup();
  const { container } = render(<ProjectDetailPage id={1} />);
  await screen.findByText("Projeto X");
  expect(screen.getByText("Kickoff")).toBeInTheDocument();
  expect(screen.getByText("Aprovar escopo")).toBeInTheDocument();

  await user.type(screen.getByPlaceholderText("Título da reunião"), "Revisão");
  const dateInputs = container.querySelectorAll('input[type="date"]');
  fireEvent.change(dateInputs[2], { target: { value: "2026-08-25" } }); // 0 marco, 1 tarefa, 2 reunião
  await user.click(screen.getByLabelText("Adicionar reunião"));
  await waitFor(() => expect(mocks.api).toHaveBeenCalledWith("/meetings/", expect.objectContaining({ method: "POST" })));

  await user.click(screen.getByLabelText("Resolver Aprovar escopo"));
  await waitFor(() => expect(mocks.api).toHaveBeenCalledWith("/pendencias/1/", expect.objectContaining({ method: "PATCH" })));
});

test("alterna a reunião entre agendada e realizada", async () => {
  // O selo de status não tinha controle nenhum: toda reunião nascia "Agendada" e ficava assim.
  const user = userEvent.setup();
  render(<ProjectDetailPage id={1} />);
  await screen.findByText("Kickoff");

  await user.click(screen.getByLabelText("Marcar Kickoff como agendada"));

  await waitFor(() => expect(mocks.api).toHaveBeenCalledWith("/meetings/1/", expect.objectContaining({
    method: "PATCH", body: expect.stringContaining("\"status\":\"scheduled\""),
  })));
});

test("gera discovery e assessment da reunião por IA", async () => {
  const user = userEvent.setup();
  render(<ProjectDetailPage id={1} />);
  await screen.findByText("Projeto X");

  await user.click(screen.getByRole("button", { name: "Discovery" }));
  await waitFor(() => expect(mocks.api).toHaveBeenCalledWith("/meetings/1/discovery/", expect.objectContaining({ method: "POST" })));

  await user.click(screen.getByRole("button", { name: "Assessment" }));
  await waitFor(() => expect(mocks.api).toHaveBeenCalledWith("/meetings/1/assessment/", expect.objectContaining({ method: "POST" })));
});

test("o texto da reunião fica registrado como artefato, não some da tela", async () => {
  render(<ProjectDetailPage id={1} />);
  await screen.findByText("Projeto X");

  expect(await screen.findByText("Discovery — Kickoff")).toBeInTheDocument();
  expect(screen.getByLabelText("Conteúdo de Discovery — Kickoff")).toHaveValue("Análise da reunião");
  expect(mocks.api).toHaveBeenCalledWith("/artifacts/?project=1");
});

test("gera AI Score da reunião por IA", async () => {
  const user = userEvent.setup();
  render(<ProjectDetailPage id={1} />);
  await screen.findByText("Projeto X");

  await user.click(screen.getByRole("button", { name: "AI Score" }));
  await waitFor(() => expect(mocks.api).toHaveBeenCalledWith("/meetings/1/ai-score/", expect.objectContaining({ method: "POST" })));
});

test("mostra erro quando a geração do AI Score falha", async () => {
  stub();
  mocks.api.mockImplementation((path: string, init?: RequestInit) => {
    if (path === "/meetings/1/ai-score/" && init?.method === "POST") return Promise.reject(new Error("IA indisponível"));
    if (path.includes("/risk/")) return Promise.resolve({ project_id: 1, name: "Projeto X", score: 0, level: "baixo", signals: [] });
    if (path.includes("/health/")) return Promise.resolve({ project_id: 1, name: "Projeto X", score: 90, level: "saudável", signals: [] });
    if (path.startsWith("/projects/")) return Promise.resolve({ id: 1, name: "Projeto X", description: "", client: 1, owner: 1, start_date: "2026-08-01", due_date: "2026-09-01", status: "active", service: null, actual_value: "0", cost: "0", is_overdue: false, ai_maturity: null, ai_potential: null, ai_opportunity: null, ai_dimensions: [], ai_score_summary: "", ai_scored_at: null, ai_score_reviewed: false });
    if (path.startsWith("/meetings")) return Promise.resolve([{ id: 1, project: 1, title: "Kickoff", date: "2026-08-05", recording_url: "", transcript: "Cliente descreveu suas dores.", status: "held" }]);
    return Promise.resolve([]);
  });
  const user = userEvent.setup();
  render(<ProjectDetailPage id={1} />);
  await screen.findByText("Projeto X");

  await user.click(screen.getByRole("button", { name: "AI Score" }));
  expect(await screen.findByText("IA indisponível")).toBeInTheDocument();
});

test("mostra painel de AI Score quando o projeto já foi pontuado", async () => {
  mocks.api.mockImplementation((path: string) => {
    if (path.includes("/risk/")) return Promise.resolve({ project_id: 1, name: "Projeto X", score: 0, level: "baixo", signals: [] });
    if (path.includes("/health/")) return Promise.resolve({ project_id: 1, name: "Projeto X", score: 90, level: "saudável", signals: [] });
    if (path.startsWith("/projects/")) return Promise.resolve({ id: 1, name: "Projeto X", description: "", client: 1, owner: 1, start_date: "2026-08-01", due_date: "2026-09-01", status: "active", service: null, actual_value: "0", cost: "0", is_overdue: false, ai_maturity: 40, ai_potential: 85, ai_opportunity: 85, ai_dimensions: [{ label: "Dados", score: 30 }], ai_score_summary: "Espaço para automação", ai_scored_at: "2026-08-04T12:00:00Z", ai_score_reviewed: false });
    if (path.startsWith("/meetings")) return Promise.resolve([]);
    return Promise.resolve([]);
  });
  render(<ProjectDetailPage id={1} />);
  await screen.findByText("Projeto X");

  expect(screen.getByText("Maturidade")).toBeInTheDocument();
  expect(screen.getByText("40/100")).toBeInTheDocument();
  expect(screen.getByText("Dados")).toBeInTheDocument();
  expect(screen.getByText("Rascunho — revisar")).toBeInTheDocument();
});

test("publica o AI Score ao cliente (revisão)", async () => {
  mocks.auth = { aiEnabled: true, user: { role: "admin", is_admin: true } };
  mocks.api.mockImplementation((path: string) => {
    if (path.includes("/risk/")) return Promise.resolve({ project_id: 1, name: "Projeto X", score: 0, level: "baixo", signals: [] });
    if (path.includes("/health/")) return Promise.resolve({ project_id: 1, name: "Projeto X", score: 90, level: "saudável", signals: [] });
    if (path.startsWith("/projects/")) return Promise.resolve({ id: 1, name: "Projeto X", description: "", client: 1, owner: 1, start_date: "2026-08-01", due_date: "2026-09-01", status: "active", service: null, actual_value: "0", cost: "0", is_overdue: false, ai_maturity: 40, ai_potential: 85, ai_opportunity: 85, ai_dimensions: [{ label: "Dados", score: 30 }], ai_score_summary: "Espaço para automação", ai_scored_at: "2026-08-04T12:00:00Z", ai_score_reviewed: false });
    return Promise.resolve([]);
  });
  const user = userEvent.setup();
  render(<ProjectDetailPage id={1} />);
  await screen.findByText("Projeto X");
  expect(screen.getByText("Espaço para automação")).toBeInTheDocument();

  await user.click(screen.getByLabelText("Publicar ao cliente (revisado)"));
  await waitFor(() => expect(mocks.api).toHaveBeenCalledWith("/projects/1/", expect.objectContaining({ method: "PATCH", body: JSON.stringify({ ai_score_reviewed: true }) })));
});


test("mostra a equipe do projeto e deixa só o admin mexer nela", async () => {
  mocks.auth = { aiEnabled: true, user: { role: "delivery" } };
  render(<ProjectDetailPage id={1} />);

  expect(await screen.findByText("Equipe do projeto")).toBeInTheDocument();
  expect(screen.getByText("Ana Lima")).toBeInTheDocument();
  expect(screen.queryByLabelText("Adicionar à equipe")).not.toBeInTheDocument();
});

test("admin adiciona alguém à equipe", async () => {
  const user = userEvent.setup();
  mocks.auth = { aiEnabled: true, user: { role: "admin", is_admin: true } };
  mocks.people = [{ id: 9, username: "bruno", first_name: "Bruno", role: "delivery" }];
  render(<ProjectDetailPage id={1} />);
  await screen.findByText("Equipe do projeto");

  await user.selectOptions(await screen.findByLabelText("Pessoa a adicionar"), "9");
  await user.click(screen.getByLabelText("Adicionar à equipe"));

  await waitFor(() => expect(mocks.api).toHaveBeenCalledWith("/project-members/", expect.objectContaining({
    method: "POST", body: JSON.stringify({ project: 1, user: 9 }),
  })));
});


// --- Roster de Funcionários Digitais (FDD 026, FDD 025) ----------------------
//
// O backend sempre teve `PATCH`, `DELETE` e `POST /unarchive/` para este recurso, e a tela só
// alcançava `name` e `area` na criação. Os outros seis campos — os que o snapshot leva ao painel
// "Seu Time Digital" do cliente — não tinham como ser preenchidos por tela nenhuma.

const employee = (overrides = {}) => ({
  id: 4, project: 1, name: "Agente Financeiro", area: "Financeiro",
  description: "", status: "building", kpi_label: "", kpi_value: "",
  kpi_unit: "", kpi_direction: "up", kpi_baseline: null, kpi_current: null,
  hours_saved_month: "0.0", roi_month: "0.00", ...overrides,
});

function comRoster(...employees: object[]) {
  const anterior = mocks.api.getMockImplementation()!;
  mocks.api.mockImplementation((path: string, options?: { method?: string }) => {
    if (path.startsWith("/digital-employees") && (options?.method ?? "GET") === "GET") {
      return Promise.resolve(path.includes("archived=1") ? [] : employees);
    }
    return anterior(path, options);
  });
}

test("preenche pela tela os campos que só a API alcançava", async () => {
  const user = userEvent.setup();
  mocks.auth = { aiEnabled: true, user: { role: "delivery" } };
  comRoster(employee());
  render(<ProjectDetailPage id={1} />);
  await screen.findByText("Agente Financeiro");

  await user.click(screen.getByLabelText("Editar Agente Financeiro"));
  fireEvent.change(screen.getByLabelText("O que ele faz"), { target: { value: "Concilia notas fiscais." } });
  await user.selectOptions(screen.getByLabelText("Status"), "active");
  fireEvent.change(screen.getByLabelText("Rótulo do KPI"), { target: { value: "Notas/mês" } });
  fireEvent.change(screen.getByLabelText("Valor do KPI (texto livre)"), { target: { value: "312" } });
  await user.selectOptions(screen.getByLabelText("Unidade do KPI"), "count");
  fireEvent.change(screen.getByLabelText("Horas poupadas/mês"), { target: { value: "40" } });
  fireEvent.change(screen.getByLabelText("ROI/mês (R$)"), { target: { value: "8000" } });
  await user.click(screen.getByRole("button", { name: "Salvar" }));

  await waitFor(() => expect(mocks.api).toHaveBeenCalledWith("/digital-employees/4/", expect.objectContaining({
    method: "PATCH",
    body: JSON.stringify({
      name: "Agente Financeiro", area: "Financeiro", status: "active",
      description: "Concilia notas fiscais.", kpi_label: "Notas/mês", kpi_value: "312",
      kpi_unit: "count", kpi_direction: "up",
      hours_saved_month: "40", roi_month: "8000",
    }),
  })));
});

/**
 * A metade de **cliente** da decisão C1 do DAP `dap-prove-e-valor-r1`.
 *
 * O servidor já ignora `kpi_baseline`/`kpi_current` desde a ADR 0055 — quem escrevesse por ali
 * receberia 200 sem efeito. É justamente por isso que este teste existe: um campo morto que o
 * servidor aceita em silêncio não deixa nada vermelho, e a próxima pessoa a ler a tela concluiria
 * que ela ainda escreve a medição. A medição mora no PROVE, e o ativo apenas a referencia.
 */
test("o formulário do Time Digital não escreve mais a medição do KPI", async () => {
  const user = userEvent.setup();
  mocks.auth = { aiEnabled: true, user: { role: "delivery" } };
  comRoster(employee({ kpi_baseline: "260.00", kpi_current: "65.00" }));
  render(<ProjectDetailPage id={1} />);
  await screen.findByText("Agente Financeiro");

  await user.click(screen.getByLabelText("Editar Agente Financeiro"));
  expect(screen.queryByLabelText("Antes (base)")).toBeNull();
  expect(screen.queryByLabelText("Depois (atual)")).toBeNull();

  await user.click(screen.getByRole("button", { name: "Salvar" }));
  await waitFor(() => expect(mocks.api).toHaveBeenCalledWith("/digital-employees/4/", expect.anything()));
  const corpo = mocks.api.mock.calls.find(([rota, opcoes]) =>
    rota === "/digital-employees/4/" && opcoes?.method === "PATCH")![1].body as string;
  expect(corpo).not.toContain("kpi_baseline");
  expect(corpo).not.toContain("kpi_current");
});

test("decimal em branco vira zero em vez de 400", async () => {
  // O serializer recusa `""` num `DecimalField`. Mandar o campo vazio devolveria erro de validação
  // sobre algo que a pessoa deliberadamente não preencheu.
  const user = userEvent.setup();
  mocks.auth = { aiEnabled: true, user: { role: "delivery" } };
  comRoster(employee({ hours_saved_month: "", roi_month: "" }));
  render(<ProjectDetailPage id={1} />);
  await screen.findByText("Agente Financeiro");

  await user.click(screen.getByLabelText("Editar Agente Financeiro"));
  await user.click(screen.getByRole("button", { name: "Salvar" }));

  await waitFor(() => expect(mocks.api).toHaveBeenCalledWith("/digital-employees/4/", expect.objectContaining({
    body: expect.stringContaining('"hours_saved_month":"0","roi_month":"0"'),
  })));
});

test("arquivar o funcionário digital pede confirmação", async () => {
  const user = userEvent.setup();
  mocks.auth = { aiEnabled: true, user: { role: "delivery" } };
  comRoster(employee());
  render(<ProjectDetailPage id={1} />);
  await screen.findByText("Agente Financeiro");

  await user.click(screen.getByLabelText("Arquivar Agente Financeiro"));
  expect(screen.getByText("Arquivar funcionário digital")).toBeInTheDocument();
  await user.click(screen.getByRole("button", { name: "Arquivar" }));

  await waitFor(() => expect(mocks.api).toHaveBeenCalledWith("/digital-employees/4/", expect.objectContaining({ method: "DELETE" })));
});

test("os arquivados têm onde ser restaurados", async () => {
  // "Quem promete restauração precisa oferecê-la" (FDD 025): o diálogo acima diz que dá para
  // restaurar, e antes desta entrega não havia onde.
  const user = userEvent.setup();
  mocks.auth = { aiEnabled: true, user: { role: "delivery" } };
  const anterior = mocks.api.getMockImplementation()!;
  mocks.api.mockImplementation((path: string, options?: { method?: string }) => {
    if (path.startsWith("/digital-employees") && (options?.method ?? "GET") === "GET") {
      return Promise.resolve(path.includes("archived=1") ? [employee({ name: "Agente Aposentado" })] : []);
    }
    return anterior(path, options);
  });
  render(<ProjectDetailPage id={1} />);
  await screen.findByText("Funcionários Digitais");

  await user.click(screen.getByLabelText("Mostrar arquivados"));
  await screen.findByText("Agente Aposentado");
  await user.click(screen.getByRole("button", { name: "Restaurar" }));

  await waitFor(() => expect(mocks.api).toHaveBeenCalledWith("/digital-employees/4/unarchive/", expect.objectContaining({ method: "POST" })));
});

test("Vendas lê o roster e não mexe nele", async () => {
  // A permissão é do backend (`RolePermission` dá só leitura a Vendas); a tela não pode oferecer
  // um botão que responderia 403.
  mocks.auth = { aiEnabled: true, user: { role: "sales" } };
  comRoster(employee());
  render(<ProjectDetailPage id={1} />);
  await screen.findByText("Agente Financeiro");

  expect(screen.queryByLabelText("Editar Agente Financeiro")).not.toBeInTheDocument();
  expect(screen.queryByLabelText("Arquivar Agente Financeiro")).not.toBeInTheDocument();
  expect(screen.queryByLabelText("Adicionar funcionário digital")).not.toBeInTheDocument();
});


// --- Instanciar da biblioteca (FDD 026) -------------------------------------
//
// O caminho que a metodologia quer: o bloco nasce preenchido, em vez de um cartão vazio para
// alguém completar à mão — que era o estado anterior, e a razão de tudo chegar ao cliente zerado.

const blueprint = (overrides = {}) => ({
  id: 3, name: "SDR", area: "commercial", area_display: "Comercial",
  description: "Qualifica lead fora do horário.", kpi_label: "Leads qualificados/mês",
  default_hours_saved_month: "40.0", default_roi_month: "8000.00", service: null,
  service_name: "", active: true, variants: [], resolved: null, has_variant: true, ...overrides,
});

function comCatalogo(...catalog: object[]) {
  const anterior = mocks.api.getMockImplementation()!;
  mocks.api.mockImplementation((path: string, options?: { method?: string }) => {
    if (path.startsWith("/digital-employee-blueprints")) return Promise.resolve(catalog);
    if (path.includes("/from-blueprint/")) return Promise.resolve({ id: 9 });
    if (path.startsWith("/digital-employees") && (options?.method ?? "GET") === "GET") return Promise.resolve([]);
    return anterior(path, options);
  });
}

test("instancia um Funcionário Digital a partir do catálogo", async () => {
  const user = userEvent.setup();
  mocks.auth = { aiEnabled: true, user: { role: "delivery" } };
  comCatalogo(blueprint());
  render(<ProjectDetailPage id={1} />);
  await screen.findByText("Funcionários Digitais");

  // O catálogo é pedido já resolvido pela vertical do cliente — é o que a instanciação vai copiar.
  await waitFor(() => expect(mocks.api).toHaveBeenCalledWith("/digital-employee-blueprints/?active=1&vertical=7"));
  await user.selectOptions(await screen.findByLabelText("Adicionar da biblioteca"), "3");
  await user.click(screen.getByRole("button", { name: "Instanciar" }));

  // **Sem `kpi_baseline`** (decisão C1): o backend deixou de aceitá-lo, e o "antes" virou uma
  // `Measurement(kind=baseline)` registrada no PROVE.
  await waitFor(() => expect(mocks.api).toHaveBeenCalledWith("/projects/1/digital-employees/from-blueprint/", expect.objectContaining({
    method: "POST", body: JSON.stringify({ blueprint: 3 }),
  })));
});

test("sem catálogo, a tela não mostra um seletor vazio", async () => {
  // Instalação nova não tem biblioteca. Oferecer um `<select>` sem opção seria prometer um caminho
  // que não existe — o formulário livre continua ali e dá conta.
  mocks.auth = { aiEnabled: true, user: { role: "delivery" } };
  comCatalogo();
  render(<ProjectDetailPage id={1} />);
  await screen.findByText("Funcionários Digitais");

  expect(screen.queryByLabelText("Adicionar da biblioteca")).not.toBeInTheDocument();
  expect(screen.getByLabelText("Adicionar funcionário digital")).toBeInTheDocument();
});

test("Vendas não vê o caminho da biblioteca", async () => {
  mocks.auth = { aiEnabled: true, user: { role: "sales" } };
  comCatalogo(blueprint());
  render(<ProjectDetailPage id={1} />);
  await screen.findByText("Funcionários Digitais");

  expect(screen.queryByLabelText("Adicionar da biblioteca")).not.toBeInTheDocument();
});

test("a decisão em rascunho aparece marcada como tal, e publicar é um clique", async () => {
  // O selo é a única coisa na tela que diz **se o cliente vê**: rascunho não entra no snapshot
  // (FDD 032), e é isso que faz a extração por IA não alcançar o portal antes de alguém olhar.
  stub();
  comFase();
  render(<ProjectDetailPage id={1} />);

  expect(await screen.findByText("Adotar fila gerenciada")).toBeTruthy();
  expect(screen.getByText("Custa menos que o Memorystore.")).toBeTruthy();
  expect(screen.getByText("Fase · PROVE")).toBeTruthy();

  const selo = screen.getByRole("button", { name: "Publicar Adotar fila gerenciada" });
  expect(selo.textContent).toBe("Rascunho");
  fireEvent.click(selo);

  await waitFor(() => expect(mocks.api).toHaveBeenCalledWith(
    "/decisoes/1/",
    expect.objectContaining({ method: "PATCH", body: JSON.stringify({ status: "published" }) }),
  ));
});

test("registra decisão manual com fase escolhida explicitamente", async () => {
  const user = userEvent.setup();
  stub();
  comFase();
  render(<ProjectDetailPage id={1} />);
  await screen.findByText("Projeto X");

  await user.type(screen.getByLabelText("Título"), "Validar oferta com contas piloto");
  await user.selectOptions(screen.getByLabelText("Fase da jornada"), "10");
  await user.click(screen.getByLabelText("Adicionar decisão"));

  await waitFor(() => expect(mocks.api).toHaveBeenCalledWith(
    "/decisoes/",
    expect.objectContaining({
      method: "POST",
      body: JSON.stringify({
        project: 1,
        title: "Validar oferta com contas piloto",
        rationale: "",
        decided_by: "",
        project_phase: 10,
      }),
    }),
  ));
});

test("rascunho sem fase exige vínculo humano antes de publicar", async () => {
  comFase();
  const base = mocks.api.getMockImplementation()!;
  mocks.api.mockImplementation((path: string, options?: { method?: string }) =>
    path.startsWith("/decisoes") && !options?.method
      ? Promise.resolve([{ id: 2, project: 1, project_phase: null, title: "Priorizar onboarding assistido", rationale: "", decided_on: null, decided_by: "", status: "draft", source_meeting: 1, published_at: null }])
      : base(path, options));
  const user = userEvent.setup();
  render(<ProjectDetailPage id={1} />);

  const publicar = await screen.findByRole("button", { name: "Publicar Priorizar onboarding assistido" });
  expect(publicar).toBeDisabled();
  await user.selectOptions(screen.getByLabelText("Fase de Priorizar onboarding assistido"), "10");

  await waitFor(() => expect(mocks.api).toHaveBeenCalledWith(
    "/decisoes/2/",
    expect.objectContaining({ method: "PATCH", body: JSON.stringify({ project_phase: 10 }) }),
  ));
});

// --- Risk Register (FDD 034) ------------------------------------------------
//
// O painel "Sinais de atraso" logo acima é o risco **calculado** — o que já escorregou. Este é o
// declarado: o que a equipe teme e ainda não aconteceu, que é o único momento em que mitigar
// ainda é possível. Os dois convivem na mesma tela e não se substituem.

test("o risco declarado aparece com probabilidade, impacto e mitigação", async () => {
  stub();
  render(<ProjectDetailPage id={1} />);

  expect(await screen.findByText("ERP do cliente pode atrasar a carga")).toBeTruthy();
  expect(screen.getByText("Probabilidade alta · impacto médio")).toBeTruthy();
  expect(screen.getByText("Janela alternativa negociada com o TI.")).toBeTruthy();
  expect(mocks.api).toHaveBeenCalledWith("/riscos/?project=1");
});

test("registra um risco novo com os dois eixos", async () => {
  const user = userEvent.setup();
  stub();
  render(<ProjectDetailPage id={1} />);
  await screen.findByText("Projeto X");

  await user.type(screen.getByPlaceholderText("O que pode dar errado"), "Equipe do cliente indisponível");
  await user.selectOptions(screen.getByLabelText("Probabilidade do risco"), "low");
  await user.selectOptions(screen.getByLabelText("Impacto do risco"), "high");
  await user.type(screen.getByPlaceholderText("Plano de mitigação — o que se faz para o risco não virar fato"), "Antecipar as entrevistas.");
  await user.click(screen.getByLabelText("Adicionar risco"));

  await waitFor(() => expect(mocks.api).toHaveBeenCalledWith("/riscos/", expect.objectContaining({
    method: "POST",
    body: JSON.stringify({ project: 1, title: "Equipe do cliente indisponível", probability: "low", impact: "high", mitigation: "Antecipar as entrevistas." }),
  })));
});

test("encerrar o risco é uma escolha entre quatro saídas, não um alternador", async () => {
  // Mitigado, aceito e materializado não são sinônimos: o primeiro resolveu, o segundo decidiu
  // conviver, o terceiro aconteceu. Um botão de dois estados obrigaria a inventar ordem entre eles.
  const user = userEvent.setup();
  stub();
  render(<ProjectDetailPage id={1} />);
  await screen.findByText("ERP do cliente pode atrasar a carga");

  await user.selectOptions(screen.getByLabelText("Estado de ERP do cliente pode atrasar a carga"), "materialized");

  await waitFor(() => expect(mocks.api).toHaveBeenCalledWith("/riscos/1/", expect.objectContaining({
    method: "PATCH", body: JSON.stringify({ status: "materialized" }),
  })));
});

test("arquivar o risco pede confirmação", async () => {
  const user = userEvent.setup();
  stub();
  render(<ProjectDetailPage id={1} />);
  await screen.findByText("ERP do cliente pode atrasar a carga");

  await user.click(screen.getByLabelText("Arquivar ERP do cliente pode atrasar a carga"));
  expect(screen.getByText("Arquivar risco")).toBeInTheDocument();
  await user.click(screen.getByRole("button", { name: "Arquivar" }));

  await waitFor(() => expect(mocks.api).toHaveBeenCalledWith("/riscos/1/", expect.objectContaining({ method: "DELETE" })));
});

test("extrair decisões da transcrição chama a reunião, não a decisão", async () => {
  // O insumo é a transcrição, e é por isso que a action mora no `MeetingViewSet` — o mesmo lugar
  // do Discovery. Um botão que chamasse `/decisoes/` não teria de onde extrair.
  stub();
  render(<ProjectDetailPage id={1} />);

  fireEvent.click(await screen.findByRole("button", { name: "Decisões" }));

  await waitFor(() => expect(mocks.api).toHaveBeenCalledWith(
    "/meetings/1/extrair-decisoes/", expect.objectContaining({ method: "POST" }),
  ));
});

test("extrair processos mapeia a operação a partir da transcrição", async () => {
  // Mesmo argumento do botão de decisões acima: o insumo é a transcrição, então a action mora no
  // `MeetingViewSet`. O resultado, porém, não aparece aqui — o processo pende do cliente (FDD 039),
  // e sem a linha de sucesso o clique não se distinguiria de uma falha silenciosa.
  stub();
  render(<ProjectDetailPage id={1} />);
  await screen.findByText("Projeto X");

  mocks.api.mockImplementationOnce(() => Promise.resolve({ text: "[]", interaction: 9, processes: [{ id: 1 }, { id: 2 }] }));
  fireEvent.click(screen.getByRole("button", { name: "Processos" }));

  await waitFor(() => expect(mocks.api).toHaveBeenCalledWith(
    "/meetings/1/estruturar/", expect.objectContaining({ method: "POST" }),
  ));
  expect(await screen.findByRole("status")).toHaveTextContent(/2 processo\(s\) mapeado\(s\) como hipótese/);
});

test("o 409 da extração mostra a mensagem do servidor, e não uma falha genérica", async () => {
  // **A divergência de dialeto é deliberada** (ver `estruturarProcessos`): esta é a única ação da
  // tela que recusa reexecução, e o corpo do 409 traz quantos processos já existem e qual é a
  // saída. `mensagemDeFalha` acrescenta a orientação da tabela de `erros.ts`; o
  // `(cause as Error).message` do resto da página entregaria a metade que não diz o que fazer.
  stub();
  render(<ProjectDetailPage id={1} />);
  await screen.findByText("Projeto X");

  mocks.api.mockImplementationOnce(() => Promise.reject(Object.assign(
    new Error("Esta reunião já tem 3 processo(s) mapeado(s). Arquive-os ou edite-os em vez de extrair de novo."),
    { status: 409 },
  )));
  fireEvent.click(screen.getByRole("button", { name: "Processos" }));

  const alerta = await screen.findByRole("alert");
  expect(alerta).toHaveTextContent(/já tem 3 processo\(s\) mapeado\(s\)/);
  expect(alerta).toHaveTextContent(/recarregue para ver o que vale agora/);
});
