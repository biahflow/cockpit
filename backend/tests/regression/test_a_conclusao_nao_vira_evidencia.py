"""Regressão: a extração escreve o achado em `Finding`, e a `Evidence` fica só com a fonte (FDD 045).

O defeito que o split existe para desfazer é a fusão: na `Evidencia` da FDD 039, o que foi dito e
o que a casa concluiu do que foi dito são **a mesma linha**. Quem edita o texto para "melhorar a
redação do achado" está editando, sem saber, a prova que o sustenta.

A extração por IA é onde o defeito voltaria mais fácil, porque ali só existe um texto: o achado que
o modelo devolveu. Copiar esse texto para `Evidence.raw_excerpt` seria a coisa mais natural do
mundo, e refaria a fusão em uma linha — sem nada ficar vermelho, porque o campo aceita qualquer
string. O que impede é a decisão de que a `Evidence` da extração carrega **o localizador da
reunião** e nada mais: o modelo não devolve o trecho que gerou o achado, e inventar um seria
afirmar que alguém disse aquilo com aquelas palavras.

A segunda metade é a invariante §6.8 do language map, agora do lado novo: `Finding` criado por
extração nasce `hypothesis`. A regra já é guardada para a `Evidencia` legada em
`test_a_extracao_nasce_hipotese.py`; sem esta cópia, o dia em que o produto passar a ler o
`Finding` traria a regra de volta a zero.
"""

import json

import pytest
from django.test import override_settings
from django.urls import reverse
from django.utils import timezone
from rest_framework.test import APIClient

from apps.core import ai
from apps.core.models import Evidence, Evidencia, Finding, Meeting, User
from apps.core.tests.factories import ProjectFactory, ProjectMemberFactory, UserFactory

#: O modelo dizendo o contrário do que a casa impõe, como no teste irmão da FDD 039.
RESPOSTA = json.dumps([{
    "name": "Faturamento mensal",
    "etapas": [{"name": "Conferir notas", "tempo": "Dois dias"}],
    "achados": ["São 400 notas por mês.", "O fechamento leva dois dias."],
    "rotulo": "fato",
    "epistemic_status": "fact",
}])

ACHADOS = ["São 400 notas por mês.", "O fechamento leva dois dias."]


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
def test_o_achado_vai_para_o_finding_e_nao_para_a_evidencia(
    api: APIClient, reuniao: Meeting
) -> None:
    resposta = api.post(reverse("meeting-estruturar", args=[reuniao.pk]))

    assert resposta.status_code == 200, resposta.data
    assert sorted(Finding.objects.values_list("statement", flat=True)) == sorted(ACHADOS)
    # Uma `Evidence` por processo: ela diz **de onde** os achados vieram, não o que eles afirmam.
    evidencia = Evidence.objects.get()
    assert evidencia.raw_excerpt == ""
    assert evidencia.content_hash == ""
    for achado in ACHADOS:
        assert achado not in evidencia.reference
    assert str(reuniao.pk) in evidencia.reference


@override_settings(AI_ENABLED=True, OPENAI_API_KEY="sk-teste")
def test_o_finding_extraido_nasce_hipotese_e_ligado_a_evidencia(
    api: APIClient, reuniao: Meeting
) -> None:
    api.post(reverse("meeting-estruturar", args=[reuniao.pk]))

    achados = list(Finding.objects.prefetch_related("evidences"))
    assert len(achados) == 2
    assert {a.epistemic_status for a in achados} == {Finding.EpistemicStatus.HYPOTHESIS}
    assert not Finding.objects.filter(epistemic_status=Finding.EpistemicStatus.FACT).exists()
    assert all(a.reviewed_by_id is None and a.reviewed_at is None for a in achados)
    # A ponte entre as duas metades: sem ela o achado extraído seria uma afirmação sem fonte.
    evidencia = Evidence.objects.get()
    assert all(list(a.evidences.all()) == [evidencia] for a in achados)
    assert evidencia.kind == Evidence.Kind.INTERVIEW
    assert evidencia.source_meeting_id == reuniao.pk


@override_settings(AI_ENABLED=True, OPENAI_API_KEY="sk-teste")
def test_o_par_novo_aponta_para_a_linha_legada_de_onde_saiu(
    api: APIClient, reuniao: Meeting
) -> None:
    """`legacy_evidencia` é o que permite descontinuar o legado depois sem perder o vínculo."""
    api.post(reverse("meeting-estruturar", args=[reuniao.pk]))

    legadas = {e.pk: e.content for e in Evidencia.objects.all()}
    assert len(legadas) == 2
    for achado in Finding.objects.all():
        assert achado.legacy_evidencia_id in legadas
        assert legadas[achado.legacy_evidencia_id] == achado.statement
