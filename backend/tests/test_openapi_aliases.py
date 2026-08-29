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
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml
from django.conf import settings

from apps.core.openapi_aliases import ALIASES_DEPRECIADOS

OPENAPI_PATH = Path(settings.BASE_DIR) / "openapi.yaml"


def _schemas_do_contrato() -> dict[str, Any]:
    conteudo = yaml.safe_load(OPENAPI_PATH.read_text(encoding="utf-8"))
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
    for nome_componente, propriedades_alias in ALIASES_DEPRECIADOS.items():
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
    for nome_componente, propriedades_alias in ALIASES_DEPRECIADOS.items():
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
