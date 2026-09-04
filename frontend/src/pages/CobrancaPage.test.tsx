import { cleanup, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, expect, test, vi } from "vitest";

import { CobrancaPage } from "./CobrancaPage";

const mocks = vi.hoisted(() => ({
  api: vi.fn(),
  getConfig: vi.fn(),
  user: { id: 7, username: "ana", first_name: "Ana", last_name: "Souza", role: "admin", is_admin: true },
}));
vi.mock("../api", () => ({ api: mocks.api, getConfig: mocks.getConfig }));
vi.mock("../auth", () => ({ useAuth: () => ({ user: mocks.user }) }));

/** Uma linha do painel. **Todos os campos vêm do backend** — o teste nunca calcula um deles. */
function linha(overrides: Record<string, unknown> = {}) {
  return {
    invoice: 5, number: "2026-0007", account: 1, account_name: "Imobiliária Aurora",
    amount: "48750.90", due_date: "2026-08-05", status: "overdue", status_display: "Vencida",
    dias_de_atraso: 12, payment_url: "",
    proximo_degrau: "firm", proximo_degrau_display: "Cobrança firme",
    proximo_degrau_em: "2026-08-15", motivo: "",
    health_level: "atenção", tempo_de_casa_dias: 1200, reincidente: false,
    regua: "relacao_longa", recebido_do_cliente: "180000.00",
    suspensao: null, regua_ligada: true,
    // Satisfação (FDD 037): `null` por padrão — a maioria das faturas de verdade não tem registro
    // dentro da janela de 90 dias, e é esse o caso que os testes que não mencionam satisfação
    // precisam continuar cobrindo.
    satisfacao_nivel: null, satisfacao_fonte: null, satisfacao_dias: null,
    // A tensão e o sinal por registrar (FDD 038): nulos por padrão pelo mesmo motivo da satisfação
    // — a maioria das faturas não tem tensão nem resposta classificada pendente, e é esse o caso
    // que os testes que não os mencionam precisam continuar cobrindo.
    tensao_causa: null,
    sinal_kind: null, sinal_display: null, sinal_em: null, sinal_activity: null,
    ...overrides,
  };
}

function falha(status: number, detail: string) {
  return Object.assign(new Error(detail), { status });
}

function stub(linhas: unknown[], extra: Record<string, unknown> = {}) {
  return (path: string, options?: { method?: string }) => {
    if ((options?.method ?? "GET") === "GET") {
      if (path.startsWith("/cobranca/painel/")) return Promise.resolve(linhas);
      if (path.startsWith("/cobranca/")) return Promise.resolve(extra.historico ?? []);
      if (path.startsWith("/users/")) return Promise.resolve([mocks.user]);
    }
    return Promise.resolve({});
  };
}

beforeEach(() => {
  mocks.user = { id: 7, username: "ana", first_name: "Ana", last_name: "Souza", role: "admin", is_admin: true };
  mocks.api.mockImplementation(stub([linha()]));
  mocks.getConfig.mockResolvedValue({ ai_enabled: true, calendar_enabled: false, esign_enabled: false, integrations: [] });
});
afterEach(() => { cleanup(); vi.clearAllMocks(); });

/**
 * O critério de aceite 7 da FDD 036 e a seção Segurança da RFC 0004, que é a razão de esta tela
 * existir separada do Financeiro: os quatro fatos da relação **na mesma linha do próximo degrau**,
 * sem clique. É o teste que reprovaria um "ver mais" bonito.
 */
test("health, tempo de casa, total recebido e reincidência ficam na mesma linha do próximo degrau", async () => {
  render(<CobrancaPage />);
  const cartao = (await screen.findByRole("heading", { name: "Imobiliária Aurora" })).closest("article");
  expect(cartao).not.toBeNull();
  const dentro = within(cartao as HTMLElement);

  expect(dentro.getByText("atenção")).toBeInTheDocument();
  expect(dentro.getByText(/Cliente há 3 anos, nunca atrasou — régua de relação longa/)).toBeInTheDocument();
  expect(dentro.getByText(/180\.000,00/)).toBeInTheDocument();
  expect(dentro.getByText(/Próximo degrau: Cobrança firme/)).toBeInTheDocument();
});

test("o rótulo do degrau é o que o backend mandou, não um mapa local", async () => {
  mocks.api.mockImplementation(stub([linha({ proximo_degrau: "firm", proximo_degrau_display: "Um rótulo que só o backend conhece" })]));
  render(<CobrancaPage />);
  expect(await screen.findByText(/Um rótulo que só o backend conhece/)).toBeInTheDocument();
});

test("o vencimento não volta um dia: a data pura é lida ao meio-dia", async () => {
  render(<CobrancaPage />);
  expect(await screen.findByText("Vence 05/08/2026")).toBeInTheDocument();
});

test("régua desligada é estado declarado, não erro — e o Enviar fica desabilitado com o motivo à vista", async () => {
  mocks.api.mockImplementation(stub([linha({ regua_ligada: false })]));
  render(<CobrancaPage />);

  expect(await screen.findByText(/Régua desligada/)).toBeInTheDocument();
  expect(screen.queryByRole("alert")).not.toBeInTheDocument();
  const enviar = screen.getByRole("button", { name: /Enviar cobrança/ });
  expect(enviar).toBeDisabled();
  expect(screen.getByText(/A régua de cobrança está desligada/)).toBeInTheDocument();
});

test("sem linha nenhuma não há aviso de régua desligada nem tabela vazia sem explicação", async () => {
  mocks.api.mockImplementation(stub([]));
  render(<CobrancaPage />);
  expect(await screen.findByText(/Nenhuma fatura cobrável hoje/)).toBeInTheDocument();
  expect(screen.queryByText(/Régua desligada/)).not.toBeInTheDocument();
});

const SILENCIOS: ReadonlyArray<readonly [string, RegExp]> = [
  ["suspensa", /Cobrança suspensa até 30\/09\/2026, sob Marina/],
  ["degrau_gasto", /já foi enviado — ele não se repete/],
  ["teto_de_frequencia", /Teto de frequência/],
  ["sem_degrau", /Nada hoje/],
];

test.each(SILENCIOS)("o silêncio vem traduzido: %s", async (motivo, esperado) => {
  mocks.api.mockImplementation(stub([linha({
    motivo, proximo_degrau: null, proximo_degrau_display: null, proximo_degrau_em: null,
    suspensao: motivo === "suspensa" ? { id: 3, until: "2026-09-30", owner: 2, owner_name: "Marina Alves" } : null,
  })]));
  render(<CobrancaPage />);
  expect(await screen.findByText(esperado)).toBeInTheDocument();
});

test("o teto de frequência não repete o número de dias do servidor", async () => {
  mocks.api.mockImplementation(stub([linha({ motivo: "teto_de_frequencia", proximo_degrau: null, proximo_degrau_display: null })]));
  render(<CobrancaPage />);
  const texto = await screen.findByText(/Teto de frequência/);
  expect(texto.textContent).not.toMatch(/\d+ dias/);
});

test("com a IA desligada o botão de rascunho some da tela — e a régua continua inteira", async () => {
  mocks.getConfig.mockResolvedValue({ ai_enabled: false, calendar_enabled: false, esign_enabled: false, integrations: [] });
  render(<CobrancaPage />);
  await screen.findByRole("button", { name: /Enviar cobrança/ });
  expect(screen.queryByRole("button", { name: /Rascunhar no tom/ })).not.toBeInTheDocument();
});

test("rascunhar pede o degrau que a régua indicou e abre o texto para revisão", async () => {
  mocks.api.mockImplementation((path: string, options?: { method?: string }) => {
    if (path === "/invoices/5/cobranca/rascunhar/") return Promise.resolve({ text: "Olá, tudo bem?", interaction: 42, degrau: "firm" });
    return stub([linha()])(path, options);
  });
  render(<CobrancaPage />);
  await userEvent.click(await screen.findByRole("button", { name: /Rascunhar no tom/ }));

  await waitFor(() => expect(mocks.api).toHaveBeenCalledWith(
    "/invoices/5/cobranca/rascunhar/",
    expect.objectContaining({ method: "POST", body: JSON.stringify({ degrau: "firm" }) }),
  ));
  expect(await screen.findByRole("textbox", { name: "Texto revisado" })).toHaveValue("Olá, tudo bem?");
});

test("nunca envia sem alguém ver o corpo: o botão abre o texto, não a rota", async () => {
  render(<CobrancaPage />);
  await userEvent.click(await screen.findByRole("button", { name: /Enviar cobrança/ }));

  expect(await screen.findByRole("textbox", { name: "Texto revisado" })).toBeInTheDocument();
  expect(mocks.api).not.toHaveBeenCalledWith(
    "/invoices/5/cobranca/enviar/", expect.objectContaining({ method: "POST" }),
  );
});

test("enviar manda degrau, corpo revisado e a interação de IA que produziu o texto", async () => {
  mocks.api.mockImplementation((path: string, options?: { method?: string }) => {
    if (path === "/invoices/5/cobranca/rascunhar/") return Promise.resolve({ text: "Rascunho", interaction: 42, degrau: "firm" });
    return stub([linha()])(path, options);
  });
  render(<CobrancaPage />);
  await userEvent.click(await screen.findByRole("button", { name: /Rascunhar no tom/ }));
  await userEvent.click(await screen.findByRole("button", { name: /Enviar ao cliente/ }));

  await waitFor(() => expect(mocks.api).toHaveBeenCalledWith(
    "/invoices/5/cobranca/enviar/",
    expect.objectContaining({ method: "POST", body: JSON.stringify({ degrau: "firm", subject: "", body: "Rascunho", ai_interaction: 42 }) }),
  ));
});

test("o 503 do envio tem texto próprio: diz que a régua está desligada e onde ligá-la", async () => {
  mocks.api.mockImplementation((path: string, options?: { method?: string }) => {
    if (path === "/invoices/5/cobranca/enviar/") return Promise.reject(falha(503, "A régua de cobrança está desativada."));
    return stub([linha()])(path, options);
  });
  render(<CobrancaPage />);
  await userEvent.click(await screen.findByRole("button", { name: /Enviar cobrança/ }));
  await userEvent.type(await screen.findByRole("textbox", { name: "Texto revisado" }), "Texto");
  await userEvent.click(screen.getByRole("button", { name: /Enviar ao cliente/ }));

  expect(await screen.findByRole("alert")).toHaveTextContent(
    "A régua de cobrança está desativada. Um administrador liga isso na tela de Configurações.",
  );
});

test("o 409 do degrau gasto tem texto próprio e mantém o corpo revisado na tela", async () => {
  mocks.api.mockImplementation((path: string, options?: { method?: string }) => {
    if (path === "/invoices/5/cobranca/enviar/") return Promise.reject(falha(409, "O degrau 'firm' desta fatura já foi enviado."));
    return stub([linha()])(path, options);
  });
  render(<CobrancaPage />);
  await userEvent.click(await screen.findByRole("button", { name: /Enviar cobrança/ }));
  await userEvent.type(await screen.findByRole("textbox", { name: "Texto revisado" }), "Texto");
  await userEvent.click(screen.getByRole("button", { name: /Enviar ao cliente/ }));

  expect(await screen.findByRole("alert")).toHaveTextContent(/já foi enviado.*recarregue para ver o que vale agora/);
  expect(screen.getByRole("textbox", { name: "Texto revisado" })).toHaveValue("Texto");
});

test("suspender exige dono, prazo e motivo, e grava a suspensão da fatura", async () => {
  render(<CobrancaPage />);
  await userEvent.click(await screen.findByRole("button", { name: /Suspender cobrança/ }));

  const prazo = await screen.findByLabelText(/Suspender até/);
  const motivo = screen.getByLabelText("Motivo");
  expect(screen.getByLabelText(/Dono da suspensão/)).toBeRequired();
  expect(prazo).toBeRequired();
  expect(motivo).toBeRequired();

  fireEvent.change(prazo, { target: { value: "2026-09-30" } });
  await userEvent.type(motivo, "Entrega atrasada do nosso lado.");
  await userEvent.click(screen.getByRole("button", { name: "Suspender" }));

  await waitFor(() => expect(mocks.api).toHaveBeenCalledWith(
    "/cobranca/suspensoes/",
    expect.objectContaining({
      method: "POST",
      body: JSON.stringify({ invoice: 5, owner: 7, until: "2026-09-30", reason: "Entrega atrasada do nosso lado." }),
    }),
  ));
});

test("a suspensão pode alcançar o cliente inteiro, e aí manda client — nunca os dois", async () => {
  render(<CobrancaPage />);
  await userEvent.click(await screen.findByRole("button", { name: /Suspender cobrança/ }));

  await userEvent.click(await screen.findByRole("radio", { name: /Este cliente inteiro/ }));
  fireEvent.change(screen.getByLabelText(/Suspender até/), { target: { value: "2026-09-30" } });
  await userEvent.type(screen.getByLabelText("Motivo"), "Insatisfeito com a entrega.");
  await userEvent.click(screen.getByRole("button", { name: "Suspender" }));

  await waitFor(() => expect(mocks.api).toHaveBeenCalledWith(
    "/cobranca/suspensoes/",
    expect.objectContaining({
      method: "POST",
      body: JSON.stringify({ account: 1, owner: 7, until: "2026-09-30", reason: "Insatisfeito com a entrega." }),
    }),
  ));
  const corpo = mocks.api.mock.calls.find(([rota]) => rota === "/cobranca/suspensoes/")?.[1]?.body as string;
  expect(corpo).not.toContain("invoice");
});

test("o alcance nasce na fatura da linha em que se clicou", async () => {
  render(<CobrancaPage />);
  await userEvent.click(await screen.findByRole("button", { name: /Suspender cobrança/ }));
  expect(await screen.findByRole("radio", { name: /Só esta fatura/ })).toBeChecked();
});

test("com suspensão ativa a linha oferece levantar, não suspender de novo", async () => {
  mocks.api.mockImplementation(stub([linha({
    motivo: "suspensa", proximo_degrau: null, proximo_degrau_display: null,
    suspensao: { id: 9, until: "2026-09-30", owner: 2, owner_name: "Marina Alves" },
  })]));
  render(<CobrancaPage />);

  expect(await screen.findByRole("button", { name: /Levantar suspensão/ })).toBeInTheDocument();
  expect(screen.queryByRole("button", { name: /Suspender cobrança/ })).not.toBeInTheDocument();

  await userEvent.click(screen.getByRole("button", { name: /Levantar suspensão/ }));
  await userEvent.click(await screen.findByRole("button", { name: "Levantar" }));
  await waitFor(() => expect(mocks.api).toHaveBeenCalledWith(
    "/cobranca/suspensoes/9/levantar/", expect.objectContaining({ method: "POST" }),
  ));
});

test("o histórico do que já saiu é buscado por fatura, sob demanda", async () => {
  mocks.api.mockImplementation(stub([linha()], {
    historico: [{
      id: 1, invoice: 5, invoice_number: "2026-0007", account: 1, client: 1, client_name: "Imobiliária Aurora",
      dunning_step: "reminder", dunning_step_display: "Lembrete", canal: "email", canal_display: "E-mail ao cliente",
      sent_on: "2026-08-08", subject: "Fatura em aberto", to_email: "financeiro@aurora.test",
      body: "…", sent_by: null, ai_interaction: null, created_at: "2026-08-08T09:00:00Z",
    }],
  }));
  render(<CobrancaPage />);
  expect(mocks.api).not.toHaveBeenCalledWith("/cobranca/?invoice=5");

  await userEvent.click(await screen.findByRole("button", { name: /Histórico de cobrança/ }));
  await waitFor(() => expect(mocks.api).toHaveBeenCalledWith("/cobranca/?invoice=5"));
  expect(await screen.findByText(/Lembrete · E-mail ao cliente/)).toBeInTheDocument();
  expect(screen.getByText(/enviado pela régua/)).toBeInTheDocument();
});

test("Vendas suspende mas não envia nem rascunha — a assimetria da FDD 036 chega à tela", async () => {
  mocks.user = { id: 8, username: "bruno", first_name: "Bruno", last_name: "Lima", role: "sales", is_admin: false };
  mocks.api.mockImplementation(stub([linha()]));
  render(<CobrancaPage />);

  expect(await screen.findByRole("button", { name: /Suspender cobrança/ })).toBeInTheDocument();
  expect(screen.queryByRole("button", { name: /Enviar cobrança/ })).not.toBeInTheDocument();
  expect(screen.queryByRole("button", { name: /Rascunhar no tom/ })).not.toBeInTheDocument();
  expect(mocks.getConfig).not.toHaveBeenCalled();
});

// --- satisfação (FDD 037, ADR 0032) --------------------------------------------------------------

/**
 * A satisfação vigente ao lado de saúde, tempo de casa e reincidência (FDD 037, critério de
 * aceite 4) — a mesma exigência da RFC 0004 de decidir "na mesma tela, não a dois cliques". A
 * fonte vai junto do nível: é o que diz se aquilo é o cliente falando ou a nossa leitura sobre
 * ele, e é a declarada, não a percebida, que troca a régua para `relacao_tensa`.
 */
test("a satisfação vigente aparece no card, com nível, fonte e idade", async () => {
  mocks.api.mockImplementation(stub([linha({
    satisfacao_nivel: "dissatisfied", satisfacao_fonte: "declared", satisfacao_dias: 12,
  })]));
  render(<CobrancaPage />);
  const cartao = (await screen.findByRole("heading", { name: "Imobiliária Aurora" })).closest("article");
  const dentro = within(cartao as HTMLElement);

  expect(dentro.getByText("Insatisfeito")).toBeInTheDocument();
  expect(dentro.getByText(/declarada pelo cliente/)).toBeInTheDocument();
  expect(dentro.getByText(/há 12 dias/)).toBeInTheDocument();
});

test("sem registro de satisfação, o card não inventa texto de ausência", async () => {
  mocks.api.mockImplementation(stub([linha()]));
  render(<CobrancaPage />);
  const cartao = (await screen.findByRole("heading", { name: "Imobiliária Aurora" })).closest("article");
  const dentro = within(cartao as HTMLElement);

  expect(dentro.queryByText("Satisfação")).not.toBeInTheDocument();
});

test("relacao_tensa tem rótulo próprio, que não julga o cliente", async () => {
  mocks.api.mockImplementation(stub([linha({
    regua: "relacao_tensa", tensao_causa: "satisfacao",
    satisfacao_nivel: "dissatisfied", satisfacao_fonte: "declared", satisfacao_dias: 5,
  })]));
  render(<CobrancaPage />);
  expect(await screen.findByText(/relação tensa/)).toBeInTheDocument();
});

// --- a camada 5 fechada: entrega e o sinal por registrar (FDD 038) -------------------------------

/**
 * A escada é a **mesma** nas duas origens da tensão, e é por isso que a causa vai na linha: sem
 * ela a tela diria "relação tensa" e quem lê não saberia se conserta a entrega ou liga para o
 * cliente. O texto é do mapa local; a decisão é do backend.
 */
test("a causa da tensão aparece junto do nome da régua", async () => {
  mocks.api.mockImplementation(stub([linha({
    regua: "relacao_tensa", tensao_causa: "entrega", health_level: "crítico",
  })]));
  render(<CobrancaPage />);

  expect(await screen.findByText(/relação tensa, porque a nossa entrega está em estado crítico/)).toBeInTheDocument();
});

test("sem tensão a linha da régua não ganha causa nenhuma", async () => {
  render(<CobrancaPage />);
  const texto = await screen.findByText(/régua de relação longa/);
  expect(texto.textContent).not.toMatch(/porque/);
});

test("a saúde mostrada é a da entrega do cliente, e sem projeto ativo não se inventa nível", async () => {
  mocks.api.mockImplementation(stub([linha({ health_level: null })]));
  render(<CobrancaPage />);
  expect(await screen.findByText("Sem projeto ativo neste cliente")).toBeInTheDocument();
});

/**
 * A armadilha que a FDD 030 nomeou ao recusar um segundo score: dois sinais parecidos na mesma tela
 * viram dois números discordando sem que ninguém saiba qual olhar. A satisfação vigente é
 * **registro** e move número; o sinal é **leitura de uma resposta** e não move nada — e a tela tem
 * de dizer isso, não só mostrar os dois.
 */
test("o sinal da IA aparece rotulado como leitura por registrar, distinto da satisfação vigente", async () => {
  mocks.api.mockImplementation(stub([linha({
    satisfacao_nivel: "neutral", satisfacao_fonte: "perceived", satisfacao_dias: 30,
    sinal_kind: "dissatisfied", sinal_display: "Insatisfeito", sinal_em: "2026-08-14", sinal_activity: 31,
  })]));
  render(<CobrancaPage />);
  const cartao = (await screen.findByRole("heading", { name: "Imobiliária Aurora" })).closest("article");
  const dentro = within(cartao as HTMLElement);

  expect(dentro.getByText(/Resposta lida pela IA — por registrar/)).toBeInTheDocument();
  expect(dentro.getByText(/não move o Health Score nem a régua/)).toBeInTheDocument();
  expect(dentro.getByText("14/08/2026", { exact: false })).toBeInTheDocument();
  // A satisfação vigente continua no seu lugar, com o rótulo dela — os dois não se confundem.
  expect(dentro.getByText("Neutro")).toBeInTheDocument();
  expect(dentro.getByText(/percebida por quem entrega/)).toBeInTheDocument();
});

test("sem sinal pendente a linha não oferece o atalho", async () => {
  render(<CobrancaPage />);
  await screen.findByRole("heading", { name: "Imobiliária Aurora" });
  expect(screen.queryByRole("button", { name: /Registrar satisfação/ })).not.toBeInTheDocument();
});

test("o atalho registra a satisfação declarada, com a data do que aconteceu e o nível derivado", async () => {
  mocks.api.mockImplementation(stub([linha({
    sinal_kind: "dissatisfied", sinal_display: "Insatisfeito", sinal_em: "2026-08-14", sinal_activity: 31,
  })]));
  render(<CobrancaPage />);
  await userEvent.click(await screen.findByRole("button", { name: /Registrar satisfação/ }));

  // Pré-preenchido, não decidido: o nível vem do sinal e a fonte é declarada porque quem falou foi
  // o cliente. Quem salva é uma pessoa — a IA leu, ela não registrou (ADR 0032).
  expect(await screen.findByLabelText("Nível")).toHaveValue("dissatisfied");
  expect(screen.getByText(/declarada pelo cliente/)).toBeInTheDocument();
  await userEvent.type(screen.getByLabelText("O que o cliente disse"), "Disse que o marco 2 atrasou duas vezes.");
  await userEvent.click(screen.getByRole("button", { name: "Registrar" }));

  await waitFor(() => expect(mocks.api).toHaveBeenCalledWith(
    "/satisfaction-records/",
    expect.objectContaining({
      method: "POST",
      body: JSON.stringify({
        account: 1, source_activity: 31, nivel: "dissatisfied", fonte: "declared",
        happened_on: "2026-08-14", note: "Disse que o marco 2 atrasou duas vezes.",
      }),
    }),
  ));
});

test("o sinal que fala de dinheiro nasce neutro, e não insatisfeito", async () => {
  mocks.api.mockImplementation(stub([linha({
    sinal_kind: "unable_to_pay", sinal_display: "Não pôde pagar", sinal_em: "2026-08-14", sinal_activity: 32,
  })]));
  render(<CobrancaPage />);
  await userEvent.click(await screen.findByRole("button", { name: /Registrar satisfação/ }));

  expect(await screen.findByLabelText("Nível")).toHaveValue("neutral");
});

test("registrado o sinal, a linha é recarregada e o atalho some", async () => {
  const comSinal = linha({ sinal_kind: "dissatisfied", sinal_display: "Insatisfeito", sinal_em: "2026-08-14", sinal_activity: 31 });
  let registrado = false;
  mocks.api.mockImplementation((path: string, options?: { method?: string }) => {
    if (path === "/satisfaction-records/" && options?.method === "POST") { registrado = true; return Promise.resolve({}); }
    return stub([registrado ? linha({ regua: "relacao_tensa", tensao_causa: "satisfacao" }) : comSinal])(path, options);
  });
  render(<CobrancaPage />);
  await userEvent.click(await screen.findByRole("button", { name: /Registrar satisfação/ }));
  await userEvent.type(await screen.findByLabelText("O que o cliente disse"), "Disse que o marco 2 atrasou.");
  await userEvent.click(screen.getByRole("button", { name: "Registrar" }));

  await waitFor(() => expect(screen.queryByRole("button", { name: /Registrar satisfação/ })).not.toBeInTheDocument());
  expect(screen.getByText(/relação tensa/)).toBeInTheDocument();
});
