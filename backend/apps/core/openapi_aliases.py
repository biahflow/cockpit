"""O mapa dos aliases de leitura da `/api/v1/` — um mapa, três consumidores.

A `docs/ontology/aliases.md` §2c já diz, em prosa, que a chave legada continua saindo em cada
serializer que a issue #67 renomeou — mas ninguém que só lê `openapi.yaml` ou o Swagger de
`/api/docs/` enxerga essa prosa. Este módulo é o que fecha a lacuna: um mapa declarativo de
componente → propriedades-alias, e um `POSTPROCESSING_HOOKS` (`config/settings.py`,
`SPECTACULAR_SETTINGS`) que marca `deprecated: true` em cada uma delas na geração do esquema.

**Desde a issue #122 o mesmo mapa também executa a depreciação que anuncia.**
`serializers.AliasesDaV1Mixin` o lê para **remover** essas chaves da resposta quando a requisição
veio pela `/api/v2/`. A alternativa — cada serializer declarar a própria lista do que sumir — faria
o contrato prometer uma ausência que a resposta não cumpre, no dia em que as duas divergissem, e
divergir é o que duas listas do mesmo fato fazem. A terceira consumidora é a recusa de escrita, que
lê `ALIASES_DE_ENTRADA` porque ali é preciso saber também o **nome canônico** de cada chave.

**Por que o mapa é escrito à mão, e não inferido do código.** A tentação óbvia é varrer os
serializers e marcar como depreciado todo campo declarado com `source=` apontando para outro nome
— é exatamente o padrão sintático que o `AliasesDaV1Mixin` e os aliases de leitura usam
(`apps/core/serializers.py` e os comentários "Alias de leitura da `/api/v1/`" espalhados
pelo arquivo). O problema é que a maioria dos `source=` do repositório **não** é alias de
compatibilidade: é projeção legítima, do mesmo jeito que `client_name = CharField(source=
"account.name")` ou `is_overdue = BooleanField(read_only=True)`. Inferir por sintaxe marcaria como
"vai morrer na v2" um campo que não tem nenhuma intenção de morrer, e a mentira no contrato é pior
que o silêncio que este módulo substitui. Só quem sabe que uma chave é sinônimo do nome canônico —
e não uma leitura nova sobre ele — é quem leu `aliases.md`; por isso o mapa é a tradução manual
dele para o vocabulário do OpenAPI, revisada junto com o serializer na hora de cada fatia.

O mapa cobre dois mecanismos, e os dois produzem a mesma forma no esquema (uma propriedade
`read_only` com `source=` apontando para o campo canônico, ou um método derivado):

- os doze serializers que declaram `ALIASES_DE_ENTRADA` para aceitar também a chave antiga em
  `POST`/`PATCH`;
- os aliases só-de-leitura que não precisam de escrita porque o vínculo é lavrado por uma action
  própria — a chave legada do gate em `ProjectPhase`/`PhaseEvent` (`apply-gate`/`set-waiting`,
  `docs/ontology/aliases.md` §2c), `Lead.client`/`Lead.opportunity` (`convert`/
  `open-opportunity`), `Project.opportunity` (`convert-to-project`), `Case.client_consent`
  (`record-consent`), `CobrancaContato.client` (o contato nasce do envio) e o par
  `kpi_baseline`/`kpi_current` do `DigitalEmployee`, que é derivado do KPI referenciado (§2d).

**Toda entrada do mapa tem um serializer que a executa, e isso é guardado.** Componente sem
serializer que herde `AliasesDaV1Mixin` seria uma chave anunciada como depreciada no esquema e
ainda saindo na resposta da v2 — ver `backend/tests/test_aliases_da_v2.py`.

**São dois mapas desde a fatia 4a, e o segundo existe para essa guarda continuar valendo.**
`ALIASES_DEPRECIADOS_DE_DICT_CRU` lista os componentes de `inline_serializer` — o painel de
cobrança e a visão compacta da entrega —, cujo alias a **view** remove à mão porque não há
serializer por onde o mixin passar. Os hooks leem a união (`ALIASES_DEPRECIADOS_NO_ESQUEMA`), que é
o único ponto em que a origem da propriedade deixa de importar; o mixin lê só o primeiro.

**Nota sobre a referência à chave do gate.** `outcome-como-decisao-de-gate`
(`backend/tests/test_vocabulario.py`) é a única regra do vocabulário que casa **referência**, não
declaração — o identificador inteiro está errado em qualquer posição. `ALIASES_DEPRECIADOS`
precisa do nome literal da chave para procurá-la no schema, então a referência é legítima e está
declarada em `docs/ontology/legacy-allowlist.txt`, como já valia para o alias de leitura do
`ProjectPhaseSerializer`/`PhaseEventSerializer`. O nome mora numa única constante
(`_CHAVE_LEGADA_DO_GATE`) para essa referência aparecer **uma vez** no arquivo, não duas.

Chave do mapa é o nome do **componente** do schema, o mesmo que aparece em
`components.schemas` no `openapi.yaml` — sem o prefixo `Patched` que o drf-spectacular gera para o
corpo de `PATCH` (`COMPONENT_SPLIT_PATCH`, ligado por padrão): o hook abaixo despe o prefixo antes
de procurar no mapa, para as duas formas do mesmo recurso saírem marcadas juntas.
"""

from __future__ import annotations

import os
import re
from typing import Any

from .versioning import PREFIXO_DA_V2, V1, V2

# Espelho de `docs/ontology/aliases.md` §2c. Cada entrada morre quando o campo dela morrer —
# na `/api/v2/` — e nenhuma antes, porque a chave continua respondendo até lá.
# Isolado numa constante para a chave legada do gate (ver nota acima) aparecer uma única vez
# no arquivo — é a única referência do módulo que a regra `outcome-como-decisao-de-gate` casa.
_CHAVE_LEGADA_DO_GATE: tuple[str, ...] = ("gate_outcome",)

ALIASES_DEPRECIADOS: dict[str, tuple[str, ...]] = {
    "Account": ("status",),
    # `cobranca_sinal`/`cobranca_sinal_display` entraram na issue #122, fatia 5.2, junto do renome
    # de `Activity.CobrancaSinal` para `DunningSignal` (D10). Sem `ALIASES_DE_ENTRADA`: o campo é
    # `read_only` — ver o comentário do `ActivitySerializer`.
    "Activity": ("client", "opportunity", "cobranca_sinal", "cobranca_sinal_display"),
    "Artifact": ("opportunity",),
    "CobrancaContato": ("client", "client_name"),
    "CobrancaSuspensao": ("client", "client_name"),
    "Case": ("client_consent", "client_name"),
    "CommercialOpportunity": ("client",),
    "Contact": ("client",),
    # `kpi_baseline`/`kpi_current` são a exceção da §2d: a **escrita** por elas parou na ADR 0055
    # e a leitura ficou, derivada da baseline viva e do `Outcome` mais recente do KPI referenciado.
    # A docstring do `DigitalEmployeeSerializer` prometia a depreciação no esquema desde então e o
    # mapa não a cumpria — entrada que faltava, não alias novo (issue #122).
    "DigitalEmployee": ("kpi_baseline", "kpi_current"),
    "Document": ("client", "opportunity"),
    "Invoice": ("client", "client_name"),
    "Lead": ("client", "opportunity"),
    "PhaseEvent": _CHAVE_LEGADA_DO_GATE,
    "Process": ("client", "client_name"),
    "ProcessStep": ("processo",),
    # `client_vertical`/`client_vertical_name` são **projeção**, e nunca foram coluna: o campo do
    # modelo é `Account.vertical`, e estas duas chaves atravessam `engagement.account` para o
    # detalhe do projeto pedir o catálogo já resolvido (FDD 026). Por isso não há `RenameField` a
    # fazer — o que a fatia 4a paga é a **chave de payload**, que é onde o nome errado estava
    # (`docs/ontology/aliases.md` §2c). As canônicas (`account_vertical`/`account_vertical_name`)
    # saem ao lado na v1 e sozinhas na v2, como todo par desta tabela.
    "Project": (
        "opportunity", "client", "ai_opportunity", "client_vertical", "client_vertical_name",
    ),
    "ProjectPhase": _CHAVE_LEGADA_DO_GATE,
    # `SatisfactionRecord` desde a issue #122, fatia 5.3 (a classe era `Satisfacao`). A chave
    # continua sendo só `client`: `nivel`/`fonte` **não** são alias — o nome do campo não mudou,
    # só o valor que ele persiste (D10), e valor não se remove da resposta.
    "SatisfactionRecord": ("client",),
}

# Os componentes que **não têm serializer** e por isso não podem estar no mapa acima: são
# `inline_serializer` de `@extend_schema`, descrevendo um dicionário cru que a view monta à mão.
#
# A separação não é organização, é a diferença de **quem executa a remoção**. `AliasesDaV1Mixin` lê
# `ALIASES_DEPRECIADOS` e some com a chave na resposta da v2; um dict cru não passa por serializer
# nenhum, então quem o faz é a própria view (`views._sem_chaves_legadas`, chamada quando
# `versao_de(request) == V2`). Guardar os dois casos no mesmo dicionário quebraria a guarda que
# `backend/tests/test_aliases_da_v2.py` mantém sobre o primeiro — "todo componente do mapa tem um
# serializer que executa a remoção" —, e afrouxá-la para caber estes dois abriria a porta para o
# caso que ela existe para pegar: a entrada nova que anuncia uma depreciação que ninguém executa.
#
# O que os dois casos **têm** em comum é o esquema, e é por isso que os hooks abaixo leem a união
# (`ALIASES_DEPRECIADOS_NO_ESQUEMA`) e não um dos dois: para quem lê o contrato, a origem da
# propriedade é indiferente — ela sai `deprecated` na v1 e ausente na v2 nos dois casos.
ALIASES_DEPRECIADOS_DE_DICT_CRU: dict[str, tuple[str, ...]] = {
    "CobrancaPainelLinha": ("client", "client_name"),
    "DeliveryTimelineOverview": ("client_name",),
}

# A união, e a única coisa que os hooks do drf-spectacular leem.
ALIASES_DEPRECIADOS_NO_ESQUEMA: dict[str, tuple[str, ...]] = {
    **ALIASES_DEPRECIADOS,
    **ALIASES_DEPRECIADOS_DE_DICT_CRU,
}

# O nome canônico de cada chave legada que aparece em `ALIASES_DEPRECIADOS` — a quarta consumidora
# do mapa, desde a issue #122 fatia 3a. `AliasesDaV1Mixin.to_internal_value` já sabia recusar as
# chaves de `ALIASES_DE_ENTRADA` na v2 (ali o nome canônico mora ao lado, porque também é preciso
# traduzir na v1); as chaves só-de-leitura desta tabela nunca precisaram de tradução, então não
# tinham onde guardar o canônico — e sem ele a recusa não teria o que dizer.
#
# `None` marca a exceção da §2d: `kpi_baseline`/`kpi_current` pararam de **aceitar** escrita ainda
# na `/api/v1/` (ADR 0055), então não há campo canônico de escrita para apontar — a frase delas é
# `versioning.frase_da_chave_sem_sucessora`, não `frase_da_chave_removida`.
#
# Guardado por `test_aliases_da_v2.py`: toda chave de `ALIASES_DEPRECIADOS` precisa de uma entrada
# aqui, para uma chave nova não nascer recusada em silêncio (sem 400, sem frase).
#
# A chave do gate vem de `_CHAVE_LEGADA_DO_GATE`, e não de um segundo literal — pela mesma razão
# que aquela constante existe (ver a nota no topo do módulo): a regra de vocabulário que casa essa
# referência conta ocorrências de texto, e a allowlist deste arquivo só declara uma.
CANONICO_DA_CHAVE: dict[str, str | None] = {
    "client": "account",
    "client_name": "account_name",
    "client_vertical": "account_vertical",
    "client_vertical_name": "account_vertical_name",
    "status": "lifecycle_status",
    "opportunity": "commercial_opportunity",
    _CHAVE_LEGADA_DO_GATE[0]: "gate_decision",
    "ai_opportunity": "ai_potential",
    "client_consent": "account_consent",
    "processo": "process",
    "kpi_baseline": None,
    "kpi_current": None,
    "cobranca_sinal": "dunning_signal",
    "cobranca_sinal_display": "dunning_signal_display",
}

_PREFIXO_PATCHED = re.compile(r"^Patched(.+)$")


def alvo_da_geracao() -> str:
    """O alvo desta geração de esquema: `'v1'` (default) ou `'v2'`, lido de `OPENAPI_ALVO`.

    Por que env, e não introspecção do `generator`. Os hooks do drf-spectacular recebem os
    endpoints já enumerados (`PREPROCESSING_HOOKS`, `endpoints=`) ou o esquema já montado
    (`POSTPROCESSING_HOOKS`, `result=`/`generator=`) — nenhum dos dois carrega **qual urlconf**
    produziu aquilo, então nada aqui dentro consegue inferir sozinho se a geração corrente é a da
    v1 ou a da v2. O comando da v2 (`OPENAPI_ALVO=v2 manage.py spectacular --urlconf
    config.urls_v2_schema --file openapi-v2.yaml`) declara o alvo explicitamente; sem ele,
    `excluir_a_v2_do_contrato` esvaziaria a geração da v2 inteira, filtrando os únicos caminhos que
    o urlconf dedicado enumera.
    """
    return os.environ.get("OPENAPI_ALVO", V1).strip().lower() or V1


def chave_da_geracao(legada: str, canonica: str) -> str:
    """A chave que **troca** por versão, dita no vocabulário do esquema (issue #122, fatia 4a).

    O par leitura-legada/leitura-canônica de `ALIASES_DEPRECIADOS` convive: as duas chaves saem na
    v1 e só a canônica na v2. Há um caso em que isso não vale — a chave que **envolve a lista
    inteira** —, porque duplicá-la pagaria o corpo da resposta duas vezes. O precedente é a fatia
    3a (`processos`/`processes` na action de IA); a fatia 4a aplica o mesmo a `clients`/`accounts`
    em `GET /accounts/overview/`.

    Quando a chave troca, o **componente** também troca, e é isso que esta função entrega: a view
    escolhe a chave da resposta por `versao_de(request)`, e o `@extend_schema` escolhe a do esquema
    pelo alvo da geração. Sem ela, o `openapi-v2.yaml` descreveria `clients` numa resposta que só
    tem `accounts` — a mentira publicada que a decisão 5 da ADR 0066 recusa.
    """
    return canonica if alvo_da_geracao() == V2 else legada


def marcar_aliases_depreciados(
    result: dict[str, Any], generator: Any, request: Any, public: bool
) -> dict[str, Any]:
    """`POSTPROCESSING_HOOKS`: marca `deprecated: true` em cada propriedade de `ALIASES_DEPRECIADOS`.

    Roda depois de o esquema estar montado, então só toca `components.schemas` — nunca decide
    forma de request/response, só anota o que já existe. Um componente sem entrada no mapa, ou uma
    propriedade que o mapa cita mas o schema não tem, passa direto: é o teste
    `test_openapi_aliases.py` que garante que o mapa não apodrece (entrada morta) nem fica atrás do
    código (alias novo sem entrada).

    No-op quando o alvo da geração é v2 (`alvo_da_geracao`): a v2 não *anuncia* a depreciação, ela
    **remove** — quem faz isso é `remover_aliases_do_contrato`, logo abaixo, no mesmo par
    filtra/inclui de `excluir_a_v2_do_contrato`.
    """
    if alvo_da_geracao() == V2:
        return result
    schemas = result.get("components", {}).get("schemas", {})
    for nome_componente, schema in schemas.items():
        casado = _PREFIXO_PATCHED.match(nome_componente)
        nome_base = casado.group(1) if casado else nome_componente
        propriedades_alias = ALIASES_DEPRECIADOS_NO_ESQUEMA.get(nome_base)
        if not propriedades_alias:
            continue
        propriedades = schema.get("properties", {})
        for nome_propriedade in propriedades_alias:
            propriedade = propriedades.get(nome_propriedade)
            if propriedade is not None:
                propriedade["deprecated"] = True
    return result


def remover_aliases_do_contrato(
    result: dict[str, Any], generator: Any, request: Any, public: bool
) -> dict[str, Any]:
    """`POSTPROCESSING_HOOKS`: no alvo v2, remove cada propriedade-alias do componente e de `required`.

    O espelho exato de `marcar_aliases_depreciados`, na outra direção: onde aquele anota o que
    ainda sai na v1, este apaga o que a v2 promete não sair — a mesma leitura de
    `ALIASES_DEPRECIADOS`, o mesmo despir do prefixo `Patched`. É o que torna o `openapi-v2.yaml`
    verdadeiro (ADR 0066, decisão 5): a chave não fica marcada como obsoleta, ela simplesmente não
    está lá.

    Tirar também de `required`, quando presente, é o que mantém o esquema válido: um `required`
    apontando para uma propriedade que `properties` não tem mais reprova o `--validate` do
    spectacular tão bem quanto reprovaria qualquer cliente gerado a partir do contrato.

    No-op quando o alvo é v1 (o default) — quem cuida daquele caso é `marcar_aliases_depreciados`.
    """
    if alvo_da_geracao() != V2:
        return result
    schemas = result.get("components", {}).get("schemas", {})
    for nome_componente, schema in schemas.items():
        casado = _PREFIXO_PATCHED.match(nome_componente)
        nome_base = casado.group(1) if casado else nome_componente
        propriedades_alias = ALIASES_DEPRECIADOS_NO_ESQUEMA.get(nome_base)
        if not propriedades_alias:
            continue
        propriedades = schema.get("properties", {})
        obrigatorias = schema.get("required")
        for nome_propriedade in propriedades_alias:
            propriedades.pop(nome_propriedade, None)
            if isinstance(obrigatorias, list) and nome_propriedade in obrigatorias:
                obrigatorias.remove(nome_propriedade)
    return result


def excluir_a_v2_do_contrato(endpoints: list[Any]) -> list[Any]:
    """`PREPROCESSING_HOOKS`: o `openapi.yaml` da v1 descreve a `/api/v1/`, e só ela.

    A `/api/v2/` monta-se sobre **os mesmos serializers**, e por isso sobre os mesmos componentes
    do esquema quando a geração é a da v1. Publicá-la ali emitiria ~240 caminhos novos apontando
    para componentes que ainda mostram as chaves-alias — e `deprecated: true` não é `ausente`. O
    contrato diria que `GET /api/v2/accounts/` devolve `status`, que é justamente o que a v2 não
    faz: seria uma mentira publicada, pior que o silêncio de não descrevê-la.

    Roda **antes** da montagem, e não depois: filtrar aqui mantém o prefixo comum que o
    drf-spectacular estima a partir dos caminhos (`/api/v1`) e, com ele, todo `operationId` do
    `openapi.yaml` commitado inalterado.

    No-op quando o alvo da geração é v2 (`alvo_da_geracao`): o urlconf dedicado
    (`config.urls_v2_schema`) já enumera só a árvore `/api/v2/`, então filtrar aqui esvaziaria a
    geração inteira — é exatamente por isso que o alvo é uma variável de ambiente explícita, e não
    algo que este hook tentasse inferir do `generator`.
    """
    if alvo_da_geracao() == V2:
        return endpoints
    return [
        endpoint for endpoint in endpoints if not str(endpoint[0]).startswith(PREFIXO_DA_V2)
    ]
