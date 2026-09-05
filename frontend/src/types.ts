export type PipelineStage = { id: number; name: string; kind: "open" | "won" | "lost"; position: number; opportunity_count?: number; estimated_total?: string | null };
export type CommercialOpportunity = { id: number; account: number; contact: number | null; title: string; scope: string; estimated_value: string; stage: number; stage_name: string; stage_kind: "open" | "won" | "lost"; engagement: number | null; owner: number; expected_close_date: string; service: number | null; service_name: string; service_tier: ServiceTier; project: number | null; project_archived: boolean; origin_qualification: number | null };
export type AiScoreDimension = { label: string; score: number };
// O mandato de transformação da conta, entre `Account` e `Project` (ADR 0050, FDD 046). Uma venda
// avulsa também tem o seu — de escopo único, criado pela própria conversão.
export type EngagementStatus = "active" | "paused" | "closed";
// `design_partner` recebe Discovery sem cobrança em troca de servir de caso; `paid` é o
// mandato vendido. O campo **registra** a condição e não concede nada — nenhuma regra de
// preço, fatura ou catálogo o lê (FDD 046). Não atravessa para o One: é dado comercial
// (`docs/ontology/language-map.md` §3).
export type EngagementCommercialModel = "design_partner" | "paid";
// `projects_count` é **recortado pelo escopo de quem lê** (`project_scope_q`), não o total do
// mandato: dois usuários veem números diferentes para a mesma linha, e cada um vê o que alcança.
// É o mesmo comportamento de `/accounts/overview/` (FDD 046, emenda de 28/08/2026).
export type Engagement = { id: number; account: number; account_name: string; name: string; mandate: string; sponsor: number | null; sponsor_name: string | null; owner: number; owner_name: string | null; status: EngagementStatus; status_display: string; commercial_model: EngagementCommercialModel; commercial_model_display: string; originating_commercial_opportunity: number | null; originating_commercial_opportunity_title: string; originating_design_partner_agreement: number | null; originating_design_partner_agreement_name: string; started_at: string | null; ended_at: string | null; success_definition: string; projects_count: number; needs_review: boolean; discovery_scheduled_at: string | null; whatsapp_group_id: string; whatsapp_group_invite_url: string; archived_at: string | null; created_at: string; updated_at: string };
// `opportunity` (alias de leitura de `originating_commercial_opportunity`) e `ai_opportunity`
// (alias de `ai_potential`) eram aliases da `/api/v1/` e a `/api/v2/` não os emite mais
// (`docs/ontology/aliases.md` §2c). O mesmo vale para `client`/`client_vertical`/
// `client_vertical_name`, que viraram `account_vertical`/`account_vertical_name` — a projeção
// nunca teve coluna própria, então o nome errado só existia na chave de payload.
export type Project = { id: number; name: string; description: string; engagement: number; engagement_name: string; originating_commercial_opportunity: number | null; owner: number; start_date: string; due_date: string; status: string; service: number | null; actual_value: string; cost: string; is_overdue: boolean; ai_maturity: number | null; ai_potential: number | null; ai_dimensions: AiScoreDimension[]; ai_score_summary: string; ai_scored_at: string | null; ai_score_reviewed: boolean; account_vertical: number | null; account_vertical_name: string };
export type ServiceTier = "qualification_call" | "discovery_sprint" | "feasibility" | "prove" | "scale" | "transformation" | "";
// `acquisition` é a porta (a Qualification Call), `commercial` é degrau vendável — e é a
// categoria, não o preço zero, que decide: o Discovery + Assessment do founding client também é
// gratuito e é degrau (ADR 0049).
export type ServiceCategory = "acquisition" | "commercial";
export type Service = { id: number; name: string; active: boolean; tier: ServiceTier; tier_display: string; category: ServiceCategory; category_display: string; list_price: string; summary: string };
// **Dinheiro chega como `string`, e índice calculado como `number`** (ADR 0068). A API emite
// decimal em texto para não perder centavo no `float` do JSON, e os agregados deixaram de ser a
// exceção a essa regra: `estimated_total`, `revenue` e `cost` são texto;
// `win_rate`, `acceptance_rate`, `roi` e `avg_ticket` são quocientes e continuam número. Formatar
// converte com `Number()` na borda (`dinheiro.ts`); somar é do servidor.
export type TierFunnelRow = { tier: ServiceTier; label: string; total: number; open: number; won: number; lost: number; estimated_total: string; win_rate: number | null };
export type StageFunnelRow = { kind: ArtifactKind; label: string; total: number; sent: number; accepted: number; rejected: number; acceptance_rate: number | null; reached: number };
export type SourceFunnelRow = { source: string; leads: number; won: number; projects: number; revenue: string };
export type RoiRow = { label: string; revenue: string; cost: string; roi: number | null };
export type Analytics = {
  funnel: {
    leads: { total: number; by_status: Record<string, number> };
    opportunities: { open: number; won: number; lost: number };
    projects: { total: number; by_status: Record<string, number> };
    by_tier: TierFunnelRow[];
    by_stage: StageFunnelRow[];
    by_source: SourceFunnelRow[];
  };
  win_rate: number | null;
  avg_ticket: number;
  avg_cycle_days: number | null;
  // `estimated_total` é `null` — nunca `"0.00"` — na etapa sem oportunidade nenhuma: "não há o
  // que somar" e "somou zero" são fatos diferentes, e a API preserva a distinção.
  pipeline: { id: number; name: string; kind: string; position: number; opportunity_count: number; estimated_total: string | null }[];
  // `by_account` é o recorte por conta. Ele **trocou** de nome com a `/api/v2/` (era `by_client`
  // na `/api/v1/`, e a chave envolve a lista inteira, então não convive — `docs/ontology/aliases.md`);
  // a SPA fala a `/api/v2/`, então só a canônica existe aqui. O rótulo da tela continua dizendo
  // "ROI por cliente": "Cliente" é rótulo legítimo de interface (`language-map.md` §4), e o que
  // muda é a chave de payload.
  roi: { revenue: string; cost: string; roi: number | null; by_account: RoiRow[]; by_service: RoiRow[] };
};
// Onde a conta está na relação com a casa. **"Cliente" é o rótulo de `active`, não o nome da
// entidade** (`docs/ontology/language-map.md` §4): `prospect` ainda não fechou, `active` é
// cliente de fato, `inactive` já foi e hoje não tem trabalho em andamento. `status` era alias da
// `/api/v1/` com o mesmo valor de `lifecycle_status`; a `/api/v2/` não o emite mais.
export type AccountLifecycleStatus = "prospect" | "active" | "inactive";
// `published_count` é derivado e só-leitura (issue #114): quantos registros do Discovery desta
// conta o cliente está vendo agora. Arquivar a conta **não** os despublica — só um ato humano
// despublica (ADR 0060) —, então a confirmação de arquivar avisa em vez de cascatear.
export type Account = { id: number; name: string; legal_name: string; tax_id: string; owner: number; lifecycle_status: AccountLifecycleStatus; vertical: number | null; vertical_name: string; published_count: number };
// `receives_billing` marca quem recebe cobrança (FDD 036). Sem ninguém marcado, o degrau **não**
// vira e-mail ao cliente: vira escalada interna com o motivo escrito — a casa cala quando não sabe
// em vez de chutar o destinatário de um e-mail sobre dinheiro.
// `name` é derivado e só-leitura (issue #55, FDD 001) — `first_name` + `last_name`, sem espaço
// solto quando não há sobrenome. Quem escreve manda `first_name`/`last_name`, nunca `name`.
export type Contact = { id: number; account: number; first_name: string; last_name: string; name: string; email: string; phone: string; job_title: string; receives_billing: boolean };
// Interação comercial com o cliente (FDD 035, ADR 0030) — a materialização das "Activities" do
// CRM na leitura FDE. `commercial_opportunity` é opcional e, quando preenchida, tem de ser do
// mesmo cliente (o backend recusa com 400; ver `docs/metodologia-fde.md`).
export type ActivityKind = "call" | "meeting" | "email" | "note";
// `dunning_signal` é lavrado por `POST /activities/{id}/classificar/` e é **só de leitura** aqui:
// a IA grava o sinal e não age (ADR 0031). Os três valores roteiam condutas diferentes — `forgot`
// já se resolveu com o lembrete, `unable_to_pay` pede renegociação, `dissatisfied` não é problema
// de cobrança e é onde insistir piora tudo. O valor fala inglês desde a issue #122, fatia 5.2
// (D10); o alias pt-BR (`cobranca_sinal`) só existe na `/api/v1/`, que a SPA não consome.
export type DunningSignal = "" | "forgot" | "unable_to_pay" | "dissatisfied";
// `opportunity` era **alias de leitura** da `/api/v1/` para `commercial_opportunity`
// (`docs/ontology/aliases.md` §2c); a `/api/v2/` não o emite mais.
export type Activity = { id: number; account: number; commercial_opportunity: number | null; invoice: number | null; dunning_signal: DunningSignal; dunning_signal_display: string; kind: ActivityKind; kind_display: string; happened_on: string; summary: string; notes: string; owner: number | null; created_at: string; updated_at: string };
export type WorkItemStatus = "todo" | "in_progress" | "done";
export type Party = "provider" | "client";
export type Milestone = { id: number; project: number; title: string; description: string; owner: number; due_date: string; completed_at: string | null; status: WorkItemStatus; party: Party; is_overdue: boolean };
export type Task = Milestone & { milestone: number | null };
export type Meeting = { id: number; project: number; title: string; date: string; meeting_url: string; recording_url: string; transcript: string; status: "scheduled" | "held" };
export type Pendencia = { id: number; project: number; title: string; description: string; status: "open" | "resolved"; party: Party; owner: number | null; resolved_at: string | null };
export type Decisao = { id: number; project: number; project_phase: number | null; title: string; rationale: string; decided_on: string | null; decided_by: string; status: "draft" | "published"; source_meeting: number | null; published_at: string | null };
// Risk Register do projeto (FDD 034) — o risco **declarado** por alguém, que não é o mesmo que a
// `RiskAssessment` calculada logo abaixo. Aquela deriva de prazo e item atrasado; esta é escrita.
export type RiscoNivel = "low" | "medium" | "high";
export type RiscoStatus = "open" | "mitigated" | "accepted" | "materialized";
export type Risco = { id: number; project: number; title: string; description: string; probability: RiscoNivel; impact: RiscoNivel; mitigation: string; status: RiscoStatus; owner: number | null; resolved_at: string | null };
// Projeção de entrega GitHub (FDD 041, ADR 0046) — leitura do estado de engenharia (Issue/PR/CI)
// sobre um item de entrega. **Somente-projeção**: a tela lê e nunca reescreve o estado do GitHub.
// `state` é o estado *visível* já com o frescor dobrado (`current`/`stale`/…), distinto do
// `projection_status` persistido — nunca inventa status.
export type GithubProjectionStatus = "pending" | "current" | "unavailable" | "permission_denied" | "reference_missing";
export type GithubProjectionState = "pending" | "current" | "stale" | "unavailable" | "permission_denied" | "reference_missing";
export type GithubIssueState = "unknown" | "open" | "closed";
export type GithubPullState = "unknown" | "none" | "draft" | "open" | "closed" | "merged";
export type GithubReviewState = "unknown" | "pending" | "approved" | "changes_requested";
export type GithubCiState = "unknown" | "pending" | "success" | "failure";
export type GithubDeliveryProjection = { id: number; project: number; handoff: number | null; repository: string; issue_number: number; issue_url: string; projection_status: GithubProjectionStatus; state: GithubProjectionState; stale_after_seconds: number; issue_state: GithubIssueState; pr_state: GithubPullState; pr_number: number | null; pr_url: string; head_sha: string; head_ref: string; review_state: GithubReviewState; ci_state: GithubCiState; observed_at: string | null; last_event_at: string | null; last_delivery_id: string; last_event_type: string; last_error_code: string; last_error_message: string; created_at: string; updated_at: string };
// A marca de publicável do Discovery (FDD 051, ADR 0060) e o campo derivado que a acompanha nos
// **cinco** recursos que atravessam para o portal do cliente — `Process`, `Evidence`, `Finding`,
// `PainPoint` e `ImprovementOpportunity`.
//
// **As frases vêm do servidor e não se reescrevem aqui** (DAP `dap-publicacao-discovery-r1`,
// decisão E1): `missing_phrase` é `publication.frase_do_que_falta` e `blocked_phrase` é
// `publication.frase_do_impedimento`, os mesmos textos que compõem o 400 e o 409 das actions. Um
// mapa chave→rótulo em TypeScript seria a segunda definição da mesma copy, e as duas divergem no
// primeiro conserto sem nada ficar vermelho.
//
// As **chaves** continuam saindo e não são decoração: é por elas que a tela sabe *o que* precisa
// subir junto num lote, sem parsear texto em português.
export type PublicationRequirement = "published_evidence" | "published_finding" | "published_pain_point" | "published_process";
// Três estados, e a superfície desenha **dois selos** (decisão D1): `published` é "Visível ao
// cliente"; `ready` e `blocked` são os dois "Oculto do cliente", e o que os separa é a frase da
// linha, não uma terceira pastilha. `blocked_by` só é maior que zero no ramo publicado — um
// registro que não atravessou não pode ter dependente publicado.
export type PublicationState = { state: "published" | "ready" | "blocked"; missing: PublicationRequirement[]; missing_phrase: string; blocked_by: number; blocked_phrase: string };
// O Discovery estruturado (FDD 039, ADR 0034) — o **dado** do mapa da operação, que não é o
// `Artifact` de `kind=discovery` (a narrativa entregue ao cliente): aquele se lê, este se soma.
// Liga ao cliente e não ao projeto, porque o processo mapeado sobrevive à venda que o descobriu.
//
// **Os nove insumos são `string | null` e nulo é "não apurado", nunca zero.** Zerar afirmaria que
// executar o processo não custa nada; o backend devolve o que faltou em `custo.nao_apurado` em vez
// de somar zero, e a tela precisa poder dizer a mesma coisa.
export type Process = { id: number; account: number; account_name: string; name: string; position: number; source_project: number | null; source_meeting: number | null; registered_by: number | null; volume_mes: number | null; tempo_horas: string | null; pessoas: number | null; custo_hora: string | null; retrabalho_mes: string | null; erros_mes: string | null; perdas_mes: string | null; espera_mes: string | null; risco_mes: string | null; custo: CustoEstadoAtual; published_at: string | null; published_by: number | null; publication_state: PublicationState; created_at: string; updated_at: string };
// A conta do custo do estado atual, derivada e só de leitura. **Os valores são texto**, como
// `Invoice.amount`: dinheiro em `number` soma centavos com erro, e este total existe para ser
// levado a uma reunião. `nao_apurado` é o que separa "não há insumo" de "medimos e deu zero" —
// um total mostrado sem ele vira "custo zero" na leitura rápida. `sustentacao` responde a outra
// metade da metodologia: só há **fato** por trás do número, ou ainda é hipótese da casa.
export type CustoEstadoAtual = { parcelas: { label: string; valor: string }[]; total: string; nao_apurado: string[]; sustentacao: "sustentado" | "hipotese" };
// A etapa e o P-S-D-T-E-R dela (`docs/metodologia-fde.md:106-110`). Os seis campos são exatamente as
// seis letras, nessa ordem: é assim que a pergunta é feita na reunião, e um formulário fora de
// ordem faz quem preenche pular a que faltou. Aqui `tempo`, `erro` e `retrabalho` são **descrição**
// — os homônimos `_mes` do `Process` são dinheiro e quantidade, e não se confundem.
// **`process` é a canônica e `processo` é o alias da `/api/v1/`** (`docs/ontology/aliases.md`
// §2c): a fatia 4 da issue #67 renomeou o campo do modelo, e a chave antiga continua saindo no GET
// da `/api/v1/` e sendo aceita na escrita — mas morre na `/api/v2/`, que é a que esta SPA fala
// (`src/api.ts`). O alias não entra aqui: declará-lo seria o tipo afirmando o que a API não manda.
export type ProcessStep = { id: number; process: number; name: string; position: number; pessoas: string; sistema: string; dados: string; tempo: string; erro: string; retrabalho: string };
// O split Evidence/Finding e o Discovery (FDD 045, ADR 0049). O `ProcessDetailPage` **consome**
// `Finding`/`Evidence` desde a Fase 6 (ADR 0052), que removeu a `Evidencia` fundida e o dual-write:
// a tela lista os achados do split e promove a fato por ali. As demais superfícies (tela de
// Discovery, painel de achados dedicado) seguem pendentes de Design Approval Package.
//
// A regra de nome da ontologia vale aqui igual: termo canônico em inglês nas quatro superfícies.
export type DiscoveryStatus = "planned" | "running" | "completed" | "cancelled";
export type Discovery = { id: number; project: number; project_name: string; scope: string; status: DiscoveryStatus; status_display: string; started_at: string | null; completed_at: string | null; owner: number | null; created_at: string; updated_at: string };
export type DiscoverySession = { id: number; discovery: number; meeting: number | null; happened_at: string; participants: string; source_artifact: number | null; transcript: string; created_at: string; updated_at: string };
export type ProcessObservationKind = "initial" | "revisit" | "validation";
export type ProcessObservation = { id: number; discovery: number; process: number; observed_at: string; observation_type: ProcessObservationKind; observation_type_display: string; source_session: number | null; created_at: string; updated_at: string };
// As cinco formas de evidência, em inglês canônico (`docs/metodologia-fde.md:112-115`). São cinco
// de propósito: um sexto valor aqui seria um conceito novo, não uma tradução.
export type EvidenceKind = "interview" | "observation" | "artifact" | "system" | "data";
// `raw_excerpt` é o trecho **como foi dito**, e `reference` é o localizador — um dos dois precisa
// existir. A conclusão que a casa tirou dali mora em `Finding.statement`, nunca aqui: misturar as
// duas refaria a fusão que este split desfaz. `content_hash` é o carimbo de integridade do trecho,
// derivado e só de leitura.
export type Evidence = { id: number; account: number; discovery: number | null; process: number | null; step: number | null; kind: EvidenceKind; kind_display: string; raw_excerpt: string; reference: string; source_session: number | null; source_meeting: number | null; captured_at: string; captured_by: number | null; content_hash: string; published_at: string | null; published_by: number | null; publication_state: PublicationState; created_at: string; updated_at: string };
// FATO / HIPÓTESE / DESCONHECIDO com o nome canônico da ontologia (`language-map` §4). O rótulo não
// tem default no banco (ADR 0034), e há uma proibição a mais: **um select não promove a `fact`
// sozinho**. Promover exige revisor humano e evidência viva, e o backend responde 400 — a tela que
// oferecer o valor sem pedir as duas coisas produz um erro que quem clica não entende.
export type EpistemicStatus = "fact" | "hypothesis" | "unknown";
export type Finding = { id: number; account: number; process: number | null; step: number | null; statement: string; epistemic_status: EpistemicStatus; epistemic_status_display: string; confidence: number | null; reviewed_by: number | null; reviewed_at: string | null; evidences: number[]; published_at: string | null; published_by: number | null; publication_state: PublicationState; created_at: string; updated_at: string };
// A cadeia do PRIORITIZE (FDD 048, ADR 0054): dor → oportunidade de melhoria → avaliação →
// hipótese. **Nenhuma tela consome estes tipos ainda**, exatamente como os do split da Fase 3
// logo acima, e pelo mesmo motivo: é o recorte da fatia, não esquecimento — a superfície tem DAP
// aprovado (`docs/design/dap-priorizacao-r1/`) e vem na tarefa seguinte. Eles entram aqui para
// que a forma do contrato fique escrita do lado do consumidor no mesmo commit em que ela nasce no
// servidor.
export type PainPointImpactType = "financial" | "operational" | "experience" | "risk";
export type PainPointStatus = "observed" | "confirmed" | "discarded";
// `impact_estimate` **nulo é "não estimado"**, e nunca zero: zero afirma que a dor não custa
// nada. A tela mostra `—` no nulo, como `Process.custo_do_estado_atual` já faz com `nao_apurado`.
// `confirmed` exige ao menos um achado vivo em `findings`, e o backend responde 400 — um select
// que ofereça o valor sem exigir o vínculo produz um erro que quem clica não entende.
export type PainPoint = { id: number; account: number; process: number | null; step: number | null; title: string; description: string; impact_type: PainPointImpactType; impact_type_display: string; impact_estimate: string | null; findings: number[]; status: PainPointStatus; status_display: string; published_at: string | null; published_by: number | null; publication_state: PublicationState; created_at: string; updated_at: string };
export type ImprovementOpportunityStatus = "open" | "assessing" | "prioritized" | "discarded";
// `score`, `assessment_version` e `rank` são **derivados e só de leitura**: saem da avaliação
// vigente (a de maior versão não arquivada) e da ordenação por score dentro da conta. Os três
// vêm `null` juntos quando ninguém avaliou — é o `—` do desenho, e nunca `0`.
export type ImprovementOpportunity = { id: number; account: number; engagement: number | null; title: string; desired_change: string; impact_hypothesis: string; pain_points: number[]; status: ImprovementOpportunityStatus; status_display: string; score: string | null; assessment_version: number | null; rank: number | null; published_at: string | null; published_by: number | null; publication_state: PublicationState; created_at: string; updated_at: string };
// **A avaliação é imutável**: repriorizar é um `POST` de versão nova, e `PUT`/`PATCH` respondem
// 405. `version`, `weights` e `score` saem do servidor; `weights` é a cópia congelada dos pesos
// que produziram aquele score, para que mudar a fórmula amanhã não reescreva o número de ontem.
export type PriorityAssessment = { id: number; improvement_opportunity: number; version: number; impact: number; evidence_strength: number; feasibility: number; time_to_value: number; economics: number; formula_key: string; weights: Record<string, string>; score: string; rationale: string; assessed_by: number | null; assessed_by_name: string; created_at: string; updated_at: string };
// Hipóteses concorrentes são o estado normal; **uma só `chosen` viva por oportunidade**.
export type SolutionHypothesisStatus = "proposed" | "chosen" | "discarded";
export type SolutionHypothesis = { id: number; improvement_opportunity: number; statement: string; intervention: string; assumptions: string; expected_effect: string; status: SolutionHypothesisStatus; status_display: string; created_at: string; updated_at: string };
// A justificativa do investimento (FDD 053, ADR 0069), governada pelo DAP
// `docs/design/dap-discovery-session-e-business-case-r2/` — decisões **A1** e **F1**.
export type BusinessCaseStatus = "draft" | "approved" | "rejected";
// A proveniência do congelamento (`business_case.custo_congelavel`): uma linha por processo
// alcançado, com a mesma `sustentacao` de `CustoEstadoAtual`, e os ids que **de fato** entraram na
// soma. Existe para a lacuna do `current_state_cost` nulo ser dita, nunca inventada pela tela.
export type BusinessCaseCostSourceRow = { id: number; sustentacao: CustoEstadoAtual["sustentacao"]; total: string; nao_apurado: string[] };
export type BusinessCaseCostSource = { processos: BusinessCaseCostSourceRow[]; somados: number[] };
// `current_state_cost` nulo é "não apurado", nunca zero (decisão F1) — a mesma regra do
// `impact_estimate` da dor e do `nao_apurado` do processo. `investment`/`expected_return_year`
// nuláveis pela razão inversa: o rascunho existe antes de alguém orçar, e zero ali seria um
// investimento que ninguém fez. `decided_by` sai só como id — o contrato não publica o nome de
// quem decidiu, e inventá-lo aqui seria a tela afirmando o que não sabe.
export type BusinessCase = { id: number; improvement_opportunity: number; account: number; solution_hypothesis: number; priority_assessment: number; investment: string | null; expected_return_year: string | null; payback_months: number | null; current_state_cost: string | null; current_state_cost_source: BusinessCaseCostSource; rationale: string; assumptions: string; status: BusinessCaseStatus; status_display: string; decided_at: string | null; decided_by: number | null; decided_by_name: string; created_at: string; updated_at: string };
// O próximo passo da conta (FDD 054, ADR 0069), no molde de `ProveMissingRequirement` logo abaixo:
// **o servidor devolve a chave e a tela tem o rótulo**. `missing` é o **primeiro** degrau que falta
// na primeira oportunidade ranqueada com pendência — nunca a de maior score quando ela já está
// encaminhada —, e a tela não recalcula nenhum dos dois: uma segunda expressão da regra faria o
// painel discordar da recomendação de `/indicadores`, que lê a mesma função.
//
// `ranked_count` existe porque **os dois vazios não são o mesmo vazio**: `next_step: null` com
// contagem zero é "nada avaliado nesta conta" (o vazio honesto, com a porta para a priorização) e
// com contagem maior que zero é "nada pendente" (o neutro, que não inventa urgência).
export type AccountNextStepMissing = "choose_hypothesis" | "build_business_case" | "decide_investment" | "open_commercial_opportunity";
export type AccountNextStep = { improvement_opportunity: number; title: string; score: string; assessment_version: number; missing: AccountNextStepMissing };
export type AccountNextStepResponse = { next_step: AccountNextStep | null; ranked_count: number };
// Feasibility, PROVE, KPI/Measurement e Value Ledger (FDD 049, ADR 0055). **Nenhuma tela consome
// estes tipos ainda**, exatamente como os da Fase 4 logo acima e pelo mesmo motivo: é o recorte da
// fatia, não esquecimento — a superfície tem DAP aprovado (`docs/design/dap-prove-e-valor-r1/`,
// decisões A1 · B1 · C1 · D1 · E1) e vem na tarefa seguinte. Eles entram aqui para que a forma do
// contrato fique escrita do lado do consumidor no mesmo commit em que ela nasce no servidor.
export type FeasibilityVerdict = "favorable" | "caveat" | "unfavorable";
// `gate_decision` do laudo usa **as quatro** saídas da Feasibility, e o do PROVE **as três** dele
// (ADR 0053): a pergunta é outra e as saídas são outras. `""` é "ainda não decidido", como no
// campo da fase. Os rótulos moram em `journey.ts`, o único mapa — não se traduzem.
export type FeasibilityGateDecision = "" | "go" | "conditional_go" | "redesign" | "no_go";
export type FeasibilityAssessment = { id: number; solution_hypothesis: number; project: number; technical_verdict: FeasibilityVerdict; technical_verdict_display: string; technical_note: string; operational_verdict: FeasibilityVerdict; operational_verdict_display: string; operational_note: string; economic_verdict: FeasibilityVerdict; economic_verdict_display: string; economic_note: string; sample: string; error_classes: string; evidence: number[]; gate_decision: FeasibilityGateDecision; gate_decision_display: string; created_at: string; updated_at: string };
export type ProveGateDecision = "" | "scale" | "iterate" | "stop";
export type ProveExperimentStatus = "planned" | "running" | "concluded";
// **`missing_to_start` é derivado e só de leitura**, e é a mesma lista que a action `start/` usa
// para recusar: KPI, critério de sucesso e baseline. A tela desenha as três pastilhas a partir
// **dela**, e nunca recalculando a regra — duas expressões divergiriam, e o botão ficaria
// habilitado para um POST que o servidor nega. `status` não vai a `running` por `PATCH`: iniciar é
// `POST /prove-experiments/{id}/start/`. Lacuna aprovada exige `gap_waiver` **e** `gap_waiver_by`;
// `gap_waiver_at` é carimbado pelo servidor.
export type ProveMissingRequirement = "kpi" | "success_criteria" | "baseline";
export type ProveExperiment = { id: number; solution_hypothesis: number; project: number; controlled_scope: string; started_at: string | null; ended_at: string | null; success_criteria: string; status: ProveExperimentStatus; status_display: string; gate_decision: ProveGateDecision; gate_decision_display: string; gap_waiver: string; gap_waiver_by: number | null; gap_waiver_at: string | null; missing_to_start: ProveMissingRequirement[]; created_at: string; updated_at: string };
// `prove_experiment` é **opcional** e `project` é a âncora obrigatória: o KPI migrado da era
// anterior pende do projeto e não nasceu de experimento nenhum (ADR 0055).
export type KPI = { id: number; project: number; prove_experiment: number | null; name: string; definition: string; formula: string; unit: KpiUnit; unit_display: string; direction: KpiDirection; direction_display: string; data_source: string; cadence: string; owner: number | null; target: string | null; created_at: string; updated_at: string };
export type MeasurementKind = "baseline" | "outcome" | "monitoring";
// **`value` nulo é "não medido", nunca zero** — a tela mostra `— → 1h05` e deixa a variação vazia.
// Unidade e método **não** estão aqui de propósito: são do KPI, e é isso que torna baseline e
// outcome comparáveis (`language-map` §6.11). No máximo uma `baseline` viva por KPI.
export type Measurement = { id: number; kpi: number; kind: MeasurementKind; kind_display: string; value: string | null; period_start: string; period_end: string; measured_at: string; source_evidence: number[]; confidence: number | null; created_at: string; updated_at: string };
export type ValueType = "cost_saving" | "revenue" | "risk_reduction" | "capacity";
export type ValueLedgerStatus = "draft" | "pending" | "approved";
// `outcome_measurement` só aceita uma medição `kind=outcome`, `attribution_method` não pode ser
// vazio, e `approved` exige `approved_by` — as invariantes §6.11 e §6.12 do `language-map`.
// `approved_at` é carimbado pelo servidor. `project` é opcional: valor é do mandato, e a fatia por
// projeto existe quando alguém consegue atribuí-la.
export type ValueLedgerEntry = { id: number; engagement: number; project: number | null; outcome_measurement: number; value_type: ValueType; value_type_display: string; amount: string | null; quantity: string | null; period_start: string; period_end: string; attribution_method: string; status: ValueLedgerStatus; status_display: string; approved_by: number | null; approved_at: string | null; created_at: string; updated_at: string };
// `signer_role` decide **onde** a assinatura cai na página e qual `action` vai para o fornecedor
// (ADR 0065). "Biahflow" não é escolha da tela: quem atribui `house` é o servidor, a partir de
// `ESIGN_HOUSE_SIGNER_EMAIL` (DAP `dap-assinatura-com-papeis-r1`, decisão C1).
export type SignerRole = "house" | "counterparty" | "witness";
export type SignatureRequest = { id: number; signer_email: string; signer_role: SignerRole; status: "pending" | "signed" | "declined"; sign_url: string; reminded_at: string | null; signed_at: string | null; created_at: string };
// `opportunity` e `client` eram **aliases de leitura** da `/api/v1/` — o primeiro para
// `commercial_opportunity`, o segundo para o vínculo direto de conta (`docs/ontology/aliases.md`
// §2c) — e a `/api/v2/` não os emite mais.
// `owning_account` é a conta-dona **derivada** (`drive.account_of` no servidor, um lugar só): um
// contrato pendurado numa oportunidade chega com conta-dona preenchida mesmo sem vínculo direto
// (DAP r1, decisão B1).
// `signature_positioning_gap` é o que o servidor já sabe **antes** do envio sobre a assinatura não
// cair sobre as linhas; `null` é "nenhuma lacuna conhecida", não promessa de posição (E1).
export type SignaturePositioningGap = "not_pdf" | "kind_without_block";
export type DocumentEntry = { id: number; kind: string; account: number | null; commercial_opportunity: number | null; project: number | null; file: string; drive_link: string; original_name: string; uploaded_by: number; created_at: string; signature_requests: SignatureRequest[]; originated_engagement: number | null; owning_account: number | null; signature_positioning_gap: SignaturePositioningGap | null };
export type ArtifactKind = "discovery" | "assessment" | "proposal" | "contract";
export type ArtifactStatus = "draft" | "review" | "sent" | "accepted" | "rejected";
// `opportunity` era **alias de leitura** da `/api/v1/` para `commercial_opportunity`
// (`docs/ontology/aliases.md` §2c); a `/api/v2/` não o emite mais.
export type Artifact = { id: number; kind: ArtifactKind; kind_display: string; status: ArtifactStatus; status_display: string; title: string; content: string; commercial_opportunity: number | null; project: number | null; source_meeting: number | null; document: number | null; ai_interaction: number | null; created_by: number; sent_at: string | null; decided_at: string | null; created_at: string; updated_at: string };
export type Dashboard = { pipeline: PipelineStage[]; active_projects: number; overdue_count: number; upcoming_tasks: { id: number; title: string; due_date: string; project_id: number }[] };
// `is_admin` vem do backend (`User.is_admin_role`: papel admin **ou** superusuário) em vez de ser
// derivado aqui. É o mesmo predicado que a API usa para autorizar, então a tela não pode divergir
// dela — que era exatamente o defeito de `createsuperuser` (FDD 017).
// `has_avatar` e não a URL da foto: o arquivo é privado como o documento e sai por rota
// autenticada (`/users/<id>/avatar/`), então o que a sessão precisa saber é **se** existe uma —
// entre a miniatura e as iniciais. `avatar_updated_at` é o que muda a `src` do `<img>` depois de
// uma troca; sem ele o navegador seguiria mostrando a foto anterior até resolver revalidar.
export type SessionUser = { id: number; username: string; first_name: string; last_name: string; email: string; role: "admin" | "sales" | "delivery"; is_admin: boolean; has_avatar: boolean; avatar_updated_at: string | null };
export type Role = "admin" | "sales" | "delivery";
export type Invitation = { id: number; email: string; role: Role; expires_at: string; accepted_at: string | null; created_at: string };
// `missing` traz os nomes das variáveis de ambiente que faltam para a integração poder ligar. Sem
// eles a tela só sabia dizer "faltam credenciais", e quem ia corrigir tinha de abrir o código.
export type IntegrationFlag = { key: string; label: string; enabled: boolean; configured: boolean; toggleable: boolean; missing: string[] };
// `esign_house_signer_email` sai **fora** de `integrations` de propósito: uma flag responde
// "configurado?" sem revelar valor, e aqui o valor é a resposta — é o e-mail com que a casa
// assina, e ele vai no próprio documento (DAP `dap-assinatura-com-papeis-r1`, decisão D1).
export type AppConfig = { ai_enabled: boolean; calendar_enabled: boolean; esign_enabled: boolean; esign_house_signer_email: string | null; integrations: IntegrationFlag[] };
export type RiskSignal = { label: string; detail: string; weight: number };
export type RiskForecast = { predicted_finish_date: string; delay_days: number; basis: string };
export type RiskAssessment = { project_id: number; name: string; score: number; level: string; signals: RiskSignal[]; forecast: RiskForecast | null };
export type HealthLevel = "saudável" | "atenção" | "crítico";
export type HealthAssessment = { project_id: number; name: string; score: number; level: HealthLevel; signals: RiskSignal[] };
export type AccountOverview = {
  account_id: number;
  name: string;
  lifecycle_status: AccountLifecycleStatus;
  // Texto pela regra da ADR 0068 — e aqui o contrato não mudou: o esquema desta rota já dizia
  // `string`, era o corpo que emitia número.
  roi: { revenue: string; cost: string; roi: number | null };
  health: { score: number; level: HealthLevel; project_id: number } | null;
  risk_level: string | null;
  phase: { name: string; status: JourneyPhaseStatus } | null;
  next_meeting: { title: string; date: string } | null;
  ai_score: AiScore | null;
};
export type AiScore = { maturity: number | null; opportunity: number | null; dimensions: AiScoreDimension[]; summary: string; scored_at: string };
export type AgentReply = { text: string; interaction: number; sources?: AgentSource[] };
export type Recommendation = { kind: string; label: string; detail: string; url: string };
export type Notification = { id: number; kind: string; message: string; url: string; read: boolean; created_at: string };
/** Participação numa equipe de projeto — é o que dá acesso a quem é da Entrega (RFC 0003). */
export type ProjectMember = { id: number; project: number; user: number; user_name: string; user_username: string; user_role: Role; added_by: number | null; created_at: string };

export type DigitalEmployeeStatus = "building" | "active" | "paused";
// O KPI tipado (FDD 027). `kpi_value` continua no tipo porque continua na API — é a frase livre
// da era anterior, obsoleta e não removida —, mas quem mede usa o par baseline/atual: `null` é
// "não medido", que é diferente de zero e é o que faz o case declarar a lacuna em vez de inventar
// um "antes".
export type KpiUnit = "" | "percent" | "hours" | "minutes" | "currency" | "count";
export type KpiDirection = "up" | "down";
// **`kpi_baseline` e `kpi_current` saíram do ativo desde a ADR 0055.** O KPI vive em `KPI`, é
// medido em `Measurement`, e `kpi` é o ponteiro para qual indicador este funcionário digital move.
// As duas chaves eram derivadas e só de leitura na `/api/v1/`; a `/api/v2/` não as emite mais, e o
// painel de `ProjectDetailPage` lê o par pelas medições do KPI referenciado.
// **Escrever por elas já não tinha efeito** (decisão C1 do DAP `dap-prove-e-valor-r1`): quem media
// pelo formulário do Time Digital passa a medir pelo PROVE.
export type DigitalEmployee = { id: number; project: number; blueprint: number | null; kpi: number | null; name: string; area: string; description: string; status: DigitalEmployeeStatus; kpi_label: string; kpi_value: string; kpi_unit: KpiUnit; kpi_direction: KpiDirection; hours_saved_month: string; roi_month: string };
// A biblioteca de Funcionários Digitais (FDD 026): catálogo global + parametrização por vertical.
// Mesmo par que `JourneyPhaseTemplate`/`ProjectPhase`, um nível acima: o que a entrega instancia
// é uma **cópia**, e por isso `DigitalEmployee` não referencia nada aqui além da procedência.
export type Vertical = { id: number; name: string; slug: string; position: number; active: boolean };
// Valor fala inglês desde a migração `0084` (issue #122, fatia 5.1; D10 do language-map §4) — o
// rótulo em `BibliotecaPage.tsx` continua pt-BR, e é só ele que a UI mostra.
export type BlueprintArea = "commercial" | "finance" | "hr" | "legal" | "support";
export type BlueprintVariant = { id: number; blueprint: number; vertical: number; vertical_name: string; description: string; kpi_label: string; default_hours_saved_month: string | null; default_roi_month: string | null };
// `resolved` só vem preenchido quando a lista é pedida com `?vertical=` — são os valores já com a
// variante aplicada, que é exatamente o que a instanciação vai copiar.
export type ResolvedBlueprint = { name: string; area: string; description: string; kpi_label: string; kpi_unit: KpiUnit; kpi_direction: KpiDirection; hours_saved_month: string; roi_month: string };
export type DigitalEmployeeBlueprint = { id: number; name: string; area: BlueprintArea; area_display: string; description: string; kpi_label: string; kpi_unit: KpiUnit; kpi_direction: KpiDirection; default_hours_saved_month: string; default_roi_month: string; service: number | null; service_name: string; active: boolean; variants: BlueprintVariant[]; resolved: ResolvedBlueprint | null; has_variant: boolean };
export type JourneyPhaseStatus = "locked" | "active" | "done";
export type ProjectDeliverableStatus = "pending" | "delivered";
export type ProjectDeliverable = { id: number; project_phase: number; name: string; status: ProjectDeliverableStatus; document: number | null; position: number; delivered_at: string | null };
// As quatro saídas do decision gate (FDD 033). `""` é "ainda não decidido" — o gate não tem
// default, porque um default seria uma decisão que ninguém tomou.
// As sete saídas dos dois vocabulários de gate (ADR 0053): as quatro da Feasibility ("a
// tecnologia consegue fazer a tarefa?") e as três do PROVE ("funcionou em produção controlada?").
// Qual delas vale numa fase sai de `journey.ts`, a partir do `canonical_stage`.
export type GateDecision = "go" | "conditional_go" | "redesign" | "no_go" | "scale" | "iterate" | "stop";
export type ProjectChecklistItem = { id: number; project_phase: number; text: string; position: number; checked: boolean; checked_at: string | null };
// A jornada canônica de entrega — o vocabulário FDE (FDD 042). Classificação **opcional** da fase
// configurável; `""` é a fase operacional Biahflow sem equivalente FDE. `feasibility` é membro
// explícito e opcional: uma jornada que não a atravessa não tem fase mapeada nela.
export type CanonicalStage = "" | "discover" | "prioritize" | "feasibility" | "prove" | "scale" | "optimize";
// Quem/o quê a fase ativa espera (FDD 042). `""` = fluindo. `engineering` é classificação de
// delivery ("esperando engenharia"), não o estado de execução do GitHub — a fronteira é limpa.
export type WaitingParty = "" | "biahflow" | "client" | "engineering" | "external" | "human_gate";
// O estado semântico derivado, determinístico no backend (FDD 042). A tela mapeia situação →
// variante de selo, nunca recalcula a regra.
export type PhaseSituation = "active" | "completed" | "blocked" | "waiting_decision" | "cancelled" | "replanned" | "pending";
export type ProjectPhase = { id: number; project: number; phase: number; phase_name: string; phase_description: string; phase_position: number; requires_gate: boolean; canonical_stage: CanonicalStage; status: JourneyPhaseStatus; situation: PhaseSituation; started_at: string | null; completed_at: string | null; target_date: string | null; gate_decision: GateDecision | ""; gate_notes: string; checklist_waiver: string; waiting_party: WaitingParty; blocker_note: string; deliverables: ProjectDeliverable[]; checklist_items: ProjectChecklistItem[] };
export type PhaseEventKind = "started" | "completed" | "reopened" | "locked_by_redesign" | "gate_recorded" | "waiting_set" | "waiting_cleared";
export type PhaseEvent = { id: number; project: number; project_phase: number | null; phase_name: string; kind: PhaseEventKind; from_status: string; to_status: string; gate_decision: GateDecision | ""; waiting_party: WaitingParty; note: string; actor: number | null; actor_name: string | null; source: "user" | "system"; created_at: string };
export type ProjectTimeline = {
  project: number;
  phases: ProjectPhase[];
  current_phase: ProjectPhase | null;
  next_phase: { phase_name: string; canonical_stage: CanonicalStage } | null;
  next_gate: { phase_name: string; canonical_stage: CanonicalStage } | null;
  blockers: { phase_name: string; waiting_party: WaitingParty; blocker_note: string }[];
  events: PhaseEvent[];
};
export type DeliveryTimelineRow = { project_id: number; project_name: string; account_name: string; current_phase_name: string | null; canonical_stage: CanonicalStage; situation: PhaseSituation | null; waiting_party: WaitingParty; blocker_note: string; next_gate_name: string | null };
export type PhaseDeliverableTemplate = { id: number; phase: number; name: string; position: number };
export type PhaseChecklistItemTemplate = { id: number; phase: number; text: string; position: number };
export type JourneyPhaseTemplate = { id: number; name: string; description: string; position: number; active: boolean; requires_gate: boolean; canonical_stage: CanonicalStage; deliverables: PhaseDeliverableTemplate[]; checklist_items: PhaseChecklistItemTemplate[] };
export type LeadStatus = "new" | "contacted" | "qualified" | "discarded";
export type LeadFit = "high" | "medium" | "low" | "";
// O cadastro público que o enriquecimento trouxe (FDD 030). Todo campo é opcional porque o objeto
// inteiro é opcional: sem CNPJ, com a flag desligada ou com o fornecedor fora do ar, ele é `{}`.
export type LeadEnrichment = { cnpj?: string; legal_name?: string; trade_name?: string; cnae_code?: string; cnae_label?: string; size?: string; share_capital?: string; status?: string; city?: string; state?: string; opened_on?: string };
// `opportunity` era **alias de leitura** da `/api/v1/` para `commercial_opportunity`
// (`docs/ontology/aliases.md` §2c); a `/api/v2/` não o emite mais.
export type Lead = { id: number; name: string; email: string; company: string; phone: string; cnpj: string; message: string; source: string; status: LeadStatus; ai_fit: LeadFit; ai_score: number | null; ai_summary: string; ai_recommended_action: string; qualified_at: string | null; enrichment: LeadEnrichment; account: number | null; commercial_opportunity: number | null; qualification: number | null; qualification_outcome: QualificationOutcome | ""; created_at: string };

// A avaliação que decide se um lead vira venda (ADR 0049). Só `qualified` abre oportunidade
// comercial — e ela é um **segundo ato**, em `POST /qualifications/{id}/open-opportunity/`.
export type QualificationOutcome = "qualified" | "nurture" | "disqualified";
export type QualificationLevel = "high" | "medium" | "low" | "";
export type Qualification = { id: number; lead: number; lead_name: string; account: number | null; account_name: string; happened_at: string; assessor: number | null; fit: QualificationLevel; need: QualificationLevel; urgency: QualificationLevel; authority: QualificationLevel; capacity: QualificationLevel; evidence: string; outcome: QualificationOutcome; outcome_display: string; rationale: string; next_step: string; nurture_until: string | null; ai_suggested_outcome: QualificationOutcome | ""; ai_score_snapshot: number | null; legacy_opportunity: number | null; created_at: string; updated_at: string };

// O case de um projeto concluído (FDD 027). Os três campos de snapshot são **fotografia**: vêm
// congelados do backend e não há como reescrevê-los pela API — a tela só os exibe.
export type CaseStatus = "draft" | "review" | "published";
export type CaseMetric = { employee_id: number; blueprint_id: number | null; name: string; area: string; kpi_label: string; kpi_unit: KpiUnit; kpi_direction: KpiDirection; baseline: string | null; current: string | null; has_baseline: boolean; kpi_value: string; hours_saved_month: string };
export type CaseHealthSnapshot = { score: number; level: string; signals: { label: string; detail: string; weight: number }[] };
export type CaseRoiSnapshot = { revenue: string; cost: string; roi: number | null };
export type Case = { id: number; project: number; project_name: string; title: string; summary: string; vertical: number | null; vertical_name: string; account_name: string; metrics: CaseMetric[]; health_snapshot: CaseHealthSnapshot; roi_snapshot: CaseRoiSnapshot; status: CaseStatus; status_display: string; published_at: string | null; account_consent: boolean; consent_recorded_at: string | null; consent_recorded_by: number | null; anonymized: boolean; created_at: string; updated_at: string };

// Contas a receber (FDD 028). Valores em `string` porque é assim que o DRF serializa `DecimalField`
// — converter para `number` aqui perderia centavos em valores grandes, que é o oposto do objetivo.
// `is_overdue` é derivado no backend e não é `status === "overdue"`: o estado só vira `overdue` no
// job das 06:00, e entre a virada do dia e ele a tela precisa dizer a verdade.
export type InvoiceStatus = "draft" | "issued" | "paid" | "overdue" | "renegotiated" | "cancelled";
export type InvoiceMethod = "pix" | "boleto" | "card" | "transfer" | "other" | "";
export type Invoice = { id: number; account: number; account_name: string; project: number | null; project_name: string; service: number | null; service_name: string; number: string; amount: string; description: string; due_date: string; method: InvoiceMethod; method_display: string; status: InvoiceStatus; status_display: string; is_overdue: boolean; issued_at: string | null; issued_by: number | null; paid_at: string | null; settled_by: number | null; cancelled_at: string | null; cancelled_by: number | null; cancel_reason: string; provider: string; external_reference: string; payment_url: string; created_at: string; updated_at: string };
export type InvoiceSummary = { open: string; overdue: string; paid: string; open_count: number; overdue_count: number; paid_count: number };

// A régua de cobrança (FDD 036, ADR 0031). **Nada aqui é calculado no SPA.** Próximo degrau, régua
// aplicada, reincidência e motivo do silêncio chegam prontos de `/cobranca/painel/` — reimplementar
// qualquer um deles em TypeScript seria a segunda definição da régua, e as duas cópias não ficam
// vermelhas ao divergir: elas só passam a discordar do relógio, em silêncio.
// Os cinco degraus falam inglês desde a issue #122, fatia 5.4 (D10 do language-map): a classe
// virou `DunningContact`, o campo `dunning_step` e o valor persistido atravessou junto. Os
// **rótulos** continuam em pt-BR e continuam vindo do servidor (`*_display`) — nenhum mapa de
// rótulo nasce aqui, pelo motivo de sempre: seria a segunda definição da régua.
export type DunningStep = "pre_notice" | "reminder" | "firm" | "escalation" | "renegotiation";
export type CobrancaCanal = "email" | "interno";
// Por que a régua se calou, com as mesmas constantes do backend. Vazio quando há degrau.
export type CobrancaMotivo = "" | "suspensa" | "degrau_gasto" | "teto_de_frequencia" | "sem_degrau" | "estado_nao_cobravel";
// `relacao_longa` é cliente de um ano de casa e sem reincidência: o lembrete atrasa, o degrau firme
// não existe e o caso vai direto à escalada interna. `relacao_tensa` é insatisfação **declarada**
// vigente (FDD 037, ADR 0032): o degrau firme também não existe, mas a escalada interna antecipa —
// a régua nunca cala por causa da satisfação, ela troca de escada. Quem escolhe é o backend.
export type CobrancaRegua = "padrao" | "relacao_longa" | "relacao_tensa";
export type CobrancaSuspensaoResumo = { id: number; until: string; owner: number; owner_name: string };

// A satisfação do cliente (FDD 037, ADR 0032). `declared` é o cliente tendo dito; `perceived` é a
// leitura de quem entrega. **Só a declarada move número** — Health Score e escada de cobrança — e é
// essa distinção, não o nível, a decisão central da fatia: uma tela que tratasse as duas fontes
// iguais desfaria o que a ADR 0032 decidiu.
//
// Os valores falam inglês desde a issue #122, fatia 5.3 (D10 do language-map): a classe virou
// `SatisfactionRecord` e os dois enums atravessaram junto. As **chaves** `nivel`/`fonte` ficam —
// elas são chave de payload, e o prazo delas é a `/api/v2/` (`docs/ontology/aliases.md` §2c) —, e
// os rótulos em português vêm do `*_display` do servidor ou dos mapas de tela, não daqui.
export type SatisfactionLevel = "promoter" | "satisfied" | "neutral" | "dissatisfied";
export type SatisfactionSource = "declared" | "perceived";
export type SatisfactionRecord = {
  id: number; account: number; project: number | null; source_meeting: number | null;
  // A resposta de cobrança que a IA classificou e que originou este registro (FDD 038). É o que
  // faz o painel parar de oferecer o atalho depois do registro — sem ela, o mesmo sinal insistiria
  // para sempre. Continua sendo **uma pessoa** que salva: a IA lê, ela não registra (ADR 0032).
  source_activity: number | null;
  nivel: SatisfactionLevel; nivel_display: string; fonte: SatisfactionSource; fonte_display: string;
  happened_on: string; note: string; registered_by: number | null;
  created_at: string; updated_at: string;
};

export type CobrancaPainelLinha = {
  invoice: number; number: string; account: number; account_name: string;
  amount: string; due_date: string; status: InvoiceStatus; status_display: string;
  dias_de_atraso: number; payment_url: string;
  // As **chaves** `proximo_degrau*` ficam: elas são do dict cru do painel, e a família `Cobranca*`
  // segue sem coinagem (`docs/ontology/aliases.md`, "Termos ainda sem nome canônico"). O que
  // atravessou na fatia 5.4 foi o valor.
  proximo_degrau: DunningStep | null; proximo_degrau_display: string | null;
  proximo_degrau_em: string | null; motivo: CobrancaMotivo;
  // Só o **nível** da saúde, nunca o score nem os sinais: é a cerca comercial do backend, e a linha
  // vai para a tela. Nulo quando a fatura não está presa a projeto nenhum.
  health_level: HealthLevel | null; tempo_de_casa_dias: number; reincidente: boolean;
  regua: CobrancaRegua; recebido_do_cliente: string;
  suspensao: CobrancaSuspensaoResumo | null; regua_ligada: boolean;
  // A satisfação vigente (FDD 037): nível e fonte, ou os três `null` quando não há registro dentro
  // da janela de 90 dias. A fonte vai junto do nível porque a linha precisa dizer se é o cliente
  // falando ou a nossa leitura sobre ele — é o que separa o que move a régua do que não move.
  satisfacao_nivel: SatisfactionLevel | null; satisfacao_fonte: SatisfactionSource | null;
  satisfacao_dias: number | null;
  // Por que a relação está tensa (FDD 038). É rótulo e não decisão: as duas origens levam à mesma
  // escada, e quem diz qual escada vale continua sendo `regua`. Nulo quando não há tensão.
  tensao_causa: CobrancaTensaoCausa | null;
  // A leitura da IA sobre a última resposta do cliente que **ninguém registrou ainda** (ADR 0032).
  // Os quatro são nulos juntos. Não é satisfação — é uma resposta lida —, e some da linha assim que
  // alguém registrar a satisfação apontando para aquela interação.
  sinal_kind: Exclude<DunningSignal, ""> | null; sinal_display: string | null;
  sinal_em: string | null; sinal_activity: number | null;
};
export type CobrancaTensaoCausa = "satisfacao" | "entrega" | "ambas";
// `dunning_step`/`dunning_step_display` e não `degrau`/`degrau_display`: a SPA lê a `/api/v2/`, e
// lá o par legado não sai (`ALIASES_DEPRECIADOS`). Na `/api/v1/` os dois continuam saindo, para
// quem integrou antes da fatia 5.4. Pela mesma razão o tipo não declara `client_name`: morreu na
// `/api/v2/` junto do resto do alias `client`/`client_name` (issue #122, fatia 4a).
export type DunningContact = { id: number; invoice: number; invoice_number: string; account: number; dunning_step: DunningStep; dunning_step_display: string; canal: CobrancaCanal; canal_display: string; sent_on: string; subject: string; to_email: string; body: string; sent_by: number | null; ai_interaction: number | null; created_at: string };
// `client_name` morreu na `/api/v2/` junto do resto do alias `client`/`client_name` (issue #122,
// fatia 4a) — pelo mesmo motivo do `DunningContact` acima.
export type CobrancaSuspensao = { id: number; invoice: number | null; invoice_number: string; account: number | null; owner: number; until: string; reason: string; created_by: number | null; lifted_at: string | null; lifted_by: number | null; is_active: boolean; created_at: string; updated_at: string };
// A chave `degrau` fica: ela é do corpo e da resposta das actions `rascunhar`/`enviar`, e chave de
// action não muda de nome por versão (o precedente de `signers` era substituição, não renome). O
// **valor** dentro dela é o canônico — a v1 traduz o legado, a v2 o recusa.
export type CobrancaRascunho = { text: string; interaction: number; degrau: DunningStep };

// Base de conhecimento interna (FDD 029). `status` é derivado no backend — depende do dono da área
// e do relógio —, então a tela **não** o recalcula: reproduzi-lo aqui seria a segunda expressão da
// regra, e ela divergiria na primeira mudança de prazo.
export type KnowledgeStatus = "sem_dono" | "vencido" | "a_vencer" | "corrente";
export type KnowledgeKind = "decision" | "procedure" | "reference";
export type KnowledgeArea = { id: number; name: string; slug: string; position: number; active: boolean; owner: number | null; owner_name: string; review_interval_days: number };
export type KnowledgePiece = { id: number; area: number | null; area_name: string; owner_name: string; title: string; kind: KnowledgeKind; kind_display: string; source_path: string; summary: string; last_verified_at: string | null; verified_by: number | null; review_interval_days: number | null; status: KnowledgeStatus; next_review_at: string | null; is_gap: boolean; created_at: string; updated_at: string };
export type KnowledgeSummary = Record<KnowledgeStatus, number>;

// A citação que o agente devolve (ADR 0023). `stale` marca fonte vencida — a citação sem esse aviso
// legitimaria material velho, que é o modo de falha que a FDD 029 chama de pior que não ter KB.
export type AgentSource = { ref: string; piece: number; title: string; section: string; path: string; stale: boolean };
