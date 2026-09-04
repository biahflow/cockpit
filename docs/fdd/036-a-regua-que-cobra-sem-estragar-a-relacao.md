# FDD 036 — A régua que cobra sem estragar a relação

> **Status: entregue (19/08/2026), e desligada.** Camadas 3 e 4 da **RFC 0004**, sobre as camadas
> 0 e 1 que a FDD 028 entregou. A flag `cobranca` nasce **desligada** — construir não é ligar, e a
> seção "O pressuposto que não se cumpriu" diz por quê. Ver "O que a construção decidiu", no fim,
> para os onze pontos em que o construído diverge do escrito aqui.

## Jornada

A FDD 028 tirou a inadimplência da invisibilidade: existe `Invoice`, existe vencimento,
existe pagamento, e um trabalho agendado às 06:00 marca vencida a fatura cujo prazo passou.
O que ela não fez — e disse que não faria, no lugar certo — foi avisar alguém. O docstring de
`invoices.mark_overdue` é literalmente o começo desta fatia:

> "**Nenhuma notificação sai daqui**, e a próxima pessoa vai querer adicionar uma. Aviso é
> camada 3 da RFC 0004, que só entra depois de a reconciliação estar de pé."

Então hoje o portal **sabe** quem está vencido e **não diz a ninguém**. Nem ao cliente, que na
maioria dos casos apenas esqueceu, nem a quem responde pela relação. A inadimplência deixou de
ser imensurável e continua inerte, e um número que ninguém aciona custa quase o mesmo que
número nenhum.

A tentação, aqui, é construir um agente de cobrança. A RFC 0004 passa metade do texto
explicando por que isso é o erro: *"O objetivo não é receber esta fatura — é receber e manter
o cliente. Existe cobrança que recupera o dinheiro e mata a relação, e ela é mau negócio mesmo
quando o boleto entra."* Esta fatia é escrita contra essa tentação.

## O pressuposto que não se cumpriu

A RFC abre o plano de migração por **medir**: registrar vencimento e pagamento, olhar dois ou
três meses, e *"se a dor for pequena, parar aqui — e considerar isso um bom resultado"*. A
FDD 028 entrou em 07/08/2026 e esta fatia é de 19/08. São **doze dias**. A medição que
justificaria a régua não existe.

O segundo pressuposto é mais duro. A camada 1 — a reconciliação — é o que **desarma** a régua,
e ela nunca foi exercitada: o Stripe segue sem homologação (runbook
`homologacao-de-integracoes.md`, seção 5, "pendente"). As cinco rodadas anteriores acharam
defeito, cada uma, e **três acharam a mesma classe**: registro gravado sem o fornecedor ter
sido chamado. Se a baixa por webhook tiver esse defeito, a régua cobra quem pagou — que é
exatamente o desfecho que a ordem das camadas existia para impedir.

Nada disso impede construir; impede **ligar**. Por isso a flag `cobranca` nasce desligada, por
uma razão que não é custo nem credencial, e por isso a homologação do Stripe
(runbook, seção 5) é pré-requisito declarado de qualquer instalação real ligar esta régua. Está escrito aqui para que a próxima
pessoa não leia a flag desligada como esquecimento.

## O que esta fatia entrega

A escada determinística sobre a fatura, o registro do que saiu, a suspensão declarada, e os
dois usos de IA que a RFC autoriza — rascunhar o tom e classificar a resposta.

### A escada

| Offset | Degrau | Destino | O que ele é |
| --- | --- | --- | --- |
| D−3 | `pre_notice` | cliente | favor, não cobrança: a fatura ainda nem venceu |
| D+1..D+2 | *carência* | ninguém | o silêncio é o degrau |
| D+3 | `reminder` | cliente | neutro |
| D+10 | `firm` | cliente | firme |
| D+20 | `escalation` | interno | não sai para o cliente: acorda quem responde pela relação |
| D+30 | `renegotiation` | interno | pede decisão humana |

> **Os cinco valores da coluna Degrau falam inglês desde a fatia 5.4 da issue #122** (D10 do
> `language-map`, 04/09/2026): a classe virou `DunningContact`, o campo `dunning_step`, e os
> valores acima acompanharam. O rótulo que a tela mostra (`Pré-aviso`, `Lembrete`, `Cobrança
> firme`, `Escalada interna`, `Renegociação`) não mudou — é superfície, e só o que persiste no
> banco mudou de idioma. Ver `docs/ontology/aliases.md`.

A carência **não tem linha**. Ela é o intervalo entre o vencimento e o lembrete, e
representá-la como um degrau que não faz nada convidaria alguém a preenchê-lo.

Os dois últimos degraus não falam com o cliente. A RFC os descreve como "escalada para humano"
e "renegociação", e as duas coisas são atos de gente: o que o sistema faz é acordar a pessoa
certa com o contexto na mão.

### A segmentação por relação

A régua tem duas formas, escolhidas por função pura sobre o cliente:

- **`PADRAO`** — a tabela acima.
- **`RELACAO_LONGA`** — cliente com pelo menos um ano de casa e **sem reincidência**: o
  lembrete atrasa, o degrau firme **não existe**, e o caso vai direto à escalada interna.

Isto não é refinamento; é requisito da seção Segurança da RFC: *"cinco dias de atraso de um
cliente antigo não é o mesmo evento que reincidência"*. Uma régua que trata os dois igual está
programada para perder o cliente melhor da carteira, e vai fazê-lo por uma fatura.

Reincidência sai do dado que já existe — fatura paga depois do vencimento (`paid_at` contra
`due_date`) ou vencida agora (a `property is_overdue` da FDD 028). Nenhum campo novo: o
histórico de atraso sempre esteve gravado, faltava alguém perguntar.

### Os tetos duros

A RFC pede *"teto duro de frequência e de horário"*, e os três são deliberados:

- **Um contato por cliente a cada cinco dias**, somando todas as faturas. Quem tem três
  vencidas recebe um e-mail, não três — e três e-mails no mesmo minuto é a forma mais rápida
  de um sistema de cobrança parecer um robô hostil.
- **Nada em fim de semana.** Cobrança que chega no sábado é lida como falta de educação, e o
  ganho de mandá-la dois dias antes é zero.
- **Sem contato de cobrança cadastrado, nada sai para o cliente**: o degrau vira escalada
  interna com o motivo escrito. Falha fechada, no padrão que a FDD 030 já usou para o
  enriquecimento — cala quando não sabe, em vez de chutar o destinatário de um e-mail sobre
  dinheiro.

### Recuar é declarado

Suspender a cobrança quando a entrega está atrasada ou o cliente está insatisfeito é a regra
certa e, nas palavras da RFC, *"a que mais apodrece na prática: vira desculpa para nunca
cobrar, e o recebível estraga invisível"*. Então a suspensão tem **dono, prazo e motivo
obrigatórios**, é linha no banco, aparece na tela com a data em que expira, e expira sozinha.
Não existe "pular" silencioso em nenhum dos dois sentidos: nem calar sem registro, nem voltar
a cobrar sem que a suspensão tenha vencido.

### Onde a IA entra — e onde não entra

Os dois usos que a RFC autoriza, e nada além:

- **Rascunhar o tom do degrau.** Pedido na tela, devolvido para revisão, enviado por uma
  pessoa. Nunca sai sozinho — a razão está na **ADR 0031**.
- **Classificar a resposta do cliente**, roteando entre os três problemas que a mesma régua
  estraga: *esqueceu* (o lembrete resolveu), *não pôde* (renegociação, e cedo) e *está
  insatisfeito e retendo pagamento como sinal* — que não é problema de cobrança, é problema de
  relação disfarçado, e onde insistir piora tudo. A resposta chega como `Activity` (FDD 035),
  digitada por quem atendeu; a IA grava o sinal e **não age**.

### A cerca comercial

O valor da fatura é do cliente por direito; **custo e margem nunca saem**. O contexto do
rascunho leva cliente, valor, vencimento, dias, degrau, tempo de casa, o **nível** de health e
se há entrega atrasada. Não leva `actual_value`, não leva ROI, não leva `roi_snapshot`, não
leva fatura de outro cliente, e não leva o corpus interno — este último de graça, porque o
`grounding` só é preenchido pelo `AgentView` e o ponto de injeção é único (FDD 029).

## Contrato

Rotas novas em `/api/v1/`, todas aditivas:

| Rota | Quem |
| --- | --- |
| `/cobranca/` (leitura do que saiu; `?client=`, `?invoice=`, `?degrau=`, `?canal=`) | admin / Vendas lê |
| `/cobranca/painel/` (a decisão: próximo degrau + a relação à vista) | admin / Vendas lê |
| `/cobranca/suspensoes/` e `.../{id}/levantar/` | admin / Vendas (a suspensão é decisão de relação) |
| `/invoices/{id}/cobranca/rascunhar/` | admin |
| `/invoices/{id}/cobranca/enviar/` | admin |
| `/activities/{id}/classificar/` | admin / Vendas |

Entrega **não alcança nenhuma delas**, nem para ler, pelo mesmo mecanismo que fecha `invoice`
na FDD 028: o recurso não entra em conjunto nenhum e o `has_permission` termina em
`return False`. Recurso novo nasce fechado.

Campos novos, todos opcionais: `Contact.receives_billing`, `Activity.invoice` e
`Activity.dunning_signal` (chamava-se `Activity.cobranca_sinal` até a fatia 5.2 da issue #122;
as chaves de payload `cobranca_sinal`/`cobranca_sinal_display` continuam saindo até a
`/api/v2/`, ver `docs/ontology/aliases.md`).

## Critérios de aceite

1. **Ninguém que pagou é cobrado.** Fatura baixada entre duas execuções não recebe degrau
   nenhum — e não por uma rotina de cancelamento, mas porque a régua é derivada do estado e
   `paid` é terminal. É o pecado capital da RFC, e tem regressão dedicada.
2. **O degrau não se repete**, nem no mesmo dia nem no seguinte. A idempotência é
   `UniqueConstraint(invoice, dunning_step)` (campo `degrau` até a fatia 5.4 da issue #122), não
   uma guarda em Python.
3. **Custo e margem não saem** — teste estrutural além do comportamental, no molde do
   anti-vazamento do corpus (FDD 029).
4. **Suspensão ativa cala a régua; suspensão vencida a devolve**, sem intervenção.
5. **A régua funciona com a IA desligada.** O texto do degrau é constante; a IA some da tela e
   não sai um lembrete do ar.
6. **O vencimento é apurado antes da régua rodar** — 06:00 contra 09:30 —, com teste de ordem
   na tabela de jobs, no molde do que a FDD 028 já fez contra o digest.
7. **A tela decide com a relação à vista.** Health, tempo de casa, total já recebido e
   reincidência na mesma linha do próximo degrau — a RFC exige "na mesma tela, não a dois
   cliques", e a dois cliques ninguém olha.

## Fora deste recorte

- **A homologação do Stripe** (runbook, seção 5). É pré-requisito de ligar, e é trabalho próprio.
- **Nota de crédito, NFS-e e trocar a fonte do ROI** — os três já estavam nomeados como fora
  pela FDD 028, e o terceiro segue pedindo ADR própria.
- **WhatsApp.** O canal é e-mail. A RFC prevê os dois; um canal novo é adaptador novo, e o
  gate da ADR 0031 já vale para ele.
- **Caixa de entrada de verdade.** A resposta do cliente entra como `Activity` digitada por
  quem atendeu. Ler e-mail recebido é integração nova, com todos os problemas de uma.
- **A camada 5 completa da RFC** (travas plugadas em satisfação e nos sinais de entrega). O
  que entra aqui é o mínimo que a seção Segurança exige da própria camada 3: segmentar por
  relação e decidir com a relação à vista. Satisfação continua sem onde ser registrada — a
  mesma lacuna que o `health.py` declara desde a Fase 2.

## O que a construção decidiu

Doze pontos em que construir mudou o desenho. Ficam aqui, e não no commit, porque é esta página que
a próxima pessoa lê.

**O degrau virou janela, e não offset.** "Passou de D−3" mandaria o pré-aviso em D+1 se a régua não
tivesse rodado no dia — fim de semana, flag desligada, fatura emitida em cima da hora. Um "sua
fatura vence em 3 dias" chegando depois do vencimento é mentira escrita pela casa. Com janela, o
degrau simplesmente não cabe mais e o próximo assume. A carência continua sendo o **buraco** entre
duas janelas, e continua sem entrada na tabela.

**A régua da relação longa reusa a chave do lembrete padrão, e não cria uma nova.** A idempotência
é `UniqueConstraint(invoice, dunning_step)`. Se um cliente mudar de régua entre duas execuções — completou
um ano, deixou de ser reincidente —, uma chave própria faria o mesmo lembrete sair duas vezes. O que
muda entre as duas escadas é a janela, não a identidade do degrau.

**A reincidência exclui a própria fatura, e isso é o que faz a segmentação existir.** Sem
`ignorando=`, toda fatura vencida tornaria o próprio cliente reincidente, e a régua da relação longa
seria inalcançável exatamente quando serve para alguma coisa. Reincidência é histórico: *outras*
faturas. Foi o desvio de maior consequência da construção — sem ele, a exigência da RFC existiria
só no papel.

**`sent_on` é data, não carimbo de relógio**, ao contrário de `paid_at` e `issued_at`. Toda regra da
régua é aritmética de dias, e o comando aceita `--hoje`; gravar `now()` faria o teto de frequência
comparar o dia simulado com o dia real, e a régua se comportaria diferente no teste e no ar. O
relógio de parede continua no `created_at` herdado.

**Suspender é viewset próprio, não uma ação na fatura.** Uma action em `/invoices/{id}/` só
alcançaria metade do modelo: a suspensão vale para uma fatura **ou** para o cliente inteiro. A
consequência é boa — a permissão virou recurso próprio (`cobranca_suspensao`), e é por ele que
Vendas escreve sem escrever em fatura nenhuma.

**O teto de frequência só vale para o que vai ao cliente.** A RFC descreve o teto como limite de
*contato*; a escalada interna não chega ao cliente, e submetê-la ao mesmo teto atrasaria justamente
o degrau que existe para acordar gente. Pela mesma razão, o **envio manual não aplica o teto**: ele
contém o robô que ninguém está olhando, e quem clica está olhando.

**Escalada sem ninguém a acordar não gasta o degrau.** Achado da revisão do diff, e o mais caro dos
três: com o dono do cliente inativo e nenhum admin, a notificação ia para lista vazia, o contato era
gravado e o degrau não voltava — a régua parava de falar com o cliente e ninguém ficava sabendo. É o
"pular silencioso" que a RFC recusa, na direção que ninguém olha. Agora levanta, a falha é contada e
logada (vira evento no Sentry, ADR 0012), e o degrau volta a caber quando existir a quem escalar.

**Quem recebe a escalada é `role == admin` ou `is_superuser`** — o mesmo predicado que autoriza no
backend, e não só o papel. `manage.py createsuperuser` cria com `role` no default (`delivery`), então
numa instalação nova o único admin que existe é justamente o que um filtro por papel deixaria de
fora. É a FDD 017 outra vez, agora do lado do servidor.

**A flag vale para o envio manual, e não vale para o rascunho de IA.** Sem a primeira metade,
"Régua de cobrança: desligada" na tela de Configurações seria mentira — o relógio calaria e a API
seguiria mandando cobrança. A segunda metade é deliberada: rascunhar não sai da casa, e quem avalia
se vale ligar a régua tem motivo legítimo para ver o que o modelo escreve antes de decidir. As
guardas de `_ai_run` (flag `ai` e cota) continuam valendo.

**O painel pré-carrega o insumo; ele não recalcula a decisão.** `avaliar` faz quatro perguntas ao
banco por fatura, e o painel é um laço sobre faturas — sem pré-carga são quatro N+1 simultâneos, que
é o defeito que a ADR 0014 mediu quando `/clients/overview/` foi de 43 a 169 queries. A saída foi um
parâmetro `contexto=` que troca a **fonte** do dado e não a regra, no movimento que
`assess_project_health(project, milestones=…, tasks=…)` já fazia. O contexto nasce ligado a um dia e
recusa outro: teto e reincidência são recortes de "hoje", e um contexto de ontem produziria silêncio
sem nada ficar vermelho.

**Dinheiro sai do painel como string, não como número.** Um `Decimal` num agregador que não passa
por serializer vira float no encoder do DRF: `10000.01` passaria a depender do binário, e — pior que
o centavo — `amount` seria string em `/invoices/` e número em `/cobranca/painel/`, com o SPA
obrigado a saber qual é qual.

**A carência é testada no relógio da rota, e a suíte não alcança fornecedor.** O teste que pede um
rascunho quando nenhum degrau cabe congela o `localdate()` que `degrau_devido` realmente lê e prova
que `ai.complete` não foi chamado. A cerca global da ADR 0059 impede qualquer teste backend de
resolver DNS, conectar ou enviar UDP para fora — inclusive por cliente async; mocks terminam no
limite do adapter, enquanto loopback e Unix socket seguem livres para infraestrutura local de teste.
