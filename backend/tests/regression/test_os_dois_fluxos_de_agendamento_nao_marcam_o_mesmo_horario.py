"""Regressão: pré-venda e Discovery disputam a mesma agenda, e nenhum dos dois marca por cima.

É a razão pela qual `Booking` passou a servir os dois fluxos em vez de o Discovery criar apenas o
evento no Google. A tentação era essa — o Design Partner não tem `Lead`, e a coluna era NOT NULL —,
mas o teste de conflito de `booking.book` consulta a **tabela `Booking`**, não o Google, e por um
motivo declarado no próprio código: a criação do evento é *best-effort* e pode falhar
(`CalendarProviderError`, o caso conhecido `forbiddenForServiceAccounts`). Um Discovery que só
existisse na agenda do Google deixaria o horário parecendo livre para o lead qualificado — e o
inverso também.

O defeito regride **calado**: as duas reservas acontecem, ninguém vê erro, e o conflito só aparece
na hora da reunião. Por isso a afirmação está aqui, e não só na suíte de cada fluxo.

As duas direções são testadas, e a terceira metade também: mesmo com o evento do Google
**falhando**, a reserva grava e continua bloqueando o horário para o outro fluxo.
"""

from datetime import datetime, time, timedelta

import pytest
from django.test import override_settings
from django.utils import timezone

from apps.core import booking, calendar_sync, design_partner
from apps.core.models import Booking, Document, Lead, SignatureRequest, User
from apps.core.tests.factories import AccountFactory, UserFactory

AGENDA_LIGADA = override_settings(
    CALENDAR_ENABLED=True, GOOGLE_CALENDAR_ID="cal", DISCOVERY_BOOKING_ENABLED=True
)


def _next_monday():
    today = timezone.localdate()
    return today + timedelta(days=(7 - today.weekday()) % 7 or 7)


def _at(day, hour: int) -> datetime:
    return timezone.make_aware(
        datetime.combine(day, time(hour, 0)), timezone.get_current_timezone()
    )


def _mandato():
    uploader = UserFactory(role=User.Role.ADMIN)
    document = Document.objects.create(
        account=AccountFactory(owner=uploader),
        original_name="acordo-design-partner.pdf",
        uploaded_by=uploader,
        kind=Document.Kind.DESIGN_PARTNER_AGREEMENT,
    )
    SignatureRequest.objects.create(
        document=document,
        signer_email="patrocinador@x.test",
        status=SignatureRequest.Status.SIGNED,
        signed_at=timezone.now(),
    )
    engagement = design_partner.abrir_engagement_do_acordo(document)
    assert engagement is not None
    return engagement


@pytest.fixture
def agenda_vazia(monkeypatch):
    """O Google não vê nada ocupado: quem tem de recusar é a tabela `Booking`, sozinha."""
    monkeypatch.setattr(calendar_sync, "freebusy", lambda a, b: [])
    monkeypatch.setattr(calendar_sync, "create_timed_event", lambda **kw: ("ev", "http://cal/ev"))


@pytest.mark.django_db
@AGENDA_LIGADA
def test_o_discovery_nao_marca_por_cima_da_pre_venda(agenda_vazia):
    UserFactory()
    slot = _at(_next_monday(), 9)
    booking.book(Lead.objects.create(name="Lead", email="lead@x.test"), slot)

    with pytest.raises(booking.SlotUnavailable):
        booking.book_discovery(_mandato(), slot, "patrocinador@x.test")

    assert Booking.objects.filter(starts_at=slot).count() == 1


@pytest.mark.django_db
@AGENDA_LIGADA
def test_a_pre_venda_nao_marca_por_cima_do_discovery(agenda_vazia):
    UserFactory()
    slot = _at(_next_monday(), 9)
    booking.book_discovery(_mandato(), slot, "patrocinador@x.test")

    with pytest.raises(booking.SlotUnavailable):
        booking.book(Lead.objects.create(name="Lead", email="lead@x.test"), slot)

    assert Booking.objects.filter(starts_at=slot).count() == 1


@pytest.mark.django_db
@AGENDA_LIGADA
def test_discovery_sem_evento_no_google_continua_bloqueando_o_horario(monkeypatch):
    """A linha existe **porque** o evento pode falhar — é aqui que isso vira afirmação."""
    monkeypatch.setattr(calendar_sync, "freebusy", lambda a, b: [])

    def recusa(**kwargs):
        raise calendar_sync.CalendarProviderError("forbiddenForServiceAccounts")

    monkeypatch.setattr(calendar_sync, "create_timed_event", recusa)
    UserFactory()
    slot = _at(_next_monday(), 9)

    reserva = booking.book_discovery(_mandato(), slot, "patrocinador@x.test")

    assert reserva.calendar_event_id == ""
    with pytest.raises(booking.SlotUnavailable):
        booking.book(Lead.objects.create(name="Lead", email="lead@x.test"), slot)


@pytest.mark.django_db
@AGENDA_LIGADA
def test_a_grade_de_horarios_desconta_as_reservas_dos_dois_fluxos(agenda_vazia):
    UserFactory()
    dia = _next_monday()
    booking.book(Lead.objects.create(name="Lead", email="lead@x.test"), _at(dia, 9))
    booking.book_discovery(_mandato(), _at(dia, 14), "patrocinador@x.test")

    livres = booking.available_slots(_at(dia, 0), _at(dia, 23))

    assert _at(dia, 9) not in livres
    assert _at(dia, 14) not in livres
