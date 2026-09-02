"""Agendamento automático de reuniões (FDD 013, RFC 0002).

Gera os horários livres a partir de uma grade de horário comercial menos o que já está ocupado
(free/busy do Google) e as reservas existentes (`Booking`), e materializa a reserva criando o
evento com horário no Google Calendar. Atrás da flag `calendar`.

Dois fluxos entram pela mesma grade e pela mesma tabela: a **pré-venda** (`book`, o lead
qualificado que veio do site) e o **Discovery** do Design Partner (`book_discovery`, o cliente que
acabou de assinar o acordo). O núcleo é um só — `_reservar` — porque a checagem de conflito é
justamente o que os dois precisam compartilhar: dois núcleos seriam duas agendas que não se veem.

**A oferta, essa é de cada um.** `available_slots` (pré-venda) mostra 14 dias corridos e todo
horário livre; `available_slots_for_discovery` mostra 5 dias com grade a partir de 3 dias e no
máximo 3 por dia. As duas leem a mesma ocupação por `_slots_livres` e decidem sozinhas a janela —
unificá-las é o que o teste de regressão do agendamento existe para impedir.

A geração de slots é pura/testável; o I/O com o Google fica em `calendar_sync` (`# pragma: no cover`).
"""

from __future__ import annotations

import logging
from datetime import date, datetime, timedelta
from typing import TYPE_CHECKING

from django.conf import settings
from django.db import transaction
from django.utils import timezone

from . import calendar_sync, notifications

logger = logging.getLogger(__name__)

if TYPE_CHECKING:
    from .models import Booking, Engagement, Lead

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

# --- A janela do Discovery ------------------------------------------------------------------
#
# **Só do Discovery.** A pré-venda continua com os 14 dias corridos e todos os horários livres: a
# janela é a mesma decisão dos dois lados só enquanto ninguém mede, e o primeiro teste em uso mediu
# — 80 opções numa página, que é lista longa demais para uma escolha (DAP
# `dap-agendamento-discovery-r1`, emenda de 02/09). O que os dois fluxos precisam compartilhar é a
# **agenda** (`slots_for_range`, `_slots_livres`), não a oferta.
#
# Três constantes e nenhum número solto, porque cada uma responde a uma pergunta diferente e elas
# vão divergir na próxima revisão do pacote.
#
# O prazo é contado a partir de agora — ninguém agenda um walkthrough para amanhã.
DISCOVERY_LEAD_TIME_DAYS = 3
# **Dias com grade**, não dias corridos: `BOOKING_HOURS` tem segunda a sexta, e contar corrido
# entregaria três dias úteis na semana que começa numa quinta.
DISCOVERY_BUSINESS_DAYS = 5
# As duas bordas da grade comercial, e é delas que sai a leitura de "manhã" e "tarde". Cravar 12 e
# 14 dentro da regra de seleção faria a oferta discordar da grade na primeira mudança de horário.
DISCOVERY_MORNING_END_HOUR = 12
DISCOVERY_AFTERNOON_START_HOUR = 14


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


def _slots_livres(start: datetime, end: datetime, now: datetime) -> list[datetime]:
    """A agenda de verdade no intervalo: grade menos free/busy do Google menos `Booking` viva.

    É o que os dois fluxos compartilham — quem oferta pela pré-venda e quem oferta pelo Discovery
    precisa enxergar a **mesma** ocupação, pelo mesmo motivo que `_reservar` é um núcleo só. O que
    cada um decide sozinho é a janela e quantas opções mostrar.
    """
    from .models import Booking

    busy = calendar_sync.freebusy(start, end)
    taken = [
        (b.starts_at, b.ends_at)
        for b in Booking.objects.filter(
            status=Booking.Status.SCHEDULED, archived_at__isnull=True,
            starts_at__lt=end, ends_at__gt=start,
        )
    ]
    return slots_for_range(busy, start, end, now, taken=taken)


def available_slots(start: datetime | None = None, end: datetime | None = None) -> list[datetime]:
    """Horários livres para agendamento. Vazio quando a integração está desligada."""
    if not calendar_sync.is_enabled():
        return []

    now = timezone.localtime()
    start = start or now
    end = end or (now + timedelta(days=BOOKING_HORIZON_DAYS))
    return _slots_livres(start, end, now)


def discovery_window(
    now: datetime, hours: dict[int, list[tuple[int, int]]] | None = None
) -> tuple[datetime, datetime]:
    """O intervalo que o Discovery oferta: começa em `now + 3 dias`, cobre 5 **dias com grade**.

    A varredura anda dia a dia contando só o que `BOOKING_HOURS` conhece, porque "dia útil" aqui
    não é uma segunda definição de calendário — é a própria grade dizendo em que dias a casa
    atende. O teto do laço existe para uma grade vazia devolver janela degenerada em vez de rodar
    para sempre.
    """
    hours = BOOKING_HOURS if hours is None else hours
    start = now + timedelta(days=DISCOVERY_LEAD_TIME_DAYS)
    ultimo = day = start.date()
    uteis = 0
    for _ in range(DISCOVERY_BUSINESS_DAYS * 7):
        if uteis >= DISCOVERY_BUSINESS_DAYS:
            break
        if hours.get(day.weekday()):
            uteis += 1
            ultimo = day
        day += timedelta(days=1)
    end = timezone.make_aware(
        datetime.combine(ultimo, datetime.max.time()), timezone.get_current_timezone()
    )
    return start, end


def _hora_local(slot: datetime) -> int:
    return timezone.localtime(slot).hour


def tres_do_dia(slots: list[datetime]) -> list[datetime]:
    """Reduz cada dia a no máximo três opções: primeira da manhã, primeira da tarde, última do dia.

    A regra é de **degradação**, não de contagem: os três papéis são o que sobrevive quando a
    agenda enche. Dois papéis que caem no mesmo horário viram um — daí a deduplicação, e é por ela
    que "menos de três livres oferece os que existem" sai de graça, sem uma segunda regra que
    pudesse discordar da primeira. Dia sem nenhum livre simplesmente não aparece.

    A leitura de manhã/tarde é sempre no fuso local (`localtime`), como o agrupamento por dia: o
    slot chega ciente do fuso, e comparar a hora crua de um UTC deslocaria as duas faixas juntas.
    """
    por_dia: dict[date, list[datetime]] = {}
    for slot in sorted(slots):
        por_dia.setdefault(timezone.localtime(slot).date(), []).append(slot)

    escolhidos: list[datetime] = []
    for do_dia in por_dia.values():
        papeis = (
            next((s for s in do_dia if _hora_local(s) < DISCOVERY_MORNING_END_HOUR), None),
            next((s for s in do_dia if _hora_local(s) >= DISCOVERY_AFTERNOON_START_HOUR), None),
            do_dia[-1],
        )
        do_dia_escolhidos: list[datetime] = []
        for candidato in papeis:
            if candidato is not None and candidato not in do_dia_escolhidos:
                do_dia_escolhidos.append(candidato)
        escolhidos.extend(sorted(do_dia_escolhidos))
    return escolhidos


def available_slots_for_discovery() -> list[datetime]:
    """Os horários que a página do Discovery oferece (DAP `dap-agendamento-discovery-r1`).

    Função irmã de `available_slots`, e não um parâmetro dela, porque a pré-venda **não muda**:
    ela continua ofertando a janela inteira, e é a rota pública do site que depende disso. As duas
    dividem a agenda (`_slots_livres`) e nada mais.
    """
    if not calendar_sync.is_enabled():
        return []

    now = timezone.localtime()
    start, end = discovery_window(now)
    return tres_do_dia(_slots_livres(start, end, now))


def _default_owner():
    from .models import User

    return (
        User.objects.filter(is_active=True)
        .filter(role=User.Role.ADMIN)
        .order_by("id")
        .first()
    )


def _reservar(
    slot_start: datetime,
    *,
    attendee_email: str,
    summary: str,
    description: str,
    aviso: str,
    aviso_link: str,
    lead: Lead | None = None,
    engagement: Engagement | None = None,
) -> Booking:
    """Núcleo dos dois fluxos: trava o horário, grava a `Booking`, cria o evento e avisa o dono.

    Um núcleo só, e não dois parecidos, porque é aqui que mora a checagem de conflito: quem
    reserva pela pré-venda e quem reserva pelo Discovery precisam disputar a **mesma** linha
    travada, senão os dois marcam o mesmo horário sem nada ficar vermelho.

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
            lead=lead, engagement=engagement, owner=owner,
            starts_at=slot_start, ends_at=slot_end,
            attendee_email=attendee_email,
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
            summary=summary,
            start=slot_start, end=slot_end,
            description=description,
            attendee_email=attendee_email,
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
        notifications.notify([owner], "booking", f"{aviso}{ressalva}", aviso_link)
    return booking


def book(lead: Lead, slot_start: datetime) -> Booking:
    """Reserva o horário para o lead: cria a `Booking`, o evento no Google e notifica o dono.

    Levanta `SlotUnavailable` se o horário deixou de estar livre (corrida/duplo booking).
    """
    booking = _reservar(
        slot_start,
        lead=lead,
        attendee_email=lead.email,
        summary=f"Reunião com {lead.name}",
        description=lead.message or "Reunião agendada pelo site.",
        aviso=(
            f"{lead.name} agendou uma reunião para "
            f"{timezone.localtime(slot_start):%d/%m %H:%M}."
        ),
        aviso_link="/leads",
    )
    _send_confirmation(lead, slot_start)
    return booking


def book_discovery(engagement: Engagement, slot_start: datetime, attendee_email: str) -> Booking:
    """Reserva o Discovery do mandato de Design Partner (FDD 013, DAP agendamento-discovery r1).

    Mesma agenda e mesma tabela da pré-venda; o que muda é a origem da reserva, o que o evento
    diz e para onde o aviso ao dono aponta. **Sem confirmação por e-mail própria**: a decisão C1
    do DAP é que a confirmação acontece na página e o convite do Google vai ao cliente — o texto
    de `_send_confirmation` é de pré-venda e reusá-lo aqui mentiria sobre o que foi marcado.
    """
    account = engagement.account
    return _reservar(
        slot_start,
        engagement=engagement,
        attendee_email=attendee_email,
        summary=f"Discovery — {account.name}",
        description="Sessão de Discovery agendada pelo cliente.",
        aviso=(
            f"{account.name} agendou o Discovery para "
            f"{timezone.localtime(slot_start):%d/%m %H:%M}."
        ),
        aviso_link=f"/contas/{engagement.account_id}",
    )


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
