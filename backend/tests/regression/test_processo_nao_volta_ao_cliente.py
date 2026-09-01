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

## Emenda (FDD 051, 01/09/2026) — quatro chaves entraram, e **nada atravessa sem a marca**

A §3 do `docs/ontology/language-map.md` lista `Process · ProcessStep (o AS-IS validado)` e
`Finding · PainPoint (revisados)` entre o que o One mostra; o schema é que estava atrás do
documento, e a FDD 051 o moveu — dando ao schema os dois estados que a §3 pressupunha e não
tinha. `processes`, `findings`, `pain_points` e `improvement_opportunities` entraram no snapshot,
e **nenhum item de nenhuma das quatro atravessa sem `published_at`/`published_by`**, o mapa do
AS-IS inclusive:

- **"validado" era qualificador sem lastro**, exatamente como "revisada e publicável" era para a
  `Evidence`: não havia campo nenhum dizendo que aquele mapa tinha sido conferido com o cliente.
  A ADR 0060 deu marca aos **cinco** modelos, e o AS-IS chega ao One porque alguém o publicou;
- **nada deste cenário atravessa**, portanto, e nenhuma asserção deste arquivo precisou afrouxar.
  O processo não está publicado, e por isso o nome dele, o do passo, as duas analistas do
  financeiro e a suspeita sobre o time do cliente continuam do lado de cá — palavra por palavra,
  como sempre estiveram;
- **os nove insumos do custo continuam fora**, inteiros, e é a asserção mais importante deste
  arquivo: um total parcial apresentado como número fechado vira "vocês disseram que eu perco
  tanto por mês", e nada na FDD 051 mexeu nisso;
- **a camada estrutural não mudou uma linha.** `PROIBIDOS_NA_FONTE` continua reprovando as
  palavras do levantamento na prosa de `portal.py`, e foi contornada escrevendo os comentários em
  volta dela — nunca afrouxando a lista. É o que mantém o nome deste arquivo verdadeiro.

O que mudou de verdade foi a **força** da guarda: antes ela passava por ausência de código, e
agora passa por invariante cobrada. As quatro listas vazias abaixo dizem "o bloco existe, o
registro existe, e ele não atravessou porque ninguém o publicou".

Ver a FDD 051, a ADR 0060 e a regressão irmã
`test_a_cadeia_de_publicacao_nao_vaza.py`, que cobra a marca do outro lado.
"""

import inspect
import json
from decimal import Decimal

import pytest

from apps.core import portal
from apps.core.models import Finding, Process, ProcessStep
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
        account=project.engagement.account,
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
    Finding.objects.create(
        account=project.engagement.account,
        process=processo,
        step=etapa,
        epistemic_status=Finding.EpistemicStatus.HYPOTHESIS,
        statement="Suspeita nossa: o time do cliente não confere o preço antes de faturar.",
    )
    return project


def test_o_snapshot_nao_carrega_processo_etapa_nem_evidencia(projeto_com_discovery) -> None:  # type: ignore[no-untyped-def]
    """As chaves legadas nunca voltam, e as novas saem **vazias** sem nada publicado (FDD 051).

    Sair vazio é a asserção que substitui a chave ausente, e é mais forte que ela: a chave ausente
    dizia "ninguém escreveu o bloco ainda", e a lista vazia diz "o bloco existe, o registro existe,
    e ele não atravessou porque ninguém o publicou". Um `published_at__isnull=False` removido de
    `portal.py` fica vermelho aqui.
    """
    snapshot = portal.build_snapshot(projeto_com_discovery)

    assert "processos" not in snapshot
    assert "evidencias" not in snapshot
    assert "evidence" not in snapshot
    assert snapshot["processes"] == []
    assert snapshot["findings"] == []
    assert snapshot["pain_points"] == []
    assert snapshot["improvement_opportunities"] == []
    serializado = json.dumps(snapshot, default=str).lower()
    for palavra in PROIBIDOS:
        assert palavra not in serializado, f"'{palavra}' vazou para o snapshot do cliente"


def test_nem_o_conteudo_dos_registros_aparece_em_profundidade_nenhuma(projeto_com_discovery) -> None:  # type: ignore[no-untyped-def]
    """O teste acima pega a chave; este pega o texto, que é o que constrange de verdade.

    Um vazamento não precisa se chamar "processos" para ser vazamento: bastaria alguém juntar a
    afirmação não publicada a um bloco existente — "contexto da entrega", "o que estamos
    observando" — e o cliente leria a suspeita da casa sobre o time dele.

    **Nenhuma asserção saiu daqui na FDD 051**, e é o que a marca no AS-IS comprou (ADR 0060):
    nada deste cenário está publicado, então nada dele atravessa. O nome do processo e o do passo
    voltaram junto com as duas analistas do financeiro — o `pessoas` de um passo é gente com
    nome dentro da empresa do cliente, e ela não aparece num painel porque a casa mapeou a
    operação. O que ainda não se decidiu mostrar, e o dinheiro que a casa estima que o cliente
    perde, continuam aqui: é o que este teste sempre existiu para guardar.
    """
    serializado = json.dumps(portal.build_snapshot(projeto_com_discovery), default=str).lower()

    assert "faturamento manual" not in serializado
    assert "conferência manual de pedidos" not in serializado
    assert "duas analistas do financeiro" not in serializado
    assert "suspeita nossa" not in serializado
    # O custo estimado é o que menos pode sair sem quem o levantou por perto.
    assert "9000" not in serializado
    assert "84000" not in serializado  # 400 × 1,50 × 2 × 70 — o núcleo da fórmula
    # Os nove insumos não atravessam por chave nenhuma, e não só por valor: um `volume_mes` num
    # item de `processes[]` seria a fórmula chegando ao cliente pela porta que a FDD 051 abriu.
    for insumo in ("volume_mes", "custo_hora", "tempo_horas", "retrabalho_mes", "erros_mes",
                   "perdas_mes", "espera_mes", "risco_mes"):
        assert insumo not in serializado, f"'{insumo}' vazou no bloco do AS-IS"


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
