import { cleanup, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, expect, test, vi } from "vitest";

import { ClientDetailPage } from "./ClientDetailPage";

const mocks = vi.hoisted(() => ({
  api: vi.fn(),
  auth: { user: { id: 1, is_admin: true, role: "admin" } } as { user: { id: number; is_admin: boolean; role: string } },
}));
vi.mock("../api", () => ({ api: mocks.api }));
vi.mock("../auth", () => ({ useAuth: () => mocks.auth }));

function stub() {
  mocks.api.mockImplementation((path: string) => {
    if (path === "/clients/1/") return Promise.resolve({ id: 1, name: "Cliente A", legal_name: "ACME SA", tax_id: "123", owner: 1, status: "active", vertical: null, vertical_name: "" });
    if (path === "/verticals/") return Promise.resolve([{ id: 7, name: "Igrejas", slug: "igrejas", position: 0, active: true }]);
    if (path === "/clients/1/overview/") return Promise.resolve({ client_id: 1, name: "Cliente A", status: "active", roi: { revenue: 1000, cost: 250, roi: 3 }, health: { score: 82, level: "saudável", project_id: 5 }, risk_level: "baixo", phase: { name: "Prove", status: "active" }, next_meeting: { title: "Comitê", date: "2026-09-10" }, ai_score: { maturity: 35, opportunity: 80, dimensions: [{ label: "Dados", score: 30 }], summary: "ok", scored_at: "2026-08-04T12:00:00Z" } });
    if (path.startsWith("/contacts")) return Promise.resolve([{ id: 1, client: 1, name: "João", email: "j@x.com", phone: "", job_title: "CEO" }]);
    if (path.startsWith("/activities")) return Promise.resolve([{ id: 9, client: 1, opportunity: null, kind: "call", kind_display: "Ligação", happened_on: "2026-08-10", summary: "Alinhamento de escopo", notes: "Cliente confirmou prazo.", owner: 1, created_at: "2026-08-10T10:00:00Z", updated_at: "2026-08-10T10:00:00Z" }]);
    return Promise.resolve([]);
  });
}

beforeEach(() => { mocks.api.mockReset(); mocks.auth.user = { id: 1, is_admin: true, role: "admin" }; stub(); });
afterEach(cleanup);

test("mostra cliente e seus contatos", async () => {
  render(<ClientDetailPage id={1} />);
  expect(await screen.findByRole("heading", { name: "Cliente A" })).toBeInTheDocument();
  expect(screen.getByText("João")).toBeInTheDocument();
  expect(screen.getByText("CEO")).toBeInTheDocument();
  expect(screen.getByText("Saúde da relação")).toBeInTheDocument();
  expect(screen.getByText("Você está aqui · Prove")).toBeInTheDocument();
  expect(screen.getByText("Maturidade de IA")).toBeInTheDocument();
  expect(screen.getByText("35/100")).toBeInTheDocument();
});

test("salva o cliente, cria e remove contato", async () => {
  const user = userEvent.setup();
  render(<ClientDetailPage id={1} />);
  await screen.findByRole("heading", { name: "Cliente A" });

  await user.clear(screen.getByLabelText("Nome"));
  await user.type(screen.getByLabelText("Nome"), "Cliente B");
  await user.click(screen.getByRole("button", { name: "Salvar alterações" }));
  await waitFor(() => expect(mocks.api).toHaveBeenCalledWith("/clients/1/", expect.objectContaining({ method: "PATCH" })));

  await user.type(screen.getByPlaceholderText("Nome"), "Maria");
  await user.type(screen.getByPlaceholderText("E-mail"), "maria@x.com");
  await user.type(screen.getByPlaceholderText("Telefone"), "1199");
  await user.type(screen.getByPlaceholderText("Cargo"), "CTO");
  await user.click(screen.getByRole("button", { name: "Adicionar contato" }));
  await waitFor(() => expect(mocks.api).toHaveBeenCalledWith("/contacts/", expect.objectContaining({ method: "POST" })));

  await user.click(screen.getByLabelText("Remover João"));
  await user.click(screen.getByRole("button", { name: "Remover" }));
  await waitFor(() => expect(mocks.api).toHaveBeenCalledWith("/contacts/1/", expect.objectContaining({ method: "DELETE" })));
});

test("corrige a situação do cliente e leva o status no PATCH", async () => {
  const user = userEvent.setup();
  render(<ClientDetailPage id={1} />);
  await screen.findByRole("heading", { name: "Cliente A" });
  // O formulário nasce com o que veio da API, não com um default que apagaria o valor real.
  expect(screen.getByLabelText("Situação")).toHaveValue("active");

  await user.selectOptions(screen.getByLabelText("Situação"), "prospect");
  await user.click(screen.getByRole("button", { name: "Salvar alterações" }));

  await waitFor(() => expect(mocks.api).toHaveBeenCalledWith("/clients/1/", expect.objectContaining({
    method: "PATCH", body: expect.stringContaining("\"status\":\"prospect\""),
  })));
});


test("atribui uma vertical ao cliente", async () => {
  // É ela que escolhe a variante do blueprint quando a entrega instancia um bloco (FDD 026).
  const user = userEvent.setup();
  render(<ClientDetailPage id={1} />);
  await screen.findByRole("heading", { name: "Cliente A" });

  await user.selectOptions(screen.getByLabelText("Vertical"), "7");
  await user.click(screen.getByRole("button", { name: "Salvar alterações" }));

  await waitFor(() => expect(mocks.api).toHaveBeenCalledWith("/clients/1/", expect.objectContaining({
    method: "PATCH", body: expect.stringContaining("\"vertical\":7"),
  })));
});

test("cliente sem vertical continua funcionando", async () => {
  // Regra da FDD 026: nada exige vertical. Sem ela o catálogo inteiro segue disponível, genérico.
  render(<ClientDetailPage id={1} />);
  await screen.findByRole("heading", { name: "Cliente A" });

  expect(screen.getByLabelText("Vertical")).toHaveValue("");
});

// --- interações (FDD 035) -----------------------------------------------------------------------

test("lista as interações do cliente e registra uma nova", async () => {
  const user = userEvent.setup();
  render(<ClientDetailPage id={1} />);
  await screen.findByRole("heading", { name: "Cliente A" });

  expect(screen.getByText("Alinhamento de escopo")).toBeInTheDocument();
  expect(screen.getByText(/Ligação · 10\/08\/2026/)).toBeInTheDocument();

  await user.type(screen.getByPlaceholderText("Do que se tratou o contato"), "Ligação de follow-up");
  await user.click(screen.getByRole("button", { name: "Registrar interação" }));

  await waitFor(() => expect(mocks.api).toHaveBeenCalledWith("/activities/", expect.objectContaining({
    method: "POST", body: expect.stringContaining('"client":1'),
  })));
});

test("arquiva uma interação do cliente", async () => {
  const user = userEvent.setup();
  render(<ClientDetailPage id={1} />);
  await screen.findByRole("heading", { name: "Cliente A" });

  await user.click(screen.getByLabelText("Arquivar interação: Alinhamento de escopo"));

  await waitFor(() => expect(mocks.api).toHaveBeenCalledWith("/activities/9/", expect.objectContaining({ method: "DELETE" })));
});

test("entrega não vê o formulário nem o botão de arquivar de interações", async () => {
  mocks.auth.user = { id: 2, is_admin: false, role: "delivery" };
  render(<ClientDetailPage id={1} />);
  await screen.findByText("Alinhamento de escopo");

  expect(screen.queryByPlaceholderText("Do que se tratou o contato")).not.toBeInTheDocument();
  expect(screen.queryByLabelText("Arquivar interação: Alinhamento de escopo")).not.toBeInTheDocument();
});
