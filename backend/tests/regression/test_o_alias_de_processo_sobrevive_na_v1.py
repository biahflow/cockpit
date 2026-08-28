"""Regressão: as chaves `processo` e `etapa` continuam na `/api/v1/`, na leitura, na escrita e no
filtro — e as duas rotas continuam onde estavam.

A fatia 4 da issue #67 renomeou `Processo`/`ProcessoEtapa` para `Process`/`ProcessStep` e, com
elas, os três campos que apontavam para os dois (ADR 0052). O que a ADR **não** antecipou é a
chave de payload: rota e chave morrem na `/api/v2/`, não antes, porque um consumidor da v1 não tem
como saber que o nome mudou (`docs/ontology/aliases.md` §2c).

Sem este teste os aliases são linhas de serializer sem chamador dentro do repositório — a SPA já
escreve e lê `process`/`step` —, e a próxima pessoa que varrer `processo` atrás do último resquício
do nome antigo vai removê-las achando que está pagando dívida. Estaria quebrando a `/api/v1/` em
silêncio: nada aqui dentro ficaria vermelho, e o erro apareceria no consumidor de fora.

A **escrita** é o que nenhum outro teste cobre. `AliasDeEntradaMixin` normaliza a chave legada
antes da validação, e o empate resolve pela canônica — mesma regra de `apply-gate` desde a fatia 1
da issue.

O **query param** entra pelo mesmo argumento e por um motivo a mais: em `QueryParamFilterMixin` o
nome do param **é** o caminho do ORM, então `?processo=` não ficaria "sem efeito" depois do renome
— estouraria `FieldError`.

A **rota** fecha a lista porque foi ela que obrigou a declarar `basename` explícito: derivado do
queryset, ele passaria a ser `process`/`processstep`, e todo `reverse("processo-…")` do
repositório quebraria junto com o link de quem integrou de fora.
"""

from __future__ import annotations

import pytest
from django.urls import reverse
from rest_framework.test import APIClient

from apps.core.models import Evidencia, ProcessStep, User
from apps.core.tests.factories import (
    EvidenciaFactory,
    ProcessFactory,
    ProcessStepFactory,
    UserFactory,
)


@pytest.fixture
def admin_client() -> APIClient:
    client = APIClient()
    client.force_authenticate(UserFactory(role=User.Role.ADMIN))
    return client


def _payload_evidencia(**overrides: object) -> dict:
    corpo: dict = {
        "forma": Evidencia.Forma.OBSERVACAO,
        "rotulo": Evidencia.Rotulo.FATO,
        "content": "Vi a analista conferindo pedido a pedido na planilha.",
    }
    corpo.update(overrides)
    return corpo


@pytest.mark.django_db
def test_a_etapa_devolve_as_duas_chaves_com_o_mesmo_valor(admin_client: APIClient) -> None:
    """`GET /processo-etapas/` sai com `process` (canônica) **e** `processo`."""
    etapa = ProcessStepFactory()

    resposta = admin_client.get(reverse("processoetapa-list"))

    assert resposta.status_code == 200
    linha = next(item for item in resposta.data if item["id"] == etapa.pk)
    assert linha["process"] == etapa.process_id
    assert linha["processo"] == etapa.process_id


@pytest.mark.django_db
def test_a_etapa_aceita_a_chave_antiga_no_corpo(admin_client: APIClient) -> None:
    """O alias de **escrita**: quem integrou com a v1 continua mandando `processo`."""
    processo = ProcessFactory()

    resposta = admin_client.post(
        reverse("processoetapa-list"),
        {"processo": processo.pk, "name": "Conferência da nota"},
        format="json",
    )

    assert resposta.status_code == 201, resposta.data
    assert ProcessStep.objects.get(pk=resposta.data["id"]).process_id == processo.pk


@pytest.mark.django_db
def test_com_as_duas_chaves_no_corpo_a_canonica_vence(admin_client: APIClient) -> None:
    """Corpo com as duas é confusão do chamador; resolver pela nova não trava quem já migrou."""
    canonico = ProcessFactory()
    legado = ProcessFactory()

    resposta = admin_client.post(
        reverse("processoetapa-list"),
        {"process": canonico.pk, "processo": legado.pk, "name": "Conferência da nota"},
        format="json",
    )

    assert resposta.status_code == 201, resposta.data
    assert ProcessStep.objects.get(pk=resposta.data["id"]).process_id == canonico.pk


@pytest.mark.django_db
def test_a_evidencia_carrega_os_dois_pares(admin_client: APIClient) -> None:
    """A classe legada não foi renomeada, mas os **campos** dela sim — e os dois pares saem.

    `Evidencia` é o único dos quatro nomes em português que não entrou na #67: a Fase 3 já a
    dividiu em `Evidence` + `Finding`, e quem a remove é a Fase 6, junto com o dual-write.
    """
    etapa = ProcessStepFactory()
    evidencia = EvidenciaFactory(process=etapa.process, step=etapa)

    resposta = admin_client.get(reverse("evidencia-detail", args=[evidencia.pk]))

    assert resposta.status_code == 200
    assert resposta.data["process"] == etapa.process_id
    assert resposta.data["processo"] == etapa.process_id
    assert resposta.data["step"] == etapa.pk
    assert resposta.data["etapa"] == etapa.pk


@pytest.mark.django_db
def test_a_evidencia_aceita_as_duas_chaves_antigas_no_corpo(admin_client: APIClient) -> None:
    etapa = ProcessStepFactory()

    resposta = admin_client.post(
        reverse("evidencia-list"),
        _payload_evidencia(processo=etapa.process_id, etapa=etapa.pk),
        format="json",
    )

    assert resposta.status_code == 201, resposta.data
    gravada = Evidencia.objects.get(pk=resposta.data["id"])
    assert gravada.process_id == etapa.process_id
    assert gravada.step_id == etapa.pk


@pytest.mark.django_db
def test_o_query_param_antigo_continua_filtrando(admin_client: APIClient) -> None:
    """`?processo=` filtra igual a `?process=` — e não estoura `FieldError`."""
    processo = ProcessFactory()
    etapa = ProcessStepFactory(process=processo)
    ProcessStepFactory()
    da_etapa = EvidenciaFactory(process=processo)
    EvidenciaFactory()

    legado = admin_client.get(reverse("processoetapa-list"), {"processo": processo.pk})
    canonico = admin_client.get(reverse("processoetapa-list"), {"process": processo.pk})
    achados_legado = admin_client.get(reverse("evidencia-list"), {"processo": processo.pk})

    assert legado.status_code == 200
    assert {item["id"] for item in legado.data} == {etapa.pk}
    assert {item["id"] for item in canonico.data} == {etapa.pk}
    assert {item["id"] for item in achados_legado.data} == {da_etapa.pk}


@pytest.mark.django_db
def test_as_rotas_e_os_basenames_nao_mudaram() -> None:
    """`/api/v1/processos/` e `reverse("processo-…")` sobrevivem ao renome da classe.

    Os dois `basename` viraram explícitos em `urls.py` justamente por isto: derivados do queryset
    eles passariam a ser `process` e `processstep`.
    """
    assert reverse("processo-list") == "/api/v1/processos/"
    assert reverse("processo-detail", args=[7]) == "/api/v1/processos/7/"
    assert reverse("processoetapa-list") == "/api/v1/processo-etapas/"
    assert reverse("processoetapa-detail", args=[7]) == "/api/v1/processo-etapas/7/"

    api = APIClient()
    api.force_authenticate(UserFactory(role=User.Role.ADMIN))
    assert api.get(reverse("processo-list")).status_code == 200
    assert api.get(reverse("processoetapa-list")).status_code == 200
