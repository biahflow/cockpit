"""As partes puras do consentimento do Google (ADR 0016).

O fluxo em si é interativo — navegador, redirect, rede — e não se testa aqui. O que dá para testar
é o que erra calado: a gravação no `.env` (que não pode comer o resto do arquivo) e o PKCE (que não
pode gerar o mesmo verifier duas vezes). É o mesmo movimento da FDD 024: extrair a regra da chamada
de rede para poder exercitá-la sem ela.
"""

from __future__ import annotations

import base64
import hashlib
from pathlib import Path

from apps.core.management.commands.google_oauth_setup import VARIAVEL, _grava_no_env, _pkce


def test_grava_a_variavel_preservando_o_resto_do_env(tmp_path: Path) -> None:
    """O `.env` tem tudo o que faz o portal subir; escrever nele não pode ser um `write` cego."""
    env = tmp_path / ".env"
    env.write_text("POSTGRES_PASSWORD=segredo\nAI_ENABLED=true\n")

    _grava_no_env(env, "refresh-abc")

    linhas = env.read_text().splitlines()
    assert "POSTGRES_PASSWORD=segredo" in linhas
    assert "AI_ENABLED=true" in linhas
    assert f"{VARIAVEL}=refresh-abc" in linhas


def test_reconsentir_substitui_em_vez_de_duplicar(tmp_path: Path) -> None:
    """Rodar o comando de novo é o caso normal (token revogado, escopo novo). Duas linhas com a
    mesma variável deixam o valor efetivo à sorte de quem lê o arquivo."""
    env = tmp_path / ".env"
    env.write_text(f"{VARIAVEL}=antigo\nOUTRA=1\n")

    _grava_no_env(env, "novo")

    linhas = env.read_text().splitlines()
    assert linhas.count(f"{VARIAVEL}=novo") == 1
    assert f"{VARIAVEL}=antigo" not in linhas
    assert "OUTRA=1" in linhas


def test_cria_o_env_quando_ainda_nao_existe(tmp_path: Path) -> None:
    env = tmp_path / ".env"

    _grava_no_env(env, "refresh-xyz")

    assert env.read_text() == f"{VARIAVEL}=refresh-xyz\n"


def test_pkce_gera_challenge_que_corresponde_ao_verifier() -> None:
    """Se o challenge não for o SHA-256 do verifier, o Google recusa a troca do código — e o erro
    só apareceria no meio do consentimento, com o navegador aberto."""
    verifier, challenge = _pkce()

    esperado = base64.urlsafe_b64encode(hashlib.sha256(verifier.encode()).digest())
    assert challenge == esperado.decode().rstrip("=")
    assert "=" not in challenge  # base64url do PKCE é sem padding (RFC 7636)


def test_pkce_nao_se_repete() -> None:
    assert _pkce()[0] != _pkce()[0]
