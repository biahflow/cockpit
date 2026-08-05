# ADR 0008 — Artefatos da jornada como entidade

**Status:** aceito

## Contexto

Discovery, Assessment, Proposta e Contrato são as quatro etapas da jornada (RFC 0002) que
produzem texto. Nenhuma tinha onde guardá-lo. `_ai_run` devolvia `{text, interaction}` e seguia
adiante: o `AiInteraction` registra tokens, autor, recurso e nota — **nunca o conteúdo**. Na tela,
proposta e contrato só persistiam se alguém clicasse "Salvar como documento", que empacotava o
texto num `.txt` cujo tipo era adivinhável apenas pelo nome do arquivo; Discovery e Assessment
apareciam num painel de leitura e sumiam ao recarregar.

Duas consequências: **trabalho perdido** (o diagnóstico de uma reunião era irrecuperável) e
**nada de conversão medível por etapa** — o `funnel.by_tier` (FDD 015) mede nível de produto e o
`PipelineStage` mede aberto/ganho/perdido, mas nenhum dos dois responde "quantos clientes que
receberam um Assessment chegaram a receber uma Proposta?".

## Opções consideradas

**A. Continuar em `Document`, acrescentando um campo de tipo.** Barato. Mas `Document` é um
arquivo com dono e download — não tem conteúdo editável nem estado; ganharia um ciclo de vida
paralelo ao de arquivo, e artefatos ainda não salvos como documento (o caso comum: um rascunho em
revisão) não existiriam. Confunde "o que foi produzido" com "o arquivo que foi entregue".

**B. Três (ou quatro) modelos: `Assessment`, `Proposal`, `Contract`.** Mais expressivo por etapa —
cada um poderia ter campos próprios. Mas hoje os quatro têm exatamente a mesma forma (texto +
estado + origem), então a expressividade extra seria vazia; e triplicaria viewset, serializer,
policy de RBAC e testes. Pior: o funil por etapa viraria a união de quatro tabelas, quando é
justamente a pergunta central desta entrega.

**C. Um `Artifact` com `kind` (escolhida).** Um modelo, uma rota, uma policy; o funil por etapa é
um `GROUP BY`.

## Decisão

Adotamos a **opção C**, com as mesmas convenções que o app já usa em outros lugares:

- `kind` como `TextChoices` no modelo, exatamente como `Service.tier` estrutura os níveis de
  produto (FDD 015). Se algum dia um tipo precisar de campos próprios, ele sai para um modelo
  dedicado sem quebrar os outros três.
- **Vínculo único** a `opportunity` **ou** `project`, validado em `clean()` e no serializer — a
  mesma invariante do `Document`, e pelo mesmo motivo: o vínculo é o que define quem enxerga o
  conteúdo. Sem campo `client` denormalizado; o cliente vem pela ponta vinculada.
- **Estado explícito** (`draft → review → sent → accepted | rejected`) numa constante de módulo,
  `ARTIFACT_TRANSITIONS`, validada no serializer. Foi essa decisão que tornou a conversão entre
  etapas medível: `reached` conta clientes distintos por etapa, não artefatos.
- **`Document` continua sendo o arquivo.** O artefato o referencia (`document`), não o substitui.
  Assinatura eletrônica segue presa ao `Document` (ADR 0007) e nada em `SignatureRequest` muda —
  o artefato de contrato apenas **acompanha** a decisão do signatário quando o webhook chega.
- **A geração por IA é aditiva.** `_ai_run` cria o artefato quando recebe `artifact_kind`; as
  respostas das quatro rotas mantêm `text` e `interaction` e ganham `artifact`. O contrato
  `/api/v1/` é preservado, e a revisão humana continua obrigatória: o artefato nasce em rascunho.

## Consequências

O texto gerado deixa de ser efêmero e a jornada passa a ter funil próprio (`funnel.by_stage`), o
que fecha o critério de sucesso do PRD sobre medir conversão. Entrega ganha visibilidade do
Discovery/Assessment do projeto sem enxergar proposta e contrato — o recorte é feito no
`get_queryset`, como já se faz com oportunidades não ganhas.

Custo: um recurso a mais para manter e mais um lugar onde o mesmo conteúdo pode existir (artefato
e documento podem divergir se alguém editar o texto depois de salvar o arquivo). Aceitamos: o
documento é um instantâneo do que foi entregue, e é isso que se quer preservar. Não versionamos
artefatos — gerar de novo cria outro registro do mesmo `kind`, e a ordenação por `-created_at` dá
o mais recente; se o histórico por versão virar requisito, ele cabe sem migração destrutiva.
