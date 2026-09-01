# ADR 0060 — Publicável é campo próprio, e publicar é o ato de revisão humana

**Status:** aceita
**Data:** 2026-09-01
**Depende de:** ADR 0003 (webhook para o portal do cliente) · ADR 0027 (o que entra no snapshot
precisa de emissor) · ADR 0049 (a ontologia entra pela linguagem) · ADR 0054 (a avaliação de
prioridade é imutável) · `docs/ontology/language-map.md` §3 e §6.9
**Implementada por:** FDD 051 · issue #106

## Contexto

A regra 1 da §3 do mapa de linguagem é curta e categórica: **"nada aparece no One antes de ser
revisado por humano"**. A tabela ao lado dela qualifica o que atravessa —
`Process · ProcessStep (o AS-IS validado)`, `Finding · PainPoint (revisados)`, `Evidence marcada
como revisada e publicável` — e a issue `biahflow/one#90` pediu exatamente esse conjunto.

**Os três qualificadores da tabela pressupõem estados que o schema não tinha.** É um defeito só,
e ele aparece três vezes:

- **`Evidence` não tem nenhum campo de revisão ou publicabilidade.** Nenhum. A frase "Evidence
  marcada como revisada e publicável" não tinha marca nenhuma para nomear.
- **`Process`/`ProcessStep` não têm nada que diga "validado".** Nenhum campo registra que aquele
  mapa foi conferido com o cliente. "Validado" é exatamente o mesmo tipo de qualificador sem
  lastro que "revisada e publicável", e passou despercebido por parecer um adjetivo descritivo em
  vez de um estado.
- **`Finding` tem `reviewed_by`/`reviewed_at`, e eles não servem.** O `clean()` só os exige para
  `epistemic_status=fact`. `hypothesis` é o **default** e é o que a extração por IA produz
  (invariante §6.8), então o estado mais comum do modelo nasce sem revisor.
- **`PainPoint.status=confirmed` e `ImprovementOpportunity.status=prioritized` também não servem**,
  por outra razão: eles existem, são obrigatórios e são preenchidos — mas respondem a uma pergunta
  diferente.

Sem uma marca, a fatia teria duas saídas, e as duas ruins: derivar visibilidade de um campo que
significa outra coisa, ou não ter filtro nenhum e mandar o levantamento inteiro ao cliente.

O caso do AS-IS não é hipotético. `ProcessStep` tem as letras **E** e **R** do P-S-D-T-E-R — "o
que pode dar errado" e "o que acontece quando dá errado" —, e o que se escreve ali é a
caracterização da casa sobre onde o time do cliente erra: *"Pedido faturado com preço
desatualizado"*, *"Nota cancelada e reemitida no dia seguinte"*. Sem marca, isso atravessa a
fronteira sem ninguém ter decidido mostrá-lo.

## Decisão

**A publicabilidade é campo próprio, independente do estado epistemológico e do estado de fluxo, e
o ato de publicar é a revisão humana que a §3 exige.**

### 1. `published_at`/`published_by` em cinco modelos

`Process`, `Evidence`, `Finding`, `PainPoint` e `ImprovementOpportunity`. Os dois campos ou
nenhum, cobrado num lugar só (`models.valida_marca_de_publicavel`, chamado pelos cinco `clean()`
— o do `Process` nasceu para isto).

**`ProcessStep` não recebe marca própria**, e a exceção é sobre granularidade, não sobre
visibilidade: a etapa anda com o processo pai. As seis letras do P-S-D-T-E-R são um formulário só
(`ProcessStep`), e "meio mapa publicado" não é um estado que alguém queira — publicar etapa a
etapa custaria trabalho manual sem nenhum ganho de controle: quem decide mostrar o mapa decide
mostrar o mapa.

`published_by` é obrigatório porque é ele que faz a marca **ser** a revisão: sem nome, "alguém
revisou" é alegação de ninguém. É a forma que este repositório já usa duas vezes — o par
`gap_waiver`/`gap_waiver_by` do `ProveExperiment` (ADR 0055) e o `status=approved`/`approved_by` do
`ValueLedgerEntry`.

### 2. As duas perguntas são distintas, e é por isso que a marca é campo novo

`epistemic_status` responde *"quão certos estamos disso"*. A marca responde *"o cliente pode ver
isso"*. Elas se cruzam nos quatro sentidos, e é o cruzamento que prova a independência:

|  | interno | publicado |
| --- | --- | --- |
| `hypothesis` | a suspeita em deliberação | **o que se leva à reunião**, rotulado como hipótese |
| `fact` | o fato que ainda não se decidiu mostrar | o achado do readout |

A célula superior direita é a que uma marca derivada de `reviewed_at` tornaria impossível — e ela é
o caso mais comum do produto. A inferior esquerda é a que uma marca derivada de `fact` tornaria
impossível de manter interna.

### 3. Publicar é ato de action, nunca `PATCH` de campo

`POST publish/` e `POST unpublish/`, e os dois campos são só de leitura nos serializers. É a razão
exata de `journey.apply_gate` (ADR 0053) e de `POST /prove-experiments/{id}/start/` (ADR 0055): o
que vale depende do **estado corrente** — qual sustentação está publicada e viva agora —, e só quem
conhece esse estado pode fazer a pergunta. Um `PATCH` gravaria a marca sem ela, e a invariante
viraria sugestão.

### 4. A cadeia, e as cinco portas

O que o cliente vê tem que ter sustentação publicada embaixo. `Finding` em `fact` exige `Evidence`
publicada viva; `PainPoint` exige `Finding` publicado vivo; `ImprovementOpportunity` exige
`PainPoint` publicado vivo; `Evidence` é a folha e não exige nada.

**Mais a âncora do `Process`, que não é degrau da escada.** `Process` é raiz do próprio ramo e não
exige nada para subir — as etapas andam com ele. Mas `findings[].process_id` e
`pain_points[].process_id` atravessam, então um achado publicado que cite um mapa fora de
`processes[]` é referência pendurada: o mesmo defeito que `finding_ids`/`pain_point_ids` filtrados
evitam do outro lado. Daí as **três** metades — **publicar `Finding` ou `PainPoint` exige o mapa
citado publicado e vivo**, **tirar o mapa do ar é 409** enquanto algo publicado o citar, e
**mover a âncora por baixo de um registro publicado é 400**. A citação conta por `process` **e**
por `step`: os dois FKs atravessam, os dois são `SET_NULL` e independentes, e olhar só um
deixaria a referência pendurada pelo outro.

Ao contrário dos degraus, a âncora não pergunta pela *última*: um achado cita **um** mapa, e não
há segunda âncora que o salve como uma segunda evidência salva o fato.

A invariante tem **cinco** portas, e quatro delas não são a que a issue nomeou: `publish/`,
`unpublish/`, o `DELETE` (arquivar some da projeção como despublicar), o `PATCH` que promove a
`fact` um achado já publicado e o `PATCH` que **move a âncora** de um registro publicado para um
mapa não publicado. Uma regra cobrada só na porta de entrada é uma regra que a segunda semana
desfaz.

A quinta é a que menos parece porta, e é exatamente por isso que ela é uma: as outras quatro
olham a **marca** — publicam, despublicam, arquivam ou mudam o que a marca exige. Mover
`process`/`step` num registro já publicado não toca em `published_at` nenhum, e ainda assim
`findings[].process_id` passa a apontar para fora de `processes[]`. A invariante vaza pela porta
que ninguém olhou, e não há como olhá-la sem nomeá-la.

Recusa-se, e nunca se despublica o de cima em silêncio: é o argumento das guardas de arquivamento
da FDD 045 e da FDD 048 — desfazer sozinho uma decisão que uma pessoa tomou é pior que o 409 que
diz qual estado impede e como sair dele.

### 5. Não há exceção: o AS-IS passa pela mesma regra

"O AS-IS **validado**" é um qualificador da §3 como "revisada e publicável" é — e nenhum dos dois
tinha campo. A diferença de redação entre *validado* e *revisado* descreve **quem** confere (o
cliente, na sessão de readout, contra a casa, na revisão interna); ela não descreve um estado que
o banco saiba afirmar, e é isso que uma marca precisa ser.

Ler a diferença de redação como dispensa de marca inverteria o argumento inteiro desta ADR:
"desenhado com o cliente" é a **intenção** do artefato, e a marca existe justamente porque a
intenção não é um fato consultável. Um mapa levantado numa entrevista e ainda não apresentado a
ninguém é indistinguível, no schema, de um mapa conferido linha a linha na reunião.

E o que está em jogo não é o nome do processo. `ProcessStep.erro` e `.retrabalho` são a
caracterização da casa sobre onde o time do cliente erra e o que acontece quando erra — o mesmo
tipo de material que a coluna *Nunca no One* protege em `Evidence` não revisada.

Os nove insumos do cálculo de custo continuam sem atravessar, publicado ou não: eles são conta
interna e nunca estiveram na §3. Isso a FDD 039 já protegia, e nada aqui afrouxou.

### 6. Sem backfill

Nenhuma linha existente nasce publicada. O schema não pode decidir retroativamente que uma
afirmação sobre a operação de um cliente pode ser mostrada a ele; marcar o que já existe por
`fact`, por `confirmed` ou por data fabricaria a revisão humana que a marca existe para registrar.

## Consequências

- **A §3 passa a ter onde se apoiar, nos dois qualificadores.** "Evidence marcada como revisada e
  publicável" e "o AS-IS validado" nomeiam um campo que existe, e a regra 1 vira invariante
  cobrada em vez de intenção escrita.
- **Publicar vira trabalho, e é isso que se está comprando.** Nada aparece no One por omissão. O
  custo é uma decisão humana por item; o que ela evita é o cliente lendo, com a autoridade de um
  painel, aquilo que a casa ainda não decidiu mostrar.
- **A cadeia é cobrada nas cinco portas, e por um módulo só.** `apps/core/publication.py` responde
  "pode subir?", "quem cai se este sair?" e "esta âncora atravessa?", e as cinco portas o
  consultam — as duas actions, os `perform_destroy` e os dois serializers. Expressar a regra em
  cada porta faria as portas divergirem no primeiro conserto; é por isso que `falta_a_ancora` é
  público e recebe a âncora **resolvida**, em vez de o serializer reexpressar "publicado e vivo"
  sobre os valores que chegaram no corpo.
- **A ordem importa no `DELETE` do `Process`.** `Process.archive()` cascateia para as etapas no
  mesmo instante (FDD 039), então a guarda vem **antes** dele — recusar depois já teria escondido
  metade do mapa.
- **Um `Finding` publicado em `hypothesis` é estado normal e desejado.** Quem consome precisa
  renderizar o rótulo; omiti-lo seria a casa afirmando como fato o que marcou como suspeita.
- **A superfície de publicação fica devendo.** Publicar hoje é chamada de API. A tela é pacote
  próprio com DAP, porque decidir *o que o cliente vê* merece board revisado e não um botão
  improvisado ao lado de "Arquivar".
- **A regressão da FDD 039 foi emendada e não perdeu asserção nenhuma.**
  `test_processo_nao_volta_ao_cliente.py` guarda um cenário em que nada está publicado, e por isso
  o nome do processo, o do passo, o `pessoas` da etapa, o achado em `hypothesis` e os nove insumos
  do custo continuam do lado de cá — palavra por palavra. O que mudou foi a **força** da guarda:
  ela passava por ausência de código e passa agora por invariante cobrada, com as quatro listas
  vazias afirmando que o bloco existe e o registro não atravessou. A camada estrutural sobre a
  fonte de `portal.py` não mudou uma linha, e `PROIBIDOS_NA_FONTE` foi contornada escrevendo a
  prosa em volta dela — nunca afrouxada.

## Alternativas consideradas

**Reusar `Finding.reviewed_at`/`reviewed_by` como marca de publicável.** Recusada. Eles só existem
para o `fact`, então o estado mais comum do modelo — `hypothesis`, o default e o que a IA produz —
seria impublicável por construção, ou publicável sem revisor nenhum. E as duas perguntas se cruzam:
um fato pode ser interno, e reusar o campo tornaria isso inexprimível. Um campo que responde a duas
perguntas responde mal à segunda, e a divergência não deixa nada vermelho.

**Reusar `PainPoint.status=confirmed` e `ImprovementOpportunity.status=prioritized`.** Recusada
pela mesma razão, com um agravante: são estados de **fluxo**. "A dor se sustenta em achado vivo" e
"a oportunidade foi priorizada" são fatos sobre o trabalho interno, e o backlog priorizado é
justamente o artefato em que uma linha ainda em deliberação convive com as que já foram
apresentadas. Amarrar visibilidade a eles faria priorizar significar publicar.

**Deixar `Process`/`ProcessStep` atravessarem sem marca, por serem o entregável desenhado com o
cliente.** Recusada, e foi a primeira redação desta ADR. O argumento era que a tabela da §3
qualifica com "(revisados)" exatamente `Finding · PainPoint` e chama o AS-IS de *validado*: o mapa
seria o próprio entregável do Discovery, que o cliente conferiu em vez de descobrir num painel, e
uma marca aqui transformaria a entrega do readout em trabalho manual item a item.

Ele não se sustenta, por duas razões independentes:

1. **"Validado" é um qualificador tão sem lastro quanto "revisada e publicável".** A §3 pressupõe
   dois estados que o schema não tinha, e esta ADR move o schema para os **dois** — tratar um como
   estado e o outro como adjetivo seria escolher qual metade do documento levar a sério. "Desenhado
   com o cliente" descreve a **intenção** do artefato, não um fato que o banco saiba afirmar: um
   mapa levantado numa entrevista e nunca apresentado é, no schema, idêntico a um conferido linha
   a linha.
2. **O que atravessaria não é neutro.** `ProcessStep.erro` e `.retrabalho` são a caracterização da
   casa sobre onde o time do cliente erra e o que acontece quando erra — *"Pedido faturado com
   preço desatualizado"*, *"Nota cancelada e reemitida no dia seguinte"*. É o mesmo tipo de
   material que a coluna *Nunca no One* protege em `Evidence` não revisada, chegando pela porta de
   um bloco que ninguém marcou.

O custo aceito é o que o argumento recusado previa: publicar o mapa é um ato a mais. Ele é **um**
por processo, não um por etapa, e é o mesmo ato que os outros quatro modelos já exigem.

**Marca só em `Finding` e `PainPoint`, como a issue propôs.** Recusada. `Evidence` sem marca
deixaria a lista de fontes de um achado publicado apontar para material bruto não revisado — e é
literalmente a linha "Evidence não revisada" da coluna *Nunca no One*. `ImprovementOpportunity` sem
marca publicaria o backlog inteiro no instante em que a primeira dor subisse.

**Uma rota de ingestão de escopo Account no One, em vez de duplicar por projeto.** Recusada nesta
fatia. Seria um segundo canal de ingestão do outro lado — a única parte do pacote que não seria
aditiva, e a que obrigaria o One a mudar antes de poder ler qualquer coisa. A duplicação por
projeto custa banda e é resolvida por deduplicação de id, que o consumidor já faz.

**Emitir `rank` junto do `score`.** Recusada, com dois motivos independentes: o rank de
`priority.ranking_da_conta` ordena **todas** as oportunidades vivas da conta, então o cliente
receberia `2, 4, 7` e deduziria corretamente que existem itens escondidos que o superam; e
recalculá-lo só entre as publicadas criaria uma segunda definição de rank — exatamente o que a
ADR 0054 recusou ao não persistir o campo.

**Marcar o legado como publicado no backfill.** Recusada. Ver a decisão 6: seria a casa fabricando
uma revisão humana que não aconteceu, no registro em que ela mais importa.
