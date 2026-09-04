"""O `urlconf` da `/api/v2/` — fino de propósito (issue #122).

Ele existe porque `include()` recebe um **módulo** e lê o `urlpatterns` dele; o que a v2 precisa é
de um nome de módulo próprio apontando para a segunda lista que `urls.py` já monta. Registrar as
rotas de novo aqui seria a segunda tabela que `urls.py` explica não ter.
"""

from __future__ import annotations

from .urls import urlpatterns_da_v2 as urlpatterns

__all__ = ["urlpatterns"]
