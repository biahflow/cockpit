import { cleanup, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, expect, test, vi } from "vitest";

import { AccountsPage } from "./AccountsPage";

const mocks = vi.hoisted(() => ({ api: vi.fn() }));
vi.mock("../api", () => ({ api: mocks.api }));

beforeEach(() => {
  mocks.api.mockImplementation((path: string) => {
    if (path.startsWith("/accounts/overview/")) return Promise.resolve({ accounts: [
      { account_id: 1, name: "Acme", lifecycle_status: "active", roi: { revenue: "0.00", cost: "0.00", roi: null }, health: { score: 40, level: "crítico", project_id: 9 }, risk_level: "alto", phase: { name: "Prove", status: "active" }, next_meeting: null },
      { account_id: 2, name: "Beta", lifecycle_status: "prospect", roi: { revenue: "0.00", cost: "0.00", roi: null }, health: null, risk_level: null, phase: null, next_meeting: null },
      { account_id: 3, name: "Gama", lifecycle_status: "inactive", roi: { revenue: "0.00", cost: "0.00", roi: null }, health: null, risk_level: null, phase: null, next_meeting: null },
    ] });
    return Promise.resolve({});
  });
});
afterEach(() => { cleanup(); vi.clearAllMocks(); });

test("mostra o semáforo de saúde e filtra contas por prospect", async () => {
  const user = userEvent.setup();
  render(<AccountsPage />);
  await screen.findByText("Acme");
  expect(screen.getByText("Prospect")).toBeInTheDocument();
  // "Cliente" é o rótulo de `active`, e "Inativo" o do terceiro estado.
  expect(screen.getByText("Cliente")).toBeInTheDocument();
  expect(screen.getByText("Inativo")).toBeInTheDocument();
  expect(screen.getByText("Jornada · Prove")).toBeInTheDocument();
  expect(screen.getByLabelText("Saúde crítico")).toBeInTheDocument();
  await user.click(screen.getByRole("button", { name: "Prospects" }));
  await waitFor(() => expect(mocks.api).toHaveBeenCalledWith("/accounts/overview/?lifecycle_status=prospect"));
});

test("sem filtro, a lista traz os três estados vivos — inativo não é arquivado", async () => {
  render(<AccountsPage />);
  await screen.findByText("Acme");
  expect(screen.getByText("Beta")).toBeInTheDocument();
  expect(screen.getByText("Gama")).toBeInTheDocument();
  expect(mocks.api).toHaveBeenCalledWith("/accounts/overview/");
});

test("cadastro declara a situação da conta, e o default é prospect", async () => {
  const user = userEvent.setup();
  render(<AccountsPage />);
  await screen.findByText("Acme");
  // Default conservador: cadastrar sem pensar não alega uma venda que não houve.
  expect(screen.getByLabelText("Situação")).toHaveValue("prospect");

  await user.type(screen.getByLabelText("Nome da conta"), "Nova Empresa");
  await user.selectOptions(screen.getByLabelText("Situação"), "active");
  await user.click(screen.getByRole("button", { name: "Cadastrar conta" }));

  await waitFor(() => expect(mocks.api).toHaveBeenCalledWith("/accounts/", expect.objectContaining({
    method: "POST", body: expect.stringContaining("\"lifecycle_status\":\"active\""),
  })));
});

test("filtro sem resultado explica o filtro, não manda cadastrar a primeira conta", async () => {
  // A base tem conta; só o filtro está vazio. Dizer "sua base começa aqui" aqui é falso — e
  // manda fazer algo (cadastrar) que nasceria prospect e não encheria a aba de inativos.
  mocks.api.mockImplementation((path: string) => Promise.resolve(
    path === "/accounts/overview/?lifecycle_status=inactive"
      ? { accounts: [] }
      : { accounts: [{ account_id: 1, name: "Acme", lifecycle_status: "active", roi: { revenue: "0.00", cost: "0.00", roi: null }, health: null, risk_level: null, phase: null, next_meeting: null }] },
  ));
  const user = userEvent.setup();
  render(<AccountsPage />);
  await screen.findByText("Acme");
  await user.click(screen.getByRole("button", { name: "Inativos" }));
  expect(await screen.findByText("Nenhuma conta inativa")).toBeInTheDocument();
  expect(screen.queryByText("Sua base começa aqui")).not.toBeInTheDocument();
});
