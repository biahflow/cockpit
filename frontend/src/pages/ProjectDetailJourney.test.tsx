import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
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
vi.mock("../auth", () => ({ useAuth: () => ({ aiEnabled: false, calendarEnabled: false, user: { role: "delivery" } }) }));

const PHASES = [
  { id: 10, project: 1, phase: 1, phase_name: "Welcome", phase_description: "Recepção", phase_position: 0, requires_gate: false, status: "done", started_at: "2026-08-01T00:00:00Z", completed_at: "2026-08-02T00:00:00Z", target_date: null, gate_decision: "", gate_notes: "", checklist_waiver: "", deliverables: [], checklist_items: [] },
  { id: 11, project: 1, phase: 2, phase_name: "Prove", phase_description: "Piloto", phase_position: 1, requires_gate: false, status: "active", started_at: "2026-08-02T00:00:00Z", completed_at: null, target_date: null, gate_decision: "", gate_notes: "", checklist_waiver: "", deliverables: [{ id: 100, project_phase: 11, name: "Dashboard", status: "pending", document: null, position: 0, delivered_at: null }], checklist_items: [] },
  { id: 12, project: 1, phase: 3, phase_name: "Scale", phase_description: "", phase_position: 2, requires_gate: false, status: "locked", started_at: null, completed_at: null, target_date: null, gate_decision: "", gate_notes: "", checklist_waiver: "", deliverables: [], checklist_items: [] },
];
// A mesma jornada com os dois gates ligados na fase ativa (FDD 033).
const GATED = [
  { ...PHASES[0], gate_decision: "conditional_go", gate_notes: "Latência acima do alvo." },
  { ...PHASES[1], requires_gate: true, checklist_items: [{ id: 200, project_phase: 11, text: "Baseline registrado?", position: 0, checked: false, checked_at: null }] },
  PHASES[2],
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

function mockGated(overrides: (path: string) => unknown | undefined = () => undefined) {
  mocks.api.mockImplementation((path: string) => {
    const override = overrides(path);
    if (override !== undefined) return override;
    if (path.includes("/risk/")) return Promise.resolve({ project_id: 1, name: "Projeto X", score: 0, level: "baixo", signals: [] });
    if (path.includes("/health/")) return Promise.resolve({ project_id: 1, name: "Projeto X", score: 90, level: "saudável", signals: [] });
    if (path.includes("/apply-gate/") || path.includes("/advance-phase/")) return Promise.resolve(GATED);
    if (path.startsWith("/project-phases")) return Promise.resolve(GATED);
    if (path.startsWith("/projects/")) return Promise.resolve({ id: 1, name: "Projeto X", description: "", client: 1, owner: 1, start_date: "2026-08-01", due_date: "2026-09-01", status: "active", service: null, actual_value: "0", cost: "0", is_overdue: false });
    return Promise.resolve([]);
  });
}

test("marca um item do checklist e registra a justificativa da fase", async () => {
  const user = userEvent.setup();
  mockGated();
  render(<ProjectDetailPage id={1} />);
  await screen.findByText("Jornada de Transformação");

  await user.click(screen.getByRole("button", { name: "Marcar Baseline registrado?" }));
  await waitFor(() => expect(mocks.api).toHaveBeenCalledWith("/project-checklist-items/200/", expect.objectContaining({ method: "PATCH", body: "{\"checked\":true}" })));

  await user.type(screen.getByLabelText(/Justificativa para concluir/), "Cliente antecipou o go-live.");
  await user.click(screen.getByRole("button", { name: "Registrar justificativa" }));
  await waitFor(() => expect(mocks.api).toHaveBeenCalledWith("/project-phases/11/", expect.objectContaining({ body: expect.stringContaining("checklist_waiver") })));
});

test("aplica GO pelo painel do decision gate, com as notas", async () => {
  const user = userEvent.setup();
  mockGated();
  render(<ProjectDetailPage id={1} />);
  await screen.findByText("Decision gate");

  await user.type(screen.getByLabelText(/Ressalvas, motivo ou condições/), "Piloto sustentou o volume.");
  await user.click(screen.getByRole("button", { name: "GO" }));

  await waitFor(() => expect(mocks.api).toHaveBeenCalledWith("/projects/1/apply-gate/", expect.objectContaining({ method: "POST", body: expect.stringContaining("\"decision\":\"go\"") })));
});

test("REDESIGN e NO-GO pedem confirmação antes de registrar", async () => {
  // As duas saídas que **não** avançam mexem no que já estava fechado ou param a jornada: um
  // clique de descuido nelas não pode valer o mesmo que um clique em GO.
  const user = userEvent.setup();
  mockGated();
  render(<ProjectDetailPage id={1} />);
  await screen.findByText("Decision gate");

  await user.click(screen.getByRole("button", { name: "REDESIGN" }));
  expect(screen.getByText(/volta para/)).toBeInTheDocument();
  await user.click(screen.getByRole("button", { name: "Registrar REDESIGN" }));
  await waitFor(() => expect(mocks.api).toHaveBeenCalledWith("/projects/1/apply-gate/", expect.objectContaining({ body: expect.stringContaining("redesign") })));

  await user.click(screen.getByRole("button", { name: "NO-GO" }));
  expect(screen.getByText(/para nesta fase/)).toBeInTheDocument();
  await user.click(screen.getByRole("button", { name: "Registrar NO-GO" }));
  await waitFor(() => expect(mocks.api).toHaveBeenCalledWith("/projects/1/apply-gate/", expect.objectContaining({ body: expect.stringContaining("no_go") })));
});

test("o gate do PROVE oferece três saídas, e não as quatro da Feasibility", async () => {
  // ADR 0053: o vocabulário sai do `canonical_stage` da fase ativa. Sem isto, a equipe lê no
  // cronograma do kickoff "Registrar a decisão SCALE / ITERATE / STOP" e encontra outros botões.
  const user = userEvent.setup();
  const NO_PROVE = [GATED[0], { ...GATED[1], canonical_stage: "prove" }, GATED[2]];
  mocks.api.mockImplementation((path: string) => {
    if (path.includes("/risk/")) return Promise.resolve({ project_id: 1, name: "Projeto X", score: 0, level: "baixo", signals: [] });
    if (path.includes("/health/")) return Promise.resolve({ project_id: 1, name: "Projeto X", score: 90, level: "saudável", signals: [] });
    if (path.includes("/apply-gate/") || path.includes("/advance-phase/")) return Promise.resolve(NO_PROVE);
    if (path.startsWith("/project-phases")) return Promise.resolve(NO_PROVE);
    if (path.startsWith("/projects/")) return Promise.resolve({ id: 1, name: "Projeto X", description: "", client: 1, owner: 1, start_date: "2026-08-01", due_date: "2026-09-01", status: "active", service: null, actual_value: "0", cost: "0", is_overdue: false });
    return Promise.resolve([]);
  });
  render(<ProjectDetailPage id={1} />);
  await screen.findByText("Decision gate");

  expect(screen.getByRole("button", { name: "SCALE" })).toBeInTheDocument();
  expect(screen.getByRole("button", { name: "ITERATE" })).toBeInTheDocument();
  expect(screen.getByRole("button", { name: "STOP" })).toBeInTheDocument();
  expect(screen.queryByRole("button", { name: "GO" })).not.toBeInTheDocument();
  expect(screen.queryByRole("button", { name: "CONDITIONAL GO" })).not.toBeInTheDocument();
  // A copy de apoio acompanha o vocabulário, e não fala de REDESIGN numa fase que não o aceita.
  expect(screen.getByText(/ITERATE reabre a fase anterior; STOP para a jornada aqui/)).toBeInTheDocument();

  // SCALE avança como o GO: sem confirmação. ITERATE e STOP mexem no que já estava fechado.
  await user.click(screen.getByRole("button", { name: "SCALE" }));
  await waitFor(() => expect(mocks.api).toHaveBeenCalledWith("/projects/1/apply-gate/", expect.objectContaining({ body: expect.stringContaining("\"decision\":\"scale\"") })));

  await user.click(screen.getByRole("button", { name: "ITERATE" }));
  await user.click(screen.getByRole("button", { name: "Registrar ITERATE" }));
  await waitFor(() => expect(mocks.api).toHaveBeenCalledWith("/projects/1/apply-gate/", expect.objectContaining({ body: expect.stringContaining("iterate") })));
});

test("mostra o selo do gate na fase que já decidiu, e a recusa 409 do avanço", async () => {
  const user = userEvent.setup();
  mockGated(path => path.includes("/advance-phase/")
    ? Promise.reject(new Error("Faltam 1 item(ns) do checklist de qualidade desta fase."))
    : undefined);
  render(<ProjectDetailPage id={1} />);
  await screen.findByText("Jornada de Transformação");

  // O selo é identificado pelas notas do gate: o rótulo sozinho também é o texto do botão.
  expect(screen.getByTitle("Latência acima do alvo.")).toHaveTextContent("CONDITIONAL GO");

  await user.click(screen.getByRole("button", { name: "Concluir fase e avançar" }));
  expect(await screen.findByRole("alert")).toHaveTextContent("Faltam 1 item(ns)");
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
