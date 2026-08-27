# ADR 0046 — A projeção de entrega GitHub lê, e não vira fonte da verdade

**Status:** aceita
**Data:** 2026-08-27
**Completa:** ADR 0040

## Contexto

A ADR 0040 fixou o fluxo `Pulse ↕ GitHub ↕ One` e listou, entre as responsabilidades mínimas da
integração, "consumir webhooks de Issue, Pull Request e checks relevantes" e "atualizar no Pulse
apenas o estado de engenharia necessário à operação, de forma idempotente e retry-safe, sem promover
merge a Done". A FDD 040 implementou a direção de **escrita** (Pulse cria a GitHub Issue como Task
Contract) e deixou explicitamente de fora webhooks, sincronia de PR e idempotência de entrada.

Falta a direção de **leitura**: o Pulse é a superfície de comando operacional e precisa ver o estado
de engenharia (Issue/PR/CI) sem sair para o GitHub. O risco de fazer isso errado é conhecido e caro:
se o Pulse passar a **guardar** esse estado como se fosse dele, vira um segundo sistema de registro
de engenharia, e a divergência silenciosa entre o que o Pulse diz e o que o GitHub diz é exatamente o
drift que a ADR 0040 removeu ao cortar ClickUp e Make.

## Decisão

O Pulse **projeta** o estado de engenharia do GitHub; não é autoritativo por ele. A fronteira é
estrutural, não convencional:

1. **A referência é canônica e mínima.** Uma projeção ancora em `(project, repository,
   issue_number)`, único por `(repository, issue_number)`, e pode apontar para o `EngineeringHandoff`
   que a originou (FDD 040) — reusa a referência, não a bifurca.
2. **Os campos de engenharia são somente-projeção.** `issue_state`, `pr_state`, `head_sha`,
   `ci_state` e irmãos são read-only no serializer: uma edição normal do Pulse **não** os reescreve.
   Quem os move é o webhook ou a reconciliação. Não há rota do Pulse que escreva estado de volta no
   GitHub por esta fatia (o provisionamento da FDD 040 é o único caminho de escrita, e é outro
   contrato).
3. **Status nunca é inventado.** Uma referência não confirmada é visível como distinta de uma
   confirmada: `current`/`stale`/`unavailable`/`permission_denied`/`reference_missing`. `stale` é
   derivado do frescor (`observed_at` vs. um limite), não persistido, para que "atual" não sobreviva
   à própria idade.
4. **Webhook-first, idempotente, com reconciliação determinística.** A entrada autentica por HMAC do
   corpo cru; a reentrega literal é absorvida por um inbox (`X-GitHub-Delivery` único); o
   out-of-order é barrado por marca d'água temporal; e um poll de reconciliação recupera eventos
   perdidos e traduz falha do GitHub em estado degradado explícito. Tudo determinístico e **sem LLM**
   (FinOps da EngineeringOS).
5. **Merge não é Done.** Esta fatia projeta `pr_state = merged`; não promove nada a concluído, não
   mescla PR e não dispara release — a mesma linha que a ADR 0040 traçou.

Fica atrás da flag `github_delivery`, desligada por padrão e fail-closed quando não configurada
(ADR 0018).

## Consequências

- O Pulse ganha a superfície de comando de entrega sem assumir a responsabilidade pela verdade
  técnica: o GitHub continua sendo o registro de Issue/PR/CI.
- A projeção pode ficar `stale` — e isso é uma feature, não um defeito: é preferível dizer "não
  confirmei agora" a afirmar um estado velho como atual. A reconciliação existe para encurtar a
  janela.
- A watermark de out-of-order é única por projeção nesta fatia; streams independentes (Issue/PR/CI)
  podem, em teoria, se atropelar dentro da folga que a reconciliação cobre. Uma watermark por-stream
  fica registrada como evolução, não como dívida silenciosa (FDD 041).
- Escrever estado de volta no GitHub (fechar Issue, pedir revisão) exigiria um contrato de comando
  separado e explicitamente autorizado; esta ADR não o abre.
