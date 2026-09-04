"""Regressão: o ROI é exatamente o mesmo antes e depois de existirem faturas (FDD 028, RFC 0004).

É a maior ameaça declarada da RFC 0004, e ela não é um bug — é uma **deriva**. No instante em que a
fatura existe, passam a existir duas verdades sobre receita: `Project.actual_value`, que sempre
alimentou o ROI, e a soma das faturas pagas. Sem decisão explícita, alguém "corrige" o `_roi` para
somar faturas num commit de terça, e o número muda em seis lugares de uma vez — inclusive no bloco
de ROI que `portal.build_snapshot` **já entrega à tela do cliente**.

A FDD 028 decidiu: `actual_value` é o **valor contratado**, a soma das faturas pagas é o
**recebido**, e nenhum consumidor muda. Trocar a fonte é mudança de contrato e exigia ADR próprio.

**A ADR 0067 (04/09/2026) é essa decisão, e ela é: a fonte não muda.** O ROI segue saindo do
contratado nos seis leitores, e o recebido ganha nome próprio quando for construído — nunca o
rótulo do ROI. Este teste deixou de ser um congelamento à espera de decisão e passou a ser a
guarda **daquela** decisão: um PR que faça o `_roi` somar faturas contradiz uma ADR aceita.

O teste é diferencial de propósito. Ele não afirma que o ROI vale tal número — afirma que o corpo
inteiro das respostas é **idêntico** antes e depois, o que continua valendo quando alguém mexer
legitimamente na fórmula. Cobre os seis leitores que a FDD nomeia, incluindo os dois que não são
rota HTTP.
"""

from datetime import timedelta
from decimal import Decimal

import pytest
from django.utils import timezone
from rest_framework.test import APIClient

from apps.core import agents, health, invoices, portal
from apps.core.models import Invoice, Service
from apps.core.tests.factories import (
    AccountFactory,
    InvoiceFactory,
    ProjectFactory,
    UserFactory,
)


@pytest.fixture
def cenario():
    admin = UserFactory(role="admin")
    api = APIClient()
    api.force_authenticate(admin)
    cliente = AccountFactory()
    projeto = ProjectFactory(
        engagement__account=cliente,
        owner=admin,
        service=Service.objects.get(tier="prove"),
        actual_value=Decimal("120000.00"),
        cost=Decimal("80000.00"),
    )
    return api, projeto, admin


def _fotografar(api, projeto, admin):
    """Os seis leitores de `actual_value` que a FDD 028 nomeia, num retrato só."""
    return {
        "analytics": api.get("/api/v1/analytics/").data,
        "clients_overview": api.get("/api/v1/clients/overview/").data,
        "client_overview": api.get(f"/api/v1/clients/{projeto.engagement.account_id}/overview/").data,
        "portal_snapshot": portal.build_snapshot(projeto).get("roi"),
        "health": health.assess_project_health(projeto),
        "finance_context": agents.build_finance_context(admin),
    }


@pytest.mark.django_db
def test_o_roi_nao_muda_quando_faturas_passam_a_existir(cenario):
    api, projeto, admin = cenario
    antes = _fotografar(api, projeto, admin)

    # O ciclo inteiro da camada 0: semear, emitir e receber.
    assert invoices.seed_invoices(projeto) == 3
    for fatura in projeto.invoices.all():
        api.post(f"/api/v1/invoices/{fatura.id}/issue/")
    primeira = projeto.invoices.order_by("due_date").first()
    api.post(f"/api/v1/invoices/{primeira.id}/mark-paid/")

    assert Invoice.objects.filter(status=Invoice.Status.PAID).count() == 1
    assert _fotografar(api, projeto, admin) == antes


@pytest.mark.django_db
def test_fatura_vencida_tambem_nao_mexe_no_roi(cenario):
    """Inadimplência é sinal financeiro, não sinal de saúde — ainda não, e não por acidente."""
    api, projeto, admin = cenario
    antes = _fotografar(api, projeto, admin)

    InvoiceFactory(
        account=projeto.engagement.account,
        project=projeto,
        status=Invoice.Status.OVERDUE,
        number="2026-6001",
        amount=Decimal("50000.00"),
        due_date=timezone.localdate() - timedelta(days=90),
    )
    assert _fotografar(api, projeto, admin) == antes


@pytest.mark.django_db
def test_o_snapshot_do_cliente_nao_ganha_fatura(cenario):
    """Nada deste recorte cruza ao portal do cliente — a FDD é explícita."""
    api, projeto, admin = cenario
    invoices.seed_invoices(projeto)
    snapshot = portal.build_snapshot(projeto)

    assert "invoices" not in snapshot
    assert "faturas" not in snapshot
    serializado = str(snapshot)
    assert "Implantação — entrada" not in serializado
