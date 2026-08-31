"""Repositório de cases com métrica — congelamento, consentimento e publicação (FDD 027)."""

from datetime import timedelta
from decimal import Decimal

import pytest
from rest_framework.test import APIClient

from apps.core import cases
from apps.core.models import (
    Case,
    DigitalEmployee,
    DigitalEmployeeBlueprint,
    KpiDirection,
    KpiUnit,
    Pendencia,
    Project,
    Task,
    Vertical,
    WorkItem,
)

from .factories import (
    AccountFactory,
    EngagementFactory,
    ProjectFactory,
    ProjectMemberFactory,
    UserFactory,
    digital_employee_medido,
)


def _api(role: str = "admin") -> APIClient:
    client = APIClient()
    client.force_authenticate(UserFactory(role=role))
    return client


def _vertical(name: str = "Igrejas", slug: str = "igrejas") -> Vertical:
    return Vertical.objects.create(name=name, slug=slug)


def _employee(
    project: Project,
    kpi_baseline: Decimal | None = Decimal("12.00"),
    kpi_current: Decimal | None = Decimal("48.00"),
    **overrides,
) -> DigitalEmployee:
    """O ativo com o KPI que ele referencia e as medições dele (ADR 0055).

    Delega ao ajudante compartilhado: o par baseline/atual deixou de ser coluna do ativo e virou
    duas `Measurement` do mesmo KPI, e três suítes reescrevendo essa montagem divergiriam.
    """
    campos = {
        "name": "SDR",
        "area": "Comercial",
        "kpi_label": "Leads qualificados/mês",
        "kpi_unit": KpiUnit.COUNT,
        "kpi_direction": KpiDirection.UP,
    }
    return digital_employee_medido(
        project, baseline=kpi_baseline, current=kpi_current, **{**campos, **overrides}
    )


def _completed_project(**overrides) -> Project:
    """Cria o projeto **e depois** o conclui: é a transição que congela, não o `create`."""
    project = ProjectFactory(**overrides)
    _employee(project)
    project.status = Project.Status.COMPLETED
    project.save()
    return project


# --- o congelamento na conclusão --------------------------------------------------------------


@pytest.mark.django_db
def test_concluir_projeto_congela_um_case_em_rascunho():
    vertical = _vertical()
    project = _completed_project(
        engagement=EngagementFactory(account=AccountFactory(vertical=vertical)),
        actual_value=Decimal("180000.00"),
        cost=Decimal("90000.00"),
    )

    case = Case.objects.get(project=project)
    assert case.status == Case.Status.DRAFT
    assert case.published_at is None
    assert case.vertical == vertical
    assert case.roi_snapshot == {"revenue": "180000.00", "cost": "90000.00", "roi": 1.0}
    assert case.health_snapshot["score"] == 100
    assert [m["kpi_label"] for m in case.metrics] == ["Leads qualificados/mês"]
    assert case.metrics[0]["baseline"] == "12.00"
    assert case.metrics[0]["current"] == "48.00"
    assert case.metrics[0]["has_baseline"] is True


@pytest.mark.django_db
def test_projeto_em_andamento_nao_gera_case():
    ProjectFactory(status=Project.Status.ACTIVE)

    assert not Case.objects.exists()


@pytest.mark.django_db
def test_reconcluir_projeto_nao_duplica_o_case():
    """A segunda conclusão não pode congelar de novo: o case é a foto do encerramento."""
    project = _completed_project()
    project.status = Project.Status.ACTIVE
    project.save()
    project.status = Project.Status.COMPLETED
    project.save()

    assert Case.objects.filter(project=project).count() == 1


@pytest.mark.django_db
def test_salvar_projeto_ja_concluido_nao_gera_case_novo():
    project = _completed_project()
    project.name = "Outro nome"
    project.save()

    assert Case.objects.filter(project=project).count() == 1


@pytest.mark.django_db
def test_case_sem_baseline_declara_a_lacuna_em_vez_de_inventar_zero():
    project = ProjectFactory()
    _employee(project, name="Cobrador", kpi_baseline=None, kpi_current=Decimal("30.00"))
    project.status = Project.Status.COMPLETED
    project.save()

    metricas = {m["name"]: m for m in Case.objects.get(project=project).metrics}
    assert metricas["Cobrador"]["baseline"] is None
    assert metricas["Cobrador"]["has_baseline"] is False


@pytest.mark.django_db
def test_funcionario_digital_arquivado_fica_de_fora_do_case():
    project = ProjectFactory()
    _employee(project, name="Ativo")
    _employee(project, name="Aposentado").archive()
    project.status = Project.Status.COMPLETED
    project.save()

    assert [m["name"] for m in Case.objects.get(project=project).metrics] == ["Ativo"]


@pytest.mark.django_db
def test_roi_sem_custo_registrado_sai_nulo_e_nao_estoura():
    project = _completed_project(actual_value=Decimal("50000.00"), cost=Decimal("0.00"))

    assert Case.objects.get(project=project).roi_snapshot["roi"] is None


# --- consentimento e publicação ----------------------------------------------------------------


@pytest.mark.django_db
def test_publicar_sem_consentimento_e_recusado():
    case = Case.objects.get(project=_completed_project())

    resposta = _api().patch(f"/api/v1/cases/{case.pk}/", {"status": "published"}, format="json")

    assert resposta.status_code == 400
    assert "consentimento" in str(resposta.data).lower()
    case.refresh_from_db()
    assert case.status == Case.Status.DRAFT


@pytest.mark.django_db
def test_registrar_consentimento_grava_autor_e_carimbo():
    case = Case.objects.get(project=_completed_project())
    api = APIClient()
    admin = UserFactory(role="admin")
    api.force_authenticate(admin)

    resposta = api.post(f"/api/v1/cases/{case.pk}/record-consent/")

    assert resposta.status_code == 200
    case.refresh_from_db()
    assert case.account_consent is True
    assert case.consent_recorded_by == admin
    assert case.consent_recorded_at is not None


@pytest.mark.django_db
def test_com_consentimento_publica_e_carimba_a_data():
    case = Case.objects.get(project=_completed_project())
    api = _api()
    api.post(f"/api/v1/cases/{case.pk}/record-consent/")

    resposta = api.patch(f"/api/v1/cases/{case.pk}/", {"status": "published"}, format="json")

    assert resposta.status_code == 200
    case.refresh_from_db()
    assert case.status == Case.Status.PUBLISHED
    assert case.published_at is not None


@pytest.mark.django_db
def test_publicado_e_terminal():
    case = Case.objects.get(project=_completed_project())
    api = _api()
    api.post(f"/api/v1/cases/{case.pk}/record-consent/")
    api.patch(f"/api/v1/cases/{case.pk}/", {"status": "published"}, format="json")

    volta = api.patch(f"/api/v1/cases/{case.pk}/", {"status": "draft"}, format="json")

    assert volta.status_code == 400


@pytest.mark.django_db
def test_rascunho_e_revisao_vao_e_voltam():
    case = Case.objects.get(project=_completed_project())
    api = _api()

    assert api.patch(f"/api/v1/cases/{case.pk}/", {"status": "review"}, format="json").status_code == 200
    assert api.patch(f"/api/v1/cases/{case.pk}/", {"status": "draft"}, format="json").status_code == 200


@pytest.mark.django_db
def test_consentimento_nao_e_gravavel_pelo_patch():
    """Consentimento é ato com autor; um PATCH o gravaria sem dizer quem autorizou."""
    case = Case.objects.get(project=_completed_project())

    _api().patch(f"/api/v1/cases/{case.pk}/", {"client_consent": True}, format="json")

    case.refresh_from_db()
    assert case.account_consent is False


# --- a superfície da API -----------------------------------------------------------------------


@pytest.mark.django_db
def test_case_nao_pode_ser_criado_a_mao():
    project = ProjectFactory()

    resposta = _api().post(
        "/api/v1/cases/", {"project": project.pk, "title": "Case inventado"}, format="json"
    )

    assert resposta.status_code == 405
    assert not Case.objects.exists()


@pytest.mark.django_db
def test_numeros_congelados_sao_somente_leitura_na_api():
    case = Case.objects.get(
        project=_completed_project(actual_value=Decimal("180000.00"), cost=Decimal("90000.00"))
    )

    _api().patch(
        f"/api/v1/cases/{case.pk}/",
        {"title": "Título revisado", "health_snapshot": {"score": 1}, "metrics": [],
         "roi_snapshot": {"revenue": "0"}},
        format="json",
    )

    case.refresh_from_db()
    assert case.title == "Título revisado"
    assert case.health_snapshot["score"] == 100
    assert case.metrics != []
    assert case.roi_snapshot["revenue"] != "0"


@pytest.mark.django_db
def test_lista_filtra_por_vertical_e_por_status():
    igrejas, saude = _vertical(), _vertical("Saúde", "saude")
    _completed_project(engagement=EngagementFactory(account=AccountFactory(vertical=igrejas)))
    _completed_project(engagement=EngagementFactory(account=AccountFactory(vertical=saude)))
    api = _api()

    por_vertical = api.get(f"/api/v1/cases/?vertical={igrejas.pk}")
    por_status = api.get("/api/v1/cases/?status=published")

    assert len(por_vertical.data) == 1
    assert por_status.data == []


@pytest.mark.django_db
def test_case_arquiva_e_restaura_como_todo_recurso_de_negocio():
    case = Case.objects.get(project=_completed_project())
    api = _api()

    assert api.delete(f"/api/v1/cases/{case.pk}/").status_code == 204
    assert api.get("/api/v1/cases/").data == []
    assert api.post(f"/api/v1/cases/{case.pk}/unarchive/").status_code == 200
    assert len(api.get("/api/v1/cases/").data) == 1


# --- permissões ---------------------------------------------------------------------------------


@pytest.mark.django_db
def test_vendas_le_o_case_e_nao_publica():
    case = Case.objects.get(project=_completed_project())
    cases.record_consent(case, UserFactory(role="admin"))
    api = _api("sales")

    assert api.get("/api/v1/cases/").status_code == 200
    assert api.patch(f"/api/v1/cases/{case.pk}/", {"status": "published"}, format="json").status_code == 403
    assert api.post(f"/api/v1/cases/{case.pk}/record-consent/").status_code == 403


@pytest.mark.django_db
def test_entrega_ve_case_so_dos_projetos_de_que_participa():
    meu = _completed_project()
    _completed_project()  # de outra equipe
    entrega = UserFactory(role="delivery")
    ProjectMemberFactory(project=meu, user=entrega)
    api = APIClient()
    api.force_authenticate(entrega)

    listagem = api.get("/api/v1/cases/")

    assert [linha["project"] for linha in listagem.data] == [meu.pk]


@pytest.mark.django_db
def test_entrega_nao_alcanca_case_de_projeto_alheio():
    alheio = Case.objects.get(project=_completed_project())
    api = APIClient()
    api.force_authenticate(UserFactory(role="delivery"))

    assert api.get(f"/api/v1/cases/{alheio.pk}/").status_code == 404


# --- o health congelado é o do encerramento, não o de hoje --------------------------------------


@pytest.mark.django_db
def test_health_congelado_reflete_o_estado_no_encerramento():
    project = ProjectFactory()
    dono = project.owner
    Task.objects.create(
        project=project, title="Tarefa vencida", owner=dono,
        due_date=project.start_date - timedelta(days=10),
    )
    Pendencia.objects.create(
        project=project, title="Decisão do cliente", owner=dono, party=WorkItem.Party.CLIENT,
    )
    project.status = Project.Status.COMPLETED
    project.save()

    case = Case.objects.get(project=project)
    assert case.health_snapshot["score"] < 100
    assert {sinal["label"] for sinal in case.health_snapshot["signals"]} == {
        "Entregas atrasadas", "Decisões pendentes",
    }


# --- a instanciação a partir do catálogo carrega a tipagem, e não mais a base -------------------


@pytest.mark.django_db
def test_instanciar_do_catalogo_copia_unidade_e_direcao():
    blueprint = DigitalEmployeeBlueprint.objects.create(
        name="Cobrador", area=DigitalEmployeeBlueprint.Area.FINANCE,
        kpi_label="Dias médios de atraso", kpi_unit=KpiUnit.HOURS,
        kpi_direction=KpiDirection.DOWN,
    )
    project = ProjectFactory()

    resposta = _api().post(
        f"/api/v1/projects/{project.pk}/digital-employees/from-blueprint/",
        {"blueprint": blueprint.pk},
        format="json",
    )

    assert resposta.status_code == 201
    employee = DigitalEmployee.objects.get(pk=resposta.data["id"])
    assert employee.kpi_unit == KpiUnit.HOURS
    assert employee.kpi_direction == KpiDirection.DOWN


@pytest.mark.django_db
def test_instanciar_nao_grava_mais_baseline_e_o_ativo_nasce_sem_kpi():
    """A quebra deliberada da decisão C1 (ADR 0055): `kpi_baseline` deixou de ser aceito aqui.

    O que a substitui é o par `KPI`/`Measurement` — dois lugares escrevendo a mesma medição é o
    defeito que a fase inteira desfaz. A chave no corpo é **ignorada**, no molde dos três
    snapshots congelados do `Case`: não há caminho de escrita, em vez de haver um caminho que se
    combina não usar.
    """
    blueprint = DigitalEmployeeBlueprint.objects.create(name="SDR", kpi_unit=KpiUnit.COUNT)
    project = ProjectFactory()

    resposta = _api().post(
        f"/api/v1/projects/{project.pk}/digital-employees/from-blueprint/",
        {"blueprint": blueprint.pk, "kpi_baseline": "40.00"},
        format="json",
    )

    assert resposta.status_code == 201
    employee = DigitalEmployee.objects.get(pk=resposta.data["id"])
    assert employee.kpi_id is None
    # A chave continua saindo na `/api/v1/`, derivada — e sem KPI ela é `None`, nunca zero.
    assert resposta.data["kpi_baseline"] is None
    assert resposta.data["kpi_current"] is None
