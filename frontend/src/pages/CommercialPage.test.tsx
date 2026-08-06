import { cleanup, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, expect, test, vi } from "vitest";

import { CommercialPage } from "./CommercialPage";

const mocks = vi.hoisted(() => ({ api: vi.fn() }));
vi.mock("../api", () => ({ api: mocks.api, documentDownloadUrl: (id: number) => `/api/v1/documents/${id}/download/` }));
vi.mock("../auth", () => ({ useAuth: () => ({ user: { id: 1, username: "admin", first_name: "", last_name: "", email: "", role: "admin", is_admin: true }, aiEnabled: true }) }));

const stages = [
  { id: 1, name: "Prospecção", kind: "open", position: 0 },
  { id: 2, name: "Ganho", kind: "won", position: 50 },
];
const opp = { id: 1, client: 1, contact: null, title: "Oport X", scope: "escopo", estimated_value: "15000", stage: 2, stage_name: "Ganho", owner: 1, expected_close_date: "2026-08-31", service: 10, service_name: "Discovery Express", service_tier: "discovery_express", project: null as number | null, project_archived: false };
const services = [
  { id: 10, name: "Discovery Express", active: true, tier: "discovery_express", tier_display: "Discovery Express", list_price: "0.00", summary: "Diagnóstico gratuito." },
  { id: 11, name: "Implantação", active: true, tier: "implantacao", tier_display: "Implantação", list_price: "90000.00", summary: "Funcionários digitais." },
];

const proposalArtifact = {
  id: 3, kind: "proposal", kind_display: "Proposta", status: "draft", status_display: "Rascunho",
  title: "Proposta — Oport X", content: "Rascunho gerado pela IA", opportunity: 1, project: null,
  source_meeting: null, document: null, ai_interaction: 4, created_by: 1, sent_at: null,
  decided_at: null, created_at: "2026-08-05T10:00:00Z", updated_at: "2026-08-05T10:00:00Z",
};
let artifacts: unknown[] = [];

function stub() {
  mocks.api.mockImplementation((path: string, options?: { method?: string }) => {
    const method = options?.method?.toUpperCase() ?? "GET";
    if (path === "/pipeline-stages/") return Promise.resolve(stages);
    if (path === "/opportunities/" && method === "GET") return Promise.resolve([opp]);
    if (path === "/services/") return Promise.resolve(services);
    if (path === "/clients/") return Promise.resolve([{ id: 1, name: "Cliente A", legal_name: "", tax_id: "", owner: 1 }]);
    if (path.startsWith("/contacts")) return Promise.resolve([{ id: 5, client: 1, name: "João", email: "", phone: "", job_title: "" }]);
    if (path.startsWith("/documents/?opportunity")) return Promise.resolve([{ id: 9, client: null, opportunity: 1, project: null, file: "x", original_name: "proposta.pdf", uploaded_by: 1, created_at: "2026-08-01" }]);
    if (path.includes("/convert-to-project/")) return Promise.resolve({ id: 7, name: "Oport X" });
    if (path.includes("/proposal/")) return Promise.resolve({ text: "Rascunho gerado pela IA", interaction: 4, artifact: proposalArtifact });
    if (path.includes("/summary/")) return Promise.resolve({ text: "Rascunho gerado pela IA", interaction: 4 });
    if (path.startsWith("/artifacts/?")) return Promise.resolve(artifacts);
    return Promise.resolve({});
  });
}

beforeEach(() => { mocks.api.mockReset(); artifacts = []; stub(); });
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
  // Converter sem retorno nenhum deixava a dúvida "criou?". O aviso responde e leva ao projeto.
  const aviso = await screen.findByRole("status");
  expect(within(aviso).getByRole("link", { name: /Abrir projeto/ })).toHaveAttribute("href", "/projetos/7");
});

test("oportunidade já convertida oferece ver o projeto, não criá-lo de novo", async () => {
  // Sem isto o card segue oferecendo "Criar projeto" numa oportunidade que só pode responder 409.
  mocks.api.mockImplementation((path: string) => {
    if (path === "/pipeline-stages/") return Promise.resolve(stages);
    if (path === "/opportunities/") return Promise.resolve([{ ...opp, project: 7 }]);
    if (path === "/services/") return Promise.resolve(services);
    if (path === "/clients/") return Promise.resolve([]);
    return Promise.resolve([]);
  });
  render(<CommercialPage />);
  await screen.findByText("Oport X");

  expect(screen.getByRole("link", { name: /Ver projeto/ })).toHaveAttribute("href", "/projetos/7");
  expect(screen.queryByRole("button", { name: /Criar projeto/ })).not.toBeInTheDocument();
});

test("a proposta gerada por IA fica registrada como artefato em rascunho", async () => {
  const user = userEvent.setup();
  render(<CommercialPage />);
  await user.click(await screen.findByText("Oport X"));

  artifacts = [proposalArtifact];  // o POST persiste o rascunho no backend
  await user.click(await screen.findByRole("button", { name: "Gerar proposta" }));

  expect(await screen.findByText("Proposta — Oport X")).toBeInTheDocument();
  expect(screen.getByLabelText("Conteúdo de Proposta — Oport X")).toHaveValue("Rascunho gerado pela IA");
  expect(screen.getByText("Rascunho")).toBeInTheDocument();
});

test("o resumo segue efêmero e pode virar documento", async () => {
  const user = userEvent.setup();
  render(<CommercialPage />);
  await user.click(await screen.findByText("Oport X"));
  await user.click(await screen.findByRole("button", { name: "Resumir" }));

  expect(await screen.findByLabelText("Rascunho gerado pela IA")).toHaveValue("Rascunho gerado pela IA");
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
  await user.selectOptions(within(dialog).getByLabelText("Cliente"), "1");
  await user.type(within(dialog).getByLabelText("Valor estimado"), "5000");
  fireEvent.change(within(dialog).getByLabelText("Previsão de fechamento"), { target: { value: "2026-10-01" } });
  await user.click(within(dialog).getByRole("button", { name: "Adicionar ao pipeline" }));
  await waitFor(() => expect(mocks.api).toHaveBeenCalledWith("/opportunities/", expect.objectContaining({ method: "POST" })));
});

test("mostra o nível de produto no card do pipeline", async () => {
  render(<CommercialPage />);
  await screen.findByText("Oport X");
  expect(screen.getByText("Discovery Express")).toBeInTheDocument();
});

test("cria a oportunidade com o nível de produto escolhido", async () => {
  const user = userEvent.setup();
  render(<CommercialPage />);
  await screen.findByText("Oport X");
  await user.click(screen.getByRole("button", { name: "Nova oportunidade" }));
  const dialog = await screen.findByRole("dialog", { name: "Nova oportunidade" });
  await user.type(within(dialog).getByLabelText("Título"), "Nova Op");
  await user.selectOptions(within(dialog).getByLabelText("Cliente"), "1");
  await user.selectOptions(within(dialog).getByLabelText("Nível de produto"), "11");
  await user.type(within(dialog).getByLabelText("Valor estimado"), "5000");
  fireEvent.change(within(dialog).getByLabelText("Previsão de fechamento"), { target: { value: "2026-10-01" } });
  await user.click(within(dialog).getByRole("button", { name: "Adicionar ao pipeline" }));

  await waitFor(() => expect(mocks.api).toHaveBeenCalledWith("/opportunities/", expect.objectContaining({
    method: "POST", body: expect.stringContaining('"service":11'),
  })));
});

test("altera o nível de produto pelo detalhe da oportunidade", async () => {
  const user = userEvent.setup();
  render(<CommercialPage />);
  await user.click(await screen.findByText("Oport X"));
  await screen.findByText("Detalhe da oportunidade");
  await user.selectOptions(screen.getByLabelText("Nível de produto"), "11");
  await user.click(screen.getByRole("button", { name: "Salvar" }));

  await waitFor(() => expect(mocks.api).toHaveBeenCalledWith("/opportunities/1/", expect.objectContaining({
    method: "PATCH", body: expect.stringContaining('"service":11'),
  })));
});


// --- arquivar e restaurar (FDD 025) -------------------------------------------------------------
//
// O fluxo "Arquivar de dentro do detalhe" não tinha teste nenhum — foi exatamente onde o
// empilhamento de modais quebrou em produção.

test("arquiva a oportunidade a partir do detalhe, com confirmação", async () => {
  const user = userEvent.setup();
  render(<CommercialPage />);
  await user.click(await screen.findByText("Oport X"));
  await screen.findByText("Detalhe da oportunidade");

  await user.click(screen.getByRole("button", { name: /Arquivar/ }));
  // A confirmação abre por cima; o detalhe continua montado atrás.
  expect(screen.getByRole("dialog", { name: "Arquivar oportunidade" })).toBeInTheDocument();
  expect(screen.getByRole("dialog", { name: "Detalhe da oportunidade" })).toBeInTheDocument();
  expect(mocks.api).not.toHaveBeenCalledWith("/opportunities/1/", expect.objectContaining({ method: "DELETE" }));

  await user.click(within(screen.getByRole("dialog", { name: "Arquivar oportunidade" })).getByRole("button", { name: "Arquivar" }));
  await waitFor(() => expect(mocks.api).toHaveBeenCalledWith("/opportunities/1/", expect.objectContaining({ method: "DELETE" })));
});

test("projeto arquivado não vira link nem oferece nova conversão", async () => {
  mocks.api.mockImplementation((path: string, options?: { method?: string }) => {
    const method = options?.method?.toUpperCase() ?? "GET";
    if (path === "/pipeline-stages/") return Promise.resolve(stages);
    if (path === "/opportunities/" && method === "GET") return Promise.resolve([{ ...opp, project: 7, project_archived: true }]);
    if (path === "/services/") return Promise.resolve(services);
    if (path === "/clients/") return Promise.resolve([]);
    return Promise.resolve({});
  });
  render(<CommercialPage />);

  expect(await screen.findByText("Projeto arquivado")).toBeInTheDocument();
  // Um link levaria a 404 (o projeto sai do queryset) e "Criar projeto" responderia 409.
  expect(screen.queryByRole("link", { name: /Ver projeto/ })).not.toBeInTheDocument();
  expect(screen.queryByRole("button", { name: /Criar projeto/ })).not.toBeInTheDocument();
});

test("lista e restaura oportunidades arquivadas", async () => {
  const user = userEvent.setup();
  mocks.api.mockImplementation((path: string) => {
    if (path === "/pipeline-stages/") return Promise.resolve(stages);
    if (path === "/opportunities/?archived=1") return Promise.resolve([{ ...opp, id: 2, title: "Arquivada X" }]);
    if (path === "/opportunities/") return Promise.resolve([]);
    if (path === "/services/") return Promise.resolve(services);
    if (path === "/clients/") return Promise.resolve([]);
    return Promise.resolve({});
  });
  render(<CommercialPage />);

  await user.click(await screen.findByRole("button", { name: "Arquivadas" }));
  expect(await screen.findByText("Arquivada X")).toBeInTheDocument();

  await user.click(screen.getByRole("button", { name: /Restaurar/ }));
  await waitFor(() => expect(mocks.api).toHaveBeenCalledWith("/opportunities/2/unarchive/", expect.objectContaining({ method: "POST" })));
});
