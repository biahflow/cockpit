# ADR 0012 — Observabilidade: identidade de requisição, sondas e rastreamento de erro

**Status:** aceita

## Contexto

A ADR 0011 deixou o portal capaz de subir em produção; não o deixou observável. O que existia:
`LOGGING` jogando texto solto em stderr, nenhuma forma de ligar uma linha de log a uma requisição,
e um 500 que morria no stderr sem ninguém saber. A sonda do container era um `GET` em
`/api/v1/auth/csrf/` — que responde 200 com o banco fora, e que respondia **400** assim que
`DJANGO_ALLOWED_HOSTS` virava o domínio real.

Três decisões precisavam ser tomadas: de onde nasce a identidade de uma requisição, quem responde
"o processo está bem" e a quem contar que deu erro.

## Decisão

**A identidade da requisição nasce na borda e é aproveitada, não regerada.** O nginx manda o
`$request_id` dele em `X-Request-ID`; o Django usa o que chegou, e só gera um `uuid4` quando não
veio nenhum. O id vive num `ContextVar`, entra em toda linha de log, vira tag no Sentry e **volta
na resposta** — o SPA mostra esse código na tela de erro. É o que faz "deu erro para o cliente"
virar uma requisição localizável em três logs.

Como o header vem de fora, ele é sanitizado (`[A-Za-z0-9._-]`, 64 caracteres). Sem isso, um
`X-Request-ID` com quebra de linha injeta uma entrada falsa no log — a versão em texto do log
injection. Aproveitar o id do cliente é uma escolha consciente: ele não autoriza nada, não indexa
nada e serve só para correlacionar; o custo de mentir sobre ele é confundir a si mesmo.

**As sondas são middleware, não rota, e ficam fora do `/api/v1/`.** `/healthz` (vivo) e `/readyz`
(pronto: banco + cache) respondem **antes** de `ALLOWED_HOSTS` e do `SECURE_SSL_REDIRECT`. Não é
preferência de estilo: a sonda do container fala com `127.0.0.1` enquanto `ALLOWED_HOSTS` é o
domínio, e uma sonda http com redirect ligado receberia 301. Nenhuma view chega antes dessas duas
coisas. Fora do `/api/v1/` porque sonda não é contrato de API — não entra no `openapi.yaml`, não
tem sessão nem teto de requisição, e `/api/v1/health/` já é outra coisa (o *health score* de
projeto).

A consequência aceita: **`/healthz` e `/readyz` não validam o `Host`.** É inerte, porque a resposta
é constante e não deriva nada do header — não há link, redirect nem cookie para envenenar.

**Vivo e pronto são perguntas diferentes.** `/healthz` não toca em nada: se ele reprovasse quando o
banco cai, o orquestrador reiniciaria um container saudável, e reiniciar não traz o Postgres de
volta. `/readyz` toca banco e cache e responde 503 — o certo é sair do balanceador, não morrer.

**Sentry é o fornecedor de rastreamento de erro, atrás de flag e sem adaptador.** Sem `SENTRY_DSN`
o SDK não é inicializado e nada sai do processo; no SPA, o `import()` dinâmico vira código morto e
o SDK some do bundle. `send_default_pii=False` nos dois lados: este portal carrega proposta,
contrato e dado de cliente, e o que se quer no Sentry é o stack trace mais o `request_id` para
achar o resto no log.

Diferente da assinatura eletrônica (ADR 0007), **não** há camada de adaptador: o SDK do Sentry já é
a abstração, o ponto de contato é uma função (`init_sentry`/`reportError`), e trocar de fornecedor
é reescrever essas duas.

**Log em JSON é opção de ambiente, não default.** `DJANGO_LOG_FORMAT=json` liga; o compose de
produção liga. JSON no terminal de quem desenvolve é hostil, e o formato só rende com um coletor
que indexa campo. O `request_id` sai nos dois formatos.

**O alerta é do fornecedor, e nada de alerta mora no repositório.** Regras de alerta são do Sentry
e do provedor de infraestrutura; o que o código entrega é o sinal (evento de erro, 503 na sonda,
linha de log estruturada). Runbook em `docs/runbooks/monitoramento.md`.

Alternativas recusadas:

- **Rota `/healthz` em `config/urls.py`** — não resolve `ALLOWED_HOSTS` nem o redirect de https, que
  é exatamente o defeito que se está corrigindo.
- **Pôr as sondas em `/api/v1/`** — mudaria o `openapi.yaml` e colidiria com `/api/v1/health/`.
- **Um `SECURE_REDIRECT_EXEMPT` com as sondas** — resolveria metade (o 301) e deixaria o 400 de
  `DisallowedHost` de pé.
- **Adicionar o host da sonda a `ALLOWED_HOSTS`** — devolve o `Host` de container para dentro da
  lista que o `check --deploy` existe para manter limpa, e depende do IP que o Docker sorteou.
- **`django-structlog` / `python-json-logger`** — dependência para o que 30 linhas de `Formatter`
  da stdlib fazem, e mais uma superfície de atualização.
- **Um check de deploy exigindo `SENTRY_DSN`** — transformaria "não contratei o fornecedor" em "o
  deploy não sobe". O fornecedor é opcional por decisão.
- **`sentry_sdk` com `send_default_pii=True`** — manda cookie de sessão, corpo da requisição e
  e-mail do usuário para um terceiro.
- **Session Replay do Sentry no SPA** — grava a tela, e a tela mostra contrato e dado de cliente.
- **Métricas Prometheus / OpenTelemetry** — outro eixo (o que medir, onde guardar, quem consulta),
  e nada disso responde à pergunta deste item, que é "deu erro, onde vejo".
- **`threading.local` para o request-id** — não acompanha código assíncrono e sobrevive ao
  reaproveitamento de worker.

## Consequências

- Uma requisição é rastreável de ponta a ponta pelo mesmo id: log do nginx, access log do gunicorn,
  log estruturado do Django, evento do Sentry e a tela de erro do SPA.
- O orquestrador e o balanceador passam a ter sondas com significados distintos — e é preciso
  apontar cada um para a sua (`/healthz` para reinício, `/readyz` para tráfego).
- `/healthz` e `/readyz` são anônimos e alcançáveis pela borda. Por isso o corpo é constante e sem
  versão, hostname ou traceback.
- O DSN do SPA é assado no build da imagem do `web`: trocá-lo exige reconstruir, não reiniciar.
- Ligado, o SDK do browser é um chunk de 475 kB (156 kB gzip) carregado à parte.
- `sentry-sdk` passa a ser dependência do backend mesmo com o fornecedor desligado.
