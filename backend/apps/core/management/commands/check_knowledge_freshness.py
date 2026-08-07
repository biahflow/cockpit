from typing import Any

from django.core.management.base import BaseCommand

from apps.core import knowledge


class Command(BaseCommand):
    help = "Avisa quem responde pelo conhecimento vencido, e os admins pelo que está sem dono (FDD 029)."

    def handle(self, *args: Any, **options: Any) -> None:
        resumo = knowledge.check_freshness()
        linha = (
            f"vencidas: {resumo['vencidas']} · sem dono: {resumo['sem_dono']} · "
            f"a vencer: {resumo['a_vencer']} · avisos enviados: {resumo['avisos']}"
        )
        # Sem `CommandError`: dívida editorial não é incidente. Ver o docstring de `check_freshness`.
        estilo = self.style.WARNING if resumo["vencidas"] or resumo["sem_dono"] else self.style.SUCCESS
        self.stdout.write(estilo(linha))
