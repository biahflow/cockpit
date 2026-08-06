import { cleanup, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, expect, test, vi } from "vitest";

import { DocumentsPage } from "./DocumentsPage";

const mocks = vi.hoisted(() => ({ api: vi.fn() }));
const authState = vi.hoisted(() => ({ esignEnabled: false, user: { role: "admin", is_admin: true } as { role: string; is_admin?: boolean } }));
vi.mock("../api", () => ({ api: mocks.api, documentDownloadUrl: (id: number) => `/api/v1/documents/${id}/download/` }));
vi.mock("../auth", () => ({ useAuth: () => authState }));

function stub(signatureRequests: object[] = []) {
  mocks.api.mockImplementation((path: string) => {
    if (path === "/documents/") return Promise.resolve([{ id: 1, client: 1, opportunity: null, project: null, file: "x", original_name: "contrato.pdf", uploaded_by: 1, created_at: "2026-08-01", signature_requests: signatureRequests }]);
    if (path === "/clients/") return Promise.resolve([{ id: 1, name: "Cliente A", legal_name: "", tax_id: "", owner: 1 }]);
    return Promise.resolve([]);
  });
}

beforeEach(() => { mocks.api.mockReset(); authState.esignEnabled = false; authState.user = { role: "admin", is_admin: true }; stub(); });
afterEach(cleanup);

test("entrega só pode vincular documento a projeto", async () => {
  authState.user = { role: "delivery" };
  render(<DocumentsPage />);
  await screen.findByText("contrato.pdf");

  const linkType = screen.getAllByRole("combobox")[0];
  expect(Array.from(linkType.querySelectorAll("option")).map(option => option.value)).toEqual(["project"]);
  expect(mocks.api).not.toHaveBeenCalledWith("/opportunities/");
});

test("lista documentos com vínculo e link de download", async () => {
  render(<DocumentsPage />);
  expect(await screen.findByText("contrato.pdf")).toBeInTheDocument();
  expect(screen.getByText("Cliente: Cliente A")).toBeInTheDocument();
  expect(screen.getByRole("link", { name: "Baixar contrato.pdf" })).toHaveAttribute("href", "/api/v1/documents/1/download/");
});

test("envia um documento vinculado a um cliente", async () => {
  const user = userEvent.setup();
  render(<DocumentsPage />);
  await screen.findByText("contrato.pdf");

  await user.selectOptions(screen.getAllByRole("combobox")[1], "1");
  const file = new File(["conteudo"], "proposta.pdf", { type: "application/pdf" });
  await user.upload(screen.getByLabelText("Arquivo"), file);
  await user.click(screen.getByRole("button", { name: "Enviar documento" }));

  await waitFor(() => expect(mocks.api).toHaveBeenCalledWith("/documents/", expect.objectContaining({ method: "POST" })));
  const [, options] = mocks.api.mock.calls.find(([path, opts]) => path === "/documents/" && opts?.method === "POST")!;
  expect(options.body).toBeInstanceOf(FormData);
  expect((options.body as FormData).get("client")).toBe("1");
});

test("arquiva um documento", async () => {
  const user = userEvent.setup();
  render(<DocumentsPage />);
  await screen.findByText("contrato.pdf");

  await user.click(screen.getByLabelText("Arquivar contrato.pdf"));
  await user.click(screen.getByRole("button", { name: "Arquivar" }));
  await waitFor(() => expect(mocks.api).toHaveBeenCalledWith("/documents/1/", expect.objectContaining({ method: "DELETE" })));
});

test("lembra pendentes e marca assinatura como assinada", async () => {
  authState.esignEnabled = true;
  stub([{ id: 7, signer_email: "quem@assina.test", status: "pending", sign_url: "", reminded_at: null, signed_at: null, created_at: "2026-08-01" }]);
  const user = userEvent.setup();
  render(<DocumentsPage />);
  await screen.findByText("contrato.pdf");
  expect(screen.getByText("Pendente")).toBeInTheDocument();

  await user.click(screen.getByLabelText("Lembrar assinantes de contrato.pdf"));
  await waitFor(() => expect(mocks.api).toHaveBeenCalledWith("/documents/1/remind-signature/", expect.objectContaining({ method: "POST" })));

  await user.click(screen.getByRole("button", { name: "Marcar assinado" }));
  await waitFor(() => expect(mocks.api).toHaveBeenCalledWith("/documents/1/mark-signed/", expect.objectContaining({ method: "POST" })));
});

test("mostra o link de assinatura do fornecedor quando há", async () => {
  authState.esignEnabled = true;
  stub([{ id: 7, signer_email: "quem@assina.test", status: "pending", sign_url: "https://assina.ae/abc", reminded_at: null, signed_at: null, created_at: "2026-08-01" }]);
  render(<DocumentsPage />);
  await screen.findByText("contrato.pdf");

  expect(screen.getByRole("link", { name: "Abrir link de assinatura de quem@assina.test" })).toHaveAttribute("href", "https://assina.ae/abc");
});
