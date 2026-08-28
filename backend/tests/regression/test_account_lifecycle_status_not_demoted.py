"""Regressão: um PATCH não desfaz a promoção que a oportunidade ganha causou.

`lifecycle_status` deixou de ser somente-leitura para que quem cadastra declare o que a conta é. O
risco que isso abre é o inverso da promoção: rebaixar para prospect alguém que já fechou. O signal
`_promote_account_on_won` só promove na transição, então ele não corrigiria de volta — a recusa é
a única proteção.

O caminho `active → inactive` **é** permitido e vive em `test_inativo_nao_e_arquivado.py`: sair da
carteira não é o mesmo que nunca ter comprado.
"""

import pytest
from django.urls import reverse
from rest_framework.test import APIClient

from apps.core.models import Account, PipelineStage, User
from apps.core.tests.factories import AccountFactory, CommercialOpportunityFactory, UserFactory


@pytest.mark.django_db
def test_account_with_won_opportunity_cannot_return_to_prospect() -> None:
    account = AccountFactory(lifecycle_status=Account.LifecycleStatus.PROSPECT)
    won = PipelineStage.objects.get(kind=PipelineStage.Kind.WON)
    CommercialOpportunityFactory(account=account, stage=won)
    api = APIClient()
    api.force_authenticate(UserFactory(role=User.Role.ADMIN))

    response = api.patch(
        reverse("client-detail", args=[account.pk]), {"lifecycle_status": "prospect"}, format="json"
    )

    assert response.status_code == 400
    account.refresh_from_db()
    assert account.lifecycle_status == Account.LifecycleStatus.ACTIVE


@pytest.mark.django_db
def test_account_without_won_opportunity_can_be_corrected() -> None:
    account = AccountFactory(lifecycle_status=Account.LifecycleStatus.ACTIVE)
    CommercialOpportunityFactory(account=account)  # etapa aberta
    api = APIClient()
    api.force_authenticate(UserFactory(role=User.Role.ADMIN))

    response = api.patch(
        reverse("client-detail", args=[account.pk]), {"lifecycle_status": "prospect"}, format="json"
    )

    assert response.status_code == 200
    account.refresh_from_db()
    assert account.lifecycle_status == Account.LifecycleStatus.PROSPECT
