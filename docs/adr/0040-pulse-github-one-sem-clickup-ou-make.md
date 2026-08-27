# ADR 0040 — Pulse + GitHub + One sem ClickUp ou Make

**Status:** aceita
**Data:** 2026-08-24

## Contexto

A arquitetura anterior colocou ClickUp como sistema da verdade de Delivery e Make como automação SaaS de bootstrap entre ClickUp e GitHub. Esse desenho acrescenta duas plataformas, sincronização adicional de estados e risco de drift sem necessidade clara, porque a Biahflow já terá Pulse para operação interna, GitHub para engenharia e One para experiência/aceitação do cliente.

A ADR 0036 é superseded por esta decisão no que diz respeito ao ownership de Delivery e ao uso de ClickUp.

## Decisão

O core operacional será:

```text
Pulse
  ↕ GitHub API / Webhooks
GitHub Issues / Projects / PR / CI
  ↕ eventos / projeções
One
```

Não haverá ClickUp nem Make no core stack.

### Fontes da verdade

| Domínio | Source of Truth |
| --- | --- |
| CRM, cliente, oportunidade, comercial | Pulse |
| Projeto, milestone de negócio, prioridade operacional | Pulse |
| Trabalho operacional não técnico | Pulse |
| Backlog e Task Contract de engenharia | GitHub Issues |
| Kanban de engenharia | GitHub Projects, quando necessário |
| Código, PR, CI e evidência técnica | GitHub |
| Regras de execução AI-assisted | EngineeringOS |
| Arquitetura, ADR, NFR, FDD e contratos | Git |
| Client review e aceite | One |
| Auditoria de negócio | PostgreSQL / Event Store |

Pulse não replica o detalhe técnico do GitHub. Ele mantém referências, agregados e estado relevante ao negócio.

One não vira sistema de gestão de trabalho. Ele projeta a entrega para o cliente e registra decisões/aceite.

## Lifecycle de engenharia e aceite

Fluxo canônico:

```text
Pulse / roadmap
      ↓
GitHub Issue
      ↓
Planner
      ↓
Builder
      ↓
PR + CI
      ↓
Reviewer + Human Gate
      ↓
Merge
      ↓
READY_FOR_ACCEPTANCE
      ↓
One / Client Review
      ↓
ACCEPTED
      ↓
DONE
```

`pull_request.merged` não significa `DONE` quando há aceite de negócio. Merge produz no máximo `READY_FOR_ACCEPTANCE`.

## Integração Pulse ↔ GitHub

A integração será implementada no backend do Pulse por GitHub API e Webhooks, sem plataforma SaaS intermediária obrigatória.

Responsabilidades mínimas:

- criar GitHub Issue a partir de trabalho de engenharia aprovado no Pulse;
- persistir `repository`, `issue_number`, URL e identificadores de correlação;
- consumir webhooks de Issue, Pull Request e checks relevantes;
- atualizar no Pulse apenas o estado de engenharia necessário à operação;
- tornar handlers idempotentes e retry-safe;
- nunca promover `merge` diretamente a `DONE`;
- preservar audit trail e `correlation_id`.

## GitHub Issue como Task Contract

O harness recebe a GitHub Issue como contrato técnico executável. A Issue deve referenciar explicitamente ADRs, NFRs, FDDs e o recorte do roadmap necessários à execução.

O Builder não deve consultar Pulse para descobrir o que implementar.

## Roadmap

`roadmap.md` é contexto estratégico e macroestado, não fila operacional detalhada. Não haverá `status.md` redundante por padrão.

GitHub Issues representam execução de engenharia; Pulse representa operação de negócio. Atualizações de roadmap devem ocorrer em mudança de Feature/Workstream/Milestone e preferencialmente por PR revisado.

## FinOps

Remover ClickUp e Make reduz:

- custo SaaS;
- integrações e webhooks redundantes;
- duplicação de estado;
- manutenção operacional;
- contexto documental repetido;
- risco de drift entre ferramentas.

Automações determinísticas de sincronização usam código comum e não LLM.

## Consequências

- ADR 0036 fica superseded em sua escolha de ClickUp como SoR de Delivery.
- ClickUp e Make passam a ser opcionais/adapters externos, não dependências do core.
- EngineeringOS deve refletir GitHub Issue como Source of Work sem depender de ClickUp.
- O diagrama BiahflowOS deve mostrar Pulse ↔ GitHub ↔ One como fluxo principal.
