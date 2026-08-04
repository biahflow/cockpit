# ADR 0004 — Gestão de tarefas: espelho vs. sistema de registro externo

**Status:** aceito

## Contexto

A equipe de entrega quer trabalhar em ferramentas de tarefas que já conhece (Linear,
GitHub Issues). Hoje as tarefas são nativas: `WorkItem` → `Milestone`/`Task`, ligadas a
`Project` (`apps/core/models.py`), com status `todo/in_progress/done`. Vários recursos
dependem desse modelo interno: conversão oportunidade→projeto, indicadores/ROI, previsão
de atrasos e o **portal do cliente** (ADR 0003, que emite webhooks de `Task`/`Milestone`).

A pergunta é **quem é a fonte da verdade** das tarefas.

## Opções consideradas

**A. Linear/GitHub como sistema de registro externo.** O Biahflow deixaria de gravar
tarefas e leria de terceiros. Contras: ROI, atrasos e o portal do cliente passariam a
depender da disponibilidade e do modelo de dados de um sistema externo; o contrato
`/api/v1/` de tarefas ficaria acoplado a webhooks de fora; offline/reprocessamento fica
frágil. Prós: zero duplicação para quem já vive na ferramenta.

**B. Biahflow como fonte da verdade, Linear/GitHub como espelho opcional (escolhida).**
O `WorkItem` continua sendo o registro. A ferramenta externa é um espelho bidirecional
ligado por *flag*, coerente com o resto das integrações (Drive, IA, e-sign, webhook do
portal — todas desligáveis, ver `docs/operacao.md`).

## Decisão

Adotamos a **opção B**. O `WorkItem` ganha dois campos aditivos (migração 0008):

- `source` (default `"biahflow"`) — de onde o item nasce/espelha (`"linear"`, `"github"`).
- `external_id` — o id do item no sistema externo (issue).

Há uma `UniqueConstraint` condicional em `(source, external_id)` quando `external_id`
não é vazio, por modelo concreto (`core_task_unique_external_ref`,
`core_milestone_unique_external_ref`), garantindo mapeamento 1‑para‑1 sem impedir
tarefas nativas (que têm `external_id` vazio). Ambos são **read-only** na API: são
gravados pela camada de integração, nunca por clientes comuns.

O status externo (backlog, in review, blocked, labels…) é mais rico que os 3 estados do
Biahflow; a integração deve manter uma tabela de‑para explícita e não perder informação
no caminho.

## Fluxo de sincronia

```
Linear / GitHub  ⇄  BIAHFLOW (fonte da verdade)  →  portal_cliente (read-only, HMAC)
```

- **Entrada** (externo → Biahflow): webhook da ferramenta chega, acha a `Task` por
  `(source, external_id)` e atualiza `status`/`completed_at`. Reaproveita o padrão de
  token + endpoint dedicado do *lead intake*.
- **Saída** (Biahflow → portal_cliente): **não muda nada** — o webhook do ADR 0003 já
  dispara na mudança da `Task`, venha ela da UI, da API ou da ferramenta externa.

## Consequências

O cliente nunca fala com Linear/GitHub e o Biahflow segue como sistema de registro
único; a integração externa é ligável e removível sem afetar ROI, atrasos nem o portal.
Custo: manter o de‑para de status e a reconciliação por `external_id`. Nenhum dado
comercial é exposto à ferramenta externa. Mudanças aditivas, contrato `/api/v1/`
preservado. Uma FDD deve detalhar os adaptadores por fornecedor antes de ligar em produção.
