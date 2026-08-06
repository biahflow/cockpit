import { cleanup, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, expect, test, vi } from "vitest";

import { ClientDetailPage } from "./ClientDetailPage";

const mocks = vi.hoisted(() => ({ api: vi.fn() }));
vi.mock("../api", () => ({ api: mocks.api }));
vi.mock("../auth", () => ({ useAuth: () => ({ user: { id: 1, is_admin: true, role: "admin" } }) }));

function stub() {
  mocks.api.mockImplementation((path: string) => {
    if (path === "/clients/1/") return Promise.resolve({ id: 1, name: "Cliente A", legal_name: "ACME SA", tax_id: "123", owner: 1, status: "active" });
    if (path === "/clients/1/overview/") return Promise.resolve({ client_id: 1, name: "Cliente A", status: "active", roi: { revenue: 1000, cost: 250, roi: 3 }, health: { score: 82, level: "saudável", project_id: 5 }, risk_level: "baixo", phase: { name: "Prove", status: "active" }, next_meeting: { title: "Comitê", date: "2026-09-10" }, ai_score: { maturity: 35, opportunity: 80, dimensions: [{ label: "Dados", score: 30 }], summary: "ok", scored_at: "2026-08-04T12:00:00Z" } });
    if (path.startsWith("/contacts")) return Promise.resolve([{ id: 1, client: 1, name: "João", email: "j@x.com", phone: "", job_title: "CEO" }]);
    return Promise.resolve([]);
  });
}

beforeEach(() => { mocks.api.mockReset(); stub(); });
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
