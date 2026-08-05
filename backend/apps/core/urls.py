from django.urls import include, path
from rest_framework.routers import DefaultRouter

from .views import (
    AcceptInvitationView,
    AgentView,
    AiFeedbackView,
    AiMetricsView,
    AnalyticsView,
    ArtifactViewSet,
    BookingCreateView,
    BookingSlotsView,
    CalendarSyncView,
    ClientViewSet,
    ConfigView,
    ContactViewSet,
    DashboardView,
    DigitalEmployeeViewSet,
    DocumentViewSet,
    EsignWebhookView,
    HealthView,
    InvitationView,
    JourneyPhaseViewSet,
    LeadIntakeView,
    LeadViewSet,
    LoginView,
    LogoutView,
    MeetingViewSet,
    MeView,
    MilestoneViewSet,
    NotificationViewSet,
    OpportunityViewSet,
    PendenciaViewSet,
    PhaseDeliverableViewSet,
    PipelineStageViewSet,
    PortalProjectSnapshotView,
    ProjectDeliverableViewSet,
    ProjectPhaseViewSet,
    ProjectViewSet,
    RecommendationsView,
    RiskView,
    ServiceViewSet,
    TaskSyncIntakeView,
    TaskViewSet,
    UserViewSet,
    csrf,
)

router = DefaultRouter()
router.register("clients", ClientViewSet)
router.register("contacts", ContactViewSet)
router.register("pipeline-stages", PipelineStageViewSet)
router.register("opportunities", OpportunityViewSet)
router.register("projects", ProjectViewSet)
router.register("journey-phases", JourneyPhaseViewSet)
router.register("phase-deliverables", PhaseDeliverableViewSet)
router.register("project-phases", ProjectPhaseViewSet)
router.register("project-deliverables", ProjectDeliverableViewSet)
router.register("digital-employees", DigitalEmployeeViewSet)
router.register("milestones", MilestoneViewSet)
router.register("tasks", TaskViewSet)
router.register("meetings", MeetingViewSet)
router.register("pendencias", PendenciaViewSet)
router.register("documents", DocumentViewSet)
router.register("artifacts", ArtifactViewSet)
router.register("leads", LeadViewSet)
router.register("notifications", NotificationViewSet, basename="notification")
router.register("services", ServiceViewSet)
router.register("users", UserViewSet)

urlpatterns = [
    path("leads/intake/", LeadIntakeView.as_view(), name="lead-intake"),
    path("booking/slots/", BookingSlotsView.as_view(), name="booking-slots"),
    path("booking/book/", BookingCreateView.as_view(), name="booking-book"),
    path("tasks/sync/", TaskSyncIntakeView.as_view(), name="task-sync"),
    path("esign/webhook/", EsignWebhookView.as_view(), name="esign-webhook"),
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
