from __future__ import annotations

import logging
import os
import re
from datetime import date
from typing import Any, cast

from django.contrib.auth.password_validation import validate_password
from django.core.exceptions import ValidationError as DjangoValidationError
from django.core.files.uploadedfile import UploadedFile
from django.utils import timezone
from drf_spectacular.utils import extend_schema_field
from rest_framework import serializers

from . import blueprints, drive, knowledge, ladder, processos
from .exceptions import DriveUnavailable
from .models import (
    ARTIFACT_TRANSITIONS,
    CASE_TRANSITIONS,
    INVOICE_TRANSITIONS,
    AccountRung,
    AccountRungEvent,
    Activity,
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
    GithubProjection,
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
    PipelineStage,
    Processo,
    ProcessoEtapa,
    Project,
    ProjectChecklistItem,
    ProjectDeliverable,
    ProjectMember,
    ProjectPhase,
    Risco,
    Satisfacao,
    Service,
    SignatureRequest,
    Task,
    User,
    Vertical,
)

logger = logging.getLogger(__name__)


class UserSerializer(serializers.ModelSerializer[User]):
    # O mesmo predicado que o backend usa em 14 lugares (`RolePermission`, `visible_to`,
    # `agents`...), e não o `is_superuser` cru: assim o SPA **consome** a regra em vez de
    # reconstruí-la em TypeScript como `is_superuser || role === "admin"`, que seria uma segunda
    # expressão dela. Sem isto, `createsuperuser` — o primeiro comando de toda instalação — produz
    # alguém que a API trata como admin e a tela trata como Entrega (FDD 017, ADR 0010).
    is_admin = serializers.BooleanField(source="is_admin_role", read_only=True)

    class Meta:
        model = User
        fields = ["id", "username", "first_name", "last_name", "email", "role", "is_admin"]
        # `is_admin` explicitamente aqui também: hoje nenhum endpoint de escrita usa este
        # serializer, mas os demais campos são graváveis, e o dia em que alguém o pendurar num
        # viewset de escrita não pode ser o dia em que virou caminho de promoção.
        read_only_fields = ["id", "is_admin"]


class ClientSerializer(serializers.ModelSerializer[Client]):
    vertical_name = serializers.CharField(source="vertical.name", read_only=True, default="")

    class Meta:
        model = Client
        fields = ["id", "name", "legal_name", "tax_id", "owner", "status", "vertical",
                  "vertical_name", "created_at", "updated_at"]
        read_only_fields = ["id", "owner", "created_at", "updated_at"]

    def validate_status(self, value: str) -> str:
        """`status` é afirmado por quem cadastra, mas o que o sistema observou não se desdiz.

        Prospect vira ativo pelo signal `_promote_client_on_won`. Deixar um PATCH devolver o
        cliente para prospect apagaria esse fato — e o signal só promove na transição, então ele
        não corrigiria de volta. O critério de "ganha" é o mesmo de `Opportunity.is_won`.
        """
        if value != Client.Status.PROSPECT or self.instance is None:
            return value
        if Opportunity.objects.filter(
            client=self.instance, stage__kind=PipelineStage.Kind.WON, archived_at__isnull=True
        ).exists():
            raise serializers.ValidationError(
                "O cliente tem oportunidade ganha e não volta a ser prospect."
            )
        return value


class ContactSerializer(serializers.ModelSerializer[Contact]):
    class Meta:
        model = Contact
        fields = ["id", "client", "name", "email", "phone", "job_title", "receives_billing",
                  "created_at", "updated_at"]
        read_only_fields = ["id", "created_at", "updated_at"]


class ActivitySerializer(serializers.ModelSerializer[Activity]):
    kind_display = serializers.CharField(source="get_kind_display", read_only=True)
    cobranca_sinal_display = serializers.CharField(
        source="get_cobranca_sinal_display", read_only=True
    )

    class Meta:
        model = Activity
        fields = ["id", "client", "opportunity", "invoice", "kind", "kind_display", "happened_on",
                  "summary", "notes", "cobranca_sinal", "cobranca_sinal_display", "owner",
                  "created_at", "updated_at"]
        # `cobranca_sinal` é só de leitura: ele é lavrado por `POST /activities/{id}/classificar/`,
        # que carrega a `AiInteraction` que o produziu. Um `PATCH` com o campo cru gravaria a mesma
        # coluna sem procedência nenhuma — a distinção que a FDD 028 já fez entre "campo" e "ato"
        # no `status` da fatura.
        read_only_fields = ["id", "kind_display", "cobranca_sinal", "cobranca_sinal_display",
                            "owner", "created_at", "updated_at"]

    def validate(self, attrs: dict[str, object]) -> dict[str, object]:
        client = cast(Client | None, attrs.get("client", getattr(self.instance, "client", None)))
        opportunity = cast(
            Opportunity | None, attrs.get("opportunity", getattr(self.instance, "opportunity", None))
        )
        if opportunity and client and opportunity.client_id != client.id:
            raise serializers.ValidationError(
                {"opportunity": "A oportunidade deve pertencer ao mesmo cliente."}
            )
        invoice = cast(Invoice | None, attrs.get("invoice", getattr(self.instance, "invoice", None)))
        if invoice and client and invoice.client_id != client.id:
            raise serializers.ValidationError(
                {"invoice": "A fatura deve pertencer ao mesmo cliente."}
            )
        return attrs


class PipelineStageSerializer(serializers.ModelSerializer[PipelineStage]):
    class Meta:
        model = PipelineStage
        fields = ["id", "name", "kind", "position"]
        read_only_fields = ["id"]


class PhaseDeliverableSerializer(serializers.ModelSerializer[PhaseDeliverable]):
    """Entregável do template de uma fase (config admin)."""

    class Meta:
        model = PhaseDeliverable
        fields = ["id", "phase", "name", "position"]
        read_only_fields = ["id"]


class PhaseChecklistItemSerializer(serializers.ModelSerializer[PhaseChecklistItem]):
    """Item do quality gate no template de uma fase (config admin, FDD 033)."""

    class Meta:
        model = PhaseChecklistItem
        fields = ["id", "phase", "text", "position"]
        read_only_fields = ["id"]


class JourneyPhaseSerializer(serializers.ModelSerializer[JourneyPhase]):
    """Fase do template da Jornada de Transformação (config admin, vocabulário editável)."""

    deliverables = PhaseDeliverableSerializer(many=True, read_only=True)
    checklist_items = PhaseChecklistItemSerializer(many=True, read_only=True)

    class Meta:
        model = JourneyPhase
        fields = [
            "id", "name", "description", "position", "active", "requires_gate",
            "deliverables", "checklist_items",
        ]
        read_only_fields = ["id"]


class ProjectDeliverableSerializer(serializers.ModelSerializer[ProjectDeliverable]):
    """Entregável de um projeto — só `status`/`document` são editáveis (marcar entregue)."""

    class Meta:
        model = ProjectDeliverable
        fields = [
            "id", "project_phase", "name", "status", "document", "position",
            "delivered_at", "created_at", "updated_at",
        ]
        read_only_fields = [
            "id", "project_phase", "name", "position", "delivered_at", "created_at", "updated_at",
        ]


class ProjectChecklistItemSerializer(serializers.ModelSerializer[ProjectChecklistItem]):
    """Item do quality gate de um projeto — só `checked` é editável (FDD 033)."""

    class Meta:
        model = ProjectChecklistItem
        fields = [
            "id", "project_phase", "text", "position", "checked", "checked_at",
            "created_at", "updated_at",
        ]
        read_only_fields = [
            "id", "project_phase", "text", "position", "checked_at", "created_at", "updated_at",
        ]


class ProjectPhaseSerializer(serializers.ModelSerializer[ProjectPhase]):
    """Fase da jornada de um projeto (estado). A equipe edita `target_date` e a justificativa.

    `gate_outcome`/`gate_notes` são **read-only de propósito** (FDD 033): a decisão entra só pela
    action `apply-gate`, que é onde moram as consequências de cada saída — concluir e avançar,
    reabrir a fase anterior, ou parar. Um PATCH direto gravaria "REDESIGN" sem nada acontecer, e
    o campo passaria a mentir sobre o estado da jornada.
    """

    phase_name = serializers.CharField(source="phase.name", read_only=True)
    phase_description = serializers.CharField(source="phase.description", read_only=True)
    phase_position = serializers.IntegerField(source="phase.position", read_only=True)
    requires_gate = serializers.BooleanField(source="phase.requires_gate", read_only=True)
    deliverables = ProjectDeliverableSerializer(many=True, read_only=True)
    checklist_items = ProjectChecklistItemSerializer(many=True, read_only=True)

    class Meta:
        model = ProjectPhase
        fields = [
            "id", "project", "phase", "phase_name", "phase_description", "phase_position",
            "requires_gate", "status", "started_at", "completed_at", "target_date",
            "gate_outcome", "gate_notes", "checklist_waiver", "deliverables", "checklist_items",
        ]
        read_only_fields = [
            "id", "project", "phase", "phase_name", "phase_description", "phase_position",
            "requires_gate", "status", "started_at", "completed_at", "gate_outcome",
            "gate_notes", "deliverables", "checklist_items",
        ]


class OpportunitySerializer(serializers.ModelSerializer[Opportunity]):
    stage_name = serializers.CharField(source="stage.name", read_only=True)
    service_name = serializers.CharField(source="service.name", read_only=True)
    service_tier = serializers.CharField(source="service.tier", read_only=True)
    project = serializers.SerializerMethodField()
    project_archived = serializers.SerializerMethodField()

    class Meta:
        model = Opportunity
        fields = [
            "id", "client", "contact", "title", "scope", "estimated_value", "stage", "stage_name",
            "owner", "expected_close_date", "service", "service_name", "service_tier", "project",
            "project_archived", "created_at", "updated_at",
        ]
        read_only_fields = ["id", "owner", "created_at", "updated_at"]

    @extend_schema_field(serializers.IntegerField(allow_null=True))
    def get_project(self, obj: Opportunity) -> int | None:
        """Id do projeto que saiu desta oportunidade, ou `None` se ela ainda não foi convertida.

        Sem isto a tela do pipeline não tem como saber que já converteu, e continua oferecendo
        "Criar projeto" numa oportunidade que só pode responder 409. O `getattr` com default dá
        conta do reverso 1-1 porque `RelatedObjectDoesNotExist` herda de `AttributeError`.
        """
        project = getattr(obj, "project", None)
        return project.pk if project else None

    @extend_schema_field(serializers.BooleanField())
    def get_project_archived(self, obj: Opportunity) -> bool:
        """O projeto convertido está arquivado?

        `project` continua preenchido nesse caso, de propósito: anulá-lo faria a tela voltar a
        oferecer "Criar projeto", e a conversão responderia 409 porque o `OneToOneField` segue
        ocupado — trocaria um link morto por um botão morto. Com este campo a tela mostra o estado
        em vez de oferecer uma ação que não existe (FDD 025).
        """
        project = getattr(obj, "project", None)
        return project is not None and project.archived_at is not None

    def validate(self, attrs: dict[str, object]) -> dict[str, object]:
        client = cast(Client | None, attrs.get("client", getattr(self.instance, "client", None)))
        contact = cast(Contact | None, attrs.get("contact", getattr(self.instance, "contact", None)))
        if contact and client and contact.client_id != client.id:
            raise serializers.ValidationError({"contact": "O contato deve pertencer ao cliente selecionado."})
        return attrs


class ProjectSerializer(serializers.ModelSerializer[Project]):
    is_overdue = serializers.SerializerMethodField()
    # A vertical do cliente, aqui, para o detalhe do projeto pedir o catálogo já resolvido sem
    # ter de carregar o cliente inteiro só por causa de um id (FDD 026).
    client_vertical = serializers.IntegerField(source="client.vertical_id", read_only=True)
    client_vertical_name = serializers.CharField(
        source="client.vertical.name", read_only=True, default=""
    )

    class Meta:
        model = Project
        fields = [
            "id", "client", "opportunity", "name", "description", "owner", "start_date", "due_date",
            "status", "service", "actual_value", "cost", "is_overdue", "created_at", "updated_at",
            "ai_maturity", "ai_opportunity", "ai_dimensions", "ai_score_summary", "ai_scored_at",
            "ai_score_reviewed", "client_vertical", "client_vertical_name",
        ]
        # ai_maturity/opportunity/dimensions/summary são editáveis: parte da revisão humana do
        # rascunho antes de publicar. ai_scored_at é carimbo da geração (só a IA escreve).
        read_only_fields = [
            "id", "opportunity", "owner", "is_overdue", "created_at", "updated_at", "ai_scored_at",
        ]

    def validate(self, attrs: dict[str, object]) -> dict[str, object]:
        start = cast(date | None, attrs.get("start_date", getattr(self.instance, "start_date", None)))
        due = cast(date | None, attrs.get("due_date", getattr(self.instance, "due_date", None)))
        if start and due and due < start:
            raise serializers.ValidationError({"due_date": "A data final não pode ser anterior à inicial."})
        return attrs

    def get_is_overdue(self, project: Project) -> bool:
        return project.status != Project.Status.COMPLETED and project.due_date < date.today()


class WorkItemSerializer(serializers.ModelSerializer):
    is_overdue = serializers.BooleanField(read_only=True)

    class Meta:
        fields = [
            "id", "project", "title", "description", "owner", "due_date", "completed_at", "status",
            "is_overdue", "party", "source", "external_id", "created_at", "updated_at",
        ]
        read_only_fields = [
            "id", "owner", "completed_at", "is_overdue", "source", "external_id",
            "created_at", "updated_at",
        ]


class MilestoneSerializer(WorkItemSerializer):
    class Meta(WorkItemSerializer.Meta):
        model = Milestone


class MeetingSerializer(serializers.ModelSerializer[Meeting]):
    class Meta:
        model = Meeting
        fields = ["id", "project", "title", "date", "meeting_url", "recording_url", "transcript",
                  "status", "created_at", "updated_at"]
        read_only_fields = ["id", "created_at", "updated_at"]


class PendenciaSerializer(serializers.ModelSerializer[Pendencia]):
    class Meta:
        model = Pendencia
        fields = ["id", "project", "title", "description", "status", "party", "owner",
                  "resolved_at", "created_at", "updated_at"]
        read_only_fields = ["id", "owner", "resolved_at", "created_at", "updated_at"]


class DecisaoSerializer(serializers.ModelSerializer[Decisao]):
    # `published_at` é read-only pela razão do `resolved_at` acima: quem carimba é o `save()` do
    # modelo, não quem manda o PATCH. Aceitar a data do cliente seria deixar reescrever quando uma
    # decisão passou a valer.
    class Meta:
        model = Decisao
        fields = ["id", "project", "title", "rationale", "decided_on", "decided_by", "status",
                  "source_meeting", "published_at", "created_at", "updated_at"]
        read_only_fields = ["id", "published_at", "created_at", "updated_at"]


class RiscoSerializer(serializers.ModelSerializer[Risco]):
    # `owner` e `resolved_at` são read-only pelo motivo da `Pendencia` acima: o dono sai da sessão
    # de quem registrou e o carimbo sai do `save()` do modelo. Aceitá-los do corpo deixaria
    # reescrever quem viu o risco e quando ele deixou de ameaçar.
    class Meta:
        model = Risco
        fields = ["id", "project", "title", "description", "probability", "impact", "mitigation",
                  "status", "owner", "resolved_at", "created_at", "updated_at"]
        read_only_fields = ["id", "owner", "resolved_at", "created_at", "updated_at"]


class SatisfacaoSerializer(serializers.ModelSerializer[Satisfacao]):
    """O registro de satisfação (FDD 037).

    `registered_by` é só de leitura pelo motivo do `owner` do `Risco` acima: quem registrou sai da
    sessão, não do corpo. Aqui pesa mais que lá — este registro muda o Health Score e a escada da
    cobrança, e "quem ouviu isso do cliente" é metade do que torna o sinal avaliável depois.
    """

    nivel_display = serializers.CharField(source="get_nivel_display", read_only=True)
    fonte_display = serializers.CharField(source="get_fonte_display", read_only=True)

    class Meta:
        model = Satisfacao
        fields = ["id", "client", "project", "source_meeting", "source_activity", "nivel",
                  "nivel_display", "fonte", "fonte_display", "happened_on", "note",
                  "registered_by", "created_at", "updated_at"]
        read_only_fields = ["id", "nivel_display", "fonte_display", "registered_by", "created_at",
                            "updated_at"]

    def validate(self, attrs: dict[str, object]) -> dict[str, object]:
        """As mesmas três regras do `clean()` do modelo, repetidas aqui de propósito.

        É o que o `ActivitySerializer` já faz: sem elas a API devolveria 500 no `full_clean` do
        `save()` em vez de um 400 com o campo errado apontado, e a tela não teria o que mostrar.
        """
        client = cast(Client | None, attrs.get("client", getattr(self.instance, "client", None)))
        project = cast(
            Project | None, attrs.get("project", getattr(self.instance, "project", None))
        )
        if project and client and project.client_id != client.id:
            raise serializers.ValidationError(
                {"project": "O projeto deve pertencer ao mesmo cliente."}
            )
        # A atividade de origem (FDD 038) tem a mesma fronteira do projeto: o atalho do painel
        # manda o id da interação, e uma resposta de outro cliente viraria a satisfação declarada
        # deste — a linha que troca a escada e tira 20 pontos do Health Score.
        source_activity = cast(
            Activity | None,
            attrs.get("source_activity", getattr(self.instance, "source_activity", None)),
        )
        if source_activity and client and source_activity.client_id != client.id:
            raise serializers.ValidationError(
                {"source_activity": "A interação deve pertencer ao mesmo cliente."}
            )
        nivel = attrs.get("nivel", getattr(self.instance, "nivel", None))
        note = cast(str, attrs.get("note", getattr(self.instance, "note", "")) or "")
        if nivel == Satisfacao.Nivel.INSATISFEITO and not note.strip():
            raise serializers.ValidationError(
                {"note": "Diga o que o cliente disse: insatisfeito sem nota não se avalia depois."}
            )
        return attrs


class ProcessoSerializer(serializers.ModelSerializer[Processo]):
    """O processo mapeado no Discovery (FDD 039), com a conta do custo do estado atual junto.

    `custo` é derivado e só de leitura: ele é a fórmula de `docs/metodologia-fde.md:87-88` aplicada
    aos nove insumos que já estão no corpo. Persistir o total seria uma segunda verdade sobre o
    mesmo dado — mudaria o volume e o número gravado continuaria dizendo o antigo.

    `registered_by` é só de leitura pelo motivo do `Risco` e da `Satisfacao` acima: quem levantou
    sai da sessão, não do corpo.
    """

    client_name = serializers.CharField(source="client.name", read_only=True)
    custo = serializers.SerializerMethodField()

    class Meta:
        model = Processo
        fields = ["id", "client", "client_name", "name", "position", "source_project",
                  "source_meeting", "registered_by", "volume_mes", "tempo_horas", "pessoas",
                  "custo_hora", "retrabalho_mes", "erros_mes", "perdas_mes", "espera_mes",
                  "risco_mes", "custo", "created_at", "updated_at"]
        read_only_fields = ["id", "client_name", "registered_by", "custo", "created_at",
                            "updated_at"]

    @extend_schema_field(serializers.DictField())
    def get_custo(self, processo: Processo) -> dict[str, Any]:
        """A conta à vista: parcelas, total, o que não foi apurado e se há fato sustentando.

        Quem lê **não** pode concluir "custa zero" de um total zerado: é `nao_apurado` que separa
        "não há insumo" de "medimos e deu zero" (ver `processos.custo_do_estado_atual`).

        **Os valores saem como texto, e não é preciosismo.** `SerializerMethodField` entrega o que
        devolver direto ao renderizador, e o encoder do DRF converte `Decimal` em `float`
        (`rest_framework/utils/encoders.py`) — o próprio comentário de lá diz que aquele ramo
        existe para quem escapa de um `DecimalField`, que é este caso. Sem a conversão,
        `Decimal("5000.00")` chega ao cliente como `5000.0`, dinheiro trafega em ponto flutuante e
        `Invoice.amount` (string, pelo `COERCE_DECIMAL_TO_STRING`) e o custo passam a ter formatos
        diferentes na mesma API. Também contrariaria o `processos.py`, que evita `float` por dentro
        justamente para não somar centavos com erro.

        Um teste sobre `response.data` **não pega isto**: ali o valor ainda é `Decimal`, e a
        conversão só acontece na renderização. A regressão afirma sobre o JSON renderizado.
        """
        custo = processos.custo_do_estado_atual(processo)
        return {
            **custo,
            "total": str(custo["total"]),
            "parcelas": [
                {**parcela, "valor": str(parcela["valor"])} for parcela in custo["parcelas"]
            ],
        }


class ProcessoEtapaSerializer(serializers.ModelSerializer[ProcessoEtapa]):
    """A etapa e o P-S-D-T-E-R dela (`docs/metodologia-fde.md:75-79`).

    Os seis campos saem na ordem das seis letras de propósito: é assim que a pergunta é feita na
    reunião, e um formulário fora de ordem faz quem preenche pular a pergunta que faltou.
    """

    class Meta:
        model = ProcessoEtapa
        fields = ["id", "processo", "name", "position", "pessoas", "sistema", "dados", "tempo",
                  "erro", "retrabalho", "created_at", "updated_at"]
        read_only_fields = ["id", "created_at", "updated_at"]


class EvidenciaSerializer(serializers.ModelSerializer[Evidencia]):
    """O achado com a forma de onde veio e o rótulo que a metodologia exige (`:81-86`).

    `forma` e `rotulo` **não têm default** no modelo, e o serializer não inventa um: omiti-los no
    corpo é erro de validação, e é o comportamento que se quer. Um default faria a casa escolher
    por quem não escolheu, sempre para o mesmo lado — chamar de fato o que ninguém confirmou.
    """

    forma_display = serializers.CharField(source="get_forma_display", read_only=True)
    rotulo_display = serializers.CharField(source="get_rotulo_display", read_only=True)

    class Meta:
        model = Evidencia
        fields = ["id", "processo", "etapa", "forma", "forma_display", "rotulo", "rotulo_display",
                  "content", "source_meeting", "registered_by", "created_at", "updated_at"]
        read_only_fields = ["id", "forma_display", "rotulo_display", "registered_by", "created_at",
                            "updated_at"]

    def validate(self, attrs: dict[str, object]) -> dict[str, object]:
        """A mesma regra do `clean()` do modelo, repetida aqui pelo motivo da `Satisfacao` acima.

        Sem ela o `save()` do DRF não chama `full_clean`, e a evidência apontando para a etapa de
        **outro cliente** seria gravada em silêncio — a guarda do modelo só valeria para quem
        passasse pelo admin ou pelo shell.
        """
        processo = cast(
            Processo | None, attrs.get("processo", getattr(self.instance, "processo", None))
        )
        etapa = cast(
            ProcessoEtapa | None, attrs.get("etapa", getattr(self.instance, "etapa", None))
        )
        if etapa and processo and etapa.processo_id != processo.id:
            raise serializers.ValidationError(
                {"etapa": "A etapa deve pertencer ao mesmo processo."}
            )
        return attrs


class TaskSerializer(WorkItemSerializer):
    class Meta(WorkItemSerializer.Meta):
        model = Task
        fields = WorkItemSerializer.Meta.fields + ["milestone"]

    def validate(self, attrs: dict[str, object]) -> dict[str, object]:
        project = cast(Project | None, attrs.get("project", getattr(self.instance, "project", None)))
        milestone = cast(Milestone | None, attrs.get("milestone", getattr(self.instance, "milestone", None)))
        if milestone and project and milestone.project_id != project.id:
            raise serializers.ValidationError({"milestone": "O marco deve pertencer ao mesmo projeto."})
        return attrs


class AccountRungEventSerializer(serializers.ModelSerializer[AccountRungEvent]):
    """Uma transição do histórico. **Só de leitura, e não por comodidade**: o registro é
    append-only (FDD 042), e um serializer gravável aqui ofereceria a operação que o modelo existe
    para negar.
    """

    from_status_display = serializers.SerializerMethodField()
    to_status_display = serializers.SerializerMethodField()
    by_name = serializers.SerializerMethodField()

    class Meta:
        model = AccountRungEvent
        fields = [
            "id", "rung", "from_status", "from_status_display", "to_status",
            "to_status_display", "at", "by", "by_name", "note",
        ]
        read_only_fields = fields

    @extend_schema_field(serializers.CharField())
    def get_from_status_display(self, obj: AccountRungEvent) -> str:
        return AccountRung.Status(obj.from_status).label if obj.from_status else ""

    @extend_schema_field(serializers.CharField())
    def get_to_status_display(self, obj: AccountRungEvent) -> str:
        return AccountRung.Status(obj.to_status).label

    @extend_schema_field(serializers.CharField())
    def get_by_name(self, obj: AccountRungEvent) -> str:
        return obj.by.get_full_name() or obj.by.username if obj.by else ""


class AccountRungSerializer(serializers.ModelSerializer[AccountRung]):
    """Um degrau da escada FDE da conta (FDD 042). **Inteiramente de leitura.**

    A escrita entra por `POST /account-rungs/{id}/transition/`, que é onde moram as consequências
    de cada estado — carimbo, autor, motivo do pulo e o evento append-only. Um `PATCH status=done`
    gravaria a conclusão sem nada disso e o campo passaria a mentir sobre a escada; é o mesmo
    motivo pelo qual `ProjectPhase.gate_outcome` é read-only e só a action `apply-gate` o move.

    **O que a Entrega vê é a *forma* da escada, não o conteúdo comercial** (ADR 0047): oportunidade
    e título de oportunidade vêm sempre nulos, e o degrau realizado por um projeto de que a pessoa
    não participa vem marcado `no_access`, sem projeto, sem datas e sem histórico. O recorte de
    quais projetos são visíveis vem de `Project.objects.visible_to` e **nunca é reescrito** (RFC
    0003, ADR 0010) — o viewset o resolve uma vez e entrega no contexto.

    `gate_outcome` e `next_gate` são **projeções da jornada de entrega da FDD 011**, derivadas do
    projeto que realiza o degrau. Referenciadas, não redesenhadas: a decisão de gate continua sendo
    tomada na tela do projeto, e aqui ela só aparece.
    """

    rung_display = serializers.CharField(source="get_rung_display", read_only=True)
    status_display = serializers.CharField(source="get_status_display", read_only=True)
    waiting_on_display = serializers.SerializerMethodField()
    opportunity_title = serializers.SerializerMethodField()
    project_name = serializers.SerializerMethodField()
    skipped_by_name = serializers.SerializerMethodField()
    days_stalled = serializers.SerializerMethodField()
    is_stale = serializers.SerializerMethodField()
    gate_outcome = serializers.SerializerMethodField()
    next_gate = serializers.SerializerMethodField()
    no_access = serializers.SerializerMethodField()
    events = AccountRungEventSerializer(many=True, read_only=True)

    class Meta:
        model = AccountRung
        fields = [
            "id", "client", "rung", "rung_display", "status", "status_display",
            "opportunity", "opportunity_title", "project", "project_name",
            "started_at", "completed_at", "waiting_on", "waiting_on_display", "blocker",
            "skip_reason", "skipped_by", "skipped_by_name", "skipped_at",
            "days_stalled", "is_stale", "gate_outcome", "next_gate", "no_access", "events",
        ]
        read_only_fields = fields

    # ---- o recorte da Entrega -------------------------------------------------------------
    def _redacted(self) -> bool:
        """A pessoa é da Entrega? Só aí há conteúdo comercial a esconder."""
        user = getattr(self.context.get("request"), "user", None)
        return bool(user and not user.is_admin_role and user.role == User.Role.DELIVERY)

    def _visible_projects(self) -> set[int]:
        """Ids de projeto que a pessoa alcança, resolvidos uma vez pelo viewset."""
        return self.context.get("visible_project_ids", set())

    def _sem_acesso(self, obj: AccountRung) -> bool:
        return bool(
            self._redacted()
            and obj.project_id
            and obj.project_id not in self._visible_projects()
        )

    def to_representation(self, instance: AccountRung) -> dict[str, Any]:
        dados = super().to_representation(instance)
        if not self._redacted():
            return dados
        # A oportunidade é conteúdo **comercial** e some para a Entrega mesmo quando o projeto é
        # visível: quem entrega precisa saber em que degrau a conta está, não por quanto ele foi
        # vendido. Isso é decisão de contrato — ver a FDD 042.
        dados["opportunity"] = None
        dados["opportunity_title"] = ""
        if dados["no_access"]:
            # A *forma* da escada continua: nome do degrau e posição. O resto some, inclusive o
            # histórico — a transição carrega a proveniência comercial junto.
            dados.update(
                project=None, project_name="", started_at=None, completed_at=None,
                blocker="", skip_reason="", skipped_by=None, skipped_by_name="",
                skipped_at=None, waiting_on="", waiting_on_display="",
                gate_outcome="", next_gate=None, days_stalled=None, is_stale=False,
                events=[],
            )
        return dados

    # ---- campos derivados -----------------------------------------------------------------
    @extend_schema_field(serializers.CharField())
    def get_waiting_on_display(self, obj: AccountRung) -> str:
        return AccountRung.WaitingOn(obj.waiting_on).label if obj.waiting_on else ""

    @extend_schema_field(serializers.CharField())
    def get_opportunity_title(self, obj: AccountRung) -> str:
        return obj.opportunity.title if obj.opportunity_id and obj.opportunity else ""

    @extend_schema_field(serializers.CharField())
    def get_project_name(self, obj: AccountRung) -> str:
        return obj.project.name if obj.project_id and obj.project else ""

    @extend_schema_field(serializers.CharField())
    def get_skipped_by_name(self, obj: AccountRung) -> str:
        if not obj.skipped_by_id or not obj.skipped_by:
            return ""
        return obj.skipped_by.get_full_name() or obj.skipped_by.username

    @extend_schema_field(serializers.IntegerField(allow_null=True))
    def get_days_stalled(self, obj: AccountRung) -> int | None:
        return ladder.days_stalled(obj)

    @extend_schema_field(serializers.BooleanField())
    def get_is_stale(self, obj: AccountRung) -> bool:
        return ladder.is_stale(ladder.days_stalled(obj))

    @extend_schema_field(serializers.CharField())
    def get_gate_outcome(self, obj: AccountRung) -> str:
        """A última decisão de gate registrada na jornada do projeto que realiza o degrau.

        Projeção, não campo próprio: o gate é decidido em `POST /projects/{id}/apply-gate/` e
        gravado em `ProjectPhase.gate_outcome`. Guardar uma segunda cópia aqui criaria a divergência
        silenciosa que a casa evita — e o SPA usa o **mesmo mapa** de rótulo/variante da tela do
        projeto, nunca um segundo.
        """
        fase = self._gate_phase(obj)
        return fase.gate_outcome if fase else ""

    @extend_schema_field(
        serializers.DictField(child=serializers.CharField(), allow_null=True)
    )
    def get_next_gate(self, obj: AccountRung) -> dict[str, Any] | None:
        """A fase ativa da jornada que termina em decision gate — o "próximo gate" do degrau."""
        fase = next(
            (
                fase
                for fase in self._phases(obj)
                if fase.status == ProjectPhase.Status.ACTIVE and fase.phase.requires_gate
            ),
            None,
        )
        if fase is None:
            return None
        return {
            "phase_name": fase.phase.name,
            "target_date": fase.target_date.isoformat() if fase.target_date else None,
        }

    @extend_schema_field(serializers.BooleanField())
    def get_no_access(self, obj: AccountRung) -> bool:
        return self._sem_acesso(obj)

    def _phases(self, obj: AccountRung) -> list[ProjectPhase]:
        if not obj.project_id or self._sem_acesso(obj):
            return []
        return list(self.context.get("phases_by_project", {}).get(obj.project_id, []))

    def _gate_phase(self, obj: AccountRung) -> ProjectPhase | None:
        decididas = [fase for fase in self._phases(obj) if fase.gate_outcome]
        return decididas[-1] if decididas else None


class AccountRungTransitionSerializer(serializers.Serializer):
    """O corpo de `POST /account-rungs/{id}/transition/`. As recusas moram em `ladder`, não aqui."""

    status = serializers.ChoiceField(choices=AccountRung.Status.choices)
    note = serializers.CharField(required=False, allow_blank=True, default="")
    waiting_on = serializers.ChoiceField(
        choices=AccountRung.WaitingOn.choices, required=False, allow_blank=True
    )
    blocker = serializers.CharField(required=False, allow_blank=True)
    skip_reason = serializers.CharField(required=False, allow_blank=True)
    opportunity = serializers.PrimaryKeyRelatedField(
        queryset=Opportunity.objects.all(), required=False, allow_null=True
    )
    project = serializers.PrimaryKeyRelatedField(
        queryset=Project.objects.all(), required=False, allow_null=True
    )


class EngineeringHandoffSerializer(serializers.ModelSerializer[EngineeringHandoff]):
    """Handoff de engenharia (FDD 040). Número/URL/status saem do provisionamento, não do corpo.

    O UniqueValidator de `pulse_work_item_id` é desligado de propósito: o POST duplicado não é
    400, é 200 no registro existente — a chave de idempotência.
    """

    class Meta:
        model = EngineeringHandoff
        fields = [
            "id", "project", "source_task", "pulse_work_item_id", "title", "objective",
            "context", "acceptance_criteria", "scope_text", "out_of_scope_text",
            "repository", "milestone_ref", "adr_refs", "nfr_refs", "fdd_refs",
            "correlation_id", "github_issue_number", "github_issue_url", "github_node_id",
            "status", "attempt_count", "last_attempt_at", "last_error_code",
            "last_error_message", "created_at", "updated_at",
        ]
        read_only_fields = [
            "id", "correlation_id", "github_issue_number", "github_issue_url",
            "github_node_id", "status", "attempt_count", "last_attempt_at",
            "last_error_code", "last_error_message", "created_at", "updated_at",
        ]
        extra_kwargs: dict[str, dict[str, list[object]]] = {
            "pulse_work_item_id": {"validators": []},
        }
        validators: list[Any] = []

    def validate(self, attrs: dict[str, object]) -> dict[str, object]:
        def valor(campo: str, default: object = "") -> object:
            if campo in attrs:
                return attrs[campo]
            if self.instance is not None:
                return getattr(self.instance, campo)
            return default

        if "pulse_work_item_id" in attrs:
            attrs["pulse_work_item_id"] = str(attrs["pulse_work_item_id"] or "").strip()
        pulse_id = str(valor("pulse_work_item_id") or "").strip()
        if self.instance is not None and "pulse_work_item_id" in attrs:
            if pulse_id != self.instance.pulse_work_item_id:
                raise serializers.ValidationError(
                    {"pulse_work_item_id": "O identificador Pulse não muda depois de criado."}
                )

        instancia = EngineeringHandoff(
            project=cast(Project | None, valor("project", None)),
            source_task=cast(Task | None, valor("source_task", None)),
            pulse_work_item_id=pulse_id,
            title=str(valor("title") or ""),
            objective=str(valor("objective") or ""),
            context=str(valor("context") or ""),
            acceptance_criteria=str(valor("acceptance_criteria") or ""),
            scope_text=str(valor("scope_text") or ""),
            out_of_scope_text=str(valor("out_of_scope_text") or ""),
            repository=str(valor("repository") or ""),
            milestone_ref=str(valor("milestone_ref") or ""),
            adr_refs=valor("adr_refs", []),
            nfr_refs=valor("nfr_refs", []),
            fdd_refs=valor("fdd_refs", []),
            status=str(valor("status", EngineeringHandoff.Status.PENDING) or ""),
            github_issue_number=cast(int | None, valor("github_issue_number", None)),
            github_issue_url=str(valor("github_issue_url") or ""),
        )
        try:
            instancia.clean()
        except DjangoValidationError as exc:
            raise serializers.ValidationError(
                exc.message_dict if hasattr(exc, "message_dict") else exc.messages
            ) from exc
        return attrs


class GithubProjectionSerializer(serializers.ModelSerializer[GithubProjection]):
    """A projeção de engenharia como o painel a lê (FDD 041). Somente leitura, inteira.

    **`is_stale` e as idades vêm daqui, e não da tela.** O limiar de obsolescência mora em
    `settings.GITHUB_PROJECTION_STALE_AFTER_SECONDS`; deixar o cálculo para o frontend criaria uma
    segunda definição de "velho" — a da tela e a da reconciliação — divergindo em silêncio na
    primeira vez que alguém mexesse numa delas (DAP GH-41 r1, decisão 1).
    """

    project = serializers.IntegerField(source="handoff.project_id", read_only=True)
    repository = serializers.CharField(source="handoff.repository", read_only=True)
    issue_number = serializers.IntegerField(source="handoff.github_issue_number", read_only=True)
    issue_url = serializers.CharField(source="handoff.github_issue_url", read_only=True)
    reference = serializers.CharField(read_only=True)
    is_stale = serializers.SerializerMethodField()
    age_seconds = serializers.SerializerMethodField()
    last_error_age_seconds = serializers.SerializerMethodField()

    class Meta:
        model = GithubProjection
        fields = [
            "id", "handoff", "project", "repository", "issue_number", "issue_url", "reference",
            "issue_state", "issue_title", "pr_number", "pr_state", "head_sha", "ci_state",
            "observed_at", "observed_via", "age_seconds", "is_stale",
            "last_error_kind", "last_error_at", "last_error_age_seconds",
            "source_updated_at", "created_at", "updated_at",
        ]
        read_only_fields = fields

    @extend_schema_field(serializers.BooleanField())
    def get_is_stale(self, obj: GithubProjection) -> bool:
        return obj.is_stale()

    @extend_schema_field(serializers.IntegerField())
    def get_age_seconds(self, obj: GithubProjection) -> int:
        return obj.age_seconds()

    @extend_schema_field(serializers.IntegerField(allow_null=True))
    def get_last_error_age_seconds(self, obj: GithubProjection) -> int | None:
        """A idade da **última tentativa de contato**, que é outra pergunta que a idade da
        observação: no estado "GitHub indisponível" o painel diz as duas ("observado há 26 min ·
        última tentativa há 1 min"), e é a segunda que informa se alguém precisa agir."""
        if obj.last_error_at is None:
            return None
        return max(0, int((timezone.now() - obj.last_error_at).total_seconds()))


class SignatureRequestSerializer(serializers.ModelSerializer[SignatureRequest]):
    class Meta:
        model = SignatureRequest
        fields = [
            "id", "signer_email", "status", "sign_url", "reminded_at", "signed_at", "created_at",
        ]
        read_only_fields = fields


# Tipos aceitos no upload de documento (FDD 017). O download já força `as_attachment`, mas o
# arquivo também segue para o Drive e para o fornecedor de assinatura — lugares onde um
# `.html`/`.svg` volta a ser servido como página.
ALLOWED_DOCUMENT_EXTENSIONS = frozenset({
    ".pdf", ".doc", ".docx", ".odt", ".xls", ".xlsx", ".ods", ".ppt", ".pptx", ".odp",
    ".txt", ".md", ".csv", ".png", ".jpg", ".jpeg", ".webp", ".gif", ".zip",
})

_UNSAFE_NAME_CHARS = re.compile(r"[\x00-\x1f\x7f]")


def _safe_original_name(name: str | None) -> str:
    """Nome de arquivo é entrada do usuário e viaja para o Drive, o e-sign e o portal do cliente.

    O download não é o risco (o Django já faz `basename` e escapa o header); os outros
    consumidores é que recebem o valor cru.
    """
    cleaned = _UNSAFE_NAME_CHARS.sub("", (name or "").replace("\\", "/"))
    cleaned = os.path.basename(cleaned).strip().lstrip(".")
    return cleaned[:255] or "documento"


class DocumentSerializer(serializers.ModelSerializer[Document]):
    signature_requests = SignatureRequestSerializer(many=True, read_only=True)

    class Meta:
        model = Document
        fields = [
            "id", "client", "opportunity", "project", "file", "drive_link", "original_name",
            "uploaded_by", "created_at", "signature_requests",
        ]
        read_only_fields = ["id", "drive_link", "original_name", "uploaded_by", "created_at"]

    def validate(self, attrs: dict[str, object]) -> dict[str, object]:
        links = [attrs.get("client"), attrs.get("opportunity"), attrs.get("project")]
        if sum(value is not None for value in links) != 1:
            raise serializers.ValidationError("Vincule o documento a exatamente um cliente, oportunidade ou projeto.")
        uploaded_file = cast(UploadedFile | None, attrs.get("file"))
        if uploaded_file is None:
            raise serializers.ValidationError({"file": "Envie um arquivo."})
        if (uploaded_file.size or 0) > 10 * 1024 * 1024:
            raise serializers.ValidationError({"file": "O arquivo excede o limite de 10 MB."})
        extension = os.path.splitext(uploaded_file.name or "")[1].lower()
        if extension not in ALLOWED_DOCUMENT_EXTENSIONS:
            raise serializers.ValidationError({
                "file": "Tipo de arquivo não aceito. Aceitos: "
                        f"{', '.join(sorted(ALLOWED_DOCUMENT_EXTENSIONS))}."
            })
        return attrs

    def create(self, validated_data: dict[str, object]) -> Document:
        uploaded_file = cast(UploadedFile, validated_data.pop("file"))
        document = Document(
            **validated_data,
            original_name=_safe_original_name(uploaded_file.name),
            uploaded_by=self.context["request"].user,
        )
        if drive.is_enabled():
            try:
                document.drive_file_id, document.drive_link = drive.upload_document(
                    document, uploaded_file
                )
            except Exception as exc:  # noqa: BLE001 - qualquer falha do Drive, não só HTTP
                # Era o único ponto de integração num caminho de **escrita** sem tratamento:
                # credencial errada ou pasta inexistente davam 500 mudo e o arquivo do usuário
                # sumia. 502 diz de quem é o problema (o fornecedor, não o pedido) e deixa claro
                # que vale repetir — nada é gravado pela metade, porque o `save()` vem depois.
                logger.exception("upload ao Drive falhou para %s", document.original_name)
                raise DriveUnavailable(
                    "O Google Drive não aceitou o arquivo agora. Tente de novo em instantes."
                ) from exc
        else:
            document.file = uploaded_file
        document.save()
        return document


class ProjectMemberSerializer(serializers.ModelSerializer[ProjectMember]):
    user_name = serializers.CharField(source="user.get_full_name", read_only=True)
    user_username = serializers.CharField(source="user.username", read_only=True)
    user_role = serializers.CharField(source="user.role", read_only=True)

    class Meta:
        model = ProjectMember
        fields = ["id", "project", "user", "user_name", "user_username", "user_role",
                  "added_by", "created_at"]
        read_only_fields = ["id", "added_by", "created_at"]

    def validate(self, attrs: dict[str, object]) -> dict[str, object]:
        # A constraint do banco é condicional ao arquivamento; aqui é só para o erro sair
        # como mensagem de campo em vez de 500.
        project = cast(Project | None, attrs.get("project"))
        user = cast(User | None, attrs.get("user"))
        if ProjectMember.objects.filter(
            project=project, user=user, archived_at__isnull=True
        ).exists():
            raise serializers.ValidationError("Esta pessoa já está na equipe do projeto.")
        return attrs


class ServiceSerializer(serializers.ModelSerializer[Service]):
    tier_display = serializers.CharField(source="get_tier_display", read_only=True)

    class Meta:
        model = Service
        fields = ["id", "name", "active", "tier", "tier_display", "list_price", "summary",
                  "created_at", "updated_at"]
        # A unicidade do `tier` ativo vem da UniqueConstraint do modelo; o DRF a deriva
        # sozinho (respeitando a condição), como no `PipelineStage`.
        read_only_fields = ["id", "created_at", "updated_at"]


class VerticalSerializer(serializers.ModelSerializer[Vertical]):
    """Setor do cliente (config admin, vocabulário editável — FDD 026)."""

    class Meta:
        model = Vertical
        fields = ["id", "name", "slug", "position", "active"]
        read_only_fields = ["id"]


class BlueprintVariantSerializer(serializers.ModelSerializer[BlueprintVariant]):
    """Parametrização de um blueprint por vertical. Campo em branco herda o do blueprint."""

    vertical_name = serializers.CharField(source="vertical.name", read_only=True)

    class Meta:
        model = BlueprintVariant
        fields = ["id", "blueprint", "vertical", "vertical_name", "description", "kpi_label",
                  "default_hours_saved_month", "default_roi_month"]
        # A unicidade (blueprint, vertical) vem da UniqueConstraint do modelo; o DRF a deriva
        # sozinho, como faz com o `tier` do `Service`.
        read_only_fields = ["id"]


class DigitalEmployeeBlueprintSerializer(serializers.ModelSerializer[DigitalEmployeeBlueprint]):
    """Bloco do catálogo, com as variantes aninhadas (forma do `JourneyPhaseSerializer`).

    `resolved` só aparece quando o viewset recebe `?vertical=`: são os valores já com a variante
    aplicada, que é o que a instanciação vai copiar. Sem o parâmetro o campo é omitido — quem
    lista o catálogo para editá-lo não quer ver os valores de um setor em particular.
    """

    variants = BlueprintVariantSerializer(many=True, read_only=True)
    area_display = serializers.CharField(source="get_area_display", read_only=True)
    service_name = serializers.CharField(source="service.name", read_only=True, default="")
    resolved = serializers.SerializerMethodField()
    has_variant = serializers.SerializerMethodField()

    class Meta:
        model = DigitalEmployeeBlueprint
        fields = ["id", "name", "area", "area_display", "description", "kpi_label",
                  "kpi_unit", "kpi_direction",
                  "default_hours_saved_month", "default_roi_month", "service", "service_name",
                  "active", "variants", "resolved", "has_variant"]
        read_only_fields = ["id"]

    def _vertical(self) -> Vertical | None:
        return self.context.get("vertical")

    @extend_schema_field(serializers.DictField(allow_null=True))
    def get_resolved(self, blueprint: DigitalEmployeeBlueprint) -> dict[str, object] | None:
        vertical = self._vertical()
        if vertical is None:
            return None
        valores = blueprints.resolve(blueprint, vertical)
        return {
            "name": valores["name"],
            "area": valores["area_display"],
            "description": valores["description"],
            "kpi_label": valores["kpi_label"],
            "kpi_unit": valores["kpi_unit"],
            "kpi_direction": valores["kpi_direction"],
            "hours_saved_month": str(valores["hours_saved_month"]),
            "roi_month": str(valores["roi_month"]),
        }

    def get_has_variant(self, blueprint: DigitalEmployeeBlueprint) -> bool:
        return blueprints.variant_for(blueprint, self._vertical()) is not None


class DigitalEmployeeSerializer(serializers.ModelSerializer[DigitalEmployee]):
    class Meta:
        model = DigitalEmployee
        fields = ["id", "project", "blueprint", "name", "area", "description", "status",
                  "kpi_label", "kpi_value", "kpi_unit", "kpi_direction",
                  "kpi_baseline", "kpi_current", "hours_saved_month", "roi_month",
                  "created_at", "updated_at"]
        # `blueprint` é procedência, gravada pela rota `from-blueprint` (FDD 026). Gravável aqui,
        # abriria um segundo caminho que aponta para o template **sem copiar** — exatamente o que
        # a cópia por instância existe para impedir.
        read_only_fields = ["id", "blueprint", "created_at", "updated_at"]


class ArtifactSerializer(serializers.ModelSerializer[Artifact]):
    kind_display = serializers.CharField(source="get_kind_display", read_only=True)
    status_display = serializers.CharField(source="get_status_display", read_only=True)

    class Meta:
        model = Artifact
        fields = ["id", "kind", "kind_display", "status", "status_display", "title", "content",
                  "opportunity", "project", "source_meeting", "document", "ai_interaction",
                  "created_by", "sent_at", "decided_at", "created_at", "updated_at"]
        read_only_fields = ["id", "kind_display", "status_display", "source_meeting",
                            "ai_interaction", "created_by", "sent_at", "decided_at",
                            "created_at", "updated_at"]

    def validate(self, attrs: dict[str, object]) -> dict[str, object]:
        # Na edição parcial só temos o que veio no corpo; o resto vem da instância.
        opportunity = attrs.get("opportunity", getattr(self.instance, "opportunity", None))
        project = attrs.get("project", getattr(self.instance, "project", None))
        if sum(value is not None for value in [opportunity, project]) != 1:
            raise serializers.ValidationError(
                "Vincule o artefato a exatamente uma oportunidade ou projeto."
            )
        return attrs

    def validate_status(self, value: str) -> str:
        if self.instance is None:
            return value
        current = self.instance.status
        if value != current and value not in ARTIFACT_TRANSITIONS[current]:
            raise serializers.ValidationError(
                f"Não é possível ir de {self.instance.get_status_display()} para "
                f"{Artifact.Status(value).label}."
            )
        return value


class CaseSerializer(serializers.ModelSerializer[Case]):
    """O case de um projeto concluído (FDD 027).

    A lista de `read_only_fields` é a entrega, não burocracia: `metrics`, `health_snapshot` e
    `roi_snapshot` são a fotografia, e mantê-los fora da escrita é o que faz "os números não mudam
    depois de congelados" ser verdade por construção — não há caminho, em vez de haver um caminho
    que ninguém usa. O trio do consentimento fica de fora pelo motivo oposto: ele *deve* mudar, mas
    só pela ação `record-consent`, que grava quem autorizou.
    """

    status_display = serializers.CharField(source="get_status_display", read_only=True)
    vertical_name = serializers.CharField(source="vertical.name", read_only=True, default="")
    client_name = serializers.SerializerMethodField()
    project_name = serializers.CharField(source="project.name", read_only=True)

    class Meta:
        model = Case
        fields = ["id", "project", "project_name", "title", "summary", "vertical",
                  "vertical_name", "client_name", "metrics", "health_snapshot", "roi_snapshot",
                  "status", "status_display", "published_at", "client_consent",
                  "consent_recorded_at", "consent_recorded_by", "anonymized",
                  "created_at", "updated_at"]
        read_only_fields = ["id", "project", "project_name", "vertical", "vertical_name",
                            "client_name", "metrics", "health_snapshot", "roi_snapshot",
                            "status_display", "published_at", "client_consent",
                            "consent_recorded_at", "consent_recorded_by",
                            "created_at", "updated_at"]

    def get_client_name(self, case: Case) -> str:
        """Vazio quando anonimizado — a anonimização vive aqui, e não na tela.

        Deixá-la para o frontend faria a resposta da API carregar o nome mesmo assim, e "não
        aparece" passaria a depender de todo consumidor lembrar de escondê-lo. Razão social e CNPJ
        nunca são projetados, anonimizado ou não: o case não precisa deles.
        """
        return "" if case.anonymized else case.project.client.name

    def _anonimo(self, case: Case) -> str:
        setor = case.vertical.name if case.vertical else None
        return f"Uma empresa do setor {setor}" if setor else "Uma empresa cliente"

    def to_representation(self, instance: Case) -> dict[str, Any]:
        """Apagar o `client_name` não bastava: o nome também vive no **texto**.

        O congelamento monta o título como "Cliente — Projeto", então um case anonimizado saía com
        o nome no título enquanto o campo dedicado vinha vazio — a permissão que o cliente deu
        virando a que ele não deu, por uma porta que ninguém olha. A substituição alcança também o
        resumo escrito à mão, onde o mesmo nome costuma reaparecer.

        Substituir, e não esconder o título inteiro: quem revisa precisa saber de que case se
        trata, e "Uma empresa do setor Imobiliárias — Implantação de agentes" continua dizendo isso.
        """
        dados = super().to_representation(instance)
        if not instance.anonymized:
            return dados
        nome = instance.project.client.name
        rotulo = self._anonimo(instance)
        for campo in ("title", "summary"):
            if isinstance(dados.get(campo), str):
                dados[campo] = dados[campo].replace(nome, rotulo)
        return dados

    def validate_status(self, value: str) -> str:
        if self.instance is None:
            return value
        current = self.instance.status
        if value != current and value not in CASE_TRANSITIONS[current]:
            raise serializers.ValidationError(
                f"Não é possível ir de {self.instance.get_status_display()} para "
                f"{Case.Status(value).label}."
            )
        return value

    def validate(self, attrs: dict[str, object]) -> dict[str, object]:
        # A guarda de consentimento é repetida aqui e no `Case.clean()` porque as duas portas são
        # de verdade: o `clean()` cobre admin do Django, shell e job; esta cobre a API e é a que
        # devolve 400 com o campo certo. `anonymized` não abre exceção — anonimizar autoriza omitir
        # a marca, não usar o resultado.
        status = attrs.get("status", getattr(self.instance, "status", Case.Status.DRAFT))
        consent = getattr(self.instance, "client_consent", False)
        if status == Case.Status.PUBLISHED and not consent:
            raise serializers.ValidationError(
                {"status": "Registre o consentimento do cliente antes de publicar o case."}
            )
        return attrs


# Os estados que **existem** no mapa de transições mas não se alcançam por digitação: cada um tem
# carimbo, autor ou chamada ao gateway por trás, e um PATCH não produz nenhum dos três.
_INVOICE_ACTION_FOR: dict[str, str] = {
    "issued": "issue",
    "paid": "mark-paid",
    "cancelled": "cancel",
}

# O que a fatura emitida não admite mais. **Não** são `read_only_fields`: em rascunho eles são o
# próprio trabalho de quem monta a cobrança.
_FROZEN_ONCE_ISSUED = (
    "client", "project", "service", "amount", "due_date", "description",
)


class InvoiceSerializer(serializers.ModelSerializer[Invoice]):
    """A fatura (FDD 028).

    Duas travas que valem ser lidas juntas, porque a diferença entre elas é deliberada.

    **A do estado** é o mapa `INVOICE_TRANSITIONS` mais um segundo degrau que aponta a ação certa.
    O primeiro devolve o 400 de `paga → emitida`; o segundo existe porque emitir, baixar e cancelar
    são **atos com autor e carimbo** — um `PATCH status=paid` não carrega nem a data do provedor nem
    quem baixou, e aceitar isso produziria uma baixa sem procedência.

    **A dos campos** é um erro alto, e não o descarte silencioso que o `CaseSerializer` escolheu
    para a fotografia do case. Lá ninguém *queria* escrever `health_snapshot`; aqui, quem digita um
    novo `amount` numa fatura emitida **quis** — e um 200 que joga fora uma edição de dinheiro é o
    pior modo de falha disponível.
    """

    status_display = serializers.CharField(source="get_status_display", read_only=True)
    method_display = serializers.CharField(source="get_method_display", read_only=True)
    client_name = serializers.CharField(source="client.name", read_only=True)
    project_name = serializers.CharField(source="project.name", read_only=True, default="")
    service_name = serializers.CharField(source="service.name", read_only=True, default="")
    is_overdue = serializers.BooleanField(read_only=True)

    class Meta:
        model = Invoice
        fields = [
            "id", "client", "client_name", "project", "project_name", "service", "service_name",
            "number", "amount", "description", "due_date", "method", "method_display",
            "status", "status_display", "is_overdue", "issued_at", "issued_by", "paid_at",
            "settled_by", "cancelled_at", "cancelled_by", "cancel_reason",
            "provider", "external_reference", "payment_url", "created_at", "updated_at",
        ]
        read_only_fields = [
            "id", "client_name", "project_name", "service_name", "number", "method_display",
            "status_display", "is_overdue", "issued_at", "issued_by", "paid_at", "settled_by",
            "cancelled_at", "cancelled_by", "cancel_reason",
            "provider", "external_reference", "payment_url", "created_at", "updated_at",
        ]

    def validate_status(self, value: str) -> str:
        if self.instance is None:
            return value
        current = self.instance.status
        if value == current:
            return value
        if value not in INVOICE_TRANSITIONS[current]:
            raise serializers.ValidationError(
                f"Não é possível ir de {self.instance.get_status_display()} para "
                f"{Invoice.Status(value).label}."
            )
        acao = _INVOICE_ACTION_FOR.get(value)
        if acao:
            raise serializers.ValidationError(
                f"{Invoice.Status(value).label} não é campo, é ação: "
                f"use POST /invoices/{{id}}/{acao}/."
            )
        return value

    def validate(self, attrs: dict[str, object]) -> dict[str, object]:
        if self.instance is not None and self.instance.status != Invoice.Status.DRAFT:
            travados = sorted(set(attrs) & set(_FROZEN_ONCE_ISSUED))
            if travados:
                raise serializers.ValidationError(
                    {c: "Fatura emitida não se edita. Cancele e emita outra." for c in travados}
                )
        return attrs


class CobrancaContatoSerializer(serializers.ModelSerializer[CobrancaContato]):
    """O que a casa já disse sobre uma fatura (FDD 036). **Só de leitura pelo router.**

    Nenhum campo é gravável aqui, e a ausência é a entrega: um `POST /cobranca/` criaria a prova de
    um contato que não aconteceu. Contato nasce de `POST /invoices/{id}/cobranca/enviar/` ou do job
    — os dois mandam o e-mail **antes** de gravar.
    """

    degrau_display = serializers.CharField(source="get_degrau_display", read_only=True)
    canal_display = serializers.CharField(source="get_canal_display", read_only=True)
    client_name = serializers.CharField(source="client.name", read_only=True)
    invoice_number = serializers.CharField(source="invoice.number", read_only=True, default="")

    class Meta:
        model = CobrancaContato
        fields = ["id", "invoice", "invoice_number", "client", "client_name", "degrau",
                  "degrau_display", "canal", "canal_display", "sent_on", "subject", "to_email",
                  "body", "sent_by", "ai_interaction", "created_at"]
        read_only_fields = fields


class CobrancaSuspensaoSerializer(serializers.ModelSerializer[CobrancaSuspensao]):
    """Suspender a cobrança — com dono, prazo e motivo, os três obrigatórios (RFC 0004).

    A validação de "exatamente uma fatura ou um cliente" mora no `clean()` do modelo, como a do
    `Document`, e é chamada daqui: uma suspensão que valesse para os dois níveis teria duas
    leituras de "levantar", e a errada devolve a cobrança a quem ainda não devia ouvi-la.
    """

    client_name = serializers.CharField(source="client.name", read_only=True, default="")
    invoice_number = serializers.CharField(source="invoice.number", read_only=True, default="")
    is_active = serializers.BooleanField(read_only=True)

    class Meta:
        model = CobrancaSuspensao
        fields = ["id", "invoice", "invoice_number", "client", "client_name", "owner", "until",
                  "reason", "created_by", "lifted_at", "lifted_by", "is_active",
                  "created_at", "updated_at"]
        read_only_fields = ["id", "invoice_number", "client_name", "created_by", "lifted_at",
                            "lifted_by", "is_active", "created_at", "updated_at"]

    def validate(self, attrs: dict[str, Any]) -> dict[str, Any]:
        # Cai no que já está gravado quando o campo não veio no corpo — o molde do
        # `ActivitySerializer` logo acima. Sem isto, um `PATCH` que só corrige o motivo montaria uma
        # instância sem fatura nem cliente e seria recusado por "vale para exatamente uma fatura ou
        # um cliente", que é o oposto do que a suspensão em disco diz.
        def valor(campo: str) -> Any:
            return attrs.get(campo, getattr(self.instance, campo, None))

        instancia = CobrancaSuspensao(
            **{campo: valor(campo) for campo in ("invoice", "client", "owner", "until")},
            reason=str(valor("reason") or ""),
        )
        try:
            instancia.clean()
        except DjangoValidationError as exc:
            raise serializers.ValidationError(exc.message_dict if hasattr(exc, "message_dict") else exc.messages) from exc
        return attrs


class KnowledgeAreaSerializer(serializers.ModelSerializer[KnowledgeArea]):
    owner_name = serializers.CharField(source="owner.get_full_name", read_only=True, default="")
    piece_count = serializers.IntegerField(read_only=True, default=0)

    class Meta:
        model = KnowledgeArea
        fields = ["id", "name", "slug", "position", "active", "owner", "owner_name",
                  "review_interval_days", "piece_count"]
        read_only_fields = ["id", "owner_name", "piece_count"]


class KnowledgePieceSerializer(serializers.ModelSerializer[KnowledgePiece]):
    """A peça do inventário (FDD 029).

    `last_verified_at` e `verified_by` são **read-only**: verificar é ato com autor e carimbo, pela
    ação `verify` — no molde do `record-consent` da FDD 027. Um `PATCH` que ligue a data diria "foi
    conferido" sem dizer por quem, que é a alegação de ninguém.
    """

    kind_display = serializers.CharField(source="get_kind_display", read_only=True)
    area_name = serializers.CharField(source="area.name", read_only=True, default="")
    owner_name = serializers.CharField(source="area.owner.get_full_name", read_only=True, default="")
    status = serializers.SerializerMethodField()
    next_review_at = serializers.SerializerMethodField()
    is_gap = serializers.SerializerMethodField()

    class Meta:
        model = KnowledgePiece
        fields = ["id", "area", "area_name", "owner_name", "title", "kind", "kind_display",
                  "source_path", "summary", "last_verified_at", "verified_by",
                  "review_interval_days", "status", "next_review_at", "is_gap",
                  "created_at", "updated_at"]
        read_only_fields = ["id", "area_name", "owner_name", "kind_display", "last_verified_at",
                            "verified_by", "status", "next_review_at", "is_gap",
                            "created_at", "updated_at"]

    def get_status(self, piece: KnowledgePiece) -> str:
        return knowledge.freshness(piece)

    def get_next_review_at(self, piece: KnowledgePiece) -> str | None:
        vence = knowledge.due_date(piece)
        return vence.isoformat() if vence else None

    def get_is_gap(self, piece: KnowledgePiece) -> bool:
        """Peça sem arquivo é **lacuna tácita** — o que só alguém sabe e ainda não está escrito."""
        return not piece.source_path


class NotificationSerializer(serializers.ModelSerializer[Notification]):
    class Meta:
        model = Notification
        fields = ["id", "kind", "message", "url", "read", "created_at"]
        read_only_fields = fields


class LeadSerializer(serializers.ModelSerializer[Lead]):
    class Meta:
        model = Lead
        fields = [
            "id", "name", "email", "company", "phone", "cnpj", "message", "source", "status",
            "ai_fit", "ai_score", "ai_summary", "ai_recommended_action", "qualified_at",
            "enrichment", "client", "opportunity", "created_at", "updated_at",
        ]
        read_only_fields = [
            "id", "source", "ai_fit", "ai_score", "ai_summary", "ai_recommended_action",
            # `enrichment` é retrato do fornecedor, não campo de trabalho: editável pela tela, ele
            # deixaria de responder "o que a Receita diz" e passaria a responder "o que alguém
            # digitou", que é a diferença entre dado enriquecido e dado inventado.
            "qualified_at", "enrichment", "client", "opportunity", "created_at", "updated_at",
        ]


class LeadIntakeSerializer(serializers.Serializer):
    name = serializers.CharField(max_length=255)
    email = serializers.EmailField()
    company = serializers.CharField(max_length=255, required=False, allow_blank=True)
    phone = serializers.CharField(max_length=32, required=False, allow_blank=True)
    # Opcional, e tem de continuar opcional: é a chave do enriquecimento (FDD 030), mas exigi-lo
    # colocaria um campo a mais entre o visitante e o formulário enviado — trocar volume de lead
    # por qualidade de cadastro é o negócio errado para quem depende de demanda de topo.
    cnpj = serializers.CharField(max_length=18, required=False, allow_blank=True)
    message = serializers.CharField(required=False, allow_blank=True)
    # Respostas de perguntas de triagem do formulário (rótulo → resposta), usadas na qualificação.
    answers = serializers.DictField(child=serializers.CharField(allow_blank=True), required=False)
    website = serializers.CharField(required=False, allow_blank=True)  # honeypot anti-spam


class BookingCreateSerializer(serializers.Serializer):
    token = serializers.CharField()
    slot_start = serializers.DateTimeField()


class TaskSyncSerializer(serializers.Serializer):
    """Entrada do webhook de sincronia (Linear/GitHub → Biahflow)."""

    source = serializers.ChoiceField(choices=["linear", "github"])
    external_id = serializers.CharField(max_length=128)
    external_status = serializers.CharField(max_length=64)


class LinkExternalSerializer(serializers.Serializer):
    """Vincula uma Task a uma issue existente no fornecedor."""

    source = serializers.ChoiceField(choices=["linear", "github"])
    external_id = serializers.CharField(max_length=128)


class InvitationSerializer(serializers.ModelSerializer[Invitation]):
    class Meta:
        model = Invitation
        fields = ["id", "email", "role", "expires_at", "accepted_at", "created_at"]
        read_only_fields = ["id", "expires_at", "accepted_at", "created_at"]


class AcceptInvitationSerializer(serializers.Serializer):
    token = serializers.UUIDField()
    username = serializers.CharField(max_length=150)
    password = serializers.CharField(write_only=True)
    first_name = serializers.CharField(max_length=150, required=False, allow_blank=True)
    last_name = serializers.CharField(max_length=150, required=False, allow_blank=True)

    def validate_username(self, value: str) -> str:
        # Sem isso o `create_user` da view estourava `IntegrityError` — 500 em vez de 400.
        if User.objects.filter(username__iexact=value).exists():
            raise serializers.ValidationError("Este nome de usuário já está em uso.")
        return value

    def validate(self, attrs: dict[str, Any]) -> dict[str, Any]:
        # A validação é de objeto, não de campo, porque o `UserAttributeSimilarityValidator`
        # desiste sem um `user` — passar só a senha o tornaria decorativo. O usuário aqui é
        # instanciado e não salvo, só para o validador ter o que comparar. O e-mail fica de fora:
        # ele vem do `Invitation`, que só é resolvido na view.
        candidate = User(
            username=attrs["username"],
            first_name=attrs.get("first_name", ""),
            last_name=attrs.get("last_name", ""),
        )
        try:
            validate_password(attrs["password"], user=candidate)
        except DjangoValidationError as exc:
            raise serializers.ValidationError({"password": list(exc.messages)}) from exc
        return attrs


class LoginSerializer(serializers.Serializer):
    username = serializers.CharField(max_length=150)
    password = serializers.CharField(write_only=True)
