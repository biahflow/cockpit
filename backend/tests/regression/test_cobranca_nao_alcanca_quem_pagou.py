"""Regressão: ninguém que pagou é cobrado (FDD 036, RFC 0004).

É **o pecado capital** que a RFC nomeia — *"o pecado capital da cobrança é cobrar quem já pagou;
destrói confiança num toque"* — e por isso tem regressão própria, separada da suíte da régua.

O que este arquivo defende não é uma rotina de cancelamento: é uma **propriedade de desenho**. A
régua é derivada do estado atual da fatura (ADR 0031), e `paid`/`cancelled` são terminais no
`INVOICE_TRANSITIONS` — então não há nada pendente para o pagamento cancelar. Uma fila de mensagens
agendadas teria o modo de falha oposto: a baixa entra às 14h, o worker já tinha o e-mail na mão, e
quem pagou de manhã é cobrado à tarde. Quem "otimizar" `cobranca.py` para uma tabela de mensagens
agendadas faz este teste ficar vermelho, que é exatamente o serviço dele.

O cenário é o que importa: a baixa acontece **entre duas execuções** da régua, no dia em que o
degrau seguinte estava para sair.
"""

from datetime import date, timedelta

import pytest
from django.core import mail
from django.test import override_settings

from apps.core import cobranca, invoices
from apps.core.models import Contact, DunningContact, Invoice
from apps.core.tests.factories import InvoiceFactory, UserFactory

HOJE = date(2026, 9, 2)  # quarta-feira


@pytest.fixture
def vencida() -> Invoice:
    """Fatura vencida há 9 dias, com contato de cobrança: amanhã cai o degrau firme."""
    invoice = InvoiceFactory(
        status=Invoice.Status.OVERDUE,
        number="2026-0001",
        due_date=HOJE - timedelta(days=9),
    )
    Contact.objects.create(
        account=invoice.account, first_name="Financeiro", email="financeiro@cliente.test",
        receives_billing=True,
    )
    return invoice


@pytest.mark.django_db
@override_settings(DUNNING_ENABLED=True)
def test_a_baixa_entre_duas_execucoes_cala_a_regua(vencida: Invoice) -> None:
    primeira = cobranca.executar(HOJE)
    assert primeira["contatos"] == 1  # o lembrete saiu
    assert len(mail.outbox) == 1

    invoices.settle(vencida, by=UserFactory())

    # Amanhã seria o dia do degrau firme — e não é mais dia de nada.
    segunda = cobranca.executar(HOJE + timedelta(days=1))

    assert segunda["contatos"] == 0
    # Zero **avaliadas**: a fatura paga nem entra na consulta do job.
    assert segunda["avaliadas"] == 0
    assert len(mail.outbox) == 1
    assert list(DunningContact.objects.values_list("dunning_step", flat=True)) == ["reminder"]


@pytest.mark.django_db
def test_a_guarda_de_estado_recusa_a_fatura_paga_por_si_so(vencida: Invoice) -> None:
    """A mesma regra escrita duas vezes, e as duas precisam de teste.

    `executar` filtra por `status__in=COBRAVEIS` na consulta **e** `avaliar` recusa o estado não
    cobrável. Ou uma sozinha já impediria o defeito — e é exatamente por isso que remover *uma
    delas* não quebra nada visível, e o próximo refactor levaria a outra junto. Este teste guarda a
    guarda; o de cima guarda o filtro.
    """
    invoices.settle(vencida, by=UserFactory())
    vencida.refresh_from_db()

    assert cobranca.avaliar(vencida, HOJE + timedelta(days=1)).motivo == (
        cobranca.ESTADO_NAO_COBRAVEL
    )
    assert cobranca.degrau_devido(vencida, HOJE + timedelta(days=1)) is None


@pytest.mark.django_db
@override_settings(DUNNING_ENABLED=True)
def test_nem_a_fatura_cancelada_nem_a_renegociada_recebem_degrau() -> None:
    """`cancelled` e `renegotiated` são terminais pela mesma razão, e a régua não os distingue de
    `paid`: nenhum dos três é um recebível em aberto."""
    for indice, estado in enumerate(
        (Invoice.Status.CANCELLED, Invoice.Status.RENEGOTIATED, Invoice.Status.DRAFT)
    ):
        InvoiceFactory(
            status=estado, number=f"2026-{indice + 10:04d}", due_date=HOJE - timedelta(days=45)
        )

    resumo = cobranca.executar(HOJE)

    assert resumo["avaliadas"] == 0  # nem entram na consulta
    assert DunningContact.objects.count() == 0
    assert mail.outbox == []


@pytest.mark.django_db
def test_a_regua_nao_tem_fila_para_o_pagamento_cancelar() -> None:
    """A guarda estrutural, e é ela que sobrevive a um refactor.

    Se um dia existir uma tabela de mensagens agendadas, o pagamento passará a precisar cancelá-la
    — e a corrida entre a baixa e o worker aparece uma vez por trimestre, com um cliente irritado do
    outro lado. `DunningContact` registra o **passado** (`sent_on`), nunca um futuro.
    """
    campos = {campo.name for campo in DunningContact._meta.get_fields()}
    assert "sent_on" in campos
    assert not campos & {"scheduled_for", "send_at", "agendado_para", "status"}
