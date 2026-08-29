import { cleanup, render, screen } from "@testing-library/react";
import { afterEach, beforeEach, expect, test, vi } from "vitest";

import { ProjectDetailPage } from "./ProjectDetailPage";

const mocks = vi.hoisted(() => ({ api: vi.fn() }));
// A carga da Fase 5 (FDD 049) roda em paralelo ao detalhe do projeto e não é o assunto deste
// arquivo: listas vazias mantêm os dois painéis fora do caminho. Quem os exercita é
// `ProjectDetailProve.test.tsx`. Em `vi.hoisted` porque a fábrica do `vi.mock` roda **antes** do
// corpo do módulo.
const semFase5 = vi.hoisted(() => ({
  listKpis: () => Promise.resolve([]),
  listFeasibilityAssessments: () => Promise.resolve([]),
  listProveExperiments: () => Promise.resolve([]),
  listMeasurements: () => Promise.resolve([]),
  startProveExperiment: () => Promise.resolve({}),
  registerProveGapWaiver: () => Promise.resolve({}),
}));
vi.mock("../api", () => ({ api: mocks.api, ...semFase5 }));
vi.mock("../auth", () => ({ useAuth: () => ({ aiEnabled: false, calendarEnabled: false, user: { role: "sales" } }) }));

const PHASES = [
  { id: 11, project: 1, phase: 2, phase_name: "Prove", phase_description: "Piloto", phase_position: 1, requires_gate: true, status: "active", started_at: "2026-08-02T00:00:00Z", completed_at: null, target_date: "2026-08-30", gate_decision: "", gate_notes: "", checklist_waiver: "", deliverables: [{ id: 100, project_phase: 11, name: "Dashboard", status: "delivered", document: null, position: 0, delivered_at: "2026-08-10T00:00:00Z" }], checklist_items: [{ id: 200, project_phase: 11, text: "Baseline registrado?", position: 0, checked: false, checked_at: null }] },
];

beforeEach(() => {
  mocks.api.mockReset();
  mocks.api.mockImplementation((path: string) => {
    if (path.includes("/risk/")) return Promise.resolve({ project_id: 1, name: "Projeto X", score: 0, level: "baixo", signals: [] });
    if (path.includes("/health/")) return Promise.resolve({ project_id: 1, name: "Projeto X", score: 90, level: "saudável", signals: [] });
    if (path.startsWith("/project-phases")) return Promise.resolve(PHASES);
    if (path.startsWith("/projects/")) return Promise.resolve({ id: 1, name: "Projeto X", description: "", client: 1, owner: 1, start_date: "2026-08-01", due_date: "2026-09-01", status: "active", service: null, actual_value: "0", cost: "0", is_overdue: false });
    return Promise.resolve([]);
  });
});
afterEach(cleanup);

test("mostra a jornada em modo leitura para quem não gerencia", async () => {
  render(<ProjectDetailPage id={1} />);
  await screen.findByText("Jornada de Transformação");
  // vendas vê a previsão como texto, sem botão de avançar
  expect(screen.getByText(/Previsão:/)).toBeInTheDocument();
  expect(screen.queryByRole("button", { name: "Concluir fase e avançar" })).toBeNull();
});

test("vendas lê o checklist mas não o marca, nem alcança o painel do gate", async () => {
  // O 403 do backend é a fronteira de verdade; a tela apenas não oferece o que não é dela.
  render(<ProjectDetailPage id={1} />);
  await screen.findByText("Jornada de Transformação");

  expect(screen.getByText("Baseline registrado?")).toBeInTheDocument();
  expect(screen.getByRole("button", { name: "Marcar Baseline registrado?" })).toBeDisabled();
  expect(screen.queryByText("Decision gate")).toBeNull();
  expect(screen.queryByRole("button", { name: "GO" })).toBeNull();
});
