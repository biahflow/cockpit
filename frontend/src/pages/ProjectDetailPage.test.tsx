import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, expect, test, vi } from "vitest";

import { ProjectDetailPage } from "./ProjectDetailPage";

const mocks = vi.hoisted(() => ({
  api: vi.fn(),
  auth: { aiEnabled: true } as { aiEnabled: boolean; user?: { role: string; is_admin?: boolean } },
  people: [] as { id: number; username: string; first_name: string; role: string }[],
}));
vi.mock("../api", () => ({ api: mocks.api, listUsers: () => Promise.resolve(mocks.people) }));
vi.mock("../auth", () => ({ useAuth: () => mocks.auth }));

const artifact = () => ({
  id: 5, kind: "discovery", kind_display: "Discovery", status: "draft", status_display: "Rascunho",
  title: "Discovery — Kickoff", content: "Análise da reunião", opportunity: null, project: 1,
  source_meeting: 1, document: null, ai_interaction: 9, created_by: 1, sent_at: null,
  decided_at: null, created_at: "2026-08-05T10:00:00Z", updated_at: "2026-08-05T10:00:00Z",
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
    if (path.startsWith("/projects/")) return Promise.resolve({ id: 1, name: "Projeto X", description: "", client: 1, owner: 1, start_date: "2026-08-01", due_date: "2026-09-01", status: "active", service: null, actual_value: "0", cost: "0", is_overdue: false, ai_maturity: null, ai_opportunity: null, ai_dimensions: [], ai_score_summary: "", ai_scored_at: null, ai_score_reviewed: false, client_vertical: 7, client_vertical_name: "Igrejas" });
    if (path.startsWith("/milestones")) return Promise.resolve([{ id: 1, project: 1, title: "Marco 1", description: "", owner: 1, due_date: "2026-08-15", completed_at: null, status: "todo", party: "provider", is_overdue: true }]);
    if (path.startsWith("/tasks")) return Promise.resolve([{ id: 1, project: 1, title: "Tarefa 1", description: "", owner: 1, due_date: "2026-08-10", completed_at: null, status: "todo", party: "provider", is_overdue: false, milestone: null }]);
    if (path.startsWith("/meetings")) return Promise.resolve([{ id: 1, project: 1, title: "Kickoff", date: "2026-08-05", recording_url: "https://rec/1", transcript: "Cliente descreveu suas dores.", status: "held" }]);
    if (path.startsWith("/pendencias")) return Promise.resolve([{ id: 1, project: 1, title: "Aprovar escopo", description: "", status: "open", party: "client", owner: null, resolved_at: null }]);
    if (path.startsWith("/decisoes")) return Promise.resolve([{ id: 1, project: 1, title: "Adotar fila gerenciada", rationale: "Custa menos que o Memorystore.", decided_on: "2026-08-06", decided_by: "Marina", status: "draft", source_meeting: 1, published_at: null }]);
    if (path.startsWith("/project-members")) return Promise.resolve([{ id: 7, project: 1, user: 3, user_name: "Ana Lima", user_username: "ana", user_role: "delivery", added_by: 1, created_at: "2026-08-05T10:00:00Z" }]);
    return Promise.resolve([]);
  });
}

beforeEach(() => { mocks.api.mockReset(); mocks.auth = { aiEnabled: true }; mocks.people = []; stub(); });
afterEach(cleanup);

test("mostra projeto com marcos e tarefas", async () => {
  render(<ProjectDetailPage id={1} />);
  expect(await screen.findByText("Projeto X")).toBeInTheDocument();
  expect(screen.getAllByText("Marco 1").length).toBeGreaterThan(0);
  expect(screen.getByText("Tarefa 1")).toBeInTheDocument();
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
    if (path.startsWith("/projects/")) return Promise.resolve({ id: 1, name: "Projeto X", description: "", client: 1, owner: 1, start_date: "2026-08-01", due_date: "2026-09-01", status: "active", service: null, actual_value: "0", cost: "0", is_overdue: false, ai_maturity: null, ai_opportunity: null, ai_dimensions: [], ai_score_summary: "", ai_scored_at: null, ai_score_reviewed: false });
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
    if (path.startsWith("/projects/")) return Promise.resolve({ id: 1, name: "Projeto X", description: "", client: 1, owner: 1, start_date: "2026-08-01", due_date: "2026-09-01", status: "active", service: null, actual_value: "0", cost: "0", is_overdue: false, ai_maturity: 40, ai_opportunity: 85, ai_dimensions: [{ label: "Dados", score: 30 }], ai_score_summary: "Espaço para automação", ai_scored_at: "2026-08-04T12:00:00Z", ai_score_reviewed: false });
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
    if (path.startsWith("/projects/")) return Promise.resolve({ id: 1, name: "Projeto X", description: "", client: 1, owner: 1, start_date: "2026-08-01", due_date: "2026-09-01", status: "active", service: null, actual_value: "0", cost: "0", is_overdue: false, ai_maturity: 40, ai_opportunity: 85, ai_dimensions: [{ label: "Dados", score: 30 }], ai_score_summary: "Espaço para automação", ai_scored_at: "2026-08-04T12:00:00Z", ai_score_reviewed: false });
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
  await user.type(screen.getByLabelText("O que ele faz"), "Concilia notas fiscais.");
  await user.selectOptions(screen.getByLabelText("Status"), "active");
  await user.type(screen.getByLabelText("Rótulo do KPI"), "Notas/mês");
  await user.type(screen.getByLabelText("Valor do KPI (texto livre)"), "312");
  await user.selectOptions(screen.getByLabelText("Unidade do KPI"), "count");
  await user.type(screen.getByLabelText("Antes (base)"), "120");
  await user.type(screen.getByLabelText("Depois (atual)"), "312");
  await user.clear(screen.getByLabelText("Horas poupadas/mês"));
  await user.type(screen.getByLabelText("Horas poupadas/mês"), "40");
  await user.clear(screen.getByLabelText("ROI/mês (R$)"));
  await user.type(screen.getByLabelText("ROI/mês (R$)"), "8000");
  await user.click(screen.getByRole("button", { name: "Salvar" }));

  await waitFor(() => expect(mocks.api).toHaveBeenCalledWith("/digital-employees/4/", expect.objectContaining({
    method: "PATCH",
    body: JSON.stringify({
      name: "Agente Financeiro", area: "Financeiro", status: "active",
      description: "Concilia notas fiscais.", kpi_label: "Notas/mês", kpi_value: "312",
      kpi_unit: "count", kpi_direction: "up", kpi_baseline: "120", kpi_current: "312",
      hours_saved_month: "40", roi_month: "8000",
    }),
  })));
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
  id: 3, name: "SDR", area: "comercial", area_display: "Comercial",
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

  await waitFor(() => expect(mocks.api).toHaveBeenCalledWith("/projects/1/digital-employees/from-blueprint/", expect.objectContaining({
    method: "POST", body: JSON.stringify({ blueprint: 3, kpi_baseline: null }),
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
  render(<ProjectDetailPage />);

  expect(await screen.findByText("Adotar fila gerenciada")).toBeTruthy();
  expect(screen.getByText("Custa menos que o Memorystore.")).toBeTruthy();

  const selo = screen.getByRole("button", { name: "Publicar Adotar fila gerenciada" });
  expect(selo.textContent).toBe("Rascunho");
  fireEvent.click(selo);

  await waitFor(() => expect(mocks.api).toHaveBeenCalledWith(
    "/decisoes/1/",
    expect.objectContaining({ method: "PATCH", body: JSON.stringify({ status: "published" }) }),
  ));
});

test("extrair decisões da transcrição chama a reunião, não a decisão", async () => {
  // O insumo é a transcrição, e é por isso que a action mora no `MeetingViewSet` — o mesmo lugar
  // do Discovery. Um botão que chamasse `/decisoes/` não teria de onde extrair.
  stub();
  render(<ProjectDetailPage />);

  fireEvent.click(await screen.findByRole("button", { name: "Decisões" }));

  await waitFor(() => expect(mocks.api).toHaveBeenCalledWith(
    "/meetings/1/extrair-decisoes/", expect.objectContaining({ method: "POST" }),
  ));
});
