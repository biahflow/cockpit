# ADR 0069 — O que a 0030 adiou entra sem o gatilho que ela pediu, e o que ela nomeou já não existe

**Status:** aceita
**Data:** 2026-09-05
**Depende de:** ADR 0030 (a operação sai do texto) · ADR 0034 (só o fato sustenta número) ·
ADR 0035 (o produto se chama Pulse) · ADR 0020 (os snapshots congelados do `Case`) · ADR 0054
(a fórmula congelada e o `nao_apurado`) · FDD 039, FDD 045, FDD 048 e FDD 049 ·
`docs/metodologia-fde.md`
**Fecha:** as quatro pendências que o roadmap carregava sob "Seguem adiados" — três por decisão,
uma por não ter mais objeto

## Contexto

A ADR 0030 tirou a operação do texto e deixou de pé uma regra do material antigo: **a camada de
Discovery estruturado só é modelada depois de Discoveries reais.** A ADR 0034 exerceu essa regra
peça a peça, com um teste explícito — *existir no material como regra pronta (checklist, gate,
escada), não como ideia* — e o resultado não foi sim nem não: ela partiu o bloco em dois. Entraram
P-S-D-T-E-R, as cinco formas de evidência, os três rótulos e a fórmula do custo do estado atual.
Reprovaram sete peças.

**Cinco das sete foram pagas depois**, e nenhuma delas por relaxamento do teste: o Pain Point e o
par Evidence/Finding (FDD 045), o Opportunity Backlog — que virou `ImprovementOpportunity` —, o
Opportunity Score com a fórmula que a 0034 registrou como inexistente (FDD 048, `priority.FORMULAS`)
e o Value Ledger (FDD 049). Restaram três: **Business Case**, o **cockpit de reunião de Discovery**
e o **Next Best Opportunity**.

A quarta pendência da lista nunca foi peça de método: a **migração das quatro bases do Notion**
(Accounts · Contacts · Opportunities · Activities), que a própria ADR 0030 deixou "nomeada e não
feita".

O contador que a 0030 usou como gatilho **não andou**. Não houve a série de Discoveries reais que
ela pediu, e a tabela "Como esta base evolui" da ficha *Discovery Questions* — o registro que a
operação manteria a cada engagement — segue vazia. Continuar esperando é a decisão que esta ADR
recusa.

## Decisão

### 1. Os três blocos entram agora, sem o gatilho, e o que é aposta se declara

**O gatilho da ADR 0030 não é auto-cumprível para estas três peças, e a 0034 não tinha como ver
isso — ela mediu o material, não a dependência entre instrumento e prática.**

- O **cockpit** é o instrumento que produz Discovery estruturado. Esperar Discoveries reais para
  construir a ferramenta que os conduz é esperar que o processo estabilize sem instrumento — a
  reunião de duas horas continua sendo conduzida no caderno, e o que ela produz continua morrendo
  ali, que é literalmente o problema que a FDD 039 nomeia no título.
- O **Business Case** é o registro da decisão de investir. Ele não aparece no material porque a
  operação nunca teve onde registrá-la; a ausência do registro é a causa da ausência do material,
  não a prova de que a peça não estabilizou.
- O **Next Best Opportunity** já existe pela metade e ninguém percebeu: `priority.ranking_da_conta`
  ordena por Opportunity Score e `recommendations.py` já emite a recomendação `prioritization`.
  Manter "adiado" um bloco cuja maior parte está entregue é inventário errado, não prudência.

**O lastro mudou desde a medição da 0034**, e num ponto específico: os blocos A–F das *Discovery
Questions* são checklist pronto, com momento de uso mapeado e regra de saída explícita (*tudo o que
sai dali entra como evidência declarada, nunca como Baseline*). Isso passa no teste da 0030 —
apenas não estava no arquivo que a 0034 mediu, porque vive no Notion e o corpus nunca o alcançou.

**O que é aposta fica dito, aqui e no código.** Os campos do `BusinessCase` e a forma do cockpit
podem mudar depois dos primeiros Discoveries reais. Essa possibilidade não é risco descoberto: é a
consequência aceita desta decisão, e ela se paga com o mesmo mecanismo que o resto do produto usa —
o que muda é campo, não a verdade gravada, porque nenhuma das três peças reescreve número de outra.

### 2. A ADR 0030 não é revogada, e o teste dela continua valendo

O que esta ADR revoga é **um critério de espera que se mostrou circular**, não o princípio. Bloco
novo da camada FDE continua precisando provar que estabilizou — e as peças que seguem sem lastro
seguem fora, nominalmente: o `Opportunity Backlog` como ritual mensal, o Founder Dashboard e a
recomendação automática de Improvement Opportunities pela IA (Fase 3 do material) não entram aqui.

### 3. As quatro bases do Notion foram desligadas, não migradas — e a pendência morre

A ficha *Sistema Operacional — PULSE* declara, em 04/09/2026, que as quatro bases **não existem
como database no Notion**: elas vivem no Pulse (ADR 0035), e o que ficou na página é a
especificação do que o Pulse cobre. Uma varredura do workspace confirma: não há base de CRM, só
prosa.

Logo **não há o que migrar**, e insistir na linha seria manter um item de trabalho cujo objeto não
existe — o oposto do que a ADR 0034 chama de "lacuna nomeada com o motivo escrito ao lado".

O que sobra de vivo no Notion não é CRM, é **conhecimento**: as *Discovery Questions* e as três
Vertical Knowledge Bases (Home Care, Igreja, Engenharia). O destino delas não é uma importação de
dados — é o corpus da FDD 029, onde viram resposta citável em vez de página para ler, que é o
princípio da própria ADR 0030. Entram como **espelho**, no molde de `docs/ontology/`: a página do
Notion é a fonte, o arquivo aqui é cópia fiel e não se edita aqui.

## Consequências

- Nascem `BusinessCase` (entidade, no molde congelado do `Case` — ADR 0020), o cockpit de reunião
  (atrás de DAP aprovado, porque é superfície nova) e a promoção do `prioritization` a recomendação
  de primeira classe. Cada um em sua fatia, com FDD própria.
- O corpus ganha fonte que não vem de `docs/` escrito aqui, e o `KB_SOURCES` passa a ter um espelho.
  A disciplina do manifesto explícito continua: entra peça a peça, com tipo e área declarados, nunca
  por glob.
- O roadmap perde a frase "Seguem adiados **Business Cases**, o **cockpit de reunião de Discovery**,
  **Next Best Opportunity** e a migração dos dados do Notion" — três viram trabalho, uma vira fato
  registrado.
- **O risco assumido, dito com todas as letras:** se os primeiros Discoveries reais mostrarem que o
  Business Case precisa de outros campos, a migração é de schema e o custo é conhecido. O que não se
  aceita é o inverso — inventar processo que não aconteceu e depois preservá-lo por inércia. Por
  isso nenhuma das três peças ganha automação que decida sozinha: o cockpit captura o que gente
  digita, o Business Case registra a decisão que gente tomou, e a recomendação continua sugestão.

## Alternativas consideradas

- **Continuar esperando o gatilho.** Rejeitada pelo argumento circular acima: para duas das três
  peças, o instrumento é pré-requisito da prática que o gatilho mede.
- **Construir só o Next Best Opportunity** (o que já tem lastro) e manter os outros dois. Rejeitada
  porque o NBO isolado é a menor entrega das três e a que menos muda a operação — fecharia o item
  mais barato e deixaria em pé exatamente o que dói.
- **Modelar o bloco inteiro do material**, incluindo Founder Dashboard e a recomendação por IA.
  Rejeitada pelo motivo original da ADR 0030, que continua de pé: seria inventar processo que ainda
  não aconteceu, e desta vez sem nem a desculpa de um checklist pronto.
- **Importar as fichas do Notion como dado** (uma base de perguntas editável no Pulse). Rejeitada:
  a página do Notion é a fonte do método comercial, e duplicá-la como dado editável aqui criaria
  duas versões da mesma pergunta divergindo em silêncio — o defeito que o espelho de
  `docs/ontology/` existe para evitar.
