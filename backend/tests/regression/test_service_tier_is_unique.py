"""Regressão: no máximo um serviço ativo por degrau da escada.

Espelha a invariante do pipeline (uma etapa "ganho", uma "perdido"): duas Qualification Calls
ativas ao mesmo tempo tornariam ambíguo qual degrau o lead e a proposta usam.
"""

import pytest
from django.db import IntegrityError, transaction

from apps.core.models import Service


@pytest.mark.django_db
def test_database_rejects_a_second_active_service_in_the_same_tier():
    assert Service.objects.filter(tier=Service.Tier.QUALIFICATION_CALL).count() == 1

    with pytest.raises(IntegrityError), transaction.atomic():
        Service.objects.create(name="Qualification Call bis", tier=Service.Tier.QUALIFICATION_CALL)

    assert Service.objects.filter(tier=Service.Tier.QUALIFICATION_CALL).count() == 1


@pytest.mark.django_db
def test_archived_service_does_not_hold_its_tier():
    seeded = Service.objects.get(tier=Service.Tier.PROVE)
    seeded.archive()

    replacement = Service.objects.create(name="PROVE 2026", tier=Service.Tier.PROVE)

    assert replacement.pk != seeded.pk
    assert Service.objects.filter(tier=Service.Tier.PROVE, archived_at__isnull=True).count() == 1
