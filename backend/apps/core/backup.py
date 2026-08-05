"""Estado do último backup (FDD 021, ADR 0013).

O portal **não** faz backup: quem faz é o sidecar `backup` do `docker-compose.prod.yml`, em outro
container e com a mesma major do Postgres do servidor. O que mora aqui é a única parte que a
aplicação sabe fazer melhor — dizer que o backup **parou de rodar**.

Sem isso, um backup que quebrou (credencial expirada, disco cheio, cron que nunca subiu) só aparece
no dia em que se precisa dele, e aí a resposta é "não tem". O sidecar deixa um carimbo ao fim de
cada ciclo bem-sucedido; este módulo lê o carimbo e calcula a idade. Nada de rede, nada de banco.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, replace
from datetime import UTC, datetime
from pathlib import Path

from django.conf import settings

STAMP_NAME = "latest.json"
# O mesmo formato que o `backup.sh` usa no nome do arquivo: UTC, sem separador, sufixo Z.
STAMP_FORMAT = "%Y%m%dT%H%M%SZ"


@dataclass(frozen=True)
class BackupStatus:
    """Resultado da leitura do carimbo. `ok=False` sempre traz o motivo em `reason`."""

    ok: bool
    reason: str
    finished_at: datetime | None = None
    age_hours: float | None = None
    db_bytes: int | None = None
    media_bytes: int | None = None
    offsite: bool = False


def _parse_finished_at(payload: dict[str, object]) -> datetime | None:
    """`finished_at` (ISO) é a hora do fim; `timestamp` é o nome da cópia. Um dos dois basta."""
    raw_finished = payload.get("finished_at")
    if isinstance(raw_finished, str):
        try:
            return datetime.fromisoformat(raw_finished.replace("Z", "+00:00"))
        except ValueError:
            pass
    raw_stamp = payload.get("timestamp")
    if isinstance(raw_stamp, str):
        try:
            return datetime.strptime(raw_stamp, STAMP_FORMAT).replace(tzinfo=UTC)
        except ValueError:
            return None
    return None


def _as_int(value: object) -> int | None:
    return value if isinstance(value, int) and not isinstance(value, bool) else None


def read_backup_status(now: datetime | None = None) -> BackupStatus:
    """Lê o carimbo do último backup e diz se ele está dentro da idade aceitável.

    Nunca levanta: este é o caminho de um alerta, e um comando de monitoramento que estoura com
    traceback vira "o alerta está quebrado" em vez de "o backup está quebrado".
    """
    now = now or datetime.now(UTC)
    root = getattr(settings, "BACKUP_ROOT", "")
    if not root:
        return BackupStatus(ok=False, reason="BACKUP_ROOT não está configurado neste processo.")

    stamp = Path(root) / STAMP_NAME
    try:
        payload = json.loads(stamp.read_text())
    except FileNotFoundError:
        return BackupStatus(ok=False, reason=f"Nenhum backup registrado em {stamp}.")
    except (OSError, json.JSONDecodeError) as exc:
        return BackupStatus(ok=False, reason=f"O carimbo {stamp} está ilegível: {exc}")

    if not isinstance(payload, dict):
        return BackupStatus(ok=False, reason=f"O carimbo {stamp} não é um objeto JSON.")

    finished_at = _parse_finished_at(payload)
    if finished_at is None:
        return BackupStatus(ok=False, reason=f"O carimbo {stamp} não tem data utilizável.")

    age_hours = (now - finished_at).total_seconds() / 3600
    max_age = float(getattr(settings, "BACKUP_MAX_AGE_HOURS", 26))
    status = BackupStatus(
        ok=True,
        reason="Backup em dia.",
        finished_at=finished_at,
        age_hours=age_hours,
        db_bytes=_as_int(payload.get("db_bytes")),
        media_bytes=_as_int(payload.get("media_bytes")),
        offsite=payload.get("offsite") is True,
    )
    if age_hours > max_age:
        return replace(
            status,
            ok=False,
            reason=(
                f"O último backup terminou há {age_hours:.1f} h, acima do limite de "
                f"{max_age:.0f} h. O agendamento pode ter parado — veja o log do serviço `backup`."
            ),
        )
    return status
