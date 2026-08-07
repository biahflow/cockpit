"""Fatiamento do corpus de conhecimento (FDD 029) — puro, sem banco e sem IA.

O que estes testes protegem é a **exatidão da citação**. Um trecho que cruza cabeçalho produz uma
citação que aponta para a seção errada, e uma citação que não dá para conferir em dez segundos não
vale como citação — que é justamente a exigência que a FDD 029 chama de condição de existir.
"""

import json

from apps.core import knowledge


def _chunks(texto: str, **kwargs):
    kwargs.setdefault("source_path", "docs/adr/0000-teste.md")
    kwargs.setdefault("kind", knowledge.Kind.DECISION)
    kwargs.setdefault("fallback_title", "teste")
    return knowledge.chunk_markdown(texto, **kwargs)


def test_o_caminho_do_cabecalho_e_o_localizador_da_citacao():
    chunks = _chunks("# ADR 0013 — Backup\n\nIntro.\n\n## Decisão\n\nDump lógico.\n")
    caminhos = [c.heading_path for c in chunks]
    assert "ADR 0013 — Backup" in caminhos
    assert "ADR 0013 — Backup › Decisão" in caminhos


def test_trecho_nunca_cruza_cabecalho():
    chunks = _chunks("## Contexto\n\nUm.\n\n## Decisão\n\nDois.\n")
    corpo = {c.heading_path: c.content for c in chunks}
    assert "Dois." not in corpo["Contexto"]
    assert "Um." not in corpo["Decisão"]


def test_cabecalho_de_nivel_4_fica_dentro_da_secao_pai():
    """`####` não abre seção: cortar ali fragmentaria listas sem ganhar precisão de citação."""
    chunks = _chunks("## Regras\n\nUm.\n\n#### Detalhe\n\nDois.\n")
    assert len(chunks) == 1
    assert "Detalhe" in chunks[0].content


def test_comentario_dentro_de_bloco_de_codigo_nao_vira_secao():
    """A guarda que impede seções fantasma tituladas com um comentário de shell."""
    texto = "## Ligar\n\n```bash\n# isto é comentário, não cabeçalho\ndocker compose up\n```\n"
    chunks = _chunks(texto)
    assert [c.heading_path for c in chunks] == ["Ligar"]
    assert "docker compose up" in chunks[0].content


def test_secao_longa_quebra_entre_itens_de_lista():
    """As seções 'Regras' das FDDs são listas sem linha em branco — a fronteira é o item."""
    itens = "\n".join(f"- **Regra {i}.** " + "palavra " * 60 for i in range(12))
    chunks = _chunks(f"## Regras\n\n{itens}\n")
    assert len(chunks) > 1
    # Nenhum trecho começa no meio de um item: todos abrem num marcador de lista.
    for chunk in chunks[1:]:
        corpo = chunk.content.split("\n\n", 1)[1]
        assert corpo.lstrip().startswith("- **Regra")


def test_secao_longa_nao_quebra_dentro_de_bloco_de_codigo():
    bloco = "```bash\n" + "\n".join(f"comando_{i} --flag" for i in range(200)) + "\n```"
    chunks = _chunks(f"## Roteiro\n\n{bloco}\n")
    juntos = "\n".join(c.content for c in chunks)
    assert juntos.count("```") % 2 == 0


def test_todo_trecho_se_descreve_sozinho():
    """Recuperado isolado, 'Decisão' sem dizer de que documento não ajuda ninguém."""
    chunks = _chunks("# ADR 0013 — Backup\n\n## Decisão\n\nDump lógico.\n")
    for chunk in chunks:
        assert chunk.content.startswith(chunk.heading_path)


def test_fatiamento_e_deterministico():
    """O artefato é conferido por `git diff` no CI: ordenar diferente acusaria mudança que não houve."""
    texto = "# T\n\n## A\n\nUm.\n\n## B\n\nDois.\n"
    primeira = [c.as_json() for c in _chunks(texto)]
    segunda = [c.as_json() for c in _chunks(texto)]
    assert primeira == segunda
    assert [c["position"] for c in primeira] == list(range(len(primeira)))


def test_hash_muda_com_o_conteudo_e_com_a_seccao():
    a = _chunks("## A\n\nUm.\n")[0]
    b = _chunks("## A\n\nDois.\n")[0]
    c = _chunks("## B\n\nUm.\n")[0]
    assert a.content_hash != b.content_hash
    assert a.content_hash != c.content_hash


def test_secao_vazia_nao_vira_trecho():
    chunks = _chunks("## Vazia\n\n\n## Cheia\n\nAlgo.\n")
    assert [c.heading_path for c in chunks] == ["Cheia"]


# --- O artefato ---------------------------------------------------------------


def test_o_artefato_commitado_esta_em_dia():
    """O mesmo gate do CI, rodando junto da suíte.

    Sem isto, quem edita um ADR só descobre que esqueceu de regerar o corpus quando o CI reprova —
    e o mais provável é concluir que o gate está quebrado, não que faltou um comando.
    """
    from pathlib import Path

    from django.conf import settings

    esperado = knowledge.build_corpus(Path(settings.BASE_DIR).parent)
    atual = knowledge.load_corpus()
    assert [c.as_json() for c in esperado] == atual, (
        "O corpus mudou: rode `manage.py build_knowledge_corpus` e commite o .jsonl."
    )


def test_o_artefato_e_json_por_linha():
    linhas = knowledge.CORPUS_FILE.read_text(encoding="utf-8").splitlines()
    assert linhas
    for linha in linhas[:5]:
        assert set(json.loads(linha)) == {
            "source_path", "title", "kind", "position", "heading_path", "content", "content_hash",
        }


def test_o_manifesto_deixa_de_fora_o_que_envelheceria_mentindo():
    """CHANGELOG e roadmap não entram, e o motivo é o modo de falha que a FDD nomeia.

    O roadmap é lista de status: uma linha velha citada como corrente é exatamente a informação
    desatualizada servida com fluência confiante. O CHANGELOG são 86 KB de prosa de commit que
    dominariam a recuperação sem responder nada.
    """
    caminhos = {linha["source_path"] for linha in knowledge.load_corpus()}
    assert not any(c.startswith(("CHANGELOG", "roadmap", "CLAUDE", "AGENTS")) for c in caminhos)
    assert any(c.startswith("docs/adr/") for c in caminhos)
    assert "PRD.md" in caminhos


def test_readme_de_pasta_fica_de_fora():
    """Índice de pasta aponta para os outros documentos e não afirma nada por si."""
    caminhos = {linha["source_path"] for linha in knowledge.load_corpus()}
    assert not any(c.endswith("README.md") for c in caminhos)
