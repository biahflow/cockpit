import { cleanup, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, expect, test, vi } from "vitest";

import { ProjectDetailPage } from "./ProjectDetailPage";

const mocks = vi.hoisted(() => ({ api: vi.fn() }));
vi.mock("../api", () => ({ api: mocks.api }));
vi.mock("../auth", () => ({ useAuth: () => ({ aiEnabled: false, calendarEnabled: false, user: { role: "delivery" } }) }));

const CURRENT = {
  id: 11, project: 1, phase: 2, phase_name: "Prove", phase_description: "Piloto", phase_position: 1,
  requires_gate: false, canonical_stage: "prove", status: "active", situation: "blocked",
  started_at: "2026-08-02T00:00:00Z", completed_at: null, target_date: null, gate_outcome: "",
  gate_notes: "", checklist_waiver: "", waiting_party: "client", blocker_note: "aguardando acesso ao ERP",
  deliverables: [], checklist_items: [],
};
const TIMELINE = {
  project: 1,
  phases: [CURRENT],
  current_phase: CURRENT,
  next_phase: { phase_name: "Scale", canonical_stage: "scale" },
  next_gate: { phase_name: "Scale", canonical_stage: "scale" },
  blockers: [{ phase_name: "Prove", waiting_party: "client", blocker_note: "aguardando acesso ao ERP" }],
  events: [
    { id: 2, project: 1, project_phase: 11, phase_name: "Prove", kind: "waiting_set", from_status: "", to_status: "", gate_outcome: "", waiting_party: "client", note: "aguardando acesso ao ERP", actor: 3, actor_name: "Ana Lima", source: "user", created_at: "2026-08-03T12:00:00Z" },
    { id: 1, project: 1, project_phase: 10, phase_name: "Welcome", kind: "started", from_status: "", to_status: "active", gate_outcome: "", waiting_party: "", note: "", actor: null, actor_name: null, source: "system", created_at: "2026-08-01T09:00:00Z" },
  ],
};

beforeEach(() => {
  mocks.api.mockReset();
  mocks.api.mockImplementation((path: string) => {
    if (path.includes("/timeline/")) return Promise.resolve(TIMELINE);
    if (path.includes("/set-waiting/")) return Promise.resolve([CURRENT]);
    if (path.includes("/risk/")) return Promise.resolve({ project_id: 1, name: "Projeto X", score: 0, level: "baixo", signals: [] });
    if (path.includes("/health/")) return Promise.resolve({ project_id: 1, name: "Projeto X", score: 90, level: "saudável", signals: [] });
    if (path.startsWith("/project-phases")) return Promise.resolve([CURRENT]);
    if (path.startsWith("/projects/")) return Promise.resolve({ id: 1, name: "Projeto X", description: "", client: 1, owner: 1, start_date: "2026-08-01", due_date: "2026-09-01", status: "active", service: null, actual_value: "0", cost: "0", is_overdue: false });
    return Promise.resolve([]);
  });
});
afterEach(cleanup);

test("mostra a linha do tempo com situação, próximo gate e histórico", async () => {
  render(<ProjectDetailPage id={1} />);
  expect(await screen.findByText("Linha do tempo da entrega")).toBeInTheDocument();
  // situação semântica derivada (selo)
  expect(screen.getByText("Bloqueada")).toBeInTheDocument();
  // quem está aguardando, sem abrir a nota crua
  expect(screen.getByText("Aguardando Cliente")).toBeInTheDocument();
  expect(screen.getByText("aguardando acesso ao ERP")).toBeInTheDocument();
  // histórico append-only, com proveniência (autor vs sistema)
  expect(screen.getByText(/Aguardando definido/)).toBeInTheDocument();
  expect(screen.getByText(/Fase iniciada/)).toBeInTheDocument();
});

test("resolve o bloqueio pela action set-waiting", async () => {
  const user = userEvent.setup();
  render(<ProjectDetailPage id={1} />);
  await screen.findByText("Linha do tempo da entrega");

  await user.click(screen.getByRole("button", { name: "Resolver bloqueio" }));
  await waitFor(() => expect(mocks.api).toHaveBeenCalledWith(
    "/projects/1/set-waiting/",
    expect.objectContaining({ method: "POST" }),
  ));
});
