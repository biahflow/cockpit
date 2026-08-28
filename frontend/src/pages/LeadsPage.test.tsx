import { cleanup, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, expect, test, vi } from "vitest";

import { LeadsPage } from "./LeadsPage";

const mocks = vi.hoisted(() => ({ api: vi.fn() }));
vi.mock("../api", () => ({ api: mocks.api }));

const lead = { id: 1, name: "Fulano", email: "f@x.com", company: "ACME", phone: "", message: "quero ajuda", source: "site", status: "new", client: null, opportunity: null, created_at: "2026-08-01" };

beforeEach(() => {
  mocks.api.mockImplementation((path: string, options?: { method?: string }) => {
    if (path === "/leads/" && (options?.method ?? "GET") === "GET") return Promise.resolve([lead]);
    return Promise.resolve({});
  });
});
afterEach(() => { cleanup(); vi.clearAllMocks(); });

test("lista leads recebidos", async () => {
  render(<LeadsPage />);
  expect(await screen.findByText("Fulano")).toBeInTheDocument();
  expect(screen.getByText("ACME")).toBeInTheDocument();
  expect(screen.getByText("quero ajuda")).toBeInTheDocument();
});

test("mostra o setor que o enriquecimento trouxe, e cala sem ele", async () => {
  // O lead do fixture não tem `enrichment`, e é o caso que mais importa: o campo é opcional no
  // contrato e a tela não pode quebrar com ele ausente — sem CNPJ, com a flag desligada ou com o
  // fornecedor fora do ar, é exatamente esse o corpo que chega (FDD 030).
  mocks.api.mockImplementation((path: string) => {
    if (path === "/leads/") return Promise.resolve([
      lead,
      { ...lead, id: 3, name: "Beltrana", cnpj: "11222333000181", enrichment: { cnae_label: "Desenvolvimento de software", size: "DEMAIS", cnpj: "11222333000181" } },
    ]);
    return Promise.resolve({});
  });
  render(<LeadsPage />);
  expect(await screen.findByText("Beltrana")).toBeInTheDocument();
  expect(screen.getByText(/Desenvolvimento de software · DEMAIS/)).toBeInTheDocument();
  expect(screen.getByText("Fulano")).toBeInTheDocument();
});

test("registra a qualificação do lead e diz o resultado", async () => {
  // A ação deixou de prometer oportunidade (ADR 0049): ela registra a avaliação, e a venda é um
  // segundo ato. A resposta mudou de forma junto — `{lead, qualification}` —, e é dela que sai o
  // texto de feedback; consumi-la como antes deixaria a tela muda no sucesso.
  const user = userEvent.setup();
  mocks.api.mockImplementation((path: string, options?: { method?: string }) => {
    if (path === "/leads/" && (options?.method ?? "GET") === "GET") return Promise.resolve([lead]);
    if (path === "/leads/1/convert/") return Promise.resolve({ lead: { ...lead, status: "qualified" }, qualification: { id: 7, outcome: "qualified" } });
    return Promise.resolve({});
  });
  render(<LeadsPage />);
  await screen.findByText("Fulano");
  await user.click(screen.getByRole("button", { name: /Registrar qualificação/ }));
  await waitFor(() => expect(mocks.api).toHaveBeenCalledWith("/leads/1/convert/", expect.objectContaining({ method: "POST" })));
  expect(await screen.findByRole("status")).toHaveTextContent(/Qualificação registrada: Qualificado/);
});

test("lead já qualificado mostra o resultado e não oferece qualificar de novo", async () => {
  mocks.api.mockImplementation((path: string) => {
    if (path === "/leads/") return Promise.resolve([{ ...lead, id: 4, name: "Já avaliado", status: "qualified", qualification: 9, qualification_outcome: "qualified" }]);
    return Promise.resolve({});
  });
  render(<LeadsPage />);
  await screen.findByText("Já avaliado");
  expect(screen.getAllByText("Qualificado").length).toBeGreaterThan(0);
  expect(screen.queryByRole("button", { name: /Registrar qualificação/ })).not.toBeInTheDocument();
});


test("lista e restaura leads arquivados", async () => {
  // O diálogo de arquivar promete restauração; sem esta aba a promessa era falsa (FDD 025).
  const user = userEvent.setup();
  mocks.api.mockImplementation((path: string) => {
    if (path === "/leads/?archived=1") return Promise.resolve([{ ...lead, id: 2, name: "Arquivado" }]);
    if (path === "/leads/") return Promise.resolve([lead]);
    return Promise.resolve({});
  });
  render(<LeadsPage />);
  await screen.findByText("Fulano");

  await user.click(screen.getByRole("button", { name: "Arquivados" }));
  expect(await screen.findByText("Arquivado")).toBeInTheDocument();

  await user.click(screen.getByRole("button", { name: /Restaurar/ }));
  await waitFor(() => expect(mocks.api).toHaveBeenCalledWith("/leads/2/unarchive/", expect.objectContaining({ method: "POST" })));
});
