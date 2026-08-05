# ADR 0013 — Backup lógico em container próprio, com restauração exercitada no CI

**Status:** aceito

## Contexto

O último item do bloco "Prontidão para produção" que ainda bloqueia ir ao ar. Até aqui o
repositório não tinha backup nenhum: o `docs/runbooks/producao.md` pedia "Postgres provisionado,
**com backup**" e mandava "confirme o backup do provedor antes de qualquer migração" — sem dizer
quem faz, onde cai, por quanto tempo fica, nem como se restaura.

Três fatos moldam a decisão.

**O estado do portal mora em dois lugares.** O Postgres (volume `postgres_data`) e os documentos de
cliente (volume `media_data`, `Document.file`). Backup só do banco restaura um portal cheio de
registros apontando para arquivos que não existem — e documento é justamente o que a ADR 0002 trata
como privado: proposta, contrato, anexo de projeto.

**`pg_dump` não é compatível para frente.** Um cliente de major menor que o servidor **se recusa a
rodar**. A imagem da API é Debian bookworm, cujo `postgresql-client` é o 15, contra um servidor 16:
pôr a ferramenta de backup lá dentro criaria uma incompatibilidade silenciosa, descoberta no dia em
que se precisa dela.

**Backup que ninguém nunca restaurou não é backup, é fé.** A pergunta que este recorte responde não
é "existe cópia?", é "o host pegou fogo às 4h — o que eu rodo, e como sei que funciona antes de
precisar?".

## Decisão

**Dump lógico (`pg_dump --format=custom`) + tar dos documentos, em um sidecar próprio.** Serviço
`backup` no `docker-compose.prod.yml`, construído de `postgres:16-alpine` — **a mesma imagem do
serviço `db`**. Trocar a major de um obriga a trocar do outro, e isso é uma vantagem: o acoplamento
fica visível no compose em vez de escondido em uma imagem que "por acaso" tinha o cliente certo. De
quebra, o backup deixa de depender do build da aplicação: API quebrada, ainda se restaura.

**O agendamento mora no sidecar (`crond`), não no host.** Quem sobe a stack com `up -d` já tem
backup. Um cron de host documentado em runbook é um passo manual que, esquecido, faz o portal ir a
produção sem cópia nenhuma — e ninguém percebe até precisar.

**Destino local por padrão, offsite opt-in.** `BACKUP_S3_BUCKET` vazio mantém as cópias no volume
`backup_data`; preenchido, cada par sobe para um storage compatível com S3 (rclone, credencial por
ambiente). Backup no mesmo host não é backup — mas exigir credencial de nuvem para a primeira
cópia existir travaria o caminho simples, e cópia local é melhor que nenhuma.

**A restauração é exercitada a cada PR.** `.github/scripts/backup-drill.sh` sobe a topologia de
produção, semeia dado, faz backup, **destrói banco e documentos**, restaura pelo mesmo comando do
runbook e confere que voltaram — inclusive que a destruição foi real, senão o drill passaria por não
ter destruído nada.

**A aplicação só observa.** `manage.py backup_status` lê o carimbo que o sidecar deixa e sai com
código 1 quando o backup está velho ou não existe. O volume entra no `api` **só-leitura**.

Alternativas recusadas:

- **`postgresql-client` na imagem da API** — versão errada (15 contra 16), e amarra o backup ao
  build da aplicação.
- **Snapshot do volume do Postgres** — copiar `PGDATA` com o servidor no ar produz um backup
  inconsistente; fazer direito exige `pg_basebackup` e parada, e não resolve os documentos.
- **Backup pelo provedor, e só** — resolve o banco de quem usa Postgres gerenciado, não resolve os
  documentos, não é testável no CI e varia por hospedagem. Continua **recomendado como camada
  extra** no runbook.
- **PITR / arquivamento de WAL** — janela de perda menor, mas é outro eixo (arquivamento contínuo,
  storage, base backup, restauração por tempo). É o próximo degrau, não este.
- **Criptografar o dump no script (`age`/`gpg`)** — mais um segredo crítico, e chave perdida é
  backup ilegível, que dá no mesmo que não ter. Fica a criptografia em repouso do bucket.
- **Cron do host** — ver acima.
- **`pg_restore --clean` em vez de derrubar o schema** — `--clean` não remove objeto que existe
  hoje e não existia no dump; a restauração tem de devolver exatamente o estado da cópia.
- **Um serviço separado só para restaurar** (para o `backup` montar a mídia só-leitura) — imagem
  duplicada e um serviço que ninguém lembra de manter.
- **Testar os scripts com mocks em pytest** — provaria que o script chama `pg_dump`, não que o dump
  restaura. O drill é o teste.

## Consequências

**A janela de perda é de até um dia.** Dump diário significa que um desastre às 03:14 perde o que
entrou desde as 03:15 do dia anterior. É a escolha consciente deste recorte; quem precisar de menos
ajusta `BACKUP_CRON` (o custo é tempo de CPU e espaço) ou parte para PITR.

**O dump é o banco inteiro em claro.** Nasce com permissão `600`, o volume é tão sensível quanto o
Postgres, e quem lê o bucket lê a base de clientes. Sem criptografia própria, a proteção é a
credencial restrita, o versionamento e a criptografia em repouso do provedor — **risco aceito e
registrado**, com o passo a passo no runbook.

**A major do Postgres passa a aparecer em dois lugares.** `docker-compose.prod.yml` (`db`) e
`ops/backup/Dockerfile`. Um upgrade de major precisa mexer nos dois, e o drill do CI reprova se
esquecerem — que é exatamente onde se quer descobrir.

**O CI ficou mais lento e mais caro.** Um job que sobe containers custa minutos, contra segundos dos
demais. É o preço de um backup que se sabe restaurar.

**A restauração exige parar o `api`.** O script derruba as conexões abertas e recria o schema; com o
gunicorn no ar, requisições em voo veriam um banco sem tabelas. Está no runbook, e é o motivo de
`--yes` ser obrigatório.

**Documento no Google Drive fica fora.** Com `GOOGLE_DRIVE_ENABLED=true` os arquivos vivem no Drive,
com versionamento e lixeira próprios; o que o portal guarda é o `drive_file_id`, que está no dump.

**`down -v` continua sendo o comando mais perigoso do repositório** — agora ele leva também as
cópias, porque elas moram em volume nomeado do mesmo compose. O offsite é o que sobrevive a isso.
