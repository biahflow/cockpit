from datetime import date
from typing import Any

from django.core.management.base import BaseCommand, CommandError

from apps.core import cobranca


class Command(BaseCommand):
    help = "Roda a régua de cobrança: o degrau que cabe hoje em cada fatura em aberto (FDD 036)."

    def add_arguments(self, parser: Any) -> None:
        # Existe para exercitar a régua fim a fim sem esperar o calendário: `--hoje=2026-09-01`
        # responde "o que sairia naquele dia?". Toda regra daqui é aritmética de dias sobre o
        # vencimento, então fixar o dia é o suficiente para o exercício ser determinístico.
        parser.add_argument("--hoje", help="Data no formato AAAA-MM-DD (default: hoje).")

    def handle(self, *args: Any, **options: Any) -> None:
        bruto = options.get("hoje")
        try:
            hoje = date.fromisoformat(bruto) if bruto else None
        except ValueError as exc:
            raise CommandError(f"--hoje inválido: {bruto!r}. Use AAAA-MM-DD.") from exc
        resumo = cobranca.executar(hoje)
        # O resumo inteiro, e não só quantos saíram: um job de cobrança que não manda nada é o caso
        # comum (fim de semana, teto, suspensão, degrau já gasto), e sem os motivos a única leitura
        # possível do silêncio é supor que ele quebrou.
        self.stdout.write(
            self.style.SUCCESS(
                f"Régua de cobrança: {resumo['contatos']} contato(s) ao cliente, "
                f"{resumo['escaladas']} escalada(s) interna(s), "
                f"{resumo['avaliadas']} fatura(s) avaliada(s), "
                f"{resumo['falhas']} falha(s). "
                f"Calados: {resumo['calados'] or 'nenhum'}. "
                f"Motivo: {resumo['motivo'] or '-'}."
            )
        )
