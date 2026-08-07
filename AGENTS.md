# Instruções para agentes e contribuidores

1. Leia `PRD.md`, os FDDs relevantes e ADRs antes de alterar comportamento.
2. Não exponha segredos, dados pessoais ou documentos em código, testes, logs ou commits.
3. Toda funcionalidade relevante atualiza seu FDD; decisão técnica duradoura exige ADR; mudança transversal ou incompatível exige RFC.
4. Preserve o contrato `/api/v1/`. Toda alteração incompatível deve ser deliberada e documentada.
5. Para corrigir defeitos, escreva primeiro um teste de regressão em `backend/tests/regression/` ou na suíte mais próxima.
6. Execute lint, tipos, testes e build aplicáveis antes da entrega. Não desative verificações de qualidade para concluir uma tarefa.
7. Use exclusão lógica quando houver registros de negócio; não elimine dados operacionais sem requisito explícito.


## Corpus de conhecimento (FDD 029)

`backend/apps/core/knowledge_corpus.jsonl` é **derivado** de `docs/` e `PRD.md` e vive commitado,
como o `openapi.yaml`. Mexeu em ADR, FDD, RFC, runbook, `PRD.md`, `docs/architecture.md`,
`docs/operacao.md` ou `docs/captacao-de-leads.md`? Rode:

```bash
cd backend && uv run python manage.py build_knowledge_corpus
```

e commite o `.jsonl` junto. O CI reprova se ele estiver defasado. A fricção é de propósito: é o que
faz "mudei a metodologia" ser um ato visível e revisado, em vez de o índice divergir do repositório
em silêncio.
