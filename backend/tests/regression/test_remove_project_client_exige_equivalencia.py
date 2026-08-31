"""Regressão: a migração 0070 só remove `Project.client` depois de provar equivalência.

`Project.clean()` nunca foi constraint de banco e `save()` não o chama automaticamente. Portanto,
uma linha histórica divergente pode existir mesmo que todos os caminhos atuais estejam corretos.
O teste volta ao estado 0069 e mede a função que roda na própria migração antes do `RemoveField`.
"""

from __future__ import annotations

import importlib
from datetime import timedelta

import pytest
from django.db import connection
from django.db.migrations.executor import MigrationExecutor
from django.utils import timezone

pytestmark = pytest.mark.django_db(transaction=True)

MIGRACAO = "apps.core.migrations.0070_remove_project_client"
ANTES = ("core", "0069_renomeia_tabelas_da_ontologia")


@pytest.fixture
def estado_0069():
    executor = MigrationExecutor(connection)
    executor.migrate([ANTES])
    apps = executor.loader.project_state([ANTES]).apps
    yield apps

    # Um caso divergente deliberado precisa ser reconciliado para o próprio teardown conseguir
    # avançar pela 0070. Isso também prova que o gate libera a base depois da correção dos dados.
    Project = apps.get_model("core", "Project")
    for projeto in Project.objects.select_related("engagement__account"):
        if projeto.client_id != projeto.engagement.account_id:
            Project.objects.filter(pk=projeto.pk).update(client_id=projeto.engagement.account_id)

    de_volta = MigrationExecutor(connection)
    de_volta.loader.build_graph()
    de_volta.migrate(de_volta.loader.graph.leaf_nodes())


def _criar_projeto(apps, *, divergente: bool):
    User = apps.get_model("core", "User")
    Account = apps.get_model("core", "Account")
    Engagement = apps.get_model("core", "Engagement")
    Project = apps.get_model("core", "Project")

    dono = User.objects.create(username=f"dono-{divergente}")
    conta = Account.objects.create(name="Conta canônica", owner=dono, lifecycle_status="active")
    client = (
        Account.objects.create(name="Conta divergente", owner=dono, lifecycle_status="active")
        if divergente
        else conta
    )
    engagement = Engagement.objects.create(
        account=conta,
        name="Mandato",
        owner=dono,
        started_at=timezone.localdate(),
    )
    return Project.objects.create(
        client=client,
        engagement=engagement,
        name="Projeto",
        owner=dono,
        start_date=timezone.localdate(),
        due_date=timezone.localdate() + timedelta(days=30),
    )


def _exigir_equivalencia(apps) -> None:
    importlib.import_module(MIGRACAO).exigir_equivalencia_da_projecao(apps, None)


def test_base_alinhada_libera_a_remocao(estado_0069) -> None:
    _criar_projeto(estado_0069, divergente=False)

    _exigir_equivalencia(estado_0069)


def test_base_divergente_interrompe_a_remocao_e_nomeia_o_projeto(estado_0069) -> None:
    projeto = _criar_projeto(estado_0069, divergente=True)

    with pytest.raises(RuntimeError, match=rf"project ids: \[{projeto.pk}\]"):
        _exigir_equivalencia(estado_0069)
