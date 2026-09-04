import { cleanup, render, screen } from "@testing-library/react";
import { afterEach, beforeEach, expect, test, vi } from "vitest";

import { DashboardPage } from "./DashboardPage";

const mocks = vi.hoisted(() => ({ api: vi.fn() }));
vi.mock("../api", () => ({ api: mocks.api }));
const authState = vi.hoisted(() => ({ user: { role: "admin", is_admin: true } as { role: string; is_admin?: boolean } }));
vi.mock("../auth", () => ({ useAuth: () => authState }));

const OVERVIEW = [
  { project_id: 1, project_name: "Projeto X", account_name: "Igreja Batista", current_phase_name: "Prove", canonical_stage: "prove", situation: "blocked", waiting_party: "client", blocker_note: "acesso", next_gate_name: "Scale" },
];
function stub() {
  mocks.api.mockImplementation((path: string) => {
    if (path.includes("timeline-overview")) return Promise.resolve(OVERVIEW);
    return Promise.resolve({ pipeline: [], active_projects: 2, overdue_count: 1, upcoming_tasks: [{ id: 1, title: "Reunião", due_date: "2026-08-10", project_id: 1 }] });
  });
}

beforeEach(() => { mocks.api.mockReset(); stub(); });
afterEach(cleanup);

test("esconde o pipeline comercial de quem é da Entrega", async () => {
  authState.user = { role: "delivery" };
  render(<DashboardPage />);
  expect(await screen.findByText("Projetos ativos")).toBeInTheDocument();
  expect(screen.queryByText("Pipeline estimado")).not.toBeInTheDocument();
  expect(screen.queryByText("Pipeline comercial")).not.toBeInTheDocument();
  authState.user = { role: "admin", is_admin: true };
});

test("exibe métricas e próximas entregas", async () => {
  render(<DashboardPage />);
  expect(await screen.findByText("Projetos ativos")).toBeInTheDocument();
  expect(screen.getByText("Reunião")).toBeInTheDocument();
  expect(screen.getByText("1")).toBeInTheDocument();
});

test("mostra a jornada de entrega compacta com fase e situação", async () => {
  render(<DashboardPage />);
  expect(await screen.findByText("Jornada de entrega")).toBeInTheDocument();
  expect(screen.getByText(/Igreja Batista/)).toBeInTheDocument();
  expect(screen.getByText("Bloqueada")).toBeInTheDocument();
  expect(screen.getByText(/Próx. gate: Scale/)).toBeInTheDocument();
});
