# Runbook — backup e restauração

O que é copiado, para onde, por quanto tempo, e **como trazer de volta** (FDD 021, ADR 0013).
Subida e transporte estão em `producao.md`; log, sondas e alertas, em `monitoramento.md`.

A pergunta que tudo aqui existe para responder: **o host pegou fogo às 4h — o que eu rodo?**

## O que é copiado

| O quê | De onde | Para onde | Formato |
| --- | --- | --- | --- |
| Banco | serviço `db` | `backup_data:/backups/db-<carimbo>.dump` | `pg_dump --format=custom` |
| Documentos | volume `media_data` | `backup_data:/backups/media-<carimbo>.tar.gz` | `tar -czf` |

O carimbo é UTC (`20260805T031500Z`) e é o mesmo nos dois arquivos — eles andam em par, e
restaurar só um é quase sempre errado: o banco tem os registros que apontam para os arquivos.

Quem faz é o serviço `backup`, um sidecar construído da **mesma imagem do `db`**
(`postgres:16-alpine`), com `crond` próprio. Sobe junto com a stack: **quem faz `up -d` já tem
backup**, e a primeira cópia sai no boot, sem esperar o horário.

## Conferir que está funcionando

```bash
# de quando é a última cópia, quanto ocupa e se saiu do host
docker compose -f docker-compose.prod.yml exec api python manage.py backup_status

# o que existe no volume
docker compose -f docker-compose.prod.yml exec backup ls -lh /backups

# o log do sidecar (uma linha por ciclo)
docker compose -f docker-compose.prod.yml logs backup
```

`backup_status` sai com **código 1** quando não há cópia ou quando a última passou de
`BACKUP_MAX_AGE_HOURS` (26 h). É esse código que o alerta lê — a regra está em `monitoramento.md`.

Forçar uma cópia agora (antes de uma migração arriscada, por exemplo):

```bash
docker compose -f docker-compose.prod.yml exec backup backup.sh
```

## Ajustes

Tudo pelo `.env`, aplicado com `up -d backup`:

| Variável | Default | O que faz |
| --- | --- | --- |
| `BACKUP_CRON` | `15 3 * * *` | quando rodar (5 campos, fuso do container; use `TZ`) |
| `BACKUP_RETENTION_DAYS` | `14` | por quantos dias guardar; `0` desliga a poda |
| `BACKUP_MAX_AGE_HOURS` | `26` | a partir de quando o `backup_status` reprova |
| `BACKUP_S3_*` | vazio | envio offsite (abaixo) |

A poda **só roda depois de uma cópia nova bem-sucedida** e nunca apaga a última que restou.

## Offsite (recomendado)

Cópia que mora no mesmo host morre com o host. Qualquer storage compatível com S3 serve — AWS,
Backblaze B2, Cloudflare R2, MinIO:

```
BACKUP_S3_BUCKET=biahflow-backups
BACKUP_S3_PREFIX=producao
BACKUP_S3_ENDPOINT=              # vazio = AWS S3
BACKUP_S3_REGION=us-east-1
BACKUP_S3_ACCESS_KEY=...
BACKUP_S3_SECRET_KEY=...
```

`docker compose -f docker-compose.prod.yml up -d backup`, e o próximo ciclo já sobe.

**O dump é o banco inteiro em claro** — proposta, contrato, dado de todo cliente. Portanto:

1. credencial **só deste bucket**, e de mais nada;
2. **versionamento ligado** e, se o provedor tiver, **object lock**: é o que sobrevive a alguém
   com a credencial rodando um `delete`;
3. **regra de ciclo de vida** no bucket com a mesma retenção (o script também poda, mas a regra do
   bucket sobrevive a este container ter sido esquecido);
4. criptografia em repouso do provedor ligada — o portal não criptografa o dump (ADR 0013).

## Restaurar

> **Destrutivo.** O que está no banco agora é substituído pelo que está na cópia. Por isso `--yes`
> é obrigatório.

**1. Pare quem escreve.** Conexão viva segura lock, e requisição em voo veria um banco sem tabelas:

```bash
docker compose -f docker-compose.prod.yml stop web api
```

**2. Restaure** (banco + documentos, da cópia mais recente):

```bash
docker compose -f docker-compose.prod.yml exec backup restore.sh --latest --yes
```

**3. Suba de volta e confira:**

```bash
docker compose -f docker-compose.prod.yml up -d api web
curl -s https://SEU-DOMINIO/readyz
```

Variações:

```bash
# de uma cópia específica
restore.sh --from 20260805T031500Z --yes

# só uma das metades (raro; normalmente as duas andam juntas)
restore.sh --latest --yes --only media

# forçar a busca no bucket, mesmo havendo cópia local
restore.sh --latest --yes --offsite
```

### Host novo, do zero

O caso real de desastre. Com offsite configurado, o volume local está vazio e o `restore.sh`
**busca no bucket sozinho**:

```bash
git clone <repo> && cd biahflow-portal
cp .env-do-cofre .env                       # inclui as BACKUP_S3_*
docker compose -f docker-compose.prod.yml up -d --build db redis
docker compose -f docker-compose.prod.yml run --rm api-migrate
docker compose -f docker-compose.prod.yml run --rm backup restore.sh --latest --yes --offsite
docker compose -f docker-compose.prod.yml up -d      # aqui, sim, o sidecar sobe
```

Duas coisas importam nessa ordem:

- **o sidecar `backup` sobe por último.** Ele faz uma cópia no boot quando não encontra nenhuma, e
  em um host novo essa cópia seria do banco recém-restaurado — ou, pior, do banco ainda vazio, que
  passaria a ser "a mais recente". (O sidecar se protege: pula a cópia de boot enquanto o banco não
  tem tabelas. A ordem acima é o cinto além do suspensório.) Por isso `run --rm`, que executa só o
  comando dado, e não o agendador;
- **`--offsite` é explícito.** Sem ele o script usaria uma cópia local, se houvesse — e num host de
  recuperação a cópia local é justamente a que não se quer.

O `api-migrate` cria um schema que a restauração vai substituir inteiro — ele está aí só para o
banco existir em um estado conhecido.

## Teste de mesa

O repositório restaura **a cada PR**: `.github/scripts/backup-drill.sh` sobe a topologia de
produção, semeia um cliente e um documento, faz backup, **destrói banco e mídia**, restaura e
confere que voltaram. Rode localmente quando mexer nos scripts:

```bash
bash .github/scripts/backup-drill.sh
```

Ele usa nome de projeto e volumes próprios (`biahflow-drill`): não encosta em produção nem no seu
ambiente de desenvolvimento.

Ainda assim, faça o drill **no ambiente de verdade** de tempos em tempos (a cada trimestre é um bom
ritmo), de preferência restaurando em um host descartável a partir do offsite. O CI prova que o
script funciona; só o drill real prova que **a sua credencial, o seu bucket e a sua cópia**
funcionam.

## Quando algo dá errado

| Sintoma | Causa provável |
| --- | --- |
| `backup_status` diz "Nenhum backup registrado" | o sidecar nunca completou um ciclo: `logs backup` diz por quê (banco fora, disco cheio) |
| `backup_status` diz "BACKUP_ROOT não está configurado" | está rodando fora do compose de produção, ou o volume não foi montado no `api` |
| backup para de rodar depois de trocar a major do Postgres | o `ops/backup/Dockerfile` continua na major antiga; `pg_dump` menor que o servidor recusa rodar |
| `restore.sh` diz "faltou --yes" | é de propósito: ninguém restaura sem querer |
| restauração pendurada sem mensagem | sobrou conexão no banco; pare `api` e `web` (o script derruba as que sobram, mas não o que reconecta) |
| upload falha com "permission denied" depois de restaurar | mídia restaurada com outro dono; o script ajusta pelo dono do diretório montado — confira `DJANGO_MEDIA_ROOT` |
| as cópias sumiram | alguém rodou `down -v`: ele leva o volume `backup_data` junto. É o que o offsite existe para sobreviver |
| o bucket não recebe nada | credencial ou endpoint errados: `logs backup` traz o erro do rclone; teste com `exec backup rclone ls :s3:SEU-BUCKET` |
