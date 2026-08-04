# FDD 012 — Calendário → tarefas (eventos viram tarefas)

## Jornada

Complementa a etapa **Agendamento** da jornada (RFC 0002) e fecha o item de roadmap V3
"criação automática de tarefas a partir de eventos". Além do lado outbound já existente
(lançar um marco/tarefa no Google Calendar), o Biahflow passa a **ler** o calendário
compartilhado e criar **tarefas** no projeto correspondente, prontas para o dono revisar.

## Regras

- Atrás da flag `calendar` (`CALENDAR_ENABLED` + `GOOGLE_CALENDAR_ID`, reusa a service
  account do Drive). Desligado, é no-op e a ação manual retorna 503.
- **Associação evento → projeto** por convenção: um marcador `#proj-<id>` no **título ou na
  descrição** do evento (regex `#proj-(\d+)`). Sem marcador, ou projeto inexistente/arquivado,
  o evento é **ignorado** (nunca cria tarefa órfã).
- **Idempotência**: a tarefa nasce com `source="calendar"` e `external_id=<id do evento>`;
  o `UniqueConstraint(source, external_id)` do `WorkItem` garante que reprocessar os mesmos
  eventos não duplica (usa `get_or_create`).
- **Anti-loop**: eventos criados pelo próprio portal são carimbados em
  `extendedProperties.private.biahflow_origin`; o mapeador descarta qualquer evento com esse
  carimbo, então o outbound não volta como tarefa.
- Prazo da tarefa = data do evento (all-day `start.date` ou horário `start.dateTime` → data);
  o dono é o **dono do projeto**. A criação dispara notificação ao dono e webhook do portal
  pelos signals já existentes (não há caminho novo de notificação).
- Janela padrão de varredura: `SYNC_WINDOW_DAYS = 30` dias a partir de hoje.
- Disparo: management command `sync_calendar` (para cron) ou ação admin
  `POST /api/v1/config/sync-calendar/` (botão "Sincronizar agora" em Configurações). Aditivo
  ao contrato `/api/v1/`.

## Aceite

Com a flag ligada, um evento com `#proj-<id>` de um projeto ativo vira uma tarefa nesse
projeto (título do evento, prazo na data do evento, dono = dono do projeto), com o dono
notificado. Rodar a sincronização de novo não cria duplicatas.

## Regressão crítica

Reprocessar o mesmo evento não duplica a tarefa; eventos sem marcador, de projeto
arquivado/inexistente, ou originados no próprio portal (`biahflow_origin`) são ignorados;
com a flag desligada, `sync_calendar()` é no-op `(0, 0)` e a ação manual retorna 503.
