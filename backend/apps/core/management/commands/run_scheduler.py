import signal
import threading
from typing import Any

from django.conf import settings
from django.core.management.base import BaseCommand

from apps.core import scheduler


class Command(BaseCommand):
    help = (
        "Roda o trabalho periódico do portal: digest diário, sincronia de calendário e alerta de "
        "backup velho (FDD 023). Fica em primeiro plano — é o processo do serviço `scheduler`."
    )

    def add_arguments(self, parser: Any) -> None:
        parser.add_argument(
            "--once",
            action="store_true",
            help="Roda um único tique e sai, em vez de ficar em laço.",
        )

    def handle(self, *args: Any, **options: Any) -> None:
        # Antes de instalar tratador de sinal: `signal.signal` só vale na thread principal e
        # levanta `ValueError` fora dela — e `--once` existe justamente para ser chamado de
        # dentro de um teste ou de um `exec` manual, onde essa garantia não é dada.
        if options["once"]:
            self._tique()
            return

        # `Event` e não uma flag booleana: ele serve de `sleep` interrompível, então um SIGTERM
        # durante a espera encerra na hora em vez de segurar o `docker compose down` por um tique
        # inteiro. O sinal só pede a saída; o job em andamento termina — matar um envio de e-mail
        # ou uma sincronia no meio é pior que esperar por ele.
        parar = threading.Event()

        def encerrar(signum: int, frame: Any) -> None:
            self.stderr.write("scheduler: sinal recebido, encerrando após o job atual")
            parar.set()

        # Os tratadores anteriores voltam ao sair. No container isto é indiferente — o processo
        # morre logo depois —, mas o comando também roda dentro da suíte, e um SIGINT preso a um
        # tratador defunto tiraria o Ctrl-C de quem estiver rodando os testes.
        anteriores = {
            numero: signal.signal(numero, encerrar)
            for numero in (signal.SIGTERM, signal.SIGINT)
        }
        try:
            intervalo = settings.SCHEDULER_TICK_SECONDS
            self.stderr.write(f"scheduler: no ar (tique de {intervalo}s)")
            for job in scheduler.jobs():
                self.stderr.write(f"  · {job.name}: {job.description} — {job.schedule}")

            while not parar.is_set():
                self._tique()
                parar.wait(intervalo)
        finally:
            for numero, anterior in anteriores.items():
                signal.signal(numero, anterior)

        self.stderr.write("scheduler: encerrado")

    def _tique(self) -> None:
        # O laço não pode morrer. `run_due` já isola falha por job, mas um erro fora dela (banco
        # indisponível no meio da noite) deixaria o container em laço de restart, e um agendador
        # que não sobe é o problema que este item veio resolver.
        try:
            resultados = scheduler.run_due()
        except Exception as exc:  # noqa: BLE001
            self.stderr.write(f"scheduler: tique falhou: {exc}")
            return

        for resultado in resultados:
            if resultado.ok:
                self.stdout.write(self.style.SUCCESS(f"{resultado.name}: {resultado.detail}"))
            else:
                self.stderr.write(f"{resultado.name}: FALHOU — {resultado.detail}")
