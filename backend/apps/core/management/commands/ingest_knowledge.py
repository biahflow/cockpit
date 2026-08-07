from typing import Any

from django.core.management.base import BaseCommand

from apps.core import knowledge


class Command(BaseCommand):
    help = (
        "Traz o corpus commitado para o banco e embeda o que mudou (FDD 029). "
        "Não roda no boot: boot que fala com a OpenAI é boot que não sobe quando ela cai."
    )

    def add_arguments(self, parser: Any) -> None:
        parser.add_argument("--force", action="store_true", help="refaz trechos e embeddings")
        parser.add_argument(
            "--no-embed", action="store_true",
            help="popula sem gastar chamada de IA (é o modo com AI_ENABLED=false)",
        )

    def handle(self, *args: Any, **options: Any) -> None:
        resumo = knowledge.ingest(force=options["force"], embed=not options["no_embed"])
        self.stdout.write(self.style.SUCCESS(
            f"peças: {resumo['pecas']} ({resumo['criadas']} novas) · "
            f"trechos: {resumo['trechos']} · embeddadas: {resumo['embeddadas']} · "
            f"arquivadas: {resumo['arquivadas']}"
        ))
