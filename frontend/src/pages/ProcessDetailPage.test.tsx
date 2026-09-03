import { cleanup, render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, expect, test, vi } from "vitest";

import { ProcessDetailPage } from "./ProcessDetailPage";

const mocks = vi.hoisted(() => ({
  api: vi.fn(),
  listPainPointsByProcess: vi.fn(),
  listImprovementOpportunities: vi.fn(),
  createPainPoint: vi.fn(),
  updatePainPoint: vi.fn(),
}));
vi.mock("../api", () => ({
  api: mocks.api,
  listPainPointsByProcess: mocks.listPainPointsByProcess,
  listImprovementOpportunities: mocks.listImprovementOpportunities,
  createPainPoint: mocks.createPainPoint,
  updatePainPoint: mocks.updatePainPoint,
}));
// A promoção a fato carimba `reviewed_by` com o usuário autenticado (§6.9): a tela lê `useAuth`.
vi.mock("../auth", () => ({
  useAuth: () => ({ user: { id: 99, username: "ana", first_name: "Ana", last_name: "Sá", email: "ana@x.co", role: "delivery", is_admin: false, has_avatar: false, avatar_updated_at: null } }),
}));

/**
 * A conta do custo do estado atual (FDD 039). **Nasce parcial**, que é o caso que importa: três
 * dos seis rótulos sem apuração, e um total que não é a conta inteira. Um mock com `nao_apurado`
 * vazio faria a asserção mais importante desta tela nunca rodar.
 */
function custo(overrides: Record<string, unknown> = {}) {
  return {
    parcelas: [
      { label: "Execução do processo", valor: "32000.00" },
      { label: "Retrabalho", valor: "3200.00" },
    ],
    total: "35200.00",
    nao_apurado: ["Erros", "Perdas", "Espera", "Risco"],
    sustentacao: "hipotese",
    ...overrides,
  };
}

/**
 * A marca de publicável (FDD 051, ADR 0060), no estado em que tudo nasce: **nada é publicado por
 * decisão** — a ADR 0060 recusou o backfill de propósito, e a migração `0075` não tem `RunPython`.
 * O selo de leitura desta tela (DAP `dap-publicacao-discovery-r1`, decisão A1) lê daqui.
 */
const oculto = (estado: "ready" | "blocked" = "ready", falta = "") => ({
  published_at: null, published_by: null,
  publication_state: {
    state: estado, missing: falta ? ["published_evidence"] : [], missing_phrase: falta,
    blocked_by: 0, blocked_phrase: "",
  },
});
const visivel = (presos = 0, impedimento = "") => ({
  published_at: "2026-08-20T10:00:00Z", published_by: 1,
  publication_state: {
    state: "published", missing: [], missing_phrase: "",
    blocked_by: presos, blocked_phrase: impedimento,
  },
});

function processoMapeado(overrides: Record<string, unknown> = {}) {
  return {
    id: 1, account: 4, client: 4, client_name: "Cliente A", name: "Faturamento manual de notas",
    position: 1, source_project: 2, source_meeting: 3, registered_by: 1,
    volume_mes: 400, tempo_horas: "0.50", pessoas: 2, custo_hora: "80.00",
    retrabalho_mes: "3200.00", erros_mes: null, perdas_mes: null, espera_mes: null, risco_mes: null,
    custo: custo(), ...oculto(),
    created_at: "2026-08-10T10:00:00Z", updated_at: "2026-08-10T10:00:00Z",
    ...overrides,
  };
}

/** A `Evidence` do split: o dado bruto, com a forma de onde veio (FDD 045). */
function evidence(overrides: Record<string, unknown> = {}) {
  return {
    id: 7, account: 4, discovery: null, process: 1, step: null,
    kind: "interview", kind_display: "Entrevista (o que dizem)",
    raw_excerpt: "A gente refaz a conferência inteira quando a nota volta.", reference: "",
    source_session: null, source_meeting: 3, captured_at: "2026-08-10T10:00:00Z",
    captured_by: 1, content_hash: "abc", ...oculto(), created_at: "2026-08-10T10:00:00Z",
    updated_at: "2026-08-10T10:00:00Z", ...overrides,
  };
}

/** O `Finding` do split: a afirmação, ligada à `Evidence` que a sustenta. */
function finding(overrides: Record<string, unknown> = {}) {
  return {
    id: 20, account: 4, process: 1, step: null,
    statement: "A equipe acredita que metade do retrabalho vem de cadastro desatualizado.",
    epistemic_status: "hypothesis", epistemic_status_display: "Hipótese",
    confidence: null, reviewed_by: null, reviewed_at: null, evidences: [7], ...oculto(),
    created_at: "2026-08-10T10:00:00Z", updated_at: "2026-08-10T10:00:00Z", ...overrides,
  };
}

/** A dor observada no processo (FDD 048, DAP priorização r1 — decisão E1). */
function painPoint(overrides: Record<string, unknown> = {}) {
  return {
    id: 11, account: 4, process: 1, step: null,
    title: "Retrabalho na conciliação de pagamentos de convênio", description: "",
    impact_type: "financial", impact_type_display: "Financeiro", impact_estimate: null,
    findings: [], status: "observed", status_display: "Observado",
    ...oculto(), created_at: "2026-08-10T10:00:00Z", updated_at: "2026-08-10T10:00:00Z",
    ...overrides,
  };
}

let processo: unknown = processoMapeado();
let etapas: unknown[] = [];
let findings: unknown[] = [];
let evidencias: unknown[] = [];
let dores: unknown[] = [];
let oportunidades: unknown[] = [];

function stub() {
  mocks.api.mockImplementation((path: string, init?: RequestInit) => {
    if (path === "/processos/1/") return Promise.resolve(processo);
    if (path.startsWith("/processo-etapas")) return Promise.resolve(etapas);
    if (path.startsWith("/findings")) return Promise.resolve(findings);
    if (path.startsWith("/evidence")) {
      // O POST de `Evidence` devolve a linha criada: o `Finding` precisa da chave dela para nascer
      // ligado. Só o `?process=` de leitura devolve a lista.
      if (init?.method === "POST") return Promise.resolve({ ...evidence(), id: 501 });
      return Promise.resolve(evidencias);
    }
    return Promise.resolve([]);
  });
  mocks.listPainPointsByProcess.mockImplementation(() => Promise.resolve(dores));
  mocks.listImprovementOpportunities.mockImplementation(() => Promise.resolve(oportunidades));
  mocks.createPainPoint.mockResolvedValue(painPoint());
  mocks.updatePainPoint.mockResolvedValue(painPoint({ status: "discarded", status_display: "Descartado" }));
}

/** A linha de lista que contém aquele texto — o selo e o botão são irmãos do `.row-main`.
 *
 * `getAllByText` e não `getByText`: o nome de uma etapa aparece **duas** vezes na tela, na linha
 * dela e na opção do seletor de vínculo do formulário do achado. Consultar o primeiro que tem
 * `.row` acima é o que distingue os dois sem depender da ordem do DOM. */
function linhaDe(texto: string): HTMLElement {
  const linha = screen.getAllByText(texto).map(no => no.closest(".row")).find(Boolean);
  expect(linha).toBeTruthy();
  return linha as HTMLElement;
}

beforeEach(() => {
  mocks.api.mockReset();
  mocks.listPainPointsByProcess.mockReset();
  mocks.listImprovementOpportunities.mockReset();
  mocks.createPainPoint.mockReset();
  mocks.updatePainPoint.mockReset();
  dores = [];
  oportunidades = [];
  processo = processoMapeado();
  etapas = [{ id: 5, process: 1, processo: 1, name: "Conferência da nota no ERP", position: 1, pessoas: "Analista de faturamento", sistema: "ERP Protheus", dados: "Entra o pedido; sai a nota", tempo: "30 minutos por nota", erro: "", retrabalho: "" }];
  findings = [finding()];
  evidencias = [evidence()];
  stub();
});
afterEach(cleanup);

test("mostra o processo com a conta à vista, e não só o total", async () => {
  render(<ProcessDetailPage clientId={4} id={1} />);
  expect(await screen.findByRole("heading", { name: "Faturamento manual de notas" })).toBeInTheDocument();

  expect(screen.getByText("R$ 35.200,00")).toBeInTheDocument();
  // As parcelas são a razão de a tela existir: um número sem a conta que o produziu não se
  // discute numa reunião, aceita-se ou rejeita-se.
  expect(screen.getByText("Execução do processo")).toBeInTheDocument();
  expect(screen.getByText("R$ 32.000,00")).toBeInTheDocument();
  expect(screen.getByText("R$ 3.200,00")).toBeInTheDocument();
});

test("o total parcial nunca aparece sozinho: a tela diz o que ficou de fora", async () => {
  render(<ProcessDetailPage clientId={4} id={1} />);
  await screen.findByRole("heading", { name: "Faturamento manual de notas" });

  // Sem esta linha, um total parcial vira "custo zero" na leitura rápida — e "não medimos as
  // perdas" e "não há perdas" são conclusões opostas.
  const aviso = screen.getByText(/O total é parcial/);
  expect(aviso).toHaveTextContent("Erros, Perdas, Espera, Risco");
  expect(aviso).toHaveTextContent(/fora desta soma/);
});

test("sem insumo nenhum a tela não mostra conta: zero não seria a resposta", async () => {
  processo = processoMapeado({ custo: custo({ parcelas: [], total: "0.00", nao_apurado: ["Execução do processo", "Retrabalho", "Erros", "Perdas", "Espera", "Risco"] }) });
  render(<ProcessDetailPage clientId={4} id={1} />);
  await screen.findByRole("heading", { name: "Faturamento manual de notas" });

  expect(screen.getByText(/O total é parcial/)).toHaveTextContent("Execução do processo");
  expect(screen.getByText(/zero não seria a resposta/)).toBeInTheDocument();
});

test("o processo em hipótese diz que ainda é hipótese", async () => {
  render(<ProcessDetailPage clientId={4} id={1} />);
  await screen.findByRole("heading", { name: "Faturamento manual de notas" });

  expect(screen.getByText("Ainda em hipótese")).toBeInTheDocument();
  expect(screen.queryByText("Sustentado por evidência")).not.toBeInTheDocument();
});

test("o processo com fato registrado diz que o número se sustenta", async () => {
  processo = processoMapeado({ custo: custo({ sustentacao: "sustentado" }) });
  render(<ProcessDetailPage clientId={4} id={1} />);
  await screen.findByRole("heading", { name: "Faturamento manual de notas" });

  expect(screen.getByText("Sustentado por evidência")).toBeInTheDocument();
  expect(screen.queryByText("Ainda em hipótese")).not.toBeInTheDocument();
});

test("as seis perguntas do P-S-D-T-E-R aparecem, inclusive as que ninguém respondeu", async () => {
  render(<ProcessDetailPage clientId={4} id={1} />);
  await screen.findByRole("heading", { name: "Faturamento manual de notas" });

  const etapa = linhaDe("Conferência da nota no ERP");
  const dentro = within(etapa);
  expect(dentro.getByText("Pessoas — quem faz")).toBeInTheDocument();
  expect(dentro.getByText("Sistema — onde faz")).toBeInTheDocument();
  expect(dentro.getByText("Dados — o que entra e sai")).toBeInTheDocument();
  expect(dentro.getByText("Tempo — quanto demora")).toBeInTheDocument();
  expect(dentro.getByText("Erro — o que pode dar errado")).toBeInTheDocument();
  expect(dentro.getByText("Retrabalho — o que acontece quando dá errado")).toBeInTheDocument();
  // A lacuna é o produto: uma pergunta que a reunião não fez tem de ficar visível, senão a tela
  // parece completa justamente onde o levantamento não está.
  expect(dentro.getAllByText("Não levantado")).toHaveLength(2);
});

test("cria a etapa com as seis perguntas na ordem em que se pergunta", async () => {
  const user = userEvent.setup();
  render(<ProcessDetailPage clientId={4} id={1} />);
  await screen.findByRole("heading", { name: "Faturamento manual de notas" });

  await user.type(screen.getByPlaceholderText("O que acontece nesta etapa"), "Aprovação do fiscal");
  await user.type(screen.getByLabelText("Erro — o que pode dar errado"), "Fiscal ausente trava a fila");
  await user.click(screen.getByRole("button", { name: "Adicionar etapa" }));

  await waitFor(() => expect(mocks.api).toHaveBeenCalledWith("/processo-etapas/", expect.objectContaining({
    method: "POST", body: expect.stringContaining('"process":1'),
  })));
  expect(mocks.api).toHaveBeenCalledWith("/processo-etapas/", expect.objectContaining({
    body: expect.stringContaining('"erro":"Fiscal ausente trava a fila"'),
  }));
});

// --- a classificação governa (ADR 0034) ----------------------------------------------------------

test("o achado mostra a forma da fonte, a classificação e o que afirma", async () => {
  findings = [
    finding(),
    finding({ id: 21, epistemic_status: "unknown", epistemic_status_display: "Desconhecido", statement: "Ninguém soube dizer quanto a nota espera na fila.", evidences: [8] }),
  ];
  evidencias = [evidence(), evidence({ id: 8, kind: "observation", kind_display: "Observação (o que fazem)" })];
  render(<ProcessDetailPage clientId={4} id={1} />);
  await screen.findByRole("heading", { name: "Faturamento manual de notas" });

  const suposicao = within(linhaDe("A equipe acredita que metade do retrabalho vem de cadastro desatualizado."));
  expect(suposicao.getByText("Hipótese")).toBeInTheDocument();
  expect(suposicao.getByText("Entrevista (o que dizem)")).toBeInTheDocument();

  // `unknown` é valor de primeira classe: nomear o que ainda não se sabe é fazer o trabalho.
  const lacuna = within(linhaDe("Ninguém soube dizer quanto a nota espera na fila."));
  expect(lacuna.getByText("Desconhecido")).toBeInTheDocument();
});

test("promover a fato é ato humano: manda o PATCH com o revisor e o selo muda", async () => {
  const user = userEvent.setup();
  render(<ProcessDetailPage clientId={4} id={1} />);
  await screen.findByRole("heading", { name: "Faturamento manual de notas" });

  const achado = "A equipe acredita que metade do retrabalho vem de cadastro desatualizado.";
  expect(within(linhaDe(achado)).getByText("Hipótese")).toBeInTheDocument();

  // A segunda carga já traz o estado promovido pelo backend — a tela não o adivinha.
  findings = [finding({ epistemic_status: "fact", epistemic_status_display: "Fato" })];
  await user.click(screen.getByLabelText(`Promover a fato: ${achado}`));

  await waitFor(() => expect(mocks.api).toHaveBeenCalledWith("/findings/20/", expect.objectContaining({
    method: "PATCH", body: '{"epistemic_status":"fact","reviewed_by":99}',
  })));
  await waitFor(() => expect(within(linhaDe(achado)).getByText("Fato")).toBeInTheDocument());
  // Não há para onde promover de novo: um botão inerte diria que existe um grau acima do fato.
  expect(screen.queryByLabelText(/Promover a fato:/)).not.toBeInTheDocument();
});

test("o achado que já é fato não oferece promover", async () => {
  findings = [finding({ epistemic_status: "fact", epistemic_status_display: "Fato" })];
  render(<ProcessDetailPage clientId={4} id={1} />);
  await screen.findByRole("heading", { name: "Faturamento manual de notas" });

  expect(screen.queryByLabelText(/Promover a fato:/)).not.toBeInTheDocument();
});

test("classificação e forma abrem sem escolha feita — o default que a ADR 0034 recusou não volta pela tela", async () => {
  render(<ProcessDetailPage clientId={4} id={1} />);
  await screen.findByRole("heading", { name: "Faturamento manual de notas" });

  const classificacao = screen.getByLabelText("Classificação") as HTMLSelectElement;
  const forma = screen.getByLabelText("Forma da fonte") as HTMLSelectElement;
  expect(classificacao.value).toBe("");
  expect(forma.value).toBe("");
  // A opção vazia existe, é a selecionada e não é escolhível: quem não escolheu não passa.
  expect(within(classificacao).getByRole("option", { name: "Selecione…" })).toBeDisabled();
  expect(within(forma).getByRole("option", { name: "Selecione…" })).toBeDisabled();
  // E "Fato" não é oferecido na criação: ele é o que a promoção faz, com revisor e evidência viva.
  expect(within(classificacao).queryByRole("option", { name: "Fato" })).not.toBeInTheDocument();
});

test("registrar o achado grava a evidência e o finding ligados", async () => {
  const user = userEvent.setup();
  render(<ProcessDetailPage clientId={4} id={1} />);
  await screen.findByRole("heading", { name: "Faturamento manual de notas" });

  await user.selectOptions(screen.getByLabelText("Classificação"), "hypothesis");
  await user.selectOptions(screen.getByLabelText("Forma da fonte"), "data");
  await user.type(screen.getByPlaceholderText(/O que foi dito ou observado/), "O ERP registrou 412 notas no mês.");
  await user.type(screen.getByPlaceholderText(/A conclusão que a casa tirou/), "O volume mensal é de 412 notas.");
  await user.click(screen.getByRole("button", { name: "Registrar achado" }));

  // Primeiro a `Evidence`, com a forma e o trecho.
  await waitFor(() => expect(mocks.api).toHaveBeenCalledWith("/evidence/", expect.objectContaining({
    method: "POST", body: expect.stringContaining('"kind":"data"'),
  })));
  expect(mocks.api).toHaveBeenCalledWith("/evidence/", expect.objectContaining({
    body: expect.stringContaining('"raw_excerpt":"O ERP registrou 412 notas no mês."'),
  }));
  // Depois o `Finding`, em hipótese e ligado à evidência recém-criada (id 501 do stub).
  const findingPost = mocks.api.mock.calls.find(([path, init]) => path === "/findings/" && (init as RequestInit)?.method === "POST");
  expect(findingPost).toBeTruthy();
  const corpo = JSON.parse((findingPost![1] as RequestInit).body as string);
  expect(corpo.statement).toBe("O volume mensal é de 412 notas.");
  expect(corpo.epistemic_status).toBe("hypothesis");
  expect(corpo.evidences).toEqual([501]);
});

test("arquivar avisa que as etapas vão junto e os achados ficam com a conta", async () => {
  const user = userEvent.setup();
  render(<ProcessDetailPage clientId={4} id={1} />);
  await screen.findByRole("heading", { name: "Faturamento manual de notas" });

  // Nada foi arquivado ainda: a confirmação é o que existe entre o clique e o `DELETE`.
  await user.click(screen.getByRole("button", { name: "Arquivar processo" }));
  expect(mocks.api).not.toHaveBeenCalledWith("/processos/1/", expect.objectContaining({ method: "DELETE" }));

  const dialogo = within(screen.getByRole("dialog"));
  expect(dialogo.getByText(/1 etapa\(s\) dele/)).toBeInTheDocument();
  expect(dialogo.getByText(/achados ficam com a conta/)).toBeInTheDocument();
  expect(dialogo.getByRole("button", { name: "Arquivar" })).toBeInTheDocument();
});

test("a falha da API chega traduzida, com a orientação da tabela de erros", async () => {
  mocks.api.mockImplementation(() => Promise.reject(
    Object.assign(new Error("O estado deste processo mudou."), { status: 409 }),
  ));
  render(<ProcessDetailPage clientId={4} id={1} />);

  expect(await screen.findByRole("alert")).toHaveTextContent(/recarregue para ver o que vale agora/);
});


test("os insumos do custo são editáveis, e o que já foi medido vem preenchido", async () => {
  render(<ProcessDetailPage clientId={4} id={1} />);
  await screen.findByRole("heading", { name: "Faturamento manual de notas" });

  // Sem este formulário a conta seria zero para sempre: a extração traz o mapa, e os números são
  // levantados por gente depois.
  expect(screen.getByLabelText("Volume — ocorrências por mês")).toHaveValue(400);
  expect(screen.getByLabelText("Custo/hora — R$")).toHaveValue(80);
  // O que ainda não foi medido chega vazio, e não zerado.
  expect(screen.getByLabelText("Erros — R$/mês")).toHaveValue(null);
});

test("campo em branco vira null no envio, e nunca zero", async () => {
  const user = userEvent.setup();
  render(<ProcessDetailPage clientId={4} id={1} />);
  await screen.findByRole("heading", { name: "Faturamento manual de notas" });

  await user.type(screen.getByLabelText("Perdas — R$/mês"), "1500");
  await user.click(screen.getByRole("button", { name: /Salvar os insumos do custo/ }));

  await waitFor(() => expect(mocks.api).toHaveBeenCalledWith("/processos/1/", expect.objectContaining({
    method: "PATCH",
  })));
  const corpo = JSON.parse(
    (mocks.api.mock.calls.find(([path, init]) => path === "/processos/1/" && init?.method === "PATCH")![1] as RequestInit).body as string
  );
  expect(corpo.perdas_mes).toBe("1500");
  // A asserção inteira desta fatia, do lado da tela: em branco é "não apurado", não é zero.
  // Mandar `0` apagaria a diferença entre "não medimos" e "medimos e não há", e o `nao_apurado`
  // deixaria de existir — o total pareceria fechado sem nunca ter sido.
  expect(corpo.erros_mes).toBeNull();
  expect(corpo.espera_mes).toBeNull();
  expect(corpo.risco_mes).toBeNull();
});

test("limpar um insumo já medido devolve o campo a não apurado", async () => {
  const user = userEvent.setup();
  render(<ProcessDetailPage clientId={4} id={1} />);
  await screen.findByRole("heading", { name: "Faturamento manual de notas" });

  await user.clear(screen.getByLabelText("Retrabalho — R$/mês"));
  await user.click(screen.getByRole("button", { name: /Salvar os insumos do custo/ }));

  await waitFor(() => expect(mocks.api).toHaveBeenCalledWith("/processos/1/", expect.anything()));
  const corpo = JSON.parse(
    (mocks.api.mock.calls.find(([path, init]) => path === "/processos/1/" && init?.method === "PATCH")![1] as RequestInit).body as string
  );
  expect(corpo.retrabalho_mes).toBeNull();
});


test("o achado pode ser ligado a uma etapa, e sem escolha vai como null", async () => {
  const user = userEvent.setup();
  render(<ProcessDetailPage clientId={4} id={1} />);
  await screen.findByRole("heading", { name: "Faturamento manual de notas" });

  // O padrão é o processo inteiro: a extração nunca liga achado a etapa, porque o modelo não sabe
  // a qual delas ele pertence. Quem sabe é quem estava na reunião.
  await user.selectOptions(screen.getByLabelText("Classificação"), "hypothesis");
  await user.selectOptions(screen.getByLabelText("Forma da fonte"), "observation");
  await user.type(screen.getByPlaceholderText(/O que foi dito ou observado/), "Vi a fila travar.");
  await user.type(screen.getByLabelText("Achado"), "A conferência trava quando o pedido vem sem PO.");
  await user.click(screen.getByRole("button", { name: /Registrar achado/ }));

  await waitFor(() => expect(mocks.api).toHaveBeenCalledWith("/findings/", expect.anything()));
  const corpo = JSON.parse(
    (mocks.api.mock.calls.find(([path, init]) => path === "/findings/" && init?.method === "POST")![1] as RequestInit).body as string
  );
  expect(corpo.step).toBeNull();
});

test("escolher a etapa manda o id dela no achado e na evidência", async () => {
  const user = userEvent.setup();
  render(<ProcessDetailPage clientId={4} id={1} />);
  await screen.findByRole("heading", { name: "Faturamento manual de notas" });

  // Escopado ao formulário do achado: "Etapa (opcional)" é o rótulo dos **dois** vínculos opcionais
  // desta tela — o do achado e o da dor (DAP priorização r1, decisão E1).
  await user.selectOptions(within(screen.getByTestId("finding-form")).getByLabelText("Etapa (opcional)"), "5");
  await user.selectOptions(screen.getByLabelText("Classificação"), "hypothesis");
  await user.selectOptions(screen.getByLabelText("Forma da fonte"), "data");
  await user.type(screen.getByPlaceholderText(/O que foi dito ou observado/), "São 400 notas por mês.");
  await user.type(screen.getByLabelText("Achado"), "O volume mensal é de 400 notas.");
  await user.click(screen.getByRole("button", { name: /Registrar achado/ }));

  await waitFor(() => expect(mocks.api).toHaveBeenCalledWith("/findings/", expect.anything()));
  const evid = JSON.parse(
    (mocks.api.mock.calls.find(([path, init]) => path === "/evidence/" && init?.method === "POST")![1] as RequestInit).body as string
  );
  const find = JSON.parse(
    (mocks.api.mock.calls.find(([path, init]) => path === "/findings/" && init?.method === "POST")![1] as RequestInit).body as string
  );
  expect(evid.step).toBe(5);
  expect(find.step).toBe(5);
});

// --- a dor se registra onde é observada (DAP priorização r1, decisão E1) ------------------------

test("sem pain point, a seção diz por onde a dor entra", async () => {
  render(<ProcessDetailPage clientId={4} id={1} />);
  await screen.findByRole("heading", { name: "Faturamento manual de notas" });

  expect(screen.getByRole("heading", { name: "Pain points" })).toBeInTheDocument();
  expect(screen.getByText(/Nenhum pain point registrado/)).toHaveTextContent(
    /ao lado da evidência que a sustenta/,
  );
});

test("registra o pain point com o tipo de impacto escolhido, e a conta vem do processo", async () => {
  const user = userEvent.setup();
  render(<ProcessDetailPage clientId={4} id={1} />);
  await screen.findByRole("heading", { name: "Faturamento manual de notas" });

  // O select abre sem escolha feita: `impact_type` não tem default no modelo, e um formulário que
  // já abrisse em "Financeiro" classificaria como custo o que era risco.
  const impacto = screen.getByLabelText("Tipo de impacto") as HTMLSelectElement;
  expect(impacto.value).toBe("");
  expect(within(impacto).getByRole("option", { name: "Selecione…" })).toBeDisabled();

  await user.type(screen.getByPlaceholderText("A dor, na frase de quem observou"), "Glosas recorrentes por documentação incompleta");
  await user.selectOptions(impacto, "financial");
  await user.click(screen.getByRole("button", { name: "Registrar pain point" }));

  await waitFor(() => expect(mocks.createPainPoint).toHaveBeenCalledWith({
    account: 4, title: "Glosas recorrentes por documentação incompleta",
    impact_type: "financial", process: 1, step: null,
  }));
});

test("o selo diz se a dor já virou trabalho de priorização", async () => {
  dores = [painPoint(), painPoint({ id: 12, title: "Agenda dupla entre unidades" })];
  oportunidades = [{
    id: 3, account: 4, engagement: null, title: "Padronizar checklist de documentação",
    desired_change: "", impact_hypothesis: "", pain_points: [11], status: "open",
    status_display: "Aberta", score: null, assessment_version: null, rank: null,
    created_at: "2026-08-10T10:00:00Z", updated_at: "2026-08-10T10:00:00Z",
  }];
  render(<ProcessDetailPage clientId={4} id={1} />);
  await screen.findByRole("heading", { name: "Faturamento manual de notas" });

  const agrupada = within(linhaDe("Retrabalho na conciliação de pagamentos de convênio"));
  expect(agrupada.getByText("Agrupado")).toBeInTheDocument();
  expect(agrupada.getByText(/agrupado em "Padronizar checklist de documentação"/)).toBeInTheDocument();

  // "Sem oportunidade" é o neutro e aparece sempre: um selo ausente significaria duas coisas
  // para quem lê — dor solta, ou linha que a tela não soube classificar.
  expect(within(linhaDe("Agenda dupla entre unidades")).getByText("Sem oportunidade")).toBeInTheDocument();
});

test("descartar a dor manda o PATCH — e confirmar não é oferecido aqui", async () => {
  const user = userEvent.setup();
  dores = [painPoint()];
  render(<ProcessDetailPage clientId={4} id={1} />);
  await screen.findByRole("heading", { name: "Faturamento manual de notas" });

  // Confirmar exige achado vivo (FDD 048) e o produto ainda não tem essa costura na tela: oferecer
  // o valor produziria um 400 que quem clicou não entende.
  expect(screen.queryByRole("button", { name: /Confirmar pain point/ })).not.toBeInTheDocument();

  dores = [painPoint({ status: "discarded", status_display: "Descartado" })];
  await user.click(screen.getByLabelText("Descartar pain point: Retrabalho na conciliação de pagamentos de convênio"));

  await waitFor(() => expect(mocks.updatePainPoint).toHaveBeenCalledWith(11, { status: "discarded" }));
  await waitFor(() => expect(screen.getByText("Descartado")).toBeInTheDocument());
  expect(screen.getByLabelText(/^Reabrir pain point:/)).toBeInTheDocument();
});

test("o selo de publicação é leitura — e não se confunde com os dois vizinhos da mesma linha", async () => {
  // Decisão **D1** do DAP `dap-publicacao-discovery-r1`: na linha do achado convivem o selo
  // epistêmico ("Fato"/"Hipótese") e o de publicação; na da dor, "Sem oportunidade" e "Oculto do
  // cliente" — os dois `state--off`, cinzas, na mesma faixa. O que os separa é a copy e o ícone.
  processo = processoMapeado(visivel(2, "Este processo é a âncora de 2 achado(s) ou dor(es) publicado(s). Despublique-os primeiro."));
  findings = [finding(visivel())];
  evidencias = [evidence()];
  dores = [painPoint()];
  stub();
  render(<ProcessDetailPage clientId={4} id={1} />);
  await screen.findByRole("heading", { name: "Faturamento manual de notas" });

  // O mapa publicado, no cabeçalho, ao lado de "Arquivar processo".
  expect(screen.getAllByText("Visível ao cliente")).toHaveLength(2);
  const dor = within(linhaDe("Retrabalho na conciliação de pagamentos de convênio"));
  expect(dor.getByText("Sem oportunidade")).toBeInTheDocument();
  expect(dor.getByText("Oculto do cliente")).toBeInTheDocument();

  // **Acrescenta selo, não acrescenta ação** (decisão A1): publicar e ocultar moram na tela da
  // conta, e daqui só se vai até lá.
  expect(screen.queryByRole("button", { name: /Publicar/ })).not.toBeInTheDocument();
  expect(screen.queryByRole("button", { name: /Ocultar do cliente/ })).not.toBeInTheDocument();
  expect(screen.getByRole("link", { name: /Abrir a publicação do Discovery desta conta/ }))
    .toHaveAttribute("href", "/contas/4/publicacao");
});
