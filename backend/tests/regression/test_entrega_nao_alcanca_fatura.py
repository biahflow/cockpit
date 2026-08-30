"""Regressão: a Entrega não alcança rota de fatura nenhuma (FDD 028, ADR 0010).

A guarda é uma **ausência**: `invoice` não aparece em nenhum dos dois conjuntos da Entrega em
`RolePermission.has_permission`, e o `return False` do fim produz o 403. O teste existe porque uma
ausência é fácil de desfazer sem querer — basta alguém acrescentar `"invoice"` à lista ao lado
achando que corrige um bug de tela.

O detalhe que carrega o teste: o usuário **participa do projeto** da fatura. Se o `ProjectScopedMixin`
tivesse sido aplicado por reflexo (ele está em quase toda viewset que tem `project`), ou se `Invoice`
tivesse entrado no `PROJECT_OF`, a Entrega passaria — e passaria exatamente no caso que a FDD
recusa. Sem a participação, o teste passaria pelo motivo errado.

Vendas lê e não escreve, no mesmo molde do `case`.
"""

import pytest
from rest_framework.test import APIClient

from apps.core.models import Invoice
from apps.core.tests.factories import (
    InvoiceFactory,
    ProjectFactory,
    ProjectMemberFactory,
    UserFactory,
)


@pytest.fixture
def cenario():
    """Fatura de um projeto de que a pessoa da Entrega **participa**."""
    projeto = ProjectFactory()
    entrega = UserFactory(role="delivery")
    ProjectMemberFactory(project=projeto, user=entrega)
    fatura = InvoiceFactory(account=projeto.engagement.account, project=projeto)
    api = APIClient()
    api.force_authenticate(entrega)
    return api, fatura, projeto


@pytest.mark.django_db
def test_entrega_toma_403_ate_para_ler(cenario):
    api, fatura, _ = cenario
    assert api.get("/api/v1/invoices/").status_code == 403
    assert api.get(f"/api/v1/invoices/{fatura.id}/").status_code == 403
    assert api.get("/api/v1/invoices/summary/").status_code == 403


@pytest.mark.django_db
def test_entrega_toma_403_para_escrever(cenario):
    api, fatura, projeto = cenario
    assert api.post(
        "/api/v1/invoices/",
        {"account": projeto.engagement.account_id, "amount": "10.00", "due_date": "2026-12-01"},
        format="json",
    ).status_code == 403
    assert api.patch(
        f"/api/v1/invoices/{fatura.id}/", {"amount": "1.00"}, format="json"
    ).status_code == 403
    assert api.delete(f"/api/v1/invoices/{fatura.id}/").status_code == 403


@pytest.mark.django_db
def test_entrega_toma_403_nas_acoes(cenario):
    api, fatura, _ = cenario
    for rota in ("issue", "mark-paid", "cancel"):
        assert api.post(f"/api/v1/invoices/{fatura.id}/{rota}/").status_code == 403
    fatura.refresh_from_db()
    assert fatura.status == Invoice.Status.DRAFT


@pytest.mark.django_db
def test_vendas_le_e_nao_escreve():
    fatura = InvoiceFactory()
    api = APIClient()
    api.force_authenticate(UserFactory(role="sales"))

    assert api.get("/api/v1/invoices/").status_code == 200
    assert api.get(f"/api/v1/invoices/{fatura.id}/").status_code == 200
    assert api.patch(
        f"/api/v1/invoices/{fatura.id}/", {"amount": "1.00"}, format="json"
    ).status_code == 403
    assert api.post(f"/api/v1/invoices/{fatura.id}/issue/").status_code == 403


@pytest.mark.django_db
def test_entrega_toma_403_em_toda_rota_de_cobranca(cenario):
    """A régua herda a fronteira da fatura (FDD 036), pelo mesmo mecanismo: `cobranca` e
    `cobranca_suspensao` não aparecem em nenhum conjunto da Entrega, e o `return False` do fim
    produz o 403. Quem não alcança o recebível não alcança o que a casa disse sobre ele.

    Vale para as ações penduradas na fatura também — elas são `resource = "invoice"`, então já
    estavam fechadas; a asserção existe porque um `permission_classes` próprio numa action futura
    reabriria o caminho sem tocar em `RolePermission`.
    """
    api, fatura, _ = cenario
    assert api.get("/api/v1/cobranca/").status_code == 403
    assert api.get("/api/v1/cobranca/suspensoes/").status_code == 403
    assert api.post("/api/v1/cobranca/suspensoes/", {}, format="json").status_code == 403
    for rota in ("cobranca/rascunhar", "cobranca/enviar"):
        assert api.post(f"/api/v1/invoices/{fatura.id}/{rota}/").status_code == 403
