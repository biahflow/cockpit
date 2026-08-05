#!/bin/sh
# Restauração do portal: banco + documentos (FDD 021, ADR 0013).
#
#   restore.sh --latest --yes
#   restore.sh --from 20260805T031500Z --yes
#   restore.sh --latest --yes --only media
#
# Destrutivo por definição: o que está no banco agora é substituído pelo que está no dump. Por isso
# `--yes` é obrigatório e não tem default — ninguém restaura sem querer.
#
# **Pare o `api` antes** (`docker compose -f docker-compose.prod.yml stop api`). O passo a passo,
# com o que fazer em cada cenário, está em docs/runbooks/backup-e-restauracao.md.

set -eu

BACKUP_ROOT="${BACKUP_ROOT:-/backups}"
BACKUP_MEDIA_ROOT="${BACKUP_MEDIA_ROOT:-/media}"

target=""
confirmed="no"
only="all"
force_offsite="no"

log() {
    echo "$(date -u +%Y-%m-%dT%H:%M:%SZ) restore: $*" >&2
}

fail() {
    log "ERRO: $*"
    exit 1
}

usage() {
    cat >&2 <<'EOF'
uso: restore.sh (--latest | --from <timestamp>) --yes [--only db|media] [--offsite]

  --latest          usa a cópia mais recente disponível
  --from <ts>       usa a cópia de um carimbo específico (ex.: 20260805T031500Z)
  --yes             confirma que o destino vai ser sobrescrito (obrigatório)
  --only db|media   restaura só uma das duas metades (default: as duas)
  --offsite         baixa do bucket mesmo que exista cópia local
EOF
    exit 2
}

while [ $# -gt 0 ]; do
    case "$1" in
        --latest) target="latest" ;;
        --from) shift; [ $# -gt 0 ] || usage; target="$1" ;;
        --yes) confirmed="yes" ;;
        --only) shift; [ $# -gt 0 ] || usage; only="$1" ;;
        --offsite) force_offsite="yes" ;;
        -h|--help) usage ;;
        *) log "argumento desconhecido: $1"; usage ;;
    esac
    shift
done

[ -n "$target" ] || usage
[ "$confirmed" = "yes" ] || fail "faltou --yes: a restauração sobrescreve o banco e os documentos atuais"
case "$only" in all|db|media) ;; *) usage ;; esac

# ---------------------------------------------------------------------------
# De onde vem a cópia
# ---------------------------------------------------------------------------
# O caso real de desastre é justamente o host novo, com o volume de backup vazio: sem buscar no
# offsite, o script só saberia restaurar quando não fosse preciso.
setup_offsite() {
    [ -n "${BACKUP_S3_BUCKET:-}" ] || return 1
    RCLONE_S3_PROVIDER="${BACKUP_S3_PROVIDER:-Other}"
    RCLONE_S3_ACCESS_KEY_ID="${BACKUP_S3_ACCESS_KEY:-}"
    RCLONE_S3_SECRET_ACCESS_KEY="${BACKUP_S3_SECRET_KEY:-}"
    RCLONE_S3_ENDPOINT="${BACKUP_S3_ENDPOINT:-}"
    RCLONE_S3_REGION="${BACKUP_S3_REGION:-}"
    export RCLONE_S3_PROVIDER RCLONE_S3_ACCESS_KEY_ID RCLONE_S3_SECRET_ACCESS_KEY \
        RCLONE_S3_ENDPOINT RCLONE_S3_REGION
    remote=":s3:$BACKUP_S3_BUCKET"
    [ -n "${BACKUP_S3_PREFIX:-}" ] && remote="$remote/$BACKUP_S3_PREFIX"
    return 0
}

resolve_local() {
    if [ "$target" = "latest" ]; then
        basename "$(find "$BACKUP_ROOT" -maxdepth 1 -name 'db-*.dump' | sort | tail -n 1)" .dump \
            2>/dev/null | sed 's/^db-//'
    else
        echo "$target"
    fi
}

stamp=""
if [ "$force_offsite" = "no" ]; then
    stamp="$(resolve_local)"
    [ -f "$BACKUP_ROOT/db-$stamp.dump" ] || stamp=""
fi

if [ -z "$stamp" ]; then
    setup_offsite || fail "não há cópia em $BACKUP_ROOT e nenhum offsite configurado (BACKUP_S3_BUCKET)"
    log "buscando no offsite"
    if [ "$target" = "latest" ]; then
        stamp="$(rclone lsf "$remote/" --include 'db-*.dump' | sort | tail -n 1 | sed 's/^db-//;s/\.dump$//')"
        [ -n "$stamp" ] || fail "o bucket não tem nenhuma cópia"
    else
        stamp="$target"
    fi
    rclone copy "$remote/db-$stamp.dump" "$BACKUP_ROOT/" || fail "download do banco falhou"
    rclone copy "$remote/media-$stamp.tar.gz" "$BACKUP_ROOT/" || fail "download da mídia falhou"
fi

db_file="$BACKUP_ROOT/db-$stamp.dump"
media_file="$BACKUP_ROOT/media-$stamp.tar.gz"
log "restaurando a partir de $stamp"

# ---------------------------------------------------------------------------
# Banco
# ---------------------------------------------------------------------------
if [ "$only" = "all" ] || [ "$only" = "db" ]; then
    [ -f "$db_file" ] || fail "$db_file não existe"

    # Conexão aberta segura lock, e o DROP SCHEMA ficaria pendurado em silêncio até alguém
    # perceber. O runbook manda parar o `api`; isto aqui é a rede de proteção para o que sobrou.
    psql -v ON_ERROR_STOP=1 -d postgres -q -c \
        "SELECT pg_terminate_backend(pid) FROM pg_stat_activity
         WHERE datname = '$PGDATABASE' AND pid <> pg_backend_pid();" > /dev/null

    # Terra arrasada em vez de `pg_restore --clean`: o --clean deixa passar objeto que existe hoje
    # e não existia no dump, e a restauração tem de devolver exatamente o estado da cópia.
    psql -v ON_ERROR_STOP=1 -q -c 'DROP SCHEMA IF EXISTS public CASCADE; CREATE SCHEMA public;'

    # --exit-on-error porque o default do pg_restore é seguir em frente contando erros no fim:
    # uma restauração pela metade que "terminou bem" é o pior resultado possível aqui.
    pg_restore --no-owner --no-privileges --exit-on-error --dbname "$PGDATABASE" "$db_file" \
        || fail "pg_restore falhou"
    log "banco restaurado"
fi

# ---------------------------------------------------------------------------
# Documentos
# ---------------------------------------------------------------------------
if [ "$only" = "all" ] || [ "$only" = "media" ]; then
    [ -f "$media_file" ] || fail "$media_file não existe"
    [ -d "$BACKUP_MEDIA_ROOT" ] || fail "$BACKUP_MEDIA_ROOT não está montado"

    # Extrai primeiro, troca depois. Apagar antes deixaria o portal sem os arquivos que ele ainda
    # tinha se o tar falhasse no meio — e no meio de um desastre é exatamente quando falha.
    staging="$BACKUP_MEDIA_ROOT/.restore-$$"
    rm -rf "$staging"
    mkdir -p "$staging"
    tar -xzf "$media_file" -C "$staging" || { rm -rf "$staging"; fail "extração da mídia falhou"; }

    find "$BACKUP_MEDIA_ROOT" -mindepth 1 -maxdepth 1 -not -name ".restore-$$" -exec rm -rf {} +
    for entry in "$staging"/* "$staging"/.[!.]*; do
        [ -e "$entry" ] || continue
        mv "$entry" "$BACKUP_MEDIA_ROOT/"
    done
    rmdir "$staging"

    # O dono vem do diretório montado, não do arquivo tar: restaurar em outro host pode cair em
    # um mapeamento de uid diferente, e mídia que o gunicorn não consegue escrever quebra o upload.
    owner="$(stat -c '%u:%g' "$BACKUP_MEDIA_ROOT")"
    find "$BACKUP_MEDIA_ROOT" -mindepth 1 -exec chown "$owner" {} +
    log "documentos restaurados"
fi

log "concluído ($stamp)"
