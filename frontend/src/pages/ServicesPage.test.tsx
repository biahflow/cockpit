import { cleanup, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, expect, test, vi } from "vitest";

import { ServicesPage } from "./ServicesPage";

const mocks = vi.hoisted(() => ({ api: vi.fn() }));
vi.mock("../api", () => ({ api: mocks.api }));

const services = [
  { id: 1, name: "Consultoria", active: true, tier: "", tier_display: "", list_price: "0.00", summary: "" },
  { id: 2, name: "Discovery Express", active: true, tier: "discovery_express", tier_display: "Discovery Express", list_price: "0.00", summary: "Diagnóstico gratuito." },
  { id: 3, name: "Implantação", active: true, tier: "implantacao", tier_display: "Implantação", list_price: "90000.00", summary: "Funcionários digitais." },
];

beforeEach(() => {
  mocks.api.mockImplementation((path: string, options?: { method?: string }) => {
    if (path === "/services/" && (options?.method ?? "GET") === "GET") return Promise.resolve(services);
    return Promise.resolve({});
  });
});
afterEach(() => { cleanup(); vi.clearAllMocks(); });

test("lista e cria serviços", async () => {
  const user = userEvent.setup();
  render(<ServicesPage />);
  expect(await screen.findByDisplayValue("Consultoria")).toBeInTheDocument();
  await user.type(screen.getByLabelText("Novo serviço"), "Automação");
  await user.click(screen.getByRole("button", { name: "Adicionar serviço" }));
  await waitFor(() => expect(mocks.api).toHaveBeenCalledWith("/services/", expect.objectContaining({ method: "POST" })));
});

test("edita, salva e arquiva um serviço avulso", async () => {
  const user = userEvent.setup();
  render(<ServicesPage />);
  await screen.findByDisplayValue("Consultoria");
  await user.click(screen.getByLabelText("Ativo"));
  await user.click(screen.getAllByRole("button", { name: "Salvar" })[2]);
  await waitFor(() => expect(mocks.api).toHaveBeenCalledWith("/services/1/", expect.objectContaining({ method: "PATCH" })));
  await user.click(screen.getByLabelText("Arquivar serviço Consultoria"));
  // O clique abre a confirmação; o DELETE só sai depois do segundo passo.
  expect(mocks.api).not.toHaveBeenCalledWith("/services/1/", expect.objectContaining({ method: "DELETE" }));
  await user.click(screen.getByRole("button", { name: "Arquivar" }));
  await waitFor(() => expect(mocks.api).toHaveBeenCalledWith("/services/1/", expect.objectContaining({ method: "DELETE" })));
});

test("separa os níveis de produto e mostra preço e escopo", async () => {
  render(<ServicesPage />);
  expect(await screen.findByText("Níveis de produto")).toBeInTheDocument();
  expect(screen.getByDisplayValue("Discovery Express")).toBeInTheDocument();
  expect(screen.getByText("Gratuito — porta de entrada da metodologia.")).toBeInTheDocument();
  expect(screen.getByDisplayValue("Funcionários digitais.")).toBeInTheDocument();
  expect(screen.getByText("Serviços avulsos")).toBeInTheDocument();
});

test("salva preço e escopo de um nível", async () => {
  const user = userEvent.setup();
  render(<ServicesPage />);
  const price = await screen.findByLabelText("Preço de Implantação");
  await user.clear(price);
  await user.type(price, "120000");
  await user.click(screen.getAllByRole("button", { name: "Salvar" })[1]);

  await waitFor(() => expect(mocks.api).toHaveBeenCalledWith("/services/3/", expect.objectContaining({
    method: "PATCH", body: expect.stringContaining('"list_price":"120000"'),
  })));
});

test("cria um serviço já no nível escolhido", async () => {
  const user = userEvent.setup();
  render(<ServicesPage />);
  await screen.findByDisplayValue("Consultoria");
  await user.type(screen.getByLabelText("Novo serviço"), "Assessment");
  await user.selectOptions(screen.getByLabelText("Nível"), "discovery_assessment");
  await user.click(screen.getByRole("button", { name: "Adicionar serviço" }));

  await waitFor(() => expect(mocks.api).toHaveBeenCalledWith("/services/", expect.objectContaining({
    method: "POST", body: expect.stringContaining('"tier":"discovery_assessment"'),
  })));
});
