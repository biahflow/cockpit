# ADR 0007 — Assinatura eletrônica: provedor homologado e webhook de status

**Status:** aceito

## Contexto

A etapa **Contrato** da jornada (RFC 0002, FDD 009) já gera o rascunho por IA, registra
signatários (`SignatureRequest`) e lembra quem falta assinar. Faltava o essencial: a
assinatura em si. Até aqui `apps/core/esign.py` era um esqueleto — `send_for_signature()`
apenas logava, `SignatureRequest.provider_ref` nascia vazio, e a transição
`pending → signed` dependia de alguém clicar "Marcar assinado" no portal.

Isso deixa o estado da assinatura **desalinhado da realidade**: o cliente assina no
fornecedor e o Biahflow só sabe quando um humano se lembra de registrar. Indicadores de
conversão da etapa Contrato e o lembrete de pendentes herdam esse atraso.

Duas perguntas: **qual fornecedor** e **quem move o estado**.

## Opções consideradas

**A. Integrar um fornecedor direto nas views.** Menos indireção, mas amarra o
`DocumentViewSet` ao formato de um fornecedor e torna a troca (ou o suporte a dois
clientes com fornecedores diferentes) uma reescrita.

**B. Polling periódico do status.** Um comando `manage.py` consultando o fornecedor.
Dispensa endpoint público, mas gasta chamadas, atrasa o estado pela janela do cron e
repete um problema que o fornecedor já resolve empurrando o evento.

**C. Adaptador atrás de um protocolo + webhook assinado (escolhida).** Mesmo desenho já
usado na sincronia de tarefas (ADR 0004): de‑para explícito de status, entrada por
endpoint dedicado autenticado por segredo compartilhado, integração atrás de flag.

## Decisão

Adotamos a **opção C**. O fornecedor em uso é o **Autentique** (contexto brasileiro,
GraphQL com modo sandbox para homologação); o **Clicksign** fica como segundo adaptador.

- `esign.Provider` é um `Protocol` com `send` / `verify` / `parse_event`.
  `ESIGN_PROVIDER` escolhe o adaptador; sem um reconhecido, vale o `NullProvider`, que
  preserva o comportamento anterior (registra a intenção, não promete nada). Trocar de
  fornecedor é uma classe nova e uma linha no registry — nenhuma view, model ou tela muda.
- **Cada fornecedor traz o próprio esquema de assinatura do webhook**, e foi isso que
  validou o `Protocol`: o Autentique manda `x-autentique-signature` com o HMAC em hex puro,
  o Clicksign manda `Content-Hmac: sha256=<hex>`. Por isso `verify()` mora no adaptador e a
  view não conhece fornecedor nenhum.
- **O webhook é a fonte da transição de estado.** `POST /api/v1/esign/webhook/` valida
  HMAC‑SHA256 do **corpo cru** (segredo `ESIGN_WEBHOOK_SECRET`, comparação em tempo
  constante), normaliza o evento e aplica o status. Reusa `portal.sign()` — o mesmo HMAC do
  webhook do portal do cliente (ADR 0003).
- **Quem avisa o signatário é configurável** (`ESIGN_DELIVERY`). O Autentique só devolve o
  link de assinatura (`short_link`) quando o signatário é criado com entrega por link — e
  nesse modo ele não manda o convite. Default `email`: o fornecedor convida e o portal não
  duplica o aviso. Com `link`: o portal grava o `sign_url`, mostra "Assinar" na tela e
  entrega convite e lembrete por e‑mail.
- **Idempotência por construção.** `SignatureRequest` ganha `document_ref` e índice em
  `provider_ref` (migração 0021); o evento casa por `provider_ref` e, na falta dele, por
  `document_ref` + e‑mail. Evento já aplicado é no‑op: não recarimba `signed_at` nem
  renotifica. Fornecedores reentregam até receber 200.
- **Eventos desconhecidos respondem 200 "ignorado"**, nunca erro — um 4xx/5xx faria o
  fornecedor reentregar indefinidamente (o Autentique tenta 3 vezes: 60s, 120s e 300s). O
  de‑para é explícito e por fornecedor: Autentique `signature.accepted` → assinado e
  `signature.rejected` → recusado (os outros 13 eventos não movem nada); Clicksign
  `sign`/`auto_close`/`document_closed` → assinado e `refusal`/`cancel` → recusado.
- **`mark-signed` continua existindo**, agora como fallback manual declarado: sem
  provedor configurado (ou com assinatura em papel), alguém do time fecha a pendência à
  mão, com a mesma trilha de datas.

## Consequências

O estado da assinatura passa a refletir o fornecedor sem intervenção humana, e a etapa
Contrato fecha o laço da jornada. O portal ganha um segundo endpoint público — mitigado
por HMAC sobre o corpo cru, `ScopedRateThrottle` (`esign_webhook`, `120/hour`) e a flag
`esign`, que responde 503 quando desligada. Nada muda para quem não usa a integração: sem
`ESIGN_PROVIDER` o comportamento é o de antes.

Custo: manter o de‑para de eventos e o adaptador por fornecedor. As chamadas HTTP de saída
seguem o padrão de `tasksync.py` (`urllib`, timeout curto, best‑effort com log) e ficam
fora da cobertura. Mudanças aditivas: o contrato `/api/v1/` existente é preservado
(`request-signature`, `remind-signature` e `mark-signed` seguem iguais, agora com `sign_url`
a mais na resposta).

Homologado contra o sandbox real do Autentique. Duas coisas que a documentação do
fornecedor descreve de forma enganosa e o teste corrigiu, registradas para quem for mexer:
**`sandbox` é argumento do `createDocument`**, não campo do `DocumentInput`; e o
`link { short_link }` só vem preenchido para signatário com entrega por link — daí o
`ESIGN_DELIVERY`. Quando a API do fornecedor e a documentação divergirem, a introspecção do
schema é a fonte da verdade.
