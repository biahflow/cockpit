/**
 * A matriz de telas — rota × papel — que alimenta `a11y.spec.ts` e `responsive.spec.ts` (FDD 022).
 *
 * Uma tela nova entra na matriz por **uma linha** em `ROUTES`, não por um arquivo de teste novo.
 * É o que impede a matriz de envelhecer: o custo de cobrir a próxima página é uma linha.
 *
 * O mock é um `route` único sobre `/api/v2/**`, resolvido por `pathname` — mesmo padrão dos e2e
 * que já existem (`login.spec.ts`, `dashboard.spec.ts`), que também não sobem backend.
 */

import type { Page, Route } from "@playwright/test";

import type { Role } from "../src/types";

export type Screen = { path: string; name: string; role: Role | null };

export const ROUTES: readonly Screen[] = [
  { path: "/", name: "Visão geral", role: "admin" },
  { path: "/comercial", name: "Comercial", role: "admin" },
  { path: "/contas", name: "Contas", role: "admin" },
  { path: "/contas/1", name: "Detalhe da conta", role: "admin" },
  { path: "/contas/1/processos/1", name: "Processo mapeado", role: "admin" },
  { path: "/contas/1/priorizacao", name: "Priorização", role: "admin" },
  { path: "/contas/1/valor", name: "Valor gerado", role: "admin" },
  { path: "/contas/1/publicacao", name: "Publicação do Discovery", role: "admin" },
  { path: "/projetos", name: "Projetos", role: "admin" },
  { path: "/projetos/1", name: "Detalhe do projeto", role: "admin" },
  { path: "/documentos", name: "Documentos", role: "admin" },
  { path: "/leads", name: "Leads", role: "admin" },
  { path: "/indicadores", name: "Indicadores", role: "admin" },
  { path: "/pipeline", name: "Pipeline", role: "admin" },
  { path: "/jornada", name: "Jornada", role: "admin" },
  { path: "/servicos", name: "Serviços", role: "admin" },
  { path: "/biblioteca", name: "Biblioteca de Funcionários Digitais", role: "admin" },
  { path: "/cases", name: "Cases", role: "admin" },
  { path: "/financeiro", name: "Financeiro", role: "admin" },
  { path: "/cobranca", name: "Cobrança", role: "admin" },
  { path: "/conhecimento", name: "Conhecimento", role: "admin" },
  { path: "/equipe", name: "Equipe", role: "admin" },
  { path: "/configuracoes", name: "Configurações", role: "admin" },
  // Perfil próprio: entra pela Entrega de propósito, que é o papel para quem `/users/` está
  // fechado — se a tela dependesse daquela rota, é aqui que quebraria.
  { path: "/perfil", name: "Meu perfil", role: "delivery" },
  { path: "/design-system", name: "Design system", role: "admin" },
  // Entrega sem projeto: o estado vazio é uma tela de verdade e tem seu próprio texto.
  { path: "/projetos", name: "Projetos (Entrega, sem equipe)", role: "delivery" },
  { path: "/", name: "Login", role: null },
  { path: "/aceitar-convite", name: "Aceitar convite", role: null },
  // Pública e movida a token, como a de cima (DAP `dap-agendamento-discovery-r1`). Cobre o
  // caminho feliz — os cinco estados de exceção são cobertos no vitest de
  // `AgendarDiscoveryPage.test.tsx`, não aqui: a matriz mede uma tela por rota, e o token na URL
  // não tem como selecionar qual resposta o mock devolve.
  { path: "/agendar/tok-e2e", name: "Agendar Discovery", role: null },
];

/**
 * Nome longo de propósito: conteúdo curto cabe em qualquer largura, e uma matriz de
 * responsividade alimentada com "Cliente 1" passaria sem provar nada. Este é o comprimento
 * de uma razão social real.
 */
const NOME_LONGO = "Indústria Metalúrgica São Bernardo do Campo Participações S.A.";

/**
 * A marca de publicável (FDD 051, ADR 0060) e o campo derivado que a tela de publicação consome
 * (DAP `dap-publicacao-discovery-r1`, decisão B1).
 *
 * **Os quatro estados por item entram na amostra**, e não é completude: eles são quatro
 * superfícies diferentes — pastilha escura sólida contra pastilha cinza, frase do impedimento,
 * frase do que falta, caixa de seleção presente ou ausente, botão habilitado ou desabilitado. Um
 * mock com tudo no mesmo estado aprovaria a tela sem que metade dela tivesse renderizado uma vez,
 * que é o modo de falha que o comentário de `/api/v2/processes/` já registra um nível acima.
 */
const visivel = (presos = 0, impedimento = "") => ({
  published_at: `${HOJE}T09:00:00Z`, published_by: 1,
  publication_state: { state: "published", missing: [], missing_phrase: "", blocked_by: presos, blocked_phrase: impedimento },
});
const oculto = (falta?: { chave: string; frase: string }) => ({
  published_at: null, published_by: null,
  publication_state: {
    state: falta ? "blocked" : "ready",
    missing: falta ? [falta.chave] : [], missing_phrase: falta ? falta.frase : "",
    blocked_by: 0, blocked_phrase: "",
  },
});
const FALTA_ACHADO = { chave: "published_finding", frase: "ao menos um achado publicado e vivo" };
const FALTA_DOR = { chave: "published_pain_point", frase: "ao menos uma dor publicada e viva" };
/** Um token sem espaço nem hífen: reproduz o conteúdo que não oferece ponto natural de quebra. */
export const TITULO_DE_LINHA_INQUEBRAVEL = "Inconsistenciacadastralidentificadaautomaticamentenoprocessodefaturamentomensal";
const HOJE = "2026-08-05";
const VENCIDO = "2026-07-01";

const usuarios: Record<Role, unknown> = {
  admin: { id: 1, username: "ana", first_name: "Ana", last_name: "Souza", email: "ana@example.test", role: "admin", is_admin: true },
  sales: { id: 2, username: "bruno", first_name: "Bruno", last_name: "Lima", email: "bruno@example.test", role: "sales", is_admin: false },
  delivery: { id: 3, username: "carla", first_name: "Carla", last_name: "Reis", email: "carla@example.test", role: "delivery", is_admin: false },
};

const serie = <T,>(quantos: number, molde: (indice: number) => T): T[] =>
  Array.from({ length: quantos }, (_, indice) => molde(indice + 1));

const clientes = serie(8, index => ({
  id: index, name: `${NOME_LONGO} — unidade ${index}`, legal_name: NOME_LONGO,
  tax_id: "12.345.678/0001-90", owner: 1,
  // Os três estados vivos entram na amostra: a pílula "Inativo" também precisa passar pelo axe.
  lifecycle_status: index % 3 === 0 ? "inactive" : index % 2 ? "active" : "prospect",
}));

const projetos = serie(8, index => ({
  id: index, name: `Implantação de agentes no faturamento — frente ${index}`, description: "",
  owner: 1, start_date: "2026-05-01", due_date: VENCIDO, status: "active",
  service: null, actual_value: "180000.00", cost: "90000.00", is_overdue: true,
  ai_maturity: 62, ai_potential: 78, ai_dimensions: [{ label: "Dados", score: 55 }],
  ai_score_summary: "Base de dados fragmentada entre ERP e planilhas.",
  ai_scored_at: `${HOJE}T12:00:00Z`, ai_score_reviewed: true,
}));

const etapas = ["Qualificação", "Proposta enviada", "Negociação", "Ganha", "Perdida"].map((name, i) => ({
  id: i + 1, name, kind: i === 3 ? "won" : i === 4 ? "lost" : "open",
  position: i, opportunity_count: 3, estimated_total: "450000.00",
}));

const oportunidades = serie(8, index => {
  // Uma venda ganha e ainda sem mandato alimenta o select da origem contratual no detalhe da
  // Account. As demais preservam a variedade do pipeline; a segunda já vinculada prova que a
  // tela não a oferece de novo.
  const etapa = index === 1 ? etapas[3] : etapas[index % 3];
  return {
    id: index, account: index, contact: null,
    title: `Discovery e assessment de automação — ${NOME_LONGO}`,
    scope: "Mapeamento de processos e desenho de agentes.", estimated_value: "150000.00",
    stage: etapa.id, stage_name: etapa.name, stage_kind: etapa.kind,
    engagement: index === 2 ? 1 : null, owner: 1,
    expected_close_date: HOJE, service: 1, service_name: "Discovery Sprint",
    service_tier: "discovery_sprint", project: null, project_archived: false,
    origin_qualification: null,
  };
});

const itensDeTrabalho = serie(8, index => ({
  id: index, project: 1, title: `Entrevistar área de faturamento — bloco ${index}`,
  description: "", owner: 1, due_date: VENCIDO, completed_at: null,
  status: "todo", party: "provider", is_overdue: true, milestone: null,
}));

const riscos = serie(8, index => ({
  project_id: index, name: projetos[index - 1].name, score: 70, level: "alto",
  signals: [{ label: "Itens atrasados", detail: "3 item(ns) vencido(s)", weight: 30 }],
  forecast: { predicted_finish_date: "2026-09-30", delay_days: 45, basis: "40% concluído em 60 dia(s)" },
}));

// O Discovery estruturado (FDD 039, ADR 0034). `nao_apurado` vai **cheio** de propósito: o aviso
// de que o total é parcial é a superfície mais importante da tela, e um mock com a conta completa
// aprovaria três larguras sem que ele tivesse renderizado uma vez. Um processo sustentado e dois em
// hipótese, para os dois selos aparecerem na lista do detalhe do cliente.
const processos = serie(3, index => ({
  id: index, account: 1, account_name: NOME_LONGO,
  name: `Faturamento manual de notas de serviço — frente ${index}`,
  position: index, source_project: 1, source_meeting: 1, registered_by: 1,
  volume_mes: 400, tempo_horas: "0.50", pessoas: 2, custo_hora: "80.00",
  retrabalho_mes: "3200.00", erros_mes: "1500.00",
  perdas_mes: null, espera_mes: null, risco_mes: null,
  custo: {
    parcelas: [
      { label: "Execução do processo", valor: "32000.00" },
      { label: "Retrabalho", valor: "3200.00" },
      { label: "Erros", valor: "1500.00" },
    ],
    total: "36700.00",
    nao_apurado: ["Perdas", "Espera", "Risco"],
    sustentacao: index === 1 ? "sustentado" : "hipotese",
  },
  // O primeiro mapa é a **âncora** de um achado e de uma dor publicados: é o visível·preso, com o
  // botão desabilitado e a frase do 409 na linha. O segundo está oculto·pronto — e é ele que
  // bloqueia o achado ancorado nele. O terceiro é visível·solto.
  ...(index === 1
    ? visivel(2, "Este processo é a âncora de 2 achado(s) ou dor(es) publicado(s). Despublique-os primeiro.")
    : index === 2 ? oculto() : visivel()),
  created_at: `${HOJE}T09:00:00Z`, updated_at: `${HOJE}T09:00:00Z`,
}));

const processoEtapas = serie(3, index => ({
  id: index, process: 1, processo: 1, position: index,
  name: `Etapa ${index} — conferência manual da nota fiscal no ERP`,
  pessoas: "Analista de faturamento, duas pessoas em revezamento",
  sistema: "ERP Protheus e uma planilha de conferência no Drive",
  dados: "Entra o pedido aprovado; saem a nota emitida e o boleto",
  tempo: "Cerca de 30 minutos por nota",
  // A última etapa vai sem as duas últimas letras de propósito: "Não levantado" é conteúdo de
  // verdade na tela — é a pergunta que a reunião não fez — e precisa ser medido junto com o resto.
  erro: index === 3 ? "" : "CNPJ divergente do cadastro e item de serviço sem código fiscal",
  retrabalho: index === 3 ? "" : "Cancelar a nota e reemitir no dia seguinte, com novo aceite",
}));

// **Um achado de cada classificação**, e não é completude: são três selos diferentes (`state--1`,
// `state--2`, `state--off`) e o botão "Promover a fato", que só existe nos dois que ainda não são
// fato. Sem os três, o axe mediria a tela sem o par que ela não pode deixar parecer a mesma coisa.
// Cada `Finding` (o split, Fase 6) aponta para a `Evidence` de mesmo id, que diz de onde veio.
const findings = [
  { epistemic_status: "fact", epistemic_status_display: "Fato",
    statement: "O ERP registrou 412 notas emitidas no mês passado, com 37 canceladas e reemitidas." },
  { epistemic_status: "hypothesis", epistemic_status_display: "Hipótese",
    statement: TITULO_DE_LINHA_INQUEBRAVEL },
  { epistemic_status: "unknown", epistemic_status_display: "Desconhecido",
    statement: "Ninguém soube dizer quanto tempo a nota espera na fila de aprovação do fiscal." },
].map((registro, indice) => ({
  id: indice + 1, account: 1,
  // O terceiro achado é **ancorado no segundo mapa**, que está oculto: é o que produz o
  // oculto·bloqueado por âncora — "Falta: o processo que ele cita publicado e vivo" —, e é também o
  // que dá à árvore da tela de publicação um segundo mapa com filho, em vez de um só.
  process: indice === 2 ? 2 : 1, step: null, confidence: null,
  reviewed_by: registro.epistemic_status === "fact" ? 1 : null,
  reviewed_at: registro.epistemic_status === "fact" ? `${HOJE}T09:00:00Z` : null,
  evidences: [indice + 1],
  // O fato publicado prende a evidência que o sustenta e é preso pela dor que ele sustenta — os
  // dois lados da cadeia, na mesma linha. A hipótese está pronta; o desconhecido, bloqueado.
  ...(indice === 0
    ? visivel(1, "Este é o último achado publicado e vivo de 1 dor(es) publicada(s). Despublique a dor primeiro, ou publique outro achado.")
    : indice === 1 ? oculto() : oculto({ chave: "published_process", frase: "o processo que ele cita publicado e vivo" })),
  created_at: `${HOJE}T09:00:00Z`, updated_at: `${HOJE}T09:00:00Z`, ...registro,
}));
const evidence = [
  { kind: "data", kind_display: "Dado (volume, tempo, custo, erro)" },
  { kind: "interview", kind_display: "Entrevista (o que dizem)" },
  { kind: "observation", kind_display: "Observação (o que fazem)" },
].map((registro, indice) => ({
  id: indice + 1, account: 1, discovery: null, process: indice === 2 ? 2 : 1, step: null,
  raw_excerpt: "Trecho da fonte.",
  reference: "", source_session: null, source_meeting: 1, captured_at: `${HOJE}T09:00:00Z`,
  captured_by: 1, content_hash: "abc",
  // A primeira é a **última sustentação publicada** do fato publicado: visível·presa, com o botão
  // desabilitado. As outras duas estão ocultas·prontas — a folha da escada não pede nada para subir.
  ...(indice === 0
    ? visivel(1, "Esta é a última evidência publicada e viva de 1 achado(s) publicado(s) como fato. Despublique o achado primeiro, ou publique outra evidência.")
    : oculto()),
  created_at: `${HOJE}T09:00:00Z`, updated_at: `${HOJE}T09:00:00Z`,
  ...registro,
}));

const saude = serie(8, index => ({
  project_id: index, name: projetos[index - 1].name, score: 42, level: "crítico",
  signals: [{ label: "Decisões pendentes", detail: "4 em aberto · 2 aguardando o cliente", weight: 25 }],
}));

/** Rotas exatas → resposta. O que não casar cai no default por método (lista vazia). */
/** As leituras de cada KPI. O 22 **não tem baseline**: é o `—` que nunca pode virar `0`. */
const MEDICOES_POR_KPI: Record<string, unknown[]> = {
  "21": [
    { id: 30, kpi: 21, kind: "baseline", kind_display: "Baseline", value: "260.00", measured_at: "2026-07-03T10:00:00Z" },
    { id: 32, kpi: 21, kind: "outcome", kind_display: "Outcome", value: "85.00", measured_at: "2026-07-17T10:00:00Z" },
    { id: 31, kpi: 21, kind: "outcome", kind_display: "Outcome", value: "65.00", measured_at: "2026-07-24T10:00:00Z" },
  ],
  "22": [
    { id: 33, kpi: 22, kind: "outcome", kind_display: "Outcome", value: "68.00", measured_at: "2026-07-24T10:00:00Z" },
  ],
};

const FIXTURES: Record<string, unknown> = {
  "/api/v2/auth/csrf/": { csrfToken: "test" },
  // O caminho feliz de `/agendar/:token` (DAP `dap-agendamento-discovery-r1`, decisão B1):
  // horários em dois dias, para o axe medir os dois cabeçalhos de dia e a grade de pastilhas.
  "/api/v2/booking/discovery/slots/": {
    account: "Rio Home Care",
    slots: ["2026-09-10T13:00:00Z", "2026-09-10T15:00:00Z", "2026-09-11T13:00:00Z"],
    scheduled_at: null,
  },
  // As sete flags que `flags.FLAGS` serve, e **com `missing`** — o campo nasceu na ADR 0018, a
  // `SettingsPage` passou a fazer `flag.missing.join()` e esta fixture ficou para trás, estourando
  // a tela em toda varredura. Passou despercebido porque o `ErrorBoundary` também tem `<h1>` e a
  // matriz media o cartão de erro; a trava de `fixtures.ts` existe por causa disto. Duas
  // integrações ficam sem credencial de propósito: é o caminho que estourava, e é o que exercita o
  // texto "Falta no ambiente: X" — o mais longo da tela, que é o que a largura precisa aguentar.
  "/api/v2/config/": {
    ai_enabled: true, calendar_enabled: false, esign_enabled: true,
    // Fora de `integrations` de propósito (DAP `dap-assinatura-com-papeis-r1`, D1): é o e-mail com
    // que a casa assina, e é ele que faz a linha fixa "Você (Biahflow)" existir na rodada.
    esign_house_signer_email: "daniel@biahflow.ai",
    integrations: [
      { key: "ai", label: "Assistente de IA", enabled: true, configured: true, toggleable: true, missing: [] },
      { key: "drive", label: "Documentos no Google Drive", enabled: false, configured: false, toggleable: true, missing: ["GOOGLE_DRIVE_ROOT_FOLDER_ID"] },
      { key: "calendar", label: "Calendário (Google)", enabled: false, configured: false, toggleable: true, missing: ["GOOGLE_CALENDAR_ID", "GOOGLE_OAUTH_REFRESH_TOKEN"] },
      { key: "esign", label: "Assinatura eletrônica", enabled: true, configured: true, toggleable: true, missing: [] },
      { key: "email", label: "Notificações por e-mail e digest", enabled: true, configured: true, toggleable: true, missing: [] },
      { key: "tasksync", label: "Sincronia de tarefas (Linear/GitHub)", enabled: false, configured: true, toggleable: true, missing: [] },
      { key: "portal", label: "Portal do cliente", enabled: true, configured: true, toggleable: true, missing: [] },
      // A régua de cobrança (FDD 036), **desligada e sem credencial faltando** — que é a
      // combinação que nenhuma outra linha desta fixture exercita: as outras desligadas devem
      // isso a variável ausente, e esta é a única cujo `enabled: false` é uma decisão.
      { key: "cobranca", label: "Régua de cobrança", enabled: false, configured: true, toggleable: true, missing: [] },
    ],
  },
  "/api/v2/dashboard/": {
    pipeline: etapas, active_projects: 12, overdue_count: 5,
    upcoming_tasks: itensDeTrabalho.slice(0, 5).map(item => ({
      id: item.id, title: item.title, due_date: item.due_date, project_id: 1,
    })),
  },
  "/api/v2/accounts/": clientes,
  "/api/v2/accounts/1/": clientes[0],
  "/api/v2/accounts/overview/": {
    // `client_id` e `status` (redundante com `lifecycle_status`) dentro de cada linha somem da
    // v2 desde a fatia 4c (ADR 0066, emenda da fatia 4a): é dict cru sem item tipado no esquema
    // — a dívida era de resposta, não de contrato —, mas a resposta em si já não os emite mais
    // aqui. `accounts:` é a chave que **envolve** a lista, trocada desde a fatia 4a — era
    // `clients:` na v1.
    accounts: clientes.map(cliente => ({
      account_id: cliente.id, name: cliente.name,
      lifecycle_status: cliente.lifecycle_status,
      roi: { revenue: "180000.00", cost: "90000.00", roi: 1 },
      health: { score: 42, level: "crítico", project_id: cliente.id },
      risk_level: "alto", phase: { name: "Implantação assistida", status: "active" },
      next_meeting: { title: "Comitê quinzenal de acompanhamento", date: HOJE },
      ai_score: { maturity: 62, opportunity: 78, dimensions: [{ label: "Dados", score: 55 }],
        summary: "Base fragmentada.", scored_at: `${HOJE}T12:00:00Z` },
    })),
  },
  "/api/v2/accounts/1/overview/": {
    account_id: 1, name: clientes[0].name, lifecycle_status: "active",
    roi: { revenue: "180000.00", cost: "90000.00", roi: 1 },
    health: { score: 42, level: "crítico", project_id: 1 },
    risk_level: "alto", phase: { name: "Implantação assistida", status: "active" },
    next_meeting: { title: "Comitê quinzenal de acompanhamento", date: HOJE },
    ai_score: null,
  },
  // O próximo passo da conta (FDD 054, decisão B1). Um degrau de verdade, e não o vazio: o painel
  // com conteúdo é o que a matriz precisa medir — dois selos e um título longo na mesma faixa é
  // exatamente onde 390px quebra, e o vazio não exercitaria nem o contraste do par de pastilhas.
  "/api/v2/accounts/1/next-step/": {
    next_step: {
      improvement_opportunity: 77,
      title: "Reconciliação manual de repasses entre a operadora e as unidades",
      score: "78.00", assessment_version: 2, missing: "choose_hypothesis",
    },
    ranked_count: 3,
  },
  "/api/v2/projects/": projetos,
  "/api/v2/projects/1/": projetos[0],
  "/api/v2/projects/1/risk/": riscos[0],
  "/api/v2/projects/1/health/": saude[0],
  "/api/v2/commercial-opportunities/": oportunidades,
  "/api/v2/pipeline-stages/": etapas,
  "/api/v2/milestones/": itensDeTrabalho,
  "/api/v2/tasks/": itensDeTrabalho,
  "/api/v2/risk/": { projects: riscos },
  "/api/v2/health/": { projects: saude },
  "/api/v2/recommendations/": {
    items: serie(5, index => ({
      kind: "followup", label: `Retomar contato com ${NOME_LONGO}`,
      detail: "Sem interação registrada há 21 dias.", url: `/contas/${index}`,
    })),
  },
  "/api/v2/services/": serie(4, index => ({
    id: index, name: index === 1 ? "Discovery Sprint" : `Serviço avulso ${index}`,
    active: true, tier: index === 1 ? "discovery_sprint" : "",
    tier_display: index === 1 ? "Discovery Sprint" : "", list_price: "0.00",
    category: "commercial", category_display: "Comercial",
    summary: "Diagnóstico inicial gratuito de oportunidades de automação.",
  })),
  "/api/v2/leads/": serie(8, index => ({
    id: index, name: `Contato ${index}`, email: `contato${index}@empresa.test`,
    company: NOME_LONGO, phone: "(11) 99999-0000",
    message: "Gostaria de entender como reduzir o retrabalho no faturamento.",
    source: "site", status: "new", ai_fit: "high", ai_score: 82,
    ai_summary: "Dor clara em processo manual, porte compatível.",
    ai_recommended_action: "Agendar discovery express.",
    qualified_at: null, commercial_opportunity: null,
    qualification: null,
    qualification_outcome: "", created_at: `${HOJE}T09:00:00Z`,
  })),
  "/api/v2/documents/": serie(6, index => ({
    id: index, account: index, commercial_opportunity: null,
    project: null,
    file: "/media/x.pdf",
    drive_link: "", original_name: `Contrato de prestação de serviços — ${NOME_LONGO}.pdf`,
    uploaded_by: 1, created_at: `${HOJE}T09:00:00Z`, originated_engagement: null,
    // A conta-dona derivada (decisão B1) é o que faz o modal buscar os contatos; e **um** dos seis
    // sem posicionamento, porque o `.alert--warn` do aviso E1 é cor nova e precisa entrar na
    // varredura de contraste do axe — o modal só abre a partir da primeira linha.
    owning_account: index,
    signature_positioning_gap: index === 1 ? "not_pdf" : null,
    signature_requests: index === 1
      ? [{ id: 1, signer_email: "juridico@empresa.test", signer_role: "counterparty", status: "signed", sign_url: "https://exemplo.test/s/1", reminded_at: null, signed_at: `${HOJE}T10:00:00Z`, created_at: `${HOJE}T09:00:00Z` }]
      : [],
  })),
  "/api/v2/verticals/": serie(5, index => ({
    id: index, name: `Setor ${index} — indústria metalúrgica de base`, slug: `setor-${index}`,
    position: index, active: true,
  })),
  "/api/v2/digital-employee-blueprints/": serie(4, index => ({
    id: index, name: `SDR de ${NOME_LONGO}`, area: "commercial", area_display: "Comercial",
    description: "Qualifica lead fora do horário comercial e agenda a reunião de discovery.",
    kpi_label: "Leads qualificados por mês", kpi_unit: "count", kpi_direction: "up",
    default_hours_saved_month: "40.0",
    default_roi_month: "8000.00", service: null, service_name: "", active: true,
    variants: serie(2, v => ({
      id: v, blueprint: index, vertical: v, vertical_name: `Setor ${v} — indústria metalúrgica de base`,
      description: "Ajustado ao vocabulário do setor.", kpi_label: "",
      default_hours_saved_month: null, default_roi_month: null,
    })),
    resolved: null, has_variant: false,
  })),
  "/api/v2/cases/": serie(4, index => ({
    id: index, project: index, project_name: `Implantação de agentes — frente ${index}`,
    title: `${NOME_LONGO} — implantação de agentes no faturamento`,
    summary: "Triplicou a qualificação de leads e cortou o tempo de resposta pela metade.",
    vertical: 1, vertical_name: "Setor 1 — indústria metalúrgica de base",
    account_name: NOME_LONGO,
    metrics: serie(3, m => ({
      employee_id: m, blueprint_id: m, name: `SDR de ${NOME_LONGO}`, area: "Comercial",
      kpi_label: "Leads qualificados por mês", kpi_unit: "count", kpi_direction: "up",
      // A terceira linha vai sem base de propósito: o estado "sem base registrada" é conteúdo
      // de verdade na tela e precisa ser medido pela matriz junto com o resto.
      baseline: m === 3 ? null : "12.00", current: "48.00", has_baseline: m !== 3,
      kpi_value: "", hours_saved_month: "40.0",
    })),
    health_snapshot: { score: 82, level: "saudável", signals: [{ label: "Decisões pendentes", detail: "2 em aberto", weight: 10 }] },
    roi_snapshot: { revenue: "180000.00", cost: "90000.00", roi: 1 },
    status: index === 1 ? "published" : "draft",
    status_display: index === 1 ? "Publicado" : "Rascunho",
    published_at: index === 1 ? `${HOJE}T12:00:00Z` : null,
    account_consent: index === 1, consent_recorded_at: index === 1 ? `${HOJE}T11:00:00Z` : null,
    consent_recorded_by: index === 1 ? 1 : null, anonymized: false,
    created_at: `${HOJE}T10:00:00Z`, updated_at: `${HOJE}T10:00:00Z`,
  })),
  // Uma fatura de cada estado que a tela desenha, incluindo a vencida — o pior caso de
  // comprimento é a linha vermelha com selo, valor e data juntos.
  "/api/v2/invoices/": serie(5, index => ({
    id: index, account: 1, account_name: NOME_LONGO,
    project: index, project_name: `Implantação de agentes — frente ${index}`,
    service: 1, service_name: "Implantação",
    number: index === 1 ? "" : `2026-000${index}`,
    amount: "48750.90", description: "Implantação — parcela de go-live do faturamento",
    due_date: HOJE, method: index === 4 ? "pix" : "", method_display: index === 4 ? "Pix" : "",
    status: ["draft", "issued", "overdue", "paid", "cancelled"][index - 1],
    status_display: ["Rascunho", "Emitida", "Vencida", "Paga", "Cancelada"][index - 1],
    is_overdue: index === 3,
    issued_at: index === 1 ? null : `${HOJE}T10:00:00Z`, issued_by: index === 1 ? null : 1,
    paid_at: index === 4 ? `${HOJE}T11:00:00Z` : null, settled_by: index === 4 ? 1 : null,
    cancelled_at: index === 5 ? `${HOJE}T12:00:00Z` : null, cancelled_by: index === 5 ? 1 : null,
    cancel_reason: index === 5 ? "Escopo renegociado com o cliente antes do go-live" : "",
    provider: "", external_reference: "", payment_url: index === 2 ? "https://pay.example.test/i/2" : "",
    created_at: `${HOJE}T09:00:00Z`, updated_at: `${HOJE}T09:00:00Z`,
  })),
  // A régua de cobrança (FDD 036). `regua_ligada: false` **é o estado que o produto entrega**: a
  // flag nasce desligada porque a reconciliação que a desarma nunca foi homologada. É também o que
  // rende mais superfície nova para o axe medir — a faixa de aviso neutro e os botões desabilitados
  // com o motivo à vista, que é o texto mais longo desta tela.
  //
  // Uma linha por motivo de silêncio, mais uma com degrau: o `motivo` é o que a tela traduz, e um
  // mock com um só valor aprovaria quatro textos que nunca renderizaram.
  "/api/v2/cobranca/painel/": [
    { motivo: "", degrau: "reminder", rotulo: "Lembrete", dias: 4, suspensa: false },
    { motivo: "suspensa", degrau: null, rotulo: null, dias: 12, suspensa: true },
    { motivo: "degrau_gasto", degrau: null, rotulo: null, dias: 3, suspensa: false },
    { motivo: "teto_de_frequencia", degrau: null, rotulo: null, dias: 21, suspensa: false },
    { motivo: "sem_degrau", degrau: null, rotulo: null, dias: -2, suspensa: false },
  ].map((caso, indice) => ({
    invoice: indice + 1, number: `2026-00${indice + 1}0`, account: 1, account_name: NOME_LONGO,
    amount: "48750.90", due_date: VENCIDO,
    status: caso.dias > 0 ? "overdue" : "issued",
    status_display: caso.dias > 0 ? "Vencida" : "Emitida",
    dias_de_atraso: caso.dias, payment_url: indice === 0 ? "https://pay.example.test/i/1" : "",
    proximo_degrau: caso.degrau, proximo_degrau_display: caso.rotulo,
    proximo_degrau_em: caso.degrau ? HOJE : null,
    motivo: caso.motivo,
    // A terceira linha vai sem projeto ativo de propósito: "sem projeto ativo neste cliente" é
    // conteúdo de verdade na tela e precisa ser medido junto com o resto. A segunda vai crítica
    // pela razão oposta: é a que entra tensa **por entrega**, e um "atenção" ali deixaria o mock
    // incoerente justamente onde a FDD 038 exige que a tela não contradiga o relógio.
    health_level: indice === 2 ? null : ["saudável", "crítico", "crítico", "saudável", "atenção"][indice],
    tempo_de_casa_dias: [1460, 200, 45, 20, 900][indice],
    reincidente: indice % 2 === 1,
    // Uma régua de cada (FDD 037): a terceira linha entra tensa, com satisfação declarada
    // insatisfeita vigente — a única combinação que rende o selo `state--3` novo na tela.
    regua: indice === 0 || indice === 4 ? "relacao_longa" : indice === 1 || indice === 2 ? "relacao_tensa" : "padrao",
    recebido_do_cliente: "180000.00",
    // A satisfação vigente (FDD 037). Uma linha declarada insatisfeita (a que carrega a régua
    // tensa), uma percebida promotora e as demais sem registro — o axe precisa medir o selo
    // `.state` e o rótulo de fonte nos dois casos, e o card sem satisfação nenhuma.
    satisfacao_nivel: indice === 2 ? "dissatisfied" : indice === 4 ? "promoter" : null,
    satisfacao_fonte: indice === 2 ? "declared" : indice === 4 ? "perceived" : null,
    satisfacao_dias: indice === 2 ? 5 : indice === 4 ? 40 : null,
    // A causa da tensão (FDD 038). A terceira linha é tensa por satisfação declarada; a segunda
    // entra tensa **por entrega**, que é a combinação que rende o texto mais longo da faixa e a
    // única em que a causa aparece sem satisfação nenhuma na linha.
    tensao_causa: indice === 2 ? "satisfacao" : indice === 1 ? "entrega" : null,
    // O sinal por registrar (FDD 038): selo neutro, data e o botão do atalho — superfície nova, e o
    // axe precisa medir o contraste dela ao lado do selo colorido da satisfação vigente, que é
    // justamente o par que a tela não pode deixar parecer a mesma coisa.
    sinal_kind: indice === 1 ? "dissatisfied" : indice === 3 ? "unable_to_pay" : null,
    sinal_display: indice === 1 ? "Insatisfeito" : indice === 3 ? "Não pôde pagar" : null,
    sinal_em: indice === 1 || indice === 3 ? VENCIDO : null,
    sinal_activity: indice === 1 ? 11 : indice === 3 ? 13 : null,
    suspensao: caso.suspensa
      ? { id: 1, until: "2026-09-30", owner: 1, owner_name: "Maria de Lourdes Albuquerque" }
      : null,
    regua_ligada: false,
  })),
  "/api/v2/cobranca/": serie(2, index => ({
    id: index, invoice: 1, invoice_number: "2026-0010", account: 1, client_name: NOME_LONGO,
    dunning_step: index === 1 ? "pre_notice" : "reminder",
    dunning_step_display: index === 1 ? "Pré-aviso" : "Lembrete",
    canal: "email", canal_display: "E-mail ao cliente", sent_on: HOJE,
    subject: `Fatura 2026-0010 em aberto — ${NOME_LONGO}`,
    to_email: "financeiro@empresa.test", body: "Olá, passando para lembrar…",
    sent_by: index === 1 ? null : 1, ai_interaction: null, created_at: `${HOJE}T09:00:00Z`,
  })),
  // A interação com sinal de cobrança lavrado (FDD 036, camada 4): sem ela a linha do sinal na
  // timeline do cliente nunca renderiza, e a matriz aprovaria uma superfície que não abriu.
  "/api/v2/activities/": serie(3, index => ({
    id: index, account: 1, commercial_opportunity: null,
    invoice: index === 1 ? 1 : null,
    dunning_signal: index === 1 ? "unable_to_pay" : "",
    dunning_signal_display: index === 1 ? "Não pôde pagar" : "",
    kind: "call", kind_display: "Ligação", happened_on: HOJE,
    summary: `Retorno do financeiro sobre a fatura em aberto — ${NOME_LONGO}`,
    notes: "Pediu para reprogramar o pagamento para o próximo ciclo de faturamento.",
    owner: 1, created_at: `${HOJE}T09:00:00Z`, updated_at: `${HOJE}T09:00:00Z`,
  })),
  // A satisfação do cliente (FDD 037, ADR 0032): uma declarada e uma percebida, para o axe medir
  // o selo de nível e o rótulo de fonte nos dois casos — sem as duas, o painel de Satisfação do
  // detalhe do cliente renderiza sempre a mesma metade da tela.
  "/api/v2/satisfaction-records/": [
    { nivel: "dissatisfied", nivel_display: "Insatisfeito", fonte: "declared", fonte_display: "Declarada pelo cliente", happened_on: HOJE, note: "Reclamou do prazo da última entrega na call de comitê." },
    { nivel: "promoter", nivel_display: "Promotor", fonte: "perceived", fonte_display: "Percebida por quem entrega", happened_on: VENCIDO, note: "" },
  ].map((registro, indice) => ({
    id: indice + 1, account: 1, project: null, source_meeting: null,
    registered_by: 1, created_at: `${HOJE}T09:00:00Z`, updated_at: `${HOJE}T09:00:00Z`,
    ...registro,
  })),
  // O Discovery estruturado (FDD 039). **A chave é o pathname exato, com barra final**: uma rota
  // não mapeada cai no fallback de lista vazia, nunca em 404, então uma chave errada aqui passa em
  // silêncio e a matriz aprova uma tela que renderizou só o estado vazio.
  "/api/v2/processes/": processos,
  // A cadeia do PRIORITIZE (FDD 048), na tela que o DAP `dap-priorizacao-r1` aprovou.
  // **Uma linha de cada combinação que a tela sabe desenhar**, e não quatro iguais: a dor solta e
  // a já agrupada, a oportunidade ranqueada com versão e a **sem avaliação nenhuma** — que é a que
  // rende o `—` e a linha sem pílula de versão. Sem ela, o axe mediria a tela sem o par que ela
  // não pode deixar parecer a mesma coisa: "avaliada e vale zero" e "ninguém avaliou".
  //
  // Sem estas chaves as rotas cairiam no fallback de lista vazia e a matriz aprovaria o estado
  // vazio no lugar da tela — o modo de falha que o comentário de `/api/v2/processes/` registra.
  "/api/v2/pain-points/": [
    { id: 1, title: "Retrabalho na conciliação de pagamentos de convênio dos três maiores planos",
      impact_type: "financial", impact_type_display: "Financeiro", findings: [1, 2] },
    { id: 2, title: "Agenda dupla por falha de sincronização entre as unidades da rede",
      impact_type: "operational", impact_type_display: "Operacional", findings: [1] },
    { id: 3, title: "Tempo de espera na recepção acima de quarenta minutos em dia de pico",
      impact_type: "experience", impact_type_display: "Experiência", findings: [1] },
  ].map((registro, indice) => ({
    account: 1, process: 1, step: null, description: "", impact_estimate: null,
    status: "observed", status_display: "Observado",
    // A primeira só cita o achado que ainda não subiu: oculta·bloqueada. A segunda cita o fato
    // publicado e está oculta·pronta. A terceira é visível·presa pela oportunidade que a agrupa.
    ...(indice === 0 ? oculto(FALTA_ACHADO) : indice === 1 ? oculto()
      : visivel(1, "Esta é a última dor publicada e viva de 1 oportunidade(s) de melhoria publicada(s). Despublique a oportunidade primeiro, ou publique outra dor.")),
    created_at: `${HOJE}T09:00:00Z`, updated_at: `${HOJE}T09:00:00Z`, ...registro,
  })),
  "/api/v2/improvement-opportunities/": [
    { id: 1, title: "Padronizar o checklist de documentação exigida para faturamento TISS",
      pain_points: [3], status: "prioritized", status_display: "Priorizada",
      score: "78.00", assessment_version: 2, rank: 1 },
    { id: 2, title: "Automatizar a confirmação de agendamento por WhatsApp em todas as unidades",
      pain_points: [1], status: "assessing", status_display: "Em avaliação",
      score: "64.00", assessment_version: 1, rank: 2 },
    // A que ninguém avaliou: score, versão e rank saem **nulos juntos**, e é o `—` do desenho.
    { id: 3, title: "Consolidar o prontuário eletrônico entre as unidades da rede",
      pain_points: [], status: "open", status_display: "Aberta",
      score: null, assessment_version: null, rank: null },
  ].map((registro, indice) => ({
    account: 1, engagement: null, desired_change: "", impact_hypothesis: "",
    // O topo da escada: a primeira é **visível·solta** — nada pende dela, e o botão de ocultar
    // dela é o único habilitado da tela. As outras duas estão bloqueadas por falta de dor
    // publicada, e é a segunda que mostra a caixa de seleção **vazia** num item bloqueado.
    ...(indice === 0 ? visivel() : oculto(FALTA_DOR)),
    created_at: `${HOJE}T09:00:00Z`, updated_at: `${HOJE}T09:00:00Z`, ...registro,
  })),
  "/api/v2/priority-assessments/": [
    { id: 2, version: 2, impact: 4, evidence_strength: 5, feasibility: 3, time_to_value: 4,
      economics: 3, score: "78.00", created_at: `${HOJE}T09:00:00Z`,
      rationale: "As glosas de TISS são o maior item do custo do estado atual do faturamento." },
    { id: 1, version: 1, impact: 3, evidence_strength: 3, feasibility: 3, time_to_value: 3,
      economics: 2, score: "56.00", created_at: "2026-07-02T09:00:00Z", rationale: "" },
  ].map(registro => ({
    improvement_opportunity: 1, formula_key: "v1", weights: {}, assessed_by: 1,
    updated_at: `${HOJE}T09:00:00Z`, ...registro,
  })),
  // As três situações da hipótese, para os três selos passarem pelo axe (decisão D1).
  "/api/v2/solution-hypotheses/": [
    { id: 1, statement: "Padronizar um checklist único de documentos por convênio", status: "chosen", status_display: "Escolhida" },
    { id: 2, statement: "Implementar OCR na entrada de guias para conferência automática", status: "proposed", status_display: "Proposta" },
    { id: 3, statement: "Terceirizar a auditoria de glosas para escritório especializado", status: "discarded", status_display: "Descartada" },
  ].map(registro => ({
    improvement_opportunity: 1, intervention: "", assumptions: "", expected_effect: "",
    created_at: `${HOJE}T09:00:00Z`, updated_at: `${HOJE}T09:00:00Z`, ...registro,
  })),
  // Feasibility, PROVE, KPI/medição e Value Ledger (FDD 049), nas superfícies que o DAP
  // `dap-prove-e-valor-r1` aprovou. **Uma linha de cada combinação que a tela sabe desenhar**: os
  // três vereditos do laudo, o experimento planejado com dois dos três requisitos faltando (as
  // pastilhas `Pronto`/`Falta` e o botão desabilitado), o KPI com o par completo e o **sem
  // baseline** — que é o `— → 65` com a variação vazia, o estado que o pacote inteiro existe para
  // preservar. Sem ele o axe mediria só a metade bonita da tela.
  "/api/v2/feasibility-assessments/": [{
    id: 1, solution_hypothesis: 1, project: 1,
    technical_verdict: "favorable", technical_verdict_display: "Favorável",
    technical_note: "A integração com o CRM sustenta o volume de pico sem timeout em 93% das chamadas simuladas.",
    operational_verdict: "caveat", operational_verdict_display: "Com ressalva",
    operational_note: "O time de N1 precisa de um fallback humano para tickets ambíguos — sem ele, a fila trava.",
    economic_verdict: "unfavorable", economic_verdict_display: "Desfavorável",
    economic_note: "O custo de inferência por ticket ainda supera o custo humano equivalente na mesma tarefa.",
    sample: "312 tickets analisados na simulação de 15 dias corridos.",
    error_classes: "Classificação incorreta em tickets ambíguos (7%) · timeout de integração em picos (3%).",
    evidence: [1, 2, 3], gate_decision: "conditional_go", gate_decision_display: "CONDITIONAL GO",
    created_at: `${HOJE}T09:00:00Z`, updated_at: `${HOJE}T09:00:00Z`,
  }],
  "/api/v2/prove-experiments/": [{
    id: 9, solution_hypothesis: 1, project: 1,
    controlled_scope: "Rotear tickets do time de Suporte N1 durante o expediente comercial, com fallback humano automático.",
    started_at: null, ended_at: null, success_criteria: "",
    status: "planned", status_display: "Planejado",
    gate_decision: "", gate_decision_display: "",
    gap_waiver: "", gap_waiver_by: null, gap_waiver_at: null,
    missing_to_start: ["success_criteria", "baseline"],
    created_at: `${HOJE}T09:00:00Z`, updated_at: `${HOJE}T09:00:00Z`,
  }],
  "/api/v2/kpis/": [
    { id: 21, name: "Tempo de resposta", unit: "hours", unit_display: "Horas", direction: "down", direction_display: "Menor é melhor" },
    { id: 22, name: "Taxa de resolução no primeiro contato", unit: "percent", unit_display: "Percentual", direction: "up", direction_display: "Maior é melhor" },
  ].map(registro => ({
    project: 1, prove_experiment: 9, definition: "", formula: "", data_source: "", cadence: "",
    owner: null, target: null, created_at: `${HOJE}T09:00:00Z`, updated_at: `${HOJE}T09:00:00Z`,
    ...registro,
  })),
  "/api/v2/kpis/21/": { id: 21, project: 1, prove_experiment: 9, name: "Tempo de resposta", definition: "", formula: "", unit: "hours", unit_display: "Horas", direction: "down", direction_display: "Menor é melhor", data_source: "", cadence: "", owner: null, target: null, created_at: `${HOJE}T09:00:00Z`, updated_at: `${HOJE}T09:00:00Z` },
  "/api/v2/measurements/31/": { id: 31, kpi: 21, kind: "outcome", kind_display: "Outcome", value: "65.00", period_start: "2026-07-01", period_end: "2026-07-31", measured_at: "2026-07-24T10:00:00Z", source_evidence: [], confidence: null, created_at: `${HOJE}T09:00:00Z`, updated_at: `${HOJE}T09:00:00Z` },
  "/api/v2/solution-hypotheses/1/": {
    id: 1, improvement_opportunity: 1,
    statement: "Padronizar um checklist único de documentos por convênio",
    intervention: "", assumptions: "", expected_effect: "",
    status: "chosen", status_display: "Escolhida",
    created_at: `${HOJE}T09:00:00Z`, updated_at: `${HOJE}T09:00:00Z`,
  },
  // O Value Ledger de `/contas/1/valor`: uma aprovada, uma pendente e um rascunho **sem montante
  // apurado** — o `—` que não pode virar `R$ 0`, e a razão de a linha do total dizer o que ficou
  // de fora.
  "/api/v2/value-ledger-entries/": [
    { id: 51, outcome_measurement: 31, value_type: "cost_saving", value_type_display: "Redução de custo",
      amount: "18400.00", period_start: "2026-07-01", period_end: "2026-07-31",
      attribution_method: "direta (medição do PROVE)", status: "approved", status_display: "Aprovado",
      approved_by: 1, approved_at: `${HOJE}T09:00:00Z` },
    { id: 52, outcome_measurement: 31, value_type: "capacity", value_type_display: "Capacidade",
      amount: "6200.00", period_start: "2026-08-01", period_end: "2026-08-31",
      attribution_method: "estimada (projeção linear)", status: "pending", status_display: "Pendente",
      approved_by: null, approved_at: null },
    { id: 53, outcome_measurement: 31, value_type: "risk_reduction", value_type_display: "Redução de risco",
      amount: null, period_start: "2026-06-01", period_end: "2026-08-31",
      attribution_method: "qualitativa, ainda sem apuração", status: "draft", status_display: "Rascunho",
      approved_by: null, approved_at: null },
  ].map(registro => ({
    engagement: 1, project: 1, quantity: null,
    created_at: `${HOJE}T09:00:00Z`, updated_at: `${HOJE}T09:00:00Z`, ...registro,
  })),
  "/api/v2/processes/1/": processos[0],
  "/api/v2/process-steps/": processoEtapas,
  "/api/v2/findings/": findings,
  "/api/v2/evidence/": evidence,
  "/api/v2/knowledge-pieces/": serie(5, index => ({
    id: index, area: 1, area_name: "Operação",
    owner_name: index === 5 ? "" : "Maria de Lourdes Albuquerque",
    title: `Runbook — homologação de integrações e sondas do fornecedor ${index}`,
    kind: "procedure", kind_display: "Procedimento",
    source_path: index === 4 ? "" : `docs/runbooks/homologacao-${index}.md`,
    summary: "", last_verified_at: index === 2 ? null : HOJE, verified_by: 1,
    review_interval_days: 90,
    status: ["sem_dono", "vencido", "a_vencer", "corrente", "sem_dono"][index - 1],
    next_review_at: index === 2 ? null : HOJE, is_gap: index === 4,
    created_at: `${HOJE}T09:00:00Z`, updated_at: `${HOJE}T09:00:00Z`,
  })),
  "/api/v2/knowledge-pieces/summary/": { sem_dono: 2, vencido: 1, a_vencer: 1, corrente: 1 },
  "/api/v2/knowledge-areas/": serie(3, index => ({
    id: index, name: ["Operação", "Produto", "Comercial"][index - 1],
    slug: ["operacao", "produto", "comercial"][index - 1],
    position: index * 10, active: true,
    owner: index === 1 ? 1 : null,
    owner_name: index === 1 ? "Maria de Lourdes Albuquerque" : "",
    review_interval_days: 180,
  })),
  "/api/v2/invoices/summary/": {
    open: "97501.80", overdue: "48750.90", paid: "48750.90",
    open_count: 2, overdue_count: 1, paid_count: 1,
  },
  "/api/v2/journey-phases/": serie(5, index => ({
    id: index, name: `Fase ${index} — implantação assistida`, description: "", active: true,
    position: index, deliverables: serie(3, d => ({ id: d, phase: index, name: `Entregável ${d}`, position: d })),
    // FDD 033: o contrato passou a enviar sempre os dois campos do gate; uma fase com gate e
    // checklist para a tela renderizar as superfícies novas nas três larguras.
    requires_gate: index === 2,
    checklist_items: index === 2
      ? serie(2, c => ({ id: c, phase: index, text: `Item de qualidade ${c}`, position: c }))
      : [],
  })),
  "/api/v2/analytics/": {
    funnel: {
      leads: { total: 40, by_status: { new: 12, contacted: 10, qualified: 14, discarded: 4 } },
      opportunities: { open: 9, won: 6, lost: 3 },
      projects: { total: 12, by_status: { active: 8, completed: 4 } },
      by_tier: [
        { tier: "discovery_sprint", label: "Discovery Sprint", total: 10, open: 4, won: 5, lost: 1, estimated_total: "0.00", win_rate: 0.83 },
        { tier: "feasibility", label: "Technical Feasibility (T.O.E.)", total: 8, open: 3, won: 4, lost: 1, estimated_total: "320000.00", win_rate: 0.8 },
        { tier: "prove", label: "PROVE (piloto)", total: 5, open: 2, won: 2, lost: 1, estimated_total: "900000.00", win_rate: 0.67 },
      ],
      by_stage: [
        { kind: "discovery", label: "Discovery", total: 12, sent: 10, accepted: 8, rejected: 1, acceptance_rate: 0.8, reached: 12 },
        { kind: "assessment", label: "Assessment", total: 9, sent: 8, accepted: 6, rejected: 2, acceptance_rate: 0.75, reached: 9 },
        { kind: "proposal", label: "Proposta", total: 7, sent: 7, accepted: 5, rejected: 2, acceptance_rate: 0.71, reached: 7 },
        { kind: "contract", label: "Contrato", total: 5, sent: 5, accepted: 5, rejected: 0, acceptance_rate: 1, reached: 5 },
      ],
      // Os seis ganhos de `opportunities.won` distribuídos por origem: a matriz mede contraste e
      // rolagem, mas um mock que não reconcilia com o funil de cima seria a própria tela que a
      // FDD 030 recusa — e alguém a leria como exemplo do formato certo.
      by_source: [
        { source: "indicacao", leads: 6, won: 3, projects: 3, revenue: "540000.00" },
        { source: "site", leads: 28, won: 2, projects: 2, revenue: "180000.00" },
        { source: "direto", leads: 0, won: 1, projects: 1, revenue: "95000.00" },
      ],
    },
    win_rate: 0.67, avg_ticket: 150000, avg_cycle_days: 38, pipeline: etapas,
    roi: {
      revenue: "1440000.00", cost: "720000.00", roi: 1,
      // `by_account`: a chave do recorte por conta trocou de nome na `/api/v2/`, que é a versão
      // que este mock serve (`docs/ontology/aliases.md`).
      by_account: clientes.map(c => ({ label: c.name, revenue: "180000.00", cost: "90000.00", roi: 1 })),
      by_service: [{ label: "Discovery + Assessment", revenue: "640000.00", cost: "300000.00", roi: 1.13 }],
    },
  },
  "/api/v2/notifications/": serie(4, index => ({
    id: index, kind: "task", message: `Tarefa "Entrevistar área de faturamento" vence hoje (${index})`,
    url: "/projetos/1", read: index > 2, created_at: `${HOJE}T08:00:00Z`,
  })),
  "/api/v2/users/": Object.values(usuarios),
  "/api/v2/invitations/": serie(3, index => ({
    id: index, email: `convidado${index}@empresa.test`, role: "delivery",
    expires_at: "2026-08-12T00:00:00Z", accepted_at: null, created_at: `${HOJE}T08:00:00Z`,
  })),
  "/api/v2/project-members/": serie(4, index => ({
    id: index, project: 1, user: index, user_name: `Pessoa ${index}`,
    user_username: `pessoa${index}`, user_role: "delivery", added_by: 1,
    created_at: `${HOJE}T08:00:00Z`,
  })),
  "/api/v2/project-phases/": serie(4, index => ({
    id: index, project: 1, phase: index, phase_name: `Fase ${index} — implantação assistida`,
    phase_description: "", phase_position: index,
    status: index === 1 ? "done" : index === 2 ? "active" : "locked",
    started_at: null, completed_at: index === 1 ? `${HOJE}T08:00:00Z` : null, target_date: HOJE,
    deliverables: serie(2, d => ({ id: d, project_phase: index, name: `Entregável ${d}`, status: "pending", document: null, position: d, delivered_at: null })),
    // FDD 033: a fase concluída carrega uma decisão (o selo renderiza e o axe o mede) e a ativa
    // termina em gate com checklist pendente — senão o e2e aprova superfícies que nunca abriu.
    requires_gate: index === 2,
    // A fase canônica é o que faz os painéis de Feasibility e PROVE existirem (DAP
    // `dap-prove-e-valor-r1`, decisão A1). Sem ela a matriz aprovaria o detalhe do projeto sem os
    // dois painéis novos — que é o mesmo modo de falha da chave de rota errada, um nível acima.
    // `serie` é **1-based** (`indice + 1`), e é por isso que os dois valores são 1 e 2: a fase 1
    // concluída é Feasibility e a fase 2 ativa é PROVE; as duas juntas fazem os painéis existirem.
    canonical_stage: index === 1 ? "feasibility" : index === 2 ? "prove" : "",
    gate_decision: index === 1 ? "conditional_go" : "",
    gate_notes: index === 1 ? "Seguimos monitorando a acurácia do OCR." : "",
    checklist_waiver: "",
    checklist_items: index === 2
      ? serie(2, c => ({ id: c, project_phase: index, text: `Item de qualidade ${c}`, position: c, checked: c === 1, checked_at: c === 1 ? `${HOJE}T08:00:00Z` : null }))
      : [],
  })),
  // O ativo **referencia** o KPI desde a decisão C1 (ADR 0055) — `kpi_baseline`/`kpi_current` não
  // saem mais da `/api/v2/`, e o painel lê o par pelas medições do KPI referenciado. O primeiro
  // aponta para o KPI 21 (par completo, `— → 65`); o segundo, para o 22 (**sem baseline**, para o
  // axe medir o "variação —" e não só o par completo); o terceiro não referencia KPI nenhum.
  "/api/v2/digital-employees/": serie(3, index => ({
    id: index, project: 1, blueprint: null, kpi: index === 1 ? 21 : index === 2 ? 22 : null,
    name: `Agente de conciliação ${index}`, area: "Financeiro",
    description: "Concilia notas fiscais com o extrato bancário.", status: "active",
    kpi_label: "Horas poupadas", kpi_value: "120",
    kpi_unit: "hours", kpi_direction: "down",
    hours_saved_month: "120.0", roi_month: "18000.00",
  })),
  "/api/v2/meetings/": serie(4, index => ({
    id: index, project: 1, title: `Comitê quinzenal de acompanhamento ${index}`,
    date: HOJE, recording_url: "", transcript: "Cliente relatou processo manual.", status: "held",
  })),
  "/api/v2/pendencias/": serie(4, index => ({
    id: index, project: 1, title: `Liberar acesso ao ERP para a equipe ${index}`,
    description: "", status: "open", party: "client", owner: null, resolved_at: null,
  })),
  "/api/v2/contacts/": serie(4, index => ({
    id: index, account: 1, first_name: "Pessoa", last_name: `de contato ${index}`,
    name: `Pessoa de contato ${index}`,
    email: `pessoa${index}@empresa.test`, phone: "(11) 98888-0000", job_title: "Gerente de operações",
    // Um marcado e três não: o selo "Recebe cobrança" (FDD 036) precisa renderizar, e a linha sem
    // ele é a maioria dos contatos de verdade.
    receives_billing: index === 1,
  })),
  // Os mandatos da conta (ADR 0050, FDD 046), na seção que o DAP `dap-engagement-r1` aprovou.
  // **Um de cada combinação que a seção sabe desenhar**, e não três iguais: os três status
  // (`state--1`, `state--2`, `state--off`), os dois modelos comerciais — que a decisão B1 manda
  // mostrar **sempre**, e não só na exceção —, a linha com patrocínio e a sem, e as duas formas do
  // período (aberto e fechado). Sem isso o axe mediria "Pago" cinza e nunca o "Design partner"
  // azul, que é justamente o par que a tela não pode deixar parecer a mesma coisa.
  //
  // Sem esta chave a rota cairia no fallback de lista vazia e a matriz aprovaria o estado vazio no
  // lugar da seção — o modo de falha que o comentário de `/api/v2/processes/` acima já registra.
  "/api/v2/engagements/": [
    // O primeiro leva o par completo (D1: link de convite) — o terceiro momento do board é o
    // segundo desta lista, e o silêncio (C1) é o terceiro: um de cada estado que a linha desenha.
    { name: `Transformação do faturamento e do fiscal — ${NOME_LONGO}`,
      status: "active", status_display: "Ativo",
      commercial_model: "paid", commercial_model_display: "Pago",
      sponsor: 1, sponsor_name: "Maria de Lourdes Albuquerque",
      started_at: "2026-03-02", ended_at: null, projects_count: 3,
      whatsapp_group_id: "120363431743499021@g.us",
      whatsapp_group_invite_url: "https://chat.whatsapp.com/GONwbGG" },
    // JID sem link de convite (D1): o texto sem affordance também entra na varredura do axe.
    { name: "Discovery Cartas Vivas", status: "paused", status_display: "Pausado",
      commercial_model: "design_partner", commercial_model_display: "Design partner",
      sponsor: null, sponsor_name: null,
      started_at: "2026-06-01", ended_at: null, projects_count: 1,
      whatsapp_group_id: "120363431743499099@g.us", whatsapp_group_invite_url: "" },
    // Sem grupo nenhum (C1): silêncio, sem traço nem estado.
    { name: "Piloto de atendimento 24h", status: "closed", status_display: "Encerrado",
      commercial_model: "paid", commercial_model_display: "Pago",
      sponsor: 2, sponsor_name: "Pessoa de contato 2",
      started_at: "2026-02-10", ended_at: "2026-05-20", projects_count: 2,
      whatsapp_group_id: "", whatsapp_group_invite_url: "" },
  ].map((registro, indice) => ({
    id: indice + 1, account: 1, account_name: NOME_LONGO,
    mandate: "Reduzir o retrabalho do faturamento e fechar o mês sem conferência manual.",
    owner: 1, owner_name: "Ana Souza",
    success_definition: "Fechamento mensal sem reemissão de nota por erro de cadastro.",
    needs_review: false, archived_at: null,
    originating_commercial_opportunity: registro.commercial_model === "paid" ? indice + 1 : null,
    originating_commercial_opportunity_title: registro.commercial_model === "paid" ? "Discovery e assessment de automação" : "",
    originating_design_partner_agreement: registro.commercial_model === "design_partner" ? 1 : null,
    originating_design_partner_agreement_name: registro.commercial_model === "design_partner" ? "Design Partner Agreement.pdf" : "",
    created_at: `${HOJE}T09:00:00Z`, updated_at: `${HOJE}T09:00:00Z`,
    ...registro,
  })),
  "/api/v2/artifacts/": serie(4, index => ({
    id: index, kind: "proposal", kind_display: "Proposta", status: "draft",
    status_display: "Rascunho", title: `Proposta — ${NOME_LONGO}`,
    content: "Rascunho gerado por IA para revisão humana.", commercial_opportunity: 1,
    project: null,
    source_meeting: null, document: null, ai_interaction: 1, created_by: 1,
    sent_at: null, decided_at: null, created_at: `${HOJE}T09:00:00Z`, updated_at: `${HOJE}T09:00:00Z`,
  })),
};

/**
 * Intercepta toda a API com um handler só.
 *
 * `role: null` responde 403 em `/auth/me/` — que é como o SPA decide mostrar a tela de login.
 * `role: "delivery"` devolve listas vazias de projeto, porque é exatamente o que a Entrega vê
 * sem estar em nenhuma equipe (RFC 0003) — o estado vazio faz parte da matriz.
 */
export async function mockApi(page: Page, role: Role | null): Promise<void> {
  await page.route("**/api/v2/**", (route: Route) => {
    const { pathname } = new URL(route.request().url());
    if (pathname === "/api/v2/auth/me/") {
      return role
        ? route.fulfill({ json: usuarios[role] })
        : route.fulfill({ status: 403, json: { detail: "Credenciais ausentes." } });
    }
    if (role === "delivery" && (pathname === "/api/v2/projects/" || pathname === "/api/v2/accounts/")) {
      return route.fulfill({ json: [] });
    }
    // Duas rotas da Fase 5 precisam **respeitar o filtro**, e são as duas únicas leituras de query
    // string desta função.
    //
    // As medições são por KPI, e o KPI sem baseline é justamente o estado que o axe precisa medir
    // (`— → 68`, com a variação vazia): um fixture único, igual para os dois indicadores,
    // esconderia metade do desenho. O Value Ledger é por engajamento, e a tela faz uma chamada por
    // mandato da conta — devolver a mesma lista três vezes renderizaria cada entrada em triplicata
    // e o total sairia triplicado, aprovando uma soma que o produto não faz.
    const busca = new URL(route.request().url()).searchParams;
    if (pathname === "/api/v2/measurements/") {
      return route.fulfill({ json: MEDICOES_POR_KPI[busca.get("kpi") ?? ""] ?? [] });
    }
    if (pathname === "/api/v2/value-ledger-entries/") {
      const doMandato = (FIXTURES[pathname] as { engagement: number }[])
        .filter(entrada => String(entrada.engagement) === busca.get("engagement"));
      return route.fulfill({ json: doMandato });
    }
    const fixture = FIXTURES[pathname];
    if (fixture !== undefined) return route.fulfill({ json: fixture });
    // Rota não mapeada: lista vazia em vez de 404, para uma tela nova na matriz renderizar
    // seu estado vazio em vez de estourar antes de o axe chegar nela.
    return route.fulfill({ json: [] });
  });
}

/**
 * Abre a tela já com sessão e API mockadas, e espera o conteúdo **assentar**.
 *
 * Esperar só pelo `<h1>` não basta e chega a ser pior que não esperar: painéis que carregam
 * depois (o de artefatos, no detalhe do projeto) entram na tela **após** o título, e a medição
 * pegava a página pela metade. O resultado seria um teste que passa ou reprova conforme a
 * máquina do dia — e foi exatamente assim que o estouro horizontal do painel de artefatos quase
 * passou despercebido. `networkidle` fecha a janela: com toda a API mockada, ele significa
 * "nenhuma requisição pendente", isto é, o React já renderizou tudo o que ia buscar.
 */
export async function abrir(page: Page, screen: Screen): Promise<void> {
  await mockApi(page, screen.role);
  await page.goto(screen.path);
  await page.locator("h1").first().waitFor({ state: "visible" });
  await page.waitForLoadState("networkidle");
}
