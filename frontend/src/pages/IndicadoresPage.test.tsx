import { cleanup, render, screen } from "@testing-library/react";
import { afterEach, expect, test, vi } from "vitest";

import { IndicadoresPage } from "./IndicadoresPage";

vi.mock("../auth", () => ({ useAuth: () => ({ user: { role: "admin" } }) }));
vi.mock("../api", () => ({
  api: vi.fn((path: string) => {
    if (path === "/risk/") return Promise.resolve({ projects: [{ project_id: 7, name: "Projeto Z", score: 70, level: "alto", signals: [{ label: "Projeto vencido", detail: "3 dias", weight: 30 }] }] });
    if (path === "/health/") return Promise.resolve({ projects: [{ project_id: 8, name: "Projeto W", score: 55, level: "atenção", signals: [{ label: "Decisões pendentes", detail: "2 em aberto", weight: 15 }] }] });
    if (path === "/recommendations/") return Promise.resolve({ items: [{ kind: "upsell", label: "Novo negócio com ACME", detail: "Cliente ativo", url: "/clientes/1" }] });
    return Promise.resolve({
      funnel: { leads: { total: 3, by_status: { new: 3 } }, opportunities: { open: 2, won: 1, lost: 1 }, projects: { total: 1, by_status: { active: 1 } } },
      win_rate: 0.5, avg_ticket: 1000, avg_cycle_days: 12,
      pipeline: [{ id: 1, name: "Prospecção", kind: "open", position: 0, opportunity_count: 2, estimated_total: 5000 }],
      roi: { revenue: 1000, cost: 400, roi: 1.5, by_client: [{ label: "ACME", revenue: 1000, cost: 400, roi: 1.5 }], by_service: [{ label: "Consultoria", revenue: 1000, cost: 400, roi: 1.5 }] },
    });
  }),
}));

afterEach(cleanup);

test("mostra KPIs e ROI por cliente/serviço", async () => {
  render(<IndicadoresPage />);
  expect(await screen.findByText("Taxa de ganho")).toBeInTheDocument();
  expect(screen.getByText("50%")).toBeInTheDocument();
  expect(screen.getByText("ROI por cliente")).toBeInTheDocument();
  expect(screen.getByText("ACME")).toBeInTheDocument();
  expect(screen.getByText("Consultoria")).toBeInTheDocument();
  expect(await screen.findByText("Projeto Z")).toBeInTheDocument();
  expect(screen.getByText("Novo negócio com ACME")).toBeInTheDocument();
});
