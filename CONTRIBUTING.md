# Contribuindo

Use branches curtas e pull requests pequenos. Cada PR deve declarar o FDD, ADR ou RFC relacionado, o impacto em dados/API e os testes executados. O CI deve estar verde antes da promoção de ambiente.

Nome novo — de modelo, campo, rota, componente ou prop — segue [`docs/ontology/language-map.md`](docs/ontology/language-map.md), que é normativo; os aliases legados e a fase em que cada um morre estão em [`docs/ontology/aliases.md`](docs/ontology/aliases.md), e `backend/tests/test_vocabulario.py` reprova o que sair disso.



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
