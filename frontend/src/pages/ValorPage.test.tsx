import { cleanup, render, screen, within } from "@testing-library/react";
import { afterEach, beforeEach, expect, test, vi } from "vitest";

import { ValorPage } from "./ValorPage";

/**
 * A tela `/contas/:id/valor` — DAP `docs/design/dap-prove-e-valor-r1/`, revisão 1, decisão **D1**.
 *
 * Duas coisas são cobradas aqui, e as duas são a mesma preocupação vista de dois lados: **pendente
 * não entra no total** (só valor aprovado é valor) e **montante não apurado é `—`, nunca `R$ 0`**.
 * Um total que somasse o pendente afirmaria dinheiro que ninguém aprovou; um zero no lugar do
 * traço afirmaria que se apurou e deu zero.
 */

const mocks = vi.hoisted(() => ({
  api: vi.fn(),
  listValueLedgerEntries: vi.fn(),
  getMeasurement: vi.fn(),
  getKpi: vi.fn(),
  auth: { user: { id: 1, is_admin: true, role: "admin" } } as { user: { id: number; is_admin: boolean; role: string } },
}));
vi.mock("../api", () => ({
  api: mocks.api,
  listValueLedgerEntries: mocks.listValueLedgerEntries,
  getMeasurement: mocks.getMeasurement,
  getKpi: mocks.getKpi,
}));
vi.mock("../auth", () => ({ useAuth: () => mocks.auth }));

const conta = { id: 4, name: "Nord Logística", legal_name: "", tax_id: "", owner: 1, lifecycle_status: "active", status: "active", vertical: null, vertical_name: "" };
const engagement = { id: 6, account: 4, account_name: "Nord Logística", name: "Transformação do atendimento", mandate: "", sponsor: null, sponsor_name: null, owner: 1, owner_name: "Ana", status: "active", status_display: "Ativo", commercial_model: "paid", commercial_model_display: "Pago", started_at: "2026-03-02", ended_at: null, success_definition: "", projects_count: 2, needs_review: false, archived_at: null, created_at: "2026-03-02T10:00:00Z", updated_at: "2026-03-02T10:00:00Z" };

const entrada = (overrides: Record<string, unknown> = {}) => ({
  id: 51, engagement: 6, project: 12, outcome_measurement: 31,
  value_type: "cost_saving", value_type_display: "Redução de custo",
  amount: "18400.00", quantity: null, period_start: "2026-07-01", period_end: "2026-07-31",
  attribution_method: "direta (medição do PROVE)", status: "approved", status_display: "Aprovado",
  approved_by: 1, approved_at: "2026-08-05T10:00:00Z",
  created_at: "2026-08-01T10:00:00Z", updated_at: "2026-08-05T10:00:00Z", ...overrides,
});

let entradas: ReturnType<typeof entrada>[] = [];
let engagements: unknown[] = [engagement];
let contaOuFalha: unknown = conta;

function stub() {
  mocks.api.mockImplementation((path: string) => {
    if (path === "/clients/4/") return contaOuFalha instanceof Error ? Promise.reject(contaOuFalha) : Promise.resolve(contaOuFalha);
    if (path.startsWith("/engagements/")) return Promise.resolve(engagements);
    return Promise.resolve([]);
  });
  mocks.listValueLedgerEntries.mockImplementation(() => Promise.resolve(entradas));
  // Entrada → medição → indicador, os dois saltos que dão nome ao Outcome de origem.
  mocks.getMeasurement.mockImplementation((id: number) => Promise.resolve({
    id, kpi: id === 31 ? 21 : 22, kind: "outcome", kind_display: "Outcome", value: "65.00",
    period_start: "2026-07-01", period_end: "2026-07-31", measured_at: "2026-07-24T10:00:00Z",
    source_evidence: [], confidence: null, created_at: "2026-07-24T10:00:00Z", updated_at: "2026-07-24T10:00:00Z",
  }));
  mocks.getKpi.mockImplementation((id: number) => Promise.resolve({
    id, project: 12, prove_experiment: 9,
    name: id === 21 ? "Tempo de resposta" : "Taxa de resolução no primeiro contato",
    definition: "", formula: "", unit: "hours", unit_display: "Horas",
    direction: "down", direction_display: "Menor é melhor", data_source: "", cadence: "",
    owner: null, target: null, created_at: "2026-07-01T10:00:00Z", updated_at: "2026-07-01T10:00:00Z",
  }));
}

function linhaDe(texto: string | RegExp): HTMLElement {
  const linha = screen.getAllByText(texto).map(no => no.closest(".row")).find(Boolean);
  expect(linha).toBeTruthy();
  return linha as HTMLElement;
}

beforeEach(() => {
  for (const mock of Object.values(mocks)) if (typeof mock === "function") mock.mockReset();
  mocks.auth = { user: { id: 1, is_admin: true, role: "admin" } };
  entradas = []; engagements = [engagement]; contaOuFalha = conta;
  stub();
});
afterEach(cleanup);

test("o ledger vazio diz de onde uma entrada de valor vem", async () => {
  render(<ValorPage accountId={4} />);
  await screen.findByRole("heading", { name: "Valor gerado — Nord Logística" });

  expect(screen.getByText(/Nenhum valor registrado/)).toHaveTextContent(/aponta para um Outcome medido/);
  expect(screen.getByText("Nenhuma entrada fora do total.")).toBeInTheDocument();
});

test("o total soma só o aprovado, e diz quanto ficou de fora", async () => {
  entradas = [
    entrada(),
    entrada({ id: 52, outcome_measurement: 32, amount: "6200.00", value_type: "capacity", value_type_display: "Capacidade", status: "pending", status_display: "Pendente", approved_by: null, approved_at: null, period_start: "2026-08-01", period_end: "2026-08-31" }),
  ];
  render(<ValorPage accountId={4} />);
  await screen.findByText("Redução de custo");

  const total = screen.getByText("Total aprovado").closest(".metric-card") as HTMLElement;
  expect(within(total).getByText("R$ 18.400")).toBeInTheDocument();
  expect(within(total).getByText(/1 entrada não aprovada de R\$ 6\.200 não somada — fora deste total/)).toBeInTheDocument();
  // Pendente continua na lista: o que ela não faz é entrar no total.
  expect(within(linhaDe("Capacidade")).getByText("Pendente")).toHaveClass("state--2");
});

test("montante não apurado é traço, e não R$ 0", async () => {
  entradas = [entrada({ amount: null, status: "draft", status_display: "Rascunho", approved_by: null, approved_at: null })];
  render(<ValorPage accountId={4} />);
  await screen.findByText("Redução de custo");

  const linha = linhaDe("Redução de custo");
  expect(within(linha).getByText(/^— · julho\/2026 · atribuição: direta/)).toBeInTheDocument();
  // Rascunho é o **neutro**: não é aviso, e não é valor.
  expect(within(linha).getByText("Rascunho")).toHaveClass("state--off");
  expect(screen.getByText("Total aprovado").closest(".metric-card")).toHaveTextContent("R$ 0");
});

test("cada linha cita o Outcome de origem pelo nome do KPI", async () => {
  entradas = [entrada(), entrada({ id: 52, outcome_measurement: 32, value_type_display: "Capacidade", value_type: "capacity" })];
  render(<ValorPage accountId={4} />);
  await screen.findByText("Redução de custo");

  expect(within(linhaDe("Redução de custo")).getByText("Outcome de origem: Tempo de resposta")).toBeInTheDocument();
  expect(within(linhaDe("Capacidade")).getByText("Outcome de origem: Taxa de resolução no primeiro contato")).toBeInTheDocument();
  // A entrada com projeto atribuído tem por onde voltar ao experimento que a mediu.
  expect(within(linhaDe("Redução de custo")).getByRole("link", { name: "Ver no PROVE" })).toHaveAttribute("href", "/projetos/12#prove");
});

test("a janela de mais de um mês vira intervalo", async () => {
  entradas = [entrada({ period_start: "2026-07-01", period_end: "2026-09-30" })];
  render(<ValorPage accountId={4} />);
  await screen.findByText("Redução de custo");

  expect(within(linhaDe("Redução de custo")).getByText(/julho\/2026 → setembro\/2026/)).toBeInTheDocument();
});

test("a Entrega fora da conta lê a razão, e não um 404 cru", async () => {
  // O recorte do RFC 0003 chega como 404 na rota da conta; só a Entrega vê a frase, porque para
  // admin e Vendas um 404 significa mesmo "esta conta não existe".
  mocks.auth = { user: { id: 9, is_admin: false, role: "delivery" } };
  contaOuFalha = Object.assign(new Error("Não encontrado."), { status: 404 });
  render(<ValorPage accountId={4} />);

  expect(await screen.findByText(/Você não participa de nenhum projeto desta conta/)).toBeInTheDocument();
});

test("uma conta sem mandato não pede ledger nenhum", async () => {
  // O Value Ledger pende do `Engagement`: sem mandato não há entrada, e não há o que perguntar.
  engagements = [];
  render(<ValorPage accountId={4} />);
  await screen.findByRole("heading", { name: "Valor gerado — Nord Logística" });

  expect(mocks.listValueLedgerEntries).not.toHaveBeenCalled();
  expect(screen.getByText(/Nenhum valor registrado/)).toBeInTheDocument();
});

test("a aprovada sem montante fica fora do total, e o rodapé diz isso", async () => {
  // `value_type: capacity` carrega `quantity` e não `amount`. Somá-la como zero é aritmética
  // correta e leitura errada: o total afirmaria ter contado tudo que foi aprovado. É a mesma
  // distinção nulo≠zero da Fase 5, do lado de quem lê.
  entradas = [
    entrada({ id: 1, status: "approved", status_display: "Aprovado", amount: "12000.00" }),
    entrada({
      id: 2, status: "approved", status_display: "Aprovado",
      amount: null, quantity: "180.00", value_type: "capacity", value_type_display: "Capacidade",
    }),
  ];
  render(<ValorPage accountId={4} />);
  await screen.findByText("Redução de custo");

  const total = screen.getByText("Total aprovado").closest(".metric-card") as HTMLElement;
  // O total conta só o que tem montante...
  expect(within(total).getByText("R$ 12.000")).toBeInTheDocument();
  // ...e o rodapé não deixa a outra sumir.
  expect(within(total).getByText(/1 aprovada sem montante/)).toBeInTheDocument();
  expect(screen.queryByText("Nenhuma entrada fora do total.")).not.toBeInTheDocument();
});
