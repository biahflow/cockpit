# ADR 0061 — A assinatura abre o mandato, e o que ela abre se declara antes

**Status:** aceita
**Data:** 2026-09-02
**Depende de:** ADR 0007 (assinatura eletrônica) · ADR 0016 (como o portal se autentica no Google)
· ADR 0050 (o Engagement entre a conta e o projeto) · ADR 0053 (a escada de seis degraus e o
Design Partner) · ADR 0058 (o Engagement nasce do instrumento assinado) ·
`docs/ontology/language-map.md` §6, invariantes 7 e 13
**Implementada por:** FDD 013 (emenda 02/09) · FDD 046 (emenda 02/09) ·
DAP `dap-agendamento-discovery-r1` · DAP `dap-finalidade-do-documento-r1` ·
DAP `dap-engagement-r3`

## Contexto

A ADR 0058 fechou a invariante 13 pela **origem** do mandato: um `Engagement` só nasce de um
instrumento assinado, e o `design_partner` nasce de um Design Partner Agreement. O que ela não
resolveu foi o **movimento**: quem transforma a assinatura em mandato continuava sendo uma pessoa,
abrindo um formulário depois de conferir num e-mail que o documento voltou assinado.

O ciclo do Design Partner terminava, na prática, em três becos encadeados:

- **A assinatura não tinha consequência.** `esign.apply_event` fechava o artefato de contrato e
  notificava; o mandato ficava esperando alguém lembrar.
- **O cliente não recebia nada.** Nenhum e-mail transacional saía para o cliente em evento de
  contrato — só notificação interna para quem subiu o arquivo. O primeiro passo depois de assinar
  era um silêncio que alguém precisava quebrar por fora do produto.
- **O mandato não virava projeto.** `Project.engagement` é `NOT NULL`, e o único caminho de criação
  na SPA era a conversão de venda ganha, que carimba `paid`. Design Partner não passa por venda:
  o Discovery não virava projeto sem um `POST /projects/` fora da tela.

Automatizar isso esbarra num problema que não é de implementação: **o sistema não sabia o que era
o documento assinado.** `Document` era genérico — o único discriminador era `original_name`, string
livre do upload. Um gancho na assinatura dispararia igual para um NDA, um contrato comercial e um
acordo de parceria.

## Decisão

**A assinatura passa a ter consequência de domínio, e a intenção é declarada antes dela, não
inferida depois.** Três partes de uma decisão só.

### 1. A finalidade é campo do documento, declarada no upload

`Document.kind`, `TextChoices`, com **um** valor: `design_partner_agreement`. Não é classificação
de arquivo — é o que liga o comportamento, e por isso o rótulo na tela é "Finalidade" e não "Tipo".

O enum nasce com um valor porque só um tem consumidor. Valor sem chamador é a mesma dívida que
classe sem chamador, e é a regra que já tirou `.btn--ghost` e `accent-200` do CSS.

`Artifact.kind` **não** servia, e a razão é estrutural, não estilística: `Artifact.clean()` exige
âncora em oportunidade ou projeto, e o acordo de parceria vive na **conta** — é o que
`Engagement.clean()` compara. Um artefato para esse documento não teria onde pendurar.

Um `kind = design_partner_agreement` só se ancora numa `Account`. A invariante mora nas **duas**
metades — `Document.clean()` e `DocumentSerializer.validate()` — porque o serializer não chama
`full_clean()`, e shell, admin e migração não passam por rota.

### 2. A assinatura conclui num lugar só, e é dali que o mandato nasce

Havia **dois** caminhos que concluíam uma assinatura, e eles divergiam: `esign.apply_event` (o
webhook) fechava artefato e notificava; `DocumentViewSet.mark_signed` — o fallback usado sempre que
não há provedor homologado, e portanto **o caminho real** — só gravava `status`/`signed_at`. O mesmo
fato de negócio produzia efeitos diferentes conforme a porta.

`esign.apply_decision(signature_pk, new_status)` passa a ser o único lugar onde uma assinatura se
conclui, e os dois caminhos passam por ela. Ela recebe **pk** e não a instância já lida, de
propósito: a trava é parte da operação, e uma API que aceitasse o objeto carregado permitiria
chamá-la sem travar nada.

Dentro dela, `transaction.atomic()` mais `select_for_update()`. Antes não havia nem um nem outro no
webhook: duas entregas simultâneas duplicavam uma notificação — dano cosmético. **A partir do
momento em que a assinatura cria linha, a mesma janela viraria `IntegrityError` não tratado → 500
para o fornecedor → reentrega em laço.** A guarda de idempotência lê a linha já travada, que é o
que a torna verdadeira sob concorrência e não só sob reentrega sequencial.

`design_partner.abrir_engagement_do_acordo` cria o mandato quando — e só quando — as quatro
condições valem: `kind` certo, conta vinculada, assinatura concluída, e nenhum mandato já originado
por aquele documento. Fora delas, silêncio. **Essa é a metade que mais importa:** um mandato que
nasce da assinatura errada não faz barulho nenhum ao nascer.

O nome é derivado (`Design Partner — {conta}`) e o dono é quem subiu o documento, porque o webhook
não tem usuário autenticado. Derivar nome não é invenção nova: `convert-to-project` já cria
Engagement com o título da oportunidade. Mandato, patrocinador e definição de sucesso ficam vazios
— são julgamento humano, e a pessoa os edita depois.

### 3. A consequência alcança o cliente, por uma rota pública com token

O mandato recém-nascido dispara um e-mail ao signatário com um link onde ele escolhe o horário do
Discovery. O texto é **constante de código, revisada uma vez** — é isso que autoriza um e-mail a
sair sozinho, o mesmo desenho do `Degrau` de `cobranca.py`. O envio é best-effort e fora da
transação: a assinatura não pode ficar por aplicar porque o SMTP caiu.

A rota `/agendar/<token>` é pública. **Não é a primeira do produto** — `/aceitar-convite` já era,
e também movida a token. O que ela tem de inédito é a audiência: aquela fala com alguém que está
virando usuário do Pulse, esta fala com um cliente que nunca vai ter login. O token é a credencial:
assinado com `django.core.signing`, escopado a **um** mandato, com validade alinhada ao horizonte de
oferta — um link que sobrevive à janela que ele mostra abre numa página sem horário nenhum, e o
cliente lê "sem horários" quando o que houve foi o link vencer.

O salt é **próprio**, distinto do booking de pré-venda: salt compartilhado deixaria um token servir
para a outra rota, e quem recebeu o convite do Discovery passaria a agendar como lead qualificado.

O e-mail do convidado do evento vem do **mandato**, nunca do corpo da requisição. Aceitá-lo do
payload deixaria quem tem o link redirecionar o convite do Google para terceiros.

`Booking` passa a servir os dois fluxos — `lead` vira nulável, entra `engagement`, com restrição de
banco de "exatamente um". Não bastaria criar só o evento no Google: o teste de conflito consulta a
tabela `Booking`, e essa linha existe porque o evento **pode falhar**. Sem ela, um Discovery com
falha no Google deixaria o horário parecendo livre para o outro fluxo.

### E o que a rota de projeto herda disso

`POST /engagements/{id}/create-project/` fecha o ciclo, com guarda de papel própria. Não é
`POST /projects/` cru por três razões verificadas: ele só passa para admin, não semeia nada, e a
invariante 6 não roda no serializer.

Uma consequência só apareceu com ela: sem oportunidade de origem,
`invoices.contracted_value` cai no `Service.list_price`, e o Discovery Sprint vale R$ 3.000 desde a
migração `0064`. **Um mandato `design_partner` semearia cobrança contra quem a casa decidiu não
cobrar.** A guarda entrou em `invoices.seed_invoices`, onde a cobrança se decide — quem semeia
fatura pergunta uma vez só, e a próxima rota que criar projeto herda a resposta.

## Consequências

- A assinatura deixa de ser registro e passa a ser **ato com efeito**. Quem depurar um mandato que
  apareceu sozinho tem um lugar para olhar: `apply_decision`, e a notificação que ela emite.
- **Documento sem finalidade continua inerte.** A automação é opt-in por declaração, e o custo
  disso é real: esquecer de marcar o `kind` no upload faz a assinatura passar sem abrir mandato,
  sem nada avisando. É o preço de não inferir intenção do nome do arquivo.
- **Design Partner não fatura**, e agora isso é regra em código, não convenção. Mandato pago com o
  mesmo degrau continua faturando — a guarda é sobre o modelo comercial.
- O e-mail ao cliente é **irreversível**, e a flag `discovery_booking` nasce desligada por isso.
- A rota pública é superfície de ataque nova, mitigada por token assinado, escopado, expirável e
  com throttle próprio — e por a página não expor nada além dos horários e do nome da conta.
- **A idempotência é derivada do estado, não da identidade do evento.** Não há registro dos eventos
  recebidos do fornecedor, então uma sequência `signed → declined → signed` reexecutaria os efeitos
  na segunda passagem. Fica registrado como limite conhecido.

## Alternativas consideradas

**Inferir a finalidade do nome do arquivo.** Rejeitada: `original_name` é string livre do upload,
e um "contrato-parceria-final-v2.pdf" abriria mandato por acidente. A regra da casa é que o sistema
cala quando não sabe.

**Pendurar o efeito só no `apply_event`.** Rejeitada: deixaria o `mark-signed` descoberto — que é
justamente o caminho usado quando não há provedor homologado, ou seja, o caminho real hoje.

**Criar o mandato em estado provisório antes da assinatura.** Rejeitada: a `CheckConstraint`
`engagement_has_one_origin_or_needs_review` e o `clean()` recusam mandato novo sem instrumento, e
`needs_review` existe para o legado de backfill, não para nascer assim.

**Reusar o token do booking de pré-venda.** Rejeitada pelo salt: um token serviria para as duas
rotas, e as duas têm autorizações diferentes.

**Não persistir `Booking` no fluxo do Discovery.** Rejeitada: o horário deixaria de ser bloqueado
para o outro fluxo sempre que o evento no Google falhasse — e o código já trata essa falha como
esperada.
