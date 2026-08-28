from datetime import timedelta
from decimal import Decimal

import factory
from django.utils import timezone

from apps.core.models import (
    Activity,
    Artifact,
    Client,
    EngineeringHandoff,
    Evidencia,
    GithubDeliveryProjection,
    Invoice,
    Lead,
    Meeting,
    Opportunity,
    PipelineStage,
    Processo,
    ProcessoEtapa,
    Project,
    ProjectMember,
    Qualification,
    Service,
    User,
)


class UserFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = User
        skip_postgeneration_save = True

    username = factory.Sequence(lambda n: f"user{n}")
    email = factory.LazyAttribute(lambda obj: f"{obj.username}@example.test")
    role = User.Role.ADMIN

    @factory.post_generation
    def password(obj, create, extracted, **kwargs):
        obj.set_password(extracted or "Segura123!senha")
        if create:
            obj.save()


class ClientFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = Client

    name = factory.Sequence(lambda n: f"Cliente {n}")
    owner = factory.SubFactory(UserFactory)


class PipelineStageFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = PipelineStage

    name = factory.Sequence(lambda n: f"Etapa {n}")
    kind = PipelineStage.Kind.OPEN
    position = factory.Sequence(lambda n: n + 100)


class ServiceFactory(factory.django.DjangoModelFactory):
    """Serviço avulso por padrão. Os três níveis vêm semeados pela migração 0020 —
    busque-os com `Service.objects.get(tier=...)` em vez de criar duplicatas."""

    class Meta:
        model = Service

    name = factory.Sequence(lambda n: f"Serviço {n}")
    tier = ""


class OpportunityFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = Opportunity

    client = factory.SubFactory(ClientFactory)
    title = "Diagnóstico comercial"
    scope = "Escopo inicial"
    estimated_value = Decimal("10000.00")
    stage = factory.SubFactory(PipelineStageFactory)
    owner = factory.SubFactory(UserFactory)
    expected_close_date = factory.LazyFunction(lambda: timezone.localdate() + timedelta(days=7))


class LeadFactory(factory.django.DjangoModelFactory):
    """Lead recém-recebido pelo formulário do site — o estado em que a triagem o encontra."""

    class Meta:
        model = Lead

    name = factory.Sequence(lambda n: f"Lead {n}")
    email = factory.LazyAttribute(lambda obj: f"{obj.name.lower().replace(' ', '')}@example.test")
    company = factory.Sequence(lambda n: f"Empresa {n}")
    message = "Quer entender como automatizar o faturamento."


class QualificationFactory(factory.django.DjangoModelFactory):
    """Avaliação qualificada, com conta — o caso que abre oportunidade comercial.

    `outcome` explícito porque o modelo **não** tem default (uma avaliação sem resultado é uma
    avaliação que não aconteceu); quem testa `nurture` passa `nurture_until` junto, senão o
    `clean()` recusa — que é exatamente o que o teste daquele caso quer ver.
    """

    class Meta:
        model = Qualification

    lead = factory.SubFactory(LeadFactory)
    account = factory.SubFactory(ClientFactory)
    outcome = Qualification.Outcome.QUALIFIED
    assessor = factory.SubFactory(UserFactory)


class ActivityFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = Activity

    client = factory.SubFactory(ClientFactory)
    kind = Activity.Kind.CALL
    happened_on = factory.LazyFunction(timezone.localdate)
    summary = "Contato comercial"
    owner = factory.SubFactory(UserFactory)


class ProjectFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = Project

    client = factory.SubFactory(ClientFactory)
    name = "Projeto de aceleração"
    owner = factory.SubFactory(UserFactory)
    start_date = factory.LazyFunction(timezone.localdate)
    due_date = factory.LazyFunction(lambda: timezone.localdate() + timedelta(days=30))


class ProjectMemberFactory(factory.django.DjangoModelFactory):
    """Participação numa equipe de projeto — o que dá acesso a quem é da Entrega (RFC 0003)."""

    class Meta:
        model = ProjectMember
        django_get_or_create = ("project", "user")

    project = factory.SubFactory(ProjectFactory)
    user = factory.SubFactory(UserFactory)


class EngineeringHandoffFactory(factory.django.DjangoModelFactory):
    """Handoff pendente válido — o caso que a API cria antes de falar com o GitHub."""

    class Meta:
        model = EngineeringHandoff

    project = factory.SubFactory(ProjectFactory)
    pulse_work_item_id = factory.Sequence(lambda n: f"pulse-work-{n}")
    title = "Provision GitHub Issue from Pulse handoff"
    objective = "Create the engineering Task Contract as a GitHub Issue."
    acceptance_criteria = "The issue exists, is idempotent, and records correlation ids."


class GithubDeliveryProjectionFactory(factory.django.DjangoModelFactory):
    """Projeção de entrega recém-mapeada — antes de qualquer evento ou reconciliação (FDD 041)."""

    class Meta:
        model = GithubDeliveryProjection

    project = factory.SubFactory(ProjectFactory)
    repository = "acme/repo"
    issue_number = factory.Sequence(lambda n: n + 1)


class MeetingFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = Meeting

    project = factory.SubFactory(ProjectFactory)
    title = "Reunião de discovery"
    date = factory.LazyFunction(timezone.localdate)
    transcript = "Cliente relatou processo manual de faturamento e atraso nas entregas."
    status = Meeting.Status.HELD


class ArtifactFactory(factory.django.DjangoModelFactory):
    """Artefato de proposta por padrão; passe `project=...`/`opportunity=None` para os de entrega."""

    class Meta:
        model = Artifact

    kind = Artifact.Kind.PROPOSAL
    title = "Proposta — Diagnóstico comercial"
    content = "Rascunho gerado para revisão humana."
    opportunity = factory.SubFactory(OpportunityFactory)
    created_by = factory.SubFactory(UserFactory)


class InvoiceFactory(factory.django.DjangoModelFactory):
    """Fatura em rascunho por padrão — o único estado que se cria à mão.

    Emitir, baixar e cancelar passam por `invoices.issue`/`settle`/`cancel`, e os testes devem usar
    essas funções (ou as ações da API) em vez de gravar `status` direto: é justamente o caminho que
    carrega número, carimbo e autor.
    """

    class Meta:
        model = Invoice

    client = factory.SubFactory(ClientFactory)
    amount = Decimal("1000.00")
    description = "Parcela única"
    due_date = factory.LazyFunction(lambda: timezone.localdate() + timedelta(days=15))


class ProcessoFactory(factory.django.DjangoModelFactory):
    """Processo mapeado, **sem nenhum insumo de custo** por padrão (FDD 039).

    Vazio de propósito: o caso interessante do cálculo é a lacuna, e uma fábrica que preenchesse
    os nove faria todo teste de `nao_apurado` começar desfazendo o que ela fez.
    """

    class Meta:
        model = Processo

    client = factory.SubFactory(ClientFactory)
    name = "Faturamento mensal"


class ProcessoEtapaFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = ProcessoEtapa

    processo = factory.SubFactory(ProcessoFactory)
    name = "Conferir pedidos do mês"
    pessoas = "Analista financeiro"
    sistema = "ERP e planilha"


class EvidenciaFactory(factory.django.DjangoModelFactory):
    """Achado de entrevista rotulado como hipótese — o caso mais comum e o menos afirmativo.

    `forma` e `rotulo` não têm default no modelo (é a decisão central da fatia); a fábrica escolhe
    um valor explícito para não obrigar todo teste a repeti-lo, e quem testa a ausência monta o
    payload à mão.
    """

    class Meta:
        model = Evidencia

    processo = factory.SubFactory(ProcessoFactory)
    forma = Evidencia.Forma.ENTREVISTA
    rotulo = Evidencia.Rotulo.HIPOTESE
    content = "O time diz que o fechamento leva dois dias."
