"""Base de conhecimento interna: corpus, frescor e resposta ancorada (FDD 029, ADR 0022, ADR 0023).

"Assistente de base de conhecimento" soa como produto novo e não é: é **o corpus sobre o qual os
agentes que já existem se apoiam**. Antes disto o portal não tinha nenhum — `ai.build_project_context`
passa documento como **nome**, nunca conteúdo (anti-vazamento, e continua assim), e a metodologia da
casa vivia no repositório, fora do alcance dos agentes.

O módulo tem quatro camadas, e a ordem importa:

1. **Fatiar** (`chunk_markdown`) — puro, sem I/O, sem banco. Corta por cabeçalho, nunca no meio de
   uma seção, porque é isso que faz a citação ser *exata* ("ADR 0013 — … › Decisão") em vez de
   estimada. Citação que não dá para conferir em dez segundos não vale como citação.
2. **Congelar** (`build_corpus`/`load_corpus`) — o corpus vira um artefato **gerado e commitado**,
   `knowledge_corpus.jsonl`, conferido no CI por `git diff --exit-code`. É o mesmo objeto que o
   `openapi.yaml` já é, com outro gerador. Ver a nota abaixo sobre por que não é leitura de disco.
3. **Frescor** (`freshness`, `check_freshness`) — funciona com `AI_ENABLED=false` e é a metade que
   sozinha já entrega o inventário: quem responde por quê, e o que venceu.
4. **Ancorar** (`ground`, `enforce_citations`) — recuperação e a regra de citar-ou-declarar-lacuna.

**Por que o corpus é artefato e não leitura de `docs/`.** O runtime não tem `docs/`: o
`backend/Dockerfile` é `COPY . .` com contexto `./backend`, e o dev monta só `./backend:/app`.
Mudar o contexto para a raiz resolveria — e tornaria **inerte** o `backend/.dockerignore`, cujo
propósito declarado é manter os **documentos reais de cliente** de `media/` fora da imagem que vai
para o registry. Um artefato commitado custa um passo de CI e não arrisca nada disso.
"""

from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass
from pathlib import Path

# Cabeçalhos de nível 1 a 3 abrem seção. `####` em diante fica **dentro** da seção-pai de
# propósito: o corpus quase não os usa, e cortar ali fragmentaria listas no meio.
_HEADING = re.compile(r"^(#{1,3})\s+(.*\S)\s*$")
_FENCE = re.compile(r"^\s*(```|~~~)")
# Item de lista de primeiro nível (sem recuo): fronteira de quebra para seções longas.
_TOP_BULLET = re.compile(r"^([-*+]|\d+\.)\s+\S")

# Acima disto a seção é quebrada, em fronteira semântica (ver `_split_long`). Medido no corpus real
# depois de fatiado: 421 trechos, mediana de 129 palavras, p95 de 383 e um único acima de 500 — o
# teto corta pouco e o trecho continua legível sozinho.
MAX_WORDS = 350

# Sem sobreposição, e isso é escolha e não economia. Sobreposição é a muleta de quem fatia em
# deslocamento arbitrário, onde uma frase é guilhotinada no meio. Aqui toda fronteira é semântica —
# cabeçalho, linha em branco ou início de item de lista —, então sobrepor só duplicaria token no
# prompt e produziria dois acertos para o mesmo trecho no top-k.


@dataclass(frozen=True)
class Chunk:
    """Um trecho recuperável, ancorado numa seção."""

    source_path: str
    title: str
    kind: str
    position: int
    heading_path: str
    content: str

    @property
    def content_hash(self) -> str:
        return hashlib.sha256(
            f"{self.heading_path}\n{self.content}".encode()
        ).hexdigest()

    def as_json(self) -> dict:
        return {
            "source_path": self.source_path,
            "title": self.title,
            "kind": self.kind,
            "position": self.position,
            "heading_path": self.heading_path,
            "content": self.content,
            "content_hash": self.content_hash,
        }


def _split_sections(text: str) -> list[tuple[list[str], list[str]]]:
    """Quebra o texto em (pilha de cabeçalhos, linhas), respeitando blocos de código.

    A guarda de cerca não é zelo: `docs/operacao.md` e os runbooks estão cheios de blocos com
    comentários `# assim`, e sem ela cada um deles viraria uma seção fantasma cujo "título" é um
    comentário de shell.
    """
    secoes: list[tuple[list[str], list[str]]] = []
    pilha: list[str] = []
    atual: list[str] = []
    dentro_de_cerca = False

    for linha in text.splitlines():
        if _FENCE.match(linha):
            dentro_de_cerca = not dentro_de_cerca
        cabecalho = None if dentro_de_cerca else _HEADING.match(linha)
        if cabecalho is None:
            atual.append(linha)
            continue
        if atual or pilha:
            secoes.append((list(pilha), atual))
        nivel, titulo = len(cabecalho.group(1)), cabecalho.group(2)
        pilha = pilha[: nivel - 1]
        while len(pilha) < nivel - 1:
            pilha.append("")
        pilha.append(titulo)
        atual = []
    if atual or pilha:
        secoes.append((list(pilha), atual))
    return secoes


def _split_long(lines: list[str]) -> list[str]:
    """Quebra uma seção longa em fronteira **semântica**, nunca dentro de um bloco de código.

    Duas fronteiras valem: linha em branco e **início de item de lista de primeiro nível**.

    O item de lista não é refinamento — sem ele o fatiador não quebra as seções que mais importam.
    As seções "Regras" das FDDs são listas de `- **Nome.** explicação` **sem linha em branco entre
    os itens** (a da FDD 019 tem 71 linhas e duas em branco), então a fronteira de parágrafo
    sozinha deixava blocos de quase mil palavras.

    Quebrar *entre* itens preserva o que importa: cada item é uma regra inteira. Quebrar *dentro*
    de um seria pior que não quebrar — meia lista de regras lida como a lista completa, e num
    corpus de metodologia isso não é um trecho grande demais, é uma resposta errada.
    """
    partes: list[str] = []
    atual: list[str] = []
    palavras = 0
    dentro_de_cerca = False

    for linha in lines:
        if _FENCE.match(linha):
            dentro_de_cerca = not dentro_de_cerca
        eh_fronteira = not dentro_de_cerca and (
            not linha.strip() or bool(_TOP_BULLET.match(linha))
        )
        if eh_fronteira and palavras >= MAX_WORDS and atual:
            partes.append("\n".join(atual).strip())
            atual, palavras = [], 0
        atual.append(linha)
        palavras += len(linha.split())
    resto = "\n".join(atual).strip()
    if resto:
        partes.append(resto)
    return partes or [""]


def chunk_markdown(text: str, *, source_path: str, kind: str, fallback_title: str) -> list[Chunk]:
    """Fatia um markdown em trechos citáveis. Puro: mesma entrada, mesma saída, sempre.

    O determinismo é requisito, não elegância — o artefato é conferido por `git diff` no CI, e um
    fatiador que ordena diferente entre execuções faria o gate acusar mudança onde não houve.
    """
    secoes = _split_sections(text.replace("\r\n", "\n"))
    titulo = fallback_title
    for pilha, _ in secoes:
        if pilha and pilha[0]:
            titulo = pilha[0]
            break

    chunks: list[Chunk] = []
    for pilha, linhas in secoes:
        corpo = "\n".join(linhas).strip()
        if not corpo:
            continue
        caminho = " › ".join(p for p in pilha if p) or titulo
        for parte in _split_long(linhas):
            if not parte.strip():
                continue
            chunks.append(
                Chunk(
                    source_path=source_path,
                    title=titulo,
                    kind=kind,
                    position=len(chunks),
                    heading_path=caminho,
                    # O caminho do cabeçalho é repetido no topo do trecho para que ele se
                    # descreva sozinho: recuperado isolado, "Decisão" sem dizer de que documento
                    # não ajuda o modelo nem quem for conferir a citação.
                    content=f"{caminho}\n\n{parte.strip()}",
                )
            )
    return chunks


# --- O corpus: manifesto e artefato ------------------------------------------


class Kind:
    """Os três tipos da FDD 029, com meias-vidas e governanças diferentes."""

    DECISION = "decision"    # ADR — quase imutável; substitui-se, não se atualiza
    PROCEDURE = "procedure"  # runbook — apodrece rápido, laço mais apertado
    REFERENCE = "reference"  # o quê — apodrece em silêncio


# Manifesto **explícito**, e não um glob sobre `docs/`. O que fica de fora importa tanto quanto o
# que entra: `CHANGELOG.md` são 86 KB de prosa de commit que dominariam a recuperação sem responder
# nada; `roadmap.md` é lista de status cujas linhas velhas seriam citadas como correntes — que é o
# modo de falha que a FDD 029 nomeia; e `CLAUDE.md`/`AGENTS.md` são instrução para agente, não
# metodologia. Um glob engoliria os quatro sem ninguém decidir.
KB_SOURCES: tuple[tuple[str, str], ...] = (
    ("docs/adr", Kind.DECISION),
    ("docs/fdd", Kind.REFERENCE),
    ("docs/rfcs", Kind.REFERENCE),
    ("docs/runbooks", Kind.PROCEDURE),
    ("docs/architecture.md", Kind.REFERENCE),
    ("docs/operacao.md", Kind.PROCEDURE),
    ("docs/captacao-de-leads.md", Kind.REFERENCE),
    ("PRD.md", Kind.REFERENCE),
)

# Prazo de revisão por tipo, aplicado na ingestão e sobrescrevível por peça.
# **Zero significa "não vence"**, e é o valor certo para ADR: elas são substituídas por outra que
# as referencia, não atualizadas — cobrar revisão semestral da ADR 0001 seria ruído, e ruído é o
# que faz o laço inteiro ser ignorado.
DEFAULT_REVIEW_DAYS: dict[str, int] = {
    Kind.DECISION: 0,
    Kind.PROCEDURE: 90,
    Kind.REFERENCE: 180,
}

# A dimensão é **constante de módulo, não setting**, e a diferença importa: `VectorField` assa o
# valor na migração, então um env var seria promessa que o código não cumpre — alguém o mudaria e
# levaria um `ProgrammingError` no primeiro insert. O *modelo* é setting (`AI_EMBEDDING_MODEL`);
# trocá-lo é legal, trocar a dimensão é migração. 1536 é o nativo do `text-embedding-3-small`.
EMBEDDING_DIMENSIONS = 1536

CORPUS_FILE = Path(__file__).resolve().parent / "knowledge_corpus.jsonl"


def _iter_sources(repo_root: Path):
    """Os arquivos do manifesto, em ordem estável."""
    for alvo, kind in KB_SOURCES:
        caminho = repo_root / alvo
        if caminho.is_dir():
            for arquivo in sorted(caminho.glob("*.md")):
                if arquivo.name.upper() == "README.MD":
                    continue  # índice de pasta: aponta para os outros e não afirma nada
                yield arquivo, kind
        elif caminho.is_file():
            yield caminho, kind


def build_corpus(repo_root: Path) -> list[Chunk]:
    """Lê o manifesto e devolve todos os trechos, em ordem determinística."""
    chunks: list[Chunk] = []
    for arquivo, kind in _iter_sources(repo_root):
        relativo = arquivo.relative_to(repo_root).as_posix()
        chunks += chunk_markdown(
            arquivo.read_text(encoding="utf-8"),
            source_path=relativo,
            kind=kind,
            fallback_title=arquivo.stem,
        )
    return chunks


def write_corpus(chunks: list[Chunk], destino: Path = CORPUS_FILE) -> int:
    """Grava o artefato. JSONL e não JSON: o diff fica por linha, e é ele que o CI lê."""
    linhas = [
        json.dumps(chunk.as_json(), ensure_ascii=False, sort_keys=True) for chunk in chunks
    ]
    destino.write_text("\n".join(linhas) + "\n", encoding="utf-8")
    return len(linhas)


def load_corpus(origem: Path = CORPUS_FILE) -> list[dict]:
    """Lê o artefato. **É a única fonte da ingestão** — o runtime nunca toca em `docs/`."""
    if not origem.exists():
        return []
    return [
        json.loads(linha) for linha in origem.read_text(encoding="utf-8").splitlines() if linha
    ]


# --- Frescor: quem responde por quê, e o que venceu --------------------------

# Os quatro estados do inventário. `sem_dono` vem primeiro e **vence os demais** porque a FDD é
# explícita: "peça sem dono é peça em falta". Uma peça fresquíssima cujo dono saiu da empresa não
# está em ordem — está órfã, e chamá-la de corrente é o inventário mentindo.
SEM_DONO = "sem_dono"
VENCIDO = "vencido"
A_VENCER = "a_vencer"
CORRENTE = "corrente"

# Janela em que a peça já aparece como "a vencer", para dar tempo de agir antes de virar dívida.
AVISO_PREVIO_DIAS = 30

# Teto de frequência do aviso ao dono. Sem ele o job vira lembrete diário, a pessoa aprende a
# ignorar em uma semana, e aí o laço inteiro é teatro.
INTERVALO_AVISO_DIAS = 7


def review_interval(piece) -> int:
    """O prazo da peça: o dela, ou o da área. **Zero significa não vence.**"""
    if piece.review_interval_days is not None:
        return piece.review_interval_days
    return piece.area.review_interval_days if piece.area else 0


def due_date(piece):
    """Quando a peça vence, ou `None` quando não vence.

    A base é `last_verified_at` — ou, se ninguém nunca conferiu, a data de criação. Peça nunca
    verificada **não** é corrente: ela é "nunca conferida", e tratá-la como fresca é como um
    inventário vira decoração.
    """
    intervalo = review_interval(piece)
    if not intervalo:
        return None
    from datetime import timedelta

    base = piece.last_verified_at or piece.created_at.date()
    return base + timedelta(days=intervalo)


def freshness(piece, today=None) -> str:
    """O estado de uma peça no inventário. Uma regra, uma expressão."""
    from django.utils import timezone

    hoje = today or timezone.localdate()
    if piece.area is None or piece.area.owner_id is None:
        return SEM_DONO
    vence = due_date(piece)
    if vence is None:
        return CORRENTE
    if vence < hoje:
        return VENCIDO
    from datetime import timedelta

    return A_VENCER if vence <= hoje + timedelta(days=AVISO_PREVIO_DIAS) else CORRENTE


def inventory(today=None) -> dict[str, list]:
    """As peças ativas agrupadas por estado — a leitura que a tela e o job compartilham."""
    from .models import KnowledgePiece

    grupos: dict[str, list] = {SEM_DONO: [], VENCIDO: [], A_VENCER: [], CORRENTE: []}
    consulta = KnowledgePiece.objects.filter(archived_at__isnull=True).select_related(
        "area", "area__owner"
    )
    for piece in consulta:
        grupos[freshness(piece, today)].append(piece)
    return grupos


def check_freshness(today=None) -> dict[str, int]:
    """Avisa quem responde pelo que venceu, e os admins pelo que está sem dono (FDD 029).

    **Não levanta e não vira incidente.** Dívida editorial não é queda de serviço, e transformar um
    runbook vencido em evento de Sentry ensina quem opera a silenciar o Sentry — que é o oposto do
    que a FDD 020 construiu. É a diferença deliberada em relação ao `backup_status`, que sai com
    código 1 de propósito porque *ali* o que falta é a cópia de segurança.
    """
    from datetime import timedelta

    from django.utils import timezone

    from . import notifications
    from .models import KnowledgePiece, User

    hoje = today or timezone.localdate()
    grupos = inventory(hoje)
    limite = hoje - timedelta(days=INTERVALO_AVISO_DIAS)
    avisados = 0

    for piece in grupos[VENCIDO]:
        if piece.last_notified_at and piece.last_notified_at > limite:
            continue
        notifications.notify(
            [piece.area.owner],
            "knowledge_stale",
            f"'{piece.title}' venceu em {due_date(piece)}. Revise ou marque como verificado.",
            "/conhecimento",
        )
        avisados += 1
        KnowledgePiece.objects.filter(pk=piece.pk).update(last_notified_at=hoje)

    sem_dono = [p for p in grupos[SEM_DONO] if not p.last_notified_at or p.last_notified_at <= limite]
    if sem_dono:
        admins = list(User.objects.filter(role=User.Role.ADMIN, is_active=True))
        for piece in sem_dono:
            area = piece.area.name if piece.area else "nenhuma"
            notifications.notify(
                admins,
                "knowledge_ownerless",
                f"'{piece.title}' está sem dono — a área ({area}) não tem responsável.",
                "/conhecimento",
            )
            avisados += 1
            KnowledgePiece.objects.filter(pk=piece.pk).update(last_notified_at=hoje)

    return {
        "vencidas": len(grupos[VENCIDO]),
        "sem_dono": len(grupos[SEM_DONO]),
        "a_vencer": len(grupos[A_VENCER]),
        "avisos": avisados,
    }
