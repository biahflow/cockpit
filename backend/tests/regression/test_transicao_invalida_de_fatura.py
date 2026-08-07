"""Regressão: transição de estado inválida é recusada com 400 (FDD 028).

O mapa `INVOICE_TRANSITIONS` só vale se houver **um** lugar por onde passar, e este teste cobre os
dois degraus da guarda do serializer, que existem por razões diferentes:

1. **o que não pode acontecer** — `paga → emitida` é o exemplo que a FDD nomeia. Uma fatura paga
   que volta a emitida é dinheiro que entrou e sumiu do registro;
2. **o que pode acontecer mas não por digitação** — emitir, baixar e cancelar são atos com autor,
   carimbo e, no caso da emissão, uma chamada ao gateway. Um `PATCH status=paid` não carrega a data
   do provedor nem quem baixou, e aceitá-lo produziria uma baixa sem procedência.

O segundo degrau é o que a mensagem torna útil: em vez de "transição inválida", ela diz **qual rota
usar**.
"""

import pytest
from rest_framework.test import APIClient

from apps.core.models import Invoice
from apps.core.tests.factories import InvoiceFactory, UserFactory


@pytest.fixture
def api():
    client = APIClient()
    client.force_authenticate(UserFactory(role="admin"))
    return client


@pytest.mark.django_db
def test_de_paga_para_emitida_e_recusado(api):
    fatura = InvoiceFactory(status=Invoice.Status.PAID, number="2026-7001")
    resposta = api.patch(f"/api/v1/invoices/{fatura.id}/", {"status": "issued"}, format="json")
    assert resposta.status_code == 400
    assert "Não é possível ir de Paga para Emitida." in str(resposta.data["status"])
    fatura.refresh_from_db()
    assert fatura.status == Invoice.Status.PAID


@pytest.mark.django_db
def test_de_cancelada_nao_se_sai(api):
    fatura = InvoiceFactory(status=Invoice.Status.CANCELLED, number="2026-7002")
    for alvo in ("issued", "paid", "overdue"):
        assert api.patch(
            f"/api/v1/invoices/{fatura.id}/", {"status": alvo}, format="json"
        ).status_code == 400
    fatura.refresh_from_db()
    assert fatura.status == Invoice.Status.CANCELLED


@pytest.mark.django_db
def test_de_rascunho_nao_se_pula_para_paga(api):
    fatura = InvoiceFactory()
    resposta = api.patch(f"/api/v1/invoices/{fatura.id}/", {"status": "paid"}, format="json")
    assert resposta.status_code == 400
    fatura.refresh_from_db()
    assert fatura.status == Invoice.Status.DRAFT


@pytest.mark.django_db
def test_transicao_que_existe_mas_e_ato_aponta_a_rota(api):
    fatura = InvoiceFactory()
    resposta = api.patch(f"/api/v1/invoices/{fatura.id}/", {"status": "issued"}, format="json")
    assert resposta.status_code == 400
    assert "/issue/" in str(resposta.data["status"])
    fatura.refresh_from_db()
    assert fatura.status == Invoice.Status.DRAFT
    assert fatura.number == ""  # nada de número sem passar pela emissão


@pytest.mark.django_db
def test_vencida_para_paga_continua_valendo(api):
    """A aresta que a FDD não escreveu — e sem a qual o webhook recusaria a baixa mais comum."""
    fatura = InvoiceFactory(status=Invoice.Status.OVERDUE, number="2026-7003")
    resposta = api.post(f"/api/v1/invoices/{fatura.id}/mark-paid/")
    assert resposta.status_code == 200
    fatura.refresh_from_db()
    assert fatura.status == Invoice.Status.PAID
