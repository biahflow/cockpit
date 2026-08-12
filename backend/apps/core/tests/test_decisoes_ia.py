"""A extração de decisões a partir da transcrição (FDD 032).

O que dá para exercitar sem chamar o provedor é o **parser** — e é onde os defeitos moram. A
chamada ao modelo fica atrás de `# pragma: no cover` (`ai.py`), como todo caminho de IA aqui.
"""

import json

import pytest
from django.test import override_settings
from django.urls import reverse
from django.utils import timezone
from rest_framework.test import APIClient

from apps.core import ai, portal
from apps.core.models import Decisao, Meeting, User
from apps.core.views import decisoes_do_texto

from .factories import ProjectFactory, ProjectMemberFactory, UserFactory


def test_a_clean_json_array_is_read() -> None:
    texto = '[{"title": "Adotar fila gerenciada", "rationale": "Custa menos.", "decided_by": "Ana"}]'
    assert decisoes_do_texto(texto) == [
        {"title": "Adotar fila gerenciada", "rationale": "Custa menos.", "decided_by": "Ana"}
    ]


def test_prose_and_markdown_fences_around_the_array_are_cut() -> None:
    """A falha típica do modelo não é JSON inválido — é JSON válido dentro de prosa.

    Instruir "devolva APENAS o array" reduz, não elimina. Recortar do primeiro `[` ao último `]`
    cobre prosa antes, cerca de markdown e prosa depois com uma regra só.
    """
    texto = (
        "Claro! Aqui estão as decisões que identifiquei:\n\n```json\n"
        '[{"title": "Adotar fila gerenciada"}]\n```\n\nPosso detalhar alguma delas?'
    )
    assert decisoes_do_texto(texto) == [
        {"title": "Adotar fila gerenciada", "rationale": "", "decided_by": ""}
    ]


def test_a_malformed_item_is_dropped_and_the_others_survive() -> None:
    """Perder o quinto item não é razão para perder os outros seis."""
    texto = (
        '[{"title": "Primeira"}, {"title": "   "}, "isto não é objeto", '
        '{"rationale": "sem título"}, {"title": "Última"}]'
    )
    assert [d["title"] for d in decisoes_do_texto(texto)] == ["Primeira", "Última"]


def test_no_array_at_all_yields_nothing() -> None:
    """Sem lista não houve extração — e quem chama responde 502 em vez de gravar zero em silêncio."""
    assert decisoes_do_texto("Não consegui identificar decisões nesta transcrição.") == []
    assert decisoes_do_texto("") == []
    assert decisoes_do_texto("[isto não fecha") == []
    assert decisoes_do_texto('{"title": "um objeto, não uma lista"}') == []


def test_the_model_cannot_overflow_the_columns() -> None:
    """`title` é `CharField(255)` e `decided_by` é `CharField(160)`.

    O modelo não tem como saber disso, e um título de 4.000 caracteres viraria `DataError` no meio
    do `bulk_create` — derrubando a extração inteira por um item.
    """
    texto = json.dumps([{"title": "t" * 4000, "decided_by": "d" * 400}])
    (decisao,) = decisoes_do_texto(texto)
    assert len(decisao["title"]) == 255
    assert len(decisao["decided_by"]) == 160


@pytest.mark.django_db
def test_a_meeting_without_a_transcript_is_refused_before_any_ai_call() -> None:
    """Mesma recusa do `discovery`, e pelo mesmo motivo: sem insumo não há o que extrair."""
    delivery = UserFactory(role=User.Role.DELIVERY)
    project = ProjectFactory()
    ProjectMemberFactory(project=project, user=delivery)
    meeting = Meeting.objects.create(
        project=project, title="Comitê", date=timezone.localdate(), transcript="   "
    )
    client = APIClient()
    client.force_authenticate(delivery)

    resp = client.post(reverse("meeting-extrair-decisoes", args=[meeting.pk]))

    assert resp.status_code == 400
    assert Decisao.objects.count() == 0


def _reuniao_com_ata(delivery):  # type: ignore[no-untyped-def]
    project = ProjectFactory()
    ProjectMemberFactory(project=project, user=delivery)
    meeting = Meeting.objects.create(
        project=project, title="Comitê", date=timezone.localdate(),
        transcript="Decidimos adotar a fila gerenciada.",
    )
    return project, meeting


@pytest.mark.django_db
@override_settings(AI_ENABLED=True, OPENAI_API_KEY="sk-teste")
def test_the_extraction_writes_drafts_linked_to_the_meeting(monkeypatch: pytest.MonkeyPatch) -> None:
    """Rascunho e proveniência, que são as duas propriedades que fazem a IA caber aqui."""
    delivery = UserFactory(role=User.Role.DELIVERY)
    project, meeting = _reuniao_com_ata(delivery)
    monkeypatch.setattr(
        ai, "complete",
        lambda s, u, **_: (
            '[{"title": "Adotar fila gerenciada", "rationale": "Custa menos.",'
            ' "decided_by": "Marina"}, {"title": "Adiar o piloto"}]',
            {"prompt_tokens": 5, "completion_tokens": 3},
        ),
    )
    client = APIClient()
    client.force_authenticate(delivery)

    resp = client.post(reverse("meeting-extrair-decisoes", args=[meeting.pk]))

    assert resp.status_code == 200
    assert [d["title"] for d in resp.json()["decisoes"]] == [
        "Adotar fila gerenciada", "Adiar o piloto"
    ]
    gravadas = Decisao.objects.filter(project=project)
    assert gravadas.count() == 2
    assert all(d.status == Decisao.Status.DRAFT for d in gravadas)
    assert all(d.source_meeting_id == meeting.pk for d in gravadas)
    # E nada disso alcança o cliente enquanto for rascunho.
    assert portal.build_snapshot(project)["decisions"] == []


@pytest.mark.django_db
@override_settings(AI_ENABLED=True, OPENAI_API_KEY="sk-teste")
def test_the_prompt_does_not_carry_the_plain_text_instruction(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """`_TEXTO_CORRIDO` manda o modelo não usar crase; pedir JSON logo depois se contradiz.

    O motivo daquela instrução é real — o destino de quase todo texto gerado aqui é um `<textarea>`
    —, então ela não sai: o que muda é o formato desta chamada. Sem esta asserção, alguém a
    reintroduz sem nada ficar vermelho, e o sintoma aparece longe, num parse que falha.
    """
    delivery = UserFactory(role=User.Role.DELIVERY)
    _, meeting = _reuniao_com_ata(delivery)
    visto: dict[str, str] = {}

    def espia(system: str, user: str, **_):  # type: ignore[no-untyped-def]
        visto["system"] = system
        return '[{"title": "Adotar fila gerenciada"}]', {"prompt_tokens": 1, "completion_tokens": 1}

    monkeypatch.setattr(ai, "complete", espia)
    client = APIClient()
    client.force_authenticate(delivery)
    client.post(reverse("meeting-extrair-decisoes", args=[meeting.pk]))

    assert "Markdown" not in visto["system"]
    assert "array JSON" in visto["system"]


@pytest.mark.django_db
@override_settings(AI_ENABLED=True, OPENAI_API_KEY="sk-teste")
def test_an_unusable_answer_writes_nothing_and_says_so(monkeypatch: pytest.MonkeyPatch) -> None:
    """502 e zero linhas — a alternativa seria gravar zero decisões e responder 200.

    O `atomic` em volta é o que garante o "zero": sem ele, um `bulk_create` que falhasse no meio
    deixaria rascunhos órfãos de uma extração que a pessoa viu falhar.
    """
    delivery = UserFactory(role=User.Role.DELIVERY)
    _, meeting = _reuniao_com_ata(delivery)
    monkeypatch.setattr(
        ai, "complete",
        lambda s, u, **_: ("Desculpe, não identifiquei decisões.", {"prompt_tokens": 1, "completion_tokens": 1}),
    )
    client = APIClient()
    client.force_authenticate(delivery)

    resp = client.post(reverse("meeting-extrair-decisoes", args=[meeting.pk]))

    assert resp.status_code == 502
    assert Decisao.objects.count() == 0


@pytest.mark.django_db
def test_sales_cannot_extract_decisions() -> None:
    """A action herda o `resource = "meeting"` do viewset, e o caso trava isso."""
    sales = UserFactory(role=User.Role.SALES)
    project = ProjectFactory()
    meeting = Meeting.objects.create(
        project=project, title="Comitê", date=timezone.localdate(), transcript="ata"
    )
    client = APIClient()
    client.force_authenticate(sales)

    assert client.post(reverse("meeting-extrair-decisoes", args=[meeting.pk])).status_code == 403
