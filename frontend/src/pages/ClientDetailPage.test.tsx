import { cleanup, render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, expect, test, vi } from "vitest";

import { ClientDetailPage } from "./ClientDetailPage";

const mocks = vi.hoisted(() => ({
  api: vi.fn(),
  getConfig: vi.fn(),
  auth: { user: { id: 1, is_admin: true, role: "admin" } } as { user: { id: number; is_admin: boolean; role: string } },
}));
vi.mock("../api", () => ({ api: mocks.api, getConfig: mocks.getConfig }));
vi.mock("../auth", () => ({ useAuth: () => mocks.auth }));

function atividade(overrides: Record<string, unknown> = {}) {
  return {
    id: 9, client: 1, opportunity: null, invoice: null, cobranca_sinal: "", cobranca_sinal_display: "",
    kind: "call", kind_display: "Ligação", happened_on: "2026-08-10", summary: "Alinhamento de escopo",
    notes: "Cliente confirmou prazo.", owner: 1,
    created_at: "2026-08-10T10:00:00Z", updated_at: "2026-08-10T10:00:00Z",
    ...overrides,
  };
}

let atividades: unknown[] = [atividade()];

/** Um registro de satisfação (FDD 037). As duas fontes não são a mesma coisa (ADR 0032). */
function satisfacaoRegistro(overrides: Record<string, unknown> = {}) {
  return {
    id: 3, client: 1, project: null, source_meeting: null,
    nivel: "insatisfeito", nivel_display: "Insatisfeito",
    fonte: "declarada", fonte_display: "Declarada pelo cliente",
    happened_on: "2026-08-10", note: "Reclamou do prazo da última entrega.",
    registered_by: 1, created_at: "2026-08-10T10:00:00Z", updated_at: "2026-08-10T10:00:00Z",
    ...overrides,
  };
}

// Vazia por padrão: os testes que não são sobre satisfação não devem ver um "Insatisfeito" ou um
// "Promotor" a mais na tela — colidiria com o texto de outros selos (o `cobranca_sinal_display`
// de Interações, por exemplo, também usa "Insatisfeito"). Cada teste de satisfação povoa a sua.
let satisfacoes: unknown[] = [];

/** Um processo mapeado (FDD 039). A conta chega pronta do backend — a tela não a calcula. */
function processoMapeado(overrides: Record<string, unknown> = {}) {
  return {
    id: 12, client: 1, client_name: "Cliente A", name: "Faturamento manual de notas",
    position: 1, source_project: null, source_meeting: null, registered_by: 1,
    volume_mes: 400, tempo_horas: "0.50", pessoas: 2, custo_hora: "80.00",
    retrabalho_mes: "3200.00", erros_mes: null, perdas_mes: null, espera_mes: null, risco_mes: null,
    custo: {
      parcelas: [{ label: "Execução do processo", valor: "32000.00" }, { label: "Retrabalho", valor: "3200.00" }],
      total: "35200.00", nao_apurado: ["Erros", "Perdas", "Espera", "Risco"], sustentacao: "hipotese",
    },
    created_at: "2026-08-10T10:00:00Z", updated_at: "2026-08-10T10:00:00Z",
    ...overrides,
  };
}

// Vazia por padrão, pelo motivo da lista de satisfação acima: os testes que não são sobre processo
// não devem ganhar um selo a mais na tela para colidir com o texto dos vizinhos.
let processos: unknown[] = [];

/** Um contato (issue #55). `name` já vem composto, como o backend devolveria. */
function contato(overrides: Record<string, unknown> = {}) {
  return {
    id: 1, client: 1, first_name: "João", last_name: "", name: "João",
    email: "j@x.com", phone: "", job_title: "CEO", receives_billing: false,
    ...overrides,
  };
}

let contacts: unknown[] = [contato()];

/**
 * Um mandato (ADR 0050, FDD 046), no formato que `EngagementSerializer` devolve.
 *
 * `projects_count` chega **recortado pelo escopo de quem lê** — a tela só o mostra, não o calcula.
 */
function mandato(overrides: Record<string, unknown> = {}) {
  return {
    id: 5, account: 1, account_name: "Cliente A", name: "Transformação Financeira",
    mandate: "", sponsor: null, sponsor_name: null, owner: 1, owner_name: "Ana Souza",
    status: "active", status_display: "Ativo",
    commercial_model: "paid", commercial_model_display: "Pago",
    started_at: "2026-03-02", ended_at: null, success_definition: "",
    projects_count: 3, needs_review: false, archived_at: null,
    created_at: "2026-03-02T10:00:00Z", updated_at: "2026-03-02T10:00:00Z",
    ...overrides,
  };
}

// Vazia por padrão, pela razão das listas acima: os testes que não são sobre o mandato não devem
// ganhar dois selos a mais na tela para colidir com o texto dos vizinhos.
let engagements: unknown[] = [];

function stub() {
  mocks.api.mockImplementation((path: string) => {
    if (path === "/clients/1/") return Promise.resolve({ id: 1, name: "Cliente A", legal_name: "ACME SA", tax_id: "123", owner: 1, status: "active", vertical: null, vertical_name: "" });
    if (path === "/verticals/") return Promise.resolve([{ id: 7, name: "Igrejas", slug: "igrejas", position: 0, active: true }]);
    if (path === "/clients/1/overview/") return Promise.resolve({ client_id: 1, name: "Cliente A", status: "active", roi: { revenue: 1000, cost: 250, roi: 3 }, health: { score: 82, level: "saudável", project_id: 5 }, risk_level: "baixo", phase: { name: "Prove", status: "active" }, next_meeting: { title: "Comitê", date: "2026-09-10" }, ai_score: { maturity: 35, opportunity: 80, dimensions: [{ label: "Dados", score: 30 }], summary: "ok", scored_at: "2026-08-04T12:00:00Z" } });
    if (path.startsWith("/contacts")) return Promise.resolve(contacts);
    if (path.startsWith("/activities")) return Promise.resolve(atividades);
    if (path.startsWith("/invoices")) return Promise.resolve([{ id: 4, number: "2026-0007", status_display: "Vencida", due_date: "2026-08-05" }]);
    if (path.startsWith("/satisfacoes")) return Promise.resolve(satisfacoes);
    if (path.startsWith("/processos")) return Promise.resolve(processos);
    if (path.startsWith("/engagements")) return Promise.resolve(engagements);
    return Promise.resolve([]);
  });
}

beforeEach(() => {
  mocks.api.mockReset();
  mocks.getConfig.mockReset();
  mocks.auth.user = { id: 1, is_admin: true, role: "admin" };
  atividades = [atividade()];
  satisfacoes = [];
  processos = [];
  contacts = [contato()];
  engagements = [];
  mocks.getConfig.mockResolvedValue({ ai_enabled: true, calendar_enabled: false, esign_enabled: false, integrations: [] });
  stub();
});
afterEach(cleanup);

test("mostra cliente e seus contatos", async () => {
  render(<ClientDetailPage id={1} />);
  expect(await screen.findByRole("heading", { name: "Cliente A" })).toBeInTheDocument();
  expect(screen.getByText("João")).toBeInTheDocument();
  expect(screen.getByText("CEO")).toBeInTheDocument();
  expect(screen.getByText("Saúde da relação")).toBeInTheDocument();
  expect(screen.getByText("Você está aqui · Prove")).toBeInTheDocument();
  expect(screen.getByText("Maturidade de IA")).toBeInTheDocument();
  expect(screen.getByText("35/100")).toBeInTheDocument();
});

test("salva o cliente, cria e remove contato", async () => {
  const user = userEvent.setup();
  render(<ClientDetailPage id={1} />);
  await screen.findByRole("heading", { name: "Cliente A" });
  const cliente = within(screen.getByTestId("client-form"));
  const painel = within(screen.getByTestId("contacts-panel"));

  await user.clear(cliente.getByLabelText("Nome"));
  await user.type(cliente.getByLabelText("Nome"), "Cliente B");
  await user.click(cliente.getByRole("button", { name: "Salvar alterações" }));
  await waitFor(() => expect(mocks.api).toHaveBeenCalledWith("/clients/1/", expect.objectContaining({ method: "PATCH" })));

  await user.type(painel.getByLabelText("Nome"), "Maria");
  await user.type(painel.getByLabelText("E-mail"), "maria@x.com");
  await user.type(painel.getByLabelText("Telefone"), "1199");
  await user.type(painel.getByLabelText("Cargo"), "CTO");
  await user.click(painel.getByRole("button", { name: "Adicionar contato" }));
  await waitFor(() => expect(mocks.api).toHaveBeenCalledWith("/contacts/", expect.objectContaining({ method: "POST" })));

  await user.click(painel.getByLabelText("Remover João"));
  await user.click(screen.getByRole("button", { name: "Remover" }));
  await waitFor(() => expect(mocks.api).toHaveBeenCalledWith("/contacts/1/", expect.objectContaining({ method: "DELETE" })));
});

test("o formulário de contato tem campo Nome e campo Sobrenome", async () => {
  render(<ClientDetailPage id={1} />);
  await screen.findByRole("heading", { name: "Cliente A" });
  const painel = within(screen.getByTestId("contacts-panel"));

  expect(painel.getByLabelText("Nome")).toBeInTheDocument();
  expect(painel.getByLabelText("Sobrenome")).toBeInTheDocument();
});

test("o lápis carrega o contato no formulário e salva com PATCH", async () => {
  contacts = [contato({ id: 5, first_name: "Maria", last_name: "Souza", name: "Maria Souza", email: "maria@x.com" })];
  const user = userEvent.setup();
  render(<ClientDetailPage id={1} />);
  await screen.findByRole("heading", { name: "Cliente A" });
  const painel = within(screen.getByTestId("contacts-panel"));

  await user.click(painel.getByLabelText("Editar Maria Souza"));

  expect(painel.getByLabelText("Nome")).toHaveValue("Maria");
  expect(painel.getByLabelText("Sobrenome")).toHaveValue("Souza");
  expect(painel.getByRole("heading", { name: "Editando Maria Souza" })).toBeInTheDocument();

  await user.clear(painel.getByLabelText("Sobrenome"));
  await user.type(painel.getByLabelText("Sobrenome"), "Souza Lima");
  await user.click(painel.getByRole("button", { name: "Salvar alterações" }));

  await waitFor(() => expect(mocks.api).toHaveBeenCalledWith("/contacts/5/", expect.objectContaining({ method: "PATCH" })));
});

test("cancelar a edição de contato volta ao modo de criação sem requisição", async () => {
  contacts = [contato({ id: 5, first_name: "Maria", last_name: "Souza", name: "Maria Souza" })];
  const user = userEvent.setup();
  render(<ClientDetailPage id={1} />);
  await screen.findByRole("heading", { name: "Cliente A" });
  const painel = within(screen.getByTestId("contacts-panel"));

  await user.click(painel.getByLabelText("Editar Maria Souza"));
  mocks.api.mockClear();

  await user.click(painel.getByRole("button", { name: "Cancelar" }));

  expect(painel.getByRole("button", { name: "Adicionar contato" })).toBeInTheDocument();
  expect(painel.getByLabelText("Nome")).toHaveValue("");
  expect(mocks.api).not.toHaveBeenCalled();
});

test("arquivar o contato em edição sai do modo de edição", async () => {
  // Sem isto o formulário segue apontando para uma linha que `ArchiveModelViewSet` já não
  // devolve, e o "Salvar alterações" seguinte vira um 404 sem explicação.
  contacts = [contato({ id: 5, first_name: "Maria", last_name: "Souza", name: "Maria Souza" })];
  const user = userEvent.setup();
  render(<ClientDetailPage id={1} />);
  await screen.findByRole("heading", { name: "Cliente A" });
  const painel = within(screen.getByTestId("contacts-panel"));

  await user.click(painel.getByLabelText("Editar Maria Souza"));
  expect(painel.getByRole("heading", { name: "Editando Maria Souza" })).toBeInTheDocument();

  contacts = [];
  await user.click(painel.getByLabelText("Remover Maria Souza"));
  await user.click(screen.getByRole("button", { name: "Remover" }));

  await waitFor(() => expect(painel.getByRole("button", { name: "Adicionar contato" })).toBeInTheDocument());
  expect(painel.queryByRole("heading", { name: "Editando Maria Souza" })).not.toBeInTheDocument();
  expect(painel.getByLabelText("Nome")).toHaveValue("");
});

test("contato sem sobrenome não renderiza espaço solto", async () => {
  contacts = [contato({ id: 1, first_name: "Madonna", last_name: "", name: "Madonna" })];
  render(<ClientDetailPage id={1} />);
  await screen.findByRole("heading", { name: "Cliente A" });
  const painel = within(screen.getByTestId("contacts-panel"));

  expect(painel.getByText("Madonna", { exact: true })).toBeInTheDocument();
});

test("corrige a situação do cliente e leva o status no PATCH", async () => {
  const user = userEvent.setup();
  render(<ClientDetailPage id={1} />);
  await screen.findByRole("heading", { name: "Cliente A" });
  // O formulário nasce com o que veio da API, não com um default que apagaria o valor real.
  expect(screen.getByLabelText("Situação")).toHaveValue("active");

  await user.selectOptions(screen.getByLabelText("Situação"), "prospect");
  await user.click(screen.getByRole("button", { name: "Salvar alterações" }));

  await waitFor(() => expect(mocks.api).toHaveBeenCalledWith("/clients/1/", expect.objectContaining({
    method: "PATCH", body: expect.stringContaining("\"status\":\"prospect\""),
  })));
});


test("atribui uma vertical ao cliente", async () => {
  // É ela que escolhe a variante do blueprint quando a entrega instancia um bloco (FDD 026).
  const user = userEvent.setup();
  render(<ClientDetailPage id={1} />);
  await screen.findByRole("heading", { name: "Cliente A" });

  await user.selectOptions(screen.getByLabelText("Vertical"), "7");
  await user.click(screen.getByRole("button", { name: "Salvar alterações" }));

  await waitFor(() => expect(mocks.api).toHaveBeenCalledWith("/clients/1/", expect.objectContaining({
    method: "PATCH", body: expect.stringContaining("\"vertical\":7"),
  })));
});

test("cliente sem vertical continua funcionando", async () => {
  // Regra da FDD 026: nada exige vertical. Sem ela o catálogo inteiro segue disponível, genérico.
  render(<ClientDetailPage id={1} />);
  await screen.findByRole("heading", { name: "Cliente A" });

  expect(screen.getByLabelText("Vertical")).toHaveValue("");
});

// --- interações (FDD 035) -----------------------------------------------------------------------

test("lista as interações do cliente e registra uma nova", async () => {
  const user = userEvent.setup();
  render(<ClientDetailPage id={1} />);
  await screen.findByRole("heading", { name: "Cliente A" });

  expect(screen.getByText("Alinhamento de escopo")).toBeInTheDocument();
  expect(screen.getByText(/Ligação · 10\/08\/2026/)).toBeInTheDocument();

  await user.type(screen.getByPlaceholderText("Do que se tratou o contato"), "Ligação de follow-up");
  await user.click(screen.getByRole("button", { name: "Registrar interação" }));

  await waitFor(() => expect(mocks.api).toHaveBeenCalledWith("/activities/", expect.objectContaining({
    method: "POST", body: expect.stringContaining('"client":1'),
  })));
});

test("arquiva uma interação do cliente", async () => {
  const user = userEvent.setup();
  render(<ClientDetailPage id={1} />);
  await screen.findByRole("heading", { name: "Cliente A" });

  await user.click(screen.getByLabelText("Arquivar interação: Alinhamento de escopo"));

  await waitFor(() => expect(mocks.api).toHaveBeenCalledWith("/activities/9/", expect.objectContaining({ method: "DELETE" })));
});

test("entrega não vê o formulário nem o botão de arquivar de interações", async () => {
  mocks.auth.user = { id: 2, is_admin: false, role: "delivery" };
  render(<ClientDetailPage id={1} />);
  await screen.findByText("Alinhamento de escopo");

  expect(screen.queryByPlaceholderText("Do que se tratou o contato")).not.toBeInTheDocument();
  expect(screen.queryByLabelText("Arquivar interação: Alinhamento de escopo")).not.toBeInTheDocument();
});

test("classificar chama a rota e o sinal gravado volta com a conduta, não só com o selo", async () => {
  const user = userEvent.setup();
  render(<ClientDetailPage id={1} />);
  await screen.findByRole("heading", { name: "Cliente A" });

  // A segunda carga já traz o sinal lavrado pelo backend — a tela não o adivinha.
  atividades = [atividade({ invoice: 4, cobranca_sinal: "insatisfeito", cobranca_sinal_display: "Insatisfeito" })];
  await user.click(screen.getByLabelText("Classificar resposta: Alinhamento de escopo"));

  await waitFor(() => expect(mocks.api).toHaveBeenCalledWith(
    "/activities/9/classificar/", expect.objectContaining({ method: "POST" }),
  ));
  // O selo sozinho não muda o comportamento de ninguém: o que roteia a conduta é a linha ao lado.
  expect(await screen.findByText(/insistir piora tudo/)).toBeInTheDocument();
  // `selector: "strong"` (e não um `getByText` livre) desde a FDD 037: o painel de Satisfação
  // logo acima tem um `<option>Insatisfeito</option>` no próprio select de Nível, e um texto solto
  // colidiria com ele.
  expect(screen.getByText("Insatisfeito", { selector: "strong" })).toBeInTheDocument();
});

test("a interação já classificada não oferece classificar de novo", async () => {
  atividades = [atividade({ cobranca_sinal: "esqueceu", cobranca_sinal_display: "Esqueceu" })];
  render(<ClientDetailPage id={1} />);
  await screen.findByText("Alinhamento de escopo");

  expect(screen.queryByLabelText(/Classificar resposta/)).not.toBeInTheDocument();
  expect(screen.getByText(/o lembrete já resolveu/)).toBeInTheDocument();
});

test("a tela diz, e não só o código, que a IA grava o sinal e não age", async () => {
  render(<ClientDetailPage id={1} />);
  await screen.findByText("Alinhamento de escopo");
  expect(screen.getByText(/grava o sinal — não age/)).toBeInTheDocument();
});

test("com a IA desligada o botão de classificar some da tela", async () => {
  mocks.getConfig.mockResolvedValue({ ai_enabled: false, calendar_enabled: false, esign_enabled: false, integrations: [] });
  render(<ClientDetailPage id={1} />);
  await screen.findByText("Alinhamento de escopo");

  await waitFor(() => expect(mocks.getConfig).toHaveBeenCalled());
  expect(screen.queryByLabelText(/Classificar resposta/)).not.toBeInTheDocument();
  expect(screen.queryByText(/grava o sinal — não age/)).not.toBeInTheDocument();
});

test("o 502 diz que nada foi gravado — é diferente de um palpite gravado em silêncio", async () => {
  const user = userEvent.setup();
  render(<ClientDetailPage id={1} />);
  await screen.findByRole("heading", { name: "Cliente A" });

  mocks.api.mockImplementationOnce(() => Promise.reject(
    Object.assign(new Error("A IA não devolveu um sinal utilizável. Tente de novo."), { status: 502 }),
  ));
  await user.click(screen.getByLabelText("Classificar resposta: Alinhamento de escopo"));

  expect(await screen.findByRole("alert")).toHaveTextContent(/nada foi gravado — nenhum palpite entra no lugar/);
});

test("a interação pode responder a uma fatura, e é ela que dá contexto ao classificador", async () => {
  const user = userEvent.setup();
  render(<ClientDetailPage id={1} />);
  await screen.findByRole("heading", { name: "Cliente A" });

  await user.type(screen.getByPlaceholderText("Do que se tratou o contato"), "Retorno sobre a fatura");
  await user.selectOptions(await screen.findByLabelText("Responde a uma cobrança?"), "4");
  await user.click(screen.getByRole("button", { name: "Registrar interação" }));

  await waitFor(() => expect(mocks.api).toHaveBeenCalledWith("/activities/", expect.objectContaining({
    method: "POST", body: expect.stringContaining('"invoice":4'),
  })));
});

test("entrega não classifica nem pergunta pela flag: o recurso é fechado para ela", async () => {
  mocks.auth.user = { id: 2, is_admin: false, role: "delivery" };
  render(<ClientDetailPage id={1} />);
  await screen.findByText("Alinhamento de escopo");

  expect(screen.queryByLabelText(/Classificar resposta/)).not.toBeInTheDocument();
  expect(mocks.getConfig).not.toHaveBeenCalled();
});

// --- satisfação (FDD 037, ADR 0032) --------------------------------------------------------------

test("a lista de satisfação distingue as duas fontes, não só o nível", async () => {
  satisfacoes = [
    satisfacaoRegistro(),
    satisfacaoRegistro({ id: 4, nivel: "promotor", nivel_display: "Promotor", fonte: "percebida", fonte_display: "Percebida por quem entrega", happened_on: "2026-08-01", note: "" }),
  ];
  render(<ClientDetailPage id={1} />);
  await screen.findByRole("heading", { name: "Cliente A" });

  expect(await screen.findByText("Satisfação")).toBeInTheDocument();
  // Cada registro é a linha inteira: nível, fonte e nota juntos. Ancorar pela nota (única por
  // registro) evita colidir com as opções do próprio `<select>` de fonte no formulário logo acima.
  const declarada = (await screen.findByText("Reclamou do prazo da última entrega.")).closest(".row");
  expect(declarada).not.toBeNull();
  const dentroDeclarada = within(declarada as HTMLElement);
  expect(dentroDeclarada.getByText("Insatisfeito")).toBeInTheDocument();
  expect(dentroDeclarada.getByText("Declarada pelo cliente")).toBeInTheDocument();

  const percebida = (await screen.findByText("01/08/2026")).closest(".row");
  expect(percebida).not.toBeNull();
  const dentroPercebida = within(percebida as HTMLElement);
  expect(dentroPercebida.getByText("Promotor")).toBeInTheDocument();
  expect(dentroPercebida.getByText("Percebida por quem entrega")).toBeInTheDocument();
});

test("registra uma satisfação nova", async () => {
  const user = userEvent.setup();
  render(<ClientDetailPage id={1} />);
  await screen.findByRole("heading", { name: "Cliente A" });

  await user.selectOptions(screen.getByLabelText("Nível"), "promotor");
  await user.selectOptions(screen.getByLabelText("Fonte"), "percebida");
  await user.type(screen.getByPlaceholderText("O que o cliente disse, ou o que foi percebido"), "Elogiou a entrega na call de comitê.");
  await user.click(screen.getByRole("button", { name: "Registrar satisfação" }));

  await waitFor(() => expect(mocks.api).toHaveBeenCalledWith("/satisfacoes/", expect.objectContaining({
    method: "POST", body: expect.stringContaining('"client":1'),
  })));
  expect(mocks.api).toHaveBeenCalledWith("/satisfacoes/", expect.objectContaining({
    body: expect.stringContaining('"nivel":"promotor"'),
  }));
  expect(mocks.api).toHaveBeenCalledWith("/satisfacoes/", expect.objectContaining({
    body: expect.stringContaining('"fonte":"percebida"'),
  }));
});

test("insatisfeito sem nota volta 400 e a tela mostra a mensagem do campo, não uma falha genérica", async () => {
  const user = userEvent.setup();
  render(<ClientDetailPage id={1} />);
  await screen.findByRole("heading", { name: "Cliente A" });

  mocks.api.mockImplementationOnce(() => Promise.reject(
    Object.assign(new Error("Diga o que o cliente disse: insatisfeito sem nota não se avalia depois."), { status: 400 }),
  ));
  await user.selectOptions(screen.getByLabelText("Nível"), "insatisfeito");
  await user.click(screen.getByRole("button", { name: "Registrar satisfação" }));

  expect(await screen.findByRole("alert")).toHaveTextContent(/insatisfeito sem nota não se avalia depois/);
  // A tela continua inteira — o formulário não some, e o rascunho não se perde.
  expect(screen.getByRole("button", { name: "Registrar satisfação" })).toBeInTheDocument();
});

// --- Discovery estruturado (FDD 039, ADR 0034) ---------------------------------------------------

test("o painel de processos leva ao mapa e diz se o número se sustenta", async () => {
  processos = [
    processoMapeado(),
    processoMapeado({ id: 13, name: "Cobrança por planilha", custo: { parcelas: [{ label: "Execução do processo", valor: "9000.00" }], total: "9000.00", nao_apurado: [], sustentacao: "sustentado" } }),
  ];
  render(<ClientDetailPage id={1} />);
  await screen.findByRole("heading", { name: "Cliente A" });

  expect(await screen.findByText("Processos mapeados")).toBeInTheDocument();

  const emHipotese = (await screen.findByText("Faturamento manual de notas")).closest(".row");
  expect(emHipotese).not.toBeNull();
  const dentroHipotese = within(emHipotese as HTMLElement);
  expect(dentroHipotese.getByText("Ainda em hipótese")).toBeInTheDocument();
  // O total nunca vai sozinho quando é parcial: sem esta marca, R$ 35.200,00 é lido como a conta
  // inteira de um processo cujos quatro últimos insumos ninguém apurou.
  expect(dentroHipotese.getByText(/R\$ 35\.200,00 por mês · total parcial, 4 sem apuração/)).toBeInTheDocument();
  expect(dentroHipotese.getByRole("link", { name: "Abrir o mapa" })).toHaveAttribute("href", "/clientes/1/processos/12");

  const sustentado = (await screen.findByText("Cobrança por planilha")).closest(".row");
  const dentroSustentado = within(sustentado as HTMLElement);
  expect(dentroSustentado.getByText("Sustentado por evidência")).toBeInTheDocument();
  // Conta completa: nada de "parcial" pendurado num total que é a conta inteira.
  expect(dentroSustentado.getByText("R$ 9.000,00 por mês")).toBeInTheDocument();
});

test("cliente sem processo mapeado mostra o estado vazio, não um painel em branco", async () => {
  render(<ClientDetailPage id={1} />);
  await screen.findByRole("heading", { name: "Cliente A" });

  expect(await screen.findByText("Nenhum processo mapeado para este cliente.")).toBeInTheDocument();
});

// --- Engagements (ADR 0050, FDD 046; DAP `docs/design/dap-engagement-r1/`, r1, A1 · B1) --------

test("a seção lista os mandatos com status e as duas pílulas de modelo comercial", async () => {
  engagements = [
    mandato({ sponsor_name: "Marina Alencar" }),
    mandato({
      id: 6, name: "Discovery Cartas Vivas", sponsor_name: "Rafael Nôga",
      commercial_model: "design_partner", commercial_model_display: "Design partner",
      started_at: "2026-06-01", projects_count: 1,
    }),
  ];
  render(<ClientDetailPage id={1} />);
  await screen.findByRole("heading", { name: "Cliente A" });
  const painel = within(screen.getByTestId("engagements-panel"));

  // Decisão A1: o termo canônico em inglês como título, a copy em volta em pt-BR.
  expect(painel.getByRole("heading", { name: "Engagements" })).toBeInTheDocument();
  expect(painel.getByText("2 engagements ativos nesta conta")).toBeInTheDocument();
  expect(painel.getByText("Transformação Financeira")).toBeInTheDocument();
  expect(painel.getByText("Patrocínio de Marina Alencar")).toBeInTheDocument();
  // Precisão de mês (decisão 6), e o singular do projeto na segunda linha.
  expect(painel.getByText("Desde 03/2026 · 3 projetos")).toBeInTheDocument();
  expect(painel.getByText("Desde 06/2026 · 1 projeto")).toBeInTheDocument();

  // **Decisão B1, e é por isso que "Pago" é asserção própria**: um teste que só verificasse
  // "Design partner" passaria igual sob B2, que é justamente a alternativa recusada.
  expect(painel.getByText("Pago")).toHaveClass("state--off");
  expect(painel.getByText("Design partner")).toHaveClass("state--0");
  expect(painel.getAllByText("Ativo")).toHaveLength(2);
  expect(painel.getAllByText("Ativo")[0]).toHaveClass("state--1");
});

test("mandato encerrado é neutro, não vermelho, e mostra o período fechado", async () => {
  engagements = [mandato({
    name: "Piloto Atendimento 24h", status: "closed", status_display: "Encerrado",
    started_at: "2026-02-10", ended_at: "2026-05-20", projects_count: 2,
  })];
  render(<ClientDetailPage id={1} />);
  await screen.findByRole("heading", { name: "Cliente A" });
  const painel = within(screen.getByTestId("engagements-panel"));

  // Decisão 2: "Arquivado"/"Encerrado" não são aviso — são a ausência de um estado. `state--3`
  // faria a conta de melhor histórico parecer a mais problemática.
  expect(painel.getByText("Encerrado")).toHaveClass("state--off");
  expect(painel.getByText("02/2026 → 05/2026 · 2 projetos")).toBeInTheDocument();
  // Nenhum mandato ativo, e a frase continua sendo a aprovada — sem improviso.
  expect(painel.getByText("0 engagements ativos nesta conta")).toBeInTheDocument();
});

test("conta sem mandato mostra o estado vazio, não um painel em branco", async () => {
  render(<ClientDetailPage id={1} />);
  await screen.findByRole("heading", { name: "Cliente A" });
  const painel = within(screen.getByTestId("engagements-panel"));

  expect(painel.getByText("Nenhum engagement")).toBeInTheDocument();
  // A copy diz o que fazer e por quê — "Nenhum engagement cadastrado." deixaria a pessoa
  // exatamente onde estava.
  expect(painel.getByText(/Crie o mandato antes de converter uma oportunidade/)).toBeInTheDocument();
  // O vazio não esconde a saída.
  expect(painel.getByRole("button", { name: "Novo engagement" })).toBeInTheDocument();
});

test("entrega vê a lista de mandatos e nenhuma ação sobre ela", async () => {
  mocks.auth.user = { id: 3, is_admin: false, role: "delivery" };
  engagements = [mandato({ sponsor_name: "Marina Alencar" })];
  render(<ClientDetailPage id={1} />);
  await screen.findByRole("heading", { name: "Cliente A" });
  const painel = within(screen.getByTestId("engagements-panel"));

  // A lista, sim: quem entrega precisa saber a que mandato o projeto pertence.
  expect(painel.getByText("Transformação Financeira")).toBeInTheDocument();
  // O desenho não inventa permissão — ele deixa de mostrar o que a API recusaria (403).
  expect(painel.queryByRole("button", { name: "Novo engagement" })).not.toBeInTheDocument();
  expect(painel.queryByLabelText("Editar Transformação Financeira")).not.toBeInTheDocument();
  expect(painel.queryByLabelText("Arquivar Transformação Financeira")).not.toBeInTheDocument();
});

test("o formulário embutido cria o mandato e não pede responsável", async () => {
  const user = userEvent.setup();
  render(<ClientDetailPage id={1} />);
  await screen.findByRole("heading", { name: "Cliente A" });
  const painel = within(screen.getByTestId("engagements-panel"));

  // Sem modal (decisão 3): o formulário abre dentro do próprio painel.
  await user.click(painel.getByRole("button", { name: "Novo engagement" }));
  await user.type(painel.getByLabelText("Nome"), "Transformação Financeira");
  await user.selectOptions(painel.getByLabelText("Modelo comercial"), "design_partner");
  await user.click(painel.getByRole("button", { name: "Adicionar engagement" }));

  await waitFor(() => expect(mocks.api).toHaveBeenCalledWith("/engagements/", expect.objectContaining({ method: "POST" })));
  const corpo = JSON.parse(mocks.api.mock.calls.find(([rota]) => rota === "/engagements/")![1].body);
  expect(corpo).toMatchObject({ account: 1, name: "Transformação Financeira", commercial_model: "design_partner" });
  // `owner` não vai no payload: quem cria aqui é quem está logado, e é `perform_create` que grava.
  expect(corpo).not.toHaveProperty("owner");
  // Data vazia vai como `null`, e não como `""` — um `DateField` com string vazia volta 400.
  expect(corpo.started_at).toBeNull();
  expect(corpo.sponsor).toBeNull();
});

test("o lápis carrega o mandato no formulário e o título vira Editando", async () => {
  const user = userEvent.setup();
  engagements = [mandato()];
  render(<ClientDetailPage id={1} />);
  await screen.findByRole("heading", { name: "Cliente A" });
  const painel = within(screen.getByTestId("engagements-panel"));

  await user.click(painel.getByLabelText("Editar Transformação Financeira"));

  expect(painel.getByRole("heading", { name: "Editando Transformação Financeira" })).toBeInTheDocument();
  expect(painel.getByLabelText("Nome")).toHaveValue("Transformação Financeira");
  expect(painel.getByLabelText("Início")).toHaveValue("2026-03-02");
  // Os dois "Cancelar" são os que o board desenha: um no cabeçalho, que é o botão da faixa
  // enquanto o formulário está aberto, e um ao lado de "Salvar alterações".
  expect(painel.getAllByRole("button", { name: "Cancelar" })).toHaveLength(2);

  await user.clear(painel.getByLabelText("Nome"));
  await user.type(painel.getByLabelText("Nome"), "Transformação Financeira 2027");
  await user.click(painel.getByRole("button", { name: "Salvar alterações" }));

  await waitFor(() => expect(mocks.api).toHaveBeenCalledWith("/engagements/5/", expect.objectContaining({ method: "PATCH" })));
});

test("cancelar a edição volta ao modo de criação sem requisição", async () => {
  const user = userEvent.setup();
  engagements = [mandato()];
  render(<ClientDetailPage id={1} />);
  await screen.findByRole("heading", { name: "Cliente A" });
  const painel = within(screen.getByTestId("engagements-panel"));

  await user.click(painel.getByLabelText("Editar Transformação Financeira"));
  await user.click(painel.getAllByRole("button", { name: "Cancelar" })[0]);

  expect(painel.getByRole("heading", { name: "Engagements" })).toBeInTheDocument();
  expect(painel.getByRole("button", { name: "Novo engagement" })).toBeInTheDocument();
  expect(mocks.api).not.toHaveBeenCalledWith("/engagements/5/", expect.anything());
});

test("arquivar mandato com projeto vivo mostra a recusa do backend no topo da página", async () => {
  const user = userEvent.setup();
  engagements = [mandato()];
  render(<ClientDetailPage id={1} />);
  await screen.findByRole("heading", { name: "Cliente A" });
  const painel = within(screen.getByTestId("engagements-panel"));

  await user.click(painel.getByLabelText("Arquivar Transformação Financeira"));
  mocks.api.mockImplementationOnce(() => Promise.reject(Object.assign(
    new Error("Este engagement ainda tem 3 projeto(s) em aberto. Arquive esses projetos antes de arquivar o engagement."),
    { status: 409 },
  )));
  await user.click(screen.getByRole("button", { name: "Arquivar" }));

  // No `.alert--error` do **topo da página** (decisão 4), que é onde esta tela já põe o erro dela —
  // e com o `detail` do backend inteiro, sem a orientação genérica de 409 colada atrás: nada
  // mudou desde que a tela carregou, e recarregar não resolveria.
  const alerta = await screen.findByRole("alert");
  expect(alerta).toHaveTextContent("Este engagement ainda tem 3 projeto(s) em aberto. Arquive esses projetos antes de arquivar o engagement.");
  expect(alerta).toHaveClass("alert--error");
});
