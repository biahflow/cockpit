"""Regressão: o backfill dá mandato a todo projeto que já existe (migração 0056, ADR 0050).

A 0057 fecha `Project.engagement` em NOT NULL. Se a 0056 deixar um único projeto para trás, o
`ALTER TABLE` falha — em produção, no meio do deploy, com o esquema meio migrado. Não há sintoma
mais barato de prevenir e mais caro de descobrir tarde, e por isso o teste executa **a função da
migração** sobre dados reais, no molde de `test_project_member_backfill.py`.

O outro alvo é o carimbo `needs_review`: ele é a única coisa que a migração afirma além do
agrupamento óbvio, e uma heurística que não é testada é uma heurística que ninguém sabe se roda.

## Por que este arquivo rola o esquema para trás

Os outros testes de backfill da casa (`test_project_member_backfill.py`,
`test_qualification_backfill.py`) rodam a função contra o registro **vivo** e o banco no HEAD, e
podem: o estado pré-migração deles se reproduz apagando linhas (`ProjectMember.objects.all()
.delete()`).

Aqui não se pode. O estado pré-migração é "projeto **com a coluna nula**", e no HEAD a coluna é
NOT NULL — um `update(engagement=None)` levanta `IntegrityError` antes de o teste começar. Então
o esquema volta de verdade para a 0055, os dados nascem pelos modelos **históricos** daquele
estado, e o esquema volta para o HEAD no fim. É o que torna o teste uma medição do que a migração
faz, e não do que o modelo de hoje permite.

`transaction=True` é consequência disso, não escolha: o SQLite recusa DDL dentro de uma transação
(`NotSupportedError` do schema editor), e é o que o `django_db` normal abre.
"""

import importlib
from datetime import timedelta

import pytest
from django.db import connection
from django.db.migrations.executor import MigrationExecutor
from django.utils import timezone

pytestmark = pytest.mark.django_db(transaction=True)

MIGRACAO = "apps.core.migrations.0056_backfill_engagement"
ANTES = ("core", "0055_engagement")
DEPOIS = ("core", "0057_project_engagement_obrigatorio")


@pytest.fixture
def estado_0055():
    """Volta o esquema para a 0055 e devolve os modelos **daquele** estado.

    É exatamente o `from_state.apps` que o Django entrega a um `RunPython` da 0056.
    """
    executor = MigrationExecutor(connection)
    executor.migrate([ANTES])
    yield executor.loader.project_state([ANTES]).apps
    de_volta = MigrationExecutor(connection)
    de_volta.loader.build_graph()
    # Migra até o **HEAD**, não só até `DEPOIS`: a partir da `0069` (renome das tabelas da Fase 6)
    # o nome físico das tabelas muda entre estados de migração, e o `flush` do teardown usa o nome
    # do HEAD. Parar num estado intermediário deixa a tabela com o nome antigo e o flush estoura.
    de_volta.migrate(de_volta.loader.graph.leaf_nodes())


def _rodar_backfill(apps) -> None:
    """Importa a migração pelo nome de módulo (o número no início impede o `import` normal)."""
    importlib.import_module(MIGRACAO).backfill_engagement(apps, None)


def _reverter_backfill(apps) -> None:
    importlib.import_module(MIGRACAO).desfazer_backfill(apps, None)


# --------------------------------------------------------------------- fábricas históricas

_SEQ = {"n": 0}


def _proximo() -> int:
    _SEQ["n"] += 1
    return _SEQ["n"]


def _conta(apps, nome: str | None = None):
    n = _proximo()
    User = apps.get_model("core", "User")
    dono = User.objects.create(username=f"dono{n}", email=f"dono{n}@exemplo.test")
    return apps.get_model("core", "Client").objects.create(
        name=nome or f"Conta {n}", owner=dono, status="active"
    )


def _servico(apps):
    n = _proximo()
    return apps.get_model("core", "Service").objects.create(name=f"Serviço {n}")


def _projeto(apps, conta, *, service=None, start_date=None, engagement=None):
    inicio = start_date or timezone.localdate()
    return apps.get_model("core", "Project").objects.create(
        client=conta,
        engagement=engagement,
        name=f"Projeto {_proximo()}",
        owner=conta.owner,
        start_date=inicio,
        due_date=inicio + timedelta(days=30),
        service=service,
    )


def _engagements(apps):
    return apps.get_model("core", "Engagement").objects


def _projetos(apps):
    return apps.get_model("core", "Project").objects


# ------------------------------------------------------------------------------- testes


def test_todo_projeto_sai_do_backfill_com_engajamento(estado_0055) -> None:
    """A condição que a 0057 exige. Sem ela o passo 3 falha no `ALTER TABLE`."""
    apps = estado_0055
    conta = _conta(apps)
    um = _projeto(apps, conta)
    outro = _projeto(apps, conta)
    de_outra_conta = _projeto(apps, _conta(apps))

    _rodar_backfill(apps)

    assert not _projetos(apps).filter(engagement__isnull=True).exists()
    um.refresh_from_db()
    outro.refresh_from_db()
    de_outra_conta.refresh_from_db()
    assert um.engagement_id == outro.engagement_id  # um mandato por conta
    assert de_outra_conta.engagement_id != um.engagement_id


def test_o_engajamento_criado_descreve_a_conta(estado_0055) -> None:
    apps = estado_0055
    hoje = timezone.localdate()
    conta = _conta(apps, "Acme")
    _projeto(apps, conta, start_date=hoje - timedelta(days=40))
    _projeto(apps, conta, start_date=hoje)

    _rodar_backfill(apps)

    engagement = _engagements(apps).get(account=conta)
    assert engagement.name == "Engajamento — Acme"
    assert engagement.owner_id == conta.owner_id
    assert engagement.status == "active"
    # A data em que o trabalho começou de fato, não a do projeto mais novo.
    assert engagement.started_at == hoje - timedelta(days=40)


def test_conta_sem_projeto_nao_ganha_engajamento(estado_0055) -> None:
    """O mandato nasce quando a primeira venda vira projeto; engajamento vazio seria só ruído."""
    apps = estado_0055
    _conta(apps)

    _rodar_backfill(apps)

    assert not _engagements(apps).exists()


def test_carimbo_de_revisao_por_servicos_distintos(estado_0055) -> None:
    """Primeira heurística: degraus diferentes **podem** ser duas contratações sem relação."""
    apps = estado_0055
    conta = _conta(apps)
    _projeto(apps, conta, service=_servico(apps))
    _projeto(apps, conta, service=_servico(apps))

    _rodar_backfill(apps)

    assert _engagements(apps).get(account=conta).needs_review is True


def test_servico_nulo_nao_conta_como_servico_distinto(estado_0055) -> None:
    """Projeto sem serviço é lacuna de cadastro, não sinal de outra jornada — e marcar por isso
    encheria a fila de revisão de ruído, que é como uma sinalização deixa de ser lida."""
    apps = estado_0055
    conta = _conta(apps)
    servico = _servico(apps)
    _projeto(apps, conta, service=servico)
    _projeto(apps, conta, service=None)
    _projeto(apps, conta, service=servico)

    _rodar_backfill(apps)

    assert _engagements(apps).get(account=conta).needs_review is False


def test_carimbo_de_revisao_por_intervalo_longo(estado_0055) -> None:
    """Segunda heurística: meio ano de silêncio descreve uma conta que voltou a comprar."""
    apps = estado_0055
    conta = _conta(apps)
    servico = _servico(apps)
    hoje = timezone.localdate()
    _projeto(apps, conta, service=servico, start_date=hoje - timedelta(days=400))
    _projeto(apps, conta, service=servico, start_date=hoje)

    _rodar_backfill(apps)

    assert _engagements(apps).get(account=conta).needs_review is True


def test_jornada_continua_nao_e_carimbada(estado_0055) -> None:
    """O falso positivo é barato, mas não é de graça: a jornada contínua tem de passar limpa."""
    apps = estado_0055
    conta = _conta(apps)
    servico = _servico(apps)
    hoje = timezone.localdate()
    _projeto(apps, conta, service=servico, start_date=hoje - timedelta(days=60))
    _projeto(apps, conta, service=servico, start_date=hoje)

    _rodar_backfill(apps)

    assert _engagements(apps).get(account=conta).needs_review is False


def test_backfill_e_idempotente(estado_0055) -> None:
    """Um deploy reexecutado depois de falhar no passo 3 não pode duplicar mandato."""
    apps = estado_0055
    conta = _conta(apps)
    _projeto(apps, conta)

    _rodar_backfill(apps)
    _rodar_backfill(apps)

    assert _engagements(apps).filter(account=conta).count() == 1


def test_backfill_nao_mexe_em_engajamento_que_ja_existia(estado_0055) -> None:
    """O projeto que já aponta para um mandato fica onde está."""
    apps = estado_0055
    conta = _conta(apps)
    escolhido = _engagements(apps).create(
        account=conta, name="Mandato escrito por gente", owner=conta.owner
    )
    projeto = _projeto(apps, conta, engagement=escolhido)

    _rodar_backfill(apps)

    projeto.refresh_from_db()
    assert projeto.engagement_id == escolhido.pk


def test_reversa_solta_os_projetos_e_apaga_o_que_criou(estado_0055) -> None:
    """`Project.engagement` é `PROTECT`: sem soltar antes, a reversa levantaria em vez de apagar."""
    apps = estado_0055
    conta = _conta(apps)
    projeto = _projeto(apps, conta)
    _rodar_backfill(apps)

    _reverter_backfill(apps)

    projeto.refresh_from_db()
    assert projeto.engagement_id is None
    assert not _engagements(apps).exists()


def test_reversa_nao_apaga_mandato_escrito_por_gente(estado_0055) -> None:
    """O nome derivado é a assinatura da migração; um mandato com outro nome não é dela."""
    apps = estado_0055
    conta = _conta(apps)
    escolhido = _engagements(apps).create(
        account=conta, name="Transformação 2027", owner=conta.owner
    )
    _projeto(apps, conta, engagement=escolhido)

    _reverter_backfill(apps)

    assert _engagements(apps).filter(pk=escolhido.pk).exists()
