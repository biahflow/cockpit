# FDD 047 — O snapshot que falava o vocabulário antigo

> **A projeção do portal passa a falar canônico.** Entram `account` e `engagement` no projeto,
> `canonical_stage`/`requires_gate`/`gate_decision` em cada fase da jornada, e o par
> `observed_at`/`projection_version` na raiz — o carimbo que o consumidor já sabia ler e que
> ninguém produzia. Contrato `/api/v1/` preservado: tudo aditivo, e `client` continua saindo.

## Jornada

O One (repo `one`, o portal do cliente) é **projeção de leitura** do Pulse. A §3 do
`docs/ontology/language-map.md` diz o que isso significa em uma linha: *o One nunca renomeia*. O
que o Pulse chama de Engagement, o One chama de Engagement.

Só que o Pulse não estava mandando Engagement. O snapshot foi escrito em 2025 e fala o vocabulário
daquele ano: `project.client` e mais nada sobre a organização; a jornada saindo com nome, posição
e estado, sem a classificação canônica da fase nem a decisão do gate que a encerrou. O outro lado
tinha duas saídas, e as duas eram ruins — inventar a tradução (o que a regra proíbe) ou não mostrar
o conceito.

E havia um terceiro buraco, deste lado invisível: **o consumidor implementou o leitor de um campo
que o produtor nunca escreveu.** A ADR 0076 do `one` ("O snapshot que precisava de versão e hora",
26/08/2026) pôs de pé um `sync_snapshot` que recusa snapshot com `projection_version` menor que o
persistido, resolve empate por `observed_at` e loga `projection.stale_rejected`. O campo chegava
ausente, a própria ADR declara que versão ausente não recusa nada, e a proteção inteira ficou
desligada por falta da outra metade.

O que ela protege não é hipotético: duas requisições concorrentes ao snapshot, ou um backfill
manual disparado enquanto um webhook do mesmo projeto está em voo, entregam dois estados fora de
ordem. O mais antigo chega por último, o read model do cliente volta para um estado que já não
existe, e nenhum dos dois lados acusa nada — cada um fez exatamente o que devia.

## O que esta fatia entrega

### 1. A conta e o mandato, com o nome certo

```
project.account     = {id, name}      # de `engagement.account`
project.engagement  = {id, name, status}
project.client      = {id, name}      # inalterado, alias com data
```

**`account` sai do engajamento, não de `Project.client`.** Os dois são iguais por construção —
`Project.clean()` amarra `engagement.account_id == client_id` —, e a projeção lê a fonte mesmo
assim: `Project.client` é projeção temporária que a Fase 6 remove, e quem já lê pelo lado canônico
não muda quando ela sair. Há teste que compara os dois lados, para que a divergência, se um dia
existir, apareça aqui e não na tela do cliente.

**`client` continua saindo, exatamente como saía.** Ele é alias com data, e a data é a `/api/v2/`
(`docs/ontology/aliases.md`). `engagement` está sempre presente porque `Project.engagement` é
NOT NULL desde a migração `0057`.

### 2. O vocabulário da fase

```
journey.phases[].canonical_stage   # "" é legítimo
journey.phases[].requires_gate     # bool, vem do TEMPLATE
journey.phases[].gate_decision     # "" enquanto ninguém decidiu
```

**`canonical_stage` vazio não é dado faltando.** É a fase operacional Biahflow sem equivalente FDE
— a docstring de `JourneyPhase.CanonicalStage` cita `Activation`. Nenhum default é inventado, e o
teste fixa os dois casos lado a lado justamente para que o próximo leitor não "corrija" o branco.

**`requires_gate` vem do template e não da instância**, e é ele que faz o One distinguir "exige
gate e ninguém decidiu" de "não tem gate". Sem ele os dois casos são o mesmo `gate_decision`
vazio, e a barra da jornada não teria como mostrar uma decisão pendente.

**`gate_decision` é o nome do D7.** Quando esta fatia foi escrita o modelo ainda tinha
`gate_outcome`, e a projeção lia por uma **propriedade-alias** `ProjectPhase.gate_decision`, na
forma que `docs/ontology/aliases.md` prescreve — custo assumido de uma ocorrência a mais do nome
legado em `models.py` (o corpo do alias), que era o que permitia remover todas as outras. O campo
foi renomeado depois, na issue #67 (ADR 0052, emenda abaixo): a propriedade sumiu e a projeção lê
o campo. **A chave emitida nunca mudou**, que é a razão de o alias ter existido.

**`situation` fica de fora.** Ela colapsa `waiting_party`, que é classificação interna de delivery
("estamos esperando engenharia") e não atravessa a fronteira do cliente (`language-map` §3).
Decisão tomada com a sessão do `one`; eles derivam o que precisam do par acima. Também não saem
`blocker_note`, `gate_notes` nem `checklist_waiver`.

### 3. O carimbo da projeção

```
observed_at         # ISO 8601 com timezone, ou null
projection_version  # inteiro monotônico por projeto
```

Duas colunas novas em `Project` (migração `0058_carimbo_da_projecao`), sem backfill, e **uma regra
que é o desenho inteiro: quem carimba é quem muda o estado, não quem lê.** O raciocínio completo
está na **ADR 0051**; o resumo operacional é que o carimbo mora em `portal.emit` — o ponto de
estrangulamento por onde passam os onze receivers `_emit_*` —, usa `F(...) + 1` para resolver a
concorrência no banco, e roda **antes** da guarda de flag, porque a projeção mudou de fato mesmo
com o webhook desligado.

**Duas leituras seguidas devolvem a mesma versão, e isso é o caso comum, não sintoma.** A projeção
não mudou; não há o que versionar. O `sync_snapshot` do outro lado trata empate aplicando o
snapshot, porque é idempotente por substituição. Há teste que reprova quem "consertar" isso movendo
o incremento para o `build_snapshot` — que é a forma exata como este desenho seria desfeito por
alguém tentando ajudar.

### 4. Os dois emissores que as chaves novas exigem

A regra em negrito da ADR 0003 — *o que entra no snapshot precisa de emissor* — vale para as chaves
novas, e a guarda da ADR 0027 **não** as alcança: ela compara chaves de **topo**, e estas são
aninhadas. Por isso os dois receivers estão escritos à mão e testados à mão.

| Receiver | Dispara em | Alcance |
| --- | --- | --- |
| `_emit_engagement` | `post_save` de `Engagement` | **todos** os projetos do mandato |
| `_emit_journey_phase` | `post_save` de `JourneyPhase` | projetos com aquela fase materializada e viva |

O fan-out do engajamento é deliberado, e o contraste com o `_emit_artifact` (emenda de 07/08/2026
na ADR 0003) é o argumento: lá **um** projeto é escolhido porque só um é afetado; aqui renomear ou
pausar um mandato muda o snapshot de todos eles. O do template é maior ainda — uma fase é comum a
toda a carteira — e se justifica pela raridade: é tela de admin da metodologia, não fluxo de
operação.

`gate_decision` já tinha emissor: `_emit_project_phase` cobre `ProjectPhase`.

## Aceite

1. `project.account` e `project.engagement` saem com a forma exata, e `project.client` continua
   idêntico ao que era.
2. `project.account` é o do engajamento e bate com `project.client` — a projeção não divergiu.
3. Cada fase leva as três chaves; `canonical_stage=""` quando não há equivalente FDE,
   `gate_decision=""` antes da decisão, `requires_gate` refletindo o template.
4. `gate_decision` devolve o mesmo valor do campo legado depois de um gate decidido.
5. Salvar `Project`, `Milestone` ou `Engagement` avança `projection_version` em 1 e move
   `projection_observed_at`.
6. Duas leituras seguidas do snapshot **não** mudam a versão — nenhum `GET` escreve.
7. Com a flag `portal` desligada, salvar ainda avança a versão.
8. Renomear um `Engagement` emite para todos os projetos dele; editar um `JourneyPhase` emite para
   os projetos que a têm materializada, e não para os que a têm arquivada.
9. A guarda da ADR 0027 passa com as duas chaves de topo declaradas em `_DERIVADA_DE`.
10. Regressão: o conjunto de chaves de topo do snapshot é exatamente o esperado
    (`backend/tests/regression/test_o_contrato_do_snapshot_e_fechado.py`).

## Pendência conhecida

**Nenhuma guarda deste repositório desce um nível.** A da ADR 0027 e a regressão nova fixam
chaves de **topo**; `project.*` e `journey.phases[].*` não são fixadas por nenhuma das duas, então
um campo interno que vaze para dentro de um bloco aninhado não deixa nada vermelho. O repo `one`
diagnosticou o mesmo defeito do lado dele (ADR 0033 de lá). Não foi corrigido aqui de propósito:
descer um nível toca a guarda de todo mundo — muda o formato dos dois mapas, obriga a declarar
dezenas de chaves e muda o que "chave nova" significa — e merece decisão própria, com ADR.

## Fora de escopo

- Remover `project.client` do snapshot (é a `/api/v2/`, Fase 6).
- Renomear `gate_outcome` no modelo. Era Fase 6 quando esta fatia foi escrita, e a propriedade
  `gate_decision` era alias, não renome; a ADR 0052 antecipou o renome para a issue #67, e ele
  aconteceu na fatia 1 dela (ver a emenda abaixo).
- Expor `situation`, `waiting_party`, `blocker_note`, `gate_notes` ou `checklist_waiver`.
- Criar schema de resposta para a rota do snapshot no `openapi.yaml` — ela segue sem corpo
  documentado, como antes.
- Qualquer mudança de tela.

## Referências

- ADR 0051 — A projeção ganha versão e hora, e quem carimba é quem muda o estado.
- ADR 0003 (emenda de 28/08/2026) e ADR 0027 — a regra do emissor e a guarda derivada dela.
- ADR 0076 do repo `one` — o leitor que existia antes do produtor.
- `docs/ontology/language-map.md` §2, §3 e D7; `docs/ontology/aliases.md`.

## Emenda (28/08/2026) — a propriedade-alias virou o próprio campo

A issue #67, fatia 1, renomeou `ProjectPhase.gate_outcome` para `gate_decision` (decisão D7,
autorizada pela ADR 0052, migração `0060`). Com isso a **propriedade-alias que esta fatia criou
deixou de existir**, e não por remoção: o campo passou a ter o nome dela.

**O snapshot não muda em nada.** `portal.build_snapshot` continua emitindo `gate_decision` com o
mesmo valor; a única diferença é que ele lê o campo canônico direto em vez da propriedade. É o
desfecho que o alias antecipava — ele existia justamente para o One nunca ver o nome antigo e não
precisar renomear depois (`language-map` §3), e `apps/core/tests/test_portal.py` guarda a chave
emitida, não o caminho de leitura.

O que **continua** fora de escopo é o resto da lista acima: `project.client` só sai na `/api/v2/`,
e a chave de payload `gate_outcome` sobrevive na `/api/v1/` como alias de leitura pelo mesmo prazo.
