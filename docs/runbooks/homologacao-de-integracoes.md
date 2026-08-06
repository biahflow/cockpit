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
oportunidade e convidar alguém ainda produz e-mail; só o espelho de notificação, o digest, o
lembrete de assinatura e a confirmação de agendamento respeitam a flag. É intencional — os dois são
transacionais, e um portal cujo convite não sai não onboarda ninguém —, mas a FDD 010 descrevia a
flag desligada como "nada muda (só in-app)", o que se lia como "nenhum e-mail sai". A FDD foi
corrigida.

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
contato, oportunidade no **nível gratuito** `discovery_express`, projeto com uma tarefa **vencida**
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

## 3. Google (Drive + Calendário) — pendente

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
remova ao fim.

Três correções da FDD 024 esperam confirmação aqui, todas feitas por análise:

- evento de dia inteiro com `end.date` exclusivo (antes a API recusava **toda** tentativa);
- free/busy que falha fechado quando a agenda é inacessível;
- upload no Drive devolvendo 502 em vez de 500 mudo.

**Já se sabe que vai falhar:** `create_timed_event` convida participante, e uma conta de serviço não
convida sem delegação em todo o domínio — o Google responde `forbiddenForServiceAccounts`. É
configuração do Workspace, não código.

## 4. Assinatura eletrônica — pendente

**Variáveis:** `ESIGN_ENABLED=true`, `ESIGN_PROVIDER` (`autentique` homologado na ADR 0007;
`clicksign` **sem** homologação), `ESIGN_API_TOKEN`, `ESIGN_WEBHOOK_SECRET`, e
**`ESIGN_SANDBOX=true`**.

> **`request-signature` manda e-mail a um signatário de verdade** — é a única ação de todo este
> runbook que sai da máquina e chega a uma pessoa. Use sandbox, um endereço **seu**, e nunca um
> contato real de cliente.

Exercitar: pedido de assinatura, lembrete de pendentes, e o webhook de status com HMAC fechando o
artefato sozinho.
