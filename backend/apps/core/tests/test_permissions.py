from datetime import timedelta
from types import SimpleNamespace

import pytest
from django.urls import reverse
from django.utils import timezone
from rest_framework.test import APIClient, APIRequestFactory

from apps.core.models import (
    Account,
    Engagement,
    Milestone,
    PipelineStage,
    Project,
    SatisfactionRecord,
    User,
    ValueLedgerEntry,
)
from apps.core.permissions import RolePermission

from .factories import (
    AccountFactory,
    CommercialOpportunityFactory,
    EngagementFactory,
    EvidenceFactory,
    PriorityAssessmentFactory,
    ProcessFactory,
    ProcessStepFactory,
    ProjectFactory,
    ProjectMemberFactory,
    UserFactory,
    ValueLedgerEntryFactory,
)


@pytest.fixture
def client() -> APIClient:
    return APIClient()


@pytest.mark.django_db
def test_anonymous_user_cannot_access_internal_crm(client: APIClient) -> None:
    assert client.get(reverse("client-list")).status_code == 403
    assert client.get(reverse("dashboard")).status_code == 403


@pytest.mark.django_db
def test_sales_operates_crm_but_cannot_create_or_edit_projects(client: APIClient) -> None:
    sales = UserFactory(role=User.Role.SALES)
    project = ProjectFactory()
    client.force_authenticate(sales)

    created_client = client.post(reverse("client-list"), {"name": "Novo cliente"}, format="json")
    rejected_project = client.post(
        reverse("project-list"),
        {
            "client": project.engagement.account_id,
            "name": "Projeto indevido",
            "start_date": str(timezone.localdate()),
            "due_date": str(timezone.localdate() + timedelta(days=10)),
        },
        format="json",
    )
    rejected_update = client.patch(
        reverse("project-detail", args=[project.id]), {"name": "Alteração indevida"}, format="json"
    )

    assert created_client.status_code == 201
    assert rejected_project.status_code == 403
    assert rejected_update.status_code == 403


@pytest.mark.django_db
def test_delivery_only_sees_won_opportunities_and_cannot_edit_crm(client: APIClient) -> None:
    """Ganha **e** convertida num projeto da equipe (RFC 0003) — antes bastava estar ganha."""
    delivery = UserFactory(role=User.Role.DELIVERY)
    won = CommercialOpportunityFactory(stage=PipelineStage.objects.get(kind=PipelineStage.Kind.WON))
    project = ProjectFactory(originating_commercial_opportunity=won, engagement__account=won.account)
    ProjectMemberFactory(project=project, user=delivery)
    CommercialOpportunityFactory(stage=PipelineStage.objects.get(kind=PipelineStage.Kind.WON))
    CommercialOpportunityFactory()
    client.force_authenticate(delivery)

    listed = client.get(reverse("opportunity-list"))
    rejected_client = client.post(reverse("client-list"), {"name": "Sem permissão"}, format="json")
    rejected_update = client.patch(
        reverse("opportunity-detail", args=[won.id]), {"title": "Alteração"}, format="json"
    )

    assert listed.status_code == 200
    assert [item["id"] for item in listed.data] == [won.id]
    assert rejected_client.status_code == 403
    assert rejected_update.status_code == 403


@pytest.mark.django_db
def test_delivery_can_manage_project_execution(client: APIClient) -> None:
    delivery = UserFactory(role=User.Role.DELIVERY)
    project = ProjectFactory()
    ProjectMemberFactory(project=project, user=delivery)
    client.force_authenticate(delivery)

    response = client.patch(
        reverse("project-detail", args=[project.id]), {"status": Project.Status.ACTIVE}, format="json"
    )

    assert response.status_code == 200
    assert response.data["status"] == Project.Status.ACTIVE


@pytest.mark.django_db
def test_only_administrators_manage_pipeline_and_invitations(client: APIClient) -> None:
    sales = UserFactory(role=User.Role.SALES)
    client.force_authenticate(sales)

    stage_response = client.get(reverse("pipelinestage-list"))
    invite_response = client.post(
        reverse("invitation"), {"email": "x@example.test", "role": "delivery"}, format="json"
    )

    assert stage_response.status_code == 403
    assert invite_response.status_code == 403


@pytest.mark.django_db
def test_delete_archives_client_without_losing_record(client: APIClient) -> None:
    admin = UserFactory(role=User.Role.ADMIN)
    record = AccountFactory(owner=admin)
    client.force_authenticate(admin)

    deleted = client.delete(reverse("client-detail", args=[record.id]))
    listed = client.get(reverse("client-list"))

    assert deleted.status_code == 204
    assert list(listed.data) == []
    assert record.__class__.objects.get(id=record.id).archived_at is not None


# --- has_object_permission, ramo a ramo -----------------------------------------------------
#
# O caminho HTTP comum não alcança a maior parte destes ramos: get_object() do DRF filtra pelo
# queryset escopado (ProjectScopedMixin/get_queryset) antes de chamar check_object_permissions, e
# um GET num objeto alheio já vira 404 pela queryset, sem nunca avaliar a permissão de objeto. Os
# testes abaixo chamam RolePermission().has_object_permission diretamente para exercitar cada
# ramo de verdade; a Camada de integração fica em
# backend/tests/regression/test_a_permissao_de_objeto_e_a_unica_barreira_do_unarchive.py, que usa
# a action `unarchive` — o único caminho HTTP que resolve o objeto pela queryset **crua**.
#
# APIRequestFactory não passa por middleware de autenticação: `request.user` é atribuído à mão.

PERM = RolePermission()


def _request(user: User, method: str = "GET"):
    factory = APIRequestFactory()
    request = getattr(factory, method.lower())("/")
    request.user = user
    return request


def _grant_project_in_account(delivery: User, account: Account) -> None:
    """Dá a `delivery` um projeto dentro do mandato de `account` — o caminho que `visible_to` lê."""
    project = ProjectFactory(engagement__account=account)
    ProjectMemberFactory(project=project, user=delivery)


def _grant_project_in_engagement(delivery: User, engagement: Engagement) -> Project:
    project = ProjectFactory(engagement=engagement)
    ProjectMemberFactory(project=project, user=delivery)
    return project


@pytest.mark.django_db
def test_admin_sempre_passa_qualquer_objeto_e_metodo() -> None:
    """Ramo `is_admin_role`: decide sozinho, sem olhar para `obj` nem para o método."""
    admin = UserFactory(role=User.Role.ADMIN)

    assert PERM.has_object_permission(_request(admin, "DELETE"), SimpleNamespace(), object()) is True


@pytest.mark.django_db
def test_sales_so_le_projeto() -> None:
    """Ramo SALES, lado `isinstance(obj, Project)`: os dois métodos."""
    sales = UserFactory(role=User.Role.SALES)
    project = ProjectFactory()

    assert PERM.has_object_permission(_request(sales, "GET"), SimpleNamespace(), project) is True
    assert PERM.has_object_permission(_request(sales, "PATCH"), SimpleNamespace(), project) is False


@pytest.mark.django_db
def test_sales_escreve_qualquer_coisa_que_nao_seja_projeto() -> None:
    """Ramo SALES, lado "qualquer outro tipo": passa mesmo em método não-seguro."""
    sales = UserFactory(role=User.Role.SALES)
    opportunity = CommercialOpportunityFactory()

    assert (
        PERM.has_object_permission(_request(sales, "PATCH"), SimpleNamespace(), opportunity) is True
    )


@pytest.mark.django_db
def test_delivery_catalogo_e_so_leitura() -> None:
    """Ramo `resource in CATALOG`: catálogo global, os dois métodos."""
    delivery = UserFactory(role=User.Role.DELIVERY)
    view = SimpleNamespace(resource="service")

    assert PERM.has_object_permission(_request(delivery, "GET"), view, object()) is True
    assert PERM.has_object_permission(_request(delivery, "POST"), view, object()) is False


@pytest.mark.django_db
def test_delivery_conta_contato_atividade_e_so_leitura() -> None:
    """Ramo `resource in {"account", "contact", "activity"}`, os dois métodos."""
    delivery = UserFactory(role=User.Role.DELIVERY)
    view = SimpleNamespace(resource="account")

    assert PERM.has_object_permission(_request(delivery, "GET"), view, object()) is True
    assert PERM.has_object_permission(_request(delivery, "POST"), view, object()) is False


@pytest.mark.django_db
def test_delivery_conhecimento_e_leitura_ou_verificacao() -> None:
    """Ramo `resource == "knowledge"`: leitura passa, escrita comum não passa, `verify` passa mesmo escrevendo."""
    delivery = UserFactory(role=User.Role.DELIVERY)
    view_leitura = SimpleNamespace(resource="knowledge", action="retrieve")
    view_escrita = SimpleNamespace(resource="knowledge", action="partial_update")
    view_verificar = SimpleNamespace(resource="knowledge", action="verify")

    assert PERM.has_object_permission(_request(delivery, "GET"), view_leitura, object()) is True
    assert PERM.has_object_permission(_request(delivery, "POST"), view_escrita, object()) is False
    assert PERM.has_object_permission(_request(delivery, "POST"), view_verificar, object()) is True


@pytest.mark.django_db
def test_delivery_satisfaction_record_pela_conta_do_engajamento() -> None:
    """Ramo `SatisfactionRecord`: os dois desfechos, pela conta — não pelo `project`, que é opcional aqui."""
    account = AccountFactory()
    registro = SatisfactionRecord.objects.create(
        account=account,
        nivel=SatisfactionRecord.Nivel.SATISFIED,
        fonte=SatisfactionRecord.Fonte.DECLARED,
        happened_on=timezone.localdate(),
    )
    alcanca = UserFactory(role=User.Role.DELIVERY)
    _grant_project_in_account(alcanca, account)
    nao_alcanca = UserFactory(role=User.Role.DELIVERY)

    assert PERM.has_object_permission(_request(alcanca), SimpleNamespace(), registro) is True
    assert PERM.has_object_permission(_request(nao_alcanca), SimpleNamespace(), registro) is False


@pytest.mark.django_db
def test_delivery_evidence_pela_conta_direta() -> None:
    """Ramo do Discovery/PRIORITIZE, caminho `obj.account` (`Evidence`): campo próprio."""
    account = AccountFactory()
    evidence = EvidenceFactory(account=account)
    alcanca = UserFactory(role=User.Role.DELIVERY)
    _grant_project_in_account(alcanca, account)
    nao_alcanca = UserFactory(role=User.Role.DELIVERY)

    assert PERM.has_object_permission(_request(alcanca), SimpleNamespace(), evidence) is True
    assert PERM.has_object_permission(_request(nao_alcanca), SimpleNamespace(), evidence) is False


@pytest.mark.django_db
def test_delivery_priority_assessment_pela_conta_da_oportunidade() -> None:
    """Ramo do Discovery/PRIORITIZE, caminho `obj.improvement_opportunity.account`."""
    account = AccountFactory()
    assessment = PriorityAssessmentFactory(improvement_opportunity__account=account)
    alcanca = UserFactory(role=User.Role.DELIVERY)
    _grant_project_in_account(alcanca, account)
    nao_alcanca = UserFactory(role=User.Role.DELIVERY)

    assert PERM.has_object_permission(_request(alcanca), SimpleNamespace(), assessment) is True
    assert PERM.has_object_permission(_request(nao_alcanca), SimpleNamespace(), assessment) is False


@pytest.mark.django_db
def test_delivery_process_pela_conta_direta() -> None:
    """Ramo do Discovery/PRIORITIZE, caminho `Process.account`: campo próprio do processo."""
    account = AccountFactory()
    process = ProcessFactory(account=account)
    alcanca = UserFactory(role=User.Role.DELIVERY)
    _grant_project_in_account(alcanca, account)
    nao_alcanca = UserFactory(role=User.Role.DELIVERY)

    assert PERM.has_object_permission(_request(alcanca), SimpleNamespace(), process) is True
    assert PERM.has_object_permission(_request(nao_alcanca), SimpleNamespace(), process) is False


@pytest.mark.django_db
def test_delivery_process_step_pela_conta_do_processo_pai() -> None:
    """Ramo do Discovery/PRIORITIZE, caminho `ProcessStep` → `obj.process.account`, o pai."""
    account = AccountFactory()
    step = ProcessStepFactory(process__account=account)
    alcanca = UserFactory(role=User.Role.DELIVERY)
    _grant_project_in_account(alcanca, account)
    nao_alcanca = UserFactory(role=User.Role.DELIVERY)

    assert PERM.has_object_permission(_request(alcanca), SimpleNamespace(), step) is True
    assert PERM.has_object_permission(_request(nao_alcanca), SimpleNamespace(), step) is False


@pytest.mark.django_db
def test_delivery_value_ledger_entry_por_projeto_quando_tem_projeto() -> None:
    """Ramo `ValueLedgerEntry`, lado `project_id`: a entrada já diz de qual projeto é."""
    engagement = EngagementFactory()
    project = ProjectFactory(engagement=engagement)
    entry = ValueLedgerEntryFactory(engagement=engagement, project=project)
    alcanca = UserFactory(role=User.Role.DELIVERY)
    ProjectMemberFactory(project=project, user=alcanca)
    nao_alcanca = UserFactory(role=User.Role.DELIVERY)

    assert entry.project_id is not None
    assert PERM.has_object_permission(_request(alcanca), SimpleNamespace(), entry) is True
    assert PERM.has_object_permission(_request(nao_alcanca), SimpleNamespace(), entry) is False


@pytest.mark.django_db
def test_delivery_value_ledger_entry_pelo_engajamento_quando_sem_projeto() -> None:
    """Ramo `ValueLedgerEntry`, lado `engagement`: sem projeto atribuído à entrada."""
    engagement = EngagementFactory()
    entry: ValueLedgerEntry = ValueLedgerEntryFactory(engagement=engagement)
    alcanca = UserFactory(role=User.Role.DELIVERY)
    _grant_project_in_engagement(alcanca, engagement)
    nao_alcanca = UserFactory(role=User.Role.DELIVERY)

    assert entry.project_id is None
    assert PERM.has_object_permission(_request(alcanca), SimpleNamespace(), entry) is True
    assert PERM.has_object_permission(_request(nao_alcanca), SimpleNamespace(), entry) is False


@pytest.mark.django_db
def test_delivery_engagement_e_leitura_e_alcance_do_projeto() -> None:
    """Ramo `Engagement`: método seguro e alcance do mandato têm de valer os dois, juntos."""
    engagement = EngagementFactory()
    alcanca = UserFactory(role=User.Role.DELIVERY)
    _grant_project_in_engagement(alcanca, engagement)
    nao_alcanca = UserFactory(role=User.Role.DELIVERY)

    assert PERM.has_object_permission(_request(alcanca, "GET"), SimpleNamespace(), engagement) is True
    assert (
        PERM.has_object_permission(_request(nao_alcanca, "GET"), SimpleNamespace(), engagement)
        is False
    )
    assert (
        PERM.has_object_permission(_request(alcanca, "PATCH"), SimpleNamespace(), engagement)
        is False
    )


@pytest.mark.django_db
def test_delivery_commercial_opportunity_ganha_e_so_leitura() -> None:
    """Ramo `CommercialOpportunity`: `is_won` e método seguro têm de valer os dois, juntos."""
    delivery = UserFactory(role=User.Role.DELIVERY)
    ganha = CommercialOpportunityFactory(
        stage=PipelineStage.objects.get(kind=PipelineStage.Kind.WON)
    )
    aberta = CommercialOpportunityFactory()

    assert PERM.has_object_permission(_request(delivery, "GET"), SimpleNamespace(), ganha) is True
    assert (
        PERM.has_object_permission(_request(delivery, "PATCH"), SimpleNamespace(), ganha) is False
    )
    assert (
        PERM.has_object_permission(_request(delivery, "GET"), SimpleNamespace(), aberta) is False
    )


@pytest.mark.django_db
def test_delivery_project_member_e_leitura_de_quem_participa() -> None:
    """Ramo `ProjectMember`: ler a equipe do próprio projeto, sim; método não-seguro, não."""
    project = ProjectFactory()
    membro_lido = ProjectMemberFactory(project=project)
    leitor = UserFactory(role=User.Role.DELIVERY)
    ProjectMemberFactory(project=project, user=leitor)
    de_fora = UserFactory(role=User.Role.DELIVERY)

    assert (
        PERM.has_object_permission(_request(leitor, "GET"), SimpleNamespace(), membro_lido) is True
    )
    assert (
        PERM.has_object_permission(_request(de_fora, "GET"), SimpleNamespace(), membro_lido)
        is False
    )
    assert (
        PERM.has_object_permission(_request(leitor, "PATCH"), SimpleNamespace(), membro_lido)
        is False
    )


@pytest.mark.django_db
def test_delivery_project_of_generico_por_participacao() -> None:
    """Ramo genérico: o mapa `PROJECT_OF` genérico, exercitado com `Milestone`."""
    project = ProjectFactory()
    milestone = Milestone.objects.create(
        project=project, title="Marco", owner=project.owner, due_date=project.due_date
    )
    alcanca = UserFactory(role=User.Role.DELIVERY)
    ProjectMemberFactory(project=project, user=alcanca)
    nao_alcanca = UserFactory(role=User.Role.DELIVERY)

    assert PERM.has_object_permission(_request(alcanca), SimpleNamespace(), milestone) is True
    assert PERM.has_object_permission(_request(nao_alcanca), SimpleNamespace(), milestone) is False


@pytest.mark.django_db
def test_delivery_nega_por_padrao_para_tipo_fora_de_todo_ramo() -> None:
    """O `return False` que fecha o bloco DELIVERY: `Account` não está em nenhum `isinstance` acima nem em `PROJECT_OF`."""
    delivery = UserFactory(role=User.Role.DELIVERY)
    account = AccountFactory()

    assert PERM.has_object_permission(_request(delivery, "GET"), SimpleNamespace(), account) is False


@pytest.mark.django_db
def test_papel_fora_do_vocabulario_nega() -> None:
    """O `return False` final do método: papel que não é admin/sales/delivery — nasce fechado."""
    estranho = UserFactory(role="auditor")

    assert PERM.has_object_permission(_request(estranho, "GET"), SimpleNamespace(), object()) is False
