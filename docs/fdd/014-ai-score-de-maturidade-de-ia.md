# FDD 014 — AI Score de maturidade/oportunidade de IA por cliente

## Jornada

Fase 4 da visão da metodologia (RFC 0002; motor do ADR 0006). A partir da transcrição de uma
reunião — as mesmas etapas de Discovery/Assessment (FDD 007) —, a IA produz um **AI Score**
estruturado do cliente: **maturidade** (o quanto já usa IA hoje), **oportunidade** (potencial de
ganho), **dimensões** (Dados, Processos, Pessoas/Cultura, Ferramentas) e um **resumo**. É
**rascunho para revisão humana** e só cruza ao portal do cliente depois de revisado e publicado.

No detalhe do projeto, cada reunião com transcrição ganha um terceiro botão (**AI Score**, ao
lado de Discovery/Assessment). O resultado é gravado no **projeto** (campos `ai_*`); a equipe
revisa/edita e liga **"Publicar ao cliente"** (`ai_score_reviewed`). O índice então flui pelo
snapshot (por projeto) e agrega por cliente na visão multi-cliente (`build_client_overview`).

## Regras

- Reusa o motor de IA (`ai.py`): depende de `AI_ENABLED` (desligado → 503) e respeita o limite
  diário de uso (429). Cada geração é auditada em `AiInteraction` (feature `ai_score`), ligada
  ao projeto da reunião.
- O contexto passado ao modelo contém **apenas** os dados desta reunião (`build_meeting_context`,
  transcrição truncada) — anti-vazamento; nada é executado sozinho.
- Reunião **sem transcrição** → 400. Valores de `maturity`/`opportunity` e de cada dimensão são
  normalizados para 0–100; entradas de dimensão sem rótulo ou score válido são descartadas.
- Persistência no `Project` (`ai_maturity`, `ai_opportunity`, `ai_dimensions`, `ai_score_summary`,
  `ai_scored_at`, `ai_score_reviewed`, `ai_score_meeting`). Gera sempre `ai_score_reviewed=False`.
- **Só publica quando revisado**: `build_snapshot` inclui o bloco `ai_score` apenas quando
  `ai_score_reviewed=True`; sem revisão, o portal simplesmente não mostra o índice. O agregado por
  cliente usa o AI Score revisado mais recente entre os projetos ativos.
- Acesso segue o RBAC do recurso `meeting` (geração) e `project` (revisão/publicação).

## Aceite

Numa reunião com transcrição, o usuário aciona **AI Score** e recebe maturidade, oportunidade,
dimensões e resumo, gravados no projeto como rascunho. Após editar e ligar "Publicar ao cliente",
o índice aparece no snapshot do projeto e na visão do cliente.

## Regressão crítica

Reunião sem transcrição retorna 400; IA desligada retorna 503; limite diário retorna 429; e
**fornecedor fora do ar retorna 502** (rodada 2 da FDD 024). Os três dizem coisas diferentes de
propósito: 503 é "um admin desligou", 429 é "a sua cota acabou", 502 é "a OpenAI caiu". Como a
chamada ao modelo é a primeira coisa que `score_meeting` faz, o 502 deixa o projeto **sem carimbo**
(`ai_scored_at` intacto) — não existe AI Score pela metade. A
interação é registrada com feature `ai_score` e vinculada ao projeto. O `ai_score` **não** cruza
ao snapshot enquanto `ai_score_reviewed` for `False`.
