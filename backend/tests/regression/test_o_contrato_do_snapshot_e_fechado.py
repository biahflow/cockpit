"""Regressão: o conjunto de chaves de topo do snapshot do portal é **fixo** (ADR 0003, 0027, 0051).

A guarda da ADR 0027 (`apps/core/tests/test_portal.py`) pergunta uma coisa: toda chave nova tem
emissor, ou está declarada como derivada? É a pergunta certa e não é esta. Ela obriga a
**declarar** a chave nova, e uma chave declarada é uma chave que atravessou — o custo de declarar
é uma linha de dicionário, e ninguém revisando um diff de uma linha se pergunta se aquele dado
podia sair da casa.

Este teste fixa a lista. Acrescentar chave ao snapshot passa a exigir editar aqui, com o diff
mostrando o nome da chave nova ao lado das vinte e três existentes — que é o momento em que a
pergunta "isto pode ir ao cliente?" é feita por alguém. Sem ele, um campo interno que vaze não deixa nada
vermelho: o snapshot é montado à mão, `json.dumps` aceita qualquer dicionário, e o portal do outro
lado simplesmente ignora o que não conhece.

**Pendência conhecida, e ela é deliberada:** nem esta guarda nem a da ADR 0027 descem um nível.
As chaves aninhadas (`project.*`, `journey.phases[].*`) não são fixadas por nenhuma das duas — o
repo `one` diagnosticou o mesmo defeito do lado dele (ADR 0033 de lá). Descer um nível toca a
guarda de todo mundo e merece decisão própria; ver a FDD 047.
"""

import pytest

from apps.core import portal
from apps.core.tests.factories import ProjectFactory

#: O contrato de topo, byte a byte. Mexer aqui é mexer no que o cliente recebe.
CHAVES_DE_TOPO = {
    "project",
    "artifact_accepted_at",
    "observed_at",
    "projection_version",
    "completion",
    "health",
    "digital_employees",
    "kpis",
    "value_ledger",
    "processes",
    "findings",
    "pain_points",
    "improvement_opportunities",
    "journey",
    "ai_score",
    "milestones",
    "documents",
    "meetings",
    "pendencias",
    "decisions",
    "next_meeting",
    "roi",
    "resultados",
}


@pytest.mark.django_db
def test_o_snapshot_nao_ganha_nem_perde_chave_de_topo_sem_alguem_dizer() -> None:
    presentes = set(portal.build_snapshot(ProjectFactory()))

    novas = presentes - CHAVES_DE_TOPO
    assert not novas, (
        f"chave(s) nova(s) no snapshot do portal: {sorted(novas)}. Se ela deve mesmo atravessar "
        "a fronteira do cliente, acrescente-a a `CHAVES_DE_TOPO` no mesmo commit — o diff é o "
        "lugar onde a pergunta 'isto pode ir ao cliente?' é feita."
    )

    sumidas = CHAVES_DE_TOPO - presentes
    assert not sumidas, (
        f"chave(s) que o snapshot deixou de levar: {sorted(sumidas)}. O portal do cliente lê "
        "este contrato; remover chave é mudança incompatível e precisa ser deliberada (ADR 0003)."
    )
