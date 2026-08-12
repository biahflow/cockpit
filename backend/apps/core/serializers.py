from __future__ import annotations

import logging
import os
import re
from datetime import date
from typing import Any, cast

from django.contrib.auth.password_validation import validate_password
from django.core.exceptions import ValidationError as DjangoValidationError
from django.core.files.uploadedfile import UploadedFile
from drf_spectacular.utils import extend_schema_field
from rest_framework import serializers

from . import blueprints, drive, knowledge
from .exceptions import DriveUnavailable
from .models import (
    ARTIFACT_TRANSITIONS,
    CASE_TRANSITIONS,
    INVOICE_TRANSITIONS,
    Artifact,
    BlueprintVariant,
    Case,
    Client,
    Contact,
    Decisao,
    DigitalEmployee,
    DigitalEmployeeBlueprint,
    Document,
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
        fields = ["id", "client", "name", "email", "phone", "job_title", "created_at", "updated_at"]
        read_only_fields = ["id", "created_at", "updated_at"]


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


class JourneyPhaseSerializer(serializers.ModelSerializer[JourneyPhase]):
    """Fase do template da Jornada de Transformação (config admin, vocabulário editável)."""

    deliverables = PhaseDeliverableSerializer(many=True, read_only=True)

    class Meta:
        model = JourneyPhase
        fields = ["id", "name", "description", "position", "active", "deliverables"]
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


class ProjectPhaseSerializer(serializers.ModelSerializer[ProjectPhase]):
    """Fase da jornada de um projeto (estado). Só `target_date` é editável pela equipe."""

    phase_name = serializers.CharField(source="phase.name", read_only=True)
    phase_description = serializers.CharField(source="phase.description", read_only=True)
    phase_position = serializers.IntegerField(source="phase.position", read_only=True)
    deliverables = ProjectDeliverableSerializer(many=True, read_only=True)

    class Meta:
        model = ProjectPhase
        fields = [
            "id", "project", "phase", "phase_name", "phase_description", "phase_position",
            "status", "started_at", "completed_at", "target_date", "deliverables",
        ]
        read_only_fields = [
            "id", "project", "phase", "phase_name", "phase_description", "phase_position",
            "status", "started_at", "completed_at", "deliverables",
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
