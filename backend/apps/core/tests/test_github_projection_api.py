"""API da projeção de engenharia (FDD 041): escopo, papéis e o webhook de entrada.

O painel do DAP GH-41 r1 só pode dizer "não sei mais" se o backend for quem decide o que é
obsoleto, e só pode mostrar a copy invariante para Vendas se Vendas de fato **não alcançar** o
recurso. As duas coisas se afirmam aqui.
"""

from __future__ import annotations

import hmac
import json
from datetime import timedelta
from hashlib import sha256

import pytest
from django.test import override_settings
from django.urls import reverse
from django.utils import timezone
from rest_framework.test import APIClient

from apps.core.models import GithubDelivery, GithubProjection, User

from .factories import (
    GithubProjectionFactory,
    ProjectFactory,
    ProjectMemberFactory,
    ProvisionedHandoffFactory,
    UserFactory,
)

SECRET = "segredo-de-fixture"
REPO = "acme/repo"
LISTA = "/api/v1/github-projections/"


@pytest.fixture
def api() -> APIClient:
    return APIClient()


def assinado(api: APIClient, payload: dict, *, event: str, delivery: str, secret: str = SECRET):
    body = json.dumps(payload).encode()
    return api.post(
        reverse("github-webhook"),
        data=body,
        content_type="application/json",
        headers={
            "X-Hub-Signature-256": "sha256=" + hmac.new(secret.encode(), body, sha256).hexdigest(),
            "X-GitHub-Event": event,
            "X-GitHub-Delivery": delivery,
        },
    )


# --- Leitura -------------------------------------------------------------------


@pytest.mark.django_db
@override_settings(GITHUB_PROJECTION_STALE_AFTER_SECONDS=1800)
def test_admin_le_as_referencias_do_projeto_com_estado_e_proveniencia(api: APIClient) -> None:
    projeto = ProjectFactory()
    projecao = GithubProjectionFactory(
        handoff__project=projeto,
        handoff__repository=REPO,
        handoff__github_issue_number=41,
        pr_number=90,
        head_sha="a" * 40,
        ci_state=GithubProjection.CiState.SUCCESS,
    )
    GithubProjectionFactory()  # de outro projeto: não pode aparecer no recorte
    api.force_authenticate(UserFactory(role=User.Role.ADMIN))

    resposta = api.get(f"{LISTA}?project={projeto.pk}")

    assert resposta.status_code == 200
    (linha,) = resposta.json()
    assert linha["id"] == projecao.pk
    assert linha["reference"] == "acme/repo#41"
    assert linha["issue_url"].endswith("/issues/41")
    assert linha["ci_state"] == "success"
    assert linha["observed_via"] == "webhook"
    assert linha["is_stale"] is False
    assert linha["age_seconds"] < 60
    assert linha["last_error_age_seconds"] is None


@pytest.mark.django_db
@override_settings(GITHUB_PROJECTION_STALE_AFTER_SECONDS=1800)
def test_a_obsolescencia_vem_calculada_do_backend(api: APIClient) -> None:
    projecao = GithubProjectionFactory(observed_at=timezone.now() - timedelta(hours=3))
    api.force_authenticate(UserFactory(role=User.Role.ADMIN))

    linha = api.get(f"{LISTA}?project={projecao.handoff.project_id}").json()[0]

    assert linha["is_stale"] is True
    assert linha["age_seconds"] >= 3 * 3600


@pytest.mark.django_db
def test_projeto_sem_referencia_devolve_lista_vazia(api: APIClient) -> None:
    projeto = ProjectFactory()
    api.force_authenticate(UserFactory(role=User.Role.ADMIN))

    assert api.get(f"{LISTA}?project={projeto.pk}").json() == []


@pytest.mark.django_db
def test_handoff_arquivado_tira_a_projecao_da_listagem(api: APIClient) -> None:
    projecao = GithubProjectionFactory()
    projecao.handoff.archive()
    api.force_authenticate(UserFactory(role=User.Role.ADMIN))

    assert api.get(LISTA).json() == []
    assert api.get(f"{LISTA}{projecao.pk}/").status_code == 404


@pytest.mark.django_db
def test_vendas_nao_alcanca_o_recurso(api: APIClient) -> None:
    """Decisão 6 do DAP: Vendas vê o painel e vê que não vê — o 403 é quem sustenta isso."""
    projecao = GithubProjectionFactory()
    api.force_authenticate(UserFactory(role=User.Role.SALES))

    assert api.get(LISTA).status_code == 403
    assert api.get(f"{LISTA}{projecao.pk}/").status_code == 403


@pytest.mark.django_db
def test_entrega_so_ve_a_referencia_do_projeto_de_que_participa(api: APIClient) -> None:
    minha = GithubProjectionFactory()
    alheia = GithubProjectionFactory()
    pessoa = UserFactory(role=User.Role.DELIVERY)
    ProjectMemberFactory(project=minha.handoff.project, user=pessoa)
    api.force_authenticate(pessoa)

    listagem = api.get(LISTA).json()

    assert [linha["id"] for linha in listagem] == [minha.pk]
    assert api.get(f"{LISTA}{alheia.pk}/").status_code == 404


@pytest.mark.django_db
def test_o_recurso_e_somente_leitura(api: APIClient) -> None:
    """Comando sobre o GitHub é contrato próprio, e a Issue #41 o reserva explicitamente."""
    projecao = GithubProjectionFactory()
    api.force_authenticate(UserFactory(role=User.Role.ADMIN))

    assert api.post(LISTA, {}, format="json").status_code == 405
    assert api.patch(f"{LISTA}{projecao.pk}/", {"ci_state": "success"}, format="json").status_code == 405
    assert api.delete(f"{LISTA}{projecao.pk}/").status_code == 405


# --- Webhook -------------------------------------------------------------------


@pytest.mark.django_db
@override_settings(GITHUB_WEBHOOK_SECRET="")
def test_sem_segredo_configurado_o_webhook_recusa(api: APIClient) -> None:
    resposta = assinado(api, {}, event="issues", delivery="d-1")

    assert resposta.status_code == 503
    assert not GithubDelivery.objects.exists()


@pytest.mark.django_db
@override_settings(GITHUB_WEBHOOK_SECRET=SECRET)
def test_assinatura_invalida_e_4xx(api: APIClient) -> None:
    resposta = assinado(api, {}, event="issues", delivery="d-1", secret="outro")

    assert resposta.status_code == 401
    assert not GithubDelivery.objects.exists()


@pytest.mark.django_db
@override_settings(GITHUB_WEBHOOK_SECRET=SECRET)
def test_evento_desconhecido_responde_200(api: APIClient) -> None:
    """Erro aqui faria o GitHub reentregar em laço e acabar desabilitando o hook."""
    resposta = assinado(api, {"zen": "x"}, event="ping", delivery="d-1")

    assert resposta.status_code == 200
    assert resposta.json()["detail"] == "Evento ignorado."


@pytest.mark.django_db
@override_settings(GITHUB_WEBHOOK_SECRET=SECRET)
def test_entrega_sem_identidade_e_400(api: APIClient) -> None:
    body = b"{}"
    resposta = api.post(
        reverse("github-webhook"),
        data=body,
        content_type="application/json",
        headers={
            "X-Hub-Signature-256": "sha256=" + hmac.new(SECRET.encode(), body, sha256).hexdigest(),
            "X-GitHub-Event": "issues",
        },
    )

    assert resposta.status_code == 400


@pytest.mark.django_db
@override_settings(GITHUB_WEBHOOK_SECRET=SECRET)
def test_corpo_invalido_e_400(api: APIClient) -> None:
    body = b"nao e json"
    resposta = api.post(
        reverse("github-webhook"),
        data=body,
        content_type="application/json",
        headers={
            "X-Hub-Signature-256": "sha256=" + hmac.new(SECRET.encode(), body, sha256).hexdigest(),
            "X-GitHub-Event": "issues",
            "X-GitHub-Delivery": "d-1",
        },
    )

    assert resposta.status_code == 400


@pytest.mark.django_db
@override_settings(GITHUB_WEBHOOK_SECRET=SECRET)
def test_webhook_valido_projeta_o_estado_e_dispensa_sessao(api: APIClient) -> None:
    handoff = ProvisionedHandoffFactory(repository=REPO, github_issue_number=41)

    resposta = assinado(
        api,
        {
            "repository": {"full_name": REPO},
            "issue": {
                "number": 41,
                "state": "closed",
                "title": "Do GitHub",
                "updated_at": "2026-08-27T12:00:00Z",
            },
        },
        event="issues",
        delivery="d-1",
    )

    assert resposta.status_code == 200
    projecao = GithubProjection.objects.get(handoff=handoff)
    assert projecao.issue_state == GithubProjection.IssueState.CLOSED
    assert GithubDelivery.objects.count() == 1


@pytest.mark.django_db
@override_settings(GITHUB_WEBHOOK_SECRET=SECRET)
def test_o_teto_do_webhook_tem_escopo_proprio() -> None:
    from apps.core.views import GithubWebhookView

    assert GithubWebhookView.throttle_scope == "github_webhook"
    assert GithubWebhookView.authentication_classes == []
