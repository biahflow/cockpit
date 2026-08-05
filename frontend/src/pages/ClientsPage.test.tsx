import { cleanup, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, expect, test, vi } from "vitest";

import { ClientsPage } from "./ClientsPage";

const mocks = vi.hoisted(() => ({ api: vi.fn() }));
vi.mock("../api", () => ({ api: mocks.api }));

beforeEach(() => {
  mocks.api.mockImplementation((path: string) => {
    if (path.startsWith("/clients/overview/")) return Promise.resolve({ clients: [
      { client_id: 1, name: "Acme", status: "active", roi: { revenue: 0, cost: 0, roi: null }, health: { score: 40, level: "crítico", project_id: 9 }, risk_level: "alto", phase: { name: "Prove", status: "active" }, next_meeting: null },
      { client_id: 2, name: "Beta", status: "prospect", roi: { revenue: 0, cost: 0, roi: null }, health: null, risk_level: null, phase: null, next_meeting: null },
    ] });
    return Promise.resolve({});
  });
});
afterEach(() => { cleanup(); vi.clearAllMocks(); });

test("mostra o semáforo de saúde e filtra clientes por prospect", async () => {
  const user = userEvent.setup();
  render(<ClientsPage />);
  await screen.findByText("Acme");
  expect(screen.getByText("Prospect")).toBeInTheDocument();
  expect(screen.getByText("Ativo")).toBeInTheDocument();
  expect(screen.getByText("Jornada · Prove")).toBeInTheDocument();
  expect(screen.getByLabelText("Saúde crítico")).toBeInTheDocument();
  await user.click(screen.getByRole("button", { name: "Prospects" }));
  await waitFor(() => expect(mocks.api).toHaveBeenCalledWith("/clients/overview/?status=prospect"));
});

test("cadastro declara a situação do cliente, e o default é prospect", async () => {
  const user = userEvent.setup();
  render(<ClientsPage />);
  await screen.findByText("Acme");
  // Default conservador: cadastrar sem pensar não alega uma venda que não houve.
  expect(screen.getByLabelText("Situação")).toHaveValue("prospect");

  await user.type(screen.getByLabelText("Nome do cliente"), "Nova Empresa");
  await user.selectOptions(screen.getByLabelText("Situação"), "active");
  await user.click(screen.getByRole("button", { name: "Cadastrar cliente" }));

  await waitFor(() => expect(mocks.api).toHaveBeenCalledWith("/clients/", expect.objectContaining({
    method: "POST", body: expect.stringContaining("\"status\":\"active\""),
  })));
});

test("filtro sem resultado explica o filtro, não manda cadastrar o primeiro cliente", async () => {
  // A base tem cliente; só o filtro está vazio. Dizer "sua base começa aqui" aqui é falso — e
  // manda fazer algo (cadastrar) que nasceria ativo e não encheria a aba de prospects.
  mocks.api.mockImplementation((path: string) => Promise.resolve(
    path === "/clients/overview/?status=prospect"
      ? { clients: [] }
      : { clients: [{ client_id: 1, name: "Acme", status: "active", roi: { revenue: 0, cost: 0, roi: null }, health: null, risk_level: null, phase: null, next_meeting: null }] },
  ));
  const user = userEvent.setup();
  render(<ClientsPage />);
  await screen.findByText("Acme");
  await user.click(screen.getByRole("button", { name: "Prospects" }));
  expect(await screen.findByText("Nenhum prospect")).toBeInTheDocument();
  expect(screen.queryByText("Sua base começa aqui")).not.toBeInTheDocument();
});
