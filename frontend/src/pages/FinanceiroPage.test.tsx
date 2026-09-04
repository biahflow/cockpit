import { cleanup, render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, expect, test, vi } from "vitest";

import { FinanceiroPage } from "./FinanceiroPage";

const mocks = vi.hoisted(() => ({ api: vi.fn(), user: { is_admin: true, role: "admin" } }));
vi.mock("../api", () => ({ api: mocks.api }));
vi.mock("../auth", () => ({ useAuth: () => ({ user: mocks.user }) }));

function fatura(overrides: Record<string, unknown> = {}) {
  return {
    id: 5, account: 1, client: 1, client_name: "Imobiliária Aurora",
    project: 2, project_name: "Implantação", service: 1, service_name: "Implantação",
    number: "2026-0007", amount: "48750.90", description: "Implantação — entrada",
    due_date: "2026-09-10", method: "", method_display: "",
    status: "issued", status_display: "Emitida", is_overdue: false,
    issued_at: "2026-08-01T10:00:00Z", issued_by: 1, paid_at: null, settled_by: null,
    cancelled_at: null, cancelled_by: null, cancel_reason: "",
    provider: "", external_reference: "", payment_url: "",
    created_at: "2026-08-01T09:00:00Z", updated_at: "2026-08-01T09:00:00Z",
    ...overrides,
  };
}

const resumo = {
  open: "48750.90", overdue: "0.00", paid: "0.00",
  open_count: 1, overdue_count: 0, paid_count: 0,
};

function stub(faturas: unknown[], sumario = resumo) {
  return (path: string, options?: { method?: string }) => {
    if ((options?.method ?? "GET") === "GET") {
      if (path.startsWith("/invoices/summary/")) return Promise.resolve(sumario);
      if (path.startsWith("/invoices/")) return Promise.resolve(faturas);
      if (path.startsWith("/clients/")) return Promise.resolve([{ id: 1, name: "Imobiliária Aurora" }]);
    }
    return Promise.resolve({});
  };
}

beforeEach(() => {
  mocks.user = { is_admin: true, role: "admin" };
  mocks.api.mockImplementation(stub([fatura()]));
});
afterEach(() => { cleanup(); vi.clearAllMocks(); });

test("mostra os três totais por faixa", async () => {
  render(<FinanceiroPage />);
  expect(await screen.findByText("Em aberto")).toBeInTheDocument();
  expect(screen.getByText("Vencido")).toBeInTheDocument();
  expect(screen.getByText("Recebido")).toBeInTheDocument();
  expect(screen.getAllByText(/48\.750,90/).length).toBeGreaterThan(0);
});

test("emitir chama a ação e não um PATCH de status", async () => {
  mocks.api.mockImplementation(stub([fatura({ status: "draft", status_display: "Rascunho", number: "" })]));
  render(<FinanceiroPage />);
  await userEvent.click(await screen.findByRole("button", { name: /Emitir/ }));
  await waitFor(() => expect(mocks.api).toHaveBeenCalledWith(
    "/invoices/5/issue/", expect.objectContaining({ method: "POST" }),
  ));
});

test("o botão Emitir fica desabilitado com o motivo à vista, em vez de sumir", async () => {
  mocks.api.mockImplementation(stub([fatura({ status: "draft", status_display: "Rascunho", number: "", amount: "0.00" })]));
  render(<FinanceiroPage />);
  const botao = await screen.findByRole("button", { name: /Emitir/ });
  expect(botao).toBeDisabled();
  expect(screen.getByText("Uma fatura de valor zero não se emite.")).toBeInTheDocument();
});

test("fatura emitida não oferece descartar — só cancelar", async () => {
  render(<FinanceiroPage />);
  expect(await screen.findByRole("button", { name: /Cancelar/ })).toBeInTheDocument();
  expect(screen.queryByRole("button", { name: /Descartar/ })).not.toBeInTheDocument();
});

test("cancelar pede motivo e manda no corpo", async () => {
  render(<FinanceiroPage />);
  await userEvent.click(await screen.findByRole("button", { name: /Cancelar fatura|Cancelar$/ }));
  await userEvent.type(screen.getByLabelText("Motivo do cancelamento"), "Escopo distratado");
  await userEvent.click(screen.getByRole("button", { name: "Cancelar fatura" }));
  await waitFor(() => expect(mocks.api).toHaveBeenCalledWith(
    "/invoices/5/cancel/",
    expect.objectContaining({ method: "POST", body: JSON.stringify({ reason: "Escopo distratado" }) }),
  ));
});

test("vencida aparece com o selo mesmo antes de o job rodar", async () => {
  mocks.api.mockImplementation(stub([fatura({ is_overdue: true })]));
  render(<FinanceiroPage />);
  expect(await screen.findByText("Venceu")).toBeInTheDocument();
});

test("Vendas não vê o formulário nem as ações de escrita", async () => {
  mocks.user = { is_admin: false, role: "sales" };
  render(<FinanceiroPage />);
  expect(await screen.findByText("Em aberto")).toBeInTheDocument();
  expect(screen.queryByRole("button", { name: /Criar rascunho/ })).not.toBeInTheDocument();
  expect(screen.queryByRole("button", { name: /Marcar como paga/ })).not.toBeInTheDocument();
});

test("diz em voz alta que sem gateway a baixa manual é o único caminho", async () => {
  render(<FinanceiroPage />);
  expect(await screen.findByText(/único caminho de baixa/)).toBeInTheDocument();
});

test("o erro 409 da API vai para a tela", async () => {
  mocks.api.mockImplementation((path: string, options?: { method?: string }) => {
    if (options?.method === "POST") return Promise.reject(new Error("A fatura 2026-0007 já foi emitida e não se apaga. Cancele-a, se for o caso."));
    return stub([fatura({ status: "draft", status_display: "Rascunho" })])(path, options);
  });
  render(<FinanceiroPage />);
  await userEvent.click(await screen.findByRole("button", { name: /Emitir/ }));
  expect(await screen.findByRole("alert")).toHaveTextContent(/não se apaga/);
});

test("criar manda o rascunho e avisa que emitir é um passo à parte", async () => {
  render(<FinanceiroPage />);
  await userEvent.selectOptions(await screen.findByLabelText("Conta"), "1");
  await userEvent.type(screen.getByLabelText("Valor (R$)"), "1500");
  await userEvent.type(screen.getByLabelText("Vencimento"), "2026-10-01");
  await userEvent.type(screen.getByLabelText("Descrição"), "Parcela única");
  await userEvent.click(screen.getByRole("button", { name: /Criar rascunho/ }));

  await waitFor(() => expect(mocks.api).toHaveBeenCalledWith(
    "/invoices/",
    expect.objectContaining({
      method: "POST",
      body: JSON.stringify({ account: "1", amount: "1500", due_date: "2026-10-01", description: "Parcela única" }),
    }),
  ));
  expect(await screen.findByRole("status")).toHaveTextContent(/rascunho/i);
});

test("descartar rascunho confirma e manda DELETE", async () => {
  mocks.api.mockImplementation(stub([fatura({ status: "draft", status_display: "Rascunho", number: "" })]));
  render(<FinanceiroPage />);
  await userEvent.click(await screen.findByRole("button", { name: /Descartar/ }));
  // O rótulo se repete na linha e no diálogo; a confirmação é a do diálogo.
  await userEvent.click(within(screen.getByRole("dialog")).getByRole("button", { name: "Descartar" }));
  await waitFor(() => expect(mocks.api).toHaveBeenCalledWith(
    "/invoices/5/", expect.objectContaining({ method: "DELETE" }),
  ));
});

test("marcar como paga chama a ação de baixa", async () => {
  render(<FinanceiroPage />);
  await userEvent.click(await screen.findByRole("button", { name: /Marcar como paga/ }));
  await waitFor(() => expect(mocks.api).toHaveBeenCalledWith(
    "/invoices/5/mark-paid/", expect.objectContaining({ method: "POST" }),
  ));
});

test("o filtro de estado vai como parâmetro para o servidor", async () => {
  render(<FinanceiroPage />);
  await userEvent.selectOptions(await screen.findByLabelText("Estado"), "overdue");
  await waitFor(() => expect(mocks.api).toHaveBeenCalledWith("/invoices/?status=overdue"));
});

test("fatura paga mostra a data e o meio, e nenhuma ação de escrita", async () => {
  mocks.api.mockImplementation(stub([fatura({
    status: "paid", status_display: "Paga", paid_at: "2026-08-05T12:00:00Z",
    method: "pix", method_display: "Pix",
  })]));
  render(<FinanceiroPage />);
  expect(await screen.findByText(/Recebida em .* · Pix/)).toBeInTheDocument();
  expect(screen.queryByRole("button", { name: /Marcar como paga/ })).not.toBeInTheDocument();
});

test("cancelada mostra o motivo registrado", async () => {
  mocks.api.mockImplementation(stub([fatura({
    status: "cancelled", status_display: "Cancelada", cancel_reason: "Escopo distratado",
  })]));
  render(<FinanceiroPage />);
  expect(await screen.findByText(/Cancelada: Escopo distratado/)).toBeInTheDocument();
});

test("com gateway ligado, o link de pagamento aparece", async () => {
  mocks.api.mockImplementation(stub([fatura({ payment_url: "https://pay.example.test/i/7" })]));
  render(<FinanceiroPage />);
  const link = await screen.findByRole("link", { name: /Link de pagamento/ });
  expect(link).toHaveAttribute("href", "https://pay.example.test/i/7");
});

test("sem faturas, explica de onde elas vêm", async () => {
  mocks.api.mockImplementation(stub([], { open: "0.00", overdue: "0.00", paid: "0.00", open_count: 0, overdue_count: 0, paid_count: 0 }));
  render(<FinanceiroPage />);
  expect(await screen.findByText(/nascem em rascunho na conversão/)).toBeInTheDocument();
});

test("falha ao carregar vai para a tela em vez de deixar branco", async () => {
  mocks.api.mockImplementation(() => Promise.reject(new Error("Sessão expirada.")));
  render(<FinanceiroPage />);
  expect(await screen.findByRole("alert")).toHaveTextContent("Sessão expirada.");
});
