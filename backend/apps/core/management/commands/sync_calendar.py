from typing import Any

from django.core.management.base import BaseCommand

from apps.core import calendar_sync


class Command(BaseCommand):
    help = "Cria tarefas a partir de eventos do Google Calendar marcados com #proj-<id>."

    def handle(self, *args: Any, **options: Any) -> None:
        created, skipped = calendar_sync.sync_calendar()
        self.stdout.write(self.style.SUCCESS(f"Tarefas criadas: {created} (ignorados: {skipped})"))
