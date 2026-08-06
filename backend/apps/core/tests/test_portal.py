from datetime import timedelta

import pytest
from django.test import override_settings
from django.urls import reverse
from django.utils import timezone
from rest_framework.test import APIClient

from apps.core import journey, portal
from apps.core.models import (
    AppSetting,
    DigitalEmployee,
    Document,
    Meeting,
    Milestone,
    Pendencia,
    Project,
    ProjectDeliverable,
    ProjectPhase,
)

from .factories import ProjectFactory


def _milestone(project: Project, status: str = Milestone.Status.TODO, days: int = 5) -> Milestone:
    return Milestone.objects.create(
        project=project,
        title="Marco",
        owner=project.owner,
        due_date=timezone.localdate() + timedelta(days=days),
        status=status,
    )


def test_sign_is_deterministic_hmac() -> None:
    assert portal.sign("segredo", b"corpo") == portal.sign("segredo", b"corpo")
    assert portal.sign("segredo", b"corpo") != portal.sign("outro", b"corpo")


@pytest.mark.django_db
def test_build_snapshot_projects_status_completion_and_children() -> None:
    project = ProjectFactory()
    _milestone(project, status=Milestone.Status.DONE)
    _milestone(project, status=Milestone.Status.TODO)
    archived = _milestone(project)
    archived.archive()
    Document.objects.create(
        project=project,
        original_name="plano.pdf",
        drive_link="http://drive/plano",
        uploaded_by=project.owner,
    )
    Meeting.objects.create(
        project=project, title="Kickoff", date=timezone.localdate(),
        recording_url="http://rec/1", transcript="ata", status=Meeting.Status.HELD,
    )
    Pendencia.objects.create(project=project, title="Aprovar escopo")  # status/party = defaults

    snapshot = portal.build_snapshot(project)

    assert snapshot["project"]["id"] == project.pk
    assert snapshot["project"]["client"]["name"] == project.client.name
    assert snapshot["completion"] == 50  # 1 de 2 marcos ativos concluído
    assert len(snapshot["milestones"]) == 2  # marco arquivado é excluído
    assert snapshot["milestones"][0]["party"] == "provider"
    # documentos com tipo (extensão) e autor (uploaded_by)
    assert snapshot["documents"][0]["name"] == "plano.pdf"
    assert snapshot["documents"][0]["type"] == "PDF"
    assert snapshot["documents"][0]["author"] == project.owner.username
    # reuniões / pendências
    assert snapshot["meetings"][0]["title"] == "Kickoff"
    assert snapshot["meetings"][0]["has_transcript"] is True
    assert snapshot["pendencias"][0]["title"] == "Aprovar escopo"
    # resultados derivados (client-safe, sem dado comercial)
    assert snapshot["resultados"]["conclusao_pct"] == 50
    assert snapshot["resultados"]["marcos_total"] == 2
    assert snapshot["resultados"]["marcos_done"] == 1
    assert "cost" not in snapshot["resultados"] and "actual_value" not in snapshot["resultados"]


@pytest.mark.django_db
def test_build_snapshot_completion_zero_without_milestones() -> None:
    snapshot = portal.build_snapshot(ProjectFactory())
    assert snapshot["completion"] == 0
    assert snapshot["milestones"] == []


@pytest.mark.django_db
def test_build_snapshot_projects_journey_and_roi() -> None:
    # actual_value = receita, cost = custo → ROI (receita - custo) / custo, client-safe.
    project = ProjectFactory(actual_value=1000, cost=250)
    journey.materialize_journey(project)  # cria as fases do template (seed 0015)
    first = ProjectPhase.objects.filter(project=project).order_by("phase__position").first()
    assert first is not None
    # marca um entregável da fase ativa como entregue ("desbloqueado")
    deliverable = first.deliverables.first()
    if deliverable is not None:
        deliverable.status = ProjectDeliverable.Status.DELIVERED
        deliverable.save()
    Meeting.objects.create(
        project=project, title="Revisão de fase",
        date=timezone.localdate() + timedelta(days=3), status=Meeting.Status.SCHEDULED,
    )

    snapshot = portal.build_snapshot(project)

    journey_block = snapshot["journey"]
    assert journey_block["current_phase"] == first.phase.name  # "Você está aqui"
    assert journey_block["phases"][0]["status"] == ProjectPhase.Status.ACTIVE
    assert journey_block["phases"][0]["name"] == first.phase.name
    if deliverable is not None:
        names = [d["name"] for d in journey_block["phases"][0]["deliverables"]]
        assert deliverable.name in names
    # ROI derivado, sem expor dado comercial cru fora deste bloco explícito
    assert snapshot["roi"] == {"revenue": 1000.0, "cost": 250.0, "net": 750.0, "roi": 3.0}
    assert snapshot["next_meeting"]["title"] == "Revisão de fase"
    # saúde amigável (sem score/sinais internos): projeto novo e sem atrasos → "No prazo"/verde
    assert snapshot["health"] == {"label": "No prazo", "level": "green"}
    # funcionários digitais do projeto (o produto central) fluem ao cliente pelo snapshot
    DigitalEmployee.objects.create(
        project=project, name="Agente Financeiro", area="Financeiro", status="active",
        kpi_label="Conciliação", kpi_value="80%", hours_saved_month="120.0", roi_month="14000.00",
    )
    refreshed = portal.build_snapshot(project)
    assert refreshed["digital_employees"][0]["name"] == "Agente Financeiro"
    assert refreshed["digital_employees"][0]["roi_month"] == 14000.0


@pytest.mark.django_db  # `emit` passou a consultar a flag, que lê o override em `AppSetting`
def test_emit_is_noop_when_not_configured(monkeypatch: pytest.MonkeyPatch) -> None:
    scheduled: list = []
    monkeypatch.setattr(portal.transaction, "on_commit", lambda fn: scheduled.append(fn))
    with override_settings(PORTAL_WEBHOOK_URL="", PORTAL_WEBHOOK_SECRET=""):
        portal.emit("updated", "project", 1)  # integração desligada
    with override_settings(PORTAL_WEBHOOK_URL="http://portal/hook", PORTAL_WEBHOOK_SECRET="s"):
        portal.emit("updated", "project", None)  # sem projeto
    assert scheduled == []


@pytest.mark.django_db
def test_emit_schedules_signed_delivery_when_configured(monkeypatch: pytest.MonkeyPatch) -> None:
    posted: dict[str, object] = {}

    def fake_post(url: str, body: bytes, signature: str) -> None:
        posted.update(url=url, body=body, signature=signature)

    class FakeThread:
        def __init__(self, target, args, daemon):  # type: ignore[no-untyped-def]
            self._target = target
            self._args = args

        def start(self) -> None:
            self._target(*self._args)

    callbacks: list = []
    monkeypatch.setattr(portal, "_post", fake_post)
    monkeypatch.setattr(portal.threading, "Thread", FakeThread)
    monkeypatch.setattr(portal.transaction, "on_commit", lambda fn: callbacks.append(fn))

    with override_settings(PORTAL_WEBHOOK_URL="http://portal/hook", PORTAL_WEBHOOK_SECRET="s3"):
        portal.emit("updated", "project", 7)

    assert len(callbacks) == 1
    callbacks[0]()  # dispara o que rodaria no on_commit
    assert posted["url"] == "http://portal/hook"
    assert posted["signature"] == portal.sign("s3", posted["body"])  # type: ignore[arg-type]


def test_post_sends_signed_request(monkeypatch: pytest.MonkeyPatch) -> None:
    seen: dict[str, object] = {}

    class FakeResponse:
        def __enter__(self) -> "FakeResponse":
            return self

        def __exit__(self, *args: object) -> bool:
            return False

        def read(self) -> bytes:
            return b""

    def fake_urlopen(request, timeout):  # type: ignore[no-untyped-def]
        seen["signature"] = request.get_header("X-biahflow-signature")
        seen["data"] = request.data
        return FakeResponse()

    monkeypatch.setattr(portal.urllib.request, "urlopen", fake_urlopen)
    portal._post("http://portal/hook", b"{}", "abc")
    assert seen["signature"] == "sha256=abc"
    assert seen["data"] == b"{}"


@pytest.mark.django_db
def test_saving_project_emits_webhook(monkeypatch: pytest.MonkeyPatch) -> None:
    calls: list[tuple] = []
    monkeypatch.setattr(portal, "emit", lambda *args: calls.append(args))
    project = ProjectFactory()
    _milestone(project)
    assert ("updated", "project", project.pk) in calls
    assert any(event == "milestone" for _, event, _ in calls)


@pytest.mark.django_db
def test_saving_meeting_and_pendencia_emit_webhook(monkeypatch: pytest.MonkeyPatch) -> None:
    calls: list[tuple] = []
    project = ProjectFactory()
    monkeypatch.setattr(portal, "emit", lambda *args: calls.append(args))
    Meeting.objects.create(project=project, title="Revisão", date=timezone.localdate())
    Pendencia.objects.create(project=project, title="Aprovar")
    assert ("updated", "meeting", project.pk) in calls
    assert ("updated", "pendencia", project.pk) in calls


@pytest.mark.django_db
def test_advancing_the_journey_emits_webhook(monkeypatch: pytest.MonkeyPatch) -> None:
    """A jornada é o que a barra "Você está aqui" do portal mostra — e mudava em silêncio.

    Avançar fase não salva o `Project`, então nenhum dos outros emissores cobria este caminho: a
    fase nova só chegava ao cliente de carona no próximo salvamento de outro objeto.
    """
    project = ProjectFactory()
    calls: list[tuple] = []
    monkeypatch.setattr(portal, "emit", lambda *args: calls.append(args))

    journey.advance_phase(project)

    assert ("updated", "project_phase", project.pk) in calls


@pytest.mark.django_db
def test_marking_a_deliverable_emits_webhook(monkeypatch: pytest.MonkeyPatch) -> None:
    project = ProjectFactory()
    deliverable = ProjectDeliverable.objects.filter(project_phase__project=project).first()
    assert deliverable is not None
    calls: list[tuple] = []
    monkeypatch.setattr(portal, "emit", lambda *args: calls.append(args))

    deliverable.status = ProjectDeliverable.Status.DELIVERED
    deliverable.save(update_fields=["status", "updated_at"])

    # O entregável chega ao projeto pela fase; se o caminho quebrar, o webhook sai sem projeto.
    assert ("updated", "project_deliverable", project.pk) in calls


@pytest.mark.django_db
def test_creating_a_project_does_not_flood_the_portal(monkeypatch: pytest.MonkeyPatch) -> None:
    """Um projeto novo vale **um** aviso, não um por fase e entregável materializados.

    `materialize_journey` cria as fases e os entregáveis num laço; emitir em cada `create` faria
    o portal buscar o snapshot inteiro dezenas de vezes pelo mesmo commit. Este teste é o que
    protege o guarda `created` de ser "simplificado" depois.
    """
    calls: list[tuple] = []
    monkeypatch.setattr(portal, "emit", lambda *args: calls.append(args))

    project = ProjectFactory()

    assert ProjectPhase.objects.filter(project=project).count() > 1  # houve materialização
    assert [event for _, event, _ in calls] == ["project"]


@pytest.mark.django_db
def test_snapshot_endpoint_requires_valid_token() -> None:
    project = ProjectFactory()
    client = APIClient()
    url = reverse("portal-project-snapshot", args=[project.pk])

    with override_settings(PORTAL_READ_TOKEN="token-secreto"):
        assert client.get(url).status_code == 401
        assert client.get(url, HTTP_AUTHORIZATION="Bearer errado").status_code == 401
        ok = client.get(url, HTTP_AUTHORIZATION="Bearer token-secreto")
        assert ok.status_code == 200
        assert ok.json()["project"]["id"] == project.pk


@pytest.mark.django_db
def test_ai_score_crosses_to_snapshot_only_after_review() -> None:
    project = ProjectFactory(
        ai_maturity=40, ai_opportunity=85,
        ai_dimensions=[{"label": "Dados", "score": 30}],
        ai_score_summary="Espaço para automação", ai_scored_at=timezone.now(),
    )
    # Rascunho (não revisado) não cruza ao cliente.
    assert portal.ai_score_snapshot(project) is None
    assert portal.build_snapshot(project)["ai_score"] is None

    project.ai_score_reviewed = True
    project.save(update_fields=["ai_score_reviewed"])
    ai_score = portal.build_snapshot(project)["ai_score"]
    assert ai_score == {
        "maturity": 40,
        "opportunity": 85,
        "dimensions": [{"label": "Dados", "score": 30}],
        "summary": "Espaço para automação",
        "scored_at": project.ai_scored_at.isoformat(),
    }


@pytest.mark.django_db
def test_snapshot_endpoint_denies_when_token_unset() -> None:
    project = ProjectFactory()
    client = APIClient()
    url = reverse("portal-project-snapshot", args=[project.pk])
    with override_settings(PORTAL_READ_TOKEN=""):
        assert client.get(url, HTTP_AUTHORIZATION="Bearer qualquer").status_code == 401


@pytest.mark.django_db
def test_emit_respeita_desligamento_pela_tela(monkeypatch: pytest.MonkeyPatch) -> None:
    """Desligar o portal em Configurações silencia a emissão sem passar por deploy (ADR 0018).

    Antes, `emit` relia as settings direto e ignorava o override — o portal seguia recebendo evento
    durante o incidente que motivou desligá-lo.
    """
    scheduled: list = []
    monkeypatch.setattr(portal.transaction, "on_commit", lambda fn: scheduled.append(fn))
    AppSetting.objects.create(key="portal", enabled=False)

    with override_settings(PORTAL_WEBHOOK_URL="http://portal/hook", PORTAL_WEBHOOK_SECRET="s"):
        portal.emit("updated", "project", 7)

    assert scheduled == []
