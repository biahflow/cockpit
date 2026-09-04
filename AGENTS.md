# Instruções para agentes e contribuidores

## Contexto Engineering OS

A camada global da Engineering OS está vendorizada e pinada em
[`docs/engineering-os/`](docs/engineering-os/PROVENANCE.md), na tag `v0.1.0` — alcançável do
próprio checkout, por CI e por colaborador novo, não só por quem tem um bootstrap pessoal
instalado. Ela é a **primeira** fonte em caso de conflito (ADR 0045): guardrails, princípios,
[Definition of Done](docs/engineering-os/core/definition-of-done.md), contratos de
[Planner](docs/engineering-os/agents/planner.md),
[Builder](docs/engineering-os/agents/builder.md) e
[Reviewer](docs/engineering-os/agents/reviewer.md), e os gates humanos.

A precedência é **assimétrica**: este repositório pode *acrescentar* restrição — mais teste,
mais revisão, mais evidência — e **não pode enfraquecer** guardrail global nem remover gate
humano. Documento daqui mais estrito que o global vale; mais frouxo é defeito, e o conserto é
aqui. O espelho não se edita: mudança na regra global é PR na origem, e chega como avanço de
pino, revisado.

Leia [`docs/project-context.md`](docs/project-context.md) para as
fontes canônicas do projeto, ciclo de features, perfis de validação e gates humanos. Ele complementa
a Engineering OS global; não a substitui.

1. Leia `PRD.md`, os FDDs relevantes e ADRs antes de alterar comportamento — e leia
   [`docs/ontology/language-map.md`](docs/ontology/language-map.md) **antes de nomear qualquer
   coisa nova** (modelo, campo, rota, componente, prop). Ele é normativo: um conceito, um nome,
   quatro superfícies. A §5 lista os termos banidos e a §6 as invariantes; os aliases ainda
   vivos e a fase em que cada um morre estão em
   [`docs/ontology/aliases.md`](docs/ontology/aliases.md). A regra é cobrada, não só escrita:
   `backend/tests/test_vocabulario.py` (ADR 0049) reprova declaração **nova** fora do
   vocabulário canônico, e a dívida legada que ela tolera está declarada linha a linha em
   `docs/ontology/legacy-allowlist.txt` — arquivo que só encolhe. Precedência: a página do
   Notion vence no **significado**, este espelho vence no **rótulo dentro do repositório**, e
   `AGENTS.md`/`CLAUDE.md` apontam para ele sem poder enfraquecê-lo. O espelho é cópia fiel e
   não se edita aqui.
2. Não exponha segredos, dados pessoais ou documentos em código, testes, logs ou commits.
3. Toda funcionalidade relevante atualiza seu FDD; decisão técnica duradoura exige ADR; mudança transversal ou incompatível exige RFC.
4. Preserve o contrato `/api/v1/`. Toda alteração incompatível deve ser deliberada e documentada.
5. Para corrigir defeitos, escreva primeiro um teste de regressão em `backend/tests/regression/` ou na suíte mais próxima.
6. Execute lint, tipos, testes e build aplicáveis antes da entrega. Não desative verificações de qualidade para concluir uma tarefa.
7. Use exclusão lógica quando houver registros de negócio; não elimine dados operacionais sem requisito explícito.


## Corpus de conhecimento (FDD 029)

`backend/apps/core/knowledge_corpus.jsonl` é **derivado** de `docs/` e `PRD.md` e vive commitado,
como o `openapi.yaml` e o `openapi-v2.yaml`. Mexeu em ADR, FDD, RFC, runbook, `PRD.md`, `docs/architecture.md`,
`docs/operacao.md` ou `docs/captacao-de-leads.md`? Rode:

```bash
cd backend && uv run python manage.py build_knowledge_corpus
```

e commite o `.jsonl` junto. O CI reprova se ele estiver defasado. A fricção é de propósito: é o que
faz "mudei a metodologia" ser um ato visível e revisado, em vez de o índice divergir do repositório
em silêncio.
