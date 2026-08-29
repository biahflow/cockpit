# Design Approval Package — Priorização (PainPoint → ImprovementOpportunity → Priority → Hypothesis)

Classificação: `INTERFACE_CHANGE` · `BROWSER_REQUIRED`
Revisão: **1**
Status: **Approved**
Data: 2026-08-28
Produzido por: harness (Claude Code), sob `workflows/design-approval.md`
Issue: [#68](https://github.com/biahflow/pulse/issues/68) — Fase 4 da migração de ontologia (épico [#62](https://github.com/biahflow/pulse/issues/62))

> Este artefato é evidência para um gate humano. Não é implementação e não deve ser copiado para
> dentro do código de aplicação. Nenhuma linha de `frontend/src/` ou `backend/` muda nesta entrega.

## Por que existe um gate

O PRIORITIZE é a segunda pergunta da escada FDE — *"onde devemos atuar?"* (`docs/metodologia-fde.md`).
Hoje ela **não tem entidade nenhuma no domínio**: existe como fase configurável (`JourneyPhase`
com `canonical_stage="prioritize"`) e como prosa em documento. O "Opportunity Score" que o método
cita e que o Executive Readout promete ao cliente não tem onde morar, e os dois números que o
produto tem hoje — `Lead.ai_score` (aquisição) e `Project.ai_opportunity` (maturidade de IA) —
**não são ele**: o mapa de linguagem lista os dois como termos banidos para esse papel
(`docs/ontology/language-map.md` §5).

A issue #68 cria os quatro modelos que fecham a cadeia: `PainPoint` → `ImprovementOpportunity` →
`PriorityAssessment` → `SolutionHypothesis`. Criar uma superfície para eles é, pela definição de
`workflows/design-approval.md`, "criar ou alterar materialmente uma superfície perceptível por
humano" — e a mesma página diz que a classificação cobre os estados de vazio, erro, carregamento e
não autorizado, que são os descobertos tarde.

Há um segundo fato que dá peso à decisão, e ele é o mesmo que a Fase 3 deixou em aberto: **o split
`Evidence`/`Finding` nasceu sem tela**. `frontend/src/types.ts:120-125` registra isso
explicitamente — os tipos existem, as rotas existem, e nenhuma tela consome. Se a Fase 4 nascer do
mesmo jeito, o produto acumula quatro modelos a mais que só um `curl` alcança, e a cadeia inteira
do PRIORITIZE fica invisível para quem trabalha nela. **Esta é a primeira tela do produto que
responde "onde atuar" com um número que se pode auditar.**

Nenhuma aprovação vigente cobre esta superfície. O DAP GH-26 r1 aprovou marca e fundações no shell
e listou "as outras 20 telas de produto" como **não** aprovadas
(`docs/design/dap-gh26-r1/README.md`); o DAP engagement r1 aprovou uma seção do detalhe da conta;
o DAP lifecycle-status r1 aprovou a listagem de contas e suas pastilhas.

O gate fica **antes do planejamento**, não antes da construção. Ele é pedido agora, com o
mapeamento de código feito e nenhuma linha de implementação escrita.

## Artefato

| Arquivo | O que é |
| --- | --- |
| `board.html` | Renderização auto-contida. Abre sem build, sem toolchain e sem rede. |
| `board-desktop.png` | Captura congelada do board a 1280px, `deviceScaleFactor: 2`. |
| `board-mobile.png` | Captura congelada do board a 390px. |

As capturas são a evidência fixa do que foi renderizado: um board depende de fonte, navegador e
plataforma, e é ao PNG que a aprovação se refere. Elas retratam o **board**, não o produto — a
evidência renderizada da tela implementada é `BROWSER_REQUIRED` e vem depois, contra o código. O
board cita, valor a valor, a origem de cada cor, corpo, raio e sombra em `frontend/src/index.css`.

## Onde a superfície mora

Duas superfícies, e elas são deliberadamente **assimétricas**:

1. **Uma tela nova por conta**, em `/contas/:id/priorizacao` — o backlog ranqueado de
   `ImprovementOpportunity`, com a avaliação vigente, o histórico de versões e as hipóteses.
   Entrada pelo detalhe da conta, num `.back-link` no molde de `ProcessDetailPage`.
2. **Uma seção nova em `ProcessDetailPage`**, abaixo de "Evidências"
   (`frontend/src/pages/ProcessDetailPage.tsx:290`) — os `PainPoint` daquele processo, onde a dor
   é observada.

O raciocínio da assimetria está na decisão **E** abaixo. **Nenhum link novo entra no menu lateral**
— o produto já tem 17, e a priorização é sempre de *uma conta*: um item de menu que abre pedindo
"qual conta?" é um beco.

## O que está sendo pedido

Cinco decisões, desenhadas **lado a lado no board** para serem escolhidas olhando. A recomendação
do harness está marcada, e a marcação é proposta — não decisão tomada.

### Decisão A — a priorização é tela própria ou nona seção do detalhe da conta

- **A1 (recomendada)** — tela própria em `/contas/:id/priorizacao`.
- **A2** — mais uma `<section className="panel">` no `AccountDetailPage`.

`AccountDetailPage` já tem oito seções (saúde, engagements, satisfação, processos, dados,
contatos, interações e o cabeçalho). Uma nona empurraria o backlog ranqueado para o rodapé de uma
página de rolagem longa — e a lista de prioridades é justamente a que precisa ser lida do topo,
porque a ordem *é* o conteúdo. Além disso, o detalhe da oportunidade tem dimensões, histórico e
hipóteses: é uma página, não um painel.

O contra-argumento honesto de A2: o Engagement ganhou seção, não tela (DAP engagement r1), e há
valor em manter a espinha `Account → Engagement → Project` visível num lugar só. A diferença é de
volume e de uso — o mandato é um cadastro que se consulta; o backlog é uma lista de trabalho que
se percorre.

### Decisão B — a linha da oportunidade mostra o score, ou só o rank

- **B1 (recomendada)** — `#1` · título · **Opportunity Score 78** · `v2` · pílula de status.
- **B2** — `#1` · título · pílula de status. O score aparece só ao abrir.

`PriorityAssessment` é versionado de propósito: guarda a fórmula, as dimensões e a versão usadas
(issue #68, "pontos que costumam ser errados"). **Um score sem a versão ao lado é um número que
não se pode comparar com o da semana passada** — e uma tela que esconde a versão desfaz, na
leitura, a decisão que o modelo tomou na escrita. B1 mostra os dois juntos, sempre.

"Opportunity Score" fica **em inglês**: o mapa de linguagem §5 nomeia os três rótulos de
entregável que sobrevivem como exceção — *Opportunity Score*, *Opportunity Map* e *Improvement
Opportunity Backlog* — e §2 registra `PriorityAssessment` como "Opportunity Score" na superfície.
Isso não é uma decisão deste pacote; é o mapa sendo obedecido, e está aqui só para ficar visível.

### Decisão C — repriorizar mostra histórico, ou só a vigente

- **C1 (recomendada)** — bloco "Avaliações" com as versões, a vigente destacada e as anteriores
  colapsadas.
- **C2** — só a avaliação vigente; o histórico existe na API e não na tela.

Repriorizar **cria uma versão nova, não sobrescreve** — é a primeira armadilha que a issue lista.
Uma tela que mostra só a vigente faz o produto *parecer* que sobrescreve, e a pessoa que
reprioriza não tem como ver que o critério mudou. C1 custa um `<details>`; C2 custa a razão de o
modelo ser versionado.

### Decisão D — hipóteses concorrentes lado a lado, ou em lista com status

- **D1 (recomendada)** — lista vertical, uma `.row` por hipótese, com pílula
  `proposta` · `escolhida` · `descartada`.
- **D2** — colunas lado a lado, para a competição ficar literal.

D2 é mais fiel à ideia de "hipóteses concorrentes", e é pior no produto: duas colunas de 420px não
cabem em 390px sem rolagem horizontal, que `e2e/responsive.spec.ts` mede e o produto proíbe. D1
mantém a competição legível pela pílula e pela ordem, e sobrevive ao celular sem um segundo
layout.

### Decisão E — o Pain Point nasce no processo ou na priorização

- **E1 (recomendada)** — registra-se na tela do processo, ao lado da evidência; agrupa-se na tela
  de priorização.
- **E2** — tudo na tela de priorização, inclusive o registro.

A dor é observada **no processo**, junto do trecho que a sustenta e do custo do estado atual
(`ProcessDetailPage` já mostra os dois). Obrigar quem está lendo a evidência a trocar de tela para
registrar a dor é o tipo de fricção que faz o registro não acontecer — e um `PainPoint` que não é
registrado no instante em que é visto vira memória de reunião, que é exatamente o defeito que a
FDD 039 existe para corrigir.

A tela de priorização mostra, no topo, os **pain points ainda não agrupados** em nenhuma
oportunidade: é ali que o trabalho de priorizar começa, e é o único lugar onde "o que ainda não
foi olhado" é visível.

## Estados desenhados

O board desenha todos, e não só o caminho feliz:

| Estado | Onde | O que diz |
| --- | --- | --- |
| Carregando | tela de priorização | "Carregando…", no molde de `ProcessDetailPage.tsx:196` |
| Vazio — sem pain point | tela e seção do processo | "Nenhum pain point registrado. A dor entra pela tela do processo, ao lado da evidência que a sustenta." |
| Vazio — sem oportunidade | tela de priorização | "Nenhuma Improvement Opportunity. Agrupe pain points para abrir a primeira." |
| Vazio — oportunidade sem avaliação | detalhe da oportunidade | "Sem Opportunity Score. Avaliar registra a versão 1 do critério." — e a linha mostra `—` no lugar do número, **nunca zero** |
| Erro | tela de priorização | `.alert--error` com o texto do backend |
| Não autorizado | tela de priorização | "Você não participa de nenhum projeto desta conta." — o recorte de Entrega é o mesmo de `Evidence`/`Finding` (`permissions.py:213-232`) |

**A lacuna é `—`, nunca `0`.** Zero afirma que a oportunidade foi avaliada e vale zero; o traço diz
que ninguém avaliou. É a mesma regra que `Process.custo_do_estado_atual` já aplica com
`nao_apurado` (`backend/apps/core/process.py:71-74`) e que a issue #69 repete para medição.

## Procedência de cada valor visual

Nenhum valor novo. Tudo vem de `frontend/src/index.css` e do DAP GH-26 r1 (fundações r2):

| Valor | Origem |
| --- | --- |
| Cores `ink`, `canvas`, `line`, `muted`, `brand-*`, `danger` | `index.css` `@theme` — paleta branco/preto/laranja da ADR 0024 |
| `.panel`, `.row`, `.panel-heading`, `.eyebrow`, `.page-head` | `@layer components` de `index.css` |
| `.state--0..3` e `.state--off` | idem. `--off` é o neutro: "descartada" e "arquivado" não são aviso |
| `.btn`, `.btn--secondary`, `.btn--secondary-danger`, `.btn--icon` | idem |
| `.field`, `.form-label`, `.form-grid`, `.toolbar`, `.filter-chip` | idem |
| `.empty-state`, `.alert--error`, `.back-link` | idem |
| Raio 8px (controle) / 12px (cartão), papéis `--text-title/-body/-label/-meta` | fundações r2, DAP GH-26 r1 |
| Ícones | `lucide-react`, já dependência — `Target` (oportunidade), `Flame` (pain point), `FlaskConical` (hipótese), `Gauge` (score) |

**Nada é marcado como novo.** Se a implementação precisar de uma primitiva que não existe, isso é
uma revisão deste pacote, não uma decisão de quem implementa — a invariante de
`src/test/primitivas.test.ts` (ADR 0026) proíbe o literal escrito à mão onde há primitiva, e a
saída legítima é criar a primitiva, com aprovação.

## Fronteira entre entregue e reservado

**Entregue nesta feature:** a tela `/contas/:id/priorizacao` (lista, detalhe, avaliação, histórico,
hipóteses), a seção de pain points em `ProcessDetailPage`, e os seis estados acima.

**Reservado (desenhado esmaecido, com a condição escrita ao lado):**

- **"Gerar Opportunity Map"** — o entregável de cliente que o método cita (`language-map` §5). Vira
  real quando houver `Artifact(kind=...)` para ele; hoje o botão não existiria.
- **"Sugerir score com IA"** — a sugestão da IA é insumo, nunca decisão, no mesmo molde de
  `Qualification.ai_suggested_outcome` (FDD 044). Vira real quando a Fase 4 tiver prompt e contexto
  próprios; **não** entra nesta entrega.
- **Vínculo com `Engagement`** — `ImprovementOpportunity.engagement` é opcional na issue. A coluna
  fica desenhada e vazia até haver mais de um mandato vivo na conta.

## O que a aprovação não cobre

- O **backend** da Fase 4 (modelos, rotas, permissões, migrações). Aprovar a tela não aprova o
  schema; ele vem no PR da #68, com FDD e ADR próprios se a decisão for durável.
- O **One**. Nada aqui projeta para o portal do cliente. `PainPoint` e `ImprovementOpportunity`
  aparecem lá pelo `language-map` §3, e isso é decisão do repo `one`.
- As telas da **Fase 5** (#69 — Feasibility, PROVE, KPI, Measurement, Value Ledger). Elas têm
  pacote próprio.
- **Copy final de microtexto** fora dos seis estados listados. Rótulo de botão e texto de ajuda que
  não estão no board seguem a copy vigente do produto.
- Qualquer alteração nas oito seções existentes de `AccountDetailPage` e nas quatro de
  `ProcessDetailPage`, que **não** são tocadas.

## Registro de aprovação

| Campo | Valor |
| --- | --- |
| Revisão | 1 |
| Decisões submetidas | A · B · C · D · E · **`.row-meta`** |
| Escolhas | **A1 · B1 · C1 · D1 · E1**, mais a aprovação explícita da primitiva nova |
| Aprovado por | Daniel Campos |
| Data | 2026-08-28 |
| Escopo | superfície, estados e uma primitiva nova. Não cobre backend, One, Fase 5, nem copy fora dos seis estados |

### A sexta decisão, que não estava no pacote quando ele foi escrito

`.row-meta` **não existe em `index.css`** e o board a usa. A seção "Procedência" deste pacote dizia
que a coluna "novo" estava inteiramente em "não" — dizia errado, e foi corrigida antes da
aprovação: uma evidência de gate que declara falso sobre si mesma não é evidência.

**Por que ela apareceu.** `.row-main` é `@apply min-w-0 flex-1` (`index.css:214`), e `flex-1` traz
`flex-basis:0`. Uma pílula `.state` irmã dentro da mesma `.row` não encolhe, então o título fica
com a sobra — e num título longo sem hífen, em 390px, a palavra vaza sobre a pílula. `.row-meta`
empurra o cluster de pílulas para a própria linha dentro da mesma `.row`. É posicionamento puro:
sem cor, sem raio, sem corpo de texto próprio.

**Aprovada**, com duas consequências registradas:

1. Ela nasce em `index.css` **com consumidor no mesmo commit**, como a invariante de
   `src/test/primitivas.test.ts` (ADR 0026) exige — classe sem chamador é a mesma dívida de
   chamador sem classe.
2. **O defeito já está em produção.** A composição `.row` + `.row-main` + `.state` é a das
   evidências de `ProcessDetailPage`; ela só não apareceu porque nenhum achado ficou longo o
   bastante, e não porque a composição esteja certa. A correção dessas telas vai para issue
   própria: consertar tela alheia dentro do PR da Fase 4 seria ampliar escopo por conta própria.
