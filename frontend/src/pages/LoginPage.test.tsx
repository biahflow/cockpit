import { cleanup, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, expect, test, vi } from "vitest";

import { LoginPage } from "./LoginPage";

const authMocks = vi.hoisted(() => ({ login: vi.fn() }));
vi.mock("../auth", () => ({ useAuth: () => ({ login: authMocks.login }) }));

beforeEach(() => authMocks.login.mockReset());
afterEach(cleanup);

test("envia usuário e senha para autenticação", async () => {
  const user = userEvent.setup();
  authMocks.login.mockResolvedValue(undefined);
  render(<LoginPage />);

  await user.type(screen.getByLabelText("Usuário"), "bia");
  await user.type(screen.getByLabelText("Senha"), "SenhaSegura123!");
  await user.click(screen.getByRole("button", { name: "Entrar no portal" }));

  await waitFor(() => expect(authMocks.login).toHaveBeenCalledWith("bia", "SenhaSegura123!"));
});
