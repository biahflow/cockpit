"""Urlconf dedicado à geração do esquema da `/api/v2/` — nada além dela (issue #122, fatia 3b).

`manage.py spectacular` enumera endpoints a partir de **um** urlconf, e o de produção
(`config.urls`) inclui a v1 e a v2 lado a lado. Gerar o `openapi-v2.yaml` a partir dele obrigaria o
`PREPROCESSING_HOOKS` a filtrar a v1 fora — o inverso exato de `excluir_a_v2_do_contrato`, que
existe para manter a v2 fora do `openapi.yaml` da v1. Duas direções do mesmo filtro por cima da
mesma árvore são a chance de uma delas divergir da outra; um urlconf que só contém a v2 evita a
segunda direção — não há v1 para filtrar.

Nunca é o `ROOT_URLCONF` da aplicação; existe só para `manage.py spectacular --urlconf
config.urls_v2_schema` enxergar essa árvore.
"""

from __future__ import annotations

from django.urls import include, path

urlpatterns = [path("api/v2/", include("apps.core.urls_v2"))]
