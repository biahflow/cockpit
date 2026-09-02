"""Resolução das flags de integração: override em runtime sobre o default do ambiente.

Cada integração tem um default vindo do `.env` (`settings.*_ENABLED` ou a presença de uma
credencial) e pode ser ligada/desligada em runtime por um admin, gravando um `AppSetting`.
Segredos/keys continuam só no ambiente; aqui mora apenas o liga/desliga.

`configured(name)` diz se as credenciais necessárias estão presentes — sem elas o toggle não
deve ligar (a API recusa). A leitura do banco é protegida para não quebrar o boot/migrate
(quando a tabela `AppSetting` ainda não existe, cai no default do ambiente).
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field

from django.conf import settings
from django.db.utils import OperationalError, ProgrammingError


@dataclass(frozen=True)
class Flag:
    label: str
    env_default: Callable[[], bool]
    requires: tuple[str, ...] = field(default_factory=tuple)
    toggleable: bool = True
    # Grupos "um destes basta": exigir todos recusaria uma instalação legítima.
    requires_any: tuple[tuple[str, ...], ...] = field(default_factory=tuple)
    # Exigência que depende de outra configuração e não cabe numa lista fixa — hoje só a auth do
    # Google, cujo conjunto obrigatório muda com o `GOOGLE_AUTH_MODE` (ADR 0016).
    extra_missing: Callable[[], list[str]] | None = None


def _esign_missing() -> list[str]:
    """O que falta na assinatura eletrônica — e o conjunto depende de haver fornecedor.

    Sem `ESIGN_PROVIDER` a integração roda no `NullProvider`: registra a intenção de assinatura e
    espera o `mark-signed` manual, sem chamar ninguém e sem receber webhook. Esse modo não precisa
    de credencial nenhuma, e cobrá-la aqui desligaria um caminho que funciona — o que passou a
    importar quando `is_enabled` deixou de ignorar `configured()` (ADR 0018).

    Nomeado o fornecedor, os dois viram obrigatórios: sem token a chamada estoura, e sem o segredo
    do webhook o retorno de status leva 401 e a assinatura nunca fecha sozinha — a falha mais
    silenciosa desta integração.
    """
    if not settings.ESIGN_PROVIDER:
        return []
    return [
        key
        for key in ("ESIGN_API_TOKEN", "ESIGN_WEBHOOK_SECRET")
        if not getattr(settings, key, "")
    ]


def _payments_missing() -> list[str]:
    """O que falta no gateway de pagamento — mesma forma do e-sign, mesma razão (FDD 028).

    Sem `PAYMENTS_PROVIDER` a integração roda no `NullProvider`, e isso **não** é um modo degradado:
    a camada 0 inteira funciona sem gateway — emitir, acompanhar, vencer e baixar à mão. Cobrar
    credencial aqui desligaria a tela Financeiro numa instalação que nunca quis gateway nenhum.

    Nomeado o fornecedor, os dois viram obrigatórios: sem token a emissão estoura, e sem o segredo
    do webhook a baixa leva 401 e a fatura nunca fecha sozinha — que é a falha silenciosa desta
    integração, e a mais cara, porque a fatura fica cobrando quem já pagou.
    """
    if not settings.PAYMENTS_PROVIDER:
        return []
    return [
        key
        for key in ("PAYMENTS_API_TOKEN", "PAYMENTS_WEBHOOK_SECRET")
        if not getattr(settings, key, "")
    ]


def _google_auth_missing() -> list[str]:
    """O que falta na autenticação com o Google (ADR 0016).

    No modo `oauth`, o trio de credenciais. No modo `adc` — o default — **nada**, e isso é
    correto, não descuido: num pod com Workload Identity não existe variável de ambiente para
    conferir, a credencial vem do metadata server. Cobrar uma variável ali recusaria a instalação
    mais segura das duas.

    Quem responde "isto funciona?" nesse caso é a sonda do `check_integrations`, que pergunta ao
    provedor em vez de ao ambiente — a tese da FDD 024 aplicada ao próprio mecanismo de auth.
    """
    from . import google_auth

    return google_auth.oauth_settings_missing()


# `requires` lista o que o código realmente **dereferencia**, não só o que identifica a integração.
# Antes, cinco das sete flags podiam ser ligadas pela tela Configurações faltando a credencial que
# o adaptador usa na primeira chamada: Drive e Calendário pediam o id da pasta/agenda mas não a
# conta de serviço, e-sign pedia o nome do provedor mas não o token. A tela dizia "Ligada" e o
# recurso estourava — enquanto o `docs/operacao.md` promete que "o toggle só não liga uma
# integração cujas credenciais faltem no ambiente". Agora a promessa é verdade.
FLAGS: dict[str, Flag] = {
    "ai": Flag("Assistente de IA", lambda: bool(settings.AI_ENABLED), ("OPENAI_API_KEY",)),
    "drive": Flag(
        "Documentos no Google Drive",
        lambda: bool(settings.GOOGLE_DRIVE_ENABLED),
        ("GOOGLE_DRIVE_ROOT_FOLDER_ID",),
        extra_missing=_google_auth_missing,
    ),
    "calendar": Flag(
        "Calendário (Google)",
        lambda: bool(settings.CALENDAR_ENABLED),
        ("GOOGLE_CALENDAR_ID",),
        extra_missing=_google_auth_missing,
    ),
    "esign": Flag(
        "Assinatura eletrônica",
        lambda: bool(settings.ESIGN_ENABLED),
        extra_missing=lambda: _esign_missing(),
    ),
    "payments": Flag(
        "Gateway de pagamento",
        lambda: bool(settings.PAYMENTS_ENABLED),
        extra_missing=lambda: _payments_missing(),
    ),
    # SMTP tem default (`localhost:1025`, o Mailpit do compose), então não há variável cuja ausência
    # denuncie falta de configuração — em produção esse default é "lugar nenhum". Quem cobra aqui é
    # a sonda de `check_integrations`, que abre a conexão de verdade (FDD 024).
    "email": Flag("Notificações por e-mail e digest", lambda: bool(settings.EMAIL_NOTIFICATIONS_ENABLED)),
    "tasksync": Flag(
        "Sincronia de tarefas (Linear/GitHub)",
        # `TASKSYNC_TOKEN` é o segredo de **entrada**; sem credencial de fornecedor a saída fica
        # muda, que é o modo de falha que a ADR 0004 mais quer evitar.
        lambda: bool(settings.TASKSYNC_ENABLED),
        ("TASKSYNC_TOKEN",),
        requires_any=(("LINEAR_API_KEY", "GITHUB_TOKEN"),),
    ),
    # Provisionamento de GitHub Issue a partir de um handoff de engenharia (FDD 040, ADR 0040).
    # Distinto de `tasksync`: aqui a Issue é o Task Contract, não o espelho de uma `Task`.
    # Os dois `requires` são os que o adaptador dereferenceia — sem token a chamada nem sai,
    # sem repo o handoff sem `repository` próprio não tem para onde ir.
    "github_provisioning": Flag(
        "Provisionamento GitHub (engenharia)",
        lambda: bool(settings.GITHUB_PROVISIONING_ENABLED),
        ("GITHUB_TOKEN", "GITHUB_REPO"),
    ),
    # Projeção de entrega: lê Issue/PR/CI do GitHub para o Pulse (FDD 041, ADR 0046). Direção de
    # leitura, complementar ao provisionamento acima. `requires` são os dois que o código
    # dereferenceia: sem `GITHUB_WEBHOOK_SECRET` o webhook não autentica a entrada, sem
    # `GITHUB_TOKEN` a reconciliação por poll nem chama. `GITHUB_REPO` **não** entra: o repositório
    # é por-projeção, e exigi-lo recusaria uma instalação que projeta de vários repos.
    "github_delivery": Flag(
        "Projeção de entrega GitHub (Issue/PR/CI)",
        lambda: bool(settings.GITHUB_DELIVERY_ENABLED),
        ("GITHUB_TOKEN", "GITHUB_WEBHOOK_SECRET"),
    ),
    # Portal do cliente: o default é "ligado se URL+secret estão presentes", mas o admin pode
    # desligar pela tela sem mexer no ambiente — parar de emitir num incidente do portal era, antes,
    # trabalho de deploy. Quem respeita o toggle é `portal.emit`.
    "portal": Flag(
        "Portal do cliente",
        lambda: bool(settings.PORTAL_WEBHOOK_URL and settings.PORTAL_WEBHOOK_SECRET),
        ("PORTAL_WEBHOOK_URL", "PORTAL_WEBHOOK_SECRET"),
    ),
    # **`toggleable=False`, e não é zelo.** Para onde o arquivo vai não é algo que se liga e
    # desliga na tela: desligar deixaria órfão todo objeto já gravado no bucket, e ligar não
    # traria de volta o que está no disco. Quem decide é a variável de ambiente, e a tela diz
    # isso com todas as letras ("Controlada por variáveis de ambiente"). Desligada, o
    # documento continua no sistema de arquivos — que é o compose, e é onde ele é durável
    # porque há volume; no Cloud Run, sem bucket, ele morre na revisão seguinte.
    "storage": Flag(
        "Documentos no Cloud Storage",
        lambda: bool(settings.GCS_MEDIA_BUCKET),
        ("GCS_MEDIA_BUCKET",),
        toggleable=False,
    ),
    # Enriquecimento de lead (FDD 030). **Sem `requires`, e isso é correto**: o provedor default é
    # cadastro público e não pede credencial, então não existe variável cuja ausência denuncie
    # falta de configuração — cobrar uma recusaria a instalação que está certa. É o precedente do
    # modo `adc` do Google (ADR 0016), e quem responde "isto funciona?" é a sonda.
    "enrichment": Flag(
        "Enriquecimento de lead (CNPJ público)",
        lambda: bool(settings.ENRICHMENT_ENABLED),
    ),
    # Régua de cobrança (FDD 036). **Sem `requires`**, pelo precedente do `enrichment` logo acima:
    # a régua não fala com fornecedor nenhum — ela lê fatura, escreve registro e manda e-mail pelo
    # SMTP que a casa já usa —, então não existe variável cuja ausência denuncie falta de
    # configuração, e cobrar uma recusaria a instalação que está certa.
    #
    # **E `env_default` falso**, que é o oposto do `payments` acima e merece ser lido junto: o
    # gateway nasce ligado porque a camada 0 funciona inteira sem ele; a régua nasce desligada
    # porque a camada 1 — a reconciliação que a *desarma* — nunca foi homologada. Ligar antes
    # disso é cobrar quem já pagou, que é o único defeito desta funcionalidade que custa um
    # cliente. Ver `DUNNING_ENABLED` em `config/settings.py`.
    "cobranca": Flag(
        "Régua de cobrança",
        lambda: bool(settings.DUNNING_ENABLED),
    ),
    # Agendamento do Discovery pelo cliente (FDD 013, DAP `dap-agendamento-discovery-r1`). Governa
    # as duas rotas públicas **e** o e-mail que leva o link — as duas metades do mesmo ato, e
    # separá-las produziria o pior estado possível: o cliente recebe o convite e a página recusa.
    #
    # **Sem `requires`**, pelo precedente do `enrichment` e do `cobranca`: o convite sai pelo SMTP
    # que a casa já usa e o link se monta com `FRONTEND_BASE_URL`, que tem default — não existe
    # variável cuja ausência denuncie falta de configuração. A agenda em si é a flag `calendar`,
    # que as rotas conferem por conta própria, como as de booking já faziam.
    #
    # **E `env_default` falso**, como a régua de cobrança: esta é a primeira rota sem autenticação
    # do produto além do login, e o e-mail sai sozinho para fora da casa. Construir não é ligar.
    "discovery_booking": Flag(
        "Agendamento do Discovery pelo cliente",
        lambda: bool(settings.DISCOVERY_BOOKING_ENABLED),
    ),
}


def _override(name: str) -> bool | None:
    from .models import AppSetting

    try:
        setting = AppSetting.objects.filter(key=name).first()
    except (OperationalError, ProgrammingError):  # pragma: no cover - tabela ainda não migrada
        return None
    return setting.enabled if setting else None


def desired(name: str) -> bool:
    """A intenção declarada: o que o ambiente (ou o override do admin) **pede**, sem olhar credencial.

    `is_enabled` responde "isto funciona?"; esta responde "alguém pediu isto?". A diferença entre as
    duas é justamente o diagnóstico da sonda (FDD 024): pedida-e-quebrada não é a mesma coisa que
    desligada, e quem opera precisa saber qual das duas está vendo.
    """
    flag = FLAGS[name]
    if flag.toggleable:
        override = _override(name)
        if override is not None:
            return override
    return flag.env_default()


def is_enabled(name: str) -> bool:
    # Sem credencial não existe "ligada" — nem por default do ambiente, nem por override. A tela já
    # recusava ligar o que não está configurado (`ConfigView.patch`), mas o default do `.env` entrava
    # sem passar por essa porta: com `ESIGN_ENABLED=true` e nenhum token, o guard de 503 liberava a
    # ação e a falha só aparecia dentro do adaptador, como erro do fornecedor. Ver ADR 0018.
    return configured(name) and desired(name)


def configured(name: str) -> bool:
    """Todas as credenciais exigidas pela integração estão presentes no ambiente?"""
    return not missing(name)


def missing(name: str) -> list[str]:
    """O que falta para a integração poder ser ligada — em nome de variável, para quem vai corrigir."""
    flag = FLAGS[name]
    faltando = [key for key in flag.requires if not getattr(settings, key, "")]
    faltando += [
        " ou ".join(grupo)
        for grupo in flag.requires_any
        if not any(getattr(settings, key, "") for key in grupo)
    ]
    if flag.extra_missing is not None:
        faltando += flag.extra_missing()
    return faltando


def status(name: str) -> dict[str, object]:
    flag = FLAGS[name]
    faltando = missing(name)
    return {
        "key": name,
        "label": flag.label,
        "enabled": is_enabled(name),
        "configured": not faltando,
        "toggleable": flag.toggleable,
        # A tela dizia só "faltam credenciais"; quem ia corrigir tinha de abrir o código para
        # descobrir quais. O nome da variável é o que resolve o problema de quem lê.
        "missing": faltando,
    }


def all_status() -> list[dict[str, object]]:
    return [status(name) for name in FLAGS]
