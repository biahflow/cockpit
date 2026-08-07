"""Expurgo do dado pessoal arquivado que passou do prazo (LGPD).

**Não apaga nada sem `--apply`.** O default é ensaio, e isso não é excesso de zelo: é a única
operação do portal que destrói dado de propósito, e a regra da casa é justamente a oposta — soft
delete em todo lugar. Um expurgo que apaga por engano é pior que um expurgo que não existe.

Irmão do `check_integrations` e do `backup_status` no formato: sai com código 1 quando há algo a
dizer que quem opera precisa ver, e diz em português o que faria.
"""

from __future__ import annotations

from typing import Any

from django.core.management.base import BaseCommand, CommandError

from apps.core import retention


class Command(BaseCommand):
    help = "Expurga dado pessoal arquivado além do prazo de retenção. Ensaia por padrão (LGPD)."

    def add_arguments(self, parser: Any) -> None:
        parser.add_argument(
            "--apply", action="store_true",
            help="Apaga de verdade. Sem esta flag o comando só relata o que faria.",
        )

    def handle(self, *args: Any, **options: Any) -> None:
        aplicar = bool(options["apply"])
        planos = retention.executar() if aplicar else retention.planejar()

        desligadas = [plano for plano in planos if not plano.ativa]
        ativas = [plano for plano in planos if plano.ativa]

        for plano in ativas:
            verbo = "apagados" if aplicar else "seriam apagados"
            self.stdout.write(
                f"{plano.familia:10} retenção de {plano.dias} dias — "
                f"{plano.quantidade} {verbo}"
            )
        for plano in desligadas:
            self.stdout.write(
                f"{plano.familia:10} retenção desligada (RETENTION_{plano.familia.upper()}_DAYS=0)"
            )

        if not ativas:
            # Não é erro: é o estado de fábrica, e dizê-lo alto evita a conclusão errada de que o
            # expurgo rodou e não achou nada.
            self.stdout.write(self.style.WARNING(
                "Nenhuma família tem prazo configurado — nada foi (ou seria) apagado. "
                "O prazo é decisão de negócio; ver docs/adr/0017."
            ))
            return

        total = sum(plano.quantidade for plano in ativas)
        # As linhas cujo arquivo não saiu do provedor ficaram, de propósito (ADR 0017) — mas quem
        # mandou apagar precisa saber que não apagou. Sair 0 aqui seria dizer "expurgo concluído"
        # sobre dado pessoal que continua na base, e é a mentira que o comando inteiro evita.
        ficaram = sum(plano.falhas for plano in ativas)
        if aplicar and ficaram:
            self.stdout.write(self.style.SUCCESS(f"Expurgo parcial: {total} registro(s)."))
            raise CommandError(
                f"{ficaram} documento(s) não saíram do provedor e as linhas ficaram para a "
                "próxima execução. Confira a credencial do Drive e o log do comando."
            )
        if aplicar:
            self.stdout.write(self.style.SUCCESS(f"Expurgo concluído: {total} registro(s)."))
        elif total:
            self.stdout.write(self.style.WARNING(
                f"Ensaio: {total} registro(s) seriam apagados. Rode com --apply para valer."
            ))
        else:
            self.stdout.write(self.style.SUCCESS("Nada além do prazo."))
