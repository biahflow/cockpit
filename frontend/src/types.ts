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
export type Contact = { id: number; client: number; name: string; email: string; phone: string; job_title: string };
export type WorkItemStatus = "todo" | "in_progress" | "done";
export type Party = "provider" | "client";
export type Milestone = { id: number; project: number; title: string; description: string; owner: number; due_date: string; completed_at: string | null; status: WorkItemStatus; party: Party; is_overdue: boolean };
export type Task = Milestone & { milestone: number | null };
export type Meeting = { id: number; project: number; title: string; date: string; meeting_url: string; recording_url: string; transcript: string; status: "scheduled" | "held" };
export type Pendencia = { id: number; project: number; title: string; description: string; status: "open" | "resolved"; party: Party; owner: number | null; resolved_at: string | null };
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
export type ProjectPhase = { id: number; project: number; phase: number; phase_name: string; phase_description: string; phase_position: number; status: JourneyPhaseStatus; started_at: string | null; completed_at: string | null; target_date: string | null; deliverables: ProjectDeliverable[] };
export type PhaseDeliverableTemplate = { id: number; phase: number; name: string; position: number };
export type JourneyPhaseTemplate = { id: number; name: string; description: string; position: number; active: boolean; deliverables: PhaseDeliverableTemplate[] };
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
