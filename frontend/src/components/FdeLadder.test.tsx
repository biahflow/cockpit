/**
 * Os onze estados da escada FDE (FDD 042, DAP GH-42 r1) — os dez que a especificação lista mais o
 * erro de carregamento, que todo pacote de design tem de cobrir e que esta tela alcança.
 *
 * O que estes testes protegem, e não é estilo: **"pulada" e "não vendido" não podem parecer a
 * mesma coisa**. As duas deixam o degrau sem projeto e as duas são neutras — nenhuma é aviso —,
 * então o que as separa é *estrutura*: a variante do degrau e a presença do registro. Uma
 * asserção sobre a cor aprovaria as duas; a asserção sobre a variante e sobre o motivo, não.
 */

import { cleanup, render, screen, within } from "@testing-library/react";
import { afterEach, expect, test } from "vitest";

import { FdeLadder, FdeLadderOverview } from "./FdeLadder";
import type { AccountLadderRow, AccountRung, AccountRungStatus, ProjectPhase } from "../types";

afterEach(cleanup);

const ROTULOS: Record<string, string> = {
  discover: "Discover", prioritize: "Prioritize", feasibility: "[ Technical Feasibility ]",
  prove: "Prove", scale: "Scale", optimize: "Optimize",
};

function degrau(overrides: Partial<AccountRung> & { rung: AccountRung["rung"] }): AccountRung {
  return {
    id: Object.keys(ROTULOS).indexOf(overrides.rung) + 1,
    client: 1, rung_display: ROTULOS[overrides.rung],
    status: "not_sold" as AccountRungStatus, status_display: "Não vendido",
    opportunity: null, opportunity_title: "", project: null, project_name: "",
    started_at: null, completed_at: null, waiting_on: "", waiting_on_display: "",
    blocker: "", skip_reason: "", skipped_by: null, skipped_by_name: "", skipped_at: null,
    days_stalled: null, is_stale: false, gate_outcome: "", next_gate: null,
    no_access: false, events: [],
    ...overrides,
  };
}

function fase(overrides: Partial<ProjectPhase> & { id: number }): ProjectPhase {
  return {
    project: 5, phase: overrides.id, phase_name: `Fase ${overrides.id}`, phase_description: "",
    phase_position: overrides.id, requires_gate: false, status: "locked",
    started_at: null, completed_at: null, target_date: null,
    gate_outcome: "", gate_notes: "", checklist_waiver: "",
    deliverables: [], checklist_items: [],
    ...overrides,
  };
}

/**
 * A variante do degrau, que é onde mora a distinção que o DAP existe para decidir.
 *
 * Só os degraus **de primeiro nível**: a trilha aninhada da FDD 011 usa as mesmas variantes, e um
 * seletor solto casaria a fase "Prove" da jornada com o degrau "Prove" da escada.
 */
function variante(container: HTMLElement, rotulo: string): string {
  const raiz = container.querySelector("ol.timeline:not(.timeline--nested)");
  const passo = [...(raiz?.children ?? [])].find(no => no.querySelector(".timeline-body strong")?.textContent === rotulo);
  return passo?.className ?? "";
}

test("1 · concluído leva o selo de sucesso e o gate registrado, com o mapa da tela do projeto", () => {
  const { container } = render(<FdeLadder loading={false} error="" phases={[]} rungs={[degrau({
    rung: "discover", status: "done", status_display: "Concluído", gate_outcome: "go",
    opportunity: 2, opportunity_title: "Discovery Sprint · Vale", project: 5, project_name: "Discovery Vale",
    started_at: "2026-02-12T09:00:00Z", completed_at: "2026-03-06T09:00:00Z",
  })]} />);

  expect(screen.getByText("Concluído")).toHaveClass("state--1");
  // O mesmo `GATE_LABEL`/`gateBadgeClass` da `JourneySection` — nunca um segundo mapa.
  expect(screen.getByText("GO")).toHaveClass("state--1");
  expect(variante(container, "Discover")).toContain("timeline-step--done");
  expect(screen.getByText(/Vendido em Discovery Sprint · Vale/)).toBeInTheDocument();
});

test("2 · ativo não leva selo de estado: quem diz ativo é a expansão e o “Você está aqui”", () => {
  const { container } = render(<FdeLadder loading={false} error="" rungs={[degrau({
    rung: "prove", status: "active", status_display: "Ativo", project: 5,
    project_name: "PROVE Triagem de NF", started_at: "2026-03-18T09:00:00Z",
    waiting_on: "biahflow", waiting_on_display: "Biahflow",
  })]} phases={[
    fase({ id: 1, phase_name: "Welcome", status: "done" }),
    fase({ id: 2, phase_name: "Launch Session", status: "active" }),
    fase({ id: 3, phase_name: "Prove", status: "locked" }),
  ]} />);

  expect(screen.queryByText("Ativo")).not.toBeInTheDocument();
  expect(screen.getByText("Você está aqui")).toHaveClass("eyebrow");
  expect(variante(container, "Prove")).toContain("timeline-step--active");
  // A jornada de entrega da FDD 011 aparece **aninhada e subordinada**, referenciada e não
  // redesenhada — a tela que a opera continua sendo a do projeto.
  const aninhada = container.querySelector(".timeline--nested");
  expect(aninhada).not.toBeNull();
  expect(within(aninhada as HTMLElement).getByText("Launch Session")).toBeInTheDocument();
  expect(screen.getByText(/Jornada de entrega do projeto · FDD 011 · 1 de 3 fases/)).toBeInTheDocument();
  expect(screen.getByText("Biahflow")).toHaveClass("state--0");
});

test("3 e 4 · não vendido e pulada não parecem a mesma coisa", () => {
  const { container } = render(<FdeLadder loading={false} error="" phases={[]} rungs={[
    degrau({
      rung: "feasibility", status: "skipped", status_display: "Pulada",
      skip_reason: "tecnologia sabida", skipped_by_name: "Daniel Campos",
      skipped_at: "2026-03-10T09:05:00Z",
    }),
    degrau({ rung: "scale" }),
  ]} />);

  // Mesmo selo neutro nas duas — de propósito: nenhuma é aviso, e pintar uma de âmbar mentiria
  // sobre a gravidade. O que as separa é a **variante**, não a tinta.
  expect(screen.getByText("Pulada")).toHaveClass("state--off");
  expect(screen.getByText("Não vendido")).toHaveClass("state--off");
  expect(variante(container, "[ Technical Feasibility ]")).toContain("timeline-step--skipped");
  expect(variante(container, "Scale")).toContain("timeline-step--future");

  // E o conteúdo faz a outra metade: pulada **prova** que houve decisão; não vendido afirma a
  // ausência em vez de ficar vazio.
  expect(screen.getByText(/Motivo registrado: tecnologia sabida/)).toBeInTheDocument();
  expect(screen.getByText(/decidido por Daniel Campos/)).toBeInTheDocument();
  expect(screen.getByText(/Nenhuma decisão registrada/)).toBeInTheDocument();
});

test("5 · bloqueado mostra o quê e quem, sem abrir nota", () => {
  const { container } = render(<FdeLadder loading={false} error="" phases={[]} rungs={[degrau({
    rung: "prove", status: "blocked", status_display: "Bloqueado",
    blocker: "Acesso ao ERP pendente do time de TI do cliente",
    waiting_on: "client", waiting_on_display: "Cliente",
    days_stalled: 19, is_stale: true,
  })]} />);

  expect(screen.getByText("Bloqueado")).toHaveClass("state--3");
  expect(screen.getByText("Acesso ao ERP pendente do time de TI do cliente")).toBeInTheDocument();
  expect(screen.getByText("Cliente")).toHaveClass("state--2");
  expect(screen.getByText("Parado há 19 dias")).toBeInTheDocument();
  expect(variante(container, "Prove")).toContain("timeline-step--blocked");
});

test("6 · aguardando gate mostra as quatro saídas como texto, não como botões", () => {
  const { container } = render(<FdeLadder loading={false} error="" phases={[]} rungs={[degrau({
    rung: "prove", status: "awaiting_gate", status_display: "Aguardando decisão de gate",
    waiting_on: "human_gate", waiting_on_display: "Human Gate",
    next_gate: { phase_name: "Prove", target_date: "2026-09-12" },
  })]} />);

  expect(screen.getByText("Aguardando decisão de gate")).toHaveClass("state--2");
  expect(screen.getByText(/GO · CONDITIONAL GO · REDESIGN · NO-GO/)).toBeInTheDocument();
  // Nenhum controle inerte: o gate se decide na tela do projeto.
  expect(screen.queryByRole("button", { name: "GO" })).not.toBeInTheDocument();
  // A única pastilha sólida do produto.
  expect(screen.getAllByText("Human Gate")[0]).toHaveClass("state--gate");
  expect(variante(container, "Prove")).toContain("timeline-step--gate");
  expect(screen.getByText(/previsto 12\/09\/2026/)).toBeInTheDocument();
});

test("7 · replanejado não apaga o histórico nem as datas em que o degrau esteve ativo", () => {
  const { container } = render(<FdeLadder loading={false} error="" phases={[]} rungs={[degrau({
    rung: "scale", status: "cancelled", status_display: "Replanejado",
    started_at: "2026-05-02T09:00:00Z", completed_at: "2026-06-14T09:00:00Z",
    events: [
      { id: 1, rung: 5, from_status: "not_sold", from_status_display: "Não vendido", to_status: "active", to_status_display: "Ativo", at: "2026-05-02T09:00:00Z", by: 1, by_name: "Daniel Campos", note: "" },
      { id: 2, rung: 5, from_status: "active", from_status_display: "Ativo", to_status: "cancelled", to_status_display: "Replanejado", at: "2026-06-14T09:00:00Z", by: 1, by_name: "Daniel Campos", note: "escopo devolvido ao PROVE" },
    ],
  })]} />);

  expect(screen.getAllByText("Replanejado")[0]).toHaveClass("state--off");
  expect(variante(container, "Scale")).toContain("timeline-step--cancelled");
  expect(screen.getByText(/02\/05\/2026 → 14\/06\/2026/)).toBeInTheDocument();
  // O histórico mora numa gaveta **por degrau**: a pergunta que se faz olhando um degrau é sempre
  // "o que aconteceu *aqui*".
  expect(screen.getByText("2 transições")).toBeInTheDocument();
  expect(screen.getByText(/escopo devolvido ao PROVE/)).toBeInTheDocument();
});

test("8 · conta nova diz o que faz a escada começar, e não só que está vazia", () => {
  render(<FdeLadder loading={false} error="" phases={[]} rungs={[]} />);

  const vazio = screen.getByText(/Nenhum degrau iniciado/);
  expect(vazio).toHaveClass("empty-state");
  expect(vazio).toHaveTextContent("a primeira oportunidade desta conta for ganha e convertida");
  // A ação mora no Comercial: sem botão primário aqui.
  expect(screen.queryByRole("button")).not.toBeInTheDocument();
});

test("9 · carregando é esqueleto sem selo colorido", () => {
  render(<FdeLadder loading error="" phases={[]} rungs={[]} />);

  expect(screen.getByTestId("escada-carregando")).toBeInTheDocument();
  // Um esqueleto com estado anuncia um estado que ainda não se sabe.
  expect(screen.queryByText("Não vendido")).not.toBeInTheDocument();
  expect(screen.queryByText(/Nenhum degrau iniciado/)).not.toBeInTheDocument();
});

test("10 · sem acesso mostra a forma da escada e nada do conteúdo comercial", () => {
  const { container } = render(<FdeLadder loading={false} error="" phases={[]} rungs={[degrau({
    rung: "discover", status: "done", status_display: "Concluído", no_access: true,
  })]} />);

  expect(screen.getByText("Sem acesso")).toHaveClass("state--off");
  expect(screen.queryByText("Concluído")).not.toBeInTheDocument();
  expect(screen.getByText("Discover")).toBeInTheDocument();
  expect(variante(container, "Discover")).toContain("timeline-step--future");
});

test("11 · erro de carregamento interrompe a tela — alerta, não selo", () => {
  render(<FdeLadder loading={false} error="Não foi possível carregar a escada desta conta." phases={[]} rungs={[]} />);

  const alerta = screen.getByRole("alert");
  expect(alerta).toHaveClass("alert--error");
  expect(screen.queryByText("Escada FDE")).not.toBeInTheDocument();
});

test("os seis degraus saem na ordem da doutrina, e o marcador é decorativo", () => {
  const { container } = render(<FdeLadder loading={false} error="" phases={[]} rungs={
    (Object.keys(ROTULOS) as AccountRung["rung"][]).map(rung => degrau({ rung }))
  } />);

  const lista = container.querySelector("ol.timeline");
  expect(lista?.tagName).toBe("OL");  // a ordem é o significado
  expect([...container.querySelectorAll(".timeline-step > .timeline-body strong")].map(no => no.textContent))
    .toEqual(["Discover", "Prioritize", "[ Technical Feasibility ]", "Prove", "Scale", "Optimize"]);
  // O estado vem do texto; o nó sobre o trilho não fala com o leitor de tela.
  for (const marcador of container.querySelectorAll(".timeline-marker")) {
    expect(marcador).toHaveAttribute("aria-hidden", "true");
  }
});

test("o dono “engenharia” usa a pele de engenharia, fora da família .state", () => {
  render(<FdeLadder loading={false} error="" phases={[]} rungs={[degrau({
    rung: "prove", status: "active", status_display: "Ativo",
    waiting_on: "engineering", waiting_on_display: "Engenharia",
  })]} />);

  const chip = screen.getByText("Engenharia");
  expect(chip).toHaveClass("eng-ref");
  expect(chip.className).not.toContain("state");
});

test("a dependência externa é neutra: ausência de agência não é aviso", () => {
  render(<FdeLadder loading={false} error="" phases={[]} rungs={[degrau({
    rung: "prove", status: "blocked", status_display: "Bloqueado", blocker: "Fornecedor de OCR fora do ar",
    waiting_on: "external", waiting_on_display: "Dependência externa",
  })]} />);

  expect(screen.getByText("Dependência externa")).toHaveClass("state--off");
});

test("a visão geral some quando nenhuma conta está vivendo um degrau", () => {
  const linhas: AccountLadderRow[] = [];
  const { container } = render(<FdeLadderOverview rows={linhas} />);
  expect(container).toBeEmptyDOMElement();
});
