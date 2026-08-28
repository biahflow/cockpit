# ADR 0052 — O renome de classe vem antes da Fase 6; a tabela e a rota ficam

**Status:** aceita
**Data:** 2026-08-28
**Fase:** passo 5 do épico de ontologia (issue #67)
**Emenda:** ADR 0049 · `docs/ontology/aliases.md`

## Contexto

A issue #67 é o passo 5 da ordem de execução do épico #62, entre a Fase 3 (split Evidence/Finding,
concluída) e a Fase 4. Ela diz, no próprio corpo: *"esta issue prepara e **executa** o renome de
domínio/API, não a limpeza final."*

Três documentos deste repositório dizem o contrário, e não por descuido — todos os três foram
escritos na mesma semana, pela mesma decisão:

- `docs/ontology/aliases.md`, na tabela de aliases vivos: `modelo Client → Account`, onde vive
  `backend/apps/core/models.py`, **morre em** "renome físico na Fase 6". Idem para `Opportunity`,
  `Processo`, `ProcessoEtapa` e `GateOutcome`.
- A docstring de `backend/tests/test_vocabulario.py`: *"o modelo existe hoje porque o renome físico
  é a Fase 6"*.
- A ADR 0049, em Contexto e em Alternativas consideradas.

Não é ambiguidade de leitura: é a mesma frase — "renome físico" — significando duas coisas
diferentes conforme quem a escreveu. Quem escreveu #67 chamou de renome físico a **troca do nome
da tabela**. Quem escreveu a ADR 0049 chamou de renome físico **tudo que não é o campo canônico
apontando para o modelo legado**, o nome da classe Python incluído.

A divergência precisa de decisão porque as duas leituras produzem trabalho diferente, e a diferença
entre elas não é de estilo: é a Fase 4 inteira nascendo pendurada numa classe chamada `Client`, ou
não.

## Decisão

**"Renome físico" deixa de ser um termo. No lugar dele, três coisas com prazos distintos.**

| O que | Onde vive | Quando |
| --- | --- | --- |
| Nome da **classe** e de tudo que a nomeia — serializer, viewset, `resource`, `related_name`, tipo TS, nome de campo FK | `models.py`, `serializers.py`, `views.py`, `permissions.py`, `types.ts` | **agora**, issue #67, uma fatia por PR |
| Nome da **tabela** | `Meta.db_table` | Fase 6 (#70) |
| **Rota** e **chave de payload** | `urls.py`, `fields` dos serializers | `/api/v2/` |

O que autoriza separá-las é que só uma das três carrega o risco que `aliases.md` §2b descreve.
Aquela seção existe porque **seis pks saíram deste repositório**: o One deriva
`organization.slug = biahflow-client-{id}` e mais cinco chaves de identidade, e as persiste. O modo
de falha é silêncio — organização órfã, entregável cujo aceite desgruda. Esse risco é da **linha e
da pk**, e a linha só se move se a tabela se mover.

Com `Meta.db_table` fixado no nome legado, o `RenameModel` não move tabela nenhuma. Isso não é
inferência: `RenameModel.database_forwards` delega a `alter_db_table`, que abre com
`if old_db_table == new_db_table: return` (Django 5.2.17, o instalado). A operação renomeia o
**estado da migração** e nada mais — a tabela `core_client` continua se chamando `core_client`, com
as mesmas linhas e as mesmas pks, depois de a classe passar a se chamar `Account`.

Cada fatia, então, tem a mesma forma de migração:

```python
migrations.AlterModelTable(name="client", table="core_client"),   # fixa o que já é verdade
migrations.RenameModel(old_name="Client", new_name="Account"),    # no-op no banco
```

A primeira operação é no-op no banco por construção (o nome já é esse) e existe para tornar o
`db_table` **explícito no estado**, de modo que a segunda seja no-op também. Sem ela, o
autodetector geraria o `RenameModel` sozinho, o banco renomearia a tabela, e o `AlterModelTable`
seguinte a renomearia de volta — duas `ALTER TABLE` para chegar onde já se estava, num caminho em
que uma falha no meio deixa a tabela com o nome errado.

O renome de **campo** (`gate_outcome` → `gate_decision`, `client` → `account`) é `RenameField`, e
esse move coluna. Fica no escopo de agora: coluna renomeada preserva linha e pk, que é a
invariante que importa. O que não fica é a chave de payload — o serializer mantém o nome antigo
como alias de leitura.

## Consequências

- **A `/api/v1/` não quebra, e é a mesma regra de antes.** Rota e chave de payload continuam
  respondendo com o nome antigo, agora como alias declarado com data de morte na `/api/v2/`. O
  `basename` e o `queryset` do router são independentes do nome da classe, então `/clients/`
  sobrevive a `class Account` sem nenhum trabalho. A chave de payload custa uma linha por
  serializer, e é o preço de não quebrar consumidor.
- **A allowlist passa a encolher por fatia, que é o único jeito de ela encolher.** Enquanto o
  renome esperasse a Fase 6, `docs/ontology/legacy-allowlist.txt` ficaria parada por mais duas
  fases e o `TETO_DA_ALLOWLIST` seria um número que ninguém baixa. Cada PR desta issue remove o
  bloco que pagou e baixa o teto no mesmo commit.
- **As fases 4 e 5 nascem penduradas no nome certo.** É a consequência que decide a ADR: a Fase 4
  cria `ImprovementOpportunity`, `PriorityAssessment` e `SolutionHypothesis`, e a Fase 5 cria `KPI`,
  `Measurement` e `ValueLedgerEntry`. Todos ganham FK para conta e para processo. Se o renome
  esperasse, seriam mais uma dúzia de `models.ForeignKey(Client, …)` escritas **depois** da decisão
  que baniu o nome — que é exatamente o defeito que a ADR 0049 existe para impedir, só que
  cometido por ela.
- **Uma fatia por PR, quatro PRs.** `GateDecision`, `Account`, `CommercialOpportunity`,
  `Process`/`ProcessStep`. A ADR 0049 já rejeitou a PR única com o argumento certo — "a mudança
  mais difícil de revisar que este repositório poderia receber" — e ele continua valendo; o que
  esta ADR muda é o calendário, não o tamanho do lote.
- **`aliases.md` é emendada, não reescrita.** A coluna "Morre em" passa a distinguir classe,
  tabela e rota. A §2b não muda uma linha: ela fala de pk, e pk é justamente o que esta decisão
  não toca.
- **Sobra uma dívida com nome novo: classe em inglês, coluna em português.** Depois de #67, a
  tabela `core_processo` guarda linhas de uma classe chamada `Process`, e os nove insumos de custo
  continuam se chamando `volume_mes` e `custo_hora`. É feio no `dbshell` e não é acidente — é a
  Fase 6 tendo o que fazer, declarado aqui para não ser descoberto como surpresa.
- **A UI não muda de idioma.** O renome é de modelo, campo, rota e tipo. Menu, botões, mensagens e
  rótulos de tela continuam em pt-BR, pela regra do `language-map` §1: não se traduz o termo,
  traduz-se o texto em volta dele. O menu segue dizendo **Clientes**, que é o rótulo que a tabela
  mestra §2 prescreve para `Account`.

## Alternativas consideradas

- **Manter tudo na Fase 6, como os três documentos dizem.** É a leitura conservadora, e ela não
  compra nada: o risco que a espera evitaria é o da tabela e da pk, e essa parte continua na Fase 6
  de qualquer jeito. O que a espera custa é concreto — duas fases inteiras de modelos novos
  batizados contra a decisão, e uma allowlist que não desce.
- **Renomear a tabela junto, com `RenameModel` de verdade.** É a Fase 6 antecipada por inteiro.
  Mexe nas seis pks que o One persiste, e o modo de falha é silencioso dos dois lados. Não há
  motivo para pagar esse risco antes de a reconciliação automática que a #70 exige existir.
- **Só alias canônico, sem tocar na classe** — `Account = Client` no fim de `models.py`, ou o
  padrão de campo canônico da Fase 1. Resolve o vocabulário para quem lê e não para quem escreve:
  o `class Client` continua lá, o `grep` continua achando, e o autor da Fase 4 continua tendo o
  nome errado à mão na hora de declarar a FK. Alias que não remove o nome antigo é sinônimo, e a
  `aliases.md` já diz o que é sinônimo permanente.
- **Renomear os campos em português junto** (`volume_mes`, `custo_hora`, o P-S-D-T-E-R). Dobraria
  o diff das fatias 2 e 4 com uma decisão que a Ontology v1 não tomou: `language-map` §2 nomeia
  `Process` e `ProcessStep` e não diz nada sobre os campos deles. Termo sem nome canônico entra
  primeiro no mapa (§8), depois aqui.
