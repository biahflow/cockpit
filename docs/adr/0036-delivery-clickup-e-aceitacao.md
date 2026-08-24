# ADR 0036 — ClickUp como SoR de Delivery e aceitação separada do merge

**Status:** Accepted  
**Data:** 2026-08-24

## Contexto

O fluxo anterior tratava tarefas internas como fonte principal e sincronizava ferramentas externas. O novo operating model define ClickUp como fila de trabalho e sistema da verdade de Delivery, enquanto GitHub é a fonte da verdade da execução de engenharia.

Merge técnico não equivale a valor aceito pelo cliente.

## Decisão

ClickUp será o sistema da verdade para backlog, prioridade, responsável, datas e status de Delivery.

O lifecycle mínimo de Delivery será:

`BACKLOG → READY → IN_PROGRESS → INTERNAL_REVIEW → CLIENT_REVIEW → ACCEPTED → DONE`

`BLOCKED` pode interromper qualquer estado executável.

Para itens de engenharia:

`ClickUp Task → GitHub Issue → Build → PR → CI/Review → Merge → CLIENT_REVIEW`

Um `pull_request.merged` **nunca** move automaticamente a task para `DONE`. O máximo permitido é `CLIENT_REVIEW`/`READY_FOR_ACCEPTANCE`.

`DONE` exige evidência de aceitação de negócio ou regra explícita de autoaceitação para classes de trabalho que não exigem homologação externa.

## Evidência de aceitação

A aceitação deve registrar, no mínimo:

- quem aceitou;
- quando;
- qual versão/entrega foi aceita;
- comentário ou evidência quando aplicável;
- `correlation_id` do fluxo.

## Consequências

- A sincronização de tarefas existente deve ser adaptada de bidirecional para integração orientada a ownership.
- Pulse exibe o estado de Delivery, mas não decide unilateralmente o status canônico.
- One pode expor pendências de homologação e registrar a decisão do cliente por contrato explícito.
- Automação de GitHub deve respeitar o human/client gate.
