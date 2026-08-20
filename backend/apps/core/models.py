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
    # Quem recebe cobrança neste cliente (FDD 036). **Default `False`, e é a decisão que importa:**
    # a régua fala de dinheiro, e chutar o destinatário é o erro caro. Sem ninguém marcado, o
    # degrau não vira e-mail ao cliente — vira escalada interna com o motivo escrito, que é o
    # "cala quando não sabe" que a casa já usa no enriquecimento de lead (FDD 030).
    receives_billing = models.BooleanField(default=False)

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


class Decisao(TimestampedModel):
    """Decisão do projeto: o que foi decidido, por quê, e a partir de qual reunião.

    **Por que ela não é uma `Pendencia`.** O docstring de lá diz "Pendência/decisão do projeto", e
    a FDD 005 repete — a casa colapsou as duas desde sempre. Elas divergem em três eixos: o estado
    de uma pendência é `aberta/resolvida` e o de uma decisão é `rascunho/publicada`; uma pendência
    diz *de quem é a bola* (`party`) e uma decisão diz *quem decidiu*, que muitas vezes é alguém do
    cliente e não um `User` daqui; e o valor de uma decisão está no **porquê**, que a pendência nem
    guarda de forma que atravesse (o `description` dela não entra no snapshot).

    **O estado existe para a IA caber.** A extração a partir da transcrição (FDD 032) grava
    `rascunho`, e só `publicada` entra no snapshot — nenhum palpite de modelo alcança o cliente
    antes de uma pessoa publicar. É a forma do `Artifact` (`draft → review → sent → accepted`),
    reduzida ao que esta entidade precisa.
    """

    class Status(models.TextChoices):
        DRAFT = "draft", "Rascunho"
        PUBLISHED = "published", "Publicada"

    project = models.ForeignKey(Project, on_delete=models.CASCADE, related_name="decisoes")
    title = models.CharField(max_length=255)
    rationale = models.TextField(blank=True)
    decided_on = models.DateField(null=True, blank=True)
    # Texto livre, e não FK para `User`: quem decide costuma ser alguém do cliente, que não tem
    # conta aqui. É o mesmo motivo de `Document.author` ser derivado e não relacional no snapshot.
    decided_by = models.CharField(max_length=160, blank=True)
    status = models.CharField(max_length=16, choices=Status.choices, default=Status.DRAFT)
    # A proveniência. `SET_NULL` porque apagar a reunião não desfaz a decisão que saiu dela — o
    # que se perde é só de onde ela veio, e perder isso é melhor que perder a decisão.
    source_meeting = models.ForeignKey(
        Meeting, on_delete=models.SET_NULL, null=True, blank=True, related_name="decisoes"
    )
    published_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["-decided_on", "-created_at"]

    def save(self, *args, **kwargs) -> None:
        # **O carimbo não se apaga**, e é aqui que esta classe diverge de propósito da `Pendencia`
        # logo acima: aquele `save()` limpa `resolved_at` ao reabrir. Para uma decisão isso seria
        # destrutivo — a data em que se publicou é fato histórico, e despublicar não a desfaz. O
        # precedente correto é o `Case` (ADR 0020): fotografia, persistida e não recalculada.
        if self.status == self.Status.PUBLISHED and self.published_at is None:
            self.published_at = timezone.now()
        super().save(*args, **kwargs)


class Risco(TimestampedModel):
    """Risco do projeto: o que pode dar errado, quanto pesa e o que se está fazendo a respeito.

    É o Risk Register do Delivery System da metodologia FDE (ADR 0030,
    `docs/metodologia-fde.md`), que até aqui só existia como página de texto — e um registro de
    risco que vive fora do sistema é consultado na semana da reunião e esquecido na seguinte.

    **Não confundir com a avaliação de risco calculada** (`risk.py`, `/projects/{id}/risk/`).
    Aquela é derivada: o sistema olha prazos e itens atrasados e devolve um escore que ninguém
    edita. Esta é declarada: uma pessoa da entrega escreve o que teme, com que probabilidade e
    com que impacto. As duas respondem "qual o risco deste projeto" por caminhos que não se
    substituem — a calculada só enxerga o que já escorregou; esta enxerga o que ainda não
    aconteceu, que é o único momento em que mitigar é possível.
    """

    # Os dois eixos têm os mesmos três valores no banco e rótulos diferentes na tela, porque o
    # português concorda: a probabilidade é *baixa*, o impacto é *baixo*. Uma classe só economizaria
    # oito linhas e faria o contexto do agente dizer "probabilidade baixo".
    class Probability(models.TextChoices):
        LOW = "low", "Baixa"
        MEDIUM = "medium", "Média"
        HIGH = "high", "Alta"

    class Impact(models.TextChoices):
        LOW = "low", "Baixo"
        MEDIUM = "medium", "Médio"
        HIGH = "high", "Alto"

    class Status(models.TextChoices):
        OPEN = "open", "Aberto"
        MITIGATED = "mitigated", "Mitigado"
        ACCEPTED = "accepted", "Aceito"
        MATERIALIZED = "materialized", "Materializado"

    project = models.ForeignKey(Project, on_delete=models.CASCADE, related_name="riscos")
    title = models.CharField(max_length=255)
    description = models.TextField(blank=True, default="")
    probability = models.CharField(
        max_length=8, choices=Probability.choices, default=Probability.MEDIUM
    )
    impact = models.CharField(max_length=8, choices=Impact.choices, default=Impact.MEDIUM)
    mitigation = models.TextField(blank=True, default="")
    status = models.CharField(max_length=16, choices=Status.choices, default=Status.OPEN)
    owner = models.ForeignKey(
        User, on_delete=models.SET_NULL, null=True, blank=True, related_name="riscos"
    )
    resolved_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        # **Não** `["status", "-created_at"]` como na `Pendencia` logo acima, e a diferença é um
        # acidente de alfabeto: lá "open" vem antes de "resolved" e o efeito é o desejado; aqui
        # "open" vem depois de "accepted", "materialized" e "mitigated", e ordenar por status
        # enterraria justamente os riscos abertos embaixo dos encerrados. Quem quer só os abertos
        # pede `?status=open`, que é filtro e não ordem.
        ordering = ["-created_at"]

    def __str__(self) -> str:
        return self.title

    def save(self, *args, **kwargs) -> None:
        # O carimbo é **estado corrente**, como o `resolved_at` da `Pendencia` e ao contrário do
        # `published_at` da `Decisao`: reabrir um risco apaga a data em que ele deixou de ameaçar.
        #
        # E ele só vale para "mitigado" e "aceito". "Materializado" também tira o risco da fila de
        # abertos, mas não o resolve — o risco aconteceu. Carimbar ali faria "resolvido em" nomear
        # o dia em que a coisa deu errado, que é a leitura oposta da que o campo promete. Quando
        # (e se) a data da materialização importar, ela pede campo próprio, não este emprestado.
        terminal = {self.Status.MITIGATED, self.Status.ACCEPTED}
        if self.status in terminal and self.resolved_at is None:
            self.resolved_at = timezone.now()
        if self.status not in terminal:
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
    # CNPJ como o visitante digitou — com ou sem pontuação, e é `enrichment.normalize_cnpj` que
    # decide se aquilo vira consulta. Guardar o cru e normalizar na leitura, e não o contrário,
    # porque um formulário público que recusa lead por causa de formatação troca um cliente
    # possível por um cadastro bonito (FDD 030).
    cnpj = models.CharField(max_length=18, blank=True, default="")
    # O cadastro público devolvido pelo enriquecimento (FDD 030). JSON e não colunas: é retrato de
    # um fornecedor, não fato do domínio — e o dia em que o provedor mudar, uma coluna a menos é
    # uma migração a menos. Vazio é o estado normal: sem CNPJ, com a flag desligada ou com o
    # fornecedor fora do ar, o lead segue para a qualificação como sempre seguiu.
    enrichment = models.JSONField(default=dict, blank=True)
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


class Activity(TimestampedModel):
    """Interação comercial com um cliente (ligação, reunião, e-mail, nota) — FDD 035.

    É a materialização das "Activities" do CRM na leitura FDE (ADR 0030,
    `docs/metodologia-fde.md`): o histórico de contato passa a viver como dado, não como texto
    solto em algum lugar. Liga-se sempre a um cliente e, opcionalmente, a uma oportunidade —
    desde que a oportunidade seja do mesmo cliente (`clean()` abaixo).
    """

    class Kind(models.TextChoices):
        CALL = "call", "Ligação"
        MEETING = "meeting", "Reunião"
        EMAIL = "email", "E-mail"
        NOTE = "note", "Nota"

    class CobrancaSinal(models.TextChoices):
        """Os três problemas que a mesma régua estraga (RFC 0004, camada 4).

        Não é sentimento nem etiqueta de CRM: cada valor manda para um lugar diferente.
        `esqueceu` já se resolveu com o lembrete; `nao_pode` pede renegociação, e cedo;
        `insatisfeito` não é problema de cobrança — é problema de relação disfarçado, e insistir
        piora tudo. A IA **grava o sinal e não age** (ADR 0031).
        """

        ESQUECEU = "esqueceu", "Esqueceu"
        NAO_PODE = "nao_pode", "Não pôde pagar"
        INSATISFEITO = "insatisfeito", "Insatisfeito"

    client = models.ForeignKey(Client, on_delete=models.CASCADE, related_name="activities")
    opportunity = models.ForeignKey(
        Opportunity, on_delete=models.SET_NULL, null=True, blank=True, related_name="activities"
    )
    # A resposta do cliente à cobrança chega por aqui, digitada por quem atendeu (FDD 036).
    # `SET_NULL` como `Artifact.project`: a interação aconteceu, e sobrevive à fatura sumir do
    # rascunho. Vazio na esmagadora maioria das interações, que não falam de dinheiro.
    invoice = models.ForeignKey(
        "Invoice", on_delete=models.SET_NULL, null=True, blank=True, related_name="activities"
    )
    cobranca_sinal = models.CharField(
        max_length=16, choices=CobrancaSinal.choices, blank=True, default=""
    )
    kind = models.CharField(max_length=16, choices=Kind.choices)
    happened_on = models.DateField()
    summary = models.CharField(max_length=255)
    notes = models.TextField(blank=True, default="")
    owner = models.ForeignKey(
        User, on_delete=models.SET_NULL, null=True, blank=True, related_name="activities"
    )

    class Meta:
        ordering = ["-happened_on", "-created_at"]

    def __str__(self) -> str:
        return f"{self.get_kind_display()}: {self.summary}"

    def clean(self) -> None:
        if self.opportunity_id and self.opportunity and self.opportunity.client_id != self.client_id:
            raise ValidationError({"opportunity": "A oportunidade deve pertencer ao mesmo cliente."})
        # Mesma checagem para a fatura, e pela mesma razão que a da oportunidade: sem ela, uma
        # resposta de cobrança pode ficar pendurada na fatura de **outro** cliente — e é essa
        # linha que a tela de cobrança lê para decidir o próximo passo.
        if self.invoice_id and self.invoice and self.invoice.client_id != self.client_id:
            raise ValidationError({"invoice": "A fatura deve pertencer ao mesmo cliente."})


class Satisfacao(TimestampedModel):
    """Satisfação do cliente: o único sinal do domínio cuja fonte está **fora** da casa (FDD 037).

    Camada 5 da RFC 0004, e a lacuna que a docstring do `health.py` declarava desde a Fase 2. Todo
    o resto que este produto usa para julgar uma relação é medida do nosso próprio trabalho —
    prazo estourado (`risk.py`), entrega atrasada e reunião não realizada (`health.py`), ROI
    (`cases.py`). Este é o primeiro que depende de o cliente ter dito alguma coisa.

    **Liga ao cliente, e não ao projeto**, ao contrário dos três registros vizinhos (`Pendencia`,
    `Decisao`, `Risco`): o molde aqui é a `Activity`. Os dois consumidores perguntam coisas
    diferentes — o Health Score pergunta por projeto, a régua de cobrança pergunta por cliente —, e
    cliente sem projeto ativo ainda pode ter fatura vencida. Ligar só ao projeto deixaria a camada
    5 sem alcance justamente em quem não está mais em entrega, que é onde a cobrança dói.

    Nada aqui sai da casa: não há canal, credencial nem flag. É registro interno digitado por quem
    conversou com o cliente, e **não** atravessa para o portal do cliente (ADR 0032).
    """

    class Nivel(models.TextChoices):
        PROMOTOR = "promotor", "Promotor"
        SATISFEITO = "satisfeito", "Satisfeito"
        NEUTRO = "neutro", "Neutro"
        INSATISFEITO = "insatisfeito", "Insatisfeito"

    class Fonte(models.TextChoices):
        """De onde veio o sinal — e é a decisão inteira desta fatia (ADR 0032).

        `declarada` é o cliente tendo dito; `percebida` é a leitura de quem entrega. Os dois são
        úteis e não são a mesma coisa: um é evidência, o outro é hipótese. **Só a declarada move
        número** — Health Score e escada de cobrança. Sem a separação, o sinal do cliente vira a
        opinião do time sobre si mesmo com aparência de medição, que é pior que não ter sinal
        nenhum, porque um número errado é consultado com a mesma confiança de um número certo.
        """

        DECLARADA = "declarada", "Declarada pelo cliente"
        PERCEBIDA = "percebida", "Percebida por quem entrega"

    client = models.ForeignKey(Client, on_delete=models.CASCADE, related_name="satisfacoes")
    project = models.ForeignKey(
        Project, on_delete=models.SET_NULL, null=True, blank=True, related_name="satisfacoes"
    )
    # A proveniência, no molde de `Decisao.source_meeting`: apagar a reunião não desfaz o que o
    # cliente disse nela — o que se perde é só de onde veio, e perder isso é melhor que perder o
    # registro.
    source_meeting = models.ForeignKey(
        Meeting, on_delete=models.SET_NULL, null=True, blank=True, related_name="satisfacoes"
    )
    # A outra proveniência: a resposta de cobrança que a IA classificou (FDD 038). É ela que dá
    # **leitor** ao `Activity.cobranca_sinal`, que até aqui era gravado e nunca lido por motor
    # nenhum. O painel usa esta ligação para parar de oferecer o atalho depois do registro — sem
    # ela, o mesmo sinal insistiria para sempre, mesmo já registrado.
    #
    # A IA continua sem gravar nada (ADR 0032): o atalho pré-preenche um formulário e quem salva é
    # gente. O campo é o registro de que a leitura virou registro, não a leitura virando registro.
    source_activity = models.ForeignKey(
        Activity, on_delete=models.SET_NULL, null=True, blank=True, related_name="satisfacoes"
    )
    nivel = models.CharField(max_length=16, choices=Nivel.choices)
    # **Sem default**, ao contrário de quase todo `choices` desta casa. Um default faria a
    # distinção que decide se o registro move número ser escolhida por omissão, e o campo existe
    # justamente para ninguém escolher por omissão.
    fonte = models.CharField(max_length=16, choices=Fonte.choices)
    # O dia do acontecido, não o do cadastro: o sinal envelhece por uma janela de 90 dias
    # (`satisfacao.SATISFACAO_VALIDA_DIAS`), e é `happened_on` que a janela lê.
    happened_on = models.DateField()
    note = models.TextField(blank=True)
    registered_by = models.ForeignKey(
        User, on_delete=models.SET_NULL, null=True, blank=True, related_name="satisfacoes"
    )

    class Meta:
        ordering = ["-happened_on", "-created_at"]

    def __str__(self) -> str:
        return f"{self.get_nivel_display()} — {self.client.name} ({self.happened_on})"

    def clean(self) -> None:
        if self.project_id and self.project and self.project.client_id != self.client_id:
            raise ValidationError({"project": "O projeto deve pertencer ao mesmo cliente."})
        # Mesma checagem para a atividade de origem, e pela mesma razão: sem ela, a resposta de
        # **outro** cliente viraria a satisfação declarada deste — e essa é a linha que troca a
        # escada da cobrança e tira 20 pontos do Health Score.
        if (
            self.source_activity_id
            and self.source_activity
            and self.source_activity.client_id != self.client_id
        ):
            raise ValidationError(
                {"source_activity": "A interação deve pertencer ao mesmo cliente."}
            )
        # **Insatisfeito é o único nível que muda comportamento** — tira 20 pontos do Health Score
        # e troca a escada da régua —, e um sinal que muda comportamento sem motivo escrito é
        # exatamente o que apodrece: seis meses depois ninguém sabe o que o cliente disse, e a
        # cobrança segue abrandada por um registro que ninguém consegue avaliar. Mesma exigência
        # que `CobrancaSuspensao.reason` já faz, e pela mesma razão.
        if self.nivel == self.Nivel.INSATISFEITO and not (self.note or "").strip():
            raise ValidationError(
                {"note": "Diga o que o cliente disse: insatisfeito sem nota não se avalia depois."}
            )


class Processo(TimestampedModel):
    """Um processo da operação do cliente, mapeado no Discovery estruturado (FDD 039).

    **Por que a entidade existe se a metodologia não a define.** O material
    (`docs/metodologia-fde.md:75-79`) descreve o P-S-D-T-E-R como o esquema "para cada etapa de um
    processo": o processo não é uma invenção deste modelo, é o que o próprio esquema exige para
    que a etapa tenha onde pendurar. Por isso ele nasce com nome, ordem e os insumos da fórmula do
    custo do estado atual — **e nada mais**. Sem `status`, sem `dono`, sem `nivel`: o que a
    metodologia não define, este modelo não inventa, porque um campo inventado vira regra de
    negócio no primeiro consumidor e depois ninguém sabe de onde ele veio.

    **Não confundir com o `Artifact` de `kind=discovery`** (FDD 016), que já existe e continua
    existindo. Aquele é a **narrativa**: o texto entregue ao cliente, com estado próprio
    (rascunho → revisão → enviado). Este é o **dado**: o mapa da operação, consultável e somável.
    Os dois convivem e não se substituem — a narrativa é o que se lê, o dado é o que se calcula —,
    e é a mesma distinção que o `Risco` faz em relação ao `risk.py` calculado.

    **Liga ao cliente e não ao projeto**, pelo argumento da `Satisfacao` acima: o processo mapeado
    é da empresa e sobrevive à venda que o descobriu (a metodologia separa Account de Opportunity,
    `docs/metodologia-fde.md:50-53`). Ancorar no projeto obrigaria a recriar o AS-IS do zero a cada
    novo Discovery da mesma empresa — que é exatamente o defeito que o `DigitalEmployee` tinha
    antes da FDD 026, quando o que valia morava só na instância e não no catálogo.
    """

    client = models.ForeignKey(Client, on_delete=models.CASCADE, related_name="processos")
    name = models.CharField(max_length=255)
    position = models.PositiveIntegerField(default=0)
    # Procedência, e não vínculo: apagar o projeto ou a reunião não desfaz o mapa levantado neles.
    # É o `SET_NULL` da `Satisfacao.source_meeting`, pela mesma razão — o que se perde é de onde
    # veio, e perder isso é melhor que perder o registro.
    source_project = models.ForeignKey(
        Project, on_delete=models.SET_NULL, null=True, blank=True,
        related_name="processos_mapeados",
    )
    source_meeting = models.ForeignKey(
        Meeting, on_delete=models.SET_NULL, null=True, blank=True, related_name="processos"
    )
    registered_by = models.ForeignKey(
        User, on_delete=models.SET_NULL, null=True, blank=True, related_name="processos"
    )

    # Os nove insumos do custo do estado atual (`docs/metodologia-fde.md:87-88`):
    # `Volume × Tempo × Pessoas × Custo + Retrabalho + Erros + Perdas + Espera + Risco`.
    #
    # Todos nulos, e **nulo aqui é "não apurado", nunca zero**: `processos.custo_do_estado_atual`
    # devolve o que faltou em `nao_apurado` em vez de somar zero, porque zerar afirmaria que
    # executar o processo não custa nada. É a lacuna dita e não preenchida, como em `ai.py` no
    # KPI sem base registrada (FDD 027).
    #
    # **O sufixo `_mes` não é decoração.** `ProcessoEtapa` tem `tempo`, `erro` e `retrabalho`, e
    # lá eles são **descrição** ("quanto demora", "o que pode dar errado"); aqui são dinheiro e
    # quantidade. Nomes iguais para perguntas diferentes fariam a segunda resposta vencer a
    # primeira em silêncio — quem lesse `retrabalho` não saberia se recebe um texto ou um valor.
    volume_mes = models.PositiveIntegerField(null=True, blank=True)  # ocorrências por mês
    tempo_horas = models.DecimalField(
        max_digits=7, decimal_places=2, null=True, blank=True
    )  # horas por ocorrência
    pessoas = models.PositiveSmallIntegerField(null=True, blank=True)  # pessoas por ocorrência
    custo_hora = models.DecimalField(
        max_digits=10, decimal_places=2, null=True, blank=True
    )  # R$/hora
    retrabalho_mes = models.DecimalField(max_digits=12, decimal_places=2, null=True, blank=True)
    erros_mes = models.DecimalField(max_digits=12, decimal_places=2, null=True, blank=True)
    perdas_mes = models.DecimalField(max_digits=12, decimal_places=2, null=True, blank=True)
    espera_mes = models.DecimalField(max_digits=12, decimal_places=2, null=True, blank=True)
    risco_mes = models.DecimalField(max_digits=12, decimal_places=2, null=True, blank=True)

    class Meta:
        ordering = ["position", "id"]

    def __str__(self) -> str:
        return self.name

    def archive(self) -> None:
        """Arquiva o processo **e o que pendura nele**, no mesmo instante.

        A regra transversal da FDD 025 é que arquivar não cascateia — e que, quando os filhos
        são listáveis por conta própria, quem os tem precisa escolher: recusar com 409 ou arquivar
        junto. Etapa e evidência são listáveis (`/processo-etapas/?processo=`,
        `/evidencias/?processo=`), então sem escolha ficariam visíveis apontando para um pai
        oculto — e, pior aqui do que no caso geral, uma evidência órfã continua sendo uma
        afirmação sobre a operação de um cliente, sem o processo que lhe dava contexto.

        Arquivar junto, e não recusar: um mapa de processo se guarda inteiro. Obrigar a apagar
        vinte etapas antes de guardar o processo transformaria "arquivar" em trabalho manual, e o
        que não se consegue guardar acaba sendo apagado de verdade.

        **O carimbo é o mesmo nos três**, e não é detalhe de implementação: é ele que o
        `unarchive` lê para devolver exatamente o que esta chamada levou, sem ressuscitar o que
        alguém tinha arquivado de propósito antes.
        """
        momento = timezone.now()
        self.archived_at = momento
        self.save(update_fields=["archived_at", "updated_at"])
        self.etapas.filter(archived_at__isnull=True).update(archived_at=momento)
        self.evidencias.filter(archived_at__isnull=True).update(archived_at=momento)

    def unarchive(self) -> None:
        """Restaura o processo e **só** os filhos que este arquivamento levou.

        A metade simétrica, e a armadilha mora nela: restaurar tudo o que está arquivado traria
        de volta a etapa que alguém removeu na semana passada, desfazendo uma decisão que ninguém
        pediu para desfazer. O critério é o carimbo idêntico ao do pai — quem foi arquivado junto
        volta junto, quem já estava arquivado antes continua onde estava.
        """
        momento = self.archived_at
        self.archived_at = None
        self.save(update_fields=["archived_at", "updated_at"])
        if momento is None:
            return
        self.etapas.filter(archived_at=momento).update(archived_at=None)
        self.evidencias.filter(archived_at=momento).update(archived_at=None)


class ProcessoEtapa(TimestampedModel):
    """Uma etapa do processo, descrita pelo P-S-D-T-E-R (`docs/metodologia-fde.md:75-79`).

    Os seis campos abaixo são **exatamente** as seis letras, nessa ordem. É a única parte do
    material que já é esquema de campos, e o valor dela está em não ser adaptada: renomear,
    juntar ou acrescentar uma sétima pergunta faria o levantamento da reunião deixar de casar com
    o formulário, e a conferência ("perguntei tudo?") deixaria de ser possível olhando a tela.
    """

    processo = models.ForeignKey(Processo, on_delete=models.CASCADE, related_name="etapas")
    name = models.CharField(max_length=255)
    position = models.PositiveIntegerField(default=0)
    pessoas = models.TextField(blank=True, default="")  # P — quem faz
    sistema = models.TextField(blank=True, default="")  # S — onde faz
    dados = models.TextField(blank=True, default="")  # D — o que entra/sai
    tempo = models.TextField(blank=True, default="")  # T — quanto demora
    erro = models.TextField(blank=True, default="")  # E — o que pode dar errado
    retrabalho = models.TextField(blank=True, default="")  # R — o que acontece quando dá errado

    class Meta:
        ordering = ["position", "id"]

    def __str__(self) -> str:
        return self.name


class Evidencia(TimestampedModel):
    """O que sustenta (ou não sustenta) cada achado do Discovery — a distinção central da FDD 039.

    A metodologia exige duas coisas que a prosa de uma ata não guarda: que o achado venha de uma
    das cinco formas de evidência, "nunca só entrevista" (`docs/metodologia-fde.md:81-84`), e que
    todo achado seja rotulado FATO / HIPÓTESE / DESCONHECIDO, porque **"nunca se apresenta
    hipótese como fato"** (`:86`). Guardar isso como campo é o que permite responder, depois da
    reunião, quanto do mapa é observação e quanto é suposição da casa.
    """

    class Forma(models.TextChoices):
        """As cinco formas de evidência (`docs/metodologia-fde.md:81-84`)."""

        ENTREVISTA = "entrevista", "Entrevista (o que dizem)"
        OBSERVACAO = "observacao", "Observação (o que fazem)"
        ARTEFATO = "artefato", "Artefato (planilha, PDF, croqui)"
        SISTEMA = "sistema", "Sistema (ERP, CRM, CAD, WhatsApp)"
        DADO = "dado", "Dado (volume, tempo, custo, erro)"

    class Rotulo(models.TextChoices):
        """Os três rótulos (`docs/metodologia-fde.md:86`).

        `DESCONHECIDO` é valor de primeira classe, e não ausência de valor: um Discovery que
        nomeia o que ainda não sabe está fazendo o trabalho, não deixando de fazê-lo — é a postura
        que o material pede ao sair da reunião (`:97-98`). Por isso ele é uma opção a escolher, e
        não o que sobra quando ninguém escolheu.
        """

        FATO = "fato", "Fato"
        HIPOTESE = "hipotese", "Hipótese"
        DESCONHECIDO = "desconhecido", "Desconhecido"

    processo = models.ForeignKey(Processo, on_delete=models.CASCADE, related_name="evidencias")
    # A etapa é opcional: nem todo achado é de uma etapa — "o volume é de 400 pedidos/mês" é do
    # processo inteiro. Quando vier preenchida, o `clean()` abaixo exige que seja deste processo.
    etapa = models.ForeignKey(
        ProcessoEtapa, on_delete=models.SET_NULL, null=True, blank=True, related_name="evidencias"
    )
    # **Sem default nos dois**, no precedente literal de `Satisfacao.fonte`: um default faria a
    # casa escolher por quem não escolheu, e o erro cairia sempre para o mesmo lado — chamar
    # suposição de fato, que é exatamente o que a metodologia proíbe. Escolher "desconhecido" é um
    # ato; recebê-lo por omissão não diz nada sobre o achado.
    forma = models.CharField(max_length=16, choices=Forma.choices)
    rotulo = models.CharField(max_length=16, choices=Rotulo.choices)
    content = models.TextField()
    source_meeting = models.ForeignKey(
        Meeting, on_delete=models.SET_NULL, null=True, blank=True, related_name="evidencias"
    )
    registered_by = models.ForeignKey(
        User, on_delete=models.SET_NULL, null=True, blank=True, related_name="evidencias"
    )

    class Meta:
        ordering = ["-created_at", "-id"]

    def __str__(self) -> str:
        return f"{self.get_rotulo_display()} — {self.content[:60]}"

    def clean(self) -> None:
        # Mesma checagem da `Satisfacao.clean()`, e aqui ela é fronteira de conta: sem a guarda,
        # uma evidência pode apontar para a etapa de um processo de **outro cliente** — vazamento
        # entre contas por um campo opcional, que é a pior forma de vazar porque ninguém preenche
        # o campo pensando nisso.
        if self.etapa_id and self.etapa and self.etapa.processo_id != self.processo_id:
            raise ValidationError({"etapa": "A etapa deve pertencer ao mesmo processo."})


class Service(TimestampedModel):
    """Catálogo de serviços e, quando `tier` estiver preenchido, os níveis de produto.

    Os três níveis da metodologia (Discovery Express grátis, Discovery + Assessment pago e
    Implantação) são registros semeados com `tier`; serviços avulsos ficam com `tier` vazio.

    Na leitura FDE (`docs/metodologia-fde.md`, ADR 0030), os níveis são os degraus comerciais
    da escada: Discovery Express é a porta de entrada (L0), Discovery + Assessment é o
    Discovery Sprint e Implantação é o PROVE — produção controlada com baseline, critérios de
    sucesso e decision gate. A Technical Feasibility, condicional na escada, **não tem tier**:
    criá-lo mexe na constraint de um ativo por nível e na semente, e é decisão de produto que
    espera o primeiro caso real que a exija.
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
    # A fase termina em decision gate de quatro saídas (FDD 033, ADR 0030). Fica no **template**
    # e não na instância porque quem decide que Feasibility e PROVE terminam em gate é a
    # metodologia, não o projeto — e é o mesmo lugar de onde saem nome, ordem e entregáveis.
    # `default=False` para que a semente da jornada e as fases já configuradas continuem
    # concluindo como sempre: o gate é opt-in do admin.
    requires_gate = models.BooleanField(default=False)

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


class PhaseChecklistItem(models.Model):
    """Template do quality gate: a pergunta que a fase precisa responder antes de fechar.

    Espelho exato de `PhaseDeliverable`, e a distinção entre os dois é o que a metodologia FDE
    separa (ADR 0030, `docs/metodologia-fde.md`): o entregável é **o que sai** da fase (um
    dashboard, um manual), e o item de checklist é **a condição de qualidade** para que aquilo
    possa sair ("baseline definido?", "amostra adequada?"). Marcar um entregável como entregue
    não afirma nada sobre qualidade; é por isso que só o checklist trava a conclusão.
    """

    phase = models.ForeignKey(
        JourneyPhase, on_delete=models.CASCADE, related_name="checklist_items"
    )
    text = models.CharField(max_length=255)
    position = models.PositiveIntegerField(default=0)

    class Meta:
        ordering = ["position", "id"]

    def __str__(self) -> str:
        return self.text


class ProjectPhase(TimestampedModel):
    """Instância por projeto × fase — o estado da jornada de transformação do projeto.

    Uma fase por vez fica `active` ("você está aqui"); as anteriores ficam `done` e as
    seguintes `locked`. Materializado a partir de `JourneyPhase` na criação do projeto.
    """

    class Status(models.TextChoices):
        LOCKED = "locked", "Bloqueada"
        ACTIVE = "active", "Em andamento"
        DONE = "done", "Concluída"

    class GateOutcome(models.TextChoices):
        """As quatro saídas do decision gate (FDD 033, `docs/metodologia-fde.md`).

        São exatamente quatro porque a metodologia diz quatro, e o valor delas está em *não*
        colapsarem: "seguiu com ressalvas" e "seguiu" acabam no mesmo lugar da jornada, mas só
        um dos dois deixa dívida nomeada para monitorar.
        """

        GO = "go", "GO"
        CONDITIONAL_GO = "conditional_go", "CONDITIONAL GO"
        REDESIGN = "redesign", "REDESIGN"
        NO_GO = "no_go", "NO-GO"

    project = models.ForeignKey(Project, on_delete=models.CASCADE, related_name="phases")
    phase = models.ForeignKey(JourneyPhase, on_delete=models.PROTECT, related_name="project_phases")
    status = models.CharField(max_length=16, choices=Status.choices, default=Status.LOCKED)
    started_at = models.DateTimeField(null=True, blank=True)
    completed_at = models.DateTimeField(null=True, blank=True)
    target_date = models.DateField(null=True, blank=True)  # a "prevista" mostrada na UI
    # O gate decidido, e o porquê. Em branco enquanto ninguém decidiu — e é esse branco que
    # `journey.advance_phase` recusa quando a fase do template exige gate. As notas não são
    # opcionais de fato em três das quatro saídas: as ressalvas do CONDITIONAL GO e o motivo do
    # REDESIGN/NO-GO são a única coisa que atravessa o tempo (FDD 033).
    gate_outcome = models.CharField(
        max_length=16, choices=GateOutcome.choices, blank=True, default=""
    )
    gate_notes = models.TextField(blank=True, default="")
    # Concluir com checklist incompleta é legítimo — o que não é legítimo é fazê-lo em silêncio.
    # Preenchido, este campo destrava a conclusão e fica como registro de quem decidiu pular o
    # quality gate e por quê.
    checklist_waiver = models.TextField(blank=True, default="")

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


class ProjectChecklistItem(TimestampedModel):
    """Instância por projeto de um item do quality gate (FDD 033).

    O `text` é copiado do template pelo mesmo motivo do `name` do entregável: reescrever a
    pergunta no template não pode reescrever o que um projeto já respondeu.

    O carimbo segue o `delivered_at` do entregável — desmarcar limpa a data, porque "conferido
    em" só faz sentido enquanto o item estiver conferido. É o mesmo movimento do `resolved_at`
    da `Pendencia`.
    """

    project_phase = models.ForeignKey(
        ProjectPhase, on_delete=models.CASCADE, related_name="checklist_items"
    )
    text = models.CharField(max_length=255)
    position = models.PositiveIntegerField(default=0)
    checked = models.BooleanField(default=False)
    checked_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["position", "id"]

    def save(self, *args, **kwargs) -> None:
        if self.checked and self.checked_at is None:
            self.checked_at = timezone.now()
        if not self.checked:
            self.checked_at = None
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


class CobrancaContato(TimestampedModel):
    """O que a casa **já disse** sobre uma fatura vencida (FDD 036, camada 3 da RFC 0004).

    Não é fila e não é agenda: é registro do que saiu. A régua é derivada do estado atual da
    fatura (`cobranca.degrau_devido`), e este modelo só responde "este degrau já foi gasto?".
    A diferença importa — uma fila de mensagens agendadas pode ser ultrapassada pelo pagamento,
    e é assim que se cobra quem pagou de manhã (ADR 0031).

    **`invoice` é `PROTECT` e não `CASCADE`.** A prova de que a casa cobrou não pode sumir com a
    fatura: sem isto, apagar um rascunho apagaria junto o histórico de comunicação sobre ele, e a
    pergunta "nós importunamos este cliente?" deixaria de ter resposta exatamente no caso em que
    alguém quer escondê-la.

    **`client` é desnormalizado de propósito.** O teto de frequência é por cliente somando *todas*
    as faturas dele; sem esta coluna a consulta viraria um `JOIN` por avaliação de degrau, dentro
    de um laço sobre faturas.

    **Nunca arquiva**, pela mesma razão e com a mesma `CheckConstraint` da `Invoice` (ADR 0021):
    é registro de comunicação sobre dinheiro, e esconder da lista sem desfazer o fato é pior que
    apagar.
    """

    class Degrau(models.TextChoices):
        PRE_AVISO = "pre_aviso", "Pré-aviso"
        LEMBRETE = "lembrete", "Lembrete"
        FIRME = "firme", "Cobrança firme"
        ESCALADA = "escalada", "Escalada interna"
        RENEGOCIACAO = "renegociacao", "Renegociação"

    class Canal(models.TextChoices):
        EMAIL = "email", "E-mail ao cliente"
        INTERNO = "interno", "Aviso interno"

    invoice = models.ForeignKey(Invoice, on_delete=models.PROTECT, related_name="cobrancas")
    client = models.ForeignKey(Client, on_delete=models.PROTECT, related_name="cobrancas")
    degrau = models.CharField(max_length=16, choices=Degrau.choices)
    canal = models.CharField(max_length=8, choices=Canal.choices)
    # **Data e não carimbo de relógio**, ao contrário de `Invoice.paid_at`. Toda regra da régua é
    # aritmética de dias sobre o vencimento, e o comando aceita `--hoje` para exercício
    # determinístico: gravar `now()` faria o teto de frequência comparar o dia simulado com o dia
    # real e a régua se comportaria diferente em teste e no ar. O relógio de parede continua
    # gravado — é o `created_at` herdado.
    sent_on = models.DateField()
    subject = models.CharField(max_length=255, blank=True, default="")
    # Vazio quando o degrau é interno. Texto e não `EmailField` porque um degrau pode ir a mais de
    # um contato de cobrança do mesmo cliente, e a prova é a lista inteira.
    to_email = models.TextField(blank=True, default="")
    # O texto que de fato saiu. É a prova, e é por isso que ele mora aqui e não é recomposto do
    # template: a constante de código muda com o tempo, o que o cliente leu não muda.
    body = models.TextField(blank=True, default="")
    # Nulo = automático (o job). Preenchido = uma pessoa apertou enviar. Os dois caminhos até aqui
    # são deliberados (ADR 0031) e se distinguem no registro, senão "quanto da nossa cobrança é
    # automática?" vira arqueologia.
    sent_by = models.ForeignKey(
        User, on_delete=models.SET_NULL, null=True, blank=True, related_name="+"
    )
    # Preenchida só quando o texto veio de um rascunho de IA revisado por gente.
    ai_interaction = models.ForeignKey(
        AiInteraction, on_delete=models.SET_NULL, null=True, blank=True, related_name="+"
    )

    class Meta:
        ordering = ["-sent_on", "-id"]
        indexes = [models.Index(fields=["client", "sent_on"])]
        constraints = [
            # **A idempotência do degrau mora aqui, e não numa guarda em Python.** Duas execuções
            # no mesmo dia, ou o job e uma pessoa ao mesmo tempo, param no banco em vez de
            # dependerem de quem leu antes.
            models.UniqueConstraint(
                fields=["invoice", "degrau"], name="unique_cobranca_degrau_por_fatura"
            ),
            models.CheckConstraint(
                condition=Q(archived_at__isnull=True), name="cobranca_contato_is_never_archived"
            ),
        ]

    def __str__(self) -> str:
        return f"{self.get_degrau_display()} — {self.client.name} ({self.sent_on})"


class CobrancaSuspensao(TimestampedModel):
    """Recuar, declarado (FDD 036, RFC 0004 "Segurança").

    Suspender a cobrança de quem está insatisfeito ou de quem esperou uma entrega atrasada é a
    regra certa e, nas palavras da RFC, *"a que mais apodrece na prática: vira desculpa para nunca
    cobrar, e o recebível estraga invisível"*. Por isso ela é **linha no banco com dono, prazo e
    motivo obrigatórios**, e não um `if` num relatório: dono para alguém responder por ela, prazo
    para ela expirar sozinha, motivo para a próxima pessoa saber o que se combinou.

    Vale para uma fatura **ou** para o cliente inteiro — exatamente um dos dois, no molde de
    `Document.clean()`. Uma suspensão que valesse para os dois níveis ao mesmo tempo teria duas
    leituras possíveis de "levantar", e a errada devolve a cobrança a quem ainda não devia ouvi-la.
    """

    invoice = models.ForeignKey(
        Invoice, on_delete=models.PROTECT, null=True, blank=True, related_name="suspensoes"
    )
    client = models.ForeignKey(
        Client, on_delete=models.PROTECT, null=True, blank=True, related_name="suspensoes"
    )
    # `PROTECT` e obrigatório: suspensão sem dono é a suspensão que apodrece. Apagar a conta de
    # quem suspendeu não pode deixar a decisão órfã.
    owner = models.ForeignKey(User, on_delete=models.PROTECT, related_name="cobrancas_suspensas")
    # Inclusivo: a régua volta a falar no dia seguinte a `until`.
    until = models.DateField()
    reason = models.TextField()
    created_by = models.ForeignKey(
        User, on_delete=models.SET_NULL, null=True, blank=True, related_name="+"
    )
    # Encerrada antes do prazo, por gente. Não é "pular silencioso": tem autor e carimbo, e é o
    # único jeito de desfazer uma suspensão criada por engano sem esperar o prazo inteiro.
    lifted_at = models.DateTimeField(null=True, blank=True)
    lifted_by = models.ForeignKey(
        User, on_delete=models.SET_NULL, null=True, blank=True, related_name="+"
    )

    class Meta:
        ordering = ["-until", "-id"]
        constraints = [
            models.CheckConstraint(
                condition=Q(archived_at__isnull=True), name="cobranca_suspensao_is_never_archived"
            ),
        ]

    def __str__(self) -> str:
        alvo = self.invoice or self.client
        return f"Suspensão até {self.until} — {alvo}"

    def clean(self) -> None:
        links = [self.invoice_id, self.client_id]
        if sum(value is not None for value in links) != 1:
            raise ValidationError(
                "A suspensão vale para exatamente uma fatura ou para um cliente."
            )
        if not (self.reason or "").strip():
            raise ValidationError({"reason": "Diga por que a cobrança está suspensa."})

    @property
    def is_active(self) -> bool:
        return self.lifted_at is None and self.until >= timezone.localdate()


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
