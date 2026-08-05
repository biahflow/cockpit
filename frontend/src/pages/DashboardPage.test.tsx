import { cleanup, render, screen } from "@testing-library/react";
import { afterEach, expect, test, vi } from "vitest";

import { DashboardPage } from "./DashboardPage";

vi.mock("../api", () => ({ api: vi.fn().mockResolvedValue({ pipeline: [], active_projects: 2, overdue_count: 1, upcoming_tasks: [{ id: 1, title: "Reunião", due_date: "2026-08-10", project_id: 1 }] }) }));
const authState = vi.hoisted(() => ({ user: { role: "admin" } as { role: string } }));
vi.mock("../auth", () => ({ useAuth: () => authState }));

afterEach(cleanup);

test("esconde o pipeline comercial de quem é da Entrega", async () => {
  authState.user = { role: "delivery" };
  render(<DashboardPage />);
  expect(await screen.findByText("Projetos ativos")).toBeInTheDocument();
  expect(screen.queryByText("Pipeline estimado")).not.toBeInTheDocument();
  expect(screen.queryByText("Pipeline comercial")).not.toBeInTheDocument();
  authState.user = { role: "admin" };
});

test("exibe métricas e próximas entregas", async () => {
  render(<DashboardPage />);
  expect(await screen.findByText("Projetos ativos")).toBeInTheDocument();
  expect(screen.getByText("Reunião")).toBeInTheDocument();
  expect(screen.getByText("1")).toBeInTheDocument();
});
