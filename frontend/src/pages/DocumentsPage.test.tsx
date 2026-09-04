import { cleanup, render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, expect, test, vi } from "vitest";

import { DocumentsPage } from "./DocumentsPage";

const mocks = vi.hoisted(() => ({ api: vi.fn() }));
const authState = vi.hoisted(() => ({ esignEnabled: false, esignHouseSignerEmail: null as string | null, user: { role: "admin", is_admin: true } as { role: string; is_admin?: boolean } }));
vi.mock("../api", () => ({ api: mocks.api, documentDownloadUrl: (id: number) => `/api/v1/documents/${id}/download/` }));
vi.mock("../auth", () => ({ useAuth: () => authState }));

const CONTATOS = [
  { id: 10, account: 1, client: 1, first_name: "Fulano", last_name: "de Tal", name: "Fulano de Tal", email: "fulano@homecare.com.br", phone: "", job_title: "", receives_billing: false },
  { id: 11, account: 1, client: 1, first_name: "Beltrana", last_name: "Souza", name: "Beltrana Souza", email: "beltrana@homecare.com.br", phone: "", job_title: "", receives_billing: false },
  { id: 12, account: 1, client: 1, first_name: "Ciclana", last_name: "Dias", name: "Ciclana Dias", email: "ciclana@homecare.com.br", phone: "", job_title: "", receives_billing: false },
];

function stub(signatureRequests: object[] = [], documento: object = {}) {
  mocks.api.mockImplementation((path: string) => {
    if (path === "/documents/") return Promise.resolve([{ id: 1, account: 1, client: 1, commercial_opportunity: null, opportunity: null, project: null, file: "x", kind: "", original_name: "contrato.pdf", uploaded_by: 1, created_at: "2026-08-01", originated_engagement: null, owning_account: 1, signature_positioning_gap: null, ...documento, signature_requests: signatureRequests }]);
    if (path === "/clients/") return Promise.resolve([{ id: 1, name: "Cliente A", legal_name: "", tax_id: "", owner: 1 }]);
    if (path.startsWith("/contacts/")) return Promise.resolve(CONTATOS);
    return Promise.resolve([]);
  });
}

/** Abre o modal de assinatura do único documento do stub. */
async function abrirRodada(user: ReturnType<typeof userEvent.setup>) {
  authState.esignEnabled = true;
  render(<DocumentsPage />);
  await screen.findByText("contrato.pdf");
  await user.click(screen.getByLabelText("Enviar contrato.pdf para assinatura"));
  return screen.getByRole("dialog", { name: "Enviar para assinatura" });
}

beforeEach(() => { mocks.api.mockReset(); authState.esignEnabled = false; authState.esignHouseSignerEmail = "daniel@biahflow.ai"; authState.user = { role: "admin", is_admin: true }; stub(); });
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
  expect((options.body as FormData).get("account")).toBe("1");
});

test("marca o documento como acordo de parceria e manda o kind", async () => {
  const user = userEvent.setup();
  render(<DocumentsPage />);
  await screen.findByText("contrato.pdf");

  await user.selectOptions(screen.getAllByRole("combobox")[1], "1");
  await user.selectOptions(screen.getByLabelText("Finalidade"), "design_partner_agreement");
  await user.upload(screen.getByLabelText("Arquivo"), new File(["x"], "acordo.pdf", { type: "application/pdf" }));
  await user.click(screen.getByRole("button", { name: "Enviar documento" }));

  await waitFor(() => expect(mocks.api).toHaveBeenCalledWith("/documents/", expect.objectContaining({ method: "POST" })));
  const [, options] = mocks.api.mock.calls.find(([path, opts]) => path === "/documents/" && opts?.method === "POST")!;
  expect((options.body as FormData).get("kind")).toBe("design_partner_agreement");
});

test("a finalidade classifica em qualquer vínculo, e só as que abrem mandato exigem conta", async () => {
  // Decisão **A1-r2** do DAP r2, que revê a A1. O que exigia conta nunca foi o campo — era abrir
  // mandato. Um NDA e um contrato comercial vivem numa oportunidade ou num projeto, e escondê-los
  // ali era o defeito que a revisão corrige.
  const user = userEvent.setup();
  render(<DocumentsPage />);
  await screen.findByText("contrato.pdf");

  await user.selectOptions(screen.getAllByRole("combobox")[0], "project");
  const finalidade = screen.getByLabelText("Finalidade");
  expect(within(finalidade).getByRole("option", { name: "NDA" })).toBeInTheDocument();
  expect(within(finalidade).queryByRole("option", { name: "Design Partner Agreement" })).not.toBeInTheDocument();

  await user.selectOptions(screen.getAllByRole("combobox")[0], "account");
  expect(within(screen.getByLabelText("Finalidade")).getByRole("option", { name: "Design Partner Agreement" })).toBeInTheDocument();
});

test("trocar o vínculo limpa só a finalidade que deixou de ser oferecida", async () => {
  // Apagar sempre perderia o que a pessoa disse: sair de Oportunidade para Projeto não tem por que
  // esquecer um "NDA", que continua válido nos dois.
  const user = userEvent.setup();
  render(<DocumentsPage />);
  await screen.findByText("contrato.pdf");

  await user.selectOptions(screen.getByLabelText("Finalidade"), "design_partner_agreement");
  await user.selectOptions(screen.getAllByRole("combobox")[0], "project");
  expect(screen.getByLabelText("Finalidade")).toHaveValue("");

  await user.selectOptions(screen.getByLabelText("Finalidade"), "nda");
  await user.selectOptions(screen.getAllByRole("combobox")[0], "commercial_opportunity");
  expect(screen.getByLabelText("Finalidade")).toHaveValue("nda");
});

test("a finalidade aparece na listagem, e o documento comum não ganha pastilha", async () => {
  // Decisão **B1**: sem isto, classificar não resolve o que motivou a revisão — achar o NDA depois.
  mocks.api.mockImplementation((path: string) => {
    if (path === "/documents/") return Promise.resolve([
      { id: 1, kind: "nda", account: 1, client: 1, commercial_opportunity: null, opportunity: null, project: null, file: "x", original_name: "nda.pdf", uploaded_by: 1, created_at: "2026-08-01", originated_engagement: null, owning_account: 1, signature_positioning_gap: null, signature_requests: [] },
      { id: 2, kind: "", account: 1, client: 1, commercial_opportunity: null, opportunity: null, project: null, file: "x", original_name: "ata.pdf", uploaded_by: 1, created_at: "2026-08-01", originated_engagement: null, owning_account: 1, signature_positioning_gap: null, signature_requests: [] },
    ]);
    if (path === "/clients/") return Promise.resolve([{ id: 1, name: "Cliente A", legal_name: "", tax_id: "", owner: 1 }]);
    return Promise.resolve([]);
  });
  render(<DocumentsPage />);
  await screen.findByText("nda.pdf");

  // Escopado na linha: "NDA" também é o rótulo de uma opção do select do formulário, e um
  // `getByText` solto acharia as duas — passaria mesmo se a pastilha não existisse.
  const linhaDoNda = screen.getByText("nda.pdf").parentElement!;
  expect(within(linhaDoNda).getByText("NDA")).toBeInTheDocument();

  const linhaComum = screen.getByText("ata.pdf").parentElement!;
  expect(linhaComum.querySelector(".state--off")).toBeNull();
});

test("documento comum não manda kind nenhum", async () => {
  const user = userEvent.setup();
  render(<DocumentsPage />);
  await screen.findByText("contrato.pdf");

  await user.selectOptions(screen.getAllByRole("combobox")[1], "1");
  await user.upload(screen.getByLabelText("Arquivo"), new File(["x"], "nota.pdf", { type: "application/pdf" }));
  await user.click(screen.getByRole("button", { name: "Enviar documento" }));

  await waitFor(() => expect(mocks.api).toHaveBeenCalledWith("/documents/", expect.objectContaining({ method: "POST" })));
  const [, options] = mocks.api.mock.calls.find(([path, opts]) => path === "/documents/" && opts?.method === "POST")!;
  expect((options.body as FormData).has("kind")).toBe(false);
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
  stub([{ id: 7, signer_email: "quem@assina.test", signer_role: "counterparty", status: "pending", sign_url: "", reminded_at: null, signed_at: null, created_at: "2026-08-01" }]);
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
  stub([{ id: 7, signer_email: "quem@assina.test", signer_role: "counterparty", status: "pending", sign_url: "https://assina.ae/abc", reminded_at: null, signed_at: null, created_at: "2026-08-01" }]);
  render(<DocumentsPage />);
  await screen.findByText("contrato.pdf");

  expect(screen.getByRole("link", { name: "Abrir link de assinatura de quem@assina.test" })).toHaveAttribute("href", "https://assina.ae/abc");
});


test("lista e restaura documentos arquivados", async () => {
  const user = userEvent.setup();
  mocks.api.mockImplementation((path: string) => {
    if (path === "/documents/?archived=1") return Promise.resolve([{ id: 2, account: 1, client: 1, commercial_opportunity: null, opportunity: null, project: null, file: "x", original_name: "antigo.pdf", uploaded_by: 1, created_at: "2026-08-01", originated_engagement: null, owning_account: 1, signature_positioning_gap: null, signature_requests: [] }]);
    if (path === "/documents/") return Promise.resolve([]);
    if (path === "/clients/") return Promise.resolve([{ id: 1, name: "Cliente A", legal_name: "", tax_id: "", owner: 1 }]);
    return Promise.resolve([]);
  });
  render(<DocumentsPage />);

  await user.click(await screen.findByRole("button", { name: "Arquivados" }));
  expect(await screen.findByText("antigo.pdf")).toBeInTheDocument();

  await user.click(screen.getByRole("button", { name: /Restaurar/ }));
  await waitFor(() => expect(mocks.api).toHaveBeenCalledWith("/documents/2/unarchive/", expect.objectContaining({ method: "POST" })));
});


// --- a rodada de assinatura (DAP `dap-assinatura-com-papeis-r1`, issue #120) ---

test("o botão de assinatura abre o modal com a linha fixa da casa", async () => {
  // Decisão **D1**: quem envia precisa saber quantas assinaturas o documento vai esperar, porque
  // desde a ADR 0065 aceitar exige todos.
  const user = userEvent.setup();
  const dialog = await abrirRodada(user);

  expect(within(dialog).getByText("Você (Biahflow)")).toBeInTheDocument();
  expect(within(dialog).getByText("daniel@biahflow.ai · assina como a casa")).toBeInTheDocument();
  expect(within(dialog).getByText("Fixo")).toBeInTheDocument();
  // A casa é fixa: não há como removê-la da rodada pela tela.
  expect(within(dialog).queryByLabelText(/^Remover /)).toBeNull();
});

test("sem e-mail da casa configurado a linha some inteira", async () => {
  authState.esignHouseSignerEmail = null;
  const user = userEvent.setup();
  const dialog = await abrirRodada(user);

  expect(within(dialog).queryByText("Você (Biahflow)")).toBeNull();
  expect(within(dialog).getByText(/Nenhum signatário do cliente ainda/)).toBeInTheDocument();
});

test("o modal busca os contatos da conta-dona, e não busca quando não há", async () => {
  // Decisão **B1**: a conta-dona vem derivada do servidor; a tela nunca reexpressa a cadeia.
  const user = userEvent.setup();
  await abrirRodada(user);
  expect(mocks.api).toHaveBeenCalledWith("/contacts/?account=1");

  cleanup();
  mocks.api.mockReset();
  stub([], { owning_account: null });
  await abrirRodada(user);
  expect(mocks.api.mock.calls.filter(([path]) => String(path).startsWith("/contacts/"))).toEqual([]);
});

test("escolher um contato monta a linha e o botão conta a casa junto", async () => {
  const user = userEvent.setup();
  const dialog = await abrirRodada(user);

  expect(within(dialog).getByRole("button", { name: "Enviar" })).toBeDisabled();

  await user.selectOptions(within(dialog).getByLabelText("Contato da conta"), "10");

  expect(within(dialog).getByText("Fulano de Tal")).toBeInTheDocument();
  expect(within(dialog).getByRole("button", { name: "Enviar para 2 signatários" })).toBeEnabled();
});

test("a ordem das testemunhas é dado: linha 1, linha 2, e a terceira sem posição", async () => {
  const user = userEvent.setup();
  const dialog = await abrirRodada(user);
  for (const id of ["10", "11", "12"]) {
    await user.selectOptions(within(dialog).getByLabelText("Contato da conta"), id);
  }

  await user.selectOptions(within(dialog).getByLabelText("Papel de fulano@homecare.com.br"), "witness");
  expect(within(dialog).getByText(/Ocupa a/).textContent).toBe("Ocupa a linha 1 de testemunha do documento");

  await user.selectOptions(within(dialog).getByLabelText("Papel de beltrana@homecare.com.br"), "witness");
  expect(within(dialog).getAllByText(/Ocupa a/).map(node => node.textContent)).toEqual([
    "Ocupa a linha 1 de testemunha do documento",
    "Ocupa a linha 2 de testemunha do documento",
  ]);

  await user.selectOptions(within(dialog).getByLabelText("Papel de ciclana@homecare.com.br"), "witness");
  expect(within(dialog).getByText("Sem linha de testemunha no documento — a assinatura vai sem posição")).toBeInTheDocument();
});

test("o envio manda a rodada na ordem da lista, e a casa não vai no corpo", async () => {
  const user = userEvent.setup();
  const dialog = await abrirRodada(user);
  await user.selectOptions(within(dialog).getByLabelText("Contato da conta"), "10");
  await user.selectOptions(within(dialog).getByLabelText("Contato da conta"), "11");
  await user.selectOptions(within(dialog).getByLabelText("Papel de beltrana@homecare.com.br"), "witness");

  await user.click(within(dialog).getByRole("button", { name: "Enviar para 3 signatários" }));

  await waitFor(() => expect(mocks.api).toHaveBeenCalledWith("/documents/1/request-signature/", expect.objectContaining({ method: "POST" })));
  const [, options] = mocks.api.mock.calls.find(([path]) => path === "/documents/1/request-signature/")!;
  expect(JSON.parse(options.body as string)).toEqual({
    signers: [
      { email: "fulano@homecare.com.br", role: "counterparty" },
      { email: "beltrana@homecare.com.br", role: "witness" },
    ],
  });
  await waitFor(() => expect(screen.queryByRole("dialog", { name: "Enviar para assinatura" })).toBeNull());
  // Recarrega: as solicitações novas precisam aparecer na lista embaixo do documento.
  expect(mocks.api.mock.calls.filter(([path]) => path === "/documents/").length).toBeGreaterThan(1);
});

test("o aviso de posicionamento diz o fato, e some quando não há lacuna", async () => {
  // Decisão **E1**: o caso silencioso é 201, o cliente assina, e a assinatura vai para a página
  // anexa. Foi o defeito que abriu a #115.
  const user = userEvent.setup();
  stub([], { signature_positioning_gap: "not_pdf" });
  let dialog = await abrirRodada(user);
  expect(within(dialog).getByText("Este documento não é PDF. As assinaturas vão para a última página do relatório, e não sobre as linhas de assinatura.")).toBeInTheDocument();

  cleanup();
  stub([], { signature_positioning_gap: "kind_without_block" });
  dialog = await abrirRodada(user);
  expect(within(dialog).getByText("Documentos desta finalidade não têm bloco de assinatura. As assinaturas vão para a última página do relatório.")).toBeInTheDocument();

  cleanup();
  stub([], { signature_positioning_gap: null });
  dialog = await abrirRodada(user);
  expect(within(dialog).queryByText(/última página do relatório/)).toBeNull();
});

test("e-mail repetido — inclusive o da casa — é recusado com o motivo", async () => {
  const user = userEvent.setup();
  const dialog = await abrirRodada(user);
  const campo = within(dialog).getByLabelText("Ou informe um e-mail");

  await user.type(campo, "fulano@homecare.com.br{Enter}");
  await user.type(campo, "FULANO@homecare.com.br{Enter}");
  expect(within(dialog).getByRole("alert")).toHaveTextContent("Este e-mail já está na rodada.");

  await user.clear(campo);
  await user.type(campo, "daniel@biahflow.ai{Enter}");
  expect(within(dialog).getByRole("alert")).toHaveTextContent("Este e-mail já está na rodada.");
  expect(within(dialog).getByRole("button", { name: "Enviar para 2 signatários" })).toBeInTheDocument();
});

test("a lista de assinaturas diz quem é a casa, quem é parte e quem testemunha", async () => {
  // Decisão **F1**: com três signatários, `daniel@biahflow.ai` ao lado de `fulano@…` não diz
  // qual deles é a casa. Os selos de status não mudam.
  authState.esignEnabled = true;
  stub([
    { id: 7, signer_email: "daniel@biahflow.ai", signer_role: "house", status: "signed", sign_url: "", reminded_at: null, signed_at: "2026-09-01", created_at: "2026-08-01" },
    { id: 8, signer_email: "fulano@homecare.com.br", signer_role: "counterparty", status: "pending", sign_url: "", reminded_at: null, signed_at: null, created_at: "2026-08-01" },
    { id: 9, signer_email: "beltrana@homecare.com.br", signer_role: "witness", status: "pending", sign_url: "", reminded_at: null, signed_at: null, created_at: "2026-08-01" },
  ]);
  render(<DocumentsPage />);
  await screen.findByText("contrato.pdf");

  expect(screen.getByText("Biahflow")).toBeInTheDocument();
  expect(screen.getByText("Parte contratante")).toBeInTheDocument();
  expect(screen.getByText("Testemunha")).toBeInTheDocument();
  expect(screen.getByText("Assinado")).toBeInTheDocument();
  expect(screen.getAllByText("Pendente")).toHaveLength(2);
});
