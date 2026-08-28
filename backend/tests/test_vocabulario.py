"""A guarda do vocabulário canônico (ADR 0049, `docs/ontology/language-map.md` §6).

**Ela casa declaração, e não referência — essa é a decisão inteira.** A tentação, ao ler "nenhum
identificador novo contém `opportunity` sem qualificador", é escrever um `grep opportunity` e
reprovar a linha. Isso reprovaria 460 ocorrências de código legítimo: um `self.opportunity`, um
`opportunity_id` de filtro, um `from .models import Opportunity` são *usos* do modelo que existe
hoje, e o modelo existe hoje porque o renome físico é a Fase 6. Uma guarda que reprova o que o
repositório precisa fazer para funcionar é desligada na primeira semana, e aí não protege nada.

O que a invariante §6 proíbe é **batizar** coisa nova com o nome errado. Batizar tem forma
sintática: `class X`, `campo = models.…`, `router.register(...)`, `path(...)`, `type X`,
`interface X`, `const X`, `function X`. Só essas linhas são medidas. O alias legado continua
podendo ser referenciado à vontade; o que não se pode é criar mais um.

Três exceções são deliberadas e as fases seguintes dependem delas (ver `docs/ontology/aliases.md`):

* prefixo `legacy_` — `legacy_opportunity`, `legacy_evidencia` nomeiam explicitamente o mapeamento
  para o registro antigo, e esconder esse mapeamento atrás de um nome bonito é o defeito, não a
  correção;
* `commercial_` / `improvement_` — são exatamente os qualificadores que a §5 pede;
* um campo chamado `account` apontando para o modelo `Client` — é o nome canônico apontando para o
  modelo legado, que é o passo 1 de toda migração de nome. A regra `client-como-organizacao` casa
  `client`, nunca `account`.

`GateOutcome`/`gate_outcome` é a única regra em que a **referência** é o problema: ali o
identificador inteiro está errado, não o contexto — não existe uso legítimo do nome antigo.

A allowlist (`docs/ontology/legacy-allowlist.txt`) nasce com o estado de `main`, nem uma entrada a
mais, e três testes a mantêm honesta: o que ela isenta precisa existir (senão a linha sai), e o
total só desce. É o mesmo desenho de `frontend/src/test/primitivas.test.ts`, pela mesma razão:
allowlist que ninguém revisa vira permissão permanente.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

from django.conf import settings

REPO_ROOT = Path(settings.BASE_DIR).parent
ALLOWLIST = REPO_ROOT / "docs" / "ontology" / "legacy-allowlist.txt"

# --------------------------------------------------------------------------------------------
# Escopo de varredura
# --------------------------------------------------------------------------------------------

# Uma guarda só, varrendo os dois lados, em vez de duas metades que divergem. Ela roda no
# `uv run pytest`, fora de `--cov=apps.core` e fora do `exclude` do mypy — não mexe em cobertura
# nem em type-check.
ESCOPO_BACKEND = "backend"
ESCOPO_FRONTEND = "frontend"
ESCOPO_TUDO = "tudo"
# `models.py`, `serializers.py` e `views.py`: onde o backend batiza entidade. A heurística de
# português é agressiva por natureza e fica restrita ao lugar onde o nome de modelo nasce.
ESCOPO_NUCLEO = "nucleo"

NUCLEO_DO_BACKEND = ("models.py", "serializers.py", "views.py")


def _fontes_do_backend() -> list[Path]:
    """`backend/apps/**/*.py`, sem `migrations/` (histórico congelado) nem `tests/`."""
    raiz = REPO_ROOT / "backend" / "apps"
    return sorted(
        arquivo
        for arquivo in raiz.rglob("*.py")
        if "migrations" not in arquivo.parts and "tests" not in arquivo.parts
    )


def _fontes_do_frontend() -> list[Path]:
    """`frontend/src/**/*.{ts,tsx}`, sem `*.test.*` nem `src/test/`."""
    raiz = REPO_ROOT / "frontend" / "src"
    arquivos = [*raiz.rglob("*.ts"), *raiz.rglob("*.tsx")]
    return sorted(
        arquivo
        for arquivo in arquivos
        if "test" not in arquivo.parts and ".test." not in arquivo.name
    )


def _arquivos(escopo: str) -> list[Path]:
    if escopo == ESCOPO_BACKEND:
        return _fontes_do_backend()
    if escopo == ESCOPO_FRONTEND:
        return _fontes_do_frontend()
    if escopo == ESCOPO_NUCLEO:
        return [a for a in _fontes_do_backend() if a.name in NUCLEO_DO_BACKEND]
    return [*_fontes_do_backend(), *_fontes_do_frontend()]


# --------------------------------------------------------------------------------------------
# Regras
# --------------------------------------------------------------------------------------------

# Marcadores de português que aparecem **em qualquer posição** do nome da classe. Lista fechada e
# comentada de propósito: um teste que reprova por heurística aberta reprova o legítimo, e a
# reação a isso é desligá-lo.
MARCADORES_PT = (
    "ç",
    "ã",
    "õ",
    "Evidencia",
    "Processo",
    "Decisao",
    "Pendencia",
    "Satisfacao",
    "Cobranca",
    "Risco",
)
# Sufixos: só valem no **fim** do nome. `Management` contém `agem` no meio e é inglês legítimo;
# `Contagem` termina em `agem` e não é. A diferença entre reprovar um e não o outro é esta.
SUFIXOS_PT = (
    "cao",
    "coes",
    "encia",
    "ancia",
    "mento",
    "agem",
    "dade",
    "eiro",
    "orio",
    "aria",
)

_MARCADORES = "|".join(MARCADORES_PT)
_SUFIXOS = "|".join(SUFIXOS_PT)


@dataclass(frozen=True)
class Regra:
    """Uma invariante de linguagem.

    `padrao` casa **uma linha de declaração** e captura o identificador batizado em um dos seus
    grupos (só um casa por vez). `isentos` são fragmentos que, presentes no identificador, tornam
    o nome legítimo — é onde moram `legacy_`, `commercial_` e o contexto HTTP/SDK de `client`.
    """

    id: str
    padrao: re.Pattern[str]
    arquivos: str
    mensagem: str
    isentos: tuple[str, ...] = ()


REGRAS: tuple[Regra, ...] = (
    Regra(
        id="opportunity-sem-qualificador",
        padrao=re.compile(
            r"^\s*class\s+(\w*opportunity\w*)"
            r"|^\s*(\w*opportunity\w*)\s*=\s*models\."
            r"|^\s*(?:router\.register|path|re_path)\(\s*[\"'](\w*opportunit\w*)"
            r"|^\s*(?:export\s+)?(?:type|interface|const|function)\s+(\w*opportunity\w*)\b",
            re.IGNORECASE,
        ),
        arquivos=ESCOPO_TUDO,
        mensagem="use CommercialOpportunity ou ImprovementOpportunity — `Opportunity` sozinho "
        "colide entre venda e melhoria operacional (language-map §5)",
        isentos=("commercial", "improvement", "legacy"),
    ),
    Regra(
        id="client-como-organizacao",
        # `client` **no início** do nome do tipo, não em qualquer posição. A distinção não é
        # estética: a organização se chama `Client…` (`Client`, `ClientSerializer`,
        # `ClientViewSet`, `ClientOverview`), enquanto um cliente de protocolo se chama
        # `…Client` (`GitHubIssuesClient`, `GithubDeliveryReadClient`, `APIClient`). Casar
        # `\w*client\w*` reprovaria os dois integradores de GitHub, que são exatamente o
        # contexto HTTP/SDK que a issue declara permitido — e uma isenção por nome de sistema
        # ("github") envelheceria no primeiro integrador novo. Campo e rota continuam casando em
        # qualquer posição, porque ali não existe o cliente de protocolo.
        padrao=re.compile(
            r"^\s*class\s+(client\w*)"
            r"|^\s*(\w*client\w*)\s*=\s*models\."
            r"|^\s*(?:router\.register|path|re_path)\(\s*[\"'](\w*client\w*)"
            r"|^\s*(?:export\s+)?(?:type|interface)\s+(client\w*)\b",
            re.IGNORECASE,
        ),
        arquivos=ESCOPO_TUDO,
        mensagem="use Account — a organização é Account desde prospect, e 'cliente' é rótulo de "
        "UI com `lifecycle_status=active` (language-map §5)",
        # `api_client`, `http_client`, `test_client` e o prefixo `legacy_` continuam legítimos
        # como nome de campo.
        isentos=("api", "http", "test", "sdk", "legacy"),
    ),
    Regra(
        id="outcome-como-decisao-de-gate",
        # A única regra que casa **referência**: o identificador inteiro está errado, em qualquer
        # posição. `Outcome` de negócio é `Measurement(kind=outcome)` e nada tem a ver com gate.
        padrao=re.compile(r"\b(gateoutcome\w*|gate_outcome\w*)", re.IGNORECASE),
        arquivos=ESCOPO_TUDO,
        mensagem="use GateDecision — `GateOutcome` colide com o Outcome de negócio (D7)",
    ),
    Regra(
        id="modelo-em-portugues",
        padrao=re.compile(rf"^\s*class\s+(\w*(?:{_MARCADORES})\w*|\w*(?:{_SUFIXOS}))\(", re.I),
        arquivos=ESCOPO_NUCLEO,
        mensagem="nomeie o modelo em inglês — termo canônico em inglês nas quatro superfícies "
        "(language-map §1)",
    ),
    Regra(
        id="legado-congelado",
        # Os quatro nomes que a Fase 3 divide e a Fase 6 renomeia. Enquanto a dívida existe ela
        # fica declarada na allowlist; classe **nova** com esses nomes reprova aqui.
        padrao=re.compile(r"^\s*class\s+(ProcessoEtapa|Processo|Evidencia|GateOutcome)\b"),
        arquivos=ESCOPO_BACKEND,
        mensagem="use Evidence / Process / ProcessStep / GateDecision (language-map §5)",
    ),
)


# --------------------------------------------------------------------------------------------
# Varredura
# --------------------------------------------------------------------------------------------


@dataclass(frozen=True)
class Achado:
    caminho: str
    linha: int
    regra: str
    identificador: str

    @property
    def chave(self) -> str:
        """A entrada da allowlist. **Sem número de linha**, de propósito: uma dívida declarada
        não pode ser reaberta por alguém ter inserido um import acima dela."""
        return f"{self.caminho}::{self.regra}::{self.identificador}"

    def __str__(self) -> str:
        return f"{self.caminho}:{self.linha} — {self.identificador} [{self.regra}]"


def achados_na_linha(regra: Regra, caminho: str, numero: int, linha: str) -> list[Achado]:
    """Aplica uma regra a uma linha. Público porque a própria guarda tem teste unitário."""
    achados: list[Achado] = []
    for m in regra.padrao.finditer(linha):
        identificador = next((g for g in m.groups() if g), None)
        if identificador is None:
            continue
        alvo = identificador.casefold()
        if any(isento in alvo for isento in regra.isentos):
            continue
        achados.append(Achado(caminho, numero, regra.id, identificador))
    return achados


def varrer() -> list[Achado]:
    """Todo achado do repositório, antes de descontar a allowlist."""
    achados: list[Achado] = []
    for regra in REGRAS:
        for arquivo in _arquivos(regra.arquivos):
            caminho = arquivo.relative_to(REPO_ROOT).as_posix()
            linhas = arquivo.read_text(encoding="utf-8").splitlines()
            for numero, linha in enumerate(linhas, start=1):
                achados.extend(achados_na_linha(regra, caminho, numero, linha))
    return achados


def entradas_da_allowlist() -> list[str]:
    """Uma entrada por linha, `#` comenta, linha vazia separa bloco."""
    if not ALLOWLIST.exists():
        return []
    entradas = []
    for linha in ALLOWLIST.read_text(encoding="utf-8").splitlines():
        conteudo = linha.strip()
        if conteudo and not conteudo.startswith("#"):
            entradas.append(conteudo)
    return entradas


# O tamanho do estado inicial (`main` @ 80da2a5). **Este número só desce.** Baixá-lo é o trabalho
# das fases 1–6; subi-lo exige justificativa escrita na PR, porque cada entrada aqui é um nome que
# o repositório ainda diz errado.
TETO_DA_ALLOWLIST = 59


def test_nenhum_termo_banido_novo() -> None:
    """Nenhum identificador **novo** fora do vocabulário canônico."""
    mensagens = {regra.id: regra.mensagem for regra in REGRAS}
    isentos = set(entradas_da_allowlist())
    achados = sorted(
        (a for a in varrer() if a.chave not in isentos),
        key=lambda a: (a.caminho, a.linha, a.regra),
    )
    relatorio = [f"{a} → {mensagens[a.regra]}" for a in achados]
    assert relatorio == [], (
        "identificador fora do vocabulário canônico (ADR 0049; "
        "docs/ontology/language-map.md §5-6).\n"
        "Se a ocorrência é dívida legada e não código novo, declare-a em "
        "docs/ontology/legacy-allowlist.txt com o motivo escrito.\n  " + "\n  ".join(relatorio)
    )


def test_a_allowlist_nao_guarda_linha_desnecessaria() -> None:
    """A direção inversa: isenção sem dívida correspondente sai da lista.

    É isto que faz a allowlist **encolher sozinha** quando a fase que paga a dívida chega — sem
    isto, a linha sobreviveria ao renome e isentaria em silêncio o próximo defeito no mesmo
    arquivo.
    """
    reais = {a.chave for a in varrer()}
    obsoletas = [entrada for entrada in entradas_da_allowlist() if entrada not in reais]
    assert obsoletas == [], (
        "entrada da allowlist sem ocorrência correspondente — remova a linha:\n  "
        + "\n  ".join(obsoletas)
    )


def test_a_allowlist_so_encolhe() -> None:
    """O teto é monotônico: a dívida de linguagem não cresce."""
    entradas = entradas_da_allowlist()
    assert len(entradas) <= TETO_DA_ALLOWLIST, (
        f"a allowlist tem {len(entradas)} entradas e o teto é {TETO_DA_ALLOWLIST}. "
        "Este número só desce: pagar a dívida abaixa o teto, e subi-lo exige justificativa "
        "escrita na PR."
    )


# --------------------------------------------------------------------------------------------
# A guarda tem teste, como qualquer outro código
# --------------------------------------------------------------------------------------------

# As linhas sintéticas que as Fases 1 e 3 vão escrever, e as que elas não podem escrever. Se a
# guarda reprovasse a primeira coluna, ela impediria justamente o passo que paga a dívida:
# nome canônico apontando para o modelo legado, e prefixo `legacy_` nomeando o mapeamento.
LINHAS_LEGITIMAS: tuple[tuple[str, str, str], ...] = (
    ("opportunity-sem-qualificador", "models.py", "    legacy_opportunity = models.ForeignKey("),
    ("opportunity-sem-qualificador", "models.py", "    commercial_opportunity = models.OneToOne("),
    ("opportunity-sem-qualificador", "models.py", "    improvement_opportunity = models.FK("),
    ("opportunity-sem-qualificador", "models.py", "class CommercialOpportunity(TimestampedModel):"),
    ("opportunity-sem-qualificador", "models.py", "class ImprovementOpportunity(models.Model):"),
    # Uso, não batismo: a linha que o `grep` reprovaria e que a guarda precisa deixar passar.
    ("opportunity-sem-qualificador", "views.py", "        return self.opportunity.client_id"),
    ("opportunity-sem-qualificador", "views.py", "from .models import Opportunity"),
    # O alias canônico da Fase 1: campo `account` apontando para o modelo legado `Client`.
    ("client-como-organizacao", "models.py", '    account = models.ForeignKey("core.Client")'),
    ("client-como-organizacao", "models.py", "    legacy_client = models.ForeignKey(Client)"),
    # Cliente de protocolo: sufixo, não prefixo.
    ("client-como-organizacao", "github_issues.py", "class GitHubIssuesClient:"),
    ("client-como-organizacao", "views.py", "        response = client.get(url)"),
    ("client-como-organizacao", "models.py", "    api_client = models.CharField()"),
    # `Management` tem `agem` no meio e é inglês legítimo; o marcador é sufixo.
    ("modelo-em-portugues", "models.py", "class ManagementReport(models.Model):"),
    ("modelo-em-portugues", "models.py", "class Engagement(TimestampedModel):"),
    ("modelo-em-portugues", "models.py", "class Measurement(TimestampedModel):"),
    # Fora do núcleo a heurística de português não roda — e `Evidence` é o nome canônico.
    ("legado-congelado", "models.py", "class Evidence(TimestampedModel):"),
    ("legado-congelado", "models.py", "class ProcessStep(TimestampedModel):"),
    ("outcome-como-decisao-de-gate", "models.py", "    class GateDecision(models.TextChoices):"),
    ("outcome-como-decisao-de-gate", "models.py", "    gate_decision = models.CharField()"),
)

LINHAS_REPROVADAS: tuple[tuple[str, str, str], ...] = (
    ("opportunity-sem-qualificador", "models.py", "    opportunity = models.ForeignKey(Opp)"),
    ("opportunity-sem-qualificador", "models.py", "class Opportunity(TimestampedModel):"),
    ("opportunity-sem-qualificador", "urls.py", 'router.register("opportunities", OppViewSet)'),
    ("opportunity-sem-qualificador", "types.ts", "export type OpportunityRow = {"),
    ("client-como-organizacao", "models.py", "class Client(TimestampedModel):"),
    ("client-como-organizacao", "models.py", "    client = models.ForeignKey(Client)"),
    ("client-como-organizacao", "urls.py", 'router.register("clients", ClientViewSet)'),
    ("client-como-organizacao", "types.ts", "export interface ClientOverview {"),
    ("modelo-em-portugues", "models.py", "class Contagem(models.Model):"),
    ("modelo-em-portugues", "models.py", "class Evidencia(TimestampedModel):"),
    ("modelo-em-portugues", "serializers.py", "class RiscoSerializer(serializers.ModelSerializer):"),
    ("legado-congelado", "models.py", "class Processo(TimestampedModel):"),
    ("outcome-como-decisao-de-gate", "models.py", "    class GateOutcome(models.TextChoices):"),
    ("outcome-como-decisao-de-gate", "views.py", "        if gate_outcome == 'go':"),
)


def _regra(identificador: str) -> Regra:
    return next(regra for regra in REGRAS if regra.id == identificador)


def test_a_guarda_deixa_passar_o_nome_que_as_fases_seguintes_vao_escrever() -> None:
    for regra_id, arquivo, linha in LINHAS_LEGITIMAS:
        achados = achados_na_linha(_regra(regra_id), arquivo, 1, linha)
        assert achados == [], f"{regra_id} reprovou linha legítima: {linha!r} → {achados}"


def test_a_guarda_reprova_o_batismo_errado() -> None:
    for regra_id, arquivo, linha in LINHAS_REPROVADAS:
        achados = achados_na_linha(_regra(regra_id), arquivo, 1, linha)
        assert achados != [], f"{regra_id} deixou passar batismo errado: {linha!r}"
