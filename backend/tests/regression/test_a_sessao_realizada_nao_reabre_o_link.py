"""Regressão: fechar a sessão não pode devolver ao cliente a chance de marcar outra.

Duas metades, cada uma correta sozinha, abriam um buraco juntas — e é o tipo de defeito que só
aparece olhando as duas ao mesmo tempo:

- o job `sessions_held` passa a reserva para `held` no dia seguinte ao da sessão, porque nada no
  sistema fazia isso e a casa nunca ficava sabendo que a conversa aconteceu;
- `discovery_booking.discovery_agendado` respondia "há sessão marcada?" filtrando por
  `status=SCHEDULED`.

Juntas: o cliente reabre o link do convite — que vale duas semanas — no dia seguinte à conversa,
a página encontra "nenhuma sessão marcada", oferece horários de novo, e ele marca um **segundo**
Discovery. Ganha um convite do Google para uma sessão que ninguém vai fazer, e a decisão C1 do
DAP (*não remarca*) é contornada sem ninguém mexer nela.

A pergunta que decide não é "há sessão no futuro?", é "este mandato já teve seu Discovery
marcado?" — e o que responde "não" a ela é o cancelamento, não o tempo passar.
"""

from datetime import timedelta

import pytest
from django.test import override_settings
from django.urls import reverse
from django.utils import timezone
from rest_framework.test import APIClient

from apps.core import booking, discovery_booking
from apps.core.models import Booking, Engagement
from apps.core.tests.factories import AccountFactory, EngagementFactory

pytestmark = pytest.mark.django_db

LIGADA = override_settings(
    DISCOVERY_BOOKING_ENABLED=True, CALENDAR_ENABLED=True, GOOGLE_CALENDAR_ID="cal"
)


def _mandato() -> Engagement:
    return EngagementFactory(
        account=AccountFactory(), commercial_model=Engagement.CommercialModel.DESIGN_PARTNER
    )


def _sessao_de_ontem(engagement: Engagement) -> Booking:
    ontem = timezone.localtime() - timedelta(days=1)
    return Booking.objects.create(
        engagement=engagement,
        starts_at=ontem,
        ends_at=ontem + timedelta(minutes=45),
        attendee_email="quem@x.test",
    )


@LIGADA
def test_a_sessao_realizada_continua_valendo_como_marcada():
    engagement = _mandato()
    _sessao_de_ontem(engagement)

    reservas, _ = booking.fechar_sessoes_realizadas()

    assert reservas == 1, "a sessão de ontem deveria ter sido fechada pelo job"
    assert discovery_booking.discovery_agendado(engagement) is not None, (
        "sessão realizada continua sendo a sessão deste mandato — senão o link reabre"
    )


@LIGADA
def test_o_link_nao_oferece_horarios_depois_da_sessao_acontecer():
    """O efeito observável, pela rota pública que o cliente abre."""
    engagement = _mandato()
    sessao = _sessao_de_ontem(engagement)
    booking.fechar_sessoes_realizadas()

    resposta = APIClient().get(
        reverse("discovery-booking-slots"),
        {"token": discovery_booking.token_for(engagement)},
    )

    assert resposta.status_code == 200
    assert resposta.data["slots"] == [], "a página não pode oferecer um segundo Discovery"
    assert resposta.data["scheduled_at"] is not None
    # O instante, e não o dia: os dois lados guardam UTC e comparar `.date()` faria o teste
    # depender da hora em que a suíte roda — verde de manhã, vermelho às nove da noite.
    assert resposta.data["scheduled_at"] == sessao.starts_at


@LIGADA
def test_sessao_cancelada_libera_o_link():
    """A outra metade: cancelar **é** o que responde "não teve" — e aí a página volta a oferecer."""
    engagement = _mandato()
    reserva = _sessao_de_ontem(engagement)
    reserva.status = Booking.Status.CANCELED
    reserva.save(update_fields=["status", "updated_at"])

    assert discovery_booking.discovery_agendado(engagement) is None
