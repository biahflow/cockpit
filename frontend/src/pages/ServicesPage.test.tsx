import { cleanup, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, expect, test, vi } from "vitest";

import { ServicesPage } from "./ServicesPage";

const mocks = vi.hoisted(() => ({ api: vi.fn() }));
vi.mock("../api", () => ({ api: mocks.api }));

beforeEach(() => {
  mocks.api.mockImplementation((path: string, options?: { method?: string }) => {
    if (path === "/services/" && (options?.method ?? "GET") === "GET") return Promise.resolve([{ id: 1, name: "Consultoria", active: true }]);
    return Promise.resolve({});
  });
});
afterEach(() => { cleanup(); vi.clearAllMocks(); });

test("lista e cria serviços", async () => {
  const user = userEvent.setup();
  render(<ServicesPage />);
  expect(await screen.findByDisplayValue("Consultoria")).toBeInTheDocument();
  await user.type(screen.getByLabelText("Novo serviço"), "Automação");
  await user.click(screen.getByRole("button", { name: "Adicionar serviço" }));
  await waitFor(() => expect(mocks.api).toHaveBeenCalledWith("/services/", expect.objectContaining({ method: "POST" })));
});

test("edita, salva e remove um serviço", async () => {
  const user = userEvent.setup();
  render(<ServicesPage />);
  await screen.findByDisplayValue("Consultoria");
  await user.click(screen.getByRole("checkbox"));
  await user.click(screen.getByRole("button", { name: "Salvar" }));
  await waitFor(() => expect(mocks.api).toHaveBeenCalledWith("/services/1/", expect.objectContaining({ method: "PATCH" })));
  await user.click(screen.getByLabelText("Excluir serviço Consultoria"));
  await waitFor(() => expect(mocks.api).toHaveBeenCalledWith("/services/1/", expect.objectContaining({ method: "DELETE" })));
});
