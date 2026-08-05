#!/bin/sh
# Entrada do sidecar de backup (FDD 021).
#
# O agendamento mora aqui, e não em um cron do host: quem sobe a stack com `up -d` já tem backup,
# sem um passo manual que, esquecido, faz o portal ir a produção sem cópia nenhuma.

set -eu

BACKUP_ROOT="${BACKUP_ROOT:-/backups}"
BACKUP_CRON="${BACKUP_CRON:-15 3 * * *}"

mkdir -p "$BACKUP_ROOT"

# A saída do job vai para o stderr do PID 1, que é o que o runtime de container coleta (FDD 020).
# Sem isso ela morreria no spool de mail do busybox, que não existe nesta imagem.
echo "$BACKUP_CRON /usr/local/bin/backup.sh > /proc/1/fd/2 2>&1" > /etc/crontabs/root
chmod 600 /etc/crontabs/root

# Primeira cópia no boot, quando ainda não existe nenhuma: sem isto, uma instalação nova fica até
# 24 h sem backup — e a janela de maior risco de um portal é justamente a primeira semana.
#
# Só que **não** se o banco ainda estiver sem tabelas. É o cenário de recuperação em host novo: o
# volume de cópias nasce vazio, e um dump de banco vazio viraria "o mais recente" — isto é, o que
# um `restore.sh --latest` escolheria para restaurar. Copiar o nada por cima do desastre.
if [ -z "$(find "$BACKUP_ROOT" -maxdepth 1 -name 'db-*.dump' 2>/dev/null)" ]; then
    tabelas="$(psql -tAc \
        "SELECT count(*) FROM information_schema.tables WHERE table_schema = 'public';" \
        2>/dev/null || echo 0)"
    if [ "${tabelas:-0}" -gt 0 ]; then
        echo "backup: nenhuma cópia em $BACKUP_ROOT; rodando a primeira agora" >&2
        # Não pode derrubar o container: banco ainda subindo é motivo comum de falhar aqui, e o
        # cron tenta de novo no horário. Sidecar em laço de restart não gera backup nenhum.
        /usr/local/bin/backup.sh \
            || echo "backup: primeira cópia falhou; o cron tentará em $BACKUP_CRON" >&2
    else
        echo "backup: banco ainda sem tabelas; a primeira cópia sai no horário agendado" >&2
    fi
fi

echo "backup: agendado ($BACKUP_CRON), retenção ${BACKUP_RETENTION_DAYS:-14} dias" >&2
exec crond -f -l 8 -L /dev/stderr
