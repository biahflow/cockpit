import { cleanup, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, expect, test, vi } from "vitest";

import { PipelinePage } from "./PipelinePage";

const mocks = vi.hoisted(() => ({ api: vi.fn() }));
vi.mock("../api", () => ({ api: mocks.api }));

beforeEach(() => {
  mocks.api.mockImplementation((path: string, options?: { method?: string }) => {
    if (path === "/pipeline-stages/" && (options?.method ?? "GET") === "GET") {
      return Promise.resolve([{ id: 1, name: "Prospecção", kind: "open", position: 0 }, { id: 2, name: "Ganho", kind: "won", position: 50 }]);
    }
    return Promise.resolve({});
  });
});
afterEach(() => { cleanup(); vi.clearAllMocks(); });

test("lista etapas e cria uma nova", async () => {
  const user = userEvent.setup();
  render(<PipelinePage />);
  expect(await screen.findByDisplayValue("Prospecção")).toBeInTheDocument();
  await user.type(screen.getByLabelText("Nova etapa"), "Proposta");
  await user.click(screen.getByRole("button", { name: "Adicionar etapa" }));
  await waitFor(() => expect(mocks.api).toHaveBeenCalledWith("/pipeline-stages/", expect.objectContaining({ method: "POST" })));
});

test("salva alteração de uma etapa", async () => {
  const user = userEvent.setup();
  render(<PipelinePage />);
  await screen.findByDisplayValue("Prospecção");
  await user.click(screen.getAllByRole("button", { name: "Salvar" })[0]);
  await waitFor(() => expect(mocks.api).toHaveBeenCalledWith("/pipeline-stages/1/", expect.objectContaining({ method: "PATCH" })));
});
