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

## 2. IA (OpenAI) — pendente

**Variáveis:** `AI_ENABLED=true`, `OPENAI_API_KEY`. Opcionais: `AI_MODEL` (default `gpt-4o-mini`),
`AI_TIMEOUT_SECONDS` (30), `AI_DAILY_LIMIT` (50/dia/usuário).

**Custa por chamada.** A sonda não gera token — só recupera o modelo. Os exercícios usam o modelo
barato e respeitam o teto diário.

Superfície a exercitar: resumo e próximos passos, proposta, contrato, Discovery/Assessment sobre
transcrição, agentes por área, AI Score, qualificação de lead e o digest redigido por IA.

**Ponto de atenção:** `qualify_lead` roda dentro do POST público do formulário. Ganhou `try/except`
e timeout na FDD 024, mas isso ainda não foi observado contra a OpenAI de verdade.

## 3. Google (Drive + Calendário) — pendente

**Variáveis:** `GOOGLE_SERVICE_ACCOUNT_INFO` (JSON inline) **ou** `GOOGLE_SERVICE_ACCOUNT_FILE`,
mais `GOOGLE_DRIVE_ROOT_FOLDER_ID` e `GOOGLE_CALENDAR_ID`. A mesma credencial serve às duas flags,
mas os escopos são diferentes — por isso as sondas são separadas: conceder Drive e esquecer
Calendar é o erro comum, e ele passaria batido.

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
