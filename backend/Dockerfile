# Dois estágios com a mesma base: desenvolvimento monta a árvore de código por bind mount e
# sobrescreve o `command` pelo compose; produção assa o código, coleta o estático e roda gunicorn
# sem privilégio. Ver FDD 019 e ADR 0011.

FROM python:3.12-slim AS base
# `UV_CACHE_DIR` em /tmp para o `uv sync` do compose de desenvolvimento continuar funcionando
# quando o processo não é root.
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 UV_CACHE_DIR=/tmp/uv-cache
WORKDIR /app
RUN pip install --no-cache-dir uv
# O `uv.lock` entra na imagem: sem ele, `uv sync` resolvia versão arbitrária a cada build e a
# imagem deixava de ser reprodutível.
COPY pyproject.toml uv.lock ./
RUN uv sync --no-dev --frozen

FROM base AS dev
EXPOSE 8000

FROM base AS prod
# Sem `uv run`: o venv entra no PATH, então `python`, `gunicorn` e `manage.py` resolvem direto.
ENV PATH="/app/.venv/bin:$PATH"
COPY . .
# Não precisa de banco, e o segredo de desenvolvimento serve para esta única finalidade.
RUN python manage.py collectstatic --noinput
# O diretório de mídia precisa existir na **imagem**, com o dono certo: um volume nomeado vazio
# herda o conteúdo e a propriedade do diretório que ele cobre. Sem isto o Docker cria o ponto de
# montagem como root, o processo roda como `app` e todo upload de documento falha com "permission
# denied". `/app/media` é o default de `MEDIA_ROOT`; `/var/lib/biahflow/media` é o que o
# `docker-compose.prod.yml` monta. Quem apontar `DJANGO_MEDIA_ROOT` para outro caminho é
# responsável pela propriedade dele (ver docs/runbooks/producao.md).
RUN useradd --uid 10001 --no-create-home --shell /usr/sbin/nologin app \
    && mkdir -p /app/media /var/lib/biahflow/media \
    && chown -R app:app /app /var/lib/biahflow
USER app
EXPOSE 8000
CMD ["sh", "./entrypoint.sh"]
