"""A guarda do vocabulário canônico (ADR 0049, `docs/ontology/language-map.md` §6).

**Ela casa declaração, e não referência — essa é a decisão inteira.** A tentação, ao ler "nenhum
identificador novo contém `opportunity` sem qualificador", é escrever um `grep opportunity` e
reprovar a linha. Isso reprovaria centenas de ocorrências de código legítimo: um `self.client`,
um `client_id` de filtro, um `from .models import Client` são *usos* do modelo que existe hoje,
e o modelo ainda existe sob o nome antigo enquanto a fatia da issue #67 que o renomeia não
chegou. Uma guarda que reprova o que o repositório precisa fazer para funcionar é desligada na
primeira semana, e aí não protege nada.

"Renome físico" era um termo que significava duas coisas, e a **ADR 0052** o desfez em três, com
prazos distintos: o nome da **classe** é a issue #67 (uma fatia por PR), o nome da **tabela** é a
Fase 6, e a **rota** com a **chave de payload** é a `/api/v2/`. As quatro fatias passaram e a #67
fechou — `GateOutcome` virou `GateDecision` com o campo `gate_decision`, `Opportunity` virou
`CommercialOpportunity` com os cinco campos `commercial_opportunity`, `Client` virou `Account` com
os dez campos `account` e o `lifecycle_status`, e `Processo`/`ProcessoEtapa` viraram
`Process`/`ProcessStep` com os três campos `process`/`step` —, restando na allowlist as rotas, as
chaves de payload que a v1 promete, o `client_consent`,
e a família sem nome canônico na Ontology v1. `ai_opportunity` virou `ai_potential` (Fase 6),
`Project.client` saiu (Fase 6), e a `Evidencia` saiu com o dual-write (Fase 6).

O que a invariante §6 proíbe é **batizar** coisa nova com o nome errado. Batizar tem forma
sintática: `class X`, `campo = models.…`, `router.register(...)`, `path(...)`, `type X`,
`interface X`, `const X`, `function X`. Só essas linhas são medidas. O alias legado continua
podendo ser referenciado à vontade; o que não se pode é criar mais um.

Três exceções são deliberadas e as fases seguintes dependem delas (ver `docs/ontology/aliases.md`):

* prefixo `legacy_` — `legacy_opportunity`, `legacy_evidencia` nomeiam explicitamente o mapeamento
  para o registro antigo, e esconder esse mapeamento atrás de um nome bonito é o defeito, não a
  correção;
* `commercial_` / `improvement_` — são exatamente os qualificadores que a §5 pede;
* um campo chamado `account` — é o nome canônico, e desde a fatia 2 da #67 ele aponta para a
  classe de nome certo. A regra `client-como-organizacao` casa `client`, nunca `account`. O mesmo
  vale para `process`/`step` desde a fatia 4.

`GateOutcome`/`gate_outcome` é a única regra em que a **referência** é o problema: ali o
identificador inteiro está errado, não o contexto — não existe uso legítimo do nome antigo dentro
do código. A exceção é a chave de payload que a `/api/v1/` promete, e ela está declarada na
allowlist, sozinha, desde que a fatia 1 da #67 pagou o resto.

A allowlist (`docs/ontology/legacy-allowlist.txt`) nasce com o estado de `main`, nem uma entrada a
mais, e três testes a mantêm honesta: o que ela isenta precisa existir (senão a linha sai), e o
total só desce. É o mesmo desenho de `frontend/src/test/primitivas.test.ts`, pela mesma razão:
allowlist que ninguém revisa vira permissão permanente.
"""

from __future__ import annotations

import re
from collections import Counter
from collections.abc import Iterable, Mapping
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
        # **Sensível a caixa, e é a correção de um defeito medido.** Com `re.I` esta regra
        # reprovava `ProcessObservation` — que é o nome **canônico** da tabela mestra (§2) —
        # porque `Process` + `Observation` emenda um `o` minúsculo que o marcador `Processo` casa
        # sem olhar a caixa. É o pior modo de falha possível aqui: a guarda reprova o nome certo,
        # e a saída fácil é declarar um nome canônico na allowlist de dívida, registrando como
        # débito exatamente o que pagou o débito.
        # Os marcadores são substantivos próprios em CamelCase (`Processo`, `Evidencia`, …) e os
        # sufixos são minúsculos, então a caixa exata basta: `ProcessO`bservation deixa de casar
        # e `Contagem`, `Evidencia` e `RiscoSerializer` continuam casando.
        padrao=re.compile(rf"^\s*class\s+(\w*(?:{_MARCADORES})\w*|\w*(?:{_SUFIXOS}))\("),
        arquivos=ESCOPO_NUCLEO,
        mensagem="nomeie o modelo em inglês — termo canônico em inglês nas quatro superfícies "
        "(language-map §1)",
    ),
    Regra(
        id="legado-congelado",
        # Os quatro nomes banidos pela §5, e os quatro já pagos: `GateOutcome` na fatia 1 da #67,
        # `Processo`/`ProcessoEtapa` na fatia 4, e `Evidencia` na Fase 6 (#70), com o dual-write.
        # Todos **continuam** no regex: lista fechada existe para barrar batismo novo, e nome pago
        # segue banido — só que agora nenhum tem ocorrência, então nenhum aparece na allowlist.
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
        """A entrada da allowlist, **sem número de linha**: uma dívida declarada não pode ser
        reaberta porque alguém inseriu um import acima dela.

        O preço de tirar a linha é que a chave sozinha não distingue a décima segunda ocorrência
        da décima terceira — e `models.py` é onde todo modelo novo nasce. Por isso a entrada
        carrega a **contagem** (`…::client::12`), e não só a chave.
        """
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


FORMATO_DA_ENTRADA = re.compile(r"^(?P<chave>[^:]+::[^:]+::[^:]+)::(?P<contagem>\d+)$")


def entradas_da_allowlist() -> dict[str, int]:
    """`chave -> contagem declarada`. Uma entrada por linha, `#` comenta, linha vazia separa bloco.

    A contagem é a segunda metade da decisão de tirar o número de linha da chave. Sem ela, uma
    dívida já declarada vira franquia ilimitada naquele arquivo: `models.py::…::client` cobre as
    doze ocorrências de hoje **e a décima terceira**, que é justamente a que a guarda existe para
    pegar. Medido por sabotagem, no espírito da ADR 0027 — um `client = models.ForeignKey(...)`
    acrescentado ao fim de `models.py` passava em silêncio.
    """
    if not ALLOWLIST.exists():
        return {}
    entradas: dict[str, int] = {}
    for numero, linha in enumerate(ALLOWLIST.read_text(encoding="utf-8").splitlines(), start=1):
        conteudo = linha.strip()
        if not conteudo or conteudo.startswith("#"):
            continue
        m = FORMATO_DA_ENTRADA.match(conteudo)
        assert m is not None, (
            f"{ALLOWLIST.name}:{numero}: entrada fora do formato "
            f"`caminho::regra::identificador::contagem`: {conteudo!r}"
        )
        chave = m.group("chave")
        assert chave not in entradas, (
            f"{ALLOWLIST.name}:{numero}: entrada duplicada para {chave!r} — some as contagens "
            "numa linha só, senão a segunda esconde a primeira"
        )
        entradas[chave] = int(m.group("contagem"))
    return entradas


def contar(achados: Iterable[Achado]) -> Counter[str]:
    """Quantas ocorrências o repositório tem de cada dívida."""
    return Counter(achado.chave for achado in achados)


def excedentes(reais: Mapping[str, int], declarados: Mapping[str, int]) -> list[str]:
    """Dívida acima do declarado — inclusive a que não está declarada de todo (declarado = 0)."""
    return sorted(chave for chave, real in reais.items() if real > declarados.get(chave, 0))


def quitadas_sem_baixa(reais: Mapping[str, int], declarados: Mapping[str, int]) -> list[str]:
    """Dívida abaixo do declarado — foi paga em parte e ninguém abaixou o número.

    Contagem zero é o caso particular: a entrada inteira ficou obsoleta e tem de sair.
    """
    return sorted(chave for chave, declarado in declarados.items() if reais.get(chave, 0) < declarado)


# Quantas **dívidas distintas** a allowlist declara — linhas do arquivo, não ocorrências no
# código. Os dois números não medem a mesma coisa: uma linha pode valer doze ocorrências, e pagar
# onze delas abaixa a contagem daquela linha sem mexer neste teto. **Este número só desce.**
# Baixá-lo é o trabalho das fases 1–6; subi-lo exige justificativa escrita na PR, porque cada
# linha aqui é um nome que o repositório ainda diz errado.
#
# A subida para 30 (fechamento da issue #67) pagou-se em parte na Fase 6 (issue #70): a remoção da
# `Evidencia` e do dual-write apagou as quatro linhas dela — `modelo-em-portugues` no modelo, no
# serializer e no viewset, mais `legado-congelado` no modelo —, e o teto desceu de 30 para 26.
#
# A exceção que resta com prazo é o `gate_outcome` de `openapi_aliases.py`: o mapa precisa conter o
# nome literal para marcar o alias como `deprecated` no `openapi.yaml` — a mesma exceção que já
# valia para `serializers.py`, aplicada a um arquivo novo. **É dívida com prazo, e o prazo é o
# mesmo do alias que ela anuncia**: quando a `/api/v2/` parar de emitir `gate_outcome`, a entrada
# sai do mapa e as duas linhas saem daqui juntas. Um mecanismo de depreciação não sobrevive ao que
# ele deprecia; ler esta linha como permanente transformaria em dívida eterna a única dívida deste
# arquivo que já tem data marcada.
TETO_DA_ALLOWLIST = 23


def test_nenhum_termo_banido_novo() -> None:
    """Nenhum identificador **novo** fora do vocabulário canônico — nem em arquivo limpo, nem
    escondido atrás de uma dívida já declarada no mesmo arquivo."""
    mensagens = {regra.id: regra.mensagem for regra in REGRAS}
    declarados = entradas_da_allowlist()
    achados = varrer()
    ocorrencias: dict[str, list[Achado]] = {}
    for achado in achados:
        ocorrencias.setdefault(achado.chave, []).append(achado)

    relatorio: list[str] = []
    for chave in excedentes(contar(achados), declarados):
        deste = sorted(ocorrencias[chave], key=lambda a: a.linha)
        declarado = declarados.get(chave, 0)
        mensagem = mensagens[deste[0].regra]
        if declarado == 0:
            relatorio.extend(f"{achado} → {mensagem}" for achado in deste)
            continue
        linhas = ", ".join(str(achado.linha) for achado in deste)
        relatorio.append(
            f"{deste[0].caminho} — {deste[0].identificador} [{deste[0].regra}]: a allowlist "
            f"declara {declarado} ocorrência(s) e o repositório tem {len(deste)} "
            f"(linhas {linhas}). Dívida nova não entra por carona numa linha já declarada → "
            f"{mensagem}"
        )

    assert relatorio == [], (
        "identificador fora do vocabulário canônico (ADR 0049; "
        "docs/ontology/language-map.md §5-6).\n"
        "Se a ocorrência é dívida legada e não código novo, declare-a em "
        "docs/ontology/legacy-allowlist.txt com o motivo escrito.\n  " + "\n  ".join(relatorio)
    )


def test_a_allowlist_nao_guarda_linha_desnecessaria() -> None:
    """A direção inversa: isenção maior que a dívida sai da lista, ou tem o número abaixado.

    É isto que faz a allowlist **encolher sozinha** quando a fase que paga a dívida chega — sem
    isto, a linha sobreviveria ao renome e isentaria em silêncio a próxima ocorrência no mesmo
    arquivo. Com contagem, ela encolhe também quando a dívida é paga **em parte**, que é o caso
    comum: um renome raramente limpa um arquivo inteiro de uma vez.
    """
    declarados = entradas_da_allowlist()
    reais = contar(varrer())
    sobrando = [
        f"{chave}: declara {declarados[chave]}, existem {reais.get(chave, 0)} — "
        + (
            "remova a linha"
            if reais.get(chave, 0) == 0
            else f"escreva `{chave}::{reais[chave]}`"
        )
        for chave in quitadas_sem_baixa(reais, declarados)
    ]
    assert sobrando == [], (
        "entrada da allowlist maior que a dívida que ela isenta:\n  " + "\n  ".join(sobrando)
    )


def test_a_allowlist_so_encolhe() -> None:
    """O teto é monotônico: o número de dívidas distintas não cresce."""
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
    ("client-como-organizacao", "models.py", '    account = models.ForeignKey("core.Account")'),
    ("client-como-organizacao", "models.py", "    legacy_client = models.ForeignKey(Client)"),
    # Cliente de protocolo: sufixo, não prefixo.
    ("client-como-organizacao", "github_issues.py", "class GitHubIssuesClient:"),
    ("client-como-organizacao", "views.py", "        response = client.get(url)"),
    ("client-como-organizacao", "models.py", "    api_client = models.CharField()"),
    # `Management` tem `agem` no meio e é inglês legítimo; o marcador é sufixo.
    ("modelo-em-portugues", "models.py", "class ManagementReport(models.Model):"),
    # **A armadilha que custou um `re.I`.** `ProcessObservation` é nome canônico da tabela mestra
    # (§2), e a emenda `Process` + `Observation` produz a sequência `Processo` — que o marcador
    # casava enquanto a regra ignorava caixa. Sem estes três casos fixados, o `re.I` volta no
    # primeiro refactor e a guarda torna a reprovar o nome que a ontologia manda usar.
    ("modelo-em-portugues", "models.py", "class ProcessObservation(TimestampedModel):"),
    ("modelo-em-portugues", "serializers.py", "class ProcessObservationSerializer(Base):"),
    ("modelo-em-portugues", "views.py", "class ProcessObservationViewSet(viewsets.ModelViewSet):"),
    ("legado-congelado", "models.py", "class ProcessObservation(TimestampedModel):"),
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


# A sabotagem que a primeira versão desta guarda não via, reduzida ao que ela realmente testa:
# a comparação de contagens. Como caso de linha isolada ela não caberia em `LINHAS_REPROVADAS` —
# a linha `client = models.ForeignKey(...)` **é** um achado nas duas versões; o que mudou é que
# agora ela é comparada contra um orçamento, e não contra a mera existência de uma entrada.
CHAVE_SINTETICA = "backend/apps/core/models.py::client-como-organizacao::client"


def test_ocorrencia_nova_em_chave_ja_declarada_reprova() -> None:
    declarados = {CHAVE_SINTETICA: 12}
    assert excedentes({CHAVE_SINTETICA: 12}, declarados) == []
    assert excedentes({CHAVE_SINTETICA: 13}, declarados) == [CHAVE_SINTETICA]
    # Chave não declarada: qualquer ocorrência é excedente, que é o comportamento de sempre.
    assert excedentes({CHAVE_SINTETICA: 1}, {}) == [CHAVE_SINTETICA]


def test_divida_paga_sem_baixa_no_numero_reprova() -> None:
    declarados = {CHAVE_SINTETICA: 12}
    assert quitadas_sem_baixa({CHAVE_SINTETICA: 12}, declarados) == []
    # Paga em parte: o número tem de descer junto.
    assert quitadas_sem_baixa({CHAVE_SINTETICA: 11}, declarados) == [CHAVE_SINTETICA]
    # Paga inteira: a linha some. É o caso particular que a versão sem contagem já cobria.
    assert quitadas_sem_baixa({}, declarados) == [CHAVE_SINTETICA]
