from pathlib import Path
from typing import Any

from django.conf import settings
from django.core.management.base import BaseCommand

from apps.core import knowledge


class Command(BaseCommand):
    help = (
        "Gera o artefato do corpus de conhecimento (FDD 029) a partir de docs/ e PRD.md. "
        "O resultado é commitado e conferido no CI, como o openapi.yaml."
    )

    def handle(self, *args: Any, **options: Any) -> None:
        raiz = Path(settings.BASE_DIR).parent
        chunks = knowledge.build_corpus(raiz)
        total = knowledge.write_corpus(chunks)
        arquivos = len({chunk.source_path for chunk in chunks})
        self.stdout.write(
            self.style.SUCCESS(f"Corpus gerado: {total} trecho(s) de {arquivos} arquivo(s).")
        )
