#!/usr/bin/env bash
# Teste de mesa da restauração (FDD 021, ADR 0013).
#
# Sobe a topologia **de produção de verdade** (`docker-compose.prod.yml`), põe dado real no banco e
# um documento na mídia, faz backup, **destrói as duas coisas**, restaura e confere que voltaram.
#
# Roda no CI a cada PR e localmente com `bash .github/scripts/backup-drill.sh`. É o que transforma
# "backup testado" em gate: script de backup que não restaura para de passar aqui, e não no dia do
# incidente.
#
# Usa um nome de projeto próprio (`biahflow-drill`) e volumes próprios: nunca toca em uma stack de
# produção ou de desenvolvimento que esteja no ar.

set -euo pipefail

cd "$(dirname "$0")/../.."

PROJECT="biahflow-drill"
ENV_FILE="$(mktemp -t biahflow-drill-env.XXXXXX)"
MARCA="Cliente do drill $(date -u +%s)"
CONTEUDO="documento-do-drill-$(date -u +%s)"

cat > "$ENV_FILE" <<EOF
POSTGRES_DB=biahflow
POSTGRES_USER=biahflow
POSTGRES_PASSWORD=drill-nao-e-segredo
DJANGO_SECRET_KEY=drill-nao-e-segredo
BACKUP_RETENTION_DAYS=14
EOF

compose() { docker compose -p "$PROJECT" -f docker-compose.prod.yml --env-file "$ENV_FILE" "$@"; }

limpar() {
    compose down -v --remove-orphans >/dev/null 2>&1 || true
    rm -f "$ENV_FILE"
}
trap limpar EXIT

passo() { echo; echo "=== $* ==="; }
falhar() { echo "DRILL REPROVADO: $*" >&2; exit 1; }

# ---------------------------------------------------------------------------
# Paridade de major entre o servidor e o sidecar (ADR 0013, emendada pela FDD 029).
#
# Até aqui a invariante era protegida por serem a **mesma imagem**, e o acoplamento ficava visível
# no compose. Desde que o `db` virou `pgvector/pgvector:pg16` e o sidecar ficou no alpine, "mesma
# imagem" deixou de valer — mas a invariante é a major, e `pg_dump` de major menor **recusa rodar**.
# Confere-se aqui porque uma nota de rodapé não impede ninguém de subir só um dos dois.
major_db="$(grep -oE 'image: .*postgres[^ ]*:(pg)?[0-9]+' docker-compose.prod.yml | grep -oE '[0-9]+$')"
major_sidecar="$(grep -oE '^FROM .*:(pg)?[0-9]+' ops/backup/Dockerfile | grep -oE '[0-9]+$')"
[ -n "$major_db" ] && [ -n "$major_sidecar" ] \
    || falhar "não consegui ler a major do Postgres (db='$major_db', sidecar='$major_sidecar')"
[ "$major_db" = "$major_sidecar" ] \
    || falhar "major divergente: db=$major_db, sidecar=$major_sidecar — pg_dump vai recusar (ADR 0013)"
echo "paridade de major conferida: db=$major_db, sidecar=$major_sidecar"

# ---------------------------------------------------------------------------
passo "1/7 · subindo banco e aplicando as migrações"
# `build` explícito: `compose run` **reaproveita a imagem existente** sem reconstruir, e sem isto o
# drill testa o script da execução anterior. Localmente ele chegou a aprovar um `restore.sh`
# sabotado justamente por isso — no CI o runner é limpo e o defeito ficaria invisível.
compose build api backup
compose up -d --wait db redis
compose run --rm --no-deps api-migrate

# ---------------------------------------------------------------------------
passo "2/7 · semeando estado real (um cliente no banco, um documento na mídia)"
compose run --rm --no-deps api python manage.py shell -c "
from apps.core.models import Client, User
dono = User.objects.create_user(username='drill', password='drill-nao-e-segredo', role='admin')
Client.objects.create(name='''$MARCA''', owner=dono)
# Um trecho de conhecimento com vetor de verdade (FDD 029): é o que prova que o dump e a
# restauração levam e trazem uma coluna \`vector\` inteira. Sem isto, quem descobre que o alvo
# de restauração precisa da extensão presente descobre às 4 da manhã.
from apps.core.models import KnowledgeArea, KnowledgeChunk, KnowledgePiece
area = KnowledgeArea.objects.first()
peca = KnowledgePiece.objects.create(area=area, title='Drill', source_path='drill.md')
KnowledgeChunk.objects.create(
    piece=peca, position=0, heading_path='Drill › Vetor', content='x', content_hash='h',
    embedding=[0.25] * 1536, embedding_model='text-embedding-3-small',
)
print('semeado')
"
compose run --rm --no-deps api sh -c \
    "mkdir -p /var/lib/biahflow/media/documents/2026/08 && \
     printf '%s' '$CONTEUDO' > /var/lib/biahflow/media/documents/2026/08/drill.txt"

# ---------------------------------------------------------------------------
passo "3/7 · backup"
# Sobe o **serviço**, não o script solto: é assim que produção funciona, e assim o drill cobre
# também o entrypoint — o crontab e a primeira cópia no boot, que é o que garante que uma
# instalação nova não fique 24 h sem backup.
compose up -d backup
for _ in $(seq 1 60); do
    compose exec -T backup test -f /backups/latest.json && break
    sleep 1
done
compose exec -T backup test -f /backups/latest.json \
    || falhar "o serviço backup subiu mas não produziu a primeira cópia"
compose exec -T backup sh -c 'ls -l /backups && cat /backups/latest.json'

# ---------------------------------------------------------------------------
passo "4/7 · destruindo o banco e os documentos"
# `WITH (FORCE)` derruba as conexões abertas: sem isso o DROP fica pendurado esperando.
compose exec -T db psql -U biahflow -d postgres \
    -c 'DROP DATABASE biahflow WITH (FORCE);' \
    -c 'CREATE DATABASE biahflow OWNER biahflow;'
compose exec -T backup sh -c 'rm -rf /media/documents'

# ---------------------------------------------------------------------------
passo "5/7 · conferindo que a destruição foi real"
# Sem este passo o drill mentiria: um restore que não faz nada "passa" se o dado nunca saiu.
tabela="$(compose exec -T db psql -U biahflow -d biahflow -tAc "SELECT to_regclass('public.core_client');" | tr -d '[:space:]')"
[ -z "$tabela" ] || falhar "a tabela core_client ainda existe depois do DROP DATABASE"
compose exec -T backup sh -c '[ ! -e /media/documents/2026/08/drill.txt ]' \
    || falhar "o documento ainda existe depois de apagar a mídia"
echo "banco vazio e mídia vazia — confirmado"

# ---------------------------------------------------------------------------
passo "6/7 · restaurando a partir da última cópia"
# Exatamente o comando que o runbook manda digitar às 4h.
compose exec -T backup restore.sh --latest --yes

# ---------------------------------------------------------------------------
passo "7/7 · conferindo que o dado voltou"
# `--no-deps` é essencial aqui: sem ele o `run api` acionaria o `api-migrate` e recriaria o schema,
# o que faria o drill passar mesmo com uma restauração que não restaurou nada.
compose run --rm --no-deps api python manage.py shell -c "
from apps.core.models import Client, KnowledgeChunk
assert Client.objects.filter(name='''$MARCA''').exists(), 'o cliente não voltou'
# A coluna \`vector\` inteira tem de voltar byte a byte (FDD 029). Um dump que perde o embedding
# restauraria um índice mudo: as buscas passariam a não achar nada, sem erro nenhum.
trecho = KnowledgeChunk.objects.get(heading_path='Drill › Vetor')
assert trecho.embedding is not None, 'o embedding voltou nulo'
assert len(trecho.embedding) == 1536, f'dimensão errada: {len(trecho.embedding)}'
assert abs(float(trecho.embedding[0]) - 0.25) < 1e-6, 'o valor do vetor mudou na restauração'
print('banco: cliente restaurado')
"
lido="$(compose exec -T backup cat /media/documents/2026/08/drill.txt)"
[ "$lido" = "$CONTEUDO" ] || falhar "o documento voltou diferente: '$lido' != '$CONTEUDO'"
echo "mídia: documento restaurado com o mesmo conteúdo"

# O carimbo que o `manage.py backup_status` lê precisa estar legível pelo processo da API, que
# monta o volume só-leitura e roda como outro usuário.
compose run --rm --no-deps api python manage.py backup_status

echo
echo "DRILL APROVADO: banco e documentos restaurados a partir do backup."
