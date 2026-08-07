"""Agendador de trabalho periódico (FDD 023, ADR 0015).

Três funcionalidades entregues dependiam de alguém as disparar, e esse alguém não existia: o digest
diário (FDD 010), a sincronia do calendário (FDD 012) e o alerta de backup velho (FDD 021) eram
management commands que a documentação mandava "agendar via cron" — cron que não estava em lugar
nenhum da árvore. Na prática, uma instalação de produção subia sem nenhum dos três.

O que mora aqui é a decisão de **o que venceu**; quem gira o relógio é o `manage.py run_scheduler`.
A separação é o que torna o agendamento testável: um crontab não se testa com `pytest`, uma tabela
de jobs em Python se testa.

Duas propriedades que um `sleep` ingênuo erraria, e que os testes cobram:

- **Carimbo durável.** O vencimento é decidido contra `ScheduledJobRun`, no banco. Sem isso, um
  restart do container logo depois do digest reenviaria o e-mail para todo mundo.
- **Reivindicação atômica.** A marcação de "vou rodar" acontece dentro de uma transação, com
  `select_for_update()`, para que dois schedulers (escala por engano, ou deploy com sobreposição)
  não disparem o mesmo job duas vezes. No SQLite da suíte o lock é no-op — lá o que protege é a
  releitura do carimbo dentro da transação, que é a mesma checagem.
"""

from __future__ import annotations

import io
import logging
from dataclasses import dataclass
from datetime import datetime, time, timedelta

from django.conf import settings
from django.core.management import call_command
from django.db import transaction
from django.utils import timezone

from .models import ScheduledJobRun

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class Daily:
    """Uma vez por dia, ancorado em hora de parede."""

    at: time

    def __str__(self) -> str:
        return f"todo dia às {self.at.strftime('%H:%M')}"

    def is_due(self, last_attempt: datetime | None, now: datetime) -> bool:
        anchor = now.replace(hour=self.at.hour, minute=self.at.minute, second=0, microsecond=0)
        if now < anchor:
            return False
        return last_attempt is None or last_attempt < anchor

    def initial_last_attempt(self, now: datetime) -> datetime | None:
        """Job diário nasce **armado**, não disparado.

        Sem isto, subir a stack às 23h com a âncora nas 07:30 faria o digest sair na hora — porque
        as 07:30 de hoje já passaram e não há carimbo que diga que ele saiu. Carimbar `now` na
        criação diz "considere hoje já atendido": o primeiro envio é na próxima âncora, que é o que
        alguém esperaria de um agendamento diário.
        """
        return now


@dataclass(frozen=True)
class Every:
    """De tempos em tempos, contado a partir da última tentativa."""

    delta: timedelta

    def __str__(self) -> str:
        return f"a cada {int(self.delta.total_seconds() // 60)} min"

    def is_due(self, last_attempt: datetime | None, now: datetime) -> bool:
        return last_attempt is None or now - last_attempt >= self.delta

    def initial_last_attempt(self, now: datetime) -> datetime | None:
        """Job por intervalo roda **no primeiro tique**, ao contrário do diário.

        Aqui a estreia imediata é desejável e barata: a sincronia de calendário é idempotente, e
        esperar 15 min depois de subir a stack só atrasaria a primeira importação sem proteger
        ninguém de nada.
        """
        return None


Schedule = Daily | Every


@dataclass(frozen=True)
class Job:
    name: str
    command: str
    schedule: Schedule
    description: str


@dataclass(frozen=True)
class JobResult:
    name: str
    ran: bool
    ok: bool
    detail: str


def _parse_at(raw: str, fallback: time) -> time:
    """`HH:MM` do ambiente. Valor inválido não derruba o agendador — cai no default e avisa."""
    try:
        hour, minute = (int(part) for part in raw.strip().split(":", 1))
        return time(hour=hour, minute=minute)
    except (ValueError, TypeError):
        logger.warning(
            "scheduler: horário inválido %r; usando %s", raw, fallback.strftime("%H:%M")
        )
        return fallback


def jobs() -> list[Job]:
    """A tabela de jobs.

    É função e não constante de módulo de propósito: lida em tempo de import, a tabela congelaria
    os horários antes de qualquer `override_settings`, e a suíte não conseguiria testar cadência.
    """
    return [
        Job(
            name="digest",
            command="send_daily_digest",
            schedule=Daily(_parse_at(settings.SCHEDULER_DIGEST_AT, time(7, 30))),
            description="Resumo diário por e-mail (FDD 010)",
        ),
        Job(
            name="calendar",
            command="sync_calendar",
            schedule=Every(timedelta(minutes=settings.SCHEDULER_CALENDAR_EVERY_MINUTES)),
            description="Eventos do calendário viram tarefas (FDD 012)",
        ),
        Job(
            name="invoices_overdue",
            command="mark_overdue_invoices",
            schedule=Daily(_parse_at(settings.SCHEDULER_INVOICES_AT, time(6, 0))),
            description="Fatura emitida com vencimento passado vira vencida (FDD 028)",
        ),
        Job(
            name="backup_status",
            command="backup_status",
            schedule=Daily(_parse_at(settings.SCHEDULER_BACKUP_CHECK_AT, time(9, 0))),
            description="Alerta de backup velho (FDD 021)",
        ),
    ]


def _claim(job: Job, now: datetime) -> bool:
    """Reivindica o job para este tique. Devolve se cabe rodá-lo agora.

    Tudo dentro de uma transação: a leitura do carimbo, a decisão e a marcação da tentativa. Quem
    chegar depois relê um `last_attempt_at` já atualizado e desiste.
    """
    with transaction.atomic():
        run, created = ScheduledJobRun.objects.get_or_create(
            name=job.name,
            defaults={"last_attempt_at": job.schedule.initial_last_attempt(now)},
        )
        if not created:
            # Relê sob lock. Quem perdeu a corrida de criação cai aqui (a unicidade de `name`
            # elege um criador só) e fica bloqueado até o vencedor confirmar a transação — então
            # o carimbo que ele lê já é o atualizado, e ele desiste.
            run = ScheduledJobRun.objects.select_for_update().get(pk=run.pk)

        if not job.schedule.is_due(run.last_attempt_at, now):
            return False

        run.last_attempt_at = now
        run.save(update_fields=["last_attempt_at"])
        return True


def _record(job: Job, now: datetime, *, ok: bool, detail: str) -> None:
    # `detail` truncado: a saída de um comando é livre, e o carimbo é para leitura humana no admin.
    fields: dict[str, object] = {"ok": ok, "detail": detail[:2000]}
    if ok:
        fields["last_success_at"] = now
    ScheduledJobRun.objects.filter(name=job.name).update(**fields)


def _execute(job: Job) -> tuple[bool, str]:
    """Roda o comando e devolve (deu certo, o que ele disse).

    Nunca propaga: um job que estoura não pode derrubar o laço nem impedir os outros do mesmo
    tique. `backup_status` levanta `CommandError` **por projeto** quando a cópia envelhece — é o
    caminho normal do alerta, não um bug a ser tratado à parte.
    """
    saida = io.StringIO()
    try:
        call_command(job.command, stdout=saida, stderr=saida)
    except Exception as exc:  # noqa: BLE001 - isolamento é o objetivo
        motivo = str(exc) or exc.__class__.__name__
        # `exception` e não `warning`: a integração de logging do Sentry manda ERROR como evento
        # (ADR 0012), e é assim que o gancho de alerta da FDD 021 finalmente tem quem o dispare.
        logger.exception("scheduler: job %s falhou: %s", job.name, motivo)
        return False, motivo
    return True, saida.getvalue().strip()


def run_due(now: datetime | None = None) -> list[JobResult]:
    """Um tique: roda o que venceu e devolve o desfecho de cada job vencido."""
    now = now or timezone.localtime()
    resultados: list[JobResult] = []

    for job in jobs():
        try:
            if not _claim(job, now):
                continue
        except Exception:  # noqa: BLE001 - banco fora do ar não pode matar o laço
            logger.exception("scheduler: não foi possível reivindicar o job %s", job.name)
            resultados.append(JobResult(job.name, ran=False, ok=False, detail="claim falhou"))
            continue

        ok, detail = _execute(job)
        try:
            _record(job, now, ok=ok, detail=detail)
        except Exception:  # noqa: BLE001 - o job já rodou; perder o carimbo não o desfaz
            logger.exception("scheduler: não foi possível gravar o carimbo de %s", job.name)

        if ok:
            logger.info("scheduler: job %s concluído", job.name)
        resultados.append(JobResult(job.name, ran=True, ok=ok, detail=detail))

    return resultados
