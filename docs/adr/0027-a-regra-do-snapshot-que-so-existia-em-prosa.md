# ADR 0027 — A regra do snapshot que só existia em prosa

**Status:** aceita
**Data:** 12/08/2026
**Fase:** transversal — integração com o portal do cliente
**Completa:** ADR 0003 (e as quatro emendas dela)

## Contexto

A ADR 0003 tem uma regra escrita em negrito e repetida em três emendas:

> **O que entra no snapshot precisa de emissor, sob pena de o portal exibir um estado que já
> mudou.**

O que **verificava** essa regra eram seis asserções escritas à mão em `test_portal.py`, contra
dezesseis chaves de topo do `build_snapshot`. Não é uma proporção ruim — é a forma errada. Uma
guarda que enumera o que confere só pega o que alguém lembrou de enumerar, e o custo disso já foi
pago aqui:

**`digital_employees` entrou no snapshot sem emissor nenhum e ficou assim por meses.** Nem para
criação, nem para KPI, nem para arquivamento. O roster é o produto central, e chegava à tela do
cliente **de carona** no próximo salvamento de outra coisa — quando chegava. Não foi o CI que achou:
foi alguém percorrendo o código a partir do outro repositório, e a correção (emenda de 07/08/2026)
acrescentou o receiver e mais uma asserção à mão. **A sétima.**

É exatamente o defeito que as ADRs 0033 e 0035 do portal do cliente diagnosticaram do lado de lá —
guardas que eram, elas próprias, listas digitadas —, e a fatia das decisões (FDD 032) acrescenta a
décima-sétima chave. Escrever a oitava asserção à mão seria repetir o padrão sabendo que ele falha.

## Decisão

**Uma guarda derivada dos dois lados.** As chaves saem do `build_snapshot` de verdade, chamado com
um projeto de fixture; os emissores saem do **registro do Django** (`post_save._live_receivers`),
não de um grep no arquivo. A diferença importa: grep casaria a palavra num comentário, e um receiver
desconectado continuaria "passando".

**Um mapa escrito à mão, e ele é sobre domínio.** `_MODELO_DA_CHAVE` diz que `documents` vem de
`Document`. É a única informação que nenhuma introspecção tem como descobrir — a ligação entre o
nome de uma chave de projeção e a tabela que a alimenta é semântica, não estrutural.

**Uma allowlist com motivo escrito, e que envelhece.** Nove chaves não têm emissor próprio porque
são **derivadas** (`roi` e `resultados` vêm dos marcos; `journey` vem de `ProjectPhase`; `ai_score`
são colunas do próprio projeto). Cada uma entra em `_DERIVADA_DE` com a razão ao lado — é a forma do
`NOT_AN_ALERT` do outro repositório, e entrada sem motivo é a lista digitada voltando pela porta dos
fundos. Um terceiro caso reprova a allowlist que guarda chave que não existe mais.

**E o portão é a chave nova, não o receiver.** Uma chave que ninguém declarou reprova pedindo uma de
duas coisas: diga de qual modelo ela vem, ou diga de qual emissor ela é derivada. Não há terceira
resposta, e é isso que impede o próximo `digital_employees`.

## Consequências

- **Medida por sabotagem.** Com o `@receiver` da decisão comentado, a guarda reprova nomeando
  `decisions`. Contra o estado de 06/08/2026 ela reprovaria com `digital_employees` — o defeito que
  a emenda de 07/08 corrigiu à mão, sem deixar guarda atrás.
- **As seis asserções antigas ficam.** Elas afirmam sobre o **conteúdo** de cada emissão (o
  `object_type` certo, o `project_id` certo, os três caminhos do arquivamento); a guarda nova afirma
  sobre a **existência**. São perguntas diferentes, e a segunda não substitui a primeira.
- **`_live_receivers` devolve dois grupos no Django 5** — síncronos e assíncronos. Medido, não
  suposto: a primeira versão desta guarda tratou o retorno como uma lista só e nasceu **verde para
  tudo**, que é o pior modo de falha possível para uma guarda. Somamos os dois.
- **Fica aberto:** a guarda cobre `build_snapshot`, que é a projeção. Ela **não** cobre o corpo do
  webhook nem o `event`/`object_type` que o portal lê — aquilo é contrato de outro formato, e o
  consumidor dele mora no outro repositório.
