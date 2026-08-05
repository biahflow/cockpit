# FDD 021 — Retenção, backup testado e restauração

## Jornada

Último item aberto do bloco "Prontidão para produção" do `roadmap.md`: *retenção, backup testado e
restauração do banco e dos documentos*. A FDD 019 o adiou nominalmente ("backup, retenção e
restauração são o item seguinte") e a FDD 020 repetiu o adiamento.

O que existia era promessa em prosa. O checklist do `producao.md` pedia "Postgres provisionado,
**com backup**" e o procedimento de deploy mandava "confirme o backup do banco antes" — sem dizer
quem faz, onde cai, por quanto tempo fica nem como se restaura. Nenhuma linha de código, nenhum
teste.

A pergunta que este recorte responde: **o host pegou fogo às 4h — o que eu rodo, e como sei que
funciona antes de precisar?**

## Regras

- **Backup que ninguém nunca restaurou não é backup, é fé.** Por isso a entrega central não é o
  script de cópia: é o **drill** (`.github/scripts/backup-drill.sh`), que roda a cada PR sobre a
  topologia de produção — semeia um cliente e um documento, faz backup, **destrói o banco e a
  mídia**, restaura e confere que voltaram, com o conteúdo idêntico.
- **O drill confere que a destruição foi real.** Sem esse passo, um `restore.sh` que não faz nada
  passaria: o dado nunca teria saído. É a forma clássica de um teste de backup mentir.
- **O drill constrói as imagens antes de rodar.** `docker compose run` reaproveita a imagem
  existente sem reconstruir — e, sem o `build` explícito, o drill local **aprovou um `restore.sh`
  sabotado de propósito**, testando o script da execução anterior. Foi assim que o defeito
  apareceu; no runner limpo do CI ele nunca teria dado as caras.
- **O estado mora em dois lugares, e os dois vão junto.** Postgres e `MEDIA_ROOT`. Restaurar só o
  banco devolve um portal cheio de registros apontando para arquivos que não existem mais.
- **A ferramenta de backup tem a mesma major do servidor.** `pg_dump` de major menor **recusa
  rodar**. A imagem da API é bookworm (cliente 15) contra um servidor 16, então o sidecar é
  construído de `postgres:16-alpine`, a mesma imagem do `db` (ADR 0013).
- **`--format=custom`, não `.sql`.** Comprimido e restaurável tabela a tabela; um dump de texto só
  serve para `psql < arquivo`, tudo ou nada.
- **Escreve em `.tmp`, renomeia no fim.** O `mv` é atômico no mesmo sistema de arquivos, então um
  backup interrompido (OOM, host reiniciado, disco cheio) nunca aparece como candidato a "o mais
  recente" — que é exatamente o que a restauração pega, às 4h, sem ninguém conferindo.
- **A poda só roda depois do sucesso, e nunca leva a última cópia.** `BACKUP_RETENTION_DAYS`
  (default 14, `0` desliga). Um ciclo que falhou não pode apagar nada, e um relógio errado no host
  não pode valer "apague tudo o que você tem".
- **O carimbo é escrito por último.** `latest.json` só existe no caminho feliz: gravá-lo antes do
  fim faria o alerta calar justamente quando o backup começa a falhar.
- **A aplicação não faz backup — ela reclama.** `manage.py backup_status` lê o carimbo e sai com
  código 1 quando não há cópia ou quando ela passou de `BACKUP_MAX_AGE_HOURS` (26 h: folga sobre o
  diário, sem deixar passar um dia inteiro). É o gancho do alerta que fecha o laço da FDD 020 —
  sem ele, backup que parou só aparece no dia em que se precisa dele.
- **O comando nunca levanta traceback.** Carimbo ausente, ilegível, sem data ou com JSON quebrado
  viram motivo em texto. Comando de alerta que estoura vira "o alerta quebrou", não "o backup
  quebrou".
- **O `api` monta o volume de backup só-leitura.** O processo que atende a internet não precisa
  poder apagar as cópias — que é o primeiro lugar onde um ransomware olha depois de entrar pela
  aplicação.
- **`/readyz` não olha para backup.** Backup velho não é motivo para tirar o portal do balanceador
  (FDD 020 define ready como "pode receber tráfego").
- **Nenhum system check novo.** Seria falso: o backup roda em **outro container**, e um
  `check --deploy` no processo da API afirmaria algo que ele não tem como saber. Quem cobra é o
  `backup_status` + alerta.
- **A restauração é destrutiva e exige `--yes`.** Sem confirmação explícita ela recusa. E derruba
  as conexões abertas antes de recriar o schema: conexão viva segura lock, e o `DROP SCHEMA`
  ficaria pendurado em silêncio.
- **Terra arrasada em vez de `pg_restore --clean`.** O `--clean` deixa passar objeto que existe hoje
  e não existia no dump; restaurar tem de devolver **exatamente** o estado da cópia. E
  `--exit-on-error`, porque o default do `pg_restore` é seguir em frente e contar os erros no fim —
  uma restauração pela metade que "terminou bem" é o pior resultado possível aqui.
- **A mídia é extraída antes de a atual ser apagada.** Um `tar` que falha no meio não pode deixar o
  portal sem os arquivos que ele ainda tinha — e é no meio de um desastre que ele falha. O dono dos
  arquivos vem do diretório montado, não do arquivo tar: restaurar em outro host pode cair em outro
  mapeamento de uid, e mídia que o gunicorn não consegue escrever quebra todo upload.
- **O desastre de verdade é o host novo, com o volume vazio.** Por isso o `restore.sh` busca no
  offsite quando não acha cópia local — senão ele só saberia restaurar quando não fosse preciso.
- **Offsite é opt-in.** Sem `BACKUP_S3_BUCKET`, o bloco inteiro não existe. Backup no mesmo host não
  é backup, mas exigir credencial de nuvem para a primeira cópia existir travaria o caminho simples.
- **Credencial nunca em argumento.** Senha do Postgres pelas variáveis do libpq, chave do bucket
  pelas variáveis do rclone: qualquer `ps` no host mostraria a linha de comando.
- **O sidecar faz a primeira cópia no boot**, quando ainda não existe nenhuma — uma instalação nova
  não pode ficar até 24 h sem backup. Se falhar, ele **não** derruba o container: banco ainda
  subindo é motivo comum, o cron tenta no horário, e um sidecar em laço de restart não gera backup
  nenhum.
- **A cópia de boot não roda com o banco sem tabelas.** É o cenário de recuperação em host novo: o
  volume de cópias nasce vazio, e um dump de banco vazio viraria "o mais recente" — exatamente o
  que um `restore.sh --latest` escolheria. Copiar o nada por cima do desastre. O runbook reforça
  pela ordem (restaurar com `run --rm ... --offsite` **antes** de subir o sidecar).

## Fora deste recorte

**PITR (arquivamento de WAL).** Dump diário perde até um dia. Restauração por ponto no tempo é
outro eixo — arquivamento contínuo, storage, base backup — e está registrada na ADR 0013 como o
próximo degrau.

**Criptografia própria do dump.** Fica a criptografia em repouso do bucket + credencial restrita.
Uma chave a mais é uma chave a perder, e chave perdida é backup ilegível. Risco aceito na ADR.

**Documentos no Google Drive.** Com `GOOGLE_DRIVE_ENABLED=true` os arquivos vivem no Drive, que tem
versionamento e lixeira próprios; o que o portal guarda é o `drive_file_id`, e ele está no dump.

**Backup do Redis.** Ele guarda contador de teto de requisição, que pode ser perdido sem
consequência — o `docker-compose.prod.yml` já desliga a persistência dele de propósito.

**Retenção de dado de negócio (LGPD)** — por quanto tempo o portal guarda dado de cliente
arquivado — é outro assunto, e não tem nada a ver com retenção de cópia.

**Alertas.** Como na FDD 020, a regra mora no fornecedor; o que o código entrega é o sinal (código
de saída 1). O mínimo a configurar está em `docs/runbooks/monitoramento.md`.

## Aceite

Quem sobe a stack de produção ganha backup sem configurar nada: o serviço `backup` faz a primeira
cópia no boot e agenda as seguintes (`BACKUP_CRON`, default 03:15). `docker compose exec api
python manage.py backup_status` imprime de quando é a última cópia, seu tamanho e se ela saiu do
host; com o backup parado, o mesmo comando sai com código 1 e diz há quantas horas.
`restore.sh --latest --yes` devolve banco e documentos — sem `--yes`, recusa. Com
`BACKUP_S3_BUCKET` preenchido, cada cópia sobe para o bucket e o restore consegue puxá-la de volta
em um host onde o volume local está vazio.

## Regressão crítica

O drill do CI é o teste principal: ele reprova se o backup não restaurar. Foi verificado sabotando
o `restore.sh` de propósito — o drill falhou com `relation "core_client" does not exist`, e voltou
a passar com o script real.

Na suíte: backup recente aprova; backup de 40 h reprova **e ainda assim informa a idade** (quem lê
o alerta quer saber de quando é a última cópia que existe); carimbo ausente, `BACKUP_ROOT` não
configurado, JSON corrompido e data ilegível reprovam com motivo em texto e sem traceback; carimbo
sem `finished_at` cai no `timestamp` do nome; e o comando sai com código 1 (via `CommandError`)
quando o backup está velho.
