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
RUN npm run build

FROM nginx:alpine AS prod
COPY nginx.conf /etc/nginx/conf.d/default.conf
COPY --from=build /app/dist /usr/share/nginx/html
EXPOSE 80
