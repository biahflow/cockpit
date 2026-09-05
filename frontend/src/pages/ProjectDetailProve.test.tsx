import { cleanup, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, expect, test, vi } from "vitest";

import { ProjectDetailPage } from "./ProjectDetailPage";

/**
 * Os dois painéis da Fase 5 em `ProjectDetailPage` — DAP `docs/design/dap-prove-e-valor-r1/`,
 * revisão 1, decisões **A1 · B1 · E1** (a **C1** é cobrada em `ProjectDetailPage.test.tsx`, junto
 * do formulário que ela esvazia).
 *
 * O que estes testes protegem é **a lacuna**: `—` e nunca `0`, na linha do KPI e em toda linha do
 * laudo. Zero afirma que se mediu e deu zero; o traço diz que ninguém mediu, e é a distinção que o
 * pacote inteiro existe para preservar.
 */

const mocks = vi.hoisted(() => ({
  api: vi.fn(),
  listUsers: vi.fn(),
  listKpis: vi.fn(),
  listFeasibilityAssessments: vi.fn(),
  listProveExperiments: vi.fn(),
  listMeasurements: vi.fn(),
  startProveExperiment: vi.fn(),
  registerProveGapWaiver: vi.fn(),
  auth: { aiEnabled: false, calendarEnabled: false, user: { role: "delivery", is_admin: false } } as { aiEnabled: boolean; calendarEnabled: boolean; user: { role: string; is_admin: boolean } },
}));
vi.mock("../api", () => ({
  api: mocks.api,
  listUsers: mocks.listUsers,
  listKpis: mocks.listKpis,
  listFeasibilityAssessments: mocks.listFeasibilityAssessments,
  listProveExperiments: mocks.listProveExperiments,
  listMeasurements: mocks.listMeasurements,
  startProveExperiment: mocks.startProveExperiment,
  registerProveGapWaiver: mocks.registerProveGapWaiver,
  // A porta da Discovery Session (FDD 055) é carga paralela e não é o assunto deste arquivo.
  listDiscoveries: () => Promise.resolve([]),
  listDiscoverySessions: () => Promise.resolve([]),
}));
vi.mock("../auth", () => ({ useAuth: () => mocks.auth }));

/** Uma jornada com as duas fases canônicas — é ela que faz os painéis existirem (decisão A1). */
const FASES_COM_GATE = [
  { id: 10, project: 1, phase: 1, phase_name: "Viabilidade técnica", phase_description: "", phase_position: 0, requires_gate: true, canonical_stage: "feasibility", status: "done", situation: "completed", started_at: null, completed_at: null, target_date: null, gate_decision: "", gate_notes: "", checklist_waiver: "", waiting_party: "", blocker_note: "", deliverables: [], checklist_items: [] },
  { id: 11, project: 1, phase: 2, phase_name: "Produção controlada", phase_description: "", phase_position: 1, requires_gate: true, canonical_stage: "prove", status: "active", situation: "active", started_at: null, completed_at: null, target_date: null, gate_decision: "", gate_notes: "", checklist_waiver: "", waiting_party: "", blocker_note: "", deliverables: [], checklist_items: [] },
];
/** A mesma jornada sem nenhuma das duas: um Discovery Sprint não mostra painel de PROVE. */
const FASES_DE_DISCOVERY = [{ ...FASES_COM_GATE[0], canonical_stage: "discover", phase_name: "Discovery" }];

const hipotese = {
  id: 5, improvement_opportunity: 2,
  statement: "Um agente de IA classifica e roteia 80% dos tickets do N1",
  intervention: "", assumptions: "", expected_effect: "", status: "chosen", status_display: "Escolhida",
  created_at: "2026-06-01T10:00:00Z", updated_at: "2026-06-01T10:00:00Z",
};

const laudo = (overrides: Record<string, unknown> = {}) => ({
  id: 7, solution_hypothesis: 5, project: 1,
  technical_verdict: "favorable", technical_verdict_display: "Favorável",
  technical_note: "A integração com o CRM sustenta o volume de pico.",
  operational_verdict: "caveat", operational_verdict_display: "Com ressalva",
  operational_note: "O N1 precisa de fallback humano para tickets ambíguos.",
  economic_verdict: "favorable", economic_verdict_display: "Favorável",
  economic_note: "Custo de inferência é 6% do custo humano equivalente.",
  sample: "312 tickets analisados em 15 dias corridos.",
  error_classes: "Classificação incorreta em tickets ambíguos (7%).",
  evidence: [1, 2, 3], gate_decision: "conditional_go", gate_decision_display: "CONDITIONAL GO",
  created_at: "2026-06-15T10:00:00Z", updated_at: "2026-06-15T10:00:00Z", ...overrides,
});

const experimento = (overrides: Record<string, unknown> = {}) => ({
  id: 9, solution_hypothesis: 5, project: 1,
  controlled_scope: "Rotear tickets do Suporte N1 no expediente comercial.",
  started_at: "2026-07-03", ended_at: "2026-07-31",
  success_criteria: "Reduzir o tempo médio de primeira resposta em ao menos 50%.",
  status: "running", status_display: "Em execução",
  gate_decision: "", gate_decision_display: "",
  gap_waiver: "", gap_waiver_by: null, gap_waiver_at: null,
  missing_to_start: [], created_at: "2026-07-01T10:00:00Z", updated_at: "2026-07-01T10:00:00Z",
  ...overrides,
});

const kpi = (overrides: Record<string, unknown> = {}) => ({
  id: 21, project: 1, prove_experiment: 9, name: "Tempo de resposta",
  definition: "", formula: "", unit: "hours", unit_display: "Horas",
  direction: "down", direction_display: "Menor é melhor",
  data_source: "", cadence: "", owner: null, target: null,
  created_at: "2026-07-01T10:00:00Z", updated_at: "2026-07-01T10:00:00Z", ...overrides,
});

const medicao = (overrides: Record<string, unknown> = {}) => ({
  id: 31, kpi: 21, kind: "outcome", kind_display: "Outcome", value: "65.00",
  period_start: "2026-07-01", period_end: "2026-07-31", measured_at: "2026-07-24T10:00:00Z",
  source_evidence: [], confidence: null,
  created_at: "2026-07-24T10:00:00Z", updated_at: "2026-07-24T10:00:00Z", ...overrides,
});

let fases: unknown[] = FASES_COM_GATE;
let laudos: unknown[] = [];
let experimentos: unknown[] = [];
let indicadores: unknown[] = [];
let leituras: Record<number, unknown[]> = {};

function stub() {
  mocks.api.mockImplementation((path: string) => {
    if (path.includes("/risk/")) return Promise.resolve({ project_id: 1, name: "Projeto X", score: 0, level: "baixo", signals: [] });
    if (path.includes("/health/")) return Promise.resolve({ project_id: 1, name: "Projeto X", score: 90, level: "saudável", signals: [] });
    if (path.startsWith("/project-phases")) return Promise.resolve(fases);
    if (path.startsWith("/project-members")) return Promise.resolve([{ id: 1, project: 1, user: 44, user_name: "Marina Kobayashi", user_username: "marina", user_role: "delivery" }]);
    if (path.startsWith("/solution-hypotheses/")) return Promise.resolve(hipotese);
    if (path.startsWith("/projects/")) return Promise.resolve({ id: 1, name: "Projeto X", description: "", client: 1, owner: 1, start_date: "2026-06-01", due_date: "2026-09-01", status: "active", service: null, actual_value: "0", cost: "0", is_overdue: false });
    return Promise.resolve([]);
  });
  mocks.listUsers.mockResolvedValue([]);
  mocks.listKpis.mockImplementation(() => Promise.resolve(indicadores));
  mocks.listFeasibilityAssessments.mockImplementation(() => Promise.resolve(laudos));
  mocks.listProveExperiments.mockImplementation(() => Promise.resolve(experimentos));
  mocks.listMeasurements.mockImplementation((id: number) => Promise.resolve(leituras[id] ?? []));
  mocks.startProveExperiment.mockResolvedValue(experimento());
  mocks.registerProveGapWaiver.mockResolvedValue(experimento());
}

/** A linha de lista que contém aquele texto — a `.row-meta` e o `<details>` são irmãos dela. */
function linhaDe(texto: string | RegExp): HTMLElement {
  const linha = screen.getAllByText(texto).map(no => no.closest(".row")).find(Boolean);
  expect(linha).toBeTruthy();
  return linha as HTMLElement;
}

/** O par `baseline → outcome · variação` daquela linha, **sem** o histórico, que repete os números. */
function parDe(texto: string): HTMLElement {
  return linhaDe(texto).querySelector(".row-meta") as HTMLElement;
}

/** A pastilha `Pronto`/`Falta` do requisito — a leitura que a decisão E1 põe antes do botão. */
function pastilhaDe(requisito: string): string {
  const item = screen.getAllByRole("listitem").find(li => li.textContent?.includes(requisito));
  expect(item).toBeTruthy();
  return item!.querySelector(".state")!.textContent ?? "";
}

beforeEach(() => {
  for (const mock of Object.values(mocks)) if (typeof mock === "function") mock.mockReset();
  mocks.auth = { aiEnabled: false, calendarEnabled: false, user: { role: "delivery", is_admin: false } };
  fases = FASES_COM_GATE;
  laudos = []; experimentos = []; indicadores = []; leituras = {};
  stub();
});
afterEach(cleanup);

test("os painéis só existem onde a fase canônica existe", async () => {
  // Decisão **A1**: um projeto de Discovery Sprint não mostra painel de PROVE, e a página só
  // cresce onde a fase existe. A condição também poupa as requisições.
  fases = FASES_DE_DISCOVERY;
  render(<ProjectDetailPage id={1} />);
  await screen.findByText("Jornada de Transformação");

  expect(screen.queryByRole("heading", { name: "PROVE" })).toBeNull();
  expect(screen.queryByRole("heading", { name: "Technical Feasibility" })).toBeNull();
  await waitFor(() => expect(mocks.listKpis).toHaveBeenCalled());
  expect(mocks.listProveExperiments).not.toHaveBeenCalled();
  expect(mocks.listFeasibilityAssessments).not.toHaveBeenCalled();
});

test("cada painel vazio diz o que aquela etapa responde", async () => {
  render(<ProjectDetailPage id={1} />);
  await screen.findByRole("heading", { name: "Technical Feasibility" });

  expect(await screen.findByText(/Nenhum laudo/)).toHaveTextContent(/se a tecnologia consegue fazer a tarefa/);
  expect(screen.getByText(/Nenhum experimento/)).toHaveTextContent(/se funcionou em produção controlada/);
});

test("o laudo mostra os três eixos, e a decisão fica ao lado do resultado", async () => {
  laudos = [laudo()];
  render(<ProjectDetailPage id={1} />);
  await screen.findByText("Hipótese de solução avaliada:");

  expect(screen.getByText(/classifica e roteia 80% dos tickets/)).toBeInTheDocument();
  expect(within(linhaDe("Eixo técnico")).getByText("Favorável")).toBeInTheDocument();
  // "Ressalva" e não "Com ressalva": é o rótulo do board, e a pílula divide a linha com a nota.
  expect(within(linhaDe("Eixo operacional")).getByText("Ressalva")).toBeInTheDocument();
  expect(screen.getByText("3 Evidence vinculadas")).toBeInTheDocument();
  // O rótulo sai de `journey.ts`, o único mapa — e a decisão é **decisão**, nunca o resultado.
  expect(screen.getByText("CONDITIONAL GO")).toBeInTheDocument();
});

test("laudo sem amostra nem classes de erro mostra a lacuna, e não um vazio disfarçado", async () => {
  laudos = [laudo({ sample: "", error_classes: "", evidence: [] })];
  render(<ProjectDetailPage id={1} />);
  await screen.findByText("Amostra usada");

  expect(within(linhaDe("Amostra usada")).getByText("—")).toBeInTheDocument();
  expect(within(linhaDe("Classes de erro observadas")).getByText("—")).toBeInTheDocument();
  expect(screen.getByText("Nenhuma Evidence vinculada.")).toBeInTheDocument();
});

test("a linha do KPI compara baseline e outcome, com a variação e a unidade", async () => {
  experimentos = [experimento()];
  indicadores = [kpi()];
  leituras = { 21: [medicao({ id: 30, kind: "baseline", kind_display: "Baseline", value: "260.00", measured_at: "2026-07-03T10:00:00Z" }), medicao()] };
  render(<ProjectDetailPage id={1} />);
  await screen.findByText("Tempo de resposta");

  const par = parDe("Tempo de resposta");
  expect(within(linhaDe("Tempo de resposta")).getByText("Medido em horas · h")).toBeInTheDocument();
  expect(within(par).getByText("260")).toBeInTheDocument();
  expect(within(par).getByText("65")).toBeInTheDocument();
  // Cair 75% é sucesso quando menor é melhor: o sinal do bem e do mal sai da direção do KPI.
  expect(within(par).getByText("−75%")).toHaveClass("state--1");
});

test("KPI sem baseline mostra o traço e deixa a variação vazia — nunca zero", async () => {
  experimentos = [experimento()];
  indicadores = [kpi({ id: 22, name: "Taxa de resolução no primeiro contato", unit: "percent", unit_display: "Percentual", direction: "up" })];
  leituras = { 22: [medicao({ id: 33, kpi: 22, value: "68.00" })] };
  render(<ProjectDetailPage id={1} />);
  await screen.findByText("Taxa de resolução no primeiro contato");

  const par = parDe("Taxa de resolução no primeiro contato");
  expect(within(par).getByText("—")).toBeInTheDocument();
  expect(within(par).getByText("68")).toBeInTheDocument();
  expect(within(par).getByText("variação —")).toBeInTheDocument();
  expect(within(par).queryByText("0%")).toBeNull();
});

test("sem medição nenhuma, os dois lados da comparação são traço", async () => {
  experimentos = [experimento()];
  indicadores = [kpi()];
  render(<ProjectDetailPage id={1} />);
  await screen.findByText("Tempo de resposta");

  const linha = linhaDe("Tempo de resposta");
  expect(within(parDe("Tempo de resposta")).getAllByText("—")).toHaveLength(2);
  expect(within(linha).getByText("variação —")).toBeInTheDocument();
  // Sem leitura não há histórico: um `<details>` vazio prometeria uma série que não existe.
  expect(within(linha).queryByText(/Ver histórico/)).toBeNull();
});

test("o histórico fica colapsado e sobe do baseline até a leitura atual", async () => {
  const user = userEvent.setup();
  experimentos = [experimento()];
  indicadores = [kpi()];
  leituras = { 21: [
    medicao({ id: 32, value: "85.00", measured_at: "2026-07-17T10:00:00Z" }),
    medicao({ id: 30, kind: "baseline", kind_display: "Baseline", value: "260.00", measured_at: "2026-07-03T10:00:00Z" }),
    medicao(),
  ] };
  render(<ProjectDetailPage id={1} />);
  await screen.findByText("Tempo de resposta");

  const resumo = screen.getByText("Ver histórico de medições (3)");
  expect(resumo.closest("details")).not.toHaveAttribute("open");
  await user.click(resumo);
  const itens = within(resumo.closest("details")!).getAllByRole("listitem").map(item => item.textContent);
  expect(itens[0]).toContain("baseline");
  expect(itens[2]).toContain("atual");
});

test("sem KPI, o painel do PROVE diz que o experimento não começa assim", async () => {
  experimentos = [experimento({ status: "planned", status_display: "Planejado", missing_to_start: ["kpi", "baseline"] })];
  render(<ProjectDetailPage id={1} />);
  // Espera pelo **conteúdo do experimento**, não pelo título: o painel vazio também tem um h2
  // "PROVE", e esperar por ele deixaria a asserção correr antes da carga.
  await screen.findByText("Falta para iniciar o PROVE:");

  expect(screen.getByText(/Sem KPI definido/)).toHaveTextContent(/não começa sem indicador, critério e baseline/);
});

test("o início fica bloqueado com as três pastilhas do que falta", async () => {
  // Decisão **E1**. A lista é a do servidor (`missing_to_start`) — a tela não reexpressa a regra,
  // senão habilitaria o botão de um `POST` que o servidor nega.
  experimentos = [experimento({ status: "planned", status_display: "Planejado", missing_to_start: ["success_criteria", "baseline"], success_criteria: "" })];
  indicadores = [kpi()];
  render(<ProjectDetailPage id={1} />);
  await screen.findByText("Falta para iniciar o PROVE:");

  expect(pastilhaDe("KPI definido")).toBe("Pronto");
  expect(pastilhaDe("Critério de sucesso")).toBe("Falta");
  expect(pastilhaDe("Baseline medida")).toBe("Falta");
  expect(screen.getByRole("button", { name: "Iniciar PROVE" })).toBeDisabled();
});

test("com a lista vazia o início passa, e chama a action que confere de novo", async () => {
  const user = userEvent.setup();
  experimentos = [experimento({ status: "planned", status_display: "Planejado", missing_to_start: [] })];
  indicadores = [kpi()];
  render(<ProjectDetailPage id={1} />);
  await screen.findByText("Falta para iniciar o PROVE:");

  await user.click(screen.getByRole("button", { name: "Iniciar PROVE" }));
  await waitFor(() => expect(mocks.startProveExperiment).toHaveBeenCalledWith(9));
});

test("a lacuna aprovada não se registra sem quem aprovou", async () => {
  const user = userEvent.setup();
  experimentos = [experimento({ status: "planned", status_display: "Planejado", missing_to_start: ["baseline"] })];
  indicadores = [kpi()];
  render(<ProjectDetailPage id={1} />);
  await screen.findByText("Falta para iniciar o PROVE:");

  await user.click(screen.getByRole("button", { name: "Registrar lacuna aprovada" }));
  fireEvent.change(screen.getByLabelText("Por quê"), { target: { value: "A baseline histórica se perdeu na troca de ferramenta." } });
  await user.click(screen.getByRole("button", { name: "Registrar lacuna" }));
  // Aprovar é ato com autor: sem `gap_waiver_by` o servidor devolveria 400, e o formulário nem
  // chega a submeter.
  expect(mocks.registerProveGapWaiver).not.toHaveBeenCalled();

  await user.selectOptions(screen.getByLabelText("Quem aprovou"), "44");
  await user.click(screen.getByRole("button", { name: "Registrar lacuna" }));
  await waitFor(() => expect(mocks.registerProveGapWaiver).toHaveBeenCalledWith(9, {
    gap_waiver: "A baseline histórica se perdeu na troca de ferramenta.", gap_waiver_by: 44,
  }));
});

test("com lacuna assinada o botão de iniciar volta a valer", async () => {
  experimentos = [experimento({ status: "planned", status_display: "Planejado", missing_to_start: ["baseline"], gap_waiver: "Baseline histórica perdida.", gap_waiver_by: 44 })];
  indicadores = [kpi()];
  render(<ProjectDetailPage id={1} />);
  await screen.findByText("Falta para iniciar o PROVE:");

  expect(screen.getByRole("button", { name: "Iniciar PROVE" })).toBeEnabled();
  expect(screen.getByText(/Lacuna aprovada por Marina Kobayashi/)).toBeInTheDocument();
});

test("quem só lê continua lendo, e não vê botão nenhum", async () => {
  // O recorte de sempre: Vendas lê os cinco recursos da fatia e não escreve nenhum (FDD 049).
  mocks.auth = { aiEnabled: false, calendarEnabled: false, user: { role: "sales", is_admin: false } };
  experimentos = [experimento({ status: "planned", status_display: "Planejado", missing_to_start: ["baseline"] })];
  indicadores = [kpi()];
  render(<ProjectDetailPage id={1} />);
  await screen.findByText("Falta para iniciar o PROVE:");

  expect(pastilhaDe("Baseline medida")).toBe("Falta");
  expect(screen.queryByRole("button", { name: "Iniciar PROVE" })).toBeNull();
  expect(screen.queryByRole("button", { name: "Registrar lacuna aprovada" })).toBeNull();
});

test("a falha da carga aparece no painel, com o texto do servidor", async () => {
  mocks.listProveExperiments.mockRejectedValue(Object.assign(new Error("Não foi possível carregar o PROVE deste projeto."), { status: 500 }));
  render(<ProjectDetailPage id={1} />);

  expect(await screen.findAllByRole("alert")).not.toHaveLength(0);
  expect(screen.getAllByText(/Não foi possível carregar o PROVE deste projeto/).length).toBeGreaterThan(0);
});
