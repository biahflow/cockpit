# Runbook de operação — Portal Biahflow

Guia prático do que ligar, em que ordem, e como testar. Tudo que depende de terceiros está
atrás de **flag**: desligado, o portal funciona normalmente. Ligue conforme tiver contas/keys.

Este documento é sobre **configuração**. Para percorrer o produto de ponta a ponta — entrar, criar
cliente, oportunidade, converter em projeto, montar equipe e conferir os indicadores — o roteiro é
[`runbooks/roteiro-de-teste.md`](runbooks/roteiro-de-teste.md).

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
| Assinatura eletrônica | `ESIGN_ENABLED`, `ESIGN_PROVIDER`, `ESIGN_API_TOKEN`, `ESIGN_WEBHOOK_SECRET`, `ESIGN_SANDBOX`, `ESIGN_DELIVERY` | conta Autentique | Pronto (desligado) |
| Webhook p/ portal do cliente | `PORTAL_WEBHOOK_URL`, `PORTAL_WEBHOOK_SECRET` | repo `portal_cliente` | Pronto (desligado) |
| Sincronia de tarefas (Linear/GitHub) | `TASKSYNC_ENABLED`, `TASKSYNC_TOKEN` + credenciais do fornecedor | conta Linear/GitHub | Pronto (desligado) |
| Sondas `/healthz` e `/readyz`, request-id e log estruturado | — | — | **Sempre ligado** |
| Rastreamento de erro (Sentry) | `SENTRY_DSN` (API) e `VITE_SENTRY_DSN` (SPA, build arg) | conta Sentry | Pronto (desligado) |
| Backup do banco e dos documentos | — (sidecar do compose de produção) | — | **Sempre ligado** em produção ✅ — agendado por `BACKUP_CRON` |
| Envio do backup para fora do host | `BACKUP_S3_*` | bucket compatível com S3 | Pronto (desligado) — **recomendado**: cópia no mesmo host morre com o host |

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
- **Assinatura (Autentique)**: `ESIGN_ENABLED=true` + `ESIGN_PROVIDER=autentique` +
  `ESIGN_API_TOKEN` (chave de API gerada no painel) + `ESIGN_WEBHOOK_SECRET`. `ESIGN_API_BASE`
  fica vazio (cada adaptador tem a própria URL padrão). No painel do Autentique, cadastre o
  webhook apontando para `https://<host>/api/v1/esign/webhook/` com **o mesmo segredo** — a
  entrega é validada por HMAC-SHA256 do corpo cru (header `x-autentique-signature`, hex puro) e é
  idempotente, então as reentregas (3 tentativas: 60s, 120s e 300s) não duplicam nada. Só
  `signature.accepted` e `signature.rejected` movem a assinatura; os demais eventos são ignorados
  com 200.
  - `ESIGN_SANDBOX=true` (padrão) cria documentos de teste: não consomem crédito e o fornecedor
    os apaga em poucos dias. Ponha `false` para valer de verdade.
  - `ESIGN_DELIVERY=email` (padrão) deixa o Autentique mandar o convite oficial; o portal não
    recebe link e o botão "Assinar" não aparece. Com `ESIGN_DELIVERY=link`, o portal recebe o
    `short_link`, convida o signatário por e-mail na hora e repete o link no lembrete — mas o
    convite passa a sair do portal, não do fornecedor.
  - Trocar de fornecedor é trocar o `ESIGN_PROVIDER` (`clicksign` também tem adaptador) e o
    segredo do webhook. Sem provedor (ou com a integração desligada), o botão "Marcar assinado"
    segue como fallback manual. Ver FDD 009 e ADR 0007.
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

## Equipe do projeto e visibilidade

Quem é da **Entrega** vê apenas os projetos de que participa — e tudo o que pende deles
(marcos, tarefas, reuniões, pendências, documentos, artefatos), mais os clientes que atende.
O critério é a **equipe do projeto** (`ProjectMember`); ser dono de um marco ou tarefa não
basta. Ver RFC 0003, ADR 0010 e FDD 018.

- **Quem monta a equipe:** só admin, no painel **"Equipe do projeto"** dentro do projeto.
- **Atenção na conversão:** quando **Vendas** converte uma oportunidade, o projeto nasce com uma
  única pessoa na equipe — quem converteu, por invariante ("quem responde pelo projeto participa
  dele"). Como essa pessoa é de Vendas ou Admin, o projeto fica **invisível para a Entrega** até um
  admin incluir alguém. Se alguém disser que "o projeto sumiu", é quase sempre isto.
- **No deploy desta versão**, a migração `0025` monta as equipes a partir de quem era dono do
  projeto, de um marco ou de uma tarefa — ninguém perde acesso. Mas esse acesso herdado é o
  antigo, que era largo demais: **revise as alocações** depois de subir.
- **Tirar alguém da equipe corta o acesso na hora.** Readmitir depois é permitido.
- Admin e Vendas continuam enxergando tudo.

## Limites de requisição

Toda a API tem teto (FDD 017, ADR 0009). `anon`/`user` são a rede de baixo; os escopos nomeados
protegem as portas específicas. Todos vêm do `.env` — mexa só se um limite estorvar uso legítimo.

| Escopo | Variável | Default | Protege |
| --- | --- | --- | --- |
| `anon` | `ANON_RATE` | `60/min` | toda a API para quem não está autenticado |
| `user` | `USER_RATE` | `2000/hour` | toda a API para quem está autenticado |
| `login` | `LOGIN_RATE` | `10/min` | força bruta de senha em `/auth/login/` |
| `invitation_accept` | `INVITATION_ACCEPT_RATE` | `20/hour` | criação de usuário sem autenticação |
| `portal_read` | `PORTAL_READ_RATE` | `120/hour` | adivinhação do `PORTAL_READ_TOKEN` no snapshot |
| `lead_intake` | `LEAD_INTAKE_RATE` | `20/hour` | formulário do site |
| `booking` | `BOOKING_RATE` | `60/hour` | horários livres e reserva |
| `task_sync` | `TASK_SYNC_RATE` | `60/hour` | webhook de Linear/GitHub |
| `esign_webhook` | `ESIGN_WEBHOOK_RATE` | `120/hour` | webhook do fornecedor de assinatura |

Dois avisos para produção, agora com trava:

- **Proxy.** O limite de anônimo é por IP, e o IP que o Django vê é o do último salto. Configure
  `NUM_PROXIES` com o número de proxies confiáveis do ingress; sem isso, todo mundo que passa pelo
  mesmo proxy divide um balde. No compose de desenvolvimento é o caso — o SPA fala com a API pelo
  container do Vite. O `docker-compose.prod.yml` põe `NUM_PROXIES=1` (o nginx é o único salto), e um
  check de deploy recusa confiar no `X-Forwarded-Proto` sem essa variável.
- **Cache.** O contador vive no cache. Sem cache compartilhado, o Django usa `LocMemCache`, que é
  por processo: com N workers, o limite efetivo é N vezes o configurado. Resolvido pelo `REDIS_URL`
  (FDD 019) — e, como produção agora roda com três workers de gunicorn, o `check --deploy` recusa
  subir sem ele.

## Produção: domínio, HTTPS e segredos

Desenvolvimento e produção são **composes diferentes**: `docker-compose.yml` roda `runserver` e
`docker-compose.prod.yml` roda gunicorn + nginx + Redis. O passo a passo (variáveis obrigatórias,
primeira subida, smoke test, ordem de ativação do HSTS, rollback e diagnóstico) está em
**`docs/runbooks/producao.md`**. O resumo:

```bash
cp .env.example .env      # preencha o bloco "Produção"
docker compose -f docker-compose.prod.yml up -d --build
```

Três coisas que mudam a operação (FDD 019, ADR 0011):

- **Configuração insegura não sobe.** O entrypoint da imagem roda
  `manage.py check --deploy --fail-level WARNING --tag security` antes do gunicorn. Faltando
  `DJANGO_SECRET_KEY`, `DATABASE_URL`, `REDIS_URL`, `DJANGO_ALLOWED_HOSTS` ou com origem `http://`
  em `DJANGO_CSRF_TRUSTED_ORIGINS`, o container recusa subir e o log nomeia o problema. É
  deliberado: sem isso, o portal subiria em SQLite efêmero parecendo saudável.
- **Nada de transporte seguro é ligado por default.** `DJANGO_SSL_REDIRECT` e `DJANGO_HSTS_SECONDS`
  vêm do ambiente porque `DEBUG=false` também é o modo da suíte de testes. O compose de produção já
  os liga; quem sobe fora dele precisa pôr no `.env`. **HSTS preload nasce desligado** e é quase
  irreversível — ligue por último, seguindo a ordem do runbook.
- **Sessão expira em 12 h de inatividade** (`SESSION_COOKIE_AGE`), deslizante: quem está usando não
  é deslogado no meio do trabalho.

O `.env` inteiro agora chega ao container (`env_file`). Antes, o compose repetia à mão parte das
variáveis e as ausentes eram descartadas em silêncio — se você já passou por "botei no `.env` e não
aconteceu nada", era isto.

## Monitoramento

Toda requisição carrega um `X-Request-ID` que volta na resposta e aparece nos três logs (nginx,
gunicorn e aplicação) — quando alguém relatar um erro, peça o **código da ocorrência** que a tela
mostra e procure por ele. As sondas são `GET /healthz` (vivo, não toca em nada) e `GET /readyz`
(pronto: banco + cache, 503 quando algum falha); aponte a sonda de reinício do orquestrador para a
primeira e a do balanceador para a segunda. Rastreamento de erro é o Sentry, atrás de `SENTRY_DSN`
(e `VITE_SENTRY_DSN`, que é **build arg** do SPA): desligado, nada é enviado a lugar nenhum.

Passo a passo, regras de alerta e diagnóstico: **`docs/runbooks/monitoramento.md`** (FDD 020, ADR 0012).

## Qualidade / CI
Antes de promover: `cd backend && uv run pytest && uv run mypy apps config && uv run ruff check .`
e `cd frontend && npm run lint && npm test && npm run build`. O workflow `.github/workflows/quality.yml`
roda isso mais Playwright E2E, audits e validação do `openapi.yaml`.
