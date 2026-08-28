"""Regressão: `commercial_model` nunca atravessa para o portal do cliente (§3 do language-map).

O `EngagementSerializer` passou a expor `commercial_model` para o Pulse (emenda da FDD 046,
28/08/2026), mas `commercial_model` é dado comercial, e a §3 do `docs/ontology/language-map.md` é
explícita: o One nunca vê dado comercial. Dizer ao cliente que ele é "design partner" ou "pago" é
exatamente a classe de coisa que fica de fora — ao lado de `CommercialOpportunity`, `PipelineStage`
e preço de tabela, que já têm a mesma proteção.

`portal.build_snapshot` continua emitindo `project.engagement` como `{id, name, status}`, sem
tocar o campo novo. O teste é deliberadamente mais largo que "a chave não está em
`snapshot['project']['engagement']`: ele varre o dicionário inteiro, recursivamente, porque o
defeito que este teste existe para prevenir não é alguém adicionar a chave ali — é alguém
adicionar `commercial_model` a mais um serializer ou a mais um lugar do snapshot amanhã, sem saber
que a regra existe. Sem este teste, a próxima pessoa que acrescentar um campo ao
`EngagementSerializer` pode achar que a projeção o segue automaticamente.
"""

from __future__ import annotations

from collections.abc import Iterator
from typing import Any

import pytest

from apps.core import portal
from apps.core.models import Engagement
from apps.core.tests.factories import ProjectFactory


def _chaves(estrutura: Any) -> Iterator[str]:
    """Todas as chaves de dicionário, em qualquer profundidade, dentro de listas ou dicionários."""
    if isinstance(estrutura, dict):
        for chave, valor in estrutura.items():
            yield str(chave)
            yield from _chaves(valor)
    elif isinstance(estrutura, list):
        for item in estrutura:
            yield from _chaves(item)


@pytest.mark.django_db
def test_commercial_model_nao_aparece_em_nenhuma_chave_do_snapshot() -> None:
    projeto = ProjectFactory()
    projeto.engagement.commercial_model = Engagement.CommercialModel.DESIGN_PARTNER
    projeto.engagement.save(update_fields=["commercial_model"])

    snapshot = portal.build_snapshot(projeto)

    assert "commercial_model" not in set(_chaves(snapshot))


@pytest.mark.django_db
def test_o_bloco_de_engagement_continua_so_id_name_status() -> None:
    projeto = ProjectFactory()

    snapshot = portal.build_snapshot(projeto)

    assert set(snapshot["project"]["engagement"]) == {"id", "name", "status"}


@pytest.mark.django_db
def test_nem_o_valor_design_partner_vaza_como_texto_no_snapshot() -> None:
    """Cinto e suspensório: nem a chave, nem o rótulo em português do valor, aparecem em lugar
    nenhum do corpo serializado — o mesmo padrão de `test_roi_nao_muda_com_faturas.py`."""
    projeto = ProjectFactory()
    projeto.engagement.commercial_model = Engagement.CommercialModel.DESIGN_PARTNER
    projeto.engagement.save(update_fields=["commercial_model"])

    serializado = str(portal.build_snapshot(projeto))

    assert "commercial_model" not in serializado
    assert "design_partner" not in serializado
    assert "Design partner" not in serializado
