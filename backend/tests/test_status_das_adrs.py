"""O campo Status das ADRs teve três vocabulários e três formatos estruturais ao mesmo tempo —
`aceito` inline, `aceita` em bullet, `## Status` como subtítulo próprio — até a convergência
registrada em `docs/adr/README.md`: campo inline, primeira linha não vazia depois do `#`,
conjunto fechado de três valores em pt-BR. Esta guarda reprova qualquer ADR nova ou editada
que volte a divergir, nos mesmos moldes de `test_indice_de_adrs.py`.
"""

import re
from pathlib import Path

from django.conf import settings

REPO_ROOT = Path(settings.BASE_DIR).parent
ADR_DIR = REPO_ROOT / "docs" / "adr"

LINHA_DE_STATUS = re.compile(r"^\*\*Status:\*\*")
VALOR_CANONICO = re.compile(
    r"^\*\*Status:\*\* (aceita|superada pela ADR (\d{4})|superada em parte pela ADR (\d{4}))$"
)
FORMA_BULLET = re.compile(r"^- \*\*Status")
FORMA_SUBTITULO = re.compile(r"^## Status")


def _arquivos_de_adr() -> list[Path]:
    """Todo arquivo de ADR, na convenção `NNNN-*.md`. `README.md` não casa e fica de fora."""
    return sorted(ADR_DIR.glob("[0-9][0-9][0-9][0-9]-*.md"))


def _primeira_linha_nao_vazia_apos_titulo(linhas: list[str]) -> str | None:
    """A primeira linha com conteúdo depois de `linhas[0]` (o `# ADR NNNN — ...`)."""
    for linha in linhas[1:]:
        if linha.strip() != "":
            return linha
    return None


def test_toda_adr_tem_exatamente_uma_linha_de_status_como_primeira_linha_apos_o_titulo() -> None:
    """D2: o campo é inline e é a segunda linha não vazia do arquivo — logo abaixo do `#`."""
    for arquivo in _arquivos_de_adr():
        linhas = arquivo.read_text(encoding="utf-8").splitlines()
        ocorrencias = [linha for linha in linhas if LINHA_DE_STATUS.match(linha)]
        assert len(ocorrencias) == 1, (
            f"{arquivo.name}: esperava exatamente uma linha '**Status:**', achou "
            f"{len(ocorrencias)}: {ocorrencias!r}"
        )
        primeira = _primeira_linha_nao_vazia_apos_titulo(linhas)
        assert primeira is not None and LINHA_DE_STATUS.match(primeira), (
            f"{arquivo.name}: a primeira linha não vazia depois do título deveria ser "
            f"'**Status:** ...', achou {primeira!r}"
        )


def test_valor_do_status_pertence_ao_conjunto_fechado() -> None:
    """D1: só `aceita`, `superada pela ADR NNNN` ou `superada em parte pela ADR NNNN` — nenhum
    estado sem ocorrência real (`proposta`, `revogada`, `rascunho`, ...)."""
    for arquivo in _arquivos_de_adr():
        linhas = arquivo.read_text(encoding="utf-8").splitlines()
        linha_de_status = next((linha for linha in linhas if LINHA_DE_STATUS.match(linha)), None)
        assert linha_de_status is not None, f"{arquivo.name}: nenhuma linha de status encontrada"
        assert VALOR_CANONICO.match(linha_de_status), (
            f"{arquivo.name}: valor de status fora do conjunto fechado: {linha_de_status!r}"
        )


def test_referencia_de_sucessao_aponta_para_adr_existente() -> None:
    """D5: `superada (em parte) pela ADR NNNN` só é uma referência válida se `NNNN-*.md`
    existir em `docs/adr/`."""
    numeros_existentes = {arquivo.name[:4] for arquivo in _arquivos_de_adr()}
    for arquivo in _arquivos_de_adr():
        linhas = arquivo.read_text(encoding="utf-8").splitlines()
        linha_de_status = next((linha for linha in linhas if LINHA_DE_STATUS.match(linha)), None)
        assert linha_de_status is not None, f"{arquivo.name}: nenhuma linha de status encontrada"
        m = VALOR_CANONICO.match(linha_de_status)
        assert m is not None, f"{arquivo.name}: valor de status fora do conjunto fechado"
        numero_referenciado = m.group(2) or m.group(3)
        if numero_referenciado is not None:
            assert numero_referenciado in numeros_existentes, (
                f"{arquivo.name}: status referencia ADR {numero_referenciado}, que não existe "
                f"em {ADR_DIR}: {linha_de_status!r}"
            )


def test_nenhuma_adr_usa_as_formas_antigas() -> None:
    """D3: as três famílias convergem para D2 — não sobra bullet nem subtítulo `## Status`."""
    for arquivo in sorted(ADR_DIR.glob("*.md")):
        for numero_da_linha, linha in enumerate(
            arquivo.read_text(encoding="utf-8").splitlines(), start=1
        ):
            assert not FORMA_BULLET.match(linha), (
                f"{arquivo.name}:{numero_da_linha}: forma antiga em bullet ainda presente: "
                f"{linha!r}"
            )
            assert not FORMA_SUBTITULO.match(linha), (
                f"{arquivo.name}:{numero_da_linha}: forma antiga em subtítulo ainda presente: "
                f"{linha!r}"
            )


def test_linha_de_status_sem_espaco_em_branco_a_direita() -> None:
    """D2: sem espaços em branco no fim da linha — vários `Accepted` chegavam com dois espaços
    de quebra de linha markdown; a conversão para `aceita` não pode carregar o resíduo."""
    for arquivo in _arquivos_de_adr():
        linhas = arquivo.read_text(encoding="utf-8").splitlines()
        linha_de_status = next((linha for linha in linhas if LINHA_DE_STATUS.match(linha)), None)
        assert linha_de_status is not None, f"{arquivo.name}: nenhuma linha de status encontrada"
        assert linha_de_status == linha_de_status.rstrip(), (
            f"{arquivo.name}: linha de status com espaço em branco à direita: "
            f"{linha_de_status!r}"
        )
