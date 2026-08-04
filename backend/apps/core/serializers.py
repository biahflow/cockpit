from __future__ import annotations

from datetime import date
from typing import cast

from django.contrib.auth.password_validation import validate_password
from django.core.exceptions import ValidationError as DjangoValidationError
from django.core.files.uploadedfile import UploadedFile
from rest_framework import serializers

from . import drive
from .models import (
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


class UserSerializer(serializers.ModelSerializer[User]):
    class Meta:
        model = User
        fields = ["id", "username", "first_name", "last_name", "email", "role"]
        read_only_fields = ["id"]


class ClientSerializer(serializers.ModelSerializer[Client]):
    class Meta:
        model = Client
        fields = ["id", "name", "legal_name", "tax_id", "owner", "status", "created_at", "updated_at"]
        read_only_fields = ["id", "owner", "status", "created_at", "updated_at"]


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

    class Meta:
        model = Opportunity
        fields = [
            "id", "client", "contact", "title", "scope", "estimated_value", "stage", "stage_name",
            "owner", "expected_close_date", "created_at", "updated_at",
        ]
        read_only_fields = ["id", "owner", "created_at", "updated_at"]

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
        fields = ["id", "project", "title", "date", "recording_url", "transcript", "status",
                  "created_at", "updated_at"]
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
        fields = ["id", "signer_email", "status", "reminded_at", "signed_at", "created_at"]
        read_only_fields = fields


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
        return attrs

    def create(self, validated_data: dict[str, object]) -> Document:
        uploaded_file = cast(UploadedFile, validated_data.pop("file"))
        document = Document(
            **validated_data,
            original_name=uploaded_file.name or "documento",
            uploaded_by=self.context["request"].user,
        )
        if drive.is_enabled():
            document.drive_file_id, document.drive_link = drive.upload_document(document, uploaded_file)
        else:
            document.file = uploaded_file
        document.save()
        return document


class ServiceSerializer(serializers.ModelSerializer[Service]):
    class Meta:
        model = Service
        fields = ["id", "name", "active", "created_at", "updated_at"]
        read_only_fields = ["id", "created_at", "updated_at"]


class DigitalEmployeeSerializer(serializers.ModelSerializer[DigitalEmployee]):
    class Meta:
        model = DigitalEmployee
        fields = ["id", "project", "name", "area", "description", "status", "kpi_label",
                  "kpi_value", "hours_saved_month", "roi_month", "created_at", "updated_at"]
        read_only_fields = ["id", "created_at", "updated_at"]


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

    def validate_password(self, value: str) -> str:
        try:
            validate_password(value)
        except DjangoValidationError as exc:
            raise serializers.ValidationError(list(exc.messages)) from exc
        return value


class LoginSerializer(serializers.Serializer):
    username = serializers.CharField(max_length=150)
    password = serializers.CharField(write_only=True)
