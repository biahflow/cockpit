# FDD 015 — Degraus da escada FDE no catálogo

> O título original desta FDD era "Três níveis de produto". A ADR 0048 abriu o catálogo para a
> escada FDE inteira e renomeou duas chaves; o arquivo continua o mesmo para não quebrar as
> referências que já apontam para ele.

## Jornada

Fase 4 da visão da metodologia (RFC 0002). A consultoria é vendida em **degraus da escada FDE**
(ADR 0030, `docs/metodologia-fde.md`), um por fase vendável:

| `tier` | Degrau | O que fecha o degrau |
| --- | --- | --- |
| `qualification_call` | Qualification Call (gratuita) | avançar para o Discovery ou NO-GO |
| `discovery_sprint` | Discovery Sprint | Executive Readout com o ranking por Opportunity Score |
| `feasibility` | Technical Feasibility (T.O.E.) | decision gate GO / CONDITIONAL GO / REDESIGN / NO-GO |
| `prove` | PROVE (piloto) | decision gate SCALE / ITERATE / STOP |
| `scale` | Scale | captura de valor no Value Ledger |
| `transformation` | Transformation Partnership | recorrente: revisão mensal |

PRIORITIZE não tem degrau: não se fatura separado, é o entregável do Discovery Sprint.

Os degraus são estruturados **sobre o catálogo de `Service`** que já existia — nada de um enum
paralelo. Um `Service` com `tier` preenchido é um degrau; com `tier` vazio segue sendo um serviço
avulso, que entra apenas no ROI por serviço.

## Regras

- `Service` tem `tier` (um dos seis acima, ou vazio), `list_price` e `summary` (o que está
  incluso). A migração `0020` semeou os três primeiros de forma **idempotente** (`get_or_create`
  por `tier`), a `0050` completou a escada — renomeou `discovery_express` → `discovery_sprint` e
  `implantacao` → `prove` **preservando o vínculo** das oportunidades e projetos existentes, e
  semeou os quatro degraus novos — e a `0064` tirou o `discovery_assessment` (ADR 0053), com
  guarda que recusa apagar linha vinculada ou editada. Nome, preço e resumo seguem editáveis pelo
  admin em **Serviços** (`/servicos`, item do menu lateral, só admin), e nenhuma das três
  **sobrescreve** nome ou resumo que já tenham sido editados na tela.
- **Gratuito é o degrau, não o preço zero** (`frontend/src/tiers.ts`). Só a Qualification Call é
  gratuita; zero em qualquer outro degrau é preço a definir — a Transformation Partnership nasce em
  zero por ser recorrente mensal, e o catálogo ainda não sabe representar recorrência.
- **No máximo um serviço ativo por degrau**, garantido por `UniqueConstraint` condicional
  (`~Q(tier="") & Q(archived_at__isnull=True)`) — mesma invariante do `PipelineStage` ganho/perdido.
  Arquivar um degrau libera o `tier` para um substituto; serviços sem `tier` coexistem à vontade.
- `CommercialOpportunity.service` é **opcional** (`SET_NULL`) — campo aditivo, não quebra as oportunidades
  existentes. O enum `TierEnum` do `/api/v1/`, esse sim, mudou de valores (ADR 0048).
- **Conversão de lead:** `leads/{id}/convert/` cria a oportunidade já na **Qualification Call**
  ativa (quando existir) — o primeiro degrau, gratuito. Vendas troca o degrau depois, se for o caso.
- **Conversão em projeto:** `convert-to-project` herda `commercial_opportunity.service` para o projeto,
  dentro da transação existente; um `service` explícito no payload prevalece. O status segue 201.
- **Kickoff por degrau** (`kickoff.KICKOFF_TEMPLATES`): a Qualification Call semeia 1 marco, o
  Discovery Sprint 3 (fechando em Executive Readout), a Feasibility 3 (meta **antes** da amostra,
  E1–E5, decision gate de quatro saídas), o PROVE 4 (baseline e critérios **antes** de construir,
  produção controlada, decision gate de três saídas), o Scale 3 e a Transformation 2. Projeto sem
  degrau (ou com serviço avulso) cai no `KICKOFF_TEMPLATE` padrão. Prazos seguem limitados à janela
  do projeto (FDD 008).
- **Cobrança por degrau** (`invoices.INVOICE_SCHEDULES`, FDD 028): Qualification Call e
  Transformation Partnership são lista vazia — a primeira por ser gratuita, a segunda porque
  semear parcela única cobraria uma vez o que se cobra todo mês. Os demais seguem entrada/entrega
  alinhadas aos marcos do kickoff.
- **Proposta e contrato:** `ai.build_opportunity_context` acrescenta degrau, preço de tabela
  (`gratuito` quando 0) e escopo; o prompt de `proposal` instrui a respeitar esse escopo e preço, e
  a não sugerir cobrança quando for gratuito. Sem degrau, o comportamento anterior é preservado.
  Anti-vazamento intacto: só dados desta oportunidade.
- **Funil por degrau:** `GET /analytics/` traz `funnel.by_tier` com total, abertas, ganhas,
  perdidas, valor estimado e taxa de ganho — sempre os seis, mesmo zerados.
- Acesso segue o RBAC já existente do recurso `service` (leitura para todos, escrita só admin) e
  do recurso `commercial_opportunity`.

## Aceite

Em **Serviços**, o admin vê os seis degraus semeados, ajusta preço e escopo e salva — e a
Transformation Partnership aparece como "Preço a definir.", não como gratuita. Em **Comercial**,
uma nova oportunidade pode ser criada em qualquer degrau; o card do pipeline mostra o selo, e a cor
escurece conforme a escada avança. Ao converter uma oportunidade ganha de Qualification Call, o
projeto nasce com o serviço preenchido e com o cronograma curto, não com os marcos do PROVE. Com
IA ligada, a proposta gerada cita o degrau e o investimento correspondente. Em **Indicadores**, o
bloco "Conversão por nível de produto" mostra onde cada degrau para no pipeline.

## Regressão crítica

Um segundo serviço ativo no mesmo degrau é rejeitado (400 na API, `IntegrityError` no banco);
arquivar libera o degrau. A conversão herda o serviço da oportunidade e o payload sobrescreve. A
Qualification Call gera exatamente 1 marco, o PROVE traz baseline e decision gate no cronograma, e
o Discovery Sprint termina em Executive Readout. Oportunidade sem degrau não inventa um bloco de
nível no contexto da IA.

## Emenda (28/08/2026) — a escada perde um degrau, e o Sprint ganha preço

A **ADR 0053** remove `discovery_assessment` de `Service.tier` (migração `0064`). Ele era a porta
gratuita do programa de founding client; com o **Design Partner** cobrindo a entrada em vertical
nova — até três organizações, escopo fechado em um Discovery, um gate, uma Feasibility quando
disparar e um PROVE sobre **um** processo-alvo —, não sobrou trabalho para ele fazer. Um degrau
que ninguém vende é coluna de funil que nunca enche, que é o argumento com que a ADR 0048 já tinha
recusado o PRIORITIZE. A escada fica com **seis** chaves, cinco delas vendáveis.

O **Discovery Sprint passa a R$ 3.000** de tabela. Ele estava em `0,00` por acidente de história
(a `0020` semeou `discovery_express` em zero e a `0050` renomeou a chave sem tocar no preço), e o
material tinha quatro números para a mesma coisa. A migração só escreve sobre a linha ainda
semeada: preço editado na tela é decisão de gente e não se sobrescreve.

A gratuidade **não** vira campo. O valor concedido ao Design Partner continua morando no
`estimated_value` da oportunidade, como desconto sobre o preço de tabela — a mesma regra que a ADR
0048 escolheu para o founding client. Oportunidade zerada some do funil; valor concedido é número
que se olha.

Nada muda em `DEGRAU_GRATUITO` (`frontend/src/tiers.ts`): a Qualification Call segue o único
degrau gratuito por definição, e ela é oferta de **aquisição** (`Service.category`), não venda.
