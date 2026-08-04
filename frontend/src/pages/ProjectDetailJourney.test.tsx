import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, expect, test, vi } from "vitest";

import { ProjectDetailPage } from "./ProjectDetailPage";

const mocks = vi.hoisted(() => ({ api: vi.fn() }));
vi.mock("../api", () => ({ api: mocks.api }));
vi.mock("../auth", () => ({ useAuth: () => ({ aiEnabled: false, calendarEnabled: false, user: { role: "delivery" } }) }));

const PHASES = [
  { id: 10, project: 1, phase: 1, phase_name: "Welcome", phase_description: "Recepção", phase_position: 0, status: "done", started_at: "2026-08-01T00:00:00Z", completed_at: "2026-08-02T00:00:00Z", target_date: null, deliverables: [] },
  { id: 11, project: 1, phase: 2, phase_name: "Prove", phase_description: "Piloto", phase_position: 1, status: "active", started_at: "2026-08-02T00:00:00Z", completed_at: null, target_date: null, deliverables: [{ id: 100, project_phase: 11, name: "Dashboard", status: "pending", document: null, position: 0, delivered_at: null }] },
  { id: 12, project: 1, phase: 3, phase_name: "Scale", phase_description: "", phase_position: 2, status: "locked", started_at: null, completed_at: null, target_date: null, deliverables: [] },
];

beforeEach(() => {
  mocks.api.mockReset();
  mocks.api.mockImplementation((path: string) => {
    if (path.includes("/risk/")) return Promise.resolve({ project_id: 1, name: "Projeto X", score: 0, level: "baixo", signals: [] });
    if (path.includes("/health/")) return Promise.resolve({ project_id: 1, name: "Projeto X", score: 90, level: "saudável", signals: [] });
    if (path.includes("/advance-phase/")) return Promise.resolve(PHASES);
    if (path.startsWith("/project-phases")) return Promise.resolve(PHASES);
    if (path.startsWith("/projects/")) return Promise.resolve({ id: 1, name: "Projeto X", description: "", client: 1, owner: 1, start_date: "2026-08-01", due_date: "2026-09-01", status: "active", service: null, actual_value: "0", cost: "0", is_overdue: false });
    return Promise.resolve([]);
  });
});
afterEach(cleanup);

test("mostra a jornada com fases e entregáveis", async () => {
  render(<ProjectDetailPage id={1} />);
  expect(await screen.findByText("Jornada de Transformação")).toBeInTheDocument();
  expect(screen.getByText("Welcome")).toBeInTheDocument();
  expect(screen.getAllByText("Scale").length).toBeGreaterThan(0); // pílula + "Próxima"
  expect(screen.getByText("Você está aqui")).toBeInTheDocument();
  expect(screen.getByText("Dashboard")).toBeInTheDocument();
});

test("avança de fase e marca um entregável", async () => {
  const user = userEvent.setup();
  render(<ProjectDetailPage id={1} />);
  await screen.findByText("Jornada de Transformação");

  await user.click(screen.getByRole("button", { name: "Marcar Dashboard como entregue" }));
  await waitFor(() => expect(mocks.api).toHaveBeenCalledWith("/project-deliverables/100/", expect.objectContaining({ method: "PATCH" })));

  await user.click(screen.getByRole("button", { name: "Concluir fase e avançar" }));
  await waitFor(() => expect(mocks.api).toHaveBeenCalledWith("/projects/1/advance-phase/", expect.objectContaining({ method: "POST" })));
});

test("define a previsão da fase ativa", async () => {
  render(<ProjectDetailPage id={1} />);
  await screen.findByText("Jornada de Transformação");
  fireEvent.change(screen.getByLabelText("Previsão desta fase"), { target: { value: "2026-08-30" } });
  await waitFor(() => expect(mocks.api).toHaveBeenCalledWith("/project-phases/11/", expect.objectContaining({ method: "PATCH" })));
});

test("mostra estado de jornada concluída quando não há fase ativa", async () => {
  mocks.api.mockImplementation((path: string) => {
    if (path.includes("/risk/")) return Promise.resolve({ project_id: 1, name: "Projeto X", score: 0, level: "baixo", signals: [] });
    if (path.includes("/health/")) return Promise.resolve({ project_id: 1, name: "Projeto X", score: 90, level: "saudável", signals: [] });
    if (path.startsWith("/project-phases")) return Promise.resolve(PHASES.map(phase => ({ ...phase, status: "done" })));
    if (path.startsWith("/projects/")) return Promise.resolve({ id: 1, name: "Projeto X", description: "", client: 1, owner: 1, start_date: "2026-08-01", due_date: "2026-09-01", status: "completed", service: null, actual_value: "0", cost: "0", is_overdue: false });
    return Promise.resolve([]);
  });
  render(<ProjectDetailPage id={1} />);
  expect(await screen.findByText(/Jornada de transformação concluída/)).toBeInTheDocument();
});
