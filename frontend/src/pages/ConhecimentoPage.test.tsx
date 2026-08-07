import { cleanup, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, expect, test, vi } from "vitest";

import { ConhecimentoPage } from "./ConhecimentoPage";

const mocks = vi.hoisted(() => ({ api: vi.fn(), user: { is_admin: true, role: "admin", first_name: "Ana", last_name: "Souza" } }));
vi.mock("../api", () => ({ api: mocks.api }));
vi.mock("../auth", () => ({ useAuth: () => ({ user: mocks.user }) }));

function peca(overrides: Record<string, unknown> = {}) {
  return {
    id: 7, area: 1, area_name: "Operação", owner_name: "Ana Souza",
    title: "Runbook — backup e restauração", kind: "procedure", kind_display: "Procedimento",
    source_path: "docs/runbooks/backup.md", summary: "",
    last_verified_at: "2026-05-01", verified_by: 1, review_interval_days: 90,
    status: "vencido", next_review_at: "2026-07-30", is_gap: false,
    created_at: "2026-01-01T09:00:00Z", updated_at: "2026-01-01T09:00:00Z",
    ...overrides,
  };
}

const areas = [
  { id: 1, name: "Operação", slug: "operacao", position: 10, active: true, owner: 1, owner_name: "Ana Souza", review_interval_days: 180 },
  { id: 2, name: "Comercial", slug: "comercial", position: 20, active: true, owner: null, owner_name: "", review_interval_days: 180 },
];

function stub(pecas: unknown[], resumo = { sem_dono: 1, vencido: 1, a_vencer: 0, corrente: 0 }) {
  return (path: string, options?: { method?: string }) => {
    if ((options?.method ?? "GET") === "GET") {
      if (path.startsWith("/knowledge-pieces/summary/")) return Promise.resolve(resumo);
      if (path.startsWith("/knowledge-pieces/")) return Promise.resolve(pecas);
      if (path.startsWith("/knowledge-areas/")) return Promise.resolve(areas);
    }
    return Promise.resolve({});
  };
}

beforeEach(() => {
  mocks.user = { is_admin: true, role: "admin", first_name: "Ana", last_name: "Souza" };
  mocks.api.mockImplementation(stub([peca()]));
});
afterEach(() => { cleanup(); vi.clearAllMocks(); });

test("mostra os quatro estados do inventário", async () => {
  render(<ConhecimentoPage />);
  // "Sem dono" aparece no contador **e** na opção do filtro — daí o `getAllByText`.
  expect(await screen.findAllByText("Sem dono")).not.toHaveLength(0);
  for (const estado of ["Vencido", "A vencer", "Corrente"]) {
    expect(screen.getAllByText(estado).length).toBeGreaterThan(0);
  }
});

test("área sem dono aparece antes de tudo, e não escondida num filtro", async () => {
  render(<ConhecimentoPage />);
  expect(await screen.findByText("Áreas sem dono")).toBeInTheDocument();
  expect(screen.getByText("Comercial")).toBeInTheDocument();
});

test("verificar chama a ação, e não um PATCH de data", async () => {
  render(<ConhecimentoPage />);
  await userEvent.click(await screen.findByRole("button", { name: /Marcar como verificado/ }));
  await waitFor(() => expect(mocks.api).toHaveBeenCalledWith(
    "/knowledge-pieces/7/verify/", expect.objectContaining({ method: "POST" }),
  ));
});

test("quem não é dono nem admin não vê o botão de verificar", async () => {
  mocks.user = { is_admin: false, role: "delivery", first_name: "João", last_name: "Lima" };
  render(<ConhecimentoPage />);
  expect(await screen.findByText("Runbook — backup e restauração")).toBeInTheDocument();
  expect(screen.queryByRole("button", { name: /Marcar como verificado/ })).not.toBeInTheDocument();
});

test("o dono da área vê o botão mesmo sem ser admin", async () => {
  mocks.user = { is_admin: false, role: "delivery", first_name: "Ana", last_name: "Souza" };
  render(<ConhecimentoPage />);
  expect(await screen.findByRole("button", { name: /Marcar como verificado/ })).toBeInTheDocument();
});

test("peça nunca verificada diz isso em vez de fingir data", async () => {
  mocks.api.mockImplementation(stub([peca({ last_verified_at: null, next_review_at: null })]));
  render(<ConhecimentoPage />);
  expect(await screen.findByText(/nunca verificado/)).toBeInTheDocument();
  expect(screen.getByText(/não vence/)).toBeInTheDocument();
});

test("lacuna aparece na seção própria", async () => {
  mocks.api.mockImplementation(stub([peca({ is_gap: true, source_path: "", title: "Como precificar fora de tabela" })]));
  render(<ConhecimentoPage />);
  expect(await screen.findByText("Lacunas")).toBeInTheDocument();
  expect(screen.getByText("Como precificar fora de tabela")).toBeInTheDocument();
});

test("o filtro de estado vai para o servidor", async () => {
  render(<ConhecimentoPage />);
  await userEvent.selectOptions(await screen.findByLabelText("Estado"), "vencido");
  await waitFor(() => expect(mocks.api).toHaveBeenCalledWith("/knowledge-pieces/?status=vencido"));
});

test("erro de carga vai para a tela", async () => {
  mocks.api.mockImplementation(() => Promise.reject(new Error("Sessão expirada.")));
  render(<ConhecimentoPage />);
  expect(await screen.findByRole("alert")).toHaveTextContent("Sessão expirada.");
});

test("sem peças, explica de onde elas vêm", async () => {
  mocks.api.mockImplementation(stub([], { sem_dono: 0, vencido: 0, a_vencer: 0, corrente: 0 }));
  render(<ConhecimentoPage />);
  expect(await screen.findByText(/ingest_knowledge/)).toBeInTheDocument();
});
