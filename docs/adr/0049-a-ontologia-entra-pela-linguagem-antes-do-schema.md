# ADR 0049 — A ontologia entra pela linguagem, antes do schema

**Status:** aceita
**Data:** 2026-08-28
**Emendada por:** ADR 0052 (28/08/2026) — "renome físico" era um termo só para três coisas com
prazos distintos. O nome da **classe** passa para a issue #67 (passo 5); o nome da **tabela**
continua na Fase 6; rota e chave de payload continuam na `/api/v2/`. Onde esta ADR diz "o renome
físico é a Fase 6" — em Contexto, em Consequências e em Alternativas consideradas — leia-se o nome
da tabela.

## Contexto

A Biahflow fala em quatro superfícies — Pulse, One, Notion e material de mercado — e até agora cada
uma nomeava as coisas por conta própria. O resultado está catalogado na Ontology v1 e no Language
Map v1.1 (`docs/ontology/language-map.md`): sete conflitos em que a **mesma palavra** significava
coisas diferentes conforme quem lia. `Opportunity` era a venda no pipeline e a melhoria operacional
no mapa do FDE. `Outcome` era o resultado medido de um KPI e a saída de um decision gate.
`Evidencia` era o registro bruto de uma observação e a conclusão tirada dele. `Client` era a
organização desde o primeiro contato, embora "cliente" só se aplique a quem já assinou.

Nada disso é erro de digitação: cada um mudava o significado de dado já persistido, e por isso a
página do Notion resolveu os sete por decisão explícita (D1–D7) em vez de deixar em aberto.

O Pulse tem seis fatias de trabalho pela frente para absorver a ontologia (§7 do language map):
Qualification, Engagement, split Evidence/Finding, o bloco de priorização, KPI/Measurement/Value e,
por último, os renomes físicos. Cada fatia é uma issue, cada issue mexe em schema, e todas
introduzem identificadores novos. A pergunta que esta ADR responde é **em que ordem**: o vocabulário
se estabiliza antes ou depois de o primeiro modelo novo nascer?

Se for depois, cada fatia batiza pelo vocabulário que estiver na cabeça de quem a escreve, e o
repositório ganha uma sexta geração de nomes divergentes — só que agora em tabelas que já têm
dado. Renomear coluna com dado é migração; renomear coluna que ainda não existe é uma tecla.

## Decisão

**A Fase 0 estabiliza a linguagem sem tocar em banco.** Ela publica o Language Map no repositório,
declara os aliases vivos com a fase em que morrem (`docs/ontology/aliases.md`) e instala uma guarda
automatizada (`backend/tests/test_vocabulario.py`) que reprova identificador novo fora do
vocabulário canônico. Zero migração, zero campo, zero rota.

As fases 1–3 (issues #64, #65, #66) nascem já obedecendo, e a guarda é o que garante isso sem
depender de o revisor lembrar da regra na terça-feira à tarde.

### A guarda casa declaração, não referência

Esta é a parte que decide se a guarda sobrevive. A leitura literal da invariante §6.1 — "nenhum
identificador novo contém `opportunity` sem qualificador" — sugere proibir a palavra na linha. Isso
reprovaria cerca de 460 ocorrências: `self.opportunity`, `opportunity_id`, `from .models import
Opportunity`. Todas são *uso* do modelo que existe hoje, e ele existe hoje porque o renome físico é
a Fase 6, por decisão desta mesma ADR.

Uma guarda que reprova o que o repositório precisa fazer para funcionar é desligada na primeira
semana, e uma guarda desligada não protege nada. O que a invariante proíbe é **batizar**, e batizar
tem forma sintática: `class X`, `campo = models.…`, `router.register(…)`, `path(…)`, `type X`,
`interface X`, `const X`, `function X`. São essas as linhas medidas.

`GateOutcome`/`gate_outcome` é a única regra que casa referência, porque ali o identificador inteiro
está errado em qualquer posição — não existe uso legítimo do nome antigo.

### A heurística de português foi estreitada duas vezes, e as duas estão registradas

`class \w*Client\w*` reprovava `GitHubIssuesClient` e `GithubDeliveryReadClient`, que são clientes
de protocolo e não organizações. A regra passou a casar `client` **no início** do nome do tipo: a
organização se chama `Client…`, o cliente HTTP se chama `…Client`. Uma isenção por nome de sistema
("github") envelheceria no primeiro integrador novo; a forma do nome, não.

Os marcadores de português valem em qualquer posição (`Evidencia`, `Processo`, `Cobranca`, `ç`,
`ã`, `õ`), mas os **sufixos** só valem no fim do nome: `Management` contém `agem` no meio e é
inglês legítimo; `Contagem` termina em `agem` e não é. A regra também só roda em `models.py`,
`serializers.py` e `views.py`, que é onde o backend batiza entidade.

O terceiro estreitamento veio de medir a guarda contra a Fase 3 antes de ela existir, e é o mais
instrutivo: a regra ignorava caixa e reprovava `ProcessObservation`, `ProcessObservationSerializer`
e `ProcessObservationViewSet` — **o nome canônico da tabela mestra §2**. A emenda de `Process` com
`Observation` produz a sequência `Processo`, e sem sensibilidade a caixa o marcador a casava.

Este é o pior modo de falha que esta guarda tem, e por dois motivos. A guarda reprova o nome
**certo**, o que sozinho já a desqualifica. E a saída fácil para quem esbarra nisso às onze da
noite é declarar `ProcessObservation` na allowlist — registrando como dívida exatamente o nome que
pagou a dívida, e fazendo a lista deixar de significar o que diz. A regra passou a ser sensível a
caixa: os marcadores são substantivos próprios em CamelCase e os sufixos são minúsculos, então
`ProcessO`bservation deixa de casar sem que nenhum achado real se perca. Os três nomes ficaram
fixados como caso permanente em `LINHAS_LEGITIMAS`, porque sem eles o `re.I` volta no primeiro
refactor.

### A allowlist nasce com o legado e só encolhe

`docs/ontology/legacy-allowlist.txt` nasceu com **59 entradas**, exatamente as ocorrências que a
guarda encontrava em `main` @ 80da2a5. Nem uma a mais: a lista é o inventário da dívida, e uma
entrada preventiva seria permissão para uma dívida que ninguém contraiu.

Três testes a mantêm honesta. O primeiro reprova o que não está nela. O segundo — copiado de
`frontend/src/test/primitivas.test.ts`, pela mesma razão que ele existe — reprova a entrada maior
que a dívida que ela isenta, forçando a baixa quando a dívida é paga; sem ele a linha sobreviveria
ao renome e isentaria em silêncio o próximo defeito no mesmo arquivo. O terceiro guarda um teto
monotônico: o número de dívidas distintas só desce, e subi-lo exige justificativa escrita na PR.

### A entrada é chave **e** contagem, e a segunda metade foi medida por sabotagem

A entrada não carrega número de linha, de propósito: dívida declarada não pode ser reaberta porque
alguém inseriu um import acima dela. A primeira versão desta guarda parou aí, e ficou cega
exatamente onde mais importa. A chave `backend/apps/core/models.py::client-como-organizacao::client`
cobre as onze ocorrências de hoje — e cobria também a décima segunda. Acrescentando ao fim de
`models.py`:

```python
class OpportunityScore(models.Model):
    client = models.ForeignKey(Client, on_delete=models.CASCADE)
    gate_outcome = models.CharField(max_length=8)
```

a guarda reprovava **só** `OpportunityScore`. O campo `client` novo (§6.2) e o `gate_outcome` novo
(§6.3, D7 — o termo sem nenhum uso legítimo) passavam em silêncio, num arquivo que as Fases 2 e 6
vão editar pesado e onde todo modelo novo nasce.

A entrada passou a declarar a contagem — `…::client::11` — e a comparação vale nos dois sentidos:
mais ocorrências que o declarado reprova como dívida nova entrando por carona; menos reprova
pedindo a baixa do número, que é a catraca funcionando quando uma fase paga parte da dívida. O
`TETO_DA_ALLOWLIST` continua contando **dívidas distintas** (linhas do arquivo), que não é a mesma
grandeza — uma linha pode valer onze ocorrências.

A verificação por sabotagem é a mesma prática da ADR 0027: uma guarda que ninguém tentou burlar é
uma guarda cujo alcance ninguém conhece.

### Precedência: Notion → espelho → repositório

A página do Notion vence no **significado**; o espelho em `docs/ontology/language-map.md` vence no
**rótulo dentro do repositório**; `CLAUDE.md` e `AGENTS.md` apontam para o espelho e não podem
enfraquecê-lo. É a mesma assimetria da ADR 0045 com a camada global vendorizada, e pela mesma
razão: o espelho é cópia fiel e não se edita aqui — divergência se registra antes de qualquer
edição.

## Consequências

- **As fases 1–3 nascem obedecendo.** `Qualification.account` aponta para o modelo que ainda se
  chama `Client`, e a guarda deixa passar porque casa `client` e nunca `account`. Isso é testado
  como linha sintética em `test_vocabulario.py`: a guarda tem teste, como qualquer outro código.
- **`/api/v1/` não quebra nesta fase nem nas seguintes.** A remoção dos aliases de rota é a
  `/api/v2/`, que só nasce depois de a Fase 6 concluir os renomes físicos. Não há data de
  calendário — há ordem de fases, porque data que ninguém pode cumprir vira `# TODO(2026)`.
- **O prefixo `legacy_` fica reservado.** `legacy_opportunity` e `legacy_evidencia` são legítimos em
  código novo: declaram no próprio nome que apontam para o registro antigo. O prefixo não é isenção
  geral, e `legacy_client` para a organização corrente continua sendo defeito — só que um que o
  revisor humano precisa pegar.
- **Um bloco da allowlist não tem para onde ir ainda.** `Pendencia`, `Decisao`, `Risco`,
  `Satisfacao` e a família `Cobranca*` estão em português e a Ontology v1 não os cobre. Ficam
  declarados mesmo assim, porque sem a linha a ausência de decisão viraria ausência de dívida.
- **A heurística de idioma é a mais frágil das cinco, e o modo de falha dela é reprovar o
  canônico.** As outras quatro nomeiam termos concretos e erram para o lado de deixar passar; esta
  reconhece um padrão de palavra e erra para o lado de barrar o nome certo, que é o erro caro.
  Daí as três contenções acumuladas: escopo restrito a `models.py`/`serializers.py`/`views.py`,
  sufixo distinto de substring, e sensibilidade a caixa. Uma quarta contenção, se for preciso, é
  preferível a uma entrada de nome canônico na allowlist.
- **A contagem cria churn de propósito.** Uma referência nova a `gate_outcome` em `journey.py`
  reprova, e o conserto é editar um número. É o comportamento certo: o D7 bane o termo sem
  exceção, e o custo de uma linha editada é o preço de a guarda não ter ponto cego no arquivo mais
  movimentado do repositório.
- **A guarda mora no backend e varre os dois lados.** Uma guarda só, em `backend/tests/`, rodando no
  `uv run pytest` — fora de `--cov=apps.core` e fora do `exclude` do mypy, então não mexe em
  cobertura nem em type-check. Duas metades, uma em pytest e outra em vitest, divergiriam.
- **Ela é grep de linha, não análise sintática.** Um `class` declarado dentro de string, um campo
  criado por metaprogramação ou um nome montado em tempo de execução passam. É o preço de uma
  guarda que roda em 0,5 s e que qualquer pessoa consegue ler e ajustar; AST daria precisão e
  cobraria manutenção de duas gramáticas.

## Alternativas consideradas

- **Renomear tudo agora, numa PR só.** Resolve o vocabulário e o schema de uma vez, e é a mudança
  mais difícil de revisar que este repositório poderia receber: renome físico de `Client`,
  `Opportunity`, `Processo`, `ProcessoEtapa`, `Evidencia` e `GateOutcome` toca modelo, serializer,
  viewset, rota, `openapi.yaml`, corpus e frontend, com migração de dado no meio. O erro que passar
  na revisão só aparece em produção.
- **Guarda só de revisão humana, sem teste.** É o que existia — e é como sete conflitos de nome
  chegaram até aqui sem ninguém decidir por eles. A revisão pega o que ela lembra de procurar.
- **Proibir a palavra, não a declaração.** Simples de escrever e impossível de conviver: 460
  reprovações no primeiro `pytest`, e a primeira reação de quem esbarra nelas é acrescentar a
  allowlist inteira — o que devolve a lista ao estado de permissão permanente que os testes 2 e 3
  existem para impedir.
- **Duas guardas, uma por stack.** Cada uma na linguagem que ela varre, com a regra escrita duas
  vezes. Regra duplicada diverge, e a divergência entre elas não deixaria nada vermelho — que é
  exatamente o modo de falha que a ADR 0026 descreve para as primitivas de UI.

## Emenda (issue #67, fatia 2 — 28/08/2026) — `Client` virou `Account`

O exemplo desta ADR usa `client = models.ForeignKey(Client, …)` para descrever a dívida que a
guarda tolera. Essa dívida foi paga: a fatia 2 da #67 renomeou a classe para `Account`, os dez
campos que apontavam para ela para `account` e o `status` da conta para `lifecycle_status`
(ADR 0052). O bloco `client-como-organizacao` da allowlist caiu de nove linhas para três —
`Project.client` (a projeção da ADR 0050, que a Fase 6 remove), `client_consent` e a rota — e o
`TETO_DA_ALLOWLIST` desceu de 43 para 37.

O que a guarda continua deixando passar não muda de forma: um campo chamado `account` é o nome
canônico, e agora ele aponta para a classe de nome certo. A regra segue casando `client`, nunca
`account`, e o contexto HTTP/SDK (`GitHubIssuesClient`, `api_client`) segue isento.

## Emenda (issue #67, fatia 4 — 28/08/2026) — `Processo`/`ProcessoEtapa` viraram `Process`/`ProcessStep`, e a #67 fechou

A alternativa "renomear tudo agora, numa PR só" citava seis nomes; a ADR 0052 os separou em quatro
fatias, e esta é a última. `Processo` virou `Process`, `ProcessoEtapa` virou `ProcessStep`, e os
três campos que apontavam para os dois (`ProcessStep.processo`, `Evidencia.processo`,
`Evidencia.etapa`) viraram `process` e `step`. O bloco `modelo-em-portugues` da allowlist caiu de
dezenove linhas para treze, o `legado-congelado` de três para uma, e o `TETO_DA_ALLOWLIST` desceu
de 37 para 29.

A regra `legado-congelado` **mantém** `Processo` e `ProcessoEtapa` no regex, como já manteve
`GateOutcome`: ela é lista fechada contra batismo novo, e nome pago segue banido. O caso sintético
de `ProcessObservation` continua fixado nos dois sentidos — a sequência `Processo` que a emenda de
`Process` + `Observation` produz é justamente o nome canônico da tabela mestra §2, e é o pior modo
de falha que esta guarda tem.

Dos seis nomes originais sobra **um**, e ele nunca foi fatia da #67: `Evidencia`, que a Fase 3
dividiu e a Fase 6 remove junto com o dual-write. O que mais fica para a Fase 6 não é nome de
classe — são as quatro **tabelas** (`core_client`, `core_opportunity`, `core_processo`,
`core_processoetapa`), fixadas em `Meta.db_table` justamente para que nenhuma pk se movesse aqui.
