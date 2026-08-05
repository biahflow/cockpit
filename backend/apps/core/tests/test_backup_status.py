"""Carimbo do último backup e o comando que alerta sobre ele (FDD 021)."""

import json
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest
from django.core.management import call_command
from django.core.management.base import CommandError
from django.test import override_settings

from apps.core import backup


def _carimbo(root: Path, *, finished_at: datetime, offsite: bool = False) -> None:
    (root / backup.STAMP_NAME).write_text(
        json.dumps(
            {
                "timestamp": finished_at.strftime(backup.STAMP_FORMAT),
                "finished_at": finished_at.strftime("%Y-%m-%dT%H:%M:%SZ"),
                "db_bytes": 5 * 1024 * 1024,
                "media_bytes": 2 * 1024 * 1024,
                "offsite": offsite,
            }
        )
    )


def test_backup_recente_passa(tmp_path: Path) -> None:
    agora = datetime.now(UTC)
    _carimbo(tmp_path, finished_at=agora - timedelta(hours=3), offsite=True)

    with override_settings(BACKUP_ROOT=str(tmp_path), BACKUP_MAX_AGE_HOURS=26):
        status = backup.read_backup_status(now=agora)

    assert status.ok
    assert status.age_hours == pytest.approx(3, abs=0.1)
    assert status.offsite is True
    assert status.db_bytes == 5 * 1024 * 1024


def test_backup_velho_reprova(tmp_path: Path) -> None:
    """O backup que parou de rodar é o caso que este módulo existe para pegar."""
    agora = datetime.now(UTC)
    _carimbo(tmp_path, finished_at=agora - timedelta(hours=40))

    with override_settings(BACKUP_ROOT=str(tmp_path), BACKUP_MAX_AGE_HOURS=26):
        status = backup.read_backup_status(now=agora)

    assert not status.ok
    assert "40.0 h" in status.reason
    # Mesmo reprovando, os números continuam disponíveis: quem lê o alerta quer saber de quando é
    # a última cópia que existe, não só que ela está velha.
    assert status.age_hours == pytest.approx(40, abs=0.1)


def test_sem_carimbo_reprova(tmp_path: Path) -> None:
    with override_settings(BACKUP_ROOT=str(tmp_path)):
        status = backup.read_backup_status()

    assert not status.ok
    assert "Nenhum backup registrado" in status.reason


def test_sem_backup_root_configurado_nao_finge_que_esta_tudo_bem() -> None:
    """Fora do compose de produção o volume não existe — e silêncio aqui seria pior que o erro."""
    with override_settings(BACKUP_ROOT=""):
        status = backup.read_backup_status()

    assert not status.ok
    assert "BACKUP_ROOT" in status.reason


def test_carimbo_corrompido_nao_estoura(tmp_path: Path) -> None:
    """Comando de alerta que levanta traceback vira 'o alerta quebrou', não 'o backup quebrou'."""
    (tmp_path / backup.STAMP_NAME).write_text("{ isso não é json")

    with override_settings(BACKUP_ROOT=str(tmp_path)):
        status = backup.read_backup_status()

    assert not status.ok
    assert "ilegível" in status.reason


def test_carimbo_sem_data_utilizavel_reprova(tmp_path: Path) -> None:
    (tmp_path / backup.STAMP_NAME).write_text(json.dumps({"timestamp": "ontem de manhã"}))

    with override_settings(BACKUP_ROOT=str(tmp_path)):
        status = backup.read_backup_status()

    assert not status.ok
    assert "data utilizável" in status.reason


def test_carimbo_sem_finished_at_usa_o_timestamp_do_nome(tmp_path: Path) -> None:
    """`timestamp` é o nome do par de arquivos; sozinho, já diz de quando é a cópia."""
    agora = datetime.now(UTC)
    (tmp_path / backup.STAMP_NAME).write_text(
        json.dumps({"timestamp": (agora - timedelta(hours=1)).strftime(backup.STAMP_FORMAT)})
    )

    with override_settings(BACKUP_ROOT=str(tmp_path), BACKUP_MAX_AGE_HOURS=26):
        status = backup.read_backup_status(now=agora)

    assert status.ok
    assert status.age_hours == pytest.approx(1, abs=0.1)


def test_finished_at_ilegivel_cai_no_timestamp_do_nome(tmp_path: Path) -> None:
    """O carimbo tem duas datas: uma quebrada não pode apagar a outra."""
    agora = datetime.now(UTC)
    (tmp_path / backup.STAMP_NAME).write_text(
        json.dumps(
            {
                "finished_at": "quinta-feira",
                "timestamp": (agora - timedelta(hours=2)).strftime(backup.STAMP_FORMAT),
            }
        )
    )

    with override_settings(BACKUP_ROOT=str(tmp_path), BACKUP_MAX_AGE_HOURS=26):
        status = backup.read_backup_status(now=agora)

    assert status.ok
    assert status.age_hours == pytest.approx(2, abs=0.1)


def test_carimbo_sem_nenhuma_data_reprova(tmp_path: Path) -> None:
    (tmp_path / backup.STAMP_NAME).write_text(json.dumps({"db_bytes": 10}))

    with override_settings(BACKUP_ROOT=str(tmp_path)):
        assert not backup.read_backup_status().ok


def test_carimbo_que_nao_e_objeto_reprova(tmp_path: Path) -> None:
    """JSON válido e inútil: uma lista onde deveria haver um objeto."""
    (tmp_path / backup.STAMP_NAME).write_text(json.dumps(["20260805T031500Z"]))

    with override_settings(BACKUP_ROOT=str(tmp_path)):
        status = backup.read_backup_status()

    assert not status.ok
    assert "objeto JSON" in status.reason


def test_comando_sai_com_erro_quando_o_backup_esta_velho(tmp_path: Path) -> None:
    """`CommandError` é o que dá código de saída 1 — é por ele que o alerta dispara."""
    _carimbo(tmp_path, finished_at=datetime.now(UTC) - timedelta(days=3))

    with override_settings(BACKUP_ROOT=str(tmp_path), BACKUP_MAX_AGE_HOURS=26):
        with pytest.raises(CommandError, match="acima do limite"):
            call_command("backup_status")


def test_comando_sem_nenhuma_copia_reprova_sem_estourar(tmp_path: Path) -> None:
    """Sem carimbo não há o que imprimir — e o comando ainda assim precisa reprovar limpo."""
    with override_settings(BACKUP_ROOT=str(tmp_path)):
        with pytest.raises(CommandError, match="Nenhum backup registrado"):
            call_command("backup_status")


def test_comando_relata_a_copia_em_dia(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    _carimbo(tmp_path, finished_at=datetime.now(UTC) - timedelta(hours=2), offsite=True)

    with override_settings(BACKUP_ROOT=str(tmp_path), BACKUP_MAX_AGE_HOURS=26):
        call_command("backup_status")

    saida = capsys.readouterr().out
    assert "Último backup" in saida
    assert "local + offsite" in saida
    assert "5.0 MB" in saida
