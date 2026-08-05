import { cleanup, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, expect, test, vi } from "vitest";

import { ArtifactsPanel } from "./ArtifactsPanel";

const mocks = vi.hoisted(() => ({ api: vi.fn() }));
vi.mock("../api", () => ({ api: mocks.api }));

const proposal = (overrides = {}) => ({
  id: 3, kind: "proposal", kind_display: "Proposta", status: "draft", status_display: "Rascunho",
  title: "Proposta — Acme", content: "Escopo e investimento.", opportunity: 1, project: null,
  source_meeting: null, document: null, ai_interaction: 4, created_by: 1, sent_at: null,
  decided_at: null, created_at: "2026-08-05T10:00:00Z", updated_at: "2026-08-05T10:00:00Z",
  ...overrides,
});

beforeEach(() => {
  mocks.api.mockReset();
  mocks.api.mockImplementation((path: string) => {
    if (path.startsWith("/artifacts/?")) return Promise.resolve([proposal()]);
    return Promise.resolve({ id: 9 });
  });
});
afterEach(cleanup);

test("lista os artefatos da oportunidade com estado e conteúdo", async () => {
  render(<ArtifactsPanel opportunity={1} />);

  expect(await screen.findByText("Proposta — Acme")).toBeInTheDocument();
  expect(screen.getByText("Rascunho")).toBeInTheDocument();
  expect(screen.getByLabelText("Conteúdo de Proposta — Acme")).toHaveValue("Escopo e investimento.");
  expect(mocks.api).toHaveBeenCalledWith("/artifacts/?opportunity=1");
});

test("salva o texto revisado pelo humano", async () => {
  const user = userEvent.setup();
  render(<ArtifactsPanel opportunity={1} />);
  await screen.findByText("Proposta — Acme");

  await user.type(screen.getByLabelText("Conteúdo de Proposta — Acme"), " Revisado.");
  await user.click(screen.getByRole("button", { name: /Salvar texto/ }));

  await waitFor(() => expect(mocks.api).toHaveBeenCalledWith("/artifacts/3/", expect.objectContaining({
    method: "PATCH",
    body: JSON.stringify({ content: "Escopo e investimento. Revisado." }),
  })));
});

test("só oferece as transições válidas do estado atual", async () => {
  render(<ArtifactsPanel opportunity={1} />);
  await screen.findByText("Proposta — Acme");

  expect(screen.getByRole("button", { name: "Marcar como em revisão" })).toBeInTheDocument();
  expect(screen.getByRole("button", { name: "Marcar como enviado" })).toBeInTheDocument();
  // Rascunho não pula direto para a decisão do cliente.
  expect(screen.queryByRole("button", { name: "Marcar como aceito" })).not.toBeInTheDocument();
});

test("um artefato decidido não oferece mais transições", async () => {
  mocks.api.mockImplementation((path: string) =>
    path.startsWith("/artifacts/?")
      ? Promise.resolve([proposal({ status: "accepted", status_display: "Aceito" })])
      : Promise.resolve({ id: 9 }));
  render(<ArtifactsPanel opportunity={1} />);
  await screen.findByText("Proposta — Acme");

  expect(screen.queryByRole("button", { name: /Marcar como/ })).not.toBeInTheDocument();
});

test("avança o estado do artefato", async () => {
  const user = userEvent.setup();
  render(<ArtifactsPanel opportunity={1} />);
  await screen.findByText("Proposta — Acme");

  await user.click(screen.getByRole("button", { name: "Marcar como enviado" }));

  await waitFor(() => expect(mocks.api).toHaveBeenCalledWith("/artifacts/3/", expect.objectContaining({
    method: "PATCH",
    body: JSON.stringify({ status: "sent" }),
  })));
});

test("salva como documento e liga o arquivo ao artefato", async () => {
  const user = userEvent.setup();
  const onChange = vi.fn();
  render(<ArtifactsPanel opportunity={1} onChange={onChange} />);
  await screen.findByText("Proposta — Acme");

  await user.click(screen.getByRole("button", { name: "Salvar como documento" }));

  await waitFor(() => expect(mocks.api).toHaveBeenCalledWith("/documents/", expect.objectContaining({ method: "POST" })));
  await waitFor(() => expect(mocks.api).toHaveBeenCalledWith("/artifacts/3/", expect.objectContaining({
    method: "PATCH",
    body: JSON.stringify({ document: 9 }),
  })));
  await waitFor(() => expect(onChange).toHaveBeenCalled());
});

test("não aparece quando não há artefato", async () => {
  mocks.api.mockImplementation(() => Promise.resolve([]));
  const { container } = render(<ArtifactsPanel project={2} />);

  await waitFor(() => expect(mocks.api).toHaveBeenCalledWith("/artifacts/?project=2"));
  expect(container).toBeEmptyDOMElement();
});
