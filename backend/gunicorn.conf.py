"""Configuração do gunicorn em produção (FDD 019).

Arquivo em vez de um `CMD` de 200 caracteres: aqui cada número pode ser explicado.
Não é type-checado (o mypy roda só em `apps` e `config`) nem importado pela aplicação.
"""

import os

bind = "0.0.0.0:8000"

# Regra usual é 2×CPU+1. Fica por env porque quem dimensiona é quem conhece a máquina — e porque
# o número de workers multiplica o teto de requisição quando o cache não é compartilhado (ADR 0009).
workers = int(os.getenv("GUNICORN_WORKERS", "3"))

# Requisição de IA e geração de proposta são as mais lentas do portal; 30s (o default) corta.
timeout = int(os.getenv("GUNICORN_TIMEOUT", "60"))
graceful_timeout = 30

# Recicla o worker periodicamente: qualquer vazamento de memória vira um problema limitado em vez
# de crescente. O jitter evita que todos reciclem na mesma requisição.
max_requests = 1000
max_requests_jitter = 100

# stdout/stderr, que é onde o runtime de container coleta log.
accesslog = "-"
errorlog = "-"
