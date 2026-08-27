from typing import Any

from django.conf import settings
from django.core.management.base import BaseCommand

from apps.core import github_projection


class Command(BaseCommand):
    help = (
        "Relê no GitHub o estado das projeções que envelheceram e cria a que nunca chegou por "
        "webhook (FDD 041). Somente leitura: nada é escrito no GitHub."
    )

    def handle(self, *args: Any, **options: Any) -> None:
        # Falha fechada, e **antes** de tocar em qualquer projeção: sem token, toda releitura
        # levantaria `GitHubIssuesError` sem status HTTP e carimbaria "GitHub indisponível" em
        # cada linha da casa — um erro de configuração vestido de incidente do fornecedor.
        if not str(getattr(settings, "GITHUB_TOKEN", "") or "").strip():
            self.stdout.write("Sem GITHUB_TOKEN configurado: reconciliação não executada.")
            return
        relatorio = github_projection.reconcile()
        self.stdout.write(self.style.SUCCESS(str(relatorio)))
