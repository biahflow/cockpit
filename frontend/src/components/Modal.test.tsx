import { cleanup, render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { useState } from "react";
import { afterEach, expect, test, vi } from "vitest";

import { ConfirmDialog, Modal } from "./Modal";

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


// --- diálogo aberto de dentro de outro (FDD 025) ------------------------------------------------
//
// Era o único caso de aninhamento do portal e estava 100% descoberto: a confirmação de "Arquivar"
// abre de dentro do detalhe da oportunidade. Em produção ela aparecia **atrás** do detalhe e o
// `Escape` fechava os dois de uma vez.

function Aninhado({ onFecharExterno, onCancelar }: { onFecharExterno: () => void; onCancelar: () => void }) {
  // Reproduz a sequência real: o detalhe já está aberto e a confirmação chega depois, por clique.
  // A ordem no JSX é a que a CommercialPage usava — a confirmação **antes** do diálogo que a abre —
  // de propósito: o empilhamento tem de seguir a ordem de abertura, senão a correção passa a
  // depender de cada página lembrar de renderizar na sequência certa.
  const [confirmando, setConfirmando] = useState(false);
  return <>
    {confirmando && <ConfirmDialog title="Arquivar oportunidade" message="Sai do pipeline." confirmLabel="Arquivar"
      onConfirm={() => undefined} onCancel={onCancelar} />}
    <Modal title="Detalhe da oportunidade" width="3xl" onClose={onFecharExterno}>
      <button type="button" onClick={() => setConfirmando(true)}>Arquivar</button>
    </Modal>
  </>;
}

async function abrirConfirmacao(onFecharExterno = vi.fn(), onCancelar = vi.fn()) {
  const user = userEvent.setup();
  render(<Aninhado onFecharExterno={onFecharExterno} onCancelar={onCancelar} />);
  await user.click(screen.getByRole("button", { name: "Arquivar" }));
  return { user, onFecharExterno, onCancelar };
}

test("a confirmação pinta na frente do diálogo que a abriu", async () => {
  await abrirConfirmacao();

  const confirmacao = screen.getByRole("dialog", { name: "Arquivar oportunidade" });
  const detalhe = screen.getByRole("dialog", { name: "Detalhe da oportunidade" });

  // Empate de z-index se resolve por ordem de DOM, e no DOM a confirmação vem antes — era assim
  // que ela terminava atrás.
  expect(Number(confirmacao.style.zIndex)).toBeGreaterThan(Number(detalhe.style.zIndex));
});

test("um Escape fecha só a camada de cima", async () => {
  const { user, onFecharExterno, onCancelar } = await abrirConfirmacao();

  await user.keyboard("{Escape}");

  expect(onCancelar).toHaveBeenCalledOnce();
  expect(onFecharExterno).not.toHaveBeenCalled();
});

test("a camada de baixo fica inerte enquanto a de cima está aberta", async () => {
  await abrirConfirmacao();

  // `inert` tira o diálogo de baixo da ordem de foco nativamente e cala o segundo
  // `aria-modal="true"`, que era inválido para leitor de tela.
  expect(screen.getByRole("dialog", { name: "Detalhe da oportunidade" })).toHaveAttribute("inert");
  expect(screen.getByRole("dialog", { name: "Arquivar oportunidade" })).not.toHaveAttribute("inert");
});

test("sozinho, o diálogo continua respondendo ao Escape", async () => {
  const user = userEvent.setup();
  const onFechar = vi.fn();
  render(<Modal title="Detalhe da oportunidade" onClose={onFechar}><button type="button">Salvar</button></Modal>);

  await user.keyboard("{Escape}");

  expect(onFechar).toHaveBeenCalledOnce();
});
