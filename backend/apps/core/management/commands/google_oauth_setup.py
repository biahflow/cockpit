"""Consentimento único que produz o `GOOGLE_OAUTH_REFRESH_TOKEN` (ADR 0016).

Roda **no host**, não no container: precisa abrir o navegador e receber o retorno do Google em
`http://localhost`. Uma vez só — depois disso o refresh token vive no `.env` e o portal se vira
sozinho.

Por que existe um comando em vez de um passo manual no runbook: o fluxo "cole o código na tela"
(OOB) foi **descontinuado pelo Google**, então hoje é preciso subir um servidor local para receber
o `code`. Fazer isso à mão em toda instalação é o tipo de passo que sai errado.

**O token nunca é impresso.** Ele vai direto para o `.env` (que está no `.gitignore`), e a saída
diz apenas o tamanho. Segredo que aparece na tela acaba em screenshot, em histórico de shell e em
log de terminal.
"""

from __future__ import annotations

import base64
import hashlib
import http.server
import json
import secrets
import urllib.error
import urllib.parse
import urllib.request
import webbrowser
from pathlib import Path
from typing import Any

from django.core.management.base import BaseCommand, CommandError

AUTH_URI = "https://accounts.google.com/o/oauth2/v2/auth"
TOKEN_URI = "https://oauth2.googleapis.com/token"
SCOPES = (
    "https://www.googleapis.com/auth/drive",
    "https://www.googleapis.com/auth/calendar",
)
VARIAVEL = "GOOGLE_OAUTH_REFRESH_TOKEN"


class _Retorno(http.server.BaseHTTPRequestHandler):
    """Recebe o redirect do Google e guarda o `code`."""

    code = ""
    erro = ""
    esperado = ""  # o `state` que nós geramos; o retorno tem de trazer o mesmo

    def do_GET(self) -> None:  # noqa: N802 - assinatura da stdlib
        params = urllib.parse.parse_qs(urllib.parse.urlparse(self.path).query)
        if params.get("state", [""])[0] != _Retorno.esperado:
            # Sem esta conferência, qualquer página aberta no seu navegador poderia mandar um
            # `code` ao nosso localhost e trocar a credencial por baixo (CSRF no callback).
            _Retorno.erro = "state divergente — o retorno não corresponde ao pedido"
        else:
            _Retorno.code = params.get("code", [""])[0]
            _Retorno.erro = params.get("error", [""])[0]
        corpo = (
            "<h2>Pode fechar esta aba.</h2><p>O consentimento voltou para o terminal.</p>"
            if _Retorno.code
            else f"<h2>Falhou</h2><p>{_Retorno.erro}</p>"
        )
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.end_headers()
        self.wfile.write(corpo.encode())

    def log_message(self, *a: object) -> None:
        """Silencia o log de acesso da stdlib: ele imprimiria o `code` na tela."""


def _pkce() -> tuple[str, str]:
    """Verifier e challenge (S256). O Google recomenda PKCE para app de computador, e ele torna o
    `client_secret` — que num app desktop não é secreto de verdade — insuficiente sozinho."""
    verifier = base64.urlsafe_b64encode(secrets.token_bytes(64)).decode().rstrip("=")
    digest = hashlib.sha256(verifier.encode()).digest()
    return verifier, base64.urlsafe_b64encode(digest).decode().rstrip("=")


def _grava_no_env(caminho: Path, valor: str) -> None:
    """Escreve/atualiza a variável no `.env`, preservando o resto do arquivo."""
    linhas = caminho.read_text().splitlines() if caminho.exists() else []
    nova = f"{VARIAVEL}={valor}"
    for i, linha in enumerate(linhas):
        if linha.startswith(f"{VARIAVEL}="):
            linhas[i] = nova
            break
    else:
        linhas.append(nova)
    caminho.write_text("\n".join(linhas) + "\n")


class Command(BaseCommand):
    help = "Consentimento único do Google que grava o refresh token no .env (ADR 0016)."

    def add_arguments(self, parser: Any) -> None:
        parser.add_argument("--client-id", required=True)
        parser.add_argument("--client-secret", required=True)
        parser.add_argument(
            "--env-file", default="../.env",
            help="Onde gravar o refresh token (default: ../.env, a partir de backend/).",
        )
        parser.add_argument("--port", type=int, default=8765)

    def handle(self, *args: Any, **options: Any) -> None:
        porta = options["port"]
        redirect_uri = f"http://localhost:{porta}"
        verifier, challenge = _pkce()
        estado = secrets.token_urlsafe(16)

        consulta = urllib.parse.urlencode({
            "client_id": options["client_id"],
            "redirect_uri": redirect_uri,
            "response_type": "code",
            "scope": " ".join(SCOPES),
            # `offline` + `consent` juntos são o que **garante** um refresh token: sem `offline`
            # não vem nenhum, e sem `consent` o Google reaproveita um consentimento anterior e
            # devolve só o access token — o modo de falha clássico deste fluxo.
            "access_type": "offline",
            "prompt": "consent",
            "code_challenge": challenge,
            "code_challenge_method": "S256",
            "state": estado,
        })
        url = f"{AUTH_URI}?{consulta}"

        _Retorno.esperado = estado
        servidor = http.server.HTTPServer(("localhost", porta), _Retorno)
        servidor.timeout = 300

        self.stdout.write("Abrindo o navegador para o consentimento…")
        self.stdout.write(f"Se não abrir, acesse:\n{url}\n")
        webbrowser.open(url)

        # Bloqueia até o Google voltar (ou o timeout estourar). Atender na thread principal é o
        # que garante que o socket só feche **depois** da resposta — fechá-lo antes derrubava o
        # redirect no meio, que era um defeito real desta primeira versão.
        servidor.handle_request()
        servidor.server_close()
        if _Retorno.erro:
            raise CommandError(f"o Google recusou: {_Retorno.erro}")
        if not _Retorno.code:
            raise CommandError("nenhum código recebido — o consentimento não completou.")

        dados = urllib.parse.urlencode({
            "client_id": options["client_id"],
            "client_secret": options["client_secret"],
            "code": _Retorno.code,
            "code_verifier": verifier,
            "grant_type": "authorization_code",
            "redirect_uri": redirect_uri,
        }).encode()
        try:
            with urllib.request.urlopen(
                urllib.request.Request(TOKEN_URI, data=dados)
            ) as resposta:
                token = json.loads(resposta.read())
        except urllib.error.HTTPError as exc:
            raise CommandError(f"troca do código falhou: {exc.read().decode()[:300]}") from exc

        refresh = token.get("refresh_token")
        if not refresh:
            raise CommandError(
                "o Google não devolveu refresh_token. Costuma ser consentimento reaproveitado — "
                "revogue o acesso do app em https://myaccount.google.com/permissions e repita."
            )

        destino = Path(options["env_file"]).resolve()
        _grava_no_env(destino, refresh)
        # Só o tamanho: segredo impresso acaba em screenshot e em histórico de shell.
        self.stdout.write(self.style.SUCCESS(
            f"{VARIAVEL} gravado em {destino} ({len(refresh)} caracteres)."
        ))
        self.stdout.write("Falta preencher no mesmo .env: GOOGLE_AUTH_MODE=oauth, "
                          "GOOGLE_OAUTH_CLIENT_ID, GOOGLE_OAUTH_CLIENT_SECRET, "
                          "GOOGLE_DRIVE_ROOT_FOLDER_ID e GOOGLE_CALENDAR_ID.")
