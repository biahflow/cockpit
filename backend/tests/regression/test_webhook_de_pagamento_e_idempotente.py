"""Regressão: reentrega do webhook não duplica baixa nem reabre fatura fechada (FDD 028).

Duas garantias, e a segunda não decorre da primeira.

**Não duplica** é a igualdade de status, o mesmo mecanismo de `esign.apply_event`: o Stripe manda
`invoice.paid` e `invoice.payment_succeeded` para o *mesmo* pagamento, e ainda reentrega por dias
quando desconfia de falha. Se cada entrega recarimbasse `paid_at`, a data do pagamento passaria a
ser a data da última reentrega — e é justamente ela que a camada 0 existe para medir.

**Não reabre fatura fechada** é o mapa de transições, e é a divergência deliberada em relação ao
molde do e-sign: lá o alvo é sempre alcançável, aqui um `paid` chegando numa fatura cancelada
ressuscitaria um recebível que um humano encerrou.
"""

import json
import time

import pytest
from django.test import override_settings
from django.utils import timezone

from apps.core import invoices
from apps.core.models import Invoice
from apps.core.portal import sign
from apps.core.tests.factories import InvoiceFactory

SEGREDO = "whsec_regressao"
COM_STRIPE = override_settings(
    PAYMENTS_ENABLED=True,
    PAYMENTS_PROVIDER="stripe",
    PAYMENTS_API_TOKEN="sk_test_x",
    PAYMENTS_WEBHOOK_SECRET=SEGREDO,
)


def entregar(client, referencia: str, tipo: str = "invoice.paid"):
    corpo = json.dumps(
        {
            "type": tipo,
            "created": 1770000000,
            "data": {"object": {"id": referencia, "amount_paid": 100000}},
        }
    ).encode()
    t = str(int(time.time()))
    return client.post(
        "/api/v1/payments/webhook/",
        data=corpo,
        content_type="application/json",
        HTTP_STRIPE_SIGNATURE=f"t={t},v1={sign(SEGREDO, t.encode() + b'.' + corpo)}",
    )


@pytest.mark.django_db
def test_a_mesma_entrega_duas_vezes_nao_muda_nada(client):
    fatura = InvoiceFactory(
        status=Invoice.Status.ISSUED, number="2026-8001", external_reference="in_dup"
    )
    with COM_STRIPE:
        assert entregar(client, "in_dup").status_code == 200
        fatura.refresh_from_db()
        primeira = fatura.paid_at
        assert fatura.status == Invoice.Status.PAID

        assert entregar(client, "in_dup").status_code == 200

    fatura.refresh_from_db()
    assert fatura.paid_at == primeira
    assert Invoice.objects.filter(external_reference="in_dup").count() == 1


@pytest.mark.django_db
def test_os_dois_eventos_do_mesmo_pagamento_dao_uma_baixa_so(client):
    """O Stripe manda `invoice.paid` e `invoice.payment_succeeded` juntos, e a ordem pode inverter."""
    fatura = InvoiceFactory(
        status=Invoice.Status.ISSUED, number="2026-8002", external_reference="in_par"
    )
    with COM_STRIPE:
        entregar(client, "in_par", tipo="invoice.payment_succeeded")
        fatura.refresh_from_db()
        primeira = fatura.paid_at
        entregar(client, "in_par", tipo="invoice.paid")

    fatura.refresh_from_db()
    assert fatura.status == Invoice.Status.PAID
    assert fatura.paid_at == primeira


@pytest.mark.django_db
def test_pagamento_nao_reabre_fatura_cancelada(client):
    fatura = InvoiceFactory(
        status=Invoice.Status.ISSUED, number="2026-8003", external_reference="in_morta"
    )
    invoices.cancel(fatura, None, "Contrato distratado")

    with COM_STRIPE:
        assert entregar(client, "in_morta").status_code == 200

    fatura.refresh_from_db()
    assert fatura.status == Invoice.Status.CANCELLED
    assert fatura.paid_at is None


@pytest.mark.django_db
def test_entrega_forjada_nao_baixa_nada(client):
    """HMAC de outro segredo é 401, e nada acontece com a fatura."""
    fatura = InvoiceFactory(
        status=Invoice.Status.ISSUED, number="2026-8004", external_reference="in_falso"
    )
    corpo = json.dumps({"type": "invoice.paid", "data": {"object": {"id": "in_falso"}}}).encode()
    t = str(int(time.time()))
    with COM_STRIPE:
        resposta = client.post(
            "/api/v1/payments/webhook/",
            data=corpo,
            content_type="application/json",
            HTTP_STRIPE_SIGNATURE=f"t={t},v1={sign('outro_segredo', t.encode() + b'.' + corpo)}",
        )
    assert resposta.status_code == 401
    fatura.refresh_from_db()
    assert fatura.status == Invoice.Status.ISSUED


@pytest.mark.django_db
def test_entrega_antiga_capturada_nao_vale_mais(client):
    """Sem a tolerância de carimbo, um corpo assinado hoje seria reproduzível para sempre."""
    fatura = InvoiceFactory(
        status=Invoice.Status.ISSUED, number="2026-8005", external_reference="in_velho"
    )
    corpo = json.dumps({"type": "invoice.paid", "data": {"object": {"id": "in_velho"}}}).encode()
    antigo = str(int(time.time()) - 86400)
    with COM_STRIPE:
        resposta = client.post(
            "/api/v1/payments/webhook/",
            data=corpo,
            content_type="application/json",
            HTTP_STRIPE_SIGNATURE=f"t={antigo},v1={sign(SEGREDO, antigo.encode() + b'.' + corpo)}",
        )
    assert resposta.status_code == 401
    fatura.refresh_from_db()
    assert fatura.status == Invoice.Status.ISSUED
    assert timezone.now() is not None  # o relógio do teste é o real, não um congelado
