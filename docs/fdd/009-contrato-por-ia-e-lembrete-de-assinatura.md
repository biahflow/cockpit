# FDD 009 — Contrato por IA e assinatura eletrônica

## Jornada

Etapa **Contrato** da jornada de consultoria assistida por IA (RFC 0002). No detalhe da
oportunidade, o time comercial gera um **rascunho de contrato por IA** a partir de um
modelo padrão de cláusulas, revisa e salva como documento. Sobre um documento, é possível
solicitar assinatura ao **fornecedor homologado**, lembrar quem ainda não assinou e
acompanhar o status — que o próprio fornecedor devolve por **webhook** (ADR 0007).

## Regras

- **Geração de contrato** (`opportunity.contract`, feature `contract`): reusa o motor de IA
  (`_ai_run`) — depende de `AI_ENABLED` (503), respeita o limite diário (429) e é auditada
  em `AiInteraction`. O modelo preenche o contrato só com o material fornecido e marca
  `[lacunas]`; a saída é **rascunho para revisão humana**.
- **Solicitar/lembrar assinatura** dependem de `ESIGN_ENABLED` (503 quando desligado).
  `request-signature` chama o adaptador do fornecedor (`ESIGN_PROVIDER`) e guarda as
  referências devolvidas (`provider_ref` do signatário, `document_ref` do documento);
  sem fornecedor reconhecido ou sem `ESIGN_API_TOKEN`, a solicitação fica só local.
  `remind-signature` envia e-mail **apenas** aos signatários com status `pending`
  (best-effort, `fail_silently`), carimba `reminded_at` e retorna quantos foram lembrados.
- **Webhook de status** (`POST /api/v1/esign/webhook/`, público, sem sessão):
  - **503** com a flag `esign` desligada; **401** quando falta `ESIGN_WEBHOOK_SECRET` ou o
    HMAC-SHA256 do **corpo cru** (header `Content-Hmac: sha256=<hex>`) não confere;
    **400** com corpo que não é um objeto JSON.
  - De-para explícito de eventos: `sign`/`auto_close`/`document_closed` → `signed`;
    `refusal`/`cancel` → `declined`; qualquer outro **não move** a assinatura.
  - Casa a `SignatureRequest` por `provider_ref`; na falta dele, por `document_ref` +
    e-mail do signatário (case-insensitive).
  - **Idempotente**: reentrega do mesmo evento responde 200 sem recarimbar `signed_at` nem
    gerar segunda notificação. Evento desconhecido ou sem solicitação correspondente
    responde **200 "Evento ignorado."** — erro faria o fornecedor reentregar para sempre.
  - Ao aplicar, notifica quem enviou o documento (`uploaded_by`) via `notifications.notify`.
  - Protegido por `ScopedRateThrottle` (`esign_webhook`, default `120/hour`).
- **Registrar assinatura** (`mark-signed`): fallback manual — move a `SignatureRequest`
  para `signed` com `signed_at` quando não há provedor configurado (ou a assinatura correu
  fora do fluxo). Assinaturas concluídas deixam de receber lembrete. Assinatura inexistente
  → 404.
- O acesso segue o RBAC do recurso `document`/`opportunity`; documentos seguem privados
  (ADR 0002) e nada comercial vaza para o portal do cliente (ADR 0003).

## Aceite

Numa oportunidade, "Gerar contrato" retorna um rascunho para revisão e salva como
documento. Sobre um documento com assinatura pendente, "Lembrar" dispara e-mail aos
pendentes; quando o signatário assina no fornecedor, o webhook marca "Assinado" sem
intervenção e notifica quem enviou o documento. "Marcar assinado" segue disponível como
fallback manual; o status aparece por signatário.

## Regressão crítica

`contract` retorna 503 com IA desligada; `remind-signature` retorna 503 com esign
desligado e só e-mail os pendentes; após `mark-signed`, um novo lembrete lembra 0;
`mark-signed` de assinatura inexistente retorna 404. No webhook: HMAC errado → 401,
evento fora do de-para → 200 sem mudar nada, e **reentrega do mesmo evento não altera
`signed_at` nem duplica notificação** (`backend/tests/regression/test_esign_webhook_idempotent.py`).
