# RFC 0004 — Contas a receber e cobrança relacional

> **Status: proposta.** Nada aqui está implementado. RFC porque acumula três gatilhos:
> **domínio novo** e transversal, **integrações externas** (gateway de pagamento e emissão
> de NFS-e) e **impacto sobre um contrato que já cruza ao cliente** — o ROI.

## Motivação

O portal carrega a oportunidade da venda até a operação, e para no ponto em que o dinheiro
deveria entrar. Não há domínio de faturamento: entre os modelos de `apps/core/models.py` não
existe fatura, pagamento, vencimento ou conta a receber. `Service.list_price` e
`CommercialOpportunity.value` são **preço**; `Project.actual_value` é um número digitado. Nenhum
deles responde "cobrei o cliente X, R$ Y, vence dia Z, está pago?".

A consequência prática vem antes de qualquer discussão de agente de cobrança: **hoje a
inadimplência é imensurável**. Não existe data de vencimento nem data de pagamento em lugar
nenhum, então não há como responder quantos clientes atrasam, por quantos dias, e quanto
isso custa em caixa.

Por isso esta RFC abre pelo passo zero, e ele não é modelar: é **medir**. Registrar
vencimento e pagamento por dois ou três meses responde se a dor justifica a régua. Se forem
poucos clientes atrasando poucos dias — o cenário provável numa carteira pequena de ticket
alto —, um pré-aviso e um humano atento resolvem, e um agente elaborado seria um sistema de
cobrança maior que a inadimplência que ele combate. A sofisticação tem que casar com o
tamanho da dor.

## Alternativas consideradas

**Não modelar nada e usar o ERP do gateway como fonte da verdade.** Rejeitada pela mesma
razão que a ADR 0004 rejeitou o espelho de tarefas sem sistema de registro: o portal é a
fonte da verdade da operação, e cobrança precisa cruzar com projeto, health e satisfação —
coisas que o gateway não conhece. O que se compra é o trilho, não o registro.

**Construir o trilho de pagamento e a emissão fiscal em casa.** Rejeitada: é commodity com
pântano municipal junto (NFS-e). Vale o mesmo argumento do provedor de assinatura — comprar
atrás de adapter, com o fornecedor trocável.

**Adotar um ERP completo (Bling, Conta Azul) como back-office.** Fora do escopo desta RFC.
São bons produtos de gestão, mas o front-end aqui é o portal: o que interessa é a API por
baixo, não as telas. Escolher back-office contábil é decisão financeira da empresa, não de
arquitetura do produto, e não precisa entrar no laço do portal.

**Deixar a IA conduzir a régua de cobrança.** Rejeitada frontalmente — ver Segurança.

## Impacto

**A colisão de verdade sobre receita é o maior risco desta RFC, e pede ADR próprio.** Hoje
`Project.actual_value` **é** a receita: alimenta o helper `_roi()`, os agregados por cliente
e por serviço em `/analytics/`, o `build_client_overview`, o sinal "ROI negativo" do
`health.py` — e o bloco de ROI que o `portal.build_snapshot` **já entrega à tela do
cliente**. No instante em que existir fatura, passam a existir duas verdades sobre receita.
É preciso decidir explicitamente: ou `actual_value` vira "valor contratado" e a fatura vira
"recebido", ou `actual_value` passa a ser derivado das faturas. Sem decisão, o ROI deriva em
silêncio — e é um número que o cliente já vê.

**Camada 0 — a fatura.** Modelo ligado a `Account`, opcionalmente a `Project` e `Service`,
com valor, emissão, vencimento, meio de pagamento, referência externa do pagamento e estado
com mapa de transições no molde de `ARTIFACT_TRANSITIONS`: `rascunho → emitida → paga /
vencida / renegociada / cancelada`. A conversão de oportunidade em projeto pode **semear** o
cronograma de cobrança pelo `tier` do `Service`, em paralelo ao que o kickoff faz com marcos
— mas **emitir é ação deliberada**, nunca débito automático.

**Invariante mais forte que o soft delete da casa.** A regra geral é arquivar em vez de
apagar; registro financeiro exige mais: fatura emitida não se edita nem se arquiva. Cancela-
se, ou emite-se crédito, e o registro sobrevive ao próprio cancelamento. É a mesma forma que
o portal já adotou para o pedido de apagamento, cuja linha sobrevive ao apagamento que ela
mesma ordenou.

**Dinheiro apurado na leitura — não reinventar.** O portal já resolveu o problema de preço e
premissa que mudam no tempo: a premissa vale por **faixa de vigência** e o valor é apurado
pela que estava em vigor **no dia do evento**, de modo que reajustar hoje não reprecifica
março. É exatamente a forma necessária para alíquota, valor-hora e reajuste contratual.

**Camada 1 — reconciliação, ou o agente nasce mentiroso.** O pecado capital da cobrança é
cobrar quem já pagou; destrói confiança num toque. Antes de qualquer régua vem o gateway
atrás de adapter, com webhook de baixa idempotente — o padrão da casa, já provado duas vezes
(dois adaptadores de assinatura, integrações atrás de flag com sondas de homologação, FDD
024, ADR 0018). Sem esse retorno, tudo depende de "marcar como pago" à mão e o lembrete
importuna quem quitou ontem. Para NFS-e, confirmar cobertura no município ou usar emissor
dedicado; o fornecedor é peça trocável.

**Camada 2 — tirar atrito antes de cobrar.** Boa parte do vencido é caminho chato, não
má-fé: link de pagamento de um toque, Pix, sem exigir login. Isso deflete uma parcela do
atraso antes de qualquer lembrete existir. Cobrança agressiva sobre pagamento difícil é
resolver o problema errado.

**Camada 3 — a escada é regra, não IA.** Máquina de estado sobre fatura: **pré-aviso antes
do vencimento** — o maior ganho isolado, porque pega quem apenas esqueceu, e é favor, não
cobrança —, carência, lembrete, tom firme, escalada para humano, renegociação. Dirigida por
tempo e por evento, no `ScheduledJobRun` que já existe (FDD 023, ADR 0015), no mesmo padrão
do digest diário. Pagamento cancela a escada na hora.

**Camada 4 — onde a IA entra.** Ela **rascunha** o texto no tom do degrau e **classifica** a
resposta do cliente, roteando entre três problemas que a mesma régua estraga: *esqueceu*
(lembrete resolve), *não pôde* (renegociação, e cedo), *está insatisfeito e está retendo
pagamento como sinal* — que não é problema de cobrança, é problema de relação disfarçado, e
onde insistir piora tudo.

## Segurança

**Nada que toca dinheiro é decisão de modelo.** Dar desconto, baixar, renegociar, escalar:
tudo humano. A ADR 0006 já proíbe efeito colateral autônomo e é a trave — cobrança é
justamente onde a tentação de automatizar demais aparece.

**A trava de relação, que distingue este assunto de todos os anteriores.** Até aqui o
interesse do portal e o do cliente andavam juntos; aqui eles se tensionam. Duas regras: a
escada **segmenta por relação**, não só por dias de atraso — cinco dias de atraso de um
cliente antigo não é o mesmo evento que reincidência —, e quem decide o próximo passo
precisa ver health, tempo de casa e valor do cliente **na mesma tela**, não a dois cliques.
Cobrar um cliente de cinco anos com tom de caloteiro é como se perde um cliente de cinco
anos por uma fatura de trinta dias.

**Recuar precisa ser declarado.** A regra de suspender a cobrança quando o cliente está
insatisfeito ou quando a entrega está atrasada é correta e é a que mais apodrece na prática:
vira desculpa para nunca cobrar, e o recebível estraga invisível. Então é **suspensão com
dono e prazo de validade, registrada como evento** — nunca um "pular" silencioso.

**Cerca comercial e limites de contato.** O valor da fatura é do cliente por direito; custo
e margem **nunca** saem. Teto duro de frequência e de horário. Em B2B a parte consumerista
do CDC afrouxa, mas o risco de relação é maior, não menor: um agente afobado transforma um
atraso de caixa em cliente perdido.

**Eixo e raio, como no resto do produto.** O lembrete sai por e-mail ou WhatsApp; a fatura,
o estado e a thread moram na conta a receber. Cobrança é comunicação, e comunicação sempre
tenta virar ilha.

## Plano de migração

1. **Medir.** Registrar vencimento e pagamento, e olhar dois ou três meses. Se a dor for
   pequena, parar aqui — e considerar isso um bom resultado.
2. **Decidir a colisão do ROI** com ADR, antes de a fatura existir.
3. **Camada 0**, com a fatura aditiva ao contrato `/api/v1/`.
4. **Camada 1**, gateway atrás de adapter e webhook de baixa, com sonda de homologação.
5. **Camada 2**, atrito de pagamento.
6. **Camadas 3 e 4**, escada determinística e depois a IA de tom e de leitura.
7. **Camada 5**, travas de relação plugadas nos sinais de saúde e satisfação.

O trabalho de verdade está de 1 a 3; os degraus de IA são os últimos e os mais baratos.

**O objetivo não é receber esta fatura — é receber e manter o cliente.** Existe cobrança que
recupera o dinheiro e mata a relação, e ela é mau negócio mesmo quando o boleto entra. Uma
consultoria vive de recorrência e indicação: ganhar a fatura e perder o cliente é o pior
resultado disfarçado de vitória.
