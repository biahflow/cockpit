"""Regressão: o mandato aberto promove a conta prospect a "Cliente" (`active`).

O defeito que ela fecha foi observado em uso: uma conta com parceria assinada e Discovery rodando
continuava marcada **"Prospect"** na listagem. A única promoção automática era
`_promote_account_on_won`, que depende de oportunidade **ganha** — e o Design Partner não tem
oportunidade nenhuma (ADR 0053, ADR 0061). Quem está recebendo entrega é cliente
(`language-map` §4, DAP `dap-lifecycle-status-r1`).

A guarda vale para **qualquer** `Engagement`, e não só o `design_partner`: mandato é trabalho
contratado. O caminho pago já promove pela oportunidade, e o filtro por `prospect` é o que faz os
dois conviverem sem duplicar efeito — exatamente como no vizinho.

`active → inactive` continua sem automação, pela razão que a docstring de `_promote_account_on_won`
dá: "não tem trabalho em andamento" não é fato observável no banco.
"""

import pytest

from apps.core.models import Account, Engagement
from apps.core.tests.factories import AccountFactory, EngagementFactory

pytestmark = pytest.mark.django_db


def test_o_mandato_promove_a_conta_prospect() -> None:
    conta = AccountFactory(lifecycle_status=Account.LifecycleStatus.PROSPECT)

    EngagementFactory(account=conta)

    conta.refresh_from_db()
    assert conta.lifecycle_status == Account.LifecycleStatus.ACTIVE


def test_o_mandato_de_design_partner_tambem_promove() -> None:
    """O caso que motivou a guarda: parceria assinada, sem venda no meio."""
    conta = AccountFactory(lifecycle_status=Account.LifecycleStatus.PROSPECT)

    EngagementFactory(
        account=conta, commercial_model=Engagement.CommercialModel.DESIGN_PARTNER
    )

    conta.refresh_from_db()
    assert conta.lifecycle_status == Account.LifecycleStatus.ACTIVE


def test_a_conta_ativa_nao_muda() -> None:
    conta = AccountFactory(lifecycle_status=Account.LifecycleStatus.ACTIVE)

    EngagementFactory(account=conta)

    conta.refresh_from_db()
    assert conta.lifecycle_status == Account.LifecycleStatus.ACTIVE


def test_a_conta_inativa_nao_regride_para_ativa() -> None:
    """`inactive` é **já foi** cliente, e é escolha de quem edita a conta.

    Sem o filtro por `prospect` no `update()`, abrir um mandato numa conta inativa a reescreveria
    para `active` sem ninguém ter dito isso — que é a regressão silenciosa que este teste barra.
    """
    conta = AccountFactory(lifecycle_status=Account.LifecycleStatus.INACTIVE)

    EngagementFactory(account=conta)

    conta.refresh_from_db()
    assert conta.lifecycle_status == Account.LifecycleStatus.INACTIVE


def test_editar_o_mandato_nao_promove() -> None:
    """Só a **criação** promove: o `created` é o que separa "abriu trabalho" de "editou linha".

    Sem ele, uma conta que alguém devolveu a `prospect` de propósito voltaria a `active` no
    primeiro `save()` do mandato — promoção sem ato que a justifique.
    """
    conta = AccountFactory(lifecycle_status=Account.LifecycleStatus.ACTIVE)
    mandato = EngagementFactory(account=conta)
    Account.objects.filter(pk=conta.pk).update(
        lifecycle_status=Account.LifecycleStatus.PROSPECT
    )

    mandato.name = "Parceria revisada"
    mandato.save()

    conta.refresh_from_db()
    assert conta.lifecycle_status == Account.LifecycleStatus.PROSPECT
