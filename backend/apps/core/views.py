from __future__ import annotations

import hmac
import json
from datetime import datetime, timedelta
from decimal import Decimal
from typing import cast

from django.conf import settings
from django.contrib.auth import authenticate, login, logout
from django.core import signing
from django.core.mail import send_mail
from django.db import IntegrityError, transaction
from django.db.models import Avg, Count, Q, Sum
from django.http import FileResponse
from django.middleware.csrf import get_token
from django.shortcuts import get_object_or_404
from django.utils import timezone
from drf_spectacular.utils import extend_schema, inline_serializer
from rest_framework import serializers, status, viewsets
from rest_framework.decorators import action, api_view, permission_classes
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.throttling import ScopedRateThrottle
from rest_framework.views import APIView

from . import (
    agents,
    ai,
    ai_score,
    booking,
    calendar_sync,
    drive,
    esign,
    flags,
    health,
    journey,
    kickoff,
    portal,
    qualification,
    recommendations,
    risk,
    tasksync,
)
from .models import (
    AiInteraction,
    AppSetting,
    Client,
    Contact,
    DigitalEmployee,
    Document,
    Invitation,
    JourneyPhase,
    Lead,
    Meeting,
    Milestone,
    Notification,
    Opportunity,
    Pendencia,
    PhaseDeliverable,
    PipelineStage,
    Project,
    ProjectDeliverable,
    ProjectPhase,
    Service,
    SignatureRequest,
    Task,
    User,
)
from .permissions import RolePermission
from .serializers import (
    AcceptInvitationSerializer,
    BookingCreateSerializer,
    ClientSerializer,
    ContactSerializer,
    DigitalEmployeeSerializer,
    DocumentSerializer,
    InvitationSerializer,
    JourneyPhaseSerializer,
    LeadIntakeSerializer,
    LeadSerializer,
    LinkExternalSerializer,
    LoginSerializer,
    MeetingSerializer,
    MilestoneSerializer,
    NotificationSerializer,
    OpportunitySerializer,
    PendenciaSerializer,
    PhaseDeliverableSerializer,
    PipelineStageSerializer,
    ProjectDeliverableSerializer,
    ProjectPhaseSerializer,
    ProjectSerializer,
    ServiceSerializer,
    SignatureRequestSerializer,
    TaskSerializer,
    TaskSyncSerializer,
    UserSerializer,
)


class ArchiveModelViewSet(viewsets.ModelViewSet):
    permission_classes = [RolePermission]

    def get_queryset(self):  # type: ignore[no-untyped-def]
        return self.queryset.filter(archived_at__isnull=True)

    def perform_destroy(self, instance) -> None:  # type: ignore[no-untyped-def]
        instance.archive()


class QueryParamFilterMixin:
    """Filtra a lista por chaves estrangeiras informadas em query params (ex.: ?project=1)."""

    filter_fields: tuple[str, ...] = ()

    def get_queryset(self):  # type: ignore[no-untyped-def]
        queryset = super().get_queryset()  # type: ignore[misc]
        for field in self.filter_fields:
            value = self.request.query_params.get(field)  # type: ignore[attr-defined]
            if value and value.isdigit():
                queryset = queryset.filter(**{field: value})
        return queryset


class CalendarActionMixin:
    """Ação para lançar o item (marco/tarefa) no Google Calendar (atrás de flag)."""

    @action(detail=True, methods=["post"], url_path="add-to-calendar")
    def add_to_calendar(self, request: Request, pk: str | None = None) -> Response:
        item = self.get_object()  # type: ignore[attr-defined]
        if not calendar_sync.is_enabled():
            return Response({"detail": "Calendário desativado."}, status=status.HTTP_503_SERVICE_UNAVAILABLE)
        origin = f"{item._meta.model_name}:{item.id}"
        link = calendar_sync.create_event(item.title, item.due_date, origin=origin)
        return Response({"link": link})


def _ai_run(request, feature, system, user_prompt, project=None, opportunity=None):  # type: ignore[no-untyped-def]
    """Guarda (flag + limite), executa a IA e registra a auditoria."""
    if not ai.is_enabled():
        return Response({"detail": "Recurso de IA está desativado."}, status=status.HTTP_503_SERVICE_UNAVAILABLE)
    if not ai.within_daily_limit(request.user):
        return Response({"detail": "Limite diário de uso de IA atingido."}, status=status.HTTP_429_TOO_MANY_REQUESTS)
    text, usage = ai.complete(system, user_prompt)
    interaction = AiInteraction.objects.create(
        user=request.user, feature=feature, project=project, opportunity=opportunity,
        prompt_tokens=usage.get("prompt_tokens", 0), completion_tokens=usage.get("completion_tokens", 0),
    )
    return Response({"text": text, "interaction": interaction.id})


def build_client_overview(client: Client) -> dict[str, object]:
    """Agrega o estado de um cliente para a visão multi-cliente 🟢🟡🔴 e o painel do detalhe.

    Semáforo = pior saúde entre os projetos ativos (é onde agir). Fase/risco vêm desse mesmo
    projeto-foco; o ROI soma todos os projetos do cliente (padrão de `AnalyticsView`).
    """
    today = timezone.localdate()
    projects = list(client.projects.filter(archived_at__isnull=True))
    active = [project for project in projects if project.status != Project.Status.COMPLETED]
    revenue = sum((project.actual_value for project in projects), Decimal("0"))
    cost = sum((project.cost for project in projects), Decimal("0"))
    overview: dict[str, object] = {
        "client_id": client.pk,
        "name": client.name,
        "status": client.status,
        "roi": {"revenue": revenue, "cost": cost, "roi": _roi(revenue, cost)},
        "health": None,
        "risk_level": None,
        "phase": None,
        "next_meeting": None,
        "ai_score": None,
    }
    if not active:
        return overview

    scored = [(health.assess_project_health(project), project) for project in active]
    assessment, focus = min(scored, key=lambda pair: (pair[0]["score"], -pair[1].pk))
    overview["health"] = {"score": assessment["score"], "level": assessment["level"], "project_id": focus.pk}
    overview["risk_level"] = risk.assess_project(focus)["level"]
    phase = focus.current_phase
    if phase is not None:
        overview["phase"] = {"name": phase.phase.name, "status": phase.status}
    meeting = (
        Meeting.objects.filter(
            project__in=active, archived_at__isnull=True,
            status=Meeting.Status.SCHEDULED, date__gte=today,
        )
        .order_by("date", "id")
        .first()
    )
    if meeting is not None:
        overview["next_meeting"] = {"title": meeting.title, "date": meeting.date.isoformat()}
    # AI Score do cliente = o mais recente já revisado entre os projetos ativos (FDD 014).
    scored_projects = sorted(
        (project for project in active if project.ai_score_reviewed and project.ai_scored_at),
        key=lambda project: cast(datetime, project.ai_scored_at),
        reverse=True,
    )
    if scored_projects:
        overview["ai_score"] = portal.ai_score_snapshot(scored_projects[0])
    return overview


class ClientViewSet(ArchiveModelViewSet):
    resource = "client"
    queryset = Client.objects.all()
    serializer_class = ClientSerializer

    def perform_create(self, serializer: ClientSerializer) -> None:
        serializer.save(owner=self.request.user)

    def get_queryset(self):  # type: ignore[no-untyped-def]
        queryset = super().get_queryset()
        status_param = self.request.query_params.get("status")
        if status_param in {Client.Status.PROSPECT, Client.Status.ACTIVE}:
            queryset = queryset.filter(status=status_param)
        return queryset

    @extend_schema(responses=inline_serializer("ClientOverviewList", {"clients": serializers.ListField()}))
    @action(detail=False, methods=["get"])
    def overview(self, request: Request) -> Response:
        """Lista agregada p/ o grid de clientes (honra `?status=`)."""
        return Response({"clients": [build_client_overview(client) for client in self.get_queryset()]})

    @extend_schema(responses=inline_serializer("ClientOverviewDetail", {}))
    @action(detail=True, methods=["get"], url_path="overview")
    def overview_detail(self, request: Request, pk: str | None = None) -> Response:
        return Response(build_client_overview(self.get_object()))


class ContactViewSet(QueryParamFilterMixin, ArchiveModelViewSet):
    resource = "contact"
    queryset = Contact.objects.select_related("client").all()
    serializer_class = ContactSerializer
    filter_fields = ("client",)


class PipelineStageViewSet(viewsets.ModelViewSet):
    resource = "pipeline"
    queryset = PipelineStage.objects.all()
    serializer_class = PipelineStageSerializer
    permission_classes = [RolePermission]


class OpportunityViewSet(ArchiveModelViewSet):
    resource = "opportunity"
    queryset = Opportunity.objects.select_related(
        "client", "contact", "stage", "owner", "service"
    ).all()
    serializer_class = OpportunitySerializer

    def perform_create(self, serializer: OpportunitySerializer) -> None:
        serializer.save(owner=self.request.user)

    def get_queryset(self):  # type: ignore[no-untyped-def]
        queryset = super().get_queryset()
        if self.request.user.role == User.Role.DELIVERY and not self.request.user.is_admin_role:
            return queryset.filter(stage__kind=PipelineStage.Kind.WON)
        return queryset

    @action(detail=True, methods=["post"], url_path="convert-to-project")
    def convert_to_project(self, request: Request, pk: str | None = None) -> Response:
        opportunity = self.get_object()
        if request.user.role not in {User.Role.ADMIN, User.Role.SALES} and not request.user.is_superuser:
            return Response({"detail": "Somente Vendas pode converter oportunidades."}, status=403)
        if not opportunity.is_won:
            return Response({"detail": "A oportunidade deve estar na etapa Ganho."}, status=400)
        if hasattr(opportunity, "project"):
            return Response({"detail": "A oportunidade já foi convertida."}, status=409)
        serializer = ProjectSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        if serializer.validated_data["client"].id != opportunity.client_id:
            return Response({"client": "O projeto deve usar o cliente da oportunidade."}, status=400)
        # O nível de produto vendido segue para a entrega; o payload pode sobrescrever.
        service = serializer.validated_data.get("service") or opportunity.service
        try:
            with transaction.atomic():
                project = serializer.save(
                    opportunity=opportunity, owner=request.user, service=service
                )
                kickoff.seed_work_items(project)
        except IntegrityError:
            return Response({"detail": "A oportunidade já foi convertida."}, status=409)
        kickoff.finalize(project)
        return Response(ProjectSerializer(project).data, status=status.HTTP_201_CREATED)

    @action(detail=True, methods=["post"])
    def summary(self, request: Request, pk: str | None = None) -> Response:
        opportunity = self.get_object()
        system = "Resuma esta oportunidade comercial em português, com o contexto e uma recomendação objetiva de próximo passo. Use apenas o material fornecido."
        return _ai_run(request, "opportunity_summary", system, ai.build_opportunity_context(opportunity), opportunity=opportunity)

    @action(detail=True, methods=["post"])
    def proposal(self, request: Request, pk: str | None = None) -> Response:
        opportunity = self.get_object()
        system = (
            "Redija um RASCUNHO de proposta comercial em português a partir dos dados (contexto, "
            "escopo sugerido, entregáveis, investimento estimado). Quando houver um nível de "
            "produto informado, respeite o escopo e o preço de tabela desse nível — se for "
            "gratuito, deixe isso explícito e não sugira cobrança. Deixe claro que é um rascunho "
            "para revisão humana e use apenas o material fornecido."
        )
        return _ai_run(request, "proposal", system, ai.build_opportunity_context(opportunity), opportunity=opportunity)

    @action(detail=True, methods=["post"])
    def contract(self, request: Request, pk: str | None = None) -> Response:
        opportunity = self.get_object()
        system = (
            "Redija um RASCUNHO de contrato de prestação de serviços em português a partir do modelo "
            "padrão, com as cláusulas: partes, objeto, escopo, valor e forma de pagamento, prazo de "
            "vigência, obrigações das partes, confidencialidade, rescisão e foro. Preencha com os dados "
            "fornecidos e marque [lacunas] onde faltar informação. É um rascunho para revisão humana; "
            "use apenas o material fornecido."
        )
        return _ai_run(request, "contract", system, ai.build_opportunity_context(opportunity), opportunity=opportunity)


class ProjectViewSet(ArchiveModelViewSet):
    resource = "project"
    queryset = Project.objects.select_related("client", "opportunity", "owner").all()
    serializer_class = ProjectSerializer

    def perform_create(self, serializer: ProjectSerializer) -> None:
        serializer.save(owner=self.request.user)

    def get_queryset(self):  # type: ignore[no-untyped-def]
        queryset = super().get_queryset()
        if self.request.user.role == User.Role.SALES and not self.request.user.is_admin_role:
            return queryset
        return queryset

    @action(detail=True, methods=["post"])
    def assistant(self, request: Request, pk: str | None = None) -> Response:
        project = self.get_object()
        question = str(request.data.get("question", "")).strip()
        if not question:
            return Response({"detail": "Envie uma pergunta."}, status=400)
        system = "Você é o assistente deste projeto. Responda em português usando somente o contexto fornecido; se a informação não estiver ali, diga que não sabe."
        prompt = f"Contexto do projeto:\n{ai.build_project_context(project)}\n\nPergunta: {question}"
        return _ai_run(request, "project_chat", system, prompt, project=project)

    @action(detail=True, methods=["post"])
    def summary(self, request: Request, pk: str | None = None) -> Response:
        project = self.get_object()
        system = "Resuma este projeto em português de forma objetiva: status atual, riscos de prazo e próximos passos. Use apenas o material fornecido."
        return _ai_run(request, "project_summary", system, ai.build_project_context(project), project=project)

    @action(detail=True, methods=["get"])
    def risk(self, request: Request, pk: str | None = None) -> Response:
        return Response(risk.assess_project(self.get_object()))

    @action(detail=True, methods=["get"])
    def health(self, request: Request, pk: str | None = None) -> Response:
        return Response(health.assess_project_health(self.get_object()))

    @extend_schema(request=None, responses={200: ProjectPhaseSerializer(many=True)})
    @action(detail=True, methods=["post"], url_path="advance-phase")
    def advance_phase(self, request: Request, pk: str | None = None) -> Response:
        """Conclui a fase ativa da jornada e ativa a próxima (delivery/admin)."""
        project = self.get_object()
        journey.advance_phase(project)
        return Response(ProjectPhaseSerializer(_project_phases_qs(project), many=True).data)

    @action(detail=True, methods=["post"], url_path="next-steps")
    def next_steps(self, request: Request, pk: str | None = None) -> Response:
        project = self.get_object()
        assessment = risk.assess_project(project)
        signals = "; ".join(f"{s['label']} ({s['detail']})" for s in assessment["signals"]) or "sem sinais de risco"
        system = "Você é o agente de Entrega. Sugira, em português, os próximos passos priorizados para destravar o projeto. Use apenas o material fornecido e seja acionável."
        prompt = f"{ai.build_project_context(project)}\n\nSinais de risco: {signals}"
        return _ai_run(request, "project_next_steps", system, prompt, project=project)


def _project_phases_qs(project: Project):  # type: ignore[no-untyped-def]
    return (
        ProjectPhase.objects.filter(project=project, archived_at__isnull=True)
        .select_related("phase")
        .prefetch_related("deliverables")
        .order_by("phase__position", "id")
    )


class JourneyPhaseViewSet(viewsets.ModelViewSet):
    """Template configurável das fases da jornada (admin). Espelha PipelineStage."""

    resource = "journey"
    queryset = JourneyPhase.objects.prefetch_related("deliverables").all()
    serializer_class = JourneyPhaseSerializer
    permission_classes = [RolePermission]


class PhaseDeliverableViewSet(QueryParamFilterMixin, viewsets.ModelViewSet):
    """Template dos entregáveis de cada fase (admin)."""

    resource = "journey"
    queryset = PhaseDeliverable.objects.select_related("phase").all()
    serializer_class = PhaseDeliverableSerializer
    permission_classes = [RolePermission]
    filter_fields = ("phase",)


class ProjectPhaseViewSet(QueryParamFilterMixin, ArchiveModelViewSet):
    """Estado da jornada por projeto (leitura para todos; equipe edita `target_date`)."""

    resource = "project_phase"
    queryset = ProjectPhase.objects.select_related("phase", "project").prefetch_related(
        "deliverables"
    )
    serializer_class = ProjectPhaseSerializer
    filter_fields = ("project",)

    def get_queryset(self):  # type: ignore[no-untyped-def]
        queryset = super().get_queryset()
        # Materializa de forma preguiçosa a jornada de projetos antigos ao consultá-la.
        project_id = self.request.query_params.get("project")
        if project_id and project_id.isdigit():
            project = Project.objects.filter(pk=project_id, archived_at__isnull=True).first()
            if project and not queryset.filter(project=project).exists():
                journey.materialize_journey(project)
                queryset = super().get_queryset().filter(project=project)
        return queryset


class ProjectDeliverableViewSet(QueryParamFilterMixin, ArchiveModelViewSet):
    """Entregáveis por projeto — a equipe marca como entregue (delivery/admin)."""

    resource = "project_deliverable"
    queryset = ProjectDeliverable.objects.select_related(
        "project_phase", "project_phase__project"
    )
    serializer_class = ProjectDeliverableSerializer
    filter_fields = ("project_phase",)


class MilestoneViewSet(CalendarActionMixin, QueryParamFilterMixin, ArchiveModelViewSet):
    resource = "milestone"
    queryset = Milestone.objects.select_related("project", "owner").all()
    serializer_class = MilestoneSerializer
    filter_fields = ("project",)

    def perform_create(self, serializer: MilestoneSerializer) -> None:
        serializer.save(owner=self.request.user)


class TaskViewSet(CalendarActionMixin, QueryParamFilterMixin, ArchiveModelViewSet):
    resource = "task"
    queryset = Task.objects.select_related("project", "milestone", "owner").all()
    serializer_class = TaskSerializer
    filter_fields = ("project", "milestone")

    def perform_create(self, serializer: TaskSerializer) -> None:
        serializer.save(owner=self.request.user)

    @extend_schema(request=LinkExternalSerializer, responses={200: TaskSerializer})
    @action(detail=True, methods=["post"], url_path="link-external")
    def link_external(self, request: Request, pk: str | None = None) -> Response:
        """Vincula a tarefa a uma issue já existente no fornecedor (Linear/GitHub)."""
        task = self.get_object()
        serializer = LinkExternalSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        task.source = serializer.validated_data["source"]
        task.external_id = serializer.validated_data["external_id"]
        try:
            with transaction.atomic():
                task.save(update_fields=["source", "external_id", "updated_at"])
        except IntegrityError:
            return Response(
                {"detail": "Esta issue já está vinculada a outra tarefa."},
                status=status.HTTP_409_CONFLICT,
            )
        return Response(TaskSerializer(task).data)

    @extend_schema(request=LinkExternalSerializer, responses={201: TaskSerializer})
    @action(detail=True, methods=["post"], url_path="push-external")
    def push_external(self, request: Request, pk: str | None = None) -> Response:
        """Cria a issue no fornecedor e vincula a tarefa ao id retornado."""
        task = self.get_object()
        if not tasksync.is_enabled():
            return Response(
                {"detail": "Sincronia de tarefas desativada."},
                status=status.HTTP_503_SERVICE_UNAVAILABLE,
            )
        source = str(request.data.get("source", ""))
        if source not in tasksync.SOURCES:
            return Response({"detail": "Fornecedor inválido."}, status=status.HTTP_400_BAD_REQUEST)
        task.source = source
        external_id = tasksync.push_create(task)
        if not external_id:
            return Response(
                {"detail": "Não foi possível criar a issue no fornecedor."},
                status=status.HTTP_502_BAD_GATEWAY,
            )
        task.external_id = external_id
        try:
            with transaction.atomic():
                task.save(update_fields=["source", "external_id", "updated_at"])
        except IntegrityError:
            return Response(
                {"detail": "Esta issue já está vinculada a outra tarefa."},
                status=status.HTTP_409_CONFLICT,
            )
        return Response(TaskSerializer(task).data, status=status.HTTP_201_CREATED)


class DigitalEmployeeViewSet(QueryParamFilterMixin, ArchiveModelViewSet):
    resource = "digital_employee"
    queryset = DigitalEmployee.objects.select_related("project").all()
    serializer_class = DigitalEmployeeSerializer
    filter_fields = ("project",)


class DocumentViewSet(QueryParamFilterMixin, ArchiveModelViewSet):
    resource = "document"
    queryset = Document.objects.select_related(
        "client", "opportunity", "project", "uploaded_by"
    ).prefetch_related("signature_requests").all()
    serializer_class = DocumentSerializer
    filter_fields = ("client", "opportunity", "project")

    @action(detail=True, methods=["get"])
    def download(self, request: Request, pk: str | None = None) -> FileResponse:
        document = self.get_object()
        self.check_object_permissions(request, document)
        if document.drive_file_id:
            content = drive.download_document(document)
            return FileResponse(content, as_attachment=True, filename=document.original_name)
        return FileResponse(document.file.open("rb"), as_attachment=True, filename=document.original_name)

    @action(detail=True, methods=["post"], url_path="request-signature")
    def request_signature(self, request: Request, pk: str | None = None) -> Response:
        document = self.get_object()
        if not esign.is_enabled():
            return Response({"detail": "Assinatura eletrônica desativada."}, status=status.HTTP_503_SERVICE_UNAVAILABLE)
        signer_email = str(request.data.get("signer_email", "")).strip()
        if not signer_email:
            return Response({"detail": "Informe o e-mail do signatário."}, status=400)
        ref = esign.send_for_signature(document, signer_email)
        signature = SignatureRequest.objects.create(
            document=document, signer_email=signer_email,
            provider_ref=ref.provider_ref, document_ref=ref.document_ref, sign_url=ref.sign_url,
        )
        esign.invite_signer(document, signature)  # no-op quando o fornecedor é quem convida
        return Response({"id": signature.id, "status": signature.status}, status=status.HTTP_201_CREATED)

    @action(detail=True, methods=["post"], url_path="remind-signature")
    def remind_signature(self, request: Request, pk: str | None = None) -> Response:
        document = self.get_object()
        if not esign.is_enabled():
            return Response({"detail": "Assinatura eletrônica desativada."}, status=status.HTTP_503_SERVICE_UNAVAILABLE)
        return Response({"reminded": esign.remind_pending(document)})

    @action(detail=True, methods=["post"], url_path="mark-signed")
    def mark_signed(self, request: Request, pk: str | None = None) -> Response:
        document = self.get_object()
        signature = document.signature_requests.filter(pk=request.data.get("signature")).first()
        if signature is None:
            return Response({"detail": "Solicitação de assinatura não encontrada."}, status=404)
        signature.status = SignatureRequest.Status.SIGNED
        signature.signed_at = timezone.now()
        signature.save(update_fields=["status", "signed_at"])
        return Response(SignatureRequestSerializer(signature).data)


class MeetingViewSet(QueryParamFilterMixin, ArchiveModelViewSet):
    resource = "meeting"
    queryset = Meeting.objects.select_related("project").all()
    serializer_class = MeetingSerializer
    filter_fields = ("project",)

    @action(detail=True, methods=["post"])
    def discovery(self, request: Request, pk: str | None = None) -> Response:
        meeting = self.get_object()
        if not meeting.transcript.strip():
            return Response({"detail": "A reunião não tem transcrição."}, status=400)
        system = (
            "Você é o agente de Discovery da consultoria. A partir da transcrição, extraia em português "
            "um Discovery estruturado: situação atual, dores, objetivos, stakeholders, restrições e "
            "perguntas em aberto. Use APENAS o material fornecido; é um rascunho para revisão humana."
        )
        return _ai_run(request, "meeting_discovery", system, ai.build_meeting_context(meeting), project=meeting.project)

    @action(detail=True, methods=["post"])
    def assessment(self, request: Request, pk: str | None = None) -> Response:
        meeting = self.get_object()
        if not meeting.transcript.strip():
            return Response({"detail": "A reunião não tem transcrição."}, status=400)
        system = (
            "Você é o agente de Assessment da consultoria. A partir da transcrição, produza em português "
            "um diagnóstico objetivo e recomendações priorizadas. Use APENAS o material fornecido; é um "
            "rascunho para revisão humana e nunca afirme ter executado ações."
        )
        return _ai_run(request, "meeting_assessment", system, ai.build_meeting_context(meeting), project=meeting.project)

    @action(detail=True, methods=["post"], url_path="ai-score")
    def ai_score(self, request: Request, pk: str | None = None) -> Response:
        """Gera o AI Score de maturidade/oportunidade a partir da transcrição (FDD 014).

        Mesmas guardas de `_ai_run` (flag/limite/auditoria), mas persiste o resultado no projeto
        em vez de só devolver texto. Fica como rascunho (`ai_score_reviewed=False`) até revisão.
        """
        meeting = self.get_object()
        if not meeting.transcript.strip():
            return Response({"detail": "A reunião não tem transcrição."}, status=400)
        if not ai.is_enabled():
            return Response({"detail": "Recurso de IA está desativado."}, status=status.HTTP_503_SERVICE_UNAVAILABLE)
        if not ai.within_daily_limit(request.user):
            return Response({"detail": "Limite diário de uso de IA atingido."}, status=status.HTTP_429_TOO_MANY_REQUESTS)
        return Response(ai_score.score_meeting(meeting, user=request.user))


class PendenciaViewSet(QueryParamFilterMixin, ArchiveModelViewSet):
    resource = "pendencia"
    queryset = Pendencia.objects.select_related("project", "owner").all()
    serializer_class = PendenciaSerializer
    filter_fields = ("project",)

    def perform_create(self, serializer: PendenciaSerializer) -> None:
        serializer.save(owner=self.request.user)


class LeadViewSet(ArchiveModelViewSet):
    resource = "lead"
    queryset = Lead.objects.select_related("client", "opportunity").all()
    serializer_class = LeadSerializer

    @action(detail=True, methods=["post"])
    def convert(self, request: Request, pk: str | None = None) -> Response:
        lead = self.get_object()
        if lead.opportunity_id:
            return Response({"detail": "Lead já convertido."}, status=status.HTTP_409_CONFLICT)
        stage = PipelineStage.objects.filter(kind=PipelineStage.Kind.OPEN).order_by("position").first()
        if stage is None:
            return Response({"detail": "Nenhuma etapa aberta configurada."}, status=400)
        # Todo lead entra pela porta de entrada gratuita; Vendas troca o nível depois se for o caso.
        entry_service = Service.objects.filter(
            tier=Service.Tier.DISCOVERY_EXPRESS, active=True, archived_at__isnull=True
        ).first()
        with transaction.atomic():
            client = Client.objects.create(
                name=lead.company or lead.name,
                owner=request.user,
                status=Client.Status.PROSPECT,  # vira "ativo" quando a oportunidade é ganha
            )
            opportunity = Opportunity.objects.create(
                client=client,
                title=lead.name,
                scope=lead.message,
                estimated_value=0,
                stage=stage,
                owner=request.user,
                expected_close_date=timezone.localdate() + timedelta(days=30),
                service=entry_service,
            )
            lead.client = client
            lead.opportunity = opportunity
            lead.status = Lead.Status.QUALIFIED
            lead.save(update_fields=["client", "opportunity", "status", "updated_at"])
            lead.archive()  # sai da lista ativa de Leads, preservando o histórico
        return Response(LeadSerializer(lead).data, status=status.HTTP_201_CREATED)


# Token efêmero (assinado) que autoriza um lead qualificado a ver horários e agendar.
BOOKING_TOKEN_SALT = "booking"
BOOKING_TOKEN_MAX_AGE = 3600  # 1h


def _valid_intake_token(request: Request) -> bool:
    expected = settings.LEAD_INTAKE_TOKEN
    provided = request.headers.get("X-Intake-Token", "")
    return bool(expected) and hmac.compare_digest(provided, expected)


def _lead_from_booking_token(token: str) -> Lead | None:
    try:
        payload = signing.loads(token, salt=BOOKING_TOKEN_SALT, max_age=BOOKING_TOKEN_MAX_AGE)
    except signing.BadSignature:
        return None
    return Lead.objects.filter(id=payload.get("lead"), archived_at__isnull=True).first()


class LeadIntakeView(APIView):
    """Entrada pública de leads (formulário do site). Autentica por token compartilhado.

    Qualifica o lead pela IA (FDD 013); se passar do corte e o calendário estiver ligado, devolve
    um `booking_token` efêmero que autoriza o agendamento.
    """

    authentication_classes: list = []
    permission_classes = [AllowAny]
    throttle_classes = [ScopedRateThrottle]
    throttle_scope = "lead_intake"

    @extend_schema(request=LeadIntakeSerializer, responses=inline_serializer("LeadIntakeResponse", {
        "detail": serializers.CharField(),
        "qualified": serializers.BooleanField(),
        "booking_available": serializers.BooleanField(),
        "booking_token": serializers.CharField(allow_null=True),
    }))
    def post(self, request: Request) -> Response:
        if not _valid_intake_token(request):
            return Response({"detail": "Token inválido."}, status=status.HTTP_401_UNAUTHORIZED)
        serializer = LeadIntakeSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data
        if data.get("website"):  # honeypot preenchido → bot; descarta silenciosamente
            return Response({"detail": "Recebido."}, status=status.HTTP_201_CREATED)
        lead = Lead.objects.create(
            name=data["name"],
            email=data["email"],
            company=data.get("company", ""),
            phone=data.get("phone", ""),
            message=data.get("message", ""),
            source="site",
        )
        qualified = qualification.qualify_lead(lead, data.get("answers"))
        booking_available = calendar_sync.is_enabled()
        token = None
        if qualified and booking_available:
            token = signing.dumps({"lead": lead.id}, salt=BOOKING_TOKEN_SALT)
        return Response(
            {
                "detail": "Recebido.",
                "qualified": qualified,
                "booking_available": booking_available,
                "booking_token": token,
            },
            status=status.HTTP_201_CREATED,
        )


class BookingSlotsView(APIView):
    """Horários livres para um lead qualificado (autoriza por intake token + booking token)."""

    authentication_classes: list = []
    permission_classes = [AllowAny]
    throttle_classes = [ScopedRateThrottle]
    throttle_scope = "booking"

    @extend_schema(responses=inline_serializer("BookingSlotsResponse", {
        "slots": serializers.ListField(child=serializers.DateTimeField()),
    }))
    def get(self, request: Request) -> Response:
        if not _valid_intake_token(request):
            return Response({"detail": "Token inválido."}, status=status.HTTP_401_UNAUTHORIZED)
        if not calendar_sync.is_enabled():
            return Response({"detail": "Agendamento desativado."}, status=status.HTTP_503_SERVICE_UNAVAILABLE)
        if _lead_from_booking_token(request.query_params.get("token", "")) is None:
            return Response({"detail": "Sessão de agendamento inválida ou expirada."}, status=status.HTTP_403_FORBIDDEN)
        return Response({"slots": booking.available_slots()})


class BookingCreateView(APIView):
    """Reserva um horário para o lead qualificado."""

    authentication_classes: list = []
    permission_classes = [AllowAny]
    throttle_classes = [ScopedRateThrottle]
    throttle_scope = "booking"

    @extend_schema(request=BookingCreateSerializer, responses=inline_serializer("BookingCreateResponse", {
        "starts_at": serializers.DateTimeField(),
        "link": serializers.CharField(),
    }))
    def post(self, request: Request) -> Response:
        if not _valid_intake_token(request):
            return Response({"detail": "Token inválido."}, status=status.HTTP_401_UNAUTHORIZED)
        if not calendar_sync.is_enabled():
            return Response({"detail": "Agendamento desativado."}, status=status.HTTP_503_SERVICE_UNAVAILABLE)
        serializer = BookingCreateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        lead = _lead_from_booking_token(serializer.validated_data["token"])
        if lead is None:
            return Response({"detail": "Sessão de agendamento inválida ou expirada."}, status=status.HTTP_403_FORBIDDEN)
        try:
            created = booking.book(lead, serializer.validated_data["slot_start"])
        except booking.SlotUnavailable:
            return Response({"detail": "Horário indisponível."}, status=status.HTTP_409_CONFLICT)
        return Response(
            {"starts_at": created.starts_at, "link": created.calendar_link},
            status=status.HTTP_201_CREATED,
        )


class TaskSyncIntakeView(APIView):
    """Entrada da sincronia de tarefas (Linear/GitHub → Biahflow). Autentica por token."""

    authentication_classes: list = []
    permission_classes = [AllowAny]
    throttle_classes = [ScopedRateThrottle]
    throttle_scope = "task_sync"

    @extend_schema(request=TaskSyncSerializer, responses={200: None})
    def post(self, request: Request) -> Response:
        expected = settings.TASKSYNC_TOKEN
        provided = request.headers.get("X-Sync-Token", "")
        if not expected or not hmac.compare_digest(provided, expected):
            return Response({"detail": "Token inválido."}, status=status.HTTP_401_UNAUTHORIZED)
        serializer = TaskSyncSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data
        try:
            task = tasksync.apply_inbound(data["source"], data["external_id"], data["external_status"])
        except ValueError:
            return Response(
                {"detail": "Status externo não reconhecido."},
                status=status.HTTP_422_UNPROCESSABLE_ENTITY,
            )
        if task is None:
            return Response(
                {"detail": "Nenhuma tarefa vinculada a esta issue."},
                status=status.HTTP_404_NOT_FOUND,
            )
        return Response({"detail": "Sincronizado.", "task": task.pk})


class EsignWebhookView(APIView):
    """Entrada do fornecedor de assinatura (ADR 0007). Autentica pelo HMAC do corpo cru.

    Eventos desconhecidos ou sem solicitação correspondente respondem 200 "ignorado" — um
    erro faria o fornecedor reentregar para sempre.
    """

    authentication_classes: list = []
    permission_classes = [AllowAny]
    throttle_classes = [ScopedRateThrottle]
    throttle_scope = "esign_webhook"

    @extend_schema(request=None, responses={200: SignatureRequestSerializer})
    def post(self, request: Request) -> Response:
        if not esign.is_enabled():
            return Response(
                {"detail": "Assinatura eletrônica desativada."},
                status=status.HTTP_503_SERVICE_UNAVAILABLE,
            )
        body = request.body  # o HMAC é sobre os bytes originais, então nada de request.data
        provider = esign.get_provider()
        if not provider.verify(body, request.headers):
            return Response({"detail": "Assinatura inválida."}, status=status.HTTP_401_UNAUTHORIZED)
        try:
            payload = json.loads(body or b"{}")
        except ValueError:
            return Response({"detail": "Corpo inválido."}, status=status.HTTP_400_BAD_REQUEST)
        if not isinstance(payload, dict):
            return Response({"detail": "Corpo inválido."}, status=status.HTTP_400_BAD_REQUEST)
        event = provider.parse_event(payload)
        signature = esign.apply_event(event) if event else None
        if signature is None:
            return Response({"detail": "Evento ignorado."})
        return Response(SignatureRequestSerializer(signature).data)


class NotificationViewSet(viewsets.ReadOnlyModelViewSet):
    serializer_class = NotificationSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):  # type: ignore[no-untyped-def]
        return Notification.objects.filter(user=self.request.user)

    @action(detail=True, methods=["post"], url_path="read", url_name="read")
    def read(self, request: Request, pk: str | None = None) -> Response:
        notification = self.get_object()
        notification.read = True
        notification.save(update_fields=["read"])
        return Response(NotificationSerializer(notification).data)

    @action(detail=False, methods=["post"], url_path="read-all", url_name="read-all")
    def read_all(self, request: Request) -> Response:
        self.get_queryset().filter(read=False).update(read=True)
        return Response(status=status.HTTP_204_NO_CONTENT)


class ServiceViewSet(ArchiveModelViewSet):
    resource = "service"
    queryset = Service.objects.all()
    serializer_class = ServiceSerializer


def _roi(revenue: Decimal, cost: Decimal) -> float | None:
    return float((revenue - cost) / cost) if cost else None


class AnalyticsView(APIView):
    resource = "analytics"
    permission_classes = [RolePermission]

    @extend_schema(
        responses=inline_serializer(
            "AnalyticsResponse",
            {
                "funnel": serializers.DictField(),
                "win_rate": serializers.FloatField(allow_null=True),
                "avg_ticket": serializers.FloatField(),
                "avg_cycle_days": serializers.FloatField(allow_null=True),
                "pipeline": serializers.ListField(),
                "roi": serializers.DictField(),
            },
        )
    )
    def get(self, request: Request) -> Response:
        active = Q(archived_at__isnull=True)
        leads = Lead.objects.filter(active)
        leads_by_status = {row["status"]: row["n"] for row in leads.values("status").annotate(n=Count("id"))}

        opps = Opportunity.objects.filter(active)
        won = opps.filter(stage__kind=PipelineStage.Kind.WON).count()
        lost = opps.filter(stage__kind=PipelineStage.Kind.LOST).count()
        open_count = opps.filter(stage__kind=PipelineStage.Kind.OPEN).count()
        win_rate = won / (won + lost) if (won + lost) else None
        avg_ticket = opps.filter(stage__kind=PipelineStage.Kind.WON).aggregate(v=Avg("estimated_value"))["v"] or 0

        stages = list(
            PipelineStage.objects.annotate(
                opportunity_count=Count("opportunities", filter=Q(opportunities__archived_at__isnull=True)),
                estimated_total=Sum("opportunities__estimated_value", filter=Q(opportunities__archived_at__isnull=True)),
            ).values("id", "name", "kind", "position", "opportunity_count", "estimated_total")
        )

        projects = Project.objects.filter(active)
        projects_by_status = {row["status"]: row["n"] for row in projects.values("status").annotate(n=Count("id"))}

        cycle_days = [
            (project.created_at - project.opportunity.created_at).days
            for project in projects.exclude(opportunity__isnull=True).select_related("opportunity")
            if project.opportunity is not None
        ]
        avg_cycle = sum(cycle_days) / len(cycle_days) if cycle_days else None

        revenue = projects.aggregate(v=Sum("actual_value"))["v"] or Decimal("0")
        cost = projects.aggregate(v=Sum("cost"))["v"] or Decimal("0")
        by_client = [
            {"label": row["client__name"], "revenue": row["rev"] or 0, "cost": row["cost"] or 0,
             "roi": _roi(row["rev"] or Decimal("0"), row["cost"] or Decimal("0"))}
            for row in projects.values("client__name").annotate(rev=Sum("actual_value"), cost=Sum("cost")).order_by("-rev")
        ]
        by_service = [
            {"label": row["service__name"] or "Sem serviço", "revenue": row["rev"] or 0, "cost": row["cost"] or 0,
             "roi": _roi(row["rev"] or Decimal("0"), row["cost"] or Decimal("0"))}
            for row in projects.values("service__name").annotate(rev=Sum("actual_value"), cost=Sum("cost")).order_by("-rev")
        ]

        # Conversão por nível de produto: onde os três níveis param no pipeline.
        by_tier = []
        for tier, label in Service.Tier.choices:
            tier_opps = opps.filter(service__tier=tier)
            tier_won = tier_opps.filter(stage__kind=PipelineStage.Kind.WON).count()
            tier_lost = tier_opps.filter(stage__kind=PipelineStage.Kind.LOST).count()
            by_tier.append({
                "tier": tier,
                "label": label,
                "total": tier_opps.count(),
                "open": tier_opps.filter(stage__kind=PipelineStage.Kind.OPEN).count(),
                "won": tier_won,
                "lost": tier_lost,
                "estimated_total": tier_opps.aggregate(v=Sum("estimated_value"))["v"] or 0,
                "win_rate": tier_won / (tier_won + tier_lost) if (tier_won + tier_lost) else None,
            })

        return Response({
            "funnel": {
                "leads": {"total": leads.count(), "by_status": leads_by_status},
                "opportunities": {"open": open_count, "won": won, "lost": lost},
                "projects": {"total": projects.count(), "by_status": projects_by_status},
                "by_tier": by_tier,
            },
            "win_rate": win_rate,
            "avg_ticket": avg_ticket,
            "avg_cycle_days": avg_cycle,
            "pipeline": stages,
            "roi": {"revenue": revenue, "cost": cost, "roi": _roi(revenue, cost),
                    "by_client": by_client, "by_service": by_service},
        })


class RiskView(APIView):
    resource = "risk"
    permission_classes = [RolePermission]

    @extend_schema(responses=inline_serializer("RiskResponse", {"projects": serializers.ListField()}))
    def get(self, request: Request) -> Response:
        projects = Project.objects.filter(archived_at__isnull=True).exclude(status=Project.Status.COMPLETED)
        assessments = sorted((risk.assess_project(p) for p in projects), key=lambda a: a["score"], reverse=True)
        return Response({"projects": assessments})


class HealthView(APIView):
    resource = "health"
    permission_classes = [RolePermission]

    @extend_schema(responses=inline_serializer("HealthResponse", {"projects": serializers.ListField()}))
    def get(self, request: Request) -> Response:
        projects = Project.objects.filter(archived_at__isnull=True).exclude(status=Project.Status.COMPLETED)
        # pior primeiro: menor score de saúde no topo, para a equipe agir onde dói.
        assessments = sorted((health.assess_project_health(p) for p in projects), key=lambda a: a["score"])
        return Response({"projects": assessments})


class RecommendationsView(APIView):
    resource = "analytics"
    permission_classes = [RolePermission]

    @extend_schema(responses=inline_serializer("RecommendationsResponse", {"items": serializers.ListField()}))
    def get(self, request: Request) -> Response:
        return Response({"items": recommendations.build_recommendations()})


class AgentView(APIView):
    """Chat com um agente de IA especializado por área (revisão humana obrigatória)."""

    permission_classes = [IsAuthenticated]

    @extend_schema(
        request=inline_serializer("AgentRequest", {"question": serializers.CharField()}),
        responses=inline_serializer("AgentResponse", {
            "text": serializers.CharField(), "interaction": serializers.IntegerField(),
        }),
    )
    def post(self, request: Request, key: str) -> Response:
        agent = agents.AGENTS.get(key)
        if agent is None:
            return Response({"detail": "Agente inválido."}, status=status.HTTP_404_NOT_FOUND)
        if not agents.can_use(agent, request.user):
            return Response(
                {"detail": "Seu papel não tem acesso a este agente."},
                status=status.HTTP_403_FORBIDDEN,
            )
        question = str(request.data.get("question", "")).strip()
        if not question:
            return Response({"detail": "Informe uma pergunta."}, status=status.HTTP_400_BAD_REQUEST)
        prompt = f"{agent.build_context()}\n\nPergunta: {question}"
        return _ai_run(request, f"agent_{key}", agent.system, prompt)


class AiFeedbackView(APIView):
    """Avaliação 👍/👎 de uma resposta da IA (só o dono da interação avalia)."""

    permission_classes = [IsAuthenticated]

    @extend_schema(
        request=inline_serializer("AiFeedback", {
            "interaction": serializers.IntegerField(), "rating": serializers.IntegerField(),
        }),
        responses={200: None},
    )
    def post(self, request: Request) -> Response:
        rating = request.data.get("rating")
        if rating not in (1, -1):
            return Response({"detail": "Rating deve ser 1 ou -1."}, status=status.HTTP_400_BAD_REQUEST)
        interaction = get_object_or_404(
            AiInteraction, pk=request.data.get("interaction"), user=request.user
        )
        interaction.rating = rating
        interaction.save(update_fields=["rating"])
        return Response({"detail": "Registrado."})


class AiMetricsView(APIView):
    """Métricas de uso/qualidade da IA (admin) — base da avaliação contínua."""

    permission_classes = [IsAuthenticated]

    @extend_schema(responses=inline_serializer("AiMetrics", {
        "total": serializers.IntegerField(),
        "positive_rate": serializers.FloatField(allow_null=True),
        "by_feature": serializers.ListField(),
    }))
    def get(self, request: Request) -> Response:
        if not request.user.is_admin_role:
            return Response({"detail": "Somente administradores."}, status=status.HTTP_403_FORBIDDEN)
        interactions = AiInteraction.objects.all()
        rated = interactions.exclude(rating__isnull=True)
        rated_count = rated.count()
        positive_rate = rated.filter(rating=1).count() / rated_count if rated_count else None
        by_feature = list(
            interactions.values("feature").annotate(
                count=Count("id"),
                positive=Count("id", filter=Q(rating=1)),
                negative=Count("id", filter=Q(rating=-1)),
            ).order_by("-count")
        )
        return Response({
            "total": interactions.count(),
            "positive_rate": positive_rate,
            "by_feature": by_feature,
        })


class DashboardView(APIView):
    resource = "dashboard"
    permission_classes = [RolePermission]

    @extend_schema(
        responses=inline_serializer(
            "DashboardResponse",
            {
                "active_projects": serializers.IntegerField(),
                "overdue_count": serializers.IntegerField(),
                "pipeline": serializers.ListField(),
                "upcoming_tasks": serializers.ListField(),
            },
        )
    )
    def get(self, request: Request) -> Response:
        today = timezone.localdate()
        stages = PipelineStage.objects.annotate(
            opportunity_count=Count("opportunities"), estimated_total=Sum("opportunities__estimated_value")
        ).values("id", "name", "kind", "position", "opportunity_count", "estimated_total")
        projects = Project.objects.filter(archived_at__isnull=True).exclude(status=Project.Status.COMPLETED)
        overdue_milestones = Milestone.objects.filter(archived_at__isnull=True, due_date__lt=today).exclude(
            status=Milestone.Status.DONE
        )
        overdue_tasks = Task.objects.filter(archived_at__isnull=True, due_date__lt=today).exclude(
            status=Task.Status.DONE
        )
        upcoming = list(
            Task.objects.filter(archived_at__isnull=True, due_date__gte=today)
            .exclude(status=Task.Status.DONE)
            .order_by("due_date")[:5]
            .values("id", "title", "due_date", "project_id")
        )
        return Response({
            "pipeline": list(stages),
            "active_projects": projects.count(),
            "overdue_count": overdue_milestones.count() + overdue_tasks.count(),
            "upcoming_tasks": upcoming,
        })


class ConfigView(APIView):
    permission_classes = [IsAuthenticated]

    @extend_schema(responses=inline_serializer("ConfigResponse", {
        "ai_enabled": serializers.BooleanField(),
        "calendar_enabled": serializers.BooleanField(),
        "esign_enabled": serializers.BooleanField(),
        "integrations": serializers.ListField(child=serializers.DictField()),
    }))
    def get(self, request: Request) -> Response:
        return Response({
            "ai_enabled": ai.is_enabled(),
            "calendar_enabled": calendar_sync.is_enabled(),
            "esign_enabled": esign.is_enabled(),
            "integrations": flags.all_status(),
        })

    @extend_schema(
        request=inline_serializer("ConfigPatch", {
            "key": serializers.CharField(),
            "enabled": serializers.BooleanField(),
        }),
        responses=inline_serializer("ConfigFlag", {
            "key": serializers.CharField(),
            "label": serializers.CharField(),
            "enabled": serializers.BooleanField(),
            "configured": serializers.BooleanField(),
            "toggleable": serializers.BooleanField(),
        }),
    )
    def patch(self, request: Request) -> Response:
        if not request.user.is_admin_role:
            return Response({"detail": "Somente administradores."}, status=status.HTTP_403_FORBIDDEN)
        key = str(request.data.get("key", ""))
        flag = flags.FLAGS.get(key)
        if flag is None or not flag.toggleable:
            return Response({"detail": "Integração inválida."}, status=status.HTTP_400_BAD_REQUEST)
        enabled = bool(request.data.get("enabled"))
        if enabled and not flags.configured(key):
            return Response(
                {"detail": "Faltam credenciais no ambiente para ligar esta integração."},
                status=status.HTTP_400_BAD_REQUEST,
            )
        AppSetting.objects.update_or_create(
            key=key, defaults={"enabled": enabled, "updated_by": request.user}
        )
        return Response(flags.status(key))


class CalendarSyncView(APIView):
    """Dispara manualmente a sincronização de eventos do calendário em tarefas (admin)."""

    permission_classes = [IsAuthenticated]

    @extend_schema(
        request=None,
        responses=inline_serializer("CalendarSyncResponse", {
            "created": serializers.IntegerField(),
            "skipped": serializers.IntegerField(),
        }),
    )
    def post(self, request: Request) -> Response:
        if not request.user.is_admin_role:
            return Response({"detail": "Somente administradores."}, status=status.HTTP_403_FORBIDDEN)
        if not calendar_sync.is_enabled():
            return Response({"detail": "Calendário desativado."}, status=status.HTTP_503_SERVICE_UNAVAILABLE)
        created, skipped = calendar_sync.sync_calendar()
        return Response({"created": created, "skipped": skipped})


@extend_schema(responses=inline_serializer("CsrfResponse", {"csrfToken": serializers.CharField()}))
@api_view(["GET"])
@permission_classes([AllowAny])
def csrf(request: Request) -> Response:
    return Response({"csrfToken": get_token(request)})


class LoginView(APIView):
    permission_classes = [AllowAny]

    @extend_schema(request=LoginSerializer, responses=UserSerializer)

    def post(self, request: Request) -> Response:
        username = request.data.get("username", "")
        password = request.data.get("password", "")
        user = authenticate(request, username=username, password=password)
        if user is None or not user.is_active:
            return Response({"detail": "Credenciais inválidas."}, status=status.HTTP_400_BAD_REQUEST)
        login(request, user)
        return Response(UserSerializer(user).data)


class LogoutView(APIView):
    permission_classes = [IsAuthenticated]

    @extend_schema(request=None, responses={204: None})

    def post(self, request: Request) -> Response:
        logout(request)
        return Response(status=status.HTTP_204_NO_CONTENT)


class MeView(APIView):
    permission_classes = [IsAuthenticated]

    @extend_schema(responses=UserSerializer)

    def get(self, request: Request) -> Response:
        return Response(UserSerializer(request.user).data)


class UserViewSet(viewsets.ReadOnlyModelViewSet):
    resource = "user"
    queryset = User.objects.order_by("first_name", "username")
    serializer_class = UserSerializer
    permission_classes = [RolePermission]


class InvitationView(APIView):
    permission_classes = [RolePermission]
    resource = "invitation"

    @extend_schema(responses={200: InvitationSerializer(many=True)})
    def get(self, request: Request) -> Response:
        invitations = Invitation.objects.order_by("-created_at")
        return Response(InvitationSerializer(invitations, many=True).data)

    @extend_schema(request=InvitationSerializer, responses={201: InvitationSerializer})
    def post(self, request: Request) -> Response:
        if not request.user.is_admin_role:
            return Response({"detail": "Somente administradores convidam pessoas."}, status=403)
        serializer = InvitationSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        invitation = serializer.save(
            invited_by=request.user, expires_at=timezone.now() + timedelta(days=7)
        )
        accept_link = f"{settings.FRONTEND_BASE_URL}/aceitar-convite?token={invitation.token}"
        send_mail(
            "Convite para o Portal Biahflow",
            f"Você foi convidado para o Portal Biahflow.\n\n"
            f"Acesse este link para ativar seu acesso:\n{accept_link}\n\n"
            f"Ou use este token na tela de ativação: {invitation.token}",
            None,
            [invitation.email],
            fail_silently=False,
        )
        return Response(InvitationSerializer(invitation).data, status=status.HTTP_201_CREATED)


class AcceptInvitationView(APIView):
    permission_classes = [AllowAny]

    @extend_schema(request=AcceptInvitationSerializer, responses={201: UserSerializer})
    def post(self, request: Request) -> Response:
        serializer = AcceptInvitationSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        invitation = get_object_or_404(Invitation, token=serializer.validated_data["token"])
        if invitation.accepted_at or invitation.is_expired:
            return Response({"detail": "Convite inválido ou expirado."}, status=status.HTTP_400_BAD_REQUEST)
        user = User.objects.create_user(
            username=serializer.validated_data["username"],
            email=invitation.email,
            password=serializer.validated_data["password"],
            first_name=serializer.validated_data.get("first_name", ""),
            last_name=serializer.validated_data.get("last_name", ""),
            role=invitation.role,
        )
        invitation.accepted_at = timezone.now()
        invitation.save(update_fields=["accepted_at"])
        return Response(UserSerializer(user).data, status=status.HTTP_201_CREATED)


class PortalProjectSnapshotView(APIView):
    """Snapshot read-only de um projeto para o portal do cliente (ADR 0003).

    Autenticado por service token (Bearer) fora do fluxo de sessão/RBAC interno, para uso
    servidor-a-servidor no backfill/reconciliação. Só expõe dados do projeto — nada comercial.
    """

    authentication_classes: list = []
    permission_classes = [AllowAny]

    def get(self, request: Request, pk: int) -> Response:
        expected = settings.PORTAL_READ_TOKEN
        provided = request.headers.get("Authorization", "").removeprefix("Bearer ").strip()
        if not expected or not hmac.compare_digest(provided, expected):
            return Response({"detail": "Token inválido."}, status=status.HTTP_401_UNAUTHORIZED)
        project = get_object_or_404(Project.objects.filter(archived_at__isnull=True), pk=pk)
        return Response(portal.build_snapshot(project))
