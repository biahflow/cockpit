"""Agendador de trabalho periódico (FDD 023, ADR 0015).

O que estes testes protegem, em ordem de importância: que um job diário **não sai duas vezes**
(era o defeito garantido sem carimbo durável), que um job que estoura **não leva os outros junto**,
e que a falha vira log de `ERROR` — que é o caminho pelo qual o alerta de backup da FDD 021
finalmente dispara.
"""

import logging
from datetime import datetime, time, timedelta

import pytest
from django.core.management import call_command
from django.test import override_settings
from django.utils import timezone

from apps.core import scheduler
from apps.core.models import ScheduledJobRun

pytestmark = pytest.mark.django_db


def _as_local(ano: int, mes: int, dia: int, hora: int, minuto: int = 0) -> datetime:
    return timezone.make_aware(datetime(ano, mes, dia, hora, minuto))


# --- cadência ---------------------------------------------------------------------------------


def test_diario_nao_vence_antes_da_ancora() -> None:
    diario = scheduler.Daily(time(7, 30))
    assert not diario.is_due(None, _as_local(2026, 8, 6, 6, 0))


def test_diario_vence_depois_da_ancora() -> None:
    diario = scheduler.Daily(time(7, 30))
    assert diario.is_due(None, _as_local(2026, 8, 6, 7, 31))


def test_diario_nao_vence_de_novo_no_mesmo_dia() -> None:
    """O defeito que o carimbo durável existe para impedir: dois digests no mesmo dia."""
    diario = scheduler.Daily(time(7, 30))
    rodou = _as_local(2026, 8, 6, 7, 30)
    assert not diario.is_due(rodou, _as_local(2026, 8, 6, 7, 31))
    assert not diario.is_due(rodou, _as_local(2026, 8, 6, 23, 59))


def test_diario_vence_de_novo_no_dia_seguinte() -> None:
    diario = scheduler.Daily(time(7, 30))
    rodou = _as_local(2026, 8, 6, 7, 30)
    assert diario.is_due(rodou, _as_local(2026, 8, 7, 7, 30))


def test_intervalo_vence_so_depois_do_periodo() -> None:
    cada15 = scheduler.Every(timedelta(minutes=15))
    rodou = _as_local(2026, 8, 6, 10, 0)
    assert not cada15.is_due(rodou, _as_local(2026, 8, 6, 10, 14))
    assert cada15.is_due(rodou, _as_local(2026, 8, 6, 10, 15))


def test_horario_invalido_no_ambiente_cai_no_default_sem_derrubar() -> None:
    """Um `SCHEDULER_DIGEST_AT=meio-dia` não pode impedir o agendador inteiro de subir."""
    assert scheduler._parse_at("meio-dia", time(7, 30)) == time(7, 30)
    assert scheduler._parse_at("06:15", time(7, 30)) == time(6, 15)


# --- estreia ----------------------------------------------------------------------------------


def test_job_diario_nasce_armado_e_nao_dispara_na_subida(monkeypatch: pytest.MonkeyPatch) -> None:
    """Subir a stack às 23h não pode mandar o digest do dia para todo mundo.

    Sem isto, as 07:30 de hoje "já passaram" e não há carimbo dizendo que o digest saiu — então a
    primeira coisa que uma instalação nova faria seria disparar um e-mail em massa fora de hora.
    """
    chamados: list[str] = []
    monkeypatch.setattr(scheduler, "jobs", lambda: [_job_falso("digest", scheduler.Daily(time(7, 30)))])
    monkeypatch.setattr(scheduler, "call_command", _registrando(chamados))

    resultados = scheduler.run_due(now=_as_local(2026, 8, 6, 23, 0))

    assert chamados == []
    assert resultados == []
    assert ScheduledJobRun.objects.get(name="digest").last_attempt_at is not None


def test_job_por_intervalo_roda_no_primeiro_tique(monkeypatch: pytest.MonkeyPatch) -> None:
    """O contrário do diário, e de propósito: a sincronia é idempotente e barata."""
    chamados: list[str] = []
    monkeypatch.setattr(
        scheduler, "jobs", lambda: [_job_falso("calendar", scheduler.Every(timedelta(minutes=15)))]
    )
    monkeypatch.setattr(scheduler, "call_command", _registrando(chamados))

    resultados = scheduler.run_due(now=_as_local(2026, 8, 6, 23, 0))

    assert chamados == ["cmd_calendar"]
    assert [r.ok for r in resultados] == [True]


# --- isolamento de falha ----------------------------------------------------------------------


def test_um_job_que_estoura_nao_impede_os_outros(monkeypatch: pytest.MonkeyPatch) -> None:
    """A propriedade central do laço: falha é isolada por job, não por tique."""
    chamados: list[str] = []

    def call_command_falso(nome: str, **kwargs: object) -> None:
        chamados.append(nome)
        if nome == "cmd_quebrado":
            raise RuntimeError("o fornecedor caiu")

    monkeypatch.setattr(
        scheduler,
        "jobs",
        lambda: [
            _job_falso("quebrado", scheduler.Every(timedelta(minutes=1))),
            _job_falso("saudavel", scheduler.Every(timedelta(minutes=1))),
        ],
    )
    monkeypatch.setattr(scheduler, "call_command", call_command_falso)

    resultados = scheduler.run_due(now=_as_local(2026, 8, 6, 10, 0))

    assert chamados == ["cmd_quebrado", "cmd_saudavel"]
    assert {r.name: r.ok for r in resultados} == {"quebrado": False, "saudavel": True}


def test_falha_grava_o_carimbo_e_loga_error(
    monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    """ERROR é o que a integração de logging do Sentry manda como evento (ADR 0012).

    É por aqui que o `backup_status` — que sai com código 1 quando a cópia envelhece — vira alerta
    de verdade, sem inventar canal novo.
    """

    def call_command_falso(nome: str, **kwargs: object) -> None:
        raise RuntimeError("backup com 40.0 h, acima do limite")

    monkeypatch.setattr(
        scheduler, "jobs", lambda: [_job_falso("backup_status", scheduler.Every(timedelta(minutes=1)))]
    )
    monkeypatch.setattr(scheduler, "call_command", call_command_falso)

    with caplog.at_level(logging.ERROR, logger="apps.core.scheduler"):
        scheduler.run_due(now=_as_local(2026, 8, 6, 10, 0))

    assert any(registro.levelno == logging.ERROR for registro in caplog.records)
    assert "acima do limite" in caplog.text

    carimbo = ScheduledJobRun.objects.get(name="backup_status")
    assert carimbo.ok is False
    assert "acima do limite" in carimbo.detail
    # A tentativa foi registrada mesmo tendo falhado — é o que impede a retentativa em enxurrada.
    assert carimbo.last_attempt_at is not None
    assert carimbo.last_success_at is None


def test_sucesso_grava_last_success_at(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        scheduler, "jobs", lambda: [_job_falso("calendar", scheduler.Every(timedelta(minutes=1)))]
    )
    monkeypatch.setattr(scheduler, "call_command", _registrando([]))

    agora = _as_local(2026, 8, 6, 10, 0)
    scheduler.run_due(now=agora)

    carimbo = ScheduledJobRun.objects.get(name="calendar")
    assert carimbo.ok is True
    assert carimbo.last_success_at == agora


# --- reivindicação ----------------------------------------------------------------------------


def test_dois_tiques_no_mesmo_instante_rodam_o_job_uma_vez(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Dois schedulers no ar (deploy com sobreposição) não podem duplicar o trabalho.

    No Postgres quem garante isso é o `select_for_update`; no SQLite da suíte, a releitura do
    carimbo dentro da transação — que é a mesma checagem, e é o que este teste exerce.
    """
    chamados: list[str] = []
    monkeypatch.setattr(
        scheduler, "jobs", lambda: [_job_falso("calendar", scheduler.Every(timedelta(minutes=15)))]
    )
    monkeypatch.setattr(scheduler, "call_command", _registrando(chamados))

    agora = _as_local(2026, 8, 6, 10, 0)
    scheduler.run_due(now=agora)
    scheduler.run_due(now=agora)

    assert chamados == ["cmd_calendar"]


def test_reivindicacao_respeita_o_carimbo_existente(monkeypatch: pytest.MonkeyPatch) -> None:
    """Sabotagem: apagar o carimbo faz o job diário sair de novo no mesmo dia.

    Se este teste passar com o carimbo apagado, o carimbo não está protegendo nada.
    """
    chamados: list[str] = []
    monkeypatch.setattr(
        scheduler, "jobs", lambda: [_job_falso("digest", scheduler.Daily(time(7, 30)))]
    )
    monkeypatch.setattr(scheduler, "call_command", _registrando(chamados))

    ScheduledJobRun.objects.create(name="digest", last_attempt_at=_as_local(2026, 8, 5, 20, 0))
    scheduler.run_due(now=_as_local(2026, 8, 6, 7, 31))
    assert chamados == ["cmd_digest"]

    # Segundo tique no mesmo dia: nada.
    scheduler.run_due(now=_as_local(2026, 8, 6, 9, 0))
    assert chamados == ["cmd_digest"]

    # Carimbo apagado à mão = o job volta a sair. É a prova de que é ele quem segura.
    ScheduledJobRun.objects.filter(name="digest").update(last_attempt_at=None)
    scheduler.run_due(now=_as_local(2026, 8, 6, 9, 1))
    assert chamados == ["cmd_digest", "cmd_digest"]


def test_banco_fora_do_ar_na_reivindicacao_nao_mata_o_tique(
    monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    """Se o banco cai às 3h, o agendador precisa estar de pé às 4h — não em laço de restart."""
    monkeypatch.setattr(
        scheduler,
        "jobs",
        lambda: [
            _job_falso("quebra_no_claim", scheduler.Every(timedelta(minutes=1))),
            _job_falso("saudavel", scheduler.Every(timedelta(minutes=1))),
        ],
    )

    claim_real = scheduler._claim

    def claim_falso(job: scheduler.Job, now: datetime) -> bool:
        if job.name == "quebra_no_claim":
            raise RuntimeError("connection already closed")
        return claim_real(job, now)

    monkeypatch.setattr(scheduler, "_claim", claim_falso)
    monkeypatch.setattr(scheduler, "call_command", _registrando([]))

    with caplog.at_level(logging.ERROR, logger="apps.core.scheduler"):
        resultados = scheduler.run_due(now=_as_local(2026, 8, 6, 10, 0))

    # O job seguinte roda mesmo assim.
    assert {r.name: (r.ran, r.ok) for r in resultados} == {
        "quebra_no_claim": (False, False),
        "saudavel": (True, True),
    }
    assert "reivindicar" in caplog.text


def test_carimbo_que_nao_grava_nao_desfaz_o_job(
    monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    """O job já rodou; falhar ao gravar o carimbo é para registrar, não para fingir que não rodou."""
    monkeypatch.setattr(
        scheduler, "jobs", lambda: [_job_falso("calendar", scheduler.Every(timedelta(minutes=1)))]
    )
    monkeypatch.setattr(scheduler, "call_command", _registrando([]))

    def record_falso(*a: object, **k: object) -> None:
        raise RuntimeError("disco cheio")

    monkeypatch.setattr(scheduler, "_record", record_falso)

    with caplog.at_level(logging.ERROR, logger="apps.core.scheduler"):
        resultados = scheduler.run_due(now=_as_local(2026, 8, 6, 10, 0))

    assert [(r.ran, r.ok) for r in resultados] == [(True, True)]
    assert "carimbo" in caplog.text


# --- tabela real e comando --------------------------------------------------------------------


def test_a_tabela_cobre_os_tres_comandos_orfaos() -> None:
    """Os três management commands que não tinham quem os chamasse (FDD 010, 012, 021)."""
    with override_settings(
        SCHEDULER_DIGEST_AT="07:30",
        SCHEDULER_CALENDAR_EVERY_MINUTES=15,
        SCHEDULER_BACKUP_CHECK_AT="09:00",
    ):
        tabela = {job.name: job for job in scheduler.jobs()}

    assert tabela["digest"].command == "send_daily_digest"
    assert tabela["calendar"].command == "sync_calendar"
    assert tabela["backup_status"].command == "backup_status"
    assert tabela["digest"].schedule == scheduler.Daily(time(7, 30))
    assert tabela["calendar"].schedule == scheduler.Every(timedelta(minutes=15))


def test_a_tabela_le_os_horarios_do_ambiente() -> None:
    """Tabela como função e não constante de módulo: é o que permite reconfigurar sem redeploy."""
    with override_settings(SCHEDULER_DIGEST_AT="06:15", SCHEDULER_CALENDAR_EVERY_MINUTES=5):
        tabela = {job.name: job for job in scheduler.jobs()}

    assert tabela["digest"].schedule == scheduler.Daily(time(6, 15))
    assert tabela["calendar"].schedule == scheduler.Every(timedelta(minutes=5))


def test_comando_once_roda_um_tique_e_sai(monkeypatch: pytest.MonkeyPatch) -> None:
    tiques: list[int] = []
    monkeypatch.setattr(scheduler, "run_due", lambda *a, **k: tiques.append(1) or [])

    call_command("run_scheduler", "--once")

    assert tiques == [1]


def test_comando_sobrevive_a_um_tique_que_estoura(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """Agendador em laço de restart é o problema que este item veio resolver, não a solução."""

    def explode(*a: object, **k: object) -> None:
        raise RuntimeError("banco fora do ar")

    monkeypatch.setattr(scheduler, "run_due", explode)

    call_command("run_scheduler", "--once")  # não levanta

    assert "tique falhou: banco fora do ar" in capsys.readouterr().err


def test_comando_relata_sucesso_e_falha_de_cada_job(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setattr(
        scheduler,
        "run_due",
        lambda *a, **k: [
            scheduler.JobResult("calendar", ran=True, ok=True, detail="Tarefas criadas: 2"),
            scheduler.JobResult("backup_status", ran=True, ok=False, detail="cópia com 40 h"),
        ],
    )

    call_command("run_scheduler", "--once")

    capturado = capsys.readouterr()
    assert "calendar: Tarefas criadas: 2" in capturado.out
    assert "backup_status: FALHOU — cópia com 40 h" in capturado.err


def test_laco_roda_ate_ser_mandado_parar(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """O laço em si: tica, espera de forma interrompível e sai limpo quando pedem.

    O `Event` falso é o que torna isto testável sem relógio — `wait()` devolve na hora e o
    segundo `is_set()` encerra, exercendo o mesmo caminho que um SIGTERM percorre.
    """
    tiques: list[int] = []
    monkeypatch.setattr(scheduler, "run_due", lambda *a, **k: tiques.append(1) or [])

    class EventoFalso:
        def __init__(self) -> None:
            self.consultas = 0
            self.esperas: list[float] = []

        def is_set(self) -> bool:
            self.consultas += 1
            return self.consultas > 1  # deixa passar um tique e manda parar

        def set(self) -> None:
            self.consultas = 99

        def wait(self, timeout: float | None = None) -> bool:
            self.esperas.append(timeout or 0)
            return False

    falso = EventoFalso()
    monkeypatch.setattr("apps.core.management.commands.run_scheduler.threading.Event", lambda: falso)

    with override_settings(SCHEDULER_TICK_SECONDS=42):
        call_command("run_scheduler")

    assert tiques == [1]
    assert falso.esperas == [42]
    saida = capsys.readouterr().err
    assert "scheduler: no ar (tique de 42s)" in saida
    # A tabela de horários no arranque: é o que um operador lê no `logs scheduler` para saber o
    # que este container promete fazer.
    assert "digest" in saida and "todo dia às" in saida
    assert "scheduler: encerrado" in saida


# --- apoio ------------------------------------------------------------------------------------


def _job_falso(nome: str, agenda: scheduler.Schedule) -> scheduler.Job:
    return scheduler.Job(
        name=nome, command=f"cmd_{nome}", schedule=agenda, description=f"job {nome}"
    )


def _registrando(destino: list[str]):  # type: ignore[no-untyped-def]
    def call_command_falso(nome: str, **kwargs: object) -> None:
        destino.append(nome)

    return call_command_falso


def test_a_tabela_marca_vencidas_antes_do_digest() -> None:
    """A ordem é o ponto: quem lê o dia precisa achar o vencimento apurado, não a apurar (FDD 028)."""
    with override_settings(SCHEDULER_INVOICES_AT="06:00", SCHEDULER_DIGEST_AT="07:30"):
        tabela = {job.name: job for job in scheduler.jobs()}

    assert tabela["invoices_overdue"].command == "mark_overdue_invoices"
    assert tabela["invoices_overdue"].schedule == scheduler.Daily(time(6, 0))
    assert tabela["invoices_overdue"].schedule.at < tabela["digest"].schedule.at
