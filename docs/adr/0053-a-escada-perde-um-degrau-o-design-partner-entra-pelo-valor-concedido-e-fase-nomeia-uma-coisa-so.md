# ADR 0053 — A escada perde um degrau, o Design Partner entra pelo valor concedido, e "fase" nomeia uma coisa só

**Status:** aceita
**Data:** 2026-08-28
**Emenda:** ADR 0048 · ADR 0035 · `docs/metodologia-fde.md`

## Contexto

A biblioteca de método no Notion cresceu por acréscimo — 23 fichas escritas em momentos
diferentes, cada uma coerente consigo mesma. Lidas juntas, contradiziam-se em quatro pontos que
nenhuma delas resolvia sozinha, porque a decisão nunca tinha sido tomada em lugar nenhum:

1. **Duas coisas diferentes chamadas "fase".** O ciclo do cliente (`discover → prioritize →
   feasibility → prove → scale → optimize`) e a entrada da casa numa vertical nova (`Fase 0 · 0.5 ·
   1 · 1b · 2 · 3-4 · 5 · 6`) usavam a mesma palavra em escalas incompatíveis. O mesmo baseline da
   Igreja aparecia como "Fase 2", "Fase 1b/2" e "Fase II" em três fichas.
2. **Pago contra gratuito, sem regra.** "Não fazer de graça. Eles pagam pelo trabalho" (Founding
   Client) convivia com "Design Partner, sem cobrança" (Home Care), "Design Partner gratuito, 90
   dias" (Igreja) e "PROVE operando — Cobra? Não" (Playbook), contra "PROVE também é pago, nunca POC
   grátis" (Financeiro). Dois modelos de negócio, nenhum critério de escolha.
3. **A escada não fechava.** O Discovery Sprint tinha quatro preços em quatro fichas (R$ 2.500,
   3.000, 3.500 e 5.000); a Feasibility tinha dois (R$ 2.500–5.000 e R$ 5.000); e "Implementation
   Project" aparecia como caminho de venda sem estar no catálogo nem ter preço.
4. **Nenhuma vertical tinha o mesmo conjunto de fichas** — porque o conjunto obrigatório nunca fora
   definido. Igreja tinha artefato de campo e nenhum blueprint; Home Care, blueprint e nenhum
   artefato de campo; Engenharia, só o AS-IS.

O repositório já estava mais coerente que o Notion: a ADR 0048 fixou a escada no enum
`Service.tier` e matou o PRIORITIZE como degrau, a ADR 0035 deu ao Pulse a posse do dado
comercial, e `docs/metodologia-fde.md` já declarava a Feasibility condicional. Faltava fechar o
resto, e fechar **aqui**, porque o Notion não é fonte de nada.

## Decisão

### "Fase" nomeia o ciclo do cliente, e só ele

As seis fases canônicas continuam sendo `discover`, `prioritize`, `feasibility`, `prove`, `scale`,
`optimize`. A entrada da Biahflow numa vertical nova passa a se chamar **Passo 0 a 6** — palavra
diferente para escala diferente. Nenhum documento volta a chamar de "fase" a numeração da entrada
em vertical, e a numeração romana ("Fase II") deixa de existir.

### O Discovery Express sai do enum

`discovery_assessment` é **removido** de `Service.tier`. Ele existia como a porta gratuita do
founding client; com o Design Partner cobrindo a entrada (abaixo), não sobrou trabalho para ele
fazer, e um degrau que ninguém vende é coluna de funil que nunca enche — o mesmo argumento com que
a ADR 0048 recusou o PRIORITIZE.

A migração é **guardada**: se existir qualquer `Service`, `CommercialOpportunity` ou `Project`
apontando para a chave, ela falha alto em vez de apagar vínculo. Remover valor de enum é mudança
de contrato em `/api/v1/`, a segunda em duas semanas depois da 0048 — deliberada, e registrada
aqui.

A escada passa a ter seis chaves: `qualification_call`, `discovery_sprint`, `feasibility`, `prove`,
`scale`, `transformation`.

### A Qualification Call é passo de aquisição, não venda

Permanece no enum, porque o funil precisa medir onde a escada trava, e continua sendo o único
degrau gratuito por definição (`DEGRAU_GRATUITO` em `frontend/src/tiers.ts`, inalterado). Mas nada
se vende nela: é onde a casa se apresenta, apresenta o método e decide com o cliente se há caso.
Ela termina em uma de duas saídas — proposta de Discovery Sprint, ou acordo de Design Partner.

### O Discovery Sprint custa R$ 3.000

Preço de tabela único, para quem não é Design Partner. Morrem a faixa R$ 2.500–3.500, o preço cheio
de R$ 5.000, a "condição piloto" de R$ 2.500 e a escada por maturação ("cases 1-2 / 3-5 / depois").
Quatro números para uma coisa é quatro chances de divergir.

### A Feasibility é sempre gate e às vezes produto

O **Decision Gate T.O.E. acontece em 100% dos casos** e sai no Executive Readout do Discovery, sem
cobrança. Ninguém o pula.

A **Technical Feasibility é o produto** — R$ 5.000, ~32h — e só existe quando responder ao gate
exige *medição*: puxar amostra real de dados ainda não vista, medir o Ceiling de Input, testar a
integração. Quando a resposta já está clara no Discovery (sistema conhecido, dado estruturado, API
madura), não há o que medir e não há o que cobrar.

O gatilho é objetivo, não é percepção: **se responder "conseguimos fazer?" exige uma amostra de
dado real que ainda não foi vista, é Feasibility paga; se não exige, é gate e fecha no readout.**
Isso é o que o material queria dizer com "Home Care e Igreja podem pular a Feasibility": não pulam
o portão, pulam a medição.

### Cada gate tem seu vocabulário

O repositório se contradizia sozinho neste ponto: a migração `0050` semeia o PROVE dizendo "fecha
em decision gate SCALE / ITERATE / STOP", enquanto `docs/metodologia-fde.md` declarava as quatro
saídas GO / CONDITIONAL GO / REDESIGN / NO-GO obrigatórias ao fim de Feasibility **e** de PROVE.
Decide-se a favor do código:

- **Feasibility** responde *"a tecnologia consegue fazer a tarefa?"* → `GO · CONDITIONAL GO ·
  REDESIGN · NO-GO`.
- **PROVE** responde *"funcionou em produção controlada?"* → `SCALE · ITERATE · STOP`.

São perguntas diferentes e merecem saídas diferentes. `docs/metodologia-fde.md` é corrigido nesta
ADR.

### "Implementation Project" deixa de existir

Era o mesmo objeto que Scale com outro nome, e mantê-lo como atalho significaria vender construção
sem prova — o oposto da tese da casa. Toda menção vira Scale.

### O Design Partner é o modo de entrada em vertical nova

Até **três** organizações por vertical nova entram sem cobrança, para derrubar a barreira de
entrada onde ainda não há case. O acordo fixa **escopo, não calendário**:

- **O que se dá:** um Discovery, um gate e — quando disparar — uma Feasibility, e um PROVE, sobre
  **um** processo-alvo. Nada além disso.
- **Sem teto por fase.** Termina quando o PROVE entra em produção, no ritmo que der. Encerramento
  automático em 120 dias se o cliente travar, para o acordo não ficar aberto para sempre.
- **A conversa comercial acontece no go-live do PROVE**, não no fim de uma janela. Continuar
  rodando já é Transformation Partnership, paga desde o primeiro mês. A janela de medição corre em
  paralelo e não segura a cobrança.
- **A contrapartida é contratual, não moral:** acesso a dado real, sponsor nomeado, horas semanais
  comprometidas do time do cliente, e case + depoimento + referência por escrito. Descumprimento
  encerra o acordo.

**No funil, o gratuito aparece como oportunidade real.** Cada degrau concedido vira
`CommercialOpportunity` normal, com `estimated_value` no preço de tabela e o subsídio registrado
como desconto — a mesma regra que a ADR 0048 já escolheu para o founding client. Valor concedido é
número que se olha; oportunidade com valor zero é número que some.

### O conjunto mínimo por vertical

Toda vertical, sem exceção, tem quatro documentos — e uma vertical sem os quatro está declarada
incompleta, não "diferente":

1. **Blueprint do produto** — domínios operacionais, catálogo de processos, modelo de ROI, roadmap.
2. **Knowledge base** — glossário, checklist de qualificação, hipóteses, sistemas, dados a pedir,
   objeções.
3. **Roteiro da primeira conversa** — script com o decisor, objeções e termômetro de qualificação.
4. **Mapa AS-IS + baseline** — o processo-alvo como é hoje, e a planilha que trava o número antes
   do PROVE.

Nenhuma vertical é priorizada sobre as outras: as três correm, e vira founding client quem
responder primeiro.

### O Notion é espelho

A ADR 0035 já dava ao Pulse a posse de Account, Lead, Contact e Opportunity. Fica explícito o outro
lado: **`docs/` neste repositório manda no método**; o Pulse manda no dado. A biblioteca do Notion
é superfície de leitura e passa a espelhar `docs/`. Nenhuma ficha do Notion volta a se declarar
fonte da verdade do método.

## Consequências

- **`TierEnum` muda de novo.** `openapi.yaml` regenerado, e a migração precisa da guarda descrita
  acima. Quem persistisse `"discovery_assessment"` fora do Pulse quebraria — não há consumidor
  externo conhecido, e o portal do cliente não lê `tier`.
- **`docs/metodologia-fde.md` muda** na seção de decision gate e ganha o gatilho objetivo da
  Feasibility, o Design Partner e a distinção fase/passo.
- **O Design Partner custa caro e isso está declarado, não mitigado.** Discovery (31h) +
  Feasibility (32h) + PROVE (65h) ≈ 128h por parceiro. Três por vertical, com as três verticais
  correndo em paralelo e sem teto por fase, é da ordem de mil horas concedidas antes da primeira
  receita recorrente. A trava é o limite de três e a contrapartida contratual; não há trava de
  prazo por fase, e essa ausência é escolha registrada.
- **A biblioteca do Notion precisa ser reescrita** contra esta ADR: 23 fichas, das quais sete
  carregam contradição direta, e sete documentos de vertical ainda não existem.
- A barra de cinco fases do Kit de Marca (`Discover · Prioritize · Prove · Scale · Optimize`)
  **deixa de estar errada**: com a Feasibility sendo gate e não fase vendida sempre, cinco
  segmentos é a leitura correta para o cliente.

## Alternativas consideradas

- **Arquivar `discovery_assessment` em vez de removê-lo do enum.** Preservaria o vínculo histórico
  e o contrato público, ao custo de manter no catálogo uma chave que ninguém mais vende. Recusada
  em favor da escada limpa; a guarda da migração cobre o risco de dado órfão.
- **Feasibility como degrau fixo, vendido sempre.** Mais receita e margem previsível — é o degrau
  de melhor hora da escada —, mas acrescenta uma terceira venda antes do PROVE numa casa que ainda
  não tem case, e contradiz `metodologia-fde.md`, que já a declarava condicional.
- **Janela fixa de 90 dias para o Design Partner**, como estava na minuta da Igreja. Ignora o
  tamanho do processo-alvo nos dois sentidos, e prende a primeira cobrança ao calendário em vez de
  prendê-la ao go-live do PROVE.
- **Notion como fonte do método, repositório como fonte do código.** Mais confortável para quem lê
  método fora do git, e é exatamente a divergência que produziu as quatro contradições acima.
