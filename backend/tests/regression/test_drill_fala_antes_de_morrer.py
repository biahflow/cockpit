"""Regressão: a paridade de major do drill **fala** ao reprovar, em vez de morrer calada (ADR 0013).

O defeito: `backup-drill.sh` lê a major do Postgres dos dois lados (o `db` do
`docker-compose.prod.yml` e o sidecar de `ops/backup/Dockerfile`) e tem uma mensagem escrita para o
caso de não conseguir ler. Ela nunca era alcançada — sob `set -euo pipefail`, um `grep` sem
casamento derruba a substituição de comando **antes** da checagem. Quando o `db` virou
`pgvector/pgvector:pg16` (FDD 029), o padrão parou de casar e o job passou a morrer em três
segundos sem imprimir uma linha: entre 08/08 e 12/08 o CI ficou vermelho sem dizer por quê, e o
teste de mesa da restauração deixou de ser exercitado sem que ninguém percebesse.

Estes casos param **antes** do Docker — a guarda é a primeira coisa do script —, então rodam na
suíte comum e em segundos. O que eles pinam não é a leitura em si: é que a reprovação **tem voz**.
"""

import shutil
import subprocess
from pathlib import Path

import pytest

RAIZ = Path(__file__).resolve().parents[3]
DRILL = RAIZ / ".github" / "scripts" / "backup-drill.sh"
COMPOSE = "docker-compose.prod.yml"
SIDECAR = Path("ops") / "backup" / "Dockerfile"


@pytest.fixture
def copia(tmp_path: Path) -> Path:
    """Uma cópia do que a guarda lê, para poder ser sabotada sem tocar no repositório.

    O script faz `cd "$(dirname "$0")/../.."`, então o que manda é onde o **script** está — não o
    diretório de trabalho de quem o chama.
    """
    (tmp_path / ".github" / "scripts").mkdir(parents=True)
    (tmp_path / SIDECAR.parent).mkdir(parents=True)
    shutil.copy(DRILL, tmp_path / ".github" / "scripts" / DRILL.name)
    shutil.copy(RAIZ / COMPOSE, tmp_path / COMPOSE)
    shutil.copy(RAIZ / SIDECAR, tmp_path / SIDECAR)
    return tmp_path


def rodar(raiz: Path) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["bash", str(raiz / ".github" / "scripts" / "backup-drill.sh")],
        capture_output=True,
        text=True,
        timeout=120,
    )


def test_a_leitura_impossivel_e_dita_em_voz_alta(copia: Path) -> None:
    """Uma imagem que a guarda não reconhece reprova **dizendo** que não conseguiu ler.

    É o caso exato de 08/08: a imagem do `db` mudou de nome e o padrão deixou de casar.
    """
    caminho = copia / COMPOSE
    caminho.write_text(caminho.read_text().replace("pgvector/pgvector:pg16", "umbanco/qualquer:latest"))

    saida = rodar(copia)

    assert saida.returncode == 1
    assert "DRILL REPROVADO: não consegui ler a major" in saida.stderr


def test_major_divergente_reprova_pelo_motivo_certo(copia: Path) -> None:
    """A invariante que a guarda existe para proteger: `pg_dump` de major menor recusa rodar."""
    caminho = copia / SIDECAR
    caminho.write_text(caminho.read_text().replace("postgres:16-alpine", "postgres:15-alpine"))

    saida = rodar(copia)

    assert saida.returncode == 1
    assert "major divergente: db=16, sidecar=15" in saida.stderr


def test_o_repositorio_como_esta_passa_pela_guarda(copia: Path) -> None:
    """O caso positivo, e o que teria pegado a FDD 029 no dia.

    Só se afirma sobre a **linha da paridade**: o resto do drill precisa de Docker e vive no job de
    CI. Aqui o script segue para o `compose build` e falha adiante — o que importa é que a paridade
    foi conferida e dita antes disso.

    E falha **rápido** mesmo numa máquina com Docker de pé: o contexto `./backend` não foi para a
    cópia — só o `ops/backup/Dockerfile`, que a guarda precisa ler —, então o `build` do `api`
    recusa na hora em vez de construir imagem dentro de um teste de unidade.
    """
    saida = rodar(copia)

    assert "paridade de major conferida: db=16, sidecar=16" in saida.stdout
