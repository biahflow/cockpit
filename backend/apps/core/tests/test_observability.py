"""Request-id e log estruturado (FDD 020)."""

import json
import logging
from unittest import mock

import pytest
from django.test import Client
from django.urls import reverse

from apps.core.observability import (
    MAX_REQUEST_ID_LENGTH,
    NO_REQUEST_ID,
    JsonFormatter,
    RequestIdFilter,
    get_request_id,
    init_sentry,
    sanitize_request_id,
    tag_request,
)


@pytest.mark.django_db
def test_resposta_ganha_um_request_id_quando_o_cliente_nao_manda() -> None:
    response = Client().get(reverse("csrf"))

    assert len(response["X-Request-ID"]) == 32


@pytest.mark.django_db
def test_request_id_da_borda_e_preservado() -> None:
    """O nginx manda o `$request_id` dele; aproveitá-lo é o que liga os dois logs."""
    response = Client().get(reverse("csrf"), headers={"x-request-id": "borda-123"})

    assert response["X-Request-ID"] == "borda-123"


@pytest.mark.django_db
@pytest.mark.parametrize(
    "recebido,esperado",
    [
        ("linha\nfalsa INFO tudo ok", "linhafalsaINFOtudook"),
        ('{"nivel": "ERROR"}', "nivelERROR"),
        ("x" * 200, "x" * MAX_REQUEST_ID_LENGTH),
    ],
)
def test_request_id_de_fora_e_sanitizado(recebido: str, esperado: str) -> None:
    """Sem isto, um header com quebra de linha injeta uma entrada falsa no log."""
    response = Client().get(reverse("csrf"), headers={"x-request-id": recebido})

    assert response["X-Request-ID"] == esperado


@pytest.mark.django_db
def test_request_id_vazio_depois_da_limpeza_vira_um_novo() -> None:
    response = Client().get(reverse("csrf"), headers={"x-request-id": "@@@ ###"})

    assert len(response["X-Request-ID"]) == 32


def test_request_id_nao_vaza_de_uma_requisicao_para_a_seguinte() -> None:
    """O worker é reaproveitado: o `ContextVar` precisa voltar ao estado anterior."""
    assert get_request_id() == NO_REQUEST_ID


@pytest.mark.django_db
def test_log_de_acesso_carrega_request_id_usuario_e_duracao(
    caplog: pytest.LogCaptureFixture,
) -> None:
    with caplog.at_level(logging.INFO, logger="biahflow.request"):
        Client().get(reverse("csrf"), headers={"x-request-id": "abc123"})

    registro = next(r for r in caplog.records if r.name == "biahflow.request")
    assert registro.request_id == "abc123"
    assert registro.status == 200
    assert registro.path == "/api/v1/auth/csrf/"
    assert registro.user_id is None
    assert registro.duration_ms >= 0


@pytest.mark.django_db
def test_sonda_nao_entra_no_log_de_acesso(caplog: pytest.LogCaptureFixture) -> None:
    """A cada 15 s a sonda viraria toda a saída do container."""
    with caplog.at_level(logging.INFO, logger="biahflow.request"):
        Client().get("/healthz")

    assert [r for r in caplog.records if r.name == "biahflow.request"] == []


def test_filtro_preenche_request_id_fora_de_uma_requisicao() -> None:
    registro = logging.LogRecord("x", logging.INFO, "arq.py", 1, "oi", None, None)

    assert RequestIdFilter().filter(registro) is True
    assert registro.request_id == NO_REQUEST_ID  # type: ignore[attr-defined]


def test_formatter_json_produz_uma_linha_parseavel() -> None:
    registro = logging.LogRecord("app", logging.WARNING, "arq.py", 1, "olá %s", ("mundo",), None)
    registro.request_id = "abc123"  # type: ignore[attr-defined]
    registro.status = 500  # type: ignore[attr-defined]

    payload = json.loads(JsonFormatter().format(registro))

    assert payload["level"] == "WARNING"
    assert payload["logger"] == "app"
    assert payload["message"] == "olá mundo"
    assert payload["request_id"] == "abc123"
    assert payload["status"] == 500
    assert "exception" not in payload


def test_formatter_json_inclui_o_traceback() -> None:
    try:
        raise ValueError("estourou")
    except ValueError:
        registro = logging.LogRecord("app", logging.ERROR, "arq.py", 1, "erro", None, None)
        import sys

        registro.exc_info = sys.exc_info()

    payload = json.loads(JsonFormatter().format(registro))

    assert "ValueError: estourou" in payload["exception"]


def test_formatter_json_nao_perde_a_linha_com_valor_nao_serializavel() -> None:
    """`extra` pode trazer `Decimal`, `datetime` ou model — `default=str` salva a linha."""
    registro = logging.LogRecord("app", logging.INFO, "arq.py", 1, "oi", None, None)
    registro.objeto = object()  # type: ignore[attr-defined]

    payload = json.loads(JsonFormatter().format(registro))

    assert payload["objeto"].startswith("<object object")


def test_sanitize_aceita_o_formato_que_o_nginx_gera() -> None:
    assert sanitize_request_id("9f1c2e4b8a7d6f3e") == "9f1c2e4b8a7d6f3e"


def test_sem_dsn_o_sentry_nao_e_inicializado() -> None:
    """O fornecedor é opcional: sem DSN o SDK nunca sobe (ADR 0012)."""
    with mock.patch("sentry_sdk.init") as init:
        assert init_sentry("") is False

    init.assert_not_called()


def test_com_dsn_o_sentry_sobe_sem_pii() -> None:
    """`send_default_pii` mandaria cookie de sessão, corpo e e-mail para um terceiro — e este
    portal carrega proposta, contrato e dado de cliente."""
    with mock.patch("sentry_sdk.init") as init:
        assert init_sentry("https://chave@o0.ingest.sentry.io/1", "producao", "2026.08.05") is True

    kwargs = init.call_args.kwargs
    assert kwargs["send_default_pii"] is False
    assert kwargs["environment"] == "producao"
    assert kwargs["release"] == "2026.08.05"
    assert kwargs["traces_sample_rate"] == 0.0


def test_tag_request_e_no_op_com_o_sentry_desligado() -> None:
    """Nada de exceção no meio de toda requisição quando ninguém contratou o fornecedor."""
    with mock.patch("sentry_sdk.set_tag") as set_tag:
        tag_request("abc123")

    set_tag.assert_not_called()


def test_tag_request_carimba_o_id_quando_o_sentry_esta_ligado() -> None:
    """É o que permite sair do evento de erro e cair na linha de log da mesma requisição."""
    with (
        mock.patch("sentry_sdk.get_client") as get_client,
        mock.patch("sentry_sdk.set_tag") as set_tag,
    ):
        get_client.return_value.is_active.return_value = True
        tag_request("abc123")

    set_tag.assert_called_once_with("request_id", "abc123")
