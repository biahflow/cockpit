"""Integração com Google Calendar (atrás da flag `CALENDAR_ENABLED`).

Reusa as credenciais de conta de serviço do Drive. Desligado por padrão. Dois sentidos:

- **Outbound**: `create_event(...)` lança um marco/tarefa no calendário (via `CalendarActionMixin`).
- **Inbound**: `sync_calendar()` lê eventos do calendário compartilhado e cria tarefas no projeto
  indicado por um marcador `#proj-<id>` no título/descrição do evento (FDD 012). Idempotente via
  `Task.source`/`external_id`; ignora eventos que nós mesmos criamos (carimbados com `biahflow_origin`).

A chamada real à API do Google fica fora da cobertura (`# pragma: no cover`); o mapeamento e a
orquestração são puros/testáveis.
"""

from __future__ import annotations

import re
from datetime import date, datetime, timedelta

from django.conf import settings
from django.utils import timezone

from . import flags

CALENDAR_SCOPE = "https://www.googleapis.com/auth/calendar"


class CalendarProviderError(Exception):
    """O Calendar recusou: credencial, escopo, agenda inexistente, permissão ou rede.

    Não confundir com `CalendarUnavailable`, logo abaixo: aquela é o free/busy **falhando fechado**
    (lemos a resposta e ela não permite afirmar nada sobre a agenda, então 503). Esta é o
    fornecedor recusando a operação, e vira 502.

    Tipo estreito pelo mesmo motivo do `ai.AiProviderError` da rodada 2: envolver só a chamada de
    rede, para que um defeito nosso logo depois não seja reportado como falha do Google.
    """


# Marcador que amarra um evento a um projeto: "#proj-42" no título ou na descrição.
PROJECT_MARKER = re.compile(r"#proj-(\d+)")
# Chave em extendedProperties.private que marca eventos originados no próprio Biahflow (anti-loop).
ORIGIN_KEY = "biahflow_origin"
# Origem gravada em Task.source para as tarefas nascidas de eventos do calendário.
CALENDAR_TASK_SOURCE = "calendar"
# Janela (dias a partir de hoje) varrida a cada sincronização.
SYNC_WINDOW_DAYS = 30


def is_enabled() -> bool:
    return flags.is_enabled("calendar")


def _service():  # pragma: no cover - I/O com a API do Google
    from googleapiclient.discovery import build

    from . import google_auth

    return build(
        "calendar", "v3", credentials=google_auth.credentials([CALENDAR_SCOPE]),
        cache_discovery=False,
    )


def all_day_range(day: date) -> tuple[str, str]:
    """`(start.date, end.date)` de um evento de dia inteiro no Google Calendar.

    `end.date` é **exclusivo**: um evento de um dia em 06/08 vai de `2026-08-06` a `2026-08-07`.
    Com start igual a end o intervalo tem comprimento zero e a API **recusa** — ou seja, o botão
    "Adicionar ao calendário" falhava em 100% das tentativas. Passou despercebido porque
    `create_event` é I/O fora da cobertura e o único teste o substitui por um dublê; esta função
    existe separada justamente para a regra ficar testável sem rede.
    """
    return day.isoformat(), (day + timedelta(days=1)).isoformat()


def create_event(summary: str, day: date, description: str = "", origin: str = "") -> str:  # pragma: no cover - I/O
    service = _service()
    inicio, fim = all_day_range(day)
    body: dict = {
        "summary": summary,
        "description": description,
        "start": {"date": inicio},
        "end": {"date": fim},
    }
    if origin:
        body["extendedProperties"] = {"private": {ORIGIN_KEY: origin}}
    try:
        created = service.events().insert(
            calendarId=settings.GOOGLE_CALENDAR_ID, body=body
        ).execute()
    except Exception as exc:  # noqa: BLE001 - a família do SDK vira um tipo só
        raise CalendarProviderError(str(exc) or exc.__class__.__name__) from exc
    return created.get("htmlLink", "")


def create_timed_event(
    summary: str, start: datetime, end: datetime, description: str = "",
    attendee_email: str = "", origin: str = "",
) -> tuple[str, str]:  # pragma: no cover - I/O
    """Cria um evento com horário (não all-day), opcionalmente convidando o lead. Retorna (id, link)."""
    service = _service()
    body: dict = {
        "summary": summary,
        "description": description,
        "start": {"dateTime": start.isoformat()},
        "end": {"dateTime": end.isoformat()},
    }
    if attendee_email:
        body["attendees"] = [{"email": attendee_email}]
    if origin:
        body["extendedProperties"] = {"private": {ORIGIN_KEY: origin}}
    calendar_id = settings.GOOGLE_BOOKING_CALENDAR_ID or settings.GOOGLE_CALENDAR_ID
    try:
        created = service.events().insert(calendarId=calendar_id, body=body).execute()
    except Exception as exc:  # noqa: BLE001 - a família do SDK vira um tipo só
        # O caso conhecido é o `forbiddenForServiceAccounts`: conta de serviço não convida
        # participante sem delegação em todo o domínio (FDD 024). Quem chama decide o que fazer —
        # em `booking.book`, degradar sem perder a reserva.
        raise CalendarProviderError(str(exc) or exc.__class__.__name__) from exc
    return created.get("id", ""), created.get("htmlLink", "")


class CalendarUnavailable(RuntimeError):
    """O calendário não pôde ser consultado — e por isso nada pode ser afirmado sobre ele."""


def parse_freebusy(result: dict, calendar_id: str) -> list[tuple[datetime, datetime]]:
    """Extrai os períodos ocupados da resposta do free/busy. **Falha fechado.**

    Quando a conta de serviço não enxerga o calendário, o Google não devolve erro HTTP: devolve
    200 com `errors` no lugar de `busy` para aquele id. Ler isso com um `.get("busy", [])` produz
    "nenhum horário ocupado", ou seja, **tudo livre** — e o site passa a oferecer e marcar reunião
    por cima da agenda real. Um agendamento que falha aberto é pior que um que não funciona, então
    aqui a ausência de resposta utilizável vira exceção.
    """
    agenda = result.get("calendars", {}).get(calendar_id)
    if agenda is None:
        raise CalendarUnavailable(f"o free/busy não devolveu o calendário {calendar_id}")
    if agenda.get("errors"):
        motivos = ", ".join(str(e.get("reason", e)) for e in agenda["errors"])
        raise CalendarUnavailable(f"calendário {calendar_id} inacessível: {motivos}")
    if "busy" not in agenda:
        raise CalendarUnavailable(f"resposta de free/busy sem 'busy' para {calendar_id}")
    return [
        (datetime.fromisoformat(b["start"]), datetime.fromisoformat(b["end"]))
        for b in agenda["busy"]
    ]


def freebusy(time_min: datetime, time_max: datetime) -> list[tuple[datetime, datetime]]:  # pragma: no cover - I/O
    """Períodos ocupados do calendário de reservas no intervalo dado."""
    service = _service()
    calendar_id = settings.GOOGLE_BOOKING_CALENDAR_ID or settings.GOOGLE_CALENDAR_ID
    try:
        result = service.freebusy().query(body={
            "timeMin": time_min.isoformat(),
            "timeMax": time_max.isoformat(),
            "items": [{"id": calendar_id}],
        }).execute()
    except Exception as exc:  # noqa: BLE001 - a família do SDK vira um tipo só
        # `CalendarUnavailable` e não `CalendarProviderError`: o `parse_freebusy` já falha fechado
        # quando a **resposta** não permite afirmar nada sobre a agenda, e uma falha de transporte
        # é o mesmo caso um passo antes — não sabemos o que há na agenda. Vira 503, como a outra.
        raise CalendarUnavailable(f"não foi possível consultar {calendar_id}: {exc}") from exc
    return parse_freebusy(result, calendar_id)


def list_events(time_min: datetime, time_max: datetime) -> list[dict]:  # pragma: no cover - I/O
    service = _service()
    try:
        result = (
            service.events()
            .list(
                calendarId=settings.GOOGLE_CALENDAR_ID,
                timeMin=time_min.isoformat(),
                timeMax=time_max.isoformat(),
                singleEvents=True,
                orderBy="startTime",
            )
            .execute()
        )
    except Exception as exc:  # noqa: BLE001 - a família do SDK vira um tipo só
        raise CalendarProviderError(str(exc) or exc.__class__.__name__) from exc
    return result.get("items", [])


def _event_day(event: dict) -> date | None:
    """Data do evento: all-day (`start.date`) ou com horário (`start.dateTime`)."""
    start = event.get("start", {})
    if start.get("date"):
        return date.fromisoformat(start["date"])
    if start.get("dateTime"):
        return datetime.fromisoformat(start["dateTime"]).date()
    return None


def event_to_taskspec(event: dict) -> dict | None:
    """Mapeia um evento do Google Calendar para os dados de uma tarefa, ou `None` se deve ignorar.

    Ignora: eventos originados no Biahflow (evita loop), sem marcador `#proj-<id>`, sem id, ou sem data.
    """
    private = event.get("extendedProperties", {}).get("private", {})
    if private.get(ORIGIN_KEY):
        return None
    external_id = event.get("id")
    if not external_id:
        return None
    summary = event.get("summary", "")
    match = PROJECT_MARKER.search(f"{summary}\n{event.get('description', '')}")
    if not match:
        return None
    day = _event_day(event)
    if day is None:
        return None
    title = PROJECT_MARKER.sub("", summary).strip() or "Evento do calendário"
    return {
        "project_id": int(match.group(1)),
        "title": title,
        "due_date": day,
        "external_id": external_id,
    }


def sync_calendar(window_days: int = SYNC_WINDOW_DAYS) -> tuple[int, int]:
    """Cria tarefas a partir dos eventos do calendário. Retorna (criadas, ignoradas).

    No-op (0, 0) quando a integração está desligada. Idempotente: reprocessar os mesmos eventos
    não duplica tarefas (constraint única em `source`/`external_id`).
    """
    if not is_enabled():
        return (0, 0)

    from .models import Project, Task

    now = timezone.now()
    events = list_events(now, now + timedelta(days=window_days))
    created = skipped = 0
    for event in events:
        spec = event_to_taskspec(event)
        if spec is None:
            skipped += 1
            continue
        project = Project.objects.filter(id=spec["project_id"], archived_at__isnull=True).first()
        if project is None:
            skipped += 1
            continue
        _, was_created = Task.objects.get_or_create(
            source=CALENDAR_TASK_SOURCE,
            external_id=spec["external_id"],
            defaults={
                "project": project,
                "title": spec["title"],
                "owner": project.owner,
                "due_date": spec["due_date"],
            },
        )
        if was_created:
            created += 1
        else:
            skipped += 1
    return (created, skipped)
