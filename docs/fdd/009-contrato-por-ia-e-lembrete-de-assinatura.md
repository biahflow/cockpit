# FDD 009 — Contrato por IA e lembrete de assinatura

## Jornada

Etapa **Contrato** da jornada de consultoria assistida por IA (RFC 0002). No detalhe da
oportunidade, o time comercial gera um **rascunho de contrato por IA** a partir de um
modelo padrão de cláusulas, revisa e salva como documento. Sobre um documento, é possível
solicitar assinatura, **lembrar quem ainda não assinou** e registrar a assinatura —
fechando o laço do `esign` enquanto não há um provedor homologado.

## Regras

- **Geração de contrato** (`opportunity.contract`, feature `contract`): reusa o motor de IA
  (`_ai_run`) — depende de `AI_ENABLED` (503), respeita o limite diário (429) e é auditada
  em `AiInteraction`. O modelo preenche o contrato só com o material fornecido e marca
  `[lacunas]`; a saída é **rascunho para revisão humana**.
- **Solicitar/lembrar assinatura** dependem de `ESIGN_ENABLED` (503 quando desligado).
  `remind-signature` envia e-mail **apenas** aos signatários com status `pending`
  (best-effort, `fail_silently`), carimba `reminded_at` e retorna quantos foram lembrados.
- **Registrar assinatura** (`mark-signed`): move a `SignatureRequest` para `signed` com
  `signed_at`; assinaturas concluídas deixam de receber lembrete. Assinatura inexistente
  → 404. Um provedor homologado (Clicksign/DocuSign) faria essa transição por webhook no
  futuro; por ora é uma ação interna com trilha de auditoria de datas.
- O acesso segue o RBAC do recurso `document`/`opportunity`; documentos seguem privados
  (ADR 0002) e nada comercial vaza para o portal do cliente (ADR 0003).

## Aceite

Numa oportunidade, "Gerar contrato" retorna um rascunho para revisão e salva como
documento. Sobre um documento com assinatura pendente, "Lembrar" dispara e-mail aos
pendentes e "Marcar assinado" encerra a pendência; o status aparece por signatário.

## Regressão crítica

`contract` retorna 503 com IA desligada; `remind-signature` retorna 503 com esign
desligado e só e-mail os pendentes; após `mark-signed`, um novo lembrete lembra 0;
`mark-signed` de assinatura inexistente retorna 404.
