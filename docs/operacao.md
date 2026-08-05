# Runbook de operação — Portal Biahflow

Guia prático do que ligar, em que ordem, e como testar. Tudo que depende de terceiros está
atrás de **flag**: desligado, o portal funciona normalmente. Ligue conforme tiver contas/keys.

## Subir o portal

```bash
docker compose up --build
docker compose exec api uv run python manage.py createsuperuser   # primeiro admin
```

| Serviço | URL |
| --- | --- |
| App | http://localhost:19173 |
| API / docs | http://localhost:19000/api/v1/ · /api/docs/ |
| E-mails (Mailpit) | http://localhost:19025 |

Após editar o `.env`, aplique com `docker compose up -d api` (recria o container lendo o `.env`).

## Estado das funcionalidades

| Recurso | Flag/env | Depende de | Estado |
| --- | --- | --- | --- |
| CRM, projetos, indicadores, ROI | — | — | **Sempre ligado** |
| **Níveis de produto** (Discovery Express / Discovery + Assessment / Implantação) | — | — | **Ligado** ✅ — semeados na migração; ajuste nome, preço e escopo em **Indicadores → Gerir serviços** (`/servicos`) |
| **Captação de leads** | `LEAD_INTAKE_TOKEN`, `CORS_ALLOWED_ORIGINS` | token (você define) | **Ligado** ✅ |
| Documentos no Google Drive | `GOOGLE_DRIVE_ENABLED` + service account | Google Workspace + Shared Drive | Desligado |
| IA (assistente/resumos/proposta/próximos passos) | `AI_ENABLED`, `OPENAI_API_KEY` | conta OpenAI | Desligado |
| Notificações in-app (sino) | — | — | **Sempre ligado** |
| Calendário (add ao Google Calendar + eventos → tarefas) | `CALENDAR_ENABLED`, `GOOGLE_CALENDAR_ID` | Google + service account | Pronto (desligado) |
| Agendamento (qualificação IA + booking pelo site) | `AI_ENABLED`+`CALENDAR_ENABLED`, `GOOGLE_BOOKING_CALENDAR_ID`, `BOOKING_MIN_FIT` | OpenAI + Google (free/busy) | Pronto (desligado) |
| Assinatura eletrônica | `ESIGN_ENABLED`, `ESIGN_PROVIDER`, `ESIGN_API_TOKEN`, `ESIGN_WEBHOOK_SECRET` | conta Clicksign | Pronto (desligado) |
| Webhook p/ portal do cliente | `PORTAL_WEBHOOK_URL`, `PORTAL_WEBHOOK_SECRET` | repo `portal_cliente` | Pronto (desligado) |
| Sincronia de tarefas (Linear/GitHub) | `TASKSYNC_ENABLED`, `TASKSYNC_TOKEN` + credenciais do fornecedor | conta Linear/GitHub | Pronto (desligado) |

> As integrações com flag booleana (IA, Drive, Calendário, Assinatura, Sincronia de tarefas)
> podem ser ligadas/desligadas em runtime por um admin na tela **Configurações** (`/configuracoes`),
> sem redeploy. O `.env` continua sendo o default e a casa dos segredos; o toggle só não liga uma
> integração cujas credenciais faltem no ambiente.

## Ordem sugerida de ativação

### 1. Leads do site (feito no CRM; falta o lado do site)
- No portal: `LEAD_INTAKE_TOKEN` já setado e validado (intake responde 201).
- No **site** (`biahflow-site/backend/.env`): use o **mesmo** token —
  `CRM_INTAKE_URL=http://<host-do-portal>/api/v1/leads/intake/` e `CRM_INTAKE_TOKEN=<mesmo>`.
- **Backfill** dos leads antigos do Mongo (uma vez): `cd backend && python scripts/backfill_leads_to_crm.py`.
- Depois: remover o MongoDB do site (já não é usado — ver `biahflow-site/CLAUDE.md`).
- **Testar:** enviar o formulário do site → o lead aparece no menu **Leads** do portal.

### 2. IA (OpenAI)
- `.env`: `AI_ENABLED=true`, `OPENAI_API_KEY=sk-...` (opcional `AI_MODEL`, default `gpt-4o-mini`).
- `docker compose up -d --build api` (rebuild instala o `openai`).
- **Testar:** no detalhe do projeto aparecem o **Assistente** e "Sugerir próximos passos";
  no detalhe da oportunidade, "Resumir" e "Gerar proposta". Limite: `AI_DAILY_LIMIT` (50/dia/usuário).

### 3. Documentos no Google Drive
- Criar service account (Drive API) + **Shared Drive** com a conta como Gerente de conteúdo.
- `.env`: `GOOGLE_DRIVE_ENABLED=true`, `GOOGLE_SERVICE_ACCOUNT_INFO={...json...}`, `GOOGLE_DRIVE_ROOT_FOLDER_ID=<id>`.
- `docker compose up -d --build api`.
- **Testar:** subir um documento → conferir a estrutura `{Cliente}/{1-Projetos|2-Áreas|3-Recursos}/` no Shared Drive.

### 4. Calendário e Assinatura
- Calendário: `CALENDAR_ENABLED=true` + `GOOGLE_CALENDAR_ID` (reusa a service account do Drive).
  - **Outbound**: botão "Adicionar ao calendário" em marcos/tarefas cria o evento no Google Calendar.
  - **Inbound (eventos → tarefas)**: eventos do calendário compartilhado com um marcador
    `#proj-<id>` no título ou na descrição viram tarefas do projeto indicado. Rode
    `docker compose exec api uv run python manage.py sync_calendar` (agende via cron), ou use
    **Configurações → Calendário → "Sincronizar agora"**. É idempotente (não duplica) e ignora
    eventos criados pelo próprio portal. Ver FDD 012.
- **Agendamento (qualificação IA + booking)**: com `AI_ENABLED` e `CALENDAR_ENABLED` ligados, o
  formulário do site qualifica o lead por IA e, se passar do corte (`BOOKING_MIN_FIT`, default
  `medium`), oferece horários livres (free/busy de `GOOGLE_BOOKING_CALENDAR_ID`, fallback
  `GOOGLE_CALENDAR_ID`) e agenda automaticamente. Grade e duração: `BOOKING_HOURS` (código) e
  `BOOKING_SLOT_MINUTES` (default 45). No site (`biahflow-site/backend/.env`) nada muda além do
  `CRM_INTAKE_URL`/`CRM_INTAKE_TOKEN` já existentes — o relay descobre os endpoints de booking a
  partir do intake. Ver FDD 013.
- **Assinatura**: `ESIGN_ENABLED=true` + `ESIGN_PROVIDER=clicksign` + `ESIGN_API_TOKEN` (token de
  acesso da conta) + `ESIGN_API_BASE` (`https://app.clicksign.com` em produção; o default é o
  sandbox) + `ESIGN_WEBHOOK_SECRET`. No painel do Clicksign, cadastre o webhook apontando para
  `https://<host>/api/v1/esign/webhook/` com **o mesmo segredo** — a entrega é validada por
  HMAC-SHA256 do corpo cru (header `Content-Hmac`) e é idempotente, então reentrega não duplica
  nada. Os eventos `sign`/`auto_close`/`document_closed` marcam "Assinado" e `refusal`/`cancel`
  marcam "Recusado"; o resto é ignorado com 200. Sem provedor (ou com a integração desligada), o
  botão "Marcar assinado" segue como fallback manual. Ver FDD 009 e ADR 0007.
- Desligados, os botões não aparecem e as ações retornam 503.

### 5. Webhook do portal do cliente
- `.env`: `PORTAL_WEBHOOK_URL`, `PORTAL_WEBHOOK_SECRET`, `PORTAL_READ_TOKEN`.
- Emite webhooks assinados (HMAC) quando Project/Milestone/Task/Document/**Meeting/Pendencia** mudam.
- O snapshot (`/api/v1/portal/projects/<id>/snapshot/`) também traz **reuniões, pendências e
  resultados** (KPIs derivados, sem dado comercial) — ver ADR 0005. Sem nova flag: entra no webhook
  já existente do portal.

### 6. Sincronia de tarefas (Linear/GitHub)
- `.env`: `TASKSYNC_ENABLED=true`, `TASKSYNC_TOKEN=<segredo>`. Por fornecedor:
  GitHub → `GITHUB_TOKEN`, `GITHUB_REPO` (`owner/repo`); Linear → `LINEAR_API_KEY`,
  `LINEAR_TEAM_ID` e os state IDs do workspace `LINEAR_STATE_TODO/IN_PROGRESS/DONE`.
- **Vincular**: `POST /api/v1/tasks/{id}/link-external/` (issue existente) ou
  `POST /api/v1/tasks/{id}/push-external/` (cria a issue e vincula).
- **Entrada**: configure o webhook do fornecedor para `POST /api/v1/tasks/sync/` com o header
  `X-Sync-Token: <TASKSYNC_TOKEN>` e corpo `{source, external_id, external_status}` (normalizado).
- **Testar:** mudar o status da issue vinculada → a tarefa muda no portal (e repropaga ao portal do
  cliente); mudar a tarefa no portal → a issue é atualizada. A entrada nunca gera loop (guard de eco).

## Qualidade / CI
Antes de promover: `cd backend && uv run pytest && uv run mypy apps config && uv run ruff check .`
e `cd frontend && npm run lint && npm test && npm run build`. O workflow `.github/workflows/quality.yml`
roda isso mais Playwright E2E, audits e validação do `openapi.yaml`.
