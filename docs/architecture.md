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

- **Google Drive** (pasta ou Shared Drive; auth por ADC/Workload Identity ou OAuth, ADR 0016 —
  nunca por chave de conta de serviço) quando a flag está ligada — o arquivo não
  toca o disco da API; guardamos `drive_file_id` e `drive_link`.
- **Disco local** (`MEDIA_ROOT`) quando desligada, que é o padrão em desenvolvimento. Em produção
  `MEDIA_ROOT` precisa ser um volume próprio (`DJANGO_MEDIA_ROOT`): dentro da árvore de código, um
  deploy leva os documentos embora. Como consequência, storage local restringe a API a uma réplica —
  escalar exige volume compartilhado ou o Drive ligado (ADR 0011).

> O `docker-compose.yml` ainda sobe um **MinIO** e passa `MINIO_ENDPOINT` para a API, mas o
> `settings.py` não lê essa variável e não há cliente S3 nas dependências: o serviço está
> provisionado e **não conectado**. Migrar os blobs para S3/MinIO — ou remover o serviço do compose —
> continua pendente e merece um ADR quando for decidido.

## Topologia em produção

Desenvolvimento roda `runserver` + dev server do Vite; produção é outro compose
(`docker-compose.prod.yml`, ADR 0011):

```
internet → [terminador de TLS, fora do compose] → [nginx: SPA + proxy] → [gunicorn] → [postgres]
                                                                              ↓
                                                                      [redis: teto de requisição]
```

O TLS termina antes do compose, e o Django só acredita no `X-Forwarded-Proto` com opt-in explícito.
O nginx é a borda **da aplicação**, não o terminador. Ver `docs/runbooks/producao.md`.

**Backup** (FDD 021, ADR 0013): um sidecar `backup`, construído da **mesma imagem do `db`** porque
`pg_dump` de major menor recusa rodar, copia banco (`pg_dump --format=custom`) e documentos (`tar`
do `MEDIA_ROOT`) em volume próprio, com retenção por dias e envio offsite opt-in para storage
compatível com S3. A aplicação não faz backup — só lê o carimbo da última cópia
(`manage.py backup_status`) para o alerta. A restauração é exercitada **a cada PR** por
`.github/scripts/backup-drill.sh`, que destrói banco e mídia e traz os dois de volta. Ver
`docs/runbooks/backup-e-restauracao.md`.

**Trabalho periódico** (FDD 023, ADR 0015): um serviço `scheduler` — a **mesma imagem do `api`**,
outro processo — roda o digest diário (FDD 010), a sincronia de calendário (FDD 012) e a
conferência de backup (FDD 021). Processo separado e não thread do gunicorn porque três workers
mandariam o digest em triplicata. O que venceu é decidido em `apps/core/scheduler.py` contra um
carimbo durável no banco (`ScheduledJobRun`), e não em memória: sem ele, um restart logo depois do
digest o reenviaria a todos. Falha é isolada por job e sai como `ERROR`, que vira evento no Sentry
— é por aí que o alerta de backup velho dispara.

**Observabilidade** (FDD 020, ADR 0012): o `X-Request-ID` nasce no nginx e atravessa todo o
caminho — log da borda, access log do gunicorn, log estruturado da aplicação, tag no Sentry e o
header da resposta que o SPA mostra na tela de erro. `/healthz` e `/readyz` respondem em middleware,
antes de `ALLOWED_HOSTS` e do redirect de https, e ficam fora do `/api/v1/` por não serem contrato
de API. Ver `docs/runbooks/monitoramento.md`.

## Integrações

Tudo que depende de terceiros fica **atrás de flag** e, desligado, o portal opera normalmente:
IA (OpenAI), Drive, Calendário (Google), assinatura eletrônica, notificações por e-mail, sincronia
de tarefas (Linear/GitHub) e webhook do portal do cliente. **As sete são alternáveis em runtime** por
um admin em Configurações; o `.env` segue como default e casa dos segredos.

`flags.is_enabled()` é `configured() and desired()`: a intenção declarada (override do admin ou
default do ambiente) só vale se as credenciais exigidas estiverem no ambiente — nenhuma flag liga
sem elas, nem por toggle nem por `.env` (ADR 0018). `email` e `esign` nascem ligadas; as demais,
desligadas. A pergunta que a flag **não** responde — "a credencial funciona?" — é da sonda do
`manage.py check_integrations` (FDD 024). Ver `docs/operacao.md`.
