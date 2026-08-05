# Portal Biahflow

Portal interno para conduzir oportunidades comerciais até a execução de projetos.

## Desenvolvimento

1. Copie `.env.example` para `.env` e substitua credenciais antes de qualquer ambiente compartilhado.
2. Execute `docker compose up --build`.
3. Crie o primeiro administrador com `docker compose exec api uv run python manage.py createsuperuser`.
4. Abra `http://localhost:19173` e entre pela tela de login.

Portas expostas pelo `docker compose` (faixa alta para evitar conflito com outros serviços):

| Serviço | URL |
| --- | --- |
| App (frontend) | `http://localhost:19173` |
| API `/api/v1/` | `http://localhost:19000/api/v1/` |
| Documentação da API | `http://localhost:19000/api/docs/` |
| Caixa de e-mail (Mailpit) | `http://localhost:19025` |

Para executar fora do Docker, use `uv sync` em `backend/` e `npm install` em `frontend/`. Nesse modo a API roda na porta padrão `8000` e o frontend em `5173` (o Vite faz proxy de `/api` para `http://localhost:8000`).

## Produção

Produção é outro compose: `docker compose -f docker-compose.prod.yml up -d --build` sobe nginx + gunicorn + Redis, sem dev server. O TLS é terminado por um proxy na frente. Configuração insegura não sobe — o container roda `manage.py check --deploy` antes do gunicorn. Variáveis obrigatórias, primeira subida, ordem de ativação do HSTS e rollback: [`docs/runbooks/producao.md`](docs/runbooks/producao.md).

As sondas são `GET /healthz` (o processo responde) e `GET /readyz` (banco e cache respondem; 503 quando não). Toda requisição carrega um `X-Request-ID` que volta na resposta e aparece no log do nginx, do gunicorn e da aplicação — em produção o log sai em JSON. Rastreamento de erro (Sentry) é opcional e nasce desligado. Como achar uma requisição pelo código, ligar o Sentry e quais alertas criar: [`docs/runbooks/monitoramento.md`](docs/runbooks/monitoramento.md).

O mesmo compose sobe um sidecar de **backup**: banco e documentos, agendado, com retenção e envio opcional para fora do host. A restauração não é promessa — o CI destrói banco e mídia e restaura a cada PR (`.github/scripts/backup-drill.sh`). Como conferir, restaurar e recuperar em um host novo: [`docs/runbooks/backup-e-restauracao.md`](docs/runbooks/backup-e-restauracao.md).

## Qualidade

Execute `cd backend && uv run pytest`, `cd backend && uv run mypy apps config`, `cd frontend && npm test`, `cd frontend && npm run build` e `cd frontend && npm run e2e` antes de abrir um pull request. Veja [AGENTS.md](AGENTS.md) e `docs/runbooks/`.
