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
  reportar, envia um resumo por e-mail. Com `AI_ENABLED`, o texto é redigido pelo modelo e
  auditado em `AiInteraction` (feature `daily_digest`); sem IA, envia o resumo estruturado.
  No-op quando a flag `email` está desligada. É disparado pelo comando
  `manage.py send_daily_digest`, que o serviço `scheduler` roda todo dia às
  `SCHEDULER_DIGEST_AT` (default 07:30) — FDD 023. Até a FDD 023 esta linha dizia "agendável
  por cron diário na infraestrutura", e esse cron não existia: na prática o digest nunca saía
  em produção.

### O que entra no digest — duas seções

| Seção | O que entra | Janela |
| --- | --- | --- |
| **Seus itens** | `owner=user`, e o projeto ainda acessível para a pessoa | atrasados + a vencer em 7 dias |
| **Do seu projeto** | itens dos projetos de que ela **participa**, de outras pessoas | só atrasados |

- **Participação não é visibilidade** (ADR 0010). A seção da equipe consulta `ProjectMember`
  diretamente e **não** `Project.objects.visible_to()`: esta devolve *tudo* para admin e
  vendas, e usá-la aqui mandaria o portfólio inteiro da casa para o admin, todo dia.
  Visibilidade responde "posso ver?"; o digest pergunta "isto é meu problema?". Um teste trava
  essa diferença justamente porque as duas funções são fáceis de confundir.
- **A seção própria respeita o acesso**, via `project_scope_q`. Nada reatribui item quando
  alguém sai de uma equipe, então quem saiu continua `owner` das suas tarefas — e o digest
  seguia mandando título e vencimento de um projeto cujo detalhe já responde 404 para ela.
  Para admin e vendas a função devolve `Q()` vazio: **ninguém perde e-mail que já recebia**.
- **A seção da equipe é só de atrasados.** "A vencer em 7 dias" do projeto inteiro, repetido
  para cada pessoa da equipe, é volume sem sinal.
- **Teto de 10 linhas por bloco**, com "... e mais X". Um projeto com dezenas de atrasos não
  pode virar parede de texto diária — digest que ninguém lê é o mesmo que digest nenhum.
- **Sem duplicação**: item próprio não reaparece na seção da equipe.

Antes disto o digest filtrava só por `owner=`, e quem entrava numa equipe sem ser dono de nada
recebia contexto vazio e era pulado — consequência que a FDD 018 registrou em aberto e que só
passou a doer quando a FDD 023 fez o digest realmente rodar.

## Aceite

Com a flag ligada, uma nova notificação (lead/tarefa/marco/kickoff) chega também por
e-mail; `send_daily_digest` envia a cada usuário com pendências um resumo do dia (redigido
pela IA quando ligada) e registra a interação. Uma pessoa de Entrega que participa de um
projeto **sem ser dona de nenhum item** recebe os atrasados daquele projeto; um admin que não
participa de projeto nenhum e não é dono de nada **não recebe nada**.

## Regressão crítica

Com a flag desligada, `notify` não envia e-mail e `send_daily_digest` retorna 0; usuário
sem itens não recebe digest; usuário sem e-mail é ignorado; falha de SMTP não interrompe a
notificação nem o digest. Quem foi removido de uma equipe deixa de receber os itens daquele
projeto, mesmo continuando `owner` deles.
