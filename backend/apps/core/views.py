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
from decimal import Decimal
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
    discovery_booking,
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
    prove,
    publication,
    qualification,
    recommendations,
    risk,
    tasksync,
)
from .dinheiro import dinheiro
from .exceptions import (
    AiProviderUnavailable,
    CalendarProviderUnavailable,
    DriveUnavailable,
    EmailUndeliverable,
    EsignUnavailable,
    InvalidInput,
    PaymentsUnavailable,
    StateConflict,
)
from .models import (
    KPI,
    Account,
    Activity,
    AiInteraction,
    AppSetting,
    Artifact,
    BlueprintVariant,
    Case,
    CobrancaSuspensao,
    CommercialOpportunity,
    Contact,
    Decisao,
    DigitalEmployee,
    DigitalEmployeeBlueprint,
    Discovery,
    DiscoverySession,
    Document,
    DunningContact,
    Engagement,
    EngineeringHandoff,
    Evidence,
    FeasibilityAssessment,
    Finding,
    GithubDeliveryProjection,
    ImprovementOpportunity,
    Invitation,
    Invoice,
    JourneyPhase,
    KnowledgeArea,
    KnowledgePiece,
    Lead,
    Measurement,
    Meeting,
    Milestone,
    Notification,
    PainPoint,
    Pendencia,
    PhaseChecklistItem,
    PhaseDeliverable,
    PhaseEvent,
    PipelineStage,
    PriorityAssessment,
    Process,
    ProcessObservation,
    ProcessStep,
    Project,
    ProjectChecklistItem,
    ProjectDeliverable,
    ProjectMember,
    ProjectPhase,
    ProveExperiment,
    Qualification,
    Risco,
    SatisfactionRecord,
    Service,
    SignatureRequest,
    SolutionHypothesis,
    Task,
    User,
    ValueLedgerEntry,
    Vertical,
    project_scope_q,
)
from .openapi_aliases import chave_da_geracao
from .permissions import RolePermission
from .serializers import (
    AVATAR_CONTENT_TYPES,
    AcceptInvitationSerializer,
    AccountSerializer,
    ActivitySerializer,
    ArtifactSerializer,
    BlueprintVariantSerializer,
    BookingCreateSerializer,
    CaseSerializer,
    ChangePasswordSerializer,
    CobrancaSuspensaoSerializer,
    CommercialOpportunitySerializer,
    ContactSerializer,
    DecisaoSerializer,
    DigitalEmployeeBlueprintSerializer,
    DigitalEmployeeSerializer,
    DiscoverySerializer,
    DiscoverySessionSerializer,
    DocumentSerializer,
    DunningContactSerializer,
    EngagementSerializer,
    EngineeringHandoffSerializer,
    EvidenceSerializer,
    FeasibilityAssessmentSerializer,
    FindingSerializer,
    GithubDeliveryProjectionSerializer,
    ImprovementOpportunitySerializer,
    InvitationSerializer,
    InvoiceSerializer,
    JourneyPhaseSerializer,
    KnowledgeAreaSerializer,
    KnowledgePieceSerializer,
    KPISerializer,
    LeadConvertSerializer,
    LeadIntakeSerializer,
    LeadSerializer,
    LinkExternalSerializer,
    LoginSerializer,
    MeasurementSerializer,
    MeetingSerializer,
    MilestoneSerializer,
    NotificationSerializer,
    OpenCommercialOpportunitySerializer,
    PainPointSerializer,
    PendenciaSerializer,
    PhaseChecklistItemSerializer,
    PhaseDeliverableSerializer,
    PhaseEventSerializer,
    PipelineStageSerializer,
    PriorityAssessmentSerializer,
    ProcessObservationSerializer,
    ProcessSerializer,
    ProcessStepSerializer,
    ProfileAvatarSerializer,
    ProfileSerializer,
    ProjectChecklistItemSerializer,
    ProjectDeliverableSerializer,
    ProjectMemberSerializer,
    ProjectPhaseSerializer,
    ProjectSerializer,
    ProveExperimentSerializer,
    QualificationSerializer,
    RiscoSerializer,
    SatisfactionRecordSerializer,
    ServiceSerializer,
    SignatureRequestSerializer,
    SolutionHypothesisSerializer,
    TaskSerializer,
    TaskSyncSerializer,
    UserSerializer,
    ValueLedgerEntrySerializer,
    VerticalSerializer,
)
from .versioning import (
    V2,
    frase_da_chave_removida,
    frase_do_parametro_removido,
    frase_do_valor_removido,
    versao_de,
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


# As duas actions da marca de publicável, para os cinco recursos do Discovery (FDD 051, ADR 0060).
#
# **Uma action, e não um `PATCH` de `published_at`**, pela razão exata de `journey.apply_gate` e de
# `POST /prove-experiments/{id}/start/`: o que vale depende do estado corrente — qual sustentação
# está publicada e viva agora —, e só quem conhece esse estado pode fazer a pergunta. Por isso os
# dois campos são só de leitura nos serializers.
#
# **Nenhuma regra nova de papel.** Os cinco `resource` já estão nos conjuntos de Vendas e de
# Entrega em `permissions.py`, e o corte por objeto (a conta no escopo) já existe nos viewsets: a
# action é um `POST` no recurso e passa pelo que já está lá.
#
# Um mixin, e não dez corpos quase iguais: a regra vive em `publication.py` e as duas portas que
# a consultam vivem aqui. O `perform_destroy` de cada viewset chama `recusa_se_sustenta_publicado`
# antes da guarda que já tinha — arquivar e despublicar desfazem a mesma sustentação.
#
# Sem docstring de propósito: o drf-spectacular usa o docstring da classe como `description` de
# cada endpoint, e um mixin no topo da MRO vaza o próprio texto para dezenas de rotas alheias.
class PublicationMixin:
    @extend_schema(request=None)
    @action(detail=True, methods=["post"])
    def publish(self, request: Request, pk: str | None = None) -> Response:
        """Publica o registro, conferindo a sustentação publicada por baixo dele (FDD 051).

        Duas recusas, com o status que cada uma merece:

        - **409** se já está publicado: o pedido está bem formado, o que impede é o estado;
        - **400** listando **o que falta** de sustentação publicada. É o pedido de *publicar
          agora* que está errado — a mesma escolha de `apply_gate` e de `start/`.

        Sucesso carimba `published_at` e `published_by` e devolve o objeto serializado.
        `published_by` é quem está autenticado, e não um id do corpo: é a pessoa que leu, e é ela
        que faz a marca valer como a revisão humana da regra 1 da §3 do `language-map`.
        """
        obj = self.get_object()  # type: ignore[attr-defined]
        if obj.published_at is not None:
            raise StateConflict("Este registro já está publicado para o cliente.")
        faltas = publication.o_que_falta_para_publicar(obj)
        if faltas:
            raise InvalidInput(
                f"Publicar exige {publication.frase_do_que_falta(faltas)}. O que o cliente vê "
                "precisa ter sustentação publicada embaixo."
            )
        obj.published_at = timezone.now()
        obj.published_by = request.user
        obj.save(update_fields=["published_at", "published_by", "updated_at"])
        return Response(self.get_serializer(obj).data)  # type: ignore[attr-defined]

    @extend_schema(request=None)
    @action(detail=True, methods=["post"])
    def unpublish(self, request: Request, pk: str | None = None) -> Response:
        """Retira o registro da projeção do cliente — e recusa quando ele sustenta algo publicado.

        **É esta metade que sempre vaza.** Publicar confere a cadeia no instante em que o item
        sobe; despublicar é o caminho por onde ela se desfaz depois, item a item, sem nada ficar
        vermelho. 409 quando este é a última sustentação publicada e viva de algo publicado, com a
        mensagem dizendo qual estado impede e como sair dele — despublique o de cima primeiro.

        Recusar, e nunca despublicar o de cima em silêncio: é o argumento das guardas de
        arquivamento da FDD 045 e da FDD 048, e desfazer sozinho uma decisão que uma pessoa tomou
        é pior que a recusa explícita.
        """
        obj = self.get_object()  # type: ignore[attr-defined]
        if obj.published_at is None:
            raise StateConflict("Este registro não está publicado.")
        presos = publication.dependentes_publicados_de(obj)
        if presos:
            raise StateConflict(publication.frase_do_impedimento(obj, presos))
        obj.published_at = None
        obj.published_by = None
        obj.save(update_fields=["published_at", "published_by", "updated_at"])
        return Response(self.get_serializer(obj).data)  # type: ignore[attr-defined]

    def recusa_se_sustenta_publicado(self, instance) -> None:  # type: ignore[no-untyped-def]
        """A porta do `DELETE` da mesma invariante: arquivar some da projeção como despublicar.

        Chamada **em cima** das guardas que cada viewset já tem, e não no lugar delas: aquelas
        olham a dimensão do `fact`/`confirmed`, esta olha a da publicação, e as duas podem impedir
        o mesmo arquivamento por motivos diferentes.
        """
        presos = publication.dependentes_publicados_de(instance)
        if presos:
            raise StateConflict(publication.frase_do_impedimento(instance, presos))


# Filtra a lista por chaves estrangeiras informadas em query params (ex.: ?project=1).
# `filter_exact_fields` faz o mesmo para campos de texto com valores fechados (ex.: ?kind=proposal),
# que não passam pelo teste de dígito das chaves estrangeiras.
# Comentário, e não docstring, pelo mesmo motivo do `ProjectScopedMixin` acima.
class QueryParamFilterMixin:

    filter_fields: tuple[str, ...] = ()
    filter_exact_fields: tuple[str, ...] = ()
    # Campo canônico → nome antigo do query param. A issue #67 renomeou o campo e a
    # `docs/ontology/aliases.md` §2c mantém o nome antigo na `/api/v1/`: `?opportunity=`
    # continua filtrando igual a `?commercial_opportunity=`, e `?client=` igual a `?account=`.
    # Sem isto o param antigo não
    # ficaria "sem efeito" — ele estouraria `FieldError`, porque o nome do param **é** o
    # caminho do ORM aqui. A canônica vence quando as duas vêm, como no corpo.
    #
    # Na `/api/v2/` (issue #122) o param legado é **recusado com 400** dizendo o canônico, pela
    # razão exata da chave de corpo: aceito e ignorado, `?client=3` devolveria 200 com a lista
    # inteira, e quem chamou leria isso como "este cliente tem tudo isso" em vez de "o filtro não
    # existe". 400 e não 409 porque é o **pedido** que está errado, não o estado.
    #
    # **O mapa vale para os dois laços desde a fatia 5.4 da issue #122**, e a segunda metade nasceu
    # de um renome de campo de texto: `CobrancaContato.degrau` virou `DunningContact.dunning_step`,
    # e sem o alias `?degrau=lembrete` deixaria de filtrar **em silêncio** na v1 — o nome do param
    # também **é** o caminho do ORM em `filter_exact_fields`. Era o pior caso possível aqui: nem
    # `FieldError`, nem 400, só a lista inteira voltando como se ninguém tivesse filtrado.
    filter_field_aliases: dict[str, str] = {}
    # Campo → {valor legado → valor canônico}, para `filter_exact_fields` cujo VALOR (não o nome
    # do parâmetro) tem alias — a área do blueprint (issue #122, fatia 5.1) é a primeira. Na
    # `/api/v1/` o valor legado continua filtrando, traduzido pelo mesmo mapa que o mixin de
    # serializer usa para o corpo; na `/api/v2/` ele é **recusado**, e não silenciosamente ignorado:
    # `?area=comercial` sem tradução casaria zero linhas, e uma lista vazia é o mesmo silêncio
    # mentiroso que a decisão 3 da ADR 0066 recusa para chave e parâmetro. Diferente daquela decisão
    # (chave de payload/parâmetro, sempre 400 na v2), aqui o valor canônico já filtra igual nas duas
    # versões — só o valor legado precisa de tratamento, e só quando o campo está neste mapa.
    filter_valores_legados: dict[str, dict[str, str]] = {}

    def get_queryset(self):  # type: ignore[no-untyped-def]
        queryset = super().get_queryset()  # type: ignore[misc]
        na_v2 = versao_de(self.request) == V2  # type: ignore[attr-defined]
        for field in self.filter_fields:
            value = self.request.query_params.get(field)  # type: ignore[attr-defined]
            legado = self.filter_field_aliases.get(field)
            if legado and legado in self.request.query_params:  # type: ignore[attr-defined]
                if na_v2:
                    raise InvalidInput(frase_do_parametro_removido(legado, field))
                if not value:
                    value = self.request.query_params.get(legado)  # type: ignore[attr-defined]
            if value and value.isdigit():
                queryset = queryset.filter(**{field: value})
        for field in self.filter_exact_fields:
            value = self.request.query_params.get(field)  # type: ignore[attr-defined]
            legado = self.filter_field_aliases.get(field)
            if legado and legado in self.request.query_params:  # type: ignore[attr-defined]
                # O mesmo tratamento do laço acima, e de propósito na mesma forma: a v1 aceita o
                # nome antigo do parâmetro, a canônica vence quando as duas vêm, e a v2 recusa
                # dizendo qual usar.
                if na_v2:
                    raise InvalidInput(frase_do_parametro_removido(legado, field))
                if not value:
                    value = self.request.query_params.get(legado)  # type: ignore[attr-defined]
            if value:
                valores_legados = self.filter_valores_legados.get(field)
                canonico = valores_legados.get(value) if valores_legados else None
                if canonico is not None:
                    if na_v2:
                        raise InvalidInput(frase_do_valor_removido(field, value, canonico))
                    value = canonico
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
#: (`docs/metodologia-fde.md:106-110`). Tupla e não literal repetido no parser e no prompt: a ordem
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
#: (`docs/metodologia-fde.md:112-115`) e não prova. Por isso as duas chaves são atribuídas como
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
    um achado pertence, e vínculo errado é pior que vínculo nenhum — `Finding.step` é opcional
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
            # 255 porque `Process.name` e `ProcessStep.name` são `CharField(max_length=255)`, e
            # o modelo não tem como saber disso: um nome de 4.000 caracteres viraria `DataError` no
            # meio da gravação, derrubando o mapa inteiro por um item.
            "name": nome[:255],
            "etapas": _etapas_do_bruto(item.get("etapas")),
            "achados": _achados_do_bruto(item.get("achados")),
        })
    return extraidos


# Tolerância de release (issue #122, fatia 5.2): o prompt de `classificar` passou a pedir os três
# tokens canônicos ingleses diretamente — pedir em português e traduzir depois deixaria no prompt
# a aparência de que o modelo decide o idioma, o mesmo argumento da FDD 039. Mas a IA pode ter
# cache ou variação e devolver o token antigo; um mapa de três entradas evita descartar uma
# resposta que ainda soa certa. Vale só aqui — a v2 não traduz nem recusa valor (§2c/D10).
_SINAIS_LEGADOS: dict[str, str] = {
    "esqueceu": Activity.DunningSignal.FORGOT,
    "nao_pode": Activity.DunningSignal.UNABLE_TO_PAY,
    "insatisfeito": Activity.DunningSignal.DISSATISFIED,
}


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
    sinal = _SINAIS_LEGADOS.get(sinal, sinal)
    return sinal if sinal in Activity.DunningSignal.values else ""


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
        user=request.user, feature=feature, project=project,
        commercial_opportunity=opportunity,
        prompt_tokens=usage.get("prompt_tokens", 0), completion_tokens=usage.get("completion_tokens", 0),
        sources=sources,
    )
    payload: dict[str, object] = {"text": text, "interaction": interaction.id}
    if grounding is not None:
        payload["sources"] = sources
    if artifact_kind is not None:
        artifact = Artifact.objects.create(
            kind=artifact_kind, title=artifact_title, content=text,
            commercial_opportunity=opportunity, project=project,
            source_meeting=source_meeting,
            ai_interaction=interaction, created_by=request.user,
        )
        payload["artifact"] = ArtifactSerializer(artifact).data
    if coletor is not None:
        payload.update(coletor(text, interaction))
    return Response(payload)


@dataclass(frozen=True)
class OverviewContext:
    """Tudo o que `build_account_overview` precisa do banco, carregado em lote.

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


def _sem_chaves_legadas(
    linhas: list[dict[str, Any]], *chaves: str
) -> list[dict[str, Any]]:
    """Tira as chaves-alias de cada linha de um agregador de **dict cru**, na `/api/v2/`.

    Nasceu no painel de cobrança (issue #122, fatia 3a) e ganhou o segundo chamador na fatia 4a (a
    visão compacta da entrega), então deixou de nomear um deles: a lista de chaves é do chamador,
    porque é ele que sabe qual é o par legado do seu dicionário. A fatia 4c acrescentou o terceiro
    e o quarto chamador — `AccountViewSet.overview`/`overview_detail`, para `client_id`/`status`.

    Um dict cru não passa por `ModelSerializer` nenhum, e é por isso que a remoção mora aqui em vez
    de em `AliasesDaV1Mixin`: aquele mixin lê `ALIASES_DEPRECIADOS` por **componente do schema**,
    e um dicionário montado à mão não tem serializer que resolva para um. O contrato, esse sim,
    perde as chaves pelo mesmo mapa dos outros — `ALIASES_DEPRECIADOS_DE_DICT_CRU`, a metade da
    união que os hooks do drf-spectacular leem (`apps/core/openapi_aliases.py`). O par `client_id`/
    `status` do overview de conta entrou nesse mapa quando `AccountOverviewList`/
    `AccountOverviewDetail` ganharam item tipado — antes disso o esquema não via as duas chaves, e
    a remoção aqui era dívida de resposta, não de contrato (a lacuna que a ADR 0066, emenda da
    fatia 4a, declarou por escrito — fechada fora da série de fatias da issue #122, que já havia
    encerrado).
    """
    for linha in linhas:
        for chave in chaves:
            linha.pop(chave, None)
    return linhas


# As cinco sub-formas de uma linha do overview de conta, cada uma classe de verdade (não
# `inline_serializer`): `_account_overview_row_fields()` é chamada duas vezes — uma para o item da
# lista, outra para o detalhe — e `inline_serializer` cria uma classe nova a cada chamada
# (`type(name, (Serializer,), fields)`); duas classes de nomes iguais e identidades diferentes é
# exatamente o que o drf-spectacular avisa como schema "muito provavelmente incorreto". Uma classe
# módulo-level nascida uma vez, instanciada de novo em cada chamada, não tem esse problema — é
# instância que se vincula ao serializer pai, a classe é a mesma nos dois lugares.
class AccountOverviewRoiSerializer(serializers.Serializer):
    # `DecimalField` sem `coerce_to_string=False`: dinheiro trafega como **texto** (ADR 0068), e
    # quem converte o valor é `dinheiro.dinheiro` em `build_account_overview` — o esquema declara,
    # a view converte, e as duas metades precisam concordar. Esta declaração já dizia `string`
    # antes da ADR 0068; era o corpo que discordava dela.
    revenue = serializers.DecimalField(max_digits=14, decimal_places=2)
    cost = serializers.DecimalField(max_digits=14, decimal_places=2)
    # `roi` é razão, não dinheiro: nasce de uma divisão, não tem centavo a perder e fica `float`.
    roi = serializers.FloatField(allow_null=True)


class AccountOverviewHealthSerializer(serializers.Serializer):
    score = serializers.IntegerField()
    level = serializers.CharField()
    project_id = serializers.IntegerField()


class AccountOverviewPhaseSerializer(serializers.Serializer):
    name = serializers.CharField()
    # `CharField`, não `ChoiceField(choices=ProjectPhase.Status.choices)`: o valor só pode ser
    # "active" de qualquer forma (`build_overview_context` só carrega a fase `ACTIVE`), e reusar o
    # enum aqui — numa linha de agregação, não no recurso `ProjectPhase` — fez o drf-spectacular
    # tropeçar em "status" de vários componentes e gerar nomes de enum em hash
    # (`Status31cEnum`/`StatusC64Enum`) que não existiam antes desta mudança.
    status = serializers.CharField()


class AccountOverviewNextMeetingSerializer(serializers.Serializer):
    title = serializers.CharField()
    date = serializers.DateField()


class AccountOverviewAiScoreSerializer(serializers.Serializer):
    maturity = serializers.IntegerField(allow_null=True)
    opportunity = serializers.IntegerField(allow_null=True)
    dimensions = serializers.JSONField()
    summary = serializers.CharField()
    scored_at = serializers.DateTimeField()


def _account_overview_row_fields() -> dict[str, Any]:
    """Os campos de uma linha do overview de conta — o que `build_account_overview` de fato monta.

    Existia como `serializers.ListField()` sem `child=`: o esquema não descrevia nenhuma chave da
    linha, então `ALIASES_DEPRECIADOS`/`ALIASES_DEPRECIADOS_DE_DICT_CRU` não tinham o que indexar
    ali e `client_id`/`status` sobreviveram invisíveis até a fatia 4c (ADR 0066). Extraída para
    função porque `AccountOverviewList` (a lista) e `AccountOverviewDetail` (uma linha sozinha)
    descrevem o **mesmo** dicionário — duas declarações lado a lado divergiriam no dia em que
    `build_account_overview` ganhasse um campo. Cada chamador pede a sua própria chamada (nunca
    reaproveita o dicionário devolvido): campo de serializer só se vincula a um serializer, e
    reusar a mesma instância nos dois lugares quebraria o segundo bind.
    """
    return {
        # `client_id`/`status` são os legados (`docs/ontology/aliases.md` §2c): saem na v1
        # marcados `deprecated` (via `ALIASES_DEPRECIADOS_DE_DICT_CRU`) e somem na v2 por
        # `_sem_chaves_legadas`. `account_id`/`lifecycle_status` são as canônicas, mesmo valor.
        # `CharField`, não `ChoiceField`: ver o comentário do `status` de `AccountOverviewPhaseSerializer`
        # sobre o ruído de nomeação de enum que reusar `Account.LifecycleStatus.choices` aqui gerava.
        "client_id": serializers.IntegerField(),
        "account_id": serializers.IntegerField(),
        "name": serializers.CharField(),
        "status": serializers.CharField(),
        "lifecycle_status": serializers.CharField(),
        "roi": AccountOverviewRoiSerializer(),
        # As quatro abaixo saem `None` quando o cliente não tem projeto ativo —
        # `build_account_overview` devolve cedo nesse caso, sem tocar em nenhuma delas.
        "health": AccountOverviewHealthSerializer(required=False, allow_null=True),
        "risk_level": serializers.CharField(required=False, allow_null=True),
        "phase": AccountOverviewPhaseSerializer(required=False, allow_null=True),
        "next_meeting": AccountOverviewNextMeetingSerializer(required=False, allow_null=True),
        "ai_score": AccountOverviewAiScoreSerializer(required=False, allow_null=True),
    }


def build_account_overview(
    account: Account,
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
        projects = Project.objects.filter(engagement__account=account, archived_at__isnull=True)
    projects = list(projects)
    if context is None:
        context = build_overview_context(projects)
    active = [project for project in projects if project.status != Project.Status.COMPLETED]
    revenue = sum((project.actual_value for project in projects), Decimal("0"))
    cost = sum((project.cost for project in projects), Decimal("0"))
    overview: dict[str, object] = {
        # `client_id` e `status` são **chaves de payload** e não mudam com o renome do campo
        # (`docs/ontology/aliases.md` §2c); `account_id`/`lifecycle_status` são as canônicas, com
        # o mesmo valor. As duas legadas morrem na `/api/v2/` — a lacuna que a ADR 0066 (emenda da
        # fatia 4a) declarou fora daquela fatia por não haver schema tipado para o mapa de aliases
        # alcançar, e que a fatia 4c paga aqui, à mão, via `_sem_chaves_legadas`.
        "client_id": account.pk,
        "account_id": account.pk,
        "name": account.name,
        "status": account.lifecycle_status,
        "lifecycle_status": account.lifecycle_status,
        # Texto, e não `Decimal` cru: este dicionário vai direto ao renderizador, que
        # transformaria `Decimal("40000.00")` em `40000.0` — o esquema já prometia `string` aqui
        # (`AccountOverviewRoiSerializer`) e era o corpo que mentia (ADR 0068).
        "roi": {"revenue": dinheiro(revenue), "cost": dinheiro(cost), "roi": _roi(revenue, cost)},
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


class AccountViewSet(ArchiveModelViewSet):
    resource = "account"
    queryset = Account.objects.all()
    serializer_class = AccountSerializer

    def perform_create(self, serializer: AccountSerializer) -> None:
        serializer.save(owner=self.request.user)

    def get_queryset(self):  # type: ignore[no-untyped-def]
        queryset = super().get_queryset()
        # `?lifecycle_status=` é o canônico e `?status=` é o alias que a `/api/v1/` promete
        # (`docs/ontology/aliases.md` §2c) — a canônica vence quando as duas vêm, como no corpo.
        # A validação é contra os **três** valores: `inactive` é conta viva e não filtro de
        # arquivo, então ela precisa ser selecionável como as outras duas.
        status_param = self.request.query_params.get(
            "lifecycle_status"
        ) or self.request.query_params.get("status")
        if status_param in set(Account.LifecycleStatus.values):
            queryset = queryset.filter(lifecycle_status=status_param)
        # Entrega só conhece o cliente para quem trabalha (RFC 0003). Desde a Fase 6, `Account` não
        # tem mais o reverso `projects` (era o related_name de `Project.client`, removido); o
        # caminho canônico até o projeto passa pelo mandato: `engagements__projects`.
        scope = project_scope_q(self.request.user, "engagements__projects")
        queryset = queryset.filter(scope).distinct() if scope else queryset
        # `published_count` (issue `#114`): quanto do Discovery desta conta o cliente está vendo,
        # para a confirmação de arquivar poder avisar. Vem por subconsulta correlacionada e não
        # por `Count` com `JOIN` — cinco joins multiplicariam as linhas entre si, e o `.distinct()`
        # acima esconderia o número errado em vez de corrigi-lo. Anotado **depois** do escopo
        # porque o recorte é da conta, não do leitor: dois usuários veem o mesmo número.
        #
        # **Só onde o serializer lê.** `get_queryset` aqui serve também ao `/clients/overview/`,
        # que monta dicionário próprio e nunca toca em `AccountSerializer`: anotar sempre faria o
        # grid de contas — a tela mais carregada do produto — rodar cinco `COUNT` correlacionados
        # por linha que ninguém lê. A contagem de *queries* não mudaria (por isso o orçamento de
        # `test_aggregate_query_budget` passa dos dois jeitos), e é exatamente o que torna esse
        # desperdício invisível: ele cresce com a carteira sem nada ficar vermelho. As demais
        # ações caem no `getattr(obj, "published_count", None)` do serializer, que conta o objeto
        # na mão — cinco `COUNT` sobre **uma** linha, que é o caso que aquele ramo existe para
        # servir.
        if self.action not in {"list", "retrieve"}:
            return queryset
        return queryset.annotate(**publication.anotacao_de_contagem_publicada())

    def perform_destroy(self, instance: Account) -> None:
        """Arquiva o cliente e, junto, os contatos dele — recusando se ainda houver trabalho aberto.

        Soft delete não cascateia sozinho, e sem estas duas regras arquivar um cliente produzia
        órfão visível: `ProjectViewSet` e `CommercialOpportunityViewSet` filtram o próprio
        `archived_at` e nunca o do cliente, então projeto e oportunidade continuavam listados apontando para uma
        linha que sumiu da tela de Clientes. O contato não tem esse problema (ninguém o lista
        sozinho), então ele acompanha em vez de bloquear.

        O **engajamento** (ADR 0050) é listado sozinho em `/engagements/?account=`, então cairia na
        primeira regra e não na segunda — mas ele não **bloqueia**: chegar aqui já significa que
        não sobrou projeto nem oportunidade viva na conta, e um mandato sem nenhum dos dois não é
        trabalho em aberto, é o resíduo dele. Acompanha o contato, na mesma transação.
        """
        projetos = Project.objects.filter(engagement__account=instance, archived_at__isnull=True).count()
        oportunidades = CommercialOpportunity.objects.filter(
            account=instance, archived_at__isnull=True
        ).count()
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
            agora = timezone.now()
            instance.contacts.filter(archived_at__isnull=True).update(
                archived_at=agora, updated_at=agora
            )
            instance.engagements.filter(archived_at__isnull=True).update(
                archived_at=agora, updated_at=agora
            )
            instance.archive()

    def _visible_projects(self, account: Account):  # type: ignore[no-untyped-def]
        return Project.objects.visible_to(self.request.user).filter(
            engagement__account=account, archived_at__isnull=True
        ).select_related("engagement")

    @extend_schema(
        responses=inline_serializer(
            "AccountOverviewList",
            {
                chave_da_geracao("clients", "accounts"): serializers.ListField(
                    child=inline_serializer("AccountOverviewRow", _account_overview_row_fields())
                )
            },
        )
    )
    @action(detail=False, methods=["get"])
    def overview(self, request: Request) -> Response:
        """Lista agregada p/ o grid de contas (honra `?lifecycle_status=` e o alias `?status=`).

        A chave que envolve a lista **troca** por versão — `clients` na `/api/v1/`, `accounts` na
        `/api/v2/` —, e não convive como o resto do payload legado: duplicar aqui pagaria o corpo
        inteiro do grid duas vezes. É o precedente da fatia 3a (`processos`/`processes` na action
        de IA), aplicado ao segundo caso da mesma forma (issue #122, fatia 4a).
        """
        # Cada linha também carrega `client_id`/`status` (legados) ao lado de `account_id`/
        # `lifecycle_status` (canônicos) — os dois somem na `/api/v2/` via `_sem_chaves_legadas`
        # (issue #122, fatia 4c). Comentário, não docstring: drf-spectacular usa a docstring como
        # `description` do endpoint, e ela não muda só porque o item da resposta ganhou tipo.
        accounts = list(self.get_queryset())
        # Um `_visible_projects` por cliente somava ~14 queries por linha do grid. Aqui os
        # projetos visíveis de todos os clientes vêm juntos e o contexto é montado uma vez —
        # o custo do endpoint deixa de crescer com o tamanho da carteira (FDD 022).
        by_client: dict[int, list[Project]] = defaultdict(list)
        for project in Project.objects.visible_to(request.user).filter(
            engagement__account__in=accounts, archived_at__isnull=True
        ).select_related("engagement"):
            by_client[project.engagement.account_id].append(project)
        context = build_overview_context(
            [project for projects in by_client.values() for project in projects]
        )
        linhas = [
            build_account_overview(account, projects=by_client[account.pk], context=context)
            for account in accounts
        ]
        if versao_de(request) == V2:
            linhas = _sem_chaves_legadas(linhas, "client_id", "status")
        chave = "accounts" if versao_de(request) == V2 else "clients"
        return Response({chave: linhas})

    @extend_schema(
        responses=inline_serializer("AccountOverviewDetail", _account_overview_row_fields())
    )
    @action(detail=True, methods=["get"], url_path="overview")
    def overview_detail(self, request: Request, pk: str | None = None) -> Response:
        account = self.get_object()
        overview = build_account_overview(account, projects=self._visible_projects(account))
        if versao_de(request) == V2:
            # O detalhe é uma linha só; `_sem_chaves_legadas` opera em lista, então envolve e
            # desembrulha em vez de duplicar a lógica de remoção (issue #122, fatia 4c).
            (overview,) = _sem_chaves_legadas([overview], "client_id", "status")
        return Response(overview)


class ContactViewSet(QueryParamFilterMixin, ArchiveModelViewSet):
    resource = "contact"
    queryset = Contact.objects.select_related("account").all()
    serializer_class = ContactSerializer
    filter_fields = ("account",)
    filter_field_aliases = {"account": "client"}

    def get_queryset(self):  # type: ignore[no-untyped-def]
        # Sem isto, as pessoas dos clientes que acabaram de sumir continuariam listadas.
        queryset = super().get_queryset()
        scope = project_scope_q(self.request.user, "account__engagements__projects")
        return queryset.filter(scope).distinct() if scope else queryset


class ActivityViewSet(QueryParamFilterMixin, ArchiveModelViewSet):
    """Interação comercial com o cliente (ligação, reunião, e-mail, nota) — FDD 035."""

    resource = "activity"
    queryset = Activity.objects.select_related(
        "account", "commercial_opportunity", "owner"
    ).all()
    serializer_class = ActivitySerializer
    filter_fields = ("account", "commercial_opportunity")
    filter_field_aliases = {"commercial_opportunity": "opportunity", "account": "client"}

    def get_queryset(self):  # type: ignore[no-untyped-def]
        # Mesma fronteira do Contact: a Entrega só enxerga interações de clientes com projeto seu.
        queryset = super().get_queryset()
        scope = project_scope_q(self.request.user, "account__engagements__projects")
        return queryset.filter(scope).distinct() if scope else queryset

    def perform_create(self, serializer: ActivitySerializer) -> None:
        serializer.save(owner=self.request.user)

    @extend_schema(request=None, responses=ActivitySerializer)
    @action(detail=True, methods=["post"])
    def classificar(self, request: Request, pk: str | None = None) -> Response:
        """Lê a resposta do cliente e grava o sinal — **e não age** (FDD 036, camada 4).

        Os três valores não são etiquetas de humor: cada um manda para uma conduta diferente e a
        mesma régua estraga os três se tratá-los igual. `forgot` já se resolveu com o lembrete;
        `unable_to_pay` pede renegociação, e cedo; `dissatisfied` não é problema de cobrança — é
        problema de relação disfarçado, e é onde insistir piora tudo.

        Gravar o sinal é o fim do que a IA faz aqui. Renegociar, dar desconto, suspender e escalar
        seguem humanos (ADR 0006, ADR 0031).
        """
        activity = self.get_object()
        # O prompt pede os TRÊS CANÔNICOS ingleses diretamente — não pt-BR traduzido depois. Pedir
        # em português e traduzir a resposta deixaria no prompt a aparência de que o modelo decide
        # o idioma do dado (mesmo argumento da FDD 039); `sinal_do_texto` ainda tolera o token
        # legado por barato custo de release (`_SINAIS_LEGADOS`, cache/variação do modelo).
        system = (
            "Você classifica a resposta de um cliente a uma cobrança. Devolva APENAS um objeto "
            'JSON, sem texto antes ou depois, com a chave "sinal" e um destes três valores: '
            '"forgot" (apenas não lembrou e vai pagar), "unable_to_pay" (tem dificuldade '
            'financeira ou de fluxo de caixa) ou "dissatisfied" (está retendo o pagamento por '
            "insatisfação com a entrega ou com a relação). Use APENAS o material fornecido: se "
            "ele não permitir decidir, devolva um objeto vazio em vez de inferir."
        )

        def grava(text: str, interaction) -> dict:  # type: ignore[no-untyped-def]
            sinal = sinal_do_texto(text)
            if not sinal:
                # Sem sinal utilizável não houve classificação — e isso é diferente de gravar um
                # valor qualquer. A coluna roteia conduta; um valor chutado manda alguém insistir
                # com quem está insatisfeito.
                raise _ExtracaoSemResultado()
            Activity.objects.filter(pk=activity.pk).update(dunning_signal=sinal)
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

        Um dos dois `DELETE` de verdade do portal (FDD 025). `CommercialOpportunity.stage` é
        `PROTECT`, e sem esta guarda o banco recusava por baixo: `ProtectedError` sem tradução vira **500**.
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


class CommercialOpportunityViewSet(QueryParamFilterMixin, ArchiveModelViewSet):
    resource = "commercial_opportunity"
    # `projects` é o reverso lido por `CommercialOpportunitySerializer._projeto_do_card`. Era
    # `select_related("project")` enquanto a relação era 1-1; virou `prefetch_related` porque
    # 1-N não cabe num `JOIN` sem multiplicar a linha da oportunidade. O motivo de estar aqui é o
    # mesmo de antes: sem ele, a listagem do pipeline faz uma query por card (ADR 0014).
    queryset = (
        CommercialOpportunity.objects
        .select_related("account", "contact", "stage", "owner", "service")
        .prefetch_related("projects")
        .all()
    )
    serializer_class = CommercialOpportunitySerializer
    filter_fields = ("account",)

    def perform_create(self, serializer: CommercialOpportunitySerializer) -> None:
        serializer.save(owner=self.request.user)

    def perform_destroy(self, instance: CommercialOpportunity) -> None:
        """Recusa arquivar oportunidade cujo projeto ainda está **ativo**.

        `Project.originating_commercial_opportunity` é `PROTECT`, e o projeto lê a oportunidade
        para montar o próprio histórico comercial. Arquivá-la sob um projeto vivo deixaria o
        projeto apontando para um registro que a interface esconde.

        A condição é o estado do projeto, e não a existência da relação: a origem continua
        apontando para cá com o projeto arquivado, porque o reverso não some com o `archived_at`.
        Testando só a existência, a recusa não tinha saída — a própria mensagem manda arquivar o
        projeto, e isso não desbloqueava nada. Ver FDD 025.
        """
        vivos = instance.projects.filter(archived_at__isnull=True).order_by("id")
        projeto = vivos.first()
        if projeto is not None:
            quantos = vivos.count()
            alvo = (
                f"os projetos \"{projeto.name}\" e mais {quantos - 1}"
                if quantos > 1
                else f"o projeto \"{projeto.name}\""
            )
            raise StateConflict(
                f"Esta oportunidade já virou {alvo}. "
                "Arquive o projeto se quiser encerrar este trabalho."
            )
        instance.archive()

    def get_queryset(self):  # type: ignore[no-untyped-def]
        queryset = super().get_queryset()
        # Ganha **e** convertida num projeto da equipe: a oportunidade é o outro lado do
        # projeto, e deixá-la aberta reabriria pelo comercial o que o recorte fechou.
        if self.request.user.role == User.Role.DELIVERY and not self.request.user.is_admin_role:
            return queryset.filter(
                project_scope_q(self.request.user, "projects"),
                stage__kind=PipelineStage.Kind.WON,
            ).distinct()
        return queryset

    @action(detail=True, methods=["post"], url_path="convert-to-project")
    def convert_to_project(self, request: Request, pk: str | None = None) -> Response:
        """Converte a oportunidade ganha num projeto — **uma vez**, e a garantia mudou de lugar.

        Até a ADR 0050 quem garantia "converte uma vez só" era o banco: o campo hoje chamado
        `Project.originating_commercial_opportunity` era `OneToOneField`, e a segunda conversão
        morria num `IntegrityError` que virava 409. Essa
        cardinalidade caiu porque ela também impedia o que a casa passou a vender — uma
        Transformation Partnership origina vários projetos ao longo do mandato.

        A invariante que importa não era a da tabela, era a do **botão**: duplo clique não pode
        criar dois projetos. Ela continua aqui, e agora explicitamente:

        - o guard olha projeto **vivo** com esta origem (arquivado não ocupa mais o lugar; a saída
          da FDD 025 deixa de depender de restaurar);
        - `select_for_update` na oportunidade serializa duas requisições simultâneas, que é o que
          o `IntegrityError` fazia de graça e deixou de fazer. Sem ele, dois cliques concorrentes
          leem "não há projeto" ao mesmo tempo e ambos criam — e nada acusa.

        Projeto adicional com a mesma origem é legítimo e nasce por `POST /projects/`, com
        `engagement` e `originating_commercial_opportunity` explícitos.
        """
        opportunity = self.get_object()
        if request.user.role not in {User.Role.ADMIN, User.Role.SALES} and not request.user.is_superuser:
            return Response({"detail": "Somente Vendas pode converter oportunidades."}, status=403)
        if not opportunity.is_won:
            return Response({"detail": "A oportunidade deve estar na etapa Ganho."}, status=400)
        serializer = ProjectSerializer(data=request.data, engagement_optional=True)
        serializer.is_valid(raise_exception=True)
        # A chave `client` segue no contrato da `/api/v1/`. Quando o payload não traz engagement,
        # o serializer ainda não tem contra o que compará-la; a oportunidade é a fonte que cria o
        # mandato logo abaixo. Ignorar uma conta divergente devolveria 201 para um corpo que a v1
        # sempre recusou — e faria o consumidor acreditar que escolheu uma conta que não foi usada.
        legacy_client = request.data.get("client")
        if legacy_client is not None and int(legacy_client) != opportunity.account_id:
            return Response(
                {"client": "O projeto deve usar o cliente da oportunidade."}, status=400
            )
        engagement = serializer.validated_data.get("engagement")
        if engagement is not None and engagement.account_id != opportunity.account_id:
            return Response(
                {"engagement": "O engagement deve ser da mesma conta da oportunidade."}, status=400
            )
        if (
            engagement is not None
            and opportunity.engagement_id is not None
            and opportunity.engagement_id != engagement.pk
        ):
            return Response(
                {"engagement": "A oportunidade já pertence a outro engagement."}, status=400
            )
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
                # A trava é aqui, e é o que substitui a unicidade que o `OneToOneField` dava. A
                # linha da oportunidade fica bloqueada até o fim da transação, então a segunda
                # requisição só lê o estado depois que a primeira gravou o projeto — e cai no 409
                # abaixo em vez de criar o segundo.
                travada = CommercialOpportunity.objects.select_for_update().get(pk=opportunity.pk)
                vivo = travada.projects.filter(archived_at__isnull=True).order_by("id").first()
                if vivo is not None:
                    return Response({"detail": "A oportunidade já foi convertida."}, status=409)
                # A continuidade de um Design Partner nasce como CommercialOpportunity **dentro**
                # do Engagement existente (D8). O formulário de conversão não precisa repetir um
                # vínculo que a venda já declara; sem esta linha ele criaria um segundo mandato e
                # separaria o projeto da própria continuidade que o originou.
                if engagement is None and travada.engagement_id is not None:
                    engagement = travada.engagement
                if engagement is None:
                    # **D3 em código**: todo projeto pertence a um engajamento, e a venda avulsa
                    # não vira caso especial — ela cria um mandato de escopo único. Manter o
                    # projeto sem engajamento para "quando for avulso" custaria um segundo caminho
                    # em cada agregador, e o caminho raro é o que ninguém testa (ADR 0050).
                    engagement = Engagement.objects.create(
                        account_id=opportunity.account_id,
                        name=opportunity.title,
                        mandate=opportunity.scope or "",
                        owner=request.user,
                        started_at=timezone.localdate(),
                        # Explícito e não herdado do default: aqui é pago por construção, porque
                        # a action exige oportunidade em "Ganho".
                        commercial_model=Engagement.CommercialModel.PAID,
                        originating_commercial_opportunity=travada,
                    )
                # A oportunidade de origem também é a primeira venda **dentro** do mandato. O
                # campo inverso já existia para continuidades; preenchê-lo aqui mantém as duas
                # leituras da mesma relação coerentes sem inferir nada no legado.
                if travada.engagement_id is None:
                    CommercialOpportunity.objects.filter(pk=travada.pk).update(
                        engagement=engagement
                    )
                project = serializer.save(
                    engagement=engagement,
                    originating_commercial_opportunity=travada,
                    owner=request.user,
                    service=service,
                )
                kickoff.seed_work_items(project)
                # Dentro da transação, e não no `finalize` abaixo, porque é escrita no banco e não
                # efeito externo — o mesmo lugar de `seed_work_items`, pelo mesmo motivo. As
                # faturas nascem em **rascunho**: débito automático não existe neste recorte, e
                # emitir é ato deliberado de gente (FDD 028).
                invoices.seed_invoices(project)
        except IntegrityError:
            # Já não carrega unicidade nenhuma — o `select_for_update` acima faz esse trabalho.
            # Fica porque continua sendo o que transforma uma falha de integridade residual em 409
            # com a transação inteira desfeita, em vez de 500 com projeto pela metade.
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


class EngagementViewSet(QueryParamFilterMixin, ArchiveModelViewSet):
    """O mandato de transformação da conta (ADR 0050, FDD 046).

    **Não é fronteira de acesso.** O recorte da Entrega continua sendo `ProjectMember`, e por isso
    esta viewset **não** usa `ProjectScopedMixin`: enxergar um engajamento não dá acesso a nenhum
    projeto dele. O `get_queryset` abaixo faz o caminho inverso — deriva a visibilidade do
    engajamento a partir dos projetos que a pessoa já podia ver.
    """

    resource = "engagement"
    queryset = Engagement.objects.select_related(
        "account",
        "owner",
        "sponsor",
        "originating_commercial_opportunity",
        "originating_design_partner_agreement",
    ).prefetch_related(
        # O fallback do grupo de WhatsApp (DAP `dap-grupo-de-whatsapp-r1`, B1) lê os projetos do
        # mandato em `kickoff.grupo_do_mandato`; sem o prefetch a listagem faz uma query por linha.
        "projects",
    ).all()
    serializer_class = EngagementSerializer
    # `status` em `filter_exact_fields` e não em `filter_fields`: o primeiro conjunto só aplica
    # valores numéricos (`value.isdigit()`), e `?status=active` seria silenciosamente ignorado —
    # a lista voltaria completa e pareceria que o filtro não filtra nada.
    filter_fields = ("account",)
    filter_exact_fields = ("status",)

    def get_queryset(self):  # type: ignore[no-untyped-def]
        queryset = super().get_queryset()
        user = self.request.user
        # A contagem de projetos que a seção do detalhe do cliente mostra na linha, e ela é
        # **recortada pelo escopo de quem lê**, não o total do mandato. Um total cru contaria,
        # para a Entrega, projetos fora do recorte dela — sinal fraco, mas ainda assim informação
        # sobre o que ela não alcança, e este repositório não abre essa exceção. É a mesma regra
        # dos outros agregadores narrowed by hand (`/clients/overview/`, `/risk/`, `/health/`),
        # e como eles esta tem teste próprio.
        #
        # A consequência é deliberada e está escrita na FDD 046: **dois usuários veem números
        # diferentes para o mesmo mandato**. Cada um vê o que alcança.
        #
        # `distinct=True` no `Count` não é enfeite, é a mesma armadilha do `.distinct()` abaixo em
        # dobro: o filtro do recorte atravessa `projects__members` e o filtro da Entrega atravessa
        # `projects` de novo, então a linha do projeto se repete e um `Count` cru somaria a
        # repetição. A anotação vem **antes** do filtro da Entrega de propósito — anotar depois
        # deixaria o join do recorte ao alcance do `Count`.
        queryset = queryset.annotate(
            projects_count=Count(
                "projects",
                filter=Q(projects__archived_at__isnull=True)
                & project_scope_q(user, "projects"),
                distinct=True,
            )
        )
        if user.is_admin_role or user.role != User.Role.DELIVERY:
            return queryset
        # Entrega vê o mandato **de que participa**, derivado de `visible_to` — a única expressão
        # da regra (ADR 0010), nunca reescrita à mão. O `.distinct()` não é enfeite: o `filter`
        # atravessa o reverso `projects` e devolve uma linha por projeto casado, então sem ele o
        # mesmo engajamento aparece tantas vezes quantos projetos a pessoa tiver nele.
        return queryset.filter(projects__in=Project.objects.visible_to(user)).distinct()

    def perform_create(self, serializer: EngagementSerializer) -> None:
        """Grava `owner=request.user` quando o payload não o traz.

        `Engagement.owner` é `PROTECT` não-nulo, e o formulário aprovado (DAP `dap-engagement-r1`)
        não expõe "Responsável": a seção vive dentro do detalhe do cliente, onde quem cria é quem
        está logado. O precedente é a própria `convert-to-project`, que cria o mandato de escopo
        único com `owner=request.user`.

        **Quando ausente, e não sempre**: `owner` continua gravável no contrato `/api/v1/` — um
        admin que cria mandato de outra pessoa segue podendo dizer de quem ele é, e forçar aqui
        tiraria em silêncio um campo que a API já aceitava.
        """
        if serializer.validated_data.get("owner") is None:
            serializer.save(owner=self.request.user)
        else:
            serializer.save()

    def perform_destroy(self, instance: Engagement) -> None:
        """Recusa arquivar mandato com projeto vivo — a regra de órfão da FDD 025.

        `ProjectViewSet` filtra o próprio `archived_at` e nunca o do engajamento, então arquivar
        aqui deixaria projetos listados apontando para um mandato que a interface esconde. É o
        mesmo defeito que o cliente e a oportunidade já tratam, e o mesmo remédio.
        """
        vivos = instance.projects.filter(archived_at__isnull=True).count()
        if vivos:
            raise StateConflict(
                f"Este engagement ainda tem {vivos} projeto(s) em aberto. "
                "Arquive esses projetos antes de arquivar o engagement."
            )
        instance.archive()

    @extend_schema(request=ProjectSerializer, responses={201: ProjectSerializer})
    @action(detail=True, methods=["post"], url_path="create-project")
    def create_project(self, request: Request, pk: str | None = None) -> Response:
        """Faz nascer um projeto do mandato, sem passar por venda (DAP `dap-engagement-r3`, D1).

        `POST /projects/` não serve a este caminho por **três** razões, e nenhuma delas é estilo:

        - ele só passa para admin (`RolePermission`), e a seção de Engagements é visível a Vendas —
          quem negocia o mandato é quem cria o projeto dele. Afrouxar o `RolePermission` para
          resolver isto abriria a criação crua de projeto para todo o comercial, que é mais do que
          se pediu; a guarda própria desta action é o mesmo remédio da `convert-to-project`;
        - `perform_create` não semeia nada: sem marcos, sem tarefas, sem faturas e sem kickoff. Um
          projeto nascido por lá aparece vazio, e o Discovery Sprint perde os marcos que **são** a
          metodologia (walkthrough, custo do estado atual, Executive Readout);
        - a invariante 6 do mapa de linguagem (oferta de aquisição não gera projeto) vive em
          `Project.clean()`, e o `ProjectSerializer` não chama `full_clean()` — hoje só a conversão
          a aplica de fato.

        **A trava não é a mesma da conversão, e a diferença é sutil.** Lá o `select_for_update`
        sustenta um "converte uma vez só"; aqui não há o que impedir — um mandato origina vários
        projetos por desenho (D1, ADR 0050), e o segundo é legítimo. A trava existe porque
        `kickoff.seed_work_items` **não** é idempotente: ela apenas serializa duas requisições
        simultâneas para que o duplo clique produza dois pedidos em fila, e não dois projetos com
        dois cronogramas gravados por cima um do outro. Ela mora em
        `kickoff.criar_projeto_do_mandato`, junto do resto do ato, desde que a rota pública do
        agendamento passou a fazer nascer o mesmo projeto (ADR 0061).
        """
        engagement = self.get_object()
        if request.user.role not in {User.Role.ADMIN, User.Role.SALES} and not request.user.is_superuser:
            return Response(
                {"detail": "Somente Vendas pode criar projetos a partir do engagement."}, status=403
            )
        # D1: mandato encerrado não oferece a ação. 409 e não 400 pela regra do `StateConflict` —
        # o corpo está perfeitamente bem formado, o que impede é o estado, e é ele que muda para o
        # pedido passar.
        if engagement.status == Engagement.Status.CLOSED:
            raise StateConflict(
                "Este engagement está encerrado e não origina projeto novo. "
                "Reabra o mandato ou crie o projeto no engagement que está em curso."
            )
        # O mandato desta rota é o da URL, e o formulário aprovado (C1) não repete o que o caminho
        # já diz: `name`, `service`, `start_date` e `due_date`, nada mais. Ele entra no corpo
        # **antes** da validação, e não como `engagement_optional` mais um `save(engagement=…)`,
        # porque é o que mantém a validação sendo a mesma do `POST /projects/` — uma definição só:
        # `due_date >= start_date` e a conferência da chave legada `client` contra a conta do
        # mandato, que sem o engajamento em mãos o serializer pula em silêncio.
        dados = request.data.copy()
        do_corpo = dados.get("engagement")
        if do_corpo is not None and str(do_corpo) != str(engagement.pk):
            # Sobrescrever devolveria 201 para um pedido que escolheu **outro** mandato, e quem
            # chamou acreditaria ter criado o projeto lá. Mesmo motivo pelo qual a conversão recusa
            # uma conta divergente em vez de ignorá-la.
            return Response(
                {"engagement": "O projeto nasce do engagement da rota. Remova a chave do corpo "
                               "ou repita o mesmo id."},
                status=400,
            )
        dados["engagement"] = engagement.pk
        serializer = ProjectSerializer(data=dados)
        serializer.is_valid(raise_exception=True)
        service = serializer.validated_data.get("service")
        # Invariante 6 do mapa de linguagem (ADR 0049), a mesma da conversão e com o mesmo texto:
        # a Qualification Call existe para descobrir se há venda, não para ser entregue.
        if service and service.category == Service.Category.ACQUISITION:
            return Response(
                {"service": "Oferta de aquisição não gera projeto — a Qualification Call abre a "
                            "venda, ela não é a venda. Escolha um degrau da escada."},
                status=400,
            )
        # A transação inteira — trava, gravação e semeadura — mora em `kickoff`, porque a rota
        # pública em que o cliente marca a sessão de Discovery faz nascer o **mesmo** projeto
        # (ADR 0061) e duas cópias do ato divergiriam na primeira manutenção. O que fica aqui é o
        # que só esta rota tem: as guardas acima e o dono, que lá não existe.
        #
        # Sem `originating_commercial_opportunity`: aqui não houve venda, e inventar uma origem
        # comercial contaminaria o funil e o ciclo médio, que leem esse campo como fato histórico.
        # Projeto de mandato sem venda é o caso do Design Partner (ADR 0053).
        project = kickoff.criar_projeto_do_mandato(
            engagement, lambda: serializer.save(owner=request.user)
        )
        kickoff.finalize(project, origem=f"a partir do engagement '{engagement.name}'")
        return Response(ProjectSerializer(project).data, status=status.HTTP_201_CREATED)


class ProjectViewSet(ProjectScopedMixin, ArchiveModelViewSet):
    resource = "project"
    project_path = ""  # o recorte é sobre o próprio projeto
    queryset = Project.objects.select_related(
        "engagement", "engagement__account", "originating_commercial_opportunity", "owner"
    ).all()
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
             "vertical": serializers.IntegerField(required=False)},
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

        **`kpi_baseline` deixou de ser aceito aqui** (ADR 0055, decisão C1 do DAP
        `dap-prove-e-valor-r1`). A FDD 027 tinha razão sobre o *momento* — o "antes" perguntado na
        conclusão é memória, não medição —, e o que mudou foi **onde** ele mora: o baseline é uma
        `Measurement(kind=baseline)` de um `KPI`, e continuar aceitando-o aqui manteria dois
        lugares escrevendo a mesma medição, que é o defeito que a fase inteira desfaz. Quebra
        deliberada e documentada da `/api/v1/`, registrada em `docs/ontology/aliases.md`: a chave
        no corpo passa a ser ignorada, e o ativo nasce sem KPI para depois referenciar um.
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
            else project.engagement.account.vertical
        )
        employee = blueprints.instantiate(project, blueprint, vertical)
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
                "decision": serializers.ChoiceField(
                    choices=ProjectPhase.DECISOES_DO_GATE,
                    help_text=(
                        "As sete saídas dos dois vocabulários (ADR 0053). O esquema aceita todas "
                        "porque não sabe de qual fase se trata; **quem estreita é o servidor**, "
                        "pelo `canonical_stage` da fase ativa — `prove` aceita SCALE / ITERATE / "
                        "STOP, e qualquer outra fase de gate aceita GO / CONDITIONAL GO / "
                        "REDESIGN / NO-GO. Fora do vocabulário da fase é 400."
                    ),
                ),
                "outcome": serializers.ChoiceField(
                    choices=ProjectPhase.DECISOES_DO_GATE,
                    required=False,
                    help_text=(
                        "Alias depreciado de `decision` (D7, ADR 0052). Continua aceito na "
                        "`/api/v1/`; saiu na `/api/v2/`, que recusa (400) e diz `decision`."
                    ),
                ),
                "notes": serializers.CharField(required=False, allow_blank=True),
            },
        ),
        responses={200: ProjectPhaseSerializer(many=True)},
    )
    @action(detail=True, methods=["post"], url_path="apply-gate")
    def apply_gate(self, request: Request, pk: str | None = None) -> Response:
        """Registra o decision gate na fase ativa (delivery/admin, FDD 033, ADR 0053).

        Devolve a jornada inteira, no mesmo formato do `advance-phase`: as saídas mexem em até
        duas fases, e a tela precisa da lista atualizada, não do que mudou.

        **Não valida a decisão aqui.** Qual vocabulário vale depende da fase ativa, que só
        `journey.apply_gate` resolve — e a invariante pertence ao domínio, não à rota (ADR 0053).
        De lá vêm o 400 do valor fora do vocabulário e o 409 do estado que impede.
        """
        project = self.get_object()
        # `decision` é a chave canônica (D7, ADR 0052); `outcome` continua aceita como alias da
        # `/api/v1/`, com a mesma precedência dos aliases de serializer (a canônica vence quando
        # as duas vêm no mesmo corpo — não trava quem já migrou). Na `/api/v2/` o alias morreu
        # (issue #122, fatia 3a): a recusa vem antes do `or`, porque senão o `outcome` de um corpo
        # só-com-`outcome` seria lido normalmente e a chave nunca chegaria a ser recusada.
        if versao_de(request) == V2 and "outcome" in request.data:
            raise InvalidInput(frase_da_chave_removida("outcome", "decision"))
        bruto = request.data.get("decision") or request.data.get("outcome", "")
        decision = str(bruto).strip()
        notes = str(request.data.get("notes", "") or "")
        journey.apply_gate(project, decision, notes, actor=request.user)
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
                "account_name": serializers.CharField(),
                # Alias de leitura da `/api/v1/` (`docs/ontology/aliases.md` §2c): mesmo valor de
                # `account_name`. Some da `/api/v2/` — a remoção é da view, porque isto é dict cru
                # (issue #122, fatia 4a); o contrato a perde por `ALIASES_DEPRECIADOS_DE_DICT_CRU`.
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

        `_build_timeline_overview` emite `account_name` e `client_name` com o mesmo valor — o
        comportamento de todo alias de leitura da v1 —, e a remoção do legado é daqui, e não do
        agregador: ele não conhece a versão da requisição, pelo motivo do painel de cobrança.
        """
        linhas = _build_timeline_overview(request.user)
        if versao_de(request) == V2:
            linhas = _sem_chaves_legadas(linhas, "client_name")
        return Response(linhas)

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

    Determinístico (FinOps): a fase ativa conta se ainda não gravou a decisão; senão, a primeira
    trancada à frente que exige gate.
    """
    for phase in phases:
        if phase.status == ProjectPhase.Status.DONE:
            continue
        if phase.phase.requires_gate and not phase.gate_decision:
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
        .select_related("engagement__account")
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
            # O par canônico e o legado saem juntos, com o mesmo valor, como no painel de cobrança
            # (issue #122, fatia 4a). Quem tira o legado na v2 é `timeline_overview`.
            "account_name": project.engagement.account.name,
            "client_name": project.engagement.account.name,
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
    # `kpi__measurements` prefetchado porque `kpi_baseline`/`kpi_current` deixaram de ser colunas e
    # passaram a ser derivados das medições (ADR 0055). Sem ele, a listagem do roster faria duas
    # consultas por linha — e o `.all()` de `prove.baseline_de` existe justamente para consumir
    # este prefetch em vez de furá-lo com um `.filter()`.
    queryset = DigitalEmployee.objects.select_related("project", "kpi").prefetch_related(
        "kpi__measurements"
    ).all()
    serializer_class = DigitalEmployeeSerializer
    filter_fields = ("project", "kpi")


class CaseViewSet(ProjectScopedMixin, QueryParamFilterMixin, ArchiveModelViewSet):
    """Cases de projetos concluídos, com os números congelados (FDD 027).

    Não há `create`: case nasce do congelamento (`cases.freeze_if_completed`, no signal de
    conclusão do projeto) e não da mão de ninguém — um case digitado seria a prova social sem a
    medição, que é o que a FDD recusa. O que a API oferece é revisar, consentir e publicar.

    O escopo de projeto vem do mixin e sai certo de graça: Entrega vê case dos projetos de que
    participa, Vendas e admin veem todos, porque `project_scope_q` só recorta para a Entrega.
    """

    resource = "case"
    queryset = Case.objects.select_related("project__engagement__account", "vertical").all()
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


#: Valor legado do degrau → canônico (issue #122, fatia 5.4; D10 do `language-map` §4). **Um mapa
#: só, e não um por consumidor**: ele é lido pelas duas actions de cobrança da `InvoiceViewSet` — o
#: degrau chega no **corpo** delas, e corpo de action não passa por serializer, então
#: `AliasesDaV1Mixin.VALORES_DE_ENTRADA` não o alcança — e por `filter_valores_legados` da
#: `DunningContactViewSet`, para `?degrau=`. Duas tabelas do mesmo fato divergiriam em silêncio na
#: primeira edição, que é o argumento da fatia 5.1 quando o viewset passou a referenciar o mapa do
#: serializer em vez de copiá-lo.
VALORES_LEGADOS_DO_DEGRAU: dict[str, str] = {
    "pre_aviso": DunningContact.DunningStep.PRE_NOTICE,
    "lembrete": DunningContact.DunningStep.REMINDER,
    "firme": DunningContact.DunningStep.FIRM,
    "escalada": DunningContact.DunningStep.ESCALATION,
    "renegociacao": DunningContact.DunningStep.RENEGOTIATION,
}


def _degrau_do_corpo(request: Request, bruto: str) -> str:
    """Normaliza o degrau que veio no corpo da action — traduz na v1, recusa na v2.

    **Por que aqui e não no mixin de serializer.** O degrau de `rascunhar`/`enviar` é chave de
    corpo de `@action`, e action não monta serializer: `VALORES_DE_ENTRADA` nunca é consultado
    neste caminho. E, diferente do corpo de um `ModelSerializer`, aqui **não existe validação de
    `choices` do DRF** para recusar o valor legado de graça na v2 — quem valida é a própria action,
    contra as réguas de `cobranca.py`. Sem esta função, `pre_aviso` na v2 cairia no
    "Degrau desconhecido", que é um erro mentiroso: o degrau existe, o nome dele é que mudou.

    A frase é a de `versioning.frase_do_valor_removido`, a mesma que o filtro `?degrau=` usa — o
    formato dela nomeia o parâmetro (`'?degrau='`) porque a chave de corpo e a de query string são
    a mesma palavra aqui, e duas redações do mesmo "não existe mais, use este nome" divergiriam na
    primeira edição (a razão de as frases morarem todas em `versioning.py`).
    """
    canonico = VALORES_LEGADOS_DO_DEGRAU.get(bruto)
    if canonico is None:
        return bruto
    if versao_de(request) == V2:
        raise InvalidInput(frase_do_valor_removido("degrau", bruto, canonico))
    return canonico


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
    queryset = Invoice.objects.select_related("account", "project", "service").all()
    serializer_class = InvoiceSerializer
    permission_classes = [RolePermission]
    filter_fields = ("account", "project")
    filter_field_aliases = {"account": "client"}
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
        # Traduzido **antes** da checagem contra o vocabulário: na v1 `pre_aviso` continua valendo,
        # na v2 leva 400 dizendo `pre_notice` (issue #122, fatia 5.4).
        degrau = _degrau_do_corpo(request, str(request.data.get("degrau", "")).strip()) or (
            getattr(cobranca.degrau_devido(invoice), "key", "")
        )
        if degrau not in DunningContact.DunningStep.values:
            return Response(
                {"degrau": "Diga qual degrau rascunhar — hoje a régua não indica nenhum."},
                status=status.HTTP_400_BAD_REQUEST,
            )
        rotulo = DunningContact.DunningStep(degrau).label
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
        responses=DunningContactSerializer,
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
        # A mesma normalização de `rascunhar`, e pelo mesmo motivo: sem ela o valor legado viraria
        # "Degrau desconhecido" na v2 — um erro que aponta para o lugar errado (issue #122, 5.4).
        degrau_key = _degrau_do_corpo(request, str(request.data.get("degrau", "")).strip())
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
        if DunningContact.objects.filter(invoice=invoice, dunning_step=degrau.key).exists():
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
                f"{invoice.account.name} não tem contato marcado como 'recebe cobrança' e não há "
                "administrador ativo a quem escalar. Cadastre o contato antes de enviar."
            ) from exc
        except OSError as exc:
            # E-mail não saiu: **nada é gravado**. Registrar aqui afirmaria um contato que não
            # aconteceu e ainda queimaria o degrau pela constraint, impedindo a retentativa.
            logger.exception("envio de cobrança falhou para a fatura %s", invoice.pk)
            raise EmailUndeliverable() from exc
        return Response(DunningContactSerializer(contato).data, status=status.HTTP_201_CREATED)

    @extend_schema(
        responses=inline_serializer(
            name="InvoiceSummary",
            fields={
                # Os três em **texto**, na mesma forma de `Invoice.amount` (ADR 0068). O
                # `max_digits=12` acompanha o do campo do modelo e é o que fixa o `pattern` do
                # contrato — mudá-lo para o 14 dos agregados de `/analytics/` seria trocar o
                # contrato desta rota de carona numa fatia que veio para o corpo parar de mentir.
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

        Os três totais saem em **texto**, como `Invoice.amount` na listagem ao lado — é o que o
        esquema desta rota já prometia, e o `default=Decimal("0")` garante que nenhum deles seja
        nulo (aqui "não há fatura na faixa" **é** zero recebido, ao contrário do funil).
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
        return Response({**dados, **{nome: dinheiro(dados[nome]) for nome in faixas}})


class DunningContactViewSet(QueryParamFilterMixin, viewsets.ReadOnlyModelViewSet):
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

    resource = "dunning_contact"
    queryset = DunningContact.objects.select_related("invoice", "account", "sent_by").all()
    serializer_class = DunningContactSerializer
    permission_classes = [RolePermission]
    filter_fields = ("account", "invoice")
    # `?degrau=` continua filtrando na v1 e leva 400 na v2, pelo mesmo mecanismo de `?client=`: o
    # campo é `dunning_step` desde a fatia 5.4, e o nome do parâmetro **é** o caminho do ORM aqui.
    filter_field_aliases = {"account": "client", "dunning_step": "degrau"}
    filter_exact_fields = ("dunning_step", "canal")
    # O **valor** do degrau, a outra metade do par (issue #122, fatia 5.4): a v1 traduz
    # `?dunning_step=lembrete` para `reminder`, a v2 recusa dizendo qual usar. O mapa é o mesmo que
    # as duas actions de cobrança leem — ver `VALORES_LEGADOS_DO_DEGRAU`.
    filter_valores_legados = {"dunning_step": VALORES_LEGADOS_DO_DEGRAU}

    @extend_schema(
        responses=inline_serializer(
            name="CobrancaPainelLinha",
            fields={
                "invoice": serializers.IntegerField(),
                "number": serializers.CharField(),
                "account": serializers.IntegerField(),
                "account_name": serializers.CharField(),
                # Alias de leitura da `/api/v1/` (`docs/ontology/aliases.md` §2c): mesmo valor de
                # `account`/`account_name`. Some da resposta da `/api/v2/` desde a fatia 3a, e do
                # **contrato** dela desde a 4a — por `ALIASES_DEPRECIADOS_DE_DICT_CRU`, que é como
                # um componente de `inline_serializer` entra no mesmo mapa dos outros.
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
                # O dicionário **inteiro** é `None` quando não há suspensão vigente
                # (`cobranca.painel`) — não é um objeto de campos nulos. `inline_serializer` e não
                # classe de módulo porque esta forma tem um consumidor só; o componente
                # `CobrancaSuspensao` do CRUD é outra coisa (tem motivo, autor, timestamps).
                "suspensao": inline_serializer(
                    "CobrancaPainelSuspensao",
                    {
                        "id": serializers.IntegerField(),
                        "until": serializers.DateField(),
                        "owner": serializers.IntegerField(),
                        "owner_name": serializers.CharField(),
                    },
                    allow_null=True,
                ),
                "regua_ligada": serializers.BooleanField(),
            },
            many=True,
        )
    )
    @action(detail=False, methods=["get"])
    def painel(self, request: Request) -> Response:
        """A tela onde se decide o próximo passo (FDD 036, critério de aceite 7).

        Agregador, e por isso **não passa pelo queryset desta viewset**: ele lista faturas, não
        contatos. O recorte de papel continua sendo o `resource` da classe — só-leitura
        para Vendas, fechado para a Entrega —, que é o mesmo mecanismo da FDD 028 e a razão de esta
        rota não precisar de guarda própria.

        Toda a decisão sai de `cobranca.painel()`, e nenhuma linha dela é recalculada aqui: a régua
        tem uma definição só, e a tela lê a mesma que o relógio executa.

        `cobranca.painel()` emite os dois pares (`account`/`account_name` e `client`/
        `client_name`, mesmo valor) — o comportamento de todo alias de leitura da `/api/v1/`. Na
        `/api/v2/` os dois legados somem daqui, e não do agregador: ele não conhece a versão da
        requisição, e não devia precisar conhecer para listar faturas.
        """
        linhas = cobranca.painel()
        if versao_de(request) == V2:
            linhas = _sem_chaves_legadas(linhas, "client", "client_name")
        return Response(linhas)


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
        "invoice", "account", "owner", "created_by"
    ).all()
    serializer_class = CobrancaSuspensaoSerializer
    permission_classes = [RolePermission]
    filter_fields = ("account", "invoice", "owner")
    filter_field_aliases = {"account": "client"}

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
        "commercial_opportunity__account", "project__engagement__account", "document"
    ).all()
    serializer_class = ArtifactSerializer
    filter_fields = ("commercial_opportunity", "project")
    filter_field_aliases = {"commercial_opportunity": "opportunity"}
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
            and serializer.validated_data.get("commercial_opportunity") is not None
        ):
            raise PermissionDenied("Entrega não vincula artefatos a oportunidades.")
        super().perform_create(serializer)


def _signers_do_pedido(data: Any, versao: str) -> list[esign.Signer]:
    """A rodada de assinatura pedida no corpo — na forma nova, ou pelo alias `signer_email`.

    `signers` é a forma canônica: uma lista de `{"email", "role"}`, na ordem em que os signatários
    ocupam o bloco de assinatura do documento (duas testemunhas pegam as duas linhas, nessa ordem).
    Na `/api/v1/`, `signer_email` continua aceito e vira **um** signatário `counterparty` — a SPA
    ainda manda a forma antiga, e a tela de escolher contatos e papéis depende de um DAP que ainda
    não existe; quebrar agora deixaria o produto sem caminho nenhum. É o mecanismo de alias de
    entrada de sempre (`docs/ontology/aliases.md` §2c), e a **forma nova vence** quando as duas vêm
    no mesmo corpo.

    Morreu na `/api/v2/` (issue #122, fatia 3a): esta action não passa por serializer com
    `ALIASES_DE_ENTRADA`, então `AliasesDaV1Mixin` não a alcança — a recusa mora aqui, e por isso
    recebe a versão do chamador em vez de a redescobrir.

    As três recusas de forma são 400 (`InvalidInput`) porque é o **corpo** que está errado, não o
    estado: lista vazia, papel fora do vocabulário, e e-mail repetido — este último porque o
    fornecedor casa signatário por e-mail, e dois iguais tornam ambíguo qual solicitação o webhook
    vem fechar.
    """
    if versao == V2 and "signer_email" in data:
        raise InvalidInput(frase_da_chave_removida("signer_email", "signers"))
    if "signers" in data:
        pedidos = data.get("signers")
        if not isinstance(pedidos, list) or not pedidos:
            raise InvalidInput("Informe ao menos um signatário em «signers».")
    else:
        email_unico = str(data.get("signer_email", "")).strip()
        if not email_unico:
            raise InvalidInput("Informe o e-mail do signatário.")
        pedidos = [{"email": email_unico, "role": SignatureRequest.SignerRole.COUNTERPARTY}]

    signers: list[esign.Signer] = []
    vistos: set[str] = set()
    for pedido in pedidos:
        if not isinstance(pedido, dict):
            raise InvalidInput("Cada signatário é um objeto com «email» e «role».")
        email = str(pedido.get("email", "")).strip()
        if not email:
            raise InvalidInput("Informe o e-mail do signatário.")
        papel = str(pedido.get("role") or SignatureRequest.SignerRole.COUNTERPARTY).strip()
        if papel not in SignatureRequest.SignerRole.values:
            raise InvalidInput(f"Papel de signatário desconhecido: «{papel}».")
        if email.lower() in vistos:
            raise InvalidInput(
                "O mesmo e-mail aparece duas vezes na lista de signatários. O fornecedor casa "
                "signatário por e-mail, e dois iguais deixam ambíguo qual assinatura foi concluída."
            )
        vistos.add(email.lower())
        signers.append(esign.Signer(email=email, role=papel))

    casa = str(settings.ESIGN_HOUSE_SIGNER_EMAIL or "").strip()
    # A casa entra sozinha quando o e-mail dela está configurado — e **não** entra duas vezes se
    # quem enviou já a nomeou no corpo: seria o e-mail repetido que a regra acima recusa.
    if casa and casa.lower() not in vistos:
        signers.append(esign.Signer(email=casa, role=SignatureRequest.SignerRole.HOUSE))
    return signers


class DocumentViewSet(ProjectScopedMixin, QueryParamFilterMixin, ArchiveModelViewSet):
    """Documentos privados, vinculados a exatamente um cliente, oportunidade ou projeto.

    Entrega só enxerga os documentos dos projetos de que participa; proposta e contrato, que
    nascem ligados à oportunidade, ficam fora do alcance dela (FDD 016, FDD 017, RFC 0003).

    `http_method_names` não inclui `put` nem `patch`, no molde de `PriorityAssessmentViewSet`: o
    documento é o próprio arquivo, e trocá-lo por baixo do registro deixaria três fatos
    divergindo em silêncio — o carimbo `content_is_pdf` (calculado do arquivo **anterior**, e lido
    pela tela de assinatura), `drive_file_id`/`drive_link` (que continuariam apontando para o
    arquivo velho) e uma assinatura já pedida sobre o conteúdo antigo. Quem precisa de outro
    arquivo envia outro documento — é `POST` que tem as guardas de extensão/tamanho.
    """

    resource = "document"
    http_method_names = ["get", "post", "delete", "head", "options"]
    queryset = Document.objects.select_related(
        "account", "commercial_opportunity", "project", "uploaded_by",
        "originated_design_partner_engagement",
        # A conta-dona derivada (`owning_account`, DAP r1 B1) segue o vínculo até
        # `engagement.account`. Sem estes dois a listagem faz uma consulta por documento pendurado
        # em oportunidade ou projeto — o campo é derivado, mas a cadeia é real.
        "commercial_opportunity__account", "project__engagement__account",
    ).prefetch_related("signature_requests").all()
    serializer_class = DocumentSerializer
    filter_fields = ("account", "commercial_opportunity", "project")
    filter_field_aliases = {"commercial_opportunity": "opportunity", "account": "client"}

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

    @extend_schema(
        request=inline_serializer(
            name="RequestSignatureRequest",
            fields={
                "signers": serializers.ListField(
                    child=inline_serializer(
                        name="RequestSignatureSigner",
                        fields={
                            "email": serializers.EmailField(),
                            "role": serializers.ChoiceField(
                                choices=SignatureRequest.SignerRole.choices, required=False
                            ),
                        },
                    ),
                    required=False,
                ),
                # Alias de entrada, morreu na `/api/v2/` (`docs/ontology/aliases.md`, issue #122
                # fatia 3a): um único signatário `counterparty`. Na `/api/v1/` a forma canônica é
                # `signers`, e ela vence quando as duas vêm no mesmo corpo; na `/api/v2/` esta
                # chave é recusada com 400.
                "signer_email": serializers.EmailField(required=False),
            },
        ),
        responses=inline_serializer(
            name="RequestSignatureCreated",
            fields={
                "signatures": serializers.ListField(
                    child=inline_serializer(
                        name="RequestSignatureCreatedItem",
                        fields={
                            "id": serializers.IntegerField(),
                            "status": serializers.CharField(),
                            "signer_email": serializers.EmailField(),
                            "signer_role": serializers.CharField(),
                        },
                    )
                )
            },
        ),
    )
    @action(detail=True, methods=["post"], url_path="request-signature")
    def request_signature(self, request: Request, pk: str | None = None) -> Response:
        document = self.get_object()
        if not esign.is_enabled():
            return Response({"detail": "Assinatura eletrônica desativada."}, status=status.HTTP_503_SERVICE_UNAVAILABLE)
        signers = _signers_do_pedido(request.data, versao_de(request))
        try:
            refs = esign.send_for_signature(document, signers)
        except esign.EsignProviderError as exc:
            logger.exception("solicitação de assinatura recusada para %s", document.original_name)
            raise EsignUnavailable() from exc
        # Uma rodada, N solicitações, o **mesmo** `document_ref` — é ele que responde "esta rodada
        # está assinada?" em `Document.is_signed`.
        criadas = [
            SignatureRequest.objects.create(
                document=document, signer_email=signer.email, signer_role=signer.role,
                provider_ref=ref.provider_ref, document_ref=ref.document_ref, sign_url=ref.sign_url,
            )
            for signer, ref in zip(signers, refs, strict=True)
        ]
        for signature in criadas:
            esign.invite_signer(document, signature)  # no-op quando o fornecedor é quem convida
        return Response(
            {
                "signatures": [
                    {
                        "id": signature.id,
                        "status": signature.status,
                        "signer_email": signature.signer_email,
                        "signer_role": signature.signer_role,
                    }
                    for signature in criadas
                ]
            },
            status=status.HTTP_201_CREATED,
        )

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
        # Fallback manual do mesmo caminho do webhook (`esign.apply_decision`): fecha o artefato
        # de contrato, notifica quem subiu o documento e é idempotente a um segundo clique.
        signature = esign.apply_decision(signature.pk, SignatureRequest.Status.SIGNED)
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
        dito*, que é uma das cinco formas de evidência (`docs/metodologia-fde.md:112-115`), não
        prova; promover a fato é ato de gente, pela mesma razão que a ADR 0032 recusou à IA gravar
        satisfação.

        **A segunda é a recusa de reexecução**, e ela é divergência deliberada do `extrair_decisoes`:
        lá cada execução cria `Decisao` em **rascunho**, um estado que a tela mostra como pendente
        de revisão, e uma segunda rodada só dá mais rascunho para revisar. `Process` não tem
        estado de rascunho — a segunda extração dobraria o mapa da operação do cliente **em
        silêncio**, e um duplo clique bastaria. Recusar com 409 é dizer qual é o estado que impede
        e como sair dele, que é para o que o `StateConflict` existe.

        **A gravação é do par do split, e a forma da resposta não muda.** Além de
        `Process`/`ProcessStep`, a mesma transação escreve uma `Evidence` por processo, que diz de
        onde o achado veio, e um `Finding` por achado, que diz o que ele afirma — sempre em
        `hypothesis`, porque o modelo produz o que foi dito, não prova. Até a Fase 6 (ADR 0052)
        havia também a `Evidencia` fundida; com o legado removido e o custo do estado atual lendo o
        `Finding`, sobra o par canônico. A resposta segue `{"processos": [...]}` e nenhuma tela
        precisou mudar por causa disso.
        """
        meeting = self.get_object()
        if not meeting.transcript.strip():
            return Response({"detail": "A reunião não tem transcrição."}, status=400)
        # **Antes** da IA, e não dentro do coletor: recusar depois de chamar o provedor gastaria a
        # cota diária de quem clicou por um trabalho que já se sabia que seria descartado.
        ja_mapeados = Process.objects.filter(
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
            account = meeting.project.engagement.account
            # A extração entra **depois** do que já foi mapeado à mão: `position` é a ordem em que
            # a operação acontece, e intercalar processos vindos de um modelo no meio de uma
            # sequência que alguém montou reescreveria essa ordem sem pedir licença.
            ultima = Process.objects.filter(account=account, archived_at__isnull=True).aggregate(
                maior=Max("position")
            )["maior"]
            proxima = (ultima or 0) + 1
            criados: list[Process] = []
            for indice, bruto in enumerate(extraidos):
                processo = Process.objects.create(
                    account=account, name=bruto["name"], source_project=meeting.project,
                    source_meeting=meeting, registered_by=request.user,
                    position=proxima + indice,
                )
                ProcessStep.objects.bulk_create([
                    ProcessStep(process=processo, position=posicao, **etapa)
                    for posicao, etapa in enumerate(bruto["etapas"], start=1)
                ])
                if bruto["achados"]:
                    # **A fonte, uma por processo: a reunião.** `raw_excerpt` fica vazio de
                    # propósito e o que sobra é o localizador — o modelo devolve o achado já
                    # interpretado, nunca o trecho que o gerou, e gravar a conclusão aqui refaria
                    # a fusão que o split desfaz (FDD 045). A linha por achado é o `Finding` logo
                    # abaixo; a `Evidence` diz só de onde ele veio.
                    evidence = Evidence.objects.create(
                        account=account, process=processo, kind=Evidence.Kind.INTERVIEW,
                        reference=(
                            meeting.recording_url
                            or f"Reunião #{meeting.pk} — {meeting.title}"
                        )[:500],
                        source_meeting=meeting, captured_by=request.user,
                    )
                    for achado in bruto["achados"]:
                        # Um `Finding` por achado, sempre em `hypothesis` — o modelo lê *o que foi
                        # dito*, não prova, e promover a fato é ato de gente (§6.9). A `Evidence`
                        # logo acima diz de onde ele veio, e o `evidences.add` os liga: é essa
                        # evidência viva que uma promoção futura vai exigir.
                        #
                        # Até a Fase 6 (ADR 0052) havia uma terceira gravação aqui — a `Evidencia`
                        # fundida —, mantida porque o custo do estado atual e a tela liam dela. Com
                        # o legado removido e o custo repontado para o `Finding` (`process.py`), a
                        # gravação dupla deixou de existir: sobra o par do split, que é o dado
                        # canônico.
                        achado_novo = Finding.objects.create(
                            account=account, process=processo, statement=achado,
                            epistemic_status=Finding.EpistemicStatus.HYPOTHESIS,
                        )
                        achado_novo.evidences.add(evidence)
                criados.append(processo)
            # A chave do corpo **troca** por versão, em vez de conviver: duplicar a lista inteira
            # em duas chaves pagaria o corpo duas vezes, e aqui — ao contrário do resto do payload
            # legado — não há um par que saia junto. Na `/api/v1/` continua `processos`; na
            # `/api/v2/` é `processes`, o nome canônico (`docs/ontology/aliases.md` §2c, issue #122
            # fatia 3a).
            chave = "processes" if versao_de(request) == V2 else "processos"
            return {chave: ProcessSerializer(criados, many=True).data}

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
    queryset = Decisao.objects.select_related("project", "project_phase", "source_meeting").all()
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


class SatisfactionRecordViewSet(QueryParamFilterMixin, ArchiveModelViewSet):
    """Satisfação do cliente (FDD 037): o sinal que vem da outra parte da relação.

    **Sem `ProjectScopedMixin`**, ao contrário do `RiscoViewSet` logo acima, porque o vínculo
    obrigatório aqui é com o cliente e o projeto é opcional — o mixin recortaria por um campo que
    pode estar vazio e esconderia justamente o cliente que não está mais em entrega, que é onde a
    cobrança dói. O recorte é o do `ActivityViewSet`: a Entrega enxerga o cliente de que participa
    por algum projeto.
    """

    resource = "satisfaction_record"
    queryset = SatisfactionRecord.objects.select_related(
        "account", "project", "source_meeting", "source_activity", "registered_by"
    ).all()
    serializer_class = SatisfactionRecordSerializer
    filter_fields = ("account", "project")
    filter_field_aliases = {"account": "client"}
    # `nivel` e `fonte` em `filter_exact_fields` e não em `filter_fields` pelo motivo do `status`
    # do `RiscoViewSet`: aquele só aplica o filtro quando o valor é dígito, e `?fonte=declared`
    # cairia no chão sem erro nenhum — a lista voltaria inteira, com a percebida junto.
    filter_exact_fields = ("nivel", "fonte")
    # Os mesmos mapas que o serializer usa para o corpo (`VALORES_DE_ENTRADA`), por referência e
    # não por cópia — pelo motivo da fatia 5.1: duas tabelas do valor legado seriam o mesmo fato
    # divergindo em silêncio no dia em que uma fosse editada sem a outra. É o primeiro viewset com
    # **dois** campos no mapa, e é por isso que ele sempre foi campo → valores.
    filter_valores_legados = SatisfactionRecordSerializer.VALORES_DE_ENTRADA

    def get_queryset(self):  # type: ignore[no-untyped-def]
        # Mesma fronteira da `Activity`: a Entrega só enxerga clientes com projeto seu.
        queryset = super().get_queryset()
        scope = project_scope_q(self.request.user, "account__engagements__projects")
        return queryset.filter(scope).distinct() if scope else queryset

    def _assert_cliente_no_escopo(self, account: Account | None) -> None:
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
        if account is None or not Project.objects.visible_to(user).filter(engagement__account=account).exists():
            raise PermissionDenied("Você não participa de nenhum projeto deste cliente.")

    def perform_create(self, serializer: SatisfactionRecordSerializer) -> None:
        self._assert_cliente_no_escopo(serializer.validated_data.get("account"))
        serializer.save(registered_by=self.request.user)

    def perform_update(self, serializer: SatisfactionRecordSerializer) -> None:
        # Só quando o corpo tenta *mudar* o cliente — o caminho inverso, que o
        # `ProjectScopedMixin` também fecha: mover um registro próprio para um cliente alheio.
        if "account" in serializer.validated_data:
            self._assert_cliente_no_escopo(serializer.validated_data.get("account"))
        super().perform_update(serializer)


def _exige_cliente_no_escopo(user: User, account: Account | None) -> None:
    """A metade de **escrita** da fronteira do Discovery estruturado (FDD 039).

    Função e não método porque os três recursos abaixo fazem a mesma pergunta a partir de âncoras
    diferentes (o processo tem o cliente; a etapa e a evidência chegam a ele pelo processo pai), e
    três cópias divergiriam na primeira correção. O argumento é o do `_assert_cliente_no_escopo`
    da `SatisfactionRecordViewSet`: só a leitura é contornável de graça — sem a guarda de escrita,
    uma requisição bastaria para mapear processo, etapa e evidência dentro do cliente que a
    listagem esconde.

    A pergunta sai de `visible_to` (ADR 0010), a única expressão da regra.
    """
    if user.is_admin_role or user.role != User.Role.DELIVERY:
        return
    if account is None or not Project.objects.visible_to(user).filter(engagement__account=account).exists():
        raise PermissionDenied("Você não participa de nenhum projeto deste cliente.")


class ProcessViewSet(PublicationMixin, QueryParamFilterMixin, ArchiveModelViewSet):
    """O processo da operação do cliente, mapeado no Discovery (FDD 039).

    **Sem `ProjectScopedMixin`**, pelo motivo do `SatisfactionRecordViewSet` acima: não há FK de
    projeto aqui, e não há por design — o mapa é da empresa e sobrevive à venda que o descobriu. O
    recorte é o mesmo: a Entrega enxerga o cliente de que participa por algum projeto.

    O AS-IS também passou a ter marca de publicável (FDD 051, ADR 0060): "validado", na §3 do mapa
    de linguagem, era qualificador sem lastro nenhum no schema.
    """

    resource = "process"
    queryset = Process.objects.select_related(
        "account", "source_project", "source_meeting", "registered_by", "published_by"
    ).all()
    serializer_class = ProcessSerializer
    filter_fields = ("account",)
    filter_field_aliases = {"account": "client"}

    def get_queryset(self):  # type: ignore[no-untyped-def]
        queryset = super().get_queryset()
        scope = project_scope_q(self.request.user, "account__engagements__projects")
        return queryset.filter(scope).distinct() if scope else queryset

    def perform_create(self, serializer: ProcessSerializer) -> None:
        _exige_cliente_no_escopo(self.request.user, serializer.validated_data.get("account"))
        serializer.save(registered_by=self.request.user)

    def perform_update(self, serializer: ProcessSerializer) -> None:
        # Só quando o corpo tenta *mudar* o cliente — o caminho inverso: mover um processo próprio
        # para um cliente alheio seria o atalho para escrever lá dentro.
        if "account" in serializer.validated_data:
            _exige_cliente_no_escopo(self.request.user, serializer.validated_data.get("account"))
        super().perform_update(serializer)

    def perform_destroy(self, instance: Process) -> None:
        """Recusa arquivar o mapa que ancora achado ou dor publicados (FDD 051).

        A porta do `DELETE` da mesma dimensão do `unpublish/`: arquivar some da projeção
        exatamente como despublicar, e `findings[].process_id` passaria a apontar para o que não
        está mais em `processes[]`.

        **A guarda vem antes de `archive()`, e a ordem é o cuidado**: aquele cascateia para as
        etapas no mesmo instante (FDD 039), então recusar depois já teria escondido metade do
        mapa. É a primeira guarda deste viewset — até aqui nada dependia do processo para poder
        ser mostrado.
        """
        self.recusa_se_sustenta_publicado(instance)
        instance.archive()

    @extend_schema(
        responses=inline_serializer("ProcessUnarchived", {"id": serializers.IntegerField()}),
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


class ProcessStepViewSet(QueryParamFilterMixin, ArchiveModelViewSet):
    """As etapas do processo, descritas pelo P-S-D-T-E-R (FDD 039)."""

    resource = "process_step"
    queryset = ProcessStep.objects.select_related("process", "process__account").all()
    serializer_class = ProcessStepSerializer
    filter_fields = ("process",)
    filter_field_aliases = {"process": "processo"}

    def get_queryset(self):  # type: ignore[no-untyped-def]
        queryset = super().get_queryset()
        scope = project_scope_q(self.request.user, "process__account__engagements__projects")
        return queryset.filter(scope).distinct() if scope else queryset

    def perform_create(self, serializer: ProcessStepSerializer) -> None:
        # O cliente é resolvido **pelo processo pai**: é dele que a etapa herda a fronteira, e é
        # por ele que ela vazaria se ninguém perguntasse.
        processo = serializer.validated_data.get("process")
        _exige_cliente_no_escopo(self.request.user, processo.account if processo else None)
        serializer.save()

    def perform_update(self, serializer: ProcessStepSerializer) -> None:
        if "process" in serializer.validated_data:
            processo = serializer.validated_data.get("process")
            _exige_cliente_no_escopo(self.request.user, processo.account if processo else None)
        super().perform_update(serializer)


# `outcome` da avaliação → `status` do lead. O mapa é explícito porque as duas escalas existiam
# antes uma da outra: `nurture` cai em "contatado" (o lead segue no radar, sem decisão tomada) e
# não em "qualificado", que afirmaria uma venda que ninguém abriu.
STATUS_POR_OUTCOME = {
    Qualification.Outcome.QUALIFIED: Lead.Status.QUALIFIED,
    Qualification.Outcome.NURTURE: Lead.Status.CONTACTED,
    Qualification.Outcome.DISQUALIFIED: Lead.Status.DISCARDED,
}

class DiscoveryViewSet(ProjectScopedMixin, QueryParamFilterMixin, ArchiveModelViewSet):
    """O Discovery como unidade de levantamento (FDD 045).

    **Com `ProjectScopedMixin`**, ao contrário do `ProcessViewSet` logo acima, e a diferença é a
    âncora: o processo é do cliente e sobrevive à venda; o Discovery é o levantamento contratado,
    e ele tem projeto. Quem participa do projeto vê e escreve o Discovery dele — leitura e escrita
    pela mesma guarda, como em todo recurso de projeto.
    """

    resource = "discovery"
    queryset = Discovery.objects.select_related("project", "project__engagement__account", "owner").all()
    serializer_class = DiscoverySerializer
    filter_fields = ("project", "owner")
    filter_exact_fields = ("status",)


class DiscoverySessionViewSet(ProjectScopedMixin, QueryParamFilterMixin, ArchiveModelViewSet):
    """As sessões de um Discovery (FDD 045)."""

    resource = "discovery_session"
    queryset = DiscoverySession.objects.select_related(
        "discovery", "discovery__project", "meeting"
    ).all()
    serializer_class = DiscoverySessionSerializer
    project_path = "discovery__project"  # a sessão não carrega o projeto direto
    scope_payload_field = "discovery"
    filter_fields = ("discovery", "meeting")

    def scoped_project(self, validated_data: dict) -> Project | None:
        discovery = validated_data.get("discovery")
        return discovery.project if discovery else None


class ProcessObservationViewSet(ProjectScopedMixin, QueryParamFilterMixin, ArchiveModelViewSet):
    """A observação de um processo dentro de um Discovery (FDD 045).

    Duas fronteiras, e não uma: o Discovery traz a do **projeto** (é o `ProjectScopedMixin`), e o
    processo traz a da **conta**. Sem a segunda, uma requisição bastaria para pendurar o processo
    de outro cliente num Discovery próprio — o mesmo caminho que `_exige_cliente_no_escopo` fecha
    nos três recursos da FDD 039.
    """

    resource = "process_observation"
    queryset = ProcessObservation.objects.select_related(
        "discovery", "discovery__project", "process", "process__account", "source_session"
    ).all()
    serializer_class = ProcessObservationSerializer
    project_path = "discovery__project"
    scope_payload_field = "discovery"
    filter_fields = ("discovery", "process")
    filter_exact_fields = ("observation_type",)

    def scoped_project(self, validated_data: dict) -> Project | None:
        discovery = validated_data.get("discovery")
        return discovery.project if discovery else None

    def perform_create(self, serializer: ProcessObservationSerializer) -> None:
        self._exige_processo_no_escopo(serializer.validated_data)
        # `super()` e não `serializer.save()`: quem checa o projeto é o mixin, e reimplementar o
        # `perform_create` aqui era exatamente como a guarda de escopo passava despercebida.
        super().perform_create(serializer)

    def perform_update(self, serializer: ProcessObservationSerializer) -> None:
        if "process" in serializer.validated_data:
            self._exige_processo_no_escopo(serializer.validated_data)
        super().perform_update(serializer)

    def _exige_processo_no_escopo(self, validated_data: dict) -> None:
        processo = validated_data.get("process")
        _exige_cliente_no_escopo(self.request.user, processo.account if processo else None)


class EvidenceViewSet(PublicationMixin, QueryParamFilterMixin, ArchiveModelViewSet):
    """O dado bruto que sustenta um achado (FDD 045).

    **Sem `ProjectScopedMixin`**, como o `ProcessViewSet`: a evidência é da conta, e o Discovery
    dela é opcional — uma evidência levantada fora de um Discovery formal continua sendo
    evidência. O recorte é o mesmo dos três recursos da FDD 039, com a conta alcançada pelo
    `account` em vez de pelo processo pai.
    """

    resource = "evidence"
    queryset = Evidence.objects.select_related(
        "account", "discovery", "process", "step", "source_session", "source_meeting",
        "captured_by", "published_by",
    ).all()
    serializer_class = EvidenceSerializer
    filter_fields = ("account", "discovery", "process", "step", "source_session")
    # `kind` em `filter_exact_fields`, e não em `filter_fields`: o teste de dígito de
    # `filter_fields` derrubaria `?kind=interview` no chão sem erro nenhum, e a lista voltaria
    # inteira.
    filter_exact_fields = ("kind",)

    def get_queryset(self):  # type: ignore[no-untyped-def]
        queryset = super().get_queryset()
        scope = project_scope_q(self.request.user, "account__engagements__projects")
        return queryset.filter(scope).distinct() if scope else queryset

    def perform_create(self, serializer: EvidenceSerializer) -> None:
        _exige_cliente_no_escopo(self.request.user, serializer.validated_data.get("account"))
        serializer.save(captured_by=self.request.user)

    def perform_update(self, serializer: EvidenceSerializer) -> None:
        if "account" in serializer.validated_data:
            _exige_cliente_no_escopo(self.request.user, serializer.validated_data.get("account"))
        super().perform_update(serializer)

    def perform_destroy(self, instance: Evidence) -> None:
        """Recusa arquivar a **última** evidência viva de um achado que já é fato (FDD 045).

        A invariante §6.9 da ontologia diz que um `Finding` em `fact` tem revisor humano e ao
        menos uma `Evidence` viva. Arquivar a última sem olhar deixaria o fato de pé sem nada
        embaixo — e nada ficaria vermelho: o achado continuaria dizendo "fato" na tela e na
        proposta, com a evidência escondida. É o mesmo defeito que a FDD 025 chama de órfão
        visível, aqui com uma agravante: o órfão é uma **afirmação** sobre a operação do cliente.

        Recusar em vez de rebaixar o achado, pelo argumento da exclusão de etapa do pipeline:
        rebaixar em silêncio desfaria uma promoção que uma pessoa fez, sem que ela pedisse. O 409
        diz qual é o estado que impede e como sair dele — rebaixe o achado, ou registre outra
        evidência.

        **Duas dimensões, e a segunda entrou em cima da primeira** (FDD 051): a de baixo pergunta
        se sobra evidência viva para o fato, a de cima se sobra evidência **publicada** para o
        fato **publicado**. Um arquivamento pode passar na primeira e cair na segunda — é o caso
        do fato publicado com duas evidências, uma publicada e uma interna.
        """
        self.recusa_se_sustenta_publicado(instance)
        presos = [
            finding
            for finding in instance.findings.filter(
                epistemic_status=Finding.EpistemicStatus.FACT, archived_at__isnull=True
            )
            if not finding.evidences.filter(archived_at__isnull=True)
            .exclude(pk=instance.pk)
            .exists()
        ]
        if presos:
            raise StateConflict(
                f"Esta é a última evidência viva de {len(presos)} achado(s) registrado(s) como "
                "fato. Rebaixe o achado para hipótese ou registre outra evidência antes de "
                "arquivar esta."
            )
        instance.archive()


class FindingViewSet(PublicationMixin, QueryParamFilterMixin, ArchiveModelViewSet):
    """O achado com o estado epistemológico da ontologia (FDD 045, ADR 0049).

    Mesmo recorte de conta da `EvidenceViewSet`. As invariantes de promoção a `fact` e de
    transição vivem no serializer, que é onde o M2M já existe.
    """

    resource = "finding"
    queryset = Finding.objects.select_related(
        "account", "process", "step", "reviewed_by", "published_by"
    ).prefetch_related("evidences").all()
    serializer_class = FindingSerializer
    filter_fields = ("account", "process", "step")
    filter_exact_fields = ("epistemic_status",)

    def get_queryset(self):  # type: ignore[no-untyped-def]
        queryset = super().get_queryset()
        scope = project_scope_q(self.request.user, "account__engagements__projects")
        return queryset.filter(scope).distinct() if scope else queryset

    def perform_create(self, serializer: FindingSerializer) -> None:
        _exige_cliente_no_escopo(self.request.user, serializer.validated_data.get("account"))
        serializer.save()

    def perform_update(self, serializer: FindingSerializer) -> None:
        if "account" in serializer.validated_data:
            _exige_cliente_no_escopo(self.request.user, serializer.validated_data.get("account"))
        super().perform_update(serializer)

    def perform_destroy(self, instance: Finding) -> None:
        """Recusa arquivar o **último** achado vivo de uma dor confirmada (FDD 048).

        A terceira metade da invariante de `PainPoint.status=confirmed`, e a razão de ela existir
        é a mesma que fez a `EvidenceViewSet` ganhar esta guarda logo acima: sem ela a invariante
        vaza pelo `DELETE`. Uma dor confirmada sem achado vivo continua dizendo "confirmado" na
        tela e na priorização, com o que a sustentava escondido — e nada fica vermelho.

        Recusar em vez de rebaixar a dor, pelo argumento da FDD 045: desfazer em silêncio uma
        confirmação que uma pessoa fez, sem que ela peça, é pior que o 409 que diz qual é o estado
        que impede e como sair dele.

        A dimensão da publicação entra **em cima** desta, e não no lugar dela (FDD 051): uma
        pergunta é se sobra achado vivo para a dor confirmada, a outra se sobra achado publicado
        para a dor publicada.
        """
        self.recusa_se_sustenta_publicado(instance)
        presas = [
            dor
            for dor in instance.pain_points.filter(
                status=PainPoint.Status.CONFIRMED, archived_at__isnull=True
            )
            if not dor.findings.filter(archived_at__isnull=True)
            .exclude(pk=instance.pk)
            .exists()
        ]
        if presas:
            raise StateConflict(
                f"Este é o último achado vivo de {len(presas)} dor(es) confirmada(s). Volte a dor "
                "para observada ou registre outro achado antes de arquivar este."
            )
        instance.archive()


class PainPointViewSet(PublicationMixin, QueryParamFilterMixin, ArchiveModelViewSet):
    """A dor observada na operação do cliente (FDD 048).

    **Sem `ProjectScopedMixin`**, como `Evidence` e `Finding` e pelo mesmo motivo: a dor é da
    conta, e o processo dela é opcional. O recorte da Entrega é o mesmo dos dois — a conta
    alcançada pelo campo `account`, e não por um pai a resolver.
    """

    resource = "pain_point"
    queryset = PainPoint.objects.select_related(
        "account", "process", "step", "published_by"
    ).prefetch_related("findings").all()
    serializer_class = PainPointSerializer
    filter_fields = ("account", "process", "step")
    # `status` e `impact_type` em `filter_exact_fields` pelo motivo do `kind` da `Evidence`: o
    # teste de dígito de `filter_fields` derrubaria `?status=confirmed` no chão sem erro nenhum.
    filter_exact_fields = ("status", "impact_type")

    def get_queryset(self):  # type: ignore[no-untyped-def]
        queryset = super().get_queryset()
        scope = project_scope_q(self.request.user, "account__engagements__projects")
        return queryset.filter(scope).distinct() if scope else queryset

    def perform_create(self, serializer: PainPointSerializer) -> None:
        _exige_cliente_no_escopo(self.request.user, serializer.validated_data.get("account"))
        serializer.save()

    def perform_update(self, serializer: PainPointSerializer) -> None:
        if "account" in serializer.validated_data:
            _exige_cliente_no_escopo(self.request.user, serializer.validated_data.get("account"))
        super().perform_update(serializer)

    def perform_destroy(self, instance: PainPoint) -> None:
        """Recusa arquivar a **última** dor publicada de uma oportunidade publicada (FDD 051).

        A guarda que faltava — as irmãs de `Evidence` e `Finding` já existiam para a dimensão do
        `fact`/`confirmed`, e a dor não tinha nenhuma porque nada dependia dela dentro da casa. A
        publicação criou essa dependência: `improvement_opportunities[].pain_point_ids` só lista
        as dores publicadas e vivas, e arquivar a última deixaria uma oportunidade de pé no One
        com uma lista vazia embaixo.
        """
        self.recusa_se_sustenta_publicado(instance)
        instance.archive()


class ImprovementOpportunityViewSet(
    PublicationMixin, QueryParamFilterMixin, ArchiveModelViewSet
):
    """A oportunidade de melhoria — **e ela não é venda** (FDD 048).

    Nenhum filtro, nenhum campo e nenhum import de `PipelineStage` aqui: o mapa de linguagem §5
    bane `Opportunity` sem qualificador justamente porque as duas colidiam. O funil comercial vive
    na `CommercialOpportunityViewSet`, e as duas rotas não se encostam.

    Mesmo recorte de conta da `PainPointViewSet`.
    """

    resource = "improvement_opportunity"
    queryset = ImprovementOpportunity.objects.select_related(
        "account", "engagement", "published_by"
    ).prefetch_related("pain_points", "assessments").all()
    serializer_class = ImprovementOpportunitySerializer
    filter_fields = ("account", "engagement")
    filter_exact_fields = ("status",)

    def get_queryset(self):  # type: ignore[no-untyped-def]
        queryset = super().get_queryset()
        scope = project_scope_q(self.request.user, "account__engagements__projects")
        return queryset.filter(scope).distinct() if scope else queryset

    def perform_create(self, serializer: ImprovementOpportunitySerializer) -> None:
        _exige_cliente_no_escopo(self.request.user, serializer.validated_data.get("account"))
        serializer.save()

    def perform_update(self, serializer: ImprovementOpportunitySerializer) -> None:
        if "account" in serializer.validated_data:
            _exige_cliente_no_escopo(self.request.user, serializer.validated_data.get("account"))
        super().perform_update(serializer)


class PriorityAssessmentViewSet(QueryParamFilterMixin, ArchiveModelViewSet):
    """A avaliação de prioridade — **criada, nunca editada** (FDD 048, ADR 0054).

    `http_method_names` não inclui `put` nem `patch`, e é isso que faz a imutabilidade ser um 405
    ("este método não existe aqui") em vez de um 400 ("corrija o corpo"). Repriorizar é `POST` de
    uma versão nova; a anterior fica de pé, que é a razão de o modelo ser versionado.

    `DELETE` continua sendo o arquivamento da FDD 025: uma avaliação registrada por engano sai da
    listagem sem sumir do histórico — e o número de versão dela **não** é reaproveitado.
    """

    resource = "priority_assessment"
    queryset = PriorityAssessment.objects.select_related(
        "improvement_opportunity", "improvement_opportunity__account", "assessed_by"
    ).all()
    serializer_class = PriorityAssessmentSerializer
    filter_fields = ("improvement_opportunity",)
    filter_exact_fields = ("formula_key",)
    http_method_names = ["get", "post", "delete", "head", "options"]

    def get_queryset(self):  # type: ignore[no-untyped-def]
        queryset = super().get_queryset()
        scope = project_scope_q(
            self.request.user, "improvement_opportunity__account__engagements__projects"
        )
        return queryset.filter(scope).distinct() if scope else queryset

    def perform_create(self, serializer: PriorityAssessmentSerializer) -> None:
        oportunidade = serializer.validated_data.get("improvement_opportunity")
        _exige_cliente_no_escopo(
            self.request.user, oportunidade.account if oportunidade else None
        )
        # `assessed_by` sai da sessão, como `captured_by` na `Evidence`: quem avaliou tem nome, e
        # o nome é o de quem está autenticado. Não é o `reviewed_by` do `Finding`, que vem do
        # corpo porque responde "quem confirmou" e pode não ser quem digita.
        serializer.save(assessed_by=self.request.user)


class SolutionHypothesisViewSet(QueryParamFilterMixin, ArchiveModelViewSet):
    """As hipóteses concorrentes de solução (FDD 048).

    Mesmo recorte, um hop a mais: a conta chega pela oportunidade.
    """

    resource = "solution_hypothesis"
    queryset = SolutionHypothesis.objects.select_related(
        "improvement_opportunity", "improvement_opportunity__account"
    ).all()
    serializer_class = SolutionHypothesisSerializer
    filter_fields = ("improvement_opportunity",)
    filter_exact_fields = ("status",)

    def get_queryset(self):  # type: ignore[no-untyped-def]
        queryset = super().get_queryset()
        scope = project_scope_q(
            self.request.user, "improvement_opportunity__account__engagements__projects"
        )
        return queryset.filter(scope).distinct() if scope else queryset

    def perform_create(self, serializer: SolutionHypothesisSerializer) -> None:
        oportunidade = serializer.validated_data.get("improvement_opportunity")
        _exige_cliente_no_escopo(
            self.request.user, oportunidade.account if oportunidade else None
        )
        serializer.save()

    def perform_update(self, serializer: SolutionHypothesisSerializer) -> None:
        if "improvement_opportunity" in serializer.validated_data:
            oportunidade = serializer.validated_data.get("improvement_opportunity")
            _exige_cliente_no_escopo(
                self.request.user, oportunidade.account if oportunidade else None
            )
        super().perform_update(serializer)


class FeasibilityAssessmentViewSet(ProjectScopedMixin, QueryParamFilterMixin, ArchiveModelViewSet):
    """O laudo que sustenta o gate de Feasibility (FDD 049).

    **Com `ProjectScopedMixin`**, ao contrário dos quatro da Fase 4: o laudo pende de um projeto —
    é *neste* trabalho que a avaliação aconteceu —, e o recorte da Entrega é o de sempre
    (`ProjectMember`). A hipótese é da conta e chega junto, mas quem responde pela fronteira é o
    projeto; validar as duas pontas é o que o `clean()`/`validate` fazem.
    """

    resource = "feasibility_assessment"
    queryset = FeasibilityAssessment.objects.select_related(
        "solution_hypothesis", "solution_hypothesis__improvement_opportunity", "project"
    ).prefetch_related("evidence").all()
    serializer_class = FeasibilityAssessmentSerializer
    filter_fields = ("project", "solution_hypothesis")
    # `gate_decision` em `filter_exact_fields` pelo motivo do `kind` da `Evidence`: o teste de
    # dígito de `filter_fields` derrubaria `?gate_decision=go` no chão sem erro nenhum, e a lista
    # voltaria inteira.
    filter_exact_fields = ("gate_decision",)


class ProveExperimentViewSet(ProjectScopedMixin, QueryParamFilterMixin, ArchiveModelViewSet):
    """O experimento do PROVE, e a invariante de início (FDD 049, decisão E1 do DAP)."""

    resource = "prove_experiment"
    queryset = ProveExperiment.objects.select_related(
        "solution_hypothesis", "solution_hypothesis__improvement_opportunity", "project",
        "gap_waiver_by",
    ).prefetch_related("kpis__measurements").all()
    serializer_class = ProveExperimentSerializer
    filter_fields = ("project", "solution_hypothesis")
    filter_exact_fields = ("status", "gate_decision")

    @extend_schema(responses=ProveExperimentSerializer, request=None)
    @action(detail=True, methods=["post"])
    def start(self, request: Request, pk: str | None = None) -> Response:
        """Inicia o PROVE, conferindo KPI, critério de sucesso e baseline (FDD 049).

        **Uma action, e não um `PATCH` de `status`**, pela razão exata de `journey.apply_gate`
        (ADR 0053): a validação depende do **estado corrente** — quais KPIs pendem deste
        experimento e quais deles já têm baseline viva —, e só quem conhece esse estado pode fazer
        a pergunta. Um `PATCH` gravaria `running` sem ela, e a invariante viraria sugestão.

        Três recusas, com o status que cada uma merece:

        - **409** se o experimento já está em execução ou concluído: o pedido está bem formado, o
          que impede é o estado (`StateConflict`);
        - **400** listando **o que falta**, quando não há lacuna aprovada: aqui é o estado do
          experimento que precisa mudar, mas a recusa é sobre o pedido de *iniciar agora* — é a
          mesma escolha de `apply_gate`, que devolve 400 para a decisão fora do vocabulário;
        - **400** quando há `gap_waiver` sem `gap_waiver_by`: lacuna aprovada é ato assinado, e sem
          autor "alguém aprovou" é alegação de ninguém — a mesma regra do trio de consentimento do
          `Case`.

        A lacuna se registra no próprio experimento (`PATCH` com `gap_waiver` e `gap_waiver_by`) e
        esta ação **lê** o estado, como `apply_gate` lê a fase ativa. `gap_waiver_at` é carimbado
        aqui: é o instante em que a lacuna passou a valer.
        """
        experimento = self.get_object()
        if experimento.status != ProveExperiment.Status.PLANNED:
            raise StateConflict(
                f"Este PROVE já está em {experimento.get_status_display().lower()}. "
                "Só um experimento planejado pode ser iniciado."
            )
        lacuna = (experimento.gap_waiver or "").strip()
        if lacuna and experimento.gap_waiver_by_id is None:
            raise InvalidInput(
                "Lacuna aprovada é ato assinado: informe em `gap_waiver_by` quem a aprovou."
            )
        faltas = prove.o_que_falta_para_iniciar(experimento)
        if faltas and not lacuna:
            raise InvalidInput(
                f"O PROVE não começa sem {prove.frase_do_que_falta(faltas)}. Registre o que falta "
                "ou uma lacuna aprovada (`gap_waiver` e `gap_waiver_by`)."
            )
        experimento.status = ProveExperiment.Status.RUNNING
        campos = ["status", "updated_at"]
        if experimento.started_at is None:
            experimento.started_at = timezone.localdate()
            campos.append("started_at")
        if lacuna and experimento.gap_waiver_at is None:
            experimento.gap_waiver_at = timezone.now()
            campos.append("gap_waiver_at")
        experimento.save(update_fields=campos)
        return Response(ProveExperimentSerializer(experimento).data)


class KPIViewSet(ProjectScopedMixin, QueryParamFilterMixin, ArchiveModelViewSet):
    """O indicador (FDD 049, ADR 0055).

    O recorte é pelo **projeto**, que é a âncora obrigatória do KPI. `prove_experiment` é opcional
    e por isso não serve de caminho para o escopo: um `project_path` que passasse por ele deixaria
    de fora exatamente o KPI migrado, que não tem experimento nenhum.
    """

    resource = "kpi"
    queryset = KPI.objects.select_related("project", "prove_experiment", "owner").all()
    serializer_class = KPISerializer
    filter_fields = ("project", "prove_experiment")
    filter_exact_fields = ("unit", "direction")

    def perform_destroy(self, instance: KPI) -> None:
        """Arquiva o KPI **e as medições dele**, ou recusa — nunca deixa órfão (FDD 025).

        As medições são listadas por conta própria (`/measurements/?kpi=`), então arquivar só o pai
        deixaria linhas visíveis apontando para um KPI que a interface esconde. A regra do
        `CLAUDE.md` dá duas saídas legítimas, e as duas se aplicam aqui em ordem:

        - **recusar** quando uma `ValueLedgerEntry` viva pende de alguma medição deste KPI. Arquivar
          ali esvaziaria por baixo uma afirmação de valor que alguém pode ter aprovado — é o mesmo
          argumento do último achado de uma dor confirmada (FDD 048), com dinheiro em cima;
        - **arquivar junto, na mesma transação**, no caso normal: uma leitura não tem vida fora do
          indicador que a define.
        """
        vivas = instance.measurements.filter(archived_at__isnull=True)
        presas = ValueLedgerEntry.objects.filter(
            outcome_measurement__in=vivas, archived_at__isnull=True
        ).count()
        if presas:
            raise StateConflict(
                f"{presas} entrada(s) de valor ainda pendem das medições deste KPI. Arquive as "
                "entradas antes de arquivar o indicador que as sustenta."
            )
        with transaction.atomic():
            agora = timezone.now()
            vivas.update(archived_at=agora, updated_at=agora)
            instance.archive()


class MeasurementViewSet(ProjectScopedMixin, QueryParamFilterMixin, ArchiveModelViewSet):
    """As leituras de um KPI — baseline, outcome e monitoramento (FDD 049).

    O projeto chega pelo KPI, um hop a mais; `scope_payload_field = "kpi"` é o que faz a guarda de
    escrita do mixin olhar a chave certa — sem ela, registrar uma medição num KPI alheio seria
    escrita fora do escopo passando pelo `perform_create`.
    """

    resource = "measurement"
    project_path = "kpi__project"
    scope_payload_field = "kpi"
    queryset = Measurement.objects.select_related("kpi", "kpi__project").prefetch_related(
        "source_evidence"
    ).all()
    serializer_class = MeasurementSerializer
    filter_fields = ("kpi",)
    filter_exact_fields = ("kind",)

    def scoped_project(self, validated_data: dict) -> Project | None:
        kpi = validated_data.get("kpi")
        return kpi.project if kpi else None

    def perform_destroy(self, instance: Measurement) -> None:
        """Recusa arquivar a medição de que uma entrada de valor viva ainda depende (FDD 025).

        O `PROTECT` do modelo impede o apagamento **real**, e o `api_exception_handler` o traduz em
        409 se algum caminho chegar lá. Mas a API não apaga: ela arquiva — e sem esta guarda a
        entrada de valor continuaria de pé, na listagem, apontando para uma medição que a interface
        esconde. É o órfão visível da FDD 025, aqui sustentando um número que a casa afirma ao
        cliente.
        """
        presas = instance.value_entries.filter(archived_at__isnull=True).count()
        if presas:
            raise StateConflict(
                f"{presas} entrada(s) de valor apontam para esta medição. Arquive as entradas "
                "antes de arquivar o Outcome que as sustenta."
            )
        instance.archive()


class ValueLedgerEntryViewSet(QueryParamFilterMixin, ArchiveModelViewSet):
    """O Value Ledger da conta (FDD 049, `language-map` §6.11 e §6.12).

    **Sem `ProjectScopedMixin`, e é o desvio consciente desta fatia.** A entrada pende de um
    `Engagement` e o `project` é opcional — um mixin com `project_path="project"` esconderia da
    Entrega toda entrada de mandato que ninguém conseguiu atribuir a um projeto, e a permissão de
    objeto devolveria 403 no detalhe de uma linha que a listagem mostra. É exatamente o defeito que
    `SatisfactionRecordViewSet` já previu, e por isso os quatro irmãos entram em `PROJECT_OF` e
    esta não.

    **O engajamento não é fronteira de acesso** (ADR 0050): a visibilidade *deriva* de
    `Project.objects.visible_to`, nunca o contrário. Quem tem projeto vê a entrada do projeto; e a
    entrada sem projeto é vista por quem alcança algum projeto daquele mandato — a mesma pergunta
    inversa que `EngagementViewSet.get_queryset` faz, e a única expressão da regra (ADR 0010).
    """

    resource = "value_ledger_entry"
    queryset = ValueLedgerEntry.objects.select_related(
        "engagement", "engagement__account", "project", "outcome_measurement",
        "outcome_measurement__kpi", "approved_by",
    ).all()
    serializer_class = ValueLedgerEntrySerializer
    filter_fields = ("engagement", "project", "outcome_measurement")
    filter_exact_fields = ("status", "value_type")

    def get_queryset(self):  # type: ignore[no-untyped-def]
        queryset = super().get_queryset()
        user = self.request.user
        if user.is_admin_role or user.role != User.Role.DELIVERY:
            return queryset
        visiveis = Project.objects.visible_to(user)
        return queryset.filter(
            Q(project__in=visiveis) | Q(project__isnull=True, engagement__projects__in=visiveis)
        ).distinct()

    def _exige_escopo(self, validated_data: dict) -> None:
        """A metade de **escrita** do mesmo recorte.

        Só a leitura seria contornável em uma requisição: sem esta guarda, criar a entrada de valor
        de um mandato alheio bastaria para escrever dentro do que a listagem esconde — o argumento
        de `_exige_cliente_no_escopo` e do `ProjectScopedMixin`.
        """
        user = self.request.user
        if user.is_admin_role or user.role != User.Role.DELIVERY:
            return
        visiveis = Project.objects.visible_to(user)
        projeto = validated_data.get("project")
        engagement = validated_data.get("engagement")
        if projeto is not None:
            if visiveis.filter(pk=projeto.pk).exists():
                return
        elif engagement is not None and visiveis.filter(engagement=engagement).exists():
            return
        raise PermissionDenied("Você não participa de nenhum projeto deste engagement.")

    def perform_create(self, serializer: ValueLedgerEntrySerializer) -> None:
        self._exige_escopo(serializer.validated_data)
        serializer.save()

    def perform_update(self, serializer: ValueLedgerEntrySerializer) -> None:
        if {"engagement", "project"} & set(serializer.validated_data):
            dados = dict(serializer.validated_data)
            dados.setdefault("engagement", serializer.instance.engagement)
            dados.setdefault("project", serializer.instance.project)
            self._exige_escopo(dados)
        super().perform_update(serializer)


class LeadViewSet(ArchiveModelViewSet):
    resource = "lead"
    queryset = (
        Lead.objects.select_related("account", "commercial_opportunity")
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

        Até aqui esta ação criava, num ato só, um `Account` **e** uma `CommercialOpportunity` no
        degrau gratuito da escada. Uma conversa de qualificação entrava no funil como venda registrada,
        somava no pipeline e podia virar `Project`. A sequência normativa é
        `Lead → Qualification → (qualified) → CommercialOpportunity`, e o passo comercial passou a
        ter porta própria: `POST /qualifications/{id}/open-opportunity/`.

        Some daqui, junto com a `CommercialOpportunity`, a busca por `PipelineStage` aberto e
        pelo `Service` de entrada — e os dois 400 que elas produziam. Qualificar um lead não depende mais de o
        pipeline estar configurado.
        """
        lead = self.get_object()
        payload = LeadConvertSerializer(data=request.data)
        payload.is_valid(raise_exception=True)
        dados = payload.validated_data

        if lead.commercial_opportunity_id:
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

        if dados["account"] and lead.account_id and dados["account"].pk != lead.account_id:
            # Mover o lead para outra conta deixaria a avaliação anterior apontando para a antiga,
            # e `Qualification.clean()` passaria a recusar qualquer edição naquela linha. Corrigir
            # a conta de um lead é ato próprio, na tela do lead — não efeito de qualificá-lo.
            return Response(
                {"account_id": "Este lead já está vinculado a outra conta."}, status=400
            )

        with transaction.atomic():
            account = dados["account"] or lead.account or self._nova_conta(lead, request.user)
            lead.account = account
            lead.status = STATUS_POR_OUTCOME[dados["outcome"]]
            lead.save(update_fields=["account", "status", "updated_at"])
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

    def _nova_conta(self, lead: Lead, owner: User) -> Account:
        # A vertical que o CNAE sugere, quando o enriquecimento a trouxe e o admin já cadastrou
        # aquela vertical (FDD 030, FDD 026). Derivada aqui e não gravada no lead: o CNAE é a
        # fonte, e um segundo campo com a mesma verdade diverge no dia em que alguém corrigir só
        # um. Sem CNAE, sem mapa ou sem a vertical cadastrada, o cliente nasce sem setor — que é o
        # estado que a FDD 026 já trata, e não uma lacuna nova.
        vertical = enrichment.infer_vertical(lead.enrichment.get("cnae_code", ""))
        return Account.objects.create(
            name=lead.company or lead.name,
            owner=owner,
            # vira "Cliente" (`active`) quando a oportunidade é ganha, pelo signal
            # `_promote_account_on_won`. Entrar em `inactive` não tem automação: é escolha de
            # quem edita a conta.
            lifecycle_status=Account.LifecycleStatus.PROSPECT,
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
        request=OpenCommercialOpportunitySerializer, responses=CommercialOpportunitySerializer
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
        if contato and contato.account_id != qualification.account_id:
            return Response(
                {"contact": "O contato deve pertencer ao cliente selecionado."}, status=400
            )
        stage = (
            PipelineStage.objects.filter(kind=PipelineStage.Kind.OPEN).order_by("position").first()
        )
        if stage is None:
            return Response({"detail": "Nenhuma etapa aberta configurada."}, status=400)

        with transaction.atomic():
            opportunity = CommercialOpportunity.objects.create(
                account_id=qualification.account_id,
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
            # **`Lead.commercial_opportunity` continua sendo ligado aqui**, e não é resíduo do
            # caminho antigo: a análise de origem da FDD 030 atravessa `projeto → oportunidade → lead → source`
            # por esta chave. Movendo a criação da venda para cá sem religar o lead, todo negócio
            # nascido de lead passaria a contar como "Cadastro direto" — uma tela de decisão de
            # investimento errando em silêncio, que é o modo de falha que
            # `tests/regression/test_origem_do_lead_sobrevive_a_conversao.py` existe para pegar.
            # O vínculo canônico da fatia nova é `origin_qualification`; este é o atalho da
            # analítica, e some no dia em que ela souber ler a avaliação no meio do caminho.
            lead = qualification.lead
            if lead.commercial_opportunity_id is None:
                lead.commercial_opportunity = opportunity
                lead.save(update_fields=["commercial_opportunity", "updated_at"])
        return Response(
            CommercialOpportunitySerializer(opportunity).data, status=status.HTTP_201_CREATED
        )


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


# --- Agendamento do Discovery pelo cliente (FDD 013, DAP `dap-agendamento-discovery-r1`) ------
#
# As duas rotas abaixo são públicas e o **token é a credencial** — ele chega por e-mail a quem
# acabou de assinar o acordo de Design Partner. Sem `X-Intake-Token`, ao contrário das de
# pré-venda: ali o segredo do relay é a primeira porta porque o formulário é do site da casa;
# aqui quem abre é o cliente, direto do e-mail, e não há relay entre os dois.
#
# **Os quatro estados da decisão D1 precisam ser distinguíveis pela resposta**, cada um com seu
# `code`: a página desenha mensagem diferente para cada um, e colapsá-los faria a tela dizer
# "não há horário livre" quando o que houve foi a agenda não responder — mentira que custa uma
# reunião. Por isso `code` e não só `detail`: texto de mensagem é da superfície, e a página não
# deve ramificar por ele.
DISCOVERY_INDISPONIVEL = "Agendamento indisponível."
DISCOVERY_AGENDA_FORA = "Não foi possível consultar a agenda."


def _discovery_erro(detail: str, code: str, http_status: int) -> Response:
    return Response({"detail": detail, "code": code}, status=http_status)


def _discovery_token_response(exc: Exception) -> Response:
    """Traduz a falha do token no 400 que a página sabe desenhar."""
    if isinstance(exc, discovery_booking.TokenExpirado):
        return _discovery_erro(
            "Este link expirou.", "token_expired", status.HTTP_400_BAD_REQUEST
        )
    # Sem dizer por quê: distinguir "assinatura errada" de "mandato inexistente" para quem não
    # está autenticado é dar retorno a quem sonda (decisão D1).
    return _discovery_erro(
        "Link não reconhecido.", "token_invalid", status.HTTP_400_BAD_REQUEST
    )


def _discovery_fora_do_ar() -> Response | None:
    """503 quando a funcionalidade ou a agenda estão desligadas; `None` quando dá para seguir."""
    if not discovery_booking.is_enabled() or not calendar_sync.is_enabled():
        return _discovery_erro(
            DISCOVERY_INDISPONIVEL, "booking_disabled", status.HTTP_503_SERVICE_UNAVAILABLE
        )
    return None


class DiscoveryBookingSlotsView(APIView):
    """Horários livres para o cliente marcar o Discovery do seu mandato (rota pública)."""

    authentication_classes: list = []
    permission_classes = [AllowAny]
    throttle_classes = [ScopedRateThrottle]
    throttle_scope = "discovery_booking"

    @extend_schema(responses=inline_serializer("DiscoveryBookingSlotsResponse", {
        "account": serializers.CharField(),
        "slots": serializers.ListField(child=serializers.DateTimeField()),
        "scheduled_at": serializers.DateTimeField(allow_null=True),
    }))
    def get(self, request: Request) -> Response:
        fora = _discovery_fora_do_ar()
        if fora is not None:
            return fora
        try:
            engagement = discovery_booking.engagement_from_token(request.query_params.get("token", ""))
        except (discovery_booking.TokenExpirado, discovery_booking.TokenInvalido) as exc:
            return _discovery_token_response(exc)

        # Já marcado: a página mostra o horário e não oferece outro (decisão C1, sem remarcação).
        # A pergunta vem **antes** da agenda de propósito — consultar o Google aqui só criaria uma
        # chance a mais de 503 para quem já não tem nada a escolher.
        agendado = discovery_booking.discovery_agendado(engagement)
        if agendado is not None:
            return Response({
                "account": engagement.account.name,
                "slots": [],
                "scheduled_at": agendado.starts_at,
            })
        try:
            # A janela do Discovery, **não** a da pré-venda: 5 dias com grade a partir de 3 dias,
            # 3 opções por dia (DAP `dap-agendamento-discovery-r1`, emenda de 02/09). A oferta
            # inteira eram 80 escolhas numa página que pede uma.
            slots = booking.available_slots_for_discovery()
        except calendar_sync.CalendarUnavailable:
            # Sem enxergar a agenda não dá para dizer o que está livre, e lista vazia aqui seria a
            # página afirmando "não há horário" — o estado que a D1 separa deste.
            return _discovery_erro(
                DISCOVERY_AGENDA_FORA, "calendar_unavailable", status.HTTP_503_SERVICE_UNAVAILABLE
            )
        # Lista vazia é 200: "a janela acabou cheia" é resposta legítima, não falha.
        return Response({
            "account": engagement.account.name, "slots": slots, "scheduled_at": None,
        })


class DiscoveryBookingCreateView(APIView):
    """Marca o Discovery do mandato no horário escolhido (rota pública)."""

    authentication_classes: list = []
    permission_classes = [AllowAny]
    throttle_classes = [ScopedRateThrottle]
    throttle_scope = "discovery_booking"

    @extend_schema(
        request=BookingCreateSerializer,
        responses=inline_serializer("DiscoveryBookingCreateResponse", {
            "starts_at": serializers.DateTimeField(),
            "link": serializers.CharField(),
        }),
    )
    def post(self, request: Request) -> Response:
        fora = _discovery_fora_do_ar()
        if fora is not None:
            return fora
        serializer = BookingCreateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        try:
            engagement = discovery_booking.engagement_from_token(serializer.validated_data["token"])
        except (discovery_booking.TokenExpirado, discovery_booking.TokenInvalido) as exc:
            return _discovery_token_response(exc)
        if discovery_booking.discovery_agendado(engagement) is not None:
            return _discovery_erro(
                "O Discovery deste mandato já está agendado.",
                "already_scheduled",
                status.HTTP_409_CONFLICT,
            )
        try:
            created = booking.book_discovery(
                engagement,
                serializer.validated_data["slot_start"],
                _discovery_attendee(engagement),
            )
        except booking.SlotUnavailable:
            return _discovery_erro(
                "Horário indisponível.", "slot_unavailable", status.HTTP_409_CONFLICT
            )
        except calendar_sync.CalendarUnavailable:
            return _discovery_erro(
                DISCOVERY_AGENDA_FORA, "calendar_unavailable", status.HTTP_503_SERVICE_UNAVAILABLE
            )
        # **Depois** da reserva e **fora** da transação dela: o projeto do Discovery nasce aqui, e
        # não num clique posterior de alguém da casa (ADR 0061). Best-effort por dentro — falhe o
        # que falhar, a resposta abaixo continua 201, porque o cliente marcou o horário e o projeto
        # é consequência interna.
        discovery_booking.abrir_projeto_da_sessao(engagement, created)
        return Response(
            {"starts_at": created.starts_at, "link": created.calendar_link},
            status=status.HTTP_201_CREATED,
        )


def _discovery_attendee(engagement: Engagement) -> str:
    """Quem o Google convida: a **parte contratante** do acordo que abriu o mandato.

    O e-mail **não** vem do corpo da requisição, e é a decisão inteira: quem tem o link poderia,
    então, redirecionar o convite do Discovery para um endereço qualquer. O mandato já sabe de
    onde veio (`originating_design_partner_agreement`), e é dali que o endereço sai.

    Era "quem assinou por último" (`order_by("-signed_at")`), e isso acertava por sorte enquanto o
    acordo tinha um signatário só. Desde a issue #115 a rodada tem a casa e as testemunhas, e o
    último a assinar pode ser qualquer um deles — o convite de calendário iria para dentro de casa,
    ou para quem só testemunhou. Quem responde é `esign.email_da_contraparte`, o mesmo lugar que o
    convite por e-mail consulta: duas buscas parecidas para a mesma pergunta divergiriam no
    primeiro conserto, e esta já tinha divergido.
    """
    documento = engagement.originating_design_partner_agreement
    if documento is None:  # pragma: no cover - mandato de Design Partner sempre tem o acordo
        return ""
    return esign.email_da_contraparte(documento, documento.rodada_assinada)


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

        `Account.vertical` é `SET_NULL`: sem esta guarda, apagar uma vertical **zeraria em silêncio**
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
    # Mesmo mapa que o serializer usa para o corpo (`VALORES_DE_ENTRADA`), por referência — e não
    # uma segunda cópia: as duas tabelas do valor legado de `area` seriam o mesmo fato divergindo
    # em silêncio no dia em que uma fosse editada sem a outra.
    filter_valores_legados = {"area": DigitalEmployeeBlueprintSerializer.VALORES_DE_ENTRADA["area"]}

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

    Subconsulta e não `join`: `CommercialOpportunity.leads` é reverso de FK e aceita mais de
    uma linha, então agrupar pelo join multiplicaria o projeto por lead e a **receita seria somada duas
    vezes**. Aqui a origem é escalar por construção, e o dinheiro não pode dobrar.

    O critério de desempate é o lead mais antigo: quem trouxe o negócio é quem chegou
    primeiro, não quem foi cadastrado por último.
    """
    return Subquery(
        Lead.objects.filter(commercial_opportunity=OuterRef(opportunity_path))
        .order_by("created_at")
        .values("source")[:1]
    )


# `_dinheiro_do_agregado(coerce_to_string=False)` morava aqui. Ele nasceu no PR #125 descrevendo
# honestamente o defeito — o esquema dizia `number` porque era `number` que trafegava — e morreu na
# ADR 0068, que trocou o corpo em vez do contrato: os agregados passaram a converter o `Decimal`
# com `dinheiro.dinheiro`, e o que sobrava do envelope era um `DecimalField` padrão. Um invólucro
# que não acrescenta nada é a mesma dívida de uma classe CSS sem consumidor, então as declarações
# abaixo dizem `serializers.DecimalField(...)` por extenso — a mesma linha que
# `AccountOverviewRoiSerializer` e `InvoiceSummary` já usavam, o que é o ponto de "uma
# representação só".


# As três sub-formas abaixo são descritas por **mais de uma** resposta agregada, e por isso cada
# uma é classe de módulo — pela razão medida no comentário de `AccountOverviewRoiSerializer`
# (acima): `inline_serializer` faz `type(name, (Serializer,), fields)` a cada chamada, e duas
# classes de mesmo nome disputando um componente é exatamente o que o drf-spectacular acusa como
# schema "muito provavelmente incorreto". A classe nasce uma vez; cada uso a instancia de novo.
#
# Nas três, a docstring é a `description` do componente no `openapi.yaml` e quem a lê é quem
# consome a API; o porquê de manutenção fica no comentário, que não atravessa (o molde de
# `DigitalEmployeeSerializer`).


# A mesma linha em `risk.assess_project` e `health.assess_project_health`: quem lê `/risk/` e
# `/health/` desenha a mesma lista.
class AssessmentSignalSerializer(serializers.Serializer):
    """Um sinal da avaliação e o peso com que ele entrou no escore."""

    label = serializers.CharField()
    detail = serializers.CharField()
    weight = serializers.IntegerField()


# `/analytics/` e `/dashboard/` diferem no filtro (o painel não conta oportunidade arquivada; a
# análise conta) e não na forma: é a mesma linha, e descrevê-la duas vezes seria duas definições
# do mesmo fato.
class PipelineStageRowSerializer(serializers.Serializer):
    """Uma etapa do funil com o agregado das oportunidades dela."""

    id = serializers.IntegerField()
    name = serializers.CharField()
    # `CharField`, não `ChoiceField(choices=PipelineStage.Kind.choices)`: ver o comentário do
    # `status` de `AccountOverviewPhaseSerializer` sobre o ruído de nomeação de enum
    # (`Status31cEnum`/`KindC64Enum`) que reusar o enum do modelo numa linha de agregação gera.
    kind = serializers.CharField()
    position = serializers.IntegerField()
    opportunity_count = serializers.IntegerField()
    # `None` na etapa sem oportunidade nenhuma: `Sum` de queryset vazio é `NULL`, e o `/dashboard/`
    # e a `/analytics/` emitem esse `None` cru — não é zero, é "não há o que somar". Quando há o
    # que somar, o total sai em **texto** (ADR 0068): quem converte é `_linhas_de_etapa`, logo
    # adiante, e `dinheiro.dinheiro` preserva o nulo justamente para não apagar a distinção.
    estimated_total = serializers.DecimalField(max_digits=14, decimal_places=2, allow_null=True)


# Os dois recortes do ROI (por conta e por serviço) têm a mesma forma — uma classe, duas
# instâncias, nunca duas declarações paralelas.
class RoiBreakdownRowSerializer(serializers.Serializer):
    """Uma linha de recorte do ROI. `roi` é nulo quando o custo é zero — divisão que não existe
    não vira zero.
    """

    label = serializers.CharField()
    revenue = serializers.DecimalField(max_digits=14, decimal_places=2)
    cost = serializers.DecimalField(max_digits=14, decimal_places=2)
    roi = serializers.FloatField(allow_null=True)


def _linhas_de_etapa(linhas: Iterable[dict[str, Any]]) -> list[dict[str, Any]]:
    """As linhas de `PipelineStageRowSerializer` com o dinheiro já em texto (ADR 0068).

    Uma função pela mesma razão de a forma ser uma classe de módulo: `/analytics/` e `/dashboard/`
    diferem no filtro e não na linha, e converter o `estimated_total` dentro de cada uma seria duas
    definições do mesmo fato — a segunda esqueceria o `None` no dia em que alguém "simplificasse" a
    primeira.
    """
    return [{**linha, "estimated_total": dinheiro(linha["estimated_total"])} for linha in linhas]


class AnalyticsView(APIView):
    resource = "analytics"
    permission_classes = [RolePermission]

    @extend_schema(
        responses=inline_serializer(
            "AnalyticsResponse",
            {
                "funnel": inline_serializer(
                    "AnalyticsFunnel",
                    {
                        # `by_status` é `DictField` **com `child`**, e isso não é o defeito que
                        # esta fatia remove: as chaves são dinâmicas de verdade (só aparece o
                        # status que ocorre nos dados), então o que se pode afirmar é o tipo do
                        # valor. `DictField()` sem `child` é que não afirmava nada.
                        "leads": inline_serializer(
                            "FunnelLeads",
                            {
                                "total": serializers.IntegerField(),
                                "by_status": serializers.DictField(
                                    child=serializers.IntegerField()
                                ),
                            },
                        ),
                        # `FunnelCommercialOpportunities`, e não `FunnelOpportunities`: o
                        # componente é superfície de nome (`language-map` §5 bane `Opportunity`
                        # sem qualificador), e o que se conta aqui é `CommercialOpportunity`. A
                        # **chave** continua `opportunities` — chave de payload não se renomeia
                        # fora da `/api/v2/`.
                        "opportunities": inline_serializer(
                            "FunnelCommercialOpportunities",
                            {
                                "open": serializers.IntegerField(),
                                "won": serializers.IntegerField(),
                                "lost": serializers.IntegerField(),
                            },
                        ),
                        "projects": inline_serializer(
                            "FunnelProjects",
                            {
                                "total": serializers.IntegerField(),
                                "by_status": serializers.DictField(
                                    child=serializers.IntegerField()
                                ),
                            },
                        ),
                        "by_tier": inline_serializer(
                            "FunnelTierRow",
                            {
                                "tier": serializers.CharField(),
                                "label": serializers.CharField(),
                                "total": serializers.IntegerField(),
                                "open": serializers.IntegerField(),
                                "won": serializers.IntegerField(),
                                "lost": serializers.IntegerField(),
                                "estimated_total": serializers.DecimalField(
                                    max_digits=14, decimal_places=2
                                ),
                                # `None` quando ninguém ganhou nem perdeu naquele degrau —
                                # denominador zero não é taxa zero.
                                "win_rate": serializers.FloatField(allow_null=True),
                            },
                            many=True,
                        ),
                        "by_stage": inline_serializer(
                            "FunnelStageRow",
                            {
                                "kind": serializers.CharField(),
                                "label": serializers.CharField(),
                                "total": serializers.IntegerField(),
                                "sent": serializers.IntegerField(),
                                "accepted": serializers.IntegerField(),
                                "rejected": serializers.IntegerField(),
                                "acceptance_rate": serializers.FloatField(allow_null=True),
                                "reached": serializers.IntegerField(),
                            },
                            many=True,
                        ),
                        "by_source": inline_serializer(
                            "FunnelSourceRow",
                            {
                                "source": serializers.CharField(),
                                "leads": serializers.IntegerField(),
                                "won": serializers.IntegerField(),
                                "projects": serializers.IntegerField(),
                                "revenue": serializers.DecimalField(
                                    max_digits=14, decimal_places=2
                                ),
                            },
                            many=True,
                        ),
                    },
                ),
                "win_rate": serializers.FloatField(allow_null=True),
                # `avg_ticket` **não** é dinheiro pelo critério da ADR 0068, embora seja um valor
                # em reais: ele é um quociente (`Avg`), e não a soma exata de valores gravados.
                # Fixá-lo em duas casas seria arredondar uma estatística — decisão de produto, não
                # de formatação —, e é a mesma razão de `win_rate` e `roi` ficarem `float`.
                "avg_ticket": serializers.FloatField(),
                "avg_cycle_days": serializers.FloatField(allow_null=True),
                "pipeline": PipelineStageRowSerializer(many=True),
                "roi": inline_serializer(
                    "AnalyticsRoi",
                    {
                        "revenue": serializers.DecimalField(max_digits=14, decimal_places=2),
                        "cost": serializers.DecimalField(max_digits=14, decimal_places=2),
                        "roi": serializers.FloatField(allow_null=True),
                        # **O recorte por conta troca de chave por versão** — `by_client` na
                        # `/api/v1/`, `by_account` na `/api/v2/` — e não convive, pelo precedente
                        # de `clients`/`accounts` em `AccountViewSet.overview` e de
                        # `processos`/`processes` na action de IA: a chave envolve a lista
                        # inteira, e duplicá-la pagaria o recorte duas vezes.
                        #
                        # É a troca que destravou **tipar** a chave aqui, o que esta declaração
                        # antes não podia fazer: enquanto a v2 também emitia `by_client`,
                        # declará-la a faria aparecer em `openapi-v2.yaml` e reprovar
                        # `test_nenhuma_chave_client_sobra_na_v2` — a guarda da fatia 4a, que
                        # mede no artefato e não no mapa. O esquema ficava silencioso sobre ela
                        # (objeto sem `additionalProperties: false` admite a chave), que é o menos
                        # ruim entre calar e mentir, mas ainda era dívida. Com a troca não há o
                        # que calar: cada contrato descreve a chave que a sua versão emite.
                        #
                        # O par **não** entra em `ALIASES_DEPRECIADOS_DE_DICT_CRU`. Aquele mapa
                        # marca a propriedade como depreciada na v1 e a **remove** da v2; aqui a
                        # chave da v2 já nasce `by_account`, então não há o que remover — o mesmo
                        # motivo pelo qual `clients`/`accounts` também não está em mapa nenhum.
                        chave_da_geracao("by_client", "by_account"): RoiBreakdownRowSerializer(
                            many=True
                        ),
                        "by_service": RoiBreakdownRowSerializer(many=True),
                    },
                ),
            },
        )
    )
    def get(self, request: Request) -> Response:
        active = Q(archived_at__isnull=True)
        leads = Lead.objects.filter(active)
        leads_by_status = {row["status"]: row["n"] for row in leads.values("status").annotate(n=Count("id"))}

        opps = CommercialOpportunity.objects.filter(active)
        won = opps.filter(stage__kind=PipelineStage.Kind.WON).count()
        lost = opps.filter(stage__kind=PipelineStage.Kind.LOST).count()
        open_count = opps.filter(stage__kind=PipelineStage.Kind.OPEN).count()
        win_rate = won / (won + lost) if (won + lost) else None
        avg_ticket = opps.filter(stage__kind=PipelineStage.Kind.WON).aggregate(v=Avg("estimated_value"))["v"] or 0

        stages = _linhas_de_etapa(
            PipelineStage.objects.annotate(
                opportunity_count=Count("opportunities", filter=Q(opportunities__archived_at__isnull=True)),
                estimated_total=Sum("opportunities__estimated_value", filter=Q(opportunities__archived_at__isnull=True)),
            ).values("id", "name", "kind", "position", "opportunity_count", "estimated_total")
        )

        projects = Project.objects.filter(active)
        projects_by_status = {row["status"]: row["n"] for row in projects.values("status").annotate(n=Count("id"))}

        # Dias entre a venda e o projeto que saiu dela. Com a origem em 1-N (ADR 0050) a conta
        # continua sendo por **projeto**, e não por oportunidade: cada projeto tem uma origem só,
        # e é a distância dele até ela que descreve o ciclo. Somar por oportunidade faria o
        # segundo projeto de um mandato recorrente entrar como um ciclo comercial que não houve.
        cycle_days = [
            (project.created_at - project.originating_commercial_opportunity.created_at).days
            for project in projects.exclude(
                originating_commercial_opportunity__isnull=True
            ).select_related("originating_commercial_opportunity")
            if project.originating_commercial_opportunity is not None
        ]
        avg_cycle = sum(cycle_days) / len(cycle_days) if cycle_days else None

        revenue = projects.aggregate(v=Sum("actual_value"))["v"] or Decimal("0")
        cost = projects.aggregate(v=Sum("cost"))["v"] or Decimal("0")
        # Os dois recortes com o dinheiro em texto (ADR 0068). O piso é `Decimal("0")` e não `0`:
        # aqui o recorte **existe** porque há projeto nele, então "sem receita registrada" é zero
        # de verdade — o nulo que sobrevive é o do funil, onde não há linha a somar.
        by_account = [
            {"label": row["engagement__account__name"],
             "revenue": dinheiro(row["rev"] or Decimal("0")),
             "cost": dinheiro(row["cost"] or Decimal("0")),
             "roi": _roi(row["rev"] or Decimal("0"), row["cost"] or Decimal("0"))}
            for row in projects.values("engagement__account__name").annotate(rev=Sum("actual_value"), cost=Sum("cost")).order_by("-rev")
        ]
        by_service = [
            {"label": row["service__name"] or "Sem serviço",
             "revenue": dinheiro(row["rev"] or Decimal("0")),
             "cost": dinheiro(row["cost"] or Decimal("0")),
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
                # O degrau sem oportunidade nenhuma vale `"0.00"`, e não `null`: a linha do degrau
                # sai sempre (o laço é sobre `Service.Tier.choices`), então aqui "não há venda
                # neste degrau" **é** zero estimado — a forma declarada em `FunnelTierRow`, que
                # nunca foi nulável.
                "estimated_total": dinheiro(
                    tier_opps.aggregate(v=Sum("estimated_value"))["v"] or Decimal("0")
                ),
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
                rows.annotate(
                    account=Coalesce("commercial_opportunity__account_id", "project__engagement__account_id")
                )
                .values("account").distinct().count()
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
        # FDD 013, porque `Lead.commercial_opportunity` é FK e
        # `Project.originating_commercial_opportunity` é FK desde a ADR 0050.
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
                origin=Coalesce(
                    _lead_source("originating_commercial_opportunity_id"), Value(SEM_LEAD)
                )
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
                    "revenue": dinheiro(closed_by_source.get(origin, (0, Decimal("0")))[1]),
                }
                for origin in set(entered) | set(won_by_source) | set(closed_by_source)
            ),
            key=lambda row: (-row["won"], -row["leads"], row["source"]),
        )

        # A chave do recorte por conta é escolhida **aqui** pela versão da requisição, e no
        # `@extend_schema` acima pelo alvo da geração (`chave_da_geracao`). São dois mecanismos
        # distintos — `request.version` não existe na hora de montar o esquema, e `OPENAPI_ALVO`
        # não existe na hora de responder — e mexer em só um deles publicaria um contrato que
        # discorda do corpo devolvido, que é o defeito que a decisão 5 da ADR 0066 recusa.
        chave_do_recorte_por_conta = "by_account" if versao_de(request) == V2 else "by_client"

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
            "roi": {"revenue": dinheiro(revenue), "cost": dinheiro(cost),
                    "roi": _roi(revenue, cost),
                    chave_do_recorte_por_conta: by_account, "by_service": by_service},
        })


class RiskView(APIView):
    resource = "risk"
    permission_classes = [RolePermission]

    @extend_schema(
        responses=inline_serializer(
            "RiskResponse",
            {
                "projects": inline_serializer(
                    "RiskProject",
                    {
                        "project_id": serializers.IntegerField(),
                        "name": serializers.CharField(),
                        "score": serializers.IntegerField(),
                        "level": serializers.CharField(),
                        "signals": AssessmentSignalSerializer(many=True),
                        # `None` quando não há marco nenhum, ou quando o ritmo não permite prever
                        # (`risk.assess_project`): a chave sai sempre, o valor é que falta.
                        "forecast": inline_serializer(
                            "RiskForecast",
                            {
                                # `DateField` e não `CharField`: `risk.py` já emite
                                # `date.isoformat()`, que é byte a byte o que `DateField`
                                # serializa (`format: date`). O componente descreve o **que
                                # trafega**, e "data ISO" é mais informativo para quem gera
                                # cliente do que "texto". Nada aqui serializa de fato — o
                                # `inline_serializer` é só o esquema da resposta.
                                "predicted_finish_date": serializers.DateField(),
                                "delay_days": serializers.IntegerField(),
                                "basis": serializers.CharField(),
                            },
                            allow_null=True,
                        ),
                    },
                    many=True,
                )
            },
        )
    )
    def get(self, request: Request) -> Response:
        projects = Project.objects.visible_to(request.user).filter(
            archived_at__isnull=True
        ).exclude(status=Project.Status.COMPLETED)
        assessments = sorted(risk.assess_projects(projects), key=lambda a: a["score"], reverse=True)
        return Response({"projects": assessments})


class HealthView(APIView):
    resource = "health"
    permission_classes = [RolePermission]

    @extend_schema(
        responses=inline_serializer(
            "HealthResponse",
            {
                # A mesma cabeça da linha de risco e **sem `forecast`**: previsão de término é do
                # risco de atraso, e a saúde mede outra coisa. Compartilham só o sinal.
                "projects": inline_serializer(
                    "HealthProject",
                    {
                        "project_id": serializers.IntegerField(),
                        "name": serializers.CharField(),
                        "score": serializers.IntegerField(),
                        "level": serializers.CharField(),
                        "signals": AssessmentSignalSerializer(many=True),
                    },
                    many=True,
                )
            },
        )
    )
    def get(self, request: Request) -> Response:
        # `select_related("engagement")`: `assess_projects_health` lê `project.engagement.account_id`
        # por projeto (satisfação é por conta). Antes da Fase 6 isso era `project.client_id`, campo
        # direto sem query; agora é um hop, e sem o join o custo cresce com a base (N+1). Ver
        # `test_aggregate_query_budget`.
        projects = Project.objects.visible_to(request.user).select_related("engagement").filter(
            archived_at__isnull=True
        ).exclude(status=Project.Status.COMPLETED)
        # pior primeiro: menor score de saúde no topo, para a equipe agir onde dói.
        assessments = sorted(health.assess_projects_health(projects), key=lambda a: a["score"])
        return Response({"projects": assessments})


class RecommendationsView(APIView):
    resource = "analytics"
    permission_classes = [RolePermission]

    @extend_schema(
        responses=inline_serializer(
            "RecommendationsResponse",
            {
                "items": inline_serializer(
                    "RecommendationItem",
                    {
                        # `CharField`, não `ChoiceField`: `upsell`/`followup`/`prioritization`/
                        # `deadline` são literais de `recommendations.py`, não `choices` de
                        # modelo — não há enum de onde derivar, e inventar um aqui criaria a
                        # segunda definição da lista.
                        "kind": serializers.CharField(),
                        "label": serializers.CharField(),
                        "detail": serializers.CharField(),
                        "url": serializers.CharField(),
                    },
                    many=True,
                )
            },
        )
    )
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
        "by_feature": inline_serializer(
            "AiFeatureMetric",
            {
                # `AiInteraction.feature` é `CharField(max_length=32)` **sem `choices`** — o nome
                # da feature é escrito por quem chama `_ai_run`. Não há enum a reusar aqui nem
                # que se quisesse.
                "feature": serializers.CharField(),
                "count": serializers.IntegerField(),
                "positive": serializers.IntegerField(),
                "negative": serializers.IntegerField(),
            },
            many=True,
        ),
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
                # Lista **vazia** para Entrega (ver o comentário no `get`), e não ausente: a
                # forma do contrato não muda com o papel de quem pergunta.
                "pipeline": PipelineStageRowSerializer(many=True),
                "upcoming_tasks": inline_serializer(
                    "DashboardUpcomingTask",
                    {
                        "id": serializers.IntegerField(),
                        "title": serializers.CharField(),
                        # `.values()` entrega `due_date` como objeto `date`; o renderizador o
                        # emite ISO, que é o que `DateField` descreve.
                        "due_date": serializers.DateField(),
                        "project_id": serializers.IntegerField(),
                    },
                    many=True,
                ),
            },
        )
    )
    def get(self, request: Request) -> Response:
        today = timezone.localdate()
        is_delivery = (
            request.user.role == User.Role.DELIVERY and not request.user.is_admin_role
        )
        # O funil traz valor estimado de **todas** as oportunidades, inclusive as não-ganhas,
        # que o `CommercialOpportunityViewSet` já esconde de Entrega. O painel não pode ser o canal
        # lateral disso. O campo permanece (a forma do contrato não muda), vazio.
        stages = [] if is_delivery else _linhas_de_etapa(PipelineStage.objects.annotate(
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


# O estado de uma integração — `flags.status()`, o que o `GET` lista e o que o `PATCH` devolve.
# Classe de módulo pela regra das outras três: a forma é a **mesma** nas duas rotas (o `PATCH`
# devolve `flags.status(key)`, o `GET` devolve `flags.all_status()`), e descrevê-la duas vezes
# seria duas definições do mesmo fato — o `GET` a descrevia como `DictField()` sem `child`, então
# o item da lista não tinha chave nenhuma no contrato enquanto o `PATCH` tinha as seis.
# O componente continua se chamando `ConfigFlag`, como já se chamava.
class ConfigFlagSerializer(serializers.Serializer):
    key = serializers.CharField()
    label = serializers.CharField()
    enabled = serializers.BooleanField()
    configured = serializers.BooleanField()
    toggleable = serializers.BooleanField()
    # Os nomes de variável de ambiente que faltam para poder ligar — lista vazia quando não falta
    # nada (`flags.missing`), que é o mesmo que `configured: true`.
    missing = serializers.ListField(child=serializers.CharField())


class ConfigView(APIView):
    permission_classes = [IsAuthenticated]

    @extend_schema(responses=inline_serializer("ConfigResponse", {
        "ai_enabled": serializers.BooleanField(),
        "calendar_enabled": serializers.BooleanField(),
        "esign_enabled": serializers.BooleanField(),
        "esign_house_signer_email": serializers.CharField(allow_null=True),
        "integrations": ConfigFlagSerializer(many=True),
    }))
    def get(self, request: Request) -> Response:
        return Response({
            "ai_enabled": ai.is_enabled(),
            "calendar_enabled": calendar_sync.is_enabled(),
            "esign_enabled": esign.is_enabled(),
            # Fora do mecanismo de flags de propósito (DAP `dap-assinatura-com-papeis-r1`, D): as
            # flags respondem "configurado?" sem revelar valor, e aqui o valor **é** a resposta —
            # é o e-mail com que a casa assina, e ele vai no próprio documento.
            "esign_house_signer_email": str(settings.ESIGN_HOUSE_SIGNER_EMAIL or "").strip() or None,
            "integrations": flags.all_status(),
        })

    @extend_schema(
        request=inline_serializer("ConfigPatch", {
            "key": serializers.CharField(),
            "enabled": serializers.BooleanField(),
        }),
        responses=ConfigFlagSerializer,
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
        # `select_related` porque o snapshot lê `client`, `engagement` e a conta do engajamento
        # (Issue #71): sem ele, cada leitura somaria três consultas ao que já é uma projeção
        # inteira montada por requisição.
        project = get_object_or_404(
            Project.objects.select_related("engagement", "engagement__account"), pk=pk
        )
        return Response(portal.build_snapshot(project))
