"""O índice de ADRs (`docs/adr/README.md`) é escrito à mão, uma linha por ADR, no mesmo commit
que cria a ADR — e foi assim que dez entradas divergiram do `#` do arquivo que deveriam
espelhar, uma a uma, sem que nada acusasse. Esta guarda compara as duas strings byte a byte.
"""

import re
from pathlib import Path

from django.conf import settings

REPO_ROOT = Path(settings.BASE_DIR).parent
ADR_DIR = REPO_ROOT / "docs" / "adr"
INDICE = ADR_DIR / "README.md"

LINHA_DE_ENTRADA = re.compile(r"^- (\d{4}) — (.+)$")
LINHA_DE_TITULO = re.compile(r"^# ADR (\d{4}) — (.+)$")
NOME_DE_ARQUIVO = re.compile(r"^\d{4}-.+\.md$")


def _entradas_do_indice() -> dict[str, str]:
    """Número -> título, para cada linha `- NNNN — ...` do índice."""
    entradas: dict[str, str] = {}
    for linha in INDICE.read_text(encoding="utf-8").splitlines():
        m = LINHA_DE_ENTRADA.match(linha)
        if m:
            entradas[m.group(1)] = m.group(2)
    return entradas


def _numeros_do_indice() -> list[str]:
    """Números das entradas do índice, na ordem em que aparecem — preserva duplicata.

    `_entradas_do_indice` devolve um dict e colapsaria duas entradas para o mesmo número
    em uma só, em silêncio; esta lista é o que permite acusar a duplicata.
    """
    numeros = []
    for linha in INDICE.read_text(encoding="utf-8").splitlines():
        m = LINHA_DE_ENTRADA.match(linha)
        if m:
            numeros.append(m.group(1))
    return numeros


def _arquivos_de_adr() -> list[Path]:
    """Todo arquivo de ADR, na convenção `NNNN-*.md`. `README.md` não casa e fica de fora."""
    return sorted(ADR_DIR.glob("[0-9][0-9][0-9][0-9]-*.md"))


def test_titulo_da_entrada_espelha_o_cabecalho_do_arquivo() -> None:
    """O índice é derivado: a entrada não pode dizer nada que o `#` do arquivo já não diga.

    Foi por reescrever, encurtar ou anotar a entrada — em vez de copiar o `#` — que dez ADRs
    divergiram do próprio arquivo sem que nada no repositório acusasse.
    """
    entradas = _entradas_do_indice()
    for arquivo in _arquivos_de_adr():
        numero = arquivo.name[:4]
        primeira_linha = arquivo.read_text(encoding="utf-8").splitlines()[0]
        m = LINHA_DE_TITULO.match(primeira_linha)
        assert m is not None, (
            f"ADR {numero}: cabeçalho fora do formato esperado: {primeira_linha!r}"
        )
        titulo_do_arquivo = m.group(2)
        titulo_do_indice = entradas.get(numero)
        assert titulo_do_indice == titulo_do_arquivo, (
            f"ADR {numero}: entrada do índice diverge do cabeçalho do arquivo.\n"
            f"  índice:  {titulo_do_indice!r}\n"
            f"  arquivo: {titulo_do_arquivo!r}"
        )


def test_todo_arquivo_de_adr_aparece_exatamente_uma_vez_no_indice() -> None:
    """Cobertura nos dois sentidos, e sem duplicata nem no índice nem no conjunto de arquivos."""
    numeros_de_arquivo = [arquivo.name[:4] for arquivo in _arquivos_de_adr()]
    numeros_do_indice = _numeros_do_indice()

    faltando = sorted(set(numeros_de_arquivo) - set(numeros_do_indice))
    assert not faltando, f"ADR(s) sem entrada no índice: {faltando}"

    sobrando = sorted(set(numeros_do_indice) - set(numeros_de_arquivo))
    assert not sobrando, f"Entrada(s) no índice sem arquivo correspondente: {sobrando}"

    duplicadas_no_indice = sorted(
        {numero for numero in numeros_do_indice if numeros_do_indice.count(numero) > 1}
    )
    assert not duplicadas_no_indice, (
        f"ADR(s) com mais de uma entrada no índice: {duplicadas_no_indice}"
    )

    duplicadas_em_arquivo = sorted(
        {numero for numero in numeros_de_arquivo if numeros_de_arquivo.count(numero) > 1}
    )
    assert not duplicadas_em_arquivo, f"ADR(s) com mais de um arquivo: {duplicadas_em_arquivo}"


def test_formato_das_linhas_e_numero_do_arquivo() -> None:
    """Cada linha de entrada e cada cabeçalho seguem o formato fixo, o número bate com o nome
    do arquivo, e todo `.md` de `docs/adr/` (fora `README.md`) segue a convenção `NNNN-*.md` —
    sem isso a forma de burlar as outras asserções é nomear o arquivo errado."""
    linhas_de_entrada = [
        linha
        for linha in INDICE.read_text(encoding="utf-8").splitlines()
        if linha.startswith("- ")
    ]
    for linha in linhas_de_entrada:
        assert LINHA_DE_ENTRADA.match(linha), (
            f"Linha de entrada fora do formato esperado: {linha!r}"
        )

    for arquivo in ADR_DIR.glob("*.md"):
        if arquivo.name == "README.md":
            continue
        assert NOME_DE_ARQUIVO.match(arquivo.name), (
            f"Nome de arquivo fora da convenção NNNN-*.md: {arquivo.name!r}"
        )

    for arquivo in _arquivos_de_adr():
        primeira_linha = arquivo.read_text(encoding="utf-8").splitlines()[0]
        m = LINHA_DE_TITULO.match(primeira_linha)
        assert m is not None, (
            f"Cabeçalho fora do formato esperado em {arquivo.name}: {primeira_linha!r}"
        )
        assert m.group(1) == arquivo.name[:4], (
            f"{arquivo.name}: número do cabeçalho ({m.group(1)}) não bate com o nome do arquivo"
        )
