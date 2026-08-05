# Sidecar de backup (FDD 021, ADR 0013).
#
# A base é a **mesma imagem do servidor** (postgres:16-alpine), e isso não é economia de linha:
# `pg_dump` recusa rodar contra um servidor de major maior que a dele, e a imagem da API é Debian
# bookworm, cujo `postgresql-client` é o 15. Trocar a major do `db` no compose obriga a trocar aqui
# junto — de propósito, porque o contrário é descobrir isso no dia do desastre.
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
