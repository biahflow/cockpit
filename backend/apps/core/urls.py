from django.urls import include, path
from rest_framework.routers import DefaultRouter

from .views import (
    AcceptInvitationView,
    AccountViewSet,
    ActivityViewSet,
    AgentView,
    AiFeedbackView,
    AiMetricsView,
    AnalyticsView,
    ArtifactViewSet,
    BlueprintVariantViewSet,
    BookingCreateView,
    BookingSlotsView,
    CalendarSyncView,
    CaseViewSet,
    CobrancaSuspensaoViewSet,
    CobrancaViewSet,
    CommercialOpportunityViewSet,
    ConfigView,
    ContactViewSet,
    DashboardView,
    DecisaoViewSet,
    DigitalEmployeeBlueprintViewSet,
    DigitalEmployeeViewSet,
    DiscoverySessionViewSet,
    DiscoveryViewSet,
    DocumentViewSet,
    EngagementViewSet,
    EngineeringHandoffViewSet,
    EsignWebhookView,
    EvidenceViewSet,
    EvidenciaViewSet,
    FeasibilityAssessmentViewSet,
    FindingViewSet,
    GithubDeliveryProjectionViewSet,
    GithubDeliveryWebhookView,
    HealthView,
    ImprovementOpportunityViewSet,
    InvitationView,
    InvoiceViewSet,
    JourneyPhaseViewSet,
    KnowledgeAreaViewSet,
    KnowledgePieceViewSet,
    KPIViewSet,
    LeadIntakeView,
    LeadViewSet,
    LoginView,
    LogoutView,
    MeasurementViewSet,
    MeAvatarView,
    MeetingViewSet,
    MePasswordView,
    MeView,
    MilestoneViewSet,
    NotificationViewSet,
    PainPointViewSet,
    PaymentsWebhookView,
    PendenciaViewSet,
    PhaseChecklistItemViewSet,
    PhaseDeliverableViewSet,
    PipelineStageViewSet,
    PortalProjectSnapshotView,
    PriorityAssessmentViewSet,
    ProcessObservationViewSet,
    ProcessStepViewSet,
    ProcessViewSet,
    ProjectChecklistItemViewSet,
    ProjectDeliverableViewSet,
    ProjectMemberViewSet,
    ProjectPhaseViewSet,
    ProjectViewSet,
    ProveExperimentViewSet,
    QualificationViewSet,
    RecommendationsView,
    RiscoViewSet,
    RiskView,
    SatisfacaoViewSet,
    ServiceViewSet,
    SolutionHypothesisViewSet,
    TaskSyncIntakeView,
    TaskViewSet,
    UserAvatarView,
    UserViewSet,
    ValueLedgerEntryViewSet,
    VerticalViewSet,
    csrf,
)

router = DefaultRouter()
# A rota e o `basename` **não** mudam com o renome da classe (ADR 0052): a rota canônica
# `/accounts/` nasce na `/api/v2/`. O `basename` passa a ser explícito porque o derivado do
# queryset viraria `account` e quebraria todo `reverse("client-…")` do repositório.
router.register("clients", AccountViewSet, basename="client")
router.register("contacts", ContactViewSet)
router.register("activities", ActivityViewSet)
router.register("pipeline-stages", PipelineStageViewSet)
# A rota e o `basename` **não** mudam com o renome da classe (ADR 0052): a rota canônica
# `/commercial-opportunities/` nasce na `/api/v2/`. O `basename` passa a ser explícito porque
# o derivado do queryset viraria `commercialopportunity` e quebraria todo
# `reverse("opportunity-…")` do repositório.
router.register("opportunities", CommercialOpportunityViewSet, basename="opportunity")
# Entre a conta e o projeto (ADR 0050): o mandato que agrupa várias vendas e vários projetos.
router.register("engagements", EngagementViewSet)
router.register("projects", ProjectViewSet)
router.register("journey-phases", JourneyPhaseViewSet)
router.register("phase-deliverables", PhaseDeliverableViewSet)
router.register("phase-checklist-items", PhaseChecklistItemViewSet)
router.register("project-phases", ProjectPhaseViewSet)
router.register("project-deliverables", ProjectDeliverableViewSet)
router.register("project-checklist-items", ProjectChecklistItemViewSet)
router.register("project-members", ProjectMemberViewSet)
router.register("digital-employees", DigitalEmployeeViewSet)
router.register("milestones", MilestoneViewSet)
router.register("tasks", TaskViewSet)
router.register("meetings", MeetingViewSet)
router.register("pendencias", PendenciaViewSet)
router.register("decisoes", DecisaoViewSet)
# `riscos` (registro declarado, FDD 034) e não `risks` — a avaliação calculada já ocupa
# `/projects/{id}/risk/` e `/risk/`, e dois nomes iguais em português e inglês seriam a pior
# forma de distinguir duas coisas diferentes.
router.register("riscos", RiscoViewSet)
router.register("engineering-handoffs", EngineeringHandoffViewSet)
router.register("github-projections", GithubDeliveryProjectionViewSet)
router.register("satisfacoes", SatisfacaoViewSet)
# O Discovery estruturado (FDD 039): o processo é ancorado no **cliente**, e por isso as três
# rotas ficam fora de `/projects/`. Etapa e evidência pendem do processo, não do projeto.
#
# **As rotas ficam, e os `basename` viraram explícitos.** A fatia 4 da issue #67 renomeou as
# classes para `Process`/`ProcessStep` (ADR 0052); o `basename` derivado do queryset passaria a
# ser `process`/`processstep` e quebraria todo `reverse("processo-…")`. `/processes/` e
# `/process-steps/` nascem na `/api/v2/`, que é o prazo que a `docs/ontology/aliases.md` sempre
# deu à rota.
router.register("processos", ProcessViewSet, basename="processo")
router.register("processo-etapas", ProcessStepViewSet, basename="processoetapa")
router.register("evidencias", EvidenciaViewSet)
# O split Evidence/Finding e o Discovery (FDD 045, ADR 0049). As duas âncoras convivem e a rota
# mostra isso: `discoveries` e o que pende dele são de **projeto**; `evidence` e `findings` são da
# **conta**, como os processos logo acima. `evidence` no singular porque é substantivo incontável
# em inglês — "evidences" é o verbo, e um plural inventado seria um sinônimo criado para soar
# melhor, que é o que o language map proíbe.
router.register("discoveries", DiscoveryViewSet)
router.register("discovery-sessions", DiscoverySessionViewSet)
router.register("process-observations", ProcessObservationViewSet)
router.register("evidence", EvidenceViewSet, basename="evidence")
router.register("findings", FindingViewSet)
# A cadeia do PRIORITIZE (FDD 048, ADR 0054): dor → oportunidade de melhoria → avaliação →
# hipótese. **Nomes canônicos e nenhum alias**, ao contrário dos vizinhos de cima: alias existe
# para não quebrar chave que a `/api/v1/` já prometeu, e aqui não há chave antiga nenhuma — estes
# quatro modelos nascem com o nome do mapa de linguagem.
#
# `improvement-opportunities` no plural qualificado, e nunca `opportunities`: a rota de venda é
# `/commercial-opportunities/`, e as duas não se encostam (language-map §5).
router.register("pain-points", PainPointViewSet)
router.register("improvement-opportunities", ImprovementOpportunityViewSet)
router.register("priority-assessments", PriorityAssessmentViewSet)
router.register("solution-hypotheses", SolutionHypothesisViewSet)
# Feasibility, PROVE, KPI/Measurement e Value Ledger (FDD 049, ADR 0055). **Nomes canônicos e
# nenhum alias**, como os quatro da Fase 4 e pelo mesmo motivo: alias existe para não quebrar chave
# que a `/api/v1/` já prometeu, e estes cinco modelos nascem com o nome do mapa de linguagem.
#
# `kpis` e não `indicadores`: o termo canônico é KPI nas quatro superfícies (`language-map` §2).
router.register("feasibility-assessments", FeasibilityAssessmentViewSet)
router.register("prove-experiments", ProveExperimentViewSet)
router.register("kpis", KPIViewSet)
router.register("measurements", MeasurementViewSet)
router.register("value-ledger-entries", ValueLedgerEntryViewSet)
router.register("documents", DocumentViewSet)
router.register("artifacts", ArtifactViewSet)
router.register("cases", CaseViewSet)
router.register("invoices", InvoiceViewSet)
# **`cobranca/suspensoes` antes de `cobranca`, e a ordem não é estética.** O `DefaultRouter` gera
# `^cobranca/(?P<pk>[^/.]+)/$` para o detalhe, e essa rota casa com `cobranca/suspensoes/` lendo
# "suspensoes" como pk — registrada primeiro, ela sequestraria a lista de suspensões e o sintoma
# seria um 404 de detalhe onde deveria haver uma coleção.
router.register("cobranca/suspensoes", CobrancaSuspensaoViewSet, basename="cobranca-suspensao")
router.register("cobranca", CobrancaViewSet, basename="cobranca")
router.register("knowledge-areas", KnowledgeAreaViewSet)
router.register("knowledge-pieces", KnowledgePieceViewSet)
router.register("leads", LeadViewSet)
# A avaliação do lead (ADR 0049, FDD 044). Fora de `/leads/` porque um lead tem **várias**: o
# `nurture` de hoje vira `qualified` daqui a seis meses, e as duas são fatos distintos.
router.register("qualifications", QualificationViewSet)
router.register("notifications", NotificationViewSet, basename="notification")
router.register("services", ServiceViewSet)
router.register("verticals", VerticalViewSet)
router.register("digital-employee-blueprints", DigitalEmployeeBlueprintViewSet)
router.register("blueprint-variants", BlueprintVariantViewSet)
router.register("users", UserViewSet)

urlpatterns = [
    path("leads/intake/", LeadIntakeView.as_view(), name="lead-intake"),
    path("booking/slots/", BookingSlotsView.as_view(), name="booking-slots"),
    path("booking/book/", BookingCreateView.as_view(), name="booking-book"),
    path("tasks/sync/", TaskSyncIntakeView.as_view(), name="task-sync"),
    path("esign/webhook/", EsignWebhookView.as_view(), name="esign-webhook"),
    path("payments/webhook/", PaymentsWebhookView.as_view(), name="payments-webhook"),
    path("github/webhook/", GithubDeliveryWebhookView.as_view(), name="github-webhook"),
    path("", include(router.urls)),
    path("dashboard/", DashboardView.as_view(), name="dashboard"),
    path("analytics/", AnalyticsView.as_view(), name="analytics"),
    path("risk/", RiskView.as_view(), name="risk"),
    path("health/", HealthView.as_view(), name="health"),
    path("recommendations/", RecommendationsView.as_view(), name="recommendations"),
    path("agents/<str:key>/", AgentView.as_view(), name="agent"),
    path("ai/feedback/", AiFeedbackView.as_view(), name="ai-feedback"),
    path("ai/metrics/", AiMetricsView.as_view(), name="ai-metrics"),
    path(
        "portal/projects/<int:pk>/snapshot/",
        PortalProjectSnapshotView.as_view(),
        name="portal-project-snapshot",
    ),
    path("config/", ConfigView.as_view(), name="config"),
    path("config/sync-calendar/", CalendarSyncView.as_view(), name="config-sync-calendar"),
    # Antes do `include(router.urls)` não é necessário — o detalhe do router é ancorado e não
    # casaria `users/1/avatar/` — mas fica junto das demais rotas explícitas, como `leads/intake/`.
    path("users/<int:pk>/avatar/", UserAvatarView.as_view(), name="user-avatar"),
    path("auth/csrf/", csrf, name="csrf"),
    path("auth/login/", LoginView.as_view(), name="login"),
    path("auth/logout/", LogoutView.as_view(), name="logout"),
    path("auth/me/", MeView.as_view(), name="me"),
    # Tudo sob `auth/me/` opera sobre `request.user`, e é o que torna a escrita de perfil segura
    # sem afrouxar `RolePermission`: não existe alvo vindo do cliente para apontar para outra
    # pessoa. A leitura da foto é a única com id na URL, e ela é só leitura.
    path("auth/me/avatar/", MeAvatarView.as_view(), name="me-avatar"),
    path("auth/me/password/", MePasswordView.as_view(), name="me-password"),
    path("invitations/", InvitationView.as_view(), name="invitation"),
    path("invitations/accept/", AcceptInvitationView.as_view(), name="accept-invitation"),
]
