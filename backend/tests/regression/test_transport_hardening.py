"""Regressão: o transporte é redirecionado e fixado em https (FDD 019).

A FDD 017 deixou este bloco explicitamente para o item de infraestrutura: sem `SECURE_SSL_REDIRECT`
a sessão trafegava em claro se alguém digitasse `http://`, e sem HSTS o navegador voltava a tentar
http na visita seguinte. O teste é de comportamento, não de leitura de settings: o que importa é a
resposta que sai do middleware.
"""

import pytest
from django.test import Client, override_settings
from django.urls import reverse

CSRF = reverse("csrf")


def test_http_e_redirecionado_para_https() -> None:
    with override_settings(SECURE_SSL_REDIRECT=True):
        resposta = Client().get(CSRF)

    assert resposta.status_code == 301
    assert resposta["Location"].startswith("https://")


def test_o_header_do_proxy_evita_o_redirect_em_loop() -> None:
    """Com TLS terminado na borda, o Django precisa aceitar o que o proxy diz — ou nunca para."""
    with override_settings(
        SECURE_SSL_REDIRECT=True,
        SECURE_PROXY_SSL_HEADER=("HTTP_X_FORWARDED_PROTO", "https"),
    ):
        resposta = Client().get(CSRF, headers={"x-forwarded-proto": "https"})

    assert resposta.status_code == 200


def test_sem_o_opt_in_o_header_do_cliente_nao_vale_nada() -> None:
    """O footgun da ADR 0011: sem `SECURE_PROXY_SSL_HEADER`, dizer "sou https" não convence."""
    with override_settings(SECURE_SSL_REDIRECT=True, SECURE_PROXY_SSL_HEADER=None):
        resposta = Client().get(CSRF, headers={"x-forwarded-proto": "https"})

    assert resposta.status_code == 301


def test_rota_isenta_nao_e_redirecionada() -> None:
    """Serve para a sonda de um balanceador que só fala http com o container."""
    with override_settings(SECURE_SSL_REDIRECT=True, SECURE_REDIRECT_EXEMPT=[r"^api/v1/auth/csrf/$"]):
        resposta = Client().get(CSRF)

    assert resposta.status_code == 200


@pytest.mark.parametrize("preload", [False, True])
def test_hsts_sai_no_header_e_preload_so_quando_pedido(preload: bool) -> None:
    with override_settings(
        SECURE_HSTS_SECONDS=31_536_000,
        SECURE_HSTS_INCLUDE_SUBDOMAINS=True,
        SECURE_HSTS_PRELOAD=preload,
        SECURE_PROXY_SSL_HEADER=("HTTP_X_FORWARDED_PROTO", "https"),
    ):
        resposta = Client().get(CSRF, headers={"x-forwarded-proto": "https"})

    hsts = resposta["Strict-Transport-Security"]
    assert "max-age=31536000" in hsts
    assert "includeSubDomains" in hsts
    assert ("preload" in hsts) is preload


def test_sem_hsts_configurado_nao_ha_header() -> None:
    """O default do código é 0: ligar HSTS por engano em desenvolvimento trava o navegador em https."""
    with override_settings(
        SECURE_HSTS_SECONDS=0,
        SECURE_PROXY_SSL_HEADER=("HTTP_X_FORWARDED_PROTO", "https"),
    ):
        resposta = Client().get(CSRF, headers={"x-forwarded-proto": "https"})

    assert "Strict-Transport-Security" not in resposta
