import { cleanup, render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, expect, test, vi } from "vitest";

import { PublicacaoPage } from "./PublicacaoPage";

const mocks = vi.hoisted(() => ({
  api: vi.fn(),
  listPainPointsByAccount: vi.fn(),
  listImprovementOpportunities: vi.fn(),
  publishProcess: vi.fn(),
  publishEvidence: vi.fn(),
  publishFinding: vi.fn(),
  publishPainPoint: vi.fn(),
  publishImprovementOpportunity: vi.fn(),
  unpublishProcess: vi.fn(),
  unpublishEvidence: vi.fn(),
  unpublishFinding: vi.fn(),
  unpublishPainPoint: vi.fn(),
  unpublishImprovementOpportunity: vi.fn(),
  auth: { user: { id: 1, is_admin: true, role: "admin" } } as { user: { id: number; is_admin: boolean; role: string } },
}));
vi.mock("../api", () => ({
  api: mocks.api,
  listPainPointsByAccount: mocks.listPainPointsByAccount,
  listImprovementOpportunities: mocks.listImprovementOpportunities,
  publishProcess: mocks.publishProcess,
  publishEvidence: mocks.publishEvidence,
  publishFinding: mocks.publishFinding,
  publishPainPoint: mocks.publishPainPoint,
  publishImprovementOpportunity: mocks.publishImprovementOpportunity,
  unpublishProcess: mocks.unpublishProcess,
  unpublishEvidence: mocks.unpublishEvidence,
  unpublishFinding: mocks.unpublishFinding,
  unpublishPainPoint: mocks.unpublishPainPoint,
  unpublishImprovementOpportunity: mocks.unpublishImprovementOpportunity,
}));
vi.mock("../auth", () => ({ useAuth: () => mocks.auth }));

/**
 * O campo derivado `publication_state` (DAP `dap-publicacao-discovery-r1`, decisão B1/E1).
 *
 * As frases são as de `backend/apps/core/publication.py` — `ROTULOS` e `_IMPEDIMENTO` — copiadas
 * **como fixture**, que é o oposto de reescrevê-las na tela: aqui elas entram pelo mesmo lugar por
 * onde entrariam do servidor, e é justamente isso que a última asserção deste arquivo verifica.
 */
const oculto = (falta?: { chave: string; frase: string }) => ({
  published_at: null, published_by: null,
  publication_state: {
    state: falta ? "blocked" : "ready",
    missing: falta ? [falta.chave] : [], missing_phrase: falta ? falta.frase : "",
    blocked_by: 0, blocked_phrase: "",
  },
});
const visivel = (presos = 0, impedimento = "") => ({
  published_at: "2026-08-20T09:00:00Z", published_by: 1,
  publication_state: {
    state: "published", missing: [], missing_phrase: "",
    blocked_by: presos, blocked_phrase: impedimento,
  },
});
const FALTA_EVIDENCIA = { chave: "published_evidence", frase: "ao menos uma evidência publicada e viva" };
const FALTA_ACHADO = { chave: "published_finding", frase: "ao menos um achado publicado e vivo" };
const FALTA_DOR = { chave: "published_pain_point", frase: "ao menos uma dor publicada e viva" };
const FALTA_PROCESSO = { chave: "published_process", frase: "o processo que ele cita publicado e vivo" };
const PRESO_PELO_ACHADO = "Este é o último achado publicado e vivo de 1 dor(es) publicada(s). Despublique a dor primeiro, ou publique outro achado.";

function processo(overrides: Record<string, unknown> = {}) {
  return {
    id: 1, account: 4, client: 4, client_name: "Transportadora Rota Norte",
    name: "Conferência de carga na expedição", position: 1,
    source_project: null, source_meeting: null, registered_by: 1,
    volume_mes: null, tempo_horas: null, pessoas: null, custo_hora: null,
    retrabalho_mes: null, erros_mes: null, perdas_mes: null, espera_mes: null, risco_mes: null,
    custo: { parcelas: [], total: "0.00", nao_apurado: [], sustentacao: "hipotese" },
    ...oculto(), created_at: "2026-08-10T09:00:00Z", updated_at: "2026-08-10T09:00:00Z",
    ...overrides,
  };
}

function evidencia(overrides: Record<string, unknown> = {}) {
  return {
    id: 7, account: 4, discovery: null, process: 1, step: null,
    kind: "interview", kind_display: "Entrevista (o que dizem)",
    raw_excerpt: "A gente refaz a conferência inteira quando o coletor não sobe.", reference: "",
    source_session: null, source_meeting: null, captured_at: "2026-08-12T09:00:00Z",
    captured_by: 1, content_hash: "abc",
    ...oculto(), created_at: "2026-08-12T09:00:00Z", updated_at: "2026-08-12T09:00:00Z",
    ...overrides,
  };
}

function achado(overrides: Record<string, unknown> = {}) {
  return {
    id: 20, account: 4, process: 1, step: null,
    statement: "O conferente refaz a conferência da carga porque o coletor não sincroniza com o WMS",
    epistemic_status: "fact", epistemic_status_display: "Fato",
    confidence: null, reviewed_by: 1, reviewed_at: "2026-08-12T09:00:00Z", evidences: [7],
    ...oculto(FALTA_EVIDENCIA), created_at: "2026-08-12T09:00:00Z", updated_at: "2026-08-12T09:00:00Z",
    ...overrides,
  };
}

function dor(overrides: Record<string, unknown> = {}) {
  return {
    id: 30, account: 4, process: 1, step: null,
    title: "Reemissão de nota fiscal por divergência de volume", description: "",
    impact_type: "financial", impact_type_display: "Financeiro", impact_estimate: null,
    findings: [20], status: "confirmed", status_display: "Confirmado",
    ...oculto(FALTA_ACHADO), created_at: "2026-08-12T09:00:00Z", updated_at: "2026-08-12T09:00:00Z",
    ...overrides,
  };
}

function oportunidade(overrides: Record<string, unknown> = {}) {
  return {
    id: 40, account: 4, engagement: null,
    title: "Sincronizar o coletor de expedição com o WMS em tempo real",
    desired_change: "", impact_hypothesis: "", pain_points: [30],
    status: "prioritized", status_display: "Priorizada",
    score: "74.00", assessment_version: 1, rank: 1,
    ...oculto(FALTA_DOR), created_at: "2026-08-12T09:00:00Z", updated_at: "2026-08-12T09:00:00Z",
    ...overrides,
  };
}

let conta: unknown = { id: 4, name: "Transportadora Rota Norte", legal_name: "", tax_id: "", owner: 1, lifecycle_status: "active", status: "active", vertical: null, vertical_name: "" };
let processos: unknown[] = [];
let evidencias: unknown[] = [];
let achados: unknown[] = [];
let dores: unknown[] = [];
let oportunidades: unknown[] = [];

function stub() {
  mocks.api.mockImplementation((path: string) => {
    if (path === "/clients/4/") return conta instanceof Error ? Promise.reject(conta) : Promise.resolve(conta);
    if (path.startsWith("/processos")) return Promise.resolve(processos);
    if (path.startsWith("/evidence")) return Promise.resolve(evidencias);
    if (path.startsWith("/findings")) return Promise.resolve(achados);
    return Promise.resolve([]);
  });
  mocks.listPainPointsByAccount.mockImplementation(() => Promise.resolve(dores));
  mocks.listImprovementOpportunities.mockImplementation(() => Promise.resolve(oportunidades));
  for (const nome of ["publishProcess", "publishEvidence", "publishFinding", "publishPainPoint", "publishImprovementOpportunity", "unpublishProcess", "unpublishEvidence", "unpublishFinding", "unpublishPainPoint", "unpublishImprovementOpportunity"] as const) {
    mocks[nome].mockResolvedValue({});
  }
}

/** A linha de lista que contém aquele texto — o selo e o botão são irmãos do `.row-main`. */
function linhaDe(texto: string | RegExp): HTMLElement {
  const linha = screen.getAllByText(texto).map(no => no.closest(".row")).find(Boolean);
  expect(linha).toBeTruthy();
  return linha as HTMLElement;
}

/** O cenário completo da conta, com **os quatro estados por item** de pé ao mesmo tempo. */
function discoveryCompleto() {
  processos = [
    processo(visivel(2, "Este processo é a âncora de 2 achado(s) ou dor(es) publicado(s). Despublique-os primeiro.")),
    processo({ id: 2, name: "Roteirização de entregas", ...oculto() }),
  ];
  evidencias = [evidencia(), evidencia({ id: 8, process: 2, kind_display: "Observação (o que fazem)" })];
  achados = [
    achado(),
    achado({ id: 21, process: 2, statement: "A roteirização manual acrescenta 90 km por dia", epistemic_status: "hypothesis", epistemic_status_display: "Hipótese", evidences: [8], ...oculto(FALTA_PROCESSO) }),
  ];
  dores = [dor()];
  oportunidades = [oportunidade()];
  stub();
}

beforeEach(() => {
  for (const mock of Object.values(mocks)) if (typeof mock === "function") mock.mockReset();
  mocks.auth.user = { id: 1, is_admin: true, role: "admin" };
  conta = { id: 4, name: "Transportadora Rota Norte", legal_name: "", tax_id: "", owner: 1, lifecycle_status: "active", status: "active", vertical: null, vertical_name: "" };
  processos = []; evidencias = []; achados = []; dores = []; oportunidades = [];
  stub();
});
afterEach(cleanup);

test("a conta sem Discovery diz que não há o que publicar", async () => {
  render(<PublicacaoPage accountId={4} />);
  await screen.findByRole("heading", { name: "Publicação do Discovery — Transportadora Rota Norte" });

  // A mesma frase da `AccountDetailPage`: a tela não inventa uma segunda redação para o mesmo vazio.
  expect(screen.getByText("Nenhum processo mapeado para esta conta.")).toBeInTheDocument();
  expect(screen.getByRole("button", { name: "Publicar selecionados (0)" })).toBeDisabled();
});

test("os quatro estados por item convivem, e cada um diz o que é", async () => {
  discoveryCompleto();
  render(<PublicacaoPage accountId={4} />);
  await screen.findByRole("heading", { name: "Publicação do Discovery — Transportadora Rota Norte" });

  // **Visível · preso** — selo escuro, frase do 409 na linha, botão desabilitado (decisão G1).
  const mapa = within(linhaDe("Conferência de carga na expedição"));
  expect(mapa.getByText("Visível ao cliente")).toBeInTheDocument();
  expect(mapa.getByText(/âncora de 2 achado\(s\) ou dor\(es\) publicado\(s\)/)).toBeInTheDocument();
  expect(mapa.getByRole("button", { name: /^Ocultar do cliente:/ })).toBeDisabled();
  // Publicado não tem caixa: não há o que selecionar para publicar.
  expect(screen.queryByLabelText("Selecionar para publicar: Conferência de carga na expedição")).not.toBeInTheDocument();

  // **Oculto · pronto** — nada falta, e a linha não traz frase de falta.
  const outroMapa = within(linhaDe("Roteirização de entregas"));
  expect(outroMapa.getByText("Oculto do cliente")).toBeInTheDocument();
  expect(outroMapa.queryByText(/^Falta:/)).not.toBeInTheDocument();
  expect(outroMapa.getByLabelText("Selecionar para publicar: Roteirização de entregas")).toBeInTheDocument();

  // **Oculto · bloqueado** — a caixa existe (decisão F1) e a frase diz o que falta.
  const bloqueado = within(linhaDe("O conferente refaz a conferência da carga porque o coletor não sincroniza com o WMS"));
  expect(bloqueado.getByText("Oculto do cliente")).toBeInTheDocument();
  expect(bloqueado.getByText("Falta: ao menos uma evidência publicada e viva")).toBeInTheDocument();
  expect(bloqueado.getByLabelText(/^Selecionar para publicar: O conferente refaz/)).toBeInTheDocument();
  // O selo epistêmico continua na mesma faixa, e o de publicação não o substitui (decisão D1).
  expect(bloqueado.getByText("Fato")).toBeInTheDocument();

  // **Visível · solto** existe no PROVE desta conta? Não: aqui é a oportunidade que é o topo — ela
  // está bloqueada. O contador do cabeçalho é o resumo dos quatro.
  expect(screen.getByText("1 visível ao cliente")).toBeInTheDocument();
  expect(screen.getByText("3 prontos para publicar")).toBeInTheDocument();
  expect(screen.getByText("4 bloqueados")).toBeInTheDocument();
});

test("o item preso não oferece o botão; o solto abre o diálogo antes de executar", async () => {
  const user = userEvent.setup();
  processos = [processo(visivel(1, "Este processo é a âncora de 1 achado(s) ou dor(es) publicado(s). Despublique-os primeiro."))];
  oportunidades = [oportunidade(visivel())];
  stub();
  render(<PublicacaoPage accountId={4} />);
  await screen.findByRole("heading", { name: "Publicação do Discovery — Transportadora Rota Norte" });

  // Habilitar o botão do item preso seria oferecer um `POST` que o servidor nega — o defeito que o
  // `CLAUDE.md` nomeia para o PROVE. A razão fica **na linha**, e não num `title=`.
  expect(screen.getByLabelText("Ocultar do cliente: Conferência de carga na expedição")).toBeDisabled();

  // O solto executa, e passa pelo `ConfirmDialog`: ocultar é retirar do cliente algo que ele já vê.
  await user.click(screen.getByLabelText("Ocultar do cliente: Sincronizar o coletor de expedição com o WMS em tempo real"));
  expect(await screen.findByRole("dialog", { name: "Ocultar do cliente" })).toBeInTheDocument();
  expect(mocks.unpublishImprovementOpportunity).not.toHaveBeenCalled();

  await user.click(screen.getByRole("button", { name: "Ocultar" }));
  await waitFor(() => expect(mocks.unpublishImprovementOpportunity).toHaveBeenCalledWith(40));
});

test("marcar o mapa cascateia para baixo, marcando a subárvore", async () => {
  const user = userEvent.setup();
  discoveryCompleto();
  render(<PublicacaoPage accountId={4} />);
  await screen.findByRole("heading", { name: "Publicação do Discovery — Transportadora Rota Norte" });

  await user.click(screen.getByLabelText("Selecionar para publicar: Roteirização de entregas"));

  // O mapa 2 leva o achado ancorado nele e a evidência que o achado cita.
  expect(screen.getByLabelText(/^Selecionar para publicar: A roteirização manual/)).toBeChecked();
  expect(screen.getByLabelText(/^Selecionar para publicar: Observação \(o que fazem\)/)).toBeChecked();
  expect(screen.getByRole("button", { name: "Publicar selecionados (3)" })).toBeEnabled();
});

test("marcar um filho bloqueado cascateia para cima, levando o que ele precisa que suba antes", async () => {
  const user = userEvent.setup();
  discoveryCompleto();
  render(<PublicacaoPage accountId={4} />);
  await screen.findByRole("heading", { name: "Publicação do Discovery — Transportadora Rota Norte" });

  // A dor precisa de achado publicado; o achado (fato) precisa de evidência publicada. Quem diz o
  // que falta é `publication_state.missing`, do servidor — a tela só segue a cadeia.
  await user.click(screen.getByLabelText(/^Selecionar para publicar: Reemissão de nota fiscal/));

  expect(screen.getByLabelText(/^Selecionar para publicar: O conferente refaz/)).toBeChecked();
  expect(screen.getByLabelText(/^Selecionar para publicar: Entrevista \(o que dizem\)/)).toBeChecked();
  // O mapa 1 já está publicado: ele não entra na fila, e o contador não o conta.
  expect(screen.getByRole("button", { name: "Publicar selecionados (3)" })).toBeEnabled();

  // Desmarcar não desfaz os ancestrais puxados: eles podem valer para outro item ainda marcado.
  await user.click(screen.getByLabelText(/^Selecionar para publicar: Reemissão de nota fiscal/));
  expect(screen.getByRole("button", { name: "Publicar selecionados (2)" })).toBeEnabled();
});

test("o lote sobe na ordem da cadeia, e a falha parcial não desfaz o que passou", async () => {
  const user = userEvent.setup();
  discoveryCompleto();
  mocks.publishFinding.mockRejectedValue(Object.assign(
    new Error("Publicar exige ao menos uma evidência publicada e viva. O que o cliente vê precisa ter sustentação publicada embaixo."),
    { status: 400 },
  ));
  render(<PublicacaoPage accountId={4} />);
  await screen.findByRole("heading", { name: "Publicação do Discovery — Transportadora Rota Norte" });

  await user.click(screen.getByLabelText("Selecionar para publicar: Roteirização de entregas"));
  await user.click(screen.getByLabelText(/^Selecionar para publicar: Reemissão de nota fiscal/));
  await user.click(screen.getByRole("button", { name: /^Publicar selecionados/ }));

  await waitFor(() => expect(mocks.publishPainPoint).toHaveBeenCalled());
  // `Process → Evidence → Finding → PainPoint → ImprovementOpportunity`: a ordem é o único
  // conhecimento de regra que a tela carrega (decisão F1).
  const ordem = [
    mocks.publishProcess.mock.invocationCallOrder[0],
    mocks.publishEvidence.mock.invocationCallOrder[0],
    mocks.publishFinding.mock.invocationCallOrder[0],
    mocks.publishPainPoint.mock.invocationCallOrder[0],
  ];
  expect(ordem).toEqual([...ordem].sort((a, b) => a - b));

  // **Nada é desfeito**: o que subiu ficou, e os dois recusados dizem por quê.
  expect(mocks.unpublishProcess).not.toHaveBeenCalled();
  expect(mocks.unpublishEvidence).not.toHaveBeenCalled();
  const resumo = await screen.findByText(/não foram publicados/);
  expect(resumo).toHaveTextContent(/nada foi desfeito/);
});

test("a frase da recusa é a que veio do servidor — a tela não tem mapa de rótulo", async () => {
  const user = userEvent.setup();
  discoveryCompleto();
  // Uma frase que **não existe** em `publication.py`: se a tela a renderizar tal e qual, ela veio
  // do servidor. É a guarda contra alguém reintroduzir no front o mapa chave→rótulo que a decisão
  // E1 recusa — um mapa em TypeScript escreveria a frase canônica, nunca esta.
  const frase = "Frase inventada só por este teste, vinda inteira do servidor.";
  mocks.publishProcess.mockRejectedValue(Object.assign(new Error(frase), { status: 400 }));
  render(<PublicacaoPage accountId={4} />);
  await screen.findByRole("heading", { name: "Publicação do Discovery — Transportadora Rota Norte" });

  await user.click(screen.getByLabelText("Selecionar para publicar: Roteirização de entregas"));
  await user.click(screen.getByRole("button", { name: /^Publicar selecionados/ }));

  expect(await screen.findByText(frase)).toBeInTheDocument();
  // E **sem** a orientação por código de `erros.ts`: nada mudou desde que a tela carregou, e não há
  // degrau nenhum a conferir — o board desenha a linha com o texto puro do servidor.
  expect(screen.queryByText(/Confira o degrau/)).not.toBeInTheDocument();
});

test("a falta e o impedimento vêm inteiros do servidor, incluindo a contagem", async () => {
  discoveryCompleto();
  achados = [achado(visivel(1, PRESO_PELO_ACHADO))];
  stub();
  render(<PublicacaoPage accountId={4} />);
  await screen.findByRole("heading", { name: "Publicação do Discovery — Transportadora Rota Norte" });

  // A contagem "1 dor(es)" só pode ter vindo de `publication.frase_do_impedimento`: nada na tela
  // sabe contar dependentes, e é essa a fronteira que a decisão E1 desenha.
  expect(screen.getByText(PRESO_PELO_ACHADO)).toBeInTheDocument();
  expect(screen.getByText("Falta: ao menos um achado publicado e vivo")).toBeInTheDocument();
});

test("nada pendente mostra a árvore mesmo assim", async () => {
  processos = [processo(visivel())];
  stub();
  render(<PublicacaoPage accountId={4} />);
  await screen.findByRole("heading", { name: "Publicação do Discovery — Transportadora Rota Norte" });

  // Esconder a lista tiraria a resposta à pergunta que traz alguém aqui: *o que o cliente vê?*
  expect(screen.getByText(/Todo o Discovery desta conta já está visível ao cliente/)).toBeInTheDocument();
  expect(screen.getByText("Conferência de carga na expedição")).toBeInTheDocument();
  expect(screen.getByLabelText("Ocultar do cliente: Conferência de carga na expedição")).toBeEnabled();
});

test("a falha de carga chega traduzida, com a orientação da tabela de erros", async () => {
  conta = Object.assign(new Error("O estado desta conta mudou."), { status: 409 });
  stub();
  render(<PublicacaoPage accountId={4} />);

  expect(await screen.findByRole("alert")).toHaveTextContent(/recarregue para ver o que vale agora/);
});

test("a Entrega fora do escopo da conta lê o motivo, e não um erro genérico", async () => {
  mocks.auth.user = { id: 3, is_admin: false, role: "delivery" };
  conta = Object.assign(new Error("Não encontrado."), { status: 404 });
  stub();
  render(<PublicacaoPage accountId={4} />);

  expect(await screen.findByText("Você não participa de nenhum projeto desta conta.")).toBeInTheDocument();
  expect(screen.queryByRole("alert")).not.toBeInTheDocument();
});
