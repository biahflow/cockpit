"""Regressão: a escada da ontologia atravessa inteira, de ponta a ponta.

As quatro fatias (ADR 0049, ADR 0050, FDD 044/045/046) foram escritas em branches paralelas, e
cada uma testou o próprio degrau contra o `main` de antes das outras. Este arquivo cobre o que
nenhuma delas podia cobrir sozinha: a corrente ligada.

```
Lead → Qualification →(qualified) CommercialOpportunity → Engagement + Project → Discovery
                                                                                    ↓
                                                                         Evidence + Finding
```

O que se protege aqui não é cada elo — cada um tem a suíte dele — é a **emenda**. Um elo solto não
deixa nada vermelho: a tela renderiza, o teste da fatia vizinha passa, e o defeito só aparece quando
alguém percorre o caminho de verdade meses depois. É o mesmo argumento do
`test_origem_do_lead_sobrevive_a_conversao.py`, uma fatia acima.
"""

from datetime import timedelta

import pytest
from django.urls import reverse
from django.utils import timezone
from rest_framework.test import APIClient

from apps.core.models import (
    CommercialOpportunity,
    Discovery,
    Evidence,
    Finding,
    Lead,
    PipelineStage,
    Project,
    Qualification,
    Service,
    User,
)
from apps.core.tests.factories import UserFactory

pytestmark = pytest.mark.django_db


@pytest.fixture
def api() -> APIClient:
    client = APIClient()
    client.force_authenticate(UserFactory(role=User.Role.ADMIN))
    return client


def test_de_lead_a_achado_sem_elo_solto(api: APIClient) -> None:
    lead = Lead.objects.create(name="ACME", email="a@acme.com", company="ACME")

    convertido = api.post(reverse("lead-convert", args=[lead.pk]), {}, format="json")
    assert convertido.status_code == 201, convertido.data
    qualification = Qualification.objects.get(pk=convertido.data["qualification"]["id"])
    assert qualification.outcome == Qualification.Outcome.QUALIFIED
    # Fase 1: converter registra a avaliação e **não** abre venda.
    assert CommercialOpportunity.objects.count() == 0

    degrau = Service.objects.get(tier=Service.Tier.DISCOVERY_SPRINT)
    aberta = api.post(
        reverse("qualification-open-opportunity", args=[qualification.pk]),
        {"title": "Discovery Sprint", "service": degrau.pk},
        format="json",
    )
    assert aberta.status_code == 201, aberta.data
    opportunity = CommercialOpportunity.objects.get(pk=aberta.data["id"])
    assert opportunity.origin_qualification_id == qualification.pk

    opportunity.stage = PipelineStage.objects.get(kind=PipelineStage.Kind.WON)
    opportunity.save(update_fields=["stage"])
    convertida = api.post(
        reverse("opportunity-convert-to-project", args=[opportunity.pk]),
        {
            "client": opportunity.account_id, "name": "Discovery Sprint ACME",
            "start_date": str(timezone.localdate()),
            "due_date": str(timezone.localdate() + timedelta(days=30)), "status": "planning",
        },
        format="json",
    )
    assert convertida.status_code == 201, convertida.data
    projeto = Project.objects.get(pk=convertida.data["id"])
    # Fase 2: a venda avulsa não vira caso especial — ela cria o mandato de escopo único (D3).
    assert projeto.engagement_id is not None
    assert projeto.engagement.account_id == opportunity.account_id
    assert projeto.originating_commercial_opportunity_id == opportunity.pk

    criado = api.post(
        reverse("discovery-list"), {"project": projeto.pk, "scope": "AS-IS"}, format="json"
    )
    assert criado.status_code == 201, criado.data
    discovery = Discovery.objects.get(pk=criado.data["id"])

    evidencia = api.post(
        reverse("evidence-list"),
        {
            "account": projeto.client_id, "discovery": discovery.pk,
            "kind": "interview", "raw_excerpt": "o fechamento leva tres dias",
        },
        format="json",
    )
    assert evidencia.status_code == 201, evidencia.data
    assert Evidence.objects.get(pk=evidencia.data["id"]).content_hash

    achado = api.post(
        reverse("finding-list"),
        {
            "account": projeto.client_id, "statement": "o fechamento e lento",
            "evidences": [evidencia.data["id"]],
        },
        format="json",
    )
    assert achado.status_code == 201, achado.data
    # Fase 3: achado nasce hipótese, e promover é ato humano com revisor.
    assert Finding.objects.get(pk=achado.data["id"]).epistemic_status == "hypothesis"


def test_a_oferta_de_aquisicao_continua_barrada_depois_do_engagement(api: APIClient) -> None:
    """A invariante 6 (fase 1) sobrevive à chegada do Engagement (fase 2).

    O `Engagement` acrescentou um caminho novo para nascer projeto, e a recusa da oferta de
    aquisição precisa valer nos dois. Aqui ela é medida um degrau antes: a Qualification Call nem
    chega a abrir a venda.
    """
    lead = Lead.objects.create(name="Beta", email="b@beta.com")
    convertido = api.post(reverse("lead-convert", args=[lead.pk]), {}, format="json")
    aquisicao = Service.objects.get(tier=Service.Tier.QUALIFICATION_CALL)

    recusada = api.post(
        reverse("qualification-open-opportunity", args=[convertido.data["qualification"]["id"]]),
        {"title": "Não deveria abrir", "service": aquisicao.pk},
        format="json",
    )

    assert recusada.status_code == 400, recusada.data
    assert CommercialOpportunity.objects.count() == 0
