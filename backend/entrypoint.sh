#!/bin/sh
# Entrada da imagem de produção (FDD 019).
#
# A recusa de configuração insegura acontece aqui, não no import de `config/settings.py`: um
# `raise` lá dentro mataria também `migrate`, `collectstatic` e `shell` — exatamente os comandos
# de que se precisa durante um incidente. Aqui, quem se recusa a subir é o servidor, e a mensagem
# do check diz qual variável falta.
#
# `--tag security` porque o `check --deploy` sem filtro também levanta avisos de schema do
# drf-spectacular, que não têm nada a ver com estar pronto para produção.
set -e

python manage.py check --deploy --fail-level WARNING --tag security

exec gunicorn -c gunicorn.conf.py config.wsgi:application
