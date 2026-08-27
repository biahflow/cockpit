import { cleanup, render, screen, within } from "@testing-library/react";
import { afterEach, expect, test, vi } from "vitest";

import { DashboardPage } from "./DashboardPage";

// `account_ladder` é parte do contrato de `/dashboard/` desde a FDD 042 — a fixture o carrega
// preenchido para que o bloco compacto renderize aqui em vez de sumir por lista vazia.
const { escada } = vi.hoisted(() => ({ escada: [{
  client_id: 7, client_name: "Metalúrgica Vale", rung: "prove", rung_display: "Prove",
  status: "blocked", status_display: "Bloqueado",
  waiting_on: "client", waiting_on_display: "Cliente", days_stalled: 31, is_stale: true,
  steps: [
    { rung: "discover", rung_display: "Discover", status: "done" },
    { rung: "prioritize", rung_display: "Prioritize", status: "done" },
    { rung: "feasibility", rung_display: "[ Technical Feasibility ]", status: "skipped" },
    { rung: "prove", rung_display: "Prove", status: "blocked" },
    { rung: "scale", rung_display: "Scale", status: "not_sold" },
    { rung: "optimize", rung_display: "Optimize", status: "not_sold" },
  ],
}] }));
vi.mock("../api", () => ({ api: vi.fn().mockResolvedValue({ pipeline: [], active_projects: 2, overdue_count: 1, upcoming_tasks: [{ id: 1, title: "Reunião", due_date: "2026-08-10", project_id: 1 }], account_ladder: escada }) }));
const authState = vi.hoisted(() => ({ user: { role: "admin", is_admin: true } as { role: string; is_admin?: boolean } }));
vi.mock("../auth", () => ({ useAuth: () => authState }));

afterEach(cleanup);

test("esconde o pipeline comercial de quem é da Entrega", async () => {
  authState.user = { role: "delivery" };
  render(<DashboardPage />);
  expect(await screen.findByText("Projetos ativos")).toBeInTheDocument();
  expect(screen.queryByText("Pipeline estimado")).not.toBeInTheDocument();
  expect(screen.queryByText("Pipeline comercial")).not.toBeInTheDocument();
  authState.user = { role: "admin", is_admin: true };
});

test("exibe métricas e próximas entregas", async () => {
  render(<DashboardPage />);
  expect(await screen.findByText("Projetos ativos")).toBeInTheDocument();
  expect(screen.getByText("Reunião")).toBeInTheDocument();
  expect(screen.getByText("1")).toBeInTheDocument();
});

/**
 * Superfície B da escada FDE (FDD 042). A linha diz **onde a conta está, de quem é a bola e há
 * quanto tempo parou** — e a linha inteira é um link para a conta, porque isto serve para varrer a
 * carteira e não para operar.
 */
test("mostra a escada FDE por conta, com o dono e o tempo parado", async () => {
  render(<DashboardPage />);
  const linha = await screen.findByRole("link", { name: /Metalúrgica Vale/ });
  expect(linha).toHaveAttribute("href", "/clientes/7");
  expect(within(linha).getByText("Prove · bloqueado")).toBeInTheDocument();
  expect(within(linha).getByText("Cliente")).toBeInTheDocument();
  expect(within(linha).getByText("parado há 31 dias")).toBeInTheDocument();
});

/** A escada compacta é decoração: o degrau e o estado vão escritos por extenso ao lado dela. */
test("a trilha compacta não fala com o leitor de tela", async () => {
  const { container } = render(<DashboardPage />);
  await screen.findByRole("link", { name: /Metalúrgica Vale/ });
  const trilha = container.querySelector(".timeline--compact");
  expect(trilha).toHaveAttribute("aria-hidden", "true");
  expect(trilha?.querySelectorAll(".timeline-step")).toHaveLength(6);
});
