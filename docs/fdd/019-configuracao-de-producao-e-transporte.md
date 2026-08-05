# FDD 019 — Configuração de produção e transporte

## Jornada

Item `roadmap.md` do bloco "Prontidão para produção": *domínio, HTTPS, variáveis de produção e
segredos em cofre apropriado*. A FDD 017 parou exatamente aqui, por escrito: hardening de
transporte, expiração de sessão, validadores de senha adicionais e `check --deploy` no CI
"dependem de domínio e HTTPS resolvidos". A ADR 0009 deixou no mesmo item o `LocMemCache`, que
multiplica todo teto de requisição pelo número de workers.

O que existia não tinha caminho de produção: o compose subia `runserver` com `DJANGO_DEBUG=true`
por default, a imagem não tinha `CMD`, `uv.lock` nem usuário sem privilégio, o `SECRET_KEY` caía
no segredo do repositório sem reclamar e o `MEDIA_ROOT` morava dentro do bind mount da árvore de
código. Este recorte é o **de código, configuração e runbook**: comprar domínio, terminar TLS,
escolher provedor e popular o cofre seguem sendo passos manuais, agora documentados.

## Regras

- **Nada de transporte é derivado de `DEBUG`.** `DEBUG=False` não significa produção neste repo: é
  também o modo da suíte e do CI. Com `SECURE_SSL_REDIRECT = not DEBUG`, o `SecurityMiddleware`
  responde 301 a toda requisição do test client e a suíte inteira fica vermelha — verificado.
  `SECURE_SSL_REDIRECT`, `SECURE_HSTS_SECONDS` e o header de proxy nascem desligados e são ligados
  pelo ambiente; quem cobra que estejam ligados em produção é o `check --deploy`.
- **Confiar no `X-Forwarded-Proto` é opt-in.** `TRUST_X_FORWARDED_PROTO` é booleano, não o nome do
  header, para que um erro de digitação não vire buraco de spoofing. Ligado sem um proxy que
  **sobrescreva** o header, qualquer cliente se declara em https e derruba o redirect e a premissa
  do cookie `Secure`. Ver ADR 0011.
- **HSTS preload nasce desligado e o aviso é silenciado.** Preload é submissão a uma lista compilada
  no binário do navegador, que nenhum deploy desfaz. Como o gate roda com `--fail-level WARNING`, o
  `security.W021` entra em `SILENCED_SYSTEM_CHECKS` — é o único aviso que este projeto escolhe não
  ouvir, e está comentado no código dizendo por quê.
- **A recusa de configuração insegura é system check, não `raise`.** Um `ImproperlyConfigured` no
  import de `settings.py` quebraria todos os testes (que rodam sem `DJANGO_SECRET_KEY`) e, em
  produção, mataria também `migrate` e `shell` — os comandos de que se precisa durante um incidente.
  `apps/core/checks.py` registra sete erros com `deploy=True`, invisíveis para `manage.py check` e
  para a suíte, cobrindo o que o Django não cobre: segredo de desenvolvimento, `*` ou hosts de
  localhost em `ALLOWED_HOSTS` (o `W020` nativo só reclama de lista vazia), **SQLite** — que em
  container sobe, migra, atende e perde tudo no restart —, cache por processo, origem `http://` em
  `CSRF_TRUSTED_ORIGINS`, `collectstatic` não rodado e header de proxy sem `NUM_PROXIES`. Quem
  recusa subir é o entrypoint da imagem, que roda o check antes do `exec gunicorn`.
- **A sessão expira por inatividade.** `SESSION_COOKIE_AGE` (12 h) com
  `SESSION_SAVE_EVERY_REQUEST`: expiração deslizante, porque o SPA só chama `currentUser()` na
  montagem e não tem interceptador de 403 — uma expiração absoluta apareceria como erro opaco no
  meio da tela em vez de volta ao login. Sessão continua no banco, não no cache.
- **Os quatro validadores de senha, e o de similaridade funcionando.** Faltavam
  `UserAttributeSimilarity` e `NumericPassword`. O primeiro **desiste em silêncio** sem um `user`, e
  o serializer chamava `validate_password(value)` sem usuário: ligá-lo no settings sozinho não
  mudaria nada. A validação do aceite de convite passou a ser de objeto, com um `User` instanciado e
  não salvo, e o erro continua sendo 400 no campo `password`. O e-mail fica fora da comparação: ele
  vem do `Invitation`, resolvido só na view.
- **O Redis fecha a ressalva da ADR 0009.** O contador de teto vive no cache; com três workers de
  gunicorn e `LocMemCache`, cada limite da FDD 017 passava a valer o triplo. `REDIS_URL` liga o
  cache compartilhado e um check recusa produção sem ele. Perder o dado do Redis é degradação;
  perder o Redis é queda — está na ADR.
- **Processo de produção de verdade.** `gunicorn.conf.py` (3 workers, timeout 60 s para as chamadas
  de IA, reciclagem por `max_requests`), imagem em dois estágios com `uv.lock` copiado,
  `collectstatic` no build, WhiteNoise servindo o estático do admin e usuário `app` uid 10001.
  `docker-compose.prod.yml` é autônomo — override não removeria o bind mount, o Mailpit nem o MinIO
  — com `db` e `redis` sem porta publicada, migração como serviço one-shot e `media_data` em volume
  nomeado: documento de cliente dentro da árvore de código não sobrevive a um deploy.
- **A imagem deixou de levar dado de cliente.** Não havia `.dockerignore`: o `COPY . .` assava o
  `.venv` do host, o `db.sqlite3` e os arquivos reais de `media/` na imagem que vai para um
  registry.
- **O volume de mídia é criado na imagem, com o dono certo.** Um volume nomeado vazio herda
  conteúdo e propriedade do diretório que cobre; sem o `mkdir` + `chown` no build, o Docker cria o
  ponto de montagem como root, o processo roda como `app` e **todo upload de documento falha com
  "permission denied"**. Quem apontar `DJANGO_MEDIA_ROOT` para outro caminho responde pela
  propriedade dele.
- **`/media/` responde 404 também na borda.** O Django já não serve `MEDIA_ROOT` em ambiente nenhum
  (ADR 0002, FDD 017), mas o `try_files` do SPA devolvia o `index.html` com **200** para
  `/media/...`. Não é vazamento — é a resposta errada para o que a FDD 017 documentou como 404.
- **O nginx resolve o upstream em runtime.** Com o host literal em `proxy_pass`, o nginx resolve o
  nome no boot e **se recusa a iniciar** se a API ainda não existe; como o compose reinicia
  containers de forma independente, um restart do `web` com a API fora deixaria o nginx morto até
  alguém subir na mão. Com variável + `resolver`, o pior caso é um 502 temporário.
- **Os dois composes têm nomes de projeto distintos.** Sem `name:`, ambos usariam o nome do
  diretório — e produção anexaria o **mesmo volume de banco** do ambiente de desenvolvimento.
- **A query string do `DATABASE_URL` era descartada**, então `...?sslmode=require` não fazia nada —
  e é assim que um Postgres gerenciado entrega a credencial. Agora é honrada, com `DB_SSLMODE`
  vencendo a URL, mais `CONN_MAX_AGE` e `CONN_HEALTH_CHECKS`.
- **O `.env` inteiro chega ao container.** O compose repetia à mão ~26 das ~60 variáveis que o
  `settings.py` lê, e as que faltavam (`FRONTEND_ORIGIN`, `PORTAL_*`, `TASKSYNC_*`, `NUM_PROXIES`,
  todos os `*_RATE`) eram descartadas em silêncio — o clássico "botei no `.env` e não aconteceu
  nada". Virou `env_file`, e o `.env.example` passou a documentar tudo.
- **500 deixou de ser invisível.** O default do Django manda traceback para `mail_admins` e, sem
  `ADMINS`, para lugar nenhum. Um `LOGGING` mínimo joga tudo em stderr, que é o que o runtime de
  container coleta.

## Fora deste recorte

Comprar domínio, terminar TLS, escolher provedor e popular o cofre — os passos manuais do runbook.
Log estruturado, request-id, alertas, rastreamento de erro e um `/healthz` de verdade são o item de
**monitoramento** do roadmap: até ele existir, o healthcheck do container usa
`/api/v1/auth/csrf/`. Backup, retenção e restauração são o item seguinte. Também ficam de fora
S3/MinIO para os documentos (com storage local, mais de uma réplica exige volume compartilhado ou
`GOOGLE_DRIVE_ENABLED`) e o build das imagens no CI, que só valida os composes.

Dois avisos de schema do drf-spectacular (`W001` de parâmetro sem tipo e colisão de `operationId`,
`W002` de serializer não inferível) aparecem no `check --deploy` cru e **não** foram corrigidos
aqui: mexer nisso muda `openapi.yaml` e um `operationId` do cliente gerado, o que é alteração de
contrato dentro de uma entrega de segurança. Por isso o gate roda com `--tag security`.

Fora do recorte mas corrigido por bloquear a entrega: o `frontend/package-lock.json` estava fora de
sinc com o `package.json`, então `npm ci` falhava — o job `frontend` do CI estava vermelho em todos
os merges recentes e a imagem do SPA não construía. Consertar isso descobriu um segundo defeito
atrás dele: o `playwright.config.ts` desligava o `webServer` quando `CI` estava definido, sem nada
subir o Vite no lugar, então **os cinco testes e2e nunca poderiam ter passado no CI** — ficava
invisível porque o job quebrava antes de chegar lá. Agora o Playwright sobe o servidor também no
CI, e só o dispensa se `E2E_BASE_URL` apontar para um ambiente já no ar.

## Aceite

Quem sobe o portal em produção copia o `.env.example`, preenche o bloco "Produção" com o segredo
gerado e os hosts reais, e roda `docker compose -f docker-compose.prod.yml up -d --build`. Se
faltar `DJANGO_SECRET_KEY`, `DATABASE_URL` ou `REDIS_URL`, o container **não sobe** e o log diz qual
variável falta e por quê. Subindo, `http://` responde 301 para `https://`, a resposta em https
carrega `Strict-Transport-Security` com `includeSubDomains` e **sem** `preload`, o **Django admin**
abre com CSS, e um documento subido continua lá depois de `down` e `up` novamente. Doze horas sem
tocar no portal e a próxima ação leva de volta ao **login**. No aceite de convite, senha só de
dígitos ou parecida com o nome de usuário é recusada com erro no campo. Em desenvolvimento nada
muda: `docker compose up --build` segue servindo em `19173`/`19000` sem redirect para https.

## Regressão crítica

`manage.py check --deploy --fail-level WARNING --tag security` sai limpo sob ambiente de produção e
falha com o ambiente de desenvolvimento, apontando um erro por defeito com id próprio; o
`manage.py check` comum continua limpo, e nenhum dos checks novos roda na suíte. Com
`SECURE_SSL_REDIRECT`, uma requisição http responde 301 para https, uma requisição com
`X-Forwarded-Proto: https` **e** o opt-in responde 200, e a mesma requisição **sem** o opt-in
responde 301 — é o que impede o cliente de mentir sobre o esquema. `SECURE_REDIRECT_EXEMPT` poupa a
rota listada. O header de HSTS traz `max-age` e `includeSubDomains`, traz `preload` só quando
pedido, e não existe com `SECURE_HSTS_SECONDS=0`. O cookie de sessão carrega o `max-age`
configurado e uma sessão vencida no banco responde 403 em `/auth/me/`. O aceite de convite recusa
com 400 e erro em `password` a senha numérica, a curta e a parecida com o nome de usuário, e aceita
a forte com 201. `REDIS_URL` troca o backend de cache e a ausência dele volta ao `LocMemCache`; a
query string do `DATABASE_URL` chega em `OPTIONS`, e `DB_SSLMODE` vence a URL. A imagem de produção
roda como uid 10001, tem `staticfiles/admin/css/base.css` e não tem `db.sqlite3`.
