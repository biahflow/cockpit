# Portal Biahflow

Portal interno para conduzir oportunidades comerciais até a execução de projetos.

## Desenvolvimento

O caminho mais simples é via Docker Compose:

```bash
cp .env.example .env
docker compose up --build
```

As migrações rodam automaticamente. Depois, em outro terminal, crie o administrador:

```bash
docker compose exec api uv run python manage.py createsuperuser
```

Informe usuário, e-mail e senha quando solicitado. Para criar sem interação, de forma idempotente:

```bash
docker compose exec \
  -e DJANGO_SUPERUSER_USERNAME=admin \
  -e DJANGO_SUPERUSER_EMAIL=admin@local.test \
  -e DJANGO_SUPERUSER_PASSWORD='SenhaLocal123!' \
  api uv run python manage.py bootstrap_admin --exigir
```

Use somente credenciais locais como as do exemplo; substitua-as antes de qualquer ambiente
compartilhado.

O `createsuperuser` cria um superusuário que já acessa o menu completo: o SPA usa `is_admin`, o
mesmo predicado de autorização do backend, e não exige ajuste manual de `User.role`. O percurso
completo do produto (cliente → oportunidade → conversão → projeto → equipe → indicadores) está em
[`docs/runbooks/roteiro-de-teste.md`](docs/runbooks/roteiro-de-teste.md).

Acesse:

| Serviço | URL |
| --- | --- |
| App (frontend) | `http://localhost:19173` |
| API `/api/v1/` | `http://localhost:19000/api/v1/` |
| Documentação da API | `http://localhost:19000/api/docs/` |
| Caixa de e-mail (Mailpit) | `http://localhost:19025` |

Para subir em background e acompanhar os serviços:

```bash
docker compose up -d --build
docker compose logs -f api web
```

Não existe um comando de seed completo com dados de demonstração. As migrações já semeiam
estruturas básicas, como pipeline, jornada e níveis de serviço; clientes, oportunidades e projetos
podem ser criados pela interface.

Sem Docker, opcionalmente:

```bash
cd backend
uv sync
uv run python manage.py migrate
uv run python manage.py runserver
```

Em outro terminal:

```bash
cd frontend
npm install
npm run dev
```

Nesse modo, API e frontend ficam em `http://localhost:8000` e `http://localhost:5173`,
respectivamente. O Vite faz proxy de `/api` para a API local.

## Produção

Produção é outro compose: `docker compose -f docker-compose.prod.yml up -d --build` sobe nginx + gunicorn + Redis, sem dev server. O TLS é terminado por um proxy na frente. Configuração insegura não sobe — o container roda `manage.py check --deploy` antes do gunicorn. Variáveis obrigatórias, primeira subida, ordem de ativação do HSTS e rollback: [`docs/runbooks/producao.md`](docs/runbooks/producao.md).

As sondas são `GET /healthz` (o processo responde) e `GET /readyz` (banco e cache respondem; 503 quando não). Toda requisição carrega um `X-Request-ID` que volta na resposta e aparece no log do nginx, do gunicorn e da aplicação — em produção o log sai em JSON. Rastreamento de erro (Sentry) é opcional e nasce desligado. Como achar uma requisição pelo código, ligar o Sentry e quais alertas criar: [`docs/runbooks/monitoramento.md`](docs/runbooks/monitoramento.md).

O mesmo compose sobe um sidecar de **backup**: banco e documentos, agendado, com retenção e envio opcional para fora do host. A restauração não é promessa — o CI destrói banco e mídia e restaura a cada PR (`.github/scripts/backup-drill.sh`). Como conferir, restaurar e recuperar em um host novo: [`docs/runbooks/backup-e-restauracao.md`](docs/runbooks/backup-e-restauracao.md).

E um serviço **`scheduler`**, que roda o trabalho periódico da aplicação: digest diário, sincronia de calendário e a conferência que dispara o alerta de backup velho. Antes dele os três dependiam de um cron montado à mão, que ninguém montava — ver [`docs/fdd/023-trabalho-periodico-agendado.md`](docs/fdd/023-trabalho-periodico-agendado.md).

## Qualidade

Selecione e execute os perfis aplicáveis descritos em
[`docs/engineering-os/project-context.md`](docs/engineering-os/project-context.md); a fonte
executável da suíte completa é [`.github/workflows/quality.yml`](.github/workflows/quality.yml).
Veja também [AGENTS.md](AGENTS.md) e `docs/runbooks/`.

O `npm run e2e` roda quatro projetos do Playwright: `e2e` (fluxo, desktop) e `mobile`/`tablet`/`desktop`, que percorrem a **matriz** de 17 telas — varredura do axe nas tags WCAG A e AA, ausência de rolagem horizontal, navegação alcançável, alvo de toque e foco de teclado visível (FDD 022). Tela nova entra por uma linha em `frontend/e2e/matrix.ts`. O `pytest` inclui o **orçamento de query** dos agregadores, que reprova N+1 comparando a mesma rota com duas bases de tamanhos diferentes (ADR 0014). Teste de carga com k6 é procedimento operado, fora do CI: [`docs/runbooks/testes-de-carga.md`](docs/runbooks/testes-de-carga.md).
