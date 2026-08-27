# Homologação de integrações

Sair de "achamos que funciona" para "rodou, e aqui está a evidência".

Todo código que fala com provedor externo está atrás de `# pragma: no cover` — a suíte para na
fronteira do mock. Este runbook é o procedimento que executa essas linhas pela primeira vez, uma
integração por vez, e registra o que foi observado. Ver FDD 024.

**A ordem é por custo e risco:** e-mail (sem credencial), IA (custa por chamada), Google (cria
artefato na sua conta), assinatura (manda e-mail a uma pessoa).

## Antes de qualquer rodada

```bash
docker compose up -d
docker compose exec api uv run python manage.py check_integrations --all
```

`--all` sonda inclusive o desligado, que é como se confere a credencial **antes** de ligar. A sonda
faz uma chamada real, barata e só de leitura; nenhuma gera token, cria arquivo ou manda e-mail.

Regras que valem para todas as rodadas:

- **Segredo só no `.env`**, que está no `.gitignore`. Nunca em comando, log ou commit.
- **Sem endereço real** nos dados semeados — use `@exemplo.test`.
- **A flag entra por runtime** (`AppSetting`), não editando o `.env`: é o caminho que a tela
  Configurações usa, e volta ao estado original no fim.
- **Limpe o cenário e a caixa** ao terminar, para a próxima rodada começar do zero.

---

## 1. E-mail — homologado em 06/08/2026

Única rodada sem credencial externa: o Mailpit sobe no `docker-compose.yml` e aceita qualquer
destinatário sem entregar a lugar nenhum.

**Atenção:** a porta SMTP do Mailpit (1025) **não é publicada no host** — só a interface web
(8025→19025). E o `docker-compose.yml` define `EMAIL_HOST`/`EMAIL_PORT` no bloco `environment`, que
vence o `env_file`. Portanto tudo roda via `docker compose exec api`; da sua máquina não alcança.

### Ligar

Desde a ADR 0018 esta flag **já nasce ligada** — o passo abaixo só é necessário se alguém a desligou
(pela tela ou com `EMAIL_NOTIFICATIONS_ENABLED=false`):

```bash
docker compose exec api uv run python manage.py shell -c \
  "from apps.core.models import AppSetting; AppSetting.objects.update_or_create(key='email', defaults={'enabled': True})"
```

### Conferir — pela API, não pelo olho

```bash
curl -s localhost:19025/api/v1/messages | python3 -m json.tool   # lista
curl -s -X DELETE localhost:19025/api/v1/messages                # limpa entre casos
curl -s localhost:19025/api/v1/message/<ID>/raw                  # headers crus (encoding)
```

### O que foi observado

| Fluxo | Gatilho | Resultado |
| --- | --- | --- |
| Sonda SMTP | `check_integrations` | **OK** — `SMTP mailpit:1025 respondeu` |
| Convite | `POST /invitations/` | 1 mensagem, `de=noreply@biahflow.local` |
| Espelho de notificação | criar lead / tarefa | 1 mensagem por destinatário |
| Kickoff | `convert-to-project` | 1 mensagem ao dono do projeto |
| Digest | `run_scheduler --once` | 3 mensagens, e `Digests enviados: 3` |

**Codificação conferida no fio.** O assunto acentuado viaja como RFC 2047 base64/utf-8 e decodifica
de volta íntegro:

```
Subject: =?utf-8?b?UG9ydGFsIEJpYWhmbG93IOKAlCBub3RpZmljYcOnw6Nv?=
      → "Portal Biahflow — notificação"
Content-Type: text/plain; charset="utf-8"   ·   Content-Transfer-Encoding: 8bit
```

Travessão e cedilha intactos. Era o principal risco da rodada — o backend de teste do Django guarda
objetos em memória e **nunca codifica nada**, então isso jamais tinha sido exercido.

### Três achados

**1. Convite e kickoff ignoram a flag `email`.** Com a flag **desligada**, converter uma
oportunidade e convidar alguém ainda produz e-mail. É intencional — os dois são transacionais, e um
portal cujo convite não sai não onboarda ninguém —, mas a FDD 010 descrevia a flag desligada como
"nada muda (só in-app)", o que se lia como "nenhum e-mail sai". A FDD foi corrigida.

> **Retificação (12/08/2026).** Este achado dizia que "o espelho de notificação, o digest, o
> lembrete de assinatura e a confirmação de agendamento respeitam a flag", e **são dois, não
> quatro**: só `notifications._email` e `digest.send_daily_digest` consultam
> `flags.is_enabled("email")`. `esign._mail_signer` e `booking._send_confirmation` **não** — foi
> medido no código, ao ligar o SMTP em HML. A rodada de 06/08 não podia ter visto isso: com o
> Mailpit de pé, tudo sai dos dois jeitos.
>
> A correção é do texto e não do código, e a razão está no rótulo da flag: ela é
> **"Notificações por e-mail e digest"**, não um interruptor geral de e-mail. O lembrete de
> assinatura está atrás da flag `esign`, que é a dele; e a confirmação de agendamento é
> transacional a um terceiro que acabou de marcar reunião — silenciá-la por uma flag de
> notificação interna deixaria o lead sem resposta. **Quatro dos seis pontos de envio ignoram a
> flag**, e quem quiser mudez total desliga os provedores, não esta chave.

**2. O convite ficava órfão quando o SMTP recusava.** Com o SMTP apontado para uma porta morta, o
`POST /invitations/` gravava a linha e devolvia **500** (`fail_silently=False`): sobrava um convite
válido que ninguém recebeu, o admin achava que falhara, e cada tentativa criava mais um. O convite
**é** o e-mail — quem recebe não tem outro caminho para o token. Agora grava e envia na mesma
transação e devolve **502**; a contagem não muda e nenhum órfão fica.

**3. A contagem do digest foi confirmada.** Com o SMTP morto, `Digests enviados: 0` e um aviso
nomeando cada destinatário. Antes da correção da FDD 024 diria `3`. Este era o único ponto da FDD
024 corrigido por análise que esta rodada conseguiu observar.

### `DEFAULT_FROM_EMAIL`

Todo ponto de envio passa `None` como remetente, então vale o `DEFAULT_FROM_EMAIL` — hoje
`noreply@biahflow.local`. **Em produção isto precisa mudar**: `.local` não é domínio entregável, e
provedores sérios recusam ou marcam como spam. Ver o bloco de produção do `.env.example`.

### Limpar

```bash
docker compose exec api uv run python manage.py shell -c \
  "from apps.core.models import AppSetting; AppSetting.objects.filter(key='email').delete()"
curl -s -X DELETE localhost:19025/api/v1/messages
```

Mais a remoção do cenário semeado (usuários, cliente, projeto, oportunidade de homologação).

---

## 2. IA (OpenAI) — homologado em 06/08/2026

**Variáveis:** `AI_ENABLED=true`, `OPENAI_API_KEY`. Opcionais: `AI_MODEL` (default `gpt-4o-mini`),
`AI_TIMEOUT_SECONDS` (30), `AI_DAILY_LIMIT` (50/dia/usuário).

**Custa por chamada.** A sonda não gera token — só recupera o modelo. Os exercícios usam o modelo
barato e respeitam o teto diário. **Esta rodada custou 7 115 tokens em 15 chamadas** de
`gpt-4o-mini` (3 738 de entrada, 3 377 de saída); converta pela tabela de preços vigente.

**Atenção — três armadilhas desta rodada:**

- **`docker compose exec` usa o `.env` de quando o container subiu.** Editar o `.env` com a stack
  no ar não muda nada; use `docker compose up -d` (recria) ou `-e VAR=valor` no próprio `exec`,
  que é o caminho usado abaixo para provocar falhas sem tocar no arquivo.
- **Logo depois de `docker compose restart api`, as primeiras chamadas podem falhar** (a rede do
  container ainda não está pronta) e, sem retentativa do SDK, isso agora aparece como 502. Dê uns
  segundos antes de medir. Foi o que produziu dois 502 espúrios aqui; 8 chamadas seguidas depois
  passaram todas.
- **`APIClient` manda `Host: testserver`**, que não está em `ALLOWED_HOSTS`: tudo responde 400
  antes de chegar na view. Use `APIClient(SERVER_NAME="localhost")` — vale para qualquer rodada
  que dirija a API de dentro do `manage.py shell`.

### Sondar antes de gastar

```bash
docker compose exec api uv run python manage.py check_integrations --all
# OK  Assistente de IA   modelo gpt-4o-mini acessível
```

Duas sondas **negativas**, ambas de graça, que são a melhor demonstração da tese da FDD 024:

```bash
docker compose exec -e AI_MODEL=gpt-4o-mini-inexistente api uv run python manage.py check_integrations
# FALHA ... "The model 'gpt-4o-mini-inexistente' does not exist" — exit 1
docker compose exec -e OPENAI_API_KEY=sk-invalida api uv run python manage.py check_integrations
# FALHA ... 401 "Incorrect API key provided: sk-inval***********" — exit 1
```

A primeira é a que importa: **chave válida, conta real, e a sonda reprova mesmo assim**. "A
credencial existe" e "a credencial funciona" são perguntas diferentes — aqui demonstrado, não
argumentado. (A OpenAI mascara a própria chave na mensagem de erro; nada vaza no log.)

### Ligar

```bash
docker compose exec api uv run python manage.py shell -c \
  "from apps.core.models import AppSetting; AppSetting.objects.update_or_create(key='ai', defaults={'enabled': True})"
```

### Semear

Um usuário `homologacao` dedicado (isola a cota diária e faz a limpeza ser um delete), cliente,
contato, oportunidade no **degrau gratuito** (`discovery_express` na época; a chave virou
`qualification_call` pela ADR 0048), projeto com uma tarefa **vencida**
e um marco a vencer, e uma reunião com transcrição curta. A transcrição **omite de propósito o
orçamento**, para checar a afirmação antivazamento do `ai.py`.

### O que foi observado

Todas as 12 superfícies responderam **200**, em português, e os quatro artefatos nasceram em
`draft` com conteúdo (FDD 016: proposta 1 596, contrato 3 197, discovery 2 087, assessment 1 798
caracteres).

| Superfície | `feature` | Tokens (in/out) | Observação |
| --- | --- | --- | --- |
| Resumo da oportunidade | `opportunity_summary` | 202 / 200 | ok |
| Proposta | `proposal` | 263 / 357 | **respeitou o nível gratuito** — não inventou cobrança |
| Contrato | `contract` | 268 / 854 | marcou `[lacuna]` onde faltava dado, como o prompt manda |
| Resumo do projeto | `project_summary` | 140 / 132 | ok |
| Próximos passos | `project_next_steps` | 185 / 364 | ok |
| Chat do projeto | `project_chat` | 162 / **3** | **"Não sei." — defeito, ver achado 1** |
| Discovery | `meeting_discovery` | 436 / 450 | ficou dentro da transcrição |
| Assessment | `meeting_assessment` | 432 / 380 | ficou dentro da transcrição |
| AI Score | `ai_score` | 517 / 178 | JSON parseado inteiro: maturidade 10, oportunidade 75, 4 dimensões |
| Agente comercial | `agent_comercial` | 200 / 140 | leu o funil corretamente |
| Agente de entrega | `agent_entrega` | 145 / 42 | **não sabe o que está atrasado — ver achado 4** |
| Agente financeiro | `agent_financeiro` | 154 / 117 | ROI correto |

**Antivazamento confere.** Nem Discovery, nem Assessment, nem o chat inventaram o orçamento que a
transcrição não trazia; perguntado direto, o chat respondeu "o contexto fornecido não contém
informações sobre o orçamento aprovado". **`_parse` aguenta o modelo real**: o AI Score veio como
JSON válido de primeira, e o clamp/dimensões entraram inteiros — não foi preciso `response_format`.

### Provocar as falhas

É o que faz a rodada valer: ver a correção agir, não só passar no teste.

```bash
docker compose exec -e AI_BASE_URL=http://127.0.0.1:9/v1 api uv run python manage.py shell < provocar.py
```

| | Provocação | Resultado |
| --- | --- | --- |
| F1 | endpoint morto + `POST /projects/<id>/summary/` | **502** em 2,2 s, mensagem em pt-BR, **0** `AiInteraction` novas |
| F2 | endpoint morto + `POST /meetings/<id>/ai-score/` | **502**; o projeto **não** ficou com AI Score pela metade |
| F3 | `-e AI_TIMEOUT_SECONDS=1` contra a OpenAI real | **502 em 5,5 s** — ver achado 2 |
| F4 | endpoint morto + `qualify_lead` | **não levantou**; lead gravado, `fit=''`, triagem manual |
| F5 | endpoint morto + `send_daily_digest` | **`Digests enviados: 2`**, em texto estruturado, com os itens atrasados no corpo |
| F6 | `-e AI_DAILY_LIMIT=0` | **429** ("Limite diário de uso de IA atingido") |
| F7 | `-e AI_ENABLED=false` | **503** ("Recurso de IA está desativado") |

F4 e F5 são o centro de gravidade: os dois estavam corrigidos **por análise** e ninguém tinha visto
agir. F6 e F7 provam que os três status seguem distinguíveis — 503 é "um admin desligou", 429 é "a
sua cota acabou", 502 é "o fornecedor caiu"; colapsar quaisquer dois faria quem opera depurar a
coisa errada.

### Quatro achados

**1. O assistente do projeto respondia "Não sei." a pergunta que o contexto respondia.** Perguntado
qual o maior risco de um projeto com tarefa vencida há três dias, o `project_chat` gastou **três
tokens** dizendo que não sabia — enquanto o `project_summary`, com o **mesmo contexto**, apontava o
risco corretamente. Duas causas, ambas corrigidas e reconferidas contra o modelo real:

- **O contexto não dizia que dia é hoje.** `build_project_context` mandava uma lista de prazos sem
  âncora, então "está atrasado?" era literalmente indecidível. Vale para resumo, próximos passos,
  chat e agentes.
- **O texto de sistema proibia raciocinar.** "Use somente o contexto; se a informação não estiver
  ali, diga que não sabe" foi lido como "só repita o que está escrito", e "risco" não é um campo.
  Agora manda usar o contexto como **fonte de fatos** e raciocinar sobre ele. Depois da correção, a
  mesma pergunta rende a resposta certa, e "qual o orçamento aprovado?" segue recusada — o
  antivazamento não afrouxou.

**2. `AI_TIMEOUT_SECONDS` não era o teto que prometia.** Com o teto em 1 s, a resposta levou
**5,5 s**: o SDK da OpenAI tenta 3 vezes por padrão, então o teto real era `timeout × 3` mais
backoff — com o default de 30 s, mais de um minuto e meio segurando um worker do gunicorn por causa
de um formulário público. Agora `max_retries=0`, e o número da variável é o número de verdade. A
retentativa não se perdeu, mudou de dono: depois desta rodada todo ponto de chamada ou degrada
(digest, qualificação) ou devolve 502 dizendo que vale repetir.

**3. O digest cobrava a cota de IA de quem nem pediu.** Ele auditava com `user=user`, e
`within_daily_limit` conta exatamente essas linhas — então o job das 07:30 tirava 1 das 50 chamadas
diárias de cada pessoa. E não consultava o limite: era isento dele e cobrava dele ao mesmo tempo.
Agora `daily_digest` fica fora da conta.

**4. O agente de Entrega não sabe o que está atrasado.** Perguntado "o que está atrasado?", ele
respondeu que não tinha os detalhes — e estava **certo**: `build_delivery_context` manda só
`nome: risco médio (escore 30) — Itens atrasados; Ritmo abaixo do esperado`, um resumo de resumos,
sem os itens. Não foi corrigido nesta rodada: o contexto do agente é um dos agregadores recortados
à mão pela ADR 0010, e ampliá-lo pede revisar o escopo com cuidado próprio. Fica registrado na
FDD 024.

### Limpar

```bash
docker compose exec api uv run python manage.py shell -c \
  "from apps.core.models import AppSetting; AppSetting.objects.filter(key__in=['ai','email']).delete()"
curl -s -X DELETE localhost:19025/api/v1/messages
docker compose exec api uv run python manage.py check_integrations --all   # confere o estado original
```

Mais o cenário semeado. **Apagamento duro, não arquivamento** — a regra de soft delete do
`CLAUDE.md` protege dado de negócio, e cenário de homologação é a exceção explícita: arquivado, ele
seguiria aparecendo em `/clients/overview/`, `/analytics/` e nas métricas de IA para sempre.

## 3. Google (Drive + Calendário) — homologado em 06/08/2026

> **A primeira tentativa desta rodada foi bloqueada, e mudou o desenho.** Não foi possível criar a
> chave de conta de serviço: a organização aplica
> `iam.managed.disableServiceAccountKeyCreation`. As duas únicas variáveis que o código sabia ler
> eram exatamente o artefato proibido — ou seja, o desenho não era subótimo, era **inconstruível**
> aqui, e é quase certamente por isso que esta integração nunca foi homologada. A autenticação foi
> trocada (ADR 0016) antes de a rodada seguir.

**Variáveis:** `GOOGLE_DRIVE_ROOT_FOLDER_ID`, `GOOGLE_CALENDAR_ID` e o modo de auth
(`GOOGLE_AUTH_MODE`, ADR 0016):

- **`adc`** (default) — em container/pod, Workload Identity: **nenhum segredo no ambiente**.
  Localmente, `gcloud auth application-default login`. Um arquivo de Workload Identity Federation
  entra por `GOOGLE_APPLICATION_CREDENTIALS`.
- **`oauth`** — `GOOGLE_OAUTH_CLIENT_ID`, `_CLIENT_SECRET`, `_REFRESH_TOKEN`. Necessário para
  **convidar participante** em evento, que exige agir como uma pessoa.
  **Armadilha:** com o app em "Testing" no Google Cloud, o refresh token expira em **7 dias** —
  precisa estar "In production" (com tipo *Interno*, num Workspace, isso não se aplica).

> **O atalho do `gcloud` não funciona para estes escopos.** `gcloud auth application-default login
> --scopes=...drive,...calendar` leva **"Este app está bloqueado"**: o cliente OAuth do próprio
> gcloud não tem permissão para pedir escopos sensíveis. É por isso que o modo `oauth` com client
> **próprio** é o caminho, e não uma alternativa.

### Preparar o projeto no Google Cloud

Quatro passos, na ordem. Os três primeiros são no console; pular qualquer um derruba a rodada mais
adiante, e nem sempre com uma mensagem que aponta para cá.

**1. Ativar as duas APIs.** No projeto, *APIs e serviços → Biblioteca*, ative:

- **Google Drive API** — `https://console.cloud.google.com/apis/api/drive.googleapis.com/overview?project=<PROJETO>`
- **Google Calendar API** — `https://console.cloud.google.com/apis/api/calendar-json.googleapis.com/overview?project=<PROJETO>`

São **duas** ativações separadas, e é fácil ativar uma e esquecer a outra. Sem elas o Google
responde **`403 accessNotConfigured`** com a credencial perfeitamente válida — o erro parece
permissão e não é. A propagação leva alguns minutos.

**2. Tela de permissão OAuth.** *APIs e serviços → Tela de permissão OAuth*:

- Tipo de usuário: **Interno**, se a conta for Workspace. Vale a pena pelos dois lados — evita a
  verificação do app e **elimina a expiração de 7 dias** do refresh token que o modo "Testing"
  impõe.
- Declare os escopos que o portal usa, senão o consentimento é recusado:

  ```
  https://www.googleapis.com/auth/drive
  https://www.googleapis.com/auth/calendar
  ```

**3. Criar o client OAuth.** *APIs e serviços → Credenciais → Criar credenciais → ID do cliente
OAuth*:

- Tipo de aplicativo: **App para computador**. É o tipo certo aqui por um motivo prático: o Google
  aceita `http://localhost` **em qualquer porta** para esse tipo, então **não é preciso cadastrar
  URI de redirecionamento nenhuma** — e é `http://localhost:8765` que o comando do passo 4 usa. Se
  você escolher *Aplicativo da Web*, aí sim precisa cadastrar `http://localhost:8765` exatamente.
- Saem dali o **`GOOGLE_OAUTH_CLIENT_ID`** (`<numero>-<hash>.apps.googleusercontent.com`) e o
  **`GOOGLE_OAUTH_CLIENT_SECRET`** (`GOCSPX-…`).
- Para *App para computador*, o Google trata o secret como **não confidencial por natureza** — ele
  vive na máquina de quem instala. Ainda assim, se um dia esse client virar *Aplicativo da Web*,
  rotacione o segredo antes, porque aí ele passa a ser secreto de verdade.

**4. Dar acesso ao recurso.** A identidade que consentiu precisa enxergar o que vai usar:

- **Drive**: acesso de escrita à pasta raiz. Num **Shared Drive** (id começa com `0A`), como
  *Gerente de conteúdo* — é a opção preferível, porque o dono passa a ser a organização e não a
  pessoa, que era a maior ressalva do modo `oauth` na ADR 0016.
- **Calendário**: uma agenda **dedicada** à homologação. A rodada cria eventos de verdade.

**Onde achar os dois ids** que faltam no `.env`:

| Variável | Onde |
| --- | --- |
| `GOOGLE_DRIVE_ROOT_FOLDER_ID` | na URL da pasta: `…/folders/<ID>?…`. **Pode colar a URL inteira** — o código extrai o id (achado desta rodada; ver adiante). |
| `GOOGLE_CALENDAR_ID` | Google Calendar → *Configurações* → a agenda → *Integrar agenda* → **ID da agenda**. Numa agenda dedicada tem a forma `c_…@group.calendar.google.com`. |

**Obtendo o refresh token** — comando dedicado, rodado **no host** (precisa de navegador):

```bash
cd backend && uv run python manage.py google_oauth_setup \
  --client-id <id> --client-secret <segredo>
```

Ele sobe um servidor efêmero em `http://localhost:8765`, abre o consentimento, troca o código e
**grava o token direto no `.env`** — nunca o imprime, porque segredo na tela acaba em screenshot e
em histórico de shell. Se o client for do tipo **App para computador**, não é preciso cadastrar
URI de redirect nenhuma: o Google aceita `http://localhost` em qualquer porta. Se for **Aplicativo
da Web**, cadastre exatamente `http://localhost:8765`.

Se o Google não devolver refresh token, é consentimento reaproveitado: revogue em
<https://myaccount.google.com/permissions> e repita (o comando já pede `prompt=consent`).

A mesma identidade serve às duas flags, mas os escopos são diferentes — por isso as sondas são
separadas: conceder Drive e esquecer Calendar é o erro comum, e ele passaria batido.

**Cria artefato na sua conta.** Prefixe tudo com `[homologação]`, use pasta e agenda dedicadas, e
remova ao fim. Esta foi a primeira rodada que deixou rastro fora da máquina.

### Habilitar as APIs no projeto

Passo que não é credencial e derruba tudo mesmo assim: no projeto do Google Cloud, **ative a Google
Drive API e a Google Calendar API**. Sem isso o Google devolve `403 accessNotConfigured` — com a
credencial perfeitamente válida. A sonda entrega o link do conserto junto com o erro.

### O que foi observado

| Superfície | Gatilho | Resultado |
| --- | --- | --- |
| Sonda do Drive | `check_integrations` | **OK** — `pasta raiz 0AAu…acessível` |
| Sonda do Calendário | `check_integrations` | **OK** — `calendário 'Biahflow - HML' acessível` |
| Árvore PARA | `convert-to-project` | **201** — pasta do cliente e do projeto criadas no Shared Drive |
| Upload | `POST /documents/` | **201** — `drive_file_id` e link preenchidos |
| Download | `GET /documents/<id>/download/` | **200**, 920 bytes, **byte a byte idêntico** (SHA-256) |
| Evento de dia inteiro | `add-to-calendar` | **200** com link — intervalo `2026-08-10` a `2026-08-11` |
| Free/busy | `calendar_sync.freebusy` | **OK** — leu a agenda |
| Slots | `booking.available_slots` | **79** nos 14 dias seguintes |
| Reserva com convite | `booking.book` | evento criado **e o convite ao participante aceito** |
| Sincronia inbound | evento `#proj-<id>` + `sync_calendar` | criadas 1, ignoradas 1 |
| Idempotência | repetir a sincronia | **criadas 0** — não duplica |

**As três correções da FDD 024 feitas por análise foram confirmadas.** A que mais importa é o
`end.date` exclusivo: o `add-to-calendar` respondeu 200 com link, e antes da correção ele falhava
em **100%** das tentativas desde que existe. O free/busy leu a agenda de verdade, e o upload/
download atravessaram inteiros.

### Provocar as falhas

Um refresh token inválido por `-e`, sem tocar no `.env`:

```bash
docker compose exec -e GOOGLE_OAUTH_REFRESH_TOKEN=invalido api uv run python manage.py shell < provocar.py
```

| | Provocação | Resultado |
| --- | --- | --- |
| F1 | download de documento | **502** — "O Google Drive não respondeu agora." |
| F2 | `add-to-calendar` | **502** — "O Google Calendar não respondeu agora." |
| F3 | sincronia manual | **502** |
| F4 | `booking.book` | **não levantou**: reserva criada, evento vazio, **dono avisado com a ressalva** de que a reunião não entrou na agenda |

F4 é a correção mais importante da varredura vista agindo: antes, isso era 500 no endpoint público
com uma reserva órfã bloqueando o horário.

### Dois achados

**1. O `forbiddenForServiceAccounts` não aconteceu — e essa é a notícia.** A FDD 024 previa que o
convite ao participante seria recusado, e o runbook dizia "já se sabe que vai falhar". Não falhou:
com a **credencial de usuário** da ADR 0016, o convite foi aceito na primeira tentativa. A troca de
autenticação, que nasceu de uma política que bloqueava a chave, resolveu de carona o defeito
funcional que se esperava contornar. A degradação do `booking.book` continua valendo — mas passou
de caminho cotidiano a **rede de segurança**.

**2. A tese da FDD 024 se provou três vezes nesta rodada, por três motivos diferentes.** A
credencial pode estar *ausente* (o refresh token vazio, que o `configured()` nomeou); pode estar
*presente com o valor errado* (a URL da pasta colada no lugar do id, que o `configured()` **não**
pega, porque a variável está preenchida); e pode estar *presente e correta com a integração morta
mesmo assim* (a API não habilitada no projeto, `403 accessNotConfigured`). Só a terceira é
inalcançável por qualquer verificação de ambiente — e as três só apareceram porque alguém sondou.

### Limpar

Apagar os eventos da agenda de homologação e a **pasta do cliente** no Drive (ela leva junto a do
projeto e os arquivos), mais o cenário do banco — apagamento duro, pelo motivo já registrado.

**Confira, não presuma.** A conferência aqui achou divergência entre o número de eventos que a
limpeza reportou e o que a rodada tinha criado; listar a agenda e a raiz do Drive depois mostrou
**zero** dos dois, mas o passo de conferir é que deu essa certeza.

## 4. Assinatura eletrônica — homologada em 06/08/2026

**Variáveis:** `ESIGN_ENABLED=true`, `ESIGN_PROVIDER` (`autentique`; o `clicksign` segue **sem**
homologação), `ESIGN_API_TOKEN`, `ESIGN_WEBHOOK_SECRET` e **`ESIGN_SANDBOX=true`**.

> **`request-signature` é a única ação de todo este runbook que sai da máquina e chega a uma
> pessoa** — mas só quando `ESIGN_DELIVERY=email`, porque aí quem convida é o **fornecedor**. Os
> e-mails do próprio portal caem no Mailpit e não escapam.
>
> **Rode com `ESIGN_DELIVERY=link`** (por `-e`, sem tocar no `.env`): o adaptador manda
> `DELIVERY_METHOD_LINK`, o Autentique **não** notifica ninguém, e o convite passa a ser nosso —
> ou seja, vai para o Mailpit. Exercita a API real de ponta a ponta sem alcançar pessoa alguma.
> Foi assim que esta rodada correu, com signatário `@exemplo.test`.

### Sondar

```bash
docker compose exec api uv run python manage.py check_integrations --all
# OK  Assinatura eletrônica   conta <e-mail da conta> acessível
```

A sonda **nasceu nesta rodada**. O gancho existia desde a FDD 024
(`integrations._probe_esign` procura um `ping` no adaptador), mas nenhum fornecedor o
implementava — e o e-sign era a única integração configurada que respondia "sem sonda disponível".
A query `me` do Autentique serve: valida o token, é só leitura e não cria documento.

### O que foi observado

| Superfície | Gatilho | Resultado |
| --- | --- | --- |
| Sonda | `check_integrations` | **OK** — a conta do token |
| Pedido de assinatura | `POST /documents/<id>/request-signature/` | **201** com `provider_ref`, `document_ref` e `sign_url` reais |
| Convite ao signatário | entrega por link | e-mail no Mailpit |
| Lembrete de pendentes | `remind-signature` | **1** lembrete |
| Webhook com HMAC válido | `POST /esign/webhook/` | **200**, assinatura fecha **sozinha** (`signed`) |
| Idempotência | reentregar o mesmo evento | **200**, status não muda |
| Webhook com HMAC errado | assinatura falsa | **401** — recusado |
| Fornecedor recusando | token inválido | **502**, e **nenhuma** solicitação gravada |

Com isso o laço inteiro da ADR 0007 está exercitado contra o fornecedor real: pedido → convite →
lembrete → webhook assinado → artefato de contrato fechado.

### Dois achados

**1. A solicitação fantasma.** `_http_raw` engole a falha do fornecedor e devolve `None` — de
propósito, o portal não pode cair porque o Autentique caiu. O problema era o degrau seguinte:
`None` virava um `SignatureRef` vazio, **indistinguível de sucesso**, e a view gravava a
`SignatureRequest` e respondia **201**. Sobrava uma assinatura "pendente" que ninguém assinaria,
que o webhook **nunca** poderia fechar (sem `provider_ref` não há o que casar), e sobre a qual o
lembrete ainda cobraria uma pessoa de verdade — sem link, porque `sign_url` também vinha vazio.
É a terceira encarnação do padrão das rodadas 1 e 3, e a pior: o convite órfão ao menos devolvia
500, a reserva órfã avisava o dono, esta respondia **201 Created**. Agora é **502** e nada é
gravado. Sem fornecedor configurado nada muda: o `NullProvider` registra a intenção, e o
`mark-signed` manual segue sendo o caminho previsto.

**2. A primeira versão da sonda deu 401 com um token válido.** Ela usava `_http`, que é o helper
do **Clicksign** — ele leva o token na URL e por isso não manda header de autorização. Só apareceu
porque a sonda foi rodada contra o fornecedor de verdade; contra um dublê, teria passado.

### Limpar

```bash
docker compose exec api uv run python manage.py shell -c \
  "from apps.core.models import AppSetting; AppSetting.objects.filter(key='esign').delete()"
curl -s -X DELETE localhost:19025/api/v1/messages
```

O documento criado no sandbox **também sai**: a mutation `deleteDocument(id:)` do Autentique
aceita o `document_ref` guardado na `SignatureRequest`. Sandbox não é motivo para deixar lixo.

---

## 5. Pagamentos (Stripe) — **pendente**

**Esta seção é roteiro, não relato.** As quatro rodadas acima aconteceram; esta ainda não. O
adaptador do Stripe foi escrito seguindo o molde já provado do e-sign, mas nenhuma linha dele falou
com o fornecedor de verdade. As quatro rodadas anteriores acharam defeito — **cada uma** —, e três
acharam a mesma classe: linha gravada como se o fornecedor tivesse aceitado, sem ele ter aceitado.
Não há razão para supor que esta seja diferente.

**Variáveis:** `PAYMENTS_ENABLED=true`, `PAYMENTS_PROVIDER=stripe`, `PAYMENTS_API_TOKEN`
(**`sk_test_…`**, nunca a chave de produção) e `PAYMENTS_WEBHOOK_SECRET` (`whsec_…`).

> **Nada aqui alcança pessoa nenhuma** se o cliente de teste for criado com e-mail `@exemplo.test`
> e o Stripe estiver em modo de teste — ele não envia e-mail de fatura em `sk_test_`. Confirme o
> modo pela sonda antes de qualquer coisa: ela diz `modo teste` ou `modo produção`, e essa é
> metade da razão de ela existir.

### Sondar antes de emitir

```bash
docker compose exec api uv run python manage.py check_integrations --all
# OK  Gateway de pagamento   chave válida, modo teste
```

`GET /v1/balance`: leitura pura, sem custo, sem efeito colateral — a regra da FDD 024. Se disser
`modo produção`, **pare**: a chave está errada e a próxima chamada cria cobrança de verdade.

### Ligar

```bash
docker compose exec api uv run python manage.py shell -c \
  "from apps.core import flags; print(flags.status('payments'))"
# {'key': 'payments', 'enabled': True, 'configured': True, 'missing': [], ...}
```

Sem `PAYMENTS_PROVIDER`, `missing` vem **vazio** e a integração fica ligada: é o `NullProvider`, e
é modo previsto. Com `stripe` nomeado e sem token, `missing` deve listar
`PAYMENTS_API_TOKEN`/`PAYMENTS_WEBHOOK_SECRET` — confira isso antes de preencher, porque é a única
forma de saber que a exigência dinâmica está funcionando.

### O que exercitar — pela API, não pelo olho

| Superfície | Gatilho | O que confirmar |
| --- | --- | --- |
| Emissão | `POST /api/v1/invoices/{id}/issue/` | volta 200 com `number`, `external_reference` (`in_…`) e `payment_url`; a fatura aparece no painel do Stripe como **finalizada** |
| Cliente reusado | emitir **duas** faturas do mesmo cliente | o segundo `issue` **não** cria outro `Customer`; `Client.payment_customer_ref` é o mesmo |
| Centavos | fatura de `R$ 18,99` | o Stripe mostra **1899**, não 1898 |
| Fatura já vencida | `due_date` no passado | o `days_until_due` vai como `0` e o Stripe aceita (negativo daria 400) |
| Baixa por webhook | pagar pela `hosted_invoice_url` com o cartão de teste `4242 4242 4242 4242` | a fatura vira `paga` sozinha, **com a data do provedor** |
| Idempotência | reenviar o evento pelo painel ("Resend") | `paid_at` **não** muda |
| Dois eventos | `invoice.paid` + `invoice.payment_succeeded` | uma baixa só |
| Cancelamento no fornecedor | "Void invoice" no painel | a fatura vira `cancelada` aqui, com o motivo |
| Duplo clique | `issue` duas vezes seguidas | 409 na segunda; e no Stripe **uma** fatura, pelo `Idempotency-Key` |

### Provocar as falhas

```bash
# 1. Fornecedor mudo: token válido, base inalcançável. A emissão tem de dar 502 e a fatura
#    continuar em RASCUNHO, sem número e sem carimbo. Se ela ficar "emitida" sem link, é a
#    quarta encarnação do defeito das rodadas 1, 3 e 4.
docker compose exec -e PAYMENTS_API_BASE=https://127.0.0.1:9 api \
  uv run python manage.py shell -c "..."

# 2. HMAC falso: mesmo corpo, outro segredo → 401 e nada muda.
# 3. Carimbo velho: assinatura correta com `t` de uma hora atrás → 401 (a tolerância é 300s).
# 4. Rotação de segredo: header com dois `v1`, um velho e um novo → **passa**.
```

Os itens 2, 3 e 4 já têm regressão automatizada
(`tests/regression/test_webhook_de_pagamento_e_idempotente.py`); rodá-los contra o painel confirma
que o formato real do header bate com o que o teste supõe — que é exatamente o tipo de coisa em que
o dublê mente.

### Limpar

```bash
docker compose exec api uv run python manage.py shell -c \
  "from apps.core.models import AppSetting; AppSetting.objects.filter(key='payments').delete()"
```

No painel do Stripe em modo de teste, apague o `Customer` criado — os `invoiceitems` e as faturas
saem junto. Modo de teste não é motivo para deixar lixo, e um `Customer` órfão com
`metadata[client_id]` apontando para um id que não existe mais confunde a próxima rodada.

---

## 6. Base de conhecimento interna — homologada em 07/08/2026

**Variáveis:** `AI_ENABLED=true`, `OPENAI_API_KEY` e `AI_EMBEDDING_MODEL`
(default `text-embedding-3-small`). Mesma credencial do assistente — não há flag própria.

**Custo da rodada:** ~US$ 0,003. O corpus inteiro são 421 trechos; indexá-lo é uma vez, e cada
pergunta custa fração de centavo.

### Sondar antes de gastar

```bash
docker compose exec api uv run python manage.py check_integrations --all
# OK  Assistente de IA   modelos gpt-4o-mini e text-embedding-3-small acessíveis
```

A sonda passou a conferir **os dois** modelos nesta rodada. Uma conta com acesso ao chat e sem
acesso a embeddings responde tudo normalmente até alguém rodar a ingestão — e aí a falha aparece
como erro de fornecedor, longe da causa.

### Indexar

```bash
docker compose exec api uv run python manage.py ingest_knowledge
# peças: 66 (66 novas) · trechos: 421 · embeddadas: 421 · arquivadas: 0
```

Reingestão é idempotente: só reembeda o que mudou de hash, de modelo, ou está sem vetor.

### O que foi medido — e é o achado principal

Similaridade do melhor trecho, por classe de pergunta:

| Classe | Valores medidos | Faixa |
| --- | --- | --- |
| Metodologia ("como restaurar o backup?") | 51 56 58 61 62 69 | **50,6 – 68,9%** |
| Operacional ("o que está atrasado?") | 47 47 51 52 53 56 | **47,0 – 56,4%** |
| Fora do corpus ("política de férias", "CNPJ", "copa do mundo") | 22 25 37 49 | 22,5 – 48,5% |

**As duas primeiras faixas se sobrepõem**, e isso derrubou o desenho: não existe limiar que separe
"perguntar sobre o método" de "perguntar sobre os dados". Não é ruído de medida — o corpus
*descreve o domínio*, então uma pergunta sobre projeto atrasado se parece com o texto de uma FDD
sobre projeto atrasado.

### Dois achados

**1. O limiar não pode decidir se a citação é obrigatória.** Estava planejado um piso de 30%: acima
dele, material injetado e citação exigida. Com os números acima, "o que está atrasado?" (52,5%)
passaria do piso, cairia na regra estrita, e uma **resposta operacional correta seria substituída
por "não encontrei isso no material"**. Agora quem declara o regime é o modelo (`FONTE: [K1]` ou
`FONTE: dados da área`), e o limiar — recalibrado para 45% — só evita gastar token com material
fora do assunto. Virou a **ADR 0023**.

**2. A citação vinha só na linha de declaração, e o código a descartava.** O prompt manda terminar
com `FONTE: [K1]`, e o `gpt-4o-mini` faz exatamente isso — cita **só** ali. A primeira versão
removia essa linha *antes* de procurar marcador, então nada resolvia e a lacuna **substituía uma
resposta correta**, com os comandos exatos deste runbook. Nenhum dublê acharia: ele citaria onde o
teste mandasse. É o achado mais concreto a favor de rodar contra o fornecedor de verdade.

### O que foi observado, depois das correções

| Pergunta | Ancorou? | Resultado |
| --- | --- | --- |
| "qual o procedimento de restauração do backup?" | sim (61%) | resposta correta, citando `[K1] Runbook — backup e restauração` |
| "qual é a política de férias da empresa?" | **não** (abaixo do piso) | o modelo declina honestamente; nada é inventado |
| "o que está atrasado nos projetos?" | sim (53%) | o modelo declara `FONTE: dados da área` e a resposta operacional **passa intacta** |

### Limpar

```bash
docker compose exec api uv run python manage.py shell -c \
  "from apps.core.models import KnowledgeChunk; KnowledgeChunk.objects.update(embedding=None)"
```

Zerar os vetores basta: as peças e a curadoria (dono, carimbo de verificação) **devem** sobreviver,
e a próxima ingestão reembeda o que faltar.
