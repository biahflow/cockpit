"""Regressão: a 0074 não inventa instrumento para Engagement anterior à invariante 13.

O dado histórico não distingue a primeira venda de uma continuidade, nem prova que um documento
era o Design Partner Agreement. A migração só pode afirmar que falta revisão humana: adiciona os
dois vínculos nulos e carimba `needs_review=True` em todas as linhas preexistentes.
"""

from __future__ import annotations

import pytest
from django.db import connection
from django.db.migrations.executor import MigrationExecutor

pytestmark = pytest.mark.django_db(transaction=True)

ANTES = ("core", "0073_decisao_project_phase")
DEPOIS = ("core", "0074_engagement_originating_instrument")


@pytest.fixture
def estado_0073():
    executor = MigrationExecutor(connection)
    executor.migrate([ANTES])
    yield executor.loader.project_state([ANTES]).apps
    de_volta = MigrationExecutor(connection)
    de_volta.loader.build_graph()
    de_volta.migrate(de_volta.loader.graph.leaf_nodes())


def test_legado_fica_sem_origem_e_marcado_para_revisao(estado_0073) -> None:
    apps = estado_0073
    User = apps.get_model("core", "User")
    Account = apps.get_model("core", "Account")
    Engagement = apps.get_model("core", "Engagement")
    owner = User.objects.create(username="owner-0074")
    account = Account.objects.create(name="Conta histórica", owner=owner)
    legacy = Engagement.objects.create(
        account=account,
        name="Mandato sem instrumento observado",
        owner=owner,
        needs_review=False,
    )

    executor = MigrationExecutor(connection)
    executor.migrate([DEPOIS])

    EngagementDepois = executor.loader.project_state([DEPOIS]).apps.get_model(
        "core", "Engagement"
    )
    migrated = EngagementDepois.objects.get(pk=legacy.pk)
    assert migrated.originating_commercial_opportunity_id is None
    assert migrated.originating_design_partner_agreement_id is None
    assert migrated.needs_review is True

