# FDD 010 — Notificações por e-mail e digest diário por IA

## Jornada

Etapas **Go-live** e **Hypercare** da jornada (RFC 0002): depois que o projeto entra em
operação, a equipe precisa ser avisada fora do app. Duas entregas atrás da flag `email`:
(1) as notificações in-app passam a ser **espelhadas por e-mail**; (2) um **digest diário
por IA** resume, para cada usuário, o que está atrasado e a vencer.

## Regras

- **Flag `email`** ("Notificações por e-mail e digest"): default do ambiente
  (`EMAIL_NOTIFICATIONS_ENABLED`) e alternável em runtime na página Configurações. Como o
  SMTP já vem configurado, não exige credencial extra para ligar. Desligada → nada muda
  (só in-app), a plataforma opera normalmente.
- **Espelho por e-mail**: `notifications.notify(...)` cria a notificação in-app e, quando a
  flag está ligada, envia a mesma mensagem por e-mail a cada destinatário com endereço
  (best-effort, `fail_silently` — falha de e-mail não quebra o fluxo que notificou).
- **Digest diário** (`digest.send_daily_digest`): para cada usuário ativo com itens a
  reportar (marcos/tarefas atrasados ou a vencer em 7 dias), envia um resumo por e-mail.
  Com `AI_ENABLED`, o texto é redigido pelo modelo e auditado em `AiInteraction`
  (feature `daily_digest`); sem IA, envia o resumo estruturado. No-op quando a flag `email`
  está desligada. É disparado pelo comando `manage.py send_daily_digest`, que o serviço
  `scheduler` roda todo dia às `SCHEDULER_DIGEST_AT` (default 07:30) — FDD 023. Até a FDD 023
  esta linha dizia "agendável por cron diário na infraestrutura", e esse cron não existia:
  na prática o digest nunca saía em produção.

## Aceite

Com a flag ligada, uma nova notificação (lead/tarefa/marco/kickoff) chega também por
e-mail; `send_daily_digest` envia a cada usuário com pendências um resumo do dia (redigido
pela IA quando ligada) e registra a interação.

## Regressão crítica

Com a flag desligada, `notify` não envia e-mail e `send_daily_digest` retorna 0; usuário
sem itens não recebe digest; usuário sem e-mail é ignorado; falha de SMTP não interrompe a
notificação nem o digest.
