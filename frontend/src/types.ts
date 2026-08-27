export type PipelineStage = { id: number; name: string; kind: "open" | "won" | "lost"; position: number; opportunity_count?: number; estimated_total?: string | null };
export type Opportunity = { id: number; client: number; contact: number | null; title: string; scope: string; estimated_value: string; stage: number; stage_name: string; owner: number; expected_close_date: string; service: number | null; service_name: string; service_tier: ServiceTier; project: number | null; project_archived: boolean };
export type AiScoreDimension = { label: string; score: number };
export type Project = { id: number; name: string; description: string; client: number; owner: number; start_date: string; due_date: string; status: string; service: number | null; actual_value: string; cost: string; is_overdue: boolean; ai_maturity: number | null; ai_opportunity: number | null; ai_dimensions: AiScoreDimension[]; ai_score_summary: string; ai_scored_at: string | null; ai_score_reviewed: boolean; client_vertical: number | null; client_vertical_name: string };
export type ServiceTier = "discovery_express" | "discovery_assessment" | "implantacao" | "";
export type Service = { id: number; name: string; active: boolean; tier: ServiceTier; tier_display: string; list_price: string; summary: string };
export type TierFunnelRow = { tier: ServiceTier; label: string; total: number; open: number; won: number; lost: number; estimated_total: number; win_rate: number | null };
export type StageFunnelRow = { kind: ArtifactKind; label: string; total: number; sent: number; accepted: number; rejected: number; acceptance_rate: number | null; reached: number };
export type SourceFunnelRow = { source: string; leads: number; won: number; projects: number; revenue: number };
export type RoiRow = { label: string; revenue: number; cost: number; roi: number | null };
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
  pipeline: { id: number; name: string; kind: string; position: number; opportunity_count: number; estimated_total: number | null }[];
  roi: { revenue: number; cost: number; roi: number | null; by_client: RoiRow[]; by_service: RoiRow[] };
};
export type ClientStatus = "prospect" | "active";
export type Client = { id: number; name: string; legal_name: string; tax_id: string; owner: number; status: ClientStatus; vertical: number | null; vertical_name: string };
// `receives_billing` marca quem recebe cobrança (FDD 036). Sem ninguém marcado, o degrau **não**
// vira e-mail ao cliente: vira escalada interna com o motivo escrito — a casa cala quando não sabe
// em vez de chutar o destinatário de um e-mail sobre dinheiro.
export type Contact = { id: number; client: number; name: string; email: string; phone: string; job_title: string; receives_billing: boolean };
// Interação comercial com o cliente (FDD 035, ADR 0030) — a materialização das "Activities" do
// CRM na leitura FDE. `opportunity` é opcional e, quando preenchida, tem de ser do mesmo cliente
// (o backend recusa com 400; ver `docs/metodologia-fde.md`).
export type ActivityKind = "call" | "meeting" | "email" | "note";
// `cobranca_sinal` é lavrado por `POST /activities/{id}/classificar/` e é **só de leitura** aqui: a
// IA grava o sinal e não age (ADR 0031). Os três valores roteiam condutas diferentes — `esqueceu` já
// se resolveu com o lembrete, `nao_pode` pede renegociação, `insatisfeito` não é problema de
// cobrança e é onde insistir piora tudo.
export type CobrancaSinal = "" | "esqueceu" | "nao_pode" | "insatisfeito";
export type Activity = { id: number; client: number; opportunity: number | null; invoice: number | null; cobranca_sinal: CobrancaSinal; cobranca_sinal_display: string; kind: ActivityKind; kind_display: string; happened_on: string; summary: string; notes: string; owner: number | null; created_at: string; updated_at: string };
export type WorkItemStatus = "todo" | "in_progress" | "done";
export type Party = "provider" | "client";
export type Milestone = { id: number; project: number; title: string; description: string; owner: number; due_date: string; completed_at: string | null; status: WorkItemStatus; party: Party; is_overdue: boolean };
export type Task = Milestone & { milestone: number | null };
export type Meeting = { id: number; project: number; title: string; date: string; meeting_url: string; recording_url: string; transcript: string; status: "scheduled" | "held" };
export type Pendencia = { id: number; project: number; title: string; description: string; status: "open" | "resolved"; party: Party; owner: number | null; resolved_at: string | null };
export type Decisao = { id: number; project: number; title: string; rationale: string; decided_on: string | null; decided_by: string; status: "draft" | "published"; source_meeting: number | null; published_at: string | null };
// Risk Register do projeto (FDD 034) — o risco **declarado** por alguém, que não é o mesmo que a
// `RiskAssessment` calculada logo abaixo. Aquela deriva de prazo e item atrasado; esta é escrita.
export type RiscoNivel = "low" | "medium" | "high";
export type RiscoStatus = "open" | "mitigated" | "accepted" | "materialized";
export type Risco = { id: number; project: number; title: string; description: string; probability: RiscoNivel; impact: RiscoNivel; mitigation: string; status: RiscoStatus; owner: number | null; resolved_at: string | null };
// O Discovery estruturado (FDD 039, ADR 0034) — o **dado** do mapa da operação, que não é o
// `Artifact` de `kind=discovery` (a narrativa entregue ao cliente): aquele se lê, este se soma.
// Liga ao cliente e não ao projeto, porque o processo mapeado sobrevive à venda que o descobriu.
//
// **Os nove insumos são `string | null` e nulo é "não apurado", nunca zero.** Zerar afirmaria que
// executar o processo não custa nada; o backend devolve o que faltou em `custo.nao_apurado` em vez
// de somar zero, e a tela precisa poder dizer a mesma coisa.
export type Processo = { id: number; client: number; client_name: string; name: string; position: number; source_project: number | null; source_meeting: number | null; registered_by: number | null; volume_mes: number | null; tempo_horas: string | null; pessoas: number | null; custo_hora: string | null; retrabalho_mes: string | null; erros_mes: string | null; perdas_mes: string | null; espera_mes: string | null; risco_mes: string | null; custo: CustoEstadoAtual; created_at: string; updated_at: string };
// A conta do custo do estado atual, derivada e só de leitura. **Os valores são texto**, como
// `Invoice.amount`: dinheiro em `number` soma centavos com erro, e este total existe para ser
// levado a uma reunião. `nao_apurado` é o que separa "não há insumo" de "medimos e deu zero" —
// um total mostrado sem ele vira "custo zero" na leitura rápida. `sustentacao` responde a outra
// metade da metodologia: só há **fato** por trás do número, ou ainda é hipótese da casa.
export type CustoEstadoAtual = { parcelas: { label: string; valor: string }[]; total: string; nao_apurado: string[]; sustentacao: "sustentado" | "hipotese" };
// A etapa e o P-S-D-T-E-R dela (`docs/metodologia-fde.md:75-79`). Os seis campos são exatamente as
// seis letras, nessa ordem: é assim que a pergunta é feita na reunião, e um formulário fora de
// ordem faz quem preenche pular a que faltou. Aqui `tempo`, `erro` e `retrabalho` são **descrição**
// — os homônimos `_mes` do `Processo` são dinheiro e quantidade, e não se confundem.
export type ProcessoEtapa = { id: number; processo: number; name: string; position: number; pessoas: string; sistema: string; dados: string; tempo: string; erro: string; retrabalho: string };
export type EvidenciaForma = "entrevista" | "observacao" | "artefato" | "sistema" | "dado";
// FATO / HIPÓTESE / DESCONHECIDO (`docs/metodologia-fde.md:86`). **`rotulo` não tem default no
// banco (ADR 0034)** e não pode ganhar um na tela: um select que já abre em "hipótese" faz a casa
// escolher por quem não escolheu, e o erro cai sempre para o mesmo lado. `desconhecido` é valor de
// primeira classe — nomear o que ainda não se sabe é fazer o trabalho, não deixar de fazê-lo.
export type EvidenciaRotulo = "fato" | "hipotese" | "desconhecido";
export type Evidencia = { id: number; processo: number; etapa: number | null; forma: EvidenciaForma; forma_display: string; rotulo: EvidenciaRotulo; rotulo_display: string; content: string; source_meeting: number | null; registered_by: number | null };
export type SignatureRequest = { id: number; signer_email: string; status: "pending" | "signed" | "declined"; sign_url: string; reminded_at: string | null; signed_at: string | null; created_at: string };
export type DocumentEntry = { id: number; client: number | null; opportunity: number | null; project: number | null; file: string; drive_link: string; original_name: string; uploaded_by: number; created_at: string; signature_requests: SignatureRequest[] };
export type ArtifactKind = "discovery" | "assessment" | "proposal" | "contract";
export type ArtifactStatus = "draft" | "review" | "sent" | "accepted" | "rejected";
export type Artifact = { id: number; kind: ArtifactKind; kind_display: string; status: ArtifactStatus; status_display: string; title: string; content: string; opportunity: number | null; project: number | null; source_meeting: number | null; document: number | null; ai_interaction: number | null; created_by: number; sent_at: string | null; decided_at: string | null; created_at: string; updated_at: string };
export type Dashboard = { pipeline: PipelineStage[]; active_projects: number; overdue_count: number; upcoming_tasks: { id: number; title: string; due_date: string; project_id: number }[] };
// `is_admin` vem do backend (`User.is_admin_role`: papel admin **ou** superusuário) em vez de ser
// derivado aqui. É o mesmo predicado que a API usa para autorizar, então a tela não pode divergir
// dela — que era exatamente o defeito de `createsuperuser` (FDD 017).
export type SessionUser = { id: number; username: string; first_name: string; last_name: string; email: string; role: "admin" | "sales" | "delivery"; is_admin: boolean };
export type Role = "admin" | "sales" | "delivery";
export type Invitation = { id: number; email: string; role: Role; expires_at: string; accepted_at: string | null; created_at: string };
// `missing` traz os nomes das variáveis de ambiente que faltam para a integração poder ligar. Sem
// eles a tela só sabia dizer "faltam credenciais", e quem ia corrigir tinha de abrir o código.
export type IntegrationFlag = { key: string; label: string; enabled: boolean; configured: boolean; toggleable: boolean; missing: string[] };
export type AppConfig = { ai_enabled: boolean; calendar_enabled: boolean; esign_enabled: boolean; integrations: IntegrationFlag[] };
export type RiskSignal = { label: string; detail: string; weight: number };
export type RiskForecast = { predicted_finish_date: string; delay_days: number; basis: string };
export type RiskAssessment = { project_id: number; name: string; score: number; level: string; signals: RiskSignal[]; forecast: RiskForecast | null };
export type HealthLevel = "saudável" | "atenção" | "crítico";
export type HealthAssessment = { project_id: number; name: string; score: number; level: HealthLevel; signals: RiskSignal[] };
export type ClientOverview = {
  client_id: number;
  name: string;
  status: ClientStatus;
  roi: { revenue: number; cost: number; roi: number | null };
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
export type DigitalEmployee = { id: number; project: number; blueprint: number | null; name: string; area: string; description: string; status: DigitalEmployeeStatus; kpi_label: string; kpi_value: string; kpi_unit: KpiUnit; kpi_direction: KpiDirection; kpi_baseline: string | null; kpi_current: string | null; hours_saved_month: string; roi_month: string };
// A biblioteca de Funcionários Digitais (FDD 026): catálogo global + parametrização por vertical.
// Mesmo par que `JourneyPhaseTemplate`/`ProjectPhase`, um nível acima: o que a entrega instancia
// é uma **cópia**, e por isso `DigitalEmployee` não referencia nada aqui além da procedência.
export type Vertical = { id: number; name: string; slug: string; position: number; active: boolean };
export type BlueprintArea = "comercial" | "financeiro" | "rh" | "juridico" | "atendimento";
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
export type GateOutcome = "go" | "conditional_go" | "redesign" | "no_go";
export type ProjectChecklistItem = { id: number; project_phase: number; text: string; position: number; checked: boolean; checked_at: string | null };
export type ProjectPhase = { id: number; project: number; phase: number; phase_name: string; phase_description: string; phase_position: number; requires_gate: boolean; status: JourneyPhaseStatus; started_at: string | null; completed_at: string | null; target_date: string | null; gate_outcome: GateOutcome | ""; gate_notes: string; checklist_waiver: string; deliverables: ProjectDeliverable[]; checklist_items: ProjectChecklistItem[] };
export type PhaseDeliverableTemplate = { id: number; phase: number; name: string; position: number };
export type PhaseChecklistItemTemplate = { id: number; phase: number; text: string; position: number };
export type JourneyPhaseTemplate = { id: number; name: string; description: string; position: number; active: boolean; requires_gate: boolean; deliverables: PhaseDeliverableTemplate[]; checklist_items: PhaseChecklistItemTemplate[] };
export type LeadStatus = "new" | "contacted" | "qualified" | "discarded";
export type LeadFit = "high" | "medium" | "low" | "";
// O cadastro público que o enriquecimento trouxe (FDD 030). Todo campo é opcional porque o objeto
// inteiro é opcional: sem CNPJ, com a flag desligada ou com o fornecedor fora do ar, ele é `{}`.
export type LeadEnrichment = { cnpj?: string; legal_name?: string; trade_name?: string; cnae_code?: string; cnae_label?: string; size?: string; share_capital?: string; status?: string; city?: string; state?: string; opened_on?: string };
export type Lead = { id: number; name: string; email: string; company: string; phone: string; cnpj: string; message: string; source: string; status: LeadStatus; ai_fit: LeadFit; ai_score: number | null; ai_summary: string; ai_recommended_action: string; qualified_at: string | null; enrichment: LeadEnrichment; client: number | null; opportunity: number | null; created_at: string };

// O case de um projeto concluído (FDD 027). Os três campos de snapshot são **fotografia**: vêm
// congelados do backend e não há como reescrevê-los pela API — a tela só os exibe.
export type CaseStatus = "draft" | "review" | "published";
export type CaseMetric = { employee_id: number; blueprint_id: number | null; name: string; area: string; kpi_label: string; kpi_unit: KpiUnit; kpi_direction: KpiDirection; baseline: string | null; current: string | null; has_baseline: boolean; kpi_value: string; hours_saved_month: string };
export type CaseHealthSnapshot = { score: number; level: string; signals: { label: string; detail: string; weight: number }[] };
export type CaseRoiSnapshot = { revenue: string; cost: string; roi: number | null };
export type Case = { id: number; project: number; project_name: string; title: string; summary: string; vertical: number | null; vertical_name: string; client_name: string; metrics: CaseMetric[]; health_snapshot: CaseHealthSnapshot; roi_snapshot: CaseRoiSnapshot; status: CaseStatus; status_display: string; published_at: string | null; client_consent: boolean; consent_recorded_at: string | null; consent_recorded_by: number | null; anonymized: boolean; created_at: string; updated_at: string };

// Contas a receber (FDD 028). Valores em `string` porque é assim que o DRF serializa `DecimalField`
// — converter para `number` aqui perderia centavos em valores grandes, que é o oposto do objetivo.
// `is_overdue` é derivado no backend e não é `status === "overdue"`: o estado só vira `overdue` no
// job das 06:00, e entre a virada do dia e ele a tela precisa dizer a verdade.
export type InvoiceStatus = "draft" | "issued" | "paid" | "overdue" | "renegotiated" | "cancelled";
export type InvoiceMethod = "pix" | "boleto" | "card" | "transfer" | "other" | "";
export type Invoice = { id: number; client: number; client_name: string; project: number | null; project_name: string; service: number | null; service_name: string; number: string; amount: string; description: string; due_date: string; method: InvoiceMethod; method_display: string; status: InvoiceStatus; status_display: string; is_overdue: boolean; issued_at: string | null; issued_by: number | null; paid_at: string | null; settled_by: number | null; cancelled_at: string | null; cancelled_by: number | null; cancel_reason: string; provider: string; external_reference: string; payment_url: string; created_at: string; updated_at: string };
export type InvoiceSummary = { open: string; overdue: string; paid: string; open_count: number; overdue_count: number; paid_count: number };

// A régua de cobrança (FDD 036, ADR 0031). **Nada aqui é calculado no SPA.** Próximo degrau, régua
// aplicada, reincidência e motivo do silêncio chegam prontos de `/cobranca/painel/` — reimplementar
// qualquer um deles em TypeScript seria a segunda definição da régua, e as duas cópias não ficam
// vermelhas ao divergir: elas só passam a discordar do relógio, em silêncio.
export type CobrancaDegrau = "pre_aviso" | "lembrete" | "firme" | "escalada" | "renegociacao";
export type CobrancaCanal = "email" | "interno";
// Por que a régua se calou, com as mesmas constantes do backend. Vazio quando há degrau.
export type CobrancaMotivo = "" | "suspensa" | "degrau_gasto" | "teto_de_frequencia" | "sem_degrau" | "estado_nao_cobravel";
// `relacao_longa` é cliente de um ano de casa e sem reincidência: o lembrete atrasa, o degrau firme
// não existe e o caso vai direto à escalada interna. `relacao_tensa` é insatisfação **declarada**
// vigente (FDD 037, ADR 0032): o degrau firme também não existe, mas a escalada interna antecipa —
// a régua nunca cala por causa da satisfação, ela troca de escada. Quem escolhe é o backend.
export type CobrancaRegua = "padrao" | "relacao_longa" | "relacao_tensa";
export type CobrancaSuspensaoResumo = { id: number; until: string; owner: number; owner_name: string };

// A satisfação do cliente (FDD 037, ADR 0032). `declarada` é o cliente tendo dito; `percebida` é a
// leitura de quem entrega. **Só a declarada move número** — Health Score e escada de cobrança — e é
// essa distinção, não o nível, a decisão central da fatia: uma tela que tratasse as duas fontes
// iguais desfaria o que a ADR 0032 decidiu.
export type SatisfacaoNivel = "promotor" | "satisfeito" | "neutro" | "insatisfeito";
export type SatisfacaoFonte = "declarada" | "percebida";
export type Satisfacao = {
  id: number; client: number; project: number | null; source_meeting: number | null;
  // A resposta de cobrança que a IA classificou e que originou este registro (FDD 038). É o que
  // faz o painel parar de oferecer o atalho depois do registro — sem ela, o mesmo sinal insistiria
  // para sempre. Continua sendo **uma pessoa** que salva: a IA lê, ela não registra (ADR 0032).
  source_activity: number | null;
  nivel: SatisfacaoNivel; nivel_display: string; fonte: SatisfacaoFonte; fonte_display: string;
  happened_on: string; note: string; registered_by: number | null;
  created_at: string; updated_at: string;
};

export type CobrancaPainelLinha = {
  invoice: number; number: string; client: number; client_name: string;
  amount: string; due_date: string; status: InvoiceStatus; status_display: string;
  dias_de_atraso: number; payment_url: string;
  proximo_degrau: CobrancaDegrau | null; proximo_degrau_display: string | null;
  proximo_degrau_em: string | null; motivo: CobrancaMotivo;
  // Só o **nível** da saúde, nunca o score nem os sinais: é a cerca comercial do backend, e a linha
  // vai para a tela. Nulo quando a fatura não está presa a projeto nenhum.
  health_level: HealthLevel | null; tempo_de_casa_dias: number; reincidente: boolean;
  regua: CobrancaRegua; recebido_do_cliente: string;
  suspensao: CobrancaSuspensaoResumo | null; regua_ligada: boolean;
  // A satisfação vigente (FDD 037): nível e fonte, ou os três `null` quando não há registro dentro
  // da janela de 90 dias. A fonte vai junto do nível porque a linha precisa dizer se é o cliente
  // falando ou a nossa leitura sobre ele — é o que separa o que move a régua do que não move.
  satisfacao_nivel: SatisfacaoNivel | null; satisfacao_fonte: SatisfacaoFonte | null;
  satisfacao_dias: number | null;
  // Por que a relação está tensa (FDD 038). É rótulo e não decisão: as duas origens levam à mesma
  // escada, e quem diz qual escada vale continua sendo `regua`. Nulo quando não há tensão.
  tensao_causa: CobrancaTensaoCausa | null;
  // A leitura da IA sobre a última resposta do cliente que **ninguém registrou ainda** (ADR 0032).
  // Os quatro são nulos juntos. Não é satisfação — é uma resposta lida —, e some da linha assim que
  // alguém registrar a satisfação apontando para aquela interação.
  sinal_kind: Exclude<CobrancaSinal, ""> | null; sinal_display: string | null;
  sinal_em: string | null; sinal_activity: number | null;
};
export type CobrancaTensaoCausa = "satisfacao" | "entrega" | "ambas";
export type CobrancaContato = { id: number; invoice: number; invoice_number: string; client: number; client_name: string; degrau: CobrancaDegrau; degrau_display: string; canal: CobrancaCanal; canal_display: string; sent_on: string; subject: string; to_email: string; body: string; sent_by: number | null; ai_interaction: number | null; created_at: string };
export type CobrancaSuspensao = { id: number; invoice: number | null; invoice_number: string; client: number | null; client_name: string; owner: number; until: string; reason: string; created_by: number | null; lifted_at: string | null; lifted_by: number | null; is_active: boolean; created_at: string; updated_at: string };
export type CobrancaRascunho = { text: string; interaction: number; degrau: CobrancaDegrau };

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

// Estado de engenharia do GitHub projetado no Pulse (FDD 041, ADR 0046). Somente leitura: a tela
// não escreve nada de volta, e a Issue #41 reserva comando sobre o GitHub para um contrato próprio.
//
// `is_stale`, `age_seconds` e `last_error_age_seconds` **vêm calculados do backend** e a tela não
// os recalcula. O limiar de obsolescência mora em `GITHUB_PROJECTION_STALE_AFTER_SECONDS`; uma
// segunda definição de "velho" aqui divergiria da primeira em silêncio (DAP GH-41 r1).
export type GithubIssueState = "open" | "closed";
export type GithubPrState = "none" | "open" | "merged" | "closed";
export type GithubCiState = "none" | "pending" | "success" | "failure";
export type GithubObservedVia = "webhook" | "reconciliation";
export type GithubErrorKind = "" | "unavailable" | "forbidden" | "missing";
export type GithubProjection = {
  id: number; handoff: number; project: number;
  repository: string; issue_number: number | null; issue_url: string; reference: string;
  issue_state: GithubIssueState; issue_title: string;
  pr_number: number | null; pr_state: GithubPrState;
  head_sha: string; ci_state: GithubCiState;
  observed_at: string; observed_via: GithubObservedVia;
  age_seconds: number; is_stale: boolean;
  last_error_kind: GithubErrorKind; last_error_at: string | null; last_error_age_seconds: number | null;
  source_updated_at: string | null; created_at: string; updated_at: string;
};
