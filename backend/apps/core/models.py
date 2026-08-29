from __future__ import annotations

import hashlib
import os
import uuid
from datetime import date, datetime
from decimal import Decimal

from django.contrib.auth.models import AbstractUser
from django.core.exceptions import ValidationError
from django.core.validators import MaxValueValidator, MinValueValidator
from django.db import models, transaction
from django.db.models import Q
from django.utils import timezone
from pgvector.django import VectorField

from . import knowledge
from .priority import (
    DIMENSOES,
    FORMULA_PADRAO,
    FORMULAS,
    MAIOR_NOTA,
    MENOR_NOTA,
    calcular_score,
    pesos_da_formula,
)


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


def avatar_upload_to(instance: User, filename: str) -> str:
    """Nome **gerado**, e não o que veio no upload.

    O `Document` preserva o nome original porque ele viaja para o Drive e para o fornecedor de
    assinatura; o avatar não tem esse destino, então o nome enviado seria entrada do usuário
    dentro de um caminho de storage sem nada em troca. O uuid também é o que faz "trocar a foto"
    gravar um objeto novo em vez de disputar o nome do anterior — e é dele que sai o `ETag` da
    rota de leitura, que serviria a foto velha se o caminho não mudasse.
    """
    extension = os.path.splitext(filename or "")[1].lower()
    return f"avatars/{uuid.uuid4().hex}{extension}"


class User(AbstractUser):
    class Role(models.TextChoices):
        ADMIN = "admin", "Administrador"
        SALES = "sales", "Vendas"
        DELIVERY = "delivery", "Entrega"

    role = models.CharField(max_length=16, choices=Role.choices, default=Role.DELIVERY)
    # `FileField` e não `ImageField`: o segundo exige Pillow, que este backend não tem, e o que
    # ele daria — "isto é mesmo uma imagem" — é feito explicitamente em `ProfileAvatarSerializer`,
    # que confere tamanho, extensão **e** os bytes de assinatura, no estilo do
    # `DocumentSerializer.validate`. O arquivo é privado como o documento: nenhum ambiente serve
    # `MEDIA_ROOT` (ADR 0002), e a única porta é `GET /api/v1/users/<id>/avatar/`.
    avatar = models.FileField(upload_to=avatar_upload_to, blank=True)
    # `AbstractUser` não tem `updated_at`, e o `Last-Modified` da rota da foto precisa de uma
    # data. É também o sinal de troca que o `<img>` do topbar usa para parar de exibir a foto
    # anterior sem esperar o navegador decidir revalidar.
    avatar_updated_at = models.DateTimeField(null=True, blank=True)

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


class Account(TimestampedModel):
    """A organização com quem a casa se relaciona — desde antes de ela comprar.

    O nome canônico é `Account` (`docs/ontology/language-map.md` §2), e "cliente" deixa de ser o
    nome da entidade para virar o **rótulo** de um dos estados dela. A ADR 0052 é o que autoriza
    renomear a classe agora, na issue #67, em vez de esperar a Fase 6: a **tabela** continua
    `core_client` (ver `Meta` abaixo), e é a tabela — a linha e a pk — que a `aliases.md` §2b
    protege, porque o One deriva `organization.slug = biahflow-client-{id}` e a persiste.
    """

    class LifecycleStatus(models.TextChoices):
        """Onde a conta está na relação com a casa — três estados, e o do meio é que se chama
        "Cliente".

        `prospect` é a organização que ainda não fechou nada; `active` é cliente de fato, com
        venda ganha; `inactive` é quem **já foi** cliente e hoje não tem trabalho em andamento.
        Sem o terceiro, a conta que terminou o mandato só tinha dois destinos igualmente errados:
        continuar dizendo "Cliente" — e inflar toda contagem de carteira — ou ser arquivada, que
        é sumir do histórico. É o `language-map` §4.

        **Entrar em `inactive` não tem automação, e é decisão.** A promoção `prospect → active`
        é do signal `_promote_account_on_won`, porque "houve venda ganha" é fato observável no
        banco. "Não tem trabalho em andamento" não é: projeto pausado, mandato em renovação e
        cliente que sumiu produzem o mesmo estado no schema e significados diferentes. Quem
        edita a conta afirma.
        """

        PROSPECT = "prospect", "Prospect"
        ACTIVE = "active", "Ativo"
        INACTIVE = "inactive", "Inativo"

    name = models.CharField(max_length=255)
    legal_name = models.CharField(max_length=255, blank=True)
    tax_id = models.CharField(max_length=32, blank=True)
    # Aditivo e opcional, na forma de `CommercialOpportunity.service`: é o que a instanciação
    # de Funcionário
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
    # Quem cadastra afirma o estado (a SPA oferece a escolha); o default é o mais conservador,
    # porque um POST que omite o campo não deve alegar uma venda que não houve. A conta vinda de
    # conversão de lead também nasce "prospect", e vira "active" pelo signal quando a oportunidade
    # é ganha — promoção que um PATCH não desfaz (ver `AccountSerializer.validate_lifecycle_status`).
    lifecycle_status = models.CharField(
        max_length=16, choices=LifecycleStatus.choices, default=LifecycleStatus.PROSPECT
    )

    class Meta:
        ordering = ["name"]
        # **A tabela não se move** (ADR 0052). Fixá-la aqui é o que torna o `RenameModel` da
        # migração `0062` um no-op no banco: `alter_db_table` abre com
        # `if old_db_table == new_db_table: return`. O nome da tabela é a Fase 6; o que sai agora
        # é só o nome da classe.
        db_table = "core_client"

    def __str__(self) -> str:
        return self.name


class Contact(TimestampedModel):
    account = models.ForeignKey(Account, on_delete=models.CASCADE, related_name="contacts")
    first_name = models.CharField(max_length=128)
    # Sobrenome é opcional (issue #55, FDD 001): nem todo contato cadastrado tem um, e exigi-lo
    # obrigaria quem cadastra a inventar um valor só para satisfazer o formulário.
    last_name = models.CharField(max_length=128, blank=True)
    email = models.EmailField(blank=True)
    phone = models.CharField(max_length=32, blank=True)
    job_title = models.CharField(max_length=128, blank=True)
    # Quem recebe cobrança neste cliente (FDD 036). **Default `False`, e é a decisão que importa:**
    # a régua fala de dinheiro, e chutar o destinatário é o erro caro. Sem ninguém marcado, o
    # degrau não vira e-mail ao cliente — vira escalada interna com o motivo escrito, que é o
    # "cala quando não sabe" que a casa já usa no enriquecimento de lead (FDD 030).
    receives_billing = models.BooleanField(default=False)

    class Meta:
        ordering = ["first_name", "last_name"]

    @property
    def full_name(self) -> str:
        """Nome composto — a única definição (CLAUDE.md): `ContactSerializer.name` e `ai.py`
        leem daqui em vez de recompor o mesmo espaço-e-strip em dois lugares."""
        return f"{self.first_name} {self.last_name}".strip()


class Engagement(TimestampedModel):
    """O mandato de transformação que a conta contratou — a espinha dorsal `Account → Project`.

    Até aqui o projeto pendurava direto na conta e nascia de uma venda, numa relação 1-1 com ela.
    Isso descreve bem a venda avulsa e descreve mal o que a casa passou a vender: uma
    Transformation Partnership é recorrente, origina vários projetos ao longo de meses e não tem
    onde ser representada — nem a oportunidade comporta os projetos (o `OneToOneField` só admitia
    um), nem existia camada onde várias vendas e vários projetos se reconhecessem como o **mesmo**
    trabalho. Sem ela, "como vai a transformação daquela conta?" só tem resposta somando projetos
    a olho, e a resposta muda conforme quem soma.

    `Engagement` é essa camada, e ela é **obrigatória** para todo projeto (D3 do mapa de
    linguagem). A venda avulsa cria um engajamento de escopo único, criado sozinho pela
    `convert-to-project` — dois caminhos no código custariam mais que uma linha a mais na tabela,
    e o caminho raro é justamente o que ninguém testa.

    Ele é do **comercial**: quem entrega lê, não escreve (`permissions.RolePermission`). E não é
    fronteira de acesso — o recorte da Entrega continua sendo `ProjectMember`, e enxergar um
    engajamento não dá acesso a projeto nenhum dele (ADR 0050, FDD 046).
    """

    class Status(models.TextChoices):
        ACTIVE = "active", "Ativo"
        PAUSED = "paused", "Pausado"
        CLOSED = "closed", "Encerrado"

    class CommercialModel(models.TextChoices):
        DESIGN_PARTNER = "design_partner", "Design partner"
        PAID = "paid", "Pago"

    # `account` é o termo canônico do mapa de linguagem. O campo nasceu com o nome certo quando
    # a classe ainda se chamava `Client`; desde a fatia 2 da issue #67 (ADR 0052) os dois nomes
    # coincidem, e o que resta de legado é a tabela, que a Fase 6 renomeia.
    account = models.ForeignKey(Account, on_delete=models.PROTECT, related_name="engagements")
    name = models.CharField(max_length=255)
    # O mandato em si: o que a casa foi contratada para transformar. Texto livre e opcional
    # porque o engajamento de escopo único nasce da conversão, onde o que existe é o escopo da
    # oportunidade — exigir redação nesse ponto travaria a conversão por um campo de prosa.
    mandate = models.TextField(blank=True, default="")
    sponsor = models.ForeignKey(
        Contact, on_delete=models.SET_NULL, null=True, blank=True,
        related_name="sponsored_engagements",
    )
    owner = models.ForeignKey(User, on_delete=models.PROTECT, related_name="owned_engagements")
    status = models.CharField(max_length=16, choices=Status.choices, default=Status.ACTIVE)
    started_at = models.DateField(null=True, blank=True)
    ended_at = models.DateField(null=True, blank=True)
    success_definition = models.TextField(blank=True, default="")
    # Carimbo do backfill da 0056, não campo de operação: marca a conta cujos projetos **talvez**
    # sejam jornadas distintas agrupadas num engajamento só. A migração não separa sozinha — ela
    # não tem como saber —, ela sinaliza para revisão humana. Ver a docstring da 0056.
    needs_review = models.BooleanField(default=False)
    # O mandato nasce de dois jeitos: a conta paga, ou entra como `design_partner` — recebe
    # Discovery sem cobrança em troca de servir de caso e de campo de prova. O campo registra a
    # condição, não concede nada: nenhuma regra de preço, fatura ou catálogo o lê hoje, e ele
    # existe só para os dois modos pararem de ser a mesma linha. Também não decide a pendência A2
    # do `docs/ontology/language-map.md` §9 ("Design Partner é condição comercial de um degrau ou
    # oferta própria?") — gravar o modo no mandato e decidir se existe um sétimo degrau no
    # catálogo são coisas diferentes, e é fácil confundir as duas se isto não estiver escrito
    # aqui. As linhas que já existiam antes deste campo viraram `paid` por inferência do
    # backfill da 0056 (mandato só nascia de conta com projeto, e projeto veio de venda) — a
    # correção de quem de fato é design partner é feita no admin do Django
    # (`EngagementAdmin`), não em migração nem em comando de terminal: a lista de contas de
    # design partner cresce por venda, não por deploy.
    commercial_model = models.CharField(
        max_length=16, choices=CommercialModel.choices, default=CommercialModel.PAID
    )

    class Meta:
        ordering = ["-started_at", "-id"]

    def __str__(self) -> str:
        return self.name

    def clean(self) -> None:
        if self.started_at and self.ended_at and self.ended_at < self.started_at:
            raise ValidationError({"ended_at": "A data final não pode ser anterior à inicial."})
        if self.status == self.Status.CLOSED and self.ended_at is None:
            raise ValidationError({"ended_at": "Um engajamento encerrado precisa de data final."})
        # O patrocinador é quem responde pelo mandato **dentro da conta**. Um contato de outra
        # organização aqui seria o mesmo defeito que `Activity.clean()` já fecha na oportunidade:
        # a tela mostraria um nome que não pertence àquele cliente, e ninguém acusaria.
        sponsor = self.sponsor if self.sponsor_id else None
        if sponsor is not None and sponsor.account_id != self.account_id:
            raise ValidationError({"sponsor": "O patrocinador deve ser contato da mesma conta."})


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


class CommercialOpportunity(TimestampedModel):
    account = models.ForeignKey(Account, on_delete=models.PROTECT, related_name="opportunities")
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
    # A avaliação que autorizou esta venda (ADR 0049). Referência por string porque
    # `Qualification` é declarada depois de `Lead`, bem abaixo daqui — e ela fica *depois* de
    # propósito: a avaliação pende do lead, não da oportunidade.
    #
    # Nula no que já existia e no que nasce fora do funil de lead (indicação, conta que volta a
    # comprar). Obrigá-la agora invalidaria a carteira inteira; o que a invariante 5 do mapa de
    # linguagem exige é o inverso — quando ela existe, ela é `qualified`, e é o `clean()` abaixo
    # que garante isso.
    origin_qualification = models.ForeignKey(
        "Qualification", on_delete=models.PROTECT, null=True, blank=True,
        related_name="commercial_opportunities",
    )
    # O mandato a que esta venda pertence (ADR 0050). **Opcional, e permanece opcional**: a
    # oportunidade costuma nascer antes de haver mandato nenhum — é ela que o origina, quando é a
    # primeira. Exigi-la aqui inverteria a ordem dos fatos. `SET_NULL` pelo mesmo motivo: apagar o
    # engajamento não pode apagar a venda que já aconteceu.
    engagement = models.ForeignKey(
        "Engagement", on_delete=models.SET_NULL, null=True, blank=True,
        related_name="commercial_opportunities",
    )

    class Meta:
        # A classe renomeou na issue #67 e a **tabela fica** (ADR 0052): `db_table` fixa aqui o
        # nome que ela já tem, para o `RenameModel` da migração não emitir `ALTER TABLE`. O nome
        # da tabela é a Fase 6, e o que a `aliases.md` §2b protege é a pk — que só se move se a
        # linha se mover.
        db_table = "core_opportunity"
        ordering = ["expected_close_date", "id"]

    def clean(self) -> None:
        """Invariante 5 do mapa de linguagem, no modelo e não só na view.

        `POST /qualifications/{id}/open-opportunity/` é o caminho previsto e já recusa com 409, mas
        a regra não pode morar só lá: shell, admin e migração futura criam
        `CommercialOpportunity` sem passar por view nenhuma, e uma venda apontando para uma avaliação `nurture` diria que a casa vendeu
        para quem ela mesma decidiu não vender ainda.
        """
        origem = self.origin_qualification if self.origin_qualification_id else None
        if origem is not None and origem.outcome != Qualification.Outcome.QUALIFIED:
            raise ValidationError({
                "origin_qualification":
                    "Só uma qualificação com resultado Qualificado abre oportunidade comercial."
            })

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

    # **Projeção temporária.** A conta canônica do projeto é `engagement.account`; este campo
    # sobrevive porque metade do produto (agregadores, permissões, portal) ainda pergunta pelo
    # cliente direto, e removê-lo é a Fase 6. O que o mantém honesto é a validação em `clean()`
    # abaixo — sem ela, a projeção divergiria da fonte em silêncio, que é exatamente o defeito
    # que uma projeção introduz quando ninguém a amarra.
    #
    # **É o único campo que a fatia 2 da issue #67 não renomeou, e isso é decisão.** Chamá-lo de
    # `account` criaria duas coisas com o nome canônico no mesmo objeto — `project.account` e
    # `project.engagement.account` — que podem divergir; o nome canônico deixaria de identificar
    # a fonte, que é a única coisa que ele existe para fazer. Ele fica com o nome antigo até a
    # Fase 6 removê-lo. Ver ADR 0052.
    client = models.ForeignKey(Account, on_delete=models.PROTECT, related_name="projects")
    # O mandato a que este projeto pertence — **obrigatório** (invariante 7 do mapa de linguagem).
    # Nasceu nulo na 0055 e virou NOT NULL na 0057, com o backfill da 0056 no meio; ver a
    # docstring da 0057 para por que os três passos são migrações separadas.
    engagement = models.ForeignKey("Engagement", on_delete=models.PROTECT, related_name="projects")
    # A venda que originou este projeto — **1-N e opcional**. Era `OneToOneField`, e a
    # cardinalidade antiga é o que impedia uma venda recorrente de originar mais de um projeto.
    # A garantia de "converte uma vez só" que o banco dava saiu daqui e virou ato explícito na
    # `CommercialOpportunityViewSet.convert_to_project` (409 + `select_for_update`), porque o
    # que se quer proteger é o **botão**, não a relação: um segundo projeto com a mesma origem é legítimo, e
    # nasce por `POST /projects/`. Ver ADR 0050.
    originating_commercial_opportunity = models.ForeignKey(
        CommercialOpportunity, on_delete=models.PROTECT, related_name="projects",
        null=True, blank=True,
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
    # O carimbo da projeção que o One consome (ADR 0051). Duas colunas e uma regra: **quem
    # carimba é quem muda o estado, não quem lê**. A rota do snapshot é um `GET`, e incrementar
    # ali seria escrita a cada leitura — com duas requisições concorrentes produzindo versões
    # iguais ou fora de ordem, que é justamente o sinal que o comparador do outro lado usa para
    # descartar o obsoleto. Quem escreve é `portal.emit`, o estrangulamento por onde passam os
    # onze receivers `_emit_*`.
    #
    # `observed_at` é o instante em que **este** lado observou o estado, e o nome vem de
    # `GithubDeliveryProjection.observed_at`, a projeção inversa (GitHub → Pulse), com o mesmo
    # sentido. Sem backfill: projeto que não mudou desde o deploy fica em `0`/`None`, e a ADR
    # 0076 do repo `one` declara que versão ausente de um lado não recusa nada.
    projection_version = models.PositiveIntegerField(default=0)
    projection_observed_at = models.DateTimeField(null=True, blank=True)

    objects = ProjectQuerySet.as_manager()

    class Meta:
        ordering = ["due_date", "id"]

    def clean(self) -> None:
        if self.due_date < self.start_date:
            raise ValidationError({"due_date": "A data final não pode ser anterior à inicial."})
        # Invariante 6 do mapa de linguagem: nenhum projeto nasce de oferta de aquisição (ADR 0049).
        # A `convert-to-project` já recusa com 400, e a regra fica aqui pela razão da
        # `CommercialOpportunity.clean()` logo acima — a via da view não é a única via.
        service = self.service if self.service_id else None
        if service is not None and service.category == Service.Category.ACQUISITION:
            raise ValidationError({
                "service": "Oferta de aquisição não gera projeto — escolha um degrau da escada."
            })
        # O que mantém a projeção `client` honesta (ADR 0050). Dois caminhos chegam ao dono do
        # projeto — `project.client` e `project.engagement.account` — e nada além desta linha
        # impede que eles digam coisas diferentes. Divergindo, o projeto aparece na carteira de
        # uma conta e no mandato de outra, e nenhuma tela acusa.
        engagement = self.engagement if self.engagement_id else None
        if engagement is not None and engagement.account_id != self.client_id:
            raise ValidationError({
                "engagement": "O engajamento deve pertencer ao mesmo cliente do projeto."
            })

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


class EngineeringHandoff(TimestampedModel):
    """Handoff de engenharia: Pulse persiste o contrato e provisiona a GitHub Issue (FDD 040).

    Distinto da sincronia de tarefas (FDD 004 / `tasksync`): aqui a Issue **é** o Task Contract
    do EngineeringOS, não o espelho de uma `Task`. Zero LLM — o corpo é markdown determinístico
    a partir dos campos estruturados. Ver ADR 0040.
    """

    class Status(models.TextChoices):
        PENDING = "pending", "Pendente"
        PROVISIONED = "provisioned", "Provisionado"
        FAILED = "failed", "Falhou"

    project = models.ForeignKey(
        Project, on_delete=models.CASCADE, related_name="engineering_handoffs"
    )
    source_task = models.ForeignKey(
        Task,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="engineering_handoffs",
    )
    pulse_work_item_id = models.CharField(max_length=128)
    title = models.CharField(max_length=255)
    objective = models.TextField()
    context = models.TextField(blank=True, default="")
    acceptance_criteria = models.TextField()
    scope_text = models.TextField(blank=True, default="")
    out_of_scope_text = models.TextField(blank=True, default="")
    # Vazio na hora de provisionar cai em `settings.GITHUB_REPO`. Persistido com o valor efetivo
    # depois do sucesso, para a unique `(repository, github_issue_number)` valer de verdade.
    repository = models.CharField(max_length=255, blank=True, default="")
    milestone_ref = models.CharField(max_length=255, blank=True, default="")
    adr_refs = models.JSONField(default=list, blank=True)
    nfr_refs = models.JSONField(default=list, blank=True)
    fdd_refs = models.JSONField(default=list, blank=True)
    correlation_id = models.UUIDField(default=uuid.uuid4, editable=False)
    github_issue_number = models.PositiveIntegerField(null=True, blank=True)
    github_issue_url = models.URLField(blank=True, default="")
    github_node_id = models.CharField(max_length=128, blank=True, default="")
    status = models.CharField(max_length=16, choices=Status.choices, default=Status.PENDING)
    attempt_count = models.PositiveIntegerField(default=0)
    last_attempt_at = models.DateTimeField(null=True, blank=True)
    last_error_code = models.CharField(max_length=64, blank=True, default="")
    last_error_message = models.TextField(blank=True, default="")

    class Meta:
        ordering = ["-created_at", "-id"]
        constraints = [
            models.UniqueConstraint(
                fields=["pulse_work_item_id"],
                name="unique_engineering_handoff_pulse_work_item",
            ),
            models.UniqueConstraint(
                fields=["repository", "github_issue_number"],
                condition=Q(github_issue_number__isnull=False) & ~Q(repository=""),
                name="unique_engineering_handoff_github_issue",
            ),
        ]

    def __str__(self) -> str:
        return self.title

    def clean(self) -> None:
        errors: dict[str, str] = {}
        if not (self.pulse_work_item_id or "").strip():
            errors["pulse_work_item_id"] = "Informe o identificador do item no Pulse."
        if not (self.title or "").strip():
            errors["title"] = "Informe o título."
        if not (self.objective or "").strip():
            errors["objective"] = "Informe o objetivo."
        if not (self.acceptance_criteria or "").strip():
            errors["acceptance_criteria"] = "Informe os critérios de aceite."
        if self.status == self.Status.PROVISIONED:
            if not self.github_issue_number or not (self.github_issue_url or "").strip():
                errors["status"] = (
                    "Um handoff provisionado precisa do número e da URL da GitHub Issue."
                )
        if (
            self.source_task_id
            and self.source_task
            and self.project_id
            and self.source_task.project_id != self.project_id
        ):
            errors["source_task"] = "A tarefa de origem deve pertencer ao mesmo projeto."
        if errors:
            raise ValidationError(errors)


class GithubDeliveryProjection(TimestampedModel):
    """Projeta o estado de engenharia do GitHub sobre um item de entrega do Pulse (FDD 041).

    Direção de **leitura**, complementar ao provisionamento (FDD 040, que é a de escrita): aqui o
    Pulse referencia `repository` + Issue/PR e projeta o estado *observado*, sem virar fonte da
    verdade do ciclo de Issue/PR/CI (ADR 0046, que herda a fronteira da ADR 0040). O que a
    engenharia decide continua no GitHub; o Pulse só espelha para operar.

    **Nunca inventa status.** Uma referência não confirmada aparece como `stale`/`unavailable`/
    `permission_denied`/`reference_missing`, distinta de um estado confirmado (`current`). Os campos
    de engenharia (`issue_state`, `pr_state`, `head_sha`, `ci_state`, ...) são somente-projeção:
    uma edição normal do Pulse não os reescreve — quem os move é o webhook ou a reconciliação. Zero
    LLM: parsing, comparação de SHA/status e serialização são determinísticos.
    """

    class ProjectionStatus(models.TextChoices):
        PENDING = "pending", "Pendente"  # criada, nunca observada
        CURRENT = "current", "Atual"  # confirmada por evento ou reconciliação
        UNAVAILABLE = "unavailable", "Indisponível"  # GitHub não respondeu
        PERMISSION_DENIED = "permission_denied", "Sem permissão"  # 403
        REFERENCE_MISSING = "reference_missing", "Referência ausente"  # 404

    class IssueState(models.TextChoices):
        UNKNOWN = "unknown", "Desconhecido"
        OPEN = "open", "Aberta"
        CLOSED = "closed", "Fechada"

    class PullState(models.TextChoices):
        UNKNOWN = "unknown", "Desconhecido"
        NONE = "none", "Sem PR"
        DRAFT = "draft", "Rascunho"
        OPEN = "open", "Aberto"
        CLOSED = "closed", "Fechado"
        MERGED = "merged", "Mesclado"

    class ReviewState(models.TextChoices):
        UNKNOWN = "unknown", "Desconhecido"
        PENDING = "pending", "Em revisão"
        APPROVED = "approved", "Aprovado"
        CHANGES_REQUESTED = "changes_requested", "Mudanças pedidas"

    class CiState(models.TextChoices):
        UNKNOWN = "unknown", "Desconhecido"
        PENDING = "pending", "Em execução"
        SUCCESS = "success", "Verde"
        FAILURE = "failure", "Vermelho"

    project = models.ForeignKey(
        Project, on_delete=models.CASCADE, related_name="github_projections"
    )
    # Proveniência da direção de escrita: quando a referência veio de um handoff provisionado
    # (FDD 040), guardamos o vínculo. Opcional — um projeto pode mapear uma Issue que o Pulse não
    # criou. `SET_NULL` para não perder a projeção se o handoff for removido.
    handoff = models.OneToOneField(
        "EngineeringHandoff",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="projection",
    )
    repository = models.CharField(max_length=255)  # formato "owner/repo"
    issue_number = models.PositiveIntegerField()
    issue_url = models.URLField(blank=True, default="")

    projection_status = models.CharField(
        max_length=24, choices=ProjectionStatus.choices, default=ProjectionStatus.PENDING
    )
    issue_state = models.CharField(
        max_length=16, choices=IssueState.choices, default=IssueState.UNKNOWN
    )
    pr_state = models.CharField(
        max_length=16, choices=PullState.choices, default=PullState.UNKNOWN
    )
    pr_number = models.PositiveIntegerField(null=True, blank=True)
    pr_url = models.URLField(blank=True, default="")
    head_sha = models.CharField(max_length=64, blank=True, default="")
    head_ref = models.CharField(max_length=255, blank=True, default="")
    review_state = models.CharField(
        max_length=24, choices=ReviewState.choices, default=ReviewState.UNKNOWN
    )
    ci_state = models.CharField(
        max_length=16, choices=CiState.choices, default=CiState.UNKNOWN
    )

    # Proveniência e frescor: quando foi confirmado, por qual evento, e o erro da última tentativa.
    observed_at = models.DateTimeField(null=True, blank=True)  # última confirmação (evento/poll)
    last_event_at = models.DateTimeField(null=True, blank=True)  # marca d'água contra out-of-order
    last_delivery_id = models.CharField(max_length=128, blank=True, default="")
    last_event_type = models.CharField(max_length=64, blank=True, default="")
    last_error_code = models.CharField(max_length=64, blank=True, default="")
    last_error_message = models.TextField(blank=True, default="")

    class Meta:
        ordering = ["-updated_at", "-id"]
        constraints = [
            # Uma Issue projeta para exatamente um item de entrega — a chave de resolução do webhook.
            models.UniqueConstraint(
                fields=["repository", "issue_number"],
                name="unique_github_delivery_projection_ref",
            ),
        ]

    def __str__(self) -> str:
        return f"{self.repository}#{self.issue_number}"

    def clean(self) -> None:
        errors: dict[str, str] = {}
        repo = (self.repository or "").strip()
        parts = repo.split("/")
        if len(parts) != 2 or not parts[0] or not parts[1] or any(c in repo for c in " ?&#"):
            errors["repository"] = "O repositório deve estar no formato owner/repo."
        if not self.issue_number:
            errors["issue_number"] = "Informe o número da Issue no GitHub."
        if self.handoff_id and self.handoff and self.project_id:
            if self.handoff.project_id != self.project_id:
                errors["handoff"] = "O handoff de origem deve pertencer ao mesmo projeto."
        if errors:
            raise ValidationError(errors)

    def display_state(self, stale_after_seconds: int, now: datetime | None = None) -> str:
        """Estado *visível*: dobra o frescor no estado persistido (FDD 041).

        `current` só sobrevive enquanto a observação é recente; passado o limite vira `stale`. A
        regra é aqui, e não no serializer, para o webhook, a reconciliação e a API concordarem — uma
        segunda definição de "atual" divergiria da primeira em silêncio.
        """
        if self.projection_status != self.ProjectionStatus.CURRENT:
            return str(self.projection_status)
        if self.observed_at is None:
            return "stale"
        reference = now if now is not None else timezone.now()
        age = (reference - self.observed_at).total_seconds()
        return "stale" if age > stale_after_seconds else "current"


class GithubWebhookDelivery(models.Model):
    """Inbox de idempotência dos webhooks GitHub (ADR 0037 como contexto, FDD 041).

    A reentrega duplicada do GitHub carrega o mesmo `X-GitHub-Delivery`; a segunda vez a linha já
    existe e o handler vira no-op. Não é recurso de negócio — é registro operacional e **não
    arquiva** (não estende `TimestampedModel`).
    """

    delivery_id = models.CharField(max_length=128, unique=True)
    event_type = models.CharField(max_length=64, blank=True, default="")
    received_at = models.DateTimeField(auto_now_add=True)
    projection = models.ForeignKey(
        GithubDeliveryProjection,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="+",
    )

    class Meta:
        ordering = ["-received_at", "-id"]

    def __str__(self) -> str:
        return self.delivery_id


class Document(TimestampedModel):
    account = models.ForeignKey(Account, on_delete=models.CASCADE, null=True, blank=True)
    commercial_opportunity = models.ForeignKey(
        CommercialOpportunity, on_delete=models.CASCADE, null=True, blank=True
    )
    project = models.ForeignKey(Project, on_delete=models.CASCADE, null=True, blank=True)
    file = models.FileField(upload_to="documents/%Y/%m/", blank=True)
    drive_file_id = models.CharField(max_length=128, blank=True, default="")
    drive_link = models.URLField(blank=True, default="")
    original_name = models.CharField(max_length=255)
    uploaded_by = models.ForeignKey(User, on_delete=models.PROTECT, related_name="uploaded_documents")

    def clean(self) -> None:
        links = [self.account_id, self.commercial_opportunity_id, self.project_id]
        if sum(value is not None for value in links) != 1:
            raise ValidationError("O documento deve estar vinculado a exatamente um recurso.")

    @property
    def linked_resource(self) -> Account | CommercialOpportunity | Project | None:
        return self.account or self.commercial_opportunity or self.project


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
    account = models.ForeignKey(Account, on_delete=models.SET_NULL, null=True, blank=True, related_name="leads")
    commercial_opportunity = models.ForeignKey(
        CommercialOpportunity, on_delete=models.SET_NULL, null=True, blank=True,
        related_name="leads",
    )

    class Meta:
        ordering = ["-created_at"]

    def __str__(self) -> str:
        return f"{self.name} <{self.email}>"


class Qualification(TimestampedModel):
    """A avaliação que decide se um `Lead` vira venda — e que até aqui não existia (ADR 0049).

    O `POST /leads/{id}/convert/` criava, num ato só, um `Account` **e** uma
    `CommercialOpportunity` no degrau gratuito da escada. Isso gravava uma conversa de qualificação como venda registrada: ela entrava
    no funil, somava no pipeline e podia virar `Project`. A sequência normativa do Language Map é
    `Lead → Qualification → (qualified) → CommercialOpportunity`, e o degrau do meio precisava de
    linha própria para que a decisão tivesse autor, data e motivo (decisão D1).

    **Um lead tem várias.** O `nurture` de hoje vira `qualified` daqui a seis meses, e as duas
    avaliações são fatos distintos — não há constraint de unicidade por lead, de propósito.
    Sobrescrever a avaliação anterior apagaria justamente o histórico que ela existe para guardar.

    **A IA é insumo, nunca decisão** (Language Map §5). `ai_suggested_outcome` e `ai_score_snapshot`
    guardam o que o modelo achou no momento da avaliação, e nada os copia para `outcome`: quem
    qualifica é o `assessor`.
    """

    class Outcome(models.TextChoices):
        QUALIFIED = "qualified", "Qualificado"
        NURTURE = "nurture", "Nutrir"
        DISQUALIFIED = "disqualified", "Desqualificado"

    class Level(models.TextChoices):
        HIGH = "high", "Alto"
        MEDIUM = "medium", "Médio"
        LOW = "low", "Baixo"

    lead = models.ForeignKey(Lead, on_delete=models.CASCADE, related_name="qualifications")
    # `PROTECT` e não `CASCADE`: a conta sobrevive à avaliação, e apagar uma conta que já tem
    # avaliação registrada é ato deliberado, não efeito colateral. Nula enquanto a conversão ainda
    # não resolveu a organização (avaliação de lead desqualificado não precisa criar conta).
    account = models.ForeignKey(
        Account, on_delete=models.PROTECT, null=True, blank=True, related_name="qualifications"
    )
    happened_at = models.DateTimeField(default=timezone.now)
    assessor = models.ForeignKey(
        User, on_delete=models.SET_NULL, null=True, blank=True,
        related_name="qualifications_assessed",
    )
    # Os cinco eixos do roteiro de qualificação. Todos opcionais: o registro tem de acontecer mesmo
    # quando quem avaliou só sabe dizer o resultado, senão ele não acontece.
    fit = models.CharField(max_length=8, choices=Level.choices, blank=True, default="")
    need = models.CharField(max_length=8, choices=Level.choices, blank=True, default="")
    urgency = models.CharField(max_length=8, choices=Level.choices, blank=True, default="")
    authority = models.CharField(max_length=8, choices=Level.choices, blank=True, default="")
    capacity = models.CharField(max_length=8, choices=Level.choices, blank=True, default="")
    evidence = models.TextField(blank=True, default="")
    # **Sem default**, e é a decisão central desta entidade: uma avaliação sem resultado é uma
    # avaliação que não aconteceu, e um default faria o formulário meio-preenchido virar decisão.
    outcome = models.CharField(max_length=16, choices=Outcome.choices)
    rationale = models.TextField(blank=True, default="")
    next_step = models.CharField(max_length=200, blank=True, default="")
    nurture_until = models.DateField(null=True, blank=True)
    ai_suggested_outcome = models.CharField(
        max_length=16, choices=Outcome.choices, blank=True, default=""
    )
    ai_score_snapshot = models.PositiveSmallIntegerField(null=True, blank=True)
    # Mapeamento do backfill da migração 0052: a `CommercialOpportunity` de tier
    # `qualification_call` que esta avaliação passou a representar. `legacy_` é o único prefixo que o mapa de linguagem
    # aceita em `opportunity` sem qualificador — é ponte para o nome antigo, não conceito novo.
    legacy_opportunity = models.OneToOneField(
        CommercialOpportunity, on_delete=models.SET_NULL, null=True, blank=True,
        related_name="backfilled_qualification",
    )

    class Meta:
        ordering = ["-happened_at"]

    def __str__(self) -> str:
        return f"{self.lead_id} · {self.get_outcome_display()}"

    def clean(self) -> None:
        if self.outcome == self.Outcome.NURTURE and self.nurture_until is None:
            raise ValidationError(
                {"nurture_until": "Nutrir exige a data em que este lead volta ao radar."}
            )
        # O inverso também é erro, e não zelo excessivo: guardar data de retorno para quem foi
        # qualificado ou descartado promete um follow-up que ninguém vai fazer, e a lista de
        # nutrição passa a mostrar quem não está em nutrição.
        if self.outcome != self.Outcome.NURTURE and self.nurture_until is not None:
            raise ValidationError(
                {"nurture_until": "Só faz sentido em uma avaliação com resultado Nutrir."}
            )
        # Fronteira de conta: sem isto, uma avaliação pode ficar pendurada na organização de
        # **outro** lead — o mesmo vazamento por campo opcional que `Activity.clean()` fecha.
        if self.account_id and self.lead_id and self.lead.account_id:
            if self.lead.account_id != self.account_id:
                raise ValidationError(
                    {"account": "A conta deve ser a mesma já vinculada ao lead."}
                )


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

    account = models.ForeignKey(Account, on_delete=models.CASCADE, related_name="activities")
    commercial_opportunity = models.ForeignKey(
        CommercialOpportunity, on_delete=models.SET_NULL, null=True, blank=True,
        related_name="activities",
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
        if (
            self.commercial_opportunity_id
            and self.commercial_opportunity
            and self.commercial_opportunity.account_id != self.account_id
        ):
            raise ValidationError(
                {"commercial_opportunity": "A oportunidade deve pertencer ao mesmo cliente."}
            )
        # Mesma checagem para a fatura, e pela mesma razão que a da oportunidade: sem ela, uma
        # resposta de cobrança pode ficar pendurada na fatura de **outro** cliente — e é essa
        # linha que a tela de cobrança lê para decidir o próximo passo.
        if self.invoice_id and self.invoice and self.invoice.account_id != self.account_id:
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

    account = models.ForeignKey(Account, on_delete=models.CASCADE, related_name="satisfacoes")
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
        return f"{self.get_nivel_display()} — {self.account.name} ({self.happened_on})"

    def clean(self) -> None:
        if self.project_id and self.project and self.project.client_id != self.account_id:
            raise ValidationError({"project": "O projeto deve pertencer ao mesmo cliente."})
        # Mesma checagem para a atividade de origem, e pela mesma razão: sem ela, a resposta de
        # **outro** cliente viraria a satisfação declarada deste — e essa é a linha que troca a
        # escada da cobrança e tira 20 pontos do Health Score.
        if (
            self.source_activity_id
            and self.source_activity
            and self.source_activity.account_id != self.account_id
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


class Process(TimestampedModel):
    """Um processo da operação do cliente, mapeado no Discovery estruturado (FDD 039).

    **Por que a entidade existe se a metodologia não a define.** O material
    (`docs/metodologia-fde.md:106-110`) descreve o P-S-D-T-E-R como o esquema "para cada etapa de um
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
    é da empresa e sobrevive à venda que o descobriu (a metodologia separa Account de
    CommercialOpportunity, `docs/metodologia-fde.md:64-67`). Ancorar no projeto obrigaria a recriar o AS-IS do zero a cada
    novo Discovery da mesma empresa — que é exatamente o defeito que o `DigitalEmployee` tinha
    antes da FDD 026, quando o que valia morava só na instância e não no catálogo.
    """

    account = models.ForeignKey(Account, on_delete=models.CASCADE, related_name="processos")
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

    # Os nove insumos do custo do estado atual (`docs/metodologia-fde.md:118-119`):
    # `Volume × Tempo × Pessoas × Custo + Retrabalho + Erros + Perdas + Espera + Risco`.
    #
    # Todos nulos, e **nulo aqui é "não apurado", nunca zero**: `processos.custo_do_estado_atual`
    # devolve o que faltou em `nao_apurado` em vez de somar zero, porque zerar afirmaria que
    # executar o processo não custa nada. É a lacuna dita e não preenchida, como em `ai.py` no
    # KPI sem base registrada (FDD 027).
    #
    # **O sufixo `_mes` não é decoração.** `ProcessStep` tem `tempo`, `erro` e `retrabalho`, e
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
        # A tabela **não** se move (ADR 0052): `RenameModel` com o `db_table` já fixado no nome
        # legado não emite SQL nenhum, e é a pk que a `docs/ontology/aliases.md` §2b protege. O
        # renome da tabela é a Fase 6.
        db_table = "core_processo"
        ordering = ["position", "id"]

    def __str__(self) -> str:
        return self.name

    def archive(self) -> None:
        """Arquiva o processo **e o que pendura nele**, no mesmo instante.

        A regra transversal da FDD 025 é que arquivar não cascateia — e que, quando os filhos
        são listáveis por conta própria, quem os tem precisa escolher: recusar com 409 ou arquivar
        junto. Etapa e evidência são listáveis (`/processo-etapas/?process=`,
        `/evidencias/?process=`), então sem escolha ficariam visíveis apontando para um pai
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
        self.steps.filter(archived_at__isnull=True).update(archived_at=momento)
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
        self.steps.filter(archived_at=momento).update(archived_at=None)
        self.evidencias.filter(archived_at=momento).update(archived_at=None)


class ProcessStep(TimestampedModel):
    """Uma etapa do processo, descrita pelo P-S-D-T-E-R (`docs/metodologia-fde.md:106-110`).

    Os seis campos abaixo são **exatamente** as seis letras, nessa ordem. É a única parte do
    material que já é esquema de campos, e o valor dela está em não ser adaptada: renomear,
    juntar ou acrescentar uma sétima pergunta faria o levantamento da reunião deixar de casar com
    o formulário, e a conferência ("perguntei tudo?") deixaria de ser possível olhando a tela.
    """

    process = models.ForeignKey(Process, on_delete=models.CASCADE, related_name="steps")
    name = models.CharField(max_length=255)
    position = models.PositiveIntegerField(default=0)
    pessoas = models.TextField(blank=True, default="")  # P — quem faz
    sistema = models.TextField(blank=True, default="")  # S — onde faz
    dados = models.TextField(blank=True, default="")  # D — o que entra/sai
    tempo = models.TextField(blank=True, default="")  # T — quanto demora
    erro = models.TextField(blank=True, default="")  # E — o que pode dar errado
    retrabalho = models.TextField(blank=True, default="")  # R — o que acontece quando dá errado

    class Meta:
        # Mesma razão do `Process` acima: a classe troca de nome, a tabela fica (ADR 0052).
        db_table = "core_processoetapa"
        ordering = ["position", "id"]

    def __str__(self) -> str:
        return self.name


class Evidencia(TimestampedModel):
    """O que sustenta (ou não sustenta) cada achado do Discovery — a distinção central da FDD 039.

    A metodologia exige duas coisas que a prosa de uma ata não guarda: que o achado venha de uma
    das cinco formas de evidência, "nunca só entrevista" (`docs/metodologia-fde.md:112-115`), e que
    todo achado seja rotulado FATO / HIPÓTESE / DESCONHECIDO, porque **"nunca se apresenta
    hipótese como fato"** (`:117`). Guardar isso como campo é o que permite responder, depois da
    reunião, quanto do mapa é observação e quanto é suposição da casa.
    """

    class Forma(models.TextChoices):
        """As cinco formas de evidência (`docs/metodologia-fde.md:112-115`)."""

        ENTREVISTA = "entrevista", "Entrevista (o que dizem)"
        OBSERVACAO = "observacao", "Observação (o que fazem)"
        ARTEFATO = "artefato", "Artefato (planilha, PDF, croqui)"
        SISTEMA = "sistema", "Sistema (ERP, CRM, CAD, WhatsApp)"
        DADO = "dado", "Dado (volume, tempo, custo, erro)"

    class Rotulo(models.TextChoices):
        """Os três rótulos (`docs/metodologia-fde.md:117`).

        `DESCONHECIDO` é valor de primeira classe, e não ausência de valor: um Discovery que
        nomeia o que ainda não sabe está fazendo o trabalho, não deixando de fazê-lo — é a postura
        que o material pede ao sair da reunião (`:128-129`). Por isso ele é uma opção a escolher, e
        não o que sobra quando ninguém escolheu.
        """

        FATO = "fato", "Fato"
        HIPOTESE = "hipotese", "Hipótese"
        DESCONHECIDO = "desconhecido", "Desconhecido"

    process = models.ForeignKey(Process, on_delete=models.CASCADE, related_name="evidencias")
    # A etapa é opcional: nem todo achado é de uma etapa — "o volume é de 400 pedidos/mês" é do
    # processo inteiro. Quando vier preenchida, o `clean()` abaixo exige que seja deste processo.
    step = models.ForeignKey(
        ProcessStep, on_delete=models.SET_NULL, null=True, blank=True, related_name="evidencias"
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
        if self.step_id and self.step and self.step.process_id != self.process_id:
            raise ValidationError({"step": "A etapa deve pertencer ao mesmo processo."})


class Discovery(TimestampedModel):
    """O levantamento como **unidade**, e não como um punhado de reuniões soltas (FDD 045).

    A FDD 039 ancorou o mapa da operação no cliente, e fez isso certo: o processo sobrevive à
    venda que o descobriu. O que ficou faltando é o outro lado — **quando** aquele mapa foi
    levantado, por quem, com que recorte. `Process.source_project`/`source_meeting` respondem por
    uma origem só, e o mesmo processo revisitado no Discovery seguinte não tem onde ser
    registrado: a segunda passada ou sobrescreve a primeira em silêncio ou vira um processo
    duplicado.

    O Discovery é essa unidade. Pendura no `Project` porque é ele que dá o contrato e o prazo do
    levantamento — o **mapa** continua sendo do cliente, e é `ProcessObservation` que os liga sem
    prender um ao outro.

    O campo `engagement` da ontologia (ADR 0049) **não** entra aqui: o modelo `Engagement` é a
    Fase 2 e ainda não existe. Acrescentá-lo depois é aditivo.
    """

    class Status(models.TextChoices):
        PLANNED = "planned", "Planejado"
        RUNNING = "running", "Em andamento"
        COMPLETED = "completed", "Concluído"
        CANCELLED = "cancelled", "Cancelado"

    project = models.ForeignKey(Project, on_delete=models.CASCADE, related_name="discoveries")
    scope = models.TextField(blank=True, default="")
    status = models.CharField(max_length=16, choices=Status.choices, default=Status.PLANNED)
    started_at = models.DateField(null=True, blank=True)
    completed_at = models.DateField(null=True, blank=True)
    owner = models.ForeignKey(
        User, on_delete=models.SET_NULL, null=True, blank=True, related_name="discoveries"
    )

    class Meta:
        ordering = ["-started_at", "-id"]

    def __str__(self) -> str:
        return f"Discovery #{self.pk} — {self.get_status_display()}"

    def clean(self) -> None:
        if self.started_at and self.completed_at and self.completed_at < self.started_at:
            raise ValidationError(
                {"completed_at": "O fim do Discovery não pode ser anterior ao início."}
            )
        # Concluído sem data de conclusão seria um levantamento que a casa diz ter terminado sem
        # saber quando — e é a data que responde "o mapa é de quando?" na venda seguinte.
        if self.status == self.Status.COMPLETED and not self.completed_at:
            raise ValidationError(
                {"completed_at": "Um Discovery concluído precisa da data de conclusão."}
            )


class DiscoverySession(TimestampedModel):
    """Uma sessão do Discovery — a reunião, a visita, a leitura do sistema (FDD 045).

    `meeting` é opcional porque nem toda sessão é uma reunião registrada no portal: o consultor
    que passa a tarde no chão de fábrica levantou tanto quanto quem gravou uma call. Quando vier
    preenchida, o `clean()` exige que seja reunião do **mesmo projeto** do Discovery — sem isso a
    sessão alcançaria a transcrição de outro cliente por um campo opcional, que é a forma de
    vazamento que a `Evidencia.clean()` já fecha do outro lado.
    """

    discovery = models.ForeignKey(Discovery, on_delete=models.CASCADE, related_name="sessions")
    meeting = models.ForeignKey(
        Meeting, on_delete=models.SET_NULL, null=True, blank=True,
        related_name="discovery_sessions",
    )
    happened_at = models.DateTimeField()
    participants = models.TextField(blank=True, default="")
    # O artefato de narrativa (FDD 016) que saiu desta sessão, quando houve. `related_name="+"`
    # como no `Artifact.source_meeting`: ninguém navega de volta a partir dele.
    source_artifact = models.ForeignKey(
        "Artifact", on_delete=models.SET_NULL, null=True, blank=True, related_name="+"
    )
    transcript = models.TextField(blank=True, default="")

    class Meta:
        ordering = ["-happened_at", "-id"]

    def __str__(self) -> str:
        return f"Sessão de {self.happened_at:%d/%m/%Y}"

    def clean(self) -> None:
        reuniao = self.meeting if self.meeting_id else None
        if reuniao is not None and self.discovery_id:
            if reuniao.project_id != self.discovery.project_id:
                raise ValidationError(
                    {"meeting": "A reunião deve pertencer ao mesmo projeto do Discovery."}
                )


class ProcessObservation(TimestampedModel):
    """A observação de um processo **dentro de um Discovery** (FDD 045).

    Esta tabela é o que desfaz a proveniência única de `Process.source_project`/`source_meeting`:
    o mesmo processo observado em dois Discoveries são **duas linhas aqui**, e nenhuma sobrescreve
    a outra. É o registro que permite dizer "o AS-IS de faturamento foi levantado no Discovery
    Sprint e revisitado no PROVE" sem duplicar o processo nem perder a primeira leitura.
    """

    class Kind(models.TextChoices):
        INITIAL = "initial", "Primeira observação"
        REVISIT = "revisit", "Revisita"
        VALIDATION = "validation", "Validação"

    discovery = models.ForeignKey(
        Discovery, on_delete=models.CASCADE, related_name="process_observations"
    )
    process = models.ForeignKey(Process, on_delete=models.CASCADE, related_name="observations")
    observed_at = models.DateField()
    observation_type = models.CharField(max_length=16, choices=Kind.choices, default=Kind.INITIAL)
    source_session = models.ForeignKey(
        DiscoverySession, on_delete=models.SET_NULL, null=True, blank=True,
        related_name="process_observations",
    )

    class Meta:
        ordering = ["-observed_at", "-id"]

    def __str__(self) -> str:
        return f"{self.get_observation_type_display()} — {self.observed_at:%d/%m/%Y}"

    def clean(self) -> None:
        sessao = self.source_session if self.source_session_id else None
        if sessao is not None and sessao.discovery_id != self.discovery_id:
            raise ValidationError(
                {"source_session": "A sessão deve pertencer ao mesmo Discovery."}
            )


def hash_do_trecho(texto: str) -> str:
    """O carimbo de integridade do trecho de evidência (`Evidence.content_hash`).

    Função de módulo, e não método, porque a migração de backfill (`0054`) precisa da **mesma**
    conta e lá o modelo é a versão histórica de `apps.get_model`, que não tem o `save()`
    customizado. Duas implementações do mesmo hash divergiriam na primeira mudança, e o sintoma
    seria um `fact` parecendo adulterado sem que ninguém tivesse tocado nele.
    """
    texto = texto or ""
    return hashlib.sha256(texto.encode("utf-8")).hexdigest() if texto else ""


class Evidence(TimestampedModel):
    """O **dado bruto** que sustenta um achado — a metade "de onde veio" do split (FDD 045).

    A `Evidencia` da FDD 039 guarda três coisas numa linha só: a forma da fonte, a afirmação já
    interpretada e o rótulo epistemológico. Com isso, a hipótese e o trecho que a sustenta são o
    mesmo registro — e a proveniência se perde no instante em que alguém edita o texto. O split da
    ADR 0049 separa: aqui fica **o que foi dito ou observado**, sem conclusão; em `Finding` fica a
    afirmação que a casa extraiu daí.

    Uma evidência sem `raw_excerpt` e sem `reference` não é evidência — é uma linha dizendo que
    existe alguma coisa em algum lugar. O `clean()` exige um dos dois.

    Ancora na **conta** (`account`), e não no projeto, pelo mesmo argumento do `Process`: o que
    se observou sobre a operação de uma empresa sobrevive à venda que a descobriu.
    """

    class Kind(models.TextChoices):
        """As cinco formas de evidência (`docs/metodologia-fde.md:112-115`), em inglês canônico.

        Espelho um a um da `Evidencia.Forma`, e é essa correspondência que o backfill da migração
        `0054` traduz. Sem default, como lá: escolher a forma é um ato, e recebê-la por omissão
        não diz nada sobre de onde o dado veio.
        """

        INTERVIEW = "interview", "Entrevista (o que dizem)"
        OBSERVATION = "observation", "Observação (o que fazem)"
        ARTIFACT = "artifact", "Artefato (planilha, PDF, croqui)"
        SYSTEM = "system", "Sistema (ERP, CRM, CAD, WhatsApp)"
        DATA = "data", "Dado (volume, tempo, custo, erro)"

    # `account`, `process` e `step` são os nomes canônicos da ADR 0049, e desde a fatia 4 da issue
    # #67 os três apontam para a classe de nome certo — `Account`, `Process` e `ProcessStep`. O
    # renome da **tabela** dos três continua sendo a Fase 6.
    account = models.ForeignKey(Account, on_delete=models.CASCADE, related_name="evidence")
    discovery = models.ForeignKey(
        Discovery, on_delete=models.SET_NULL, null=True, blank=True, related_name="evidence"
    )
    process = models.ForeignKey(
        Process, on_delete=models.SET_NULL, null=True, blank=True, related_name="evidence"
    )
    step = models.ForeignKey(
        ProcessStep, on_delete=models.SET_NULL, null=True, blank=True, related_name="evidence"
    )
    kind = models.CharField(max_length=16, choices=Kind.choices)
    # O trecho **como foi dito ou observado**, sem interpretação. Conclusão da casa vai para
    # `Finding.statement`; misturar as duas aqui refaria a fusão que este modelo desfaz.
    raw_excerpt = models.TextField(blank=True, default="")
    # O localizador: URL da gravação, nome do arquivo, `00:14:32` da transcrição. É o que permite
    # voltar à fonte quando o trecho sozinho não basta.
    reference = models.CharField(max_length=500, blank=True, default="")
    source_session = models.ForeignKey(
        DiscoverySession, on_delete=models.SET_NULL, null=True, blank=True, related_name="evidence"
    )
    source_meeting = models.ForeignKey(
        Meeting, on_delete=models.SET_NULL, null=True, blank=True,
        related_name="structured_evidence",
    )
    captured_at = models.DateTimeField(default=timezone.now)
    captured_by = models.ForeignKey(
        User, on_delete=models.SET_NULL, null=True, blank=True, related_name="captured_evidence"
    )
    # **Metadado de integridade, e não enfeite.** Um `Finding` marcado como fato afirma que existe
    # um trecho que o sustenta; sem carimbo do trecho, editar o `raw_excerpt` depois muda o que a
    # casa alega ter observado sem deixar rastro nenhum. O hash é o que permite dizer, meses
    # depois, se o que sustenta o fato continua sendo o mesmo texto — a mesma ideia do
    # `Case` congelado (FDD 027), no tamanho de um campo.
    content_hash = models.CharField(max_length=64, blank=True, default="")
    # O ponteiro para a linha fundida de onde esta evidência veio no backfill (migração `0054`).
    # Preenchido **só** no dado migrado, e é a marca de "veio do modelo fundido": ali o
    # `raw_excerpt` pode carregar conclusão interpretada, porque era tudo o que existia.
    # `legacy_` é o prefixo de escape previsto pela ADR 0049 para mapeamento de backfill.
    legacy_evidencia = models.ForeignKey(
        Evidencia, on_delete=models.SET_NULL, null=True, blank=True, related_name="split_evidence"
    )

    class Meta:
        ordering = ["-captured_at", "-id"]

    def __str__(self) -> str:
        return f"{self.get_kind_display()} — {(self.raw_excerpt or self.reference)[:60]}"

    def clean(self) -> None:
        etapa = self.step if self.step_id else None
        if etapa is not None and self.process_id and etapa.process_id != self.process_id:
            raise ValidationError({"step": "A etapa deve pertencer ao mesmo processo."})
        # A mesma fronteira de conta da `Evidencia.clean()`, agora nas duas pontas: sem ela uma
        # evidência da conta A citaria o processo da conta B por um campo opcional.
        processo = self.process if self.process_id else None
        if processo is not None and processo.account_id != self.account_id:
            raise ValidationError({"process": "O processo deve pertencer à mesma conta."})
        if etapa is not None and etapa.process.account_id != self.account_id:
            raise ValidationError({"step": "A etapa deve pertencer à mesma conta."})
        # O terceiro campo opcional entra na **mesma** pergunta que os dois acima, e a simetria é
        # o ponto: dois vínculos validados contra a conta e um terceiro fora faria quem lesse isto
        # depois concluir que há uma razão para a exceção, e não há — é a mesma classe de vínculo
        # cruzado, com um hop a menos que `step`.
        discovery = self.discovery if self.discovery_id else None
        if discovery is not None and discovery.project.client_id != self.account_id:
            raise ValidationError({"discovery": "O Discovery deve pertencer à mesma conta."})
        # E, tendo os dois, eles precisam concordar — a mesma regra que a `ProcessObservation`
        # aplica sobre o par dela. Uma evidência apontando para a sessão de outro Discovery é uma
        # proveniência que se contradiz sozinha.
        sessao = self.source_session if self.source_session_id else None
        if sessao is not None and self.discovery_id and sessao.discovery_id != self.discovery_id:
            raise ValidationError(
                {"source_session": "A sessão deve pertencer ao mesmo Discovery."}
            )
        if not (self.raw_excerpt or "").strip() and not (self.reference or "").strip():
            raise ValidationError(
                "Uma evidência precisa do trecho bruto ou de um localizador da fonte."
            )

    def save(self, *args, **kwargs) -> None:  # type: ignore[no-untyped-def]
        # Recalculado a cada gravação em vez de "quando mudou": comparar com o banco custaria uma
        # leitura por save e ainda erraria no `bulk_create`, onde não há instância anterior. O
        # trecho vazio fica com hash vazio de propósito — `sha256("")` é uma constante, e gravá-la
        # faria "não há trecho" parecer um trecho carimbado.
        self.content_hash = hash_do_trecho(self.raw_excerpt)
        super().save(*args, **kwargs)


# Transições válidas do estado epistemológico de um achado (ADR 0049, `language-map` §6.8-9).
#
# Mesma forma de `ARTIFACT_TRANSITIONS`, e a assimetria é a decisão: de `fact` só se volta para
# `hypothesis`. Não porque rebaixar seja proibido — é assim que se corrige um erro, e um estado
# do qual não se sai transforma engano em verdade permanente —, mas porque ir de `fact` direto a
# `unknown` apagaria a diferença entre "estávamos errados" e "nunca soubemos". Quem se enganou
# rebaixa a hipótese e, se for o caso, desce de lá.
FINDING_TRANSITIONS: dict[str, set[str]] = {
    "hypothesis": {"fact", "unknown"},
    "unknown": {"hypothesis", "fact"},
    "fact": {"hypothesis"},
}


class Finding(TimestampedModel):
    """A afirmação que a casa extraiu da evidência — a metade "o que isso quer dizer" (FDD 045).

    É aqui que mora o rótulo que a metodologia exige (`docs/metodologia-fde.md:117`), agora com o
    nome canônico da ADR 0049: `epistemic_status` ∈ `fact` · `hypothesis` · `unknown`. E é aqui
    que a regra ganha dente, porque o achado deixou de ser a mesma linha do dado que o sustenta:
    **um `fact` aponta para a `Evidence` viva que o sustenta e para o humano que o promoveu.**

    `epistemic_status` tem default, ao contrário do `Evidencia.rotulo`, e a diferença é
    deliberada. Lá o default seria a casa escolhendo por quem não escolheu, num campo cujos três
    valores afirmam coisas diferentes. Aqui o default é `hypothesis`, o valor **menos**
    afirmativo: quem cria sem dizer nada não ganha um fato de graça, e subir daqui exige revisor e
    evidência. O erro por omissão cai sempre para o lado seguro, que é o oposto do que acontecia
    quando o rótulo tinha default de fato algum.
    """

    class EpistemicStatus(models.TextChoices):
        FACT = "fact", "Fato"
        HYPOTHESIS = "hypothesis", "Hipótese"
        UNKNOWN = "unknown", "Desconhecido"

    account = models.ForeignKey(Account, on_delete=models.CASCADE, related_name="findings")
    process = models.ForeignKey(
        Process, on_delete=models.SET_NULL, null=True, blank=True, related_name="findings"
    )
    step = models.ForeignKey(
        ProcessStep, on_delete=models.SET_NULL, null=True, blank=True, related_name="findings"
    )
    statement = models.TextField()
    epistemic_status = models.CharField(
        max_length=16, choices=EpistemicStatus.choices, default=EpistemicStatus.HYPOTHESIS
    )
    # 0–100 e opcional: confiança que ninguém mediu não vira zero, pelo motivo dos nove insumos do
    # `Process` — zero é uma afirmação, e "não estimamos" não é.
    confidence = models.PositiveSmallIntegerField(null=True, blank=True)
    reviewed_by = models.ForeignKey(
        User, on_delete=models.SET_NULL, null=True, blank=True, related_name="reviewed_findings"
    )
    reviewed_at = models.DateTimeField(null=True, blank=True)
    # M2M porque um achado costuma se apoiar em mais de uma fonte — e é justamente o "nunca só
    # entrevista" do material (`docs/metodologia-fde.md:112-115`) que só se consegue verificar
    # quando as fontes são contáveis.
    evidences = models.ManyToManyField(Evidence, blank=True, related_name="findings")
    legacy_evidencia = models.ForeignKey(
        Evidencia, on_delete=models.SET_NULL, null=True, blank=True, related_name="split_finding"
    )

    class Meta:
        ordering = ["-created_at", "-id"]

    def __str__(self) -> str:
        return f"{self.get_epistemic_status_display()} — {self.statement[:60]}"

    def clean(self) -> None:
        if self.confidence is not None and not 0 <= self.confidence <= 100:
            raise ValidationError({"confidence": "A confiança vai de 0 a 100."})
        etapa = self.step if self.step_id else None
        processo = self.process if self.process_id else None
        if processo is not None and processo.account_id != self.account_id:
            raise ValidationError({"process": "O processo deve pertencer à mesma conta."})
        if etapa is not None and etapa.process.account_id != self.account_id:
            raise ValidationError({"step": "A etapa deve pertencer à mesma conta."})
        if etapa is not None and self.process_id and etapa.process_id != self.process_id:
            raise ValidationError({"step": "A etapa deve pertencer ao mesmo processo."})
        # A metade da invariante §6.9 que dá para checar sem o M2M: **fato tem revisor**. A outra
        # metade — ao menos uma `Evidence` viva — vive no serializer, porque o vínculo M2M só
        # existe depois do save e um `clean()` que o consultasse recusaria toda criação.
        if self.epistemic_status == self.EpistemicStatus.FACT and not self.reviewed_by_id:
            raise ValidationError(
                {"reviewed_by": "Promover um achado a fato é ato humano: informe quem revisou."}
            )

    def save(self, *args, **kwargs) -> None:  # type: ignore[no-untyped-def]
        # Mesmo movimento do `Artifact.save()`: o carimbo de quando o estado mudou sai do próprio
        # estado, e não do corpo da requisição — quem promove não escolhe a data da promoção.
        if self.epistemic_status == self.EpistemicStatus.FACT and self.reviewed_at is None:
            self.reviewed_at = timezone.now()
        super().save(*args, **kwargs)


class PainPoint(TimestampedModel):
    """A dor observada na operação do cliente — o primeiro elo do PRIORITIZE (FDD 048).

    A Fase 3 deu ao levantamento o par `Evidence`/`Finding`: o trecho bruto e a afirmação que a
    casa extraiu dele. O que faltava é o passo seguinte da metodologia, que não é nem um nem
    outro: **onde dói**. Um achado ("o fechamento leva dois dias") não é uma dor; a dor é o custo
    que aquilo impõe, e é ela que se agrupa em oportunidade de melhoria.

    Ancora na **conta**, como `Process`, `Evidence` e `Finding`, e pelo mesmo motivo: o que se
    observou sobre a operação de uma empresa sobrevive à venda que a descobriu. `process` e `step`
    são opcionais porque nem toda dor cabe num processo mapeado — mas quando vierem, respondem à
    fronteira de conta como os vínculos opcionais da `Evidence`.
    """

    class ImpactType(models.TextChoices):
        FINANCIAL = "financial", "Financeiro"
        OPERATIONAL = "operational", "Operacional"
        EXPERIENCE = "experience", "Experiência"
        RISK = "risk", "Risco"

    class Status(models.TextChoices):
        OBSERVED = "observed", "Observado"
        CONFIRMED = "confirmed", "Confirmado"
        DISCARDED = "discarded", "Descartado"

    account = models.ForeignKey(Account, on_delete=models.CASCADE, related_name="pain_points")
    process = models.ForeignKey(
        Process, on_delete=models.SET_NULL, null=True, blank=True, related_name="pain_points"
    )
    step = models.ForeignKey(
        ProcessStep, on_delete=models.SET_NULL, null=True, blank=True, related_name="pain_points"
    )
    title = models.CharField(max_length=200)
    description = models.TextField(blank=True, default="")
    impact_type = models.CharField(max_length=16, choices=ImpactType.choices)
    # **Nulo é "não estimado", e zero é "estimamos e não custa nada".** A distinção é a razão de o
    # campo ser nulável em vez de `default=0`, e é a mesma de `DigitalEmployee.kpi_baseline` e do
    # `nao_apurado` de `process.custo_do_estado_atual`: um total exibido sem ela vira "custo zero"
    # na leitura rápida, e a casa passa a afirmar ao cliente o oposto do que sabe.
    impact_estimate = models.DecimalField(max_digits=12, decimal_places=2, null=True, blank=True)
    # M2M para o que sustenta a dor. É o mesmo desenho de `Finding.evidences`, um nível acima: a
    # dor confirmada aponta para os achados que a sustentam, e "confirmado sem achado vivo" é
    # recusado — a invariante mora no serializer porque o M2M só existe depois do save.
    findings = models.ManyToManyField(Finding, blank=True, related_name="pain_points")
    status = models.CharField(max_length=16, choices=Status.choices, default=Status.OBSERVED)

    class Meta:
        ordering = ["-created_at", "-id"]

    def __str__(self) -> str:
        return f"{self.get_impact_type_display()} — {self.title[:60]}"

    def clean(self) -> None:
        etapa = self.step if self.step_id else None
        processo = self.process if self.process_id else None
        if processo is not None and processo.account_id != self.account_id:
            raise ValidationError({"process": "O processo deve pertencer à mesma conta."})
        if etapa is not None and etapa.process.account_id != self.account_id:
            raise ValidationError({"step": "A etapa deve pertencer à mesma conta."})
        if etapa is not None and self.process_id and etapa.process_id != self.process_id:
            raise ValidationError({"step": "A etapa deve pertencer ao mesmo processo."})
        # A invariante de `confirmed` **não cabe aqui**, e é a mesma razão do `Finding`: ela
        # pergunta pelo M2M, que só existe depois do save — um `clean()` que o consultasse
        # recusaria toda criação. A metade que dá para cobrar sem o M2M é zero, então ela vive
        # inteira no serializer, mais a terceira metade no arquivamento do achado (FDD 048).


class ImprovementOpportunity(TimestampedModel):
    """O agrupamento de dores em algo sobre o que se pode decidir — o Opportunity Map (FDD 048).

    **Não é venda, e não referencia `PipelineStage` em campo nenhum.** O mapa de linguagem §2
    manda nunca chamá-la de Commercial Opportunity nem de Projeto, e a §5 bane `Opportunity` sem
    qualificador exatamente porque as duas coisas colidiam: uma é receita a fechar, a outra é
    melhoria operacional a priorizar. Um campo de etapa de pipeline aqui traria a primeira para
    dentro da segunda, e o funil da casa passaria a somar melhorias que ninguém vendeu.

    `engagement` é opcional porque a oportunidade nasce do levantamento, que é da **conta** — e
    nem toda conta tem mais de um mandato vivo para escolher. Quando vier preenchido, precisa ser
    mandato da mesma conta, pela regra que `Project.clean()` já aplica sobre a mesma dupla.
    """

    class Status(models.TextChoices):
        OPEN = "open", "Aberta"
        ASSESSING = "assessing", "Em avaliação"
        PRIORITIZED = "prioritized", "Priorizada"
        DISCARDED = "discarded", "Descartada"

    account = models.ForeignKey(
        Account, on_delete=models.CASCADE, related_name="improvement_opportunities"
    )
    engagement = models.ForeignKey(
        Engagement, on_delete=models.SET_NULL, null=True, blank=True,
        related_name="improvement_opportunities",
    )
    title = models.CharField(max_length=200)
    desired_change = models.TextField(blank=True, default="")
    impact_hypothesis = models.TextField(blank=True, default="")
    pain_points = models.ManyToManyField(
        PainPoint, blank=True, related_name="improvement_opportunities"
    )
    status = models.CharField(max_length=16, choices=Status.choices, default=Status.OPEN)

    class Meta:
        ordering = ["-created_at", "-id"]

    def __str__(self) -> str:
        return self.title

    def clean(self) -> None:
        # A mesma linha que mantém `Project.client` honesto contra `engagement.account`: dois
        # caminhos chegam ao dono, e nada além desta guarda impede que digam coisas diferentes.
        engagement = self.engagement if self.engagement_id else None
        if engagement is not None and engagement.account_id != self.account_id:
            raise ValidationError(
                {"engagement": "O engajamento deve pertencer à mesma conta da oportunidade."}
            )

    @property
    def current_assessment(self) -> PriorityAssessment | None:
        """A avaliação **vigente**: a de maior `version` que não foi arquivada.

        Um lugar só, no espírito de `Project.current_phase` e de `visible_to` (ADR 0010).
        Reexpressar "vigente" numa segunda query é o começo de duas definições do mesmo fato — e
        elas divergem em silêncio, porque nada fica vermelho quando a tela mostra a v2 e o
        recomendador continua lendo a v1.

        **O recorte é em Python, e não num `.filter()`, de propósito.** Um `.filter()` no manager
        emite consulta nova toda vez e **ignora** o `prefetch_related("assessments")` de quem
        chamou — o prefetch fica lá parecendo que resolve e não resolvendo nada, que é a pior das
        duas opções: custo de N+1 com aparência de custo resolvido. Com `.all()`, quem prefetchou
        paga uma consulta para a lista inteira (é o caso de `priority.ranking_da_conta`) e quem
        não prefetchou paga a mesma consulta que pagaria antes. A definição de "vigente" continua
        aqui, e só aqui.
        """
        vivas = [
            avaliacao for avaliacao in self.assessments.all() if avaliacao.archived_at is None
        ]
        return max(vivas, key=lambda avaliacao: (avaliacao.version, avaliacao.pk), default=None)


class PriorityAssessment(TimestampedModel):
    """A avaliação que produz o Opportunity Score — **imutável, e versionada** (FDD 048, ADR 0054).

    Cinco dimensões de 1 a 5, os pesos que foram usados, a fórmula que os nomeia e o score que
    saiu dali. Repriorizar **cria a versão seguinte**; não existe editar. Uma avaliação que se
    reescreve apaga o critério anterior, e com ele a única resposta possível para "por que este
    item subiu?" — que é a pergunta que a versão existe para responder.

    A imutabilidade é cobrada na **rota** (`PriorityAssessmentViewSet` não expõe `PUT`/`PATCH`) e
    não no `save()`, porque arquivar e restaurar são gravações legítimas desta mesma linha
    (`TimestampedModel.archive()`), e um `save()` que recusasse toda atualização recusaria as
    duas junto.

    `weights` guarda a **cópia** dos pesos, não uma referência a `priority.FORMULAS`: mudar o
    catálogo amanhã não pode alterar o score de uma avaliação de ontem. Ver a docstring de
    `apps/core/priority.py`.
    """

    improvement_opportunity = models.ForeignKey(
        ImprovementOpportunity, on_delete=models.CASCADE, related_name="assessments"
    )
    # Atribuída pelo `save()`, nunca pelo corpo da requisição — ver a docstring dele.
    version = models.PositiveIntegerField()
    impact = models.PositiveSmallIntegerField(
        validators=[MinValueValidator(MENOR_NOTA), MaxValueValidator(MAIOR_NOTA)]
    )
    evidence_strength = models.PositiveSmallIntegerField(
        validators=[MinValueValidator(MENOR_NOTA), MaxValueValidator(MAIOR_NOTA)]
    )
    feasibility = models.PositiveSmallIntegerField(
        validators=[MinValueValidator(MENOR_NOTA), MaxValueValidator(MAIOR_NOTA)]
    )
    time_to_value = models.PositiveSmallIntegerField(
        validators=[MinValueValidator(MENOR_NOTA), MaxValueValidator(MAIOR_NOTA)]
    )
    economics = models.PositiveSmallIntegerField(
        validators=[MinValueValidator(MENOR_NOTA), MaxValueValidator(MAIOR_NOTA)]
    )
    formula_key = models.CharField(max_length=24, default=FORMULA_PADRAO)
    weights = models.JSONField(default=dict, blank=True)
    # Derivado das cinco dimensões pelos pesos acima; escrito pelo `save()` e nunca recebido do
    # cliente. Um score que o corpo pudesse informar não seria a fórmula — seria uma opinião com
    # aparência de cálculo.
    score = models.DecimalField(max_digits=5, decimal_places=2, default=Decimal("0"))
    rationale = models.TextField(blank=True, default="")
    assessed_by = models.ForeignKey(
        User, on_delete=models.SET_NULL, null=True, blank=True, related_name="priority_assessments"
    )

    class Meta:
        ordering = ["-version", "-id"]
        constraints = [
            # Sem condição de arquivamento, de propósito: a versão arquivada **continua ocupando**
            # o seu número. Reaproveitá-lo faria duas avaliações diferentes se chamarem "v2", e a
            # comparação com a semana passada passaria a depender de qual delas alguém abriu.
            models.UniqueConstraint(
                fields=["improvement_opportunity", "version"],
                name="unique_priority_assessment_version",
            ),
        ]

    def __str__(self) -> str:
        return f"v{self.version} — {self.score}"

    def clean(self) -> None:
        if self.formula_key not in FORMULAS:
            raise ValidationError({"formula_key": "Fórmula desconhecida."})
        for dimensao in DIMENSOES:
            nota = getattr(self, dimensao)
            if nota is not None and not MENOR_NOTA <= nota <= MAIOR_NOTA:
                raise ValidationError({dimensao: f"A nota vai de {MENOR_NOTA} a {MAIOR_NOTA}."})

    def save(self, *args, **kwargs) -> None:  # type: ignore[no-untyped-def]
        """Carimba `version`, `weights` e `score` na criação — e só nela.

        **`select_for_update` sobre a oportunidade**, pela razão exata do `convert-to-project`
        (ADR 0050): sem a trava, duas requisições concorrentes leem `max(version)` ao mesmo tempo,
        escrevem a mesma versão e a constraint estoura como 500 — um erro de servidor no lugar de
        uma sequência. A trava serializa as duas, e a segunda lê a versão que a primeira gravou.

        Os pesos são copiados aqui, e não no serializer, pelo motivo de `CommercialOpportunity.clean()`
        e `Project.clean()`: shell, admin e migração não passam por rota, e um score gravado sem
        pesos é um número que ninguém consegue reproduzir.
        """
        if self._state.adding:
            if not self.weights:
                self.weights = pesos_da_formula(self.formula_key)
            with transaction.atomic():
                ImprovementOpportunity.objects.select_for_update().get(
                    pk=self.improvement_opportunity_id
                )
                if not self.version:
                    ultima = PriorityAssessment.objects.filter(
                        improvement_opportunity_id=self.improvement_opportunity_id
                    ).aggregate(models.Max("version"))["version__max"]
                    self.version = (ultima or 0) + 1
                self.score = calcular_score(
                    {dimensao: getattr(self, dimensao) for dimensao in DIMENSOES}, self.weights
                )
                super().save(*args, **kwargs)
            return
        super().save(*args, **kwargs)


class SolutionHypothesis(TimestampedModel):
    """A hipótese de solução para uma oportunidade priorizada (FDD 048).

    **Hipóteses concorrentes são o estado normal**: a mesma dor costuma admitir automação,
    redesenho de processo e mudança de política, e escolher antes de escrever as três é decidir
    sem alternativa. O que não pode haver é **duas escolhidas ao mesmo tempo** — isso não é
    concorrência, é contradição —, e a constraint parcial abaixo é o que impede.

    Não é `DigitalEmployee` nem `SolutionHypothesis` virando escopo: o mapa de linguagem §2 manda
    nunca chamá-la de Solução, Proposta ou Escopo. Ela é a aposta que ainda vai ao gate de
    viabilidade, que é a Fase 5.
    """

    class Status(models.TextChoices):
        PROPOSED = "proposed", "Proposta"
        CHOSEN = "chosen", "Escolhida"
        DISCARDED = "discarded", "Descartada"

    improvement_opportunity = models.ForeignKey(
        ImprovementOpportunity, on_delete=models.CASCADE, related_name="hypotheses"
    )
    statement = models.TextField()
    intervention = models.TextField(blank=True, default="")
    assumptions = models.TextField(blank=True, default="")
    expected_effect = models.TextField(blank=True, default="")
    status = models.CharField(max_length=16, choices=Status.choices, default=Status.PROPOSED)

    class Meta:
        ordering = ["-created_at", "-id"]
        constraints = [
            # Condicional ao arquivamento, como `unique_active_project_member`: uma escolha
            # desfeita e arquivada não pode travar a escolha seguinte.
            models.UniqueConstraint(
                fields=["improvement_opportunity"],
                condition=Q(status="chosen", archived_at__isnull=True),
                name="unique_chosen_solution_hypothesis",
            ),
        ]

    def __str__(self) -> str:
        return f"{self.get_status_display()} — {self.statement[:60]}"


class Service(TimestampedModel):
    """Catálogo de serviços e, quando `tier` estiver preenchido, os níveis de produto.

    Os degraus da escada FDE são registros semeados com `tier`; serviços avulsos ficam com
    `tier` vazio.

    Na leitura FDE (`docs/metodologia-fde.md`, ADR 0030), os níveis **são** os degraus
    comerciais da escada, um por fase vendável:

    - `QUALIFICATION_CALL` — a porta gratuita, antes do Discover. Termina em avançar ou NO-GO.
    - `DISCOVERY_SPRINT` — o Discovery pago (R$ 3.000 de tabela desde a ADR 0053), fechando em
      Executive Readout com o custo do estado atual e o ranking por Opportunity Score.
    - `FEASIBILITY` — a Technical Feasibility (T.O.E.). O **gate** T.O.E. acontece em 100% dos
      casos e sai no readout do Discovery, sem cobrança; o **degrau** só existe quando responder
      "conseguimos fazer?" exige medir uma amostra de dado real ainda não vista (ADR 0053).
      Termina em decision gate GO / CONDITIONAL GO / REDESIGN / NO-GO.
    - `PROVE` — produção controlada com baseline e critérios de sucesso definidos **antes** de
      construir, e decision gate SCALE / ITERATE / STOP no fim.
    - `SCALE` — a captura de valor depois do PROVE aprovado.
    - `TRANSFORMATION` — a parceria contínua (OPTIMIZE). **É recorrente mensal, e o modelo
      ainda não sabe disso**: `list_price` é valor único, então o pipeline soma um mês como se
      fosse o contrato inteiro. Acrescentar recorrência é ADR própria; até lá, quem vende este
      degrau confere o valor na mão.

    PRIORITIZE não tem tier de propósito: não se fatura separado — é o entregável do Discovery
    Sprint (o ranking por Opportunity Score), e um degrau que ninguém compra seria uma coluna
    que nunca enche. `DISCOVERY_ASSESSMENT` **saiu** pelo mesmo argumento (ADR 0053, migração
    `0064`): era a porta gratuita do founding client, e com o Design Partner cobrindo a entrada
    não sobrou trabalho para ele fazer.
    """

    class Category(models.TextChoices):
        """O que a oferta faz pela casa — e é o que separa a escada comercial da porta (D4).

        `acquisition` é oferta de **aquisição**: existe para descobrir se há venda, não para ser
        vendida. A Qualification Call é a única hoje. Ela nunca gera `CommercialOpportunity`
        nem `Project`,
        e é essa categoria — não o preço zero — que carrega a regra: o Design Partner recebe
        Discovery, gate e PROVE sem cobrar (ADR 0053), e aqueles continuam sendo degraus
        vendáveis — o subsídio mora no `estimated_value` da oportunidade, não na categoria.
        """

        ACQUISITION = "acquisition", "Aquisição"
        COMMERCIAL = "commercial", "Comercial"

    class Tier(models.TextChoices):
        QUALIFICATION_CALL = "qualification_call", "Qualification Call"
        DISCOVERY_SPRINT = "discovery_sprint", "Discovery Sprint"
        FEASIBILITY = "feasibility", "Technical Feasibility (T.O.E.)"
        PROVE = "prove", "PROVE (piloto)"
        SCALE = "scale", "Scale"
        TRANSFORMATION = "transformation", "Transformation Partnership"

    name = models.CharField(max_length=120)
    active = models.BooleanField(default=True)
    tier = models.CharField(max_length=32, choices=Tier.choices, blank=True, default="")
    # `commercial` por padrão: serviço novo é para vender, e a exceção é a porta de aquisição.
    category = models.CharField(
        max_length=16, choices=Category.choices, default=Category.COMMERCIAL
    )
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
    commercial_opportunity = models.ForeignKey(
        CommercialOpportunity, on_delete=models.SET_NULL, null=True, blank=True
    )
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

    class CanonicalStage(models.TextChoices):
        """A jornada canônica de entrega — o vocabulário FDE (ADR 0030, ADR 0047, FDD 042).

        `Discover → Prioritize → [Feasibility] → Prove → Scale → Optimize`. É uma **classificação**
        opcional da fase configurável, não um segundo modelo de fase: mapeia o vocabulário que o
        admin edita (`Welcome`, `Launch Session`, …) sobre a escada canônica, para que a linha do
        tempo interna do Pulse fale a mesma língua entre projetos com jornadas nomeadas diferentes.
        `feasibility` é membro explícito e opcional: uma jornada que não a atravessa simplesmente
        não tem fase mapeada nela — é assim que a optionalidade fica *modelada*, não convencionada.
        Em branco é legítimo (a fase operacional Biahflow sem equivalente FDE, como `Activation`).
        """

        DISCOVER = "discover", "Discover"
        PRIORITIZE = "prioritize", "Prioritize"
        FEASIBILITY = "feasibility", "Feasibility"
        PROVE = "prove", "Prove"
        SCALE = "scale", "Scale"
        OPTIMIZE = "optimize", "Optimize"

    canonical_stage = models.CharField(
        max_length=16, choices=CanonicalStage.choices, blank=True, default=""
    )

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

    class GateDecision(models.TextChoices):
        """As quatro saídas do gate de **Feasibility** (FDD 033, `docs/metodologia-fde.md`).

        A pergunta que elas respondem é *"a tecnologia consegue fazer a tarefa?"*. São exatamente
        quatro porque a metodologia diz quatro, e o valor delas está em *não* colapsarem: "seguiu
        com ressalvas" e "seguiu" acabam no mesmo lugar da jornada, mas só um dos dois deixa
        dívida nomeada para monitorar.

        Até a ADR 0053 este era o vocabulário de **todo** gate, e o repositório se contradizia
        sozinho: `kickoff.KICKOFF_TEMPLATES["prove"]` já mandava registrar SCALE / ITERATE / STOP
        numa fase em que só estes quatro valores eram aceitos.
        """

        GO = "go", "GO"
        CONDITIONAL_GO = "conditional_go", "CONDITIONAL GO"
        REDESIGN = "redesign", "REDESIGN"
        NO_GO = "no_go", "NO-GO"

    class ProveDecision(models.TextChoices):
        """As três saídas do gate de **PROVE** (ADR 0053).

        A pergunta é outra — *"funcionou em produção controlada?"* —, e pergunta diferente merece
        saídas diferentes. Cada uma cai num dos mesmos três efeitos das quatro acima: `SCALE`
        conclui e avança (como GO), `ITERATE` reabre a fase anterior (como REDESIGN) e `STOP`
        registra e para (como NO-GO).
        """

        SCALE = "scale", "SCALE"
        ITERATE = "iterate", "ITERATE"
        STOP = "stop", "STOP"

    # As sete saídas num conjunto só: é o que a coluna aceita, o que o corpo da action publica no
    # esquema (`GateDecisionEnum`, override em `config/settings.py`) e o que `decisoes_do_gate`
    # estreita por fase. Uma segunda soma escrita à mão em qualquer um desses três lugares seria a
    # que esquece o valor novo — e um valor fora do enum grava sem erro num `CharField`.
    DECISOES_DO_GATE = GateDecision.choices + ProveDecision.choices

    class WaitingParty(models.TextChoices):
        """Quem/o quê a fase ativa está esperando, para a linha do tempo interna (FDD 042).

        Torna o bloqueio legível sem abrir a nota crua: a equipe classifica de quem depende a
        fase parada. `engineering` é *classificação de delivery* — "estamos esperando engenharia"
        —, não o estado de execução de engenharia em si, que é do GitHub (ADR 0040, issue #41): a
        fronteira fica limpa, e nada aqui equaciona `PR merged` a `DONE`. `human_gate` é o caso em
        que o que falta é uma decisão humana (o decision gate da FDD 033). Em branco = fluindo.
        """

        BIAHFLOW = "biahflow", "Biahflow"
        CLIENT = "client", "Cliente"
        ENGINEERING = "engineering", "Engenharia"
        EXTERNAL = "external", "Dependência externa"
        HUMAN_GATE = "human_gate", "Human Gate"

    project = models.ForeignKey(Project, on_delete=models.CASCADE, related_name="phases")
    phase = models.ForeignKey(JourneyPhase, on_delete=models.PROTECT, related_name="project_phases")
    status = models.CharField(max_length=16, choices=Status.choices, default=Status.LOCKED)
    started_at = models.DateTimeField(null=True, blank=True)
    completed_at = models.DateTimeField(null=True, blank=True)
    target_date = models.DateField(null=True, blank=True)  # a "prevista" mostrada na UI
    # O gate decidido, e o porquê. Em branco enquanto ninguém decidiu — e é esse branco que
    # `journey.advance_phase` recusa quando a fase do template exige gate. As notas não são
    # opcionais de fato nas saídas que não são de continuidade: as ressalvas do CONDITIONAL GO e
    # o motivo do REDESIGN/NO-GO/ITERATE/STOP são a única coisa que atravessa o tempo (FDD 033).
    # O nome canônico do D7 é do próprio campo desde a ADR 0052 — a propriedade-alias que
    # `aliases.md` prescrevia perdeu o objeto no momento em que o campo passou a se chamar como
    # ela. O nome antigo sobrevive só como **chave de payload** no serializer, com data de morte
    # na `/api/v2/`; nada no domínio o lê.
    #
    # **Um campo só, com os dois vocabulários** (ADR 0053). O fato é um só — "a decisão registrada
    # no gate desta fase" —, e duas colunas seriam duas definições dele, com a segunda divergindo
    # da primeira em silêncio. Quem estreita as sete para as que valem naquela fase é
    # `decisoes_do_gate`, a partir do `canonical_stage` do template.
    gate_decision = models.CharField(
        max_length=16, choices=DECISOES_DO_GATE, blank=True, default=""
    )
    gate_notes = models.TextField(blank=True, default="")
    # Concluir com checklist incompleta é legítimo — o que não é legítimo é fazê-lo em silêncio.
    # Preenchido, este campo destrava a conclusão e fica como registro de quem decidiu pular o
    # quality gate e por quê.
    checklist_waiver = models.TextField(blank=True, default="")
    # Quem a fase ativa espera, e a nota do bloqueio/decisão pendente (FDD 042). Read-only no
    # serializer e escrito só pela action `set-waiting`, pelo mesmo motivo do `gate_decision`: a
    # mudança precisa deixar rastro (um `PhaseEvent` com autor), e um PATCH direto gravaria o
    # estado sem o registro de quem e por quê.
    waiting_party = models.CharField(
        max_length=16, choices=WaitingParty.choices, blank=True, default=""
    )
    blocker_note = models.TextField(blank=True, default="")

    class Meta:
        ordering = ["phase__position", "id"]
        constraints = [
            models.UniqueConstraint(fields=["project", "phase"], name="unique_project_phase")
        ]

    def __str__(self) -> str:
        return f"{self.project_id} · {self.phase.name}"

    @property
    def situation(self) -> str:
        """Estado semântico derivado, determinístico (FDD 042; FinOps: sem LLM).

        Colapsa `status` + `gate_decision` + `waiting_party` no vocabulário que a linha do tempo
        pinta: `completed`, `cancelled`, `replanned`, `waiting_decision`, `blocked`, `active`,
        `pending`. É a fonte única da variante de selo — a tela mapeia *situação → variante*, nunca
        recalcula a regra. Puro: não toca no banco.
        """
        # As saídas dos dois vocabulários caem nos mesmos três efeitos (ADR 0053): o `STOP` do
        # PROVE cancela como o `NO-GO` da Feasibility, e o `ITERATE` replaneja como o `REDESIGN`.
        if self.gate_decision in {self.GateDecision.NO_GO, self.ProveDecision.STOP}:
            return "cancelled"
        if self.status == self.Status.DONE:
            return "completed"
        if self.status == self.Status.LOCKED:
            # Trancada por um REDESIGN/ITERATE (guarda a decisão) é "replanejada"; trancada e
            # ainda intocada é só "pendente" — fase futura da jornada, não um alerta.
            reabriu = {self.GateDecision.REDESIGN, self.ProveDecision.ITERATE}
            return "replanned" if self.gate_decision in reabriu else "pending"
        # A partir daqui a fase está ativa.
        awaiting_gate = self.phase.requires_gate and not self.gate_decision
        if self.waiting_party == self.WaitingParty.HUMAN_GATE or awaiting_gate:
            return "waiting_decision"
        if self.waiting_party:
            return "blocked"
        return "active"


def decisoes_do_gate(canonical_stage: str) -> type[models.TextChoices]:
    """O vocabulário do gate desta fase (ADR 0053).

    **Deriva do `canonical_stage`, e não de um campo novo no template.** Um
    `JourneyPhase.gate_vocabulary` seria uma segunda expressão do mesmo fato: quem diz que o gate
    do PROVE é SCALE / ITERATE / STOP é a metodologia, e `canonical_stage` já é exatamente "qual
    fase FDE é esta". Duas fontes para o mesmo fato divergem na primeira fase configurada pela
    tela sem ninguém perceber.

    **Uma função só, e todo mundo a consome.** A alternativa — `if canonical_stage == "prove"`
    espalhado por `journey`, `views` e a tela — é a que esquece o quinto lugar.

    Fase que exige gate mas está **sem** `canonical_stage` recebe as quatro da Feasibility: é o
    comportamento de todo gate anterior a esta ADR (nenhuma fase semeada tem a classificação
    preenchida, migração `0015`), e as quatro são as saídas de propósito geral — GO/NO-GO
    respondem a qualquer gate, SCALE/STOP só fazem sentido depois de um piloto rodando.
    """
    if canonical_stage == JourneyPhase.CanonicalStage.PROVE:
        return ProjectPhase.ProveDecision
    return ProjectPhase.GateDecision


# Cada saída dos dois vocabulários cai em **um** de três efeitos sobre a jornada (ADR 0053):
# conclui e avança, reabre a fase anterior, ou registra e para. É a tabela que deixa
# `journey.apply_gate` ramificar por *efeito* em vez de por valor literal — sem ela, cada saída
# nova obrigaria a caçar todos os `if decision == GO or decision == CONDITIONAL_GO` do módulo, e
# o que ficasse para trás falharia em silêncio (o gate gravado sem a consequência dele).
CONCLUEM_E_AVANCAM = frozenset(
    {
        ProjectPhase.GateDecision.GO,
        ProjectPhase.GateDecision.CONDITIONAL_GO,
        ProjectPhase.ProveDecision.SCALE,
    }
)
REABREM_A_ANTERIOR = frozenset(
    {ProjectPhase.GateDecision.REDESIGN, ProjectPhase.ProveDecision.ITERATE}
)
REGISTRAM_E_PARAM = frozenset(
    {ProjectPhase.GateDecision.NO_GO, ProjectPhase.ProveDecision.STOP}
)


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


class PhaseEvent(models.Model):
    """Histórico **append-only** da jornada de um projeto (FDD 042, ADR 0047).

    O `ProjectPhase` carrega o **estado corrente**; ele não guarda a *sequência* de como se chegou
    ali — e um REDESIGN chega a apagar `completed_at` e `gate_decision` da fase que reabre (FDD
    033), de propósito, porque "concluída em" é estado corrente. O que se perdia com isso era a
    auditoria: *por que* e *quando* a jornada voltou. Este modelo é o registro que sobrevive — uma
    linha por transição/decisão/bloqueio, com carimbo, autor e proveniência, nunca editada nem
    apagada. Não tem viewset de escrita: só `journey.py` cria evento, e a leitura sai pela linha
    do tempo do projeto.

    Determinístico, sem LLM (FinOps): ordenação, `from`/`to` e proveniência saem de campos
    explícitos. `phase_name` é *snapshot* — a auditoria continua legível se a fase for renomeada.
    """

    class Kind(models.TextChoices):
        STARTED = "started", "Fase iniciada"
        COMPLETED = "completed", "Fase concluída"
        REOPENED = "reopened", "Fase reaberta"
        LOCKED_BY_REDESIGN = "locked_by_redesign", "Fase trancada por REDESIGN"
        GATE_RECORDED = "gate_recorded", "Decision gate registrado"
        WAITING_SET = "waiting_set", "Aguardando definido"
        WAITING_CLEARED = "waiting_cleared", "Aguardando resolvido"

    class Source(models.TextChoices):
        USER = "user", "Ação de pessoa"
        SYSTEM = "system", "Automático"

    project = models.ForeignKey(Project, on_delete=models.CASCADE, related_name="phase_events")
    # `SET_NULL`: o evento sobrevive mesmo se a fase-instância for arquivada/removida — é
    # histórico, e o `phase_name` abaixo guarda o rótulo de qualquer forma.
    project_phase = models.ForeignKey(
        ProjectPhase, on_delete=models.SET_NULL, null=True, blank=True, related_name="events"
    )
    phase_name = models.CharField(max_length=80, blank=True, default="")
    kind = models.CharField(max_length=24, choices=Kind.choices)
    from_status = models.CharField(max_length=16, blank=True, default="")
    to_status = models.CharField(max_length=16, blank=True, default="")
    gate_decision = models.CharField(max_length=16, blank=True, default="")
    waiting_party = models.CharField(max_length=16, blank=True, default="")
    note = models.TextField(blank=True, default="")
    actor = models.ForeignKey(
        User, on_delete=models.SET_NULL, null=True, blank=True, related_name="+"
    )
    source = models.CharField(max_length=8, choices=Source.choices, default=Source.SYSTEM)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at", "-id"]

    def __str__(self) -> str:
        return f"{self.project_id} · {self.phase_name} · {self.kind}"


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
    commercial_opportunity = models.ForeignKey(
        CommercialOpportunity, on_delete=models.SET_NULL, null=True, blank=True,
        related_name="artifacts",
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
        links = [self.commercial_opportunity_id, self.project_id]
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
    # derrotaria o ponto — é a mesma escolha de `Project.client` e de
    # `Project.originating_commercial_opportunity`.
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
    deveria entrar: `Service.list_price` e `CommercialOpportunity.estimated_value` são **preço**,
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

    account = models.ForeignKey(Account, on_delete=models.PROTECT, related_name="invoices")
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
        return f"{self.number or 'rascunho'} — {self.account.name}"

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

    **`account` é desnormalizado de propósito.** O teto de frequência é por cliente somando *todas*
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
    account = models.ForeignKey(Account, on_delete=models.PROTECT, related_name="cobrancas")
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
        indexes = [models.Index(fields=["account", "sent_on"])]
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
        return f"{self.get_degrau_display()} — {self.account.name} ({self.sent_on})"


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
    account = models.ForeignKey(
        Account, on_delete=models.PROTECT, null=True, blank=True, related_name="suspensoes"
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
        alvo = self.invoice or self.account
        return f"Suspensão até {self.until} — {alvo}"

    def clean(self) -> None:
        links = [self.invoice_id, self.account_id]
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

    **Não tem FK para `Project`, `Account` nem `Document`, e é a invariante em forma de esquema:**
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
