"""Agendamento automático de reuniões de pré-venda (FDD 013, RFC 0002).

Gera os horários livres a partir de uma grade de horário comercial menos o que já está ocupado
(free/busy do Google) e as reservas existentes (`Booking`), e materializa a reserva criando o
evento com horário no Google Calendar. Atrás da flag `calendar`.

A geração de slots é pura/testável; o I/O com o Google fica em `calendar_sync` (`# pragma: no cover`).
"""

from __future__ import annotations

import logging
from datetime import datetime, timedelta
from typing import TYPE_CHECKING

from django.conf import settings
from django.db import transaction
from django.utils import timezone

from . import calendar_sync, notifications

logger = logging.getLogger(__name__)

if TYPE_CHECKING:
    from .models import Booking, Lead

# Grade de horário comercial: dia da semana (0=segunda … 6=domingo) → faixas (hora_ini, hora_fim).
BOOKING_HOURS: dict[int, list[tuple[int, int]]] = {
    0: [(9, 12), (14, 17)],
    1: [(9, 12), (14, 17)],
    2: [(9, 12), (14, 17)],
    3: [(9, 12), (14, 17)],
    4: [(9, 12), (14, 17)],
}
# Quantos dias à frente ofertar.
BOOKING_HORIZON_DAYS = 14


class SlotUnavailable(Exception):
    """O horário pedido não está mais livre."""


def _slot_minutes() -> int:
    return int(getattr(settings, "BOOKING_SLOT_MINUTES", 45))


def _overlaps(start: datetime, end: datetime, intervals: list[tuple[datetime, datetime]]) -> bool:
    return any(start < busy_end and busy_start < end for busy_start, busy_end in intervals)


def slots_for_range(
    busy: list[tuple[datetime, datetime]],
    start: datetime,
    end: datetime,
    now: datetime,
    hours: dict[int, list[tuple[int, int]]] | None = None,
    slot_minutes: int | None = None,
    taken: list[tuple[datetime, datetime]] | None = None,
) -> list[datetime]:
    """Slots livres da grade no intervalo [start, end], sem os ocupados/reservados e sem passado."""
    hours = BOOKING_HOURS if hours is None else hours
    slot_minutes = _slot_minutes() if slot_minutes is None else slot_minutes
    blocked = list(busy) + list(taken or [])
    step = timedelta(minutes=slot_minutes)
    tz = timezone.get_current_timezone()

    slots: list[datetime] = []
    day = start.date()
    while day <= end.date():
        for hour_start, hour_end in hours.get(day.weekday(), []):
            cursor = timezone.make_aware(datetime.combine(day, datetime.min.time()).replace(hour=hour_start), tz)
            day_end = timezone.make_aware(datetime.combine(day, datetime.min.time()).replace(hour=hour_end), tz)
            while cursor + step <= day_end:
                slot_end = cursor + step
                if cursor >= now and start <= cursor and slot_end <= end and not _overlaps(cursor, slot_end, blocked):
                    slots.append(cursor)
                cursor = slot_end
        day += timedelta(days=1)
    return slots


def available_slots(start: datetime | None = None, end: datetime | None = None) -> list[datetime]:
    """Horários livres para agendamento. Vazio quando a integração está desligada."""
    if not calendar_sync.is_enabled():
        return []

    from .models import Booking

    now = timezone.localtime()
    start = start or now
    end = end or (now + timedelta(days=BOOKING_HORIZON_DAYS))
    busy = calendar_sync.freebusy(start, end)
    taken = [
        (b.starts_at, b.ends_at)
        for b in Booking.objects.filter(
            status=Booking.Status.SCHEDULED, archived_at__isnull=True,
            starts_at__lt=end, ends_at__gt=start,
        )
    ]
    return slots_for_range(busy, start, end, now, taken=taken)


def _default_owner():
    from .models import User

    return (
        User.objects.filter(is_active=True)
        .filter(role=User.Role.ADMIN)
        .order_by("id")
        .first()
    )


def book(lead: Lead, slot_start: datetime) -> Booking:
    """Reserva o horário para o lead: cria a `Booking`, o evento no Google e notifica o dono.

    Levanta `SlotUnavailable` se o horário deixou de estar livre (corrida/duplo booking).
    """
    from .models import Booking

    slot_end = slot_start + timedelta(minutes=_slot_minutes())
    if slot_start < timezone.localtime():
        raise SlotUnavailable

    with transaction.atomic():
        clash = Booking.objects.select_for_update().filter(
            status=Booking.Status.SCHEDULED, archived_at__isnull=True,
            starts_at__lt=slot_end, ends_at__gt=slot_start,
        ).exists()
        if clash or _overlaps(slot_start, slot_end, calendar_sync.freebusy(slot_start, slot_end)):
            raise SlotUnavailable
        owner = _default_owner()
        booking = Booking.objects.create(
            lead=lead, owner=owner, starts_at=slot_start, ends_at=slot_end,
            attendee_email=lead.email,
        )

    # A transação já fechou: a `Booking` está gravada e **bloqueia o horário** para todo mundo (é
    # ela que o teste de conflito acima consulta). Se o Google recusar aqui, desfazer seria pior —
    # o horário está de fato comprometido — mas deixar a exceção subir era o pior de todos: sobrava
    # uma reserva sem evento na agenda, sem aviso ao dono e sem confirmação ao lead, e o endpoint
    # **público** devolvia 500 a quem acabara de agendar. É a "reserva órfã", uma integração
    # adiante do convite órfão da rodada 1.
    #
    # O desenho sempre tratou o evento como best-effort — o `if event_id or link:` abaixo já
    # tolerava o retorno vazio. O defeito era a *exceção* não ser tolerada como o vazio era. O caso
    # conhecido é o `forbiddenForServiceAccounts`: conta de serviço não convida participante sem
    # delegação em todo o domínio (FDD 024), e é justamente esta chamada que convida.
    evento_falhou = False
    try:
        event_id, link = calendar_sync.create_timed_event(
            summary=f"Reunião com {lead.name}",
            start=slot_start, end=slot_end,
            description=lead.message or "Reunião agendada pelo site.",
            attendee_email=lead.email,
            origin=f"booking:{booking.id}",
        )
    except calendar_sync.CalendarProviderError:
        logger.exception("reserva %s ficou sem evento na agenda", booking.id)
        event_id = link = ""
        evento_falhou = True
    if event_id or link:
        booking.calendar_event_id = event_id
        booking.calendar_link = link
        booking.save(update_fields=["calendar_event_id", "calendar_link", "updated_at"])

    if owner:
        # O aviso diz que o evento não entrou, senão a degradação fica invisível para quem responde
        # pela reunião — e a pessoa conta com um convite que não existe.
        ressalva = " **A reunião não entrou na agenda** — inclua manualmente." if evento_falhou else ""
        notifications.notify(
            [owner], "booking",
            f"{lead.name} agendou uma reunião para "
            f"{timezone.localtime(slot_start):%d/%m %H:%M}.{ressalva}",
            "/leads",
        )
    _send_confirmation(lead, slot_start)
    return booking


def _send_confirmation(lead: Lead, slot_start: datetime) -> None:
    from django.core.mail import send_mail

    if not lead.email:
        return
    send_mail(
        "Sua reunião com a Biahflow está agendada",
        f"Olá {lead.name},\n\nSua reunião está confirmada para "
        f"{timezone.localtime(slot_start):%d/%m/%Y às %H:%M}.\n\nAté lá!",
        None,
        [lead.email],
        fail_silently=True,
    )
