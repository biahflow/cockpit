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

test("mostra o código da ocorrência para quem for procurar no log", () => {
  setLastRequestId("req-987");

  render(<ErrorBoundary><Explode /></ErrorBoundary>);

  expect(screen.getByText("req-987")).toBeInTheDocument();
});

test("sem erro, renderiza o conteúdo normalmente", () => {
  render(<ErrorBoundary><p>tudo certo</p></ErrorBoundary>);

  expect(screen.getByText("tudo certo")).toBeInTheDocument();
});
