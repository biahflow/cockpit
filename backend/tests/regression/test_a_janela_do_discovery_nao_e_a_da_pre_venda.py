"""Regressão: o Discovery oferta uma janela estreita, e a pré-venda continua com a larga.

O primeiro teste em uso mostrou 80 opções na página do Discovery — 14 dias corridos × todos os
horários livres da grade. Lista longa demais para uma escolha (DAP `dap-agendamento-discovery-r1`,
emenda de 02/09): passa a ser **3 dias** de prazo, **5 dias com grade** e **3 horários por dia**.

**O que este arquivo protege é a diferença.** `available_slots` e `available_slots_for_discovery`
compartilham a agenda (`_slots_livres`) e nada mais; a próxima varredura que achar duas funções
parecidas e "simplificar" unificando-as quebra a rota pública do site — que oferta a janela inteira
de propósito — sem nada mais ficar vermelho.
"""

from datetime import datetime, time, timedelta

import pytest
from django.test import override_settings
from django.utils import timezone

from apps.core import booking, calendar_sync

pytestmark = pytest.mark.django_db

LIGADA = override_settings(CALENDAR_ENABLED=True, GOOGLE_CALENDAR_ID="cal")


def _at(day, hour, minute=0) -> datetime:
    tz = timezone.get_current_timezone()
    return timezone.make_aware(datetime.combine(day, time(hour, minute)), tz)


def _agenda_vazia(monkeypatch) -> None:
    monkeypatch.setattr(calendar_sync, "freebusy", lambda a, b: [])


# --- a janela (pura) ------------------------------------------------------------------------


def test_a_janela_comeca_tres_dias_depois() -> None:
    agora = _at(timezone.localdate(), 10)
    inicio, _ = booking.discovery_window(agora)
    assert inicio == agora + timedelta(days=booking.DISCOVERY_LEAD_TIME_DAYS)


def test_a_janela_conta_dias_com_grade_e_nao_dias_corridos() -> None:
    """Cinco dias úteis a partir de uma quinta-feira terminam na quarta seguinte.

    Contando corrido, a janela morreria no domingo e entregaria três dias de oferta — o defeito
    que a constante `DISCOVERY_BUSINESS_DAYS` existe para não ter.
    """
    # 2026-09-10 é uma quinta-feira; `now` é três dias antes para o prazo cair nela.
    quinta = datetime(2026, 9, 10).date()
    agora = _at(quinta - timedelta(days=booking.DISCOVERY_LEAD_TIME_DAYS), 9)

    inicio, fim = booking.discovery_window(agora)

    assert inicio.date() == quinta
    # qui, sex, seg, ter, qua — cinco dias com grade, e o fim é a quarta da semana seguinte.
    assert fim.date() == datetime(2026, 9, 16).date()
    com_grade = [
        inicio.date() + timedelta(days=n)
        for n in range((fim.date() - inicio.date()).days + 1)
        if booking.BOOKING_HOURS.get((inicio.date() + timedelta(days=n)).weekday())
    ]
    assert len(com_grade) == booking.DISCOVERY_BUSINESS_DAYS


# --- os três do dia (pura) ------------------------------------------------------------------


def test_tres_do_dia_pega_manha_tarde_e_ultimo() -> None:
    dia = datetime(2026, 9, 14).date()  # segunda
    livres = [_at(dia, 9), _at(dia, 9, 45), _at(dia, 10, 30), _at(dia, 14), _at(dia, 15, 30)]

    assert booking.tres_do_dia(livres) == [_at(dia, 9), _at(dia, 14), _at(dia, 15, 30)]


def test_tres_do_dia_nao_repete_quando_os_papeis_coincidem() -> None:
    """A primeira da tarde **é** a última do dia: dois papéis, um horário, uma opção."""
    dia = datetime(2026, 9, 14).date()
    livres = [_at(dia, 9), _at(dia, 14)]

    assert booking.tres_do_dia(livres) == [_at(dia, 9), _at(dia, 14)]


def test_tres_do_dia_oferece_o_que_existe_quando_ha_menos_de_tres() -> None:
    dia = datetime(2026, 9, 14).date()
    assert booking.tres_do_dia([_at(dia, 15, 30)]) == [_at(dia, 15, 30)]


def test_o_dia_sem_horario_livre_nao_aparece() -> None:
    dia = datetime(2026, 9, 14).date()
    outro = datetime(2026, 9, 15).date()
    livres = [_at(outro, 9)]

    escolhidos = booking.tres_do_dia(livres)

    assert [s.date() for s in escolhidos] == [outro]
    assert dia not in {s.date() for s in escolhidos}


def test_tres_do_dia_separa_os_dias() -> None:
    a, b = datetime(2026, 9, 14).date(), datetime(2026, 9, 15).date()
    livres = [_at(a, 9), _at(a, 14), _at(a, 16, 15), _at(b, 9), _at(b, 9, 45)]

    escolhidos = booking.tres_do_dia(livres)

    assert escolhidos == [_at(a, 9), _at(a, 14), _at(a, 16, 15), _at(b, 9), _at(b, 9, 45)]


# --- a oferta inteira -----------------------------------------------------------------------


@LIGADA
def test_a_oferta_do_discovery_respeita_prazo_janela_e_teto(monkeypatch) -> None:
    _agenda_vazia(monkeypatch)
    agora = timezone.localtime()

    slots = booking.available_slots_for_discovery()

    assert slots, "a agenda está vazia: a oferta não pode ser vazia"
    assert min(slots) >= agora + timedelta(days=booking.DISCOVERY_LEAD_TIME_DAYS)
    dias = sorted({timezone.localtime(s).date() for s in slots})
    assert len(dias) <= booking.DISCOVERY_BUSINESS_DAYS
    for dia in dias:
        do_dia = [s for s in slots if timezone.localtime(s).date() == dia]
        assert len(do_dia) <= 3, f"{dia} ofereceu {len(do_dia)} horários"


@override_settings(CALENDAR_ENABLED=False)
def test_a_oferta_do_discovery_e_vazia_com_a_agenda_desligada() -> None:
    assert booking.available_slots_for_discovery() == []


@override_settings(
    DISCOVERY_BOOKING_ENABLED=True, CALENDAR_ENABLED=True, GOOGLE_CALENDAR_ID="cal"
)
def test_a_rota_publica_do_discovery_oferta_a_janela_estreita(monkeypatch) -> None:
    """A função certa existir não basta: o que o cliente vê é o que a rota chama."""
    from django.urls import reverse
    from rest_framework.test import APIClient

    from apps.core import discovery_booking
    from apps.core.tests.factories import EngagementFactory

    _agenda_vazia(monkeypatch)
    engagement = EngagementFactory()

    resposta = APIClient().get(
        reverse("discovery-booking-slots"),
        {"token": discovery_booking.token_for(engagement)},
    )

    assert resposta.status_code == 200
    slots = [datetime.fromisoformat(s) for s in resposta.json()["slots"]]
    assert slots
    dias = sorted({timezone.localtime(s).date() for s in slots})
    assert len(dias) <= booking.DISCOVERY_BUSINESS_DAYS
    for dia in dias:
        assert len([s for s in slots if timezone.localtime(s).date() == dia]) <= 3


@LIGADA
def test_a_pre_venda_continua_com_a_janela_antiga(monkeypatch) -> None:
    """A regressão que impede unificar as duas ofertas.

    A rota pública do site oferta 14 dias corridos e todo horário livre; se alguém trocá-la pela
    janela do Discovery, o lead qualificado passa a ver três opções por dia e ninguém percebe.
    """
    _agenda_vazia(monkeypatch)
    agora = timezone.localtime()

    slots = booking.available_slots()

    assert min(slots) < agora + timedelta(days=booking.DISCOVERY_LEAD_TIME_DAYS)
    dias = {timezone.localtime(s).date() for s in slots}
    assert len(dias) > booking.DISCOVERY_BUSINESS_DAYS
    # Ao menos um dia com mais de três horários: é o teto que a pré-venda não tem.
    contagem = max(
        len([s for s in slots if timezone.localtime(s).date() == dia]) for dia in dias
    )
    assert contagem > 3
