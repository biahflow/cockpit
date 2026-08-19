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

function stub() {
  mocks.api.mockImplementation((path: string) => {
    if (path === "/clients/1/") return Promise.resolve({ id: 1, name: "Cliente A", legal_name: "ACME SA", tax_id: "123", owner: 1, status: "active", vertical: null, vertical_name: "" });
    if (path === "/verticals/") return Promise.resolve([{ id: 7, name: "Igrejas", slug: "igrejas", position: 0, active: true }]);
    if (path === "/clients/1/overview/") return Promise.resolve({ client_id: 1, name: "Cliente A", status: "active", roi: { revenue: 1000, cost: 250, roi: 3 }, health: { score: 82, level: "saudável", project_id: 5 }, risk_level: "baixo", phase: { name: "Prove", status: "active" }, next_meeting: { title: "Comitê", date: "2026-09-10" }, ai_score: { maturity: 35, opportunity: 80, dimensions: [{ label: "Dados", score: 30 }], summary: "ok", scored_at: "2026-08-04T12:00:00Z" } });
    if (path.startsWith("/contacts")) return Promise.resolve([{ id: 1, client: 1, name: "João", email: "j@x.com", phone: "", job_title: "CEO" }]);
    if (path.startsWith("/activities")) return Promise.resolve(atividades);
    if (path.startsWith("/invoices")) return Promise.resolve([{ id: 4, number: "2026-0007", status_display: "Vencida", due_date: "2026-08-05" }]);
    if (path.startsWith("/satisfacoes")) return Promise.resolve(satisfacoes);
    return Promise.resolve([]);
  });
}

beforeEach(() => {
  mocks.api.mockReset();
  mocks.getConfig.mockReset();
  mocks.auth.user = { id: 1, is_admin: true, role: "admin" };
  atividades = [atividade()];
  satisfacoes = [];
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

  await user.clear(screen.getByLabelText("Nome"));
  await user.type(screen.getByLabelText("Nome"), "Cliente B");
  await user.click(screen.getByRole("button", { name: "Salvar alterações" }));
  await waitFor(() => expect(mocks.api).toHaveBeenCalledWith("/clients/1/", expect.objectContaining({ method: "PATCH" })));

  await user.type(screen.getByPlaceholderText("Nome"), "Maria");
  await user.type(screen.getByPlaceholderText("E-mail"), "maria@x.com");
  await user.type(screen.getByPlaceholderText("Telefone"), "1199");
  await user.type(screen.getByPlaceholderText("Cargo"), "CTO");
  await user.click(screen.getByRole("button", { name: "Adicionar contato" }));
  await waitFor(() => expect(mocks.api).toHaveBeenCalledWith("/contacts/", expect.objectContaining({ method: "POST" })));

  await user.click(screen.getByLabelText("Remover João"));
  await user.click(screen.getByRole("button", { name: "Remover" }));
  await waitFor(() => expect(mocks.api).toHaveBeenCalledWith("/contacts/1/", expect.objectContaining({ method: "DELETE" })));
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
