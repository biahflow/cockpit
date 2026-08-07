# Sidecar de backup (FDD 021, ADR 0013).
#
# A base **deixou de ser a mesma imagem do servidor**, e a diferença importa (FDD 029, emenda à
# ADR 0013): desde que o `db` virou `pgvector/pgvector:pg16`, aqui ficou `postgres:16-alpine`.
#
# O que a ADR 0013 protege é **paridade de major**, não identidade de imagem — `pg_dump` recusa
# rodar contra um servidor de major maior que a dele, e 16 contra 16 segue válido. O sidecar não
# precisa de pgvector: a extensão é do servidor, e o `pg_dump` emite `CREATE EXTENSION vector;`
# mais os valores como texto. Rebaseá-lo em Debian obrigaria a reescrever o `entrypoint.sh`, que é
# busybox (`/etc/crontabs/root`, `crond`), por benefício nenhum.
#
# Como "mesma imagem" deixou de ser o mecanismo, a paridade passou a ser **conferida por máquina**
# no `.github/scripts/backup-drill.sh` — que é mais forte do que depender de alguém reparar.
#
# Vem também do lado prático: o backup fica independente da imagem da aplicação. Se o build da API
# quebrar, ainda se restaura.
FROM postgres:16-alpine

# tar do GNU (o busybox não tem --numeric-owner nem lida bem com atributos estendidos) e rclone,
# que só é usado quando existe bucket configurado. tzdata para o cron respeitar TZ.
RUN apk add --no-cache tar rclone tzdata

COPY backup.sh restore.sh entrypoint.sh /usr/local/bin/
RUN chmod 755 /usr/local/bin/backup.sh /usr/local/bin/restore.sh /usr/local/bin/entrypoint.sh

# A imagem do Postgres tem ENTRYPOINT próprio (`docker-entrypoint.sh`), que existe para inicializar
# um cluster. Aqui não há cluster nenhum: zerar o entrypoint evita que um argumento inesperado caia
# na inicialização de banco.
ENTRYPOINT []
CMD ["/usr/local/bin/entrypoint.sh"]
