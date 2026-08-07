"""Enriquecimento de lead atrás de flag (`enrichment`), agnóstico de fornecedor (FDD 030).

O que ele faz é estreito de propósito: pega o CNPJ que o formulário coletou, busca o **cadastro
público** daquela empresa e devolve o que a qualificação que já existe consegue usar — setor
(CNAE), porte, capital social, situação cadastral, praça. Nada disso é score novo. A FDD 030 é
explícita: o objetivo é **melhorar o `ai_fit`**, não produzir um segundo número que discorde do
primeiro sem que ninguém saiba qual olhar.

O molde é o de `esign.py` e `payments.py` — `Protocol`, `NullProvider`, flag, sonda —, com uma
diferença que vale registrar: aqui o `NullProvider` **não** é um modo previsto de operação, é a
ausência do recurso. Sem provedor a qualificação roda exatamente como rodava antes, que é o
comportamento certo e é também o que a regressão crítica cobra.

**Falha do fornecedor não bloqueia nada.** É a regressão crítica nomeada na FDD 030, e a razão é
a mesma que fez `qualification.qualify_lead` engolir a exceção da OpenAI: isto roda **dentro do
POST público** do formulário do site, e o `Lead` já está gravado quando a chamada sai. Um 500 do
BrasilAPI virando 500 para o visitante seria o portal reportando falha de um cadastro que
funcionou. Sem enriquecimento, o lead segue para a qualificação como sempre seguiu.

**O CNAE preenche a vertical quando dá, e cala quando não dá.** `infer_vertical_slug` mapeia a
divisão do CNAE (os dois primeiros dígitos) para um slug canônico, e quem decide se aquilo existe
é o banco: a `Vertical` é taxonomia editável pelo admin (FDD 026), não enum, então um slug que
ninguém cadastrou simplesmente não vira vertical nenhuma. Inventar a linha aqui seria o portal
criando vocabulário de negócio por conta própria a partir de uma tabela do IBGE.

As chamadas HTTP reais ficam fora da cobertura (`# pragma: no cover`), como em `esign.py` e
`payments.py`.
"""

from __future__ import annotations

import json
import logging
import re
import urllib.error
import urllib.request
from dataclasses import asdict, dataclass
from typing import TYPE_CHECKING, Protocol

from django.conf import settings

from . import flags

if TYPE_CHECKING:
    from .models import Lead, Vertical

logger = logging.getLogger(__name__)


def is_enabled() -> bool:
    return flags.is_enabled("enrichment")


@dataclass(frozen=True)
class Company:
    """O cadastro público de uma empresa, já no vocabulário do Biahflow."""

    cnpj: str = ""
    legal_name: str = ""
    trade_name: str = ""
    cnae_code: str = ""
    cnae_label: str = ""
    size: str = ""
    share_capital: str = ""
    status: str = ""
    city: str = ""
    state: str = ""
    opened_on: str = ""


class EnrichmentProvider(Protocol):
    def fetch(self, cnpj: str) -> Company | None: ...


class NullProvider:
    """Sem fornecedor não há enriquecimento — e a qualificação roda como sempre rodou."""

    def fetch(self, cnpj: str) -> Company | None:
        return None


class BrasilApiProvider:
    """Cadastro público de CNPJ pela BrasilAPI.

    Sem credencial por desenho — é dado público da Receita Federal reexposto —, e é por isso que
    a flag não tem `requires`. O que a instalação decide não é "tenho a chave?", é "quero que o
    CNPJ do formulário saia daqui?".
    """

    DEFAULT_BASE = "https://brasilapi.com.br/api/v1/cnpj/v1"

    def __init__(self, base: str = "") -> None:
        self.base = (base or self.DEFAULT_BASE).rstrip("/")

    def fetch(self, cnpj: str) -> Company | None:  # pragma: no cover - I/O com a BrasilAPI
        payload = self._get(f"{self.base}/{cnpj}")
        return None if payload is None else self.parse(cnpj, payload)

    def ping(self) -> tuple[bool, str]:  # pragma: no cover - I/O com a BrasilAPI
        """Consulta um CNPJ conhecido e público: leitura pura, sem custo e sem efeito.

        O CNPJ do Banco do Brasil é a escolha deliberada de uma sonda que não depende de dado da
        casa — sondar com o CNPJ de um cliente faria a saúde da integração variar com a situação
        cadastral de terceiro.
        """
        payload = self._get(f"{self.base}/00000000000191")
        if payload is None:
            return False, "BrasilAPI não devolveu cadastro para o CNPJ de sonda"
        return True, f"BrasilAPI respondeu ({payload.get('razao_social', 'sem razão social')})"

    def _get(self, url: str) -> dict | None:  # pragma: no cover - I/O com a BrasilAPI
        request = urllib.request.Request(url, headers={"Accept": "application/json"})
        with urllib.request.urlopen(request, timeout=settings.ENRICHMENT_TIMEOUT_SECONDS) as answer:
            body = json.loads(answer.read().decode("utf-8"))
        return body if isinstance(body, dict) else None

    @staticmethod
    def parse(cnpj: str, payload: dict) -> Company:
        """Traduz o corpo da BrasilAPI para `Company`. Puro, e testado sem rede."""
        return Company(
            cnpj=cnpj,
            legal_name=str(payload.get("razao_social") or ""),
            trade_name=str(payload.get("nome_fantasia") or ""),
            # O campo vem inteiro (7 dígitos) e é assim que ele é guardado; a divisão é derivada
            # na leitura por `infer_vertical_slug`, e não gravada — dois campos para o mesmo fato
            # divergem no dia em que alguém corrigir só um.
            cnae_code=str(payload.get("cnae_fiscal") or ""),
            cnae_label=str(payload.get("cnae_fiscal_descricao") or ""),
            size=str(payload.get("porte") or ""),
            share_capital=str(payload.get("capital_social") or ""),
            status=str(payload.get("descricao_situacao_cadastral") or ""),
            city=str(payload.get("municipio") or ""),
            state=str(payload.get("uf") or ""),
            opened_on=str(payload.get("data_inicio_atividade") or ""),
        )


def get_provider() -> EnrichmentProvider:
    if settings.ENRICHMENT_PROVIDER == "brasilapi":
        return BrasilApiProvider(settings.ENRICHMENT_API_BASE)
    return NullProvider()


def normalize_cnpj(raw: str) -> str:
    """Só os dígitos, e só se forem catorze. Devolve vazio quando não é um CNPJ.

    A validação para em comprimento de propósito: conferir o dígito verificador recusaria um CNPJ
    digitado com um erro de digitação, e o desfecho certo para isso é o fornecedor responder "não
    encontrei" — não o formulário público recusar o lead. Um lead vale mais que um cadastro limpo.
    """
    digits = re.sub(r"\D", "", raw or "")
    return digits if len(digits) == 14 else ""


# Divisão do CNAE (os dois primeiros dígitos, a "Divisão" do IBGE) → slug canônico de vertical.
#
# Divisão e não a seção inteira: a seção agrupa demais para o que a FDD 026 chama de "a consultoria
# de IA para *este* setor" — comércio e transporte caem na mesma seção G/H numa leitura grosseira e
# são mercados completamente diferentes para esta casa. E não o CNAE de 7 dígitos, que discrimina
# demais: haveria mil e tantas chaves e nenhuma vertical cadastrada para casar com elas.
#
# O mapa é intencionalmente incompleto. O que não está aqui não vira vertical, e isso é a resposta
# certa — inventar "outros" produziria um balde em que setores distintos se escondem juntos, que é
# exatamente o que a `Vertical` existe para desfazer.
_CNAE_DIVISION_TO_SLUG: dict[str, str] = {
    **{f"{d:02d}": "agro" for d in range(1, 4)},
    **{f"{d:02d}": "industria" for d in (*range(5, 10), *range(10, 34))},
    **{f"{d:02d}": "energia" for d in range(35, 40)},
    **{f"{d:02d}": "construcao" for d in range(41, 44)},
    **{f"{d:02d}": "varejo" for d in range(45, 48)},
    **{f"{d:02d}": "logistica" for d in range(49, 54)},
    **{f"{d:02d}": "hospitalidade" for d in range(55, 57)},
    **{f"{d:02d}": "tecnologia" for d in range(58, 64)},
    **{f"{d:02d}": "financeiro" for d in range(64, 67)},
    "68": "imobiliario",
    **{f"{d:02d}": "servicos-profissionais" for d in (*range(69, 76), *range(77, 83))},
    "84": "setor-publico",
    "85": "educacao",
    **{f"{d:02d}": "saude" for d in range(86, 89)},
    **{f"{d:02d}": "midia" for d in range(90, 94)},
    **{f"{d:02d}": "servicos-profissionais" for d in range(94, 97)},
}


def infer_vertical_slug(cnae_code: str) -> str:
    """O slug de vertical que aquele CNAE sugere, ou vazio.

    O CNAE vem sem pontuação e com 6 ou 7 dígitos conforme a fonte; a divisão são sempre os dois
    primeiros. Zero-padding à esquerda porque a agropecuária é a divisão `01` e um inteiro a
    entrega como `1`.
    """
    digits = re.sub(r"\D", "", cnae_code or "")
    if len(digits) < 3:
        return ""
    return _CNAE_DIVISION_TO_SLUG.get(digits.zfill(7)[:2], "")


def infer_vertical(cnae_code: str) -> Vertical | None:
    """A `Vertical` cadastrada que corresponde àquele CNAE, se alguém a cadastrou.

    Quem decide é o banco, não o mapa: a vertical é taxonomia que o admin edita (FDD 026), e um
    slug sem linha correspondente não vira vertical nenhuma. Inativa também não conta — ela some
    das escolhas novas por decisão de quem administra, e o enriquecimento não é exceção a isso.
    """
    from .models import Vertical as VerticalModel

    slug = infer_vertical_slug(cnae_code)
    if not slug:
        return None
    return VerticalModel.objects.filter(slug=slug, active=True).first()


def enrich_lead(lead: Lead) -> bool:
    """Busca o cadastro do CNPJ do lead e o grava. Devolve se enriqueceu. **Nunca levanta.**

    No-op quando a integração está desligada ou o lead não trouxe CNPJ — os dois casos deixam o
    lead exatamente como estava, para a qualificação seguir o caminho de sempre.
    """
    if not is_enabled():
        return False
    cnpj = normalize_cnpj(lead.cnpj)
    if not cnpj:
        return False

    try:
        company = get_provider().fetch(cnpj)
    except (urllib.error.URLError, TimeoutError, ValueError, OSError):
        # Mesmo desfecho da falha da OpenAI em `qualify_lead`, e pelo mesmo motivo: o visitante
        # não pode ver erro por causa de um enriquecimento que é melhoria. `exception` e não
        # `warning` porque quem opera precisa do traceback para distinguir fornecedor fora do ar
        # de contrato mudado — as duas se parecem daqui.
        logger.exception("enriquecimento do lead %s falhou; segue sem cadastro", lead.pk)
        return False

    if company is None:
        return False

    lead.enrichment = asdict(company)
    lead.save(update_fields=["enrichment", "updated_at"])
    return True


def summary_lines(enrichment: dict) -> list[str]:
    """O cadastro em linhas para o contexto da IA. Só o que a qualificação consegue usar.

    Fora daqui de propósito: `cnpj`, que o modelo não precisa ver para julgar fit e cuja presença
    no prompt só aumentaria a superfície de dado pessoal enviada ao fornecedor de IA.
    """
    if not enrichment:
        return []
    campos = (
        ("Razão social", "legal_name"),
        ("Nome fantasia", "trade_name"),
        ("Setor (CNAE)", "cnae_label"),
        ("Porte", "size"),
        ("Capital social", "share_capital"),
        ("Situação cadastral", "status"),
        ("Início de atividade", "opened_on"),
    )
    linhas = [f"{rotulo}: {enrichment[chave]}" for rotulo, chave in campos if enrichment.get(chave)]
    cidade, uf = enrichment.get("city", ""), enrichment.get("state", "")
    if cidade or uf:
        linhas.append(f"Praça: {'/'.join(parte for parte in (cidade, uf) if parte)}")
    return linhas
