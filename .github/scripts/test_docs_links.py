"""Todo link relativo de Markdown do repositório resolve.

Roda como programa, no molde do `test_release_evidence.py`: sem rede, sem banco, sem
container. O corpus sai de `git ls-files`, nunca de uma lista digitada — lista escrita à mão
é lista que deixa de descrever o repositório no dia seguinte.

## Por que existe

A camada global da Engineering OS passou a viver vendorizada em `docs/engineering-os/`
(ADR 0045), e as referências a ela são links relativos. Sem portão, um link é só um caminho
que ninguém confere — foi assim que outros repositórios desta organização carregaram por
semanas uma instrução apontando para `~/workspace/engineeringOS/`, diretório da máquina de uma
pessoa. Ninguém percebeu quando ele deixou de existir, porque referência que não resolve não é
falha: é ausência.

Na mesma mudança, o Project Context saiu de `docs/engineering-os/project-context.md` para
`docs/project-context.md`, e **subir um nível quebra todo link relativo de dentro dele** — dez,
neste caso. Um arquivo movido com links intactos é precisamente o que nenhuma revisão humana
pega lendo o diff: o caminho continua parecendo certo.

O espelho entra no corpus de propósito. Espelho incompleto quebra os links internos entre os
documentos globais, que é exatamente o sinal desejado.
"""

from __future__ import annotations

import re
import subprocess
import unittest
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[2]
LINK = re.compile(r"\[([^\]]*)\]\(([^)\s]+)\)")
EXTERNO = ("http://", "https://", "mailto:", "#")


def markdown_rastreado() -> list[str]:
    """Os Markdown rastreados, derivados por glob e nunca digitados."""
    listagem = subprocess.run(
        ["git", "-C", str(RAIZ), "ls-files", "-z", "*.md"],
        capture_output=True,
        text=True,
        check=True,
    ).stdout
    return [entrada for entrada in listagem.split("\0") if entrada]


def links_quebrados(nome: str) -> list[str]:
    documento = RAIZ / nome
    falhas: list[str] = []
    for numero, linha in enumerate(documento.read_text(encoding="utf-8").splitlines(), 1):
        for _, alvo in LINK.findall(linha):
            if alvo.startswith(EXTERNO) or "{{" in alvo:
                continue
            caminho = alvo.split("#")[0]
            if not caminho:
                continue
            if not (documento.parent / caminho).resolve().exists():
                falhas.append(f"{nome}:{numero} -> {alvo}")
    return falhas


class LinksDeMarkdown(unittest.TestCase):
    def test_corpus_nao_esta_vazio(self) -> None:
        # Fail-closed: glob que devolve quase nada passaria por engano, dizendo que nada
        # está quebrado porque nada foi olhado.
        self.assertGreater(len(markdown_rastreado()), 50)

    def test_todo_link_relativo_resolve(self) -> None:
        falhas = [f for nome in markdown_rastreado() for f in links_quebrados(nome)]
        self.assertEqual(falhas, [], "links quebrados:\n  " + "\n  ".join(falhas))


if __name__ == "__main__":
    unittest.main()
