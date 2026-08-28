"""Regressão: o Discovery estruturado não atravessa para o portal do cliente (FDD 039).

No molde de `test_satisfacao_nao_volta_ao_cliente.py`, e **mais forte aqui**. Lá o que não pode
sair é a leitura da casa sobre a relação; aqui é a leitura da casa sobre a **operação** do
cliente e sobre o dinheiro que ela estima que ele perde — dois registros que a própria casa
marca como não confirmados enquanto o levantamento não termina.

Uma evidência com `rotulo=hipotese` atravessando a fronteira seria a casa afirmando ao cliente,
com a autoridade de um painel, exatamente aquilo que ela mesma rotulou como ainda não sabido. O
custo do estado atual agrava: ele é uma conta com parcelas não apuradas, e um total parcial
apresentado como número fechado vira, do outro lado, "vocês disseram que eu perco tanto por mês".
A hora de apresentar esses números é a reunião, com quem os levantou junto — nunca um snapshot
que se atualiza sozinho.

Duas camadas, o desenho da satisfação:

- **comportamental**, sobre o snapshot montado num cenário em que os três registros existem e são
  os mais chamativos possíveis — senão a asserção passaria por ausência de dado, e não por
  ausência de vazamento;
- **estrutural**, sobre a fonte, porque pega a intenção *antes* de ela virar vazamento: um bloco
  de processos acrescentado por alguém que quer "mostrar ao cliente o mapa que fizemos" fica
  vermelho na hora.
"""

import inspect
import json
from decimal import Decimal

import pytest

from apps.core import portal
from apps.core.models import Evidencia, Process, ProcessStep
from apps.core.tests.factories import ProjectFactory

pytestmark = pytest.mark.django_db

#: O que **nunca** pode aparecer no que vai ao cliente. A lista é dos termos **distintivos**
#: desta fatia: `processo` e `etapa` no singular ficam de fora de propósito — são palavras
#: correntes em português e a semente da jornada já as usa ("processos priorizados"), de modo que
#: incluí-las reprovaria texto sem relação nenhuma com o Discovery, e guarda que grita à toa é
#: guarda que alguém desliga. As chaves de topo e o conteúdo dos registros são conferidos à parte,
#: nos dois testes abaixo, e é lá que "processo" é cobrado com precisão.
PROIBIDOS = (
    "evidencia",
    "evidência",
    "custo_do_estado_atual",
    "nao_apurado",
    "sustentacao",
    "hipotese",
    "hipótese",
)

#: Na **fonte** a lista pode ser mais dura, porque ali não há prosa de semente: nada em
#: `portal.py` tem motivo para escrever "processo", "etapas" ou "rotulo" — se alguém escreveu, foi
#: para levar o mapa ao cliente.
PROIBIDOS_NA_FONTE = (*PROIBIDOS, "processo", "etapas", "rotulo")


@pytest.fixture
def projeto_com_discovery():  # type: ignore[no-untyped-def]
    """Cenário em que os três registros existem, e o mais constrangedor possível se vazasse."""
    project = ProjectFactory()
    processo = Process.objects.create(
        account=project.client,
        source_project=project,
        name="Faturamento manual",
        volume_mes=400,
        tempo_horas=Decimal("1.50"),
        pessoas=2,
        custo_hora=Decimal("70.00"),
        retrabalho_mes=Decimal("9000.00"),
    )
    etapa = ProcessStep.objects.create(
        process=processo,
        name="Conferência manual de pedidos",
        pessoas="Duas analistas do financeiro",
        erro="Pedido faturado com preço desatualizado",
        retrabalho="Nota cancelada e reemitida no dia seguinte",
    )
    Evidencia.objects.create(
        process=processo,
        step=etapa,
        forma=Evidencia.Forma.ENTREVISTA,
        rotulo=Evidencia.Rotulo.HIPOTESE,
        content="Suspeita nossa: o time do cliente não confere o preço antes de faturar.",
    )
    return project


def test_o_snapshot_nao_carrega_processo_etapa_nem_evidencia(projeto_com_discovery) -> None:  # type: ignore[no-untyped-def]
    snapshot = portal.build_snapshot(projeto_com_discovery)

    assert "processos" not in snapshot
    assert "evidencias" not in snapshot
    serializado = json.dumps(snapshot, default=str).lower()
    for palavra in PROIBIDOS:
        assert palavra not in serializado, f"'{palavra}' vazou para o snapshot do cliente"


def test_nem_o_conteudo_dos_registros_aparece_em_profundidade_nenhuma(projeto_com_discovery) -> None:  # type: ignore[no-untyped-def]
    """O teste acima pega a chave; este pega o texto, que é o que constrange de verdade.

    Um vazamento não precisa se chamar "processos" para ser vazamento: bastaria alguém juntar o
    mapa a um bloco existente — "contexto da entrega", "o que estamos observando" — e o cliente
    leria a suspeita da casa sobre o time dele.
    """
    serializado = json.dumps(portal.build_snapshot(projeto_com_discovery), default=str).lower()

    assert "faturamento manual" not in serializado
    assert "conferência manual de pedidos" not in serializado
    assert "suspeita nossa" not in serializado
    assert "duas analistas do financeiro" not in serializado
    # O custo estimado é o que menos pode sair sem quem o levantou por perto.
    assert "9000" not in serializado
    assert "84000" not in serializado  # 400 × 1,50 × 2 × 70 — o núcleo da fórmula


# --- Camada estrutural --------------------------------------------------------


def test_a_fonte_do_snapshot_nao_menciona_o_discovery_estruturado() -> None:
    """A guarda para o vazamento que **ainda não existe**.

    Conferir na fonte custa três linhas e pega a intenção antes do fato — o mesmo movimento da
    satisfação (FDD 037) e do anti-vazamento de custo e margem (FDD 036). O docstring do módulo é
    excluído de propósito: ele pode precisar **nomear** a ausência, que é justamente o que este
    teste protege.
    """
    corpo = inspect.getsource(portal).split('"""', 2)[2].lower()

    for palavra in PROIBIDOS_NA_FONTE:
        assert palavra not in corpo, f"'{palavra}' apareceu na fonte do snapshot do cliente"
