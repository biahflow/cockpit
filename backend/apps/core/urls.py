from django.urls import URLPattern, URLResolver, include, path
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
    BusinessCaseViewSet,
    CalendarSyncView,
    CaseViewSet,
    CobrancaSuspensaoViewSet,
    CommercialOpportunityViewSet,
    ConfigView,
    ContactViewSet,
    DashboardView,
    DecisaoViewSet,
    DigitalEmployeeBlueprintViewSet,
    DigitalEmployeeViewSet,
    DiscoveryBookingCreateView,
    DiscoveryBookingSlotsView,
    DiscoverySessionViewSet,
    DiscoveryViewSet,
    DocumentViewSet,
    DunningContactViewSet,
    EngagementViewSet,
    EngineeringHandoffViewSet,
    EsignWebhookView,
    EvidenceViewSet,
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
    SatisfactionRecordViewSet,
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
# A rota e o `basename` **não** mudam com o renome da classe (ADR 0052): a rota canônica
# `/satisfaction-records/` nasce na `/api/v2/`. O `basename` passa a ser explícito porque o
# derivado do queryset viraria `satisfactionrecord` e quebraria todo `reverse("satisfacao-…")`.
router.register("satisfacoes", SatisfactionRecordViewSet, basename="satisfacao")
# O Discovery estruturado (FDD 039): o processo é ancorado no **cliente**, e por isso as rotas
# ficam fora de `/projects/`. A etapa pende do processo, não do projeto; o achado agora vive no
# split `evidence`/`findings` logo abaixo (a `Evidencia` legada saiu na Fase 6, ADR 0052).
#
# **As rotas ficam, e os `basename` viraram explícitos.** A fatia 4 da issue #67 renomeou as
# classes para `Process`/`ProcessStep` (ADR 0052); o `basename` derivado do queryset passaria a
# ser `process`/`processstep` e quebraria todo `reverse("processo-…")`. `/processes/` e
# `/process-steps/` nascem na `/api/v2/`, que é o prazo que a `docs/ontology/aliases.md` sempre
# deu à rota.
router.register("processos", ProcessViewSet, basename="processo")
router.register("processo-etapas", ProcessStepViewSet, basename="processoetapa")
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
# A justificativa do investimento (FDD 053, ADR 0069), ao lado da cadeia que a sustenta: ela cita
# a hipótese escolhida e a avaliação vigente da mesma oportunidade.
#
# `business-cases` e nunca `cases`: `/cases/` já é a prova social congelada (FDD 027), e o mapa de
# linguagem §2 põe cada um no "nunca chamar de" do outro. Nome canônico e nenhum alias — não há
# chave antiga que a `/api/v1/` tenha prometido.
router.register("business-cases", BusinessCaseViewSet)
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
router.register("cobranca", DunningContactViewSet, basename="cobranca")
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

# ---------------------------------------------------------------------------------------------
# A `/api/v2/` (issue #122) — as mesmas rotas, com os nomes canônicos
# ---------------------------------------------------------------------------------------------
#
# **A tabela é o `registry` do router acima, e não uma segunda lista.** Uma lista paralela com as
# 57 rotas repetidas divergiria da primeira no dia em que alguém registrasse a 58ª só de um lado —
# e a divergência não deixaria nada vermelho, porque as duas versões continuariam respondendo.
# `SimpleRouter.registry` já é exatamente `(prefixo, viewset, basename)` para cada registro, na
# ordem em que foram feitos: derivar dele preserva de graça a ordem que `cobranca/suspensoes`
# exige (ver o comentário lá em cima) e mantém a `/api/v1/` byte a byte igual à de antes, porque
# nenhuma linha dela é reescrita.
#
# Só **cinco** prefixos mudam — os que `docs/ontology/aliases.md` marcou para morrer aqui. Os
# quatro primeiros vieram da issue #67; `satisfacoes` entrou na fatia 5.3 da #122, quando a classe
# ganhou nome canônico (`SatisfactionRecord`) e a rota passou a ter para onde ir.
PREFIXOS_CANONICOS_DA_V2: dict[str, str] = {
    "clients": "accounts",
    "opportunities": "commercial-opportunities",
    "processos": "processes",
    "processo-etapas": "process-steps",
    "satisfacoes": "satisfaction-records",
}

router_da_v2 = DefaultRouter()
# Sem isto as duas raízes se chamariam `api-root` e `reverse("api-root")` viraria loteria — vence a
# última incluída. É o mesmo motivo do prefixo `v2-` nos basenames logo abaixo.
router_da_v2.root_view_name = "v2-api-root"
for _prefixo, _viewset, _basename in router.registry:
    # `basename` prefixado em **todas** as rotas, e não só nas quatro renomeadas: sem o prefixo,
    # `reverse("contact-detail")` passaria a ter dois alvos e devolveria o da última versão
    # registrada — a `/api/v1/` quebraria sem ninguém ter tocado nela.
    router_da_v2.register(
        PREFIXOS_CANONICOS_DA_V2.get(_prefixo, _prefixo), _viewset, basename=f"v2-{_basename}"
    )


def _rotas(router_da_versao: DefaultRouter, prefixo_do_nome: str) -> list[URLPattern | URLResolver]:
    """As rotas de uma versão: as explícitas, o router, e os nomes com o prefixo da versão.

    Uma fábrica e não duas listas, pelo motivo do `registry` acima: as rotas fora do router já
    nascem com o nome canônico e são as mesmas nas duas versões — copiá-las seria assinar que a
    próxima só entra em uma delas.
    """

    def nome(basico: str) -> str:
        return f"{prefixo_do_nome}{basico}"

    return [
        path("leads/intake/", LeadIntakeView.as_view(), name=nome("lead-intake")),
        path("booking/slots/", BookingSlotsView.as_view(), name=nome("booking-slots")),
        path("booking/book/", BookingCreateView.as_view(), name=nome("booking-book")),
        # O agendamento do Discovery pelo cliente (FDD 013, DAP `dap-agendamento-discovery-r1`).
        # Sob `booking/` porque é a mesma agenda e a mesma tabela; em rota própria porque a
        # credencial é outra — token no link, sem `X-Intake-Token`.
        path(
            "booking/discovery/slots/",
            DiscoveryBookingSlotsView.as_view(),
            name=nome("discovery-booking-slots"),
        ),
        path(
            "booking/discovery/",
            DiscoveryBookingCreateView.as_view(),
            name=nome("discovery-booking-create"),
        ),
        path("tasks/sync/", TaskSyncIntakeView.as_view(), name=nome("task-sync")),
        path("esign/webhook/", EsignWebhookView.as_view(), name=nome("esign-webhook")),
        path("payments/webhook/", PaymentsWebhookView.as_view(), name=nome("payments-webhook")),
        path("github/webhook/", GithubDeliveryWebhookView.as_view(), name=nome("github-webhook")),
        path("", include(router_da_versao.urls)),
        path("dashboard/", DashboardView.as_view(), name=nome("dashboard")),
        path("analytics/", AnalyticsView.as_view(), name=nome("analytics")),
        path("risk/", RiskView.as_view(), name=nome("risk")),
        path("health/", HealthView.as_view(), name=nome("health")),
        path("recommendations/", RecommendationsView.as_view(), name=nome("recommendations")),
        path("agents/<str:key>/", AgentView.as_view(), name=nome("agent")),
        path("ai/feedback/", AiFeedbackView.as_view(), name=nome("ai-feedback")),
        path("ai/metrics/", AiMetricsView.as_view(), name=nome("ai-metrics")),
        path(
            "portal/projects/<int:pk>/snapshot/",
            PortalProjectSnapshotView.as_view(),
            name=nome("portal-project-snapshot"),
        ),
        path("config/", ConfigView.as_view(), name=nome("config")),
        path(
            "config/sync-calendar/",
            CalendarSyncView.as_view(),
            name=nome("config-sync-calendar"),
        ),
        # Antes do `include(router.urls)` não é necessário — o detalhe do router é ancorado e não
        # casaria `users/1/avatar/` — mas fica junto das demais rotas explícitas, como
        # `leads/intake/`.
        path("users/<int:pk>/avatar/", UserAvatarView.as_view(), name=nome("user-avatar")),
        path("auth/csrf/", csrf, name=nome("csrf")),
        path("auth/login/", LoginView.as_view(), name=nome("login")),
        path("auth/logout/", LogoutView.as_view(), name=nome("logout")),
        path("auth/me/", MeView.as_view(), name=nome("me")),
        # Tudo sob `auth/me/` opera sobre `request.user`, e é o que torna a escrita de perfil
        # segura sem afrouxar `RolePermission`: não existe alvo vindo do cliente para apontar para
        # outra pessoa. A leitura da foto é a única com id na URL, e ela é só leitura.
        path("auth/me/avatar/", MeAvatarView.as_view(), name=nome("me-avatar")),
        path("auth/me/password/", MePasswordView.as_view(), name=nome("me-password")),
        path("invitations/", InvitationView.as_view(), name=nome("invitation")),
        path(
            "invitations/accept/",
            AcceptInvitationView.as_view(),
            name=nome("accept-invitation"),
        ),
    ]


urlpatterns = _rotas(router, "")
# Consumida por `apps/core/urls_v2.py`, que é o módulo que o `config/urls.py` inclui sob
# `api/v2/`. Duas listas no mesmo módulo, uma fábrica só.
urlpatterns_da_v2 = _rotas(router_da_v2, "v2-")
