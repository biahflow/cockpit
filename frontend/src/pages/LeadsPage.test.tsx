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

test("converte um lead em oportunidade", async () => {
  const user = userEvent.setup();
  render(<LeadsPage />);
  await screen.findByText("Fulano");
  await user.click(screen.getByRole("button", { name: /Converter em oportunidade/ }));
  await waitFor(() => expect(mocks.api).toHaveBeenCalledWith("/leads/1/convert/", expect.objectContaining({ method: "POST" })));
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
