"""Regressão: fatura emitida não é apagada por caminho nenhum (FDD 028, ADR 0021).

É a invariante mais forte deste recorte, e ela contraria a regra da casa: dezesseis modelos
arquivam em vez de apagar (FDD 025), e a fatura **nem arquiva nem apaga**. Cancela-se, e o registro
sobrevive ao próprio cancelamento.

O teste confere as quatro camadas que sustentam isso, porque cada uma sozinha tem um furo:

1. a viewset recusa com 409 e a mensagem aponta o cancelamento — é ela que **explica**;
2. o cancelamento não abre a porta: apagar depois de cancelada continua 409;
3. o `pre_delete` pega quem não passa pela viewset (shell, migração, cascata);
4. a `CheckConstraint` mantém `archived_at` nulo, então nem arquivar por baixo funciona.

E confere o lado permitido, que é o que faz a regra ser uma regra e não uma parede: rascunho se
descarta normalmente.
"""

from decimal import Decimal

import pytest
from django.db import transaction
from django.db.models import ProtectedError
from django.db.utils import IntegrityError
from django.utils import timezone
from rest_framework.test import APIClient

from apps.core.models import Invoice
from apps.core.tests.factories import InvoiceFactory, UserFactory


@pytest.fixture
def api():
    client = APIClient()
    client.force_authenticate(UserFactory(role="admin"))
    return client


@pytest.mark.django_db
def test_delete_em_fatura_emitida_responde_409_e_aponta_o_cancelamento(api):
    fatura = InvoiceFactory()
    api.post(f"/api/v1/invoices/{fatura.id}/issue/")

    resposta = api.delete(f"/api/v1/invoices/{fatura.id}/")
    assert resposta.status_code == 409
    assert "ancel" in resposta.data["detail"]  # a saída está dita na mensagem
    assert Invoice.objects.filter(pk=fatura.pk).exists()


@pytest.mark.django_db
def test_o_registro_sobrevive_ao_proprio_cancelamento(api):
    fatura = InvoiceFactory()
    api.post(f"/api/v1/invoices/{fatura.id}/issue/")
    api.post(f"/api/v1/invoices/{fatura.id}/cancel/", {"reason": "Escopo cancelado"}, format="json")

    assert api.delete(f"/api/v1/invoices/{fatura.id}/").status_code == 409
    fatura.refresh_from_db()
    assert fatura.status == Invoice.Status.CANCELLED
    assert fatura.number  # o número não é liberado; a sequência fica com buracos, e tudo bem


@pytest.mark.django_db
def test_delete_fora_da_api_tambem_e_recusado():
    """A parede atrás da boa mensagem: shell, migração de dados e cascata não passam pela viewset."""
    fatura = InvoiceFactory(status=Invoice.Status.ISSUED, number="2026-9001")
    # Cada tentativa no próprio savepoint: o `delete()` do Django roda dentro de um `atomic`, e a
    # exceção deixa a transação do teste quebrada para o que vier depois se não houver por onde
    # voltar. É o mesmo cuidado que `invoices.finish_issue` toma com o `IntegrityError`.
    with pytest.raises(ProtectedError), transaction.atomic():
        fatura.delete()
    with pytest.raises(ProtectedError), transaction.atomic():
        Invoice.objects.filter(pk=fatura.pk).delete()
    assert Invoice.objects.filter(pk=fatura.pk).exists()


@pytest.mark.django_db
def test_arquivar_uma_fatura_e_impossivel_no_banco():
    """`archived_at` vem herdado de `TimestampedModel` e a constraint o mantém nulo para sempre.

    Arquivar seria pior que apagar: esconde da lista sem desfazer o fato, e um recebível que sai do
    total em aberto em silêncio é exatamente o defeito que este modelo existe para não ter.
    """
    fatura = InvoiceFactory(status=Invoice.Status.ISSUED, number="2026-9002")
    with pytest.raises(IntegrityError), transaction.atomic():
        Invoice.objects.filter(pk=fatura.pk).update(archived_at=timezone.now())


@pytest.mark.django_db
def test_rascunho_se_descarta_normalmente(api):
    """A regra tem lado permitido — senão seria parede, não regra."""
    fatura = InvoiceFactory(amount=Decimal("100.00"))
    assert api.delete(f"/api/v1/invoices/{fatura.id}/").status_code == 204
    assert not Invoice.objects.filter(pk=fatura.pk).exists()
