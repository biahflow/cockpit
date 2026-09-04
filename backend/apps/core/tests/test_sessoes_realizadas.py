"""Nada fechava a sessão que já aconteceu (FDD 013, emenda de 02/09).

`Booking` e `Meeting` nasciam `scheduled` e ficavam `scheduled` para sempre: **nenhuma linha do
sistema** as transicionava para `held`. A casa nunca ficava sabendo que a conversa aconteceu — e é
por isso que a travessia da sessão para o projeto precisou de guarda de degrau, com a reserva ainda
"viva" meses depois.

O que estes testes protegem: que o passado fecha, que o futuro **não** é tocado, que rodar duas
vezes não muda nada além da primeira (o job é diário e um retry não pode inventar histórico), e que
o comando **diz** o que fechou — job silencioso sem resumo só pode ser lido como quebrado.
"""

from datetime import time, timedelta

import pytest
from django.core.management import call_command
from django.test import override_settings
from django.utils import timezone

from apps.core import booking, scheduler
from apps.core.models import Booking, Lead, Meeting

from .factories import ProjectFactory

pytestmark = pytest.mark.django_db


def _reserva(*, inicio, **extra) -> Booking:
    return Booking.objects.create(
        lead=Lead.objects.create(name="Lead", email="lead@x.test"),
        starts_at=inicio,
        ends_at=inicio + timedelta(minutes=45),
        attendee_email="lead@x.test",
        **extra,
    )


def _reuniao(*, dia, **extra) -> Meeting:
    return Meeting.objects.create(
        project=ProjectFactory(), title="Sessão de Discovery", date=dia, **extra
    )


def test_o_que_ja_aconteceu_fecha() -> None:
    agora = timezone.now()
    reserva = _reserva(inicio=agora - timedelta(hours=2))
    reuniao = _reuniao(dia=timezone.localdate() - timedelta(days=1))

    assert booking.fechar_sessoes_realizadas() == (1, 1)

    reserva.refresh_from_db()
    reuniao.refresh_from_db()
    assert reserva.status == Booking.Status.HELD
    assert reuniao.status == Meeting.Status.HELD


def test_o_que_ainda_vai_acontecer_nao_e_tocado() -> None:
    """Inclusive a reunião de **hoje**: um dia só termina quando vira o dia seguinte, e fechar o
    que ainda não aconteceu é inventar histórico."""
    agora = timezone.now()
    futura = _reserva(inicio=agora + timedelta(hours=2))
    em_curso = _reserva(inicio=agora - timedelta(minutes=10))
    hoje = _reuniao(dia=timezone.localdate())

    assert booking.fechar_sessoes_realizadas() == (0, 0)

    for registro in (futura, em_curso, hoje):
        registro.refresh_from_db()
    assert futura.status == em_curso.status == Booking.Status.SCHEDULED
    assert hoje.status == Meeting.Status.SCHEDULED


def test_cancelada_e_arquivada_ficam_de_fora() -> None:
    """Cancelada não aconteceu, e arquivada saiu da vista de propósito."""
    agora = timezone.now()
    cancelada = _reserva(inicio=agora - timedelta(hours=2), status=Booking.Status.CANCELED)
    arquivada = _reserva(inicio=agora - timedelta(hours=2), archived_at=agora)
    reuniao_arquivada = _reuniao(dia=timezone.localdate() - timedelta(days=1), archived_at=agora)

    assert booking.fechar_sessoes_realizadas() == (0, 0)

    for registro in (cancelada, arquivada, reuniao_arquivada):
        registro.refresh_from_db()
    assert cancelada.status == Booking.Status.CANCELED
    assert arquivada.status == Booking.Status.SCHEDULED
    assert reuniao_arquivada.status == Meeting.Status.SCHEDULED


def test_rodar_duas_vezes_nao_muda_nada_alem_da_primeira() -> None:
    """Idempotente **por construção**: o filtro por `status` exclui o que a rodada anterior mudou."""
    reserva = _reserva(inicio=timezone.now() - timedelta(hours=2))
    _reuniao(dia=timezone.localdate() - timedelta(days=1))

    primeira = booking.fechar_sessoes_realizadas()
    reserva.refresh_from_db()
    carimbo = reserva.updated_at
    segunda = booking.fechar_sessoes_realizadas()

    assert primeira == (1, 1)
    assert segunda == (0, 0)
    reserva.refresh_from_db()
    assert reserva.updated_at == carimbo


def test_o_comando_conta_o_que_fechou(capsys: pytest.CaptureFixture[str]) -> None:
    _reserva(inicio=timezone.now() - timedelta(hours=2))
    _reuniao(dia=timezone.localdate() - timedelta(days=1))

    call_command("mark_sessions_held")

    assert "1 reserva(s) e 1 reunião(ões)" in capsys.readouterr().out


def test_o_job_fecha_as_sessoes_antes_do_digest() -> None:
    """A ordem é a leitura do dia: o resumo das 07:30 anunciaria como agendada a sessão de ontem
    se a apuração viesse depois — o mesmo argumento do vencimento de faturas (FDD 028)."""
    with override_settings(SCHEDULER_SESSIONS_AT="06:30", SCHEDULER_DIGEST_AT="07:30"):
        tabela = {job.name: job for job in scheduler.jobs()}

    assert tabela["sessions_held"].command == "mark_sessions_held"
    assert tabela["sessions_held"].schedule == scheduler.Daily(time(6, 30))
    assert tabela["sessions_held"].schedule.at < tabela["digest"].schedule.at
    # Nenhum outro job no mesmo minuto: dois vencendo juntos disputam o mesmo tique sem precisar.
    horarios = [
        job.schedule.at for job in tabela.values() if isinstance(job.schedule, scheduler.Daily)
    ]
    assert len(horarios) == len(set(horarios))
