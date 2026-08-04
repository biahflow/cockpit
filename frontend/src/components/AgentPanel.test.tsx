import { cleanup, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, expect, test, vi } from "vitest";

import { AgentPanel } from "./AgentPanel";

const mocks = vi.hoisted(() => ({ askAgent: vi.fn(), rateInteraction: vi.fn(), useAuth: vi.fn() }));
vi.mock("../api", () => ({ askAgent: mocks.askAgent, rateInteraction: mocks.rateInteraction }));
vi.mock("../auth", () => ({ useAuth: mocks.useAuth }));

beforeEach(() => {
  mocks.askAgent.mockResolvedValue({ text: "Resposta do agente", interaction: 7 });
  mocks.rateInteraction.mockResolvedValue(undefined);
  mocks.useAuth.mockReturnValue({ aiEnabled: true, user: { role: "sales" } });
});
afterEach(() => { cleanup(); vi.clearAllMocks(); });

test("não renderiza sem IA nem para papel não autorizado", () => {
  mocks.useAuth.mockReturnValue({ aiEnabled: false, user: { role: "sales" } });
  const off = render(<AgentPanel agentKey="comercial" title="Agente Comercial" roles={["sales"]} />);
  expect(off.container).toBeEmptyDOMElement();
  cleanup();
  mocks.useAuth.mockReturnValue({ aiEnabled: true, user: { role: "delivery" } });
  const wrongRole = render(<AgentPanel agentKey="comercial" title="Agente Comercial" roles={["sales"]} />);
  expect(wrongRole.container).toBeEmptyDOMElement();
});

test("admin sempre acessa, mesmo fora dos papéis listados", () => {
  mocks.useAuth.mockReturnValue({ aiEnabled: true, user: { role: "admin" } });
  render(<AgentPanel agentKey="financeiro" title="Agente Financeiro" roles={[]} />);
  expect(screen.getByText("Agente Financeiro")).toBeInTheDocument();
});

test("pergunta ao agente e avalia a resposta com 👍", async () => {
  const user = userEvent.setup();
  render(<AgentPanel agentKey="comercial" title="Agente Comercial" roles={["sales"]} />);
  await user.type(screen.getByLabelText("Pergunta ao Agente Comercial"), "Como está o pipeline?");
  await user.click(screen.getByRole("button", { name: "Perguntar" }));
  expect(await screen.findByText("Resposta do agente")).toBeInTheDocument();
  await waitFor(() => expect(mocks.askAgent).toHaveBeenCalledWith("comercial", "Como está o pipeline?"));
  await user.click(screen.getByLabelText("Resposta útil"));
  await waitFor(() => expect(mocks.rateInteraction).toHaveBeenCalledWith(7, 1));
});
