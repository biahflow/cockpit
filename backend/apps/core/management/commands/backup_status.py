from typing import Any

from django.core.management.base import BaseCommand, CommandError

from apps.core import backup


class Command(BaseCommand):
    help = (
        "Diz há quanto tempo o último backup terminou. Sai com código 1 quando não há backup ou "
        "quando ele está mais velho que BACKUP_MAX_AGE_HOURS — é o gancho do alerta (FDD 021)."
    )

    def handle(self, *args: Any, **options: Any) -> None:
        status = backup.read_backup_status()

        if status.finished_at is not None and status.age_hours is not None:
            destino = "local + offsite" if status.offsite else "somente local"
            self.stdout.write(
                f"Último backup: {status.finished_at:%Y-%m-%d %H:%M} UTC "
                f"({status.age_hours:.1f} h atrás, {destino})"
            )
            if status.db_bytes is not None and status.media_bytes is not None:
                self.stdout.write(
                    f"Banco: {status.db_bytes / 1024 / 1024:.1f} MB · "
                    f"Documentos: {status.media_bytes / 1024 / 1024:.1f} MB"
                )

        # `CommandError` em vez de `sys.exit`: a mensagem sai no stderr e o código de saída vira 1,
        # que é o que um alerta ou um healthcheck lê.
        if not status.ok:
            raise CommandError(status.reason)

        self.stdout.write(self.style.SUCCESS(status.reason))
