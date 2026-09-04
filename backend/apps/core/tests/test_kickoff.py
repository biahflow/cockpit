import logging
from datetime import timedelta

import pytest
from django.test import override_settings
from django.utils import timezone

from apps.core import kickoff, whatsapp
from apps.core.models import Contact, Milestone, Notification, Project, Service, Task

from .factories import ProjectFactory, ServiceFactory, UserFactory


@pytest.mark.django_db
def test_seed_work_items_creates_schedule_within_window():
    owner = UserFactory()
    project = ProjectFactory(owner=owner, start_date=timezone.localdate(),
                             due_date=timezone.localdate() + timedelta(days=120))

    milestones, tasks = kickoff.seed_work_items(project)

    assert milestones == len(kickoff.KICKOFF_TEMPLATE)
    assert tasks == sum(len(spec["tasks"]) for spec in kickoff.KICKOFF_TEMPLATE)
    created = Milestone.objects.filter(project=project)
    assert created.count() == milestones
    assert all(m.owner_id == owner.id for m in created)
    assert all(project.start_date <= m.due_date <= project.due_date for m in created)
    assert all(t.milestone_id is not None for t in Task.objects.filter(project=project))


@pytest.mark.django_db
def test_seed_work_items_clamps_due_dates_to_short_window():
    project = ProjectFactory(start_date=timezone.localdate(),
                             due_date=timezone.localdate() + timedelta(days=3))
    kickoff.seed_work_items(project)
    assert all(m.due_date <= project.due_date for m in Milestone.objects.filter(project=project))


@pytest.mark.django_db
def test_qualification_call_gets_the_short_schedule():
    project = ProjectFactory(service=Service.objects.get(tier=Service.Tier.QUALIFICATION_CALL))

    milestones, _ = kickoff.seed_work_items(project)

    assert milestones == 1
    assert Milestone.objects.get(project=project).title == "Qualification Call"


@pytest.mark.django_db
def test_discovery_sprint_ends_in_the_executive_readout():
    """Sprint pago sem readout é trabalho feito que ninguém viu (ADR 0030)."""
    project = ProjectFactory(service=Service.objects.get(tier=Service.Tier.DISCOVERY_SPRINT))

    milestones, _ = kickoff.seed_work_items(project)

    assert milestones == len(kickoff.KICKOFF_TEMPLATES["discovery_sprint"])
    titles = list(Milestone.objects.filter(project=project).order_by("due_date")
                  .values_list("title", flat=True))
    assert titles[-1] == "Executive Readout"
    tasks = list(Task.objects.filter(project=project).values_list("title", flat=True))
    assert "Calcular o Opportunity Score de cada processo" in tasks


@pytest.mark.django_db
def test_feasibility_sets_the_target_before_running_the_sample():
    """Critério definido depois do resultado não é critério, é narrativa (ADR 0030)."""
    project = ProjectFactory(service=Service.objects.get(tier=Service.Tier.FEASIBILITY))

    milestones, _ = kickoff.seed_work_items(project)

    assert milestones == len(kickoff.KICKOFF_TEMPLATES["feasibility"])
    tasks = list(Task.objects.filter(project=project).values_list("title", flat=True))
    assert "Definir a meta **antes** de rodar a amostra" in tasks
    assert "Registrar o gate (GO / CONDITIONAL GO / REDESIGN / NO-GO)" in tasks


@pytest.mark.django_db
def test_discovery_sprint_fecha_em_executive_readout():
    project = ProjectFactory(service=Service.objects.get(tier=Service.Tier.DISCOVERY_SPRINT))

    milestones, _ = kickoff.seed_work_items(project)

    assert milestones == 3
    titles = list(Milestone.objects.filter(project=project).values_list("title", flat=True))
    assert "Executive Readout" in titles


@pytest.mark.django_db
def test_prove_gets_the_baseline_and_the_decision_gate():
    # ADR 0030: baseline/critérios antes de construir e o decision gate no encerramento
    # fazem parte do cronograma semeado.
    project = ProjectFactory(service=Service.objects.get(tier=Service.Tier.PROVE))

    milestones, _ = kickoff.seed_work_items(project)

    assert milestones == len(kickoff.KICKOFF_TEMPLATES["prove"])
    tasks = list(Task.objects.filter(project=project).values_list("title", flat=True))
    assert "Registrar o baseline e os critérios de sucesso antes de construir" in tasks
    assert "Registrar a decisão SCALE / ITERATE / STOP" in tasks


@pytest.mark.django_db
def test_project_without_tier_falls_back_to_the_default_schedule():
    without_service = ProjectFactory()
    loose_service = ProjectFactory(service=ServiceFactory())

    assert kickoff.template_for(without_service) is kickoff.KICKOFF_TEMPLATE
    assert kickoff.template_for(loose_service) is kickoff.KICKOFF_TEMPLATE


@pytest.mark.django_db
def test_finalize_sends_email_and_notifies_owner(mailoutbox):
    owner = UserFactory(email="dono@example.test")
    project = ProjectFactory(owner=owner)

    kickoff.finalize(project)

    # Saem dois e-mails desde a ADR 0018: o do kickoff, que ignora a flag `email` por ser parte do
    # fluxo e não notificação, e o da própria notificação, que passou a ser ligada por padrão. O que
    # este teste garante é o primeiro — daí procurá-lo pelo assunto em vez de contar a caixa.
    kickoff_mail = next(mail for mail in mailoutbox if project.name in mail.subject)
    assert kickoff_mail.to == ["dono@example.test"]
    assert Notification.objects.filter(user=owner, kind="kickoff").count() == 1


@pytest.mark.django_db
def test_finalize_skips_email_without_owner_address(mailoutbox):
    owner = UserFactory(email="")
    project = ProjectFactory(owner=owner)

    kickoff.finalize(project)

    assert len(mailoutbox) == 0
    assert Notification.objects.filter(user=owner, kind="kickoff").count() == 1


# --- O grupo do cliente no WhatsApp (issue #110) -----------------------------------------------
#
# O adaptador de WhatsApp existia inteiro e **sem um único chamador** — nascer sem chamador e ficar
# sem chamador são a mesma dívida. O chamador é o kickoff: ao nascer o projeto, a casa abre o grupo
# do cliente e guarda a referência no projeto.

LIGADO_NO_WHATSAPP = override_settings(
    WHATSAPP_ENABLED=True,
    WHATSAPP_PROVIDERS="zapi",
    WHATSAPP_ZAPI_INSTANCE_ID="inst",
    WHATSAPP_ZAPI_TOKEN="tok",
)


class GrupoFalso:
    """Substitui `whatsapp.create_group`; guarda o que foi pedido. Nada toca a rede (ADR 0059)."""

    def __init__(self, resultado: whatsapp.GroupResult | None = None) -> None:
        self.resultado = resultado or whatsapp.GroupResult(
            whatsapp.Delivery.DELIVERED,
            provider="zapi",
            group_id="120363431743499021@g.us",
            invite_url="https://chat.whatsapp.com/GONwbGG",
        )
        self.calls: list[tuple[str, list[str]]] = []

    def __call__(self, name: str, participants) -> whatsapp.GroupResult:
        self.calls.append((name, list(participants)))
        return self.resultado


@pytest.fixture
def grupo(monkeypatch: pytest.MonkeyPatch):
    def instalar(resultado: whatsapp.GroupResult | None = None) -> GrupoFalso:
        fake = GrupoFalso(resultado)
        monkeypatch.setattr(whatsapp, "create_group", fake)
        return fake

    return instalar


def _projeto_com_contatos(*, tier: str | None = Service.Tier.DISCOVERY_SPRINT) -> Project:
    service = Service.objects.get(tier=tier) if tier else None
    project = ProjectFactory(service=service)
    conta = project.engagement.account
    Contact.objects.create(account=conta, first_name="Ana", phone="+55 11 99999-0001")
    Contact.objects.create(account=conta, first_name="Bruno", phone="5511999990002")
    return project


@pytest.mark.django_db
@LIGADO_NO_WHATSAPP
def test_o_kickoff_abre_o_grupo_do_cliente_e_guarda_a_referencia(grupo):
    chamadas = grupo()
    project = _projeto_com_contatos()

    kickoff.finalize(project)

    project.refresh_from_db()
    assert project.whatsapp_group_id == "120363431743499021@g.us"
    assert project.whatsapp_group_invite_url == "https://chat.whatsapp.com/GONwbGG"
    nome, participantes = chamadas.calls[0]
    assert nome == f"{project.engagement.account.name} · {project.name}"
    assert participantes == ["+55 11 99999-0001", "5511999990002"]


@pytest.mark.django_db
@LIGADO_NO_WHATSAPP
def test_a_qualification_call_nao_ganha_grupo(grupo):
    """Conversa de trinta a quarenta e cinco minutos não precisa de canal dedicado."""
    chamadas = grupo()
    project = _projeto_com_contatos(tier=Service.Tier.QUALIFICATION_CALL)

    kickoff.finalize(project)

    project.refresh_from_db()
    assert chamadas.calls == []
    assert project.whatsapp_group_id == ""


@pytest.mark.django_db
@LIGADO_NO_WHATSAPP
def test_sem_nenhum_telefone_o_grupo_nao_e_criado_e_o_motivo_fica_no_log(grupo, caplog):
    """O "cala quando não sabe" de `receives_billing`: sem telefone não há grupo a criar."""
    chamadas = grupo()
    project = ProjectFactory(service=Service.objects.get(tier=Service.Tier.DISCOVERY_SPRINT))
    Contact.objects.create(account=project.engagement.account, first_name="Sem", phone="")

    with caplog.at_level(logging.INFO, logger="apps.core.kickoff"):
        kickoff.finalize(project)

    assert chamadas.calls == []
    assert any("telefone" in registro.message for registro in caplog.records)


@pytest.mark.django_db
@LIGADO_NO_WHATSAPP
def test_contato_arquivado_nao_entra_no_grupo_do_cliente(grupo):
    """`archive()` é como a casa demite um contato; arquivado no grupo é acesso não pretendido."""
    chamadas = grupo()
    project = _projeto_com_contatos()
    demitido = Contact.objects.create(
        account=project.engagement.account, first_name="Carla", phone="5511999990003"
    )
    demitido.archive()

    kickoff.finalize(project)

    assert "5511999990003" not in chamadas.calls[0][1]


@pytest.mark.django_db
@LIGADO_NO_WHATSAPP
def test_projeto_sem_servico_ganha_grupo(grupo):
    """O default é ganhar: serviço avulso é trabalho de entrega de verdade."""
    chamadas = grupo()
    project = _projeto_com_contatos(tier=None)

    kickoff.finalize(project)

    assert len(chamadas.calls) == 1


@pytest.mark.django_db
@LIGADO_NO_WHATSAPP
def test_finalize_duas_vezes_cria_um_grupo_so(grupo):
    """`finalize` é best-effort e pode ser reexecutado — sem a guarda, nasce o **segundo** grupo.

    É literalmente o erro caro que a issue #111 nomeia, e aqui ele chegaria ao cliente: duas
    janelas de conversa com o mesmo nome, e ninguém sabendo em qual falar.
    """
    chamadas = grupo()
    project = _projeto_com_contatos()

    kickoff.finalize(project)
    kickoff.finalize(project)

    assert len(chamadas.calls) == 1
    project.refresh_from_db()
    assert project.whatsapp_group_id == "120363431743499021@g.us"


@pytest.mark.django_db
@LIGADO_NO_WHATSAPP
def test_o_convite_entra_no_email_e_na_notificacao_quando_existe(grupo, mailoutbox):
    grupo()
    project = _projeto_com_contatos()

    kickoff.finalize(project)

    kickoff_mail = next(mail for mail in mailoutbox if project.name in mail.subject)
    assert "https://chat.whatsapp.com/GONwbGG" in kickoff_mail.body
    aviso = Notification.objects.get(user=project.owner, kind="kickoff")
    assert "https://chat.whatsapp.com/GONwbGG" in aviso.message


@pytest.mark.django_db
@LIGADO_NO_WHATSAPP
def test_sem_grupo_o_email_e_a_notificacao_nao_mencionam_grupo_nenhum(grupo, mailoutbox):
    """"Grupo: —" seria pior que o silêncio: anuncia um canal e não entrega nenhum."""
    grupo(whatsapp.GroupResult(whatsapp.Delivery.UNCERTAIN, provider="zapi", detail="timeout"))
    project = _projeto_com_contatos()

    kickoff.finalize(project)

    project.refresh_from_db()
    assert project.whatsapp_group_id == ""
    kickoff_mail = next(mail for mail in mailoutbox if project.name in mail.subject)
    assert "Grupo" not in kickoff_mail.body
    aviso = Notification.objects.get(user=project.owner, kind="kickoff")
    assert "Grupo" not in aviso.message


@pytest.mark.django_db
def test_com_a_flag_desligada_o_kickoff_nao_procura_grupo(grupo):
    chamadas = grupo()
    project = _projeto_com_contatos()

    kickoff.finalize(project)

    assert chamadas.calls == []


@pytest.mark.django_db
@LIGADO_NO_WHATSAPP
def test_uncertain_avisa_o_dono_do_projeto_pela_fila_do_produto(grupo):
    """A dívida que a ADR 0062 nomeou: `UNCERTAIN` pós-reconciliação (ADR 0064) tem destinatário.

    O fato e a saída, na mesma mensagem — avisar sem dizer o que fazer transfere o problema sem
    transferir a solução (issue #117).
    """
    grupo(whatsapp.GroupResult(whatsapp.Delivery.UNCERTAIN, provider="zapi", detail="timeout"))
    project = _projeto_com_contatos()

    kickoff.finalize(project)

    aviso = Notification.objects.get(user=project.owner, kind="whatsapp")
    assert "ficou incerta" in aviso.message
    assert "Confira a lista de grupos" in aviso.message
    assert aviso.url == f"/projetos/{project.id}"
    # A notificação de kickoff continua existindo, uma só, e sem mencionar grupo — o teste das
    # linhas 294-307 já cobre isso; aqui confirmamos que ele segue verde com o kind novo ao lado.
    kickoff_notif = Notification.objects.get(user=project.owner, kind="kickoff")
    assert "Grupo" not in kickoff_notif.message


@pytest.mark.django_db
@LIGADO_NO_WHATSAPP
@pytest.mark.parametrize("status", [whatsapp.Delivery.REFUSED, whatsapp.Delivery.UNAVAILABLE])
def test_falha_certa_nao_avisa_o_dono_do_projeto(grupo, status):
    """Certeza de não-entrega não cria grupo órfão — só `UNCERTAIN` avisa (issue #117).

    O enum não tem um estado `FAILED`; `REFUSED` e `UNAVAILABLE` são os dois estados terminais de
    não-entrega inequívoca que o spec de handoff nomeava por esse rótulo informal.
    """
    grupo(whatsapp.GroupResult(status, provider="zapi", detail="recusado"))
    project = _projeto_com_contatos()

    kickoff.finalize(project)

    assert not Notification.objects.filter(user=project.owner, kind="whatsapp").exists()


@pytest.mark.django_db
@LIGADO_NO_WHATSAPP
def test_delivered_nao_avisa_o_dono_do_projeto(grupo):
    grupo()
    project = _projeto_com_contatos()

    kickoff.finalize(project)

    assert not Notification.objects.filter(user=project.owner, kind="whatsapp").exists()
