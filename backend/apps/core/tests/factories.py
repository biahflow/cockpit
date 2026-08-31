from datetime import timedelta
from decimal import Decimal

import factory
from django.utils import timezone

from apps.core.models import (
    KPI,
    Account,
    Activity,
    Artifact,
    CommercialOpportunity,
    DigitalEmployee,
    Discovery,
    DiscoverySession,
    Engagement,
    EngineeringHandoff,
    Evidence,
    FeasibilityAssessment,
    Finding,
    GithubDeliveryProjection,
    ImprovementOpportunity,
    Invoice,
    Lead,
    Measurement,
    Meeting,
    PainPoint,
    PipelineStage,
    PriorityAssessment,
    Process,
    ProcessObservation,
    ProcessStep,
    Project,
    ProjectMember,
    ProveExperiment,
    Qualification,
    Service,
    SolutionHypothesis,
    User,
    ValueLedgerEntry,
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


class AccountFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = Account

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


class CommercialOpportunityFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = CommercialOpportunity

    account = factory.SubFactory(AccountFactory)
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
    account = factory.SubFactory(AccountFactory)
    outcome = Qualification.Outcome.QUALIFIED
    assessor = factory.SubFactory(UserFactory)


class ActivityFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = Activity

    account = factory.SubFactory(AccountFactory)
    kind = Activity.Kind.CALL
    happened_on = factory.LazyFunction(timezone.localdate)
    summary = "Contato comercial"
    owner = factory.SubFactory(UserFactory)


class EngagementFactory(factory.django.DjangoModelFactory):
    """Mandato legado por padrão, sem instrumento inferido (invariante 13, migração 0074).

    Teste que exerce criação nova deve informar uma das duas origens explicitamente. A fábrica
    genérica sustenta a massa histórica usada pelas suítes anteriores e por isso carrega o mesmo
    `needs_review=True` que a migração grava — nunca fabrica venda ou contrato por conveniência.
    """

    class Meta:
        model = Engagement

    account = factory.SubFactory(AccountFactory)
    name = factory.Sequence(lambda n: f"Engajamento {n}")
    owner = factory.SubFactory(UserFactory)
    started_at = factory.LazyFunction(timezone.localdate)
    needs_review = True


class ProjectFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = Project

    engagement = factory.SubFactory(
        EngagementFactory,
        owner=factory.SelfAttribute("..owner"),
    )
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
    """Artefato de proposta por padrão; passe `project=…`/`commercial_opportunity=None` para
    os de entrega."""

    class Meta:
        model = Artifact

    kind = Artifact.Kind.PROPOSAL
    title = "Proposta — Diagnóstico comercial"
    content = "Rascunho gerado para revisão humana."
    commercial_opportunity = factory.SubFactory(CommercialOpportunityFactory)
    created_by = factory.SubFactory(UserFactory)


class InvoiceFactory(factory.django.DjangoModelFactory):
    """Fatura em rascunho por padrão — o único estado que se cria à mão.

    Emitir, baixar e cancelar passam por `invoices.issue`/`settle`/`cancel`, e os testes devem usar
    essas funções (ou as ações da API) em vez de gravar `status` direto: é justamente o caminho que
    carrega número, carimbo e autor.
    """

    class Meta:
        model = Invoice

    account = factory.SubFactory(AccountFactory)
    amount = Decimal("1000.00")
    description = "Parcela única"
    due_date = factory.LazyFunction(lambda: timezone.localdate() + timedelta(days=15))


class ProcessFactory(factory.django.DjangoModelFactory):
    """Processo mapeado, **sem nenhum insumo de custo** por padrão (FDD 039).

    Vazio de propósito: o caso interessante do cálculo é a lacuna, e uma fábrica que preenchesse
    os nove faria todo teste de `nao_apurado` começar desfazendo o que ela fez.
    """

    class Meta:
        model = Process

    account = factory.SubFactory(AccountFactory)
    name = "Faturamento mensal"


class ProcessStepFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = ProcessStep

    process = factory.SubFactory(ProcessFactory)
    name = "Conferir pedidos do mês"
    pessoas = "Analista financeiro"
    sistema = "ERP e planilha"


class DiscoveryFactory(factory.django.DjangoModelFactory):
    """Discovery em andamento — o estado em que quase todo teste quer o levantamento (FDD 045)."""

    class Meta:
        model = Discovery

    project = factory.SubFactory(ProjectFactory)
    scope = "Faturamento e expedição"
    status = Discovery.Status.RUNNING
    started_at = factory.LazyFunction(timezone.localdate)


class DiscoverySessionFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = DiscoverySession

    discovery = factory.SubFactory(DiscoveryFactory)
    happened_at = factory.LazyFunction(timezone.now)
    participants = "Analista financeiro, coordenadora de expedição"


class ProcessObservationFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = ProcessObservation

    discovery = factory.SubFactory(DiscoveryFactory)
    process = factory.SubFactory(ProcessFactory)
    observed_at = factory.LazyFunction(timezone.localdate)


class EvidenceFactory(factory.django.DjangoModelFactory):
    """Trecho de entrevista, com o texto **bruto** e sem conclusão nenhuma (FDD 045).

    `kind` não tem default no modelo; a fábrica escolhe um valor explícito para não obrigar todo
    teste a repeti-lo, e quem testa a ausência monta o payload à mão.
    """

    class Meta:
        model = Evidence

    account = factory.SubFactory(AccountFactory)
    kind = Evidence.Kind.INTERVIEW
    raw_excerpt = "A gente confere nota por nota, e no fim do mês são umas quatrocentas."


class PainPointFactory(factory.django.DjangoModelFactory):
    """Dor **observada**, o estado menos afirmativo dos três (FDD 048).

    Nunca `confirmed` por padrão, no espírito da `FindingFactory` logo abaixo: confirmar exige
    achado vivo, e uma fábrica que entregasse dores confirmadas de graça faria todo teste da
    invariante começar desfazendo o que ela fez.

    `impact_estimate` fica **ausente** de propósito — a fábrica não inventa um número que ninguém
    estimou, e é essa a distinção que o campo nulável existe para guardar.
    """

    class Meta:
        model = PainPoint

    account = factory.SubFactory(AccountFactory)
    title = "Conferência manual de nota trava o fechamento"
    impact_type = PainPoint.ImpactType.OPERATIONAL
    status = PainPoint.Status.OBSERVED


class ImprovementOpportunityFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = ImprovementOpportunity

    account = factory.SubFactory(AccountFactory)
    title = "Automatizar a conferência de notas"
    status = ImprovementOpportunity.Status.OPEN


class PriorityAssessmentFactory(factory.django.DjangoModelFactory):
    """As cinco dimensões no meio da escala. `version`, `weights` e `score` **não** são passados:
    os três saem do `save()` do modelo, e informá-los aqui esconderia justamente o que os testes
    desta suíte medem."""

    class Meta:
        model = PriorityAssessment

    improvement_opportunity = factory.SubFactory(ImprovementOpportunityFactory)
    impact = 3
    evidence_strength = 3
    feasibility = 3
    time_to_value = 3
    economics = 3


class SolutionHypothesisFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = SolutionHypothesis

    improvement_opportunity = factory.SubFactory(ImprovementOpportunityFactory)
    statement = "Um leitor de nota fiscal reduz a conferência a uma revisão por exceção."
    status = SolutionHypothesis.Status.PROPOSED


class FindingFactory(factory.django.DjangoModelFactory):
    """Achado nascendo **hipótese** — o estado menos afirmativo dos três (FDD 045).

    Nunca `fact` por padrão: promover exige revisor e evidência viva, e uma fábrica que entregasse
    fatos de graça faria todo teste da invariante §6.9 começar desfazendo o que ela fez — e o
    primeiro teste esquecido passaria a afirmar sobre um estado que a API não deixa criar.
    """

    class Meta:
        model = Finding

    account = factory.SubFactory(AccountFactory)
    statement = "O fechamento do faturamento leva dois dias."
    epistemic_status = Finding.EpistemicStatus.HYPOTHESIS


class FeasibilityAssessmentFactory(factory.django.DjangoModelFactory):
    """Laudo **sem decisão de gate** por padrão (FDD 049).

    Em branco é o estado em que todo laudo nasce — o gate é ato posterior —, e uma fábrica que já
    entregasse `GO` faria todo teste do vocabulário começar desfazendo o que ela fez. A hipótese e
    o projeto nascem na **mesma conta**, senão o `clean()` recusaria toda criação de fábrica.
    """

    class Meta:
        model = FeasibilityAssessment

    project = factory.SubFactory(ProjectFactory)
    # `LazyAttribute` e não `SubFactory`: a hipótese precisa nascer na **conta do projeto**, e a
    # conta está dois níveis abaixo (hipótese → oportunidade → conta). Um `SubFactory` cru criaria
    # uma segunda `Account`, e o `clean()` recusaria toda criação de fábrica — é o mesmo cuidado
    # que `ProjectFactory` tem com o `engagement`.
    solution_hypothesis = factory.LazyAttribute(
        lambda obj: SolutionHypothesisFactory(
            improvement_opportunity=ImprovementOpportunityFactory(account=obj.project.engagement.account)
        )
    )
    technical_verdict = FeasibilityAssessment.Verdict.FAVORABLE
    operational_verdict = FeasibilityAssessment.Verdict.FAVORABLE
    economic_verdict = FeasibilityAssessment.Verdict.FAVORABLE


class ProveExperimentFactory(factory.django.DjangoModelFactory):
    """Experimento **planejado e sem critério de sucesso** (FDD 049).

    Os dois padrões são o caso que a invariante de início existe para recusar: `planned` porque é
    de onde `start/` parte, e `success_criteria` em branco porque preenchê-lo de graça faria a
    metade mais barata da invariante nunca ser exercida sem alguém desfazer a fábrica antes.
    """

    class Meta:
        model = ProveExperiment

    project = factory.SubFactory(ProjectFactory)
    # `LazyAttribute` e não `SubFactory`: a hipótese precisa nascer na **conta do projeto**, e a
    # conta está dois níveis abaixo (hipótese → oportunidade → conta). Um `SubFactory` cru criaria
    # uma segunda `Account`, e o `clean()` recusaria toda criação de fábrica — é o mesmo cuidado
    # que `ProjectFactory` tem com o `engagement`.
    solution_hypothesis = factory.LazyAttribute(
        lambda obj: SolutionHypothesisFactory(
            improvement_opportunity=ImprovementOpportunityFactory(account=obj.project.engagement.account)
        )
    )
    controlled_scope = "Uma filial, por quatro semanas."
    status = ProveExperiment.Status.PLANNED


class KPIFactory(factory.django.DjangoModelFactory):
    """KPI do projeto, **sem experimento** — o formato do KPI migrado (ADR 0055)."""

    class Meta:
        model = KPI

    project = factory.SubFactory(ProjectFactory)
    name = "Tempo de resposta"
    unit = "hours"
    direction = "down"


class MeasurementFactory(factory.django.DjangoModelFactory):
    """Baseline com valor. `value` é explícito porque a ausência dele **é** o caso interessante:
    nulo é "não medido" e nunca zero, e quem testa a lacuna monta a linha sem o campo."""

    class Meta:
        model = Measurement

    kpi = factory.SubFactory(KPIFactory)
    kind = Measurement.Kind.BASELINE
    value = Decimal("4.20")
    period_start = factory.LazyFunction(lambda: timezone.localdate() - timedelta(days=30))
    period_end = factory.LazyFunction(timezone.localdate)
    measured_at = factory.LazyFunction(timezone.now)


class ValueLedgerEntryFactory(factory.django.DjangoModelFactory):
    """Entrada em rascunho apontando para um `Outcome` — o único `kind` que ela aceita (§6.12).

    `attribution_method` vem preenchido porque vazio é recusado, e o teste que mede a recusa monta
    o payload à mão, no molde da `QualificationFactory`.
    """

    class Meta:
        model = ValueLedgerEntry

    engagement = factory.SubFactory(EngagementFactory)
    outcome_measurement = factory.SubFactory(MeasurementFactory, kind=Measurement.Kind.OUTCOME)
    value_type = ValueLedgerEntry.ValueType.COST_SAVING
    amount = Decimal("12000.00")
    period_start = factory.LazyFunction(lambda: timezone.localdate() - timedelta(days=30))
    period_end = factory.LazyFunction(timezone.localdate)
    attribution_method = "Diferença entre baseline e outcome do KPI, descontada a sazonalidade."
    status = ValueLedgerEntry.Status.DRAFT


def digital_employee_medido(
    project,
    baseline: Decimal | None = None,
    current: Decimal | None = None,
    **campos,
):
    """Um Funcionário Digital com o KPI que ele **referencia** e as medições dele (ADR 0055).

    Ajudante e não fábrica porque o par baseline/atual deixou de ser dois campos do ativo e virou
    duas linhas de outra tabela: `KPI` + `Measurement`. Existe num lugar só pelo motivo de sempre —
    três cópias em três suítes divergiriam na primeira correção —, e preserva os dois nomes na
    assinatura de propósito: o que as suítes do case afirmam é a **forma** do congelamento, que não
    mudou; mudou de onde ela lê.

    `None` continua sendo "não medido" e **não vira medição nenhuma**, que é o caso da lacuna.
    """
    kpi = KPI.objects.create(
        project=project,
        name=campos.get("kpi_label") or campos.get("name") or "KPI",
        unit=campos.get("kpi_unit", ""),
        direction=campos.get("kpi_direction", "up"),
    )
    agora = timezone.now()
    hoje = timezone.localdate()
    for kind, valor in ((Measurement.Kind.BASELINE, baseline), (Measurement.Kind.OUTCOME, current)):
        if valor is not None:
            Measurement.objects.create(
                kpi=kpi, kind=kind, value=valor,
                period_start=hoje, period_end=hoje, measured_at=agora,
            )
    return DigitalEmployee.objects.create(project=project, kpi=kpi, **campos)
