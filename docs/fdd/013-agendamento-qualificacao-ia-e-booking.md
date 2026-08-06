# FDD 013 — Agendamento: qualificação por IA + booking automático

## Jornada

Etapa **Agendamento** da jornada (RFC 0002). Quando um lead envia o formulário do site, a IA
**qualifica** o fit (rascunho para revisão humana); se passar do corte e o calendário estiver
ligado, o site oferece **horários livres reais** e o lead **agenda a reunião automaticamente**,
com evento no Google Calendar e confirmação por e-mail. Fora do corte, segue para contato manual.

## Fluxo

Site → relay FastAPI (`biahflow-site`) → `POST /api/v1/leads/intake/` (cabeçalho `X-Intake-Token`).
O CRM cria o `Lead`, qualifica (`qualification.qualify_lead`) e responde
`{qualified, booking_available, booking_token}`. Se qualificado + calendário ligado, o
`booking_token` (assinado, TTL 1h) autoriza `GET /api/v1/booking/slots/` e
`POST /api/v1/booking/book/`. O `X-Intake-Token` do CRM fica **só no relay**; o browser carrega
apenas o `booking_token` efêmero.

## Regras

- **Qualificação** atrás da flag `ai`: `ai.build_lead_context` (só dados do lead + respostas de
  triagem) → `ai.complete` pedindo JSON `{fit, score, summary, recommended_action}`; parse
  tolerante (cercas de código/texto ao redor); grava em `Lead.ai_fit/ai_score/ai_summary/
  ai_recommended_action/qualified_at`; auditado em `AiInteraction(user=None, lead=…,
  feature="lead_qualification")`. `ai` desligado → sem qualificação e `qualified=False`.
  **O mesmo vale quando a OpenAI falha**: a guarda que a FDD 024 pôs aqui foi finalmente
  observada na rodada 2, com o endpoint apontado para uma porta morta — o POST público
  responde 201, o lead fica gravado e cai na triagem manual, em vez do 500 que o visitante
  via para um cadastro que na verdade funcionou.
- **Corte**: `settings.BOOKING_MIN_FIT` (default `medium` → high+medium qualificam). Só quem passa
  recebe `booking_token`.
- **Disponibilidade** atrás da flag `calendar`: `booking.available_slots` = grade de horário
  comercial (`BOOKING_HOURS`, slots de `BOOKING_SLOT_MINUTES`) menos os períodos ocupados
  (`calendar_sync.freebusy` do `GOOGLE_BOOKING_CALENDAR_ID`, fallback `GOOGLE_CALENDAR_ID`) e menos
  as `Booking` já agendadas; nunca no passado.
- **Reserva** (`booking.book`): recheca o slot livre (freebusy + `Booking` com `select_for_update`)
  → `SlotUnavailable`/409 se tomado; cria `Booking` (ligada ao `Lead`, dono = 1º admin ativo);
  cria o evento com horário + convidado no Google Calendar (carimbo `biahflow_origin`); notifica o
  dono (in-app + e-mail) e envia confirmação ao lead.
- **Segurança**: endpoints públicos autenticam por `X-Intake-Token` + `booking_token`; throttle
  escopo `booking`; 401 sem intake token, 403 com booking token inválido/expirado, 503 com
  `calendar` desligado. Aditivo ao contrato `/api/v1/`.

## Aceite

Lead de bom fit (com `ai` e `calendar` ligados) recebe `booking_token`, vê horários livres reais e
consegue agendar; o `Booking` e o evento no Google Calendar são criados, o dono é notificado e o
lead recebe a confirmação. Lead de fit fraco (ou `ai` desligado) não recebe oferta de agendamento.

## Regressão crítica

Reservar o mesmo horário duas vezes retorna 409 (sem `Booking` duplicada); `slots`/`book` recusam
**A reserva sobrevive à recusa do Google.** `book()` grava a `Booking` e fecha a transação antes
de criar o evento; se o Google recusar (o caso conhecido é `forbiddenForServiceAccounts`, que conta
de serviço leva ao convidar participante sem delegação em todo o domínio), a reserva **vale** — o
horário está de fato comprometido —, o dono é avisado **com a ressalva de que a reunião não entrou
na agenda**, o lead recebe a confirmação e o visitante vê 201. Antes a exceção subia: sobrava uma
reserva bloqueando o horário, sem evento, sem aviso e sem confirmação, e o endpoint público
devolvia 500.

`booking_token` inválido ou expirado; com `calendar` desligado os endpoints retornam 503; a
qualificação tolera saída não-JSON do modelo sem quebrar o intake.
