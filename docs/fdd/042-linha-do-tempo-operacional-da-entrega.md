# FDD 042 — Linha do tempo operacional da entrega

## Jornada

O Pulse é o centro operacional da entrega Biahflow (ADR 0030, ADR 0040). Cada projeto precisa
expor, de forma **auditável**, onde está na jornada canônica FDE — `Discover → Prioritize →
[Feasibility] → Prove → Scale → Optimize` — e não só o rótulo mais recente: *quando* e *por quê* a
jornada se moveu, o que a fase ativa está esperando, e qual o próximo gate. A projeção para o
cliente é do One; **esta fatia é a visão interna do Pulse**.

A Jornada de Transformação (FDD 011) já tinha a escada de fases configurável e os gates (FDD 033).
O que ela não tinha era três coisas que a issue #42 pede, e cada uma é a razão de uma adição:

- a **jornada canônica** — o vocabulário configurável (`Welcome`, `Launch Session`, …) não é a
  escada FDE;
- o **histórico** — `ProjectPhase` guarda o estado corrente, não a sequência; e o REDESIGN chega a
  **apagar** `completed_at`/`gate_outcome` da fase que reabre (FDD 033), então a auditoria de por
  que se voltou não sobrevivia;
- **quem está esperando** — não dava para ler, sem abrir a nota crua, que a fase parou aguardando o
  cliente, a engenharia ou uma decisão humana.

## O que esta fatia entrega

Tudo **aditivo** sobre a jornada que já existe, e tudo **determinístico** (FinOps: ordenação,
situação, próximo gate e classificação de bloqueio saem de campos explícitos — zero LLM).

- **Jornada canônica como classificação.** `JourneyPhase.canonical_stage` mapeia a fase configurável
  sobre a escada FDE. Em branco é legítimo (fase operacional sem equivalente FDE). `feasibility` é
  membro **explícito e opcional**: uma jornada que não a atravessa não tem fase mapeada nela.

- **Histórico append-only.** `PhaseEvent` — uma linha por transição/decisão/bloqueio, com carimbo,
  autor e proveniência (`user`/`system`), **nunca editada nem apagada**. Emitida só por `journey.py`
  (materialização, avanço, gate, espera). É a cópia que sobrevive ao que o estado corrente descarta:
  o gate é registrado *antes* de o REDESIGN apagá-lo.

- **Parte aguardada e situação.** `ProjectPhase.waiting_party` (`biahflow`/`client`/`engineering`/
  `external`/`human_gate`) + `blocker_note`, escritos só pela action `set-waiting` (como o
  `gate_outcome`, para deixar rastro). A `situation` — `active`/`completed`/`blocked`/
  `waiting_decision`/`cancelled`/`replanned`/`pending` — é **derivada** desses campos; a tela mapeia
  situação → **variante** de `.state`, nunca a cor (ADR 0026).

- **Dois agregadores.** `GET /projects/{id}/timeline/` (fase corrente + histórico + próximo gate +
  próxima fase + bloqueios) e `GET /projects/timeline-overview/` (visão compacta por projeto ativo,
  para o dashboard). O segundo estreita à mão por `visible_to` e tem teste próprio.

Na tela: o painel "Linha do tempo da entrega" no detalhe do projeto (situação, quem aguarda,
próximo gate e o histórico), e o widget "Jornada de entrega" no dashboard.

## Critérios de aceite

1. **Todo projeto ativo expõe sua fase canônica corrente.** O `timeline`/`timeline-overview`
   devolve `canonical_stage` da fase ativa — e degrada com o nome da fase quando o admin não mapeou.
2. **A mudança de fase é auditável.** Toda transição vira `PhaseEvent`; o histórico do REDESIGN
   sobrevive mesmo com o `gate_outcome` apagado do estado corrente.
3. **Feasibility é opcional e explícita.** É membro do enum canônico; a jornada que não a percorre
   não tem fase nela, sem que isso quebre nada.
4. **O próximo gate/marco é visível.** `next_gate` é a próxima fase (na ordem) que exige gate e ainda
   não decidiu; `next_phase` é a próxima trancada.
5. **Bloqueio/dono/parte aguardada é legível sem abrir a nota crua.** `waiting_party` + `blocker_note`
   na fase ativa, e a `situation` derivada.
6. **Engenharia continua distinta de negócio/entrega.** `waiting_party=engineering` é "aguardando
   engenharia" (classificação de delivery), não o estado de execução do GitHub. Nada equaciona `PR
   merged` a `DONE`.
7. **Vendas lê, Entrega escreve no que é dela.** `set-waiting` herda a política de `advance-phase`:
   Vendas 403, Entrega dentro do projeto de que participa. `timeline`/`overview` são leitura para os
   dois; o overview nunca vaza projeto de que a Entrega não participa.

## Decisões

### Por que classificação, e não um segundo modelo de fase

Ver ADR 0047. Um `CanonicalPhase` paralelo duplicaria materialização, permissão e histórico, e faria
dois conceitos de "fase" divergirem em silêncio. A classificação sobre a fase que já existe mantém
uma jornada só.

### Por que `waiting_party`/`blocker_note` são read-only no serializer

Mesmo desenho do `gate_outcome` (FDD 033): a mudança precisa deixar um `PhaseEvent` com autor. Um
PATCH direto gravaria o estado sem o registro de quem e por quê — a pior forma de defeito, porque a
tela mostraria a espera certa sobre um sistema que não a registrou. A action `set-waiting` é o único
lugar onde a mudança e o rastro dela são a mesma operação.

### Por que sem viewset de escrita para `PhaseEvent`

O evento é histórico: nasce de `journey.py` e não se edita. Um CRUD abriria a porta para reescrever a
auditoria, que é exatamente o que ela existe para impedir. A leitura sai pela linha do tempo.

### Onde mora o recorte de permissão

`timeline`, `timeline-overview` e `set-waiting` são actions da `ProjectViewSet` (`resource =
"project"`) e herdam a política dela — não há recurso novo. `set-waiting` é POST e cai no corte "por
ação, não por método" que já libera `advance-phase`/`apply-gate` à Entrega e barra Vendas. O
`timeline-overview` estreita à mão por `visible_to`, como os outros agregadores do dashboard.

## Contrato

Rotas novas, todas em `/api/v1/`:

| Rota | Quem |
| --- | --- |
| `GET /projects/{id}/timeline/` | leitura (Vendas, Entrega no projeto, admin) |
| `GET /projects/timeline-overview/` | leitura (estreitado por `visible_to`) |
| `POST /projects/{id}/set-waiting/` | Entrega no próprio projeto / admin |

Campos novos: `JourneyPhase.canonical_stage`; `ProjectPhase.canonical_stage` (derivado), `situation`
(derivado), `waiting_party`, `blocker_note`; o modelo `PhaseEvent` e seu serializer. `apply-gate` e
`advance-phase` passam a devolver os campos novos da fase. `ENUM_NAME_OVERRIDES` ganha
`PhaseEventSourceEnum` (e fixa `SourceEnum` na sincronia de tarefas) para o `source` não colidir e
gerar sufixo instável. Nada removido — a mudança é aditiva.

## Testes

- `apps/core/tests/test_delivery_timeline.py` — o evento de origem na materialização, os eventos de
  avanço com autor, a auditoria que sobrevive ao REDESIGN, a derivação determinística da `situation`
  (as sete situações), o `set-waiting` que define e limpa com evento, a recusa de parte inválida, o
  read-only do PATCH, os dois agregadores (com o overview estreitado e sem projeto concluído) e o
  RBAC (Vendas lê e não escreve; Entrega não alcança projeto de que não participa).
- `ProjectDetailTimeline.test.tsx` — o painel com situação, próximo gate e histórico com
  proveniência, e o `set-waiting` que resolve o bloqueio.
- `DashboardPage.test.tsx` — o widget compacto da jornada de entrega.

## Fora deste recorte

- **Projeção para o One (`portal.py`).** Os campos novos não atravessam: a linha do tempo é
  linguagem operacional interna, e a projeção para o cliente é fatia própria (como o gate em FDD
  033), com emenda na ADR 0003 se vier.
- **A projeção de estado de engenharia do GitHub.** É a issue #41. A fronteira fica limpa aqui:
  `waiting_party=engineering` é classificação de delivery, não o estado de execução.
- **Transição automática de fase por merge de PR.** Fora de escopo por decisão: avançar fase é ato
  humano (FDD 011/033), e nada equaciona `PR merged` a `DONE`.
- **Semear `canonical_stage` além dos nomes da semente padrão.** Quem mapeia a fase configurável
  sobre a canônica é o admin, como já decide `requires_gate`.
