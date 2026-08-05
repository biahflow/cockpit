# Arquitetura

O portal é composto por um frontend React/TypeScript e uma API Django REST, ambos consumindo
PostgreSQL. A interface utiliza sessões seguras emitidas pela API (cookie + CSRF, não tokens) e a
API publica somente rotas sob `/api/v1/`.

## Fronteiras

- React: navegação, formulários, estados de tela e consumo da API.
- Django: regras de negócio, autorização, convites, persistência e entrega autorizada de arquivos.
  Todo o domínio vive em um único app (`apps/core`), sem camada de serviço.
- PostgreSQL: fonte de verdade transacional (SQLite como fallback quando `DATABASE_URL` não está
  definida).
- Blobs de documentos: sempre privados, nunca com URL pública — servidos só após checagem de
  permissão (ADR 0002).

## Armazenamento de documentos

Hoje há dois destinos, escolhidos pela flag `GOOGLE_DRIVE_ENABLED`:

- **Google Drive** (Shared Drive, via service account) quando a flag está ligada — o arquivo não
  toca o disco da API; guardamos `drive_file_id` e `drive_link`.
- **Disco local** (`MEDIA_ROOT`) quando desligada, que é o padrão em desenvolvimento.

> O `docker-compose.yml` ainda sobe um **MinIO** e passa `MINIO_ENDPOINT` para a API, mas o
> `settings.py` não lê essa variável e não há cliente S3 nas dependências: o serviço está
> provisionado e **não conectado**. Migrar os blobs para S3/MinIO — ou remover o serviço do compose —
> continua pendente e merece um ADR quando for decidido.

## Integrações

Tudo que depende de terceiros fica **atrás de flag** e, desligado, o portal opera normalmente:
IA (OpenAI), Drive, Calendário (Google), assinatura eletrônica, sincronia de tarefas
(Linear/GitHub) e webhook do portal do cliente. As flags booleanas são alternáveis em runtime por
um admin em Configurações; o `.env` segue como default e casa dos segredos. Ver `docs/operacao.md`.
