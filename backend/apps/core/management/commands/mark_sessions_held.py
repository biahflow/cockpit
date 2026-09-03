from typing import Any

from django.core.management.base import BaseCommand

from apps.core import booking


class Command(BaseCommand):
    help = (
        "Fecha as sessões que já aconteceram: reserva com fim no passado e reunião com data no "
        "passado viram realizadas (FDD 013)."
    )

    def handle(self, *args: Any, **options: Any) -> None:
        reservas, reunioes = booking.fechar_sessoes_realizadas()
        # O resumo com os dois números, e não um "ok": zero é o caso comum — dia sem sessão — e
        # sem contagem a única leitura possível do silêncio é supor que o job quebrou.
        self.stdout.write(
            self.style.SUCCESS(
                f"Sessões realizadas: {reservas} reserva(s) e {reunioes} reunião(ões)."
            )
        )
