"""Regressão: a migração `0059` carimba todo `Engagement` que já existia como `paid`.

Não há `RunPython` aqui — é um `AddField` com `default="paid"` — mas o comportamento que a
docstring da 0059 promete (linha existente vira paga por inferência, não por observação) é
exatamente o tipo de garantia que só uma migração real, rodando contra o esquema **anterior**,
prova. No mesmo molde de `test_engagement_backfill.py`: o esquema volta para a `0058` (antes do
campo existir), o dado nasce pelo modelo **histórico** daquele estado, a migração roda, e só então
se olha o valor.
"""

import pytest
from django.db import connection
from django.db.migrations.executor import MigrationExecutor

pytestmark = pytest.mark.django_db(transaction=True)

ANTES = ("core", "0058_carimbo_da_projecao")
DEPOIS = ("core", "0059_engagement_commercial_model")

_SEQ = {"n": 0}


def _proximo() -> int:
    _SEQ["n"] += 1
    return _SEQ["n"]


@pytest.fixture
def estado_0058():
    """Volta o esquema para antes do campo `commercial_model` existir."""
    executor = MigrationExecutor(connection)
    executor.migrate([ANTES])
    yield executor.loader.project_state([ANTES]).apps
    de_volta = MigrationExecutor(connection)
    de_volta.loader.build_graph()
    de_volta.migrate([DEPOIS])


def _conta_e_dono(apps):
    n = _proximo()
    User = apps.get_model("core", "User")
    dono = User.objects.create(username=f"dono{n}-0059", email=f"dono{n}-0059@exemplo.test")
    return apps.get_model("core", "Client").objects.create(
        name=f"Conta {n}", owner=dono, status="active"
    )


def test_engajamento_pre_existente_vira_paid_apos_a_migracao(estado_0058) -> None:
    apps = estado_0058
    conta = _conta_e_dono(apps)
    Engagement = apps.get_model("core", "Engagement")
    engagement = Engagement.objects.create(
        account=conta, name="Mandato anterior à emenda", owner=conta.owner
    )

    executor = MigrationExecutor(connection)
    executor.migrate([DEPOIS])

    EngagementDepois = executor.loader.project_state([DEPOIS]).apps.get_model(
        "core", "Engagement"
    )
    recarregado = EngagementDepois.objects.get(pk=engagement.pk)
    assert recarregado.commercial_model == "paid"
