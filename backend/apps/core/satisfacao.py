"""A satisfação vigente: qual registro ainda vale hoje (FDD 037, camada 5 da RFC 0004).

Módulo de funções puras mais duas pré-cargas em lote, no espírito de `project_scope_q` e de
`cobranca._q_em_atraso`: **uma** expressão da regra, e não uma cópia por consumidor. Três motores
perguntam a mesma coisa — o Health Score (`health.py`), a régua de cobrança (`cobranca.py`) e o
agente de Entrega (`agents.py`) —, e três cópias da janela divergiriam no primeiro ajuste sem
nada ficar vermelho: a tela passaria a considerar vigente o que o relógio já esqueceu.

**O sinal envelhece, e é isso que este módulo existe para dizer.** Um "insatisfeito" de oito
meses não é o estado de hoje. Tratá-lo como estado de hoje produziria exatamente o recebível que
estraga invisível (RFC 0004, "Segurança"): um cliente que reclamou uma vez, em março, nunca mais
cobrado com firmeza.

O que este módulo deliberadamente **não** faz é decidir o que a satisfação significa. Que só a
fonte `declared` move número é regra dos consumidores (ADR 0032), e cada um a escreve onde ela
importa — aqui ela é só um filtro opcional.
"""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Iterable
from datetime import date, timedelta
from typing import TYPE_CHECKING

from django.db.models import Q

if TYPE_CHECKING:
    from .models import SatisfactionRecord

#: Por quanto tempo um registro continua sendo "o estado de hoje". Noventa dias, e o número é o
#: mesmo tipo de corte explícito que `cobranca.RELACAO_LONGA_DIAS`: não há nada de mágico nele, há
#: o requisito de existir um limite testável em vez de "registro recente" virar julgamento de quem
#: estiver de plantão. A forma — janela, e não offset — é a que a FDD 036 já adotou na régua, e
#: pela mesma razão: passada a janela, o registro simplesmente não vale mais.
SATISFACAO_VALIDA_DIAS = 90


def _q_na_janela(hoje: date) -> Q:
    """O que ainda conta como sinal de hoje. Fechada nos dois lados.

    Expressão única, e por isso função e não literal repetido: a pré-carga em lote a usa em SQL e
    `vigente` a usa em Python sobre a mesma lista. Duas cópias fariam a janela do banco e a da
    memória discordarem em um dia, que é a classe de defeito que ninguém encontra olhando.

    O limite superior não é enfeite: um registro com data futura (dedo errado no formulário) não
    é o estado de hoje, e sem ele passaria a valer por noventa dias a partir do erro.
    """
    return Q(happened_on__gte=hoje - timedelta(days=SATISFACAO_VALIDA_DIAS), happened_on__lte=hoje)


def vigente(
    registros: Iterable[SatisfactionRecord], hoje: date, *, fonte: str | None = None
) -> SatisfactionRecord | None:
    """O registro mais recente que ainda vale hoje, ou nada.

    Função **pura** sobre uma lista já recortada por cliente (ou por projeto), no molde de
    `health._level` e de `cobranca.regua_para`: explicável em uma frase e testável sem banco.

    `fonte` restringe a escolha, e o parâmetro é o que impede o defeito sutil desta fatia: quem
    precisa da declarada não pode pegar a vigente de qualquer fonte e conferir o campo depois —
    uma percebida registrada ontem esconderia a declarada de anteontem, e o Health Score passaria
    a depender de alguém do time ter anotado uma impressão.

    Arquivado não conta. A pré-carga já filtra em SQL; a repetição aqui é para quem passar uma
    lista crua, porque um registro que alguém arquivou não pode continuar movendo número.
    """
    inicio = hoje - timedelta(days=SATISFACAO_VALIDA_DIAS)
    candidatos = [
        registro
        for registro in registros
        if registro.archived_at is None
        and inicio <= registro.happened_on <= hoje
        and (fonte is None or registro.fonte == fonte)
    ]
    if not candidatos:
        return None
    # Empate em `happened_on` desempata pelo mais novo, que é o que a ordenação do modelo
    # (`-happened_on, -created_at`) faria: dois registros do mesmo dia são uma correção, e a
    # correção é a segunda.
    return max(candidatos, key=lambda registro: (registro.happened_on, registro.pk or 0))


def registros_vigentes_por_cliente(
    client_ids: Iterable[int], hoje: date
) -> dict[int, list[SatisfactionRecord]]:
    """Os registros ainda válidos de cada cliente, em **uma** query.

    Devolve a lista e não o escolhido de propósito: o painel de cobrança mostra a vigente de
    qualquer fonte e a régua decide pela vigente **declarada**, e são duas escolhas diferentes
    sobre o mesmo dado. Pré-carregar uma delas obrigaria a segunda a se contentar com o que sobrou
    — e a tela passaria a discordar do relógio exatamente no caso que a fatia existe para tratar
    (uma percebida anotada depois de uma declarada).

    É a ADR 0014 outra vez: sem lote, `/health/`, `/clients/overview/` e `/cobranca/painel/`
    ganhariam um N+1 por cliente.
    """
    from .models import SatisfactionRecord

    ids = list(client_ids)
    if not ids:
        return {}
    por_cliente: dict[int, list[SatisfactionRecord]] = defaultdict(list)
    for registro in (
        SatisfactionRecord.objects.filter(account_id__in=ids, archived_at__isnull=True)
        .filter(_q_na_janela(hoje))
        .select_related("account")
    ):
        por_cliente[registro.account_id].append(registro)
    return dict(por_cliente)


def vigentes_por_cliente(
    client_ids: Iterable[int], hoje: date, *, fonte: str | None = None
) -> dict[int, SatisfactionRecord]:
    """A vigente de cada cliente, em uma query. Cliente sem registro válido não entra no dicionário.

    Fachada de `registros_vigentes_por_cliente` + `vigente` — a escolha continua sendo a mesma
    função, para o lote não ser uma segunda definição de "vigente".
    """
    escolhidas: dict[int, SatisfactionRecord] = {}
    for client_id, registros in registros_vigentes_por_cliente(client_ids, hoje).items():
        escolhida = vigente(registros, hoje, fonte=fonte)
        if escolhida is not None:
            escolhidas[client_id] = escolhida
    return escolhidas
