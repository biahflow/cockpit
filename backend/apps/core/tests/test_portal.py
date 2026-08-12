import json
from datetime import timedelta

import pytest
from django.db.models.signals import post_save
from django.test import override_settings
from django.urls import reverse
from django.utils import timezone
from rest_framework.test import APIClient

from apps.core import blueprints, journey, portal
from apps.core.models import (
    AppSetting,
    Artifact,
    Decisao,
    DigitalEmployee,
    DigitalEmployeeBlueprint,
    Document,
    Meeting,
    Milestone,
    Pendencia,
    Project,
    ProjectDeliverable,
    ProjectPhase,
    Vertical,
)

from .factories import ArtifactFactory, ClientFactory, OpportunityFactory, ProjectFactory


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


@pytest.mark.django_db
def test_snapshot_does_not_carry_the_internal_catalog() -> None:
    """O catálogo não cruza a fronteira do cliente — está em "Fora deste recorte" da FDD 026.

    O que o cliente vê é o Funcionário Digital dele, que a instanciação já **copiou**. Mandar junto
    o blueprint, a variante ou a vertical seria expor a biblioteca interna — e revisitar a ADR 0003,
    cujo snapshot é por projeto. Isso pede RFC, não uma emenda no `build_snapshot`.
    """
    vertical = Vertical.objects.create(name="Igrejas", slug="igrejas")
    project = ProjectFactory(client=ClientFactory(vertical=vertical))
    blueprint = DigitalEmployeeBlueprint.objects.create(name="SDR", description="Interno.")
    blueprints.instantiate(project, blueprint, vertical)

    snapshot = portal.build_snapshot(project)

    assert snapshot["digital_employees"][0]["name"] == "SDR"  # a cópia, sim
    serializado = json.dumps(snapshot, default=str)
    for chave in ("blueprint", "variant", "vertical", "Igrejas"):
        assert chave not in serializado


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
def test_saving_digital_employee_emits_webhook(monkeypatch: pytest.MonkeyPatch) -> None:
    """O roster é o produto central, e era o único item do snapshot sem emissor (ADR 0003).

    Cadastrar, mexer no KPI e arquivar um funcionário digital não avisavam o portal, então o painel
    "Seu Time Digital" do cliente só se corrigia de carona no próximo salvamento de outra coisa.
    Arquivar entra aqui porque `archive()` é um `save()` — e arquivado ele sai do snapshot, o que
    faz do arquivamento a mudança **mais** silenciosa das três.
    """
    project = ProjectFactory()
    calls: list[tuple] = []
    monkeypatch.setattr(portal, "emit", lambda *args: calls.append(args))

    employee = DigitalEmployee.objects.create(project=project, name="Ana Financeiro")
    assert ("updated", "digital_employee", project.pk) in calls

    calls.clear()
    employee.kpi_value = "312 notas/mês"
    employee.save(update_fields=["kpi_value", "updated_at"])
    assert ("updated", "digital_employee", project.pk) in calls

    calls.clear()
    employee.archive()
    assert ("updated", "digital_employee", project.pk) in calls


@pytest.mark.django_db
def test_snapshot_carries_the_date_of_the_first_accepted_artifact() -> None:
    """O degrau que o funil do portal declarava ausente por falta de produtor daqui.

    Sai a **primeira** aceitação e só o instante dela: o portal precisa de uma data para medir
    o time-to-first-value, e `kind`/`title`/`content` seriam dado comercial atravessando a
    fronteira que a ADR 0003 fecha.
    """
    project = ProjectFactory()
    primeiro = timezone.now() - timedelta(days=20)
    depois = timezone.now() - timedelta(days=3)
    ArtifactFactory(
        kind=Artifact.Kind.CONTRACT,
        opportunity=OpportunityFactory(client=project.client),
        status=Artifact.Status.ACCEPTED,
        decided_at=primeiro,
    )
    ArtifactFactory(
        project=project,
        opportunity=None,
        status=Artifact.Status.ACCEPTED,
        decided_at=depois,
    )

    snapshot = portal.build_snapshot(project)

    assert snapshot["artifact_accepted_at"] == primeiro.isoformat()
    # E nada além do instante: nem o texto que a IA redigiu, nem em que etapa comercial ele está.
    assert "artifacts" not in snapshot
    assert "Rascunho gerado" not in json.dumps(snapshot)


@pytest.mark.django_db
def test_an_artifact_still_awaiting_a_decision_is_not_a_rung() -> None:
    """`sent` é o que **nós** fizemos; o degrau é o que o cliente recebeu e aprovou.

    Recusado também não conta, e pela mesma razão — o funil mede valor recebido, não atividade.
    """
    project = ProjectFactory()
    ArtifactFactory(
        opportunity=OpportunityFactory(client=project.client),
        status=Artifact.Status.SENT,
    )
    ArtifactFactory(project=project, opportunity=None, status=Artifact.Status.REJECTED)

    assert portal.build_snapshot(project)["artifact_accepted_at"] is None


@pytest.mark.django_db
def test_an_archived_artifact_stops_counting_like_every_other_child() -> None:
    project = ProjectFactory()
    artifact = ArtifactFactory(
        project=project, opportunity=None, status=Artifact.Status.ACCEPTED
    )
    assert portal.build_snapshot(project)["artifact_accepted_at"] is not None

    artifact.archive()

    assert portal.build_snapshot(project)["artifact_accepted_at"] is None


@pytest.mark.django_db
def test_accepting_an_artifact_emits_webhook(monkeypatch: pytest.MonkeyPatch) -> None:
    """Aceitar avisa; rascunho, revisão e envio não.

    O caminho de verdade é o e-sign fechando o contrato sozinho quando o signatário assina, e
    ele é um `save()` — o mesmo motivo pelo qual `archive()` emite.
    """
    project = ProjectFactory()
    artifact = ArtifactFactory(project=project, opportunity=None, status=Artifact.Status.DRAFT)
    calls: list[tuple] = []
    monkeypatch.setattr(portal, "emit", lambda *args: calls.append(args))

    artifact.status = Artifact.Status.SENT
    artifact.save(update_fields=["status", "updated_at"])
    assert calls == []

    artifact.status = Artifact.Status.ACCEPTED
    artifact.save(update_fields=["status", "decided_at", "updated_at"])
    assert ("updated", "artifact", project.pk) in calls


@pytest.mark.django_db
def test_an_artifact_on_an_opportunity_names_the_clients_oldest_live_project(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """`emit` não faz nada sem `project_id`, e o contrato quase sempre vive na oportunidade.

    Um projeto só, nunca fan-out — o argumento é o mesmo do `post_delete` de `Project`.
    """
    client = ClientFactory()
    mais_velho = ProjectFactory(client=client)
    arquivado = ProjectFactory(client=client)
    arquivado.archive()
    ProjectFactory(client=client)  # vivo, porém mais novo
    calls: list[tuple] = []
    monkeypatch.setattr(portal, "emit", lambda *args: calls.append(args))

    ArtifactFactory(
        kind=Artifact.Kind.CONTRACT,
        opportunity=OpportunityFactory(client=client),
        status=Artifact.Status.ACCEPTED,
    )

    assert [pk for _, event, pk in calls if event == "artifact"] == [mais_velho.pk]


@pytest.mark.django_db
def test_accepting_before_any_project_exists_is_a_declared_limit(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Sem projeto não há o que nomear, e isso **não** pode estourar.

    É o caso típico do contrato: aceitá-lo é o que cria o projeto depois. O fato não se perde —
    `build_snapshot` calcula o campo sobre o cliente, então ele chega inteiro no primeiro
    snapshot depois que o projeto nascer.
    """
    calls: list[tuple] = []
    monkeypatch.setattr(portal, "emit", lambda *args: calls.append(args))

    ArtifactFactory(
        kind=Artifact.Kind.CONTRACT,
        opportunity=OpportunityFactory(client=ClientFactory()),
        status=Artifact.Status.ACCEPTED,
    )

    assert [pk for _, event, pk in calls if event == "artifact"] == [None]


@pytest.mark.django_db
def test_deleting_a_project_emits_once_even_with_children(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Exclusão definitiva é o único caminho que o arquivamento não cobre — e não avisava ninguém.

    Sem este sinal o portal ficava com um projeto morto marcado como **ativo** para sempre: nenhum
    webhook saía, e o próximo evento daquele projeto nunca viria, porque não há mais projeto.

    A segunda asserção é o que protege o desenho: a cascata apaga marcos, fases, entregáveis e
    funcionários digitais, e nenhum deles tem `post_delete` de propósito. Um por filho agendaria
    dezenas de buscas de snapshot — todas 404 — antes do aviso que interessa.
    """
    project = ProjectFactory()
    _milestone(project)
    DigitalEmployee.objects.create(project=project, name="Ana Financeiro")
    project_id = project.pk
    calls: list[tuple] = []
    monkeypatch.setattr(portal, "emit", lambda *args: calls.append(args))

    project.delete()

    assert calls == [("deleted", "project", project_id)]


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
def test_snapshot_serve_projeto_arquivado_declarando_o_arquivamento() -> None:
    """Arquivar não pode fazer o projeto sumir desta rota — só declarar que acabou.

    Arquivar emite webhook (o `archive()` é um `save()`), e o portal vem buscar o estado novo.
    Enquanto esta rota filtrava `archived_at__isnull=True`, ele levava 404 — que não distingue
    "acabou" de "nunca existiu" — e mantinha na tela do cliente, como ativo, um projeto encerrado.
    """
    project = ProjectFactory()
    client = APIClient()
    url = reverse("portal-project-snapshot", args=[project.pk])

    with override_settings(PORTAL_READ_TOKEN="token-secreto"):
        ativo = client.get(url, HTTP_AUTHORIZATION="Bearer token-secreto")
        assert ativo.status_code == 200
        assert ativo.json()["project"]["archived_at"] is None

        project.archive()
        arquivado = client.get(url, HTTP_AUTHORIZATION="Bearer token-secreto")
        assert arquivado.status_code == 200
        project.refresh_from_db()
        assert arquivado.json()["project"]["archived_at"] == project.archived_at.isoformat()

        # E o caminho de volta, que a interface oferece por item (`POST /unarchive/`).
        project.archived_at = None
        project.save(update_fields=["archived_at", "updated_at"])
        restaurado = client.get(url, HTTP_AUTHORIZATION="Bearer token-secreto")
        assert restaurado.json()["project"]["archived_at"] is None

        # 404 continua existindo, e agora quer dizer uma coisa só.
        ausente = reverse("portal-project-snapshot", args=[project.pk + 10_000])
        assert client.get(ausente, HTTP_AUTHORIZATION="Bearer token-secreto").status_code == 404


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


# --- A guarda que o funcionário digital custou -------------------------------
#
# A regra é da ADR 0003 e está escrita há meses: *"o que entra no snapshot precisa de emissor, sob
# pena de o portal exibir um estado que já mudou"*. O que **verificava** a regra eram seis asserções
# escritas à mão (as de cima) contra dezesseis chaves — e foi assim que `digital_employees` ficou no
# snapshot sem emissor nenhum até 07/08/2026. Não foi o CI que achou: foi alguém lendo o código a
# partir do outro repositório.
#
# É a forma exata das ADRs 0033 e 0035 do portal do cliente — guardas que eram, elas próprias,
# listas digitadas —, deste lado da fronteira. Os dois lados são derivados: as chaves saem do
# snapshot de verdade, e os emissores saem do **registro do Django**, não de um grep no arquivo.
# Grep casaria um comentário; `_live_receivers` casa o que vai rodar.

#: Chave do snapshot → o modelo cujo `save()` a muda. É o único mapa escrito à mão desta guarda, e
#: ele é sobre *domínio*, não sobre implementação: dizer que `documents` vem de `Document` é a
#: informação que nenhuma introspecção tem como descobrir.
_MODELO_DA_CHAVE = {
    "documents": Document,
    "meetings": Meeting,
    "pendencias": Pendencia,
    "decisions": Decisao,
    "milestones": Milestone,
    "digital_employees": DigitalEmployee,
}

#: Chaves sem emissor próprio, e o motivo de cada uma. Allowlist com razão escrita, na forma do
#: `NOT_AN_ALERT` do outro repositório: entrada sem motivo é a lista digitada voltando pela porta
#: dos fundos.
_DERIVADA_DE = {
    "project": "o próprio projeto, coberto por `_emit_project`",
    "completion": "derivada dos marcos; muda quando um `Milestone` salva",
    "health": "derivada dos marcos e do projeto",
    "roi": "derivado dos marcos e do valor do projeto",
    "resultados": "derivado dos marcos",
    "journey": "derivada de `ProjectPhase`/`ProjectDeliverable`, que têm emissor próprio",
    "next_meeting": "derivada de `Meeting`, que tem emissor próprio",
    "ai_score": "colunas do próprio `Project`, cobertas por `_emit_project`",
    "artifact_accepted_at": "derivada de `Artifact`, que tem emissor desde a FDD 031",
}


def _tem_emissor(model: type) -> bool:
    """Existe um receiver de `post_save` para este modelo que avisa o portal?

    Derivado do registro do Django (`_live_receivers`) e não do texto de `signals.py`: um grep
    encontraria a palavra num comentário, e um receiver desconectado continuaria "passando".

    O `_live_receivers` do Django 5 devolve **dois** grupos, síncronos e assíncronos — medido, não
    suposto. Somamos os dois: um emissor assíncrono continua sendo um emissor.
    """
    sincronos, assincronos = post_save._live_receivers(model)
    return any(
        getattr(receiver, "__name__", "").startswith("_emit_")
        for receiver in (*sincronos, *assincronos)
    )


@pytest.mark.django_db
def test_every_snapshot_key_has_an_emitter() -> None:
    """Toda chave do snapshot tem quem avise o portal que ela mudou.

    Que ela não nasce verde por acidente está no histórico do próprio repositório: rodada contra o
    estado de 06/08/2026, ela reprovaria com `digital_employees` — o defeito exato que a emenda de
    07/08 corrigiu à mão, sem deixar guarda atrás.
    """
    snapshot = portal.build_snapshot(ProjectFactory())

    desconhecidas = set(snapshot) - set(_MODELO_DA_CHAVE) - set(_DERIVADA_DE)
    assert not desconhecidas, (
        f"chave(s) nova(s) no snapshot: {sorted(desconhecidas)}. Diga de qual modelo ela vem em "
        "`_MODELO_DA_CHAVE`, ou de qual emissor ela é derivada em `_DERIVADA_DE`. Uma chave que "
        "ninguém avisa faz o portal exibir um estado que já mudou (ADR 0003)."
    )

    orfas = [chave for chave, model in _MODELO_DA_CHAVE.items() if not _tem_emissor(model)]
    assert not orfas, (
        f"chave(s) de snapshot sem emissor: {sorted(orfas)}. Registre um `post_save` em signals.py."
    )


@pytest.mark.django_db
def test_the_guard_lists_do_not_keep_a_key_that_stopped_existing() -> None:
    """As duas listas envelhecem junto, senão viram a lista digitada que esta guarda mata."""
    snapshot = portal.build_snapshot(ProjectFactory())
    obsoletas = (set(_MODELO_DA_CHAVE) | set(_DERIVADA_DE)) - set(snapshot)
    assert not obsoletas, f"a guarda guarda chave que não existe mais no snapshot: {sorted(obsoletas)}"


# --- Decisões no snapshot (FDD 032) -------------------------------------------


@pytest.mark.django_db
def test_snapshot_carries_published_decisions_only() -> None:
    """O rascunho é interno, e é esse filtro que faz a extração por IA ser aceitável.

    Sem ele, um palpite de modelo chegaria à tela do cliente antes de qualquer pessoa olhar — que é
    a razão de o estado existir neste modelo.
    """
    project = ProjectFactory()
    meeting = Meeting.objects.create(
        project=project, title="Comitê", date=timezone.localdate(), transcript="ata"
    )
    Decisao.objects.create(project=project, title="Rascunho da IA", source_meeting=meeting)
    Decisao.objects.create(
        project=project,
        title="Adotar fila gerenciada",
        rationale="Memorystore custa mais que o volume previsto.",
        decided_by="Marina (cliente)",
        decided_on=timezone.localdate(),
        status=Decisao.Status.PUBLISHED,
        source_meeting=meeting,
    )

    decisions = portal.build_snapshot(project)["decisions"]
    assert [d["title"] for d in decisions] == ["Adotar fila gerenciada"]
    assert decisions[0]["rationale"] == "Memorystore custa mais que o volume previsto."
    assert decisions[0]["decided_by"] == "Marina (cliente)"
    # A pk da reunião, que é como o portal recasa a proveniência com o que ele espelhou.
    assert decisions[0]["meeting_id"] == meeting.pk


@pytest.mark.django_db
def test_an_archived_decision_stops_counting_like_every_other_child() -> None:
    project = ProjectFactory()
    decisao = Decisao.objects.create(
        project=project, title="Adotar fila gerenciada", status=Decisao.Status.PUBLISHED
    )
    assert portal.build_snapshot(project)["decisions"] != []
    decisao.archive()
    assert portal.build_snapshot(project)["decisions"] == []


@pytest.mark.django_db
def test_saving_publishing_and_archiving_a_decision_all_emit(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Os três caminhos, e o terceiro é o que mais importa.

    Arquivar tira a decisão do snapshot sem criar linha nenhuma: é a mudança mais silenciosa das
    três, e é exatamente a que o funcionário digital não avisava. `archive()` é um `save()`, então
    o receiver sem guarda de `created` cobre os três de uma vez.
    """
    calls: list[tuple] = []
    project = ProjectFactory()
    monkeypatch.setattr(portal, "emit", lambda *args: calls.append(args))

    decisao = Decisao.objects.create(project=project, title="Adotar fila gerenciada")
    assert ("updated", "decisao", project.pk) in calls

    calls.clear()
    decisao.status = Decisao.Status.PUBLISHED
    decisao.save()
    assert ("updated", "decisao", project.pk) in calls

    calls.clear()
    decisao.archive()
    assert ("updated", "decisao", project.pk) in calls
