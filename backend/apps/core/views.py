from __future__ import annotations

import hmac
import json
import logging
from collections import defaultdict
from collections.abc import Iterable
from dataclasses import dataclass
from datetime import datetime, timedelta
from decimal import Decimal, InvalidOperation
from typing import Any, cast

from django.conf import settings
from django.contrib.auth import authenticate, login, logout
from django.core import signing
from django.core.mail import send_mail
from django.db import IntegrityError, transaction
from django.db.models import Avg, Count, Q, Sum
from django.db.models.functions import Coalesce
from django.http import FileResponse
from django.middleware.csrf import get_token
from django.shortcuts import get_object_or_404
from django.utils import timezone
from drf_spectacular.utils import extend_schema, inline_serializer
from rest_framework import serializers, status, viewsets
from rest_framework.decorators import action, api_view, permission_classes
from rest_framework.exceptions import APIException, PermissionDenied
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.throttling import ScopedRateThrottle
from rest_framework.views import APIView

from . import (
    agents,
    ai,
    ai_score,
    blueprints,
    booking,
    calendar_sync,
    cases,
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
from .exceptions import (
    AiProviderUnavailable,
    CalendarProviderUnavailable,
    DriveUnavailable,
    EmailUndeliverable,
    EsignUnavailable,
)
from .models import (
    AiInteraction,
    AppSetting,
    Artifact,
    BlueprintVariant,
    Case,
    Client,
    Contact,
    DigitalEmployee,
    DigitalEmployeeBlueprint,
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
    ProjectMember,
    ProjectPhase,
    Service,
    SignatureRequest,
    Task,
    User,
    Vertical,
    project_scope_q,
)
from .permissions import RolePermission
from .serializers import (
    AcceptInvitationSerializer,
    ArtifactSerializer,
    BlueprintVariantSerializer,
    BookingCreateSerializer,
    CaseSerializer,
    ClientSerializer,
    ContactSerializer,
    DigitalEmployeeBlueprintSerializer,
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
    ProjectMemberSerializer,
    ProjectPhaseSerializer,
    ProjectSerializer,
    ServiceSerializer,
    SignatureRequestSerializer,
    TaskSerializer,
    TaskSyncSerializer,
    UserSerializer,
    VerticalSerializer,
)

logger = logging.getLogger(__name__)


class StateConflict(APIException):
    """Recusado porque outra coisa ainda depende deste registro.

    409, não 400: o pedido está bem formado e a permissão existe — o que impede é o **estado** do
    sistema, e é ele que muda para o pedido passar. Um 400 mandaria quem lê procurar erro no corpo.

    Nasceu como `ArchiveConflict`, do arquivamento, e o nome ficou estreito: a exclusão **real**
    (etapa do pipeline, fase da jornada) recusa pela mesma razão e com a mesma forma — contagem do
    que depende, mais o caminho de saída. Ver FDD 025.
    """

    status_code = status.HTTP_409_CONFLICT


class ArchiveModelViewSet(viewsets.ModelViewSet):
    permission_classes = [RolePermission]

    def get_queryset(self):  # type: ignore[no-untyped-def]
        # `?archived=1` abre a lista do que foi arquivado — é o que torna o arquivamento reversível
        # pela interface (FDD 025). Sem esse recorte, restaurar exigia Django admin ou shell.
        if self.request.query_params.get("archived") == "1":
            return self.queryset.filter(archived_at__isnull=False)
        return self.queryset.filter(archived_at__isnull=True)

    def perform_destroy(self, instance) -> None:  # type: ignore[no-untyped-def]
        instance.archive()

    @extend_schema(
        responses=inline_serializer("Unarchived", {"id": serializers.IntegerField()}),
        request=None,
    )
    @action(detail=True, methods=["post"])
    def unarchive(self, request: Request, pk: str | None = None) -> Response:
        """Restaura um registro arquivado, devolvendo-o à listagem ativa."""
        # `get_object()` passa pelo `get_queryset()`, que sem `?archived=1` esconde justamente o que
        # se quer restaurar — daí resolver o objeto pela queryset crua e só então aplicar a
        # permissão de objeto, que continua sendo a mesma do `destroy`.
        instance = get_object_or_404(self.queryset, pk=pk)
        self.check_object_permissions(request, instance)
        instance.archived_at = None
        instance.save(update_fields=["archived_at", "updated_at"])
        return Response({"id": instance.pk})


# Confina o recurso aos projetos de que a pessoa participa (RFC 0003, ADR 0010).
#
# `project_path` é o caminho até o projeto a partir do modelo consultado — `""` no próprio
# `Project`, `"project"` na maioria, `"project_phase__project"` no entregável.
#
# Cobre leitura e escrita no mesmo lugar de propósito. Só a leitura seria contornável em uma
# requisição: criar uma tarefa em projeto alheio bastava para virar dono dela e, pelo critério
# antigo, ganhar acesso ao projeto. E `perform_update` fecha o caminho inverso — **mover** um
# objeto próprio para um projeto de terceiros.
#
# Sem docstring de propósito: o drf-spectacular usa o docstring da classe como `description` de
# cada endpoint, e um mixin no topo da MRO vaza o próprio texto para dezenas de rotas alheias.
class ProjectScopedMixin:

    project_path = "project"
    scope_payload_field = "project"  # a chave do corpo que amarra o objeto a um projeto

    def get_queryset(self):  # type: ignore[no-untyped-def]
        queryset = super().get_queryset()  # type: ignore[misc]
        scope = project_scope_q(self.request.user, self.project_path)  # type: ignore[attr-defined]
        return queryset.filter(scope).distinct() if scope else queryset

    def scoped_project(self, validated_data: dict) -> Project | None:
        """De onde sai o projeto do payload. Sobrescrito por quem não o carrega direto."""
        return validated_data.get("project")

    def _assert_in_scope(self, project: Project | None) -> None:
        user = self.request.user  # type: ignore[attr-defined]
        if user.is_admin_role or user.role != User.Role.DELIVERY:
            return
        if project is None or not Project.objects.visible_to(user).filter(pk=project.pk).exists():
            raise PermissionDenied("Você não participa deste projeto.")

    def create_kwargs(self) -> dict:
        """Campos derivados da sessão gravados na criação (ex.: `owner`).

        Existe como hook para que os viewsets não precisem reimplementar `perform_create` —
        era assim que a guarda de escopo passava despercebida, porque o método do viewset
        vencia o do mixin na MRO.
        """
        return {}

    def perform_create(self, serializer) -> None:  # type: ignore[no-untyped-def]
        self._assert_in_scope(self.scoped_project(serializer.validated_data))
        serializer.save(**self.create_kwargs())

    def perform_update(self, serializer) -> None:  # type: ignore[no-untyped-def]
        # Só quando o corpo tenta *mudar* o vínculo; um PATCH de status não reavalia nada.
        if self.scope_payload_field in serializer.validated_data:
            self._assert_in_scope(self.scoped_project(serializer.validated_data))
        super().perform_update(serializer)  # type: ignore[misc]


# Filtra a lista por chaves estrangeiras informadas em query params (ex.: ?project=1).
# `filter_exact_fields` faz o mesmo para campos de texto com valores fechados (ex.: ?kind=proposal),
# que não passam pelo teste de dígito das chaves estrangeiras.
# Comentário, e não docstring, pelo mesmo motivo do `ProjectScopedMixin` acima.
class QueryParamFilterMixin:

    filter_fields: tuple[str, ...] = ()
    filter_exact_fields: tuple[str, ...] = ()

    def get_queryset(self):  # type: ignore[no-untyped-def]
        queryset = super().get_queryset()  # type: ignore[misc]
        for field in self.filter_fields:
            value = self.request.query_params.get(field)  # type: ignore[attr-defined]
            if value and value.isdigit():
                queryset = queryset.filter(**{field: value})
        for field in self.filter_exact_fields:
            value = self.request.query_params.get(field)  # type: ignore[attr-defined]
            if value:
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
        try:
            link = calendar_sync.create_event(item.title, item.due_date, origin=origin)
        except calendar_sync.CalendarProviderError as exc:
            logger.exception("evento de calendário recusado para %s", origin)
            raise CalendarProviderUnavailable() from exc
        return Response({"link": link})


# O destino de todo texto gerado é um `<textarea>` — do rascunho de resumo ao artefato de proposta.
# Textarea não renderiza marcação, então o markdown que o modelo produzia por hábito chegava cru a
# quem revisa: `**Recomendação de Próximo Passo:**` com os asteriscos à mostra, e depois seguia
# assim para dentro do documento salvo. Instruir uma vez aqui cobre as nove actions que usam este
# helper; renderizar markdown exigiria dependência nova e sanitização de texto vindo de LLM.
_TEXTO_CORRIDO = (
    "Responda em texto corrido, sem marcação Markdown: nada de asteriscos para negrito ou itálico, "
    "cerquilhas de título, crases ou hifens de lista. Para separar seções, use uma linha em branco "
    "e um título em maiúsculas seguido de dois-pontos."
)


def _ai_run(  # type: ignore[no-untyped-def]
    request, feature, system, user_prompt, project=None, opportunity=None,
    artifact_kind=None, artifact_title="", source_meeting=None,
):
    """Guarda (flag + limite), executa a IA e registra a auditoria.

    Com `artifact_kind`, o texto também vira um `Artifact` em rascunho (FDD 016) — antes ele só
    existia na resposta HTTP. A chave `artifact` é aditiva: `text` e `interaction` seguem iguais.
    """
    if not ai.is_enabled():
        return Response({"detail": "Recurso de IA está desativado."}, status=status.HTTP_503_SERVICE_UNAVAILABLE)
    if not ai.within_daily_limit(request.user):
        return Response({"detail": "Limite diário de uso de IA atingido."}, status=status.HTTP_429_TOO_MANY_REQUESTS)
    # Este helper serve **nove** actions, e a chamada mora atrás de `# pragma: no cover` — por isso
    # a falta de guarda passou batida: 429 de rate limit, timeout de 30 s, chave revogada ou modelo
    # sem acesso na conta viravam 500 do Django. Nada é gravado antes da resposta chegar, então a
    # falha não consome a cota diária de quem tentou nem deixa artefato pela metade.
    try:
        text, usage = ai.complete(f"{system}\n\n{_TEXTO_CORRIDO}", user_prompt)
    except ai.AiProviderError as exc:
        logger.exception("chamada de IA (%s) falhou", feature)
        raise AiProviderUnavailable() from exc
    interaction = AiInteraction.objects.create(
        user=request.user, feature=feature, project=project, opportunity=opportunity,
        prompt_tokens=usage.get("prompt_tokens", 0), completion_tokens=usage.get("completion_tokens", 0),
    )
    payload: dict[str, object] = {"text": text, "interaction": interaction.id}
    if artifact_kind is not None:
        artifact = Artifact.objects.create(
            kind=artifact_kind, title=artifact_title, content=text,
            opportunity=opportunity, project=project, source_meeting=source_meeting,
            ai_interaction=interaction, created_by=request.user,
        )
        payload["artifact"] = ArtifactSerializer(artifact).data
    return Response(payload)


@dataclass(frozen=True)
class OverviewContext:
    """Tudo o que `build_client_overview` precisa do banco, carregado em lote.

    Existe porque a visão multi-cliente é um laço sobre clientes e cada cliente é um laço
    sobre projetos: consultar lá dentro custava ~14 queries por cliente, e o endpoint ficava
    mais lento na exata medida em que a Biahflow crescesse. Com o contexto, `/clients/overview/`
    emite o mesmo número de queries para 3 ou 300 clientes (FDD 022).
    """

    health: dict[int, dict[str, Any]]
    risk: dict[int, dict[str, Any]]
    phases: dict[int, ProjectPhase]
    next_meetings: dict[int, Meeting]


def build_overview_context(projects: Iterable[Project]) -> OverviewContext:
    """Carrega saúde, risco, fase corrente e próxima reunião de todos os projetos de uma vez."""
    active = [
        project for project in projects if project.status != Project.Status.COMPLETED
    ]
    if not active:
        return OverviewContext(health={}, risk={}, phases={}, next_meetings={})
    ids = [project.pk for project in active]
    phases: dict[int, ProjectPhase] = {}
    # `ordering` do modelo é ["phase__position", "id"], então o primeiro de cada projeto que
    # aparecer é o mesmo que `Project.current_phase` escolheria.
    for phase in (
        ProjectPhase.objects.filter(
            project_id__in=ids, status=ProjectPhase.Status.ACTIVE, archived_at__isnull=True
        ).select_related("phase")
    ):
        phases.setdefault(phase.project_id, phase)
    next_meetings: dict[int, Meeting] = {}
    for meeting in Meeting.objects.filter(
        project_id__in=ids, archived_at__isnull=True,
        status=Meeting.Status.SCHEDULED, date__gte=timezone.localdate(),
    ).order_by("date", "id"):
        next_meetings.setdefault(meeting.project_id, meeting)
    return OverviewContext(
        health={item["project_id"]: item for item in health.assess_projects_health(active)},
        risk={item["project_id"]: item for item in risk.assess_projects(active)},
        phases=phases,
        next_meetings=next_meetings,
    )


def build_client_overview(
    client: Client,
    projects: Iterable[Project] | None = None,
    context: OverviewContext | None = None,
) -> dict[str, object]:
    """Agrega o estado de um cliente para a visão multi-cliente 🟢🟡🔴 e o painel do detalhe.

    Semáforo = pior saúde entre os projetos ativos (é onde agir). Fase/risco vêm desse mesmo
    projeto-foco; o ROI soma os projetos considerados (padrão de `AnalyticsView`).

    `projects` existe porque o agregado é **por cliente**: estreitar a lista de clientes não
    basta: quem participa de um projeto do cliente X veria ROI, saúde e AI Score dos outros
    projetos de X. Quem chama passa o recorte que enxerga (RFC 0003).

    `context` é o mesmo dado carregado em lote para vários clientes; quem agrega uma lista o
    monta uma vez com `build_overview_context` (FDD 022). Omitido, monta-se um só para este
    cliente — o caminho do detalhe.
    """
    if projects is None:
        projects = client.projects.filter(archived_at__isnull=True)
    projects = list(projects)
    if context is None:
        context = build_overview_context(projects)
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

    scored = [(context.health[project.pk], project) for project in active]
    assessment, focus = min(scored, key=lambda pair: (pair[0]["score"], -pair[1].pk))
    overview["health"] = {"score": assessment["score"], "level": assessment["level"], "project_id": focus.pk}
    overview["risk_level"] = context.risk[focus.pk]["level"]
    phase = context.phases.get(focus.pk)
    if phase is not None:
        overview["phase"] = {"name": phase.phase.name, "status": phase.status}
    upcoming = [
        context.next_meetings[project.pk] for project in active
        if project.pk in context.next_meetings
    ]
    meeting = min(upcoming, key=lambda item: (item.date, item.pk), default=None)
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
        # Entrega só conhece o cliente para quem trabalha (RFC 0003).
        scope = project_scope_q(self.request.user, "projects")
        return queryset.filter(scope).distinct() if scope else queryset

    def perform_destroy(self, instance: Client) -> None:
        """Arquiva o cliente e, junto, os contatos dele — recusando se ainda houver trabalho aberto.

        Soft delete não cascateia sozinho, e sem estas duas regras arquivar um cliente produzia
        órfão visível: `ProjectViewSet` e `OpportunityViewSet` filtram o próprio `archived_at` e
        nunca o do cliente, então projeto e oportunidade continuavam listados apontando para uma
        linha que sumiu da tela de Clientes. O contato não tem esse problema (ninguém o lista
        sozinho), então ele acompanha em vez de bloquear.
        """
        projetos = Project.objects.filter(client=instance, archived_at__isnull=True).count()
        oportunidades = Opportunity.objects.filter(client=instance, archived_at__isnull=True).count()
        if projetos or oportunidades:
            partes = []
            if projetos:
                partes.append(f"{projetos} projeto(s)")
            if oportunidades:
                partes.append(f"{oportunidades} oportunidade(s)")
            raise StateConflict(
                f"Este cliente ainda tem {' e '.join(partes)} em aberto. "
                "Arquive esses registros antes de arquivar o cliente."
            )
        with transaction.atomic():
            instance.contacts.filter(archived_at__isnull=True).update(
                archived_at=timezone.now(), updated_at=timezone.now()
            )
            instance.archive()

    def _visible_projects(self, client: Client):  # type: ignore[no-untyped-def]
        return Project.objects.visible_to(self.request.user).filter(
            client=client, archived_at__isnull=True
        )

    @extend_schema(responses=inline_serializer("ClientOverviewList", {"clients": serializers.ListField()}))
    @action(detail=False, methods=["get"])
    def overview(self, request: Request) -> Response:
        """Lista agregada p/ o grid de clientes (honra `?status=`)."""
        clients = list(self.get_queryset())
        # Um `_visible_projects` por cliente somava ~14 queries por linha do grid. Aqui os
        # projetos visíveis de todos os clientes vêm juntos e o contexto é montado uma vez —
        # o custo do endpoint deixa de crescer com o tamanho da carteira (FDD 022).
        by_client: dict[int, list[Project]] = defaultdict(list)
        for project in Project.objects.visible_to(request.user).filter(
            client__in=clients, archived_at__isnull=True
        ):
            by_client[project.client_id].append(project)
        context = build_overview_context(
            [project for projects in by_client.values() for project in projects]
        )
        return Response({"clients": [
            build_client_overview(client, projects=by_client[client.pk], context=context)
            for client in clients
        ]})

    @extend_schema(responses=inline_serializer("ClientOverviewDetail", {}))
    @action(detail=True, methods=["get"], url_path="overview")
    def overview_detail(self, request: Request, pk: str | None = None) -> Response:
        client = self.get_object()
        return Response(build_client_overview(client, projects=self._visible_projects(client)))


class ContactViewSet(QueryParamFilterMixin, ArchiveModelViewSet):
    resource = "contact"
    queryset = Contact.objects.select_related("client").all()
    serializer_class = ContactSerializer
    filter_fields = ("client",)

    def get_queryset(self):  # type: ignore[no-untyped-def]
        # Sem isto, as pessoas dos clientes que acabaram de sumir continuariam listadas.
        queryset = super().get_queryset()
        scope = project_scope_q(self.request.user, "client__projects")
        return queryset.filter(scope).distinct() if scope else queryset


class PipelineStageViewSet(viewsets.ModelViewSet):
    resource = "pipeline"
    queryset = PipelineStage.objects.all()
    serializer_class = PipelineStageSerializer
    permission_classes = [RolePermission]

    def perform_destroy(self, instance: PipelineStage) -> None:
        """Recusa excluir etapa que ainda tem oportunidade — com 409, e dizendo quantas.

        Um dos dois `DELETE` de verdade do portal (FDD 025). `Opportunity.stage` é `PROTECT`, e
        sem esta guarda o banco recusava por baixo: `ProtectedError` sem tradução vira **500**.
        """
        total = instance.opportunities.count()
        if total:
            # A contagem ignora `archived_at` de propósito: `PROTECT` também ignora. Contar só as
            # ativas produziria "0 oportunidade(s)" numa recusa, ou mandaria mover o que a tela
            # não mostra — recusa cuja instrução não é verdade é o defeito que a FDD 025 corrige.
            arquivadas = instance.opportunities.filter(archived_at__isnull=False).count()
            saida = "Mova essas oportunidades para outra etapa antes de excluí-la."
            if arquivadas:
                saida += (
                    f" {arquivadas} está(ão) arquivada(s) e não aparece(m) no quadro: "
                    "restaure, mova e arquive de novo."
                )
            raise StateConflict(f"Esta etapa ainda tem {total} oportunidade(s). {saida}")
        instance.delete()


class OpportunityViewSet(ArchiveModelViewSet):
    resource = "opportunity"
    # `project` é o reverso 1-1 lido por `OpportunitySerializer.get_project`: sem ele aqui, a
    # listagem do pipeline faz uma query por card (ADR 0014).
    queryset = Opportunity.objects.select_related(
        "client", "contact", "stage", "owner", "service", "project"
    ).all()
    serializer_class = OpportunitySerializer

    def perform_create(self, serializer: OpportunitySerializer) -> None:
        serializer.save(owner=self.request.user)

    def perform_destroy(self, instance: Opportunity) -> None:
        """Recusa arquivar oportunidade cujo projeto ainda está **ativo**.

        `Project.opportunity` é `OneToOneField` com `PROTECT`, e o projeto lê a oportunidade para
        montar o próprio histórico comercial. Arquivá-la sob um projeto vivo deixaria o projeto
        apontando para um registro que a interface esconde.

        A condição é o estado do projeto, e não a existência da relação: `hasattr` continua
        verdadeiro com o projeto arquivado, porque o reverso não some com o `archived_at`. Testando
        só a existência, a recusa não tinha saída — a própria mensagem manda arquivar o projeto, e
        isso não desbloqueava nada; a oportunidade também não reconverte (o `OneToOneField` segue
        ocupado) e, viva, ainda bloqueava o cliente. Ver FDD 025.
        """
        projeto = getattr(instance, "project", None)
        if projeto is not None and projeto.archived_at is None:
            raise StateConflict(
                f"Esta oportunidade já virou o projeto \"{projeto.name}\". "
                "Arquive o projeto se quiser encerrar este trabalho."
            )
        instance.archive()

    def get_queryset(self):  # type: ignore[no-untyped-def]
        queryset = super().get_queryset()
        # Ganha **e** convertida num projeto da equipe: a oportunidade é o outro lado do
        # projeto, e deixá-la aberta reabriria pelo comercial o que o recorte fechou.
        if self.request.user.role == User.Role.DELIVERY and not self.request.user.is_admin_role:
            return queryset.filter(
                project_scope_q(self.request.user, "project"),
                stage__kind=PipelineStage.Kind.WON,
            ).distinct()
        return queryset

    @action(detail=True, methods=["post"], url_path="convert-to-project")
    def convert_to_project(self, request: Request, pk: str | None = None) -> Response:
        opportunity = self.get_object()
        if request.user.role not in {User.Role.ADMIN, User.Role.SALES} and not request.user.is_superuser:
            return Response({"detail": "Somente Vendas pode converter oportunidades."}, status=403)
        if not opportunity.is_won:
            return Response({"detail": "A oportunidade deve estar na etapa Ganho."}, status=400)
        existente = getattr(opportunity, "project", None)
        if existente is not None:
            # A conversão roda uma vez só: `Project.opportunity` é `OneToOneField` sem condição de
            # arquivamento, então o slot continua ocupado mesmo com o projeto arquivado. Dizer só
            # "já foi convertida" nesse caso manda a pessoa procurar um projeto que a interface
            # esconde — daí nomear o estado e o caminho de volta.
            detalhe = (
                f"Esta oportunidade já virou o projeto \"{existente.name}\", que está arquivado. "
                "Restaure o projeto para retomar este trabalho."
                if existente.archived_at is not None
                else "A oportunidade já foi convertida."
            )
            return Response({"detail": detalhe}, status=409)
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
            "gratuito, deixe isso explícito e não sugira cobrança. Quando houver Funcionários "
            "Digitais do catálogo listados, cite-os pelo nome e pelo que fazem, com o KPI e o "
            "ganho estimado — é o que torna a proposta concreta. Deixe claro que é um rascunho "
            "para revisão humana e use apenas o material fornecido."
        )
        return _ai_run(
            request, "proposal", system, ai.build_opportunity_context(opportunity),
            opportunity=opportunity, artifact_kind=Artifact.Kind.PROPOSAL,
            artifact_title=f"Proposta — {opportunity.title}",
        )

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
        return _ai_run(
            request, "contract", system, ai.build_opportunity_context(opportunity),
            opportunity=opportunity, artifact_kind=Artifact.Kind.CONTRACT,
            artifact_title=f"Contrato — {opportunity.title}",
        )


class ProjectViewSet(ProjectScopedMixin, ArchiveModelViewSet):
    resource = "project"
    project_path = ""  # o recorte é sobre o próprio projeto
    queryset = Project.objects.select_related("client", "opportunity", "owner").all()
    serializer_class = ProjectSerializer

    def perform_create(self, serializer: ProjectSerializer) -> None:
        # Sem `_assert_in_scope`: criar projeto novo não é acessar dado de terceiro, e o signal
        # `_owner_is_always_a_member` já coloca quem criou na equipe. Entrega não chega aqui —
        # `RolePermission` só lhe dá leitura e edição de projeto.
        serializer.save(owner=self.request.user)

    @extend_schema(
        request=inline_serializer(
            "DigitalEmployeeFromBlueprint",
            {"blueprint": serializers.IntegerField(),
             "vertical": serializers.IntegerField(required=False),
             "kpi_baseline": serializers.DecimalField(
                 max_digits=12, decimal_places=2, required=False, allow_null=True)},
        ),
        responses=DigitalEmployeeSerializer,
    )
    @action(detail=True, methods=["post"], url_path="digital-employees/from-blueprint")
    def digital_employee_from_blueprint(self, request: Request, pk: str | None = None) -> Response:
        """Instancia um Funcionário Digital a partir do catálogo, copiando os valores (FDD 026).

        Ação explícita, sem signal: a jornada é materializada no `post_save` do projeto porque é
        igual para todo projeto; o roster não é — cada entrega escolhe seus blocos.

        Mora em `ProjectViewSet` e a permissão sai certa de graça: `RolePermission` libera à Entrega
        toda ação de detalhe de `project` que não seja `create`/`destroy`, o objeto ainda passa por
        `_participates`, e Vendas — que tem `project` só-leitura — é barrada. É a regra do recurso:
        Vendas lê o roster e não mexe.

        `kpi_baseline` é opcional e entra aqui porque este é o momento em que o "antes" ainda é
        medição (FDD 027): perguntado na conclusão do projeto, ele seria digitado de memória.
        """
        project = self.get_object()
        blueprint = get_object_or_404(
            DigitalEmployeeBlueprint, pk=request.data.get("blueprint") or 0
        )
        if not blueprint.active:
            return Response(
                {"detail": "Este blueprint está desativado e não pode ser instanciado."},
                status=status.HTTP_400_BAD_REQUEST,
            )
        vertical_id = request.data.get("vertical")
        vertical = (
            Vertical.objects.filter(pk=vertical_id).first()
            if vertical_id
            else project.client.vertical
        )
        # Vazio e ausente são a mesma coisa — "não medido" —, e valem `None`, não zero.
        baseline_raw = request.data.get("kpi_baseline")
        try:
            baseline = None if baseline_raw in (None, "") else Decimal(str(baseline_raw))
        except InvalidOperation:
            return Response(
                {"kpi_baseline": "Informe um número ou deixe em branco."},
                status=status.HTTP_400_BAD_REQUEST,
            )
        employee = blueprints.instantiate(project, blueprint, vertical, kpi_baseline=baseline)
        return Response(DigitalEmployeeSerializer(employee).data, status=status.HTTP_201_CREATED)

    @action(detail=True, methods=["post"])
    def assistant(self, request: Request, pk: str | None = None) -> Response:
        project = self.get_object()
        question = str(request.data.get("question", "")).strip()
        if not question:
            return Response({"detail": "Envie uma pergunta."}, status=400)
        # "Use somente o contexto" não pode virar "só repita o que está escrito". Observado na
        # rodada 2 (FDD 024): perguntado sobre o maior risco de um projeto com uma tarefa vencida
        # há três dias, o assistente respondia **"Não sei."** em três tokens — enquanto o `summary`,
        # com o mesmo contexto e outro texto de sistema, respondia bem. O antivazamento continua
        # inteiro (nada de conhecimento externo); o que muda é permitir **raciocinar sobre** o
        # material, que é o que distingue um assistente de uma consulta ao banco.
        system = (
            "Você é o assistente deste projeto. Responda em português. Use exclusivamente o "
            "contexto fornecido como fonte de fatos — nunca conhecimento externo nem suposição "
            "sobre o que não está ali —, mas você **pode e deve raciocinar** sobre esse material: "
            "comparar prazos com a data de hoje, apontar o que está atrasado, inferir riscos e "
            "priorizar. Só diga que não sabe quando o contexto realmente não permitir concluir."
        )
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

    def perform_destroy(self, instance: JourneyPhase) -> None:
        """Recusa excluir fase já materializada — e aponta a desativação como saída (FDD 011).

        Aqui a recusa é a regra, não a exceção: `materialize_journey` copia o template inteiro
        para **todo** projeto, então basta um projeto na base para nenhuma fase poder ser
        excluída. Antes desta guarda, o `PROTECT` de `ProjectPhase.phase` respondia **500** e o
        diálogo da tela ainda prometia que "projetos que já materializaram esta fase não são
        afetados" — a exclusão nunca chegava a acontecer.

        Excluir uma fase por que se passaram projetos reais seria apagar histórico. O que se quer
        ao aposentar uma fase é que ela pare de valer daqui para frente, e isso é `active=False`.
        """
        total = instance.project_phases.count()
        if total:
            raise StateConflict(
                f"Esta fase já foi materializada em {total} projeto(s) e não pode ser excluída "
                "sem apagar o histórico deles. Desative a fase: ela deixa de ser herdada por "
                "projetos novos e os atuais mantêm a delas."
            )
        instance.delete()


class PhaseDeliverableViewSet(QueryParamFilterMixin, viewsets.ModelViewSet):
    """Template dos entregáveis de cada fase (admin)."""

    resource = "journey"
    queryset = PhaseDeliverable.objects.select_related("phase").all()
    serializer_class = PhaseDeliverableSerializer
    permission_classes = [RolePermission]
    filter_fields = ("phase",)


class ProjectPhaseViewSet(ProjectScopedMixin, QueryParamFilterMixin, ArchiveModelViewSet):
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
        # O projeto vem de `visible_to`, não de `Project.objects`: senão um `?project=` de
        # projeto alheio dispararia uma **escrita** (a materialização) fora do escopo.
        project_id = self.request.query_params.get("project")
        if project_id and project_id.isdigit():
            project = (
                Project.objects.visible_to(self.request.user)
                .filter(pk=project_id, archived_at__isnull=True)
                .first()
            )
            if project and not queryset.filter(project=project).exists():
                journey.materialize_journey(project)
                queryset = super().get_queryset().filter(project=project)
        return queryset


class ProjectDeliverableViewSet(ProjectScopedMixin, QueryParamFilterMixin, ArchiveModelViewSet):
    """Entregáveis por projeto — a equipe marca como entregue (delivery/admin)."""

    resource = "project_deliverable"
    project_path = "project_phase__project"  # o entregável não carrega o projeto direto
    scope_payload_field = "project_phase"
    queryset = ProjectDeliverable.objects.select_related(
        "project_phase", "project_phase__project"
    )
    serializer_class = ProjectDeliverableSerializer
    filter_fields = ("project_phase",)

    def scoped_project(self, validated_data: dict) -> Project | None:
        phase = validated_data.get("project_phase")
        return phase.project if phase is not None else None


class ProjectMemberViewSet(ProjectScopedMixin, QueryParamFilterMixin, ArchiveModelViewSet):
    """Equipe do projeto — a fronteira de acesso da Entrega (RFC 0003, ADR 0010).

    Escrita só de admin (`RolePermission`): quem monta a equipe concede acesso a dado de
    projeto, e essa caneta fica com uma função só. Entrega e Vendas leem a equipe dos projetos
    que já enxergam, porque precisam saber quem toca a conta.
    """

    resource = "project_member"
    queryset = ProjectMember.objects.select_related("project", "user", "added_by").all()
    serializer_class = ProjectMemberSerializer
    filter_fields = ("project", "user")

    def create_kwargs(self) -> dict:
        return {"added_by": self.request.user}


class MilestoneViewSet(ProjectScopedMixin, CalendarActionMixin, QueryParamFilterMixin, ArchiveModelViewSet):
    resource = "milestone"
    queryset = Milestone.objects.select_related("project", "owner").all()
    serializer_class = MilestoneSerializer
    filter_fields = ("project",)

    def create_kwargs(self) -> dict:
        return {"owner": self.request.user}


class TaskViewSet(ProjectScopedMixin, CalendarActionMixin, QueryParamFilterMixin, ArchiveModelViewSet):
    resource = "task"
    queryset = Task.objects.select_related("project", "milestone", "owner").all()
    serializer_class = TaskSerializer
    filter_fields = ("project", "milestone")

    def create_kwargs(self) -> dict:
        return {"owner": self.request.user}

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


class DigitalEmployeeViewSet(ProjectScopedMixin, QueryParamFilterMixin, ArchiveModelViewSet):
    resource = "digital_employee"
    queryset = DigitalEmployee.objects.select_related("project").all()
    serializer_class = DigitalEmployeeSerializer
    filter_fields = ("project",)


class CaseViewSet(ProjectScopedMixin, QueryParamFilterMixin, ArchiveModelViewSet):
    """Cases de projetos concluídos, com os números congelados (FDD 027).

    Não há `create`: case nasce do congelamento (`cases.freeze_if_completed`, no signal de
    conclusão do projeto) e não da mão de ninguém — um case digitado seria a prova social sem a
    medição, que é o que a FDD recusa. O que a API oferece é revisar, consentir e publicar.

    O escopo de projeto vem do mixin e sai certo de graça: Entrega vê case dos projetos de que
    participa, Vendas e admin veem todos, porque `project_scope_q` só recorta para a Entrega.
    """

    resource = "case"
    queryset = Case.objects.select_related("project__client", "vertical").all()
    serializer_class = CaseSerializer
    filter_fields = ("project", "vertical")
    filter_exact_fields = ("status",)

    def create(self, request: Request, *args: Any, **kwargs: Any) -> Response:
        return Response(
            {"detail": "Case é gerado na conclusão do projeto, não criado à mão."},
            status=status.HTTP_405_METHOD_NOT_ALLOWED,
        )

    @extend_schema(responses=CaseSerializer, request=None)
    @action(detail=True, methods=["post"], url_path="record-consent")
    def record_consent(self, request: Request, pk: str | None = None) -> Response:
        """Registra o consentimento do cliente para usar este case (admin).

        Ação separada do `PATCH` porque consentimento não é um campo que se edita junto com o
        título: é ato, e sem autor e carimbo "o cliente autorizou" é alegação de ninguém. Só admin
        chega aqui — `RolePermission` dá a Vendas e à Entrega apenas leitura de `case`.
        """
        case = self.get_object()
        return Response(CaseSerializer(cases.record_consent(case, request.user)).data)


class ArtifactViewSet(ProjectScopedMixin, QueryParamFilterMixin, ArchiveModelViewSet):
    """Artefatos da jornada (Discovery, Assessment, Proposta, Contrato) — FDD 016."""

    resource = "artifact"
    queryset = Artifact.objects.select_related(
        "opportunity__client", "project__client", "document"
    ).all()
    serializer_class = ArtifactSerializer
    filter_fields = ("opportunity", "project")
    filter_exact_fields = ("kind", "status")

    def create_kwargs(self) -> dict:
        return {"created_by": self.request.user}

    def perform_create(self, serializer: ArtifactSerializer) -> None:  # type: ignore[override]
        # O mixin já exige que o projeto seja da equipe. Aqui fica a regra da FDD 016 que
        # sobrevive a ela: proposta e contrato carregam valor e condição comercial, então
        # Entrega não vincula artefato a oportunidade nenhuma.
        user = self.request.user
        if (
            user.role == User.Role.DELIVERY
            and not user.is_admin_role
            and serializer.validated_data.get("opportunity") is not None
        ):
            raise PermissionDenied("Entrega não vincula artefatos a oportunidades.")
        super().perform_create(serializer)


class DocumentViewSet(ProjectScopedMixin, QueryParamFilterMixin, ArchiveModelViewSet):
    """Documentos privados, vinculados a exatamente um cliente, oportunidade ou projeto.

    Entrega só enxerga os documentos dos projetos de que participa; proposta e contrato, que
    nascem ligados à oportunidade, ficam fora do alcance dela (FDD 016, FDD 017, RFC 0003).
    """

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
            # A FDD 024 blindou o upload e deixou esta crua: 500 mudo no caminho em que a pessoa
            # tenta pegar de volta o **próprio** arquivo.
            try:
                content = drive.download_document(document)
            except drive.DriveProviderError as exc:
                logger.exception("download do Drive falhou para %s", document.original_name)
                raise DriveUnavailable() from exc
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
        try:
            ref = esign.send_for_signature(document, signer_email)
        except esign.EsignProviderError as exc:
            logger.exception("solicitação de assinatura recusada para %s", document.original_name)
            raise EsignUnavailable() from exc
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


class MeetingViewSet(ProjectScopedMixin, QueryParamFilterMixin, ArchiveModelViewSet):
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
        return _ai_run(
            request, "meeting_discovery", system, ai.build_meeting_context(meeting),
            project=meeting.project, artifact_kind=Artifact.Kind.DISCOVERY,
            artifact_title=f"Discovery — {meeting.title}", source_meeting=meeting,
        )

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
        return _ai_run(
            request, "meeting_assessment", system, ai.build_meeting_context(meeting),
            project=meeting.project, artifact_kind=Artifact.Kind.ASSESSMENT,
            artifact_title=f"Assessment — {meeting.title}", source_meeting=meeting,
        )

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
        # Guarda própria porque esta action não passa pelo `_ai_run` — ela persiste no projeto em
        # vez de só devolver texto, então repete as guardas à mão e a correção de lá não a alcança.
        # Dá para envolver a chamada inteira porque o tipo é estreito: um erro de banco no `save()`
        # que vem depois continua sendo 500, e não vira "a IA está fora do ar".
        try:
            return Response(ai_score.score_meeting(meeting, user=request.user))
        except ai.AiProviderError as exc:
            logger.exception("AI Score da reunião %s falhou", meeting.pk)
            raise AiProviderUnavailable() from exc


class PendenciaViewSet(ProjectScopedMixin, QueryParamFilterMixin, ArchiveModelViewSet):
    resource = "pendencia"
    queryset = Pendencia.objects.select_related("project", "owner").all()
    serializer_class = PendenciaSerializer
    filter_fields = ("project",)

    def create_kwargs(self) -> dict:
        return {"owner": self.request.user}


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
        try:
            slots = booking.available_slots()
        except calendar_sync.CalendarUnavailable:
            # Sem enxergar a agenda não dá para dizer o que está livre. Oferecer a grade inteira
            # seria marcar por cima de reunião real — 503 é a resposta honesta.
            return Response(
                {"detail": "Não foi possível consultar a agenda."},
                status=status.HTTP_503_SERVICE_UNAVAILABLE,
            )
        return Response({"slots": slots})


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
        except calendar_sync.CalendarUnavailable:
            return Response(
                {"detail": "Não foi possível consultar a agenda."},
                status=status.HTTP_503_SERVICE_UNAVAILABLE,
            )
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


class VerticalViewSet(viewsets.ModelViewSet):
    """Setores dos clientes (config admin). Espelha `PipelineStage`: config, não dado de negócio."""

    resource = "vertical"
    queryset = Vertical.objects.all()
    serializer_class = VerticalSerializer
    permission_classes = [RolePermission]

    def perform_destroy(self, instance: Vertical) -> None:
        """Recusa excluir vertical em uso — e aponta a desativação como saída (FDD 026, FDD 025).

        `Client.vertical` é `SET_NULL`: sem esta guarda, apagar uma vertical **zeraria em silêncio**
        o setor de todos os clientes que a tinham, sem nada na tela dizendo que aconteceu. As
        variantes já estariam protegidas pelo `PROTECT` do banco, mas de lá vem um 409 genérico,
        sem contagem e sem caminho de saída.
        """
        clientes = instance.clients.count()
        variantes = instance.variants.count()
        if clientes or variantes:
            partes = []
            if clientes:
                partes.append(f"{clientes} cliente(s)")
            if variantes:
                partes.append(f"{variantes} variante(s) de blueprint")
            raise StateConflict(
                f"Esta vertical ainda é usada por {' e '.join(partes)} e não pode ser excluída. "
                "Desative a vertical: ela deixa de ser oferecida e o que já a usa continua intacto."
            )
        instance.delete()


class DigitalEmployeeBlueprintViewSet(QueryParamFilterMixin, viewsets.ModelViewSet):
    """O catálogo de Funcionários Digitais (leitura para todos, escrita só admin — FDD 026)."""

    resource = "blueprint"
    queryset = DigitalEmployeeBlueprint.objects.select_related("service").prefetch_related(
        "variants__vertical"
    )
    serializer_class = DigitalEmployeeBlueprintSerializer
    permission_classes = [RolePermission]
    filter_fields = ("service",)
    filter_exact_fields = ("area",)

    def get_queryset(self):  # type: ignore[no-untyped-def]
        queryset = super().get_queryset()
        # `?active=1` é o que a instanciação pede: bloco aposentado não entra em entrega nova.
        # A tela de configuração não passa o parâmetro, porque precisa ver o que desativou.
        if self.request.query_params.get("active") == "1":
            queryset = queryset.filter(active=True)
        return queryset

    def get_serializer_context(self) -> dict[str, Any]:
        """`?vertical=<id>` **resolve**, não filtra.

        Filtrar para fora esconderia o bloco genérico — o que serve a qualquer setor — de quem tem
        vertical, e deixaria sem catálogo nenhum quem não tem. Aqui o parâmetro só diz sobre qual
        setor calcular `resolved`; a lista continua sendo o catálogo inteiro (FDD 026).
        """
        context = super().get_serializer_context()
        vertical_id = self.request.query_params.get("vertical")
        if vertical_id and vertical_id.isdigit():
            context["vertical"] = Vertical.objects.filter(pk=vertical_id).first()
        return context

    def perform_destroy(self, instance: DigitalEmployeeBlueprint) -> None:
        """Recusa excluir blueprint já instanciado (FDD 026, FDD 025).

        `DigitalEmployee.blueprint` é `SET_NULL`, então o banco deixaria passar — e o que se
        perderia seria a procedência dos Funcionários Digitais entregues. Aposentar um bloco é
        `active=False`: ele para de valer daqui para frente e o que foi entregue segue igual.
        """
        total = instance.instances.count()
        if total:
            raise StateConflict(
                f"Este blueprint já foi instanciado em {total} Funcionário(s) Digital(is) e não "
                "pode ser excluído sem apagar a procedência deles. Desative o blueprint: ele "
                "deixa de ser oferecido e as instâncias atuais continuam intactas."
            )
        instance.delete()


class BlueprintVariantViewSet(QueryParamFilterMixin, viewsets.ModelViewSet):
    """Parametrização por vertical de cada bloco do catálogo (admin)."""

    resource = "blueprint"
    queryset = BlueprintVariant.objects.select_related("blueprint", "vertical").all()
    serializer_class = BlueprintVariantSerializer
    permission_classes = [RolePermission]
    filter_fields = ("blueprint", "vertical")


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

        # Conversão por etapa da jornada: onde ela trava entre Discovery e Contrato (FDD 016).
        # `reached` conta clientes distintos, não artefatos — é a queda entre etapas que interessa.
        artifacts = Artifact.objects.filter(active)
        by_stage = []
        for kind, label in Artifact.Kind.choices:
            rows = artifacts.filter(kind=kind)
            accepted = rows.filter(status=Artifact.Status.ACCEPTED).count()
            rejected = rows.filter(status=Artifact.Status.REJECTED).count()
            reached = (
                rows.annotate(client=Coalesce("opportunity__client_id", "project__client_id"))
                .values("client").distinct().count()
            )
            by_stage.append({
                "kind": kind,
                "label": label,
                "total": rows.count(),
                "sent": rows.filter(status=Artifact.Status.SENT).count(),
                "accepted": accepted,
                "rejected": rejected,
                "acceptance_rate": accepted / (accepted + rejected) if (accepted + rejected) else None,
                "reached": reached,
            })

        return Response({
            "funnel": {
                "leads": {"total": leads.count(), "by_status": leads_by_status},
                "opportunities": {"open": open_count, "won": won, "lost": lost},
                "projects": {"total": projects.count(), "by_status": projects_by_status},
                "by_tier": by_tier,
                "by_stage": by_stage,
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
        projects = Project.objects.visible_to(request.user).filter(
            archived_at__isnull=True
        ).exclude(status=Project.Status.COMPLETED)
        assessments = sorted(risk.assess_projects(projects), key=lambda a: a["score"], reverse=True)
        return Response({"projects": assessments})


class HealthView(APIView):
    resource = "health"
    permission_classes = [RolePermission]

    @extend_schema(responses=inline_serializer("HealthResponse", {"projects": serializers.ListField()}))
    def get(self, request: Request) -> Response:
        projects = Project.objects.visible_to(request.user).filter(
            archived_at__isnull=True
        ).exclude(status=Project.Status.COMPLETED)
        # pior primeiro: menor score de saúde no topo, para a equipe agir onde dói.
        assessments = sorted(health.assess_projects_health(projects), key=lambda a: a["score"])
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
        prompt = f"{agent.build_context(request.user)}\n\nPergunta: {question}"
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
        is_delivery = (
            request.user.role == User.Role.DELIVERY and not request.user.is_admin_role
        )
        # O funil traz valor estimado de **todas** as oportunidades, inclusive as não-ganhas,
        # que o `OpportunityViewSet` já esconde de Entrega. O painel não pode ser o canal
        # lateral disso. O campo permanece (a forma do contrato não muda), vazio.
        stages = [] if is_delivery else list(PipelineStage.objects.annotate(
            opportunity_count=Count("opportunities"), estimated_total=Sum("opportunities__estimated_value")
        ).values("id", "name", "kind", "position", "opportunity_count", "estimated_total"))
        visible = Project.objects.visible_to(request.user).filter(archived_at__isnull=True)
        projects = visible.exclude(status=Project.Status.COMPLETED)
        overdue_milestones = Milestone.objects.filter(
            project__in=visible, archived_at__isnull=True, due_date__lt=today
        ).exclude(status=Milestone.Status.DONE)
        overdue_tasks = Task.objects.filter(
            project__in=visible, archived_at__isnull=True, due_date__lt=today
        ).exclude(status=Task.Status.DONE)
        upcoming = list(
            Task.objects.filter(
                project__in=visible, archived_at__isnull=True, due_date__gte=today
            )
            .exclude(status=Task.Status.DONE)
            .order_by("due_date")[:5]
            .values("id", "title", "due_date", "project_id")
        )
        return Response({
            "pipeline": stages,
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
            "missing": serializers.ListField(child=serializers.CharField()),
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
        try:
            created, skipped = calendar_sync.sync_calendar()
        except calendar_sync.CalendarProviderError as exc:
            logger.exception("sincronia de calendário recusada")
            raise CalendarProviderUnavailable() from exc
        return Response({"created": created, "skipped": skipped})


@extend_schema(responses=inline_serializer("CsrfResponse", {"csrfToken": serializers.CharField()}))
@api_view(["GET"])
@permission_classes([AllowAny])
def csrf(request: Request) -> Response:
    return Response({"csrfToken": get_token(request)})


class LoginView(APIView):
    permission_classes = [AllowAny]
    throttle_classes = [ScopedRateThrottle]
    throttle_scope = "login"  # sem teto, adivinhar senha era só questão de tempo

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
        # Gravação e envio na mesma transação: o convite só vale se o e-mail sair, porque o convite
        # **é** o e-mail — quem recebe não tem outro caminho para o token. Sem isto, um SMTP fora do
        # ar gravava a linha e devolvia 500 (`fail_silently=False`), então sobrava um convite válido
        # que ninguém recebeu, o admin achava que falhou e cada tentativa criava mais um. Observado
        # na homologação da FDD 024, com o SMTP apontado para uma porta morta.
        with transaction.atomic():
            invitation = serializer.save(
                invited_by=request.user, expires_at=timezone.now() + timedelta(days=7)
            )
            accept_link = f"{settings.FRONTEND_BASE_URL}/aceitar-convite?token={invitation.token}"
            try:
                send_mail(
                    "Convite para o Portal Biahflow",
                    f"Você foi convidado para o Portal Biahflow.\n\n"
                    f"Acesse este link para ativar seu acesso:\n{accept_link}\n\n"
                    f"Ou use este token na tela de ativação: {invitation.token}",
                    None,
                    [invitation.email],
                    fail_silently=False,
                )
            except Exception as exc:  # noqa: BLE001 - qualquer falha de SMTP desfaz o convite
                logger.exception("convite para %s não pôde ser enviado", invitation.email)
                raise EmailUndeliverable() from exc
        return Response(InvitationSerializer(invitation).data, status=status.HTTP_201_CREATED)


class AcceptInvitationView(APIView):
    permission_classes = [AllowAny]
    throttle_classes = [ScopedRateThrottle]
    throttle_scope = "invitation_accept"  # cria usuário sem autenticação

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

    **Projeto arquivado também responde 200.** O filtro `archived_at__isnull=True` que existia
    aqui vinha do `get_queryset` do `ArchiveModelViewSet`, onde ele está certo — quem lista não
    quer ver o arquivado. Nesta rota ele produzia o efeito oposto do pretendido: arquivar um
    projeto emite webhook (o `archive()` é um `save()`), o portal vinha buscar o estado novo e
    levava 404, que ele não tem como distinguir de "este id nunca existiu". O portal então
    mantinha o projeto encerrado na tela do cliente como se estivesse ativo, e só voltava a
    concordar quando alguém desarquivasse. Aqui o 404 volta a significar só "não existe", e
    quem diz que o projeto acabou é o `archived_at` do próprio snapshot.
    """

    authentication_classes: list = []
    permission_classes = [AllowAny]
    throttle_classes = [ScopedRateThrottle]
    throttle_scope = "portal_read"  # sem teto, o Bearer vira oráculo de força bruta

    def get(self, request: Request, pk: int) -> Response:
        expected = settings.PORTAL_READ_TOKEN
        provided = request.headers.get("Authorization", "").removeprefix("Bearer ").strip()
        if not expected or not hmac.compare_digest(provided, expected):
            return Response({"detail": "Token inválido."}, status=status.HTTP_401_UNAUTHORIZED)
        project = get_object_or_404(Project, pk=pk)
        return Response(portal.build_snapshot(project))
