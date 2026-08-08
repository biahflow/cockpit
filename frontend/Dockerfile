# Desenvolvimento roda o dev server do Vite (o compose sobrescreve o `command`); produção assa o
# bundle e serve por nginx. Um dev server atrás de um domínio não é deploy. Ver FDD 019.

FROM node:24-alpine AS dev
WORKDIR /app
COPY package*.json ./
RUN npm install
COPY . .
EXPOSE 5173

FROM node:24-alpine AS build
WORKDIR /app
# `npm ci` (e não `install`) para honrar o lockfile — a mesma razão pela qual a FDD 017 fixou as
# 17 dependências declaradas como "latest".
COPY package*.json ./
RUN npm ci
COPY . .
# Sentry do SPA (FDD 020): o Vite substitui `import.meta.env.VITE_*` por literal em tempo de
# build, então isto precisa ser build arg — não dá para injetar por variável de ambiente do
# container depois. Vazio (o default) = rastreamento de erro desligado e nenhum byte do SDK no
# bundle. `SENTRY_AUTH_TOKEN` é opt-in e liga o upload de sourcemap.
ARG VITE_SENTRY_DSN=""
ARG VITE_SENTRY_ENVIRONMENT=""
ARG VITE_SENTRY_RELEASE=""
ARG SENTRY_AUTH_TOKEN=""
ARG SENTRY_ORG=""
ARG SENTRY_PROJECT=""
ENV VITE_SENTRY_DSN=$VITE_SENTRY_DSN \
    VITE_SENTRY_ENVIRONMENT=$VITE_SENTRY_ENVIRONMENT \
    VITE_SENTRY_RELEASE=$VITE_SENTRY_RELEASE \
    SENTRY_AUTH_TOKEN=$SENTRY_AUTH_TOKEN \
    SENTRY_ORG=$SENTRY_ORG \
    SENTRY_PROJECT=$SENTRY_PROJECT
RUN npm run build

FROM nginx:alpine AS prod
# `templates/` e não `conf.d/`: a imagem oficial expande `${VAR}` daqui para lá no boot
# (`/docker-entrypoint.d/20-envsubst-on-templates.sh`). É o que permite ao mesmo arquivo servir o
# compose e o Cloud Run, que têm porta, nome de upstream e resolvedor de DNS diferentes.
COPY nginx.conf.template /etc/nginx/templates/default.conf.template
COPY --from=build /app/dist /usr/share/nginx/html

# Os defaults reproduzem o compose, para que `docker compose up` continue funcionando sem
# ninguém declarar nada. O Cloud Run sobrescreve `PORT` sozinho, e o Terraform injeta
# `API_UPSTREAM` e `DNS_RESOLVER`.
ENV PORT=8080 \
    API_UPSTREAM=http://api:8000 \
    DNS_RESOLVER=127.0.0.11

# 8080 e não 80: é a porta que o Terraform de HML declara para este serviço, e era a divergência
# que faria a sonda de inicialização do Cloud Run reprovar toda revisão (ADR 0046).
EXPOSE 8080
