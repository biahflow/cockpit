"""Como o portal se autentica no Google — um lugar só (ADR 0016).

Antes, `drive._service()` e `calendar_sync._service()` montavam credencial cada um, e os dois só
sabiam ler **chave de conta de serviço** (`GOOGLE_SERVICE_ACCOUNT_INFO`/`_FILE`). Isso tem dois
problemas, e o segundo é fatal:

- A chave é um segredo de vida longa que precisa existir em arquivo ou variável — ela vaza em
  backup, em log, na imagem, no `docker inspect`. É o tipo de credencial que o Google recomenda
  evitar "sempre que possível".
- **Organizações a proíbem por política.** `iam.managed.disableServiceAccountKeyCreation` impede
  criar a chave, e foi exatamente o que bloqueou a homologação da rodada 3 (FDD 024): o desenho
  não era subótimo, era **inconstruível** — nenhuma das duas variáveis podia ser preenchida.

Aqui há dois modos, e nenhum deles é uma chave no ambiente:

- **`adc`** — Application Default Credentials, o default. `google.auth.default()` resolve, nesta
  ordem: o arquivo de `GOOGLE_APPLICATION_CREDENTIALS` (que pode ser uma configuração de **Workload
  Identity Federation**, sem chave), as credenciais do `gcloud auth application-default login`, e o
  **metadata server** — como um pod no GKE ou um serviço no Cloud Run se autenticam sem ter segredo
  algum no ambiente. É o caminho de container/pod, e também o de desenvolvimento local.
- **`oauth`** — credencial de **usuário**, por refresh token. Existe porque há coisas que conta de
  serviço não faz: convidar participante em evento exige agir como uma pessoa (senão o Google
  responde `forbiddenForServiceAccounts`), e é o convite que faz o agendamento do site valer.

Quem tiver uma chave e puder usá-la não perdeu nada: basta apontar `GOOGLE_APPLICATION_CREDENTIALS`
para ela, porque o ADC lê chave de conta de serviço também. O que sumiu foi o **caminho dedicado**
para o único artefato que a política proíbe — manter um caminho que ninguém pode tomar é a mesma
mentira que a FDD 024 existe para consertar.

O escopo é por serviço (Drive e Calendar pedem escopos diferentes), então é sempre o chamador quem
o informa — conceder Drive e esquecer Calendar é o erro comum, e é por isso que as sondas do
`check_integrations` são separadas.
"""

from __future__ import annotations

from django.conf import settings

# Endpoint de troca do refresh token por access token. Constante do Google, não configuração.
_TOKEN_URI = "https://oauth2.googleapis.com/token"

MODE_ADC = "adc"
MODE_OAUTH = "oauth"
MODES = (MODE_ADC, MODE_OAUTH)


class GoogleAuthError(Exception):
    """Não foi possível montar uma credencial do Google — configuração, não falha do fornecedor."""


def mode() -> str:
    return (settings.GOOGLE_AUTH_MODE or MODE_ADC).strip().lower()


def oauth_settings_missing() -> list[str]:
    """O que falta para o modo `oauth`. Vazio quando o modo não é esse.

    O modo `adc` **não aparece aqui de propósito**: no GKE não há variável nenhuma para conferir —
    a credencial vem do metadata server. Quem responde "isto funciona?" nesse caso é a sonda do
    `check_integrations`, que pergunta ao provedor em vez de ao ambiente. É a tese da FDD 024
    aplicada ao próprio mecanismo de autenticação.
    """
    if mode() != MODE_OAUTH:
        return []
    obrigatorias = {
        "GOOGLE_OAUTH_CLIENT_ID": settings.GOOGLE_OAUTH_CLIENT_ID,
        "GOOGLE_OAUTH_CLIENT_SECRET": settings.GOOGLE_OAUTH_CLIENT_SECRET,
        "GOOGLE_OAUTH_REFRESH_TOKEN": settings.GOOGLE_OAUTH_REFRESH_TOKEN,
    }
    return [nome for nome, valor in obrigatorias.items() if not valor]


def credentials(scopes: list[str]):  # pragma: no cover - I/O com o Google
    """Credencial para os escopos pedidos, pelo modo configurado."""
    escolhido = mode()
    if escolhido not in MODES:
        raise GoogleAuthError(
            f"GOOGLE_AUTH_MODE inválido: {escolhido!r}. Use um de: {', '.join(MODES)}."
        )
    if escolhido == MODE_OAUTH:
        return _oauth_credentials(scopes)
    return _adc_credentials(scopes)


def _adc_credentials(scopes: list[str]):  # pragma: no cover - I/O com o Google
    import google.auth
    from google.auth.exceptions import DefaultCredentialsError

    try:
        credencial, _ = google.auth.default(scopes=scopes)
    except DefaultCredentialsError as exc:
        raise GoogleAuthError(
            "Nenhuma credencial padrão encontrada. Em container, use Workload Identity; "
            "localmente, rode `gcloud auth application-default login`. Detalhe: " + str(exc)
        ) from exc
    return credencial


def _oauth_credentials(scopes: list[str]):  # pragma: no cover - I/O com o Google
    from google.oauth2.credentials import Credentials

    faltando = oauth_settings_missing()
    if faltando:
        raise GoogleAuthError(f"modo oauth sem {', '.join(faltando)}")
    # `token=None` de propósito: o access token nasce vencido e a primeira chamada o renova pelo
    # refresh token. Não guardamos access token em lugar nenhum — ele vive minutos.
    return Credentials(
        token=None,
        refresh_token=settings.GOOGLE_OAUTH_REFRESH_TOKEN,
        client_id=settings.GOOGLE_OAUTH_CLIENT_ID,
        client_secret=settings.GOOGLE_OAUTH_CLIENT_SECRET,
        token_uri=_TOKEN_URI,
        scopes=scopes,
    )
