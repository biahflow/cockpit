"""Regressão: a cerca comercial do rascunho de tom (FDD 036, RFC 0004 "Segurança").

A RFC é literal: *"O valor da fatura é do cliente por direito; custo e margem **nunca** saem."*

Duas camadas, e a segunda é a que importa a longo prazo — mesmo desenho do anti-vazamento do corpus
interno (`test_corpus_interno_nao_vai_ao_cliente.py`):

- **comportamental**, sobre o texto que o contexto produz num cenário em que os números proibidos
  existem e valem alguma coisa;
- **estrutural**, sobre a fonte, porque ela pega a intenção errada *antes* de ela virar vazamento —
  um `f"ROI: {_roi(project)}"` acrescentado por alguém que quer "dar mais contexto ao modelo" fica
  vermelho na hora, e não no dia em que um cliente lê o número.
"""

import inspect
from datetime import date, timedelta
from decimal import Decimal

import pytest

from apps.core import ai, cobranca
from apps.core.models import Invoice
from apps.core.tests.factories import InvoiceFactory, ProjectFactory

HOJE = date(2026, 9, 2)

#: O que **nunca** pode aparecer no contexto de cobrança. `actual_value` e `roi_snapshot` são os
#: nomes concretos dos dois números que a casa calcula sobre si mesma; os outros são as palavras que
#: alguém escreveria ao acrescentá-los "só para o modelo entender melhor".
PROIBIDOS = ("actual_value", "roi_snapshot", "roi", "margem", "custo", "lucro")


@pytest.fixture
def fatura_de_projeto_lucrativo() -> Invoice:
    """Um cenário em que os números proibidos existem e não são zero — senão a asserção passaria
    por ausência de dado, não por ausência de vazamento."""
    project = ProjectFactory(actual_value=Decimal("250000.00"))
    return InvoiceFactory(
        client=project.client,
        project=project,
        status=Invoice.Status.OVERDUE,
        number="2026-0001",
        amount=Decimal("18000.00"),
        due_date=HOJE - timedelta(days=12),
    )


@pytest.mark.django_db
def test_o_contexto_nao_cita_custo_margem_nem_roi(fatura_de_projeto_lucrativo: Invoice) -> None:
    contexto = ai.build_cobranca_context(fatura_de_projeto_lucrativo, "firme", HOJE).lower()

    assert "250000" not in contexto and "250.000" not in contexto
    for palavra in PROIBIDOS:
        assert palavra not in contexto, f"'{palavra}' vazou para o contexto de cobrança"


@pytest.mark.django_db
def test_o_contexto_leva_o_nivel_de_health_e_nao_o_score(
    fatura_de_projeto_lucrativo: Invoice,
) -> None:
    """"atenção" ajusta o tom; "62/100, 2 entregas atrasadas" é a nossa medição da nossa própria
    falha, e ela não é assunto de um e-mail de cobrança."""
    contexto = ai.build_cobranca_context(fatura_de_projeto_lucrativo, "firme", HOJE)

    assert "Saúde da entrega: saudável" in contexto
    assert "/100" not in contexto


@pytest.mark.django_db
def test_o_contexto_leva_o_que_o_cliente_ja_sabe(fatura_de_projeto_lucrativo: Invoice) -> None:
    """O complemento do teste acima: cercar tudo não é cercar — o rascunho precisa do que faz o
    tom mudar (valor, prazo, tempo de casa, histórico, entrega atrasada)."""
    contexto = ai.build_cobranca_context(fatura_de_projeto_lucrativo, "firme", HOJE)

    assert "18000" in contexto
    assert "Dias de atraso: 12" in contexto
    assert "Tempo de casa:" in contexto
    assert "Histórico:" in contexto


@pytest.mark.django_db
def test_o_contexto_nao_alcanca_fatura_de_outro_cliente(
    fatura_de_projeto_lucrativo: Invoice,
) -> None:
    de_outro = InvoiceFactory(
        status=Invoice.Status.OVERDUE, number="2026-0002", amount=Decimal("77777.00"),
        due_date=HOJE - timedelta(days=40),
    )
    contexto = ai.build_cobranca_context(fatura_de_projeto_lucrativo, "firme", HOJE)

    assert "77777" not in contexto
    assert de_outro.client.name not in contexto


# --- Camada estrutural --------------------------------------------------------


def test_a_fonte_do_contexto_nao_menciona_custo_margem_nem_roi() -> None:
    """A guarda para o vazamento que **ainda não existe**.

    Conferir isto na fonte custa três linhas e pega a intenção antes do fato — que é o mesmo
    movimento de `test_portal_e_ai_nao_alcancam_o_corpus` (FDD 029). O docstring da função é
    excluído de propósito: ele **explica** as ausências, e precisa poder nomeá-las.
    """
    fonte = inspect.getsource(ai.build_cobranca_context)
    corpo = fonte.split('"""')[2].lower()

    for palavra in PROIBIDOS:
        assert palavra not in corpo, (
            f"'{palavra}' entrou no contexto de cobrança — custo e margem nunca saem (RFC 0004)"
        )


def test_a_regua_nao_alcanca_o_corpus_interno() -> None:
    """`cobranca.py` monta e manda texto ao cliente; o material da metodologia não tem o que fazer
    ali. O `grounding` é injetado num ponto único (`_ai_run`), e este teste guarda o outro lado."""
    assert "knowledge" not in inspect.getsource(cobranca)
