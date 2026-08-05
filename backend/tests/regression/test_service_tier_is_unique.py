"""Regressão: no máximo um serviço ativo por nível de produto.

Espelha a invariante do pipeline (uma etapa "ganho", uma "perdido"): dois Discovery Express
ativos ao mesmo tempo tornariam ambíguo qual nível o lead e a proposta usam.
"""

import pytest
from django.db import IntegrityError, transaction

from apps.core.models import Service


@pytest.mark.django_db
def test_database_rejects_a_second_active_service_in_the_same_tier():
    assert Service.objects.filter(tier=Service.Tier.DISCOVERY_EXPRESS).count() == 1

    with pytest.raises(IntegrityError), transaction.atomic():
        Service.objects.create(name="Discovery Express bis", tier=Service.Tier.DISCOVERY_EXPRESS)

    assert Service.objects.filter(tier=Service.Tier.DISCOVERY_EXPRESS).count() == 1


@pytest.mark.django_db
def test_archived_service_does_not_hold_its_tier():
    seeded = Service.objects.get(tier=Service.Tier.IMPLEMENTATION)
    seeded.archive()

    replacement = Service.objects.create(name="Implantação 2026", tier=Service.Tier.IMPLEMENTATION)

    assert replacement.pk != seeded.pk
    assert Service.objects.filter(tier=Service.Tier.IMPLEMENTATION, archived_at__isnull=True).count() == 1
