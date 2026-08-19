import { cleanup, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, expect, test, vi } from "vitest";

import { JourneyConfigPage } from "./JourneyConfigPage";

const mocks = vi.hoisted(() => ({ api: vi.fn() }));
vi.mock("../api", () => ({ api: mocks.api }));

beforeEach(() => {
  mocks.api.mockImplementation((path: string, options?: { method?: string }) => {
    if (path === "/journey-phases/" && (options?.method ?? "GET") === "GET") {
      return Promise.resolve([
        { id: 1, name: "Welcome", description: "Recepção", position: 0, active: true, requires_gate: false, deliverables: [{ id: 5, phase: 1, name: "Acesso ao portal", position: 0 }], checklist_items: [{ id: 9, phase: 1, text: "AS-IS validado?", position: 0 }] },
      ]);
    }
    return Promise.resolve({});
  });
});
afterEach(() => { cleanup(); vi.clearAllMocks(); });

test("lista fases e entregáveis e cria uma nova fase", async () => {
  const user = userEvent.setup();
  render(<JourneyConfigPage />);
  expect(await screen.findByDisplayValue("Welcome")).toBeInTheDocument();
  expect(screen.getByText("Acesso ao portal")).toBeInTheDocument();
  await user.type(screen.getByLabelText("Nova fase"), "Activation");
  await user.click(screen.getByRole("button", { name: "Adicionar fase" }));
  await waitFor(() => expect(mocks.api).toHaveBeenCalledWith("/journey-phases/", expect.objectContaining({ method: "POST" })));
});

test("salva a fase e adiciona um entregável", async () => {
  const user = userEvent.setup();
  render(<JourneyConfigPage />);
  await screen.findByDisplayValue("Welcome");
  await user.click(screen.getByRole("button", { name: "Salvar" }));
  await waitFor(() => expect(mocks.api).toHaveBeenCalledWith("/journey-phases/1/", expect.objectContaining({ method: "PATCH" })));

  await user.type(screen.getByLabelText("Novo entregável da fase Welcome"), "Canais definidos");
  await user.click(screen.getByLabelText("Adicionar entregável à fase Welcome"));
  await waitFor(() => expect(mocks.api).toHaveBeenCalledWith("/phase-deliverables/", expect.objectContaining({ method: "POST" })));
});

test("remove um entregável", async () => {
  const user = userEvent.setup();
  render(<JourneyConfigPage />);
  await screen.findByDisplayValue("Welcome");
  await user.click(screen.getByLabelText("Excluir entregável Acesso ao portal"));
  await waitFor(() => expect(mocks.api).toHaveBeenCalledWith("/phase-deliverables/5/", expect.objectContaining({ method: "DELETE" })));
});

test("aposenta a fase sem excluí-la", async () => {
  // A saída que a recusa da exclusão oferece (FDD 011/025): fase em uso não some, para de ser
  // herdada. Sem isto, "Excluir" seria a única alternativa oferecida — e ela é recusada.
  const user = userEvent.setup();
  render(<JourneyConfigPage />);
  await screen.findByDisplayValue("Welcome");

  await user.click(screen.getByLabelText("Herdada por projetos novos"));
  expect(screen.getByText(/não entra em projeto novo/)).toBeInTheDocument();
  await user.click(screen.getByRole("button", { name: "Salvar" }));

  await waitFor(() => expect(mocks.api).toHaveBeenCalledWith("/journey-phases/1/", expect.objectContaining({ body: expect.stringContaining("\"active\":false") })));
});

test("mostra a recusa da exclusão em vez de engolir o erro", async () => {
  // O 409 do backend traz a contagem e o caminho de saída; a tela precisa exibi-lo tal como veio.
  const user = userEvent.setup();
  mocks.api.mockImplementation((path: string, options?: { method?: string }) => {
    if (path === "/journey-phases/1/" && options?.method === "DELETE") {
      return Promise.reject(new Error("Esta fase já foi materializada em 3 projeto(s)."));
    }
    if (path === "/journey-phases/") return Promise.resolve([{ id: 1, name: "Welcome", description: "", position: 0, active: true, requires_gate: false, deliverables: [], checklist_items: [] }]);
    return Promise.resolve({});
  });
  render(<JourneyConfigPage />);
  await screen.findByDisplayValue("Welcome");

  await user.click(screen.getByLabelText("Excluir fase Welcome"));
  await user.click(screen.getByRole("button", { name: "Excluir" }));

  expect(await screen.findByRole("alert")).toHaveTextContent("materializada em 3 projeto(s)");
});

test("marca a fase como decision gate e explica o que isso passa a exigir", async () => {
  // O gate é config do **template** (FDD 033): quem decide que uma fase termina em decisão é a
  // metodologia, não o projeto. Sem o aviso, marcar a caixa não diz o que vai travar depois.
  const user = userEvent.setup();
  render(<JourneyConfigPage />);
  await screen.findByDisplayValue("Welcome");

  await user.click(screen.getByLabelText("Termina em decision gate"));
  expect(screen.getByText(/REDESIGN reabre a fase anterior/)).toBeInTheDocument();
  await user.click(screen.getByRole("button", { name: "Salvar" }));

  await waitFor(() => expect(mocks.api).toHaveBeenCalledWith("/journey-phases/1/", expect.objectContaining({ body: expect.stringContaining("\"requires_gate\":true") })));
});

test("mantém o checklist de qualidade do template", async () => {
  const user = userEvent.setup();
  render(<JourneyConfigPage />);
  await screen.findByDisplayValue("Welcome");
  expect(screen.getByText("AS-IS validado?")).toBeInTheDocument();

  await user.type(screen.getByLabelText("Novo item do checklist da fase Welcome"), "Baseline definido?");
  await user.click(screen.getByLabelText("Adicionar item ao checklist da fase Welcome"));
  await waitFor(() => expect(mocks.api).toHaveBeenCalledWith("/phase-checklist-items/", expect.objectContaining({ method: "POST" })));

  await user.click(screen.getByLabelText("Excluir item AS-IS validado?"));
  await waitFor(() => expect(mocks.api).toHaveBeenCalledWith("/phase-checklist-items/9/", expect.objectContaining({ method: "DELETE" })));
});

test("remove uma fase e edita descrição/ordem", async () => {
  const user = userEvent.setup();
  render(<JourneyConfigPage />);
  await screen.findByDisplayValue("Welcome");
  await user.clear(screen.getByLabelText("Descrição da fase Welcome"));
  await user.type(screen.getByLabelText("Descrição da fase Welcome"), "Onboarding do cliente");
  await user.click(screen.getByLabelText("Excluir fase Welcome"));
  await user.click(screen.getByRole("button", { name: "Excluir" }));
  await waitFor(() => expect(mocks.api).toHaveBeenCalledWith("/journey-phases/1/", expect.objectContaining({ method: "DELETE" })));
});
