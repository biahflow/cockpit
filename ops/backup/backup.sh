#!/bin/sh
# Backup do portal: banco + documentos (FDD 021, ADR 0013).
#
# Roda no sidecar `backup` do docker-compose.prod.yml, que é construído da **mesma major** do
# Postgres do servidor: `pg_dump` mais antigo que o servidor se recusa a rodar, e é por isso que
# esta ferramenta não mora na imagem da API (Debian bookworm, cujo postgresql-client é o 15).
#
# Conexão pelas variáveis padrão do libpq (PGHOST, PGUSER, PGPASSWORD, PGDATABASE): senha em
# variável e nunca na linha de comando, que qualquer `ps` no host mostraria.

set -eu

BACKUP_ROOT="${BACKUP_ROOT:-/backups}"
BACKUP_MEDIA_ROOT="${BACKUP_MEDIA_ROOT:-/media}"
BACKUP_RETENTION_DAYS="${BACKUP_RETENTION_DAYS:-14}"

# Todo dump nasce só para o dono. É o banco inteiro em claro: proposta, contrato, dado de todo
# cliente. O volume é tão sensível quanto o Postgres.
umask 077

log() {
    echo "$(date -u +%Y-%m-%dT%H:%M:%SZ) backup: $*" >&2
}

fail() {
    log "ERRO: $*"
    exit 1
}

timestamp="$(date -u +%Y%m%dT%H%M%SZ)"
db_file="$BACKUP_ROOT/db-$timestamp.dump"
media_file="$BACKUP_ROOT/media-$timestamp.tar.gz"

[ -d "$BACKUP_ROOT" ] || fail "BACKUP_ROOT ($BACKUP_ROOT) não existe"

# `.tmp` primeiro, `mv` no fim. O `mv` é atômico dentro do mesmo sistema de arquivos, então um
# backup interrompido (OOM, host reiniciado, disco cheio) nunca aparece como candidato a "mais
# recente" — que é justamente o que a restauração vai pegar, às 4h, sem ninguém conferindo.
log "iniciando $timestamp"

# --format=custom: comprimido, e o pg_restore consegue restaurar tabela por tabela se for preciso.
# Um .sql de texto só serve para `psql < arquivo`, tudo ou nada.
pg_dump --format=custom --file="$db_file.tmp" || fail "pg_dump falhou"
mv "$db_file.tmp" "$db_file"
log "banco: $(wc -c < "$db_file") bytes"

# Os documentos são metade do estado: sem eles, restaurar o banco devolve um portal cheio de
# registros apontando para arquivos que não existem mais.
if [ -d "$BACKUP_MEDIA_ROOT" ]; then
    tar -czf "$media_file.tmp" -C "$BACKUP_MEDIA_ROOT" . || fail "tar da mídia falhou"
else
    log "AVISO: $BACKUP_MEDIA_ROOT não existe; gerando arquivo de mídia vazio"
    tar -czf "$media_file.tmp" -T /dev/null
fi
mv "$media_file.tmp" "$media_file"
log "mídia: $(wc -c < "$media_file") bytes"

# ---------------------------------------------------------------------------
# Offsite (opt-in)
# ---------------------------------------------------------------------------
# Sem BACKUP_S3_BUCKET este bloco inteiro não existe. Backup no mesmo host não é backup — mas
# exigir credencial de nuvem para a primeira cópia existir travaria o caminho simples, e um
# backup local é melhor que nenhum.
offsite="false"
if [ -n "${BACKUP_S3_BUCKET:-}" ]; then
    # Credencial por ambiente do rclone, não em argumento nem em arquivo de configuração.
    RCLONE_S3_PROVIDER="${BACKUP_S3_PROVIDER:-Other}"
    RCLONE_S3_ACCESS_KEY_ID="${BACKUP_S3_ACCESS_KEY:-}"
    RCLONE_S3_SECRET_ACCESS_KEY="${BACKUP_S3_SECRET_KEY:-}"
    RCLONE_S3_ENDPOINT="${BACKUP_S3_ENDPOINT:-}"
    RCLONE_S3_REGION="${BACKUP_S3_REGION:-}"
    export RCLONE_S3_PROVIDER RCLONE_S3_ACCESS_KEY_ID RCLONE_S3_SECRET_ACCESS_KEY \
        RCLONE_S3_ENDPOINT RCLONE_S3_REGION

    remote=":s3:$BACKUP_S3_BUCKET"
    [ -n "${BACKUP_S3_PREFIX:-}" ] && remote="$remote/$BACKUP_S3_PREFIX"

    log "enviando para $BACKUP_S3_BUCKET"
    rclone copy "$db_file" "$remote/" || fail "envio do banco para o offsite falhou"
    rclone copy "$media_file" "$remote/" || fail "envio da mídia para o offsite falhou"
    offsite="true"

    # A mesma retenção do lado de lá. Regra de ciclo de vida no bucket é melhor (sobrevive a este
    # container ter sido esquecido), e está no runbook — isto aqui é o piso.
    if [ "$BACKUP_RETENTION_DAYS" -gt 0 ]; then
        rclone delete --min-age "${BACKUP_RETENTION_DAYS}d" "$remote/" || \
            log "AVISO: poda do offsite falhou (a cópia nova já subiu)"
    fi
fi

# ---------------------------------------------------------------------------
# Retenção local
# ---------------------------------------------------------------------------
# Só depois do sucesso acima: a poda nunca pode rodar em um ciclo que não produziu cópia nova.
# `0` desliga. E nada é apagado enquanto existir só um par — um relógio errado no host não pode
# valer "apague tudo o que você tem".
if [ "$BACKUP_RETENTION_DAYS" -gt 0 ]; then
    total="$(find "$BACKUP_ROOT" -maxdepth 1 -name 'db-*.dump' | wc -l)"
    if [ "$total" -gt 1 ]; then
        find "$BACKUP_ROOT" -maxdepth 1 -name 'db-*.dump' -mtime "+$BACKUP_RETENTION_DAYS" \
            -not -name "db-$timestamp.dump" -print | while read -r old; do
            old_ts="$(basename "$old" .dump | sed 's/^db-//')"
            log "podando $old_ts"
            rm -f "$BACKUP_ROOT/db-$old_ts.dump" "$BACKUP_ROOT/media-$old_ts.tar.gz"
        done
    fi
fi

# ---------------------------------------------------------------------------
# Carimbo
# ---------------------------------------------------------------------------
# Escrito por último, e só no caminho feliz: é ele que o `manage.py backup_status` lê para dizer
# se o backup parou de rodar. Um carimbo gravado antes do fim faria o alerta calar justamente
# quando o backup começa a falhar.
cat > "$BACKUP_ROOT/latest.json.tmp" <<EOF
{
  "timestamp": "$timestamp",
  "finished_at": "$(date -u +%Y-%m-%dT%H:%M:%SZ)",
  "db_bytes": $(wc -c < "$db_file"),
  "media_bytes": $(wc -c < "$media_file"),
  "offsite": $offsite
}
EOF
mv "$BACKUP_ROOT/latest.json.tmp" "$BACKUP_ROOT/latest.json"
# O carimbo é lido pelo `api`, que roda como outro usuário e monta este volume só-leitura.
chmod 644 "$BACKUP_ROOT/latest.json"

log "concluído $timestamp (offsite: $offsite)"
