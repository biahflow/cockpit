import { cleanup, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, expect, test, vi } from "vitest";

import { CommercialPage } from "./CommercialPage";

const mocks = vi.hoisted(() => ({ api: vi.fn() }));
vi.mock("../api", () => ({ api: mocks.api, documentDownloadUrl: (id: number) => `/api/v1/documents/${id}/download/` }));
vi.mock("../auth", () => ({ useAuth: () => ({ user: { id: 1, username: "admin", first_name: "", last_name: "", email: "", role: "admin" }, aiEnabled: true }) }));

const stages = [
  { id: 1, name: "Prospecção", kind: "open", position: 0 },
  { id: 2, name: "Ganho", kind: "won", position: 50 },
];
const opp = { id: 1, client: 1, contact: null, title: "Oport X", scope: "escopo", estimated_value: "15000", stage: 2, stage_name: "Ganho", owner: 1, expected_close_date: "2026-08-31" };

function stub() {
  mocks.api.mockImplementation((path: string, options?: { method?: string }) => {
    const method = options?.method?.toUpperCase() ?? "GET";
    if (path === "/pipeline-stages/") return Promise.resolve(stages);
    if (path === "/opportunities/" && method === "GET") return Promise.resolve([opp]);
    if (path === "/clients/") return Promise.resolve([{ id: 1, name: "Cliente A", legal_name: "", tax_id: "", owner: 1 }]);
    if (path.startsWith("/contacts")) return Promise.resolve([{ id: 5, client: 1, name: "João", email: "", phone: "", job_title: "" }]);
    if (path.startsWith("/documents/?opportunity")) return Promise.resolve([{ id: 9, client: null, opportunity: 1, project: null, file: "x", original_name: "proposta.pdf", uploaded_by: 1, created_at: "2026-08-01" }]);
    if (path.includes("/proposal/") || path.includes("/summary/")) return Promise.resolve({ text: "Rascunho gerado pela IA" });
    return Promise.resolve({});
  });
}

beforeEach(() => { mocks.api.mockReset(); stub(); });
afterEach(cleanup);

test("mostra o pipeline e abre o detalhe da oportunidade", async () => {
  const user = userEvent.setup();
  render(<CommercialPage />);
  await user.click(await screen.findByText("Oport X"));
  await screen.findByText("Detalhe da oportunidade");
  expect(await screen.findByRole("option", { name: "João" })).toBeInTheDocument();
  expect(screen.getByText("proposta.pdf")).toBeInTheDocument();
});

test("edita e salva a oportunidade pelo detalhe", async () => {
  const user = userEvent.setup();
  render(<CommercialPage />);
  await user.click(await screen.findByText("Oport X"));
  const title = await screen.findByDisplayValue("Oport X");
  await user.clear(title);
  await user.type(title, "Oport Y");
  await user.click(screen.getByRole("button", { name: "Salvar" }));
  await waitFor(() => expect(mocks.api).toHaveBeenCalledWith("/opportunities/1/", expect.objectContaining({ method: "PATCH" })));
});

test("envia documento vinculado à oportunidade", async () => {
  const user = userEvent.setup();
  render(<CommercialPage />);
  await user.click(await screen.findByText("Oport X"));
  await screen.findByText("Detalhe da oportunidade");
  const file = new File(["x"], "novo.pdf", { type: "application/pdf" });
  await user.upload(screen.getByLabelText("Arquivo da oportunidade"), file);
  await user.click(screen.getByRole("button", { name: "Enviar documento" }));
  await waitFor(() => expect(mocks.api).toHaveBeenCalledWith("/documents/", expect.objectContaining({ method: "POST" })));
});

test("converte a oportunidade ganha em projeto pelo detalhe", async () => {
  const user = userEvent.setup();
  render(<CommercialPage />);
  await user.click(await screen.findByText("Oport X"));
  await user.click(await screen.findByRole("button", { name: /Converter em projeto/ }));
  const dialog = await screen.findByRole("dialog", { name: "Criar projeto" });
  const dates = dialog.querySelectorAll('input[type="date"]');
  fireEvent.change(dates[0], { target: { value: "2026-08-01" } });
  fireEvent.change(dates[1], { target: { value: "2026-09-01" } });
  await user.click(within(dialog).getByRole("button", { name: "Criar projeto" }));
  await waitFor(() => expect(mocks.api).toHaveBeenCalledWith("/opportunities/1/convert-to-project/", expect.objectContaining({ method: "POST" })));
});

test("gera proposta com IA e salva como documento", async () => {
  const user = userEvent.setup();
  render(<CommercialPage />);
  await user.click(await screen.findByText("Oport X"));
  await user.click(await screen.findByRole("button", { name: "Gerar proposta" }));
  const draft = await screen.findByLabelText("Rascunho gerado pela IA");
  expect(draft).toHaveValue("Rascunho gerado pela IA");
  await user.click(screen.getByRole("button", { name: "Salvar como documento" }));
  await waitFor(() => expect(mocks.api).toHaveBeenCalledWith("/documents/", expect.objectContaining({ method: "POST" })));
});

test("cria uma nova oportunidade pelo compositor", async () => {
  const user = userEvent.setup();
  render(<CommercialPage />);
  await screen.findByText("Oport X");
  await user.click(screen.getByRole("button", { name: "Nova oportunidade" }));
  const dialog = await screen.findByRole("dialog", { name: "Nova oportunidade" });
  await user.type(within(dialog).getByLabelText("Título"), "Nova Op");
  await user.selectOptions(within(dialog).getByRole("combobox"), "1");
  await user.type(within(dialog).getByLabelText("Valor estimado"), "5000");
  fireEvent.change(within(dialog).getByLabelText("Previsão de fechamento"), { target: { value: "2026-10-01" } });
  await user.click(within(dialog).getByRole("button", { name: "Adicionar ao pipeline" }));
  await waitFor(() => expect(mocks.api).toHaveBeenCalledWith("/opportunities/", expect.objectContaining({ method: "POST" })));
});
