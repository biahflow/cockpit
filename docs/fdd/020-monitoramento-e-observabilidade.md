# FDD 020 — Monitoramento e observabilidade

## Jornada

Item `roadmap.md` do bloco "Prontidão para produção": *monitoramento — logs centralizados, alertas,
health checks e rastreamento de erros*. A FDD 019 o nomeou ao fechar o recorte anterior: "log
estruturado, request-id, alertas, rastreamento de erro e um `/healthz` de verdade são o item de
monitoramento do roadmap: até ele existir, o healthcheck do container usa `/api/v1/auth/csrf/`".

O que existia era um deploy que responde e não conta nada: texto solto em stderr, nenhuma forma de
ligar uma linha de log a uma requisição, um 500 que morre no stderr sem ninguém saber, e uma sonda
que dizia "saudável" com o banco fora.

A pergunta que este recorte responde é uma só: **o cliente diz que deu erro — onde eu vejo?**

## Regras

- **A identidade da requisição nasce na borda e é aproveitada.** O nginx manda o `$request_id`
  dele; o Django usa o que chegou e só gera um `uuid4` quando não veio nada. O mesmo id aparece no
  log do nginx, no access log do gunicorn, em toda linha do log da aplicação, na tag do evento do
  Sentry e **na resposta** — o SPA mostra o código na tela de erro. Verificado ponta a ponta: um
  `X-Request-ID: rastreio-abc123` sai nos três logs e volta no header.
- **O id de fora é sanitizado** (`[A-Za-z0-9._-]`, 64 caracteres) antes de qualquer coisa. Sem isso
  um header com quebra de linha injeta uma entrada falsa no log — log injection em texto. Se não
  sobrar nada de aproveitável, gera-se um novo.
- **`/healthz` e `/readyz` são middleware, não rota.** Duas coisas que view nenhuma consegue: a
  sonda do container fala com `127.0.0.1` enquanto `DJANGO_ALLOWED_HOSTS` é o domínio (`get_host()`
  levantaria `DisallowedHost` → 400), e com `SECURE_SSL_REDIRECT` ligado uma sonda http levaria 301.
  Ignorar o `Host` é inerte aqui: a resposta é constante e não deriva nada dele.
- **Vivo e pronto são perguntas diferentes.** `/healthz` não toca em nada — se ele reprovasse com o
  banco fora, o orquestrador reiniciaria um container saudável, e reiniciar não traz o Postgres de
  volta. `/readyz` confere banco (`SELECT 1`) e cache (ida **e volta**, porque um Redis que aceita
  `set` e devolve `None` no `get` só apareceria no teto de requisição horas depois) e responde 503.
  O `docker-compose.prod.yml` sonda `/readyz`, porque ali a pergunta é "pode entrar no balanceador".
- **A sonda não conta nada além de estar bem.** Corpo constante, sem versão, hostname ou traceback:
  o endpoint é anônimo e alcançável pela borda. O detalhe da falha vai para o log, com request-id.
- **As sondas ficam fora do `/api/v1/`.** Não são contrato de API: sem sessão, sem teto de
  requisição, sem entrar no `openapi.yaml`. E `/api/v1/health/` já existe e é outra coisa — o
  *health score* de projeto (`apps/core/health.py`).
- **A sonda tem bloco próprio no nginx.** `^/(healthz|readyz)$` não casa com o regex de
  `/api|/admin|/static`, então cairia no `try_files` e o balanceador receberia o **index.html do SPA
  com 200** — o mesmo defeito que o bloco `/media/` documenta, com consequência pior: "saudável"
  com a API fora do ar.
- **Log em JSON é opção de ambiente, não default.** JSON no terminal de quem desenvolve é hostil, e
  o formato só rende com um coletor que indexa campo. `DJANGO_LOG_FORMAT=json` liga; o compose de
  produção liga. O `request_id` sai nos dois formatos, e o `JsonFormatter` usa `default=str` para
  não perder a linha inteira em `TypeError` quando um `extra` traz `Decimal` ou model.
- **O access log da aplicação não substitui o do gunicorn.** O daqui sabe usuário e duração; o do
  gunicorn enxerga o que morre antes do Django (timeout de worker, corpo inválido). Os dois se
  cruzam pelo mesmo `X-Request-ID`, que por isso entrou no `access_log_format`. A sonda fica fora do
  log de acesso por construção — ela responde num middleware **antes** dele, e não por um `if`.
- **Sentry atrás de flag, sem adaptador (ADR 0012).** Sem `SENTRY_DSN` o SDK não é inicializado e
  nada sai do processo. `send_default_pii=False` nos dois lados: o portal carrega proposta, contrato
  e dado de cliente. Não há camada de adaptador como na assinatura eletrônica (ADR 0007) — o SDK já
  é a abstração e o ponto de contato são duas funções.
- **No SPA o SDK entra por import dinâmico.** Ele é grande: 475 kB (156 kB gzip), mais que o bundle
  inteiro do portal. Com DSN vira um chunk carregado em paralelo, em vez de atrasar a primeira
  pintura; **sem DSN o Rollup elimina o `import()` como código morto** e não sobra um byte de Sentry
  no `dist/` (verificado com `grep`). O preço é uma janela de milissegundos no boot sem captura.
- **O DSN do SPA é assado no build.** `import.meta.env` é substituído por literal, então ele é build
  arg da imagem do `web`, não variável do container: trocá-lo exige `up -d --build web`. Um DSN de
  Sentry é público por desenho — identifica o projeto e só aceita escrita.
- **A tela branca virou mensagem.** Um erro de render desmonta a árvore inteira do React; o
  `ErrorBoundary` mostra o **código da ocorrência** (o request-id da última chamada) e um botão de
  recarregar. É o que permite alguém do outro lado achar a requisição.
- **Só 5xx vão para o Sentry a partir do `api.ts`.** 400/403/404 são o app funcionando — validação,
  permissão, item removido — e encheriam o fornecedor de ruído que já está na tela do usuário.
- **A posição do WhiteNoise virou cálculo.** `MIDDLEWARE.insert(1, ...)` valia enquanto o
  `SecurityMiddleware` era o primeiro da lista; com os middlewares novos na frente, o WhiteNoise
  passaria a servir estático **antes** dele, sem os headers de segurança. Agora o índice sai de
  `MIDDLEWARE.index(SecurityMiddleware) + 1`.

## Defeito corrigido de carona

A sonda do `api` no `docker-compose.prod.yml` mandava `Host: 127.0.0.1`, e o `check --deploy`
recusa subir com `ALLOWED_HOSTS` de desenvolvimento (`biahflow.E005`). Em produção de verdade a
sonda levava **400**, o container nunca ficava *healthy*, e o serviço `web` — que depende de
`service_healthy` — **nunca subia**. Estava quebrada desde a FDD 019 e não apareceu porque ninguém
tinha subido com o domínio real. Reproduzido no stack de produção (`HTTPError 400`) e coberto por
`tests/regression/test_health_probe_bypasses_host_and_redirect.py`.

## Fora deste recorte

**Alertas não moram no repositório.** Regras de alerta são do Sentry e do provedor; o que o código
entrega é o sinal — evento de erro, 503 na sonda, linha estruturada. O passo a passo de configurar
está em `docs/runbooks/monitoramento.md`.

**Agregador de log.** Tudo sai em stderr, que é o que o runtime de container coleta; para onde ele
manda é escolha de quem hospeda (CloudWatch, Loki, Datadog). O formato JSON existe para essa ponta.

**Métricas e tracing distribuído** (Prometheus, OpenTelemetry) são outro eixo — o que medir, onde
guardar, quem consulta — e não respondem à pergunta deste item. `SENTRY_TRACES_SAMPLE_RATE` existe
e nasce em zero.

**Upload de sourcemap para o Sentry** é opt-in por `SENTRY_AUTH_TOKEN` (o plugin nem entra na lista
sem ele): exige um token de escrita que nem o build local nem o CI têm. Sem token, `sourcemap:
false`; com token, `hidden` — o Sentry desminifica e o nginx não passa a servir o código-fonte.

**Backup, retenção e restauração** são o item seguinte do roadmap. Também fica fora um check de
deploy que exija `SENTRY_DSN`: o fornecedor é opcional por decisão (ADR 0012).

## Aceite

Quem sobe o portal com `DJANGO_ALLOWED_HOSTS` no domínio real vê o `api` ficar **healthy** e o
`web` subir — o que não acontecia. `GET /healthz` responde `{"status": "ok"}` com qualquer `Host` e
mesmo com o redirect de https ligado; `GET /readyz` responde `{"status": "ok", "checks": {...}}` e,
com o Postgres parado, **503 `degraded`** enquanto `/healthz` continua 200. Uma requisição com
`X-Request-ID: rastreio-abc123` volta com o mesmo header e aparece nos três logs. Com `SENTRY_DSN`,
um 500 vira evento com a tag `request_id`; sem ele, nada muda e nenhum byte do SDK entra no bundle
do SPA. Um erro de render mostra "Esta tela não conseguiu carregar" com o código da ocorrência, em
vez de tela branca.

## Regressão crítica

`/healthz` responde 200 com `Host` fora de `ALLOWED_HOSTS` e com `SECURE_SSL_REDIRECT=True`,
enquanto a sonda antiga (`/api/v1/auth/csrf/`) responde 400 e 301 nos mesmos cenários. `/readyz`
devolve 503 com o banco fora e com o cache mudo, e o corpo não traz nome de host nem traceback. O
request-id é gerado quando ausente, preservado quando vem da borda, sanitizado quando vem com
quebra de linha (`"linha\nfalsa"` → `"linhafalsaINFOtudook"`), cortado em 64 caracteres, e não vaza
de uma requisição para a seguinte. A linha de acesso traz `request_id`, `status`, `duration_ms` e
`user_id`, e **não** existe para `/healthz`. O `JsonFormatter` produz JSON parseável, inclui o
traceback e não perde a linha com valor não serializável. `DJANGO_LOG_FORMAT=json` troca o
formatter; sem `SENTRY_DSN` o SDK não é inicializado nem no backend nem no SPA; com DSN,
`send_default_pii=False`. O WhiteNoise continua imediatamente após o `SecurityMiddleware`. No SPA,
o erro de API carrega `requestId` e `status`, e o `ErrorBoundary` mostra o código da ocorrência.
