"""Adaptador de gateway de pagamento (FDD 028) — Stripe e o `NullProvider`."""

import json
import time
from datetime import timedelta
from decimal import Decimal

import pytest
from django.test import override_settings
from django.utils import timezone

from apps.core import invoices, payments
from apps.core.models import Invoice
from apps.core.portal import sign

from .factories import InvoiceFactory

SEGREDO = "whsec_de_teste"
COM_STRIPE = override_settings(
    PAYMENTS_ENABLED=True,
    PAYMENTS_PROVIDER="stripe",
    PAYMENTS_API_TOKEN="sk_test_x",
    PAYMENTS_WEBHOOK_SECRET=SEGREDO,
)


def assinar(corpo: bytes, *, secret: str = SEGREDO, quando: int | None = None) -> str:
    t = str(quando if quando is not None else int(time.time()))
    return f"t={t},v1={sign(secret, t.encode() + b'.' + corpo)}"


# --- Seleção de provedor ------------------------------------------------------


def test_sem_provedor_cai_no_null():
    with override_settings(PAYMENTS_PROVIDER=""):
        assert isinstance(payments.get_provider(), payments.NullProvider)
        assert payments.has_provider() is False


def test_com_stripe_o_adaptador_e_o_stripe():
    with COM_STRIPE:
        assert isinstance(payments.get_provider(), payments.StripeProvider)
        assert payments.has_provider() is True


@pytest.mark.django_db
def test_null_provider_nao_promete_nada():
    fatura = InvoiceFactory()
    null = payments.NullProvider()
    assert null.charge(fatura) == payments.ChargeRef()
    assert null.verify(b"{}", {}) is False
    assert null.parse_event({"type": "invoice.paid"}) is None


# --- Falhar fechado -----------------------------------------------------------


@pytest.mark.django_db
def test_gateway_mudo_levanta_em_vez_de_devolver_referencia_vazia(monkeypatch):
    """A lição das quatro rodadas da FDD 024, agora com dinheiro em cima."""
    fatura = InvoiceFactory()
    with COM_STRIPE:
        monkeypatch.setattr(
            payments.StripeProvider, "charge", lambda self, invoice: payments.ChargeRef()
        )
        with pytest.raises(payments.PaymentProviderError):
            payments.issue_charge(fatura)


@pytest.mark.django_db
def test_sem_provedor_referencia_vazia_e_correta():
    fatura = InvoiceFactory()
    with override_settings(PAYMENTS_PROVIDER=""):
        assert payments.issue_charge(fatura) == payments.ChargeRef()


# --- Conversões que erram em silêncio quando erram ---------------------------


def test_centavos_nao_passam_por_float():
    """`int(float("18.99") * 100)` devolve 1898 — o erro clássico, e mudo."""
    assert payments.StripeProvider._cents(Decimal("18.99")) == 1899
    assert payments.StripeProvider._cents(Decimal("0.10")) == 10
    assert payments.StripeProvider._cents(Decimal("10000.01")) == 1000001


@pytest.mark.django_db
def test_dias_ate_vencer_nunca_e_negativo():
    """Emitir uma fatura já vencida é legítimo; o Stripe recusa `days_until_due` negativo."""
    atrasada = InvoiceFactory(due_date=timezone.localdate() - timedelta(days=5))
    assert payments.StripeProvider._days_until_due(atrasada) == 0


def test_leitura_da_resposta_de_finalize():
    ref = payments.StripeProvider._parse_finalized(
        {"id": "in_123", "hosted_invoice_url": "https://pay.stripe.com/i/123"}
    )
    assert ref.external_reference == "in_123"
    assert ref.provider == "stripe"
    # Resposta sem link não é cobrança: quem decide o que fazer com isso é `issue_charge`.
    assert payments.StripeProvider._parse_finalized({"id": "in_123"}) == payments.ChargeRef()
    assert payments.StripeProvider._parse_finalized(None) == payments.ChargeRef()


def test_sonda_distingue_teste_de_producao():
    ok, detalhe = payments.StripeProvider._parse_ping({"livemode": False})
    assert ok and "teste" in detalhe
    ok, detalhe = payments.StripeProvider._parse_ping({"livemode": True})
    assert ok and "produção" in detalhe
    assert payments.StripeProvider._parse_ping(None)[0] is False


# --- Assinatura do webhook ----------------------------------------------------


def test_assinatura_valida_passa():
    corpo = b'{"type":"invoice.paid"}'
    with COM_STRIPE:
        assert payments.StripeProvider().verify(
            corpo, {"Stripe-Signature": assinar(corpo)}
        ) is True


def test_assinatura_de_outro_segredo_nao_passa():
    corpo = b'{"type":"invoice.paid"}'
    with COM_STRIPE:
        assert payments.StripeProvider().verify(
            corpo, {"Stripe-Signature": assinar(corpo, secret="outro")}
        ) is False


def test_carimbo_fora_da_tolerancia_nao_passa():
    """Sem tolerância, um corpo assinado hoje seria reproduzível para sempre."""
    corpo = b'{"type":"invoice.paid"}'
    velho = int(time.time()) - 3600
    with COM_STRIPE:
        assert payments.StripeProvider().verify(
            corpo, {"Stripe-Signature": assinar(corpo, quando=velho)}
        ) is False


def test_header_com_dois_v1_durante_rotacao_de_segredo():
    """O Stripe manda mais de um `v1` ao rodar segredo; guardar só o último recusaria entrega boa."""
    corpo = b'{"type":"invoice.paid"}'
    t = str(int(time.time()))
    bom = sign(SEGREDO, t.encode() + b"." + corpo)
    header = f"t={t},v1={sign('antigo', t.encode() + b'.' + corpo)},v1={bom}"
    with COM_STRIPE:
        assert payments.StripeProvider().verify(corpo, {"Stripe-Signature": header}) is True


def test_header_malformado_nao_estoura():
    corpo = b"{}"
    with COM_STRIPE:
        provider = payments.StripeProvider()
        assert provider.verify(corpo, {}) is False
        assert provider.verify(corpo, {"Stripe-Signature": "lixo"}) is False
        assert provider.verify(corpo, {"Stripe-Signature": "t=abc,v1=def"}) is False


# --- De-para de eventos -------------------------------------------------------


def test_eventos_mapeados_e_o_que_de_proposito_nao_e():
    provider = payments.StripeProvider()
    pago = provider.parse_event(
        {
            "type": "invoice.paid",
            "created": 1770000000,
            "data": {"object": {"id": "in_9", "amount_paid": 250000}},
        }
    )
    assert pago is not None
    assert pago.status == "paid"
    assert pago.external_reference == "in_9"
    assert pago.amount == Decimal("2500")
    assert pago.paid_at is not None

    assert provider.parse_event({"type": "invoice.voided", "data": {"object": {"id": "in_9"}}}).status == "cancelled"
    # Tentativa recusada não muda nosso estado — a fatura segue emitida ou vencida.
    assert provider.parse_event({"type": "invoice.payment_failed", "data": {}}) is None
    assert provider.parse_event({"type": "customer.created", "data": {}}) is None


# --- Aplicação do evento ------------------------------------------------------


@pytest.mark.django_db
def test_evento_sem_fatura_correspondente_e_ignorado():
    assert payments.apply_event(payments.Event(status="paid", external_reference="in_nada")) is None


@pytest.mark.django_db
def test_reentrega_do_mesmo_evento_nao_recarimba():
    fatura = InvoiceFactory(
        status=Invoice.Status.ISSUED, number="2026-0100", external_reference="in_1"
    )
    momento = timezone.now() - timedelta(days=1)
    payments.apply_event(payments.Event(status="paid", external_reference="in_1", paid_at=momento))
    fatura.refresh_from_db()
    primeira = fatura.paid_at

    payments.apply_event(
        payments.Event(status="paid", external_reference="in_1", paid_at=timezone.now())
    )
    fatura.refresh_from_db()
    assert fatura.paid_at == primeira


@pytest.mark.django_db
def test_pagamento_nao_ressuscita_fatura_cancelada():
    """A divergência deliberada em relação a `esign.apply_event`: só a igualdade não cobre isto."""
    fatura = InvoiceFactory(
        status=Invoice.Status.ISSUED, number="2026-0101", external_reference="in_2"
    )
    invoices.cancel(fatura, None, "Escopo cancelado")

    payments.apply_event(payments.Event(status="paid", external_reference="in_2"))
    fatura.refresh_from_db()
    assert fatura.status == Invoice.Status.CANCELLED
    assert fatura.paid_at is None


@pytest.mark.django_db
def test_baixa_usa_a_data_do_provedor():
    fatura = InvoiceFactory(
        status=Invoice.Status.ISSUED, number="2026-0102", external_reference="in_3"
    )
    sexta = timezone.now() - timedelta(days=3)
    payments.apply_event(payments.Event(status="paid", external_reference="in_3", paid_at=sexta))
    fatura.refresh_from_db()
    assert fatura.paid_at == sexta


@pytest.mark.django_db
def test_cancelamento_no_gateway_fecha_a_fatura_aqui():
    fatura = InvoiceFactory(
        status=Invoice.Status.ISSUED, number="2026-0103", external_reference="in_4"
    )
    payments.apply_event(
        payments.Event(status="cancelled", external_reference="in_4", detail="invoice.voided")
    )
    fatura.refresh_from_db()
    assert fatura.status == Invoice.Status.CANCELLED
    assert "invoice.voided" in fatura.cancel_reason


# --- A rota do webhook --------------------------------------------------------


@pytest.mark.django_db
def test_webhook_desligado_responde_503(client):
    with override_settings(PAYMENTS_ENABLED=False):
        resposta = client.post(
            "/api/v1/payments/webhook/", data="{}", content_type="application/json"
        )
    assert resposta.status_code == 503


@pytest.mark.django_db
def test_webhook_sem_assinatura_responde_401(client):
    with COM_STRIPE:
        resposta = client.post(
            "/api/v1/payments/webhook/", data="{}", content_type="application/json"
        )
    assert resposta.status_code == 401


@pytest.mark.django_db
def test_webhook_baixa_a_fatura(client):
    fatura = InvoiceFactory(
        status=Invoice.Status.ISSUED, number="2026-0200", external_reference="in_ok"
    )
    corpo = json.dumps(
        {
            "type": "invoice.paid",
            "created": 1770000000,
            "data": {"object": {"id": "in_ok", "amount_paid": 100000}},
        }
    ).encode()
    with COM_STRIPE:
        resposta = client.post(
            "/api/v1/payments/webhook/",
            data=corpo,
            content_type="application/json",
            HTTP_STRIPE_SIGNATURE=assinar(corpo),
        )
    assert resposta.status_code == 200
    fatura.refresh_from_db()
    assert fatura.status == Invoice.Status.PAID


@pytest.mark.django_db
def test_evento_desconhecido_responde_200_para_o_fornecedor_parar_de_reentregar(client):
    corpo = json.dumps({"type": "customer.created", "data": {}}).encode()
    with COM_STRIPE:
        resposta = client.post(
            "/api/v1/payments/webhook/",
            data=corpo,
            content_type="application/json",
            HTTP_STRIPE_SIGNATURE=assinar(corpo),
        )
    assert resposta.status_code == 200
    assert resposta.json()["detail"] == "Evento ignorado."
