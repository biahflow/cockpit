# FDD 015 — Três níveis de produto

## Jornada

Fase 4 da visão da metodologia (RFC 0002). A consultoria é vendida em **três níveis**:
**Discovery Express** (gratuito, porta de entrada), **Discovery + Assessment** (pago) e
**Implantação**. Até aqui esses níveis viviam só no discurso comercial; agora são dados de
primeira classe: escolhidos na oportunidade, herdados pelo projeto na conversão, refletidos na
proposta gerada por IA e no cronograma de kickoff, e medidos no funil.

Os níveis são estruturados **sobre o catálogo de `Service`** que já existia — nada de um enum
paralelo. Um `Service` com `tier` preenchido é um nível de produto; com `tier` vazio segue sendo
um serviço avulso, que entra apenas no ROI por serviço.

## Regras

- `Service` ganha `tier` (`discovery_express` / `discovery_assessment` / `implantacao`, ou vazio),
  `list_price` (0 = gratuito) e `summary` (o que está incluso). A migração `0020` semeia os três
  níveis de forma **idempotente** (`get_or_create` por `tier`); nome, preço e resumo são editáveis
  pelo admin em **Serviços** (`/servicos`).
- **No máximo um serviço ativo por nível**, garantido por `UniqueConstraint` condicional
  (`~Q(tier="") & Q(archived_at__isnull=True)`) — mesma invariante do `PipelineStage` ganho/perdido.
  Arquivar um nível libera o `tier` para um substituto; serviços sem `tier` coexistem à vontade.
- `Opportunity.service` é **opcional** (`SET_NULL`) — campo aditivo, não quebra o contrato
  `/api/v1/` nem as oportunidades existentes.
- **Conversão de lead:** `leads/{id}/convert/` cria a oportunidade já no **Discovery Express**
  ativo (quando existir). Vendas troca o nível depois, se for o caso.
- **Conversão em projeto:** `convert-to-project` herda `opportunity.service` para o projeto,
  dentro da transação existente; um `service` explícito no payload prevalece. O status segue 201.
- **Kickoff por nível** (`kickoff.KICKOFF_TEMPLATES`): Discovery Express semeia 1 marco,
  Discovery + Assessment semeia 2, Implantação mantém o template padrão de 4 marcos. Projeto sem
  nível (ou com serviço avulso) cai no `KICKOFF_TEMPLATE` padrão. Prazos seguem limitados à janela
  do projeto (FDD 008).
- **Proposta e contrato:** `ai.build_opportunity_context` acrescenta nível, preço de tabela
  (`gratuito` quando 0) e escopo do nível; o prompt de `proposal` instrui a respeitar esse escopo
  e preço, e a não sugerir cobrança quando for gratuito. Sem nível, o comportamento anterior é
  preservado. Anti-vazamento intacto: só dados desta oportunidade.
- **Funil por nível:** `GET /analytics/` passa a trazer `funnel.by_tier` com total, abertas,
  ganhas, perdidas, valor estimado e taxa de ganho por nível — sempre os três, mesmo zerados.
- Acesso segue o RBAC já existente do recurso `service` (leitura para todos, escrita só admin) e
  do recurso `opportunity`.

## Aceite

Em **Serviços**, o admin vê os três níveis semeados, ajusta preço e escopo e salva. Em
**Comercial**, uma nova oportunidade pode ser criada com um nível; o card do pipeline mostra o
selo do nível. Ao converter uma oportunidade ganha de Discovery Express, o projeto nasce com o
serviço preenchido e com o cronograma curto de Discovery, não com os 4 marcos de implantação. Com
IA ligada, a proposta gerada cita o nível e o investimento correspondente. Em **Indicadores**, o
bloco "Conversão por nível de produto" mostra onde cada nível para no pipeline.

## Regressão crítica

Um segundo serviço ativo no mesmo nível é rejeitado (400 na API, `IntegrityError` no banco);
arquivar libera o nível. A conversão herda o serviço da oportunidade e o payload sobrescreve.
Discovery Express gera exatamente 1 marco e Implantação mantém os 4. Oportunidade sem nível não
inventa um bloco de nível no contexto da IA.
