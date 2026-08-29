"""Regressão: o custo do estado atual só vira número na proposta quando há **fato** atrás (FDD 039).

`docs/metodologia-fde.md:117` é explícito: todo achado é rotulado e **nunca se apresenta hipótese
como fato**. O custo do estado atual é a conta mais persuasiva que sai de um Discovery — e é
exatamente por isso que ele é o pior lugar para uma suposição: escrito numa proposta que o cliente
lê, o número volta na reunião seguinte como compromisso da casa, e ninguém consegue mais dizer que
era estimativa.

A guarda tem dois lados, e o segundo é o que costuma ser esquecido:

1. **Sem evidência `fato`, o número não sai.** É o que `processos.custo_do_estado_atual` responde
   em `sustentacao`, e o que `ai._processo_lines` obedece.
2. **A lacuna é dita, não silenciada.** Omitir o processo não sustentado deixaria o modelo diante
   de um buraco, e diante de um buraco o modelo preenche — foi o defeito que a rodada 5 de
   homologação achou na base de conhecimento (FDD 029). Uma proposta com número inventado é pior
   que uma proposta sem número, porque parece apurada.

O mesmo vale em escala menor para o total **parcial**: apresentar como fechado uma soma à qual
faltam parcelas é a mesma afirmação a mais, e o que ficou de fora sai junto do número.
"""

from decimal import Decimal

import pytest

from apps.core import ai
from apps.core.models import Finding
from apps.core.tests.factories import (
    AccountFactory,
    CommercialOpportunityFactory,
    FindingFactory,
    ProcessFactory,
    ProcessStepFactory,
)

pytestmark = pytest.mark.django_db

#: 0,5 h × 400 ocorrências × 2 pessoas × R$ 50,00 = R$ 20.000,00 por mês.
NUCLEO = {
    "volume_mes": 400,
    "tempo_horas": Decimal("0.50"),
    "pessoas": 2,
    "custo_hora": Decimal("50.00"),
}
NUMERO = "R$ 20.000,00"


def _oportunidade_com_processo(**campos: object):  # type: ignore[no-untyped-def]
    account = AccountFactory()
    processo = ProcessFactory(account=account, name="Faturamento mensal", **NUCLEO, **campos)
    ProcessStepFactory(process=processo, name="Conferir notas", position=1)
    ProcessStepFactory(process=processo, name="Emitir boletos", position=2)
    return CommercialOpportunityFactory(account=account), processo


def test_sem_fato_o_numero_nao_entra_e_a_lacuna_e_declarada() -> None:
    opportunity, _ = _oportunidade_com_processo()

    contexto = ai.build_opportunity_context(opportunity)

    assert NUMERO not in contexto
    assert "20.000" not in contexto  # nem em outro arredondamento
    # A lacuna dita, e dita como instrução: o silêncio não manda o modelo não inventar.
    assert "NÃO sustentado por evidência" in contexto
    assert "NÃO afirme número" in contexto


def test_o_mapa_qualitativo_entra_de_qualquer_jeito() -> None:
    """Descrever o que foi levantado não é afirmar quantidade — some com o número, não com o mapa.

    Sem esta asserção, "não afirmar número" poderia ser cumprido escondendo o processo inteiro, e
    a proposta perderia justamente o que o Discovery levantou.
    """
    opportunity, _ = _oportunidade_com_processo()

    contexto = ai.build_opportunity_context(opportunity)

    assert "Faturamento mensal" in contexto
    assert "Conferir notas" in contexto
    assert "Emitir boletos" in contexto


def test_com_fato_registrado_o_numero_aparece() -> None:
    """A metade complementar: sem ela, tudo passaria por o número nunca sair de lugar nenhum."""
    opportunity, processo = _oportunidade_com_processo()
    FindingFactory(
        process=processo, account=processo.account,
        epistemic_status=Finding.EpistemicStatus.FACT,
        statement="Relatório do ERP: 400 notas conferidas em abril.",
    )

    contexto = ai.build_opportunity_context(opportunity)

    assert NUMERO in contexto
    assert "sustentado por evidência" in contexto
    assert "NÃO afirme número" not in contexto


def test_arquivar_o_fato_faz_o_numero_sumir_de_novo() -> None:
    """Registro desfeito não sustenta número — e o contexto precisa voltar a dizer a lacuna.

    O caso perigoso é o do meio do caminho: a evidência sai, o número fica. Um custo que continua
    sendo afirmado depois de o que o sustentava ter sido removido é pior que o custo que nunca foi
    apurado, porque já foi visto como apurado uma vez.
    """
    opportunity, processo = _oportunidade_com_processo()
    fato = FindingFactory(
        process=processo, account=processo.account,
        epistemic_status=Finding.EpistemicStatus.FACT,
        statement="Relatório do ERP: 400 notas conferidas em abril.",
    )
    assert NUMERO in ai.build_opportunity_context(opportunity)

    fato.archive()

    contexto = ai.build_opportunity_context(opportunity)
    assert NUMERO not in contexto
    assert "NÃO sustentado por evidência" in contexto


def test_o_total_parcial_diz_o_que_ficou_de_fora() -> None:
    """Sustentado não quer dizer completo: os cinco aditivos da fórmula não foram apurados aqui."""
    opportunity, processo = _oportunidade_com_processo()
    FindingFactory(
        process=processo, account=processo.account,
        epistemic_status=Finding.EpistemicStatus.FACT,
        statement="Relatório do ERP: 400 notas conferidas em abril.",
    )

    contexto = ai.build_opportunity_context(opportunity)

    assert NUMERO in contexto
    assert "parcial" in contexto
    # Os aditivos que faltaram, nomeados: "não apurado" sem dizer o quê não muda o que o modelo faz.
    for rotulo in ("Retrabalho", "Erros", "Perdas", "Espera", "Risco"):
        assert rotulo in contexto


def test_cliente_sem_processo_mapeado_segue_com_o_contexto_de_antes() -> None:
    """Silêncio, como `_case_lines` sem case: quem não fez Discovery estruturado não perde nada."""
    opportunity = CommercialOpportunityFactory()

    contexto = ai.build_opportunity_context(opportunity)

    assert "Processos da operação do cliente" not in contexto


def test_processo_arquivado_nao_entra_na_proposta() -> None:
    """Arquivar é o jeito de tirar do mapa; um processo guardado que continua sendo vendido
    desfaria o arquivamento pela porta dos fundos."""
    opportunity, processo = _oportunidade_com_processo()
    FindingFactory(
        process=processo, account=processo.account,
        epistemic_status=Finding.EpistemicStatus.FACT,
        statement="Relatório do ERP.",
    )
    processo.archive()

    contexto = ai.build_opportunity_context(opportunity)

    assert "Faturamento mensal" not in contexto
    assert NUMERO not in contexto
