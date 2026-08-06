# FDD 023 — Trabalho periódico agendado

## Jornada

O `roadmap.md` estava inteiramente marcado, salvo o consumo no repo `portal_cliente` (trilho
separado). Mas havia uma lacuna que nenhum item cobria: **três funcionalidades entregues não rodavam
em produção, porque nada as disparava.**

| Comando | Cadência que a doc pedia | Quem chamava |
| --- | --- | --- |
| `send_daily_digest` (FDD 010) | "agendável por **cron diário na infraestrutura**" | ninguém |
| `sync_calendar` (FDD 012) | "(agende via cron)" | ninguém — só o botão "Sincronizar agora" |
| `backup_status` (FDD 021) | "rode o comando **de fora**, uma vez ao dia" | ninguém |

Os três estavam prontos e testados. O cron que os chamaria não existia em lugar nenhum da árvore:
nem crontab, nem `*.timer`, nem workflow com `schedule:`, nem serviço de compose. O único agendador
do repositório era o `crond` do sidecar `backup`, e ele só faz backup.

Na prática, uma instalação que seguisse o `producao.md` à risca subia **sem digest diário, sem
sincronia de calendário e com o alerta de backup armado sem gatilho** — e é o alerta que mais dói,
porque o `backup_status` existe precisamente para que backup que parou de rodar não apareça só no
dia em que se precisa dele.

A pergunta que este recorte responde: **quem aperta o botão às 07:30?**

## Regras

- **O agendamento sobe com a stack.** É o mesmo argumento que o `ops/backup/entrypoint.sh` já fazia
  para o backup — "sem um passo manual que, esquecido, faz o portal ir a produção sem cópia
  nenhuma" —, agora aplicado ao resto do trabalho periódico. Serviço `scheduler` no
  `docker-compose.prod.yml`, mesma imagem do `api`, `command` trocado.
- **Processo separado, não thread dentro do gunicorn.** Com três workers, um agendador embutido
  mandaria o digest em triplicata. Um container é um relógio.
- **A decisão de "o que venceu" é código testável.** `apps/core/scheduler.py` decide; o
  `manage.py run_scheduler` só gira o relógio. É a diferença que descarta o cron: um crontab não se
  testa com `pytest`, uma tabela de jobs em Python se testa (ADR 0015).
- **O carimbo do último ciclo é durável** (`ScheduledJobRun`, uma linha por job). Sem ele, um
  restart do container às 07:31, logo depois do digest das 07:30, reenviaria o e-mail para todos os
  usuários ativos. É o equivalente, no banco, do `latest.json` do sidecar de backup.
- **A reivindicação é atômica.** Leitura, decisão e marcação da tentativa dentro de uma transação,
  com `select_for_update()`: dois schedulers no ar não disparam o mesmo job duas vezes.
- **O vencimento conta da _tentativa_, não do sucesso.** Job diário que falhou não volta no próximo
  tique. São relatórios e alertas: retentar de minuto em minuto trocaria uma falha por uma
  enxurrada de e-mail e de evento no Sentry.
- **Job diário nasce armado; job por intervalo nasce disparando.** Subir a stack às 23h não pode
  mandar o digest do dia na hora — as 07:30 "já passaram" e não há carimbo dizendo que ele saiu.
  A sincronia de calendário, ao contrário, é idempotente e barata: rodar na estreia só adianta a
  primeira importação.
- **Falha é isolada por job.** Um job que estoura não derruba o laço nem impede os outros do mesmo
  tique. E o tique inteiro é protegido também: banco fora do ar às 3h não pode deixar o container
  em laço de restart — um agendador que não sobe é o problema que este item veio resolver.
- **Falha vira log de `ERROR`, que vira evento no Sentry** (a integração de logging é
  autodetectada, ADR 0012). É assim que o gancho da FDD 021 ganha dono, sem canal novo: o
  `backup_status` já sai com código 1 quando a cópia envelhece, e agora alguém o executa e alguém
  escuta.
- **O scheduler não duplica regra de flag.** `send_daily_digest` (flag `email`) e `sync_calendar`
  (flag `calendar`) já viram no-op desligados; o agendador só os chama.
- **Horário em hora de parede de `TIME_ZONE`**, não no `TZ` do container: quem configura "digest às
  07:30" quer 07:30 para quem lê o e-mail.
- **O `scheduler` monta o volume de backup só-leitura**, pelo mesmo motivo do `api` (FDD 021): quem
  só lê a data da última cópia não precisa poder apagá-la.
- **`ScheduledJobRun` é registro operacional, não recurso de negócio.** Fora do soft delete, fora do
  `RolePermission`, fora do contrato `/api/v1/`. Só-leitura no admin — editar o carimbo à mão é
  reagendar um job por baixo do agendador, e um `last_attempt_at` apagado por engano reenvia o
  digest do dia.

## Configuração

| Variável | Default | O que faz |
| --- | --- | --- |
| `SCHEDULER_TICK_SECONDS` | `60` | de quanto em quanto o laço confere o que venceu |
| `SCHEDULER_DIGEST_AT` | `07:30` | hora do digest diário |
| `SCHEDULER_CALENDAR_EVERY_MINUTES` | `15` | atraso máximo entre marcar `#proj-<id>` e ver a tarefa |
| `SCHEDULER_BACKUP_CHECK_AT` | `09:00` | hora da conferência de backup — horário comercial de quem vai agir sobre o alerta, não madrugada |

Horário inválido no ambiente (`SCHEDULER_DIGEST_AT=meio-dia`) cai no default e avisa no log, em vez
de impedir o agendador inteiro de subir.

## Critérios de aceite

- `docker compose -f docker-compose.prod.yml up -d` sobe o `scheduler`, que loga a tabela de
  horários no arranque e roda a sincronia de calendário no primeiro tique.
- O digest sai **uma** vez por dia. Reiniciar o container logo depois **não** o reenvia.
- Um job que falha é registrado (`ok=False`, motivo em `detail`), loga `ERROR` e **não** impede os
  demais do mesmo tique; o processo continua no ar.
- `manage.py run_scheduler --once` roda um tique e sai com 0 — inclusive quando um job reprova.
- `backup_status` vencido dispara `ERROR` e, com `SENTRY_DSN` configurado, evento no Sentry.

Testes em `backend/apps/core/tests/test_scheduler.py` (21). Sabotagem deliberada, como a FDD 021
estabeleceu: remover a gravação do carimbo reprova três testes, e fazer o job diário nascer
disparando em vez de armado reprova o teste da estreia — os dois comportamentos que mais fácil se
quebraria em uma refatoração.

## Fora deste recorte

**Retry com backoff e fila de uso geral.** Job diário que falha só é tentado no dia seguinte — troca
deliberada (ADR 0015). Se aparecer um caso que precise de retry, fan-out ou trabalho sob demanda, é
aí que a conversa sobre Celery se reabre, e não antes.

**Durabilidade da entrega do webhook do portal.** `portal.emit()` entrega em thread daemon, sem
retry: uma falha vira `logger.warning` e o evento se perde. É defeito real, mas de outra natureza —
durabilidade de entrega, não agendamento. E a **reconciliação não se resolve daqui**: a task
`sync_biahflow_project` vive no repo `portal_cliente`, que é quem puxa o snapshot; este repositório
só expõe o lado de leitura (`portal-project-snapshot`, ADR 0003).

**Digest por participação.** O `digest.py` filtra `owner=user`, então quem é membro de projeto sem
ser dono de nada recebe digest vazio — consequência que a FDD 018 registrou em aberto. Ligar o
digest diário pela primeira vez em produção **torna isso visível**, e vale decidir logo em seguida;
mas é mudança de comportamento do digest, não do agendador.

**Agendamento configurável pela tela.** Os horários vêm do ambiente. Uma tela de Configurações para
eles é possível (o `AppSetting` já existe), mas mudar quando o digest sai é operação de instalação,
não de uso diário.
