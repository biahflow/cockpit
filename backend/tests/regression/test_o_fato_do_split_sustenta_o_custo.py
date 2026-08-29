"""Regressão: a extração grava só o split, e é o `Finding` fato que sustenta o custo (Fase 6).

`process.custo_do_estado_atual` decide se o número mais persuasivo de um Discovery entra na
proposta que o cliente lê (`ai._processo_lines`, FDD 039), e ele decide isso perguntando por um
achado vivo com `fato` por trás. Até a Fase 6 (ADR 0052) esse achado era a `Evidencia` fundida, e a
extração gravava as duas formas (dual-write). Com o legado removido, sobra o par do split (FDD 045)
e a fonte da sustentação passou a ser o `Finding(epistemic_status=fact)`.

Duas coisas quebrariam em silêncio se ninguém as afirmasse aqui:

1. **A extração volta a gravar o legado.** Alguém ressuscita a `Evidencia` no coletor, e o produto
   passa a manter duas verdades do mesmo achado — a que a última gravação vence. O teste abaixo
   trava a extração no split: uma `Evidence` e um `Finding`, e nada mais.
2. **A sustentação para de seguir o `Finding`.** Alguém reponta o cálculo para outro lugar, e
   promover o achado deixa de mover o número que a proposta usa. O teste abaixo trava a fonte: o
   custo é `hipotese` na extração e vira `sustentado` quando o `Finding` é promovido a fato — que é
   o mesmo achado que a tela `ProcessDetailPage` promove.
"""

import json
from decimal import Decimal

import pytest
from django.test import override_settings
from django.urls import reverse
from django.utils import timezone
from rest_framework.test import APIClient

from apps.core import ai, process
from apps.core.models import Evidence, Finding, Meeting, Process, User
from apps.core.tests.factories import ProjectFactory, ProjectMemberFactory, UserFactory

RESPOSTA = json.dumps([{
    "name": "Faturamento mensal",
    "etapas": [{"name": "Conferir notas"}],
    "achados": ["São 400 notas por mês."],
}])

#: 0,5 h × 400 ocorrências × 2 pessoas × R$ 50,00 = R$ 20.000,00 por mês.
NUCLEO = {
    "volume_mes": 400,
    "tempo_horas": Decimal("0.50"),
    "pessoas": 2,
    "custo_hora": Decimal("50.00"),
}


@pytest.fixture
def reuniao(db: None) -> Meeting:
    return Meeting.objects.create(
        project=ProjectFactory(), title="Discovery", date=timezone.localdate(),
        transcript="O faturamento é conferido nota a nota.",
    )


@pytest.fixture
def api(db: None, reuniao: Meeting, monkeypatch: pytest.MonkeyPatch) -> APIClient:
    entrega = UserFactory(role=User.Role.DELIVERY)
    ProjectMemberFactory(project=reuniao.project, user=entrega)
    monkeypatch.setattr(ai, "complete", lambda s, u, **_: (RESPOSTA, {"prompt_tokens": 1}))
    client = APIClient()
    client.force_authenticate(entrega)
    return client


@override_settings(AI_ENABLED=True, OPENAI_API_KEY="sk-teste")
def test_a_extracao_grava_so_o_split(api: APIClient, reuniao: Meeting) -> None:
    resposta = api.post(reverse("meeting-estruturar", args=[reuniao.pk]))

    assert resposta.status_code == 200, resposta.data
    # Uma `Evidence` (de onde veio) e um `Finding` (o que afirma) — e nenhuma linha legada.
    assert Evidence.objects.count() == 1
    assert Finding.objects.count() == 1
    # A resposta do coletor não mudou de forma — nenhuma tela precisou mudar, e nada do modelo
    # do split atravessou para o corpo.
    assert [p["name"] for p in resposta.data["processos"]] == ["Faturamento mensal"]
    assert not {"findings", "evidence"} & set(resposta.data)


@override_settings(AI_ENABLED=True, OPENAI_API_KEY="sk-teste")
def test_promover_o_finding_a_fato_sustenta_o_custo(api: APIClient, reuniao: Meeting) -> None:
    api.post(reverse("meeting-estruturar", args=[reuniao.pk]))
    processo = Process.objects.get()
    Process.objects.filter(pk=processo.pk).update(**NUCLEO)
    processo.refresh_from_db()
    revisor = UserFactory()

    antes = process.custo_do_estado_atual(processo)
    assert antes["sustentacao"] == process.HIPOTESE
    assert antes["total"] == Decimal("20000.00")

    # Promover o achado do split move o cálculo: é o mesmo `Finding` que a tela promove e que o
    # custo consulta desde a Fase 6.
    achado = Finding.objects.get()
    achado.reviewed_by = revisor
    achado.epistemic_status = Finding.EpistemicStatus.FACT
    achado.save()

    depois = process.custo_do_estado_atual(processo)
    assert depois["sustentacao"] == process.SUSTENTADO
    # O número não muda ao ser sustentado — a conta é dos nove insumos, não do rótulo do achado.
    assert depois["total"] == antes["total"]
    assert depois["parcelas"] == antes["parcelas"]
