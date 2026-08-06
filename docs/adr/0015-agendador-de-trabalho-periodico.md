# ADR 0015 — Agendador de trabalho periódico na aplicação, com carimbo durável no banco

**Status:** aceito

## Contexto

Três funcionalidades entregues não rodavam em produção, porque nada as disparava.

O `send_daily_digest` (FDD 010), o `sync_calendar` (FDD 012) e o `backup_status` (FDD 021) eram
management commands prontos e testados, e a documentação de cada um mandava agendá-los "via cron
na infraestrutura". Esse cron **não existia em lugar nenhum da árvore**: nem crontab, nem `*.timer`,
nem workflow com `schedule:`, nem serviço de compose. O `docs/runbooks/producao.md`, que é o
procedimento de subida, não mencionava nenhum dos três. Quem seguisse o runbook à risca subia sem
digest, sem sincronia de calendário e — o mais grave — com o alerta de backup **armado e sem
gatilho**: o `backup_status` sai com código 1 quando a última cópia envelhece, exatamente para que
alguém seja acordado, e ninguém o chamava.

O repositório já tinha argumentado contra esse arranjo, em `ops/backup/entrypoint.sh:4-5`:

> O agendamento mora aqui, e não em um cron do host: quem sobe a stack com `up -d` já tem backup,
> sem um passo manual que, esquecido, faz o portal ir a produção sem cópia nenhuma.

O raciocínio foi aplicado ao backup e só a ele. Digest e calendário ficaram sendo precisamente o
passo manual esquecível que o comentário condena.

Dois fatos moldam a decisão.

**A aplicação é Python, e o sidecar de backup não é.** O `backup` roda `crond` do BusyBox sobre
`postgres:16-alpine` porque lá não há aplicação nenhuma — só `pg_dump` e `tar`. Aqui o trabalho a
agendar **é** código Django, que já tem imagem, configuração e conexão com o banco.

**Agendamento sem estado durável reenvia e-mail.** Um laço que só guarda "quando rodei" em memória
manda o digest de novo a cada restart do container. Como o digest é e-mail para todos os usuários
ativos, o defeito não é sutil: é uma enxurrada, e ele acontece no dia do primeiro deploy.

## Decisão

**Um management command em laço (`manage.py run_scheduler`) rodando como serviço próprio do
compose, com o carimbo do último ciclo no banco.**

- **Serviço `scheduler` no `docker-compose.prod.yml`**, irmão do `api`: mesma imagem (`target:
  prod`), mesmo `env_file`, mesma âncora `*api_env`, `command` trocado. Nenhuma alteração na imagem
  e nenhuma dependência nova no `pyproject.toml`.
- **Processo separado, não thread dentro do gunicorn.** Com três workers, um agendador embutido
  mandaria o digest em triplicata. Um container é um relógio.
- **A decisão de "o que venceu" mora em `apps/core/scheduler.py`**, separada do laço que gira o
  relógio. É o que torna o agendamento testável — e é a diferença que mais pesa contra o cron.
- **`ScheduledJobRun` (uma linha por job) é o carimbo durável.** Equivalente, no banco, ao
  `latest.json` que o sidecar de backup deixa em disco, e pelo mesmo motivo.
- **A reivindicação é atômica**: leitura do carimbo, decisão e marcação da tentativa dentro de uma
  transação, com `select_for_update()`. Dois schedulers no ar (escala por engano, deploy com
  sobreposição) não disparam o mesmo job duas vezes.
- **O vencimento conta a partir da _tentativa_, não do sucesso.** Um job diário que falhou não
  volta no próximo tique. Os três jobs de hoje são relatório e alerta; retentar de minuto em minuto
  trocaria uma falha por uma enxurrada — de e-mail no digest, de evento no Sentry no
  `backup_status`.
- **Job diário nasce armado; job por intervalo nasce disparando.** Subir a stack às 23h com âncora
  nas 07:30 não pode mandar o digest do dia na hora (as 07:30 "já passaram" e não há carimbo que
  diga que ele saiu). Já a sincronia de calendário é idempotente e barata: rodar na estreia só
  adianta a primeira importação.
- **Falha é isolada por job, e vira log de `ERROR`.** A integração de logging do Sentry é
  autodetectada (ADR 0012), então `ERROR` vira evento — e é assim que o gancho de alerta da FDD 021
  finalmente ganha dono, sem inventar canal novo.

### Alternativas descartadas

**Cron do host.** É o estado atual com outro nome: invisível ao versionamento, ausente do
`docker compose up`, impossível de testar e dependente de alguém lembrar. Foi o que produziu o
problema.

**Sidecar com `crond`, copiando o padrão do `backup`.** Custaria instalar `cron` na imagem Debian da
API e, o que pesa mais, deixaria a tabela de horários **fora da suíte**: um crontab não se testa com
`pytest`. A tabela em Python rende os testes de cadência, de estreia armada e de isolamento de
falha que hoje protegem o comportamento. O sidecar de backup usa `crond` porque a imagem dele não
tem Python — não porque `crond` seja preferível.

**Celery + beat.** Um broker, um segundo tipo de processo e uma dependência nova, para três jobs
sem fan-out, sem retry com backoff e sem trabalho sob demanda. O Redis do compose sobe com
`--save "" --appendonly no` justamente porque só guarda contador de teto de requisição: **não é um
broker**, e promovê-lo a um é decisão maior que o problema que se está resolvendo.

## Consequências

- Subir a stack de produção passa a agendar o trabalho periódico junto. Some o passo manual, e com
  ele o modo de falha "instalação sem digest e sem alerta de backup".
- **O alerta de backup da FDD 021 passa a existir de fato.** Era o único sinal do portal que não
  nascia de uma requisição e, por isso, o único que ninguém coletava.
- Mais um container em produção. É o custo aceito: em troca, o agendamento é versionado, testado e
  igual em toda instalação.
- **A garantia contra duplicidade tem dois níveis.** No Postgres, `select_for_update` bloqueia de
  verdade. No SQLite da suíte o lock é no-op, e o que protege é a releitura do carimbo dentro da
  transação — a mesma checagem, sem a exclusão mútua. Quem rodar dois schedulers contra SQLite não
  tem a garantia forte; quem rodar contra Postgres, que é a topologia de produção, tem.
- **Um job diário que falha só é tentado no dia seguinte.** É a troca deliberada descrita acima.
  Se algum job futuro precisar de retry com backoff, é aí que a conversa sobre uma fila de verdade
  se reabre — e não antes.
- O `ScheduledJobRun` é registro operacional: fica fora do soft delete, fora do `RolePermission` e
  fora do contrato `/api/v1/`. Leitura pelo admin, só-leitura — editar o carimbo à mão é reagendar
  um job por baixo do agendador.
- Horários em hora de parede de `TIME_ZONE` (`America/Sao_Paulo`), não no `TZ` do container: quem
  configura "digest às 07:30" quer 07:30 para quem lê o e-mail.
