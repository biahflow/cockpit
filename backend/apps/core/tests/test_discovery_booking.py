"""O cliente marca o Discovery sozinho, pelo link que chega quando o mandato nasce.

FDD 013 + DAP `docs/design/dap-agendamento-discovery-r1/` (r1, decisões A1 · B1 · C1 · D1 · E2).

O que este arquivo afirma, em ordem de importância:

* os **quatro estados da D1** têm respostas distinguíveis — colapsá-los faria a página dizer
  "não há horário livre" quando o que houve foi a agenda não responder;
* o token de pré-venda **não** abre a porta do Discovery, nem o contrário (salts distintos);
* mandato com Discovery marcado recusa o segundo (C1, sem remarcação);
* o convite sai **uma** vez quando o mandato nasce, com o link e o nome certos;
* SMTP fora do ar **não** desfaz a assinatura nem o mandato;
* flag desligada tira as duas rotas do ar e cala o e-mail;
* `Booking` pertence a um lead **ou** a um engagement — no banco e no `clean()`.
"""

from datetime import datetime, time, timedelta

import pytest
from django.core import mail, signing
from django.core.exceptions import ValidationError
from django.db import IntegrityError, transaction
from django.test import override_settings
from django.urls import reverse
from django.utils import timezone
from rest_framework.test import APIClient

from apps.core import booking, calendar_sync, design_partner, discovery_booking, esign
from apps.core.models import (
    Booking,
    Contact,
    Document,
    Engagement,
    Lead,
    SignatureRequest,
    User,
)
from apps.core.views import BOOKING_TOKEN_SALT

from .factories import AccountFactory, UserFactory

LIGADA = override_settings(
    DISCOVERY_BOOKING_ENABLED=True, CALENDAR_ENABLED=True, GOOGLE_CALENDAR_ID="cal"
)


def _next_monday():
    today = timezone.localdate()
    return today + timedelta(days=(7 - today.weekday()) % 7 or 7)


def _at(day, hour, minute=0) -> datetime:
    tz = timezone.get_current_timezone()
    return timezone.make_aware(datetime.combine(day, time(hour, minute)), tz)


def _acordo_assinado(*, signer_email: str = "patrocinador@x.test") -> Document:
    uploader = UserFactory(role=User.Role.ADMIN)
    document = Document.objects.create(
        account=AccountFactory(owner=uploader, name="Padaria do Zé"),
        original_name="acordo-design-partner.pdf",
        uploaded_by=uploader,
        kind=Document.Kind.DESIGN_PARTNER_AGREEMENT,
    )
    SignatureRequest.objects.create(
        document=document,
        signer_email=signer_email,
        status=SignatureRequest.Status.SIGNED,
        signed_at=timezone.now(),
    )
    return document


def _mandato(*, signer_email: str = "patrocinador@x.test") -> Engagement:
    engagement = design_partner.abrir_engagement_do_acordo(_acordo_assinado(signer_email=signer_email))
    assert engagement is not None
    return engagement


def _convites() -> list[mail.EmailMessage]:
    assunto = discovery_booking.CONVITE_DO_DISCOVERY.assunto
    return [m for m in mail.outbox if m.subject == assunto]


# --- os quatro estados da decisão D1 ---------------------------------------------------------


@pytest.mark.django_db
@LIGADA
def test_link_expirado_responde_400_com_codigo_proprio(monkeypatch):
    engagement = _mandato()
    token = discovery_booking.token_for(engagement)
    # Envelhece o token empurrando a validade para zero: é o mesmo `SignatureExpired` que o
    # relógio produziria no décimo quinto dia.
    monkeypatch.setattr(discovery_booking, "DISCOVERY_BOOKING_TOKEN_MAX_AGE", -1)

    resp = APIClient().get(reverse("discovery-booking-slots"), {"token": token})

    assert resp.status_code == 400
    assert resp.json()["code"] == "token_expired"


@pytest.mark.django_db
@LIGADA
def test_link_invalido_responde_400_sem_dizer_o_motivo():
    """Assinatura adulterada e mandato inexistente devolvem a **mesma** resposta (D1)."""
    client = APIClient()

    adulterado = client.get(reverse("discovery-booking-slots"), {"token": "garbage"})
    inexistente = client.get(
        reverse("discovery-booking-slots"),
        {"token": signing.dumps(
            {"engagement": 999999}, salt=discovery_booking.DISCOVERY_BOOKING_TOKEN_SALT
        )},
    )

    assert adulterado.status_code == inexistente.status_code == 400
    assert adulterado.json() == inexistente.json()
    assert adulterado.json()["code"] == "token_invalid"


@pytest.mark.django_db
@LIGADA
def test_sem_horario_na_janela_responde_200_com_lista_vazia(monkeypatch):
    """Agenda cheia é resposta legítima, não falha — e é o estado que o 503 abaixo não é."""
    monkeypatch.setattr(booking, "available_slots_for_discovery", lambda: [])
    engagement = _mandato()

    resp = APIClient().get(
        reverse("discovery-booking-slots"),
        {"token": discovery_booking.token_for(engagement)},
    )

    assert resp.status_code == 200
    assert resp.json()["slots"] == []
    assert resp.json()["scheduled_at"] is None


@pytest.mark.django_db
@LIGADA
def test_agenda_fora_do_ar_responde_503(monkeypatch):
    def indisponivel():
        raise calendar_sync.CalendarUnavailable

    monkeypatch.setattr(booking, "available_slots_for_discovery", indisponivel)
    engagement = _mandato()

    resp = APIClient().get(
        reverse("discovery-booking-slots"),
        {"token": discovery_booking.token_for(engagement)},
    )

    assert resp.status_code == 503
    assert resp.json()["code"] == "calendar_unavailable"


# --- caminho feliz e identificação da conta (B1) ----------------------------------------------


@pytest.mark.django_db
@LIGADA
def test_a_pagina_recebe_o_nome_da_conta_e_os_horarios(monkeypatch):
    dia = _next_monday()
    monkeypatch.setattr(booking, "available_slots_for_discovery", lambda: [_at(dia, 9)])
    engagement = _mandato()

    resp = APIClient().get(
        reverse("discovery-booking-slots"),
        {"token": discovery_booking.token_for(engagement)},
    )

    assert resp.status_code == 200
    assert resp.json()["account"] == "Padaria do Zé"
    assert len(resp.json()["slots"]) == 1


@pytest.mark.django_db
@LIGADA
def test_marcar_cria_a_reserva_do_mandato_com_o_email_de_quem_assinou(monkeypatch):
    monkeypatch.setattr(calendar_sync, "freebusy", lambda a, b: [])
    monkeypatch.setattr(calendar_sync, "create_timed_event", lambda **kw: ("ev", "http://cal/ev"))
    UserFactory()
    engagement = _mandato(signer_email="quem.assinou@x.test")
    slot = _at(_next_monday(), 9)

    resp = APIClient().post(
        reverse("discovery-booking-create"),
        {"token": discovery_booking.token_for(engagement), "slot_start": slot.isoformat()},
        format="json",
    )

    assert resp.status_code == 201
    reserva = Booking.objects.get(engagement=engagement)
    assert reserva.lead_id is None
    assert reserva.starts_at == slot
    # O endereço sai do acordo assinado, nunca do corpo da requisição: quem tem o link não
    # redireciona o convite do Google para outra pessoa.
    assert reserva.attendee_email == "quem.assinou@x.test"


@pytest.mark.django_db
@LIGADA
def test_marcar_com_link_invalido_responde_400():
    resp = APIClient().post(
        reverse("discovery-booking-create"),
        {"token": "garbage", "slot_start": _at(_next_monday(), 9).isoformat()},
        format="json",
    )

    assert resp.status_code == 400
    assert resp.json()["code"] == "token_invalid"


@pytest.mark.django_db
@LIGADA
def test_marcar_horario_ja_tomado_responde_409(monkeypatch):
    """O horário foi para outro entre carregar a página e clicar — 409, com código próprio."""
    monkeypatch.setattr(calendar_sync, "freebusy", lambda a, b: [])
    monkeypatch.setattr(calendar_sync, "create_timed_event", lambda **kw: ("ev", "link"))
    UserFactory()
    slot = _at(_next_monday(), 9)
    booking.book(Lead.objects.create(name="Lead", email="lead@x.test"), slot)
    engagement = _mandato()

    resp = APIClient().post(
        reverse("discovery-booking-create"),
        {"token": discovery_booking.token_for(engagement), "slot_start": slot.isoformat()},
        format="json",
    )

    assert resp.status_code == 409
    assert resp.json()["code"] == "slot_unavailable"
    assert not Booking.objects.filter(engagement=engagement).exists()


@pytest.mark.django_db
@LIGADA
def test_marcar_com_a_agenda_fora_do_ar_responde_503(monkeypatch):
    def indisponivel(a, b):
        raise calendar_sync.CalendarUnavailable

    monkeypatch.setattr(calendar_sync, "freebusy", indisponivel)
    UserFactory()
    engagement = _mandato()

    resp = APIClient().post(
        reverse("discovery-booking-create"),
        {
            "token": discovery_booking.token_for(engagement),
            "slot_start": _at(_next_monday(), 9).isoformat(),
        },
        format="json",
    )

    assert resp.status_code == 503
    assert resp.json()["code"] == "calendar_unavailable"


# --- decisão C1: sem remarcação ---------------------------------------------------------------


@pytest.mark.django_db
@LIGADA
def test_mandato_com_discovery_marcado_recusa_o_segundo(monkeypatch):
    monkeypatch.setattr(calendar_sync, "freebusy", lambda a, b: [])
    monkeypatch.setattr(calendar_sync, "create_timed_event", lambda **kw: ("ev", "link"))
    UserFactory()
    engagement = _mandato()
    booking.book_discovery(engagement, _at(_next_monday(), 9), "quem@x.test")

    resp = APIClient().post(
        reverse("discovery-booking-create"),
        {
            "token": discovery_booking.token_for(engagement),
            "slot_start": _at(_next_monday(), 10).isoformat(),
        },
        format="json",
    )

    assert resp.status_code == 409
    assert resp.json()["code"] == "already_scheduled"
    assert Booking.objects.filter(engagement=engagement).count() == 1


@pytest.mark.django_db
@LIGADA
def test_reabrir_o_link_mostra_o_horario_marcado(monkeypatch):
    monkeypatch.setattr(calendar_sync, "freebusy", lambda a, b: [])
    monkeypatch.setattr(calendar_sync, "create_timed_event", lambda **kw: ("ev", "link"))
    UserFactory()
    engagement = _mandato()
    slot = _at(_next_monday(), 9)
    booking.book_discovery(engagement, slot, "quem@x.test")

    resp = APIClient().get(
        reverse("discovery-booking-slots"),
        {"token": discovery_booking.token_for(engagement)},
    )

    assert resp.status_code == 200
    assert resp.json()["scheduled_at"] is not None
    assert resp.json()["slots"] == []


# --- os dois salts não se confundem ------------------------------------------------------------


@pytest.mark.django_db
@LIGADA
@override_settings(LEAD_INTAKE_TOKEN="secret")
def test_token_de_pre_venda_nao_serve_na_rota_do_discovery():
    lead = Lead.objects.create(name="F", email="f@x.com")
    token_da_pre_venda = signing.dumps({"lead": lead.id}, salt=BOOKING_TOKEN_SALT)

    resp = APIClient().get(reverse("discovery-booking-slots"), {"token": token_da_pre_venda})

    assert resp.status_code == 400
    assert resp.json()["code"] == "token_invalid"


@pytest.mark.django_db
@LIGADA
@override_settings(LEAD_INTAKE_TOKEN="secret")
def test_token_do_discovery_nao_serve_na_rota_de_pre_venda():
    engagement = _mandato()
    token_do_discovery = discovery_booking.token_for(engagement)

    resp = APIClient().get(
        reverse("booking-slots"),
        {"token": token_do_discovery},
        HTTP_X_INTAKE_TOKEN="secret",
    )

    assert resp.status_code == 403


# --- o convite ---------------------------------------------------------------------------------


@pytest.mark.django_db
@LIGADA
def test_o_convite_sai_uma_vez_quando_o_mandato_nasce():
    uploader = UserFactory(role=User.Role.ADMIN)
    document = Document.objects.create(
        account=AccountFactory(owner=uploader, name="Padaria do Zé"),
        original_name="acordo-design-partner.pdf",
        uploaded_by=uploader,
        kind=Document.Kind.DESIGN_PARTNER_AGREEMENT,
    )
    signature = SignatureRequest.objects.create(document=document, signer_email="ze@x.test")

    esign.apply_decision(signature.pk, SignatureRequest.Status.SIGNED)
    # Reentrega do webhook: a idempotência de `apply_decision` cobre o convite também.
    esign.apply_decision(signature.pk, SignatureRequest.Status.SIGNED)

    convites = _convites()
    assert len(convites) == 1
    assert convites[0].to == ["ze@x.test"]
    assert "Olá, Padaria do Zé." in convites[0].body

    engagement = Engagement.objects.get(originating_design_partner_agreement=document)
    # O token carrega carimbo de tempo e muda a cada `dumps`, então o que se afirma não é o texto
    # do link e sim o mandato que ele **abre**.
    token = convites[0].body.split("/agendar/")[1].split("\n")[0].strip()
    assert discovery_booking.engagement_from_token(token).pk == engagement.pk


@pytest.mark.django_db
@LIGADA
def test_o_convite_chama_quem_assinou_pelo_primeiro_nome():
    """O board aprovado abre com "Olá, Sarah." — a pessoa, não a organização.

    `SignatureRequest` guarda o e-mail de quem assina e nunca o nome; quem tem os dois é a conta,
    e é pelo e-mail que os dois registros se encontram. Sem esta busca o convite abriria com
    "Olá, Rio Home Care.", trocando a pessoa pela organização no ato mais pessoal do fluxo.
    """
    uploader = UserFactory(role=User.Role.ADMIN)
    account = AccountFactory(owner=uploader, name="Rio Home Care")
    Contact.objects.create(
        account=account, first_name="Sarah", last_name="Bignon",
        email="sarah@riohomecare.test",
    )
    document = Document.objects.create(
        account=account,
        original_name="acordo-design-partner.pdf",
        uploaded_by=uploader,
        kind=Document.Kind.DESIGN_PARTNER_AGREEMENT,
    )
    signature = SignatureRequest.objects.create(
        document=document, signer_email="SARAH@riohomecare.test"
    )

    esign.apply_decision(signature.pk, SignatureRequest.Status.SIGNED)

    convites = _convites()
    assert len(convites) == 1
    # Case-insensitive de propósito: o fornecedor de assinatura devolve o e-mail como o signatário
    # o digitou, e um contato cadastrado em minúsculas não pode deixar de ser encontrado por isso.
    assert "Olá, Sarah." in convites[0].body
    assert "Rio Home Care" not in convites[0].body


@pytest.mark.django_db
@LIGADA
def test_assinatura_de_documento_comum_nao_manda_convite():
    uploader = UserFactory(role=User.Role.ADMIN)
    document = Document.objects.create(
        account=AccountFactory(owner=uploader),
        original_name="contrato-comercial.pdf",
        uploaded_by=uploader,
    )
    signature = SignatureRequest.objects.create(document=document, signer_email="ze@x.test")

    esign.apply_decision(signature.pk, SignatureRequest.Status.SIGNED)

    assert _convites() == []


@pytest.mark.django_db
@LIGADA
def test_smtp_fora_do_ar_nao_desfaz_a_assinatura_nem_o_mandato(monkeypatch):
    def explode(*args, **kwargs):
        raise OSError("SMTP recusou a conexão")

    monkeypatch.setattr(discovery_booking, "send_mail", explode)
    uploader = UserFactory(role=User.Role.ADMIN)
    document = Document.objects.create(
        account=AccountFactory(owner=uploader),
        original_name="acordo-design-partner.pdf",
        uploaded_by=uploader,
        kind=Document.Kind.DESIGN_PARTNER_AGREEMENT,
    )
    signature = SignatureRequest.objects.create(document=document, signer_email="ze@x.test")

    esign.apply_decision(signature.pk, SignatureRequest.Status.SIGNED)

    signature.refresh_from_db()
    assert signature.status == SignatureRequest.Status.SIGNED
    assert Engagement.objects.filter(originating_design_partner_agreement=document).count() == 1


# --- a flag ------------------------------------------------------------------------------------


@pytest.mark.django_db
@override_settings(
    DISCOVERY_BOOKING_ENABLED=False, CALENDAR_ENABLED=True, GOOGLE_CALENDAR_ID="cal"
)
def test_flag_desligada_tira_as_rotas_do_ar():
    with override_settings(DISCOVERY_BOOKING_ENABLED=True):
        engagement = _mandato()
        token = discovery_booking.token_for(engagement)
    client = APIClient()

    slots = client.get(reverse("discovery-booking-slots"), {"token": token})
    marcar = client.post(
        reverse("discovery-booking-create"),
        {"token": token, "slot_start": _at(_next_monday(), 9).isoformat()},
        format="json",
    )

    assert slots.status_code == marcar.status_code == 503
    assert slots.json()["code"] == "booking_disabled"


@pytest.mark.django_db
@override_settings(DISCOVERY_BOOKING_ENABLED=False)
def test_flag_desligada_nao_manda_convite():
    uploader = UserFactory(role=User.Role.ADMIN)
    document = Document.objects.create(
        account=AccountFactory(owner=uploader),
        original_name="acordo-design-partner.pdf",
        uploaded_by=uploader,
        kind=Document.Kind.DESIGN_PARTNER_AGREEMENT,
    )
    signature = SignatureRequest.objects.create(document=document, signer_email="ze@x.test")

    esign.apply_decision(signature.pk, SignatureRequest.Status.SIGNED)

    # O mandato continua nascendo — a flag governa o convite e as rotas, não o Design Partner.
    assert Engagement.objects.filter(originating_design_partner_agreement=document).count() == 1
    assert _convites() == []


@pytest.mark.django_db
@LIGADA
def test_smtp_que_recusa_nao_conta_como_convite_enviado(monkeypatch):
    """`fail_silently=True` devolve `0`; somar um envio ali faria o log afirmar entrega que não houve."""
    monkeypatch.setattr(discovery_booking, "send_mail", lambda *a, **kw: 0)

    assert discovery_booking.enviar_convite(_mandato(), "ze@x.test") is False


@pytest.mark.django_db
@override_settings(
    DISCOVERY_BOOKING_ENABLED=True, CALENDAR_ENABLED=False, GOOGLE_CALENDAR_ID=""
)
def test_calendario_desligado_tira_as_rotas_do_ar():
    engagement = _mandato()

    resp = APIClient().get(
        reverse("discovery-booking-slots"),
        {"token": discovery_booking.token_for(engagement)},
    )

    assert resp.status_code == 503


# --- `Booking` pertence a exatamente uma origem -------------------------------------------------


@pytest.mark.django_db
def test_reserva_sem_origem_nenhuma_e_recusada_pelo_banco():
    dia = _next_monday()
    with pytest.raises(IntegrityError), transaction.atomic():
        Booking.objects.create(
            starts_at=_at(dia, 9), ends_at=_at(dia, 9, 45), attendee_email="a@x.com"
        )


@pytest.mark.django_db
def test_reserva_com_as_duas_origens_e_recusada_pelo_banco():
    dia = _next_monday()
    lead = Lead.objects.create(name="A", email="a@x.com")
    engagement = _mandato()
    with pytest.raises(IntegrityError), transaction.atomic():
        Booking.objects.create(
            lead=lead, engagement=engagement,
            starts_at=_at(dia, 9), ends_at=_at(dia, 9, 45), attendee_email="a@x.com",
        )


@pytest.mark.django_db
def test_clean_espelha_a_restricao_de_exatamente_uma_origem():
    dia = _next_monday()
    lead = Lead.objects.create(name="A", email="a@x.com")
    engagement = _mandato()

    with pytest.raises(ValidationError):
        Booking(
            starts_at=_at(dia, 9), ends_at=_at(dia, 9, 45), attendee_email="a@x.com"
        ).full_clean()
    with pytest.raises(ValidationError):
        Booking(
            lead=lead, engagement=engagement,
            starts_at=_at(dia, 9), ends_at=_at(dia, 9, 45), attendee_email="a@x.com",
        ).full_clean()

    # E a reserva de uma origem só passa pelas duas portas.
    Booking(
        engagement=engagement,
        starts_at=_at(dia, 9), ends_at=_at(dia, 9, 45), attendee_email="a@x.com",
    ).full_clean()
