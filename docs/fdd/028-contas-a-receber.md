# FDD 028 — Contas a receber

> **Status: proposta.** Nada aqui está implementado. É o recorte construível das camadas 0 e
> 1 da **RFC 0004**; a régua de cobrança e a IA de tom ficam para uma FDD posterior.

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

- **`Invoice`.** FK `Client` (`PROTECT`, como as demais âncoras comerciais), FK opcionais
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
