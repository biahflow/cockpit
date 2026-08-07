import { cleanup, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, expect, test, vi } from "vitest";

import { BibliotecaPage } from "./BibliotecaPage";

const mocks = vi.hoisted(() => ({ api: vi.fn() }));
vi.mock("../api", () => ({ api: mocks.api }));

const vertical = { id: 7, name: "Igrejas", slug: "igrejas", position: 0, active: true };
const blueprint = {
  id: 3, name: "SDR", area: "comercial", area_display: "Comercial",
  description: "Qualifica lead fora do horário.", kpi_label: "Leads qualificados/mês",
  default_hours_saved_month: "40.0", default_roi_month: "8000.00", service: null,
  service_name: "", active: true, resolved: null, has_variant: true,
  variants: [{ id: 11, blueprint: 3, vertical: 7, vertical_name: "Igrejas", description: "Qualifica visitante de culto.", kpi_label: "", default_hours_saved_month: null, default_roi_month: null }],
};

function stub(overrides: Record<string, unknown> = {}) {
  return (path: string, options?: { method?: string }) => {
    if ((options?.method ?? "GET") === "GET") {
      if (path === "/verticals/") return Promise.resolve(overrides.verticals ?? [vertical]);
      if (path === "/digital-employee-blueprints/") return Promise.resolve(overrides.blueprints ?? [blueprint]);
      if (path === "/services/") return Promise.resolve([{ id: 1, name: "Discovery Express", active: true, tier: "discovery_express", tier_display: "Discovery Express", list_price: "0.00", summary: "" }]);
    }
    return Promise.resolve({});
  };
}

beforeEach(() => { mocks.api.mockImplementation(stub()); });
afterEach(() => { cleanup(); vi.clearAllMocks(); });

test("lista verticais, blocos e as variantes de cada bloco", async () => {
  render(<BibliotecaPage />);

  expect(await screen.findByDisplayValue("Igrejas")).toBeInTheDocument();
  expect(screen.getByDisplayValue("SDR")).toBeInTheDocument();
  expect(screen.getByText("Qualifica visitante de culto.")).toBeInTheDocument();
});

test("cria uma vertical e um bloco do catálogo", async () => {
  const user = userEvent.setup();
  render(<BibliotecaPage />);
  await screen.findByDisplayValue("Igrejas");

  await user.type(screen.getByLabelText("Nova vertical"), "Saúde");
  await user.type(screen.getByLabelText("Identificador"), "saude");
  await user.click(screen.getByRole("button", { name: "Adicionar vertical" }));
  await waitFor(() => expect(mocks.api).toHaveBeenCalledWith("/verticals/", expect.objectContaining({ method: "POST", body: expect.stringContaining("saude") })));

  await user.type(screen.getByLabelText("Novo bloco"), "Agente Financeiro");
  await user.click(screen.getByRole("button", { name: "Adicionar bloco" }));
  await waitFor(() => expect(mocks.api).toHaveBeenCalledWith("/digital-employee-blueprints/", expect.objectContaining({ method: "POST", body: expect.stringContaining("Agente Financeiro") })));
});

test("adiciona uma variante mandando null onde o campo ficou em branco", async () => {
  // Em branco na variante **herda** o valor do bloco. Mandar "" ou 0 gravaria uma sobrescrita
  // silenciosa de zero hora e zero ROI — o oposto de herdar (FDD 026).
  const user = userEvent.setup();
  render(<BibliotecaPage />);
  await screen.findByDisplayValue("SDR");

  await user.selectOptions(screen.getByLabelText("Vertical da nova variante de SDR"), "7");
  await user.type(screen.getByLabelText("Descrição da nova variante de SDR"), "Visita pastoral.");
  await user.click(screen.getByLabelText("Adicionar variante a SDR"));

  await waitFor(() => expect(mocks.api).toHaveBeenCalledWith("/blueprint-variants/", expect.objectContaining({
    method: "POST",
    body: expect.stringContaining("\"default_hours_saved_month\":null"),
  })));
});

test("remove uma variante", async () => {
  const user = userEvent.setup();
  render(<BibliotecaPage />);
  await screen.findByDisplayValue("SDR");

  await user.click(screen.getByLabelText("Excluir variante Igrejas de SDR"));

  await waitFor(() => expect(mocks.api).toHaveBeenCalledWith("/blueprint-variants/11/", expect.objectContaining({ method: "DELETE" })));
});

test("aposenta o bloco em vez de excluí-lo, e o aviso explica o que não muda", async () => {
  const user = userEvent.setup();
  render(<BibliotecaPage />);
  await screen.findByDisplayValue("SDR");

  await user.click(screen.getByLabelText("Disponível para instanciar"));
  expect(screen.getByText(/já instanciados continuam iguais/)).toBeInTheDocument();
  await user.click(screen.getAllByRole("button", { name: "Salvar" })[1]);

  await waitFor(() => expect(mocks.api).toHaveBeenCalledWith("/digital-employee-blueprints/3/", expect.objectContaining({ body: expect.stringContaining("\"active\":false") })));
});

test("mostra a recusa da exclusão em vez de engolir o erro", async () => {
  // O 409 do backend traz a contagem e o caminho de saída; a tela exibe o texto tal como veio.
  const user = userEvent.setup();
  const base = stub();
  mocks.api.mockImplementation((path: string, options?: { method?: string }) => {
    if (path === "/digital-employee-blueprints/3/" && options?.method === "DELETE") {
      return Promise.reject(new Error("Este blueprint já foi instanciado em 4 Funcionário(s) Digital(is). Desative o blueprint."));
    }
    return base(path, options);
  });
  render(<BibliotecaPage />);
  await screen.findByDisplayValue("SDR");

  await user.click(screen.getByLabelText("Excluir blueprint SDR"));
  await user.click(screen.getByRole("button", { name: "Excluir" }));

  expect(await screen.findByRole("alert")).toHaveTextContent("Desative o blueprint");
});

test("o catálogo vazio diz o que fazer em vez de ficar mudo", async () => {
  mocks.api.mockImplementation(stub({ verticals: [], blueprints: [] }));
  render(<BibliotecaPage />);

  expect(await screen.findByText(/Nenhum bloco no catálogo/)).toBeInTheDocument();
  expect(screen.getByText(/Nenhuma vertical ainda/)).toBeInTheDocument();
});
