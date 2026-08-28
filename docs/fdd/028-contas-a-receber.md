# FDD 028 — Contas a receber

> **Status: entregue** (07/08/2026). É o recorte construível das camadas 0 e 1 da **RFC 0004**; a
> régua de cobrança e a IA de tom ficam para uma FDD posterior. O gateway é o **Stripe**, e ele
> **não foi homologado** contra conta real — o roteiro está em
> `docs/runbooks/homologacao-de-integracoes.md`, seção 5. Ver "O que a construção decidiu", no fim,
> para os oito pontos em que o construído diverge do escrito aqui.

## Jornada

A RFC 0004 descreve seis camadas, da conta a receber até o agente de cobrança relacional.
Esta FDD cobre só as duas primeiras — **modelar a fatura e reconciliar o pagamento** —
porque são o pré-requisito de tudo e porque, sozinhas, já entregam o que hoje não existe:
saber quem deve o quê e desde quando.

Antes delas há um passo zero que não é código e precisa estar registrado: **medir**. Não há
data de vencimento nem de pagamento em nenhum modelo, então a inadimplência é hoje
imensurável. Se, depois de dois ou três meses de registro, a dor for pequena — poucos
clientes, poucos dias —, a decisão certa é parar na camada 0 e resolver com um pré-aviso e
atenção humana. Esta FDD assume que a medição justificou seguir.

## Regras

- **`Invoice`.** FK `Account` (`PROTECT`, como as demais âncoras comerciais), FK opcionais
  `Project` e `Service` (`SET_NULL`), `number`, `amount`, `issued_at`, `due_date`,
  `method`, `external_reference` (o id no gateway) e `status`. Estende `TimestampedModel`
  pelo carimbo de tempo, **mas não pelo arquivamento** — ver a invariante abaixo.
- **Estado com mapa de transições**, no molde de `ARTIFACT_TRANSITIONS`:
  `rascunho → emitida`, e de `emitida` para `paga`, `vencida`, `renegociada` ou `cancelada`.
  `paga` e `cancelada` são terminais. `vencida` é derivada por trabalho agendado, não por
  digitação. A transição é validada no serializer, como a do `Artifact`.
- **Emitir é ação deliberada.** A conversão de oportunidade em projeto pode **semear** as
  faturas em rascunho a partir do `tier` do `Service`, em paralelo ao que o kickoff faz com
  marcos — mas nada sai de `rascunho` sozinho. Débito automático não existe neste recorte.
- **Invariante mais forte que o soft delete da casa.** Fatura emitida **não se edita e não
  se arquiva**: cancela-se, ou emite-se uma nota de crédito ligada à original, e o registro
  sobrevive ao próprio cancelamento. `ArchiveModelViewSet` **não** serve aqui; o `DELETE`
  responde 409 apontando o cancelamento como saída, no padrão que a FDD 025 estabeleceu
  para etapa de pipeline e fase da jornada. Rascunho, sim, pode ser descartado.
- **Reconciliação por webhook, idempotente.** O gateway entra atrás de adapter e flag, no
  padrão dos dois adaptadores de assinatura (FDD 009, ADR 0007) e com sonda de homologação
  (FDD 024). O webhook é assinado, e a baixa é idempotente por `external_reference`: reentrega
  do mesmo evento não duplica pagamento nem reabre fatura fechada. Sem provedor configurado,
  o caminho manual de marcar como paga continua sendo o único — e é declarado como tal.
- **A colisão do ROI é resolvida aqui ou declarada aqui.** `Project.actual_value` hoje é a
  receita que alimenta `_roi()`, os agregados de `/analytics/`, o `build_client_overview`, o
  sinal de ROI negativo do `health.py` e o bloco de ROI **que já vai à tela do cliente**.
  Esta FDD adota `actual_value` como **valor contratado** e a soma das faturas pagas como
  **recebido**, sem alterar nenhum consumidor existente — o ROI segue lendo o que sempre leu.
  Trocar a fonte do ROI é mudança de contrato e **exige ADR**, que esta FDD deixa pendente e
  nomeada em vez de resolver por conta própria.
- **Acesso.** `resource = "invoice"` no `RolePermission`, que nega por padrão: admin escreve
  e emite; Vendas lê; Entrega **não alcança** — dado financeiro não pertence ao recorte de
  projeto, e o `ProjectScopedMixin` não se aplica mesmo quando há `Project` ligado.
- **Nada disso cruza ao portal do cliente neste recorte.** O snapshot não ganha fatura. O
  bloco de ROI do `portal.py` continua exatamente como está.

## Aceite

Em **Financeiro**, o admin cria uma fatura para um cliente, com valor e vencimento, e a
emite. A lista mostra o que está em aberto, o que venceu e o que foi pago, com o total de
cada faixa. Com o gateway ligado, o pagamento registrado no provedor chega por webhook e a
fatura passa a `paga` sozinha, com a data do provedor — e uma reentrega do mesmo evento não
muda nada. Tentar excluir uma fatura emitida devolve 409 e a mensagem aponta o cancelamento.
Em **Indicadores**, o ROI continua exibindo os mesmos números de antes: a fatura ainda não é
fonte do ROI, e a FDD diz isso.

## Regressão crítica

Fatura emitida não é apagada por nenhum caminho: `DELETE` responde 409 e o registro
permanece após cancelamento. Webhook reentregue não duplica baixa nem reabre fatura já
fechada. Transição inválida (de `paga` para `emitida`, por exemplo) é rejeitada com 400.
Usuário de Entrega recebe 403 em qualquer rota de fatura, inclusive de leitura, mesmo em
projeto de que participa. E o valor do ROI em `/analytics/` permanece idêntico antes e
depois da existência de faturas — a colisão de verdade não pode acontecer por acidente.

## Fora deste recorte

**A régua de cobrança** (pré-aviso, carência, escalada) e **a IA de tom e de leitura da
resposta** — camadas 3 e 4 da RFC 0004. A ordem importa: cobrar antes de reconciliar produz
um agente que importuna quem já pagou.

**As travas de relação** — segmentar por relação, consultar health e satisfação, suspender
com dono e prazo. Dependem da régua existir.

**Emissão de NFS-e.** É pântano municipal e merece fornecedor próprio; entra quando houver
faturamento real para emitir sobre.

**Trocar a fonte do ROI de `actual_value` para faturas pagas.** Nomeado acima, **pede ADR**.

**A nota de crédito.** Citada nas Regras como alternativa ao cancelamento, ficou de fora por
recomendação — ver "O que a construção decidiu". Cancelar com motivo obrigatório, mais uma nova
fatura pelo valor corrigido, cobre o caso real deste recorte.

## O que a construção decidiu

Oito pontos em que construir mudou o desenho. Ficam registrados aqui, e não no commit, porque é
esta página que a próxima pessoa lê.

**O mapa de transições estava incompleto, e a lacuna era fatal.** A seção "Regras" escreve
`rascunho → emitida`, e de `emitida` para as quatro seguintes — e **não diz o que sai de
`vencida`**. Lido ao pé da letra, uma fatura que venceu nunca poderia ser paga: o estado derivado
pelo trabalho agendado viraria uma armadilha que impede exatamente o desfecho que se quer, e o
webhook recusaria a baixa mais comum do domínio. `vencida` recebe as mesmas saídas de `emitida`
menos vencer de novo. E `renegociada` ficou **terminal**: renegociar produz *outra* fatura com os
novos termos, e ligar as duas é camada 3. Vale manter o estado separado de `cancelada` — a camada 0
existe para medir inadimplência, e "não recebi como combinado, mas negociei" é resultado
materialmente diferente de "não vou receber".

**Faltava `paid_at` na lista de campos.** A RFC 0004 abre dizendo que "não existe data de
vencimento nem data de pagamento em lugar nenhum", e o Aceite desta FDD exige que o webhook feche a
fatura "**com a data do provedor**" — mas o campo não estava listado. É metade da medição que o
passo zero existe para fazer.

**`status` continua gravável, com dois degraus de guarda.** O primeiro é o mapa, e é ele que dá o
400 de `paga → emitida` que a "Regressão crítica" pede. O segundo recusa as transições que
*existem* mas não se alcançam por digitação — emitir, baixar e cancelar são atos com autor, carimbo
e, na emissão, uma chamada ao gateway; um `PATCH status=paid` não carrega nada disso. A mensagem
aponta a rota certa em vez de dizer só "inválido".

**"Fatura emitida não se edita" é erro alto, não descarte silencioso.** A ADR 0020 escolheu ignorar
em silêncio os campos congelados do case, e ali estava certo: ninguém *queria* escrever
`health_snapshot`. Aqui, quem digita um novo `amount` numa fatura emitida **quis** — e um 200 que
joga fora uma edição de dinheiro é o pior modo de falha disponível. Em rascunho, tudo continua
editável, porque em rascunho esses campos são o próprio trabalho.

**A gratuidade é do valor, não do nível.** A regra "Discovery Express não gera fatura" foi escrita
como cronograma vazio, e isso sozinho não bastava: a migração `0020` semeia os níveis **pagos** com
`list_price=0`, então uma implantação vendida a zero produziria três rascunhos de R$ 0,00. A guarda
que de fato salva é a do valor contratado. Junto: a divisão percentual precisou jogar o resíduo de
centavos na última parcela, senão 30/40/30 de R$ 10.000,01 não fecha com o contratado — e uma
diferença de um centavo é impossível de localizar seis meses depois.

**A numeração deriva do ano e tem buracos.** Formato `AAAA-NNNN`, atribuído na emissão (rascunho não
tem número — é o que faz dele rascunho), com `UniqueConstraint` **parcial** (`condition=~Q(number="")`)
porque um `unique=True` simples deixaria **um único rascunho** existir no sistema inteiro. Fatura
cancelada mantém o número, então a sequência tem lacunas. Isso é correto: numeração sem lacuna é
exigência *fiscal* da NFS-e, que esta FDD exclui. Alguém vai reportar como defeito.

**A nota de crédito ficou de fora**, e é recomendação, não esquecimento. As "Regras" a citam como
*alternativa* ao cancelamento ("cancela-se, **ou** emite-se uma nota de crédito"), e o cancelamento
já satisfaz a invariante inteira. Sem emissão fiscal — explicitamente fora do recorte — uma nota de
crédito seria um registro de valor negativo que não credita nada em lugar nenhum, e forçaria
`amount` a aceitar negativos, o que faria todo `Sum` futuro **compensar em silêncio**: o "total em
aberto" subtrairia notas de crédito dos recebíveis e ninguém notaria por um trimestre. O que
substitui: cancelar **com motivo obrigatório**, mais uma nova fatura pelo valor corrigido.

**A decisão de não arquivar virou a ADR 0021.** Ela contraria uma regra transversal da casa
(FDD 025) e por isso pede registro próprio, com as quatro camadas que a sustentam — da recusa com
409 até a `CheckConstraint` que mantém `archived_at` nulo para sempre.
