"""Regressão: o artefato pertence a exatamente uma ponta — oportunidade ou projeto (FDD 016).

Mesma invariante do `Document`, e pelo mesmo motivo: o vínculo define quem enxerga o conteúdo.
Um artefato solto não teria dono para o controle de acesso; um artefato com duas pontas seria
contado duas vezes no funil por etapa e poderia expor uma proposta comercial pelo lado do projeto.
"""

import pytest
from django.core.exceptions import ValidationError

from apps.core.models import Artifact
from apps.core.tests.factories import CommercialOpportunityFactory, ProjectFactory, UserFactory


@pytest.mark.django_db
def test_artifact_without_a_link_is_invalid() -> None:
    artifact = Artifact(kind=Artifact.Kind.PROPOSAL, title="Solta", created_by=UserFactory())

    with pytest.raises(ValidationError):
        artifact.full_clean()


@pytest.mark.django_db
def test_artifact_with_both_links_is_invalid() -> None:
    artifact = Artifact(
        kind=Artifact.Kind.PROPOSAL,
        title="Dupla",
        commercial_opportunity=CommercialOpportunityFactory(),
        project=ProjectFactory(),
        created_by=UserFactory(),
    )

    with pytest.raises(ValidationError):
        artifact.full_clean()
