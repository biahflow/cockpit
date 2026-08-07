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


## Emenda (ADR 0018, 06/08/2026)

A flag `portal` deixou de ser controlada **apenas** por ambiente. Ela continua nascendo do par
`PORTAL_WEBHOOK_URL` + `PORTAL_WEBHOOK_SECRET`, mas passou a ser alternável em runtime na tela
Configurações, e `portal.emit()` consulta `flags.is_enabled("portal")` antes de agendar a entrega.

O motivo é operacional: pausar a emissão durante um incidente do portal exigia deploy. A entrega
segue best-effort e sem retentativa — desligar e religar **não** reenvia o que se perdeu no meio, e
a recuperação continua sendo o backfill manual descrito acima.


## Emenda (FDD 025, 07/08/2026)

O snapshot passou a carregar `archived_at` do projeto, e a rota de leitura
(`GET /api/v1/portal/projects/{id}/snapshot/`) **serve projeto arquivado**, com 200.

"O que entra no snapshot precisa de emissor" já valia para o arquivamento — `archive()` é um
`save()` e emite. Faltava a outra ponta: a rota escondia o arquivado, então a busca disparada pelo
próprio webhook levava 404, que o portal não distingue de "este id nunca existiu". O estado que já
mudou continuava na tela do cliente, agora por omissão do lado que deveria contá-lo. O 404 desta rota
volta a significar só "não existe", e quem declara o encerramento é o `archived_at` do snapshot.

Mudança **aditiva** ao contrato `/api/v1/`: um campo novo, e um id que antes respondia 404 passando a
responder 200.
