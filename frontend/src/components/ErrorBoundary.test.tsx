import { render, screen } from "@testing-library/react";
import { afterEach, beforeEach, expect, test, vi } from "vitest";

import { setLastRequestId } from "../observability";
import { ErrorBoundary } from "./ErrorBoundary";

function Explode(): never {
  throw new Error("estourou no render");
}

beforeEach(() => {
  // O React loga o erro capturado no console; aqui ele é ruído esperado.
  vi.spyOn(console, "error").mockImplementation(() => {});
});

afterEach(() => vi.restoreAllMocks());

test("erro de render vira mensagem em vez de tela branca", () => {
  render(<ErrorBoundary><Explode /></ErrorBoundary>);

  expect(screen.getByText("Esta tela não conseguiu carregar")).toBeInTheDocument();
  expect(screen.getByRole("button", { name: /recarregar/i })).toBeInTheDocument();
});

test("marca o cartão com a âncora de que o e2e depende", () => {
  // Sem esta trava, renomear o atributo desligaria em silêncio a guarda que reprova uma tela
  // estourada nos e2e — e a matriz voltaria a medir este cartão achando que mede a tela.
  const { container } = render(<ErrorBoundary><Explode /></ErrorBoundary>);

  expect(container.querySelector("[data-erro-de-render]")).not.toBeNull();
});

test("mostra o código da ocorrência para quem for procurar no log", () => {
  setLastRequestId("req-987");

  render(<ErrorBoundary><Explode /></ErrorBoundary>);

  expect(screen.getByText("req-987")).toBeInTheDocument();
});

test("sem erro, renderiza o conteúdo normalmente", () => {
  const { container } = render(<ErrorBoundary><p>tudo certo</p></ErrorBoundary>);

  expect(screen.getByText("tudo certo")).toBeInTheDocument();
  // A âncora só existe no cartão de erro: se vazasse para o caminho feliz, todo e2e reprovaria.
  expect(container.querySelector("[data-erro-de-render]")).toBeNull();
});
