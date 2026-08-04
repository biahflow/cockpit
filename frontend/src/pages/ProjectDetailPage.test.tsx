import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, expect, test, vi } from "vitest";

import { ProjectDetailPage } from "./ProjectDetailPage";

const mocks = vi.hoisted(() => ({ api: vi.fn(), auth: { aiEnabled: true } as { aiEnabled: boolean; user?: { role: string } } }));
vi.mock("../api", () => ({ api: mocks.api }));
vi.mock("../auth", () => ({ useAuth: () => mocks.auth }));

function stub() {
  mocks.api.mockImplementation((path: string) => {
    if (path.includes("/assistant/")) return Promise.resolve({ text: "Resposta da IA" });
    if (path.includes("/summary/") || path.includes("/next-steps/")) return Promise.resolve({ text: "Resumo da IA" });
    if (path.includes("/discovery/") || path.includes("/assessment/")) return Promise.resolve({ text: "Análise da reunião", interaction: 9 });
    if (path.includes("/risk/")) return Promise.resolve({ project_id: 1, name: "Projeto X", score: 0, level: "baixo", signals: [] });
    if (path.includes("/health/")) return Promise.resolve({ project_id: 1, name: "Projeto X", score: 90, level: "saudável", signals: [] });
    if (path.startsWith("/projects/")) return Promise.resolve({ id: 1, name: "Projeto X", description: "", client: 1, owner: 1, start_date: "2026-08-01", due_date: "2026-09-01", status: "active", service: null, actual_value: "0", cost: "0", is_overdue: false, ai_maturity: null, ai_opportunity: null, ai_dimensions: [], ai_score_summary: "", ai_scored_at: null, ai_score_reviewed: false });
    if (path.startsWith("/milestones")) return Promise.resolve([{ id: 1, project: 1, title: "Marco 1", description: "", owner: 1, due_date: "2026-08-15", completed_at: null, status: "todo", party: "provider", is_overdue: true }]);
    if (path.startsWith("/tasks")) return Promise.resolve([{ id: 1, project: 1, title: "Tarefa 1", description: "", owner: 1, due_date: "2026-08-10", completed_at: null, status: "todo", party: "provider", is_overdue: false, milestone: null }]);
    if (path.startsWith("/meetings")) return Promise.resolve([{ id: 1, project: 1, title: "Kickoff", date: "2026-08-05", recording_url: "https://rec/1", transcript: "Cliente descreveu suas dores.", status: "held" }]);
    if (path.startsWith("/pendencias")) return Promise.resolve([{ id: 1, project: 1, title: "Aprovar escopo", description: "", status: "open", party: "client", owner: null, resolved_at: null }]);
    return Promise.resolve([]);
  });
}

beforeEach(() => { mocks.api.mockReset(); mocks.auth = { aiEnabled: true }; stub(); });
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

  await user.click(screen.getAllByLabelText("Concluir")[0]);
  await waitFor(() => expect(mocks.api).toHaveBeenCalledWith("/milestones/1/", expect.objectContaining({ method: "PATCH" })));
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

  await user.click(screen.getByLabelText("Resolver"));
  await waitFor(() => expect(mocks.api).toHaveBeenCalledWith("/pendencias/1/", expect.objectContaining({ method: "PATCH" })));
});

test("gera discovery e assessment da reunião por IA", async () => {
  const user = userEvent.setup();
  render(<ProjectDetailPage id={1} />);
  await screen.findByText("Projeto X");

  await user.click(screen.getByRole("button", { name: "Discovery" }));
  await waitFor(() => expect(mocks.api).toHaveBeenCalledWith("/meetings/1/discovery/", expect.objectContaining({ method: "POST" })));
  expect(await screen.findByText("Análise da reunião")).toBeInTheDocument();

  await user.click(screen.getByRole("button", { name: "Assessment" }));
  await waitFor(() => expect(mocks.api).toHaveBeenCalledWith("/meetings/1/assessment/", expect.objectContaining({ method: "POST" })));
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
  mocks.auth = { aiEnabled: true, user: { role: "admin" } };
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
