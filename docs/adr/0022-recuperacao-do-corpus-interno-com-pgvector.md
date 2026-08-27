# ADR 0022 — Recuperação do corpus interno neste repositório, com pgvector

**Status:** aceita
**Data:** 07/08/2026
**Contexto:** FDD 029 (base de conhecimento interna), ADR 0006 (motor de agentes), ADR 0013
(backup lógico em container próprio), FDD 024 (sondas de integração), FDD 022 (matriz de testes)

## Contexto

A FDD 029 fez o que uma FDD deve fazer quando esbarra numa decisão de arquitetura: **registrou a
bifurcação e não escolheu**. Nas suas Regras, com todas as letras — "uma bifurcação de arquitetura,
que é ADR e não detalhe de FDD… Esta FDD registra a decisão como pendente". As opções eram construir
recuperação aqui, duplicando um pipeline já resolvido em outra pilha, ou **reusar o índice do
`biahflow-portal-cliente`** como serviço.

A decisão foi tomada. Esta ADR a registra, e registra também o que ela custa.

## Decisão

**A recuperação é construída neste repositório, com embeddings da OpenAI e pgvector no Postgres.**

### Por que não reusar o índice do repositório vizinho

Ele é maduro — ingestão, chunk por página, citação exata, "não sei" honesto, isolamento por linha —
e mesmo assim reusá-lo seria errado aqui, por quatro razões apuradas no código dele:

- **Não existe rota de recuperação para outro serviço.** Tudo responde escopado ao projeto do
  **próprio usuário autenticado por OIDC**; há precedente de rota autenticada por chave, mas só no
  caminho de **escrita** (`/agent-events`). Reusar exigiria construir a rota que falta lá.
- **Outro fornecedor, duas vezes.** Lá o chat é Anthropic e o embedding é Voyage; aqui o chat é
  OpenAI. Reusar significaria ou padronizar tudo num fornecedor, ou manter dois.
- **Acoplamento de disponibilidade.** Um recurso **interno** passaria a depender do uptime de um
  serviço voltado ao cliente.
- **Atravessar a fronteira de dois repositórios é RFC**, não ADR, pelas convenções da casa.

### Por que **não** foi a alternativa léxica, que era a recomendação inicial

Vale registrar porque é a decisão mais discutível daqui. O corpus tem **69 mil palavras** — uma
categoria inteira caberia num prompt —, e `websearch_to_tsquery` + `pg_trgm` não exigiria
dependência nova, nem troca de imagem, nem um segundo job de CI. A escolha por pgvector foi
deliberada, sabendo disso: constrói-se **o caminho durável uma vez**, em vez de construir o barato
agora e o certo depois. O custo está listado em Consequências, e não é pequeno.

### As peças

- **`text-embedding-3-small`, 1536 dimensões nativas.** ~420 trechos × 1536 floats ≈ 2,6 MB.
  Encolher com o parâmetro `dimensions` economizaria pouco e compraria um jeito a mais de errar.
- **A dimensão é constante de módulo, não setting.** `VectorField` a assa na migração: um
  `AI_EMBEDDING_DIMENSIONS` seria promessa que o código não cumpre — alguém o mudaria e levaria um
  `ProgrammingError` no primeiro insert. O **modelo** é setting; trocá-lo é legal, trocar a dimensão
  é migração.
- **`embedding_model` carimbado por linha.** Trocar de modelo passa a ser detectável e reindexável,
  em vez de produzir um índice metade num espaço vetorial e metade noutro — defeito que não dá erro,
  só piora a busca em silêncio.
- **O corpus é um artefato gerado e commitado** (`knowledge_corpus.jsonl`), conferido no CI por
  `git diff --exit-code`. É o mesmo objeto que o `openapi.yaml` já é, com outro gerador. A
  alternativa — mudar o contexto de build para a raiz — tornaria **inerte** o `backend/.dockerignore`,
  cujo propósito declarado é manter documentos reais de cliente fora da imagem que vai ao registry.
- **Sem flag nova.** Mesma credencial e mesma decisão de ligar/desligar que a flag `ai` já governa.
  A sonda passa a conferir **os dois** modelos: conta com acesso ao chat e sem acesso a embeddings
  responde tudo normalmente até alguém rodar a ingestão.

### Sem índice ANN — e isso é engenharia, não omissão

`HnswIndex` emitiria `USING hnsw` e **quebraria `migrate` no SQLite**, levando a suíte inteira
junto. Mas o argumento decisivo é outro: a **~420 trechos um índice HNSW é mais lento e menos
exato** que a varredura exata — paga-se travessia de índice e aceita-se recall aproximado para
evitar um scan de microssegundos. O que o pgvector entrega neste tamanho é o **tipo de coluna** e o
**operador de distância em SQL**; o índice passa a pagar por volta de **50 mil trechos**, ~100× este
corpus, e aí se adiciona com uma operação `RunSQL` que no-op fora do Postgres.

### A suíte continua em SQLite, e há um job só para o Postgres

O modelo **nunca** ramifica por `connection.vendor` — só a busca: `CosineDistance` no Postgres,
cosseno em Python no SQLite. Duas expressões da mesma regra é o preço de a suíte rodar num banco e a
produção noutro, e o que impede a segunda de divergir em silêncio é o **teste de paridade**, que
exige o mesmo top-k das duas. O job `backend-pgvector` roda os testes marcados contra
`pgvector/pgvector:pg16` de verdade.

Verificado antes de decidir: `pgvector==0.5.0` **não traz `numpy`**, e o `VectorField` faz
round-trip no SQLite (a coluna é declarada `vector(1536)`, o SQLite aceita o tipo e o valor volta
como lista de floats).

## Consequências

- **A imagem do Postgres muda de família**, de `postgres:16-alpine` para `pgvector/pgvector:pg16`,
  nos dois compose. E aqui está **o item mais perigoso desta ADR**: alpine é musl, a imagem do
  pgvector é Debian/glibc, e **a collation de texto muda com a libc**. Para um cluster que **já tem
  dado**, montar o mesmo `postgres_data` sob a outra libc produz índices btree sobre texto
  sutilmente mal-ordenados — silencioso até um `ORDER BY`, um `LIKE` ou uma checagem de unicidade
  responder errado. **O drill não pega**, porque sempre parte de cluster vazio. Por isso o upgrade
  é procedimento obrigatório de runbook: parar `api`/`scheduler`/`web`, backup, trocar a imagem,
  subir o `db`, `REINDEX DATABASE`, e só então subir o resto — ou restaurar o dump num cluster novo,
  que reconstrói todo índice por construção.
- **A ADR 0013 é emendada.** O sidecar de backup fica em `postgres:16-alpine`, porque precisa de
  `pg_dump` da mesma **major** e não de pgvector, e porque o `entrypoint.sh` dele é busybox. A
  invariante sempre foi paridade de major; "mesma imagem" era só o mecanismo, e o mecanismo agora é
  uma **guarda no `backup-drill.sh`**, mais forte que depender de alguém reparar. O drill também
  passou a semear um trecho com 1536 floats reais e conferir que ele volta — senão a primeira pessoa
  a descobrir que o alvo de restauração precisa da extensão descobre às 4 da manhã.
- **Editar um ADR, FDD ou runbook passa a exigir regerar o corpus**, senão o CI reprova. É a mesma
  fricção do `openapi.yaml`, e é boa fricção: "mudei a metodologia" vira ato visível e revisado.
- **Uma dependência nova** (`pgvector`) na superfície do `pip-audit`, sem transitivas.
- **O que fica descoberto, dito em voz alta:** na suíte padrão não rodam o `CosineDistance`, a
  criação real da extensão nem o tipo `vector(1536)` como o Postgres o entende — quem cobre é o job
  novo. E **nada automatizado cobre a qualidade da recuperação**: se "procedimento de restauração"
  traz a ADR 0013 e não a FDD 019 é pergunta de homologação, e foi por isso que a rodada 5 existiu.
