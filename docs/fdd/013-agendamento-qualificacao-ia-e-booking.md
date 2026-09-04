# FDD 013 — Agendamento: qualificação por IA + booking automático

## Jornada

Etapa **Agendamento** da jornada (RFC 0002). Quando um lead envia o formulário do site, a IA
**qualifica** o fit (rascunho para revisão humana); se passar do corte e o calendário estiver
ligado, o site oferece **horários livres reais** e o lead **agenda a reunião automaticamente**,
com evento no Google Calendar e confirmação por e-mail. Fora do corte, segue para contato manual.

## Fluxo

Site → relay FastAPI (`biahflow-site`) → `POST /api/v1/leads/intake/` (cabeçalho `X-Intake-Token`).
O CRM cria o `Lead`, qualifica (`qualification.qualify_lead`) e responde
`{qualified, booking_available, booking_token}`. Se qualificado + calendário ligado, o
`booking_token` (assinado, TTL 1h) autoriza `GET /api/v1/booking/slots/` e
`POST /api/v1/booking/book/`. O `X-Intake-Token` do CRM fica **só no relay**; o browser carrega
apenas o `booking_token` efêmero.

## Regras

- **Qualificação** atrás da flag `ai`: `ai.build_lead_context` (só dados do lead + respostas de
  triagem) → `ai.complete` pedindo JSON `{fit, score, summary, recommended_action}`; parse
  tolerante (cercas de código/texto ao redor); grava em `Lead.ai_fit/ai_score/ai_summary/
  ai_recommended_action/qualified_at`; auditado em `AiInteraction(user=None, lead=…,
  feature="lead_qualification")`. `ai` desligado → sem qualificação e `qualified=False`.
  **O mesmo vale quando a OpenAI falha**: a guarda que a FDD 024 pôs aqui foi finalmente
  observada na rodada 2, com o endpoint apontado para uma porta morta — o POST público
  responde 201, o lead fica gravado e cai na triagem manual, em vez do 500 que o visitante
  via para um cadastro que na verdade funcionou.
- **Corte**: `settings.BOOKING_MIN_FIT` (default `medium` → high+medium qualificam). Só quem passa
  recebe `booking_token`.
- **Disponibilidade** atrás da flag `calendar`: `booking.available_slots` = grade de horário
  comercial (`BOOKING_HOURS`, slots de `BOOKING_SLOT_MINUTES`) menos os períodos ocupados
  (`calendar_sync.freebusy` do `GOOGLE_BOOKING_CALENDAR_ID`, fallback `GOOGLE_CALENDAR_ID`) e menos
  as `Booking` já agendadas; nunca no passado.
- **Reserva** (`booking.book`): recheca o slot livre (freebusy + `Booking` com `select_for_update`)
  → `SlotUnavailable`/409 se tomado; cria `Booking` (ligada ao `Lead`, dono = 1º admin ativo);
  cria o evento com horário + convidado no Google Calendar (carimbo `biahflow_origin`); notifica o
  dono (in-app + e-mail) e envia confirmação ao lead.
- **Segurança**: endpoints públicos autenticam por `X-Intake-Token` + `booking_token`; throttle
  escopo `booking`; 401 sem intake token, 403 com booking token inválido/expirado, 503 com
  `calendar` desligado. Aditivo ao contrato `/api/v1/`.

## Aceite

Lead de bom fit (com `ai` e `calendar` ligados) recebe `booking_token`, vê horários livres reais e
consegue agendar; o `Booking` e o evento no Google Calendar são criados, o dono é notificado e o
lead recebe a confirmação. Lead de fit fraco (ou `ai` desligado) não recebe oferta de agendamento.

## Regressão crítica

Reservar o mesmo horário duas vezes retorna 409 (sem `Booking` duplicada); `slots`/`book` recusam
**A reserva sobrevive à recusa do Google.** `book()` grava a `Booking` e fecha a transação antes
de criar o evento; se o Google recusar (o caso conhecido é `forbiddenForServiceAccounts`, que conta
de serviço leva ao convidar participante sem delegação em todo o domínio), a reserva **vale** — o
horário está de fato comprometido —, o dono é avisado **com a ressalva de que a reunião não entrou
na agenda**, o lead recebe a confirmação e o visitante vê 201. Antes a exceção subia: sobrava uma
reserva bloqueando o horário, sem evento, sem aviso e sem confirmação, e o endpoint público
devolvia 500.

`booking_token` inválido ou expirado; com `calendar` desligado os endpoints retornam 503; a
qualificação tolera saída não-JSON do modelo sem quebrar o intake.

## Emenda de 02/09 — o Discovery do Design Partner entra na mesma agenda

O ciclo do Design Partner terminava num beco: o acordo era assinado, o mandato nascia
(`design_partner.abrir_engagement_do_acordo`) e o cliente não recebia nada. Agora a assinatura
dispara um convite por e-mail com um link onde **o próprio cliente escolhe o horário do
Discovery**. Superfície governada pelo DAP `docs/design/dap-agendamento-discovery-r1/`, r1,
decisões **A1 · B1 · C1 · D1 · E2**; a página é trabalho separado do backend descrito aqui.

- **`Booking` serve os dois fluxos**, e é a decisão que sustenta todas as outras. `lead` passou a
  ser opcional (o Design Partner não tem lead), entrou `Booking.engagement`, e uma
  `CheckConstraint` (`booking_has_exactly_one_origin`) cobra "exatamente um" no banco, espelhada
  em `clean()`. Criar só o evento no Google seria mais curto e estaria errado: o teste de conflito
  consulta a **tabela**, não o Google, porque a criação do evento é best-effort e pode falhar — um
  Discovery sem evento deixaria o horário parecendo livre para a pré-venda, e vice-versa.
  Regressão: `tests/regression/test_os_dois_fluxos_de_agendamento_nao_marcam_o_mesmo_horario.py`.
- **Um núcleo de reserva** (`booking._reservar`) com duas entradas finas: `book(lead, slot)` —
  inalterada — e `book_discovery(engagement, slot, attendee_email)`. Dois núcleos parecidos seriam
  duas agendas que não se veem.
- **Token próprio** (`discovery_booking`): `signing.dumps({"engagement": id})`, salt distinto do de
  pré-venda (salt compartilhado deixaria um token servir para a outra rota) e validade alinhada ao
  horizonte de 14 dias.
- **Duas rotas públicas**, `AllowAny` e throttle `discovery_booking`:
  `GET /api/v1/booking/discovery/slots/?token=` (devolve `account`, `slots`, `scheduled_at`) e
  `POST /api/v1/booking/discovery/`. **Os quatro estados da D1 são distinguíveis pelo `code` da
  resposta** — `token_expired` (400), `token_invalid` (400, sem dizer por quê), lista vazia (200) e
  `calendar_unavailable` (503) —, porque colapsá-los faria a página afirmar "não há horário" quando
  o que houve foi a agenda não responder. Sem remarcação (C1): mandato já agendado devolve 409
  `already_scheduled` no `POST` e o horário marcado no `GET`. O e-mail do convidado sai do acordo
  assinado, nunca do corpo da requisição.
- **O convite** é constante de código revisada (redação **E2**), texto puro, enviada de
  `esign.apply_decision` **fora** da transação e best-effort: SMTP fora do ar não desfaz a
  assinatura nem o mandato.
- **Flag `discovery_booking`**, nascida desligada: governa as duas rotas **e** o e-mail — separá-las
  produziria o pior estado, o cliente recebendo um convite que a página recusa.

## Emenda de 02/09 (2) — a janela do Discovery encolhe, e só a dele

A emenda acima deixou a oferta do Discovery igual à da pré-venda: 14 dias corridos e **todos** os
horários livres da grade. O primeiro teste em uso mediu **80 opções** numa página que pede uma —
lista longa não é escolha, é adiamento. O DAP `dap-agendamento-discovery-r1` recebeu a emenda da
janela e o horizonte saiu de "fora da aprovação".

- **`booking.available_slots_for_discovery()`** oferta **3 dias** de prazo, **5 dias com grade** e
  **3 horários por dia**. Três constantes nomeadas (`DISCOVERY_LEAD_TIME_DAYS`,
  `DISCOVERY_BUSINESS_DAYS`, `DISCOVERY_MORNING_END_HOUR`/`DISCOVERY_AFTERNOON_START_HOUR`) e nenhum
  número solto: os três eixos respondem perguntas diferentes e vão divergir na próxima revisão.
- **"Dia útil" é dia com grade**, lido de `BOOKING_HOURS` — não uma segunda definição de calendário.
  Contar corrido entregaria três dias de oferta na semana que começa numa quinta.
- **Os três do dia são papéis, não contagem** (`booking.tres_do_dia`): primeiro livre da manhã,
  primeiro livre da tarde, último livre do dia. Papéis que coincidem viram um, e é dessa
  deduplicação que sai "menos de três livres oferece os que existem" — uma segunda regra de
  contagem poderia discordar da primeira. Dia sem livre não aparece, que continua sendo diferente
  do estado "sem horários" da D1.
- **A pré-venda não muda.** `available_slots` segue com os 14 dias corridos e todo horário livre: o
  lead que veio do site tem outro problema. As duas dividem a **agenda** (`_slots_livres` — mesma
  grade, mesmo free/busy, mesma tabela `Booking`) e nada mais, pela razão de `_reservar`.
  Regressão: `tests/regression/test_a_janela_do_discovery_nao_e_a_da_pre_venda.py`, que existe para
  impedir a "simplificação" que unifica as duas ofertas e encolhe a rota do site sem nada ficar
  vermelho.

## Emenda de 02/09 (3) — o projeto nasce quando o cliente marca o horário, e o que já aconteceu fecha

As duas emendas acima levaram o ciclo do Design Partner até a reserva. O que ficava depois dela era
manual e cego, em duas metades independentes.

### O projeto nasce da sessão marcada

O último passo do caminho feliz era alguém abrir o detalhe da conta e clicar em "Novo projeto". No
instante em que o cliente marca a sessão **tudo já está determinado**: o mandato existe, o degrau é
o Discovery Sprint (é para isso que o acordo foi assinado) e as datas saem da sessão, porque o dia
dela é o dia 0. `DiscoveryBookingCreateView` passa a fazer o projeto nascer ali, **depois** de
`booking.book_discovery` e **fora** da transação dela.

- **O ato de criar projeto do mandato virou uma função só**, `kickoff.criar_projeto_do_mandato`, e
  o refactor não é acessório: a lógica morava dentro de `EngagementViewSet.create_project`, e
  repeti-la na rota pública produziria duas definições do mesmo ato — que não divergem no dia em
  que nascem, e sim na primeira manutenção. Ela contém o que roda **dentro** da transação (trava do
  mandato, gravação, `seed_work_items`, `registrar_sessao_no_projeto`, `seed_invoices`); ficam de
  fora a validação de quem chamou, que é diferente nos dois, e o `finalize`, que é efeito externo
  depois do commit. A action não mudou de comportamento observável. Regressão:
  `tests/regression/test_a_rota_publica_e_o_botao_criam_o_projeto_igual.py`.
- **O dono é o do mandato**, e é a diferença que mais confunde quem comparar com a action: lá o
  dono é `request.user`, aqui a rota é **pública** e não há usuário autenticado nenhum.
- **As datas saem da sessão**: `start_date` é a data **local** da reserva (a UTC jogaria uma sessão
  das 21h para o dia seguinte, a mesma armadilha de `registrar_sessao_no_projeto`) e `due_date` é
  `+ DURACAO_DO_DISCOVERY_SPRINT_EM_DIAS`. Sete porque o Discovery dura de 5 a 7 dias — é o que o
  convite promete — e o template de kickoff do degrau fecha no Executive Readout em D+7.
- **Sem `Service` ativo no degrau, o projeto não nasce.** Ele cairia no template genérico de
  `kickoff.template_for` e nasceria **sem os marcos que são a metodologia** — sem walkthrough, sem
  custo do estado atual, sem Executive Readout —, e nada ficaria vermelho. A reserva do cliente
  continua valendo; fica o log e um aviso interno a quem responde pelo mandato, dizendo o que
  faltou. É a metade que impede um projeto de nascer sem metodologia.
- **Nada disso derruba o agendamento.** Falhe o que falhar, a resposta segue 201 — inclusive quando
  o próprio aviso interno falha. O cliente marcou o horário; o projeto é consequência interna da
  casa, e derrubar a reserva por causa dela seria punir o cliente por um problema nosso — além de
  deixar o horário parecendo livre para o outro fluxo, que é o defeito que a linha `Booking` existe
  para impedir.
- Guarda de existência igual à do duplo clique: **nenhum projeto vivo do degrau no mandato**. Um
  mandato origina vários projetos por desenho (ADR 0050), mas o Discovery Sprint dele é um.

### Nada fechava a sessão realizada

**Nenhuma linha do sistema** transicionava `Booking` ou `Meeting` para `held`: as duas nasciam
`scheduled` e ficavam `scheduled` para sempre, e a casa nunca ficava sabendo que a conversa
aconteceu. É por isso que a travessia da sessão para o projeto precisou de guarda de degrau — a
reserva continua "viva" meses depois.

`booking.fechar_sessoes_realizadas` fecha o que já passou, e o job `sessions_held`
(`manage.py mark_sessions_held`, `SCHEDULER_SESSIONS_AT`, default **06:30**) o chama todo dia.

- **Os dois modelos num lugar só**, porque a pergunta é uma — "esta sessão já aconteceu?" — e duas
  funções divergiriam na primeira mudança de corte.
- **O corte de cada uma é o que ela sabe**: a reserva tem hora de fim e fecha quando o fim passou;
  `Meeting.date` é `DateField`, e um dia só termina quando vira o dia seguinte (`date__lt`, no
  molde de `invoices.mark_overdue`).
- **Antes do digest das 07:30**, pela mesma razão de ordem do vencimento de faturas: o resumo do
  dia anunciaria como agendada a sessão de ontem.
- **Idempotente por construção** — o filtro por `status` exclui o que a rodada anterior mudou —, e
  o comando **conta** o que fechou: job silencioso sem resumo só pode ser lido como quebrado.
  Reserva **cancelada** e linha **arquivada** ficam de fora: cancelada não aconteceu, e arquivada
  saiu da vista de propósito.
