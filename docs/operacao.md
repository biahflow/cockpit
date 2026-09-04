# Runbook de operação — Portal Biahflow

Guia prático do que ligar, em que ordem, e como testar. Tudo que depende de terceiros está
atrás de **flag**, e nenhuma flag liga sem as credenciais que ela exige (ADR 0018) — desligada, a
integração some da interface e as ações dela respondem 503, com o portal funcionando normalmente.
Notificações por e-mail e assinatura eletrônica **nascem ligadas**; as demais você liga conforme
tiver contas e chaves.

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
| **Níveis de produto** (Discovery Express / Discovery + Assessment / Implantação) | — | — | **Ligado** ✅ — semeados na migração; ajuste nome, preço e escopo no menu **Serviços** (`/servicos`, admin) |
| **Captação de leads** | `LEAD_INTAKE_TOKEN`, `CORS_ALLOWED_ORIGINS` | token (você define) | **Ligado** ✅ |
| Documentos no Google Drive | `GOOGLE_DRIVE_ENABLED` + auth ADC/OAuth (ADR 0016) | Pasta ou Shared Drive acessível à identidade | Desligado |
| Documentos no Cloud Storage | `GCS_MEDIA_BUCKET` | bucket com acesso uniforme, alcançável pelo ADC | Segue a variável, e **não é alternável na tela** — para onde o arquivo vai não é um interruptor: desligar deixaria órfão o que já está no bucket. Vazia = sistema de arquivos, que só é durável onde há volume. **Num ambiente sem volume, vazia significa arquivo perdido na revisão seguinte** |
| IA (assistente/resumos/proposta/próximos passos) | `AI_ENABLED`, `OPENAI_API_KEY` | conta OpenAI | Desligado |
| Notificações in-app (sino) | — | — | **Sempre ligado** |
| Notificações por e-mail e digest diário | `EMAIL_NOTIFICATIONS_ENABLED` (default `true`), `EMAIL_HOST`/`EMAIL_PORT`, `SCHEDULER_DIGEST_AT` | SMTP acessível (Mailpit no dev) | **Ligado** ✅ — ponha `false` para silenciar |
| Calendário (add ao Google Calendar + eventos → tarefas) | `CALENDAR_ENABLED`, `GOOGLE_CALENDAR_ID` | mesma auth do Drive, **outro escopo** | Pronto (desligado) |
| Agendamento (qualificação IA + booking pelo site) | `AI_ENABLED`+`CALENDAR_ENABLED`, `GOOGLE_BOOKING_CALENDAR_ID`, `BOOKING_MIN_FIT` | OpenAI + Google (free/busy) | Pronto (desligado) |
| **Agendamento do Discovery pelo cliente** | `DISCOVERY_BOOKING_ENABLED` (default `false`), `DISCOVERY_BOOKING_RATE` (60/hour) + `CALENDAR_ENABLED` | **nenhuma própria** — usa o SMTP e a agenda que já estão configurados | Pronto (**desligada**). Governa as duas rotas públicas (`/booking/discovery/slots/`, `/booking/discovery/`) **e** o convite por e-mail que leva o link — as duas metades do mesmo ato. Desligada por decisão declarada: é a primeira rota sem autenticação do produto além do login, e o e-mail sai sozinho para fora da casa. Exige `calendar` ligado; sem ele as rotas respondem 503 |
| Assinatura eletrônica | `ESIGN_ENABLED` (default `true`), `ESIGN_PROVIDER`, `ESIGN_API_TOKEN`, `ESIGN_WEBHOOK_SECRET`, `ESIGN_SANDBOX`, `ESIGN_DELIVERY` | conta Autentique — **ou nenhuma**, ver abaixo | **Ligado** ✅ — sem `ESIGN_PROVIDER` roda em registro local (`mark-signed` manual); com fornecedor nomeado, exige token e segredo do webhook |
| Gateway de pagamento (contas a receber) | `PAYMENTS_ENABLED` (default `true`), `PAYMENTS_PROVIDER`, `PAYMENTS_API_TOKEN`, `PAYMENTS_WEBHOOK_SECRET` | conta Stripe — **ou nenhuma**, ver abaixo | **Ligado** ✅ — sem `PAYMENTS_PROVIDER` roda em registro local (`mark-paid` manual); com fornecedor nomeado, exige token e segredo do webhook. **Stripe sem homologação** |
| **Régua de cobrança** (pré-aviso, lembrete, escalada) | `DUNNING_ENABLED` (default `false`), `SCHEDULER_DUNNING_AT` (09:30), `DUNNING_MIN_DAYS_BETWEEN_CONTACTS` (5) | **nenhuma** — usa o SMTP que já está configurado | Pronto (**desligada**). Não é integração: não fala com fornecedor nenhum, e por isso não tem `requires`. Desligada por decisão declarada, e não por custo — o gateway que *desarma* a régua (a baixa por webhook) segue sem homologação, e cobrar sobre reconciliação não exercitada é cobrar quem já pagou. Ligue depois da homologação do Stripe (runbook de homologação, seção 5). Marque em cada cliente quem **recebe cobrança** (contato), senão o degrau vira aviso interno |
| Base de conhecimento interna | `AI_ENABLED`, `OPENAI_API_KEY`, `AI_EMBEDDING_MODEL`, `KB_MIN_SIMILARITY_PERCENT`, `KB_TOP_K`, `SCHEDULER_KNOWLEDGE_AT` | mesma chave do assistente | Segue a flag `ai`. O **inventário de frescor funciona sem IA**; só a recuperação com citação exige a chave. Popular: `manage.py ingest_knowledge` |
| Webhook p/ portal do cliente | `PORTAL_WEBHOOK_URL`, `PORTAL_WEBHOOK_SECRET` | repo `portal_cliente` | Pronto (desligado) — liga sozinho quando as duas variáveis estiverem preenchidas; alternável em Configurações |
| Enriquecimento de lead (CNPJ) | `ENRICHMENT_ENABLED` (default `false`), `ENRICHMENT_PROVIDER` (default `brasilapi`), `ENRICHMENT_API_BASE`, `ENRICHMENT_TIMEOUT_SECONDS` | **nenhuma** — cadastro público | Pronto (desligado). Desligado não por custo (BrasilAPI é gratuita) e sim porque manda o CNPJ do formulário público a um terceiro. Alimenta o `ai_fit` e preenche a vertical na conversão; falha do fornecedor **nunca** bloqueia o lead |
| Sincronia de tarefas (Linear/GitHub) | `TASKSYNC_ENABLED`, `TASKSYNC_TOKEN` + credenciais do fornecedor | conta Linear/GitHub | Pronto (desligado) |
| Provisionamento GitHub de engenharia | `GITHUB_PROVISIONING_ENABLED` (default `false`), `GITHUB_TOKEN`, `GITHUB_REPO` | conta GitHub | Pronto (desligado) — distinto da sincronia FDD 004: cria a Issue-contrato do EngineeringOS, não vincula uma `Task` |
| Sondas `/healthz` e `/readyz`, request-id e log estruturado | — | — | **Sempre ligado** |
| Rastreamento de erro (Sentry) | `SENTRY_DSN` (API) e `VITE_SENTRY_DSN` (SPA, build arg) | conta Sentry | Pronto (desligado) |
| Backup do banco e dos documentos | — (sidecar do compose de produção) | — | **Sempre ligado** em produção ✅ — agendado por `BACKUP_CRON` |
| Envio do backup para fora do host | `BACKUP_S3_*` | bucket compatível com S3 | Pronto (desligado) — **recomendado**: cópia no mesmo host morre com o host |

> **As dez integrações** (IA, Drive, Calendário, Assinatura, Pagamento, E-mail, Sincronia de
> tarefas, Portal do cliente, Enriquecimento de lead e Provisionamento GitHub de engenharia) —
> mais a **régua de cobrança**, que é a primeira flag da casa que **não** é integração: ela não
> fala com fornecedor nenhum, e por isso não tem `requires`. São onze interruptores e dez
> fornecedores; a diferença importa, porque a régua desligada não é credencial faltando, é
> decisão. O provisionamento GitHub de engenharia (FDD 040) é outro interruptor, distinto da
> sincronia de tarefas (FDD 004): um cria a Issue-contrato, o outro espelha status de `Task`.
> Todos podem ser ligados/desligados em runtime por um admin na tela **Configurações**
> (`/configuracoes`), sem redeploy. O `.env` continua sendo o default e a casa dos segredos.
>
> Desde a ADR 0018, **credencial faltando vence qualquer intenção**: não liga pelo toggle, nem pelo
> default do `.env`. A tela nomeia a variável que falta ("Falta no ambiente: `ESIGN_API_TOKEN`").
> Atenção ao placeholder: `flags.missing()` só verifica se a variável está preenchida, então um
> `ESIGN_WEBHOOK_SECRET=<segredo do painel>` literal conta como configurado e **liga a integração**
> — quem pega isso é `manage.py check_integrations`, que pergunta ao provedor (FDD 024).

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
- **Conferir antes de ligar:** `manage.py check_integrations --all` pergunta à OpenAI se a chave
  funciona **e** se a conta alcança o modelo — sem gerar token. Chave boa com `AI_MODEL` errado
  reprova aqui, e é o erro mais comum.
- **O custo que não parte de ninguém:** o digest diário chama o modelo **uma vez por usuário
  ativo com itens, todo dia**, e é o único gasto de IA não iniciado por uma pessoa — ele fica
  de fora do `AI_DAILY_LIMIT`, que existe para limitar gente. Se a IA cair, o digest sai em
  texto estruturado em vez de não sair. Repare que isto deixou de ser hipotético: as notificações
  por e-mail nascem ligadas (ADR 0018), então ligar `AI_ENABLED` já basta para o gasto começar.
  Para o digest sem IA, mantenha `AI_ENABLED=false`; para nenhum digest,
  `EMAIL_NOTIFICATIONS_ENABLED=false`.
- **Teto por chamada:** `AI_TIMEOUT_SECONDS` (30 s) é o teto de **tempo** de verdade — o cliente
  vai sem retentativa, senão o SDK triplicaria por baixo. O teto de **tokens** é por feature, não
  global: existe na qualificação de lead (300) e no AI Score (500), que produzem JSON curto, e
  **não** existe em proposta e contrato, onde truncar cortaria uma cláusula no meio. Ver a rodada 2
  em `docs/runbooks/homologacao-de-integracoes.md`.

### 3. Documentos no Google Drive
- **Ativar a Google Drive API e a Google Calendar API** no projeto do GCP (são duas ativações
  separadas; faltando, o Google devolve `403 accessNotConfigured` com credencial válida) e dar à
  identidade acesso de escrita à pasta raiz — num **Shared Drive**, como Gerente de conteúdo.
- O passo a passo do projeto no GCP (APIs, tela de permissão, client OAuth e onde achar cada id)
  está na seção 3 do `docs/runbooks/homologacao-de-integracoes.md`.
- `.env`: `GOOGLE_DRIVE_ENABLED=true`, `GOOGLE_DRIVE_ROOT_FOLDER_ID=<id>` e o **modo de auth**
  (ADR 0016). Em container/pod, `GOOGLE_AUTH_MODE=adc` e Workload Identity — nenhum segredo no
  ambiente. Localmente, `adc` mais `gcloud auth application-default login`. Use
  `GOOGLE_AUTH_MODE=oauth` + o trio `GOOGLE_OAUTH_*` quando precisar **agir como uma pessoa**
  (convidar participante em evento). **Chave de conta de serviço não é caminho**: muitas
  organizações a proíbem por política, e foi o que bloqueou a homologação do Google.
- `docker compose up -d --build api`.
- **Testar:** subir um documento → conferir a estrutura `{Conta}/{Contratos|Propostas|NDAs|Acordos de Design Partner|Outros}/` no Shared Drive (a subpasta segue a finalidade do documento, `Document.kind` — issue #113); a pasta do projeto criada pelo kickoff fica em `{Conta}/Projetos/{Projeto}`.
- **O acervo anterior a 03/09/2026 não foi movido, e isso é decisão, não pendência** (issue #118,
  decidida em 04/09/2026): dentro de uma pasta de conta antiga, `1-Projetos`/`2-Áreas`/`3-Recursos`
  (a estrutura PARA que valia até a issue #113) convivem com as pastas por finalidade. Nada quebra —
  o `drive_link` de cada documento continua apontando para onde o arquivo sempre esteve, e o acervo
  antigo é finito. Mover seria operação sobre dado real de cliente: a maior parte daquele acervo não
  tem `Document.kind` marcado e iria inteira para `Outros`, o que é honesto mas não ajuda ninguém a
  achar nada. Se um dia doer, o caminho registrado na issue é classificar primeiro (na tela, por quem
  sabe) e mover depois, com comando idempotente, `--dry-run` obrigatório e rastro — e apagar as
  pastas antigas vazias é ato destrutivo que exige aprovação humana explícita na hora.

### 4. Calendário e Assinatura
- Calendário: `CALENDAR_ENABLED=true` + `GOOGLE_CALENDAR_ID` (mesma identidade do Drive, mas o
  **escopo é outro** — conceder Drive e esquecer Calendar é o erro comum, e é por isso que as
  sondas do `check_integrations` são separadas).
  - **Outbound**: botão "Adicionar ao calendário" em marcos/tarefas cria o evento no Google Calendar.
  - **Inbound (eventos → tarefas)**: eventos do calendário compartilhado com um marcador
    `#proj-<id>` no título ou na descrição viram tarefas do projeto indicado. Em produção quem
    roda é o serviço `scheduler`, a cada 15 min (FDD 023); para um tique manual use
    `docker compose exec api uv run python manage.py run_scheduler --once`, ou
    **Configurações → Calendário → "Sincronizar agora"**. É idempotente (não duplica) e ignora
    eventos criados pelo próprio portal. Ver FDD 012.
- **Agendamento (qualificação IA + booking)**: com `AI_ENABLED` e `CALENDAR_ENABLED` ligados, o
  formulário do site qualifica o lead por IA e, se passar do corte (`BOOKING_MIN_FIT`, default
  `medium`), oferece horários livres (free/busy de `GOOGLE_BOOKING_CALENDAR_ID`, fallback
  `GOOGLE_CALENDAR_ID`) e agenda automaticamente. Grade e duração: `BOOKING_HOURS` (código) e
  `BOOKING_SLOT_MINUTES` (default 45). No site (`biahflow-site/backend/.env`) nada muda além do
  `CRM_INTAKE_URL`/`CRM_INTAKE_TOKEN` já existentes — o relay descobre os endpoints de booking a
  partir do intake. Ver FDD 013.
- **Assinatura (Autentique)**: já vem `ESIGN_ENABLED=true` (ADR 0018). Sem `ESIGN_PROVIDER`, a
  integração roda no **registro local**: o portal grava a solicitação e espera o "Marcar assinado"
  manual, sem chamar ninguém e sem credencial nenhuma. Para valer com fornecedor, `ESIGN_PROVIDER=autentique` +
  `ESIGN_API_TOKEN` (chave de API gerada no painel) + `ESIGN_WEBHOOK_SECRET`. `ESIGN_API_BASE`
  fica vazio (cada adaptador tem a própria URL padrão). No painel do Autentique, cadastre o
  webhook apontando para `https://<host>/api/v1/esign/webhook/` com **o mesmo segredo** — a
  entrega é validada por HMAC-SHA256 do corpo cru (header `x-autentique-signature`, hex puro) e é
  idempotente, então as reentregas (3 tentativas: 60s, 120s e 300s) não duplicam nada. Só
  `signature.accepted` e `signature.rejected` movem a assinatura; os demais eventos são ignorados
  com 200.
  **A rodada tem mais de uma pessoa desde a ADR 0065**: `request-signature` aceita
  `{"signers": [{"email": …, "role": "house"|"counterparty"|"witness"}]}` numa chamada só — os três
  assinam o mesmo documento, e chamar o fornecedor uma vez por pessoa criaria três documentos
  separados. O corpo antigo (`signer_email`) continua valendo como um único `counterparty`.
  `ESIGN_HOUSE_SIGNER_EMAIL` (**vazio por padrão**) é o e-mail com que a casa assina: preenchido, o
  Pulse acrescenta o signatário `house` a toda rodada, e quem envia não digita o próprio e-mail
  toda vez; vazio, a rodada tem exatamente os signatários que o pedido nomeou. **O documento só
  conta como assinado quando a rodada inteira assinou** — por isso o contrato só é aceito e o
  mandato de Design Partner só abre depois do último, enquanto uma recusa vale na hora. A assinatura
  vai **posicionada** na última página (`positions`, contada com `pypdf`) nos três tipos que têm
  bloco de assinatura — acordo de Design Partner, NDA e contrato comercial; documento que não é PDF
  legível vai sem posição, com o motivo no log, e a assinatura cai na página anexa como antes. **As
  coordenadas x/y são estimativa não medida**: confira no painel do fornecedor onde os campos caíram
  no primeiro envio real e ajuste `_POSICAO_POR_PAPEL` em `backend/apps/core/esign.py`.
- **Pagamentos (Stripe)**: já vem `PAYMENTS_ENABLED=true` (ADR 0018). Sem `PAYMENTS_PROVIDER`, a
  integração roda no **registro local**: a fatura vive só no portal e "Marcar como paga" é o único
  caminho de baixa — modo previsto, não degradado, e a tela Financeiro funciona inteira assim. Para
  valer com fornecedor, `PAYMENTS_PROVIDER=stripe` + `PAYMENTS_API_TOKEN` (chave secreta do painel,
  `sk_test_…` ou `sk_live_…`) + `PAYMENTS_WEBHOOK_SECRET` (`whsec_…`, gerado ao cadastrar o
  endpoint). No painel do Stripe, cadastre o webhook em
  `https://<host>/api/v1/payments/webhook/` e assine **quatro** eventos: `invoice.paid`,
  `invoice.payment_succeeded`, `invoice.voided` e `invoice.marked_uncollectible`. A entrega é
  validada por HMAC-SHA256 sobre `<carimbo>.<corpo cru>` (header `Stripe-Signature`, formato
  `t=…,v1=…`) com tolerância de `PAYMENTS_WEBHOOK_TOLERANCE_SECONDS` (300) — o que faz uma entrega
  capturada parar de valer. É idempotente: reentrega do mesmo evento não duplica baixa, e um `paid`
  numa fatura já cancelada é recusado em vez de reabri-la. `invoice.payment_failed` é ignorado com
  200 de propósito — tentativa recusada não muda estado nenhum aqui. **O Stripe ainda não foi
  homologado contra conta real**; ver `docs/runbooks/homologacao-de-integracoes.md`. E a fatura
  vencida é marcada por trabalho agendado (`SCHEDULER_INVOICES_AT`, default `06:00` — antes do
  digest, para quem lê o dia achar o vencimento já apurado). Ver FDD 028 e ADR 0021.
  - `ESIGN_SANDBOX=true` (padrão) cria documentos de teste: não consomem crédito e o fornecedor
    os apaga em poucos dias. Ponha `false` para valer de verdade.
  - `ESIGN_DELIVERY=email` (padrão) deixa o Autentique mandar o convite oficial; o portal não
    recebe link e o botão "Assinar" não aparece. Com `ESIGN_DELIVERY=link`, o portal recebe o
    `short_link`, convida o signatário por e-mail na hora e repete o link no lembrete — mas o
    convite passa a sair do portal, não do fornecedor.
  - Trocar de fornecedor é trocar o `ESIGN_PROVIDER` (`clicksign` também tem adaptador) e o
    segredo do webhook. Sem provedor (ou com a integração desligada), o botão "Marcar assinado"
    segue como fallback manual. Ver FDD 009 e ADR 0007.
- Desligados, os botões não aparecem e as ações retornam 503. E "desligado" inclui **nomear o
  fornecedor e esquecer o token ou o segredo do webhook**: nesse caso a flag resolve para desligada
  em vez de deixar a chamada estourar no provedor (ADR 0018). A tela Configurações diz qual variável
  falta.

### 5. Webhook do portal do cliente
- `.env`: `PORTAL_WEBHOOK_URL`, `PORTAL_WEBHOOK_SECRET`, `PORTAL_READ_TOKEN`.
- Preenchidas a URL e o segredo, a integração **liga sozinha**. Para pausar a emissão durante um
  incidente do portal, desligue em **Configurações** — desde a ADR 0018 `portal.emit()` respeita o
  toggle, e antes disso só um deploy silenciava a entrega.
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
- **Não confundir** com o provisionamento de Issue de engenharia (FDD 040, flag
  `github_provisioning`): aquele cria o Task Contract no GitHub a partir de um handoff Pulse e
  **não** passa por `link-external` / `push-external` / `tasks/sync`.

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

## Retenção de dado pessoal (LGPD)

O portal arquiva e, desde a ADR 0017, também sabe **esquecer** — mas nasce inerte:

```bash
docker compose exec api uv run python manage.py purge_archived           # ensaia, não apaga
docker compose exec api uv run python manage.py purge_archived --apply   # apaga de verdade
```

`RETENTION_LEAD_DAYS` e `RETENTION_DOCUMENT_DAYS` nascem em **0**, que significa *nunca expurgar*.
O prazo é decisão de negócio com peso jurídico, não default de engenharia — a ADR 0017 lista o que
precisa ser decidido. Enquanto ninguém decidir, o comando diz isso em voz alta em vez de fingir que
rodou e não achou nada.

Duas coisas que valem saber antes de configurar: o expurgo **não é desfeito pelo backup** (se a
cópia trouxesse de volta, não teria sido expurgo — pense na janela das duas juntas), e `Account`,
`Project` e `CommercialOpportunity` ficam **de fora de propósito**, porque apagá-los
cascatearia sobre o histórico comercial inteiro.

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
| `knowledge_freshness` (job) | `SCHEDULER_KNOWLEDGE_AT` | `08:00` | avisa o dono da área sobre o que venceu; **não** sai com erro, porque dívida editorial não é incidente |
| `payments_webhook` | `PAYMENTS_WEBHOOK_RATE` | `600/hour` | webhook do gateway de pagamento — cinco vezes o teto do e-sign de propósito: o Stripe trata 429 como falha e faz backoff por dias, e cada pagamento chega em **dois** eventos |

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
