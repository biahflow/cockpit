"""Como este serviço se identifica **para outro serviço nosso** (ADR 0029).

Não confundir com `google_auth.py`, que é como o portal se autentica **no Google**
para falar com Drive e Calendar (ADR 0016). São perguntas diferentes: lá o token é de
acesso com escopo, aqui é ID token com audiência, e o alvo é um Cloud Run nosso.

**Por que existe.** Em homologação a `portal-api` do portal do cliente sobe com ingress
interno **e** `run.invoker` concedido a uma conta só. Uma requisição sem identidade leva
403 do Cloud Run **antes de a aplicação existir** — não há log nosso, não há corpo, e o
webhook simplesmente não chega. A conta que este processo já usa é exatamente a que tem a
permissão; faltava apresentá-la.

É a tradução de `app/lib/serviceIdentity.ts` do repositório do portal do cliente, e a ADR
0048 de lá previu esta falta com todas as letras: *"não há equivalente em Python"*. Ela
escreveu isso sobre o sentido oposto (`portal-api → biahflow-api`), que hoje não dói
porque aquele serviço está aberto. Este módulo fecha **o nosso lado**, e só ele.

**O header é `Authorization` puro, e isso é diferente do BFF.** Lá o `Authorization` já
carregava o token do usuário, então o de serviço teve de ir em
`X-Serverless-Authorization` — o Cloud Run consome esse e não o repassa, deixando o outro
intacto. Aqui a rota do webhook autentica por HMAC em header próprio
(`X-Biahflow-Signature`) e nunca lê `Authorization`, então não há o que preservar.
"""

from __future__ import annotations

import logging
import os
import time
from urllib.parse import urlsplit

logger = logging.getLogger(__name__)

#: Margem antes da expiração. Um token que vence no voo vira 403 intermitente — o pior
#: tipo, porque some quando alguém vai olhar.
MARGEM_SEGUNDOS = 300

#: Quanto guardar quando a expiração não é legível. Guardar pouco é melhor que não
#: guardar: o caminho quente não pode pagar uma chamada de rede por evento, e os
#: emissores de webhook são doze (`signals.py`).
FALLBACK_SEGUNDOS = 600

_cache: dict[str, tuple[str, float]] = {}


def rodando_no_cloud_run() -> bool:
    """`K_SERVICE` é posto pelo próprio Cloud Run.

    **A guarda não é zelo.** Fora dele — a máquina de alguém, o compose, o CI — não há
    servidor de metadados, e tentar buscar token custaria um timeout para conseguir
    nada. O agravante é onde isso rodaria: `portal._post` vive numa thread daemon com
    5 s de timeout total, então cada webhook pagaria a espera inteira e chegaria tarde
    ou não chegaria.
    """
    return bool(os.environ.get("K_SERVICE"))


def audiencia_de(url: str) -> str | None:
    """A audiência é a URL **base** do serviço chamado, sem caminho.

    `https://portal-api-123.us-east1.run.app/api/v1/integrations/...` tem audiência
    `https://portal-api-123.us-east1.run.app`. Mandar o caminho junto produz um token
    que o Cloud Run recusa, e a mensagem fala de audiência inválida — não de URL.
    """
    partes = urlsplit(url)
    if not partes.scheme or not partes.netloc:
        return None
    return f"{partes.scheme}://{partes.netloc}"


def limpar_cache() -> None:
    """Só para teste: esquece o que está guardado."""
    _cache.clear()


def id_token_para(url_do_servico: str) -> str | None:
    """ID token para chamar `url_do_servico`, ou `None` quando não há como cunhar.

    **Devolve `None` em vez de levantar**, e isso é contrato: quem chama é uma emissão
    best-effort (`portal.emit`), e transformar "não estou no Cloud Run" em exceção faria
    o compose e a suíte quebrarem num caminho que ali nem existe.
    """
    if not rodando_no_cloud_run():
        return None

    audiencia = audiencia_de(url_do_servico)
    if audiencia is None:
        return None

    agora = time.time()
    guardado = _cache.get(audiencia)
    if guardado is not None and guardado[1] - MARGEM_SEGUNDOS > agora:
        return guardado[0]

    try:
        # Import tardio: `google.auth` só é necessário dentro do Cloud Run, e no caminho
        # do compose nem o import precisa acontecer.
        import google.auth.transport.requests
        from google.oauth2 import id_token as google_id_token

        valor = google_id_token.fetch_id_token(
            google.auth.transport.requests.Request(), audiencia
        )
    except Exception as erro:  # noqa: BLE001 — qualquer falha aqui é "sem token"
        logger.warning(
            "service_identity.sem_token", extra={"audiencia": audiencia, "erro": str(erro)}
        )
        return None

    if not valor:
        return None

    _cache[audiencia] = (valor, agora + FALLBACK_SEGUNDOS)
    return valor
