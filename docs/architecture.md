# Arquitetura

O portal é composto por um frontend React/TypeScript e uma API Django REST, ambos consumindo PostgreSQL. Documentos são guardados em armazenamento S3-compatível; no desenvolvimento, o Docker sobe MinIO. A interface utiliza sessões seguras emitidas pela API e a API publica somente rotas sob `/api/v1/`.

## Fronteiras

- React: navegação, formulários, estados de tela e consumo da API.
- Django: regras de negócio, autorização, convites, persistência e entrega autorizada de arquivos.
- PostgreSQL: fonte de verdade transacional.
- S3/MinIO: blobs de documentos, sempre privados.

