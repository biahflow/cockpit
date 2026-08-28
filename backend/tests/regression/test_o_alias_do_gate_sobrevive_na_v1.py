"""Regressão: a chave `gate_outcome` continua na `/api/v1/`, e a action ainda aceita `outcome`.

A decisão D7 do `docs/ontology/language-map.md` renomeou `GateOutcome` para `GateDecision`, e a
ADR 0052 antecipou o renome de campo — `gate_outcome` virou `gate_decision` no modelo, no
serializer e no tipo TS. O que a ADR **não** antecipou é a chave de payload: rota e chave morrem
na `/api/v2/`, não antes, porque um consumidor da v1 não tem como saber que o nome mudou.

Sem este teste o alias é uma linha de serializer sem chamador dentro do repositório — a SPA já lê
só `gate_decision` —, e a próxima pessoa que varrer `gate_outcome` atrás do último resquício do
nome antigo vai remover a chave achando que está pagando dívida. Estaria quebrando a `/api/v1/`
em silêncio: nada aqui dentro ficaria vermelho, e o erro apareceria no consumidor de fora.

O mesmo vale para a escrita. `apply-gate` passou a ler `decision`; quem já integrou manda
`outcome`, e o corpo antigo tem de continuar valendo até a v2.
"""

from __future__ import annotations

import pytest
from django.urls import reverse
from rest_framework.test import APIClient

from apps.core import journey
from apps.core.models import JourneyPhase, PhaseEvent, ProjectPhase, User
from apps.core.tests.factories import ProjectFactory, UserFactory


@pytest.fixture
def admin_client() -> APIClient:
    client = APIClient()
    client.force_authenticate(UserFactory(role=User.Role.ADMIN))
    return client


def _fase_ativa_com_gate(project) -> ProjectPhase:  # type: ignore[no-untyped-def]
    journey.materialize_journey(project)
    ativa = ProjectPhase.objects.filter(
        project=project, status=ProjectPhase.Status.ACTIVE
    ).first()
    assert ativa is not None
    JourneyPhase.objects.filter(pk=ativa.phase_id).update(requires_gate=True)
    ativa.refresh_from_db()
    return ativa


@pytest.mark.django_db
def test_a_fase_devolve_as_duas_chaves_com_o_mesmo_valor(admin_client: APIClient) -> None:
    """`GET /project-phases/` sai com `gate_decision` (canônica) **e** `gate_outcome` (alias)."""
    project = ProjectFactory()
    fase = _fase_ativa_com_gate(project)
    fase.gate_decision = ProjectPhase.GateDecision.CONDITIONAL_GO
    fase.save(update_fields=["gate_decision"])

    resposta = admin_client.get(reverse("projectphase-list"))

    assert resposta.status_code == 200
    linha = next(item for item in resposta.data if item["id"] == fase.pk)
    assert linha["gate_decision"] == "conditional_go"
    assert linha["gate_outcome"] == "conditional_go"


@pytest.mark.django_db
def test_o_historico_devolve_as_duas_chaves_com_o_mesmo_valor(admin_client: APIClient) -> None:
    """O `PhaseEvent` carrega o mesmo par: a linha do tempo é lida pelo mesmo consumidor."""
    project = ProjectFactory()
    _fase_ativa_com_gate(project)
    journey.apply_gate(project, ProjectPhase.GateDecision.NO_GO, "risco alto")
    evento = PhaseEvent.objects.filter(
        project=project, kind=PhaseEvent.Kind.GATE_RECORDED
    ).first()
    assert evento is not None

    resposta = admin_client.get(reverse("project-timeline", args=[project.pk]))

    assert resposta.status_code == 200
    linha = next(item for item in resposta.data["events"] if item["id"] == evento.pk)
    assert linha["gate_decision"] == "no_go"
    assert linha["gate_outcome"] == "no_go"


@pytest.mark.django_db
def test_apply_gate_aceita_a_chave_nova_e_a_antiga(admin_client: APIClient) -> None:
    """As duas chaves de corpo gravam a mesma decisão — `outcome` até a `/api/v2/`."""
    for chave in ("decision", "outcome"):
        project = ProjectFactory()
        fase = _fase_ativa_com_gate(project)

        resposta = admin_client.post(
            reverse("project-apply-gate", args=[project.pk]),
            {chave: "no_go", "notes": f"corpo com `{chave}`"},
            format="json",
        )

        assert resposta.status_code == 200, chave
        fase.refresh_from_db()
        assert fase.gate_decision == "no_go", chave
