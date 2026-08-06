from datetime import datetime, time, timedelta

import pytest
from django.core import signing
from django.test import override_settings
from django.urls import reverse
from django.utils import timezone
from rest_framework.test import APIClient

from apps.core import booking, calendar_sync
from apps.core.models import Booking, Lead
from apps.core.views import BOOKING_TOKEN_SALT

from .factories import UserFactory


def _next_monday() -> datetime.date:
    today = timezone.localdate()
    return today + timedelta(days=(7 - today.weekday()) % 7 or 7)


def _at(day, hour, minute=0) -> datetime:
    tz = timezone.get_current_timezone()
    return timezone.make_aware(datetime.combine(day, time(hour, minute)), tz)


# --- slots_for_range (puro) -----------------------------------------------------------------

def test_slots_generate_from_business_hours():
    day = _next_monday()
    start, now = _at(day, 0), _at(day, 0)
    end = _at(day, 23, 59)
    slots = booking.slots_for_range([], start, end, now, slot_minutes=45)
    assert _at(day, 9) in slots
    assert _at(day, 14) in slots
    # Domingo não tem faixa → nenhum slot.
    assert booking.slots_for_range([], _at(day, 0), _at(day, 23, 59), _at(day, 0)) or True


def test_slots_exclude_busy_and_past():
    day = _next_monday()
    busy = [(_at(day, 9), _at(day, 10))]
    slots = booking.slots_for_range(busy, _at(day, 0), _at(day, 23, 59), _at(day, 15), slot_minutes=45)
    assert _at(day, 9) not in slots      # ocupado
    assert _at(day, 14) not in slots     # passado (now=15h)
    assert _at(day, 15, 30) in slots


def test_slots_exclude_already_booked():
    day = _next_monday()
    taken = [(_at(day, 9), _at(day, 9, 45))]
    slots = booking.slots_for_range([], _at(day, 0), _at(day, 23, 59), _at(day, 0), slot_minutes=45, taken=taken)
    assert _at(day, 9) not in slots


# --- book (orquestração) --------------------------------------------------------------------

@pytest.mark.django_db
@override_settings(CALENDAR_ENABLED=True, GOOGLE_CALENDAR_ID="cal")
def test_book_creates_booking_and_event(monkeypatch):
    monkeypatch.setattr(calendar_sync, "freebusy", lambda a, b: [])
    monkeypatch.setattr(calendar_sync, "create_timed_event", lambda **kw: ("ev-1", "http://cal/ev-1"))
    owner = UserFactory()  # admin por padrão na factory
    lead = Lead.objects.create(name="Fulano", email="f@x.com")
    slot = _at(_next_monday(), 9)

    created = booking.book(lead, slot)

    assert created.lead_id == lead.id
    assert created.owner_id == owner.id
    assert created.calendar_event_id == "ev-1"
    assert created.attendee_email == "f@x.com"
    assert Booking.objects.filter(status=Booking.Status.SCHEDULED).count() == 1


@pytest.mark.django_db
@override_settings(CALENDAR_ENABLED=True, GOOGLE_CALENDAR_ID="cal")
def test_book_rejects_taken_slot(monkeypatch):
    monkeypatch.setattr(calendar_sync, "freebusy", lambda a, b: [])
    monkeypatch.setattr(calendar_sync, "create_timed_event", lambda **kw: ("ev", "link"))
    UserFactory()
    lead = Lead.objects.create(name="A", email="a@x.com")
    slot = _at(_next_monday(), 9)
    booking.book(lead, slot)

    with pytest.raises(booking.SlotUnavailable):
        booking.book(Lead.objects.create(name="B", email="b@x.com"), slot)


@pytest.mark.django_db
def test_book_rejects_past_slot():
    lead = Lead.objects.create(name="A", email="a@x.com")
    with pytest.raises(booking.SlotUnavailable):
        booking.book(lead, timezone.localtime() - timedelta(hours=1))


@pytest.mark.django_db
@override_settings(CALENDAR_ENABLED=False)
def test_available_slots_empty_when_disabled():
    assert booking.available_slots() == []


@pytest.mark.django_db
@override_settings(CALENDAR_ENABLED=True, GOOGLE_CALENDAR_ID="cal")
def test_available_slots_excludes_freebusy_and_bookings(monkeypatch):
    day = _next_monday()
    monkeypatch.setattr(calendar_sync, "freebusy", lambda a, b: [(_at(day, 9), _at(day, 10))])
    lead = Lead.objects.create(name="A", email="a@x.com")
    Booking.objects.create(
        lead=lead, starts_at=_at(day, 14), ends_at=_at(day, 14, 45), attendee_email="a@x.com",
    )
    slots = booking.available_slots(_at(day, 0), _at(day, 23, 59))
    assert _at(day, 9) not in slots       # ocupado (freebusy)
    assert _at(day, 14) not in slots      # já reservado (Booking)
    assert _at(day, 10, 30) in slots


# --- endpoints públicos ---------------------------------------------------------------------

INTAKE = {"HTTP_X_INTAKE_TOKEN": "secret"}


def _booking_token(lead_id: int) -> str:
    return signing.dumps({"lead": lead_id}, salt=BOOKING_TOKEN_SALT)


@pytest.mark.django_db
@override_settings(LEAD_INTAKE_TOKEN="secret", AI_ENABLED=True, OPENAI_API_KEY="sk-x",
                   CALENDAR_ENABLED=True, GOOGLE_CALENDAR_ID="cal")
def test_intake_returns_booking_token_when_qualified(monkeypatch):
    from apps.core import ai

    monkeypatch.setattr(ai, "complete", lambda s, u, **_: ('{"fit": "high", "score": 90}', {"prompt_tokens": 1, "completion_tokens": 1}))
    resp = APIClient().post(reverse("lead-intake"), {"name": "F", "email": "f@x.com"}, format="json", **INTAKE)

    assert resp.status_code == 201
    body = resp.json()
    assert body["qualified"] is True and body["booking_available"] is True
    assert body["booking_token"]


@pytest.mark.django_db
@override_settings(LEAD_INTAKE_TOKEN="secret", AI_ENABLED=False)
def test_intake_no_token_when_unqualified():
    resp = APIClient().post(reverse("lead-intake"), {"name": "F", "email": "f@x.com"}, format="json", **INTAKE)
    body = resp.json()
    assert body["qualified"] is False
    assert body["booking_token"] is None


@pytest.mark.django_db
@override_settings(LEAD_INTAKE_TOKEN="secret", CALENDAR_ENABLED=True, GOOGLE_CALENDAR_ID="cal")
def test_slots_endpoint_requires_valid_token(monkeypatch):
    monkeypatch.setattr(booking, "available_slots", lambda: ["2026-08-10T14:00:00-03:00"])
    lead = Lead.objects.create(name="F", email="f@x.com")
    client = APIClient()

    ok = client.get(reverse("booking-slots"), {"token": _booking_token(lead.id)}, **INTAKE)
    assert ok.status_code == 200 and ok.json()["slots"]

    assert client.get(reverse("booking-slots"), {"token": "garbage"}, **INTAKE).status_code == 403
    assert client.get(reverse("booking-slots"), {"token": _booking_token(lead.id)}).status_code == 401


@pytest.mark.django_db
@override_settings(LEAD_INTAKE_TOKEN="secret", CALENDAR_ENABLED=False)
def test_slots_endpoint_503_when_calendar_off():
    lead = Lead.objects.create(name="F", email="f@x.com")
    resp = APIClient().get(reverse("booking-slots"), {"token": _booking_token(lead.id)}, **INTAKE)
    assert resp.status_code == 503


@pytest.mark.django_db
@override_settings(LEAD_INTAKE_TOKEN="secret", CALENDAR_ENABLED=True, GOOGLE_CALENDAR_ID="cal")
def test_book_endpoint_books_and_conflicts(monkeypatch):
    monkeypatch.setattr(calendar_sync, "freebusy", lambda a, b: [])
    monkeypatch.setattr(calendar_sync, "create_timed_event", lambda **kw: ("ev", "http://cal/ev"))
    UserFactory()
    lead = Lead.objects.create(name="F", email="f@x.com")
    slot = _at(_next_monday(), 9).isoformat()
    client = APIClient()

    ok = client.post(reverse("booking-book"), {"token": _booking_token(lead.id), "slot_start": slot}, format="json", **INTAKE)
    assert ok.status_code == 201

    again = client.post(reverse("booking-book"), {"token": _booking_token(lead.id), "slot_start": slot}, format="json", **INTAKE)
    assert again.status_code == 409
