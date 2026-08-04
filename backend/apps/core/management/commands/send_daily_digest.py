from typing import Any

from django.core.management.base import BaseCommand

from apps.core import digest


class Command(BaseCommand):
    help = "Envia o resumo diário (digest) por e-mail aos usuários com itens pendentes."

    def handle(self, *args: Any, **options: Any) -> None:
        sent = digest.send_daily_digest()
        self.stdout.write(self.style.SUCCESS(f"Digests enviados: {sent}"))
