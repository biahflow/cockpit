"""Contas a receber — domínio e API (FDD 028)."""

from datetime import timedelta
from decimal import Decimal

import pytest
from django.utils import timezone
from rest_framework.test import APIClient

from apps.core import invoices
from apps.core.models import Invoice, PipelineStage, Service

from .factories import (
    ClientFactory,
    InvoiceFactory,
    OpportunityFactory,
    ProjectFactory,
    ServiceFactory,
    UserFactory,
)


@pytest.fixture
def admin_client_api():
    api = APIClient()
    api.force_authenticate(UserFactory(role="admin"))
    return api


# --- Cronograma e semeadura --------------------------------------------------


@pytest.mark.django_db
def test_discovery_express_nao_semeia_fatura():
    """O nível é gratuito: lista vazia, e não uma parcela de R$ 0,00."""
    servico = Service.objects.get(tier="discovery_express")
    projeto = ProjectFactory(service=servico, actual_value=Decimal("0"))
    assert invoices.seed_invoices(projeto) == 0
    assert projeto.invoices.count() == 0


@pytest.mark.django_db
def test_implantacao_semeia_tres_parcelas_em_rascunho():
    servico = Service.objects.get(tier="implantacao")
    projeto = ProjectFactory(service=servico, actual_value=Decimal("100000.00"))
    assert invoices.seed_invoices(projeto) == 3
    faturas = list(projeto.invoices.order_by("due_date"))
    assert [f.status for f in faturas] == ["draft"] * 3
    assert [f.amount for f in faturas] == [
        Decimal("30000.00"), Decimal("40000.00"), Decimal("30000.00")
    ]


@pytest.mark.django_db
def test_o_resto_dos_centavos_vai_na_ultima_parcela():
    """A soma das parcelas tem de bater **exatamente** com o contratado."""
    servico = Service.objects.get(tier="implantacao")
    projeto = ProjectFactory(
        service=servico,
        actual_value=Decimal("10000.01"),
        due_date=timezone.localdate() + timedelta(days=365),
    )
    invoices.seed_invoices(projeto)
    total = sum((f.amount for f in projeto.invoices.all()), Decimal("0"))
    assert total == Decimal("10000.01")


@pytest.mark.django_db
def test_servico_avulso_nao_semeia_nada():
    """Sem `tier` não há cronograma — errar uma cobrança é pior que não semear."""
    projeto = ProjectFactory(service=ServiceFactory(), actual_value=Decimal("50000.00"))
    assert invoices.seed_invoices(projeto) == 0


@pytest.mark.django_db
def test_nivel_pago_vendido_a_zero_nao_semeia():
    """A gratuidade é do **valor**, não do nível: `list_price=0` na semente da migração 0020."""
    servico = Service.objects.get(tier="implantacao")
    projeto = ProjectFactory(service=servico, actual_value=Decimal("0"), opportunity=None)
    assert invoices.seed_invoices(projeto) == 0


@pytest.mark.django_db
def test_semeadura_e_idempotente():
    servico = Service.objects.get(tier="discovery_assessment")
    projeto = ProjectFactory(service=servico, actual_value=Decimal("8000.00"))
    assert invoices.seed_invoices(projeto) == 2
    assert invoices.seed_invoices(projeto) == 0
    assert projeto.invoices.count() == 2


@pytest.mark.django_db
def test_valor_contratado_cai_para_a_oportunidade_e_depois_para_a_tabela():
    oportunidade = OpportunityFactory(estimated_value=Decimal("7777.00"))
    projeto = ProjectFactory(actual_value=Decimal("0"), opportunity=oportunidade)
    assert invoices.contracted_value(projeto) == Decimal("7777.00")

    servico = ServiceFactory(list_price=Decimal("333.00"))
    sozinho = ProjectFactory(actual_value=Decimal("0"), service=servico, opportunity=None)
    assert invoices.contracted_value(sozinho) == Decimal("333.00")


@pytest.mark.django_db
def test_vencimento_nao_passa_do_fim_do_projeto():
    """O mesmo grampo de `kickoff.seed_work_items`."""
    servico = Service.objects.get(tier="implantacao")
    projeto = ProjectFactory(
        service=servico,
        actual_value=Decimal("30000.00"),
        due_date=timezone.localdate() + timedelta(days=10),
    )
    invoices.seed_invoices(projeto)
    assert all(f.due_date <= projeto.due_date for f in projeto.invoices.all())


@pytest.mark.django_db
def test_conversao_de_oportunidade_semeia_o_cronograma(admin_client_api):
    ganha = PipelineStage.objects.get(kind=PipelineStage.Kind.WON)
    servico = Service.objects.get(tier="implantacao")
    oportunidade = OpportunityFactory(stage=ganha, service=servico)
    resposta = admin_client_api.post(
        f"/api/v1/opportunities/{oportunidade.id}/convert-to-project/",
        {
            "client": oportunidade.client_id,
            "name": "Implantação",
            "start_date": str(timezone.localdate()),
            "due_date": str(timezone.localdate() + timedelta(days=120)),
            "actual_value": "60000.00",
        },
        format="json",
    )
    assert resposta.status_code == 201
    faturas = Invoice.objects.filter(project_id=resposta.data["id"])
    assert faturas.count() == 3
    assert set(faturas.values_list("status", flat=True)) == {"draft"}


# --- Numeração e transições --------------------------------------------------


@pytest.mark.django_db
def test_numero_e_sequencial_dentro_do_ano():
    ano = timezone.localdate().year
    assert invoices.next_number() == f"{ano}-0001"
    InvoiceFactory(number=f"{ano}-0001", status=Invoice.Status.ISSUED)
    assert invoices.next_number() == f"{ano}-0002"


@pytest.mark.django_db
def test_varios_rascunhos_coexistem_sem_numero():
    """A constraint de número é **parcial**; um `unique=True` simples deixaria um rascunho só."""
    InvoiceFactory()
    InvoiceFactory()
    assert Invoice.objects.filter(number="").count() == 2


@pytest.mark.django_db
def test_transicoes_validas_e_invalidas():
    fatura = InvoiceFactory()
    invoices.transition(fatura, Invoice.Status.ISSUED)  # não levanta
    with pytest.raises(invoices.InvoiceTransitionError):
        invoices.transition(fatura, Invoice.Status.PAID)  # rascunho não pula para paga

    fatura.status = Invoice.Status.PAID
    with pytest.raises(invoices.InvoiceTransitionError):
        invoices.transition(fatura, Invoice.Status.ISSUED)


@pytest.mark.django_db
def test_fatura_vencida_pode_ser_paga():
    """A aresta que a FDD não escreveu e sem a qual o webhook recusaria a baixa mais comum."""
    fatura = InvoiceFactory(status=Invoice.Status.OVERDUE, number="2026-0001")
    baixada = invoices.settle(fatura)
    assert baixada.status == Invoice.Status.PAID
    assert baixada.paid_at is not None


@pytest.mark.django_db
def test_baixa_e_idempotente():
    momento = timezone.now() - timedelta(days=2)
    fatura = InvoiceFactory(status=Invoice.Status.ISSUED, number="2026-0002")
    invoices.settle(fatura, at=momento)
    primeira = fatura.paid_at
    invoices.settle(fatura, at=timezone.now())
    fatura.refresh_from_db()
    assert fatura.paid_at == primeira


# --- Vencimento --------------------------------------------------------------


@pytest.mark.django_db
def test_job_marca_vencidas_e_e_idempotente():
    ontem = timezone.localdate() - timedelta(days=1)
    atrasada = InvoiceFactory(status=Invoice.Status.ISSUED, number="2026-0010", due_date=ontem)
    rascunho = InvoiceFactory(due_date=ontem)
    paga = InvoiceFactory(status=Invoice.Status.PAID, number="2026-0011", due_date=ontem)

    assert invoices.mark_overdue() == 1
    assert invoices.mark_overdue() == 0  # segunda rodada do dia não mexe em nada

    for fatura in (atrasada, rascunho, paga):
        fatura.refresh_from_db()
    assert atrasada.status == Invoice.Status.OVERDUE
    assert rascunho.status == Invoice.Status.DRAFT  # nunca foi cobrado
    assert paga.status == Invoice.Status.PAID


@pytest.mark.django_db
def test_vencer_hoje_nao_e_atrasar_hoje():
    InvoiceFactory(
        status=Invoice.Status.ISSUED, number="2026-0020", due_date=timezone.localdate()
    )
    assert invoices.mark_overdue() == 0


@pytest.mark.django_db
def test_is_overdue_nao_espera_o_job():
    """Entre a virada do dia e o job das 06:00 a tela precisa dizer a verdade."""
    fatura = InvoiceFactory(
        status=Invoice.Status.ISSUED,
        number="2026-0030",
        due_date=timezone.localdate() - timedelta(days=1),
    )
    assert fatura.is_overdue is True


# --- API ---------------------------------------------------------------------


@pytest.mark.django_db
def test_emitir_numera_carimba_e_registra_autor(admin_client_api):
    fatura = InvoiceFactory()
    resposta = admin_client_api.post(f"/api/v1/invoices/{fatura.id}/issue/")
    assert resposta.status_code == 200
    fatura.refresh_from_db()
    assert fatura.status == Invoice.Status.ISSUED
    assert fatura.number.startswith(str(timezone.localdate().year))
    assert fatura.issued_at is not None
    assert fatura.issued_by is not None


@pytest.mark.django_db
def test_emitir_duas_vezes_responde_409(admin_client_api):
    fatura = InvoiceFactory()
    admin_client_api.post(f"/api/v1/invoices/{fatura.id}/issue/")
    assert admin_client_api.post(f"/api/v1/invoices/{fatura.id}/issue/").status_code == 409


@pytest.mark.django_db
def test_fatura_de_valor_zero_nao_se_emite(admin_client_api):
    fatura = InvoiceFactory(amount=Decimal("0"))
    assert admin_client_api.post(f"/api/v1/invoices/{fatura.id}/issue/").status_code == 400


@pytest.mark.django_db
def test_cancelar_exige_motivo(admin_client_api):
    fatura = InvoiceFactory()
    admin_client_api.post(f"/api/v1/invoices/{fatura.id}/issue/")
    assert admin_client_api.post(f"/api/v1/invoices/{fatura.id}/cancel/").status_code == 400

    resposta = admin_client_api.post(
        f"/api/v1/invoices/{fatura.id}/cancel/", {"reason": "Escopo cancelado"}, format="json"
    )
    assert resposta.status_code == 200
    fatura.refresh_from_db()
    assert fatura.status == Invoice.Status.CANCELLED
    assert fatura.cancel_reason == "Escopo cancelado"
    assert fatura.cancelled_by is not None
    assert fatura.number  # o número sobrevive ao cancelamento


@pytest.mark.django_db
def test_baixa_manual_e_o_caminho_sem_gateway(admin_client_api):
    fatura = InvoiceFactory()
    admin_client_api.post(f"/api/v1/invoices/{fatura.id}/issue/")
    resposta = admin_client_api.post(
        f"/api/v1/invoices/{fatura.id}/mark-paid/", {"method": "pix"}, format="json"
    )
    assert resposta.status_code == 200
    fatura.refresh_from_db()
    assert fatura.status == Invoice.Status.PAID
    assert fatura.method == "pix"
    assert fatura.settled_by is not None


@pytest.mark.django_db
def test_rascunho_se_descarta(admin_client_api):
    fatura = InvoiceFactory()
    assert admin_client_api.delete(f"/api/v1/invoices/{fatura.id}/").status_code == 204
    assert not Invoice.objects.filter(pk=fatura.pk).exists()


@pytest.mark.django_db
def test_campos_travados_depois_de_emitida(admin_client_api):
    fatura = InvoiceFactory()
    admin_client_api.post(f"/api/v1/invoices/{fatura.id}/issue/")
    resposta = admin_client_api.patch(
        f"/api/v1/invoices/{fatura.id}/", {"amount": "99999.00"}, format="json"
    )
    assert resposta.status_code == 400
    assert "amount" in resposta.data
    fatura.refresh_from_db()
    assert fatura.amount == Decimal("1000.00")


@pytest.mark.django_db
def test_rascunho_ainda_se_edita(admin_client_api):
    fatura = InvoiceFactory()
    resposta = admin_client_api.patch(
        f"/api/v1/invoices/{fatura.id}/", {"amount": "2500.00"}, format="json"
    )
    assert resposta.status_code == 200
    fatura.refresh_from_db()
    assert fatura.amount == Decimal("2500.00")


@pytest.mark.django_db
def test_estado_que_tem_acao_por_tras_nao_se_digita(admin_client_api):
    fatura = InvoiceFactory()
    resposta = admin_client_api.patch(
        f"/api/v1/invoices/{fatura.id}/", {"status": "issued"}, format="json"
    )
    assert resposta.status_code == 400
    assert "issue" in str(resposta.data["status"])


@pytest.mark.django_db
def test_summary_soma_por_faixa(admin_client_api):
    cliente = ClientFactory()
    InvoiceFactory(client=cliente, status=Invoice.Status.ISSUED, number="2026-1001",
                   amount=Decimal("100.00"))
    InvoiceFactory(client=cliente, status=Invoice.Status.OVERDUE, number="2026-1002",
                   amount=Decimal("200.00"))
    InvoiceFactory(client=cliente, status=Invoice.Status.PAID, number="2026-1003",
                   amount=Decimal("300.00"))
    InvoiceFactory(client=cliente, amount=Decimal("999.00"))  # rascunho não entra em faixa nenhuma

    dados = admin_client_api.get("/api/v1/invoices/summary/").data
    assert Decimal(dados["open"]) == Decimal("100.00")
    assert Decimal(dados["overdue"]) == Decimal("200.00")
    assert Decimal(dados["paid"]) == Decimal("300.00")
    assert dados["overdue_count"] == 1
