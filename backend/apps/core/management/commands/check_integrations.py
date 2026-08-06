from typing import Any

from django.core.management.base import BaseCommand, CommandError

from apps.core import integrations

_SIMBOLO = {True: "OK   ", False: "FALHA", None: "--   "}


class Command(BaseCommand):
    help = (
        "Diz se cada integração ligada realmente responde: uma chamada real, barata e só de "
        "leitura por provedor. Sai com código 1 quando alguma reprova — é o gancho de alerta "
        "(FDD 024). `flags.configured` só olha se a variável está preenchida; isto olha se ela "
        "funciona."
    )

    def add_arguments(self, parser: Any) -> None:
        parser.add_argument(
            "--all",
            action="store_true",
            help="Sonda também as integrações desligadas — para conferir a credencial antes de ligar.",
        )

    def handle(self, *args: Any, **options: Any) -> None:
        resultados = integrations.probe_all(incluir_desligadas=options["all"])

        for resultado in resultados:
            linha = f"{_SIMBOLO[resultado.ok]} {resultado.label:38} {resultado.detail}"
            if resultado.ok is True:
                self.stdout.write(self.style.SUCCESS(linha))
            elif resultado.ok is False:
                self.stdout.write(self.style.ERROR(linha))
            else:
                self.stdout.write(linha)

        reprovadas = [r for r in resultados if r.reprovou]
        if reprovadas:
            # `CommandError` e não `sys.exit`: a mensagem sai no stderr e o código vira 1, que é o
            # que um alerta lê — mesma escolha do `backup_status` (FDD 021).
            raise CommandError(
                f"{len(reprovadas)} integração(ões) reprovaram: "
                + ", ".join(r.name for r in reprovadas)
            )

        self.stdout.write(self.style.SUCCESS("Todas as integrações ligadas responderam."))
