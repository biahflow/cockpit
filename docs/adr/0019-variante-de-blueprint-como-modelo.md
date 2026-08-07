# ADR 0019 — Variante de blueprint como tabela, não como JSON

- **Status:** aceita
- **Data:** 07/08/2026
- **Contexto:** FDD 026 (biblioteca de Funcionários Digitais), FDD 011 (template global + cópia por
  instância), FDD 015 (níveis de produto), FDD 025 (arquivar e restaurar pela interface)

## Contexto

A FDD 026 produtiza o Funcionário Digital: um catálogo de blocos que a entrega **instancia** em vez
de recriar, parametrizados por vertical — o mesmo "SDR" servindo imobiliária, saúde e igreja com a
mesma espinha e textos diferentes. A pergunta de modelagem é onde mora essa parametrização.

Duas formas cabiam. **Tabela própria** (`BlueprintVariant`, uma linha por blueprint × vertical) ou
**JSON no blueprint** (`overrides = {"igrejas": {...}, "saude": {...}}`), que economizaria um
modelo, um serializer, um viewset e uma rota — quatro peças para uma tabela com cinco colunas, das
quais quatro são sobrescritas opcionais.

A própria FDD registrou a dúvida em "Fora deste recorte" e adiou a decisão de propósito: *"é decisão
duradoura e pede ADR na hora de construir, não antes: sem uso real, escolher agora seria adivinhar"*.
Este é o momento.

## Decisão

**Tabela própria.** O que decide não é o número de peças, é a `UniqueConstraint(blueprint,
vertical)`.

Duas parametrizações do mesmo bloco para o mesmo setor não são configuração, são **ambiguidade**:
`blueprints.resolve()` teria de escolher uma, e qualquer critério que ele escolhesse seria arbitrário
e invisível. Num JSON a chave duplicada nem chega a existir — o último valor escrito silenciosamente
apaga o anterior, e ninguém fica sabendo. Numa tabela o banco recusa, o DRF deriva a validação da
constraint sozinho e a tela mostra 400.

É a mesma forma de invariante que este repositório já usa três vezes — `one_won_pipeline_stage`,
`one_lost_pipeline_stage` e `one_active_service_per_tier` —, e a FDD 015 já estabeleceu a regra de
não escrever à mão a checagem que a constraint dá: *"DRF deriva a serializer validation from these
constraints — don't hand-roll a duplicate check"*.

Três consequências vêm de carona, e nenhuma delas existia no JSON:

- **`vertical` vira FK `PROTECT`.** Excluir uma vertical que alguma variante usa passa a ser recusado
  pelo banco. Num JSON a vertical seria uma string de chave, e apagar a `Vertical` deixaria
  sobrescritas órfãs apontando para um setor que não existe mais — dado morto que ninguém encontra.
- **`prefetch_related("variants")` resolve o N+1** na listagem do catálogo. `resolve()` percorre
  `blueprint.variants.all()` em memória justamente para não furar o prefetch; com JSON não haveria
  N+1 porque não haveria consulta, mas também não haveria como filtrar por vertical no banco.
- **Um campo em branco significa "herda".** Numa tabela isso é `null` no decimal e `""` no texto, e a
  distinção entre "não sobrescreve" e "sobrescreve com zero" fica no schema. Num JSON, chave ausente
  e chave com `0` já são coisas diferentes, mas nada obriga ninguém a lembrar disso.

**A cópia por instância continua sendo a proteção do histórico**, e é independente desta escolha.
`DigitalEmployee` guarda os valores, não uma referência à variante — editar o catálogo amanhã não
reescreve o que foi entregue ontem. É a terceira aplicação do molde da FDD 011.

## Consequências

- **Três recursos novos no contrato `/api/v1/`** — `verticals`, `digital-employee-blueprints` e
  `blueprint-variants` —, todos aditivos. Nada existente muda de forma; `Client` ganha `vertical` e
  `Project` expõe `client_vertical`, ambos opcionais e read-only onde precisa ser.
- **Mais superfície para manter** que o JSON teria custado: dois viewsets a mais, dois serializers, e
  uma tela que precisa editar uma sub-lista. Aceito conscientemente — é o preço da invariante, e a
  `JourneyConfigPage` já provou que a sub-lista editável é barata de clonar.
- **A resolução vira código, não leitura de campo.** `blueprints.resolve()` é o único lugar que sabe
  que branco herda; qualquer consumidor novo (a proposta por IA foi o primeiro) chama-o em vez de
  reimplementar a regra. Uma regra, uma expressão — o mesmo princípio que a ADR 0010 aplica a
  `visible_to`.
- **Versionar o blueprint fica mais fácil, se um dia for preciso.** Uma tabela aceita ganhar
  `valid_from`/`version` sem migração de dado; um JSON teria de ser reinterpretado inteiro. Não é
  motivo para decidir agora — está em "Fora deste recorte" da FDD 026 —, mas é uma porta que esta
  escolha deixa aberta e a outra fecharia.
