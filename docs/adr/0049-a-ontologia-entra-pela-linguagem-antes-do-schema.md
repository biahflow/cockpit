# ADR 0049 — A ontologia entra pela linguagem, antes do schema

**Status:** aceita
**Data:** 2026-08-28

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

### A allowlist nasce com o legado e só encolhe

`docs/ontology/legacy-allowlist.txt` nasceu com **59 entradas**, exatamente as ocorrências que a
guarda encontrava em `main` @ 80da2a5. Nem uma a mais: a lista é o inventário da dívida, e uma
entrada preventiva seria permissão para uma dívida que ninguém contraiu.

Três testes a mantêm honesta. O primeiro reprova o que não está nela. O segundo — copiado de
`frontend/src/test/primitivas.test.ts`, pela mesma razão que ele existe — reprova a entrada que não
casa mais com nada, forçando a remoção quando a dívida é paga; sem ele a linha sobreviveria ao
renome e isentaria em silêncio o próximo defeito no mesmo arquivo. O terceiro guarda um teto
monotônico: o número só desce, e subi-lo exige justificativa escrita na PR.

A entrada não carrega número de linha, de propósito: dívida declarada não pode ser reaberta porque
alguém inseriu um import acima dela.

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
