# ADR 0011 — Processo de produção e TLS na borda

**Status:** aceito

## Contexto

O item de infraestrutura do bloco "Prontidão para produção" acumulou decisões que nunca tinham
sido tomadas, porque nunca houve produção: como o processo roda, quem termina o TLS, de onde vêm os
segredos, e o que acontece quando a configuração está errada.

Enquanto isso o repositório tinha um único caminho, o de desenvolvimento — `runserver`,
`DJANGO_DEBUG=true` como default do compose, imagem sem `CMD` e sem `uv.lock`, `SECRET_KEY` com
fallback para um valor versionado. Não é que a configuração de produção estivesse errada: ela não
existia, e nada no repositório notava a diferença.

**A primeira decisão é de transporte.** A FDD 017 apontou `SECURE_SSL_REDIRECT`, HSTS e
`SECURE_PROXY_SSL_HEADER` e os adiou por dependerem de domínio e HTTPS. Ligar isso exige saber quem
termina o TLS — e, portanto, em quem o Django pode acreditar.

**A segunda é de comportamento diante de configuração insegura.** Um portal que sobe em SQLite
efêmero com o segredo do repositório parece saudável, atende, e perde os dados no primeiro restart.
Alguém tem de dizer não.

## Decisão

**O TLS termina na borda, e acreditar nisso é opt-in.** Nem gunicorn nem nginx da aplicação falam
TLS; quem termina é o proxy do provedor. `TRUST_X_FORWARDED_PROTO` (booleano, não o nome do header)
liga o `SECURE_PROXY_SSL_HEADER`, e nasce desligado.

**Gunicorn + WhiteNoise + nginx para o SPA.** Três workers por `gunicorn.conf.py`, WhiteNoise
servindo o estático do admin, e o bundle do Vite servido por um nginx que também é o salto que
carimba `X-Forwarded-Proto`. Imagem em dois estágios, `collectstatic` no build, usuário sem
privilégio.

**Redis como cache compartilhado, sessão no banco.** O contador de teto de requisição precisa ser
compartilhado; a sessão, não.

**Configuração insegura é recusada por system check, no boot do servidor.**
`apps/core/checks.py` com `deploy=True`, e o entrypoint da imagem roda
`check --deploy --fail-level WARNING --tag security` antes do `exec gunicorn`.

**Os segredos vêm de variável de ambiente**, populadas pelo cofre da plataforma. O repositório
documenta os nomes (`.env.example`) e nunca os valores.

Alternativas recusadas:

- **`raise ImproperlyConfigured` no import de `settings.py`** — mataria `migrate`, `collectstatic` e
  `shell`, exatamente os comandos de que se precisa durante um incidente, e quebraria a suíte, que
  roda sem segredo.
- **Derivar o transporte de `DEBUG`** — `DEBUG=False` é também o modo da suíte: deixaria centenas de
  testes em 301.
- **Split de settings (`settings/prod.py`) ou `DJANGO_ENV`** — um eixo novo de configuração para um
  problema que a checagem de deploy já resolve.
- **`django-environ`** — dependência para trocar `os.getenv` por outro `getenv`.
- **`--fail-level WARNING` sem `--tag security`** — falharia em avisos de schema do drf-spectacular,
  que não dizem nada sobre estar pronto para produção.
- **Deixar o estático para o nginx** — amarraria o deploy a um host específico; WhiteNoise mantém a
  imagem autossuficiente.
- **Sessão em cache (`cache`/`cached_db`)** — uma queda ou eviction do Redis deslogaria todo mundo.
- **`docker-compose.prod.yml` como override** — override não remove bind mount nem serviço herdado;
  levaria a árvore de código, o Mailpit e o MinIO para produção.
- **HSTS preload agora** — submissão irreversível a uma lista compilada no navegador.
- **`CompressedManifestStaticFilesStorage`** — levanta em runtime se um `{% static %}` não estiver no
  manifesto, e o manifesto só existe depois do `collectstatic`; com `DEBUG=False` na suíte, um
  template renderizado estouraria. Perde-se o hash no nome de alguns arquivos do admin.

## Consequências

**O `X-Forwarded-Proto` é um footgun, e fica registrado como tal.** Ligue
`TRUST_X_FORWARDED_PROTO` **somente** se todo caminho até o gunicorn passa por um proxy que
*sobrescreve* esse header. Se a porta do container for alcançável direto, qualquer cliente manda
`X-Forwarded-Proto: https` e derruba de uma vez o redirect e a premissa do cookie `Secure`. É por
isso que o `docker-compose.prod.yml` não publica a porta da API.

**`security.W021` fica silenciado para sempre**, inclusive depois de alguém ligar o preload — o
aviso não volta a ser útil. É o preço de recusar o preload sem abrir mão do `--fail-level WARNING`.

**Um `UPDATE django_session` por requisição**, custo da expiração deslizante. Aceitável no volume de
uma ferramenta interna. Um teto absoluto de sessão exigiria middleware próprio e não existe.

**Configuração errada não degrada: recusa subir.** É deliberado, e significa que um erro de
digitação em `REDIS_URL` derruba o deploy em vez de silenciosamente triplicar os tetos. Um Redis
inalcançável com `REDIS_URL` definido é queda (o `RedisCache` levanta e as rotas com throttle
respondem 500); `REDIS_URL` ausente é degradação. Está no runbook.

**`MEDIA_ROOT` local impede mais de uma réplica.** Documento fica em volume no host. Escalar exige
volume compartilhado ou `GOOGLE_DRIVE_ENABLED=true`.

**O `NUM_PROXIES` continua sendo responsabilidade de quem instala** (ADR 0009): o número depende do
ingress. O que existe agora é a recusa de confiar no header sem ele.

**Quem já tem ambiente de desenvolvimento precisa de um `docker compose down -v`.** A imagem passou
a ter estágios e o volume `api_venv` antigo foi criado por root com outra estrutura.

**O `env_file` muda a precedência**: o `.env` inteiro entra no container e o bloco `environment` do
compose vence o arquivo. Quem dependia de uma variável ser ignorada porque não estava na lista vai
vê-la passar a valer.
