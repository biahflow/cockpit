from __future__ import annotations

import uuid
from datetime import date

from django.contrib.auth.models import AbstractUser
from django.core.exceptions import ValidationError
from django.db import models
from django.db.models import Q
from django.utils import timezone


class TimestampedModel(models.Model):
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    archived_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        abstract = True

    @property
    def is_archived(self) -> bool:
        return self.archived_at is not None

    def archive(self) -> None:
        self.archived_at = timezone.now()
        self.save(update_fields=["archived_at", "updated_at"])


class User(AbstractUser):
    class Role(models.TextChoices):
        ADMIN = "admin", "Administrador"
        SALES = "sales", "Vendas"
        DELIVERY = "delivery", "Entrega"

    role = models.CharField(max_length=16, choices=Role.choices, default=Role.DELIVERY)

    @property
    def is_admin_role(self) -> bool:
        return self.role == self.Role.ADMIN or self.is_superuser


class Vertical(models.Model):
    """O setor do cliente — o eixo que o domínio não tinha (FDD 026).

    Taxonomia, não enum: é `PipelineStage`/`JourneyPhase` de novo — vocabulário que o admin edita,
    porque cravar "imobiliária, saúde, telecom" no código repetiria o erro de `DigitalEmployee.area`,
    que nasceu texto livre e por isso não filtra nem agrega. `active` aposenta sem reescrever
    histórico: uma vertical inativa some das escolhas novas e continua nos clientes que já a têm.
    """

    name = models.CharField(max_length=80)
    slug = models.SlugField(max_length=80, unique=True)
    position = models.PositiveIntegerField(default=0)
    active = models.BooleanField(default=True)

    class Meta:
        ordering = ["position", "id"]

    def __str__(self) -> str:
        return self.name


class Client(TimestampedModel):
    class Status(models.TextChoices):
        PROSPECT = "prospect", "Prospect"
        ACTIVE = "active", "Ativo"

    name = models.CharField(max_length=255)
    legal_name = models.CharField(max_length=255, blank=True)
    tax_id = models.CharField(max_length=32, blank=True)
    # Aditivo e opcional, na forma de `Opportunity.service`: é o que a instanciação de Funcionário
    # Digital usa como padrão e o que escolhe a variante do blueprint (FDD 026).
    vertical = models.ForeignKey(
        Vertical, on_delete=models.SET_NULL, null=True, blank=True, related_name="clients"
    )
    owner = models.ForeignKey(User, on_delete=models.PROTECT, related_name="owned_clients")
    drive_folder_id = models.CharField(max_length=128, blank=True, default="")
    # Quem cadastra afirma o status (a SPA oferece a escolha); o default é o mais conservador,
    # porque um POST que omite o campo não deve alegar uma venda que não houve. O cliente vindo de
    # conversão de lead também nasce "prospect", e vira "active" pelo signal quando a oportunidade
    # é ganha — promoção que um PATCH não desfaz (ver `ClientSerializer.validate_status`).
    status = models.CharField(max_length=16, choices=Status.choices, default=Status.PROSPECT)

    class Meta:
        ordering = ["name"]

    def __str__(self) -> str:
        return self.name


class Contact(TimestampedModel):
    client = models.ForeignKey(Client, on_delete=models.CASCADE, related_name="contacts")
    name = models.CharField(max_length=255)
    email = models.EmailField(blank=True)
    phone = models.CharField(max_length=32, blank=True)
    job_title = models.CharField(max_length=128, blank=True)

    class Meta:
        ordering = ["name"]


class PipelineStage(models.Model):
    class Kind(models.TextChoices):
        OPEN = "open", "Aberta"
        WON = "won", "Ganho"
        LOST = "lost", "Perdido"

    name = models.CharField(max_length=80)
    kind = models.CharField(max_length=8, choices=Kind.choices, default=Kind.OPEN)
    position = models.PositiveIntegerField(default=0)

    class Meta:
        ordering = ["position", "id"]
        constraints = [
            models.UniqueConstraint(
                fields=["kind"], condition=Q(kind="won"), name="one_won_pipeline_stage"
            ),
            models.UniqueConstraint(
                fields=["kind"], condition=Q(kind="lost"), name="one_lost_pipeline_stage"
            ),
        ]

    def __str__(self) -> str:
        return self.name


class Opportunity(TimestampedModel):
    client = models.ForeignKey(Client, on_delete=models.PROTECT, related_name="opportunities")
    contact = models.ForeignKey(Contact, on_delete=models.SET_NULL, null=True, blank=True)
    title = models.CharField(max_length=255)
    scope = models.TextField(blank=True)
    estimated_value = models.DecimalField(max_digits=12, decimal_places=2)
    stage = models.ForeignKey(PipelineStage, on_delete=models.PROTECT, related_name="opportunities")
    owner = models.ForeignKey(User, on_delete=models.PROTECT, related_name="owned_opportunities")
    expected_close_date = models.DateField()
    # Nível de produto sendo vendido; herdado pelo projeto na conversão e usado na proposta.
    service = models.ForeignKey(
        "Service", on_delete=models.SET_NULL, null=True, blank=True, related_name="opportunities"
    )

    class Meta:
        ordering = ["expected_close_date", "id"]

    @property
    def is_won(self) -> bool:
        return self.stage.kind == PipelineStage.Kind.WON


class ProjectQuerySet(models.QuerySet["Project"]):
    def visible_to(self, user: User) -> ProjectQuerySet:
        """Projetos que a pessoa pode ver — a fronteira de acesso da Entrega.

        Admin e Vendas enxergam tudo (o comercial precisa acompanhar a carteira inteira);
        Entrega vê só aquilo de que participa. É a **única** expressão da regra: viewsets,
        agregadores e permissão de objeto derivam daqui, para não repetir o critério em SQL
        num lugar e em Python no outro. Ver RFC 0003 e ADR 0010.
        """
        if user.is_admin_role or user.role != User.Role.DELIVERY:
            return self
        return self.filter(members__user=user, members__archived_at__isnull=True)


def project_scope_q(user: User, path: str = "project") -> models.Q:
    """O mesmo recorte, para quem filtra *através* de um projeto (ex.: `Task`).

    `path` é o caminho até o projeto a partir do modelo consultado (`""` no próprio `Project`).
    """
    if user.is_admin_role or user.role != User.Role.DELIVERY:
        return models.Q()
    prefix = f"{path}__" if path else ""
    return models.Q(**{
        f"{prefix}members__user": user,
        f"{prefix}members__archived_at__isnull": True,
    })


def can_access_project(user: User, project: Project) -> bool:
    """O mesmo recorte, sobre **um** projeto já em mãos.

    A terceira forma da mesma pergunta, e como as outras duas ela deriva de `visible_to` em vez de
    reescrever o critério: quem filtra queryset usa `visible_to`, quem filtra *através* de um
    projeto usa `project_scope_q`, e quem tem o projeto na mão usa esta. `permissions._participates`
    delega aqui depois de resolver o projeto do objeto.

    Serve a quem decide fora de uma view — o alvo de uma notificação, por exemplo, que pode ser
    escolhido por um webhook ou por um job agendado, onde não há `request.user` nem permissão de
    DRF para fazer a pergunta (FDD 010, FDD 018).
    """
    return Project.objects.visible_to(user).filter(pk=project.pk).exists()


class Project(TimestampedModel):
    class Status(models.TextChoices):
        PLANNING = "planning", "Planejamento"
        ACTIVE = "active", "Ativo"
        ON_HOLD = "on_hold", "Em espera"
        COMPLETED = "completed", "Concluído"

    client = models.ForeignKey(Client, on_delete=models.PROTECT, related_name="projects")
    opportunity = models.OneToOneField(
        Opportunity, on_delete=models.PROTECT, related_name="project", null=True, blank=True
    )
    name = models.CharField(max_length=255)
    description = models.TextField(blank=True)
    owner = models.ForeignKey(User, on_delete=models.PROTECT, related_name="owned_projects")
    start_date = models.DateField()
    due_date = models.DateField()
    status = models.CharField(max_length=16, choices=Status.choices, default=Status.PLANNING)
    service = models.ForeignKey(
        "Service", on_delete=models.SET_NULL, null=True, blank=True, related_name="projects"
    )
    actual_value = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    cost = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    drive_folder_id = models.CharField(max_length=128, blank=True, default="")
    # AI Score de maturidade/oportunidade de IA (Fase 4 — FDD 014). Gerado a partir da
    # transcrição de uma reunião (Discovery/Assessment) e revisado por humano antes de cruzar
    # ao portal do cliente. Vazio até a IA rodar; só publica quando `ai_score_reviewed`.
    ai_maturity = models.PositiveSmallIntegerField(null=True, blank=True)  # 0–100
    ai_opportunity = models.PositiveSmallIntegerField(null=True, blank=True)  # 0–100
    ai_dimensions = models.JSONField(default=list, blank=True)  # [{"label": str, "score": 0-100}]
    ai_score_summary = models.TextField(blank=True, default="")
    ai_scored_at = models.DateTimeField(null=True, blank=True)
    ai_score_reviewed = models.BooleanField(default=False)
    ai_score_meeting = models.ForeignKey(
        "Meeting", on_delete=models.SET_NULL, null=True, blank=True, related_name="+"
    )

    objects = ProjectQuerySet.as_manager()

    class Meta:
        ordering = ["due_date", "id"]

    def clean(self) -> None:
        if self.due_date < self.start_date:
            raise ValidationError({"due_date": "A data final não pode ser anterior à inicial."})

    @property
    def current_phase(self) -> ProjectPhase | None:
        """Fase da jornada em andamento (a que o cliente/equipe está "vivendo" agora)."""
        return (
            self.phases.filter(status=ProjectPhase.Status.ACTIVE, archived_at__isnull=True)
            .order_by("phase__position", "id")
            .first()
        )


class ProjectMember(TimestampedModel):
    """Quem participa do projeto — a fronteira de acesso da Entrega (RFC 0003, ADR 0010).

    Antes não havia como dizer "esta pessoa é deste projeto": a única ligação pessoa↔trabalho
    era `owner`, sempre igual a quem criou o registro e read-only na API. Sem isso, restringir
    Entrega aos seus projetos deixaria todo mundo sem ver nada, porque na conversão o dono do
    projeto e de todos os marcos/tarefas é o vendedor.

    Sem papel dentro do projeto de propósito: quem é da equipe, é. O papel de produto já vive
    em `User.role`, e um segundo eixo agora seria adivinhar requisito.
    """

    project = models.ForeignKey(Project, on_delete=models.CASCADE, related_name="members")
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name="project_memberships")
    # Conceder acesso é ato de segurança: sem isto não há cadeia de quem colocou quem.
    # Nulo quando a linha veio do backfill da migração 0025, que não tem autor.
    added_by = models.ForeignKey(
        User, on_delete=models.SET_NULL, null=True, blank=True, related_name="+"
    )

    class Meta:
        ordering = ["user__first_name", "user__username", "id"]
        constraints = [
            # Condicional ao arquivamento: sair da equipe e voltar depois é rotina, e uma
            # constraint cega sobre as linhas arquivadas travaria a readmissão.
            models.UniqueConstraint(
                fields=["project", "user"],
                condition=models.Q(archived_at__isnull=True),
                name="unique_active_project_member",
            ),
        ]

    def __str__(self) -> str:
        return f"{self.user} @ {self.project}"


class WorkItem(TimestampedModel):
    class Status(models.TextChoices):
        TODO = "todo", "A fazer"
        IN_PROGRESS = "in_progress", "Em andamento"
        DONE = "done", "Concluído"

    class Party(models.TextChoices):
        PROVIDER = "provider", "Fornecedor"
        CLIENT = "client", "Cliente"

    project = models.ForeignKey(Project, on_delete=models.CASCADE, related_name="%(class)s_items")
    title = models.CharField(max_length=255)
    description = models.TextField(blank=True)
    owner = models.ForeignKey(User, on_delete=models.PROTECT, related_name="%(class)s_items")
    due_date = models.DateField()
    completed_at = models.DateTimeField(null=True, blank=True)
    status = models.CharField(max_length=16, choices=Status.choices, default=Status.TODO)
    # Lado responsável pelo item (alimenta o "quem" do cronograma no portal do cliente).
    party = models.CharField(max_length=16, choices=Party.choices, default=Party.PROVIDER)
    # Where this item is mirrored/originated from ("biahflow" = native) and the id it
    # carries in that system (e.g. a Linear/GitHub issue). Biahflow stays the source of
    # truth; these only map an item to its external twin for sync. See ADR 0004.
    source = models.CharField(max_length=32, default="biahflow")
    external_id = models.CharField(max_length=128, blank=True, default="")

    class Meta:
        abstract = True
        ordering = ["due_date", "id"]
        constraints = [
            models.UniqueConstraint(
                fields=["source", "external_id"],
                condition=models.Q(external_id__gt=""),
                name="%(app_label)s_%(class)s_unique_external_ref",
            )
        ]

    @property
    def is_overdue(self) -> bool:
        return self.status != self.Status.DONE and self.due_date < date.today()

    def save(self, *args, **kwargs) -> None:
        if self.status == self.Status.DONE and self.completed_at is None:
            self.completed_at = timezone.now()
        if self.status != self.Status.DONE:
            self.completed_at = None
        super().save(*args, **kwargs)


class Milestone(WorkItem):
    pass


class Task(WorkItem):
    milestone = models.ForeignKey(
        Milestone, on_delete=models.SET_NULL, related_name="tasks", null=True, blank=True
    )

    def clean(self) -> None:
        if self.milestone_id and self.milestone and self.milestone.project_id != self.project_id:
            raise ValidationError({"milestone": "O marco deve pertencer ao mesmo projeto."})


class Document(TimestampedModel):
    client = models.ForeignKey(Client, on_delete=models.CASCADE, null=True, blank=True)
    opportunity = models.ForeignKey(Opportunity, on_delete=models.CASCADE, null=True, blank=True)
    project = models.ForeignKey(Project, on_delete=models.CASCADE, null=True, blank=True)
    file = models.FileField(upload_to="documents/%Y/%m/", blank=True)
    drive_file_id = models.CharField(max_length=128, blank=True, default="")
    drive_link = models.URLField(blank=True, default="")
    original_name = models.CharField(max_length=255)
    uploaded_by = models.ForeignKey(User, on_delete=models.PROTECT, related_name="uploaded_documents")

    def clean(self) -> None:
        links = [self.client_id, self.opportunity_id, self.project_id]
        if sum(value is not None for value in links) != 1:
            raise ValidationError("O documento deve estar vinculado a exatamente um recurso.")

    @property
    def linked_resource(self) -> Client | Opportunity | Project | None:
        return self.client or self.opportunity or self.project


class Meeting(TimestampedModel):
    """Reunião do projeto (registro manual, com links de gravação/transcrição)."""

    class Status(models.TextChoices):
        SCHEDULED = "scheduled", "Agendada"
        HELD = "held", "Realizada"

    project = models.ForeignKey(Project, on_delete=models.CASCADE, related_name="meetings")
    title = models.CharField(max_length=255)
    date = models.DateField()
    # Dois links, porque são dois momentos: `meeting_url` é a sala/convite de uma reunião que
    # ainda vai acontecer; `recording_url` é o registro do que aconteceu. Um campo só obrigaria
    # a escolher entre agendar e arquivar. O portal do cliente recebe só a gravação (ADR 0005).
    meeting_url = models.URLField(blank=True, default="")
    recording_url = models.URLField(blank=True, default="")
    transcript = models.TextField(blank=True, default="")  # texto ou URL
    status = models.CharField(max_length=16, choices=Status.choices, default=Status.SCHEDULED)

    class Meta:
        ordering = ["-date", "-id"]


class Pendencia(TimestampedModel):
    """Pendência/decisão do projeto, voltada ao acompanhamento do cliente."""

    class Status(models.TextChoices):
        OPEN = "open", "Aberta"
        RESOLVED = "resolved", "Resolvida"

    project = models.ForeignKey(Project, on_delete=models.CASCADE, related_name="pendencias")
    title = models.CharField(max_length=255)
    description = models.TextField(blank=True)
    status = models.CharField(max_length=16, choices=Status.choices, default=Status.OPEN)
    party = models.CharField(
        max_length=16, choices=WorkItem.Party.choices, default=WorkItem.Party.PROVIDER
    )
    owner = models.ForeignKey(
        User, on_delete=models.SET_NULL, null=True, blank=True, related_name="pendencias"
    )
    resolved_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["status", "-created_at"]

    def save(self, *args, **kwargs) -> None:
        if self.status == self.Status.RESOLVED and self.resolved_at is None:
            self.resolved_at = timezone.now()
        if self.status != self.Status.RESOLVED:
            self.resolved_at = None
        super().save(*args, **kwargs)


class Invitation(models.Model):
    email = models.EmailField(unique=True)
    role = models.CharField(max_length=16, choices=User.Role.choices)
    token = models.UUIDField(default=uuid.uuid4, unique=True, editable=False)
    invited_by = models.ForeignKey(User, on_delete=models.PROTECT, related_name="sent_invitations")
    expires_at = models.DateTimeField()
    accepted_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    @property
    def is_expired(self) -> bool:
        return timezone.now() >= self.expires_at


class Lead(TimestampedModel):
    class Status(models.TextChoices):
        NEW = "new", "Novo"
        CONTACTED = "contacted", "Contatado"
        QUALIFIED = "qualified", "Qualificado"
        DISCARDED = "discarded", "Descartado"

    class Fit(models.TextChoices):
        HIGH = "high", "Alto"
        MEDIUM = "medium", "Médio"
        LOW = "low", "Baixo"

    name = models.CharField(max_length=255)
    email = models.EmailField()
    company = models.CharField(max_length=255, blank=True)
    phone = models.CharField(max_length=32, blank=True)
    message = models.TextField(blank=True)
    source = models.CharField(max_length=64, default="site")
    status = models.CharField(max_length=16, choices=Status.choices, default=Status.NEW)
    # Qualificação por IA (rascunho para revisão humana — FDD 013). Vazio até a IA rodar.
    ai_fit = models.CharField(max_length=8, choices=Fit.choices, blank=True, default="")
    ai_score = models.PositiveSmallIntegerField(null=True, blank=True)
    ai_summary = models.TextField(blank=True, default="")
    ai_recommended_action = models.TextField(blank=True, default="")
    qualified_at = models.DateTimeField(null=True, blank=True)
    client = models.ForeignKey(Client, on_delete=models.SET_NULL, null=True, blank=True, related_name="leads")
    opportunity = models.ForeignKey(
        Opportunity, on_delete=models.SET_NULL, null=True, blank=True, related_name="leads"
    )

    class Meta:
        ordering = ["-created_at"]

    def __str__(self) -> str:
        return f"{self.name} <{self.email}>"


class Booking(TimestampedModel):
    """Reunião de pré-venda agendada por um lead qualificado (FDD 013).

    Diferente de `Meeting` (presa a um projeto), guarda o agendamento no próprio lead, antes
    de existir oportunidade/projeto. O evento correspondente vive no Google Calendar.
    """

    class Status(models.TextChoices):
        SCHEDULED = "scheduled", "Agendada"
        HELD = "held", "Realizada"
        CANCELED = "canceled", "Cancelada"

    lead = models.ForeignKey(Lead, on_delete=models.CASCADE, related_name="bookings")
    owner = models.ForeignKey(
        User, on_delete=models.SET_NULL, null=True, blank=True, related_name="bookings"
    )
    starts_at = models.DateTimeField()
    ends_at = models.DateTimeField()
    attendee_email = models.EmailField()
    status = models.CharField(max_length=16, choices=Status.choices, default=Status.SCHEDULED)
    calendar_event_id = models.CharField(max_length=128, blank=True, default="")
    calendar_link = models.URLField(blank=True, default="")

    class Meta:
        ordering = ["starts_at"]

    def __str__(self) -> str:
        return f"{self.lead.name} @ {self.starts_at:%Y-%m-%d %H:%M}"


class Service(TimestampedModel):
    """Catálogo de serviços e, quando `tier` estiver preenchido, os níveis de produto.

    Os três níveis da metodologia (Discovery Express grátis, Discovery + Assessment pago e
    Implantação) são registros semeados com `tier`; serviços avulsos ficam com `tier` vazio.
    """

    class Tier(models.TextChoices):
        DISCOVERY_EXPRESS = "discovery_express", "Discovery Express"
        DISCOVERY_ASSESSMENT = "discovery_assessment", "Discovery + Assessment"
        IMPLEMENTATION = "implantacao", "Implantação"

    name = models.CharField(max_length=120)
    active = models.BooleanField(default=True)
    tier = models.CharField(max_length=32, choices=Tier.choices, blank=True, default="")
    list_price = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    summary = models.TextField(blank=True, default="")

    class Meta:
        ordering = ["name"]
        constraints = [
            models.UniqueConstraint(
                fields=["tier"],
                condition=~Q(tier="") & Q(archived_at__isnull=True),
                name="one_active_service_per_tier",
            )
        ]

    def __str__(self) -> str:
        return self.name

    @property
    def is_free(self) -> bool:
        return self.list_price == 0


class SignatureRequest(models.Model):
    class Status(models.TextChoices):
        PENDING = "pending", "Pendente"
        SIGNED = "signed", "Assinado"
        DECLINED = "declined", "Recusado"

    document = models.ForeignKey(Document, on_delete=models.CASCADE, related_name="signature_requests")
    signer_email = models.EmailField()
    status = models.CharField(max_length=16, choices=Status.choices, default=Status.PENDING)
    # Referências do fornecedor (ADR 0007): `provider_ref` casa 1:1 com o signatário e é a
    # chave de busca do webhook; `document_ref` é o fallback junto com o e-mail.
    provider_ref = models.CharField(max_length=128, blank=True, default="", db_index=True)
    document_ref = models.CharField(max_length=128, blank=True, default="")
    sign_url = models.URLField(blank=True, default="")  # link do signatário, vai no lembrete
    reminded_at = models.DateTimeField(null=True, blank=True)
    signed_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]


class Notification(models.Model):
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name="notifications")
    kind = models.CharField(max_length=32)
    message = models.CharField(max_length=255)
    url = models.CharField(max_length=255, blank=True, default="")
    read = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["read", "-created_at"]


class AppSetting(models.Model):
    """Override em runtime das flags de integração (ver flags.py).

    Uma linha por integração (`key`). Ausente = usa o default vindo do ambiente (.env).
    Segredos/keys continuam no ambiente; aqui só mora o liga/desliga.
    """

    key = models.CharField(max_length=32, unique=True)
    enabled = models.BooleanField(default=False)
    updated_at = models.DateTimeField(auto_now=True)
    updated_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True)

    def __str__(self) -> str:
        return f"{self.key}={'on' if self.enabled else 'off'}"


class AiInteraction(models.Model):
    """Registro de auditoria de cada uso de IA (rastreabilidade + base do limite de uso)."""

    # user é nulo em ações sem usuário autenticado (ex.: qualificação de lead vinda do intake público).
    user = models.ForeignKey(
        User, on_delete=models.SET_NULL, null=True, blank=True, related_name="ai_interactions"
    )
    feature = models.CharField(max_length=32)
    project = models.ForeignKey(Project, on_delete=models.SET_NULL, null=True, blank=True)
    opportunity = models.ForeignKey(Opportunity, on_delete=models.SET_NULL, null=True, blank=True)
    lead = models.ForeignKey("Lead", on_delete=models.SET_NULL, null=True, blank=True)
    prompt_tokens = models.PositiveIntegerField(default=0)
    completion_tokens = models.PositiveIntegerField(default=0)
    rating = models.SmallIntegerField(null=True, blank=True)  # +1 (👍) / -1 (👎) / None
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]


class JourneyPhase(models.Model):
    """Template global e configurável das fases da Jornada de Transformação (FDD 011).

    Espelha o padrão de `PipelineStage`: registros ordenáveis/editáveis, onde mora o
    vocabulário da metodologia (Welcome → … → Optimize) — nomes são dados, não código.
    Cada `Project` instancia essas fases em `ProjectPhase` (ver `journey.py`).
    """

    name = models.CharField(max_length=80)
    description = models.TextField(blank=True, default="")
    position = models.PositiveIntegerField(default=0)
    # Aposentar uma fase da metodologia sem reescrever o histórico. `ProjectPhase.phase` é
    # `PROTECT`, então uma fase materializada não pode mais ser excluída — e excluí-la também
    # não seria o que se quer: os projetos em andamento passaram por ela. Inativa, ela deixa de
    # ser herdada por projeto novo (`journey.materialize_journey`) e os antigos ficam com a
    # delas. É a saída que a recusa da exclusão oferece (FDD 011, FDD 025).
    active = models.BooleanField(default=True)

    class Meta:
        ordering = ["position", "id"]

    def __str__(self) -> str:
        return self.name


class PhaseDeliverable(models.Model):
    """Template dos entregáveis que cada fase "desbloqueia" ao ser concluída."""

    phase = models.ForeignKey(JourneyPhase, on_delete=models.CASCADE, related_name="deliverables")
    name = models.CharField(max_length=160)
    position = models.PositiveIntegerField(default=0)

    class Meta:
        ordering = ["position", "id"]

    def __str__(self) -> str:
        return self.name


class ProjectPhase(TimestampedModel):
    """Instância por projeto × fase — o estado da jornada de transformação do projeto.

    Uma fase por vez fica `active` ("você está aqui"); as anteriores ficam `done` e as
    seguintes `locked`. Materializado a partir de `JourneyPhase` na criação do projeto.
    """

    class Status(models.TextChoices):
        LOCKED = "locked", "Bloqueada"
        ACTIVE = "active", "Em andamento"
        DONE = "done", "Concluída"

    project = models.ForeignKey(Project, on_delete=models.CASCADE, related_name="phases")
    phase = models.ForeignKey(JourneyPhase, on_delete=models.PROTECT, related_name="project_phases")
    status = models.CharField(max_length=16, choices=Status.choices, default=Status.LOCKED)
    started_at = models.DateTimeField(null=True, blank=True)
    completed_at = models.DateTimeField(null=True, blank=True)
    target_date = models.DateField(null=True, blank=True)  # a "prevista" mostrada na UI

    class Meta:
        ordering = ["phase__position", "id"]
        constraints = [
            models.UniqueConstraint(fields=["project", "phase"], name="unique_project_phase")
        ]

    def __str__(self) -> str:
        return f"{self.project_id} · {self.phase.name}"


class ProjectDeliverable(TimestampedModel):
    """Instância por projeto de um entregável de fase (marca o "desbloqueio").

    O `name` é copiado do template para que editar o template não reescreva o histórico
    de projetos já em andamento. Pode apontar para o `Document` real quando existir.
    """

    class Status(models.TextChoices):
        PENDING = "pending", "Pendente"
        DELIVERED = "delivered", "Entregue"

    project_phase = models.ForeignKey(
        ProjectPhase, on_delete=models.CASCADE, related_name="deliverables"
    )
    name = models.CharField(max_length=160)
    status = models.CharField(max_length=16, choices=Status.choices, default=Status.PENDING)
    document = models.ForeignKey(
        Document, on_delete=models.SET_NULL, null=True, blank=True, related_name="deliverables"
    )
    position = models.PositiveIntegerField(default=0)
    delivered_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["position", "id"]

    def save(self, *args, **kwargs) -> None:
        if self.status == self.Status.DELIVERED and self.delivered_at is None:
            self.delivered_at = timezone.now()
        if self.status != self.Status.DELIVERED:
            self.delivered_at = None
        super().save(*args, **kwargs)


class DigitalEmployeeBlueprint(models.Model):
    """O catálogo de Funcionários Digitais — o bloco produtizado (FDD 026).

    Global, sem FK para projeto: é o "SDR" que serve imobiliária, saúde e telecom com a mesma
    espinha. A entrega **instancia** (ver `blueprints.instantiate`), não recria.

    A `area` aqui é fechada, e é o ponto: em `DigitalEmployee` ela é `CharField` livre e por isso
    não filtra, não agrega e não aparece em consulta nenhuma. Fechá-la lá seria quebrar o contrato
    `/api/v1/` e o que o snapshot já entrega ao cliente; fechá-la aqui não custa nada, porque o
    catálogo nasce agora.
    """

    class Area(models.TextChoices):
        COMMERCIAL = "comercial", "Comercial"
        FINANCE = "financeiro", "Financeiro"
        HR = "rh", "RH"
        LEGAL = "juridico", "Jurídico"
        SUPPORT = "atendimento", "Atendimento"

    name = models.CharField(max_length=120)
    area = models.CharField(max_length=24, choices=Area.choices, default=Area.COMMERCIAL)
    description = models.TextField(blank=True, default="")
    kpi_label = models.CharField(max_length=80, blank=True, default="")  # o KPI canônico do bloco
    default_hours_saved_month = models.DecimalField(max_digits=10, decimal_places=1, default=0)
    default_roi_month = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    # Opcional, para sugerir blueprints pelo nível de produto vendido (FDD 015).
    service = models.ForeignKey(
        Service, on_delete=models.SET_NULL, null=True, blank=True, related_name="blueprints"
    )
    active = models.BooleanField(default=True)

    class Meta:
        ordering = ["area", "name", "id"]

    def __str__(self) -> str:
        return self.name


class BlueprintVariant(models.Model):
    """A parametrização de um blueprint por vertical — é isto que produtiza o bloco (FDD 026).

    Um blueprint, N parametrizações. Campo em branco (ou decimal nulo) **herda** o do blueprint:
    a variante existe para dizer o que muda, não para repetir o que não muda.
    """

    blueprint = models.ForeignKey(
        DigitalEmployeeBlueprint, on_delete=models.CASCADE, related_name="variants"
    )
    vertical = models.ForeignKey(Vertical, on_delete=models.PROTECT, related_name="variants")
    description = models.TextField(blank=True, default="")
    kpi_label = models.CharField(max_length=80, blank=True, default="")
    default_hours_saved_month = models.DecimalField(
        max_digits=10, decimal_places=1, null=True, blank=True
    )
    default_roi_month = models.DecimalField(max_digits=12, decimal_places=2, null=True, blank=True)

    class Meta:
        ordering = ["vertical__position", "id"]
        constraints = [
            # Duas parametrizações do mesmo bloco para o mesmo setor não é configuração, é
            # ambiguidade: `resolve()` não saberia qual aplicar. Mesma forma de invariante que
            # `one_won_pipeline_stage` e `one_active_service_per_tier`.
            models.UniqueConstraint(
                fields=["blueprint", "vertical"], name="unique_blueprint_variant"
            )
        ]

    def __str__(self) -> str:
        return f"{self.blueprint.name} — {self.vertical.name}"


class DigitalEmployee(TimestampedModel):
    """Funcionário Digital — o agente de IA entregue ao cliente (o produto central).

    Vive no projeto e flui ao portal do cliente pelo snapshot (como a jornada e o health).
    KPI e ganhos (horas/ROI por mês) são preenchidos pela equipe; nada técnico vaza ao cliente.
    """

    class Status(models.TextChoices):
        BUILDING = "building", "Em construção"
        ACTIVE = "active", "Ativo"
        PAUSED = "paused", "Pausado"

    project = models.ForeignKey(Project, on_delete=models.CASCADE, related_name="digital_employees")
    # Procedência, não referência viva: os valores foram **copiados** do catálogo na instanciação
    # (FDD 026). `SET_NULL` porque saber de onde veio não pode impedir o catálogo de mudar — e a
    # cópia é justamente o que garante que mudá-lo não reescreve o que foi entregue.
    blueprint = models.ForeignKey(
        DigitalEmployeeBlueprint, on_delete=models.SET_NULL, null=True, blank=True,
        related_name="instances",
    )
    name = models.CharField(max_length=120)
    area = models.CharField(max_length=80, blank=True, default="")  # Financeiro, Atendimento…
    description = models.TextField(blank=True, default="")  # o que o funcionário digital faz
    status = models.CharField(max_length=16, choices=Status.choices, default=Status.BUILDING)
    kpi_label = models.CharField(max_length=80, blank=True, default="")
    kpi_value = models.CharField(max_length=80, blank=True, default="")
    hours_saved_month = models.DecimalField(max_digits=10, decimal_places=1, default=0)
    roi_month = models.DecimalField(max_digits=12, decimal_places=2, default=0)

    class Meta:
        ordering = ["name", "id"]

    def __str__(self) -> str:
        return self.name


# Transições válidas do artefato. Rascunho e revisão vão e voltam enquanto o humano trabalha;
# depois de enviado ao cliente só resta a decisão dele, que é terminal.
ARTIFACT_TRANSITIONS: dict[str, set[str]] = {
    "draft": {"review", "sent"},
    "review": {"draft", "sent"},
    "sent": {"accepted", "rejected"},
    "accepted": set(),
    "rejected": set(),
}


class Artifact(TimestampedModel):
    """Artefato da jornada comercial: Discovery, Assessment, Proposta ou Contrato (FDD 016).

    Antes disso o texto gerado pela IA era efêmero — a resposta HTTP era o único lugar onde ele
    existia, e só proposta/contrato sobreviviam se alguém os salvasse à mão como `Document`. Aqui
    o conteúdo passa a ter registro e estado próprios, o que também permite medir onde a jornada
    trava entre uma etapa e a seguinte.

    O `Document` continua sendo o arquivo (e o alvo da assinatura eletrônica); o artefato apenas
    o referencia quando o rascunho vira documento.
    """

    class Kind(models.TextChoices):
        DISCOVERY = "discovery", "Discovery"
        ASSESSMENT = "assessment", "Assessment"
        PROPOSAL = "proposal", "Proposta"
        CONTRACT = "contract", "Contrato"

    class Status(models.TextChoices):
        DRAFT = "draft", "Rascunho"
        REVIEW = "review", "Em revisão"
        SENT = "sent", "Enviado"
        ACCEPTED = "accepted", "Aceito"
        REJECTED = "rejected", "Recusado"

    kind = models.CharField(max_length=16, choices=Kind.choices)
    status = models.CharField(max_length=16, choices=Status.choices, default=Status.DRAFT)
    title = models.CharField(max_length=255)
    content = models.TextField(blank=True, default="")
    opportunity = models.ForeignKey(
        Opportunity, on_delete=models.SET_NULL, null=True, blank=True, related_name="artifacts"
    )
    project = models.ForeignKey(
        Project, on_delete=models.SET_NULL, null=True, blank=True, related_name="artifacts"
    )
    # Reunião de onde o texto foi extraído (Discovery/Assessment); vazio nos demais.
    source_meeting = models.ForeignKey(
        Meeting, on_delete=models.SET_NULL, null=True, blank=True, related_name="+"
    )
    document = models.ForeignKey(
        Document, on_delete=models.SET_NULL, null=True, blank=True, related_name="artifacts"
    )
    ai_interaction = models.ForeignKey(
        "AiInteraction", on_delete=models.SET_NULL, null=True, blank=True, related_name="+"
    )
    created_by = models.ForeignKey(User, on_delete=models.PROTECT, related_name="artifacts")
    sent_at = models.DateTimeField(null=True, blank=True)
    decided_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["-created_at", "-id"]

    def __str__(self) -> str:
        return f"{self.get_kind_display()} — {self.title}"

    def clean(self) -> None:
        links = [self.opportunity_id, self.project_id]
        if sum(value is not None for value in links) != 1:
            raise ValidationError(
                "O artefato deve estar vinculado a uma oportunidade ou a um projeto."
            )

    def save(self, *args, **kwargs) -> None:  # type: ignore[no-untyped-def]
        if self.status == self.Status.SENT and self.sent_at is None:
            self.sent_at = timezone.now()
        if self.status in {self.Status.ACCEPTED, self.Status.REJECTED} and self.decided_at is None:
            self.decided_at = timezone.now()
        super().save(*args, **kwargs)


class ScheduledJobRun(models.Model):
    """Carimbo durável do último ciclo de cada job periódico (FDD 023, ADR 0015).

    É o equivalente, no banco, do `latest.json` que o sidecar de backup deixa em disco — e existe
    pelo mesmo motivo: sem estado que sobreviva ao processo, um restart do container às 07:31,
    logo depois do digest das 07:30, mandaria o e-mail de novo para todo mundo.

    **Não** é recurso de negócio: não estende `TimestampedModel`, não entra no soft delete, não tem
    viewset nem entra no `RolePermission`, e não toca o contrato `/api/v1/`. É registro operacional,
    lido pelo admin — que é onde o operador já olha.
    """

    name = models.CharField(max_length=64, unique=True)
    # O relógio que decide o vencimento é o da **tentativa**, não o do sucesso: um job diário que
    # falhou não volta a rodar no próximo tique. Os três jobs de hoje são relatórios e alertas, e
    # tentar de novo a cada minuto trocaria uma falha por uma enxurrada — de e-mail, no caso do
    # digest, e de evento no Sentry, no caso do `backup_status`.
    last_attempt_at = models.DateTimeField(null=True, blank=True)
    # Guardado só para quem lê: responde "quando isto funcionou pela última vez?", pergunta que
    # hoje não tem onde ser respondida.
    last_success_at = models.DateTimeField(null=True, blank=True)
    ok = models.BooleanField(default=True)
    detail = models.TextField(blank=True, default="")

    class Meta:
        ordering = ["name"]

    def __str__(self) -> str:
        return self.name
