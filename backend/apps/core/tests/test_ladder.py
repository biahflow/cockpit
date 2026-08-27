"""A escada FDE da conta (FDD 042): materialização, transição append-only e as recusas.

O oráculo destes testes é `docs/metodologia-fde.md`, não o gosto de quem escreve: a escada tem
seis degraus nessa ordem, só o Feasibility é condicional, e um degrau fecha por decisão registrada.
"""

from __future__ import annotations

from datetime import timedelta

import pytest
from django.test import override_settings
from django.utils import timezone

from apps.core import ladder
from apps.core.exceptions import StateConflict
from apps.core.models import AccountRung, AccountRungEvent, FdeRung, User

from .factories import ClientFactory, ProjectFactory, ProjectMemberFactory, UserFactory


@pytest.mark.django_db
def test_a_conta_nasce_com_os_seis_degraus_na_ordem_do_documento() -> None:
    """`ClientFactory` dispara o signal; os seis chegam `not_sold` e na ordem da doutrina."""
    client = ClientFactory()

    degraus = list(AccountRung.objects.filter(client=client))

    assert [degrau.rung for degrau in degraus] == [
        "discover", "prioritize", "feasibility", "prove", "scale", "optimize"
    ]
    assert {degrau.status for degrau in degraus} == {AccountRung.Status.NOT_SOLD}
    # Materializar não é decisão sobre a conta: o histórico nasce vazio, e é o que sustenta a
    # copy "Nenhuma decisão registrada" do degrau não vendido.
    assert AccountRungEvent.objects.count() == 0


@pytest.mark.django_db
def test_materializacao_e_idempotente() -> None:
    client = ClientFactory()

    ladder.materialize_ladder(client)
    ladder.materialize_ladder(client)

    assert AccountRung.objects.filter(client=client).count() == 6


@pytest.mark.django_db
def test_o_rotulo_do_feasibility_mantem_os_colchetes_do_documento() -> None:
    """`[ Technical Feasibility ]` é a grafia de `metodologia-fde.md:26`, e os colchetes são a
    forma como a condicionalidade está escrita lá — apagá-los apagaria a informação."""
    assert FdeRung.FEASIBILITY.label == "[ Technical Feasibility ]"


@pytest.mark.django_db
def test_transicao_grava_evento_com_carimbo_e_autor() -> None:
    client = ClientFactory()
    autor = UserFactory(role=User.Role.SALES, first_name="Ana", last_name="Ribeiro")
    degrau = AccountRung.objects.get(client=client, rung=FdeRung.DISCOVER)

    ladder.transition(degrau, to_status=AccountRung.Status.ACTIVE, by=autor, note="venda ganha")

    evento = AccountRungEvent.objects.get(rung=degrau)
    assert (evento.from_status, evento.to_status) == ("not_sold", "active")
    assert evento.by == autor
    assert evento.note == "venda ganha"
    assert evento.at is not None
    degrau.refresh_from_db()
    assert degrau.started_at is not None


@pytest.mark.django_db
def test_replanejar_nao_apaga_nada() -> None:
    """Cancelar vira **mais um evento**, e as datas em que o degrau esteve ativo permanecem."""
    client = ClientFactory()
    autor = UserFactory()
    degrau = AccountRung.objects.get(client=client, rung=FdeRung.SCALE)
    ladder.transition(degrau, to_status=AccountRung.Status.ACTIVE, by=autor)
    inicio = AccountRung.objects.get(pk=degrau.pk).started_at

    ladder.transition(
        degrau, to_status=AccountRung.Status.CANCELLED, by=autor, note="escopo devolvido ao PROVE"
    )

    degrau.refresh_from_db()
    assert degrau.started_at == inicio
    assert degrau.completed_at is not None
    assert list(
        AccountRungEvent.objects.filter(rung=degrau).values_list("from_status", "to_status")
    ) == [("not_sold", "active"), ("active", "cancelled")]


@pytest.mark.django_db
def test_so_o_feasibility_aceita_pulada() -> None:
    client = ClientFactory()
    autor = UserFactory()
    prove = AccountRung.objects.get(client=client, rung=FdeRung.PROVE)

    with pytest.raises(StateConflict) as recusa:
        ladder.transition(
            prove,
            to_status=AccountRung.Status.SKIPPED,
            by=autor,
            skip_reason="não precisamos",
        )

    assert "Feasibility" in str(recusa.value)
    prove.refresh_from_db()
    assert prove.status == AccountRung.Status.NOT_SOLD
    assert AccountRungEvent.objects.filter(rung=prove).count() == 0


@pytest.mark.django_db
def test_pular_exige_motivo_autor_e_carimbo() -> None:
    """É o que separa *pulada* de *não vendido*: uma é decisão registrada, a outra é ausência."""
    client = ClientFactory()
    autor = UserFactory(first_name="Daniel", last_name="Campos")
    feasibility = AccountRung.objects.get(client=client, rung=FdeRung.FEASIBILITY)

    with pytest.raises(StateConflict):
        ladder.transition(feasibility, to_status=AccountRung.Status.SKIPPED, by=autor)

    ladder.transition(
        feasibility,
        to_status=AccountRung.Status.SKIPPED,
        by=autor,
        skip_reason="tecnologia sabida",
    )

    feasibility.refresh_from_db()
    assert feasibility.skip_reason == "tecnologia sabida"
    assert feasibility.skipped_by == autor
    assert feasibility.skipped_at is not None


@pytest.mark.django_db
def test_bloquear_exige_dizer_o_que() -> None:
    """O impedimento tem de ser legível na escada, sem abrir nota nenhuma."""
    client = ClientFactory()
    autor = UserFactory()
    degrau = AccountRung.objects.get(client=client, rung=FdeRung.PROVE)

    with pytest.raises(StateConflict):
        ladder.transition(degrau, to_status=AccountRung.Status.BLOCKED, by=autor)

    ladder.transition(
        degrau,
        to_status=AccountRung.Status.BLOCKED,
        by=autor,
        blocker="Acesso ao ERP pendente do time de TI do cliente",
        waiting_on=AccountRung.WaitingOn.CLIENT,
    )

    degrau.refresh_from_db()
    assert degrau.status == AccountRung.Status.BLOCKED
    assert degrau.waiting_on == AccountRung.WaitingOn.CLIENT


@pytest.mark.django_db
def test_transicao_para_o_mesmo_estado_e_recusada() -> None:
    client = ClientFactory()
    degrau = AccountRung.objects.get(client=client, rung=FdeRung.DISCOVER)

    with pytest.raises(StateConflict):
        ladder.transition(degrau, to_status=AccountRung.Status.NOT_SOLD, by=UserFactory())


@pytest.mark.django_db
def test_estado_desconhecido_e_recusado() -> None:
    client = ClientFactory()
    degrau = AccountRung.objects.get(client=client, rung=FdeRung.DISCOVER)

    with pytest.raises(StateConflict):
        ladder.transition(degrau, to_status="merged", by=UserFactory())


@pytest.mark.django_db
@override_settings(ACCOUNT_RUNG_STALE_AFTER_DAYS=14)
def test_parado_ha_n_dias_sai_do_ultimo_evento() -> None:
    client = ClientFactory()
    degrau = AccountRung.objects.get(client=client, rung=FdeRung.PROVE)
    assert ladder.days_stalled(degrau) is None

    ladder.transition(degrau, to_status=AccountRung.Status.ACTIVE, by=UserFactory())
    AccountRungEvent.objects.filter(rung=degrau).update(
        at=timezone.now() - timedelta(days=31)
    )

    assert ladder.days_stalled(degrau) == 31
    assert ladder.is_stale(ladder.days_stalled(degrau)) is True
    assert ladder.is_stale(4) is False
    assert ladder.is_stale(None) is False


@pytest.mark.django_db
@override_settings(ACCOUNT_RUNG_STALE_AFTER_DAYS=14)
def test_visao_geral_ordena_por_tempo_parado_e_tem_teto() -> None:
    """Superfície B: só conta com degrau em aberto, a mais parada primeiro, teto de 8 linhas."""
    admin = UserFactory(role=User.Role.ADMIN)
    for dias in range(10):
        client = ClientFactory(name=f"Conta {dias:02d}")
        degrau = AccountRung.objects.get(client=client, rung=FdeRung.PROVE)
        ladder.transition(degrau, to_status=AccountRung.Status.ACTIVE, by=admin)
        AccountRungEvent.objects.filter(rung=degrau).update(
            at=timezone.now() - timedelta(days=dias)
        )
    ClientFactory(name="Conta sem degrau em aberto")  # nasce inteira em `not_sold`

    linhas = ladder.account_ladder_rows(admin)

    assert len(linhas) == ladder.ACCOUNT_LADDER_LIMIT
    assert [linha["days_stalled"] for linha in linhas] == [9, 8, 7, 6, 5, 4, 3, 2]
    assert linhas[0]["is_stale"] is False
    assert all(len(linha["steps"]) == 6 for linha in linhas)
    # A linha não carrega conteúdo comercial: nem oportunidade, nem valor.
    assert set(linhas[0]) == {
        "client_id", "client_name", "rung", "rung_display", "status", "status_display",
        "waiting_on", "waiting_on_display", "days_stalled", "is_stale", "steps",
    }


@pytest.mark.django_db
def test_visao_geral_da_entrega_vem_do_escopo_de_projeto() -> None:
    entrega = UserFactory(role=User.Role.DELIVERY)
    minha = ClientFactory(name="Conta com projeto meu")
    alheia = ClientFactory(name="Conta de outra equipe")
    projeto = ProjectFactory(client=minha)
    ProjectMemberFactory(project=projeto, user=entrega)
    for conta in (minha, alheia):
        degrau = AccountRung.objects.get(client=conta, rung=FdeRung.PROVE)
        ladder.transition(degrau, to_status=AccountRung.Status.ACTIVE, by=UserFactory())

    linhas = ladder.account_ladder_rows(entrega)

    assert [linha["client_name"] for linha in linhas] == ["Conta com projeto meu"]
