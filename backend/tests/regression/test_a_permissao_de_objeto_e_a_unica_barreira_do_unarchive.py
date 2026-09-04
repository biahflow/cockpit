"""Regressão: a `unarchive` é o único caminho HTTP onde `has_object_permission` é a barreira real.

O caminho comum não serve de oráculo: `get_object()` do DRF filtra pelo `get_queryset()`
escopado (`ProjectScopedMixin`/`project_scope_q`) **antes** de chamar `check_object_permissions`,
então um `GET /processos/{id_alheio}/` já devolve 404 pelo queryset — a permissão de objeto nunca
chega a ser avaliada, e um teste escrito sobre esse caminho ficaria verde exercitando o queryset,
não `permissions.py`. `ArchiveModelViewSet.unarchive` (`apps/core/views.py`) é a exceção
deliberada: ela resolve o objeto pela queryset **crua** (`get_object_or_404(self.queryset, ...)`,
sem passar por `get_queryset()`) — senão o próprio recorte esconderia justamente o registro
arquivado que se quer restaurar — e só então chama `self.check_object_permissions`. Por isso a
asserção correta aqui é **403, nunca 404**: um 404 significaria que o objeto não chegou à
permissão, e o teste não estaria provando nada sobre ela.

Os treze recursos abaixo são todos os `ArchiveModelViewSet` cuja permissão de objeto (Entrega) não
depende só de participação de projeto direta. Para cada um, um usuário Entrega que não alcança a
conta/projeto do objeto arquiva-o e tenta restaurá-lo: a resposta tem de ser 403, e o registro tem
de continuar arquivado — a permissão não pode ter deixado o efeito acontecer antes de recusar.

**Dez dos treze medem `has_object_permission`; três medem a camada de cima, e a distinção está
aqui porque ela não é visível no resultado.** `commercial_opportunity`, `engagement` e
`project_member` estão na lista de recursos só-leitura da Entrega em `RolePermission.has_permission`,
e `unarchive` é `POST`: eles levam 403 antes de existir objeto para avaliar. Medido tornando
`has_object_permission` incondicionalmente permissiva — dez casos ficaram vermelhos e estes três
seguiram verdes. Os três continuam valendo (a recusa é real e é a que o produto promete), mas quem
mexer em `permissions.py` precisa saber que eles **não** protegem o ramo de objeto: se um dia a
Entrega ganhar escrita nesses recursos, estes três casos passam a exercitar o ramo de objeto de
verdade, e é aí que o valor deles muda. Os outros dez são `SatisfactionRecord`, `Process`,
`ProcessStep`, `Evidence`, `Finding`, `PainPoint`, `ImprovementOpportunity`, `PriorityAssessment`,
`SolutionHypothesis` e `ValueLedgerEntry`.
"""

from datetime import date

import pytest
from django.urls import reverse
from rest_framework.test import APIClient

from apps.core.models import SatisfactionRecord, User
from apps.core.tests.factories import (
    AccountFactory,
    CommercialOpportunityFactory,
    EngagementFactory,
    EvidenceFactory,
    FindingFactory,
    ImprovementOpportunityFactory,
    PainPointFactory,
    PriorityAssessmentFactory,
    ProcessFactory,
    ProcessStepFactory,
    ProjectMemberFactory,
    SolutionHypothesisFactory,
    UserFactory,
    ValueLedgerEntryFactory,
)

pytestmark = pytest.mark.django_db


@pytest.fixture
def delivery() -> User:
    return UserFactory(role=User.Role.DELIVERY)


@pytest.fixture
def api(delivery: User) -> APIClient:
    client = APIClient()
    client.force_authenticate(delivery)
    return client


def _satisfaction_record() -> SatisfactionRecord:
    return SatisfactionRecord.objects.create(
        account=AccountFactory(),
        nivel=SatisfactionRecord.Nivel.SATISFIED,
        fonte=SatisfactionRecord.Fonte.DECLARED,
        happened_on=date(2026, 8, 1),
    )


# basename -> fábrica de um objeto que nasce **sem nenhum vínculo** com o `delivery` do teste
# (conta/projeto/mandato próprios, criados pela subfactory). Nenhum `ProjectMemberFactory` liga o
# usuário do teste a eles, então nenhum é alcançável por `visible_to`.
RESOURCES = {
    "opportunity": CommercialOpportunityFactory,
    "engagement": EngagementFactory,
    "projectmember": ProjectMemberFactory,
    "satisfacao": _satisfaction_record,
    "processo": ProcessFactory,
    "processoetapa": ProcessStepFactory,
    "evidence": EvidenceFactory,
    "finding": FindingFactory,
    "painpoint": PainPointFactory,
    "improvementopportunity": ImprovementOpportunityFactory,
    "priorityassessment": PriorityAssessmentFactory,
    "solutionhypothesis": SolutionHypothesisFactory,
    "valueledgerentry": ValueLedgerEntryFactory,
}


@pytest.mark.parametrize("basename", sorted(RESOURCES))
def test_delivery_sem_alcance_recebe_403_e_nao_desarquiva(
    api: APIClient, basename: str
) -> None:
    # `opportunity` nasce aberta (`PipelineStageFactory` default é `kind=OPEN`), o que também
    # recusaria o objeto pelo próprio `is_won` (o ramo `CommercialOpportunity`) — reforço, não
    # substituição, do "não alcança".
    obj = RESOURCES[basename]()
    obj.archive()

    response = api.post(reverse(f"{basename}-unarchive", args=[obj.pk]))

    assert response.status_code == 403
    obj.refresh_from_db()
    assert obj.archived_at is not None
