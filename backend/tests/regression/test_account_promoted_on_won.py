"""Regressão: a conta prospect vira "Cliente" (`active`) quando a oportunidade é ganha.

É a única transição automática de `lifecycle_status`. Entrar em `inactive` não tem signal e não
vai ter: "não tem trabalho em andamento" não é fato observável no banco.
"""

import pytest

from apps.core.models import Account, PipelineStage
from apps.core.tests.factories import AccountFactory, CommercialOpportunityFactory


@pytest.mark.django_db
def test_won_opportunity_promotes_prospect_account() -> None:
    account = AccountFactory(lifecycle_status=Account.LifecycleStatus.PROSPECT)
    won = PipelineStage.objects.get(kind=PipelineStage.Kind.WON)

    CommercialOpportunityFactory(account=account, stage=won)

    account.refresh_from_db()
    assert account.lifecycle_status == Account.LifecycleStatus.ACTIVE


@pytest.mark.django_db
def test_open_opportunity_keeps_account_prospect() -> None:
    account = AccountFactory(lifecycle_status=Account.LifecycleStatus.PROSPECT)
    CommercialOpportunityFactory(account=account)  # etapa OPEN por padrão

    account.refresh_from_db()
    assert account.lifecycle_status == Account.LifecycleStatus.PROSPECT
