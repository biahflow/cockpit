from django.urls import include, path
from rest_framework.routers import DefaultRouter

from .views import (
    AcceptInvitationView,
    AccountRungViewSet,
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
    ClientViewSet,
    CobrancaSuspensaoViewSet,
    CobrancaViewSet,
    ConfigView,
    ContactViewSet,
    DashboardView,
    DecisaoViewSet,
    DigitalEmployeeBlueprintViewSet,
    DigitalEmployeeViewSet,
    DocumentViewSet,
    EngineeringHandoffViewSet,
    EsignWebhookView,
    EvidenciaViewSet,
    GithubProjectionViewSet,
    GithubWebhookView,
    HealthView,
    InvitationView,
    InvoiceViewSet,
    JourneyPhaseViewSet,
    KnowledgeAreaViewSet,
    KnowledgePieceViewSet,
    LeadIntakeView,
    LeadViewSet,
    LoginView,
    LogoutView,
    MeetingViewSet,
    MeView,
    MilestoneViewSet,
    NotificationViewSet,
    OpportunityViewSet,
    PaymentsWebhookView,
    PendenciaViewSet,
    PhaseChecklistItemViewSet,
    PhaseDeliverableViewSet,
    PipelineStageViewSet,
    PortalProjectSnapshotView,
    ProcessoEtapaViewSet,
    ProcessoViewSet,
    ProjectChecklistItemViewSet,
    ProjectDeliverableViewSet,
    ProjectMemberViewSet,
    ProjectPhaseViewSet,
    ProjectViewSet,
    RecommendationsView,
    RiscoViewSet,
    RiskView,
    SatisfacaoViewSet,
    ServiceViewSet,
    TaskSyncIntakeView,
    TaskViewSet,
    UserViewSet,
    VerticalViewSet,
    csrf,
)

router = DefaultRouter()
router.register("clients", ClientViewSet)
router.register("contacts", ContactViewSet)
# A escada FDE (FDD 042) é da **conta** e não do projeto, e por isso a rota fica ao lado de
# `clients` em vez de pendurada em `/projects/`. `/project-phases/` continua sendo a jornada
# de entrega da FDD 011, que é outro eixo e não se confunde com este.
router.register("account-rungs", AccountRungViewSet)
router.register("activities", ActivityViewSet)
router.register("pipeline-stages", PipelineStageViewSet)
router.register("opportunities", OpportunityViewSet)
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
# A projeção do estado de engenharia (FDD 041) é **do handoff**, não do projeto, e é por
# isso que a rota é uma coleção própria com `?project=`: um projeto tem 0..N referências, e
# pendurá-la em `/projects/{id}/` obrigaria a eleger "a" referência — escolha que o modelo
# de dados não tem (DAP GH-41 r1, decisão 4).
router.register("github-projections", GithubProjectionViewSet)
router.register("satisfacoes", SatisfacaoViewSet)
# O Discovery estruturado (FDD 039): o processo é ancorado no **cliente**, e por isso as três
# rotas ficam fora de `/projects/`. Etapa e evidência pendem do processo, não do projeto.
router.register("processos", ProcessoViewSet)
router.register("processo-etapas", ProcessoEtapaViewSet)
router.register("evidencias", EvidenciaViewSet)
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
    path("github/webhook/", GithubWebhookView.as_view(), name="github-webhook"),
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
    path("auth/csrf/", csrf, name="csrf"),
    path("auth/login/", LoginView.as_view(), name="login"),
    path("auth/logout/", LogoutView.as_view(), name="logout"),
    path("auth/me/", MeView.as_view(), name="me"),
    path("invitations/", InvitationView.as_view(), name="invitation"),
    path("invitations/accept/", AcceptInvitationView.as_view(), name="accept-invitation"),
]
