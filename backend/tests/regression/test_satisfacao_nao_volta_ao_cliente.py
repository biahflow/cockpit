"""Regressão: a satisfação não atravessa para o portal do cliente (FDD 037, ADR 0032).

No molde do Risk Register (FDD 034), e por uma razão que a fonte `percebida` torna literal:
devolver ao cliente a **nossa leitura sobre ele** não é uma feature com recorte ruim, é uma
feature que não pode existir. A declarada não está melhor: mandar de volta "você disse que estava
insatisfeito em 12/08" é transformar uma conversa em cobrança de posição.

Duas camadas, mesmo desenho de `test_cobranca_nao_leva_custo_nem_margem.py`:

- **comportamental**, sobre o snapshot montado num cenário em que o registro existe e é o mais
  chamativo possível;
- **estrutural**, sobre a fonte, porque ela pega a intenção *antes* de ela virar vazamento — um
  bloco de satisfação acrescentado por alguém que quer "dar mais contexto ao cliente" fica
  vermelho na hora, e não no dia em que o cliente lê a nossa impressão sobre ele.

A guarda da ADR 0027 (`apps/core/tests/test_portal.py`) já reprova **chave nova não declarada** no
snapshot; ela pergunta "quem avisa que essa chave mudou?". Este arquivo responde a outra pergunta,
e é por isso que ele existe ao lado dela: não queremos a chave. Declará-la em `_DERIVADA_DE`
satisfaria aquela guarda e produziria exatamente o vazamento.
"""

import inspect
import json
from datetime import timedelta

import pytest
from django.utils import timezone

from apps.core import portal
from apps.core.models import Satisfacao
from apps.core.tests.factories import ProjectFactory

pytestmark = pytest.mark.django_db

#: O que **nunca** pode aparecer no que vai ao cliente. Os dois primeiros são os nomes concretos
#: dos campos; os outros são as palavras que alguém escreveria ao levá-los "para o cliente
#: acompanhar a percepção dele".
PROIBIDOS = ("satisfacao", "satisfação", "insatisfeito", "percebida", "promotor")


@pytest.fixture
def projeto_com_satisfacao():  # type: ignore[no-untyped-def]
    """Um cenário em que o registro existe, é recente e é o mais chamativo possível — senão a
    asserção passaria por ausência de dado, não por ausência de vazamento."""
    project = ProjectFactory()
    Satisfacao.objects.create(
        client=project.client,
        project=project,
        nivel=Satisfacao.Nivel.INSATISFEITO,
        fonte=Satisfacao.Fonte.PERCEBIDA,
        happened_on=timezone.localdate() - timedelta(days=2),
        note="Achei o cliente frio na última call; parece insatisfeito com o ritmo.",
    )
    return project


def test_o_snapshot_nao_carrega_a_satisfacao_em_chave_nenhuma(projeto_com_satisfacao) -> None:  # type: ignore[no-untyped-def]
    snapshot = portal.build_snapshot(projeto_com_satisfacao)

    assert "satisfacao" not in snapshot
    assert "satisfacoes" not in snapshot
    serializado = json.dumps(snapshot, default=str).lower()
    for palavra in PROIBIDOS:
        assert palavra not in serializado, f"'{palavra}' vazou para o snapshot do cliente"
    assert "frio na última call" not in serializado


def test_a_nota_nao_vaza_nem_pelo_health_do_snapshot(projeto_com_satisfacao) -> None:  # type: ignore[no-untyped-def]
    """O caminho lateral: o snapshot leva saúde, e o sexto sinal tem `label` e `detail`.

    Com a fonte declarada o sinal existe e pesa — e mesmo assim o rótulo "Cliente insatisfeito"
    não pode atravessar. O bloco de saúde do portal já leva só o nível, e este teste é o que
    impede que "detalhar um pouco mais para o cliente" desfaça isso.
    """
    Satisfacao.objects.create(
        client=projeto_com_satisfacao.client,
        nivel=Satisfacao.Nivel.INSATISFEITO,
        fonte=Satisfacao.Fonte.DECLARADA,
        happened_on=timezone.localdate(),
        note="Disse que o marco 2 atrasou duas vezes.",
    )

    snapshot = portal.build_snapshot(projeto_com_satisfacao)

    serializado = json.dumps(snapshot, default=str).lower()
    assert "insatisfeito" not in serializado
    assert "marco 2 atrasou" not in serializado


# --- Camada estrutural --------------------------------------------------------


def test_a_fonte_do_snapshot_nao_menciona_o_registro_de_satisfacao() -> None:
    """A guarda para o vazamento que **ainda não existe**.

    Conferir na fonte custa três linhas e pega a intenção antes do fato — o mesmo movimento de
    `test_portal_e_ai_nao_alcancam_o_corpus` (FDD 029) e do anti-vazamento de custo e margem
    (FDD 036). O docstring do módulo é excluído de propósito: ele pode precisar **nomear** a
    ausência, que é justamente o que este teste protege.
    """
    fonte = inspect.getsource(portal)
    corpo = fonte.split('"""', 2)[2].lower()

    assert "satisfacao" not in corpo
    assert "satisfacoes" not in corpo
