# ADR 0048 — A escada FDE inteira vira degrau comercial, e duas chaves são renomeadas

**Status:** aceita
**Data:** 2026-08-27

## Contexto

`Service.tier` nasceu com três níveis (FDD 015, migração `0020`): Discovery Express gratuito,
Discovery + Assessment pago e Implantação. Quando a metodologia FDE entrou no repositório (ADR
0030, `docs/metodologia-fde.md`), o docstring do modelo passou a *ler* esses três níveis como
degraus da escada — Discovery Express era a porta, Implantação era o PROVE — e registrou por
escrito que a Technical Feasibility ficava sem `tier` porque criá-la "mexe na constraint de um
ativo por nível e na semente, e é decisão de produto que espera o primeiro caso real que a exija".

O caso apareceu. A escada operada pela casa tem sete degraus vendáveis, e o catálogo descrevia
três — o que produzia duas dívidas concretas: negociação de Feasibility, Scale ou parceria contínua
não tinha onde morar no pipeline, e o funil por nível media uma escada que não é a que se vende.
Pior, o vocabulário da tela contradizia o da metodologia: "Implantação" e PROVE eram a mesma coisa
com dois nomes, e um deles não existia no material.

## Decisão

**`Service.tier` passa a ter um degrau por fase vendável da escada**, na ordem em que se vende:
`qualification_call`, `discovery_assessment`, `discovery_sprint`, `feasibility`, `prove`, `scale`,
`transformation`. A migração `0050` renomeia, semeia e rerrotula; `INVOICE_SCHEDULES` e
`KICKOFF_TEMPLATES` ganham um cronograma por degrau novo.

### Renomear, não recriar

`discovery_express` vira `discovery_sprint` e `implantacao` vira `prove` **por `UPDATE` na chave**.
Recriar como par novo/antigo quebraria o vínculo de toda oportunidade e todo projeto que já aponta
para aquele serviço, e o histórico do funil junto. Renomear preserva os dois.

Nome e resumo só são reescritos quando ainda são exatamente os semeados pela `0020`: quem editou o
catálogo pela tela decidiu alguma coisa, e migração que sobrescreve decisão de gente é migração em
que ninguém confia — o mesmo cuidado que a `0020` já tinha ao usar `get_or_create`.

### PRIORITIZE não vira degrau

Não se fatura separado: o ranking por Opportunity Score é o entregável do Discovery Sprint. Um
degrau que ninguém compra seria uma coluna do funil que nunca enche.

### Gratuito é o degrau, não o preço zero

A `0020` deixou a ambiguidade de semear degrau pago com `list_price = 0`, e a tela lia zero como
"gratuito". Com sete degraus isso deixa de ser detalhe: a Transformation Partnership nasce em zero
por ser **recorrente mensal**, e anunciá-la como gratuita seria dar de graça o que a casa cobra
todo mês. A regra passa a morar num lugar só (`frontend/src/tiers.ts`): gratuito é a Qualification
Call; zero em qualquer outro degrau é "preço a definir".

## Consequências

- **O enum público `TierEnum` muda de valores** — é mudança de contrato em `/api/v1/`, deliberada e
  documentada aqui e no `openapi.yaml` regenerado. Não há consumidor externo conhecido do Pulse
  hoje; o portal do cliente não lê `tier`. Um consumidor que persistisse `"implantacao"` precisaria
  do mesmo `UPDATE` que a `0050` faz.
- **A recorrência continua não modelada.** `list_price` é valor único, então a parceria contínua
  entra no pipeline como se um mês fosse o contrato inteiro, e `INVOICE_SCHEDULES` a deixa sem
  cronograma de propósito — semear qualquer coisa cobraria uma vez o que se cobra todo mês. Quem
  vende esse degrau monta a cobrança na mão, como já faz com serviço avulso. Modelar recorrência é
  ADR própria.
- **O subsídio de founding client não vira degrau.** O Discovery Express + Assessment é gratuito só
  dentro do programa, e o desconto mora no `estimated_value` da oportunidade — assim ele continua
  visível como valor concedido, em vez de virar ausência de dado no funil.
- A invariante de **um serviço ativo por degrau** vale igual para os sete; arquivar libera a vaga.

## Alternativas consideradas

- **Manter três níveis e registrar o resto como serviço avulso.** Barato, e apaga exatamente o que
  o funil precisa medir: onde a escada trava. Serviço avulso não entra em `by_tier`.
- **Criar chaves novas e arquivar as antigas.** Preserva a leitura literal de "não mexer em dado
  semeado", ao custo de quebrar o vínculo histórico de oportunidades e projetos — o oposto do que a
  ADR 0025/FDD 025 pedem sobre não deixar órfão apontando para linha escondida.
- **Um enum de escada separado do catálogo.** Dois conceitos de "o que vendemos" divergindo em
  silêncio, que é a razão de a FDD 015 ter posto os níveis sobre `Service` desde o começo.

## Emenda (ADR 0053, 28/08/2026) — a escada perde um degrau, e o Sprint ganha preço

A **ADR 0053** emenda esta em três pontos, e não a substitui:

1. **`discovery_assessment` sai do enum** (migração `0064`, guardada). Esta ADR o manteve como a
   porta gratuita do founding client; com o **Design Partner** cobrindo a entrada em vertical nova,
   ele deixou de ter trabalho a fazer — e um degrau que ninguém vende é a mesma coluna que nunca
   enche com que esta ADR recusou o PRIORITIZE. O `TierEnum` muda de valores pela segunda vez em
   duas semanas: deliberado, e registrado lá.
2. **O Discovery Sprint passa a R$ 3.000** de tabela, preço único. Ele tinha ficado em zero por
   acidente de renomeação (a `0050` trocou a chave sem tocar no preço), e o material carregava
   quatro números para a mesma coisa.
3. **"O subsídio de founding client não vira degrau" continua valendo, com outro nome.** O valor
   concedido ao Design Partner mora no `estimated_value` da oportunidade, como desconto sobre o
   preço de tabela — exatamente a regra que esta ADR escolheu. É o único ponto desta seção que a
   0053 confirma em vez de mexer.

A invariante de um serviço ativo por degrau e a `list_price` sem recorrência ficam como estão. A
escada passa a ter **seis** chaves.
