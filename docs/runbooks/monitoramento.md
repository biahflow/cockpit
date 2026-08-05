# Runbook — monitoramento

Como o portal conta o que está acontecendo, e o que fazer com isso (FDD 020, ADR 0012). O que é
subida e transporte está em `producao.md`; ativação de integração, em `../operacao.md`.

A pergunta que tudo aqui existe para responder: **o cliente diz que deu erro — onde eu vejo?**

## O caminho de um erro, do começo ao fim

Toda requisição carrega um `X-Request-ID`. Ele nasce no nginx (ou é aproveitado do proxy que estiver
na frente), atravessa o gunicorn, entra em toda linha de log, vira tag no Sentry e **volta na
resposta** — a tela de erro do SPA mostra esse código para o usuário.

Com o código em mãos:

```bash
# 1. a linha da aplicação: rota, status, duração, usuário
docker compose -f docker-compose.prod.yml logs api | grep <request-id>

# 2. a mesma requisição vista pela borda (útil quando ela nunca chegou na API: 502, timeout, 413)
docker compose -f docker-compose.prod.yml logs web | grep <request-id>
```

Com um coletor de log na frente (o formato é JSON em produção), é um filtro por
`request_id: "<id>"`. No Sentry, é a busca `request_id:<id>`.

Se o usuário não tiver o código, comece pelo horário e pelo login — a linha de acesso traz
`user_id`, `path`, `status` e `duration_ms`.

## Sondas

| Rota | Pergunta | Toca banco/cache? | Aponte |
| --- | --- | --- | --- |
| `GET /healthz` | o processo responde? | não | sonda de **reinício** do orquestrador |
| `GET /readyz` | pode receber tráfego? | sim (503 se falhar) | sonda do **balanceador** |

Trocar as duas é o erro clássico: com `/readyz` na sonda de reinício, toda queda do banco vira um
container reiniciando em laço — e reiniciar não traz o Postgres de volta.

```bash
curl -s https://SEU-DOMINIO/healthz    # {"status": "ok"}
curl -s https://SEU-DOMINIO/readyz     # {"status": "ok", "checks": {"db": "ok", "cache": "ok"}}
```

`503 degraded` diz **qual** dependência caiu, e só isso: o detalhe (host, traceback) fica no log,
porque o endpoint é anônimo e alcançável pela internet. As sondas respondem antes de
`ALLOWED_HOSTS` e do redirect de https — é de propósito, e está explicado na ADR 0012.

## Log

Em produção o formato é JSON (`DJANGO_LOG_FORMAT=json`, já no `docker-compose.prod.yml`); em
desenvolvimento, texto. Uma linha de acesso:

```json
{"timestamp": "2026-08-05T13:33:28-0300", "level": "INFO", "logger": "biahflow.request",
 "message": "GET /api/v1/auth/csrf/ 301", "request_id": "rastreio-abc123",
 "method": "GET", "path": "/api/v1/auth/csrf/", "status": 301, "duration_ms": 1.1, "user_id": null}
```

Tudo sai em stderr, que é o que o runtime de container coleta — para onde ele manda (CloudWatch,
Loki, Datadog) é escolha de quem hospeda. Três logs convivem, e é intencional:

- **nginx** — vê o que nunca chegou à API (502, timeout, 413).
- **gunicorn** (access) — vê o que morre antes do Django (timeout de worker, corpo inválido).
- **aplicação** — a única que sabe usuário e duração.

Os três carregam o mesmo `req=`/`request_id`.

`DJANGO_LOG_LEVEL` ajusta o volume (default `INFO`). `DJANGO_LOG_REQUESTS=false` desliga a linha de
acesso da aplicação — só faça isso se já coletar outra, porque é a única com usuário.

## Sentry (rastreamento de erro)

Opcional: sem DSN, nada é enviado e nenhum byte do SDK entra no bundle do SPA.

**1. Backend.** No `.env`:

```
SENTRY_DSN=https://chave@o0.ingest.sentry.io/1234567
SENTRY_ENVIRONMENT=producao
SENTRY_RELEASE=2026.08.05          # use a tag ou o SHA do deploy
```

`docker compose -f docker-compose.prod.yml up -d api`.

**2. SPA.** O DSN dele é assado no **build** (o Vite substitui `import.meta.env` por literal), então
é build arg — não adianta pôr no ambiente do container depois:

```
VITE_SENTRY_DSN=https://chave@o0.ingest.sentry.io/1234567
```

`docker compose -f docker-compose.prod.yml up -d --build web`. Ligado, o SDK é um chunk de 475 kB
(156 kB gzip) carregado à parte, depois da primeira pintura.

**3. Sourcemap (opcional).** Sem ele o stack trace do browser vem minificado. É opt-in por
`SENTRY_AUTH_TOKEN` + `SENTRY_ORG` + `SENTRY_PROJECT` como build args do `web`; o mapa é `hidden`,
isto é, o Sentry desminifica e o nginx não passa a servir o código-fonte do portal.

**O que nunca é enviado:** `send_default_pii=False` nos dois lados, sem Session Replay e sem
integração de captura de corpo. O portal mostra proposta, contrato e dado de cliente na tela — o que
se quer no Sentry é o stack trace e o `request_id` para achar o resto no log.

Do lado do SPA, só **5xx** viram evento: 400/403/404 são o app funcionando e já estão na tela.

## Alertas

Nenhuma regra de alerta mora no repositório — o código entrega o sinal, o fornecedor decide o que
acordar alguém. O mínimo a configurar:

| Onde | Regra | Por quê |
| --- | --- | --- |
| Sentry | issue nova em `producao` → e-mail/Slack | é o 500 que ninguém viu |
| Sentry | pico de eventos (ex.: >20/h) | regressão de deploy |
| Balanceador/uptime | `/readyz` != 200 por 2 checagens | banco ou Redis fora |
| Uptime externo | `GET /` de fora da rede | pega o que morre antes da borda: DNS, TLS, provedor |
| Provedor | certificado a <14 dias do vencimento | HSTS transforma TLS vencido em portal inacessível |
| Agendador (cron/CI) | `manage.py backup_status` saindo com código 1 | backup que parou de rodar só aparece no dia em que se precisa dele (FDD 021) |

Um alerta que ninguém investiga é pior que nenhum: comece por estes seis.

O de backup é o único que não vem de uma requisição: rode o comando de fora, uma vez ao dia, e
trate a saída diferente de zero como incidente.

```bash
docker compose -f docker-compose.prod.yml exec -T api python manage.py backup_status
```

O que ele confere, o que fazer quando reprova e como restaurar: **`backup-e-restauracao.md`**.

## Quando algo dá errado

| Sintoma | Onde olhar |
| --- | --- |
| usuário relata erro com um código | `logs api \| grep <código>`, depois `logs web \| grep <código>` |
| `/readyz` em 503, `/healthz` em 200 | banco ou Redis: o corpo do 503 diz qual; o traceback está no log |
| container reiniciando em laço | a sonda de reinício está apontada para `/readyz` — deve ser `/healthz` |
| balanceador diz "saudável" com a API fora | está sondando `/` (o SPA responde 200 sozinho) em vez de `/readyz` |
| nenhuma linha de log com o request-id | a requisição nunca chegou à API: veja o log do `web` |
| Sentry mudo com o DSN preenchido | no SPA, o DSN é build arg: refaça `up -d --build web` |
| log em texto em produção | `DJANGO_LOG_FORMAT` não chegou ao container (confira o `.env` e recrie o `api`) |
