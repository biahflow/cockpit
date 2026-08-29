"""Regressão: o que a IA extrai da transcrição nasce **hipótese**, e o modelo não opina (FDD 039).

A metodologia exige que todo achado seja rotulado FATO / HIPÓTESE / DESCONHECIDO e que **nunca se
apresente hipótese como fato** (`docs/metodologia-fde.md:117`). Um modelo lendo transcrição produz
*o que foi dito* — entrevista, uma das cinco formas de evidência (`:112-115`) — e nunca observação,
artefato, sistema ou dado. Por isso a extração estruturada atribui `hypothesis` e `interview` como
constantes, e promover a fato continua sendo ato de gente, pela mesma razão que a ADR 0032 recusou
à IA gravar satisfação e a ADR 0033 manteve o registro na mão.

Desde a Fase 6 (ADR 0052) o achado é o par do split (`Evidence`/`Finding`, FDD 045) — a `Evidencia`
fundida saiu com o dual-write —, e promover exige revisor humano e evidência viva (§6.9).

O arquivo tem duas camadas porque a decisão pode ser desfeita de duas maneiras diferentes:

1. **Comportamental** — alguém passa a ler `epistemic_status`/`kind` do JSON do modelo. O sintoma é
   um achado dizendo `fact` sobre algo que ninguém observou, e a partir daí
   `process.custo_do_estado_atual` devolve `sustentacao="sustentado"` e o número entra na
   proposta que o cliente lê. Nada fica vermelho: o custo continua somando, a tela continua
   desenhando, e o que muda é só o significado.
2. **Estrutural** — alguém "melhora" o prompt pedindo ao modelo que rotule, e o coletor sobrescreve
   em seguida. O banco continuaria certo, mas a imposição teria virado sugestão: quem lesse o
   prompt depois acharia que o modelo decide, e a próxima pessoa a mexer no coletor obedeceria ao
   que o prompt promete. É por isso que a segunda camada existe apesar de a primeira passar.
"""

import ast
import inspect
import json
import re
import textwrap

import pytest
from django.test import override_settings
from django.urls import reverse
from django.utils import timezone
from rest_framework.test import APIClient

from apps.core import ai, views
from apps.core.models import Finding, Meeting, Process, User
from apps.core.tests.factories import ProjectFactory, ProjectMemberFactory, UserFactory

#: O modelo dizendo o contrário do que a casa impõe: rotulando como fato e alegando ter lido dado.
RESPOSTA_ATREVIDA = json.dumps([{
    "name": "Faturamento mensal",
    "etapas": [{"name": "Conferir notas", "tempo": "Dois dias"}],
    "achados": ["São 400 notas por mês.", "O fechamento leva dois dias."],
    "rotulo": "fato",
    "forma": "dado",
}])

#: As duas palavras, com acento e no plural, delimitadas por fronteira de palavra: `\bforma\b` não
#: casa com `formato`, e é justamente `formato=_FORMATO_JSON` que passa ao lado disto sem ser um
#: pedido de rótulo ao modelo.
PEDIDO_AO_MODELO = re.compile(r"\b(r[oó]tulos?|formas?)\b", re.IGNORECASE)


def _codigo_sem_docstring(objeto: object) -> str:
    """O corpo executável, sem a prosa que explica a decisão.

    Os docstrings **falam** de rótulo e de forma de propósito — é onde a regra está argumentada —,
    então a asserção crua acusaria justamente o texto que a defende. Mesmo movimento do
    `inspect.getsource` recortado no fim do docstring do módulo em
    `test_processo_nao_volta_ao_cliente.py`, com `ast` no lugar do corte por aspas porque aqui
    são várias funções.
    """
    modulo = ast.parse(textwrap.dedent(inspect.getsource(objeto)))  # type: ignore[arg-type]
    for no in ast.walk(modulo):
        if isinstance(no, ast.Module | ast.ClassDef | ast.FunctionDef | ast.AsyncFunctionDef):
            if ast.get_docstring(no) is not None:
                no.body = no.body[1:]
    return ast.unparse(modulo)


# --------------------------------------------------------------------------------------------
# Camada 1 — o que fica no banco.
# --------------------------------------------------------------------------------------------


@pytest.fixture
def reuniao(db: None) -> Meeting:
    project = ProjectFactory()
    return Meeting.objects.create(
        project=project, title="Discovery", date=timezone.localdate(),
        transcript="O faturamento é conferido nota a nota.",
    )


@pytest.fixture
def api(db: None, reuniao: Meeting, monkeypatch: pytest.MonkeyPatch) -> APIClient:
    delivery = UserFactory(role=User.Role.DELIVERY)
    ProjectMemberFactory(project=reuniao.project, user=delivery)
    monkeypatch.setattr(
        ai, "complete", lambda s, u, **_: (RESPOSTA_ATREVIDA, {"prompt_tokens": 1})
    )
    client = APIClient()
    client.force_authenticate(delivery)
    return client


@override_settings(AI_ENABLED=True, OPENAI_API_KEY="sk-teste")
def test_o_que_o_modelo_manda_sobre_o_achado_nao_alcanca_o_banco(
    api: APIClient, reuniao: Meeting
) -> None:
    resposta = api.post(reverse("meeting-estruturar", args=[reuniao.pk]))

    assert resposta.status_code == 200, resposta.data
    achados = list(Finding.objects.all())
    assert len(achados) == 2
    assert {a.epistemic_status for a in achados} == {Finding.EpistemicStatus.HYPOTHESIS}
    assert not Finding.objects.filter(epistemic_status=Finding.EpistemicStatus.FACT).exists()


@override_settings(AI_ENABLED=True, OPENAI_API_KEY="sk-teste")
def test_o_custo_extraido_nao_nasce_sustentado(api: APIClient, reuniao: Meeting) -> None:
    """A consequência que dá para medir: hipótese não sustenta número.

    Sem esta asserção, a primeira acima passaria mesmo que `sustentacao` viesse a ler outra coisa —
    e é `sustentacao` que decide se o custo do estado atual entra na proposta que o cliente lê
    (`ai._processo_lines`).
    """
    from apps.core import process

    api.post(reverse("meeting-estruturar", args=[reuniao.pk]))

    processo = Process.objects.get()
    assert process.custo_do_estado_atual(processo)["sustentacao"] == process.HIPOTESE


@override_settings(AI_ENABLED=True, OPENAI_API_KEY="sk-teste")
def test_promover_a_fato_continua_sendo_ato_de_gente(api: APIClient, reuniao: Meeting) -> None:
    """A metade complementar: sem ela, as duas acima passariam por ninguém conseguir gravar `fact`.

    Quem afirma tem nome — o revisor vem no corpo (§6.9), e a evidência que sustenta o fato é a
    `Evidence` que a extração já ligou ao achado. Sem revisor, é 400: promoção sem autor não vale.
    """
    revisor = UserFactory(role=User.Role.DELIVERY)
    api.post(reverse("meeting-estruturar", args=[reuniao.pk]))
    achado = Finding.objects.first()
    assert achado is not None

    # Sem revisor: a promoção não passa — o fato precisa de autor.
    sem_autor = api.patch(
        reverse("finding-detail", args=[achado.pk]),
        {"epistemic_status": Finding.EpistemicStatus.FACT},
        format="json",
    )
    assert sem_autor.status_code == 400, sem_autor.data

    resposta = api.patch(
        reverse("finding-detail", args=[achado.pk]),
        {"epistemic_status": Finding.EpistemicStatus.FACT, "reviewed_by": revisor.pk},
        format="json",
    )

    assert resposta.status_code == 200, resposta.data
    achado.refresh_from_db()
    assert achado.epistemic_status == Finding.EpistemicStatus.FACT
    assert achado.reviewed_by_id == revisor.pk


# --------------------------------------------------------------------------------------------
# Camada 2 — o que o código pede ao modelo.
# --------------------------------------------------------------------------------------------


def test_o_prompt_nao_pede_rotulo_nem_forma_ao_modelo() -> None:
    """Pedir e sobrescrever depois deixaria o banco certo e a intenção errada."""
    assert PEDIDO_AO_MODELO.search(views._PROMPT_PROCESSOS) is None


def test_o_parser_nao_le_rotulo_nem_forma_da_resposta() -> None:
    """A segunda porta: um parser que lesse as chaves as entregaria prontas a quem grava."""
    for funcao in (views.processos_do_texto, views._etapas_do_bruto, views._achados_do_bruto):
        assert PEDIDO_AO_MODELO.search(_codigo_sem_docstring(funcao)) is None, funcao.__name__


def test_o_coletor_impoe_a_classificacao_como_constante() -> None:
    """Controle positivo: o coletor **atribui** o estado e a forma, em vez de lê-los do modelo.

    É a única linha do fluxo que decide o que o achado vale, e ela o decide como constante — o
    `Finding` nasce `HYPOTHESIS` e a `Evidence` nasce `INTERVIEW`. Sem esta asserção, os dois testes
    negativos acima passariam mesmo que o coletor tivesse parado de impor coisa nenhuma.
    """
    coletor = _codigo_sem_docstring(views.MeetingViewSet.estruturar)

    assert "Finding.EpistemicStatus.HYPOTHESIS" in coletor
    assert "Evidence.Kind.INTERVIEW" in coletor
