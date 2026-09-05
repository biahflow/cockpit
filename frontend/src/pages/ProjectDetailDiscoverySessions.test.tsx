import { cleanup, render, screen, within } from "@testing-library/react";
import { afterEach, beforeEach, expect, test, vi } from "vitest";

import { ProjectDetailPage } from "./ProjectDetailPage";

/**
 * A porta da Discovery Session no detalhe do projeto (FDD 055; DAP
 * `dap-discovery-session-e-business-case-r2`, decisão **G1**).
 *
 * Ela mora na seção de reuniões e **não** no menu lateral: a sessão é sempre *de um projeto*, e um
 * item de menu que abre perguntando "qual?" é o beco já recusado três vezes. O que este arquivo
 * protege é o link — sem ele a tela nova existe e ninguém chega nela.
 */

const mocks = vi.hoisted(() => ({
  api: vi.fn(),
  listDiscoveries: vi.fn(),
  listDiscoverySessions: vi.fn(),
}));
const semFase5 = vi.hoisted(() => ({
  listKpis: () => Promise.resolve([]),
  listFeasibilityAssessments: () => Promise.resolve([]),
  listProveExperiments: () => Promise.resolve([]),
  listMeasurements: () => Promise.resolve([]),
  startProveExperiment: () => Promise.resolve({}),
  registerProveGapWaiver: () => Promise.resolve({}),
}));
vi.mock("../api", () => ({
  api: mocks.api,
  listDiscoveries: mocks.listDiscoveries,
  listDiscoverySessions: mocks.listDiscoverySessions,
  listUsers: () => Promise.resolve([]),
  ...semFase5,
}));
vi.mock("../auth", () => ({ useAuth: () => ({ aiEnabled: false, calendarEnabled: false, user: { role: "delivery" } }) }));

const sessao = (id: number, quando: string, achados = 0) => ({
  id, discovery: 7, meeting: null, happened_at: quando,
  participants: "Ana Meireles, Paulo Rangel", source_artifact: null, transcript: "",
  notes: {}, structured_finding_count: achados,
  created_at: quando, updated_at: quando,
});

beforeEach(() => {
  mocks.api.mockReset();
  mocks.api.mockImplementation((path: string) => {
    if (path.includes("/risk/")) return Promise.resolve({ project_id: 1, name: "Projeto X", score: 0, level: "baixo", signals: [] });
    if (path.includes("/health/")) return Promise.resolve({ project_id: 1, name: "Projeto X", score: 90, level: "saudável", signals: [] });
    if (path === "/projects/1/") return Promise.resolve({ id: 1, name: "Projeto X", description: "", owner: 1, start_date: "2026-08-01", due_date: "2026-09-01", status: "active", service: null, actual_value: "0", cost: "0", is_overdue: false });
    return Promise.resolve([]);
  });
  mocks.listDiscoveries.mockResolvedValue([{ id: 7, project: 1, project_name: "Projeto X", scope: "", status: "running", status_display: "Em andamento", started_at: null, completed_at: null, owner: null, created_at: "", updated_at: "" }]);
  mocks.listDiscoverySessions.mockResolvedValue([
    sessao(3, "2026-09-04T14:00:00Z"),
    sessao(4, "2026-09-05T14:00:00Z", 11),
  ]);
});
afterEach(cleanup);

test("cada sessão do projeto vira um link, da mais recente para a mais antiga", async () => {
  render(<ProjectDetailPage id={1} />);
  await screen.findByRole("heading", { name: "Projeto X" });

  const sessoes = await screen.findAllByRole("link", { name: /Sessão de/ });
  expect(sessoes.map(link => link.getAttribute("href"))).toEqual([
    "/projetos/1/sessoes/4", "/projetos/1/sessoes/3",
  ]);
  // O selo aparece só na que já foi estruturada — é o que distingue "ainda em captura" de
  // "já virou processo e achado", sem abrir a sessão.
  expect(within(sessoes[0]).getByText("Estruturada")).toBeInTheDocument();
  expect(within(sessoes[1]).queryByText("Estruturada")).not.toBeInTheDocument();
  // As sessões vêm do Discovery do projeto: a rota da sessão filtra por `discovery`, não por
  // projeto, e são duas chamadas por isso.
  expect(mocks.listDiscoveries).toHaveBeenCalledWith(1);
  expect(mocks.listDiscoverySessions).toHaveBeenCalledWith(7);
});

test("projeto sem Discovery não ganha seção nenhuma", async () => {
  mocks.listDiscoveries.mockResolvedValue([]);

  render(<ProjectDetailPage id={1} />);
  await screen.findByRole("heading", { name: "Projeto X" });

  expect(screen.queryByText("Sessões de Discovery")).not.toBeInTheDocument();
});

test("falha ao listar as sessões não derruba a seção de reuniões", async () => {
  // Leitura à parte da carga principal, como a projeção do GitHub: o detalhe do projeto continua
  // de pé quando o levantamento não responde.
  mocks.listDiscoveries.mockRejectedValue(new Error("sem conexão"));

  render(<ProjectDetailPage id={1} />);

  expect(await screen.findByRole("heading", { name: "Reuniões" })).toBeInTheDocument();
  expect(screen.queryByText("Sessões de Discovery")).not.toBeInTheDocument();
});
