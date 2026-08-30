import { cleanup, render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, expect, test, vi } from "vitest";

import { CasesPage } from "./CasesPage";

const mocks = vi.hoisted(() => ({ api: vi.fn(), user: { is_admin: true, role: "admin" } }));
vi.mock("../api", () => ({ api: mocks.api }));
vi.mock("../auth", () => ({ useAuth: () => ({ user: mocks.user }) }));

const metricaMedida = {
  employee_id: 1, blueprint_id: 3, name: "SDR", area: "Comercial",
  kpi_label: "Leads qualificados/mês", kpi_unit: "count", kpi_direction: "up",
  baseline: "12.00", current: "48.00", has_baseline: true, kpi_value: "", hours_saved_month: "40.0",
};
const metricaSemBase = {
  ...metricaMedida, employee_id: 2, name: "Cobrador", area: "Financeiro",
  kpi_label: "Dias de atraso", kpi_unit: "hours", kpi_direction: "down",
  baseline: null, has_baseline: false, current: "12.00",
};

function caso(overrides: Record<string, unknown> = {}) {
  return {
    id: 5, project: 2, project_name: "Implantação de agentes",
    title: "Imobiliária Aurora — Implantação de agentes", summary: "",
    vertical: 7, vertical_name: "Imobiliárias", client_name: "Imobiliária Aurora",
    metrics: [metricaMedida, metricaSemBase],
    health_snapshot: { score: 82, level: "saudável", signals: [] },
    roi_snapshot: { revenue: "180000.00", cost: "90000.00", roi: 1 },
    status: "draft", status_display: "Rascunho", published_at: null,
    account_consent: false, client_consent: false, consent_recorded_at: null, consent_recorded_by: null,
    anonymized: false, created_at: "2026-08-01T12:00:00Z", updated_at: "2026-08-01T12:00:00Z",
    ...overrides,
  };
}

function stub(cases: unknown[]) {
  return (path: string, options?: { method?: string }) => {
    if ((options?.method ?? "GET") === "GET") {
      if (path.startsWith("/cases/")) return Promise.resolve(cases);
      if (path === "/verticals/") return Promise.resolve([{ id: 7, name: "Imobiliárias", slug: "imobiliarias", position: 0, active: true }]);
    }
    return Promise.resolve({});
  };
}

beforeEach(() => { mocks.user = { is_admin: true, role: "admin" }; mocks.api.mockImplementation(stub([caso()])); });
afterEach(() => { cleanup(); vi.clearAllMocks(); });

test("mostra o antes e o depois congelados, com a unidade certa", async () => {
  render(<CasesPage />);

  expect(await screen.findByText("Imobiliária Aurora — Implantação de agentes")).toBeInTheDocument();
  expect(screen.getByText("Saúde 82/100")).toBeInTheDocument();
  expect(screen.getByText("12")).toBeInTheDocument();
  expect(screen.getByText("48")).toBeInTheDocument();
  expect(screen.getByText("12h")).toBeInTheDocument();
});

test("métrica sem base registrada diz a lacuna em vez de mostrar zero", async () => {
  render(<CasesPage />);

  expect(await screen.findByText("sem base registrada")).toBeInTheDocument();
  expect(screen.queryByText("0")).not.toBeInTheDocument();
});

test("publicar fica bloqueado, com o motivo à vista, enquanto não houver consentimento", async () => {
  render(<CasesPage />);
  await screen.findByText("Imobiliária Aurora — Implantação de agentes");

  expect(screen.getByRole("button", { name: "Publicar" })).toBeDisabled();
  expect(screen.getByText(/anonimizar não substitui/i)).toBeInTheDocument();
});

test("registra o consentimento pelo diálogo de confirmação", async () => {
  const user = userEvent.setup();
  render(<CasesPage />);
  await screen.findByText("Imobiliária Aurora — Implantação de agentes");

  await user.click(screen.getByRole("button", { name: /registrar consentimento/i }));
  // O botão do card e o de confirmar têm o mesmo rótulo de propósito — o diálogo repete a ação
  // que o usuário pediu. Aqui a busca é dentro do diálogo, que é onde o clique confirma.
  const dialogo = screen.getByRole("dialog");
  await user.click(within(dialogo).getByRole("button", { name: "Registrar consentimento" }));

  await waitFor(() => expect(mocks.api).toHaveBeenCalledWith("/cases/5/record-consent/", { method: "POST" }));
});

test("com consentimento registrado, publicar fica disponível", async () => {
  mocks.api.mockImplementation(stub([caso({ account_consent: true, client_consent: true, status: "review", status_display: "Em revisão" })]));
  const user = userEvent.setup();
  render(<CasesPage />);
  await screen.findByText("Consentimento registrado");

  await user.click(screen.getByRole("button", { name: "Publicar" }));

  await waitFor(() => expect(mocks.api).toHaveBeenCalledWith("/cases/5/", expect.objectContaining({ method: "PATCH", body: expect.stringContaining("published") })));
});

test("case anonimizado não mostra o nome do cliente", async () => {
  mocks.api.mockImplementation(stub([caso({
    anonymized: true, client_name: "",
    title: "Uma empresa do setor Imobiliárias — Implantação de agentes",
  })]));
  render(<CasesPage />);

  expect(await screen.findByText("Anonimizado")).toBeInTheDocument();
  expect(screen.queryByText(/Imobiliária Aurora/)).not.toBeInTheDocument();
});

test("quem não é admin lê o case e não vê os controles de publicação", async () => {
  mocks.user = { is_admin: false, role: "sales" };
  mocks.api.mockImplementation(stub([caso({ summary: "Triplicou a qualificação de leads." })]));
  render(<CasesPage />);

  expect(await screen.findByText("Triplicou a qualificação de leads.")).toBeInTheDocument();
  expect(screen.queryByRole("button", { name: "Publicar" })).not.toBeInTheDocument();
  expect(screen.queryByRole("button", { name: /registrar consentimento/i })).not.toBeInTheDocument();
});

test("o filtro por vertical vai ao servidor e o de área filtra na tela", async () => {
  const user = userEvent.setup();
  render(<CasesPage />);
  await screen.findByText("Imobiliária Aurora — Implantação de agentes");

  await user.selectOptions(screen.getByLabelText("Vertical"), "7");
  await waitFor(() => expect(mocks.api).toHaveBeenCalledWith("/cases/?vertical=7"));

  await user.selectOptions(screen.getByLabelText("Área"), "RH");
  expect(screen.queryByText("Imobiliária Aurora — Implantação de agentes")).not.toBeInTheDocument();
});

test("estado vazio explica de onde vem um case", async () => {
  mocks.api.mockImplementation(stub([]));
  render(<CasesPage />);

  expect(await screen.findByText(/nascem sozinhos quando um projeto é marcado como concluído/i)).toBeInTheDocument();
});
