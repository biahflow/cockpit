from __future__ import annotations

import uuid
from datetime import date

from django.contrib.auth.models import AbstractUser
from django.core.exceptions import ValidationError
from django.db import models
from django.db.models import Q
from django.utils import timezone
from pgvector.django import VectorField

from . import knowledge


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
    # O cliente no gateway de pagamento (FDD 028), preenchido na primeira emissão e reusado depois.
    # Nome neutro pelo mesmo motivo que as settings são `PAYMENTS_*` e não `STRIPE_*`. Um cliente
    # novo por fatura quebraria a deduplicação e os relatórios do próprio fornecedor. Precedente da
    # casa: `drive_folder_id` acima já é id de fornecedor morando num modelo do domínio.
    payment_customer_ref = models.CharField(max_length=128, blank=True, default="")
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
    # As fontes que a resposta citou (FDD 029, ADR 0023). É o que torna "resposta sem citação é
    # defeito" auditável **depois do fato**, e não só no instante em que a tela mostrou. Mesmo
    # movimento que a ADR 0006 fez com `rating`.
    sources = models.JSONField(default=list, blank=True)
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


class KpiUnit(models.TextChoices):
    """A unidade em que um KPI é medido (FDD 027).

    Existe porque `DigitalEmployee.kpi_value` é `CharField` e cabe `"80%"` tanto quanto
    `"de 3h para 20min"`: dá para ler, não dá para ordenar nem agregar. Em branco é estado
    legítimo — "não tipado" —, que é onde ficam as linhas anteriores a esta FDD.
    """

    PERCENT = "percent", "Percentual"
    HOURS = "hours", "Horas"
    MINUTES = "minutes", "Minutos"
    CURRENCY = "currency", "Moeda"
    COUNT = "count", "Contagem"


class KpiDirection(models.TextChoices):
    """Para que lado o KPI melhora. Sem isto, "de 40 para 12" não diz se foi bom (FDD 027)."""

    UP = "up", "Maior é melhor"
    DOWN = "down", "Menor é melhor"


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
    # Unidade e direção ficam **só aqui**, e a `BlueprintVariant` não as sobrescreve — ao contrário
    # do `kpi_label`, que ela sobrescreve porque é o texto do setor. Deixar uma variante trocar
    # "horas" por "percentual" tornaria duas instâncias do *mesmo bloco* incomparáveis em silêncio,
    # que é exatamente o que a FDD 027 existe para impedir: é o par (unidade, direção) que torna
    # centenas de cases comparáveis entre si em vez de uma coleção de frases.
    kpi_unit = models.CharField(max_length=16, choices=KpiUnit.choices, blank=True, default="")
    kpi_direction = models.CharField(
        max_length=8, choices=KpiDirection.choices, default=KpiDirection.UP
    )
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
    # **Obsoleto** desde a FDD 027, e mantido de propósito: removê-lo quebraria `/api/v1/` e o
    # painel "Seu Time Digital" que `portal.build_snapshot` já entrega ao cliente. Quem for medir
    # usa o par tipado abaixo; este continua servindo à frase livre ("de 3h para 20min").
    kpi_value = models.CharField(max_length=80, blank=True, default="")
    # Copiados do blueprint na instanciação (`blueprints.instantiate`), como todo o resto: o que
    # vale é a cópia, não uma referência viva ao catálogo.
    kpi_unit = models.CharField(max_length=16, choices=KpiUnit.choices, blank=True, default="")
    kpi_direction = models.CharField(
        max_length=8, choices=KpiDirection.choices, default=KpiDirection.UP
    )
    # Nulo é **"não medido"**, e zero é "medido e era zero" — a distinção é a razão de o campo ser
    # nulável em vez de `default=0`. Sem ela, um case de projeto sem baseline inventaria um "antes"
    # igual a zero, que é precisamente o que destrói a credibilidade de prova social (FDD 027).
    kpi_baseline = models.DecimalField(max_digits=12, decimal_places=2, null=True, blank=True)
    kpi_current = models.DecimalField(max_digits=12, decimal_places=2, null=True, blank=True)
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


# Transições válidas do case. Rascunho e revisão vão e voltam enquanto o humano trabalha; publicado
# é terminal, porque despublicar não desfaz nada — o número já saiu em proposta. Mesma forma de
# `ARTIFACT_TRANSITIONS`, e a governança espelha a do AI Score: gerado como rascunho, publicado por
# decisão humana.
CASE_TRANSITIONS: dict[str, set[str]] = {
    "draft": {"review", "published"},
    "review": {"draft", "published"},
    "published": set(),
}


class Case(TimestampedModel):
    """O case de um projeto concluído — uma **fotografia**, não uma consulta (FDD 027, ADR 0020).

    Projeto entregue não virava nada: `Project.status` chegava a `completed` e o que aquela entrega
    provava ficava espalhado entre o ROI do projeto, os KPIs de cada `DigitalEmployee` e a memória
    de quem entregou.

    O que faz este modelo existir — em vez de uma tela que agrega o estado atual — é que os números
    **precisam parar no tempo**. `assess_project_health` é função pura sobre o estado de agora: um
    projeto concluído, recalculado meses depois, devolve outro número, porque tarefas fecharam e
    pendências sumiram. Um case cujo número muda sozinho depois de publicado é pior que nenhum case.
    Por isso `health_snapshot`, `roi_snapshot` e `metrics` são gravados no congelamento e nunca
    recalculados (o serializer os expõe como read-only: não há caminho de escrita, não é convenção).
    """

    class Status(models.TextChoices):
        DRAFT = "draft", "Rascunho"
        REVIEW = "review", "Em revisão"
        PUBLISHED = "published", "Publicado"

    # `PROTECT`, e não o `CASCADE` do resto do grafo de projeto: o case existe justamente para
    # sobreviver ao que acontece com o projeto depois. Deixar um `delete()` levar a prova junto
    # derrotaria o ponto — é a mesma escolha de `Project.client` e `Project.opportunity`.
    project = models.ForeignKey(Project, on_delete=models.PROTECT, related_name="cases")
    title = models.CharField(max_length=255)
    summary = models.TextField(blank=True, default="")
    # Cópia da vertical do cliente no instante do congelamento. É por ela que a proposta encontra
    # o case do mesmo setor (FDD 026, FDD 027).
    vertical = models.ForeignKey(
        Vertical, on_delete=models.SET_NULL, null=True, blank=True, related_name="cases"
    )
    # Uma entrada por Funcionário Digital, com rótulo, unidade, antes, depois e direção. JSON aqui
    # não repete a discussão da ADR 0019: lá a estrutura era **catálogo vivo**, com invariante de
    # unicidade que só uma constraint garante; isto é registro morto, escrito uma vez e nunca
    # consultado por chave.
    metrics = models.JSONField(default=list, blank=True)
    health_snapshot = models.JSONField(default=dict, blank=True)
    # **Interno.** Receita e custo do projeto nunca vão para texto destinado ao cliente — ver a
    # guarda em `ai._case_lines`, que injeta métrica operacional e health e nunca isto.
    roi_snapshot = models.JSONField(default=dict, blank=True)
    status = models.CharField(max_length=16, choices=Status.choices, default=Status.DRAFT)
    published_at = models.DateTimeField(null=True, blank=True)
    # O trio do consentimento. São três campos e não um booleano porque autorizar o uso do próprio
    # resultado é ato com autor e data — sem a cadeia, "o cliente deixou" é alegação de ninguém.
    # Gravados só pela ação `record-consent` (admin); read-only no serializer.
    client_consent = models.BooleanField(default=False)
    consent_recorded_at = models.DateTimeField(null=True, blank=True)
    consent_recorded_by = models.ForeignKey(
        User, on_delete=models.SET_NULL, null=True, blank=True, related_name="+"
    )
    # Publicar como "uma imobiliária de médio porte". É **outra** permissão, não uma versão fraca
    # do consentimento: autorizar o uso do resultado e autorizar o uso da marca são duas conversas,
    # e por isso anonimizar não dispensa `client_consent`.
    anonymized = models.BooleanField(default=False)

    class Meta:
        ordering = ["-created_at", "-id"]

    def __str__(self) -> str:
        return self.title

    def clean(self) -> None:
        if self.status == self.Status.PUBLISHED and not self.client_consent:
            raise ValidationError(
                {"status": "Sem consentimento registrado do cliente, o case não pode ser publicado."}
            )

    def save(self, *args, **kwargs) -> None:  # type: ignore[no-untyped-def]
        if self.status == self.Status.PUBLISHED and self.published_at is None:
            self.published_at = timezone.now()
        super().save(*args, **kwargs)


# Transições válidas da fatura (FDD 028), no molde de `ARTIFACT_TRANSITIONS` e `CASE_TRANSITIONS`.
#
# Duas arestas que a FDD não escreveu e sem as quais o recorte não fecha:
#
# `overdue → paid` é a mais importante do domínio inteiro. `overdue` é derivado por trabalho
# agendado, e lido ao pé da letra o mapa da FDD — que só descreve as saídas de `issued` — faria a
# fatura atrasada nunca poder ser paga: o webhook recusaria justamente a baixa que ele existe para
# dar. Quem venceu recebe as mesmas saídas de quem foi emitido, menos vencer de novo.
#
# `renegotiated` é **terminal** neste recorte. Renegociar produz *outra* fatura com os novos termos,
# e a original encerra dizendo o que houve; ligar as duas é camada 3 da RFC 0004 e está fora. Vale
# manter o estado separado de `cancelled` em vez de fundir os dois: a camada 0 existe para medir
# inadimplência, e "não recebi como combinado, mas negociei" é resultado materialmente diferente de
# "não vou receber" — fundir apagaria o sinal mais interessante já no primeiro dia.
INVOICE_TRANSITIONS: dict[str, set[str]] = {
    "draft": {"issued"},
    "issued": {"paid", "overdue", "renegotiated", "cancelled"},
    "overdue": {"paid", "renegotiated", "cancelled"},
    "renegotiated": set(),
    "paid": set(),
    "cancelled": set(),
}


class Invoice(TimestampedModel):
    """A fatura — o primeiro registro financeiro do portal (FDD 028, camada 0 da RFC 0004).

    O portal levava a oportunidade da venda até a operação e parava no ponto em que o dinheiro
    deveria entrar: `Service.list_price` e `Opportunity.estimated_value` são **preço**,
    `Project.actual_value` é um número digitado, e nenhum deles responde "cobrei o cliente X, R$ Y,
    vence dia Z, está pago?". Sem data de vencimento e sem data de pagamento em lugar nenhum, a
    inadimplência era **imensurável** — e é por isso que este modelo vem antes de qualquer régua de
    cobrança.

    **`actual_value` continua sendo a receita.** Esta FDD adota `Project.actual_value` como *valor
    contratado* e a soma das faturas pagas como *recebido*, sem trocar a fonte de nada: `_roi`, os
    agregados de `/analytics/`, o `build_client_overview`, o sinal de ROI negativo do `health.py` e
    o bloco de ROI que o `portal.build_snapshot` **já entrega à tela do cliente** seguem lendo o que
    sempre leram. Trocar a fonte do ROI é mudança de contrato e exige ADR próprio — deixado
    nomeado, não resolvido de carona.

    **Estende `TimestampedModel` pelos carimbos, e nunca arquiva.** É a exceção declarada à regra da
    casa (FDD 025, ADR 0021): registro financeiro não se edita nem se arquiva depois de emitido —
    cancela-se, e o registro sobrevive ao próprio cancelamento. `archived_at` vem herdado como peso
    morto e a `CheckConstraint` abaixo o mantém nulo para sempre. Arquivar seria pior que apagar:
    esconde da lista sem desfazer o fato, e um recebível que some do total em aberto em silêncio é
    exatamente o defeito que este modelo existe para não ter.
    """

    class Status(models.TextChoices):
        DRAFT = "draft", "Rascunho"
        ISSUED = "issued", "Emitida"
        PAID = "paid", "Paga"
        OVERDUE = "overdue", "Vencida"
        RENEGOTIATED = "renegotiated", "Renegociada"
        CANCELLED = "cancelled", "Cancelada"

    class Method(models.TextChoices):
        PIX = "pix", "Pix"
        BOLETO = "boleto", "Boleto"
        CARD = "card", "Cartão"
        TRANSFER = "transfer", "Transferência"
        OTHER = "other", "Outro"

    client = models.ForeignKey(Client, on_delete=models.PROTECT, related_name="invoices")
    # `SET_NULL` e não `PROTECT`: a fatura sobrevive ao arquivamento do projeto que a originou —
    # o dinheiro continuou devido. É a mesma escolha de `Artifact.project`.
    project = models.ForeignKey(
        Project, on_delete=models.SET_NULL, null=True, blank=True, related_name="invoices"
    )
    service = models.ForeignKey(
        "Service", on_delete=models.SET_NULL, null=True, blank=True, related_name="invoices"
    )
    # Vazio no rascunho — é o que faz dele um rascunho. Atribuído na emissão, formato `AAAA-NNNN`.
    number = models.CharField(max_length=32, blank=True, default="", db_index=True)
    # Sem `default=0`, ao contrário de `Project.actual_value`: aquilo é um saldo que se acumula,
    # isto é uma **afirmação**. Um POST que esquece o valor deve tomar 400, não criar um recebível
    # de R$ 0,00 que ninguém emite, ninguém paga e o job de vencimento visita todo dia.
    amount = models.DecimalField(max_digits=12, decimal_places=2)
    description = models.CharField(max_length=255, blank=True, default="")
    due_date = models.DateField()
    # Choices fechadas, e não texto livre: isto precisa agregar depois. É a lição que a FDD 026
    # registrou sobre `DigitalEmployee.area`, aplicada antes de doer.
    method = models.CharField(max_length=16, choices=Method.choices, blank=True, default="")
    status = models.CharField(max_length=16, choices=Status.choices, default=Status.DRAFT)

    issued_at = models.DateTimeField(null=True, blank=True)
    issued_by = models.ForeignKey(
        User, on_delete=models.SET_NULL, null=True, blank=True, related_name="+"
    )
    # A data **do provedor**, não `now()`: quem paga sexta e é conciliado segunda pagou sexta.
    paid_at = models.DateTimeField(null=True, blank=True)
    settled_by = models.ForeignKey(
        User, on_delete=models.SET_NULL, null=True, blank=True, related_name="+"
    )
    cancelled_at = models.DateTimeField(null=True, blank=True)
    cancelled_by = models.ForeignKey(
        User, on_delete=models.SET_NULL, null=True, blank=True, related_name="+"
    )
    cancel_reason = models.TextField(blank=True, default="")

    # Referências do gateway, no molde de `SignatureRequest` (ADR 0007). `provider` guarda de
    # **quem** é o `external_reference`: sem ele, trocar de fornecedor deixa um id órfão sem
    # namespace, e "o fornecedor é peça trocável" vira frase que o banco não sustenta.
    provider = models.CharField(max_length=32, blank=True, default="")
    external_reference = models.CharField(max_length=128, blank=True, default="", db_index=True)
    payment_url = models.URLField(blank=True, default="")

    class Meta:
        # Nunca ordenar por coluna anulável: `-issued_at` põe os NULL em pontas diferentes no
        # SQLite (testes) e no Postgres (produção), e a ordem padrão da API passaria a divergir
        # entre o CI e o ar. Ascendente por vencimento é, além disso, a leitura de recebíveis:
        # o mais atrasado primeiro.
        ordering = ["due_date", "id"]
        indexes = [models.Index(fields=["status", "due_date"])]
        constraints = [
            # Parcial, e não `unique=True` no campo: com `default=""`, um unique simples deixaria
            # **um único rascunho** existir no sistema inteiro.
            models.UniqueConstraint(
                fields=["number"], condition=~Q(number=""), name="unique_invoice_number"
            ),
            models.CheckConstraint(
                condition=Q(amount__gte=0), name="invoice_amount_is_not_negative"
            ),
            # A invariante escrita onde não depende de ninguém lembrar dela. Uma viewset futura que
            # herde `ArchiveModelViewSet` por reflexo falha alto no primeiro DELETE, em vez de
            # esconder um recebível da lista em silêncio.
            models.CheckConstraint(
                condition=Q(archived_at__isnull=True), name="invoice_is_never_archived"
            ),
        ]

    def __str__(self) -> str:
        return f"{self.number or 'rascunho'} — {self.client.name}"

    @property
    def is_overdue(self) -> bool:
        """Vencida de fato, mesmo antes de o job diário passar.

        O estado `overdue` é derivado por trabalho agendado (06:00), então entre a virada do dia e o
        job existe uma janela em que a fatura está `issued` e atrasada. Sem esta propriedade a tela
        mostraria "em aberto" para quem já venceu — e quem olha recebível não perdoa essa hora.
        """
        return self.status == self.Status.ISSUED and self.due_date < timezone.localdate()


class KnowledgeArea(models.Model):
    """A área de conhecimento — e, sobretudo, **onde o dono mora** (FDD 029).

    Taxonomia e não enum, pelo mesmo argumento do `Vertical` (FDD 026): vocabulário que o admin
    edita. Mas aqui há uma razão a mais e ela é decisiva — a exigência central da FDD é "dono **por
    área**, não por documento", e num `TextChoices` o dono não teria onde morar senão numa tabela
    lateral chaveada pelo valor do enum, que é esta taxonomia com passos a mais.

    `owner` é **nulável de propósito**: "peça sem dono é peça em falta" só é uma regra visível se o
    estado sem dono existir. `SET_NULL` em vez de `PROTECT` porque quem saiu da empresa é arquivado,
    e devolver a área ao estado "em falta" é a verdade — travar o arquivamento seria fingir que o
    dono continua lá.
    """

    name = models.CharField(max_length=80)
    slug = models.SlugField(max_length=80, unique=True)
    position = models.PositiveIntegerField(default=0)
    active = models.BooleanField(default=True)
    owner = models.ForeignKey(
        User, on_delete=models.SET_NULL, null=True, blank=True, related_name="knowledge_areas"
    )
    review_interval_days = models.PositiveIntegerField(default=180)

    class Meta:
        ordering = ["position", "id"]

    def __str__(self) -> str:
        return self.name


class KnowledgePiece(TimestampedModel):
    """Uma peça de conhecimento: **ao mesmo tempo a linha de governança e a unidade citável**.

    Que os dois papéis morem no mesmo registro não é conveniência. A FDD 029 exige que "conteúdo
    vencido apareça como vencido, e não seja servido como corrente" — e isso só é implementável se
    o caminho de recuperação conseguir ler a frescura daquilo que está prestes a citar. Em tabelas
    sem relação, aquela cláusula fica insatisfazível.

    `source_path` vazio é a **lacuna tácita**: o que só uma pessoa sabe fazer e ainda não está
    escrito. É o que o Aceite pede quando diz que "os pontos onde ela trava viram itens do
    inventário" — e por isso a unicidade abaixo é **parcial**.
    """

    class Kind(models.TextChoices):
        # Quase imutável: ADR não se atualiza, se **substitui** por outra que a referencia.
        DECISION = "decision", "Decisão"
        # Apodrece rápido porque a realidade muda; é o que pede o laço mais apertado.
        PROCEDURE = "procedure", "Procedimento"
        # Apodrece em silêncio, que é o mais perigoso dos três.
        REFERENCE = "reference", "Referência"

    area = models.ForeignKey(
        KnowledgeArea, on_delete=models.SET_NULL, null=True, blank=True, related_name="pieces"
    )
    title = models.CharField(max_length=200)
    kind = models.CharField(max_length=16, choices=Kind.choices, default=Kind.REFERENCE)
    source_path = models.CharField(max_length=255, blank=True, default="")
    summary = models.TextField(blank=True, default="")
    last_verified_at = models.DateField(null=True, blank=True)
    verified_by = models.ForeignKey(
        User, on_delete=models.SET_NULL, null=True, blank=True, related_name="+"
    )
    # Nulo **herda da área**; zero significa **não vence**. Colapsar os dois daria ou ADR cobrando
    # revisão para sempre — são quase imutáveis, e revisar a ADR 0001 a cada semestre é ruído, que
    # é o que faz o laço inteiro ser ignorado — ou lacuna que nunca aflora.
    review_interval_days = models.PositiveIntegerField(null=True, blank=True)
    # Teto de frequência do aviso. Sem ele o job vira lembrete diário que a pessoa aprende a
    # ignorar em uma semana, e aí o laço todo é teatro.
    last_notified_at = models.DateField(null=True, blank=True)
    content_hash = models.CharField(max_length=64, blank=True, default="")

    class Meta:
        ordering = ["area__position", "kind", "title", "id"]
        constraints = [
            # **Parcial**, e não `unique=True`: com `default=""`, um unique simples deixaria existir
            # uma **única** lacuna tácita no sistema inteiro. É a segunda vez que o repositório
            # precisa desta forma — a FDD 028 pagou por ela em `Invoice.number`.
            models.UniqueConstraint(
                fields=["source_path"],
                condition=~Q(source_path=""),
                name="unique_knowledge_source_path",
            ),
        ]

    def __str__(self) -> str:
        return self.title


class KnowledgeChunk(models.Model):
    """Um trecho recuperável, ancorado numa seção (FDD 029, ADR 0022).

    Registro **derivado**: fora do soft delete, fora do `RolePermission`, **sem serializer, sem
    viewset, sem rota e fora do `admin.py`**. A única saída do texto daqui é o `AgentView`, e isso
    é o anti-vazamento sendo estrutural em vez de vigiado.

    **Não tem FK para `Project`, `Client` nem `Document`, e é a invariante em forma de esquema:**
    este corpus é a metodologia da casa, e conteúdo de cliente não entra por caminho nenhum. O
    `ai.build_project_context` continua passando documento como *nome*, como sempre passou.
    """

    piece = models.ForeignKey(KnowledgePiece, on_delete=models.CASCADE, related_name="chunks")
    position = models.PositiveIntegerField(default=0)
    heading_path = models.CharField(max_length=300)  # "ADR 0013 — … › Decisão"
    content = models.TextField()
    content_hash = models.CharField(max_length=64)
    embedding = VectorField(dimensions=knowledge.EMBEDDING_DIMENSIONS, null=True, blank=True)
    # Carimbo por linha: trocar de modelo passa a ser **detectável** em vez de produzir um índice
    # metade num espaço vetorial e metade noutro — defeito que não dá erro, só piora a busca.
    embedding_model = models.CharField(max_length=64, blank=True, default="")

    class Meta:
        ordering = ["piece_id", "position"]
        constraints = [
            models.UniqueConstraint(
                fields=["piece", "position"], name="unique_knowledge_chunk_position"
            ),
        ]

    def __str__(self) -> str:
        return self.heading_path


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
