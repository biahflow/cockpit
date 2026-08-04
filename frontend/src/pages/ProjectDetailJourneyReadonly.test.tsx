import { cleanup, render, screen } from "@testing-library/react";
import { afterEach, beforeEach, expect, test, vi } from "vitest";

import { ProjectDetailPage } from "./ProjectDetailPage";

const mocks = vi.hoisted(() => ({ api: vi.fn() }));
vi.mock("../api", () => ({ api: mocks.api }));
vi.mock("../auth", () => ({ useAuth: () => ({ aiEnabled: false, calendarEnabled: false, user: { role: "sales" } }) }));

const PHASES = [
  { id: 11, project: 1, phase: 2, phase_name: "Prove", phase_description: "Piloto", phase_position: 1, status: "active", started_at: "2026-08-02T00:00:00Z", completed_at: null, target_date: "2026-08-30", deliverables: [{ id: 100, project_phase: 11, name: "Dashboard", status: "delivered", document: null, position: 0, delivered_at: "2026-08-10T00:00:00Z" }] },
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
