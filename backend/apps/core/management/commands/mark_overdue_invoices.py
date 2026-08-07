from typing import Any

from django.core.management.base import BaseCommand

from apps.core import invoices


class Command(BaseCommand):
    help = "Marca como vencidas as faturas emitidas cujo vencimento já passou (FDD 028)."

    def handle(self, *args: Any, **options: Any) -> None:
        marcadas = invoices.mark_overdue()
        self.stdout.write(self.style.SUCCESS(f"Faturas vencidas: {marcadas}"))
