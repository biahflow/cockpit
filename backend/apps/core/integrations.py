"""Sondas de integração: a credencial existe **e funciona**? (FDD 024)

`flags.configured()` responde se a variável de ambiente está preenchida — o que não distingue uma
chave válida de um `sk-xxx` colado errado, e a tela Configurações mostra "configurado" para as
duas. Aqui a pergunta é outra: **o provedor aceita esta credencial?**

É o irmão do `backup.read_backup_status` (FDD 021) e segue as mesmas duas regras:

- **Nunca levanta.** Este é o caminho do diagnóstico. Comando de diagnóstico que estoura com
  traceback vira "o diagnóstico quebrou" em vez de "a integração quebrou", que é o oposto do que
  ele existe para dizer.
- **Nada de efeito colateral.** Toda sonda é leitura, e nenhuma gera token, cria arquivo, manda
  e-mail ou abre documento para assinatura. Um diagnóstico que cobra da conta de quem o roda não
  é rodado.

Cada sonda **reusa o construtor de cliente do próprio adaptador** (`ai._client`, `drive._service`,
`calendar_sync._service`) em vez de montar um caminho paralelo. É o que faz a sonda valer: se a
credencial estiver malformada, quem estoura é o mesmo código que estouraria em produção.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass

from django.conf import settings

from . import flags

logger = logging.getLogger(__name__)

# Sonda que não existe para uma integração não é falha — é ausência de sonda, e dizer "FALHOU"
# aqui treinaria quem opera a ignorar o comando.
NAO_SONDAVEL = "sem sonda disponível; só o primeiro uso real valida"


@dataclass(frozen=True)
class ProbeResult:
    name: str
    label: str
    enabled: bool
    configured: bool
    # `None` = não sondada (desligada, ou sem sonda). Só `False` é reprovação.
    ok: bool | None
    detail: str

    @property
    def reprovou(self) -> bool:
        return self.ok is False


def _probe_ai() -> tuple[bool, str]:
    """Recupera o modelo configurado: valida a chave **e** o acesso ao modelo, sem gerar token."""
    from . import ai

    modelo = settings.AI_MODEL
    ai._client().models.retrieve(modelo)
    return True, f"modelo {modelo} acessível"


def _probe_drive() -> tuple[bool, str]:
    """Lista um item da pasta raiz: valida credencial, escopo e existência do Shared Drive."""
    from . import drive

    raiz = drive.root_folder_id()
    drive._service().files().list(
        q=f"'{raiz}' in parents",
        pageSize=1,
        fields="files(id)",
        supportsAllDrives=True,
        includeItemsFromAllDrives=True,
    ).execute()
    return True, f"pasta raiz {raiz} acessível"


def _probe_calendar() -> tuple[bool, str]:
    """Lê o calendário configurado. Mesma service account do Drive, outro escopo — por isso a
    sonda é separada: conceder Drive e esquecer Calendar é o erro comum, e ele passaria batido."""
    from . import calendar_sync

    agenda = settings.GOOGLE_CALENDAR_ID
    dados = calendar_sync._service().calendars().get(calendarId=agenda).execute()
    return True, f"calendário '{dados.get('summary', agenda)}' acessível"


def _probe_esign() -> tuple[bool, str]:
    """Pergunta ao fornecedor quem é o dono do token, sem criar documento."""
    from . import esign

    provider = esign.get_provider()
    ping = getattr(provider, "ping", None)
    if ping is None:
        return True, f"{settings.ESIGN_PROVIDER or 'nenhum provedor'}: {NAO_SONDAVEL}"
    return ping()


def _probe_email() -> tuple[bool, str]:
    """Abre e fecha a conexão SMTP. Não envia nada — sonda que manda e-mail vira spam diário."""
    from django.core.mail import get_connection

    conexao = get_connection(fail_silently=False)
    conexao.open()
    try:
        return True, f"SMTP {settings.EMAIL_HOST}:{settings.EMAIL_PORT} respondeu"
    finally:
        conexao.close()


def _probe_tasksync() -> tuple[bool, str]:
    """Sem credencial nesta instalação; implementada para quando houver."""
    return True, NAO_SONDAVEL


def _probe_portal() -> tuple[bool, str]:
    """O portal do cliente é destino de webhook, não fonte: sondá-lo exigiria entregar um evento
    de mentira a um sistema de produção. O snapshot é quem prova o caminho, sob demanda."""
    return True, NAO_SONDAVEL


PROBES = {
    "ai": _probe_ai,
    "drive": _probe_drive,
    "calendar": _probe_calendar,
    "esign": _probe_esign,
    "email": _probe_email,
    "tasksync": _probe_tasksync,
    "portal": _probe_portal,
}


def _faltando(name: str) -> str:
    return ", ".join(flags.missing(name))


def _executar(name: str) -> tuple[bool, str]:
    """Roda a sonda e traduz exceção em reprovação. Nunca propaga."""
    try:
        return PROBES[name]()
    except Exception as exc:  # noqa: BLE001 - diagnóstico não pode estourar
        # A mensagem do provedor é o produto desta função: é ela que diz se o problema é chave
        # inválida, escopo faltando ou recurso inexistente.
        motivo = str(exc).strip() or exc.__class__.__name__
        logger.warning("sonda de %s falhou: %s", name, motivo)
        return False, motivo


def probe(name: str) -> ProbeResult:
    """Sonda uma integração. Desligada não é sondada; sem credencial reprova antes de gastar rede."""
    flag = flags.FLAGS[name]
    enabled = flags.is_enabled(name)
    configured = flags.configured(name)

    if not enabled:
        return ProbeResult(name, flag.label, enabled, configured, None, "desligada")
    if not configured:
        detalhe = f"ligada, mas falta no ambiente: {_faltando(name)}"
        return ProbeResult(name, flag.label, enabled, configured, False, detalhe)

    ok, detalhe = _executar(name)
    return ProbeResult(name, flag.label, enabled, configured, ok, detalhe)


def probe_all(*, incluir_desligadas: bool = False) -> list[ProbeResult]:
    if incluir_desligadas:
        return [_forcado(nome) for nome in flags.FLAGS]
    return [probe(nome) for nome in flags.FLAGS]


def _forcado(name: str) -> ProbeResult:
    """Sonda mesmo desligada — para conferir credencial **antes** de ligar a integração."""
    if flags.is_enabled(name):
        return probe(name)

    flag = flags.FLAGS[name]
    configured = flags.configured(name)
    if not configured:
        detalhe = f"desligada; falta {_faltando(name) or 'nada'}"
        return ProbeResult(name, flag.label, False, configured, None, detalhe)

    ok, detalhe = _executar(name)
    return ProbeResult(name, flag.label, False, configured, ok, f"(desligada) {detalhe}")
