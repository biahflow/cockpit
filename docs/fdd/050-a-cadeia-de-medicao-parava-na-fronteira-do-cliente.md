# FDD 050 — A cadeia de medição parava na fronteira do cliente

> **`KPI`, `Measurement` e `ValueLedgerEntry` passam a atravessar para o One.** Entram `kpis[]` —
> com baseline, outcome e monitoramento **aninhados dentro de cada indicador** — e `value_ledger[]`
> na raiz do snapshot, mais `digital_employees[].kpi_ids` ligando o ativo ao indicador que ele move.
> Três emissores novos. Contrato `/api/v1/` preservado: tudo aditivo, e `roi` continua saindo.

## Jornada

A Fase 5 da ontologia (ADR 0055, FDD 049) tirou a medição de dentro do ativo de solução:
`kpi_baseline` e `kpi_current` eram colunas de `DigitalEmployee` e viraram `Measurement` de um
`KPI`, com `ValueLedgerEntry` registrando o valor atribuído a um resultado medido. A §3 do
`docs/ontology/language-map.md` já dizia, desde antes, que `ProveExperiment · KPI · Baseline ·
Outcome` e `Value Ledger` são coisas que o One mostra.

Nenhuma das três atravessava. A FDD 049 adiou o One **explicitamente** — *"mexer ali é mudar a
projeção do cliente; outro gate, outro pacote"* —, e este é o pacote que paga.

O que o cliente via no lugar eram duas coisas, e as duas dizem menos do que parecem:

- **os quatro campos legados de `DigitalEmployee`** (`kpi_label`, `kpi_value`,
  `hours_saved_month`, `roi_month`). `kpi_label`/`kpi_value` são texto livre — "de 3h para 20min"
  —, sem unidade tipada, sem janela, sem quem mediu e sem como comparar duas leituras;
- **`roi`**, que é `actual_value - cost` do projeto. É o dinheiro do *contrato*, não o resultado do
  trabalho. Um cliente com um PROVE bem-sucedido e um indicador que caiu 74% via, na tela dele, a
  receita que ele mesmo pagou menos o custo que nós tivemos.

A lacuna tinha, portanto, a forma que a ADR 0003 nomeia desde 2025: o Pulse é a fonte da verdade do
estado do projeto, e o estado que mais importa — *funcionou?* — não estava na projeção.

## O que esta fatia entrega

### 1. `kpis[]`, com a medição **dentro** do indicador

```
kpis[] = {
  id, name, definition, formula, unit, direction, data_source, cadence, target,
  baseline:   {value, period_start, period_end, measured_at, confidence} | null,
  outcome:    {…mesma forma…} | null,
  monitoring: [ …mesma forma… ]
}
```

**O aninhamento é a decisão da fatia, e não arrumação.** O que torna duas leituras comparáveis é
serem do *mesmo* KPI, com a mesma unidade e o mesmo método — é a invariante §6.11 do
`language-map`, e é a razão pela qual `Measurement` deliberadamente **não** tem `unit`. Numa lista
irmã de medições, parear baseline com outcome viraria trabalho do consumidor, e um pareamento
errado não deixaria nada vermelho de nenhum dos dois lados. Aninhado, **o pareamento é invariante
por construção em vez de disciplina de quem lê**.

**Nenhum outcome é emitido sem baseline do mesmo KPI.** O critério de aceite do outro lado é "todo
Outcome renderizado tem Baseline no mesmo componente". Emitir o outcome sozinho e deixar o One
recusá-lo produziria o pior resultado possível: o cliente veria lacuna onde há dado. Quem sabe que
a baseline falta é quem a consulta — daqui —, e é aqui que a regra mora.

**Duas nulidades distintas, e as duas são necessárias.** `"baseline": null` significa *não há
baseline definida*; `"baseline": {"value": null, …}` significa *a janela existe e a medição não foi
feita*. Nenhuma das duas é `0`: zero afirma que se mediu e deu zero, e a lacuna admitida é sempre
melhor que a lacuna disfarçada de medição. É a mesma distinção que `Measurement.value` guarda sendo
nulável e que o DAP `dap-prove-e-valor-r1` desenha como `— → 1h05`.

**`monitoring` é lista, vazia e nunca nula**, ordenada da leitura mais recente para a mais antiga.
Arquivado não conta, no KPI e na medição.

**Não atravessam** `KPI.owner` (pessoa interna, §3) e `Measurement.source_evidence` (evidência
bruta não revisada, §3, regra 1). A medição também não leva `id` nem `kind`: o aninhamento **é** a
identidade e o papel dela.

A leitura de qual baseline e qual outcome contam vem de `prove.py`, que ganhou
`medicao_de_baseline`/`medicao_de_outcome` — as linhas — e passou a derivar delas o `baseline_de`/
`outcome_mais_recente_de` que já existiam, que devolvem só o número. Duas expressões de "qual é o
antes deste KPI" divergiriam na primeira correção; a `/api/v1/` continua publicando o número pelo
mesmo caminho (`test_a_medicao_do_ativo_sobrevive_na_v1.py`).

### 2. `value_ledger[]`, lido **por mandato**

```
value_ledger[] = { id, value_type, amount, quantity, period_start, period_end,
                   attribution_method, kpi_id, outcome_measured_at }
```

**A fonte é `project.engagement.value_entries`, não as entradas do projeto.** Valor é do mandato:
`ValueLedgerEntry.project` é opcional de propósito, porque um resultado que atravessa dois projetos
do mesmo programa é uma entrada só (ADR 0050). É a mesma leitura por `Engagement` que a tela
`/contas/:id/valor` faz. A consequência é que a mesma entrada sai no snapshot de **todos** os
projetos do mandato — e é por isso que o emissor faz fan-out.

**Dois filtros além do arquivamento, e nenhum é zelo excessivo:**

- **só `approved`.** Rascunho e pendente são deliberação interna (regra 1 da §3), e aqui isso pesa
  mais que no resto do snapshot: é a linha que o cliente lê como *valor gerado*.
- **`attribution_method` não-vazio.** O `clean()` já o exige, mas `clean()` não roda em shell nem
  em migração de dados, e este é exatamente o campo cuja ausência transforma a linha num número sem
  procedência. "ROI" como resultado é termo banido (§5) por este motivo.

**Não atravessam** `approved_by` (pessoa interna) nem `status` — este último contaria ao cliente
que existe uma fila de aprovação da qual ele não participa.

**Não há campo de moeda, e não se criou um.** A pergunta foi feita e a resposta fica registrada
aqui para não ser reaberta: toda entrada é BRL hoje, e uma coluna para o caso hipotético é
especulação — o `roi` que já atravessa tem a mesma ausência pela mesma razão. Quando existir a
primeira entrada em outra moeda, ela nasce no modelo, não na projeção.

`kpi_id` e `outcome_measured_at` saem de `outcome_measurement`: o vínculo com o resultado que
sustenta a entrada é afirmado daqui, e o recasamento com `kpis[]` é do outro lado.

### 3. `digital_employees[].kpi_ids`, aditivo

Cada funcionário digital passa a levar `kpi_ids` — hoje zero ou um elemento, porque
`DigitalEmployee.kpi` é FK singular. **Lista porque o contrato do outro lado é lista** e porque a
FK singular é o estado atual, não a forma final.

**Os quatro campos legados ficam exatamente onde estão.** É a mesma convivência de
`account`/`client`: o legado sai quando o One parar de ler, e não antes (`docs/ontology/aliases.md`
§2c). O sucessor deles é `kpi_ids` + `kpis[]`, que é onde moram a unidade, o método e as leituras —
o que `kpi_label`/`kpi_value` nunca souberam dizer.

### 4. Três emissores, pela regra que abre a ADR 0003

| Receiver | Dispara em | Alcance |
| --- | --- | --- |
| `_emit_kpi` | `post_save` de `KPI` | o projeto do KPI |
| `_emit_measurement` | `post_save` de `Measurement` | o projeto, pelo KPI que a ancora |
| `_emit_value_ledger_entry` | `post_save` de `ValueLedgerEntry` | **todos** os projetos do mandato |

**A medição é o evento**, e é o mais importante dos três: registrar o Outcome do mês não salva o
`Project` nem o `KPI`, então sem receiver próprio ela chegaria ao cliente de carona no próximo
salvamento de outra coisa — o defeito do funcionário digital (emenda de 07/08/2026 na ADR 0003) por
outro eixo.

O fan-out da entrada de valor é o do `_emit_engagement`, literal e pelo mesmo argumento: a entrada
aparece no snapshot de todos os projetos do mandato, e um projeto que não recebesse o aviso ficaria
sem ela até o próximo salvamento de outra coisa. É o contrário do `_emit_artifact`, que escolhe
**um** projeto porque só um é afetado.

Nenhum dos três leva guarda de `created`: nenhum nasce em laço como `ProjectPhase`/
`ProjectDeliverable`, e o que importa neles é justamente o update — aprovar uma entrada e arquivar
um KPI são `save()` que mudam o que o cliente vê sem criar linha nenhuma.

**`Measurement` não tem chave de topo, e por isso ganhou asserção escrita à mão.** A guarda da ADR
0027 compara chaves de topo e não alcança o que é aninhado; sem
`test_a_medicao_tem_emissor_mesmo_sem_chave_de_topo`, a medição nova não avisaria ninguém e nada
ficaria vermelho.

## Aceite

1. `kpis[]` traz o KPI vivo do projeto com `name`, `definition`, `formula`, `unit`, `direction`,
   `data_source`, `cadence` e `target`.
2. Baseline e outcome saem aninhados no KPI, com `period_start`, `period_end`, `measured_at` e
   `confidence`.
3. KPI com outcome vivo e **sem** baseline sai com `outcome: null`.
4. KPI sem nenhuma baseline sai `baseline: null`; baseline com `value` nulo sai como objeto com
   `value: null`. Nenhum dos dois é `0`.
5. `monitoring` é lista vazia quando não há leitura, nunca `null`.
6. KPI arquivado e medição arquivada não aparecem.
7. Nenhum item de `kpis[]` tem `owner`; nenhuma medição tem `source_evidence`, `id` ou `kind`.
8. `value_ledger[]` traz só entradas `approved`; `draft` e `pending` não saem.
9. Entrada `approved` com `attribution_method` vazio ou em branco não atravessa.
10. A entrada do mandato sai no snapshot de **todos** os projetos dele, e não no de fora.
11. Entrada arquivada não aparece; nenhuma entrada leva `approved_by` nem `status`.
12. `digital_employees[].kpi_ids` sai com o KPI referenciado (ou lista vazia), e os quatro campos
    legados continuam presentes e inalterados.
13. Salvar `KPI`, `Measurement` e `ValueLedgerEntry` emite; a entrada do ledger emite para os dois
    projetos do mandato e não para o de fora.
14. As duas guardas do snapshot passam com `kpis` e `value_ledger` declaradas
    (`apps/core/tests/test_portal.py` e
    `backend/tests/regression/test_o_contrato_do_snapshot_e_fechado.py`).

Regressão: `backend/tests/regression/test_o_snapshot_leva_a_cadeia_de_medicao.py`.

## Fora deste recorte

- **A manchete continua sendo `roi`.** A chave não muda, não é renomeada e não é removida — é
  contrato `/api/v1/`, e o One a consome. Trocar a manchete da tela do cliente do `roi` do projeto
  para o Value Ledger é decisão **do outro lado**, com o dado que esta fatia acabou de entregar;
  nada aqui precisa mudar para isso acontecer.
- **Os quatro campos legados de `DigitalEmployee`.** Continuam saindo. Eles morrem quando o One
  parar de lê-los, e o registro do prazo está em `docs/ontology/aliases.md`.
- **Campo de moeda em `ValueLedgerEntry`.** Ver acima: decisão registrada, não pendência.
- **Descer as guardas do snapshot um nível.** Nem a da ADR 0027 nem a regressão fixam chaves
  aninhadas, e agora há duas listas novas dentro delas. Continua sendo a pendência deliberada que a
  FDD 047 registra: descer um nível toca a guarda de todo mundo e merece decisão própria, com ADR.
- **A cadeia do Discovery no One** (`Process`, `Finding`, `PainPoint`, `ImprovementOpportunity`) —
  é outra fatia, em PR separado.
- **Qualquer mudança de tela.** Nenhuma superfície deste produto muda; quem consome as chaves novas
  é o One.
- **Migração.** Nenhum modelo muda: a fatia inteira é projeção e sinal.

## Referências

- ADR 0003 (emenda de 01/09/2026) — a cadeia de medição atravessa, e o que a filtra.
- ADR 0027 — a guarda derivada de "o que entra no snapshot precisa de emissor".
- ADR 0055 e FDD 049 — a medição sai do ativo de solução; o One ficou fora daquele recorte.
- ADR 0050 — o Engagement como espinha, e por que o valor pende do mandato.
- ADR 0051 e FDD 047 — o carimbo da projeção e a pendência das guardas aninhadas.
- `docs/ontology/language-map.md` §3, §6.11 e §6.12; `docs/ontology/aliases.md`.
- DAP `docs/design/dap-prove-e-valor-r1/` — as duas nulidades e a leitura por mandato, do lado da
  superfície deste produto.
