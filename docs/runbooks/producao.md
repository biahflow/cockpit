# Runbook — produção (domínio, HTTPS e segredos)

Primeira subida e operação do portal em produção (FDD 019, ADR 0011). O que é ativação de
integração está em `docs/operacao.md`; desenvolvimento e release, em
`desenvolvimento-e-release.md`.

O portal **se recusa a subir** com configuração insegura: o entrypoint da imagem roda
`manage.py check --deploy --fail-level WARNING --tag security` antes do gunicorn, e a mensagem de
erro nomeia a variável que falta. Errar aqui derruba o deploy em vez de silenciosamente rodar em
SQLite efêmero ou triplicar os tetos de requisição.

## Topologia

```
internet → [terminador de TLS: proxy do provedor]     ← HTTPS acaba aqui
              ↓  http, com X-Forwarded-Proto: https
           [web]  nginx: serve o SPA, faz proxy de /api, /admin, /static
              ↓
           [api]  gunicorn (3 workers) + WhiteNoise
              ↓
           [db] postgres      [redis] cache do teto de requisição
```

O `docker-compose.prod.yml` sobe `web`, `api`, `db`, `redis`, o sidecar `backup` (FDD 021) e o
`scheduler` (FDD 023).
**Não** sobe o terminador de TLS: é o
proxy do provedor, ou um nginx/Caddy seu na frente. `db` e `redis` não publicam porta, e a `api`
também não — o único caminho até o gunicorn é o nginx, e é isso que torna seguro confiar no
`X-Forwarded-Proto`.

## 1. Antes de subir

- [ ] **Domínio** apontando (registro A/AAAA ou CNAME) para o host.
- [ ] **TLS** terminado na borda, com renovação automática. O proxy precisa **sobrescrever**
      `X-Forwarded-Proto` — se ele apenas repassar o que o cliente mandou, não ligue
      `TRUST_X_FORWARDED_PROTO` (ver ADR 0011).
- [ ] **Segredo da instalação**, no cofre da plataforma (nunca no repositório):
      ```bash
      python -c 'import secrets; print(secrets.token_urlsafe(64))'
      ```
- [ ] **Postgres** provisionado. O backup do portal sobe junto com a stack (FDD 021) — o que falta
      decidir aqui é o **offsite**: um bucket compatível com S3 e uma credencial só dele, porque
      cópia no mesmo host morre com o host. Ver `backup-e-restauracao.md`.
- [ ] **SMTP** real. Deixou de ser opcional: além do convite de usuário e do lembrete de
      assinatura, as **notificações e o digest diário nascem ligados** (ADR 0018), e o default
      `localhost:1025` é o Mailpit do compose — fora do dev, lugar nenhum. Para subir sem e-mail,
      `EMAIL_NOTIFICATIONS_ENABLED=false` explícito.

## 2. Variáveis obrigatórias

Do bloco "Produção" do `.env.example`. As quatro primeiras são recusadas pelo check se faltarem:

| Variável | Por que o deploy recusa sem ela |
| --- | --- |
| `DJANGO_SECRET_KEY` | sem ela vale o segredo que está no repositório |
| `DATABASE_URL` | sem ela o portal sobe em SQLite: atende, migra e perde tudo no restart |
| `REDIS_URL` | sem ela o teto de requisição vale 3× (um balde por worker) |
| `DJANGO_ALLOWED_HOSTS` | só localhost significa que a variável não foi definida |
| `DJANGO_CSRF_TRUSTED_ORIGINS` | origem `http://` é o default de desenvolvimento |

Mais: `DJANGO_DEBUG=false`, `FRONTEND_ORIGIN`, `DJANGO_MEDIA_ROOT`, o SMTP (`EMAIL_HOST`,
`EMAIL_PORT`, `EMAIL_USE_TLS`, `EMAIL_HOST_USER`, `EMAIL_HOST_PASSWORD`, `DEFAULT_FROM_EMAIL`) e,
se houver proxy próprio na frente do `web`, ajustar `NUM_PROXIES`.

**Duas integrações nascem ligadas** (ADR 0018) e merecem uma decisão explícita antes da subida:

| Flag | Se você não fizer nada | Para desligar |
| --- | --- | --- |
| `email` | notificações e digest diário saem pelo SMTP configurado | `EMAIL_NOTIFICATIONS_ENABLED=false` |
| `esign` | sem `ESIGN_PROVIDER`, roda em registro local ("Marcar assinado" manual) — não chama nem cobra ninguém | `ESIGN_ENABLED=false` |

Rode `manage.py check_integrations --all` antes de abrir para os usuários: ele pergunta a cada
provedor se a credencial funciona, o que a flag não sabe responder (FDD 024).

## 3. Primeira subida

```bash
cp .env.example .env          # preencha o bloco "Produção"
docker compose -f docker-compose.prod.yml up -d --build

# A migração é um serviço próprio e roda antes da API; confira que terminou bem:
docker compose -f docker-compose.prod.yml logs api-migrate

docker compose -f docker-compose.prod.yml ps          # o api precisa ficar "healthy" (sonda /readyz)
docker compose -f docker-compose.prod.yml exec api python manage.py createsuperuser
```

O `createsuperuser` agora exige senha forte: os quatro validadores estão ligados, então senha
numérica ou parecida com o nome de usuário é recusada.

Esse usuário entra como **administrador do portal**, com o menu completo — o comando não pergunta
papel, e `User.role` fica no default `delivery`, mas o que decide é o `is_superuser`, que a API e a
tela leem pelo mesmo campo `is_admin` (FDD 017). Os demais papéis saem de **Equipe → convidar**.

## 4. Smoke test

```bash
curl -I http://SEU-DOMINIO/                       # 301 para https://
curl -I https://SEU-DOMINIO/                      # 200, SPA
curl -sI https://SEU-DOMINIO/api/v1/auth/csrf/ | grep -i strict-transport
curl -s  https://SEU-DOMINIO/healthz              # {"status": "ok"}
curl -s  https://SEU-DOMINIO/readyz               # checks de banco e cache (FDD 020)
```

No navegador: login → **Configurações** abre → `/admin/` abre **com CSS** (prova o
`collectstatic`/WhiteNoise) → subir um documento em um projeto e baixá-lo. Depois
`docker compose -f docker-compose.prod.yml down && up -d`: o documento tem de continuar lá (é o
volume `media_data`).

### O agendador (FDD 023)

Dois containers rodam sozinhos, sem atender requisição: o `backup` (FDD 021) e o `scheduler`.
O segundo é quem dispara o digest diário, a sincronia de calendário e a conferência de backup —
até a FDD 023 os três dependiam de um cron que ninguém tinha montado.

```bash
docker compose -f docker-compose.prod.yml logs scheduler
```

**Deve acontecer:** uma linha `scheduler: no ar (tique de 60s)` seguida da tabela de horários, e a
sincronia de calendário no primeiro tique. O digest e a conferência de backup **não** saem na
subida — job diário nasce armado, para que subir a stack às 23h não mande o resumo do dia para todo
mundo fora de hora; eles estreiam na próxima âncora.

Para um tique manual, sem esperar o relógio:

```bash
docker compose -f docker-compose.prod.yml exec api python manage.py run_scheduler --once
```

Quando cada job rodou pela última vez e se deu certo: admin → **Scheduled job runs**. Horários em
`SCHEDULER_DIGEST_AT`, `SCHEDULER_CALENDAR_EVERY_MINUTES` e `SCHEDULER_BACKUP_CHECK_AT`.

## 5. HSTS, na ordem — e só nesta ordem

HSTS diz ao navegador "nunca mais fale http comigo". Ligar antes de o https estar sólido tranca o
acesso, e **o navegador não esquece** antes do prazo.

1. `DJANGO_SSL_REDIRECT=true` e confirme que todo o portal funciona em https por alguns dias.
2. `DJANGO_HSTS_SECONDS=300` (cinco minutos). Se algo quebrar, baixar para `0` e esperar cinco
   minutos resolve.
3. Suba para `31536000` (um ano).
4. `DJANGO_HSTS_INCLUDE_SUBDOMAINS=true` — **só** quando todo subdomínio do domínio falar https.
5. `DJANGO_HSTS_PRELOAD=true` e submissão à lista: **último passo, e praticamente irreversível.** O
   preload é compilado no binário do navegador; sair leva meses e não depende de você. O portal
   nasce com ele desligado de propósito.

Nunca faça o caminho inverso às pressas: desligar HSTS não desfaz o que os navegadores já
guardaram.

## 6. Operação

**Aplicar mudança de `.env`:**
`docker compose -f docker-compose.prod.yml up -d api` (recria o container lendo o arquivo).

**Deploy de nova versão:**
```bash
git pull
docker compose -f docker-compose.prod.yml up -d --build
```
A migração roda no serviço one-shot antes da API subir. Tire uma cópia antes — migração aplicada
não volta sozinha:

```bash
docker compose -f docker-compose.prod.yml exec backup backup.sh
```

**Rollback:** volte o código (`git checkout <tag-anterior>`) e refaça o `up -d --build`. Migração
aplicada **não** volta sozinha: restaure o banco somente conforme o plano da migração
(**`backup-e-restauracao.md`** — restaurar substitui tudo o que entrou desde a cópia).

> **Isto só funciona se houver tag**, e por um tempo não houve nenhuma — o rollback estava
> documentado e não era executável. **Corte a tag antes de subir**, não depois:
>
> ```bash
> # 1. no CHANGELOG.md, feche "Não lançado" como "## [X.Y.Z] — DD/MM/AAAA" e abra uma nova vazia
> # 2. tag anotada no commit que vai ao ar
> git tag -a vX.Y.Z -m "vX.Y.Z"
> git push origin vX.Y.Z
> ```
>
> Sem `-a` a tag não guarda autor nem data, e é justamente isso que se quer saber ao voltar.

**Conferir a configuração de um ambiente já no ar:**
```bash
docker compose -f docker-compose.prod.yml exec api \
  python manage.py check --deploy --fail-level WARNING --tag security
```

**Log e sondas:** `docker compose -f docker-compose.prod.yml logs -f api`. Em produção o formato é
JSON e toda linha carrega o `request_id`, o mesmo que volta na resposta e aparece no log do nginx e
do gunicorn. As sondas são `GET /healthz` (vivo) e `GET /readyz` (pronto: banco + cache). Como
achar uma requisição pelo código, ligar o Sentry e quais alertas criar: **`monitoramento.md`**.

**Backup:** o sidecar `backup` roda sozinho (03:15 por padrão) e copia banco **e** documentos.
`exec api python manage.py backup_status` diz de quando é a última cópia; restaurar, conferir e
mandar para fora do host: **`backup-e-restauracao.md`**.

## 7. Quando algo dá errado

| Sintoma | Causa provável |
| --- | --- |
| container reinicia sem servir | o check de deploy recusou: `logs api` diz qual variável falta |
| laço infinito de redirect | `TRUST_X_FORWARDED_PROTO` desligado com TLS terminado fora, ou o proxy não manda `X-Forwarded-Proto` |
| 429 antes do esperado | mais de um proxy na frente: ajuste `NUM_PROXIES` (ADR 0009) |
| 500 em rotas com teto | Redis inalcançável. `REDIS_URL` definido e Redis fora é **queda**; `REDIS_URL` vazio é degradação |
| admin sem CSS | `collectstatic` não rodou (a imagem faz no build; um `STATIC_ROOT` remontado por volume apaga isso) |
| documento desapareceu no deploy | `DJANGO_MEDIA_ROOT` fora do volume `media_data` |
| upload falha com "permission denied" | `DJANGO_MEDIA_ROOT` apontando para um caminho que não existe na imagem: um volume nomeado herda o dono do diretório que cobre, e fora de `/var/lib/biahflow/media` (ou `/app/media`) o ponto de montagem nasce do root, enquanto o processo roda como uid 10001 |
| `web` não sobe: "host not found in upstream" | não deve acontecer — o `proxy_pass` usa variável para adiar a resolução. Se acontecer, o `resolver` do `nginx.conf` não é o DNS da sua rede |
| "o projeto sumiu" para a Entrega | não é produção: é equipe do projeto vazia (FDD 018) |
| `backup_status` reprova | o sidecar parou: `logs backup`. Detalhe em `backup-e-restauracao.md` |
| digest não sai / calendário não sincroniza | `logs scheduler`. Job diário nasce armado: na primeira subida ele só estreia na próxima âncora (FDD 023) |
| um job periódico rodou duas vezes | há dois `scheduler` no ar. O serviço é um só de propósito — o carimbo e o `select_for_update` seguram, mas o desenho pressupõe um relógio |
| as cópias sumiram | alguém rodou `down -v`, que leva o volume `backup_data` junto — é para isso que serve o offsite |

## Pendências deste bloco do roadmap

Nenhuma. O bloco fechou: monitoramento (FDD 020, ADR 0012 — ver `monitoramento.md`), backup
(FDD 021, ADR 0013 — ver `backup-e-restauracao.md`) e a matriz de testes de acessibilidade,
responsividade e carga (FDD 022, ADR 0014 — ver `testes-de-carga.md`).


## Upgrade da imagem do Postgres para pgvector (FDD 029, ADR 0022)

O `db` passou de `postgres:16-alpine` para `pgvector/pgvector:pg16`. Numa instalação **nova** não
há nada a fazer. Num cluster que **já tem dado**, há — e é o passo mais perigoso desta mudança.

**Por quê.** Alpine é musl, a imagem do pgvector é Debian/glibc, e **a collation de texto vem da
libc**. Montar o mesmo `postgres_data` sob a outra libc pode deixar índices btree sobre colunas de
texto sutilmente mal-ordenados. É silencioso: só aparece quando um `ORDER BY`, um `LIKE` ou uma
checagem de unicidade responde errado. O teste de mesa do backup **não pega isso**, porque sempre
parte de um cluster vazio.

**O procedimento, e ele não é opcional:**

```bash
# 1. Pare quem escreve
docker compose -f docker-compose.prod.yml stop web api scheduler

# 2. Backup antes de tocar em qualquer coisa
docker compose -f docker-compose.prod.yml exec backup backup.sh

# 3. Troque a imagem (já está no compose) e suba só o banco
docker compose -f docker-compose.prod.yml up -d db

# 4. Reconstrua os índices — é este passo que fecha o risco de collation
docker compose -f docker-compose.prod.yml exec db \
    psql -U "$POSTGRES_USER" -d "$POSTGRES_DB" -c 'REINDEX DATABASE CONCURRENTLY "'"$POSTGRES_DB"'";'

# 5. Migre e suba o resto
docker compose -f docker-compose.prod.yml run --rm api-migrate
docker compose -f docker-compose.prod.yml up -d

# 6. Popule o corpus de conhecimento
docker compose -f docker-compose.prod.yml exec api uv run python manage.py ingest_knowledge
```

**Caminho alternativo, e mais seguro se houver janela:** restaurar o dump num cluster **novo**
(`restore.sh --latest --yes` sobre um volume vazio). A restauração reconstrói todo índice por
construção, então o problema de collation não chega a existir.
