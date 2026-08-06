# ADR 0003 — Webhook para o portal do cliente

**Status:** aceito

## Contexto

O portal do cliente (repositório `portal_cliente`) é um serviço externo separado que exibe
o andamento do projeto para o cliente. Ele precisa do status mantido aqui (Project,
Milestone, Task, Document), mas não deve reimplementar esse cadastro — o Biahflow é a fonte
da verdade.

## Decisão

O Biahflow **emite webhooks** quando muda qualquer objeto que o snapshot carrega (incluindo
arquivamento), com entrega assíncrona e **assinatura HMAC** por segredo compartilhado. A lista
cresceu com o produto e hoje é: Project, Milestone, Task, Document, Meeting e Pendencia (ADR 0005),
mais ProjectPhase e ProjectDeliverable — a jornada, que o snapshot já levava desde esta ADR mas
nenhum sinal anunciava, deixando a barra "Você está aqui" do portal dependente do salvamento de
outro objeto. **O que entra no snapshot precisa de emissor**, sob pena de o portal exibir um estado
que já mudou. Um
**token de leitura** (escopo read-only) permite ao portal fazer backfill/reconciliação via
`GET /api/v1/`. Nenhum dado comercial (Opportunity, PipelineStage, valores) é enviado ao
portal. As mudanças são **aditivas** e preservam o contrato `/api/v1/`.

## Consequências

O portal recebe mudanças em quase tempo real sem duplicar digitação; o Biahflow continua
como sistema de registro. É preciso configurar `PORTAL_WEBHOOK_URL` e `PORTAL_WEBHOOK_SECRET`
e proteger o token de leitura. Ver `portal_cliente/docs/adr/0006`.
