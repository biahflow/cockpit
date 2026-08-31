from datetime import timedelta

import pytest
from django.urls import reverse
from django.utils import timezone
from rest_framework.test import APIClient

from apps.core import health
from apps.core.models import Meeting, Pendencia, Satisfacao, Task, WorkItem

from .factories import AccountFactory, ProjectFactory, UserFactory


@pytest.mark.django_db
def test_health_is_full_and_clean_when_project_is_healthy():
    project = ProjectFactory(
        start_date=timezone.localdate(),
        due_date=timezone.localdate() + timedelta(days=60),
        status="active",
    )
    result = health.assess_project_health(project)
    assert result["score"] == 100
    assert result["level"] == "saudável"
    assert result["signals"] == []


@pytest.mark.django_db
def test_health_drops_on_overdue_and_missed_meetings_and_pendencias():
    project = ProjectFactory()
    Task.objects.create(
        project=project, title="Atrasada", owner=project.owner,
        due_date=timezone.localdate() - timedelta(days=2),
    )
    Meeting.objects.create(
        project=project, title="Alinhamento", date=timezone.localdate() - timedelta(days=1),
        status=Meeting.Status.SCHEDULED,
    )
    Pendencia.objects.create(project=project, title="Aprovar acesso", party=WorkItem.Party.CLIENT)

    result = health.assess_project_health(project)

    labels = [signal["label"] for signal in result["signals"]]
    assert "Entregas atrasadas" in labels
    assert "Reuniões não realizadas" in labels
    assert "Decisões pendentes" in labels
    decisao = next(s for s in result["signals"] if s["label"] == "Decisões pendentes")
    assert "cliente" in decisao["detail"]  # peso extra quando o cliente é quem trava
    assert result["score"] < 100
    assert result["level"] in {"saudável", "atenção", "crítico"}


@pytest.mark.django_db
def test_health_penalizes_negative_roi():
    project = ProjectFactory(actual_value=100, cost=300)  # custo acima do entregue
    result = health.assess_project_health(project)
    assert "ROI negativo" in [signal["label"] for signal in result["signals"]]


# --- O sexto sinal: a satisfação do cliente (FDD 037) -------------------------


def _satisfacao(project, **kwargs):  # type: ignore[no-untyped-def]
    campos = {
        "account": project.engagement.account,
        "nivel": Satisfacao.Nivel.INSATISFEITO,
        "fonte": Satisfacao.Fonte.DECLARADA,
        "happened_on": timezone.localdate(),
        "note": "Reclamou do atraso do marco 2 na call de sexta.",
    }
    campos.update(kwargs)
    return Satisfacao.objects.create(**campos)


@pytest.mark.django_db
def test_health_penalizes_declared_dissatisfaction():
    project = ProjectFactory()
    _satisfacao(project)

    result = health.assess_project_health(project)

    sinal = next(s for s in result["signals"] if s["label"] == "Cliente insatisfeito")
    assert sinal["weight"] == 20
    assert result["score"] == 80


@pytest.mark.django_db
@pytest.mark.parametrize(
    "nivel",
    [Satisfacao.Nivel.PROMOTOR, Satisfacao.Nivel.SATISFEITO, Satisfacao.Nivel.NEUTRO],
)
def test_only_dissatisfaction_moves_the_score(nivel):
    """Promotor **não soma**: o escore parte de 100 e só subtrai, e um sinal que somasse faria
    "100" deixar de significar "nenhum problema conhecido"."""
    project = ProjectFactory()
    _satisfacao(project, nivel=nivel, note="")

    result = health.assess_project_health(project)

    assert result["score"] == 100
    assert result["signals"] == []


@pytest.mark.django_db
@pytest.mark.parametrize(("dias", "esperado"), [(89, 80), (91, 100)])
def test_the_signal_ages_out_of_the_window(dias, esperado):
    project = ProjectFactory()
    _satisfacao(project, happened_on=timezone.localdate() - timedelta(days=dias))

    assert health.assess_project_health(project)["score"] == esperado


@pytest.mark.django_db
def test_dissatisfaction_of_another_client_does_not_touch_this_project():
    project = ProjectFactory()
    _satisfacao(ProjectFactory())

    assert health.assess_project_health(project)["score"] == 100


@pytest.mark.django_db
def test_preloaded_empty_sequence_means_no_record_not_go_to_the_database():
    """`[]` diz "nenhuma" e `None` diz "consulte o banco" — é essa distinção que mantém o lote
    com contagem constante de queries."""
    project = ProjectFactory()
    _satisfacao(project)

    assert health.assess_project_health(project, satisfacoes=[])["signals"] == []
    assert health.assess_project_health(project)["signals"] != []


@pytest.mark.django_db
def test_health_endpoint_lists_worst_first():
    saudavel = ProjectFactory(
        start_date=timezone.localdate(), due_date=timezone.localdate() + timedelta(days=60), status="active",
    )
    critico = ProjectFactory(status="active")
    for index in range(3):
        Task.objects.create(
            project=critico, title=f"Atraso {index}", owner=critico.owner,
            due_date=timezone.localdate() - timedelta(days=5),
        )

    client = APIClient()
    client.force_authenticate(UserFactory())
    response = client.get(reverse("health"))

    assert response.status_code == 200
    projects = response.json()["projects"]
    ids = [row["project_id"] for row in projects]
    assert ids.index(critico.pk) < ids.index(saudavel.pk)  # pior primeiro


@pytest.mark.django_db
def test_client_overview_aggregates_health_phase_roi_and_next_meeting():
    client_obj = AccountFactory(lifecycle_status="active")
    project = ProjectFactory(engagement__account=client_obj, status="active", actual_value=1000, cost=250)
    Task.objects.create(
        project=project, title="Atraso", owner=project.owner,
        due_date=timezone.localdate() - timedelta(days=3),
    )
    Meeting.objects.create(
        project=project, title="Revisão", date=timezone.localdate() + timedelta(days=5),
        status=Meeting.Status.SCHEDULED,
    )

    api = APIClient()
    api.force_authenticate(UserFactory())
    response = api.get(reverse("client-overview-detail", args=[client_obj.pk]))

    assert response.status_code == 200
    data = response.json()
    assert data["client_id"] == client_obj.pk
    assert data["lifecycle_status"] == data["status"] == "active"
    assert data["health"]["level"] in {"saudável", "atenção", "crítico"}
    assert data["health"]["score"] < 100  # há item atrasado
    assert data["risk_level"] in {"baixo", "médio", "alto"}
    assert data["roi"]["roi"] == 3.0  # (1000 - 250) / 250
    assert data["next_meeting"]["title"] == "Revisão"


@pytest.mark.django_db
def test_client_overview_includes_reviewed_ai_score():
    client_obj = AccountFactory(lifecycle_status="active")
    ProjectFactory(
        engagement__account=client_obj, status="active",
        ai_maturity=35, ai_potential=80, ai_dimensions=[{"label": "Dados", "score": 30}],
        ai_score_summary="ok", ai_scored_at=timezone.now(), ai_score_reviewed=True,
    )
    # Projeto com rascunho não revisado não deve entrar.
    ProjectFactory(engagement__account=client_obj, status="active", ai_maturity=99, ai_scored_at=timezone.now())

    api = APIClient()
    api.force_authenticate(UserFactory())
    response = api.get(reverse("client-overview-detail", args=[client_obj.pk]))

    assert response.status_code == 200
    assert response.json()["ai_score"]["maturity"] == 35


@pytest.mark.django_db
def test_client_overview_is_blank_for_prospect_without_projects():
    prospect = AccountFactory(lifecycle_status="prospect")
    api = APIClient()
    api.force_authenticate(UserFactory())
    response = api.get(reverse("client-overview-detail", args=[prospect.pk]))
    assert response.status_code == 200
    assert response.json()["health"] is None
