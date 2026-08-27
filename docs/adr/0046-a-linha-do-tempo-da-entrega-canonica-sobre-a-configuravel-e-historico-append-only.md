# ADR 0046 — A linha do tempo da entrega: canônica sobre a configurável e histórico append-only

**Status:** aceita
**Data:** 2026-08-27

## Contexto

O Pulse precisa ser o centro operacional da entrega Biahflow: cada projeto deve expor uma linha do
tempo auditável sobre a jornada canônica FDE — `Discover → Prioritize → [Feasibility] → Prove →
Scale → Optimize` (issue #42, `docs/metodologia-fde.md`, ADR 0030). Três coisas que ela pede não
existiam:

1. **A jornada canônica.** A Jornada de Transformação (FDD 011) já modela fases por projeto
   (`JourneyPhase` → `ProjectPhase`), mas com o vocabulário **configurável** Biahflow (`Welcome`,
   `Launch Session`, …), que não é a escada FDE. Havia o risco de nascer um segundo modelo de fase
   paralelo.
2. **O histórico.** `ProjectPhase` carrega só o **estado corrente**. Não guarda a sequência de como
   se chegou nele — e o REDESIGN chega a apagar `completed_at` e `gate_outcome` da fase que reabre
   (FDD 033), de propósito. O que se perdia era a auditoria: *quando* e *por quê* a jornada se moveu.
3. **Quem está esperando.** Não havia como ler, sem abrir a nota crua, que uma fase está parada
   aguardando o cliente, a engenharia, uma dependência externa ou uma decisão humana.

A fronteira da ADR 0040/0035 é dura: **o Pulse é a verdade do estado de negócio/entrega; o GitHub é
a verdade da execução de engenharia.** Nada nesta fatia pode equacionar `PR merged` a entrega
`DONE`.

## Decisão

**Reusar `JourneyPhase`, não duplicá-la. Três adições aditivas, tudo determinístico (sem LLM).**

1. **`JourneyPhase.canonical_stage`** — classificação **opcional** da fase configurável sobre a
   jornada canônica FDE. É um enum (`discover`…`optimize`), em branco quando a fase não tem
   equivalente FDE (`Activation`, `Assisted Evolution`). `feasibility` é membro **explícito e
   opcional**: uma jornada que não a atravessa simplesmente não tem fase mapeada nela — é assim que
   a optionalidade fica *modelada*, e não convencionada. Quem mapeia é o admin, como já decide
   `requires_gate`; a migração só semeia o mapa dos nomes da semente padrão (0015).

2. **`PhaseEvent`** — histórico **append-only**. Uma linha por transição/decisão/bloqueio, com
   carimbo, autor e proveniência (`user`/`system`), **nunca editada nem apagada**. Emitida só por
   `journey.py`; sem viewset de escrita. É a única cópia auditável do que o estado corrente não
   guarda — o gate registrado *antes* do REDESIGN apagá-lo, a reabertura, o trancamento.

3. **`ProjectPhase.waiting_party` + `blocker_note`** — de quem/de quê a fase ativa depende
   (`biahflow`/`client`/`engineering`/`external`/`human_gate`), e a nota. Read-only no serializer,
   escritos só pela action `set-waiting`, pelo **mesmo desenho do `gate_outcome`** (FDD 033): um
   PATCH direto gravaria o estado sem o `PhaseEvent` que o torna auditável. O estado semântico
   (`situation`: active/completed/blocked/waiting_decision/cancelled/replanned/pending) é **derivado**
   desses campos — a tela mapeia situação → variante de selo, nunca recalcula a regra.

### Por que a classificação, e não um segundo modelo de fase

Um `CanonicalPhase` paralelo ao `JourneyPhase` duplicaria materialização, permissão e histórico, e
faria dois conceitos de "fase" divergirem em silêncio. A classificação sobre a fase que já existe
mantém uma jornada só — a configurável — e deixa a canônica ser a lente FDE por cima dela.

### Por que `waiting_party = engineering` não fere a fronteira do GitHub

`engineering` é **classificação de delivery** — "estamos esperando engenharia" —, não o estado de
execução de engenharia em si. Este é do GitHub (ADR 0040, issue #41) e não atravessa para cá. A
linha do tempo do Pulse é a verdade de negócio; ela pode dizer que aguarda a engenharia sem jamais
importar `PR merged` como conclusão de fase.

## Consequências

- A jornada continua **uma só e configurável**; a canônica é uma leitura opcional por cima. Projetos
  existentes não são reescritos — o backfill toca só os nomes da semente padrão, e o resto fica em
  branco (degradação graciosa: a linha do tempo mostra o nome da fase mesmo sem estágio canônico).
- O histórico sobrevive ao que o estado corrente descarta. A auditoria do REDESIGN deixa de depender
  da memória de quem estava na reunião.
- A migração desta fatia é `0047` (o `0046` ficou reservado ao branch da projeção GitHub, issue
  #41); a linearização é reconciliada no merge.
- O snapshot do portal do cliente (`portal.py`) **não** recebe os campos novos: a linha do tempo é
  linguagem operacional interna, e a projeção para o One é fatia própria (fora de escopo, como em
  FDD 033).
