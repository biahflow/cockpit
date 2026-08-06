import { cleanup, render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, expect, test, vi } from "vitest";

import { ConfirmDialog } from "./Modal";

afterEach(cleanup);

function setup(overrides: Partial<Parameters<typeof ConfirmDialog>[0]> = {}) {
  const onConfirm = vi.fn();
  const onCancel = vi.fn();
  render(<ConfirmDialog
    title="Arquivar cliente"
    message="Some das listagens ativas."
    confirmLabel="Arquivar"
    onConfirm={onConfirm}
    onCancel={onCancel}
    {...overrides}
  />);
  return { onConfirm, onCancel };
}

test("cancelar não dispara a ação destrutiva", async () => {
  const user = userEvent.setup();
  const { onConfirm, onCancel } = setup();

  await user.click(screen.getByRole("button", { name: "Cancelar" }));

  expect(onCancel).toHaveBeenCalledOnce();
  expect(onConfirm).not.toHaveBeenCalled();
});

test("confirmar dispara a ação uma vez", async () => {
  const user = userEvent.setup();
  const { onConfirm } = setup();

  await user.click(screen.getByRole("button", { name: "Arquivar" }));

  expect(onConfirm).toHaveBeenCalledOnce();
});

test("Escape fecha sem confirmar", async () => {
  // Herdado do `Modal` (FDD 022) — e num diálogo destrutivo a tecla de fuga tem de ser a saída
  // segura, nunca a confirmação.
  const user = userEvent.setup();
  const { onConfirm, onCancel } = setup();

  await user.keyboard("{Escape}");

  expect(onCancel).toHaveBeenCalledOnce();
  expect(onConfirm).not.toHaveBeenCalled();
});

test("o foco fica preso dentro do diálogo", async () => {
  const user = userEvent.setup();
  setup();
  const dialog = screen.getByRole("dialog");

  for (let i = 0; i < 6; i++) await user.tab();

  expect(dialog.contains(document.activeElement)).toBe(true);
});

test("enquanto ocupado, o botão de confirmar não aceita segundo clique", async () => {
  const user = userEvent.setup();
  const { onConfirm } = setup({ busy: true });

  await user.click(screen.getByRole("button", { name: "Aguarde…" }));

  expect(onConfirm).not.toHaveBeenCalled();
});
