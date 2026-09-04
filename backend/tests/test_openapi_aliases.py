"""A depreciação dos aliases de leitura da `/api/v1/` no próprio contrato (issue #67).

`docs/ontology/aliases.md` §2c sempre disse, em prosa, que `client`/`status`/`opportunity`/
`processo`/`etapa`/`gate_outcome` são chave de compatibilidade e morrem na `/api/v2/`. Até aqui,
ninguém que só lesse `openapi.yaml` — ou o Swagger de `/api/docs/` — tinha como distinguir isso de
campo comum. `apps.core.openapi_aliases.ALIASES_DEPRECIADOS` é o mapa manual que fecha essa
lacuna, e um `POSTPROCESSING_HOOKS` (`config.settings.SPECTACULAR_SETTINGS`) marca
`deprecated: true` em cada propriedade dele na geração do esquema.

Esta guarda cobre a metade que o hook, sozinho, não protege: o **mapa** pode ficar comendo poeira.
Se um campo sair do serializer sem ninguém tirar a entrada correspondente, o mapa passaria a citar
uma propriedade que não existe mais — dívida morta e invisível, porque nada aqui dentro fica
vermelho sozinho. O teste (a) garante que toda entrada do mapa aponta para algo que o
`openapi.yaml` **commitado** de fato tem, e (b) garante que essa propriedade sai marcada
`deprecated: true` — o que também pega o hook desligado por engano ou um mapa que cresceu sem a
geração ter rodado de novo.

**Desde a issue #122, fatia 3b, este é também o teste do `openapi-v2.yaml`.** O contrato da v2
nasce verdadeiro (ADR 0066, decisão 5): as chaves de `ALIASES_DEPRECIADOS` não aparecem
`deprecated`, elas simplesmente não estão nos componentes — o espelho exato dos testes (a)/(b)
acima. As guardas abaixo cobrem, além da forma do artefato (só caminhos `/api/v2/`, sem as quatro
rotas legadas), o mecanismo que o produz: `openapi_aliases.alvo_da_geracao()` e o par de hooks
`marcar_aliases_depreciados`/`remover_aliases_do_contrato`, testados diretamente por monkeypatch de
`OPENAPI_ALVO` — sem depender de regenerar o arquivo em disco.

**Os testes de contrato iteram a união (`ALIASES_DEPRECIADOS_NO_ESQUEMA`)**, e não o mapa dos
serializers: para quem lê o `openapi.yaml`, a propriedade que a view remove à mão e a que o mixin
remove são a mesma coisa. A distinção entre as duas é sobre **quem executa**, e quem a cobra é
`test_aliases_da_v2.py`.

A última guarda é de outro tipo e fecha a fatia 4a: nenhuma propriedade de componente do
`openapi-v2.yaml` volta a dizer `client`. Ela não itera mapa nenhum — varre o artefato inteiro —,
porque o defeito que pega é justamente a chave que **ninguém** pôs no mapa.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest
import yaml
from django.conf import settings

from apps.core.openapi_aliases import (
    ALIASES_DEPRECIADOS_NO_ESQUEMA,
    excluir_a_v2_do_contrato,
    marcar_aliases_depreciados,
    remover_aliases_do_contrato,
)

OPENAPI_PATH = Path(settings.BASE_DIR) / "openapi.yaml"
OPENAPI_V2_PATH = Path(settings.BASE_DIR) / "openapi-v2.yaml"

# As quatro rotas legadas que `docs/ontology/aliases.md` sempre marcou para morrer na `/api/v2/`.
CAMINHOS_LEGADOS_DA_V2 = (
    "/api/v2/clients/",
    "/api/v2/opportunities/",
    "/api/v2/processos/",
    "/api/v2/processo-etapas/",
)

# Componentes principais o bastante para o teste de ausência de alias não passar por vacuidade.
_COMPONENTES_PRINCIPAIS = {"Account", "Project", "Document", "DigitalEmployee"}


def _contrato(caminho: Path) -> dict[str, Any]:
    return yaml.safe_load(caminho.read_text(encoding="utf-8"))


def _schemas_do_contrato() -> dict[str, Any]:
    conteudo = _contrato(OPENAPI_PATH)
    return conteudo["components"]["schemas"]


def _schemas_do_contrato_v2() -> dict[str, Any]:
    conteudo = _contrato(OPENAPI_V2_PATH)
    return conteudo["components"]["schemas"]


def test_toda_entrada_do_mapa_existe_no_contrato() -> None:
    """(a) — o mapa não cita componente nem propriedade que o `openapi.yaml` não tem.

    Isto é o que impede a entrada morta: sem esta guarda, remover um campo do serializer sem
    tirar a linha correspondente de `ALIASES_DEPRECIADOS` não deixaria nada vermelho — o hook
    simplesmente deixaria de encontrar a propriedade e passaria direto (ver
    `marcar_aliases_depreciados`), e o mapa ficaria falando de um alias que já morreu.
    """
    schemas = _schemas_do_contrato()
    relatorio: list[str] = []
    for nome_componente, propriedades_alias in ALIASES_DEPRECIADOS_NO_ESQUEMA.items():
        schema = schemas.get(nome_componente)
        if schema is None:
            relatorio.append(f"{nome_componente}: componente não existe em openapi.yaml")
            continue
        propriedades = schema.get("properties", {})
        for nome_propriedade in propriedades_alias:
            if nome_propriedade not in propriedades:
                relatorio.append(
                    f"{nome_componente}.{nome_propriedade}: propriedade não existe no componente"
                )

    assert relatorio == [], (
        "ALIASES_DEPRECIADOS (apps/core/openapi_aliases.py) cita alias que "
        "openapi.yaml não tem — mapa apodrecido, ver docstring do módulo:\n  "
        + "\n  ".join(relatorio)
    )


def test_toda_entrada_do_mapa_sai_depreciada() -> None:
    """(b) — cada propriedade do mapa sai com `deprecated: true` no `openapi.yaml` commitado."""
    schemas = _schemas_do_contrato()
    relatorio: list[str] = []
    for nome_componente, propriedades_alias in ALIASES_DEPRECIADOS_NO_ESQUEMA.items():
        schema = schemas.get(nome_componente)
        if schema is None:
            # Já reportado pelo teste acima; não duplica a mensagem aqui.
            continue
        propriedades = schema.get("properties", {})
        for nome_propriedade in propriedades_alias:
            propriedade = propriedades.get(nome_propriedade)
            if propriedade is not None and propriedade.get("deprecated") is not True:
                relatorio.append(f"{nome_componente}.{nome_propriedade}")

    assert relatorio == [], (
        "alias declarado em ALIASES_DEPRECIADOS sem `deprecated: true` em openapi.yaml — "
        "rode `uv run python manage.py spectacular --file openapi.yaml --validate` a partir de "
        "backend/ e confira o POSTPROCESSING_HOOKS em SPECTACULAR_SETTINGS:\n  "
        + "\n  ".join(relatorio)
    )


# ---------------------------------------------------------------------------------------------
# O contrato da v2 nasce, e nasce verdadeiro (issue #122, fatia 3b)
# ---------------------------------------------------------------------------------------------


def test_openapi_v2_so_descreve_a_v2_e_sem_as_rotas_legadas() -> None:
    """Todo caminho de `openapi-v2.yaml` começa com `/api/v2/`; as quatro rotas legadas não estão
    lá e a canônica (`/accounts/`) está — o urlconf dedicado (`config.urls_v2_schema`) e o alvo
    `v2` (`OPENAPI_ALVO`) produzindo exatamente a árvore que a ADR 0066 descreve.
    """
    contrato = _contrato(OPENAPI_V2_PATH)
    caminhos = list(contrato["paths"])

    assert caminhos, "openapi-v2.yaml não descreve nenhum caminho"
    fora_da_v2 = [caminho for caminho in caminhos if not caminho.startswith("/api/v2/")]
    assert fora_da_v2 == [], f"caminho fora da /api/v2/ em openapi-v2.yaml: {fora_da_v2}"
    for legado in CAMINHOS_LEGADOS_DA_V2:
        assert legado not in caminhos, f"rota legada {legado} não deveria existir na v2"
    assert "/api/v2/accounts/" in caminhos


def test_openapi_v2_nao_tem_as_chaves_alias_espelho_do_teste_da_v1() -> None:
    """O espelho de `test_toda_entrada_do_mapa_sai_depreciada`: na v1 a chave sai marcada
    `deprecated`, na v2 ela está **ausente** — de `properties` e de `required` — porque a forma
    do contrato só é verdadeira quando ele não promete o que a v2 não faz (ADR 0066, decisão 5).
    """
    schemas = _schemas_do_contrato_v2()

    ausentes = _COMPONENTES_PRINCIPAIS - schemas.keys()
    assert not ausentes, (
        f"componentes principais ausentes de openapi-v2.yaml ({ausentes}) — o teste passaria "
        "por vacuidade"
    )

    relatorio: list[str] = []
    for nome_componente, propriedades_alias in ALIASES_DEPRECIADOS_NO_ESQUEMA.items():
        schema = schemas.get(nome_componente)
        if schema is None:
            # Componente da v1 sem correspondente na v2 (nenhum hoje) — nada a verificar aqui.
            continue
        propriedades = schema.get("properties", {})
        obrigatorias = schema.get("required") or []
        for nome_propriedade in propriedades_alias:
            if nome_propriedade in propriedades:
                relatorio.append(f"{nome_componente}.{nome_propriedade}: ainda em properties")
            if nome_propriedade in obrigatorias:
                relatorio.append(f"{nome_componente}.{nome_propriedade}: ainda em required")

    assert relatorio == [], (
        "chave-alias sobrevivendo em openapi-v2.yaml — rode `OPENAPI_ALVO=v2 uv run python "
        "manage.py spectacular --urlconf config.urls_v2_schema --file openapi-v2.yaml "
        "--validate` a partir de backend/:\n  " + "\n  ".join(relatorio)
    )


# A única chave com «client» que o `openapi-v2.yaml` pode conter, e ela está declarada: o
# `recebido_do_cliente` do painel de cobrança é pt-BR e pertence à família de nomes que a fatia 5
# ainda vai traduzir (`docs/ontology/aliases.md`, "Termos ainda sem nome canônico"). Não é alias de
# `client` — é um nome que nunca teve canônico —, e por isso não cabe em `ALIASES_DEPRECIADOS`.
CHAVES_CLIENT_TOLERADAS_NA_V2 = frozenset({"recebido_do_cliente"})


def test_nenhuma_chave_client_sobra_na_v2() -> None:
    """A fatia 4a fechada, medida no artefato e não no mapa.

    As guardas acima iteram `ALIASES_DEPRECIADOS_NO_ESQUEMA`, então só enxergam o que alguém já
    declarou. Esta varre o `openapi-v2.yaml` inteiro pelo outro lado — toda propriedade de todo
    componente —, que é o único jeito de pegar a classe de defeito da fatia 4a: `client_name`,
    `clients`, `client_vertical` e o par do painel viveram meses no contrato **por nunca terem
    entrado no mapa**, e um teste que lê o mapa passaria por cima de todos eles.

    Vale para a chave, não para a prosa: `description` em português diz "cliente" o tempo todo, e
    isso é o texto em volta do termo, que a `language-map.md` §1 manda traduzir.
    """
    schemas = _schemas_do_contrato_v2()
    encontradas = sorted(
        f"{componente}.{propriedade}"
        for componente, schema in schemas.items()
        for propriedade in ((schema or {}).get("properties") or {})
        if "client" in propriedade and propriedade not in CHAVES_CLIENT_TOLERADAS_NA_V2
    )

    assert encontradas == [], (
        "chave com «client» sobrevivendo em openapi-v2.yaml — a v2 é onde a chave de payload "
        "legada morre (`docs/ontology/aliases.md` §2c):\n  " + "\n  ".join(encontradas)
    )


def test_a_chave_tolerada_na_v2_existe_de_fato() -> None:
    """A allowlist acima não guarda linha desnecessária — o molde de `legacy-allowlist.txt`.

    Sem isto, `recebido_do_cliente` continuaria isentado depois de a fatia 5 traduzi-lo, e a
    isenção morta esconderia que a dívida foi paga.
    """
    propriedades = {
        propriedade
        for schema in _schemas_do_contrato_v2().values()
        for propriedade in ((schema or {}).get("properties") or {})
    }

    assert CHAVES_CLIENT_TOLERADAS_NA_V2 <= propriedades


def test_versao_do_documento_e_por_alvo() -> None:
    """`info.version` marca a travessia: `1.0.0` na v1 (nunca mudou), `2.0.0` na v2."""
    assert _contrato(OPENAPI_PATH)["info"]["version"] == "1.0.0"
    assert _contrato(OPENAPI_V2_PATH)["info"]["version"] == "2.0.0"


# Schema mínimo para exercitar os hooks sem depender de regenerar o arquivo em disco: um
# componente do mapa (`Account`: alias `status` → canônico `lifecycle_status`) com a chave-alias
# presente em `properties` e em `required`, mais um componente de fora do mapa para provar que o
# hook não toca no que não é dele.
def _schema_bruto_para_hooks() -> dict[str, Any]:
    return {
        "components": {
            "schemas": {
                "Account": {
                    "properties": {
                        "status": {"type": "string"},
                        "lifecycle_status": {"type": "string"},
                    },
                    "required": ["status", "lifecycle_status"],
                },
                "Invoice": {
                    "properties": {"status": {"type": "string"}},
                    "required": ["status"],
                },
            }
        }
    }


def _rodar_hooks(schema: dict[str, Any]) -> dict[str, Any]:
    endpoints = [
        ("/api/v1/accounts/", "^/api/v1/accounts/$", "GET", object()),
        ("/api/v2/accounts/", "^/api/v2/accounts/$", "GET", object()),
    ]
    restantes = excluir_a_v2_do_contrato(endpoints=endpoints)
    resultado = marcar_aliases_depreciados(
        result=schema, generator=None, request=None, public=True
    )
    resultado = remover_aliases_do_contrato(
        result=resultado, generator=None, request=None, public=True
    )
    return {"endpoints_restantes": restantes, "schema": resultado}


def test_com_alvo_v2_o_preprocessing_nao_filtra_e_o_postprocessing_remove_de_required(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Teste de unidade do(s) hook(s) — alvo trocado por monkeypatch de env, sem tocar disco.

    Com `OPENAPI_ALVO=v2`: `excluir_a_v2_do_contrato` vira no-op (o urlconf dedicado já só tem v2,
    filtrar aqui esvaziaria a geração inteira) e `remover_aliases_do_contrato` apaga a chave-alias
    de `properties` **e** de `required` — deixar `required` órfão reprovaria o `--validate`. O
    componente fora do mapa (`Invoice`) não é tocado: `status` ali é campo real, não alias.
    """
    monkeypatch.setenv("OPENAPI_ALVO", "v2")

    saida = _rodar_hooks(_schema_bruto_para_hooks())

    assert [c for c, *_ in saida["endpoints_restantes"]] == [
        "/api/v1/accounts/",
        "/api/v2/accounts/",
    ]
    account = saida["schema"]["components"]["schemas"]["Account"]
    assert "status" not in account["properties"]
    assert "status" not in account["required"]
    assert "lifecycle_status" in account["properties"]

    invoice = saida["schema"]["components"]["schemas"]["Invoice"]
    assert "status" in invoice["properties"]
    assert "status" in invoice["required"]


def test_com_alvo_v1_os_hooks_mantem_o_comportamento_de_hoje(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """O mesmo par de hooks, com `OPENAPI_ALVO` ausente (o default): filtra a v2 fora do
    `openapi.yaml` e marca `deprecated: true` em vez de remover — nada muda em relação ao
    comportamento anterior à fatia 3b.
    """
    monkeypatch.delenv("OPENAPI_ALVO", raising=False)

    saida = _rodar_hooks(_schema_bruto_para_hooks())

    assert [c for c, *_ in saida["endpoints_restantes"]] == ["/api/v1/accounts/"]
    account = saida["schema"]["components"]["schemas"]["Account"]
    assert account["properties"]["status"]["deprecated"] is True
    assert "status" in account["required"]


# Schema mínimo para o teste **direto** de `marcar_aliases_depreciados`, isolado dos outros dois
# hooks: `_rodar_hooks` sempre os chama em cadeia e nunca inclui a forma `Patched*`, que é
# exatamente o pedaço que `_PREFIXO_PATCHED` existe para cobrir. `Task` entra como componente fora
# do mapa que tem um campo **de verdade** chamado `status` — a mesma string da chave-alias de
# `Account` —, para provar que quem decide é o componente estar em `ALIASES_DEPRECIADOS`, nunca o
# nome da propriedade coincidir com um alias de outro lugar.
def _schema_bruto_com_patched() -> dict[str, Any]:
    return {
        "components": {
            "schemas": {
                "Account": {
                    "properties": {
                        "status": {"type": "string"},
                        "lifecycle_status": {"type": "string"},
                    },
                },
                "PatchedAccount": {
                    "properties": {
                        "status": {"type": "string"},
                        "lifecycle_status": {"type": "string"},
                    },
                },
                "Task": {
                    "properties": {"status": {"type": "string"}},
                },
            }
        }
    }


def test_marcar_aliases_depreciados_e_direto_e_cobre_o_patched(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Teste direto de `marcar_aliases_depreciados`, no molde dos que já existem para os outros
    dois hooks — sem passar pelo `_rodar_hooks`, que só exercita o trio junto e nunca inclui a
    forma `Patched*`.
    """
    monkeypatch.delenv("OPENAPI_ALVO", raising=False)

    resultado = marcar_aliases_depreciados(
        result=_schema_bruto_com_patched(), generator=None, request=None, public=True
    )

    schemas = resultado["components"]["schemas"]
    assert schemas["Account"]["properties"]["status"]["deprecated"] is True
    assert "deprecated" not in schemas["Account"]["properties"]["lifecycle_status"]

    # A forma `Patched*` casa pelo regex e ganha a mesma marca — sem isto o `PatchedAccount` do
    # corpo de `PATCH` sairia do `openapi.yaml` anunciando `status` como campo comum.
    assert schemas["PatchedAccount"]["properties"]["status"]["deprecated"] is True
    assert "deprecated" not in schemas["PatchedAccount"]["properties"]["lifecycle_status"]

    # `Task` não está em `ALIASES_DEPRECIADOS_NO_ESQUEMA`: o `status` dela é campo real, e o hook
    # não pode marcá-lo só porque o nome coincide com o alias de outro componente.
    assert "deprecated" not in schemas["Task"]["properties"]["status"]


def test_marcar_aliases_depreciados_e_no_op_no_alvo_v2(monkeypatch: pytest.MonkeyPatch) -> None:
    """No alvo v2 o hook não anota nada — quem remove é `remover_aliases_do_contrato` — e o
    esquema sai bit a bit igual ao que entrou, incluindo o `Task` fora do mapa.
    """
    monkeypatch.setenv("OPENAPI_ALVO", "v2")
    schema = _schema_bruto_com_patched()

    resultado = marcar_aliases_depreciados(
        result=schema, generator=None, request=None, public=True
    )

    assert resultado == _schema_bruto_com_patched()


def test_alvo_da_geracao_normaliza_maiuscula_e_espaco(monkeypatch: pytest.MonkeyPatch) -> None:
    """`alvo_da_geracao` não é sensível a maiúscula/espaço — é lido de um env var digitado à mão
    no comando do CI e do desenvolvedor.
    """
    from apps.core.openapi_aliases import alvo_da_geracao

    monkeypatch.setenv("OPENAPI_ALVO", " V2 ")
    assert alvo_da_geracao() == "v2"

    monkeypatch.delenv("OPENAPI_ALVO", raising=False)
    assert alvo_da_geracao() == "v1"
