"""Regressão: só a **declarada** move número (FDD 037, ADR 0032).

É a decisão central da fatia e a única que um refactor desatento apaga em silêncio. Somar as duas
fontes num filtro só — `Satisfacao.objects.filter(account=...)` sem `fonte=` — deixa **todos** os
testes de comportamento passando: o Health Score continua descontando, a escada continua trocando,
e nada fica vermelho. O que muda é o significado: o sinal do cliente vira a opinião do time sobre
si mesmo com aparência de medição, e um número errado é consultado com a mesma confiança de um
número certo.

Os dois motores estão aqui juntos de propósito. A regra é uma só para os dois (é o que a ADR 0032
decidiu), e testá-la em dois arquivos separados deixaria o segundo motor sem guarda no dia em que
alguém "unificar" o filtro.

O oráculo é a **igualdade com a ausência de registro**, e não um número escrito à mão: assim o
teste continua valendo se os pesos dos outros cinco sinais mudarem.
"""

from datetime import date, timedelta
from decimal import Decimal

import pytest
from django.utils import timezone

from apps.core import cobranca, health
from apps.core.models import Account, Invoice, Satisfacao
from apps.core.tests.factories import AccountFactory, InvoiceFactory, ProjectFactory

HOJE = date(2026, 9, 2)  # uma quarta-feira, como no resto da suíte de cobrança

pytestmark = pytest.mark.django_db


def _registrar(account, fonte: str, **kwargs):  # type: ignore[no-untyped-def]
    campos = {
        "account": account,
        "nivel": Satisfacao.Nivel.INSATISFEITO,
        "fonte": fonte,
        # O dia real, e não `HOJE`: o Health Score não recebe "hoje" por parâmetro (é função pura
        # sobre o agora), e um registro com data futura não é o estado de hoje — deixaria os
        # testes de saúde passando por ausência de sinal em vez de por ausência de vazamento.
        "happened_on": timezone.localdate(),
        "note": "O cliente/eu achei que a entrega do marco 2 decepcionou.",
    }
    campos.update(kwargs)
    return Satisfacao.objects.create(**campos)


# --- Motor 1: o Health Score --------------------------------------------------


def test_a_percebida_nao_muda_o_health_score() -> None:
    """Mesmo nível, mesma data, mesma nota: a única diferença é a fonte."""
    sem_registro = ProjectFactory()
    com_percebida = ProjectFactory()
    _registrar(com_percebida.client, Satisfacao.Fonte.PERCEBIDA)

    controle = health.assess_project_health(sem_registro)
    medido = health.assess_project_health(com_percebida)

    assert medido["score"] == controle["score"]
    assert medido["signals"] == controle["signals"] == []


def test_a_declarada_muda_o_health_score() -> None:
    """O complemento do teste acima: cercar tudo não é cercar — se a declarada também não movesse,
    o teste de cima passaria por o sinal não existir."""
    project = ProjectFactory()
    _registrar(project.client, Satisfacao.Fonte.DECLARADA)

    resultado = health.assess_project_health(project)

    assert resultado["score"] < 100
    assert [sinal["label"] for sinal in resultado["signals"]] == ["Cliente insatisfeito"]


def test_a_percebida_nao_muda_o_health_score_em_lote() -> None:
    """O lote é o caminho de `/health/` e de `/clients/overview/`, e tem a sua própria pré-carga —
    um filtro por fonte esquecido **ali** não apareceria no caminho individual."""
    sem_registro = ProjectFactory()
    com_percebida = ProjectFactory()
    _registrar(com_percebida.client, Satisfacao.Fonte.PERCEBIDA)

    por_projeto = {
        linha["project_id"]: linha
        for linha in health.assess_projects_health([sem_registro, com_percebida])
    }

    assert por_projeto[com_percebida.pk]["score"] == por_projeto[sem_registro.pk]["score"]
    assert por_projeto[com_percebida.pk]["signals"] == []


def test_o_lote_e_o_individual_concordam_sobre_a_fonte() -> None:
    """A pré-carga troca a fonte do dado, nunca a regra (FDD 022)."""
    projetos = [ProjectFactory() for _ in range(3)]
    _registrar(projetos[0].client, Satisfacao.Fonte.DECLARADA)
    _registrar(projetos[1].client, Satisfacao.Fonte.PERCEBIDA)

    assert health.assess_projects_health(projetos) == [
        health.assess_project_health(project) for project in projetos
    ]


# --- Motor 2: a escada da régua de cobrança -----------------------------------


def test_a_percebida_nao_troca_a_escada() -> None:
    account = AccountFactory()
    _registrar(account, Satisfacao.Fonte.PERCEBIDA)

    assert cobranca.regua_para(account, HOJE) is cobranca.PADRAO


def test_a_percebida_nao_alcanca_nem_o_cliente_de_relacao_longa() -> None:
    """A régua da relação longa é a que a percebida teria mais chance de derrubar por engano: ela
    é escolhida por outra condição, e a tensão é avaliada **antes** dela."""
    antigo = AccountFactory()
    Account.objects.filter(pk=antigo.pk).update(created_at=timezone.now() - timedelta(days=800))
    antigo.refresh_from_db()
    _registrar(antigo, Satisfacao.Fonte.PERCEBIDA)

    assert cobranca.regua_para(antigo, HOJE) is cobranca.RELACAO_LONGA


def test_a_declarada_troca_a_escada() -> None:
    account = AccountFactory()
    _registrar(account, Satisfacao.Fonte.DECLARADA)

    assert cobranca.regua_para(account, HOJE) is cobranca.RELACAO_TENSA


def test_a_percebida_nao_muda_o_degrau_que_sai_hoje() -> None:
    """O teste de comportamento por trás dos três acima: em D+12 a régua padrão manda o `firme`, e
    é justamente esse degrau que a tensão tira."""
    com_percebida = AccountFactory()
    _registrar(com_percebida, Satisfacao.Fonte.PERCEBIDA)
    invoice = InvoiceFactory(
        account=com_percebida, status=Invoice.Status.OVERDUE, number="2026-0001",
        amount=Decimal("1000.00"), due_date=HOJE - timedelta(days=12),
    )

    assert cobranca.degrau_devido(invoice, HOJE).key == "firme"


def test_a_percebida_nao_cala_a_regua_nem_a_declarada() -> None:
    """Critério de aceite 3: nenhuma das duas fontes produz avaliação sem degrau. A trava troca a
    escada; ela nunca vira silêncio (RFC 0004, "Segurança")."""
    for fonte in (Satisfacao.Fonte.PERCEBIDA, Satisfacao.Fonte.DECLARADA):
        account = AccountFactory()
        _registrar(account, fonte)
        invoice = InvoiceFactory(
            account=account, status=Invoice.Status.OVERDUE, number=f"2026-1{fonte[:3]}",
            amount=Decimal("1000.00"), due_date=HOJE - timedelta(days=12),
        )

        avaliacao = cobranca.avaliar(invoice, HOJE)

        assert avaliacao.degrau is not None, fonte
        assert avaliacao.motivo == ""
