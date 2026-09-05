import { cleanup, render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, expect, test, vi } from "vitest";

import { moeda } from "../dinheiro";
import { PriorizacaoPage } from "./PriorizacaoPage";

const mocks = vi.hoisted(() => ({
  api: vi.fn(),
  listPainPointsByAccount: vi.fn(),
  listImprovementOpportunities: vi.fn(),
  listPriorityAssessments: vi.fn(),
  listSolutionHypotheses: vi.fn(),
  listBusinessCases: vi.fn(),
  createImprovementOpportunity: vi.fn(),
  createPriorityAssessment: vi.fn(),
  createSolutionHypothesis: vi.fn(),
  createBusinessCase: vi.fn(),
  updateImprovementOpportunity: vi.fn(),
  updateSolutionHypothesis: vi.fn(),
  updateBusinessCase: vi.fn(),
  decideBusinessCase: vi.fn(),
  auth: { user: { id: 1, is_admin: true, role: "admin" } } as { user: { id: number; is_admin: boolean; role: string } },
}));
vi.mock("../api", () => ({
  api: mocks.api,
  listPainPointsByAccount: mocks.listPainPointsByAccount,
  listImprovementOpportunities: mocks.listImprovementOpportunities,
  listPriorityAssessments: mocks.listPriorityAssessments,
  listSolutionHypotheses: mocks.listSolutionHypotheses,
  listBusinessCases: mocks.listBusinessCases,
  createImprovementOpportunity: mocks.createImprovementOpportunity,
  createPriorityAssessment: mocks.createPriorityAssessment,
  createSolutionHypothesis: mocks.createSolutionHypothesis,
  createBusinessCase: mocks.createBusinessCase,
  updateImprovementOpportunity: mocks.updateImprovementOpportunity,
  updateSolutionHypothesis: mocks.updateSolutionHypothesis,
  updateBusinessCase: mocks.updateBusinessCase,
  decideBusinessCase: mocks.decideBusinessCase,
}));
vi.mock("../auth", () => ({ useAuth: () => mocks.auth }));

function dor(overrides: Record<string, unknown> = {}) {
  return {
    id: 11, account: 4, process: 1, step: null,
    title: "Retrabalho na conciliação de pagamentos de convênio", description: "",
    impact_type: "financial", impact_type_display: "Financeiro", impact_estimate: null,
    findings: [1, 2], status: "observed", status_display: "Observado",
    created_at: "2026-08-10T10:00:00Z", updated_at: "2026-08-10T10:00:00Z",
    ...overrides,
  };
}

function oportunidade(overrides: Record<string, unknown> = {}) {
  return {
    id: 21, account: 4, engagement: null,
    title: "Padronizar checklist de documentação para faturamento TISS",
    desired_change: "", impact_hypothesis: "", pain_points: [11],
    status: "prioritized", status_display: "Priorizada",
    score: "78.00", assessment_version: 2, rank: 1,
    created_at: "2026-08-10T10:00:00Z", updated_at: "2026-08-10T10:00:00Z",
    ...overrides,
  };
}

function avaliacao(overrides: Record<string, unknown> = {}) {
  return {
    id: 31, improvement_opportunity: 21, version: 2,
    impact: 4, evidence_strength: 5, feasibility: 3, time_to_value: 4, economics: 3,
    formula_key: "v1", weights: {}, score: "78.00",
    rationale: "As glosas de TISS são o maior item do custo do estado atual.",
    assessed_by: 1, assessed_by_name: "Marina Kobayashi",
    created_at: "2026-08-18T10:00:00Z", updated_at: "2026-08-18T10:00:00Z",
    ...overrides,
  };
}

function hipotese(overrides: Record<string, unknown> = {}) {
  return {
    id: 41, improvement_opportunity: 21,
    statement: "Padronizar checklist único de documentos por convênio",
    intervention: "", assumptions: "", expected_effect: "",
    status: "chosen", status_display: "Escolhida",
    created_at: "2026-08-10T10:00:00Z", updated_at: "2026-08-10T10:00:00Z",
    ...overrides,
  };
}

function businessCase(overrides: Record<string, unknown> = {}) {
  return {
    id: 51, improvement_opportunity: 21, account: 4,
    solution_hypothesis: 41, priority_assessment: 31,
    investment: "42000.00", expected_return_year: "168000.00", payback_months: 4,
    current_state_cost: "19400.00",
    current_state_cost_source: { processos: [{ id: 1, sustentacao: "sustentado", total: "19400.00", nao_apurado: [] }], somados: [1] },
    rationale: "O leitor de nota se paga no primeiro trimestre.", assumptions: "",
    status: "draft", status_display: "Rascunho",
    decided_at: null, decided_by: null,
    created_at: "2026-08-20T10:00:00Z", updated_at: "2026-08-20T10:00:00Z",
    ...overrides,
  };
}

const processo = {
  id: 1, account: 4, account_name: "Clínica Vale Verde", name: "Faturamento TISS",
  position: 1, source_project: null, source_meeting: null, registered_by: 1,
  volume_mes: null, tempo_horas: null, pessoas: null, custo_hora: null,
  retrabalho_mes: null, erros_mes: null, perdas_mes: null, espera_mes: null, risco_mes: null,
  custo: { parcelas: [], total: "0.00", nao_apurado: [], sustentacao: "hipotese" },
  created_at: "2026-08-10T10:00:00Z", updated_at: "2026-08-10T10:00:00Z",
};

let dores: unknown[] = [];
let oportunidades: unknown[] = [];
let avaliacoes: unknown[] = [];
let hipoteses: unknown[] = [];
let businessCases: unknown[] = [];
let conta: unknown = { id: 4, name: "Clínica Vale Verde", legal_name: "", tax_id: "", owner: 1, lifecycle_status: "active", status: "active", vertical: null, vertical_name: "" };

function stub() {
  mocks.api.mockImplementation((path: string) => {
    if (path === "/accounts/4/") return conta instanceof Error ? Promise.reject(conta) : Promise.resolve(conta);
    if (path.startsWith("/processes")) return Promise.resolve([processo]);
    return Promise.resolve([]);
  });
  mocks.listPainPointsByAccount.mockImplementation(() => Promise.resolve(dores));
  mocks.listImprovementOpportunities.mockImplementation(() => Promise.resolve(oportunidades));
  mocks.listPriorityAssessments.mockImplementation(() => Promise.resolve(avaliacoes));
  mocks.listSolutionHypotheses.mockImplementation(() => Promise.resolve(hipoteses));
  mocks.listBusinessCases.mockImplementation(() => Promise.resolve(businessCases));
  mocks.createImprovementOpportunity.mockResolvedValue(oportunidade());
  mocks.createPriorityAssessment.mockResolvedValue(avaliacao());
  mocks.createSolutionHypothesis.mockResolvedValue(hipotese());
  mocks.createBusinessCase.mockResolvedValue(businessCase());
  mocks.updateImprovementOpportunity.mockResolvedValue(oportunidade());
  mocks.updateSolutionHypothesis.mockResolvedValue(hipotese());
  mocks.updateBusinessCase.mockResolvedValue(businessCase());
  mocks.decideBusinessCase.mockResolvedValue(businessCase({ status: "approved", status_display: "Aprovado", decided_at: "2026-09-05T14:12:00Z", decided_by: 1 }));
}

/** A linha de lista que contém aquele texto — o selo e o botão são irmãos do `.row-main`. */
function linhaDe(texto: string | RegExp): HTMLElement {
  const linha = screen.getAllByText(texto).map(no => no.closest(".row")).find(Boolean);
  expect(linha).toBeTruthy();
  return linha as HTMLElement;
}

beforeEach(() => {
  for (const mock of Object.values(mocks)) if (typeof mock === "function") mock.mockReset();
  mocks.auth.user = { id: 1, is_admin: true, role: "admin" };
  conta = { id: 4, name: "Clínica Vale Verde", legal_name: "", tax_id: "", owner: 1, lifecycle_status: "active", status: "active", vertical: null, vertical_name: "" };
  dores = [];
  oportunidades = [];
  avaliacoes = [];
  hipoteses = [];
  businessCases = [];
  stub();
});
afterEach(cleanup);

test("os dois painéis vazios dizem por onde começar", async () => {
  render(<PriorizacaoPage accountId={4} />);
  await screen.findByRole("heading", { name: "Priorização — Clínica Vale Verde" });

  // A dor entra pela tela do processo (decisão E1); a oportunidade nasce do agrupamento.
  expect(screen.getByText(/Nenhum pain point registrado/)).toHaveTextContent(/ao lado da evidência que a sustenta/);
  expect(screen.getByText(/Nenhuma Improvement Opportunity/)).toHaveTextContent(/Agrupe pain points para abrir a primeira/);
});

test("o painel do topo mostra só as dores que ainda não foram agrupadas", async () => {
  dores = [dor(), dor({ id: 12, title: "Agenda dupla entre unidades" })];
  oportunidades = [oportunidade()];
  render(<PriorizacaoPage accountId={4} />);
  await screen.findByRole("heading", { name: "Priorização — Clínica Vale Verde" });

  // É o único lugar do produto onde "o que ainda não foi olhado" fica visível: a dor já agrupada
  // virou trabalho de priorização e sai da fila de triagem.
  expect(screen.getByText("Agenda dupla entre unidades")).toBeInTheDocument();
  expect(screen.queryByLabelText("Selecionar Retrabalho na conciliação de pagamentos de convênio")).not.toBeInTheDocument();
  expect(screen.getByText(/1 dor observada, ainda não agrupada/)).toBeInTheDocument();
  // O nome do processo vem junto: "Observado em: 1" não diria nada a quem lê.
  expect(within(linhaDe("Agenda dupla entre unidades")).getByText(/Observado em: Faturamento TISS/)).toBeInTheDocument();
});

test("sem avaliação a linha mostra —, e nunca zero", async () => {
  oportunidades = [oportunidade({
    id: 22, title: "Consolidar prontuário eletrônico entre unidades", pain_points: [],
    status: "open", status_display: "Aberta", score: null, assessment_version: null, rank: null,
  })];
  render(<PriorizacaoPage accountId={4} />);
  await screen.findByRole("heading", { name: "Priorização — Clínica Vale Verde" });

  const linha = within(linhaDe(/Consolidar prontuário eletrônico entre unidades/));
  // Zero afirmaria que a oportunidade foi avaliada e vale zero; o traço diz que ninguém avaliou.
  expect(linha.getByText("Opportunity Score").parentElement).toHaveTextContent("—");
  expect(linha.queryByText("0")).not.toBeInTheDocument();
  // Sem avaliação não há o que versionar: a pílula de versão nem aparece.
  expect(linha.queryByText(/^v\d/)).not.toBeInTheDocument();
  expect(linha.getByText("Aberta")).toBeInTheDocument();
});

test("a lista sai ranqueada, e a sem avaliação vai para o fim", async () => {
  oportunidades = [
    oportunidade({ id: 23, title: "Sem avaliação", score: null, assessment_version: null, rank: null }),
    oportunidade({ id: 24, title: "Segunda colocada", score: "64.00", assessment_version: 1, rank: 2 }),
    oportunidade(),
  ];
  render(<PriorizacaoPage accountId={4} />);
  await screen.findByRole("heading", { name: "Priorização — Clínica Vale Verde" });

  // A ordem **é** o conteúdo desta tela: o rank vem derivado do servidor, e a tela ordena por ele
  // em vez de reexpressar a regra. Quem não tem avaliação não tem por onde ser ordenada.
  const titulos = screen.getAllByText(/^(#\d|—) · /).map(no => no.textContent);
  expect(titulos).toEqual([
    "#1 · Padronizar checklist de documentação para faturamento TISS",
    "#2 · Segunda colocada",
    "— · Sem avaliação",
  ]);
});

test("o detalhe abre com as cinco dimensões e o histórico colapsado", async () => {
  const user = userEvent.setup();
  dores = [dor()];
  oportunidades = [oportunidade()];
  avaliacoes = [avaliacao(), avaliacao({ id: 30, version: 1, impact: 3, evidence_strength: 3, feasibility: 3, time_to_value: 3, economics: 2, score: "56.00", created_at: "2026-07-02T10:00:00Z" })];
  hipoteses = [hipotese(), hipotese({ id: 42, statement: "Implementar OCR na entrada de guias", status: "proposed", status_display: "Proposta" })];
  render(<PriorizacaoPage accountId={4} />);
  await screen.findByRole("heading", { name: "Priorização — Clínica Vale Verde" });

  await user.click(screen.getByLabelText("Abrir detalhe: Padronizar checklist de documentação para faturamento TISS"));

  expect(await screen.findByText("Opportunity Score — versão 2")).toBeInTheDocument();
  for (const rotulo of ["Impact", "Evidence strength", "Feasibility", "Time to value", "Economics"]) {
    expect(screen.getAllByText(rotulo).length).toBeGreaterThan(0);
  }
  expect(screen.getByText("Versão 2 — vigente")).toBeInTheDocument();

  // Decisão C1: repriorizar cria versão nova e não sobrescreve — a anterior fica atrás de um
  // `<details>` **fechado**, visível a um clique e sem competir com a vigente.
  const historico = screen.getByText("Ver 1 avaliação anterior").closest("details") as HTMLDetailsElement;
  expect(historico.open).toBe(false);
  expect(within(historico).getByText("Versão 1")).toBeInTheDocument();
  expect(within(historico).getByText("Substituída")).toBeInTheDocument();

  // As hipóteses concorrentes, com a pílula que distingue a escolhida da proposta (decisão D1).
  // `selector: ".state"` porque o rótulo aparece **duas** vezes na linha: no selo e na opção
  // selecionada do controle de situação ao lado dele. É o selo que a decisão D1 desenha.
  expect(within(linhaDe("Padronizar checklist único de documentos por convênio")).getByText("Escolhida", { selector: ".state" })).toBeInTheDocument();
  expect(within(linhaDe("Implementar OCR na entrada de guias")).getByText("Proposta", { selector: ".state" })).toBeInTheDocument();
});

test("a oportunidade sem avaliação diz o que avaliar registra", async () => {
  const user = userEvent.setup();
  oportunidades = [oportunidade({ score: null, assessment_version: null, rank: null, status: "open", status_display: "Aberta" })];
  render(<PriorizacaoPage accountId={4} />);
  await screen.findByRole("heading", { name: "Priorização — Clínica Vale Verde" });

  await user.click(screen.getByLabelText(/^Abrir detalhe:/));

  expect(await screen.findByText(/Sem Opportunity Score/)).toHaveTextContent(/Avaliar registra a versão 1 do critério/);
});

test("avaliar manda as cinco notas — e o formulário abre sem nota escolhida", async () => {
  const user = userEvent.setup();
  oportunidades = [oportunidade({ score: null, assessment_version: null, rank: null })];
  render(<PriorizacaoPage accountId={4} />);
  await screen.findByRole("heading", { name: "Priorização — Clínica Vale Verde" });
  await user.click(screen.getByLabelText(/^Abrir detalhe:/));

  const impacto = await screen.findByLabelText("Impact") as HTMLSelectElement;
  // O mesmo argumento da ADR 0034: um select que abrisse em "3" seria a casa escolhendo por quem
  // não escolheu, e o resultado é um score que alguém leva para uma reunião.
  expect(impacto.value).toBe("");
  expect(within(impacto).getByRole("option", { name: "Selecione…" })).toBeDisabled();

  await user.selectOptions(impacto, "4");
  await user.selectOptions(screen.getByLabelText("Evidence strength"), "5");
  await user.selectOptions(screen.getByLabelText("Feasibility"), "3");
  await user.selectOptions(screen.getByLabelText("Time to value"), "4");
  await user.selectOptions(screen.getByLabelText("Economics"), "3");
  await user.click(screen.getByRole("button", { name: "Avaliar" }));

  await waitFor(() => expect(mocks.createPriorityAssessment).toHaveBeenCalledWith({
    improvement_opportunity: 21, impact: 4, evidence_strength: 5, feasibility: 3,
    time_to_value: 4, economics: 3, rationale: "",
  }));
});

test("agrupar leva as dores selecionadas para a oportunidade nova", async () => {
  const user = userEvent.setup();
  dores = [dor(), dor({ id: 12, title: "Agenda dupla entre unidades" })];
  render(<PriorizacaoPage accountId={4} />);
  await screen.findByRole("heading", { name: "Priorização — Clínica Vale Verde" });

  // Sem nada selecionado não há o que agrupar: o botão existe e não age.
  expect(screen.getByRole("button", { name: "Agrupar em oportunidade" })).toBeDisabled();

  await user.click(screen.getByLabelText("Selecionar Retrabalho na conciliação de pagamentos de convênio"));
  await user.click(screen.getByLabelText("Selecionar Agenda dupla entre unidades"));
  await user.click(screen.getByRole("button", { name: "Agrupar em oportunidade" }));
  await user.type(screen.getByLabelText("Título da oportunidade"), "Padronizar checklist de documentação");
  await user.click(screen.getByRole("button", { name: "Criar a oportunidade" }));

  await waitFor(() => expect(mocks.createImprovementOpportunity).toHaveBeenCalledWith({
    account: 4, title: "Padronizar checklist de documentação", pain_points: [11, 12],
  }));
});

test("a falha da API chega traduzida, com a orientação da tabela de erros", async () => {
  conta = Object.assign(new Error("O estado desta conta mudou."), { status: 409 });
  render(<PriorizacaoPage accountId={4} />);

  expect(await screen.findByRole("alert")).toHaveTextContent(/recarregue para ver o que vale agora/);
});

test("a Entrega fora do escopo da conta lê o motivo, e não um erro genérico", async () => {
  mocks.auth.user = { id: 3, is_admin: false, role: "delivery" };
  conta = Object.assign(new Error("Não encontrado."), { status: 404 });
  render(<PriorizacaoPage accountId={4} />);

  // O recorte de Entrega (RFC 0003) chega como 404 na conta. "Não encontrado" mandaria alguém
  // procurar um registro que existe; o motivo real é participação em projeto.
  expect(await screen.findByText("Você não participa de nenhum projeto desta conta.")).toBeInTheDocument();
  expect(screen.queryByRole("alert")).not.toBeInTheDocument();
});

test("a avaliação diz **quem** avaliou, e cai na data quando o nome não vem", async () => {
  // O board aprovado (`docs/design/dap-priorizacao-r1/`) escreve "Avaliado por {nome} em {data}",
  // e o id não diz quem é: `/users/` é fechada à Entrega, então metade de quem lê a tela veria um
  // número. `assessed_by_name` é campo derivado do serializer, no molde de `owner_name`.
  dores = [dor()];
  oportunidades = [oportunidade()];
  avaliacoes = [avaliacao()];
  stub();
  const user = userEvent.setup();
  render(<PriorizacaoPage accountId={4} />);
  await user.click(await screen.findByRole("button", { name: /Abrir detalhe/ }));

  expect(await screen.findByText(/Avaliado por Marina Kobayashi em/)).toBeInTheDocument();
});

test("sem nome do avaliador, a linha não inventa autor — mostra só a data", async () => {
  // `assessed_by` nulo (avaliação de migração, shell ou usuário removido) devolve o `default=""`
  // do serializer. A linha degrada para a data em vez de escrever "Avaliado por  em".
  dores = [dor()];
  oportunidades = [oportunidade()];
  avaliacoes = [avaliacao({ assessed_by: null, assessed_by_name: "" })];
  stub();
  const user = userEvent.setup();
  render(<PriorizacaoPage accountId={4} />);
  await user.click(await screen.findByRole("button", { name: /Abrir detalhe/ }));

  expect(await screen.findByText(/^Avaliado em/)).toBeInTheDocument();
  expect(screen.queryByText(/Avaliado por/)).not.toBeInTheDocument();
});

test("o select da hipótese não repete o que a pílula já diz", async () => {
  // Selo e select mostrando o mesmo rótulo lado a lado é a mesma informação em dois lugares, e
  // quem lê fica sem saber qual manda. A pílula é a leitura (decisão D1 do DAP); o select é a
  // ação, e por isso abre em "Mudar para…" e lista só os outros dois estados.
  dores = [dor()];
  oportunidades = [oportunidade()];
  avaliacoes = [avaliacao()];
  hipoteses = [hipotese()];  // status `chosen`
  stub();
  const user = userEvent.setup();
  render(<PriorizacaoPage accountId={4} />);
  await user.click(await screen.findByRole("button", { name: /Abrir detalhe/ }));

  const seletor = await screen.findByLabelText(/Mudar a situação da hipótese/);
  const rotulos = within(seletor).getAllByRole("option").map(opcao => opcao.textContent);
  expect(rotulos).toEqual(["Mudar para…", "Proposta", "Descartada"]);
  // "Escolhida" aparece **uma** vez na tela: na pílula, nunca também dentro do select.
  expect(screen.getAllByText("Escolhida")).toHaveLength(1);
});

/**
 * O Business Case (FDD 053), governado pelo DAP `dap-discovery-session-e-business-case-r2` —
 * decisões A1 e F1. Os seis estados do board, um por teste.
 */
async function abrirBusinessCase(): Promise<HTMLElement> {
  const user = userEvent.setup();
  render(<PriorizacaoPage accountId={4} />);
  await user.click(await screen.findByRole("button", { name: /Abrir detalhe/ }));
  const painel = await screen.findByText("Business Case");
  return painel.closest(".panel") as HTMLElement;
}

test("estado 1 — sem hipótese escolhida, a porta do business case nem aparece", async () => {
  dores = [dor()];
  oportunidades = [oportunidade()];
  hipoteses = [];  // nenhuma escolhida
  stub();
  const painel = within(await abrirBusinessCase());

  expect(painel.getByText(/Escolha uma hipótese de solução para montar o business case/)).toBeInTheDocument();
  expect(painel.queryByRole("button", { name: /Montar business case/ })).not.toBeInTheDocument();
});

test("estado 2 — hipótese escolhida, sem business case: a porta aparece", async () => {
  dores = [dor()];
  oportunidades = [oportunidade()];
  hipoteses = [hipotese()];  // status `chosen`
  businessCases = [];
  stub();
  const painel = within(await abrirBusinessCase());

  expect(painel.getByText("Nenhum registrado.")).toBeInTheDocument();
  expect(painel.getByRole("button", { name: /Montar business case/ })).toBeInTheDocument();
});

test("estado 3 — rascunho, com o custo do estado atual congelado ao lado", async () => {
  dores = [dor()];
  oportunidades = [oportunidade()];
  avaliacoes = [avaliacao()];
  hipoteses = [hipotese()];
  businessCases = [businessCase()];
  stub();
  const painel = within(await abrirBusinessCase());

  expect(painel.getByText("Rascunho")).toBeInTheDocument();
  expect(await painel.findByDisplayValue("42000.00")).toBeInTheDocument();
  expect(painel.getByDisplayValue("168000.00")).toBeInTheDocument();
  expect(painel.getByDisplayValue("4")).toBeInTheDocument();
  // Congelado — não é um campo editável, é leitura (input desabilitado).
  const custo = painel.getByLabelText("Custo do estado atual · congelado");
  expect(custo).toBeDisabled();
  expect(custo).toHaveValue(`${moeda("19400.00")} / mês`);
  expect(painel.getByRole("button", { name: "Aprovar o investimento" })).toBeEnabled();
  expect(painel.getByRole("button", { name: "Recusar" })).toBeEnabled();
});

test("estado 4 — custo não apurado é —, com o alerta, e nenhum caminho escreve R$ 0,00", async () => {
  dores = [dor()];
  oportunidades = [oportunidade()];
  avaliacoes = [avaliacao()];
  hipoteses = [hipotese()];
  businessCases = [businessCase({
    current_state_cost: null,
    current_state_cost_source: { processos: [{ id: 1, sustentacao: "hipotese", total: "0.00", nao_apurado: ["Volume", "Tempo"] }], somados: [] },
  })];
  stub();
  const painel = within(await abrirBusinessCase());

  expect(painel.getByLabelText("Custo do estado atual · congelado")).toHaveValue("—");
  const alerta = painel.getByRole("alert");
  expect(alerta).toHaveClass("alert--warn");
  expect(alerta).toHaveTextContent("Nenhum processo desta oportunidade tem custo sustentado por fato.");
  // A decisão F1 inteira: a lacuna nunca é o número zero.
  expect(screen.queryByText(/R\$\s?0,00/)).not.toBeInTheDocument();
});

test("estado 5 — aprovado: leitura, com o carimbo da decisão, e sem os botões de decisão", async () => {
  dores = [dor()];
  oportunidades = [oportunidade()];
  avaliacoes = [avaliacao()];
  hipoteses = [hipotese()];
  businessCases = [businessCase({ status: "approved", status_display: "Aprovado", decided_at: "2026-09-05T14:12:00Z", decided_by: 1, decided_by_name: "Ana Meireles" })];
  stub();
  const painel = within(await abrirBusinessCase());

  expect(painel.getByText("Aprovado", { selector: ".state" })).toBeInTheDocument();
  expect(painel.getByText(/R\$ 42\.000,00 investidos · R\$ 168\.000,00 esperados em 12 meses/)).toBeInTheDocument();
  expect(painel.getByText(/Decisão registrada/)).toBeInTheDocument();
  // Decidido não se edita: nem campo, nem botão de decisão, nem porta para montar outro.
  expect(painel.queryByRole("button", { name: "Aprovar o investimento" })).not.toBeInTheDocument();
  expect(painel.queryByRole("button", { name: "Recusar" })).not.toBeInTheDocument();
  expect(painel.queryByRole("button", { name: /Montar outro business case/ })).not.toBeInTheDocument();
  expect(painel.queryByRole("textbox")).not.toBeInTheDocument();
});

test("estado 6 — recusado: a oportunidade aceita outro", async () => {
  dores = [dor()];
  oportunidades = [oportunidade()];
  avaliacoes = [avaliacao()];
  hipoteses = [hipotese()];
  businessCases = [businessCase({ status: "rejected", status_display: "Recusado", decided_at: "2026-09-03T09:40:00Z", decided_by: 1 })];
  stub();
  const painel = within(await abrirBusinessCase());

  expect(painel.getByText("Recusado", { selector: ".state" })).toBeInTheDocument();
  expect(painel.getByRole("button", { name: /Montar outro business case/ })).toBeInTheDocument();
  // Recusado não oferece campo de edição do registro decidido.
  expect(painel.queryByRole("textbox")).not.toBeInTheDocument();
});

test("aprovar exige os dois números; recusar nunca fica desabilitado", async () => {
  const user = userEvent.setup();
  dores = [dor()];
  oportunidades = [oportunidade()];
  avaliacoes = [avaliacao()];
  hipoteses = [hipotese()];
  businessCases = [businessCase({ investment: null, expected_return_year: null })];
  stub();
  const painel = within(await abrirBusinessCase());

  const aprovar = painel.getByRole("button", { name: "Aprovar o investimento" });
  const recusar = painel.getByRole("button", { name: "Recusar" });
  expect(aprovar).toBeDisabled();
  expect(recusar).toBeEnabled();

  await user.type(painel.getByLabelText("Investimento"), "10000");
  expect(aprovar).toBeDisabled();  // falta o segundo número
  await user.type(painel.getByLabelText("Retorno esperado (12 meses)"), "40000");
  expect(aprovar).toBeEnabled();
});

test("decidir salva o rascunho digitado antes de aprovar, e nunca via PATCH de status", async () => {
  const user = userEvent.setup();
  dores = [dor()];
  oportunidades = [oportunidade()];
  avaliacoes = [avaliacao()];
  hipoteses = [hipotese()];
  businessCases = [businessCase()];
  stub();
  const painel = within(await abrirBusinessCase());

  await user.click(painel.getByRole("button", { name: "Aprovar o investimento" }));

  await waitFor(() => expect(mocks.updateBusinessCase).toHaveBeenCalledWith(51, {
    investment: "42000.00", expected_return_year: "168000.00", payback_months: 4,
    rationale: "O leitor de nota se paga no primeiro trimestre.",
  }));
  expect(mocks.decideBusinessCase).toHaveBeenCalledWith(51, "approved");
});

test("montar o business case cita a hipótese escolhida e a avaliação vigente — nunca zero no lugar do vazio", async () => {
  const user = userEvent.setup();
  dores = [dor()];
  oportunidades = [oportunidade()];
  avaliacoes = [avaliacao()];
  hipoteses = [hipotese()];
  businessCases = [];
  stub();
  const painel = within(await abrirBusinessCase());

  await user.click(painel.getByRole("button", { name: "Montar business case" }));
  await user.type(painel.getByLabelText("Justificativa"), "O leitor de nota se paga sozinho.");
  await user.click(painel.getByRole("button", { name: "Registrar o business case" }));

  await waitFor(() => expect(mocks.createBusinessCase).toHaveBeenCalledWith({
    improvement_opportunity: 21, solution_hypothesis: 41, priority_assessment: 31,
    investment: null, expected_return_year: null, payback_months: null,
    rationale: "O leitor de nota se paga sozinho.",
  }));
});

test("diz quem decidiu, e cai para a forma sem nome quando o autor saiu", async () => {
  // Decidir investir é ato **com autor** — é o que o `clean()` do modelo protege ao recusar
  // `approved` sem `decided_by`, e é o que o board aprovado mostra. Uma tela que dissesse só
  // "Aprovado em 05/09" devolveria à conversa a pergunta que este registro existe para responder.
  oportunidades = [oportunidade()];
  avaliacoes = [avaliacao()];
  hipoteses = [hipotese()];
  businessCases = [businessCase({
    status: "approved", status_display: "Aprovado",
    decided_at: "2026-09-05T14:12:00Z", decided_by: 7, decided_by_name: "Ana Meireles",
  })];
  stub();
  const painel = within(await abrirBusinessCase());

  expect(painel.getByText(/Aprovado por Ana Meireles em/)).toBeInTheDocument();
});

test("a decisão sem autor vivo degrada para a data, em vez de mentir", async () => {
  // `decided_by` é `SET_NULL`: quem decidiu pode ter saído da casa. "Aprovado por " sem nome seria
  // pior que a data sozinha — a frase encolhe, não inventa.
  oportunidades = [oportunidade()];
  avaliacoes = [avaliacao()];
  hipoteses = [hipotese()];
  businessCases = [businessCase({
    status: "approved", status_display: "Aprovado",
    decided_at: "2026-09-05T14:12:00Z", decided_by: null, decided_by_name: "",
  })];
  stub();
  const painel = within(await abrirBusinessCase());

  expect(painel.getByText(/^Aprovado em/)).toBeInTheDocument();
});
