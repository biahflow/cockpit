"""O mapa dos aliases de leitura da `/api/v1/`, e o hook que os marca como depreciados no contrato.

A `docs/ontology/aliases.md` §2c já diz, em prosa, que a chave legada continua saindo em cada
serializer que a issue #67 renomeou — mas ninguém que só lê `openapi.yaml` ou o Swagger de
`/api/docs/` enxerga essa prosa. Este módulo é o que fecha a lacuna: um mapa declarativo de
componente → propriedades-alias, e um `POSTPROCESSING_HOOKS` (`config/settings.py`,
`SPECTACULAR_SETTINGS`) que marca `deprecated: true` em cada uma delas na geração do esquema.

**Por que o mapa é escrito à mão, e não inferido do código.** A tentação óbvia é varrer os
serializers e marcar como depreciado todo campo declarado com `source=` apontando para outro nome
— é exatamente o padrão sintático que o `AliasDeEntradaMixin` e os aliases de leitura usam
(`apps/core/serializers.py:122-140` e os comentários "Alias de leitura da `/api/v1/`" espalhados
pelo arquivo). O problema é que a maioria dos `source=` do repositório **não** é alias de
compatibilidade: é projeção legítima, do mesmo jeito que `client_name = CharField(source=
"account.name")` ou `is_overdue = BooleanField(read_only=True)`. Inferir por sintaxe marcaria como
"vai morrer na v2" um campo que não tem nenhuma intenção de morrer, e a mentira no contrato é pior
que o silêncio que este módulo substitui. Só quem sabe que uma chave é sinônimo do nome canônico —
e não uma leitura nova sobre ele — é quem leu `aliases.md`; por isso o mapa é a tradução manual
dele para o vocabulário do OpenAPI, revisada junto com o serializer na hora de cada fatia.

O mapa cobre dois mecanismos, e os dois produzem a mesma forma no esquema (uma propriedade
`read_only` com `source=` apontando para o campo canônico):

- os doze serializers que usam `AliasDeEntradaMixin` para aceitar também a chave antiga em
  `POST`/`PATCH` (`ALIASES_DE_ENTRADA` em cada um);
- os aliases só-de-leitura que não precisam de escrita porque o vínculo é lavrado por uma action
  própria — a chave legada do gate em `ProjectPhase`/`PhaseEvent` (`apply-gate`/`set-waiting`,
  `docs/ontology/aliases.md` §2c), `Lead.client`/`Lead.opportunity` (`convert`/
  `open-opportunity`) e `Project.opportunity` (`convert-to-project`).

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

import re
from typing import Any

# Espelho de `docs/ontology/aliases.md` §2c. Cada entrada morre quando o campo dela morrer —
# na `/api/v2/` — e nenhuma antes, porque a chave continua respondendo até lá.
# Isolado numa constante para a chave legada do gate (ver nota acima) aparecer uma única vez
# no arquivo — é a única referência do módulo que a regra `outcome-como-decisao-de-gate` casa.
_CHAVE_LEGADA_DO_GATE: tuple[str, ...] = ("gate_outcome",)

ALIASES_DEPRECIADOS: dict[str, tuple[str, ...]] = {
    "Account": ("status",),
    "Activity": ("client", "opportunity"),
    "Artifact": ("opportunity",),
    "CobrancaContato": ("client",),
    "CobrancaSuspensao": ("client",),
    "CommercialOpportunity": ("client",),
    "Contact": ("client",),
    "Document": ("client", "opportunity"),
    "Invoice": ("client",),
    "Lead": ("client", "opportunity"),
    "PhaseEvent": _CHAVE_LEGADA_DO_GATE,
    "Process": ("client",),
    "ProcessStep": ("processo",),
    "Project": ("opportunity",),
    "ProjectPhase": _CHAVE_LEGADA_DO_GATE,
    "Satisfacao": ("client",),
}

_PREFIXO_PATCHED = re.compile(r"^Patched(.+)$")


def marcar_aliases_depreciados(
    result: dict[str, Any], generator: Any, request: Any, public: bool
) -> dict[str, Any]:
    """`POSTPROCESSING_HOOKS`: marca `deprecated: true` em cada propriedade de `ALIASES_DEPRECIADOS`.

    Roda depois de o esquema estar montado, então só toca `components.schemas` — nunca decide
    forma de request/response, só anota o que já existe. Um componente sem entrada no mapa, ou uma
    propriedade que o mapa cita mas o schema não tem, passa direto: é o teste
    `test_openapi_aliases.py` que garante que o mapa não apodrece (entrada morta) nem fica atrás do
    código (alias novo sem entrada).
    """
    schemas = result.get("components", {}).get("schemas", {})
    for nome_componente, schema in schemas.items():
        casado = _PREFIXO_PATCHED.match(nome_componente)
        nome_base = casado.group(1) if casado else nome_componente
        propriedades_alias = ALIASES_DEPRECIADOS.get(nome_base)
        if not propriedades_alias:
            continue
        propriedades = schema.get("properties", {})
        for nome_propriedade in propriedades_alias:
            propriedade = propriedades.get(nome_propriedade)
            if propriedade is not None:
                propriedade["deprecated"] = True
    return result
