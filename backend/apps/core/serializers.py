from __future__ import annotations

import os
import re
from datetime import date
from typing import Any, cast

from django.contrib.auth.password_validation import validate_password
from django.core.exceptions import ValidationError as DjangoValidationError
from django.core.files.uploadedfile import UploadedFile
from drf_spectacular.utils import extend_schema_field
from rest_framework import serializers

from . import drive
from .models import (
    ARTIFACT_TRANSITIONS,
    Artifact,
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
    ProjectMember,
    ProjectPhase,
    Service,
    SignatureRequest,
    Task,
    User,
)


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
    class Meta:
        model = Client
        fields = ["id", "name", "legal_name", "tax_id", "owner", "status", "created_at", "updated_at"]
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
        fields = ["id", "name", "description", "position", "deliverables"]
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

    class Meta:
        model = Opportunity
        fields = [
            "id", "client", "contact", "title", "scope", "estimated_value", "stage", "stage_name",
            "owner", "expected_close_date", "service", "service_name", "service_tier", "project",
            "created_at", "updated_at",
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

    def validate(self, attrs: dict[str, object]) -> dict[str, object]:
        client = cast(Client | None, attrs.get("client", getattr(self.instance, "client", None)))
        contact = cast(Contact | None, attrs.get("contact", getattr(self.instance, "contact", None)))
        if contact and client and contact.client_id != client.id:
            raise serializers.ValidationError({"contact": "O contato deve pertencer ao cliente selecionado."})
        return attrs


class ProjectSerializer(serializers.ModelSerializer[Project]):
    is_overdue = serializers.SerializerMethodField()

    class Meta:
        model = Project
        fields = [
            "id", "client", "opportunity", "name", "description", "owner", "start_date", "due_date",
            "status", "service", "actual_value", "cost", "is_overdue", "created_at", "updated_at",
            "ai_maturity", "ai_opportunity", "ai_dimensions", "ai_score_summary", "ai_scored_at",
            "ai_score_reviewed",
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
            document.drive_file_id, document.drive_link = drive.upload_document(document, uploaded_file)
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


class DigitalEmployeeSerializer(serializers.ModelSerializer[DigitalEmployee]):
    class Meta:
        model = DigitalEmployee
        fields = ["id", "project", "name", "area", "description", "status", "kpi_label",
                  "kpi_value", "hours_saved_month", "roi_month", "created_at", "updated_at"]
        read_only_fields = ["id", "created_at", "updated_at"]


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


class NotificationSerializer(serializers.ModelSerializer[Notification]):
    class Meta:
        model = Notification
        fields = ["id", "kind", "message", "url", "read", "created_at"]
        read_only_fields = fields


class LeadSerializer(serializers.ModelSerializer[Lead]):
    class Meta:
        model = Lead
        fields = [
            "id", "name", "email", "company", "phone", "message", "source", "status",
            "ai_fit", "ai_score", "ai_summary", "ai_recommended_action", "qualified_at",
            "client", "opportunity", "created_at", "updated_at",
        ]
        read_only_fields = [
            "id", "source", "ai_fit", "ai_score", "ai_summary", "ai_recommended_action",
            "qualified_at", "client", "opportunity", "created_at", "updated_at",
        ]


class LeadIntakeSerializer(serializers.Serializer):
    name = serializers.CharField(max_length=255)
    email = serializers.EmailField()
    company = serializers.CharField(max_length=255, required=False, allow_blank=True)
    phone = serializers.CharField(max_length=32, required=False, allow_blank=True)
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
