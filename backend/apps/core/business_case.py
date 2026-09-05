"""O custo do estado atual que o Business Case congela — e a proveniência do congelamento.

O business case é a justificativa do investimento (FDD 053, ADR 0069), e o número que ele coloca
do outro lado da conta é quanto a operação custa **hoje**. Esse número já existe: sai de
`process.custo_do_estado_atual`, a fórmula literal do material. O que este módulo resolve é *quais*
processos entram nele e *o que* se registra sobre os que não entraram.

**A regra é a ADR 0034: só o fato sustenta número.** Entra na soma apenas o processo cuja conta
volta `sustentacao == "sustentado"` — isto é, com ao menos um `Finding` vivo classificado como
`fact` por baixo. Um processo cujo custo é hipótese continua sendo levantamento legítimo, e por
isso aparece na proveniência; o que ele não faz é virar parcela de um número que alguém vai citar
numa reunião de investimento.

**Nenhum sustentado devolve `None`, nunca `Decimal("0")`.** É a decisão inteira de `process.py`
repetida um nível acima: "não apuramos o custo" e "o custo é zero" são conclusões opostas, e somar
zero afirmaria a segunda. Quem consome distingue os dois casos pela proveniência, que diz processo
por processo o que faltou.

Função pura, no molde de `priority.calcular_score` e de `prove.o_que_falta_para_iniciar`: fora da
view, sem request, testável sem HTTP. O dinheiro sai como **texto** pela mesma razão de sempre
(ADR 0068) — o destino é um `JSONField`, e o encoder do DRF transformaria `Decimal` em `float`, que
é onde a forma digitada se perde.
"""

from __future__ import annotations

from decimal import Decimal
from typing import TYPE_CHECKING, Any

from .dinheiro import dinheiro
from .process import SUSTENTADO, custo_do_estado_atual

if TYPE_CHECKING:
    from .models import ImprovementOpportunity, Process


def processos_da_oportunidade(oportunidade: ImprovementOpportunity) -> list[Process]:
    """Os processos **vivos e distintos** alcançados pelas dores vivas da oportunidade.

    Distintos porque duas dores no mesmo processo são o caso comum — é para isso que a
    `ImprovementOpportunity` agrupa —, e somar o custo daquele processo duas vezes dobraria o
    número sem nada ficar vermelho. `PainPoint.process` é opcional (nem toda dor cabe num processo
    mapeado), e a dor sem processo simplesmente não contribui: ela não tem conta a somar.

    Ordena pelo id para a proveniência gravada ser estável entre duas leituras — um dicionário de
    congelamento que muda de ordem sozinho é um diff que ninguém consegue revisar.
    """
    processos: dict[int, Process] = {}
    dores = oportunidade.pain_points.filter(archived_at__isnull=True).select_related("process")
    for dor in dores:
        processo = dor.process
        if processo is None or processo.archived_at is not None:
            continue
        processos.setdefault(processo.pk, processo)
    return [processos[pk] for pk in sorted(processos)]


def custo_congelavel(
    oportunidade: ImprovementOpportunity,
) -> tuple[Decimal | None, dict[str, Any]]:
    """O custo do estado atual desta oportunidade, e o registro de como ele foi apurado.

    Devolve `(total, proveniencia)`. `total` é a soma dos processos **sustentados**, ou `None`
    quando nenhum sustenta — nunca zero.

    A proveniência tem duas chaves. `processos` traz uma linha por processo alcançado, com o `id`,
    a `sustentacao`, o `total` daquele processo (texto, duas casas) e o `nao_apurado` que ele
    devolveu; `somados` lista os ids que entraram na conta. Ela existe para a lacuna ser **dita**
    em vez de silenciada: sem ela, um `current_state_cost` nulo seria indistinguível de um
    levantamento que ninguém fez, e um total baixo não explicaria que metade dos processos ficou
    de fora por ser hipótese.

    O total soma os subtotais **já arredondados** de cada processo, e não os valores em precisão
    cheia, pelo motivo escrito em `process.py`: só assim a conta que alguém confere linha a linha
    fecha com o número exibido.
    """
    linhas: list[dict[str, Any]] = []
    somados: list[int] = []
    total = Decimal("0")
    for processo in processos_da_oportunidade(oportunidade):
        conta = custo_do_estado_atual(processo)
        linhas.append(
            {
                "id": processo.pk,
                "sustentacao": conta["sustentacao"],
                "total": dinheiro(conta["total"]),
                "nao_apurado": list(conta["nao_apurado"]),
            }
        )
        # **Sustentado não basta: é preciso ter sido apurado.** As duas condições são
        # independentes — `sustentacao` pergunta se há `Finding(fact)` vivo por baixo,
        # `nao_apurado` pergunta se há insumo preenchido —, e o processo recém-mapeado numa reunião
        # de Discovery satisfaz a primeira sem a segunda: alguém confirmou o que acontece ali antes
        # de alguém medir quanto custa. Somar o zero daquele processo grava um custo de R$ 0,00 e a
        # tela o exibe como número (DAP r2, decisão F1, manda `—`), que é a casa afirmando ao
        # aprovador o oposto do que ela sabe. `parcelas` não-vazio é a pergunta certa, e é a mesma
        # que `process.py` manda fazer: *"quem consome distingue os dois casos por `nao_apurado`, e
        # não pelo total"*.
        if conta["sustentacao"] == SUSTENTADO and conta["parcelas"]:
            somados.append(processo.pk)
            total += conta["total"]
    proveniencia: dict[str, Any] = {"processos": linhas, "somados": somados}
    return (total if somados else None), proveniencia
