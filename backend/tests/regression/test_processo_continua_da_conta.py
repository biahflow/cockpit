"""Regressão: o `Process` pertence à **conta**, e o projeto é só proveniência (FDD 039, ADR 0050).

A fatia do `Engagement` acrescenta uma camada entre a conta e o projeto, e a tentação que ela cria
é reancorar o que hoje pende da conta: "o processo foi mapeado num projeto, então ele é do
projeto — ou do engajamento". Seria perder o que a FDD 039 decidiu de propósito: **o processo
mapeado é da operação do cliente e sobrevive à venda que o descobriu**. Reancorá-lo no projeto
faria o mapeamento desaparecer quando o projeto encerrasse, e o Discovery seguinte remapearia do
zero uma operação que a casa já conhecia.

Esta fatia **não mexeu** na âncora do `Process`, e este arquivo é o que faz disso um fato
verificado em vez de uma intenção. A fatia 4 da issue #67 renomeou a classe e o campo (`processo`
→ `process`, ADR 0052) e não tocou em nenhuma das duas propriedades abaixo — que é exatamente o
que este arquivo mede. O que ele fixa é estrutural, e por isso não envelhece com a implementação: a
âncora é obrigatória e é a conta; a proveniência é opcional e é o projeto.
"""

import pytest

from apps.core.models import Process, ProcessStep, Project
from apps.core.tests.factories import AccountFactory, ProcessFactory, ProjectFactory

pytestmark = pytest.mark.django_db


def test_a_ancora_do_processo_e_a_conta_e_e_obrigatoria() -> None:
    ancora = Process._meta.get_field("account")

    assert ancora.null is False
    assert ancora.related_model.__name__ == "Account"


def test_o_projeto_no_processo_e_proveniencia_opcional() -> None:
    """`source_project`, e não `project`: o nome já diz que é registro de origem, não vínculo.

    `SET_NULL` é a outra metade — o processo sobrevive ao projeto que o descobriu.
    """
    proveniencia = Process._meta.get_field("source_project")

    assert proveniencia.null is True
    assert proveniencia.related_model.__name__ == "Project"
    assert proveniencia.remote_field.on_delete.__name__ == "SET_NULL"


def test_o_processo_nao_ganhou_vinculo_com_engajamento() -> None:
    """O engajamento é comercial; o processo é operacional. Ligá-los faria o mapa de uma operação
    depender do mandato que a casa vendeu, e uma conta tem um só mapa por vez."""
    campos = {campo.name for campo in Process._meta.get_fields()}

    assert "engagement" not in campos


def test_a_etapa_chega_a_conta_pelo_processo_e_nao_pelo_projeto() -> None:
    # A etapa é filha do processo e chega à conta por ele — não pelo projeto nem pelo engajamento.
    # O achado deixou de ser filho do processo na Fase 6 (ADR 0052): `Evidence`/`Finding` são
    # ancorados na **conta** diretamente, e a suíte do split é quem fixa a âncora deles.
    relacoes = {
        campo.name
        for campo in ProcessStep._meta.get_fields()
        if campo.is_relation and not campo.auto_created
    }
    assert "process" in relacoes
    assert "project" not in relacoes
    assert "engagement" not in relacoes


def test_o_processo_sobrevive_ao_projeto_que_o_descobriu() -> None:
    """A regra estrutural exercitada: arquivar o projeto de origem não leva o mapa junto."""
    conta = AccountFactory()
    projeto = ProjectFactory(client=conta)
    processo = ProcessFactory(account=conta, source_project=projeto)

    projeto.archive()

    processo.refresh_from_db()
    assert processo.account_id == conta.pk
    assert processo.source_project_id == projeto.pk
    assert Project.objects.get(pk=projeto.pk).archived_at is not None
