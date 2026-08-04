import { cleanup, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, expect, test, vi } from "vitest";

import { AcceptInvitePage } from "./AcceptInvitePage";

const mocks = vi.hoisted(() => ({ acceptInvitation: vi.fn() }));
vi.mock("../api", () => ({ acceptInvitation: mocks.acceptInvitation }));

beforeEach(() => {
  mocks.acceptInvitation.mockResolvedValue({});
  window.history.pushState({}, "", "/aceitar-convite?token=abc-123");
});
afterEach(() => { cleanup(); vi.clearAllMocks(); });

test("pré-preenche o token da URL e ativa o acesso", async () => {
  const user = userEvent.setup();
  render(<AcceptInvitePage />);
  expect(screen.getByDisplayValue("abc-123")).toBeInTheDocument();
  await user.type(screen.getByLabelText("Usuário"), "novo");
  await user.type(screen.getByLabelText("Senha"), "SenhaSegura123!");
  await user.click(screen.getByRole("button", { name: "Ativar acesso" }));
  await waitFor(() => expect(mocks.acceptInvitation).toHaveBeenCalledWith(expect.objectContaining({ token: "abc-123", username: "novo" })));
  expect(await screen.findByText("Acesso ativado")).toBeInTheDocument();
});
