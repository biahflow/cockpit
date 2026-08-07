# FDD 010 — Notificações por e-mail e digest diário por IA

## Jornada

Etapas **Go-live** e **Hypercare** da jornada (RFC 0002): depois que o projeto entra em
operação, a equipe precisa ser avisada fora do app. Duas entregas atrás da flag `email`:
(1) as notificações in-app passam a ser **espelhadas por e-mail**; (2) um **digest diário
por IA** resume, para cada usuário, o que está atrasado e a vencer.

## Regras

- **Flag `email`** ("Notificações por e-mail e digest"): default do ambiente
  (`EMAIL_NOTIFICATIONS_ENABLED`, **`true` desde a ADR 0018**) e alternável em runtime na página
  Configurações. Foi a primeira flag sem `requires`: como o SMTP já tem default, não há
  credencial a cobrar — e por isso ela foi a candidata natural a nascer ligada. **Deixou de ser a
  única na FDD 030**, e por uma razão diferente da dela: o `enrichment` consulta cadastro público,
  então não há chave que exista para ser cobrada. Nos dois casos quem responde "isto funciona?" é
  a sonda, não o `configured()`. Ponha `false` para
  silenciar. Em produção isso torna o SMTP real um requisito de deploy, não um opcional: o default
  `localhost:1025` é o Mailpit do compose e, fora do dev, é lugar nenhum.

  **Desligada, o que para é a notificação — não todo o e-mail.** Seguem saindo o **convite**
  (`InvitationView`) e o **kickoff** (`kickoff._send_kickoff_email`), porque são transacionais: um
  portal cujo convite não sai não onboarda ninguém. Ficam atrás da flag o espelho de notificação, o
  digest, o lembrete de assinatura e a confirmação de agendamento. Esta linha dizia "nada muda (só
  in-app)", o que se lia como "nenhum e-mail sai"; a homologação da FDD 024 mostrou o contrário.

- **O convite grava e envia na mesma transação.** O convite **é** o e-mail — quem recebe não tem
  outro caminho para o token —, então SMTP fora do ar desfaz o convite e devolve **502**. Antes, a
  linha era gravada e o `fail_silently=False` devolvia 500: sobrava um convite válido que ninguém
  recebeu, o admin achava que falhara, e cada tentativa criava mais um. É o único ponto de envio
  que **não** é best-effort, e de propósito.
- **Espelho por e-mail**: `notifications.notify(...)` cria a notificação in-app e, quando a
  flag está ligada, envia a mesma mensagem por e-mail a cada destinatário com endereço
  (best-effort, `fail_silently` — falha de e-mail não quebra o fluxo que notificou).
- **Alvo por participação**: quem notifica sobre algo de um projeto passa `project=`, e aí
  `notify` descarta os destinatários que não alcançam aquele projeto — **antes** de gravar, então
  o espelho por e-mail cai no mesmo corte. A regra prática é *URL de projeto ⇒ guarda*, e vale
  para tarefa, marco, kickoff e a sincronia com Linear/GitHub.

  Existe porque nada reatribui item quando alguém sai de uma equipe: o `ProjectMember` é arquivado
  e o `WorkItem.owner` fica. O caminho que de fato vazava era o `tasksync.apply_inbound`, que
  dispara por **webhook do fornecedor** — muito depois da criação, sem `request.user` para
  consultar —, e seguia mandando o título da tarefa com um link que responde 404. Havia um segundo,
  mais silencioso: `calendar_sync` cria tarefa com `owner=project.owner`, dono que ninguém validou,
  e passou a rodar a cada 15 min desde a FDD 023.

  **Notificação escolhida por papel não leva guarda** — lead novo e booking vão para admin/vendas
  com url `/leads`, não falam de projeto, e recortá-las por participação quebraria o comercial.
  O `esign` também fica de fora: a url é `/documentos`, lista já recortada, e `Document.project`
  é nulável (pode ser de cliente ou oportunidade).

  O predicado é `models.can_access_project(user, project)` — a terceira forma da mesma pergunta,
  ao lado de `visible_to` (queryset) e `project_scope_q` (filtro através de projeto), e como elas
  derivada de `visible_to` em vez de reescrever o critério (ADR 0010).
- **Digest diário** (`digest.send_daily_digest`): para cada usuário ativo com itens a
  reportar, envia um resumo por e-mail. Com `AI_ENABLED`, o texto é redigido pelo modelo e
  auditado em `AiInteraction` (feature `daily_digest`); sem IA, envia o resumo estruturado.
  No-op quando a flag `email` está desligada. É disparado pelo comando
  `manage.py send_daily_digest`, que o serviço `scheduler` roda todo dia às
  `SCHEDULER_DIGEST_AT` (default 07:30) — FDD 023. Até a FDD 023 esta linha dizia "agendável
  por cron diário na infraestrutura", e esse cron não existia: na prática o digest nunca saía
  em produção.

- **A redação por IA é enfeite; a entrega é o produto.** Quando a OpenAI falha, o digest sai no
  mesmo texto estruturado do modo "IA desligada", com um aviso no log — não interrompe o laço.
  Antes, a chamada era crua **dentro do `for`**: um 429 no terceiro usuário matava a fila, quem já
  tinha sido iterado recebia e o resto não. E o agendador não cai (ele isola o job), então o
  carimbo do dia era gravado assim mesmo e **não havia retentativa até amanhã**. É a mesma regra
  que o `fail_silently` do envio já seguia — um destinatário ruim não pode calar a casa inteira.
  Chamada que não completou **não** gera `AiInteraction`. Observado na rodada 2 da FDD 024.

- **O digest não consome a cota diária de ninguém.** Ele audita com `user=user`, e
  `within_daily_limit` conta essas linhas — então o job das 07:30 tirava 1 das
  `AI_DAILY_LIMIT` chamadas de cada pessoa, por um e-mail que ninguém pediu, e ao mesmo tempo não
  consultava o limite (isento dele e cobrando dele). `daily_digest` entrou em
  `ai.AUTOMATED_FEATURES` e ficou fora da conta: a cota existe para limitar o que uma **pessoa**
  gasta.

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
projeto, mesmo continuando `owner` deles — no digest **e** nas notificações, incluindo o e-mail
espelhado. E o lead novo continua notificando admin/vendas, que é a prova de que a guarda não
extrapolou (`backend/tests/regression/test_notifications_respect_project_membership.py`).

## Fora deste recorte

As notificações **já gravadas** no sino de quem saiu da equipe continuam visíveis, com o título do
item e um link que dá 404. É decisão, não esquecimento: notificação é evento datado, legítimo
quando criado — como e-mail já entregue, não se retrata. Fechá-las exigiria FK `project` em
`Notification` (que hoje só guarda uma `url`) e migração de dados extraindo o id de
`/projetos/<id>`. A causa raiz — item que fica órfão quando alguém sai da equipe — é decisão de
produto ("para quem vai o item?") e provavelmente pede ADR.
