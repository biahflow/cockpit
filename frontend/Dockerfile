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
COPY nginx.conf /etc/nginx/conf.d/default.conf
COPY --from=build /app/dist /usr/share/nginx/html
EXPOSE 80
