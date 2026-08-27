/**
 * Os oito estados do painel Engenharia (DAP GH-41 r1, FDD 041).
 *
 * O que estes testes existem para travar é a **regra do obsoleto**: quando o backend diz
 * `is_stale`, nenhum selo pode continuar vestindo a cor do estado observado. Um selo verde que na
 * verdade é de anteontem passa em qualquer teste que só olhe texto — daí as asserções olharem a
 * `className` da pastilha, que é onde a afirmação de confiança de fato mora.
 */

import { cleanup, render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, expect, test, vi } from "vitest";

import { EngineeringPanel } from "./EngineeringPanel";

const mocks = vi.hoisted(() => ({ api: vi.fn() }));
vi.mock("../api", () => ({ api: mocks.api }));

const projecao = (overrides: Record<string, unknown> = {}) => ({
  id: 1, handoff: 7, project: 1,
  repository: "biahflow/pulse", issue_number: 41,
  issue_url: "https://github.com/biahflow/pulse/issues/41",
  reference: "biahflow/pulse#41",
  issue_state: "open", issue_title: "Projetar estado de entrega do GitHub no Pulse",
  pr_number: 90, pr_state: "open",
  head_sha: "a1b2c3d4e5f60718293a4b5c6d7e8f9012345678", ci_state: "success",
  observed_at: "2026-08-27T12:00:00Z", observed_via: "webhook",
  age_seconds: 120, is_stale: false,
  last_error_kind: "", last_error_at: null, last_error_age_seconds: null,
  source_updated_at: "2026-08-27T11:59:00Z",
  created_at: "2026-08-27T10:00:00Z", updated_at: "2026-08-27T12:00:00Z",
  ...overrides,
});

/** A classe da pastilha que contém aquele texto — é ela que carrega a cor. */
function variante(texto: string): string {
  return screen.getByText(texto).className;
}

function responde(lista: unknown[]) {
  mocks.api.mockImplementation(() => Promise.resolve(lista));
}

beforeEach(() => { mocks.api.mockReset(); responde([projecao()]); });
afterEach(cleanup);

test("1 · sincronizado: cada selo carrega a cor do estado real, com proveniência", async () => {
  render(<EngineeringPanel project={1} />);

  expect(await screen.findByText("biahflow/pulse#41")).toHaveAttribute(
    "href", "https://github.com/biahflow/pulse/issues/41",
  );
  expect(screen.getByText("Projetar estado de entrega do GitHub no Pulse")).toBeInTheDocument();
  expect(variante("Issue aberta")).toContain("state--0");
  expect(variante("PR aberto")).toContain("state--0");
  expect(variante("CI verde")).toContain("state--1");
  // Sete caracteres, que é como o GitHub abrevia o SHA.
  expect(screen.getByText("a1b2c3d")).toBeInTheDocument();
  expect(screen.getByText("Observado há 2 min · webhook")).toBeInTheDocument();
  expect(mocks.api).toHaveBeenCalledWith("/github-projections/?project=1");
});

test("2 · obsoleto: todo selo cai ao neutro e a proveniência sobe ao âmbar", async () => {
  responde([projecao({ is_stale: true, age_seconds: 10800, observed_via: "reconciliation" })]);
  render(<EngineeringPanel project={1} />);

  await screen.findByText("biahflow/pulse#41");
  // Mesmo texto, outra afirmação: some só a confiança que a cor emprestava.
  for (const selo of ["Issue aberta", "PR aberto", "CI verde"]) {
    expect(variante(selo), `${selo} continuou colorido em estado obsoleto`).toContain("state--off");
  }
  // O âmbar **troca de lugar**: sai dos selos e vai para a proveniência.
  expect(variante("Observado há 3 h · reconciliação")).toContain("state--2");
  expect(screen.getByText(/último estado conhecido/)).toBeInTheDocument();
});

test("3 · GitHub indisponível: alerta sem pedir ação e último estado neutralizado", async () => {
  responde([projecao({
    last_error_kind: "unavailable", last_error_at: "2026-08-27T12:25:00Z",
    last_error_age_seconds: 60, age_seconds: 1560,
  })]);
  render(<EngineeringPanel project={1} />);

  expect(await screen.findByRole("alert")).toHaveTextContent(
    "Não foi possível falar com o GitHub. O estado abaixo é o último conhecido.",
  );
  expect(variante("CI verde")).toContain("state--off");
  expect(screen.getByText(/última tentativa de contato há 1 min/)).toBeInTheDocument();
});

test("4 · permissão negada: nomeia o repositório e nunca ecoa credencial", async () => {
  responde([projecao({
    last_error_kind: "forbidden", last_error_at: "2026-08-27T08:00:00Z",
    last_error_age_seconds: 14400, age_seconds: 14400, is_stale: true,
  })]);
  render(<EngineeringPanel project={1} />);

  const alerta = await screen.findByRole("alert");
  expect(alerta).toHaveTextContent("A credencial do Pulse não alcança biahflow/pulse.");
  expect(alerta).toHaveTextContent("Revise o token e o escopo da integração em Configurações.");
  expect(alerta.textContent).not.toMatch(/ghp_|token=|Bearer/);
  expect(screen.getByText(/sem acesso desde então/)).toBeInTheDocument();
});

test("5 · referência ausente: o único erro que ganha selo vermelho", async () => {
  responde([projecao({
    last_error_kind: "missing", last_error_at: "2026-08-27T12:00:00Z",
    last_error_age_seconds: 480, pr_state: "none", head_sha: "", ci_state: "none",
  })]);
  render(<EngineeringPanel project={1} />);

  expect(await screen.findByRole("alert")).toHaveTextContent(
    "A referência biahflow/pulse#41 não existe mais no GitHub.",
  );
  // O defeito está na própria referência, e vermelho é a leitura certa.
  expect(variante("Não encontrada (404)")).toContain("state--3");
  // Os outros caem ao neutro: não há o que saber sobre eles.
  expect(variante("Sem PR")).toContain("state--off");
  expect(variante("Sem check")).toContain("state--off");
  expect(screen.getByText("—")).toBeInTheDocument();
});

test("6 · vazio: ausência não é falha, e o painel continua na tela", async () => {
  responde([]);
  render(<EngineeringPanel project={1} />);

  expect(await screen.findByText("Nenhuma referência de GitHub neste projeto.")).toBeInTheDocument();
  expect(screen.getByRole("heading", { name: "Engenharia" })).toBeInTheDocument();
  expect(screen.queryByRole("alert")).not.toBeInTheDocument();
});

test("7 · carregando: nenhum selo colorido enquanto não se sabe", () => {
  mocks.api.mockImplementation(() => new Promise(() => {}));
  const { container } = render(<EngineeringPanel project={1} />);

  // Um selo cinza aqui seria indistinguível do estado obsoleto — por isso não há selo nenhum.
  expect(container.querySelector("[aria-busy='true']")).not.toBeNull();
  expect(container.querySelector(".state")).toBeNull();
});

test("8 · sem autorização: a copy é invariante e não vaza o que existe do outro lado", async () => {
  mocks.api.mockImplementation(() => Promise.reject(
    Object.assign(new Error("Você não tem permissão para executar essa ação."), { status: 403 }),
  ));
  render(<EngineeringPanel project={1} />);

  expect(await screen.findByText("Estado de engenharia não faz parte do seu acesso.")).toBeInTheDocument();
  expect(screen.queryByRole("alert")).not.toBeInTheDocument();
  expect(screen.getByRole("heading", { name: "Engenharia" })).toBeInTheDocument();
});

test("o reservado é ausente: nenhum controle de comando é renderizado", async () => {
  render(<EngineeringPanel project={1} />);

  await screen.findByText("biahflow/pulse#41");
  // Controle inerte no produto é defeito, não marcador de lugar (DAP GH-41 r1).
  expect(screen.queryAllByRole("button")).toEqual([]);
  for (const rotulo of [/Re-disparar CI/, /Reabrir Issue/, /Reprovisionar/]) {
    expect(screen.queryByText(rotulo)).not.toBeInTheDocument();
  }
});

test("PR fechado sem merge é âmbar, e merged é verde que não diz DONE", async () => {
  responde([projecao({ id: 1, pr_state: "closed" }), projecao({ id: 2, pr_state: "merged" })]);
  render(<EngineeringPanel project={1} />);

  await waitFor(() => expect(screen.getAllByText("biahflow/pulse#41")).toHaveLength(2));
  expect(variante("PR fechado sem merge")).toContain("state--2");
  expect(variante("PR merged")).toContain("state--1");
  expect(screen.queryByText(/conclu/i)).not.toBeInTheDocument();
});

test("duas referências com a mesma causa dizem a mesma coisa uma vez só", async () => {
  responde([
    projecao({ id: 1, last_error_kind: "unavailable", last_error_age_seconds: 60 }),
    projecao({ id: 2, last_error_kind: "unavailable", last_error_age_seconds: 60 }),
  ]);
  render(<EngineeringPanel project={1} />);

  await waitFor(() => expect(screen.getAllByText("biahflow/pulse#41")).toHaveLength(2));
  expect(screen.getAllByRole("alert")).toHaveLength(1);
});

test("uma falha de carregamento aparece como alerta, não como estado inventado", async () => {
  mocks.api.mockImplementation(() => Promise.reject(
    Object.assign(new Error("Falha de rede."), { status: 500 }),
  ));
  render(<EngineeringPanel project={1} />);

  expect(await screen.findByRole("alert")).toHaveTextContent("Falha de rede.");
  expect(screen.queryByText(/CI verde/)).not.toBeInTheDocument();
});
