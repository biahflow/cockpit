from __future__ import annotations

import hashlib
import hmac
import json
import logging
import os
from collections import defaultdict
from collections.abc import Iterable
from dataclasses import dataclass
from datetime import datetime, timedelta
from decimal import Decimal, InvalidOperation
from typing import Any, cast

from django.conf import settings
from django.contrib.auth import authenticate, login, logout, update_session_auth_hash
from django.core import signing
from django.core.exceptions import ValidationError as DjangoValidationError
from django.core.files.storage import Storage
from django.core.mail import send_mail
from django.db import IntegrityError, transaction
from django.db.models import Avg, Count, Max, OuterRef, Q, Subquery, Sum, Value
from django.db.models.functions import Coalesce
from django.http import FileResponse, Http404, HttpResponseNotModified
from django.http.response import HttpResponseBase
from django.middleware.csrf import get_token
from django.shortcuts import get_object_or_404
from django.utils import timezone
from django.utils.http import http_date
from drf_spectacular.types import OpenApiTypes
from drf_spectacular.utils import extend_schema, inline_serializer
from rest_framework import serializers, status, viewsets
from rest_framework.decorators import action, api_view, permission_classes
from rest_framework.exceptions import PermissionDenied
from rest_framework.parsers import FormParser, MultiPartParser
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
    cobranca,
    drive,
    engineering_provisioning,
    enrichment,
    esign,
    flags,
    github_delivery,
    health,
    invoices,
    journey,
    kickoff,
    knowledge,
    payments,
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
    PaymentsUnavailable,
    StateConflict,
)
from .models import (
    Activity,
    AiInteraction,
    AppSetting,
    Artifact,
    BlueprintVariant,
    Case,
    Client,
    CobrancaContato,
    CobrancaSuspensao,
    Contact,
    Decisao,
    DigitalEmployee,
    DigitalEmployeeBlueprint,
    Document,
    EngineeringHandoff,
    Evidencia,
    GithubDeliveryProjection,
    Invitation,
    Invoice,
    JourneyPhase,
    KnowledgeArea,
    KnowledgePiece,
    Lead,
    Meeting,
    Milestone,
    Notification,
    Opportunity,
    Pendencia,
    PhaseChecklistItem,
    PhaseDeliverable,
    PhaseEvent,
    PipelineStage,
    Processo,
    ProcessoEtapa,
    Project,
    ProjectChecklistItem,
    ProjectDeliverable,
    ProjectMember,
    ProjectPhase,
    Qualification,
    Risco,
    Satisfacao,
    Service,
    SignatureRequest,
    Task,
    User,
    Vertical,
    project_scope_q,
)
from .permissions import RolePermission
from .serializers import (
    AVATAR_CONTENT_TYPES,
    AcceptInvitationSerializer,
    ActivitySerializer,
    ArtifactSerializer,
    BlueprintVariantSerializer,
    BookingCreateSerializer,
    CaseSerializer,
    ChangePasswordSerializer,
    ClientSerializer,
    CobrancaContatoSerializer,
    CobrancaSuspensaoSerializer,
    ContactSerializer,
    DecisaoSerializer,
    DigitalEmployeeBlueprintSerializer,
    DigitalEmployeeSerializer,
    DocumentSerializer,
    EngineeringHandoffSerializer,
    EvidenciaSerializer,
    GithubDeliveryProjectionSerializer,
    InvitationSerializer,
    InvoiceSerializer,
    JourneyPhaseSerializer,
    KnowledgeAreaSerializer,
    KnowledgePieceSerializer,
    LeadConvertSerializer,
    LeadIntakeSerializer,
    LeadSerializer,
    LinkExternalSerializer,
    LoginSerializer,
    MeetingSerializer,
    MilestoneSerializer,
    NotificationSerializer,
    OpenCommercialOpportunitySerializer,
    OpportunitySerializer,
    PendenciaSerializer,
    PhaseChecklistItemSerializer,
    PhaseDeliverableSerializer,
    PhaseEventSerializer,
    PipelineStageSerializer,
    ProcessoEtapaSerializer,
    ProcessoSerializer,
    ProfileAvatarSerializer,
    ProfileSerializer,
    ProjectChecklistItemSerializer,
    ProjectDeliverableSerializer,
    ProjectMemberSerializer,
    ProjectPhaseSerializer,
    ProjectSerializer,
    QualificationSerializer,
    RiscoSerializer,
    SatisfacaoSerializer,
    ServiceSerializer,
    SignatureRequestSerializer,
    TaskSerializer,
    TaskSyncSerializer,
    UserSerializer,
    VerticalSerializer,
)

logger = logging.getLogger(__name__)


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


class _ExtracaoSemResultado(Exception):
    """O modelo respondeu, e o que veio não é uma lista de decisões.

    Exceção e não `return`: o coletor roda **dentro** do `_ai_run`, que já montou o payload e vai
    devolver `Response`. Sinalizar por retorno obrigaria aquele helper a saber o que fazer com um
    coletor que desistiu — e ele serve dez actions que não têm essa preocupação.
    """


#: Os dois formatos de saída que o `_ai_run` sabe pedir. Constantes e não literais soltos porque o
#: valor errado aqui não quebra nada — só volta a mandar o modelo evitar crase numa resposta que
#: precisa ser JSON, e o sintoma disso é um parse que falha longe da causa.
_FORMATO_TEXTO = "texto_corrido"
_FORMATO_JSON = "json"


def decisoes_do_texto(text: str) -> list[dict]:
    """Extrai a lista de decisões do que o modelo devolveu. Função pura, e é por isso que existe.

    **O modelo não obedece à instrução de formato o tempo todo**, e a falha típica não é JSON
    inválido: é JSON válido embrulhado em prosa ("Aqui estão as decisões:") ou em cerca de markdown.
    Recortar do primeiro ``[`` ao último ``]`` cobre os três casos com uma regra só.

    **Item malformado é descartado, não derruba a extração.** Um título vazio no quinto de sete não
    é razão para perder os outros seis — quem revisa vê seis rascunhos e a transcrição continua ali
    para uma segunda passada. O que **derruba** é não haver lista nenhuma: aí não houve extração, e
    dizer isso é diferente de gravar zero decisões em silêncio (a chamada devolve ``[]`` e quem a
    invoca responde 502).

    Fora da região ``# pragma: no cover`` de propósito: é a única parte disto que dá para exercitar
    sem chamar o provedor, e é onde os defeitos moram.
    """
    inicio, fim = text.find("["), text.rfind("]")
    if inicio == -1 or fim <= inicio:
        return []
    try:
        bruto = json.loads(text[inicio : fim + 1])
    except json.JSONDecodeError:
        return []
    if not isinstance(bruto, list):
        return []

    decisoes: list[dict] = []
    for item in bruto:
        if not isinstance(item, dict):
            continue
        titulo = str(item.get("title") or "").strip()
        if not titulo:
            continue
        decisoes.append({
            "title": titulo[:255],
            "rationale": str(item.get("rationale") or "").strip(),
            "decided_by": str(item.get("decided_by") or "").strip()[:160],
        })
    return decisoes


#: Os seis campos da etapa, na ordem das seis letras do P-S-D-T-E-R
#: (`docs/metodologia-fde.md:75-79`). Tupla e não literal repetido no parser e no prompt: a ordem
#: **é** a pergunta feita na reunião, e uma sétima chave inventada aqui deixaria de casar com o
#: formulário da tela.
_ETAPA_PSDTER: tuple[str, ...] = ("pessoas", "sistema", "dados", "tempo", "erro", "retrabalho")

#: O que se pede ao modelo na extração estruturada (FDD 039).
#:
#: **Constante de módulo, e não literal dentro da action**, por uma razão que não é de estilo:
#: `tests/regression/test_a_extracao_nasce_hipotese.py` lê este texto para provar que ele **não**
#: pede rótulo nem forma de evidência ao modelo. Dentro da action, a leitura arrastaria junto o
#: docstring e o coletor — que falam dos dois de propósito — e a guarda não teria como distinguir
#: "o prompt pede" de "o código impõe", que é exatamente a distinção que ela existe para manter.
#:
#: Um modelo lendo transcrição produz **o que foi dito**, que é uma das cinco formas de evidência
#: (`docs/metodologia-fde.md:81-84`) e não prova. Por isso as duas chaves são atribuídas como
#: constantes em quem grava, e não pedidas aqui: pedir e sobrescrever depois transformaria a
#: imposição em sugestão, e quem lesse este texto acharia que o modelo decide.
_PROMPT_PROCESSOS = (
    "Você mapeia os processos da operação do cliente a partir da transcrição de uma reunião. "
    "Devolva APENAS um array JSON, sem texto antes ou depois, em que cada item é um processo com "
    'as chaves "name" (o nome do processo em poucas palavras), "etapas" (a lista das etapas na '
    'ordem em que acontecem) e "achados" (a lista do que foi levantado sobre o processo, cada '
    'achado como uma string, uma frase por achado). Cada etapa tem "name" e as seis perguntas '
    'do levantamento: "pessoas" (quem faz), "sistema" (onde faz), "dados" (o que entra e sai), '
    '"tempo" (quanto demora), "erro" (o que pode dar errado) e "retrabalho" (o que acontece '
    "quando dá errado). Deixe em branco a pergunta que a transcrição não responde. Prenda cada "
    "achado ao processo, nunca a uma etapa. Use APENAS o material fornecido: se a transcrição não "
    "descreve processo nenhum, devolva um array vazio em vez de inferir. É um rascunho para "
    "revisão humana."
)


def _etapas_do_bruto(bruto: object) -> list[dict]:
    """As etapas de um processo extraído, já normalizadas nos seis campos do P-S-D-T-E-R.

    **Etapa sem nome sai fora sem derrubar o processo**, pelo argumento de `decisoes_do_texto`:
    perder a quarta de sete não é razão para perder o processo inteiro, e quem revisa continua com
    o mapa e com a transcrição para uma segunda passada.
    """
    if not isinstance(bruto, list):
        return []
    etapas: list[dict] = []
    for item in bruto:
        if not isinstance(item, dict):
            continue
        nome = str(item.get("name") or "").strip()
        if not nome:
            continue
        etapa: dict = {"name": nome[:255]}
        etapa.update({campo: str(item.get(campo) or "").strip() for campo in _ETAPA_PSDTER})
        etapas.append(etapa)
    return etapas


def _achados_do_bruto(bruto: object) -> list[str]:
    """Os achados de um processo — strings puras, e **só** strings.

    Um item que chega como objeto (`{"content": "..."}`) é descartado em vez de convertido: o
    `str()` de um dicionário gravaria o `repr` dele como achado, um texto que ninguém disse com a
    aparência de citação de reunião.
    """
    if not isinstance(bruto, list):
        return []
    return [texto for item in bruto if isinstance(item, str) and (texto := item.strip())]


def processos_do_texto(text: str) -> list[dict]:
    """Extrai o mapa de processos do que o modelo devolveu. Função pura, mesmo molde de
    `decisoes_do_texto` acima — inclusive o recorte do primeiro ``[`` ao último ``]``, o item
    malformado descartado sem derrubar a extração e o ``[]`` de "não houve extração", que quem
    chama traduz em 502 em vez de gravar zero em silêncio. Os porquês estão argumentados lá.

    **Duas chaves não são lidas aqui, e a omissão é a fatia inteira (FDD 039).** O que rotula o
    achado e a maneira como ele foi obtido são atribuídos por quem grava, como constantes, e o
    modelo não opina: ler o que ele mandar — mesmo para sobrescrever em seguida — faria a
    imposição parecer negociável para quem lesse o código depois.

    **O achado é do processo, nunca da etapa.** O modelo não distingue com confiança a qual etapa
    um achado pertence, e vínculo errado é pior que vínculo nenhum — `Evidencia.etapa` é opcional
    exatamente para que uma pessoa o preencha depois, olhando o mapa.
    """
    inicio, fim = text.find("["), text.rfind("]")
    if inicio == -1 or fim <= inicio:
        return []
    try:
        bruto = json.loads(text[inicio : fim + 1])
    except json.JSONDecodeError:
        return []
    if not isinstance(bruto, list):
        return []

    extraidos: list[dict] = []
    for item in bruto:
        if not isinstance(item, dict):
            continue
        nome = str(item.get("name") or "").strip()
        if not nome:
            continue
        extraidos.append({
            # 255 porque `Processo.name` e `ProcessoEtapa.name` são `CharField(max_length=255)`, e
            # o modelo não tem como saber disso: um nome de 4.000 caracteres viraria `DataError` no
            # meio da gravação, derrubando o mapa inteiro por um item.
            "name": nome[:255],
            "etapas": _etapas_do_bruto(item.get("etapas")),
            "achados": _achados_do_bruto(item.get("achados")),
        })
    return extraidos


def sinal_do_texto(text: str) -> str:
    """Extrai o sinal de cobrança do que o modelo devolveu. Função pura, mesmo molde de
    `decisoes_do_texto` e pela mesma razão: **o modelo não obedece à instrução de formato o tempo
    todo**, e a falha típica é JSON válido embrulhado em prosa ou em cerca de markdown. Recortar do
    primeiro ``{`` ao último ``}`` cobre os três casos com uma regra só.

    **Sinal fora do vocabulário é descartado, não gravado.** Os três valores roteiam para condutas
    diferentes (RFC 0004, camada 4) — um quarto valor inventado pelo modelo viraria uma coluna que
    ninguém sabe ler. Descartado, a chamada devolve ``""`` e quem a invoca responde 502, que é
    diferente de gravar "não sei" em silêncio.
    """
    from .models import Activity

    inicio, fim = text.find("{"), text.rfind("}")
    if inicio == -1 or fim <= inicio:
        return ""
    try:
        bruto = json.loads(text[inicio : fim + 1])
    except json.JSONDecodeError:
        return ""
    if not isinstance(bruto, dict):
        return ""
    sinal = str(bruto.get("sinal") or "").strip().lower()
    return sinal if sinal in Activity.CobrancaSinal.values else ""


def _ai_run(  # type: ignore[no-untyped-def]
    request, feature, system, user_prompt, project=None, opportunity=None,
    artifact_kind=None, artifact_title="", source_meeting=None, grounding=None,
    formato=_FORMATO_TEXTO, coletor=None,
):
    """Guarda (flag + limite), executa a IA e registra a auditoria.

    Com `artifact_kind`, o texto também vira um `Artifact` em rascunho (FDD 016) — antes ele só
    existia na resposta HTTP. A chave `artifact` é aditiva: `text` e `interaction` seguem iguais.

    `formato` e `coletor` entraram na FDD 032, e os dois vieram do mesmo problema: extrair
    **N decisões** de uma transcrição não cabe no que este helper fazia.

    - `formato=_FORMATO_JSON` **não** concatena o `_TEXTO_CORRIDO`. Aquele texto manda o modelo não
      usar crase nem marcação, e pedir JSON logo depois é dizer duas coisas contrárias na mesma
      instrução. Ele continua sendo o padrão, porque o destino de quase todo texto gerado aqui é um
      `<textarea>`.
    - `coletor` é chamado com `(text, interaction)` e devolve o que entra no `payload`. É o mesmo
      lugar do bloco do artefato, e de propósito: um segundo caminho até `ai.complete` faria "o que
      a IA pode gravar" deixar de caber num arquivo, que é a razão de este helper ser um só (ver o
      comentário do `grounding` abaixo).
    """
    if not ai.is_enabled():
        return Response({"detail": "Recurso de IA está desativado."}, status=status.HTTP_503_SERVICE_UNAVAILABLE)
    if not ai.within_daily_limit(request.user):
        return Response({"detail": "Limite diário de uso de IA atingido."}, status=status.HTTP_429_TOO_MANY_REQUESTS)
    # Este helper serve **nove** actions, e a chamada mora atrás de `# pragma: no cover` — por isso
    # a falta de guarda passou batida: 429 de rate limit, timeout de 30 s, chave revogada ou modelo
    # sem acesso na conta viravam 500 do Django. Nada é gravado antes da resposta chegar, então a
    # falha não consome a cota diária de quem tentou nem deixa artefato pela metade.
    # O material da metodologia entra **aqui e só aqui** (FDD 029). `grounding` é preenchido
    # exclusivamente pelo `AgentView`; os outros oito chamadores passam `None` e seguem idênticos.
    # Ponto único de chamada é o que faz o anti-vazamento ser estrutural em vez de vigiado: não há
    # segundo caminho por onde o corpus interno saia.
    if grounding is not None:
        system = f"{system}\n\n{knowledge.GROUNDING_RULES}"
        user_prompt = f"{user_prompt}\n\n{grounding.block}"
    moldura = f"{system}\n\n{_TEXTO_CORRIDO}" if formato == _FORMATO_TEXTO else system
    try:
        text, usage = ai.complete(moldura, user_prompt)
    except ai.AiProviderError as exc:
        logger.exception("chamada de IA (%s) falhou", feature)
        raise AiProviderUnavailable() from exc
    sources: list[dict] = []
    if grounding is not None:
        text, sources = knowledge.enforce_citations(text, grounding)
    interaction = AiInteraction.objects.create(
        user=request.user, feature=feature, project=project, opportunity=opportunity,
        prompt_tokens=usage.get("prompt_tokens", 0), completion_tokens=usage.get("completion_tokens", 0),
        sources=sources,
    )
    payload: dict[str, object] = {"text": text, "interaction": interaction.id}
    if grounding is not None:
        payload["sources"] = sources
    if artifact_kind is not None:
        artifact = Artifact.objects.create(
            kind=artifact_kind, title=artifact_title, content=text,
            opportunity=opportunity, project=project, source_meeting=source_meeting,
            ai_interaction=interaction, created_by=request.user,
        )
        payload["artifact"] = ArtifactSerializer(artifact).data
    if coletor is not None:
        payload.update(coletor(text, interaction))
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


class ActivityViewSet(QueryParamFilterMixin, ArchiveModelViewSet):
    """Interação comercial com o cliente (ligação, reunião, e-mail, nota) — FDD 035."""

    resource = "activity"
    queryset = Activity.objects.select_related("client", "opportunity", "owner").all()
    serializer_class = ActivitySerializer
    filter_fields = ("client", "opportunity")

    def get_queryset(self):  # type: ignore[no-untyped-def]
        # Mesma fronteira do Contact: a Entrega só enxerga interações de clientes com projeto seu.
        queryset = super().get_queryset()
        scope = project_scope_q(self.request.user, "client__projects")
        return queryset.filter(scope).distinct() if scope else queryset

    def perform_create(self, serializer: ActivitySerializer) -> None:
        serializer.save(owner=self.request.user)

    @extend_schema(request=None, responses=ActivitySerializer)
    @action(detail=True, methods=["post"])
    def classificar(self, request: Request, pk: str | None = None) -> Response:
        """Lê a resposta do cliente e grava o sinal — **e não age** (FDD 036, camada 4).

        Os três valores não são etiquetas de humor: cada um manda para uma conduta diferente e a
        mesma régua estraga os três se tratá-los igual. `esqueceu` já se resolveu com o lembrete;
        `nao_pode` pede renegociação, e cedo; `insatisfeito` não é problema de cobrança — é
        problema de relação disfarçado, e é onde insistir piora tudo.

        Gravar o sinal é o fim do que a IA faz aqui. Renegociar, dar desconto, suspender e escalar
        seguem humanos (ADR 0006, ADR 0031).
        """
        activity = self.get_object()
        system = (
            "Você classifica a resposta de um cliente a uma cobrança. Devolva APENAS um objeto "
            'JSON, sem texto antes ou depois, com a chave "sinal" e um destes três valores: '
            '"esqueceu" (apenas não lembrou e vai pagar), "nao_pode" (tem dificuldade financeira '
            'ou de fluxo de caixa) ou "insatisfeito" (está retendo o pagamento por insatisfação '
            "com a entrega ou com a relação). Use APENAS o material fornecido: se ele não permitir "
            "decidir, devolva um objeto vazio em vez de inferir."
        )

        def grava(text: str, interaction) -> dict:  # type: ignore[no-untyped-def]
            sinal = sinal_do_texto(text)
            if not sinal:
                # Sem sinal utilizável não houve classificação — e isso é diferente de gravar um
                # valor qualquer. A coluna roteia conduta; um valor chutado manda alguém insistir
                # com quem está insatisfeito.
                raise _ExtracaoSemResultado()
            Activity.objects.filter(pk=activity.pk).update(cobranca_sinal=sinal)
            activity.refresh_from_db()
            return {"activity": ActivitySerializer(activity).data}

        try:
            return _ai_run(
                request, "dunning_classify", system,
                ai.build_resposta_de_cobranca_context(activity),
                formato=_FORMATO_JSON, coletor=grava,
            )
        except _ExtracaoSemResultado:
            return Response(
                {"detail": "A IA não devolveu um sinal utilizável. Tente de novo."},
                status=status.HTTP_502_BAD_GATEWAY,
            )


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
        # Invariante 6 do mapa de linguagem (ADR 0049): oferta de **aquisição** não gera projeto.
        # A Qualification Call existe para descobrir se há venda, não para ser entregue — e era
        # justamente por ela que a conversa de qualificação virava projeto. `Project.clean()`
        # repete a regra para quem não passa por aqui.
        if service and service.category == Service.Category.ACQUISITION:
            return Response(
                {"service": "Oferta de aquisição não gera projeto — a Qualification Call abre a "
                            "venda, ela não é a venda. Escolha um degrau da escada."},
                status=400,
            )
        try:
            with transaction.atomic():
                project = serializer.save(
                    opportunity=opportunity, owner=request.user, service=service
                )
                kickoff.seed_work_items(project)
                # Dentro da transação, e não no `finalize` abaixo, porque é escrita no banco e não
                # efeito externo — o mesmo lugar de `seed_work_items`, pelo mesmo motivo. As
                # faturas nascem em **rascunho**: débito automático não existe neste recorte, e
                # emitir é ato deliberado de gente (FDD 028).
                invoices.seed_invoices(project)
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
        journey.advance_phase(project, actor=request.user)
        return Response(ProjectPhaseSerializer(_project_phases_qs(project), many=True).data)

    @extend_schema(
        request=inline_serializer(
            "ApplyGate",
            {
                "outcome": serializers.ChoiceField(choices=ProjectPhase.GateOutcome.choices),
                "notes": serializers.CharField(required=False, allow_blank=True),
            },
        ),
        responses={200: ProjectPhaseSerializer(many=True)},
    )
    @action(detail=True, methods=["post"], url_path="apply-gate")
    def apply_gate(self, request: Request, pk: str | None = None) -> Response:
        """Registra o decision gate de quatro saídas na fase ativa (delivery/admin, FDD 033).

        Devolve a jornada inteira, no mesmo formato do `advance-phase`: as quatro saídas mexem em
        até duas fases, e a tela precisa da lista atualizada, não do que mudou.
        """
        project = self.get_object()
        outcome = str(request.data.get("outcome", "")).strip()
        if outcome not in ProjectPhase.GateOutcome.values:
            return Response(
                {"detail": "Informe uma das quatro saídas: go, conditional_go, redesign, no_go."},
                status=400,
            )
        notes = str(request.data.get("notes", "") or "")
        journey.apply_gate(project, outcome, notes, actor=request.user)
        return Response(ProjectPhaseSerializer(_project_phases_qs(project), many=True).data)

    @extend_schema(
        request=inline_serializer(
            "SetPhaseWaiting",
            {
                "waiting_party": serializers.ChoiceField(
                    choices=ProjectPhase.WaitingParty.choices, allow_blank=True
                ),
                "note": serializers.CharField(required=False, allow_blank=True),
            },
        ),
        responses={200: ProjectPhaseSerializer(many=True)},
    )
    @action(detail=True, methods=["post"], url_path="set-waiting")
    def set_waiting(self, request: Request, pk: str | None = None) -> Response:
        """Define de quem/de quê a fase ativa está esperando (delivery/admin, FDD 042).

        `waiting_party` vazio limpa o bloqueio. Escreve um `PhaseEvent` — é o que dá rastro à
        mudança, e o motivo de o campo não entrar por PATCH. Devolve a jornada inteira, no mesmo
        formato do `advance-phase`.
        """
        project = self.get_object()
        waiting_party = str(request.data.get("waiting_party", "") or "").strip()
        note = str(request.data.get("note", "") or "")
        journey.set_phase_waiting(project, waiting_party, note, actor=request.user)
        return Response(ProjectPhaseSerializer(_project_phases_qs(project), many=True).data)

    @extend_schema(
        request=None,
        responses=inline_serializer(
            "ProjectTimeline",
            {
                "project": serializers.IntegerField(),
                "phases": ProjectPhaseSerializer(many=True),
                "current_phase": ProjectPhaseSerializer(allow_null=True),
                "next_phase": inline_serializer(
                    "TimelineNextPhase",
                    {"phase_name": serializers.CharField(),
                     "canonical_stage": serializers.CharField(allow_blank=True)},
                    allow_null=True,
                ),
                "next_gate": inline_serializer(
                    "TimelineNextGate",
                    {"phase_name": serializers.CharField(),
                     "canonical_stage": serializers.CharField(allow_blank=True)},
                    allow_null=True,
                ),
                "blockers": inline_serializer(
                    "TimelineBlocker",
                    {"phase_name": serializers.CharField(),
                     "waiting_party": serializers.CharField(),
                     "blocker_note": serializers.CharField(allow_blank=True)},
                    many=True,
                ),
                "events": PhaseEventSerializer(many=True),
            },
        ),
    )
    @action(detail=True, methods=["get"])
    def timeline(self, request: Request, pk: str | None = None) -> Response:
        """A linha do tempo operacional do projeto (FDD 042).

        Fase corrente + histórico append-only + próximo gate + o que está aguardando, tudo
        derivado de campos explícitos (FinOps: sem LLM). Herda o recorte de projeto da
        `ProjectViewSet` — `get_object` já aplica a permissão de objeto.
        """
        project = self.get_object()
        return Response(_build_project_timeline(project))

    @extend_schema(
        responses=inline_serializer(
            "DeliveryTimelineOverview",
            {
                "project_id": serializers.IntegerField(),
                "project_name": serializers.CharField(),
                "client_name": serializers.CharField(),
                "current_phase_name": serializers.CharField(allow_null=True),
                "canonical_stage": serializers.CharField(allow_blank=True),
                "situation": serializers.CharField(allow_null=True),
                "waiting_party": serializers.CharField(allow_blank=True),
                "blocker_note": serializers.CharField(allow_blank=True),
                "next_gate_name": serializers.CharField(allow_null=True),
            },
            many=True,
        )
    )
    @action(detail=False, methods=["get"], url_path="timeline-overview")
    def timeline_overview(self, request: Request) -> Response:
        """Visão compacta da entrega para o dashboard: fase corrente e situação por projeto ativo.

        Agregador que **estreita à mão** por `visible_to` (o mesmo contrato dos outros do
        dashboard) e tem teste próprio: a Entrega não pode ver a jornada de projeto de que não
        participa. Só projetos não-concluídos entram — o dashboard é sobre o que está em curso.
        """
        return Response(_build_timeline_overview(request.user))

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
        .prefetch_related("deliverables", "checklist_items")
        .order_by("phase__position", "id")
    )


def _next_gate_phase(phases: list[ProjectPhase]) -> ProjectPhase | None:
    """A próxima fase (na ordem) que termina em gate e ainda não decidiu — o "próximo gate".

    Determinístico (FinOps): a fase ativa conta se ainda não gravou outcome; senão, a primeira
    trancada à frente que exige gate.
    """
    for phase in phases:
        if phase.status == ProjectPhase.Status.DONE:
            continue
        if phase.phase.requires_gate and not phase.gate_outcome:
            return phase
    return None


def _build_project_timeline(project: Project) -> dict[str, Any]:
    """Monta a linha do tempo operacional de um projeto (FDD 042)."""
    journey.materialize_journey(project)
    phases = list(_project_phases_qs(project))
    current = next((p for p in phases if p.status == ProjectPhase.Status.ACTIVE), None)
    next_phase = None
    if current is not None:
        after = phases[phases.index(current) + 1 :]
        nxt = next((p for p in after if p.status == ProjectPhase.Status.LOCKED), None)
        if nxt is not None:
            next_phase = {"phase_name": nxt.phase.name,
                          "canonical_stage": nxt.phase.canonical_stage}
    gate_phase = _next_gate_phase(phases)
    blockers = [
        {"phase_name": p.phase.name, "waiting_party": p.waiting_party,
         "blocker_note": p.blocker_note}
        for p in phases
        if p.status == ProjectPhase.Status.ACTIVE and p.waiting_party
    ]
    events = PhaseEvent.objects.filter(project=project).select_related("actor", "project_phase")
    return {
        "project": project.pk,
        "phases": ProjectPhaseSerializer(phases, many=True).data,
        "current_phase": ProjectPhaseSerializer(current).data if current else None,
        "next_phase": next_phase,
        "next_gate": (
            {"phase_name": gate_phase.phase.name,
             "canonical_stage": gate_phase.phase.canonical_stage}
            if gate_phase is not None
            else None
        ),
        "blockers": blockers,
        "events": PhaseEventSerializer(events, many=True).data,
    }


def _build_timeline_overview(user: User) -> list[dict[str, Any]]:
    """Visão compacta da entrega para o dashboard — estreitada à mão por `visible_to` (FDD 042)."""
    projects = list(
        Project.objects.visible_to(user)
        .filter(archived_at__isnull=True)
        .exclude(status=Project.Status.COMPLETED)
        .select_related("client")
        .order_by("due_date", "id")
    )
    if not projects:
        return []
    ids = [p.pk for p in projects]
    phases_by_project: dict[int, list[ProjectPhase]] = {}
    for phase in (
        ProjectPhase.objects.filter(project_id__in=ids, archived_at__isnull=True)
        .select_related("phase")
        .order_by("phase__position", "id")
    ):
        phases_by_project.setdefault(phase.project_id, []).append(phase)
    rows: list[dict[str, Any]] = []
    for project in projects:
        phases = phases_by_project.get(project.pk, [])
        current = next((p for p in phases if p.status == ProjectPhase.Status.ACTIVE), None)
        gate_phase = _next_gate_phase(phases)
        rows.append({
            "project_id": project.pk,
            "project_name": project.name,
            "client_name": project.client.name,
            "current_phase_name": current.phase.name if current else None,
            "canonical_stage": current.phase.canonical_stage if current else "",
            "situation": current.situation if current else None,
            "waiting_party": current.waiting_party if current else "",
            "blocker_note": current.blocker_note if current else "",
            "next_gate_name": gate_phase.phase.name if gate_phase is not None else None,
        })
    return rows


class JourneyPhaseViewSet(viewsets.ModelViewSet):
    """Template configurável das fases da jornada (admin). Espelha PipelineStage."""

    resource = "journey"
    queryset = JourneyPhase.objects.prefetch_related("deliverables", "checklist_items").all()
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


class PhaseChecklistItemViewSet(QueryParamFilterMixin, viewsets.ModelViewSet):
    """Template do checklist de qualidade de cada fase (admin, FDD 033)."""

    resource = "journey"
    queryset = PhaseChecklistItem.objects.select_related("phase").all()
    serializer_class = PhaseChecklistItemSerializer
    permission_classes = [RolePermission]
    filter_fields = ("phase",)


class ProjectPhaseViewSet(ProjectScopedMixin, QueryParamFilterMixin, ArchiveModelViewSet):
    """Estado da jornada por projeto (leitura para todos; equipe edita `target_date`)."""

    resource = "project_phase"
    queryset = ProjectPhase.objects.select_related("phase", "project").prefetch_related(
        "deliverables", "checklist_items"
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


class ProjectChecklistItemViewSet(ProjectScopedMixin, QueryParamFilterMixin, ArchiveModelViewSet):
    """Checklist de qualidade por projeto — a equipe confere item a item (delivery/admin)."""

    resource = "project_checklist_item"
    project_path = "project_phase__project"  # o item não carrega o projeto direto
    scope_payload_field = "project_phase"
    queryset = ProjectChecklistItem.objects.select_related(
        "project_phase", "project_phase__project"
    )
    serializer_class = ProjectChecklistItemSerializer
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


class InvoiceViewSet(QueryParamFilterMixin, viewsets.ModelViewSet):
    """Contas a receber (FDD 028, camada 0 da RFC 0004).

    **Nem `ArchiveModelViewSet` nem `ProjectScopedMixin`, e as duas ausências são a entrega.**

    Não arquiva porque registro financeiro emitido não se apaga nem se esconde: cancela-se, e a
    linha sobrevive ao próprio cancelamento (ADR 0021). Arquivar seria pior que apagar — some da
    lista sem desfazer o fato, e um recebível que sai do total em aberto em silêncio é o defeito
    que este recurso existe para não ter.

    Não é escopado por projeto porque dado financeiro não pertence ao recorte de projeto: a Entrega
    não alcança fatura nenhuma, nem de leitura, nem em projeto de que participa — o que quem passar
    por aqui vai querer "consertar" achando que é esquecimento. Não é.
    """

    resource = "invoice"
    queryset = Invoice.objects.select_related("client", "project", "service").all()
    serializer_class = InvoiceSerializer
    permission_classes = [RolePermission]
    filter_fields = ("client", "project")
    filter_exact_fields = ("status",)

    def perform_destroy(self, instance: Invoice) -> None:
        """Rascunho se descarta; emitida, não — 409 apontando o cancelamento (FDD 025, FDD 028)."""
        if instance.status != Invoice.Status.DRAFT:
            raise StateConflict(
                f"A fatura {instance.number or instance.pk} já foi emitida e não se apaga. "
                f"Cancele-a, se for o caso."
            )
        instance.delete()

    @extend_schema(responses=InvoiceSerializer, request=None)
    @action(detail=True, methods=["post"])
    def issue(self, request: Request, pk: str | None = None) -> Response:
        """Emite: pede a cobrança ao gateway e **só então** numera e carimba (admin).

        A ordem é a lição que a FDD 024 aprendeu quatro vezes. A chamada de rede acontece **fora**
        da transação — segurar um `select_for_update` durante um round-trip ao Stripe esgota o pool
        de conexões —, e a fatura só muda de estado depois de o fornecedor confirmar. Fornecedor
        fora do ar deixa a fatura em rascunho, sem número e sem carimbo, e devolve 502.
        """
        invoice = self.get_object()
        if invoice.status != Invoice.Status.DRAFT:
            raise StateConflict(
                f"A fatura {invoice.number or invoice.pk} já foi emitida."
            )
        if invoice.amount <= 0:
            return Response(
                {"amount": "Uma fatura de valor zero não se emite."},
                status=status.HTTP_400_BAD_REQUEST,
            )
        try:
            ref = payments.issue_charge(invoice)
        except payments.PaymentProviderError as exc:
            logger.exception("emissão recusada para a fatura %s", invoice.pk)
            raise PaymentsUnavailable() from exc
        return Response(InvoiceSerializer(invoices.finish_issue(invoice, ref, request.user)).data)

    @extend_schema(responses=InvoiceSerializer, request=None)
    @action(detail=True, methods=["post"], url_path="mark-paid")
    def mark_paid(self, request: Request, pk: str | None = None) -> Response:
        """Baixa manual (admin) — e, sem gateway configurado, o **único** caminho de baixa.

        É a gêmea do `mark-signed` do documento, e a FDD 028 pede que isso seja dito em voz alta
        em vez de descoberto: quem não tem `PAYMENTS_PROVIDER` opera a camada 0 inteira por aqui.
        """
        invoice = self.get_object()
        try:
            baixada = invoices.settle(
                invoice,
                method=str(request.data.get("method", "")),
                by=request.user,
            )
        except invoices.InvoiceTransitionError as exc:
            return Response({"status": str(exc)}, status=status.HTTP_400_BAD_REQUEST)
        return Response(InvoiceSerializer(baixada).data)

    @extend_schema(responses=InvoiceSerializer, request=None)
    @action(detail=True, methods=["post"])
    def cancel(self, request: Request, pk: str | None = None) -> Response:
        """Cancela com motivo obrigatório (admin) — a saída que substitui apagar e arquivar.

        O motivo é exigido porque cancelamento de recebível sem justificativa é o começo do
        recebível que estraga invisível: a RFC 0004 já registra que "recuar precisa ser declarado".
        """
        invoice = self.get_object()
        reason = str(request.data.get("reason", "")).strip()
        if not reason:
            return Response(
                {"reason": "Diga por que esta fatura está sendo cancelada."},
                status=status.HTTP_400_BAD_REQUEST,
            )
        try:
            cancelada = invoices.cancel(invoice, request.user, reason)
        except invoices.InvoiceTransitionError as exc:
            return Response({"status": str(exc)}, status=status.HTTP_400_BAD_REQUEST)
        return Response(InvoiceSerializer(cancelada).data)

    @extend_schema(
        request=inline_serializer(
            name="CobrancaRascunhoRequest",
            fields={"degrau": serializers.CharField(required=False)},
        ),
        responses=inline_serializer(
            name="CobrancaRascunho",
            fields={
                "text": serializers.CharField(),
                "interaction": serializers.IntegerField(),
                "degrau": serializers.CharField(),
            },
        ),
    )
    @action(detail=True, methods=["post"], url_path="cobranca/rascunhar")
    def cobranca_rascunhar(self, request: Request, pk: str | None = None) -> Response:
        """Rascunha o texto do degrau no tom certo — e **não envia** (FDD 036, ADR 0031).

        A separação entre rascunhar e enviar é a decisão da ADR 0031, não uma etapa de UI: o degrau
        determinístico sai sozinho porque seu texto é constante revisada uma vez; o texto de IA
        muda a **redação**, que é exatamente o que uma pessoa revisaria. Aprovar em bloco um gerador
        de texto de cobrança é aprovar o parágrafo que ainda não existe e que vai chamar de
        caloteiro um cliente de cinco anos.

        `grounding=None`: o corpus interno da metodologia não tem o que fazer num e-mail de
        cobrança, e o anti-vazamento é estrutural — só o `AgentView` preenche aquele parâmetro.
        """
        invoice = self.get_object()
        degrau = str(request.data.get("degrau", "")).strip() or (
            getattr(cobranca.degrau_devido(invoice), "key", "")
        )
        if degrau not in CobrancaContato.Degrau.values:
            return Response(
                {"degrau": "Diga qual degrau rascunhar — hoje a régua não indica nenhum."},
                status=status.HTTP_400_BAD_REQUEST,
            )
        rotulo = CobrancaContato.Degrau(degrau).label
        system = (
            "Você redige um e-mail de cobrança em português do Brasil, em nome de uma consultoria, "
            f"no tom do degrau '{rotulo}'. O objetivo não é receber esta fatura a qualquer custo: é "
            "receber e manter o cliente. Nunca acuse, nunca ameace e nunca insinue má-fé. Use "
            "APENAS o material fornecido — não invente valores, datas nem combinados. Não cite "
            "custo, margem nem retorno do projeto. É um rascunho para revisão humana."
        )
        return _ai_run(
            request,
            "dunning_draft",
            system,
            ai.build_cobranca_context(invoice, degrau),
            project=invoice.project,
            grounding=None,
            coletor=lambda text, interaction: {"degrau": degrau},
        )

    @extend_schema(
        request=inline_serializer(
            name="CobrancaEnvioRequest",
            fields={
                "degrau": serializers.CharField(),
                "subject": serializers.CharField(required=False),
                "body": serializers.CharField(),
                "ai_interaction": serializers.IntegerField(required=False),
            },
        ),
        responses=CobrancaContatoSerializer,
    )
    @action(detail=True, methods=["post"], url_path="cobranca/enviar")
    def cobranca_enviar(self, request: Request, pk: str | None = None) -> Response:
        """Manda o degrau ao cliente com o texto que uma pessoa revisou (admin).

        As guardas que valem tanto aqui quanto no job — estado cobrável, suspensão ativa e degrau
        já gasto — são as mesmas funções de `cobranca.py`, e é isso que impede a tela e o relógio
        de divergirem. **A que não vale aqui é o teto de frequência**: ele existe para conter o
        robô que ninguém está olhando, e quem clica está olhando. Trocar o julgamento de quem vê a
        tela pela contagem de dias seria proteger o cliente de uma decisão que já foi tomada.
        """
        if not cobranca.is_enabled():
            # A flag é o interruptor **da funcionalidade**, não só do relógio (ADR 0031). Sem esta
            # guarda, "Régua de cobrança: desligada" na tela de Configurações seria mentira: o job
            # calaria e a API seguiria mandando cobrança ao cliente. É o mesmo 503 que o webhook de
            # pagamento devolve com `payments` desligado.
            return Response(
                {"detail": "A régua de cobrança está desativada."},
                status=status.HTTP_503_SERVICE_UNAVAILABLE,
            )
        invoice = self.get_object()
        degrau_key = str(request.data.get("degrau", "")).strip()
        degrau = next(
            (d for d in cobranca.PADRAO + cobranca.RELACAO_LONGA if d.key == degrau_key), None
        )
        body = str(request.data.get("body", "")).strip()
        if degrau is None:
            return Response(
                {"degrau": "Degrau desconhecido."}, status=status.HTTP_400_BAD_REQUEST
            )
        if not body:
            return Response(
                {"body": "O texto revisado é obrigatório — o envio manual não usa o template."},
                status=status.HTTP_400_BAD_REQUEST,
            )
        if invoice.status not in cobranca.COBRAVEIS:
            raise StateConflict(
                f"A fatura {invoice.number or invoice.pk} está {invoice.get_status_display()} "
                "e não comporta cobrança."
            )
        suspensao = cobranca.suspensao_ativa(invoice)
        if suspensao is not None:
            raise StateConflict(
                f"A cobrança está suspensa até {suspensao.until}. Levante a suspensão antes de "
                "enviar — recuar e voltar a cobrar são atos declarados."
            )
        # A idempotência conferida **antes** do envio, e não só pela `UniqueConstraint` no fim: a
        # constraint impediria a linha duplicada, mas o e-mail já teria saído. Quem leva o segundo
        # "sua fatura está vencida" não se consola com a integridade do banco.
        if CobrancaContato.objects.filter(invoice=invoice, degrau=degrau.key).exists():
            raise StateConflict(f"O degrau '{degrau.key}' desta fatura já foi enviado.")
        interaction = None
        if request.data.get("ai_interaction"):
            interaction = AiInteraction.objects.filter(
                pk=request.data["ai_interaction"], user=request.user
            ).first()
        try:
            contato = cobranca.enviar_ao_cliente(
                invoice,
                degrau,
                subject=str(request.data.get("subject", "")).strip(),
                body=body,
                sent_by=request.user,
                ai_interaction=interaction,
            )
        except IntegrityError as exc:
            # A `UniqueConstraint(invoice, degrau)`. É o mesmo 409 que o job trata como "não hoje":
            # o degrau já foi gasto, por uma pessoa ou pelo relógio.
            raise StateConflict(
                f"O degrau '{degrau.key}' desta fatura já foi enviado."
            ) from exc
        except cobranca.SemDestinatarioInterno as exc:
            # Sem contato de cobrança **e** sem ninguém a quem escalar. O degrau não é gasto, e a
            # mensagem nomeia a saída em vez de devolver 500 numa condição que gente conserta.
            raise StateConflict(
                f"{invoice.client.name} não tem contato marcado como 'recebe cobrança' e não há "
                "administrador ativo a quem escalar. Cadastre o contato antes de enviar."
            ) from exc
        except OSError as exc:
            # E-mail não saiu: **nada é gravado**. Registrar aqui afirmaria um contato que não
            # aconteceu e ainda queimaria o degrau pela constraint, impedindo a retentativa.
            logger.exception("envio de cobrança falhou para a fatura %s", invoice.pk)
            raise EmailUndeliverable() from exc
        return Response(CobrancaContatoSerializer(contato).data, status=status.HTTP_201_CREATED)

    @extend_schema(
        responses=inline_serializer(
            name="InvoiceSummary",
            fields={
                "open": serializers.DecimalField(max_digits=12, decimal_places=2),
                "overdue": serializers.DecimalField(max_digits=12, decimal_places=2),
                "paid": serializers.DecimalField(max_digits=12, decimal_places=2),
                "open_count": serializers.IntegerField(),
                "overdue_count": serializers.IntegerField(),
                "paid_count": serializers.IntegerField(),
            },
        )
    )
    @action(detail=False, methods=["get"])
    def summary(self, request: Request) -> Response:
        """Os três totais da tela, numa consulta agregada só.

        Agregado no banco e não em laço de Python porque este endpoint entra na mesma disciplina
        do gate de custo de query da ADR 0014: o custo não pode crescer com a base.
        """
        faixas = {
            "open": Q(status=Invoice.Status.ISSUED),
            "overdue": Q(status=Invoice.Status.OVERDUE),
            "paid": Q(status=Invoice.Status.PAID),
        }
        dados = self.get_queryset().aggregate(
            **{nome: Sum("amount", filter=q, default=Decimal("0")) for nome, q in faixas.items()},
            **{f"{nome}_count": Count("id", filter=q) for nome, q in faixas.items()},
        )
        return Response(dados)


class CobrancaViewSet(QueryParamFilterMixin, viewsets.ReadOnlyModelViewSet):
    """O que a casa já disse sobre suas faturas (FDD 036, camada 3 da RFC 0004).

    **Só leitura, e a ausência de escrita é a entrega.** Um `POST /cobranca/` criaria a prova de um
    contato que não aconteceu — e é justamente a classe de defeito que a homologação de integrações
    achou três vezes (registro gravado sem o fornecedor ter sido chamado). Contato nasce de
    `POST /invoices/{id}/cobranca/enviar/` ou do job das 09:30, e os dois mandam o e-mail **antes**
    de gravar.

    Nem `ArchiveModelViewSet` nem `ProjectScopedMixin`, pelas mesmas duas razões da `InvoiceViewSet`
    logo acima: registro de comunicação sobre dinheiro não se esconde da lista (ADR 0021), e dado
    financeiro não é escopado por projeto — a Entrega não alcança nada disto, nem para ler.
    """

    resource = "cobranca"
    queryset = CobrancaContato.objects.select_related("invoice", "client", "sent_by").all()
    serializer_class = CobrancaContatoSerializer
    permission_classes = [RolePermission]
    filter_fields = ("client", "invoice")
    filter_exact_fields = ("degrau", "canal")

    @extend_schema(
        responses=inline_serializer(
            name="CobrancaPainelLinha",
            fields={
                "invoice": serializers.IntegerField(),
                "number": serializers.CharField(),
                "client": serializers.IntegerField(),
                "client_name": serializers.CharField(),
                "amount": serializers.DecimalField(max_digits=12, decimal_places=2),
                "due_date": serializers.DateField(),
                "status": serializers.CharField(),
                "status_display": serializers.CharField(),
                "dias_de_atraso": serializers.IntegerField(),
                "payment_url": serializers.CharField(),
                "proximo_degrau": serializers.CharField(allow_null=True),
                "proximo_degrau_display": serializers.CharField(allow_null=True),
                "proximo_degrau_em": serializers.DateField(allow_null=True),
                "motivo": serializers.CharField(),
                "health_level": serializers.CharField(allow_null=True),
                "tempo_de_casa_dias": serializers.IntegerField(),
                "reincidente": serializers.BooleanField(),
                # A satisfação vigente (FDD 037). Os três são nulos juntos: ou há registro dentro
                # da janela de 90 dias, ou não há nenhum. `fonte` vai junto do nível de propósito —
                # é ela que diz se aquilo é o cliente falando ou a nossa leitura sobre ele, e é a
                # declarada, não a percebida, que troca a régua (ADR 0032).
                "satisfacao_nivel": serializers.CharField(allow_null=True),
                "satisfacao_fonte": serializers.CharField(allow_null=True),
                "satisfacao_dias": serializers.IntegerField(allow_null=True),
                # Por que a relação está tensa (FDD 038): `satisfacao`, `entrega`, `ambas` ou nulo.
                # É rótulo, não decisão — as três causas levam à mesma escada, e quem diz qual
                # escada vale é `regua`.
                "tensao_causa": serializers.CharField(allow_null=True),
                # A resposta de cobrança que a IA classificou e que **ninguém registrou ainda**
                # (ADR 0032). Os quatro são nulos juntos. Não é satisfação: é leitura de uma
                # resposta, e o painel a oferece como atalho para uma pessoa registrar.
                "sinal_kind": serializers.CharField(allow_null=True),
                "sinal_display": serializers.CharField(allow_null=True),
                "sinal_em": serializers.DateField(allow_null=True),
                "sinal_activity": serializers.IntegerField(allow_null=True),
                "regua": serializers.CharField(),
                "recebido_do_cliente": serializers.DecimalField(
                    max_digits=12, decimal_places=2
                ),
                "suspensao": serializers.DictField(allow_null=True),
                "regua_ligada": serializers.BooleanField(),
            },
            many=True,
        )
    )
    @action(detail=False, methods=["get"])
    def painel(self, request: Request) -> Response:
        """A tela onde se decide o próximo passo (FDD 036, critério de aceite 7).

        Agregador, e por isso **não passa pelo queryset desta viewset**: ele lista faturas, não
        contatos. O recorte de papel continua sendo o `resource = "cobranca"` da classe — só-leitura
        para Vendas, fechado para a Entrega —, que é o mesmo mecanismo da FDD 028 e a razão de esta
        rota não precisar de guarda própria.

        Toda a decisão sai de `cobranca.painel()`, e nenhuma linha dela é recalculada aqui: a régua
        tem uma definição só, e a tela lê a mesma que o relógio executa.
        """
        return Response(cobranca.painel())


class CobrancaSuspensaoViewSet(QueryParamFilterMixin, viewsets.ModelViewSet):
    """Suspender a cobrança — com dono, prazo e motivo (FDD 036, RFC 0004 "Segurança").

    **Vendas escreve aqui e não escreve em `invoice` nem em `cobranca`**, e a assimetria é o ponto:
    suspender é decisão de *relação*, e quem a carrega é quem responde pelo cliente. Emitir, baixar
    e enviar cobrança seguem sendo atos de admin, porque são dinheiro.

    Não arquiva: a suspensão vencida continua na lista, porque "por que ninguém cobrou este cliente
    em março?" é uma pergunta que precisa de resposta — e um registro arquivado é o mesmo recebível
    estragando invisível que a RFC nomeia.
    """

    resource = "cobranca_suspensao"
    queryset = CobrancaSuspensao.objects.select_related(
        "invoice", "client", "owner", "created_by"
    ).all()
    serializer_class = CobrancaSuspensaoSerializer
    permission_classes = [RolePermission]
    filter_fields = ("client", "invoice", "owner")

    def perform_create(self, serializer: CobrancaSuspensaoSerializer) -> None:
        serializer.save(created_by=self.request.user)

    @extend_schema(request=None, responses=CobrancaSuspensaoSerializer)
    @action(detail=True, methods=["post"])
    def levantar(self, request: Request, pk: str | None = None) -> Response:
        """Encerra a suspensão antes do prazo, com autor e carimbo.

        Existe porque a alternativa é pior: sem ela, uma suspensão criada por engano cala a régua
        pelo prazo inteiro e a única saída seria editar a linha, apagando o que houve. Levantar é
        ato — o oposto do "pular silencioso" que a RFC recusa nos dois sentidos.
        """
        suspensao = self.get_object()
        if suspensao.lifted_at is not None:
            raise StateConflict("Esta suspensão já foi levantada.")
        suspensao.lifted_at = timezone.now()
        suspensao.lifted_by = request.user
        suspensao.save(update_fields=["lifted_at", "lifted_by", "updated_at"])
        return Response(CobrancaSuspensaoSerializer(suspensao).data)


class KnowledgeAreaViewSet(viewsets.ModelViewSet):
    """As áreas de conhecimento e seus donos (FDD 029). Catálogo: todos leem, admin escreve."""

    resource = "knowledge_area"
    queryset = KnowledgeArea.objects.select_related("owner").all()
    serializer_class = KnowledgeAreaSerializer
    permission_classes = [RolePermission]


class KnowledgePieceViewSet(QueryParamFilterMixin, ArchiveModelViewSet):
    """O inventário de conhecimento (FDD 029).

    Leitura para todo autenticado **de propósito**: o dono de uma área pode ser de qualquer papel, e
    avisá-lo sobre uma peça que ele não consegue abrir seria um laço quebrado. Escrever é do admin,
    com uma exceção — `verify`, que é justamente o ato que se espera do dono.
    """

    resource = "knowledge"
    queryset = KnowledgePiece.objects.select_related("area", "area__owner", "verified_by").all()
    serializer_class = KnowledgePieceSerializer
    permission_classes = [RolePermission]
    filter_fields = ("area",)
    filter_exact_fields = ("kind",)

    def get_queryset(self):  # type: ignore[no-untyped-def]
        queryset = super().get_queryset()
        estado = self.request.query_params.get("status")
        if not estado:
            return queryset
        # O estado é derivado (depende do dono da área e do relógio), então filtra-se em Python
        # sobre o inventário — que é a mesma função que a tela e o job usam. Reproduzi-lo em SQL
        # seria a segunda expressão da regra, e ela divergiria na primeira mudança de prazo.
        ids = [piece.pk for piece in knowledge.inventory().get(estado, [])]
        return queryset.filter(pk__in=ids)

    @extend_schema(responses=KnowledgePieceSerializer, request=None)
    @action(detail=True, methods=["post"])
    def verify(self, request: Request, pk: str | None = None) -> Response:
        """Registra que alguém conferiu esta peça hoje — com autor e carimbo.

        Ação e não campo, no molde do `record-consent` (FDD 027): "está conferido" sem dizer quem
        conferiu é alegação de ninguém, e é exatamente o que apodrece num inventário de frescor.

        Admin sempre; além dele, **o dono da área** — que é de quem se espera o ato, e travá-lo
        atrás de admin faria o aviso chegar a quem não pode agir sobre ele.
        """
        piece = self.get_object()
        dono = piece.area.owner_id if piece.area else None
        if not request.user.is_admin_role and dono != request.user.pk:
            nome = piece.area.owner.get_full_name() if dono else "ninguém ainda"
            return Response(
                {"detail": f"Só o admin ou quem responde pela área ({nome}) pode verificar."},
                status=status.HTTP_403_FORBIDDEN,
            )
        piece.last_verified_at = timezone.localdate()
        piece.verified_by = request.user
        piece.save(update_fields=["last_verified_at", "verified_by", "updated_at"])
        return Response(KnowledgePieceSerializer(piece).data)

    @extend_schema(
        responses=inline_serializer(
            name="KnowledgeSummary",
            fields={
                "sem_dono": serializers.IntegerField(),
                "vencido": serializers.IntegerField(),
                "a_vencer": serializers.IntegerField(),
                "corrente": serializers.IntegerField(),
            },
        )
    )
    @action(detail=False, methods=["get"])
    def summary(self, request: Request) -> Response:
        grupos = knowledge.inventory()
        return Response({estado: len(pecas) for estado, pecas in grupos.items()})


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

    @action(detail=True, methods=["post"], url_path="extrair-decisoes")
    def extrair_decisoes(self, request: Request, pk: str | None = None) -> Response:
        """Propõe decisões do projeto a partir da transcrição, **em rascunho** (FDD 032).

        Mora aqui e não no `DecisaoViewSet` porque o insumo é a transcrição, e é isto que o
        `discovery` logo acima já estabeleceu: a IA de reunião pertence à reunião.

        Duas diferenças em relação às duas actions acima, e as duas são o ponto da fatia. A primeira
        é o **formato**: aqui o modelo devolve JSON, então o `_TEXTO_CORRIDO` (que manda não usar
        crase nem marcação) fica de fora. A segunda é o **destino**: em vez de um `Artifact` com o
        texto inteiro, saem N linhas de `Decisao` em `rascunho` — e rascunho **não entra no
        snapshot**, que é o que faz um palpite de modelo não alcançar o cliente antes de alguém
        publicar.
        """
        meeting = self.get_object()
        if not meeting.transcript.strip():
            return Response({"detail": "A reunião não tem transcrição."}, status=400)
        system = (
            "Você extrai decisões de projeto a partir da transcrição de uma reunião. Devolva "
            "APENAS um array JSON, sem texto antes ou depois, em que cada item tem as chaves "
            '"title" (a decisão em uma frase), "rationale" (o porquê, com as alternativas '
            'descartadas quando aparecerem) e "decided_by" (quem decidiu, como foi dito na '
            "reunião). Use APENAS o material fornecido: se a transcrição não registra uma decisão, "
            "devolva um array vazio em vez de inferir. É um rascunho para revisão humana."
        )

        def grava(text: str, interaction) -> dict:  # type: ignore[no-untyped-def]
            propostas = decisoes_do_texto(text)
            if not propostas:
                # Sem lista, não houve extração — e isso não é o mesmo que "a reunião não decidiu
                # nada", que o modelo expressa devolvendo `[]` e que chega aqui como lista vazia
                # também. Distinguir os dois exigiria um segundo canal de saída; entre inventar
                # essa distinção e recusar, recusar é o que não mente.
                raise _ExtracaoSemResultado()
            criadas = Decisao.objects.bulk_create([
                Decisao(
                    project=meeting.project, source_meeting=meeting,
                    status=Decisao.Status.DRAFT, **proposta,
                )
                for proposta in propostas
            ])
            return {"decisoes": DecisaoSerializer(criadas, many=True).data}

        try:
            # `atomic` em volta da chamada inteira: se o coletor levantar depois de gravar parte
            # das linhas, um `bulk_create` parcial deixaria rascunhos órfãos de uma extração que a
            # pessoa viu falhar. Aqui ou entram todas, ou nenhuma.
            with transaction.atomic():
                return _ai_run(
                    request, "meeting_decisoes", system, ai.build_meeting_context(meeting),
                    project=meeting.project, formato=_FORMATO_JSON, coletor=grava,
                )
        except _ExtracaoSemResultado:
            return Response(
                {"detail": "A IA não devolveu decisões em formato utilizável. Tente de novo."},
                status=status.HTTP_502_BAD_GATEWAY,
            )

    @action(detail=True, methods=["post"])
    def estruturar(self, request: Request, pk: str | None = None) -> Response:
        """Mapeia processos, etapas e achados da transcrição — **tudo como hipótese** (FDD 039).

        Mesmo molde do `extrair_decisoes` acima (JSON, coletor dentro de `atomic`, 502 quando não
        veio lista), com duas diferenças que são o ponto desta fatia.

        **A primeira é o que o modelo não decide.** Todo achado nasce rotulado como hipótese e com
        a origem "entrevista", sempre, atribuídos aqui como constantes — o `_PROMPT_PROCESSOS` não
        pergunta, e o `processos_do_texto` não lê. Um modelo lendo transcrição produz *o que foi
        dito*, que é uma das cinco formas de evidência (`docs/metodologia-fde.md:81-84`), não
        prova; promover a fato é ato de gente, pela mesma razão que a ADR 0032 recusou à IA gravar
        satisfação.

        **A segunda é a recusa de reexecução**, e ela é divergência deliberada do `extrair_decisoes`:
        lá cada execução cria `Decisao` em **rascunho**, um estado que a tela mostra como pendente
        de revisão, e uma segunda rodada só dá mais rascunho para revisar. `Processo` não tem
        estado de rascunho — a segunda extração dobraria o mapa da operação do cliente **em
        silêncio**, e um duplo clique bastaria. Recusar com 409 é dizer qual é o estado que impede
        e como sair dele, que é para o que o `StateConflict` existe.
        """
        meeting = self.get_object()
        if not meeting.transcript.strip():
            return Response({"detail": "A reunião não tem transcrição."}, status=400)
        # **Antes** da IA, e não dentro do coletor: recusar depois de chamar o provedor gastaria a
        # cota diária de quem clicou por um trabalho que já se sabia que seria descartado.
        ja_mapeados = Processo.objects.filter(
            source_meeting=meeting, archived_at__isnull=True
        ).count()
        if ja_mapeados:
            raise StateConflict(
                f"Esta reunião já tem {ja_mapeados} processo(s) mapeado(s). "
                "Arquive-os ou edite-os em vez de extrair de novo."
            )

        def grava(text: str, interaction) -> dict:  # type: ignore[no-untyped-def]
            extraidos = processos_do_texto(text)
            if not extraidos:
                # Mesma distinção do `extrair_decisoes`: sem lista não houve extração, e isso não
                # é o mesmo que "a reunião não descreveu processo nenhum".
                raise _ExtracaoSemResultado()
            client = meeting.project.client
            # A extração entra **depois** do que já foi mapeado à mão: `position` é a ordem em que
            # a operação acontece, e intercalar processos vindos de um modelo no meio de uma
            # sequência que alguém montou reescreveria essa ordem sem pedir licença.
            ultima = Processo.objects.filter(client=client, archived_at__isnull=True).aggregate(
                maior=Max("position")
            )["maior"]
            proxima = (ultima or 0) + 1
            criados: list[Processo] = []
            for indice, bruto in enumerate(extraidos):
                processo = Processo.objects.create(
                    client=client, name=bruto["name"], source_project=meeting.project,
                    source_meeting=meeting, registered_by=request.user,
                    position=proxima + indice,
                )
                ProcessoEtapa.objects.bulk_create([
                    ProcessoEtapa(processo=processo, position=posicao, **etapa)
                    for posicao, etapa in enumerate(bruto["etapas"], start=1)
                ])
                Evidencia.objects.bulk_create([
                    Evidencia(
                        processo=processo,
                        # Sem etapa de propósito: o modelo não distingue com confiança a qual delas
                        # o achado pertence, e um vínculo errado é pior que vínculo nenhum.
                        etapa=None,
                        rotulo=Evidencia.Rotulo.HIPOTESE,
                        forma=Evidencia.Forma.ENTREVISTA,
                        content=achado, source_meeting=meeting, registered_by=request.user,
                    )
                    for achado in bruto["achados"]
                ])
                criados.append(processo)
            return {"processos": ProcessoSerializer(criados, many=True).data}

        try:
            # `atomic` pela razão do `extrair_decisoes`: se a gravação falhar no quinto processo,
            # os quatro anteriores ficariam num mapa que a pessoa viu falhar — e, sem estado de
            # rascunho para distingui-los, indistinguíveis do que foi levantado de verdade.
            with transaction.atomic():
                return _ai_run(
                    request, "meeting_processos", _PROMPT_PROCESSOS,
                    ai.build_meeting_context(meeting), project=meeting.project,
                    formato=_FORMATO_JSON, coletor=grava,
                )
        except _ExtracaoSemResultado:
            return Response(
                {"detail": "A IA não devolveu processos em formato utilizável. Tente de novo."},
                status=status.HTTP_502_BAD_GATEWAY,
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


class DecisaoViewSet(ProjectScopedMixin, QueryParamFilterMixin, ArchiveModelViewSet):
    resource = "decisao"
    queryset = Decisao.objects.select_related("project", "source_meeting").all()
    serializer_class = DecisaoSerializer
    # `status` entra no filtro porque a tela precisa separar rascunho de publicada: o rascunho é
    # interno e a publicada é a que o cliente vê. Sem ele, revisar a extração da IA obrigaria a
    # trazer as duas listas juntas e separá-las no navegador.
    filter_fields = ("project", "status")


class RiscoViewSet(ProjectScopedMixin, QueryParamFilterMixin, ArchiveModelViewSet):
    resource = "risco"
    queryset = Risco.objects.select_related("project", "owner").all()
    serializer_class = RiscoSerializer
    filter_fields = ("project",)
    # `status` vai em `filter_exact_fields` e não em `filter_fields`: aquele só aplica o filtro
    # quando o valor é dígito (é para chave estrangeira), e um `?status=open` cairia no chão sem
    # erro nenhum — a lista voltaria inteira, e a tela mostraria risco encerrado como aberto.
    filter_exact_fields = ("status",)

    def create_kwargs(self) -> dict:
        return {"owner": self.request.user}


class EngineeringHandoffViewSet(ProjectScopedMixin, QueryParamFilterMixin, ArchiveModelViewSet):
    """Handoffs de engenharia: provisionam GitHub Issue a partir do Pulse (FDD 040)."""

    resource = "engineering_handoff"
    queryset = EngineeringHandoff.objects.select_related("project", "source_task").all()
    serializer_class = EngineeringHandoffSerializer
    filter_fields = ("project",)
    filter_exact_fields = ("status",)

    def create(self, request: Request, *args: Any, **kwargs: Any) -> Response:
        if not engineering_provisioning.is_enabled():
            return Response(
                {"detail": "Provisionamento GitHub desativado."},
                status=status.HTTP_503_SERVICE_UNAVAILABLE,
            )
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        pulse_id = str(serializer.validated_data["pulse_work_item_id"])
        existing = EngineeringHandoff.objects.filter(pulse_work_item_id=pulse_id).first()
        if existing is not None:
            self.check_object_permissions(request, existing)
            engineering_provisioning.provision(existing)
            existing.refresh_from_db()
            return Response(self.get_serializer(existing).data)
        try:
            with transaction.atomic():
                self.perform_create(serializer)
        except IntegrityError:
            raced = EngineeringHandoff.objects.get(pulse_work_item_id=pulse_id)
            engineering_provisioning.provision(raced)
            raced.refresh_from_db()
            return Response(self.get_serializer(raced).data)
        handoff = serializer.instance
        engineering_provisioning.provision(handoff)
        handoff.refresh_from_db()
        return Response(self.get_serializer(handoff).data, status=status.HTTP_201_CREATED)

    @extend_schema(request=None, responses={200: EngineeringHandoffSerializer})
    @action(detail=True, methods=["post"], url_path="retry")
    def retry(self, request: Request, pk: str | None = None) -> Response:
        """Reexecuta o provisionamento; no-op se a Issue já existe."""
        if not engineering_provisioning.is_enabled():
            return Response(
                {"detail": "Provisionamento GitHub desativado."},
                status=status.HTTP_503_SERVICE_UNAVAILABLE,
            )
        handoff = self.get_object()
        engineering_provisioning.provision(handoff)
        handoff.refresh_from_db()
        return Response(self.get_serializer(handoff).data)


class GithubDeliveryProjectionViewSet(
    ProjectScopedMixin, QueryParamFilterMixin, ArchiveModelViewSet
):
    """Projeção de entrega GitHub (FDD 041): Issue/PR/CI espelhados no projeto Pulse.

    Direção de leitura, complementar ao provisionamento (FDD 040). O corpo só grava o mapeamento
    (projeto + repo + Issue); o estado de engenharia vem do webhook e da reconciliação, nunca de um
    PATCH — a fronteira da ADR 0046. Escopo de projeto e nega-por-padrão como as irmãs.
    """

    resource = "github_projection"
    queryset = GithubDeliveryProjection.objects.select_related("project", "handoff").all()
    serializer_class = GithubDeliveryProjectionSerializer
    filter_fields = ("project",)
    filter_exact_fields = ("projection_status",)

    def create(self, request: Request, *args: Any, **kwargs: Any) -> Response:
        # Fail-closed como o provisionamento (#40, ADR 0018): sem a integração, mapear uma
        # referência que ninguém vai observar só cria dado morto.
        if not github_delivery.is_enabled():
            return Response(
                {"detail": "Projeção GitHub desativada."},
                status=status.HTTP_503_SERVICE_UNAVAILABLE,
            )
        return super().create(request, *args, **kwargs)

    @extend_schema(request=None, responses={200: GithubDeliveryProjectionSerializer})
    @action(detail=True, methods=["post"], url_path="reconcile")
    def reconcile(self, request: Request, pk: str | None = None) -> Response:
        """Reconciliação por poll: confirma a projeção e recupera eventos perdidos."""
        if not github_delivery.is_enabled():
            return Response(
                {"detail": "Projeção GitHub desativada."},
                status=status.HTTP_503_SERVICE_UNAVAILABLE,
            )
        projection = self.get_object()
        github_delivery.reconcile(projection)
        projection.refresh_from_db()
        return Response(self.get_serializer(projection).data)


class SatisfacaoViewSet(QueryParamFilterMixin, ArchiveModelViewSet):
    """Satisfação do cliente (FDD 037): o sinal que vem da outra parte da relação.

    **Sem `ProjectScopedMixin`**, ao contrário do `RiscoViewSet` logo acima, porque o vínculo
    obrigatório aqui é com o cliente e o projeto é opcional — o mixin recortaria por um campo que
    pode estar vazio e esconderia justamente o cliente que não está mais em entrega, que é onde a
    cobrança dói. O recorte é o do `ActivityViewSet`: a Entrega enxerga o cliente de que participa
    por algum projeto.
    """

    resource = "satisfacao"
    queryset = Satisfacao.objects.select_related(
        "client", "project", "source_meeting", "source_activity", "registered_by"
    ).all()
    serializer_class = SatisfacaoSerializer
    filter_fields = ("client", "project")
    # `nivel` e `fonte` em `filter_exact_fields` e não em `filter_fields` pelo motivo do `status`
    # do `RiscoViewSet`: aquele só aplica o filtro quando o valor é dígito, e `?fonte=declarada`
    # cairia no chão sem erro nenhum — a lista voltaria inteira, com a percebida junto.
    filter_exact_fields = ("nivel", "fonte")

    def get_queryset(self):  # type: ignore[no-untyped-def]
        # Mesma fronteira da `Activity`: a Entrega só enxerga clientes com projeto seu.
        queryset = super().get_queryset()
        scope = project_scope_q(self.request.user, "client__projects")
        return queryset.filter(scope).distinct() if scope else queryset

    def _assert_cliente_no_escopo(self, client: Client | None) -> None:
        """A metade de escrita da mesma fronteira.

        O `ActivityViewSet`, de quem este recorte é copiado, tem só a metade de leitura — e podia:
        para a Entrega, `activity` é só-leitura, então nunca houve escrita a guardar. Aqui a
        Entrega **escreve**, e sem esta guarda uma requisição bastaria para registrar satisfação
        no cliente que a listagem esconde. É o mesmo argumento do `ProjectScopedMixin`, que cobre
        leitura e escrita no mesmo lugar exatamente porque só a leitura é contornável.

        A pergunta sai de `visible_to` (ADR 0010), a única expressão da regra.
        """
        user = self.request.user
        if user.is_admin_role or user.role != User.Role.DELIVERY:
            return
        if client is None or not Project.objects.visible_to(user).filter(client=client).exists():
            raise PermissionDenied("Você não participa de nenhum projeto deste cliente.")

    def perform_create(self, serializer: SatisfacaoSerializer) -> None:
        self._assert_cliente_no_escopo(serializer.validated_data.get("client"))
        serializer.save(registered_by=self.request.user)

    def perform_update(self, serializer: SatisfacaoSerializer) -> None:
        # Só quando o corpo tenta *mudar* o cliente — o caminho inverso, que o
        # `ProjectScopedMixin` também fecha: mover um registro próprio para um cliente alheio.
        if "client" in serializer.validated_data:
            self._assert_cliente_no_escopo(serializer.validated_data.get("client"))
        super().perform_update(serializer)


def _exige_cliente_no_escopo(user: User, client: Client | None) -> None:
    """A metade de **escrita** da fronteira do Discovery estruturado (FDD 039).

    Função e não método porque os três recursos abaixo fazem a mesma pergunta a partir de âncoras
    diferentes (o processo tem o cliente; a etapa e a evidência chegam a ele pelo processo pai), e
    três cópias divergiriam na primeira correção. O argumento é o do `_assert_cliente_no_escopo`
    da `SatisfacaoViewSet`: só a leitura é contornável de graça — sem a guarda de escrita, uma
    requisição bastaria para mapear processo, etapa e evidência dentro do cliente que a listagem
    esconde.

    A pergunta sai de `visible_to` (ADR 0010), a única expressão da regra.
    """
    if user.is_admin_role or user.role != User.Role.DELIVERY:
        return
    if client is None or not Project.objects.visible_to(user).filter(client=client).exists():
        raise PermissionDenied("Você não participa de nenhum projeto deste cliente.")


class ProcessoViewSet(QueryParamFilterMixin, ArchiveModelViewSet):
    """O processo da operação do cliente, mapeado no Discovery (FDD 039).

    **Sem `ProjectScopedMixin`**, pelo motivo da `SatisfacaoViewSet` acima: não há FK de projeto
    aqui, e não há por design — o mapa é da empresa e sobrevive à venda que o descobriu. O recorte
    é o mesmo: a Entrega enxerga o cliente de que participa por algum projeto.
    """

    resource = "processo"
    queryset = Processo.objects.select_related(
        "client", "source_project", "source_meeting", "registered_by"
    ).all()
    serializer_class = ProcessoSerializer
    filter_fields = ("client",)

    def get_queryset(self):  # type: ignore[no-untyped-def]
        queryset = super().get_queryset()
        scope = project_scope_q(self.request.user, "client__projects")
        return queryset.filter(scope).distinct() if scope else queryset

    def perform_create(self, serializer: ProcessoSerializer) -> None:
        _exige_cliente_no_escopo(self.request.user, serializer.validated_data.get("client"))
        serializer.save(registered_by=self.request.user)

    def perform_update(self, serializer: ProcessoSerializer) -> None:
        # Só quando o corpo tenta *mudar* o cliente — o caminho inverso: mover um processo próprio
        # para um cliente alheio seria o atalho para escrever lá dentro.
        if "client" in serializer.validated_data:
            _exige_cliente_no_escopo(self.request.user, serializer.validated_data.get("client"))
        super().perform_update(serializer)

    @extend_schema(
        responses=inline_serializer("ProcessoUnarchived", {"id": serializers.IntegerField()}),
        request=None,
    )
    @action(detail=True, methods=["post"])
    def unarchive(self, request: Request, pk: str | None = None) -> Response:
        """Restaura o processo e o que este arquivamento levou junto (FDD 025, FDD 039).

        Sobrescreve o `unarchive` do `ArchiveModelViewSet` porque aquele escreve `archived_at =
        None` **direto no objeto**, sem passar pelo modelo — e passaria por cima da metade
        simétrica da cascata, devolvendo um processo vazio, com as etapas e as evidências ainda
        escondidas. A resolução pela queryset crua continua sendo a de lá, e pelo mesmo motivo:
        `get_object()` filtra justamente o que se quer restaurar.
        """
        instance = get_object_or_404(self.queryset, pk=pk)
        self.check_object_permissions(request, instance)
        instance.unarchive()
        return Response({"id": instance.pk})


class ProcessoEtapaViewSet(QueryParamFilterMixin, ArchiveModelViewSet):
    """As etapas do processo, descritas pelo P-S-D-T-E-R (FDD 039)."""

    resource = "processo_etapa"
    queryset = ProcessoEtapa.objects.select_related("processo", "processo__client").all()
    serializer_class = ProcessoEtapaSerializer
    filter_fields = ("processo",)

    def get_queryset(self):  # type: ignore[no-untyped-def]
        queryset = super().get_queryset()
        scope = project_scope_q(self.request.user, "processo__client__projects")
        return queryset.filter(scope).distinct() if scope else queryset

    def perform_create(self, serializer: ProcessoEtapaSerializer) -> None:
        # O cliente é resolvido **pelo processo pai**: é dele que a etapa herda a fronteira, e é
        # por ele que ela vazaria se ninguém perguntasse.
        processo = serializer.validated_data.get("processo")
        _exige_cliente_no_escopo(self.request.user, processo.client if processo else None)
        serializer.save()

    def perform_update(self, serializer: ProcessoEtapaSerializer) -> None:
        if "processo" in serializer.validated_data:
            processo = serializer.validated_data.get("processo")
            _exige_cliente_no_escopo(self.request.user, processo.client if processo else None)
        super().perform_update(serializer)


class EvidenciaViewSet(QueryParamFilterMixin, ArchiveModelViewSet):
    """O achado com forma e rótulo (FDD 039) — a distinção entre observado e suposto."""

    resource = "evidencia"
    queryset = Evidencia.objects.select_related(
        "processo", "processo__client", "etapa", "source_meeting", "registered_by"
    ).all()
    serializer_class = EvidenciaSerializer
    filter_fields = ("processo", "etapa")
    # `rotulo` e `forma` em `filter_exact_fields` e não em `filter_fields` pelo motivo do `status`
    # do `RiscoViewSet`: aquele só aplica o filtro quando o valor é dígito, e `?rotulo=fato`
    # cairia no chão sem erro nenhum — a lista voltaria inteira, com hipótese junto de fato, que é
    # exatamente a mistura que esta fatia existe para desfazer.
    filter_exact_fields = ("rotulo", "forma")

    def get_queryset(self):  # type: ignore[no-untyped-def]
        queryset = super().get_queryset()
        scope = project_scope_q(self.request.user, "processo__client__projects")
        return queryset.filter(scope).distinct() if scope else queryset

    def perform_create(self, serializer: EvidenciaSerializer) -> None:
        processo = serializer.validated_data.get("processo")
        _exige_cliente_no_escopo(self.request.user, processo.client if processo else None)
        serializer.save(registered_by=self.request.user)

    def perform_update(self, serializer: EvidenciaSerializer) -> None:
        if "processo" in serializer.validated_data:
            processo = serializer.validated_data.get("processo")
            _exige_cliente_no_escopo(self.request.user, processo.client if processo else None)
        super().perform_update(serializer)


# `outcome` da avaliação → `status` do lead. O mapa é explícito porque as duas escalas existiam
# antes uma da outra: `nurture` cai em "contatado" (o lead segue no radar, sem decisão tomada) e
# não em "qualificado", que afirmaria uma venda que ninguém abriu.
STATUS_POR_OUTCOME = {
    Qualification.Outcome.QUALIFIED: Lead.Status.QUALIFIED,
    Qualification.Outcome.NURTURE: Lead.Status.CONTACTED,
    Qualification.Outcome.DISQUALIFIED: Lead.Status.DISCARDED,
}


class LeadViewSet(ArchiveModelViewSet):
    resource = "lead"
    queryset = (
        Lead.objects.select_related("client", "opportunity")
        .prefetch_related("qualifications")
        .all()
    )
    serializer_class = LeadSerializer

    @extend_schema(
        request=LeadConvertSerializer,
        responses=inline_serializer("LeadConverted", {
            "lead": LeadSerializer(), "qualification": QualificationSerializer(),
        }),
    )
    @action(detail=True, methods=["post"])
    def convert(self, request: Request, pk: str | None = None) -> Response:
        """Registra a **qualificação** do lead e resolve a conta — e não cria mais venda (ADR 0049).

        Até aqui esta ação criava, num ato só, um `Client` **e** uma `Opportunity` no degrau
        gratuito da escada. Uma conversa de qualificação entrava no funil como venda registrada,
        somava no pipeline e podia virar `Project`. A sequência normativa é
        `Lead → Qualification → (qualified) → CommercialOpportunity`, e o passo comercial passou a
        ter porta própria: `POST /qualifications/{id}/open-opportunity/`.

        Some daqui, junto com a `Opportunity`, a busca por `PipelineStage` aberto e pelo `Service`
        de entrada — e os dois 400 que elas produziam. Qualificar um lead não depende mais de o
        pipeline estar configurado.
        """
        lead = self.get_object()
        payload = LeadConvertSerializer(data=request.data)
        payload.is_valid(raise_exception=True)
        dados = payload.validated_data

        if lead.opportunity_id:
            # Lead convertido pelo caminho antigo: a oportunidade dele já existe, e converter de
            # novo criaria uma segunda conta para a mesma empresa. O backfill da 0052 dá a
            # avaliação que faltava a essas linhas.
            return Response({"detail": "Lead já convertido."}, status=status.HTTP_409_CONFLICT)
        if lead.qualifications.filter(
            outcome=Qualification.Outcome.QUALIFIED, archived_at__isnull=True
        ).exists():
            return Response(
                {"detail": "Este lead já foi qualificado — abra a oportunidade pela qualificação."},
                status=status.HTTP_409_CONFLICT,
            )

        if dados["account"] and lead.client_id and dados["account"].pk != lead.client_id:
            # Mover o lead para outra conta deixaria a avaliação anterior apontando para a antiga,
            # e `Qualification.clean()` passaria a recusar qualquer edição naquela linha. Corrigir
            # a conta de um lead é ato próprio, na tela do lead — não efeito de qualificá-lo.
            return Response(
                {"account_id": "Este lead já está vinculado a outra conta."}, status=400
            )

        with transaction.atomic():
            account = dados["account"] or lead.client or self._nova_conta(lead, request.user)
            lead.client = account
            lead.status = STATUS_POR_OUTCOME[dados["outcome"]]
            lead.save(update_fields=["client", "status", "updated_at"])
            qualification = Qualification(
                lead=lead,
                account=account,
                assessor=request.user,
                outcome=dados["outcome"],
                fit=dados["fit"],
                need=dados["need"],
                urgency=dados["urgency"],
                authority=dados["authority"],
                capacity=dados["capacity"],
                evidence=dados["evidence"],
                rationale=dados["rationale"] or lead.message,
                next_step=dados["next_step"],
                nurture_until=dados["nurture_until"],
                # Retrato do que a IA achou **no momento da avaliação**, e nada o copia para
                # `outcome`: a IA é insumo, quem qualifica é o `assessor` (mapa de linguagem §5).
                ai_suggested_outcome="",
                ai_score_snapshot=lead.ai_score,
            )
            try:
                qualification.full_clean()
            except DjangoValidationError as exc:
                raise serializers.ValidationError(exc.message_dict) from exc
            qualification.save()
            # **Nutrir não arquiva.** Quem volta ao radar em `nurture_until` precisa continuar na
            # lista ativa; arquivar aqui esconderia exatamente o lead que a nutrição existe para
            # trazer de volta. Qualificado e desqualificado saem da fila de triagem.
            if dados["outcome"] != Qualification.Outcome.NURTURE:
                lead.archive()  # sai da lista ativa de Leads, preservando o histórico

        lead.refresh_from_db()
        return Response(
            {
                "lead": LeadSerializer(lead).data,
                "qualification": QualificationSerializer(qualification).data,
            },
            status=status.HTTP_201_CREATED,
        )

    def _nova_conta(self, lead: Lead, owner: User) -> Client:
        # A vertical que o CNAE sugere, quando o enriquecimento a trouxe e o admin já cadastrou
        # aquela vertical (FDD 030, FDD 026). Derivada aqui e não gravada no lead: o CNAE é a
        # fonte, e um segundo campo com a mesma verdade diverge no dia em que alguém corrigir só
        # um. Sem CNAE, sem mapa ou sem a vertical cadastrada, o cliente nasce sem setor — que é o
        # estado que a FDD 026 já trata, e não uma lacuna nova.
        vertical = enrichment.infer_vertical(lead.enrichment.get("cnae_code", ""))
        return Client.objects.create(
            name=lead.company or lead.name,
            owner=owner,
            status=Client.Status.PROSPECT,  # vira "ativo" quando a oportunidade é ganha
            vertical=vertical,
        )


class QualificationViewSet(QueryParamFilterMixin, ArchiveModelViewSet):
    """A avaliação que decide se um lead vira venda (ADR 0049, FDD 044).

    Fechada para a Entrega, como `lead`: a qualificação é ato comercial e não atravessa para o
    portal do cliente (mapa de linguagem §3). Quem produz o 403 é o `return False` do
    `RolePermission` — recurso novo nasce fechado.
    """

    resource = "qualification"
    queryset = Qualification.objects.select_related("lead", "account", "assessor").all()
    serializer_class = QualificationSerializer
    filter_fields = ("lead", "account")
    # `outcome` é texto de valores fechados e por isso vai em `filter_exact_fields`: o teste de
    # dígito de `filter_fields` deixaria `?outcome=nurture` cair no chão sem erro, devolvendo a
    # lista inteira — a mistura que este recurso existe para desfazer.
    filter_exact_fields = ("outcome",)

    def perform_create(self, serializer: QualificationSerializer) -> None:
        serializer.save(assessor=serializer.validated_data.get("assessor") or self.request.user)

    @extend_schema(
        request=OpenCommercialOpportunitySerializer, responses=OpportunitySerializer
    )
    @action(detail=True, methods=["post"], url_path="open-opportunity")
    def open_opportunity(self, request: Request, pk: str | None = None) -> Response:
        """Abre a oportunidade comercial a partir de uma avaliação — o único caminho lead→venda.

        É um **ato explícito**, e é essa a diferença para o que existia: antes a venda nascia de
        graça junto com a conta, no mesmo clique que registrava a conversa. Aqui alguém decide
        abrir, e o sistema recusa quando a avaliação não autoriza (invariante 5).
        """
        qualification = self.get_object()
        if qualification.outcome != Qualification.Outcome.QUALIFIED:
            raise StateConflict(
                "Só uma qualificação com resultado Qualificado abre oportunidade comercial."
            )
        if qualification.commercial_opportunities.exists():
            raise StateConflict("Esta qualificação já abriu uma oportunidade comercial.")
        if qualification.account_id is None:
            return Response(
                {"account": "A qualificação precisa de uma conta antes de virar oportunidade."},
                status=400,
            )
        payload = OpenCommercialOpportunitySerializer(data=request.data)
        payload.is_valid(raise_exception=True)
        dados = payload.validated_data

        service = dados["service"]
        if service and service.category == Service.Category.ACQUISITION:
            return Response(
                {"service": "Oferta de aquisição não vira oportunidade comercial — "
                            "escolha um degrau da escada."},
                status=400,
            )
        contato = dados["contact"]
        if contato and contato.client_id != qualification.account_id:
            return Response(
                {"contact": "O contato deve pertencer ao cliente selecionado."}, status=400
            )
        stage = (
            PipelineStage.objects.filter(kind=PipelineStage.Kind.OPEN).order_by("position").first()
        )
        if stage is None:
            return Response({"detail": "Nenhuma etapa aberta configurada."}, status=400)

        with transaction.atomic():
            opportunity = Opportunity.objects.create(
                client_id=qualification.account_id,
                contact=contato,
                title=dados["title"] or qualification.lead.name,
                scope=dados["scope"] or qualification.rationale,
                estimated_value=dados["estimated_value"],
                stage=stage,
                owner=request.user,
                expected_close_date=(
                    dados["expected_close_date"] or timezone.localdate() + timedelta(days=30)
                ),
                service=service,
                origin_qualification=qualification,
            )
            # **`Lead.opportunity` continua sendo ligado aqui**, e não é resíduo do caminho antigo:
            # a análise de origem da FDD 030 atravessa `projeto → oportunidade → lead → source`
            # por esta chave. Movendo a criação da venda para cá sem religar o lead, todo negócio
            # nascido de lead passaria a contar como "Cadastro direto" — uma tela de decisão de
            # investimento errando em silêncio, que é o modo de falha que
            # `tests/regression/test_origem_do_lead_sobrevive_a_conversao.py` existe para pegar.
            # O vínculo canônico da fatia nova é `origin_qualification`; este é o atalho da
            # analítica, e some no dia em que ela souber ler a avaliação no meio do caminho.
            lead = qualification.lead
            if lead.opportunity_id is None:
                lead.opportunity = opportunity
                lead.save(update_fields=["opportunity", "updated_at"])
        return Response(OpportunitySerializer(opportunity).data, status=status.HTTP_201_CREATED)


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
            cnpj=data.get("cnpj", ""),
            message=data.get("message", ""),
            source="site",
        )
        # Antes da qualificação, e é a ordem que faz o enriquecimento valer alguma coisa: ele
        # existe para o `ai_fit` sair melhor informado, e depois seria um cadastro bonito que a
        # decisão já não usou. Não levanta — a falha do fornecedor deixa o lead como estava.
        enrichment.enrich_lead(lead)
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


class PaymentsWebhookView(APIView):
    """Entrada do gateway de pagamento (FDD 028). Autentica pela assinatura do corpo cru.

    Gêmea da `EsignWebhookView`, com duas diferenças que não são estilo:

    - **Loga a recusa.** Com `PAYMENTS_ENABLED=true` e nenhum provedor, o `NullProvider.verify`
      responde `False` para sempre e o endpoint 401 até o Stripe desistir. É o comportamento certo
      e é indiagnosticável sem esta linha.
    - **Teto de requisição cinco vezes maior** (`payments_webhook`), porque um 429 aqui vira
      backoff de dias do lado do fornecedor — e conciliação atrasada é o que faz cobrança
      importunar quem já pagou.
    """

    authentication_classes: list = []
    permission_classes = [AllowAny]
    throttle_classes = [ScopedRateThrottle]
    throttle_scope = "payments_webhook"

    @extend_schema(request=None, responses={200: InvoiceSerializer})
    def post(self, request: Request) -> Response:
        if not payments.is_enabled():
            return Response(
                {"detail": "Gateway de pagamento desativado."},
                status=status.HTTP_503_SERVICE_UNAVAILABLE,
            )
        body = request.body  # o HMAC é sobre os bytes originais, então nada de request.data
        provider = payments.get_provider()
        if not provider.verify(body, request.headers):
            logger.warning("webhook de pagamento com assinatura inválida")
            return Response({"detail": "Assinatura inválida."}, status=status.HTTP_401_UNAUTHORIZED)
        try:
            payload = json.loads(body or b"{}")
        except ValueError:
            return Response({"detail": "Corpo inválido."}, status=status.HTTP_400_BAD_REQUEST)
        if not isinstance(payload, dict):
            return Response({"detail": "Corpo inválido."}, status=status.HTTP_400_BAD_REQUEST)
        event = provider.parse_event(payload)
        invoice = payments.apply_event(event) if event else None
        if invoice is None:
            return Response({"detail": "Evento ignorado."})
        return Response(InvoiceSerializer(invoice).data)


class GithubDeliveryWebhookView(APIView):
    """Entrada dos webhooks de entrega GitHub (FDD 041). Autentica pelo HMAC-SHA256 do corpo cru.

    Idempotente: a reentrega com o mesmo `X-GitHub-Delivery` vira no-op no inbox. Evento de tipo
    desconhecido ou sem projeção correspondente responde 200 "ignorado" — um erro faria o GitHub
    reentregar para sempre, e o Pulse não inventa referência que não mapeou. Zero LLM.
    """

    authentication_classes: list = []
    permission_classes = [AllowAny]
    throttle_classes = [ScopedRateThrottle]
    throttle_scope = "github_webhook"

    @extend_schema(request=None, responses={200: GithubDeliveryProjectionSerializer})
    def post(self, request: Request) -> Response:
        if not github_delivery.is_enabled():
            return Response(
                {"detail": "Projeção GitHub desativada."},
                status=status.HTTP_503_SERVICE_UNAVAILABLE,
            )
        body = request.body  # o HMAC é sobre os bytes originais, então nada de request.data
        if not github_delivery.verify_signature(body, request.headers):
            logger.warning("webhook GitHub de entrega com assinatura inválida")
            return Response({"detail": "Assinatura inválida."}, status=status.HTTP_401_UNAUTHORIZED)
        try:
            payload = json.loads(body or b"{}")
        except ValueError:
            return Response({"detail": "Corpo inválido."}, status=status.HTTP_400_BAD_REQUEST)
        if not isinstance(payload, dict):
            return Response({"detail": "Corpo inválido."}, status=status.HTTP_400_BAD_REQUEST)
        event_type = request.headers.get("X-GitHub-Event", "")
        delivery_id = request.headers.get("X-GitHub-Delivery", "")
        outcome, projection = github_delivery.ingest(event_type, delivery_id, payload)
        if projection is None:
            return Response({"outcome": outcome})
        return Response(
            {"outcome": outcome, "projection": GithubDeliveryProjectionSerializer(projection).data}
        )


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


# A origem de quem chegou sem lead: oportunidade cadastrada à mão, que é um canal como
# qualquer outro e some da conta se não tiver nome. Sem esta linha os totais por origem não
# fecham com `funnel.opportunities.won`, e uma tabela que não reconcilia com a de cima é pior
# que tabela nenhuma — ela ensina a não confiar nas duas.
SEM_LEAD = "direto"


def _lead_source(opportunity_path: str) -> Subquery:
    """O `source` do lead que originou aquele negócio, um por linha.

    Subconsulta e não `join`: `Opportunity.leads` é reverso de FK e aceita mais de uma linha,
    então agrupar pelo join multiplicaria o projeto por lead e a **receita seria somada duas
    vezes**. Aqui a origem é escalar por construção, e o dinheiro não pode dobrar.

    O critério de desempate é o lead mais antigo: quem trouxe o negócio é quem chegou
    primeiro, não quem foi cadastrado por último.
    """
    return Subquery(
        Lead.objects.filter(opportunity=OuterRef(opportunity_path))
        .order_by("created_at")
        .values("source")[:1]
    )


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

        # Conversão por degrau da escada FDE: onde cada nível para no pipeline.
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

        # Origem do negócio, medida até o **fechado** e não até o formulário (FDD 030). O
        # desperdício de demanda mora em canal que gera lead e não gera cliente, e essa
        # pergunta era irrespondível — não por falta de dado, mas por falta de leitor: a
        # travessia `projeto → oportunidade → lead → source` já existe em chaves desde a
        # FDD 013, porque `Lead.opportunity` é FK e `Project.opportunity` é OneToOne.
        #
        # A contagem de entrada é sobre `Lead.objects` **inteiro**, sem o `active` que é o
        # reflexo do resto deste método: `LeadViewSet.convert` chama `lead.archive()`, então
        # filtrar arquivados apagaria da conta exatamente os leads que **fecharam** — a
        # coluna "entraram" ficaria menor que a coluna "ganhas" ao lado dela.
        entered = {
            row["source"]: row["n"]
            for row in Lead.objects.values("source").annotate(n=Count("id"))
        }
        won_by_source = {
            row["origin"]: row["n"]
            for row in opps.filter(stage__kind=PipelineStage.Kind.WON)
            .annotate(origin=Coalesce(_lead_source("pk"), Value(SEM_LEAD)))
            .values("origin")
            .annotate(n=Count("id"))
        }
        closed_by_source = {
            row["origin"]: (row["n"], row["rev"] or Decimal("0"))
            for row in projects.annotate(
                origin=Coalesce(_lead_source("opportunity_id"), Value(SEM_LEAD))
            )
            .values("origin")
            .annotate(n=Count("id"), rev=Sum("actual_value"))
        }
        by_source = sorted(
            (
                {
                    "source": origin,
                    "leads": entered.get(origin, 0),
                    "won": won_by_source.get(origin, 0),
                    "projects": closed_by_source.get(origin, (0, Decimal("0")))[0],
                    "revenue": closed_by_source.get(origin, (0, Decimal("0")))[1],
                }
                for origin in set(entered) | set(won_by_source) | set(closed_by_source)
            ),
            key=lambda row: (-row["won"], -row["leads"], row["source"]),
        )

        return Response({
            "funnel": {
                "leads": {"total": leads.count(), "by_status": leads_by_status},
                "opportunities": {"open": open_count, "won": won, "lost": lost},
                "projects": {"total": projects.count(), "by_status": projects_by_status},
                "by_tier": by_tier,
                "by_stage": by_stage,
                "by_source": by_source,
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
        # Abaixo do piso de similaridade `ground` devolve `None`, nada é injetado, e o agente
        # responde exatamente como respondia antes desta FDD — que é o que mantém "o que está
        # atrasado?" sendo uma pergunta operacional em vez de virar uma lacuna.
        return _ai_run(
            request, f"agent_{key}", agent.system, prompt, grounding=knowledge.ground(question)
        )


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


# Comentário e não docstring, pela mesma razão que vale para os mixins: o drf-spectacular usa a
# docstring da classe como `description` de **todos** os métodos dela, e o raciocínio abaixo é
# interno — vazá-lo para o `openapi.yaml` publica nome de teste no contrato público.
#
# A sessão corrente: lê e edita o **próprio** registro. `IsAuthenticated` e não `RolePermission`,
# como já era no GET, e isso não é afrouxamento: o `resource = "user"` continua fora de toda
# allowlist de `permissions.py`, então `/users/` segue fechado para Vendas e Entrega
# (`test_usuarios_continua_fechado_para_vendas_e_entrega`). O que autoriza aqui não é o papel — é
# o alvo ser sempre `request.user`, que não vem do cliente e por isso não tem como apontar para
# outra pessoa.
class MeView(APIView):
    permission_classes = [IsAuthenticated]

    @extend_schema(responses=UserSerializer)

    def get(self, request: Request) -> Response:
        return Response(UserSerializer(request.user).data)

    @extend_schema(
        summary="Edita o nome do usuário da sessão.",
        request=ProfileSerializer,
        responses=UserSerializer,
    )
    def patch(self, request: Request) -> Response:
        # `ProfileSerializer` e **não** `UserSerializer`: aquele tem `role` gravável, e usá-lo
        # aqui transformaria este PATCH em caminho de auto-promoção a admin. Ver o docstring do
        # serializer e `test_entrega_mandando_role_admin_nao_vira_admin`.
        serializer = ProfileSerializer(request.user, data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        serializer.save()
        return Response(UserSerializer(request.user).data)


# Envio e remoção da **própria** foto. Não há rota para a foto de outra pessoa. Comentário e não
# docstring: ver `MeView` acima.
class MeAvatarView(APIView):
    permission_classes = [IsAuthenticated]
    parser_classes = [MultiPartParser, FormParser]

    @extend_schema(
        summary="Envia a foto do usuário da sessão. JPG, PNG ou WebP, até 2 MB.",
        request=ProfileAvatarSerializer,
        responses=UserSerializer,
    )
    def put(self, request: Request) -> Response:
        user = cast(User, request.user)
        serializer = ProfileAvatarSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        # Apagar **depois** de gravar, e não antes: se a escrita falhasse no meio, apagar primeiro
        # deixaria a pessoa sem a foto antiga e com uma linha apontando para um arquivo que já não
        # existe. Só se apaga o que nenhuma linha referencia mais.
        anterior = _avatar_reference(user)
        user.avatar = serializer.validated_data["avatar"]
        user.avatar_updated_at = timezone.now()
        user.save(update_fields=["avatar", "avatar_updated_at"])
        _discard_avatar_file(anterior)
        return Response(UserSerializer(user).data)

    @extend_schema(
        summary="Remove a foto do usuário da sessão.", request=None, responses=UserSerializer,
    )
    def delete(self, request: Request) -> Response:
        user = cast(User, request.user)
        anterior = _avatar_reference(user)
        user.avatar = ""
        user.avatar_updated_at = None
        user.save(update_fields=["avatar", "avatar_updated_at"])
        _discard_avatar_file(anterior)
        return Response(UserSerializer(user).data)


def _avatar_reference(user: User) -> tuple[Storage, str] | None:
    """O storage e o caminho da foto atual, capturados antes de o campo ser sobrescrito."""
    return (user.avatar.storage, user.avatar.name) if user.avatar else None


def _discard_avatar_file(anterior: tuple[Storage, str] | None) -> None:
    """Apaga do storage a foto que nenhuma linha referencia mais.

    Sem isto cada troca de foto deixa um objeto órfão no bucket, que ninguém referencia e
    ninguém apaga. Best-effort de propósito: um storage indisponível não pode fazer a pessoa
    falhar em trocar a própria foto — o órfão fica no log em vez de sumir calado.
    """
    if anterior is None:
        return
    storage, caminho = anterior
    try:
        storage.delete(caminho)
    except Exception:  # noqa: BLE001 — limpeza best-effort; ver docstring
        logger.warning("não foi possível apagar a foto anterior %s", caminho)


# Troca da própria senha. Comentário e não docstring: ver `MeView` acima.
class MePasswordView(APIView):
    permission_classes = [IsAuthenticated]
    throttle_classes = [ScopedRateThrottle]
    # Mesmo motivo do teto do login: aqui também se acerta ou erra uma senha, e o teto genérico
    # de `user` (2000/hora) não é teto nenhum para adivinhação. Quem tem a sessão mas não a senha
    # — cookie vazado, estação destravada — é exatamente quem esta porta precisa segurar.
    throttle_scope = "password_change"

    @extend_schema(
        summary="Troca a senha do usuário da sessão, conferindo a senha atual.",
        request=ChangePasswordSerializer,
        responses={204: None},
    )
    def post(self, request: Request) -> Response:
        user = cast(User, request.user)
        serializer = ChangePasswordSerializer(data=request.data, context={"user": user})
        serializer.is_valid(raise_exception=True)
        user.set_password(serializer.validated_data["new_password"])
        user.save(update_fields=["password"])
        # O Django deriva o hash de sessão da senha: trocá-la **invalida todas as sessões,
        # inclusive esta**, e sem esta linha a pessoa trocaria a própria senha e cairia no login.
        # `update_session_auth_hash` recarimba só a sessão corrente. As **outras** caírem é o
        # comportamento seguro e está aceito (DAP perfil-e-contato r1) — não é defeito, e "consertá-lo"
        # removendo esta linha derruba quem acabou de trocar a senha.
        update_session_auth_hash(request, user)
        return Response(status=status.HTTP_204_NO_CONTENT)


# A única porta da foto, e ela passa por sessão e RBAC. Comentário e não docstring: ver `MeView`.
#
# É o mesmo desenho de `DocumentViewSet.download` e pela mesma razão: nenhum ambiente serve
# `MEDIA_ROOT` (ADR 0002, FDD 017), então mídia privada sai por rota autenticada. Servir `/media/`
# para o avatar abriria a exceção que aquela decisão existe para não ter.
#
# `IsAuthenticated` e não `RolePermission`: o recurso `user` está fechado para Vendas e Entrega, e
# passar por ele faria a pessoa não conseguir ver a **própria** foto no topbar. O corte é o alvo,
# não o papel — cada um alcança a sua, e o admin alcança as demais porque `/users/` já lhe entrega
# a lista inteira. Fora disso é 404 e não 403: quem não alcança a foto também não precisa aprender
# que o usuário existe.
#
# `ETag`/`Last-Modified` não são otimização: o topbar pede esta rota uma vez por tela, e sem
# revalidação condicional cada navegação baixaria a imagem inteira de novo.
class UserAvatarView(APIView):
    permission_classes = [IsAuthenticated]

    @extend_schema(
        summary="A foto de perfil, atrás de sessão. Cada um alcança a sua; o admin, todas.",
        responses={(200, "image/*"): OpenApiTypes.BINARY, 304: None, 404: None},
    )
    def get(self, request: Request, pk: int) -> HttpResponseBase:
        if pk != request.user.pk and not request.user.is_admin_role:
            raise Http404
        user = get_object_or_404(User, pk=pk)
        if not user.avatar:
            raise Http404
        etag = f'"{hashlib.sha256(user.avatar.name.encode()).hexdigest()[:32]}"'
        if request.headers.get("If-None-Match") == etag:
            return _avatar_headers(HttpResponseNotModified(), user, etag)
        extension = os.path.splitext(user.avatar.name)[1].lower()
        response = FileResponse(
            user.avatar.open("rb"),
            # O tipo sai do **nosso** mapa, nunca do `Content-Type` que o navegador declarou no
            # upload — aquele é entrada do usuário como qualquer outra.
            content_type=AVATAR_CONTENT_TYPES.get(extension, "application/octet-stream"),
        )
        return _avatar_headers(response, user, etag)


def _avatar_headers(response: HttpResponseBase, user: User, etag: str) -> HttpResponseBase:
    response["ETag"] = etag
    if user.avatar_updated_at is not None:
        response["Last-Modified"] = http_date(user.avatar_updated_at.timestamp())
    # `private`: é foto de pessoa atrás de sessão, e um proxy compartilhado não pode guardá-la.
    response["Cache-Control"] = "private, max-age=0, must-revalidate"
    # A segunda tranca do upload: mesmo que um arquivo passasse pela conferência de assinatura,
    # o navegador não pode reinterpretá-lo como HTML na origem do portal.
    response["X-Content-Type-Options"] = "nosniff"
    return response


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
