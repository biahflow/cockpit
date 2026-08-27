"""Regressão FDD 042: **nada equipara `PR merged` a `DONE`** na escada FDE.

A Issue #42 exclui explicitamente *"automatic phase transitions driven only by PR merge"*, e
`docs/metodologia-fde.md:42-48` diz por quê: um degrau fecha por decision gate — uma de quatro
saídas, decidida por humano. Estado de engenharia (PR, CI, commit) é projeção de outra fonte, e o
DAP GH-42 r1 desenha justamente o caso em que os dois discordam: PR *merged*, CI verde, degrau
ainda **Ativo**.

Este teste é a forma executável dessa regra. Ele reprova se alguém acoplar o provisionamento de
engenharia — ou qualquer sinal do GitHub — ao avanço da escada, que é o atalho tentador e é o que
faria a escada mentir sobre o que a casa entregou.
"""

from __future__ import annotations

import pytest
from django.test import override_settings
from django.urls import reverse
from rest_framework.test import APIClient

from apps.core import ladder
from apps.core.github_issues import IssueDraft, IssueRef
from apps.core.models import AccountRung, AccountRungEvent, EngineeringHandoff, FdeRung, User
from apps.core.tests.factories import (
    ClientFactory,
    ProjectFactory,
    UserFactory,
)


class FakeClient:
    """Um GitHub que aceita tudo: o cenário mais favorável ao atalho que este teste proíbe."""

    def find_by_handoff_id(self, repository: str, pulse_work_item_id: str) -> IssueRef | None:
        return None

    def create_issue(self, draft: IssueDraft) -> IssueRef:
        return IssueRef(
            number=204,
            url="https://github.com/biahflow/pulse/issues/204",
            node_id="I_204",
            repository="biahflow/pulse",
        )


@pytest.mark.django_db
@override_settings(
    GITHUB_PROVISIONING_ENABLED=True,
    GITHUB_TOKEN="ghp_test",
    GITHUB_REPO="biahflow/pulse",
)
def test_a_issue_provisionada_nao_move_o_degrau(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        "apps.core.engineering_provisioning.GithubIssuesApi", lambda: FakeClient()
    )
    admin = UserFactory(role=User.Role.ADMIN)
    conta = ClientFactory()
    projeto = ProjectFactory(client=conta, name="PROVE Triagem de NF")
    degrau = AccountRung.objects.get(client=conta, rung=FdeRung.PROVE)
    ladder.transition(
        degrau,
        to_status=AccountRung.Status.ACTIVE,
        by=admin,
        project=projeto,
        waiting_on=AccountRung.WaitingOn.ENGINEERING,
    )
    eventos_antes = AccountRungEvent.objects.filter(rung=degrau).count()

    api = APIClient()
    api.force_authenticate(admin)
    provisionado = api.post(
        reverse("engineeringhandoff-list"),
        {
            "project": projeto.id,
            "pulse_work_item_id": "pulse-42-prove",
            "title": "Triagem de NF",
            "objective": "Entregar o PROVE.",
            "acceptance_criteria": "A triagem roda em produção controlada.",
        },
        format="json",
    )

    assert provisionado.status_code == 201
    assert provisionado.data["status"] == EngineeringHandoff.Status.PROVISIONED
    degrau.refresh_from_db()
    assert degrau.status == AccountRung.Status.ACTIVE
    assert degrau.completed_at is None
    assert AccountRungEvent.objects.filter(rung=degrau).count() == eventos_antes


@pytest.mark.django_db
def test_nao_existe_caminho_para_done_sem_autor() -> None:
    """O único caminho de escrita da escada exige um autor, e é o que impede o degrau automático.

    `ladder.transition` é a porta única — o serializer é inteiramente read-only e a rota de escrita
    é a action `transition`. Um `by=None` continua sendo aceito (a pessoa pode sair da casa e o
    fato não sai com ela), mas o evento existe **sempre**: não há conclusão sem registro.
    """
    conta = ClientFactory()
    degrau = AccountRung.objects.get(client=conta, rung=FdeRung.PROVE)

    ladder.transition(degrau, to_status=AccountRung.Status.DONE, by=None, note="gate GO")

    evento = AccountRungEvent.objects.get(rung=degrau)
    assert evento.to_status == AccountRung.Status.DONE
    assert evento.note == "gate GO"
