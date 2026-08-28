"""Regressão: o split entra ao lado do legado, e o custo do estado atual continua idêntico (FDD 045).

`processos.custo_do_estado_atual` decide se o número mais persuasivo de um Discovery entra na
proposta que o cliente lê (`ai._processo_lines`, FDD 039), e ele decide isso perguntando por
`Evidencia` viva com `rotulo=fato`. A fatia do split **não** troca essa fonte: o dual-write existe
justamente para que a tela `ProcessoDetailPage` e essa conta continuem funcionando sem tocar em
nada enquanto o modelo novo cresce ao lado.

Duas coisas quebrariam em silêncio se ninguém as afirmasse aqui:

1. **A gravação legada some da extração.** Alguém "termina" a migração desligando a `Evidencia` no
   coletor. O custo passa a nunca ser sustentado, `test_hipotese_nao_sustenta_numero.py` continua
   verde (ele nunca sustenta o número, e passar a nunca sustentar é o que ele afirma quando não há
   fato) e a proposta perde o argumento sem que nada fique vermelho.
2. **A fonte da sustentação muda cedo demais.** Alguém aponta o cálculo para `Finding` antes de a
   base estar convertida, e o número desaparece para todo cliente cujo Discovery é anterior ao
   split. O teste abaixo trava a fonte no lugar: promover o `Finding` **não** move o custo; quem o
   move ainda é a `Evidencia`. No dia em que a troca for deliberada, este é o teste que precisa
   mudar junto — e é essa a diferença entre uma migração e um acidente.
"""

import json
from decimal import Decimal

import pytest
from django.test import override_settings
from django.urls import reverse
from django.utils import timezone
from rest_framework.test import APIClient

from apps.core import ai, processos
from apps.core.models import Evidence, Evidencia, Finding, Meeting, Processo, User
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
def test_a_extracao_grava_os_dois_lados(api: APIClient, reuniao: Meeting) -> None:
    resposta = api.post(reverse("meeting-estruturar", args=[reuniao.pk]))

    assert resposta.status_code == 200, resposta.data
    assert Evidencia.objects.count() == 1
    assert Finding.objects.count() == 1
    assert Evidence.objects.count() == 1
    # A resposta do coletor não mudou de forma — nenhuma tela precisou mudar, e nada do modelo
    # novo atravessou para o corpo.
    assert [p["name"] for p in resposta.data["processos"]] == ["Faturamento mensal"]
    assert not {"findings", "evidence"} & set(resposta.data)


@override_settings(AI_ENABLED=True, OPENAI_API_KEY="sk-teste")
def test_quem_sustenta_o_custo_continua_sendo_a_evidencia_legada(
    api: APIClient, reuniao: Meeting
) -> None:
    api.post(reverse("meeting-estruturar", args=[reuniao.pk]))
    processo = Processo.objects.get()
    Processo.objects.filter(pk=processo.pk).update(**NUCLEO)
    processo.refresh_from_db()
    revisor = UserFactory()

    antes = processos.custo_do_estado_atual(processo)
    assert antes["sustentacao"] == processos.HIPOTESE
    assert antes["total"] == Decimal("20000.00")

    # Promover o **achado novo** não move o cálculo: ele ainda lê o legado, e é isso que o
    # dual-write garante enquanto a conversão não termina.
    achado = Finding.objects.get()
    achado.reviewed_by = revisor
    achado.epistemic_status = Finding.EpistemicStatus.FACT
    achado.save()
    assert processos.custo_do_estado_atual(processo)["sustentacao"] == processos.HIPOTESE

    # Promover a **evidência legada** move — a conta continua exatamente onde estava.
    legada = Evidencia.objects.get()
    legada.rotulo = Evidencia.Rotulo.FATO
    legada.save(update_fields=["rotulo", "updated_at"])
    depois = processos.custo_do_estado_atual(processo)
    assert depois["sustentacao"] == processos.SUSTENTADO
    assert depois["total"] == antes["total"]
    assert depois["parcelas"] == antes["parcelas"]
