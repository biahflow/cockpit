"""Regressão: `kpi_baseline` e `kpi_current` continuam saindo na `/api/v1/` (ADR 0055).

A decisão **C1** do DAP `docs/design/dap-prove-e-valor-r1/` tirou as duas medições de dentro do
ativo de solução: elas eram colunas de `DigitalEmployee` e passaram a ser `Measurement` de um
`KPI`. O que **não** saiu foi o contrato — a `/api/v1/` prometeu as duas chaves, e chave de payload
morre na `/api/v2/`, não antes (ADR 0052). Elas continuam no `GET`, agora derivadas.

Este arquivo existe pelo motivo que a `docs/ontology/aliases.md` §2c dá para os aliases de escrita:
sem ele, as duas linhas do `DigitalEmployeeSerializer` não têm chamador **dentro** do repositório —
a SPA lê o campo, o backend não —, e a próxima varredura atrás de campo morto as remove achando que
paga dívida. Estaria quebrando a `/api/v1/` no único lugar onde nada aqui dentro fica vermelho.

A outra metade — que a **escrita** por essas chaves parou de funcionar, deliberadamente — está em
`apps/core/tests/test_prove_e_valor.py`. Aqui só a leitura, que é o que o contrato promete.
"""

from datetime import timedelta
from decimal import Decimal

import pytest
from django.urls import reverse
from django.utils import timezone
from rest_framework.test import APIClient

from apps.core.models import KPI, DigitalEmployee, KpiUnit, Measurement, User
from apps.core.tests.factories import ProjectFactory, UserFactory, digital_employee_medido

pytestmark = pytest.mark.django_db


@pytest.fixture
def api() -> APIClient:
    client = APIClient()
    client.force_authenticate(UserFactory(role=User.Role.ADMIN))
    return client


def test_as_duas_chaves_continuam_na_listagem_com_o_valor_da_medicao(api: APIClient) -> None:
    projeto = ProjectFactory()
    digital_employee_medido(
        projeto, baseline=Decimal("12.00"), current=Decimal("48.00"),
        name="SDR", kpi_label="Leads/mês", kpi_unit=KpiUnit.COUNT,
    )

    linha = api.get(f"{reverse('digitalemployee-list')}?project={projeto.pk}").data[0]

    assert linha["kpi_baseline"] == "12.00"
    assert linha["kpi_current"] == "48.00"


def test_a_lacuna_sai_nula_e_nunca_zero(api: APIClient) -> None:
    """O ativo sem baseline diz `null`, que é o `—` do desenho. Zero inventaria o "antes"."""
    projeto = ProjectFactory()
    digital_employee_medido(projeto, baseline=None, current=Decimal("30.00"), name="Cobrador")

    linha = api.get(f"{reverse('digitalemployee-list')}?project={projeto.pk}").data[0]

    assert linha["kpi_baseline"] is None
    assert linha["kpi_current"] == "30.00"


def test_a_medicao_arquivada_deixa_de_alimentar_o_par(api: APIClient) -> None:
    """A exclusão lógica da FDD 025 vale para a medição como vale para tudo o mais."""
    projeto = ProjectFactory()
    ativo = digital_employee_medido(projeto, baseline=Decimal("12.00"), name="SDR")
    ativo.kpi.measurements.get(kind=Measurement.Kind.BASELINE).archive()

    linha = api.get(reverse("digitalemployee-detail", args=[ativo.pk])).data

    assert linha["kpi_baseline"] is None


def test_o_par_acompanha_o_kpi_e_nao_o_ativo(api: APIClient) -> None:
    """O que a extração comprou: o KPI sobrevive à troca do ativo que o mede (ADR 0055)."""
    projeto = ProjectFactory()
    kpi = KPI.objects.create(project=projeto, name="Tempo de resposta", unit=KpiUnit.HOURS)
    agora = timezone.now()
    hoje = timezone.localdate()
    Measurement.objects.create(
        kpi=kpi, kind=Measurement.Kind.BASELINE, value=Decimal("4.20"),
        period_start=hoje - timedelta(days=30), period_end=hoje, measured_at=agora,
    )
    antigo = DigitalEmployee.objects.create(project=projeto, name="SDR v1", kpi=kpi)
    novo = DigitalEmployee.objects.create(project=projeto, name="SDR v2", kpi=kpi)
    antigo.archive()

    linha = api.get(reverse("digitalemployee-detail", args=[novo.pk])).data

    assert linha["kpi_baseline"] == "4.20"
