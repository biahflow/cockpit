"""Quebra do nome legado de contato em nome e sobrenome (issue #55, FDD 001).

Extraída da migração de dados para ser testável sem depender de `django_test_migrations`
(ausente deste projeto): o teste de regressão importa `split_full_name` diretamente, e a
migração (`apps/core/migrations/0048_contact_first_last_name.py`) importa a mesma função —
uma definição só, não duas que podem divergir em silêncio.
"""

from __future__ import annotations


def split_full_name(raw: str) -> tuple[str, str]:
    """Quebra `raw` no primeiro espaço: `first_name` fica com a primeira palavra, `last_name`
    com o resto (que pode ter espaços internos).

    - "Daniel Pilar" -> ("Daniel", "Pilar")
    - "Ana Paula Sá" -> ("Ana", "Paula Sá") — sobrenome não é rebatizado em três fragmentos.
    - "Madonna" -> ("Madonna", "") — sobrenome é opcional.
    - "" ou só espaços -> ("", "") — não quebra a migração.
    """
    cleaned = raw.strip()
    if not cleaned:
        return "", ""
    first, _, rest = cleaned.partition(" ")
    return first, rest.strip()
