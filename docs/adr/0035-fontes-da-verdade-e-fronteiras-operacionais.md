# ADR 0035 — Fontes da verdade e fronteiras operacionais

**Status:** Accepted  
**Data:** 2026-08-24

## Contexto

O produto interno passa a ser chamado **Pulse** e o portal do cliente passa a ser chamado **One**. O ecossistema BiahflowOS deixa de concentrar todas as responsabilidades de operação em um único banco/aplicação e passa a adotar ownership explícito por domínio.

A ADR 0004 e a FDD 004 assumem o portal interno como fonte da verdade também para tarefas de entrega. Essa premissa deixa de ser válida no novo desenho.

## Decisão

As fontes da verdade ficam definidas assim:

| Domínio | Sistema da verdade |
| --- | --- |
| Accounts, Leads, Contacts, Opportunities, CRM | Pulse |
| Delivery tasks, backlog, kanban e homologação | ClickUp |
| Engenharia: issue, branch, PR, CI e review técnico | GitHub |
| Artefatos visuais de discovery e arquitetura | Whimsical |
| Projeção orientada ao cliente | One |
| Eventos/auditoria de negócio | BiahflowOS/PostgreSQL |
| Telemetria técnica | OpenTelemetry |
| Execução e estado de agentes | LangGraph |
| Tracing/evals de LLM e agentes | LangSmith |

Pulse pode projetar e resumir estados pertencentes a ClickUp, GitHub e One, mas não deve duplicar ownership de campos que pertencem a esses sistemas.

One não conhece detalhes internos como GitHub Issue, Pull Request, ClickUp Custom Fields, estados de LangGraph ou IDs de integração. Ele recebe apenas uma projeção de negócio adequada ao cliente.

## Consequências

- Sincronização bidirecional genérica deixa de ser padrão; cada campo tem um dono.
- Integrações propagam eventos e projeções, não cópias concorrentes da mesma verdade.
- Mudanças de ownership exigem migração gradual e compatibilidade temporária.
- A ADR 0004 permanece como registro histórico, mas é **superseded** por esta ADR para ownership de Delivery.
- O Pulse evolui para control plane/command center da operação, não para um clone do ClickUp ou GitHub.

## Guardrails

1. Nenhum novo campo pode ser sincronizado em duas direções sem ADR explícita.
2. Projeções devem ser reconstruíveis a partir da fonte da verdade ou de eventos duráveis.
3. IDs externos podem ser armazenados como referências, nunca como identidade de domínio.
4. Mudança de status em um sistema só pode atualizar outro sistema quando houver regra de ownership definida.
