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
import logging
import re
from dataclasses import dataclass
from pathlib import Path

logger = logging.getLogger(__name__)

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
    area_slug: str = ""

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
            "area_slug": self.area_slug,
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


def chunk_markdown(
    text: str, *, source_path: str, kind: str, fallback_title: str, area_slug: str = ""
) -> list[Chunk]:
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
                    area_slug=area_slug,
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
#
# **`docs/ontology/` fica de fora, e a ausência é decisão, não esquecimento** (04/09/2026). O
# `language-map.md` e o `aliases.md` são normativos — mas para quem escreve código aqui dentro:
# dizem como batizar classe, campo e rota, e quando um alias morre. Quem consulta este corpus é o
# usuário do Pulse perguntando de negócio ao agente comercial, de entrega ou financeiro, e para ele
# "a chave `client` morre na `/api/v2/`" é ruído com aparência de resposta. O vocabulário de
# domínio que ele **precisa** (Account, Engagement, os degraus da escada, o gate do PROVE) já chega
# pelas ADRs e FDDs indexadas acima, ditas na linguagem de quem pergunta. Se um dia o mapa de
# linguagem virar material de consulta para pessoas — e não só para código —, o lugar é uma peça
# própria, escrita para esse leitor, não o espelho normativo inteiro.
# O terceiro campo é o slug da **área padrão**. Declarar a área é o mesmo ato que já se faz com o
# tipo — não é adivinhação. E não muda o estado do primeiro dia: as áreas nascem **sem dono**, então
# tudo continua "em falta". O ganho aparece depois: nomear um dono para "Operação" cobre os sete
# runbooks de uma vez, em vez de exigir etiquetar peça a peça.
KB_SOURCES: tuple[tuple[str, str, str], ...] = (
    ("docs/adr", Kind.DECISION, "produto"),
    ("docs/fdd", Kind.REFERENCE, "produto"),
    ("docs/rfcs", Kind.REFERENCE, "produto"),
    ("docs/runbooks", Kind.PROCEDURE, "operacao"),
    ("docs/architecture.md", Kind.REFERENCE, "produto"),
    ("docs/metodologia-fde.md", Kind.REFERENCE, "entrega"),
    ("docs/operacao.md", Kind.PROCEDURE, "operacao"),
    ("docs/captacao-de-leads.md", Kind.REFERENCE, "comercial"),
    # Os dois espelhos do Notion que a ADR 0069 trouxe (05/09/2026), e são a primeira fonte deste
    # manifesto que **não nasce escrita aqui**: a página do Notion é a fonte, o arquivo é cópia
    # fiel, e mudar uma pergunta é mudança lá — o mesmo regime de `docs/ontology/`, com a diferença
    # que decide a entrada: isto **é** material de consulta para quem pergunta de negócio ao agente,
    # e o mapa de linguagem não era.
    #
    # `discovery-questions.md` é condução de Discovery — os seis blocos por momento da jornada, que
    # `metodologia-fde.md` não tinha (ele tem as 7 perguntas e o P-S-D-T-E-R). Área `entrega`, e não
    # `comercial`, porque quatro dos seis blocos são de campo; os dois da Qualification Call chegam
    # ao agente comercial pela busca, não pela área.
    #
    # `docs/verticais/` é o método de cada vertical: glossário, áreas de pressão, hipóteses,
    # objeções e o que pedir. **A intel de conta não atravessa** — nome de cliente, números dele e
    # situação comercial ficam no Notion (decisão de 05/09/2026). A razão é a mesma que mantém o
    # contexto de build estreito: `docs/` é commitado **e** vira resposta citável, e um agente
    # dizendo "segundo a KB, tal cliente está pressionado financeiramente" é vazamento que ninguém
    # autorizou. O espelho carrega o que serve a qualquer conta da vertical; o que é de uma conta
    # só, não.
    ("docs/discovery-questions.md", Kind.REFERENCE, "entrega"),
    ("docs/verticais", Kind.REFERENCE, "comercial"),
    ("PRD.md", Kind.REFERENCE, "produto"),
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
    for alvo, kind, area in KB_SOURCES:
        caminho = repo_root / alvo
        if caminho.is_dir():
            for arquivo in sorted(caminho.glob("*.md")):
                if arquivo.name.upper() == "README.MD":
                    continue  # índice de pasta: aponta para os outros e não afirma nada
                yield arquivo, kind, area
        elif caminho.is_file():
            yield caminho, kind, area


def build_corpus(repo_root: Path) -> list[Chunk]:
    """Lê o manifesto e devolve todos os trechos, em ordem determinística."""
    chunks: list[Chunk] = []
    for arquivo, kind, area in _iter_sources(repo_root):
        relativo = arquivo.relative_to(repo_root).as_posix()
        chunks += chunk_markdown(
            arquivo.read_text(encoding="utf-8"),
            source_path=relativo,
            kind=kind,
            fallback_title=arquivo.stem,
            area_slug=area,
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


# --- Ingestão ----------------------------------------------------------------


def ingest(*, force: bool = False, embed: bool = True) -> dict[str, int]:
    """Traz o artefato para o banco e embeda o que mudou (FDD 029).

    Lê **só o artefato**, nunca o disco — é o que faz o runtime não precisar saber que `docs/`
    existe. E a regra que carrega a disciplina de frescor inteira: `area`, `last_verified_at`,
    `verified_by` e `review_interval_days` só são escritos **na criação**. Sem isso cada deploy
    apagaria a curadoria humana em silêncio, e ninguém ligaria uma coisa à outra.
    """
    from django.conf import settings
    from django.utils import timezone

    from . import ai
    from .models import KnowledgeArea, KnowledgeChunk, KnowledgePiece

    linhas = load_corpus()
    por_arquivo: dict[str, list[dict]] = {}
    for linha in linhas:
        por_arquivo.setdefault(linha["source_path"], []).append(linha)

    areas = {area.slug: area for area in KnowledgeArea.objects.all()}
    resumo = {"pecas": 0, "criadas": 0, "trechos": 0, "embeddadas": 0, "arquivadas": 0}
    pendentes: list[KnowledgeChunk] = []

    for caminho, trechos in por_arquivo.items():
        primeiro = trechos[0]
        assinatura = _hash_do_arquivo(trechos)
        peca = KnowledgePiece.objects.filter(source_path=caminho).first()
        if peca is None:
            peca = KnowledgePiece.objects.create(
                source_path=caminho,
                title=primeiro["title"],
                kind=primeiro["kind"],
                # Curadoria inicial — e **só** inicial.
                area=areas.get(primeiro.get("area_slug", "")),
                review_interval_days=DEFAULT_REVIEW_DAYS.get(primeiro["kind"]),
                content_hash=assinatura,
            )
            resumo["criadas"] += 1
        elif peca.archived_at is not None:
            peca.archived_at = None  # o arquivo voltou
            peca.save(update_fields=["archived_at", "updated_at"])
        resumo["pecas"] += 1

        inalterada = peca.content_hash == assinatura and not force
        if inalterada and peca.chunks.exists():
            resumo["trechos"] += peca.chunks.count()
            pendentes += list(
                peca.chunks.filter(embedding__isnull=True)
            ) if embed else []
            continue

        # Substituição em bloco: o trecho é registro derivado, e diferenciá-lo linha a linha
        # custaria complexidade para economizar um DELETE de algumas dezenas de linhas.
        peca.chunks.all().delete()
        novos = KnowledgeChunk.objects.bulk_create([
            KnowledgeChunk(
                piece=peca,
                position=trecho["position"],
                heading_path=trecho["heading_path"],
                content=trecho["content"],
                content_hash=trecho["content_hash"],
            )
            for trecho in trechos
        ])
        resumo["trechos"] += len(novos)
        pendentes += novos
        KnowledgePiece.objects.filter(pk=peca.pk).update(
            title=primeiro["title"], kind=primeiro["kind"], content_hash=assinatura,
            updated_at=timezone.now(),
        )

    # Peça cujo arquivo sumiu do artefato é **arquivada**, não apagada: o inventário não perde
    # linha em silêncio, e a curadoria dela sobrevive caso o arquivo volte.
    sumidas = KnowledgePiece.objects.filter(archived_at__isnull=True).exclude(
        source_path__in=list(por_arquivo)
    ).exclude(source_path="")
    for peca in sumidas:
        peca.archive()
        resumo["arquivadas"] += 1

    if embed and pendentes:
        modelo = settings.AI_EMBEDDING_MODEL
        # Só o que mudou: hash diferente, modelo diferente, ou vetor ausente. `--force` já
        # esvaziou os trechos acima, então cai tudo aqui.
        alvo = [c for c in pendentes if c.embedding is None or c.embedding_model != modelo]
        for inicio in range(0, len(alvo), ai.EMBED_BATCH):
            lote = alvo[inicio : inicio + ai.EMBED_BATCH]
            vetores = ai.embed([c.content for c in lote])
            for chunk, vetor in zip(lote, vetores, strict=True):
                chunk.embedding = vetor
                chunk.embedding_model = modelo
            KnowledgeChunk.objects.bulk_update(lote, ["embedding", "embedding_model"])
            resumo["embeddadas"] += len(lote)

    return resumo


def _hash_do_arquivo(trechos: list[dict]) -> str:
    """Assinatura do arquivo inteiro: muda se qualquer trecho mudou, ou se a ordem mudou."""
    return hashlib.sha256(
        "\n".join(t["content_hash"] for t in trechos).encode()
    ).hexdigest()


# --- Busca -------------------------------------------------------------------


@dataclass(frozen=True)
class Hit:
    """Um trecho recuperado, com a similaridade que o trouxe."""

    chunk_id: int
    piece_id: int
    title: str
    heading_path: str
    content: str
    source_path: str
    similarity: float
    stale: bool


def _cosine(a: list[float], b: list[float]) -> float:
    soma = sum(x * y for x, y in zip(a, b, strict=True))
    na = sum(x * x for x in a) ** 0.5
    nb = sum(y * y for y in b) ** 0.5
    return soma / (na * nb) if na and nb else 0.0


def search(vector: list[float], limit: int | None = None) -> list[Hit]:
    """Os trechos mais próximos da pergunta. **Uma função, dois caminhos.**

    No Postgres a ordenação é do banco (`CosineDistance` do pgvector); no SQLite é um cosseno em
    Python sobre as ~420 linhas, que roda em milissegundos neste tamanho.

    Duas implementações é o preço de a suíte rodar em SQLite e a produção em Postgres — e o que
    torna a segunda confiável em vez de apenas verde é o **teste de paridade**, que exige o mesmo
    top-k das duas para os mesmos vetores. Sem ele, a que roda nos testes seria justamente a que
    **não** roda em produção.
    """
    from django.conf import settings
    from django.db import connection

    from .models import KnowledgeChunk

    topo = limit or settings.KB_TOP_K
    consulta = KnowledgeChunk.objects.filter(
        embedding__isnull=False,
        embedding_model=settings.AI_EMBEDDING_MODEL,
        piece__archived_at__isnull=True,
    ).select_related("piece", "piece__area", "piece__area__owner")

    if connection.vendor == "postgresql":
        return _rank_sql(consulta, vector, topo)
    return _rank_python(consulta, vector, topo)


def _rank_sql(consulta, vector: list[float], topo: int) -> list[Hit]:  # pragma: no cover - Postgres
    from pgvector.django import CosineDistance

    linhas = consulta.annotate(distancia=CosineDistance("embedding", vector)).order_by(
        "distancia"
    )[:topo]
    return [_hit(chunk, 1.0 - float(chunk.distancia)) for chunk in linhas]


def _rank_python(consulta, vector: list[float], topo: int) -> list[Hit]:
    pontuados = [(_cosine(vector, list(chunk.embedding)), chunk) for chunk in consulta]
    pontuados.sort(key=lambda par: par[0], reverse=True)
    return [_hit(chunk, similaridade) for similaridade, chunk in pontuados[:topo]]


def _hit(chunk, similaridade: float) -> Hit:
    return Hit(
        chunk_id=chunk.pk,
        piece_id=chunk.piece_id,
        title=chunk.piece.title,
        heading_path=chunk.heading_path,
        content=chunk.content,
        source_path=chunk.piece.source_path,
        similarity=similaridade,
        stale=freshness(chunk.piece) == VENCIDO,
    )


# --- Resposta ancorada: citar ou declarar a lacuna (ADR 0023) ----------------

LACUNA = "Não encontrei isso no material."

# A **declaração de regime**, e ela existe por medição, não por gosto. A rodada 5 de homologação
# mediu a similaridade real de três classes de pergunta contra este corpus:
#
#     metodologia   51 56 58 61 62 69   (mín. 50,6%)
#     operacional   47 47 51 52 53 56   (máx. 56,4%)
#     fora do corpus 22 25 37 49
#
# **As faixas se sobrepõem**: não existe limiar que separe "perguntar sobre o método" de "perguntar
# sobre os dados". E não é ruído — o corpus *descreve* o domínio, então uma pergunta sobre projetos
# atrasados de fato se parece com o texto de uma FDD sobre projetos atrasados.
#
# O desenho original fazia o limiar decidir se a regra de citar-ou-lacuna valia, e com esses números
# ele transformaria "o que está atrasado?" — resposta operacional correta — em "não encontrei isso
# no material". Quem sabe qual pergunta está respondendo é o **modelo**, não o cosseno; então é ele
# que declara, e o código confere o que ele não pode ser confiado a fazer sozinho.
_FONTE_PREFIXO = "FONTE:"
_FONTE_AREA = "dados da área"

# Duas fontes, duas regras — e a separação é a lição que a homologação já cobrou uma vez
# (`views.py:756`): proibir conhecimento externo **sem** proibir raciocinar. "Use apenas o
# contexto" cru degenerou numa resposta literal "Não sei." para pergunta que o contexto respondia.
GROUNDING_RULES = (
    "Você tem duas fontes, e elas têm regras diferentes.\n"
    "1) Os DADOS DA ÁREA (pipeline, projetos, prazos, faturas) você pode e deve raciocinar em "
    "cima: comparar com a data de hoje, apontar o que está atrasado, inferir risco e priorizar. "
    "Isso não precisa de citação.\n"
    "2) O MATERIAL DA METODOLOGIA vem em trechos marcados [K1], [K2]… Toda afirmação sobre "
    "método, procedimento, decisão ou norma da casa precisa terminar com o marcador do trecho de "
    "onde ela saiu, assim: [K2]. Use somente marcadores que existem na lista.\n"
    f"Se a pergunta for sobre metodologia e os trechos não a responderem, escreva exatamente "
    f"'{LACUNA}' e pare — não complete com conhecimento próprio nem com o que soa plausível. "
    "Trecho marcado como VENCIDO pode ser citado, mas diga que está vencido.\n"
    f"TERMINE SEMPRE com uma última linha declarando de onde veio a resposta, exatamente num "
    f"destes dois formatos: '{_FONTE_PREFIXO} [K1], [K2]' quando qualquer afirmação vier do "
    f"material da metodologia, ou '{_FONTE_PREFIXO} {_FONTE_AREA}' quando a resposta vier apenas "
    "dos dados operacionais."
)

_MARCADOR = re.compile(r"\[K(\d+)\]")
_LINHA_FONTE = re.compile(rf"^\s*{_FONTE_PREFIXO}\s*(.+?)\s*$", re.MULTILINE | re.IGNORECASE)


@dataclass(frozen=True)
class Grounding:
    """O material recuperado para uma pergunta, já numerado."""

    hits: list[Hit]  # na ordem dos marcadores
    block: str

    def por_marcador(self) -> dict[int, Hit]:
        return {indice + 1: hit for indice, hit in enumerate(self.hits)}


def ground(question: str) -> Grounding | None:
    """Recupera material da metodologia para a pergunta, ou `None` quando nada é relevante.

    O `None` é a peça mais importante desta função. Os agentes também respondem perguntas
    puramente operacionais ("o que está atrasado?"), e injetar material irrelevante nelas — com a
    regra de citar-ou-lacuna junto — transformaria toda pergunta comercial em "não encontrei isso
    no material". O piso de similaridade é o que separa os dois mundos, e ele é **setting** porque
    vai estar errado no começo: quem descobre o número certo é a homologação, não a leitura.
    """
    from django.conf import settings

    from . import ai

    if not question.strip() or not ai.is_enabled():
        return None
    try:
        vetor = ai.embed([question])[0]
    except ai.AiProviderError:
        # A pergunta ainda pode ser respondida pelos dados da área; deixar a resposta inteira cair
        # porque o embedding falhou trocaria uma degradação por uma queda.
        logger.warning("embedding da pergunta falhou; a resposta segue sem material da metodologia")
        return None

    piso = settings.KB_MIN_SIMILARITY_PERCENT / 100
    hits = [hit for hit in search(vetor) if hit.similarity >= piso]
    if not hits:
        return None

    linhas = ["Material da metodologia (trechos recuperados; cite pelo marcador):", ""]
    for indice, hit in enumerate(hits, start=1):
        selo = " (VENCIDO — revisão pendente)" if hit.stale else ""
        linhas.append(f"[K{indice}] {hit.title} › {hit.heading_path}{selo}")
        linhas.append(hit.content)
        linhas.append("")
    return Grounding(hits=hits, block="\n".join(linhas).strip())


def enforce_citations(text: str, grounding: Grounding) -> tuple[str, list[dict]]:
    """Citar ou declarar a lacuna — **em código, não no prompt** (ADR 0023).

    O que o modelo alegou não conta. Um marcador que não resolve para um trecho realmente enviado
    (um `[K9]` quando seis foram mandados) é removido do texto e vale **zero**; e uma resposta
    ancorada sem nenhuma citação que resolva é **substituída** pela lacuna, não anotada com um
    aviso pendurado numa resposta que continua na tela — porque texto fluente sem fonte é
    precisamente o modo de falha que a FDD 029 chama de pior que não ter KB.
    """
    mapa = grounding.por_marcador()
    citados: dict[int, Hit] = {}

    declaracao = _LINHA_FONTE.search(text)
    veio_da_area = declaracao is not None and _FONTE_AREA in declaracao.group(1).lower()

    def resolver(match: re.Match) -> str:
        indice = int(match.group(1))
        hit = mapa.get(indice)
        if hit is None:
            return ""  # marcador inventado: some do texto e não conta
        citados[indice] = hit
        return match.group(0)

    # Resolver sobre o texto **inteiro**, e só depois esconder a linha de declaração.
    #
    # A rodada 5 achou isto do jeito mais claro possível: o modelo respondeu certo, com os comandos
    # exatos do runbook, e pôs a citação **só** na linha `FONTE: [K1]` — que é literalmente o que o
    # prompt pede. A versão anterior removia essa linha antes de procurar marcador, então nada
    # resolvia e a lacuna **substituía uma resposta correta**. Não havia como descobrir isso sem
    # rodar contra o modelo de verdade: qualquer dublê teria citado onde o teste mandasse.
    _MARCADOR.sub(resolver, text)
    corpo = text[: declaracao.start()] + text[declaracao.end() :] if declaracao else text
    limpo = _MARCADOR.sub(resolver, corpo).replace("  ", " ").strip()

    if not citados:
        # Respondeu pelos dados da área, ou já declarou a lacuna: passa. Substituir aqui seria
        # trocar uma resposta operacional correta por "não encontrei", que é o defeito que a
        # rodada 5 achou.
        if veio_da_area or limpo.startswith(LACUNA):
            return limpo, []
        # Alegou metodologia e não sustentou — inclusive quando inventou o marcador. Aqui a lacuna
        # **substitui**, e não anota: texto fluente sem fonte é o modo de falha que a FDD 029 chama
        # de pior que não ter KB.
        if declaracao or _MARCADOR.search(text):
            consultados = ", ".join(sorted({hit.title for hit in grounding.hits}))
            return f"{LACUNA} Consultei: {consultados}.", []
        # Nem declarou nem citou: o modelo não seguiu a instrução. Passa (a resposta pode ser
        # operacional), mas fica registrado — é assim que a deriva aparece antes de virar defeito.
        logger.warning("resposta ancorada sem declaração de FONTE; deixando passar")
        return limpo, []

    fontes = [
        {
            "ref": f"K{indice}",
            "piece": hit.piece_id,
            "title": hit.title,
            "section": hit.heading_path,
            "path": hit.source_path,
            "stale": hit.stale,
        }
        for indice, hit in sorted(citados.items())
    ]
    return limpo, fontes
