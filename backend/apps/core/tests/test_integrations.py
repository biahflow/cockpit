"""Sondas de integração e o comando que as roda (FDD 024).

O que estes testes protegem: que a sonda **nunca estoure** (é caminho de diagnóstico), que ela
distinga "desligada" de "reprovada" — dizer FALHA para integração desligada treinaria quem opera a
ignorar o comando — e que o comando saia com código 1 quando alguma reprova, que é o que um alerta
lê.
"""

import pytest
from django.core.management import call_command
from django.core.management.base import CommandError
from django.test import override_settings

from apps.core import integrations, payments

pytestmark = pytest.mark.django_db


def test_integracao_desligada_nao_e_sondada(monkeypatch: pytest.MonkeyPatch) -> None:
    """Desligada não é falha. Sondá-la ainda gastaria rede por nada."""
    chamou = []
    monkeypatch.setitem(integrations.PROBES, "ai", lambda: chamou.append(1) or (True, "ok"))

    with override_settings(AI_ENABLED=False):
        resultado = integrations.probe("ai")

    assert resultado.ok is None
    assert resultado.reprovou is False
    assert resultado.detail == "desligada"
    assert chamou == []


def test_ligada_sem_credencial_reprova_antes_de_gastar_rede(monkeypatch: pytest.MonkeyPatch) -> None:
    chamou = []
    monkeypatch.setitem(integrations.PROBES, "ai", lambda: chamou.append(1) or (True, "ok"))

    with override_settings(AI_ENABLED=True, OPENAI_API_KEY=""):
        resultado = integrations.probe("ai")

    assert resultado.reprovou
    assert "OPENAI_API_KEY" in resultado.detail
    assert chamou == []


def test_sonda_que_estoura_vira_reprovacao_com_o_motivo(monkeypatch: pytest.MonkeyPatch) -> None:
    """Diagnóstico que levanta traceback vira 'o diagnóstico quebrou' em vez de 'a integração
    quebrou' — que é o oposto do que ele existe para dizer."""

    def explode() -> tuple[bool, str]:
        raise RuntimeError("401 Incorrect API key provided")

    monkeypatch.setitem(integrations.PROBES, "ai", explode)

    with override_settings(AI_ENABLED=True, OPENAI_API_KEY="sk-errada"):
        resultado = integrations.probe("ai")

    assert resultado.reprovou
    # A mensagem do provedor é o produto da sonda: é ela que diz o que consertar.
    assert "Incorrect API key" in resultado.detail


def test_excecao_sem_mensagem_ainda_diz_alguma_coisa(monkeypatch: pytest.MonkeyPatch) -> None:
    def explode() -> tuple[bool, str]:
        raise TimeoutError()

    monkeypatch.setitem(integrations.PROBES, "ai", explode)

    with override_settings(AI_ENABLED=True, OPENAI_API_KEY="sk-x"):
        assert integrations.probe("ai").detail == "TimeoutError"


def test_sonda_bem_sucedida_passa(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setitem(integrations.PROBES, "ai", lambda: (True, "modelo acessível"))

    with override_settings(AI_ENABLED=True, OPENAI_API_KEY="sk-x"):
        resultado = integrations.probe("ai")

    assert resultado.ok is True
    assert resultado.detail == "modelo acessível"


def test_all_sonda_desligada_para_conferir_antes_de_ligar(monkeypatch: pytest.MonkeyPatch) -> None:
    """O caso de uso real da flag `--all`: validar a chave antes de ligar a integração."""
    monkeypatch.setitem(integrations.PROBES, "ai", lambda: (True, "modelo acessível"))

    with override_settings(AI_ENABLED=False, OPENAI_API_KEY="sk-x"):
        resultado = integrations._forcado("ai")

    assert resultado.enabled is False
    assert resultado.ok is True
    assert "(desligada)" in resultado.detail


def test_email_nao_envia_nada_ao_sondar(monkeypatch: pytest.MonkeyPatch, mailoutbox) -> None:  # type: ignore[no-untyped-def]
    """Sonda que manda e-mail vira spam diário assim que alguém a agendar."""
    with override_settings(EMAIL_NOTIFICATIONS_ENABLED=True):
        resultado = integrations.probe("email")

    assert resultado.ok is True
    assert mailoutbox == []


# --- o comando ---------------------------------------------------------------------------------


def test_comando_passa_com_tudo_desligado(capsys: pytest.CaptureFixture[str]) -> None:
    """O default do repositório: nada ligado, nada reprova."""
    call_command("check_integrations")

    saida = capsys.readouterr().out
    assert "desligada" in saida
    assert "Todas as integrações ligadas responderam." in saida


def test_comando_reprova_e_sai_com_erro(monkeypatch: pytest.MonkeyPatch) -> None:
    def explode() -> tuple[bool, str]:
        raise RuntimeError("Shared Drive não encontrado")

    monkeypatch.setitem(integrations.PROBES, "drive", explode)

    with override_settings(GOOGLE_DRIVE_ENABLED=True, GOOGLE_DRIVE_ROOT_FOLDER_ID="abc"):
        with pytest.raises(CommandError, match="drive"):
            call_command("check_integrations")


def test_comando_lista_o_motivo_de_cada_reprovacao(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setitem(
        integrations.PROBES, "drive", lambda: (_ for _ in ()).throw(RuntimeError("escopo faltando"))
    )

    with override_settings(
        GOOGLE_DRIVE_ENABLED=True,
        GOOGLE_DRIVE_ROOT_FOLDER_ID="abc",
        GOOGLE_AUTH_MODE="adc",
    ):
        with pytest.raises(CommandError):
            call_command("check_integrations")

    assert "escopo faltando" in capsys.readouterr().out


def test_sonda_de_pagamento_sem_provedor_diz_que_nao_ha_o_que_sondar() -> None:
    """`NullProvider` não tem `ping`: a sonda responde "não sondável", não reprovação (FDD 024)."""
    with override_settings(PAYMENTS_PROVIDER=""):
        ok, detalhe = integrations._probe_payments()
    assert ok is True
    assert "nenhum provedor" in detalhe


def test_sonda_de_pagamento_usa_o_ping_do_adaptador(monkeypatch: pytest.MonkeyPatch) -> None:
    """Reusa o cliente real do adaptador — credencial malformada falha como falharia em produção."""
    with override_settings(PAYMENTS_PROVIDER="stripe", PAYMENTS_API_TOKEN="sk_test_x"):
        monkeypatch.setattr(
            payments.StripeProvider, "ping", lambda self: (True, "chave válida, modo teste")
        )
        assert integrations._probe_payments() == (True, "chave válida, modo teste")


def test_pagamento_entra_no_registro_de_sondas() -> None:
    assert "payments" in integrations.PROBES


def test_github_provisioning_entra_no_registro_de_sondas() -> None:
    assert "github_provisioning" in integrations.PROBES


# --- aviso de entrega do esign (issue #112) -----------------------------------------------------


def test_sonda_de_esign_avisa_sem_reprovar_sem_provedor_sondavel() -> None:
    """Sem `ping` (`NullProvider`), a sonda cai no caminho `NAO_SONDAVEL` — e o aviso se anexa
    igual, porque a combinação `sandbox=True`+`delivery=email` independe de haver provedor."""
    with override_settings(ESIGN_PROVIDER="", ESIGN_SANDBOX=True, ESIGN_DELIVERY="email"):
        ok, detalhe = integrations._probe_esign()

    assert ok is True
    assert "issue #112" in detalhe


def test_sonda_de_esign_avisa_sem_reprovar_com_provedor_sondavel(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Aviso não é reprovação: `ok` continua o que o `ping()` do adaptador devolveu."""
    from apps.core import esign

    monkeypatch.setattr(esign.AutentiqueProvider, "ping", lambda self: (True, "conta x acessível"))

    with override_settings(
        ESIGN_PROVIDER="autentique", ESIGN_SANDBOX=True, ESIGN_DELIVERY="email"
    ):
        ok, detalhe = integrations._probe_esign()

    assert ok is True
    assert "conta x acessível" in detalhe
    assert "issue #112" in detalhe


def test_sonda_de_esign_sem_aviso_fora_da_combinacao(monkeypatch: pytest.MonkeyPatch) -> None:
    from apps.core import esign

    monkeypatch.setattr(esign.AutentiqueProvider, "ping", lambda self: (True, "conta x acessível"))

    with override_settings(ESIGN_PROVIDER="autentique", ESIGN_SANDBOX=True, ESIGN_DELIVERY="link"):
        ok, detalhe = integrations._probe_esign()

    assert ok is True
    assert detalhe == "conta x acessível"
    assert "issue #112" not in detalhe
