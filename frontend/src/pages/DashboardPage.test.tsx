import { render, screen } from "@testing-library/react";
import { expect, test, vi } from "vitest";

import { DashboardPage } from "./DashboardPage";

vi.mock("../api", () => ({ api: vi.fn().mockResolvedValue({ pipeline: [], active_projects: 2, overdue_count: 1, upcoming_tasks: [{ id: 1, title: "Reunião", due_date: "2026-08-10", project_id: 1 }] }) }));

test("exibe métricas e próximas entregas", async () => {
  render(<DashboardPage />);
  expect(await screen.findByText("Projetos ativos")).toBeInTheDocument();
  expect(screen.getByText("Reunião")).toBeInTheDocument();
  expect(screen.getByText("1")).toBeInTheDocument();
});
