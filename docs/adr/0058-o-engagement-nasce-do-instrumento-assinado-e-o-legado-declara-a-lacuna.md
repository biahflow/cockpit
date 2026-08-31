# ADR 0058 — O Engagement nasce do instrumento assinado, e o legado declara a lacuna

**Status:** aceita
**Data:** 2026-08-31
**Depende de:** ADR 0049 · ADR 0050 · FDD 046 · `docs/ontology/language-map.md` D8 e
invariante 13
**Implementada por:** issue #62 · DAP Engagement r2, aprovado em 31/08/2026

## Contexto

O mapa de linguagem decidiu em D8 que um `Engagement` nasce de instrumento contratual assinado e
fixou a invariante 13: além de `commercial_model`, todo mandato referencia a origem. O schema
implementado na Fase 2 carregava apenas `commercial_model`; `POST /engagements/` aceitava origem
livre e `convert-to-project` criava a linha sem guardar a oportunidade que a originou.

Há dois atos comerciais diferentes. Uma conta paga fecha uma `CommercialOpportunity`; um Design
Partner não possui oportunidade de origem, mas possui um Design Partner Agreement. Colapsar os
dois em uma FK para oportunidade violaria D8. Colapsá-los em `Document` inventaria um documento
obrigatório para a venda quando a fonte canônica do funil é a própria oportunidade ganha.

O legado é ambíguo. Uma Account pode ter várias oportunidades ganhas e vários documentos
assinados; data, id e nome não provam qual deles originou o mandato. A mesma regra usada nas ADRs
0050 e 0057 vale aqui: uma lacuna declarada é mais verdadeira que uma inferência plausível.

## Decisão

`Engagement` ganha duas referências opcionais no schema e exatamente uma delas sustenta toda
criação nova:

- `originating_commercial_opportunity`: `OneToOneField(PROTECT)` para o caminho `paid`;
- `originating_design_partner_agreement`: `OneToOneField(PROTECT)` para o caminho
  `design_partner`.

As regras são cumulativas:

1. `paid` exige oportunidade da mesma Account e com `stage.kind=won`;
2. `design_partner` exige `Document` da mesma Account com ao menos uma `SignatureRequest` em
   `signed` e `signed_at` preenchido;
3. as duas origens não coexistem;
4. um instrumento origina no máximo um Engagement;
5. uma origem registrada não muda por `PATCH` operacional;
6. a oportunidade que origina o Engagement também recebe `CommercialOpportunity.engagement`,
   mantendo a primeira venda dentro do mandato que criou.

O banco fecha a forma estrutural com `engagement_has_one_origin_or_needs_review`: exatamente uma
origem, ou ambas ausentes quando `needs_review=True`. Modelo e serializer fecham as regras que
atravessam outras tabelas (Account, estágio e assinatura). `PROTECT` preserva a proveniência; o
arquivamento lógico do instrumento continua possível.

### Legado

A migração `0074` adiciona as referências nulas, não consulta candidatos e não cria nenhum. Toda
linha preexistente recebe `needs_review=True`. O carimbo já era uma dívida operacional ampla do
backfill da 0056; por isso o reverso da migração não o apaga.

Legados sem origem continuam válidos e editáveis. A origem pode ser preenchida uma vez por
remediação humana no admin/API; o sistema não limpa `needs_review` automaticamente, porque o mesmo
carimbo também pode representar a ambiguidade de agrupamento descrita na ADR 0050.

### Interface e contrato

O contrato `/api/v1/` recebe campos aditivos. A criação passa a exigir o vínculo — mudança de
validação deliberada para cumprir a invariante já normativa. O detalhe da Account segue o DAP
[`dap-engagement-r2`](../design/dap-engagement-r2/README.md): `commercial_model` revela um select
condicional com apenas instrumentos elegíveis; sem opção, a ação fica bloqueada e explica o
pré-requisito. Upload, pedido de assinatura e remediação em lote permanecem em superfícies próprias.

## Consequências

- A invariante 13 deixa de ser prosa sem coluna e passa a ser verificável no banco, modelo, API e
  tela.
- Design Partner continua sem `CommercialOpportunity` de origem; seu acordo assinado é a origem.
- A conversão de oportunidade ganha cria o Engagement já ligado à oportunidade, dentro da mesma
  transação do projeto.
- O histórico permanece utilizável e explicitamente incompleto até revisão humana.
- `needs_review` não significa apenas “instrumento ausente”; consumidores não podem limpá-lo por
  dedução depois de preencher a origem.
- O One não recebe o instrumento nem `commercial_model`: ambos são dados comerciais.

## Alternativas consideradas

- **Inferir pelo primeiro id/data.** Recusada: ordenação não prova origem contratual.
- **Criar documentos retroativos.** Recusada: fabricaria assinatura e contrato que não foram
  observados.
- **Exigir CommercialOpportunity também para Design Partner.** Recusada por D8: parceria de design
  não é venda fictícia.
- **Usar uma GenericForeignKey.** Recusada: perde integridade referencial e torna unicidade e
  `PROTECT` dependentes de código.
- **Uma FK única para Document.** Recusada: rebaixa a oportunidade ganha, fonte do funil, a um
  arquivo opcional e força documento onde o domínio declarou a própria venda como instrumento.

