"""Regressão: a sonda responde onde a anterior não respondia (FDD 020).

O defeito: até a FDD 019, o healthcheck do `api` no `docker-compose.prod.yml` era um GET em
`/api/v1/auth/csrf/` com `Host: 127.0.0.1`. Em produção de verdade `DJANGO_ALLOWED_HOSTS` é o
domínio — o `check --deploy` **recusa subir** com hosts de desenvolvimento (`biahflow.E005`) —,
então `request.get_host()` levantava `DisallowedHost`, a sonda recebia 400, o container nunca ficava
*healthy* e o serviço `web`, que depende de `service_healthy`, nunca subia.

É a razão técnica de `/healthz` ser middleware e não rota: nenhuma view chega antes da validação de
`Host` nem antes do redirect de https.
"""

import pytest
from django.test import Client, override_settings
from django.urls import reverse

CSRF = reverse("csrf")
# Um host que não está em `ALLOWED_HOSTS` — o papel que `127.0.0.1` faz na sonda do container.
HOST_DE_FORA = "172.18.0.4"


@pytest.mark.django_db
def test_a_sonda_antiga_recusa_o_host_de_quem_sonda_o_container() -> None:
    with override_settings(ALLOWED_HOSTS=["portal.exemplo.com"]):
        resposta = Client().get(CSRF, HTTP_HOST=HOST_DE_FORA)

    assert resposta.status_code == 400


def test_healthz_responde_com_host_fora_de_allowed_hosts() -> None:
    with override_settings(ALLOWED_HOSTS=["portal.exemplo.com"]):
        resposta = Client().get("/healthz", HTTP_HOST=HOST_DE_FORA)

    assert resposta.status_code == 200
    assert resposta.json() == {"status": "ok"}


@pytest.mark.django_db
def test_as_sondas_nao_levam_301_com_ssl_redirect_ligado() -> None:
    """Um balanceador lê 301 como falha, e a sonda fala http com o container."""
    with override_settings(SECURE_SSL_REDIRECT=True):
        assert Client().get("/healthz").status_code == 200
        assert Client().get("/readyz").status_code == 200
        # Qualquer outra rota continua sendo redirecionada (FDD 019).
        assert Client().get(CSRF).status_code == 301
