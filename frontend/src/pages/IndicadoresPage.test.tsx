import { cleanup, render, screen } from "@testing-library/react";
import { afterEach, expect, test, vi } from "vitest";

import { IndicadoresPage } from "./IndicadoresPage";

vi.mock("../auth", () => ({ useAuth: () => ({ user: { role: "admin", is_admin: true } }) }));
vi.mock("../api", () => ({
  api: vi.fn((path: string) => {
    if (path === "/risk/") return Promise.resolve({ projects: [{ project_id: 7, name: "Projeto Z", score: 70, level: "alto", signals: [{ label: "Projeto vencido", detail: "3 dias", weight: 30 }] }] });
    if (path === "/health/") return Promise.resolve({ projects: [{ project_id: 8, name: "Projeto W", score: 55, level: "atenção", signals: [{ label: "Decisões pendentes", detail: "2 em aberto", weight: 15 }] }] });
    if (path === "/recommendations/") return Promise.resolve({ items: [{ kind: "upsell", label: "Novo negócio com ACME", detail: "Cliente ativo", url: "/contas/1" }] });
    return Promise.resolve({
      funnel: {
        leads: { total: 3, by_status: { new: 3 } }, opportunities: { open: 2, won: 1, lost: 1 },
        projects: { total: 1, by_status: { active: 1 } },
        by_tier: [
          { tier: "discovery_sprint", label: "Discovery Sprint", total: 2, open: 1, won: 1, lost: 0, estimated_total: "0.00", win_rate: 1 },
          { tier: "prove", label: "PROVE (piloto)", total: 0, open: 0, won: 0, lost: 0, estimated_total: "0.00", win_rate: null },
        ],
        by_stage: [
          { kind: "assessment", label: "Assessment", total: 3, sent: 1, accepted: 2, rejected: 0, acceptance_rate: 1, reached: 2 },
          { kind: "contract", label: "Contrato", total: 0, sent: 0, accepted: 0, rejected: 0, acceptance_rate: null, reached: 0 },
        ],
        by_source: [
          { source: "indicacao", leads: 4, won: 3, projects: 3, revenue: "90000.00" },
          { source: "site", leads: 10, won: 1, projects: 1, revenue: "5000.00" },
          { source: "evento-sebrae", leads: 2, won: 0, projects: 0, revenue: "0.00" },
        ],
      },
      win_rate: 0.5, avg_ticket: 1000, avg_cycle_days: 12,
      pipeline: [{ id: 1, name: "Prospecção", kind: "open", position: 0, opportunity_count: 2, estimated_total: "5000.00" }],
      // `by_account`, e não `by_client`: a SPA fala a `/api/v2/` (`api.ts`), onde a chave do
      // recorte por conta trocou de nome (`docs/ontology/aliases.md`). O mock com o nome legado
      // deixaria `rows` `undefined`, e `RoiTable` faz `rows.map` sem guarda — este teste falha
      // com `TypeError`, não com asserção. É o que o torna oráculo da chave: quem trocar o nome
      // de um lado só descobre aqui.
      roi: { revenue: "1000.00", cost: "400.00", roi: 1.5, by_account: [{ label: "ACME", revenue: "1000.00", cost: "400.00", roi: 1.5 }], by_service: [{ label: "Consultoria", revenue: "1000.00", cost: "400.00", roi: 1.5 }] },
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

test("mostra a conversão por nível de produto", async () => {
  render(<IndicadoresPage />);
  expect(await screen.findByText("Conversão por nível de produto")).toBeInTheDocument();
  expect(screen.getByText("Discovery Sprint")).toBeInTheDocument();
  expect(screen.getByText("Ganho 100%")).toBeInTheDocument();
  expect(screen.getByText("Ganho —")).toBeInTheDocument();
});

test("mostra a origem do negócio medida até o fechado", async () => {
  render(<IndicadoresPage />);
  expect(await screen.findByText("Origem do negócio")).toBeInTheDocument();
  // A pergunta da FDD 030 é "que canal fecha", não "que canal enche o formulário": o site traz
  // 10 leads e ganha 1, a indicação traz 4 e ganha 3 — e é por isso que a linha mostra as duas.
  expect(screen.getByText("Indicação")).toBeInTheDocument();
  expect(screen.getByText(/4 lead\(s\).*fecha 75%/)).toBeInTheDocument();
  expect(screen.getByText(/10 lead\(s\).*fecha 10%/)).toBeInTheDocument();
  // Origem sem nome no mapa passa crua, em vez de virar um balde chamado "Outros".
  expect(screen.getByText("evento-sebrae")).toBeInTheDocument();
});

test("mostra a conversão por etapa da jornada", async () => {
  render(<IndicadoresPage />);
  expect(await screen.findByText("Conversão por etapa da jornada")).toBeInTheDocument();
  expect(screen.getByText("Assessment")).toBeInTheDocument();
  expect(screen.getByText("2 cliente(s)")).toBeInTheDocument();
  expect(screen.getByText(/3 artefato\(s\).*aceitação 100%/)).toBeInTheDocument();
  expect(screen.getByText(/0 artefato\(s\).*aceitação —/)).toBeInTheDocument();
});
