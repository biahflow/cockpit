#!/usr/bin/env bash
# Cria as issues de alinhamento ontológico no repo biahflow/pulse.
# Requer gh autenticado. Idempotência: não há — rode uma vez.
#   bash scripts/create-ontology-issues.sh
set -euo pipefail
REPO="${REPO:-biahflow/pulse}"

mk() { # mk <title> <label> <body-file>
  gh issue create --repo "$REPO" --title "$1" --label "$2" --body-file "$3"
}

# Garante que os labels existem (ignora erro se já existirem).
for l in ontology:P0 ontology:P1 ontology:P2 ontology:P3 ontology:epic; do
  gh label create "$l" --repo "$REPO" --color BFD4F2 --description "Alinhamento Ontology v1" 2>/dev/null || true
done

TMP=$(mktemp -d)

cat > "$TMP/1.md" <<'BODY'
## Contexto

O Pulse tem boa parte da Ontology v1, mas ainda não implementa a cadeia operacional completa. Quatro desalinhamentos estruturais:

1. **Qualification está modelada como venda e projeto.** A conversão do Lead cria uma `Opportunity` no tier `qualification_call`, e uma oportunidade ganha desse tier pode criar um `Project`. Isso inverte a sequência normativa.
2. **Engagement não existe.** `Client` liga direto em `Project`, então não há como agrupar projetos e vendas sob o mesmo mandato de transformação.
3. **Evidence e Finding estão fundidos** em `Evidencia` (forma da fonte + afirmação interpretada + rótulo epistemológico no mesmo registro).
4. **Medição de valor vive dentro de ativo de solução.** Baseline e KPI moram em `DigitalEmployee`; Outcome e Value Ledger não existem.

Classificação atual: `ONTOLOGY_ALIGNMENT_REQUIRED`. A recomendação é **migração incremental** com compatibilidade de API e backfill — não reescrita.

## Vocabulário canônico

- Significado: **Biahflow Operating Ontology v1** (Notion)
- Rótulo por superfície: **Language Map — Pulse · One · Notion · Biahflow** (Notion) e `docs/ontology/language-map.md` neste repo
- Idioma: termos canônicos **em inglês** em modelo, banco, API e UI interna

## Decisões já tomadas (não reabrir sem nova versão do Language Map)

| # | Decisão |
| --- | --- |
| D1 | `Qualification` é entidade persistida — mas não é container comercial nem de entrega |
| D2 | `qualification.outcome` = `qualified` · `nurture` · `disqualified`; só `qualified` abre CommercialOpportunity |
| D3 | Todo `Project` pertence a **exatamente um** `Engagement` (não `0..1`) |
| D4 | `qualification_call` é `service.category=acquisition` — sai da escada vendável |
| D5 | "Opportunity Score" é `priority_assessment.score`, só de ImprovementOpportunity |
| D6 | FATO/HIPÓTESE/DESCONHECIDO vira `finding.epistemic_status` = `fact`/`hypothesis`/`unknown` |
| D7 | `GateOutcome` → `GateDecision` (`go`/`conditional_go`/`redesign`/`no_go`) |

## Ordem de execução

1. Fase 0 — vocabulário, aliases e testes de linguagem
2. Fase 1 — Qualification antes da CommercialOpportunity
3. Fase 2 — Engagement entre Account e Project
4. Fase 3 — separar Evidence de Finding
5. Renomes semânticos (Client, Opportunity, GateOutcome, Processo)
6. Fase 4 — PainPoint → ImprovementOpportunity → Priority → SolutionHypothesis
7. Fase 5 — Feasibility, PROVE, KPI/Measurement, Value Ledger
8. Fase 6 — remover dual-write e aliases

As fases 1 e 2 são a espinha dorsal: todas as demais relações dependem delas.

## Definition of done do épico

- [ ] Nenhum modelo novo usa `opportunity` sem qualificador, `client` como organização, ou nome em português
- [ ] As 15 invariantes de `docs/ontology/language-map.md` §6 e do gap doc §9 têm teste automatizado
- [ ] O Pulse pode declarar `ONTOLOGY_ALIGNED` no lugar de `ONTOLOGY_ALIGNMENT_REQUIRED`
BODY
mk "[ontology] Épico: alinhar o domínio do Pulse à Ontology v1" "ontology:epic" "$TMP/1.md"

cat > "$TMP/2.md" <<'BODY'
## Objetivo

Estabilizar o vocabulário **antes** de qualquer migração de dado. Nenhuma quebra de banco ou API nesta fase.

## Escopo

1. Publicar `docs/ontology/language-map.md` como vocabulário normativo do repositório e referenciá-lo em `CLAUDE.md`, `AGENTS.md` e `CONTRIBUTING.md`.
2. Adotar nomes canônicos em **documentação nova, contratos novos e código novo** — sem tocar no que já existe.
3. Definir aliases de compatibilidade para `Client`, `Opportunity` e as rotas atuais, com uma versão de API onde eles morrem declarada desde já.
4. Adicionar testes semânticos que impeçam usos ambíguos novos.

## Testes de linguagem a criar

Um teste que varre `backend/apps/**/models.py`, serializers, rotas e componentes novos e falha quando encontra:

- [ ] identificador contendo `opportunity` sem `commercial_` ou `improvement_`
- [ ] identificador novo contendo `client` como sinônimo de organização (permitir `client` em contexto HTTP/SDK)
- [ ] identificador contendo `outcome` referindo-se a decisão de gate
- [ ] modelo novo com nome em português
- [ ] uso de `Evidencia`, `Processo`, `ProcessoEtapa`, `GateOutcome` fora da lista de legado congelada

A lista de legado é um arquivo explícito (`docs/ontology/legacy-allowlist.txt`) que **só encolhe**. Um teste garante que ela nunca cresce.

## Critérios de aceite

- [ ] `docs/ontology/language-map.md` existe e é citado pelo `CLAUDE.md`
- [ ] Suíte de linguagem roda no CI e falha em PR que introduza termo banido
- [ ] Allowlist de legado criada com o estado atual, e teste que impede crescimento
- [ ] Zero mudança de schema nesta issue

## Referência

Language Map §5 (termos banidos) e §6 (invariantes de linguagem).
BODY
mk "[ontology][P0] Fase 0 — vocabulário canônico, aliases e testes de linguagem" "ontology:P0" "$TMP/2.md"

cat > "$TMP/3.md" <<'BODY'
## Problema

Hoje: `Lead → Client + Opportunity(qualification_call) → Project`.

Isso cria dado semanticamente errado na entrada — uma conversa de qualificação vira venda registrada e pode virar projeto. A sequência normativa é `Lead → Qualification → Account → CommercialOpportunity`.

## Alvo

```
Lead → Qualification ──qualified──> CommercialOpportunity
                    ├─nurture────> volta ao radar com data
                    └─disqualified> encerra
```

## Modelo `Qualification`

Campos mínimos: `lead` (FK), `account` (FK opcional — resolvida ou criada), `happened_at`, `assessor`, `fit`, `need`, `urgency`, `authority`, `capacity`, `evidence`, `outcome`, `rationale`, `next_step`, `nurture_until` (quando `outcome=nurture`).

`outcome` ∈ `qualified` · `nurture` · `disqualified` (D2). O score de IA (`Lead.ai_score`) é **insumo**, não decisão — ele preenche um campo de sugestão, nunca `outcome`.

Um Lead pode ter **várias** Qualifications ao longo do tempo (o `nurture` de hoje vira `qualified` daqui a seis meses).

## Mudanças

- [ ] Criar `Qualification` + serializer + rotas `/api/v1/qualifications/`
- [ ] Alterar `leads/{id}/convert/`: cria/associa `Account` e cria `Qualification`. **Não cria Opportunity automaticamente**
- [ ] `CommercialOpportunity` só nasce após `Qualification.outcome=qualified` **e** escolha explícita da primeira oferta comercial
- [ ] Bloquear criação de `Project` a partir de oferta com `category=acquisition`
- [ ] Adicionar `Service.category` ∈ `acquisition` · `commercial`; classificar `qualification_call` como `acquisition` (D4)
- [ ] Backfill: cada `Opportunity` existente com tier `qualification_call` vira `Qualification` + `Activity`, preservando auditoria e ids legados em tabela de mapeamento

## Invariantes (viram teste)

- [ ] `Qualification.outcome != qualified` não abre `CommercialOpportunity`
- [ ] Oferta com `category=acquisition` nunca gera `Project`
- [ ] Todo `CommercialOpportunity` criado a partir de um Lead tem uma `Qualification` `qualified` como origem

## Riscos

Backfill mexe em dado comercial já existente. Rodar em transação, com dump antes e relatório de reconciliação (quantas Opportunities viraram Qualification, quantas ficaram, por quê).

Depende de: Fase 0.
BODY
mk "[ontology][P0] Fase 1 — Qualification antes da CommercialOpportunity" "ontology:P0" "$TMP/3.md"

cat > "$TMP/4.md" <<'BODY'
## Problema

`Client 1:N Project` e `Opportunity 0..1:0..1 Project`. Não existe onde agrupar várias vendas e vários projetos sob o mesmo mandato de transformação — e uma venda recorrente (Transformation Partnership) não consegue originar vários projetos.

## Alvo

```
Account 1:N Engagement
Engagement 1:N CommercialOpportunity
Engagement 1:N Project
CommercialOpportunity 1:N Project   (relação de origem, opcional no Project)
Account 1:N Process                 (Process NÃO pertence ao Project)
```

**D3: todo Project pertence a exatamente um Engagement.** Venda avulsa cria um Engagement de escopo único — é mais barato que manter dois caminhos no código e no One.

## Modelo `Engagement`

`account`, `name`, `mandate`, `sponsor`, `owner`, `status` (`active`/`paused`/`closed`), `started_at`, `ended_at`, `success_definition`.

## Mudanças

- [ ] Criar `Engagement` nullable + rotas `/api/v1/engagements/`
- [ ] Relacionar `Project.engagement` e `CommercialOpportunity.engagement`
- [ ] Backfill: um Engagement inicial por Account agrupando os projetos existentes; marcar para revisão manual quando a Account tiver projetos de jornadas claramente distintas
- [ ] Trocar `Project.opportunity` OneToOne por `originating_commercial_opportunity` FK opcional
- [ ] Tornar `Project.engagement` obrigatório após o backfill (migração em dois passos: nullable → popular → NOT NULL)
- [ ] Manter `Project.client/account` como projeção temporária; depois derivar de `Engagement`

## Invariantes (viram teste)

- [ ] Todo `Project` tem `engagement_id` não nulo
- [ ] Todo `Engagement` pertence a exatamente uma `Account`
- [ ] `Process` pertence à `Account`; `Project` e `Discovery` só registram proveniência/observação

## Saída

`Account → Engagement → Projects` vira invariante real. Esta é a espinha dorsal — o resto do backlog depende dela.

Depende de: Fase 0. Recomendado depois da Fase 1.
BODY
mk "[ontology][P0] Fase 2 — Engagement entre Account e Project" "ontology:P0" "$TMP/4.md"

cat > "$TMP/5.md" <<'BODY'
## Problema

`Evidencia` guarda ao mesmo tempo a **forma da fonte**, a **afirmação interpretada** e o **rótulo epistemológico**. Com isso, uma hipótese e o dado que a sustenta são o mesmo registro, e a proveniência se perde. Além disso `Processo.source_project`/`source_meeting` só suportam uma proveniência — o mesmo processo revisitado em outro Discovery não tem onde registrar.

## Alvo

```
Project 1:N Discovery
Discovery 1:N DiscoverySession
Discovery N:M Process  (via ProcessObservation)
Account 1:N Process → 1:N ProcessStep
Evidence N:M Finding
```

## Modelos

| Modelo | Campos mínimos |
| --- | --- |
| `Discovery` | project, engagement, scope, status, started_at, completed_at, owner |
| `DiscoverySession` | discovery, meeting (opcional), happened_at, participants, source_artifact/transcript |
| `ProcessObservation` | discovery, process, observed_at, observation_type, source_session |
| `Evidence` | account, discovery (opc.), process/step (opc.), type, raw_excerpt/reference, source, captured_at, captured_by, integrity metadata |
| `Finding` | account, process/step (opc.), statement, epistemic_status, confidence (opc.), reviewed_by, reviewed_at, evidences M:N |

`finding.epistemic_status` ∈ `fact` · `hypothesis` · `unknown` (D6).

## Backfill (por registro de `Evidencia`)

- [ ] Criar `Evidence` com o tipo/forma, `source_meeting` e referência ao conteúdo legado
- [ ] Criar `Finding` com `statement=content` e `epistemic_status=rotulo`
- [ ] Ligar Finding → Evidence
- [ ] Preservar process/step e ids legados em tabela de mapeamento
- [ ] Dual-write controlado, depois descontinuar gravação no modelo legado

## Extração por IA

- [ ] Transcrição gera `Evidence` de entrevista + `Finding` com `epistemic_status=hypothesis`
- [ ] Promoção a `fact` continua sendo **ato humano**, independentemente do texto que a IA devolveu
- [ ] `Finding` marcado `fact` exige ao menos uma `Evidence` viva e `reviewed_by` preenchido

## Invariantes (viram teste)

- [ ] Finding criado por extração nasce `hypothesis`
- [ ] Finding `fact` tem Evidence viva e revisor humano
- [ ] Nenhuma conclusão interpretada é gravada como Evidence

Depende de: Fase 0. Independente das Fases 1 e 2, mas ganha com o Engagement pronto.
BODY
mk "[ontology][P1] Fase 3 — separar Evidence de Finding; criar Discovery" "ontology:P1" "$TMP/5.md"

cat > "$TMP/6.md" <<'BODY'
## Objetivo

Trocar os nomes que colidem semanticamente, com alias de compatibilidade. **Renome físico só depois de comportamento e dados estabilizados** — esta issue prepara e executa o renome de domínio/API, não a limpeza final.

| Atual | Canônico | Por quê |
| --- | --- | --- |
| `Client` | `Account` | Já é a organização raiz, inclusive como prospect. "Cliente" continua sendo rótulo de UI quando `lifecycle_status=active` |
| `Opportunity` | `CommercialOpportunity` | Libera "opportunity" para o domínio operacional (`ImprovementOpportunity`) |
| `GateOutcome` | `GateDecision` | Decisão de gate não é resultado de negócio (D7) |
| `Processo` | `Process` | Nome em português no modelo |
| `ProcessoEtapa` | `ProcessStep` | idem |
| `Evidencia` | `Evidence` + `Finding` | Ver Fase 3 |

## Mudanças

- [ ] Renomear no domínio e nos contratos novos, mantendo tabela/rota via alias durante a transição
- [ ] `Account.lifecycle_status` ∈ `prospect` · `active` · `inactive`; rótulo "cliente" na UI só em `active`
- [ ] `gate_decision` ∈ `go` · `conditional_go` · `redesign` · `no_go`
- [ ] Versionar a depreciação dos aliases explicitamente na API
- [ ] Atualizar `docs/metodologia-fde.md` e as ADRs que citam os nomes antigos

## Cuidado

`docs/metodologia-fde.md` é citado **por número de linha** dentro dos modelos. Qualquer edição nele exige revisar as citações — ou o renome quebra a rastreabilidade silenciosamente.

## Critérios de aceite

- [ ] Nenhum nome novo usa a forma antiga
- [ ] Aliases documentados com versão de remoção
- [ ] Teste de linguagem da Fase 0 passa com a allowlist reduzida

Depende de: Fase 0.
BODY
mk "[ontology][P1] Renomes semânticos: Client, Opportunity, GateOutcome, Processo" "ontology:P1" "$TMP/6.md"

cat > "$TMP/7.md" <<'BODY'
## Problema

O PRIORITIZE não tem entidades no domínio. Hoje ele existe como fase (`JourneyPhase`) e como prosa em documento — o "Opportunity Score" não tem onde morar, e `Lead.ai_score` (aquisição) e `Project.ai_opportunity` (maturidade de IA) **não** são equivalentes a ele.

## Modelos

| Modelo | Campos mínimos |
| --- | --- |
| `PainPoint` | account, process/step, title, description, impact_type, impact_estimate, findings M:N, status |
| `ImprovementOpportunity` | account, engagement (opc.), title, desired_change, impact_hypothesis, pain_points M:N, status |
| `PriorityAssessment` | improvement_opportunity, version, impact, evidence_strength, feasibility, time_to_value, economics, score, rank, rationale, assessed_by |
| `SolutionHypothesis` | improvement_opportunity, statement, intervention, assumptions, expected_effect, status |

Relações: `Finding N:M PainPoint` · `PainPoint N:M ImprovementOpportunity` · `ImprovementOpportunity 1:N PriorityAssessment` · `ImprovementOpportunity 1:N SolutionHypothesis`.

## Pontos que costumam ser errados

- **`PriorityAssessment` é versionado.** Guarda a fórmula, as dimensões e a versão usadas no score — não é uma coluna ou enum manual. Repriorizar cria uma versão nova, não sobrescreve.
- **"Opportunity Score" é o `score` daqui (D5)** — rótulo de UI, aplicável só a `ImprovementOpportunity`. Nunca a uma venda.
- **`ImprovementOpportunity` não usa `PipelineStage`.** Nomes, APIs e permissões separados de `CommercialOpportunity`.
- Uma ImprovementOpportunity pode ter **hipóteses concorrentes**.

## Critérios de aceite

- [ ] Os quatro modelos existem com rotas próprias
- [ ] O recomendador de próximo passo consome a `PriorityAssessment` aprovada, não um campo opaco
- [ ] `ImprovementOpportunity` não referencia `PipelineStage`
- [ ] `PainPoint` confirmado tem ao menos um `Finding` de sustentação
- [ ] `PriorityAssessment` preserva fórmula, dimensões e versão

Depende de: Fase 3 (Finding).
BODY
mk "[ontology][P2] Fase 4 — PainPoint → ImprovementOpportunity → Priority → SolutionHypothesis" "ontology:P2" "$TMP/7.md"

cat > "$TMP/8.md" <<'BODY'
## Problema

Baseline e KPI vivem dentro de `DigitalEmployee` — o ativo de solução é dono da verdade da medição. Outcome e Value Ledger não existem; `Case` congela snapshots e acaba virando, na prática, a fonte de verdade do resultado. Não é.

## Modelos

| Modelo | Campos mínimos |
| --- | --- |
| `FeasibilityAssessment` | solution_hypothesis, project, technical, operational, economic, sample, error_classes, evidence, gate_decision |
| `ProveExperiment` | solution_hypothesis, project, controlled_scope, start/end, success_criteria, gate_decision |
| `KPI` | prove_experiment, name, definition, formula, unit, direction, data_source, cadence, owner, target |
| `Measurement` | kpi, kind (`baseline`/`outcome`/`monitoring`), value, period_start/end, measured_at, source_evidence, confidence |
| `ValueLedgerEntry` | engagement, project (opc.), outcome_measurement, value_type, amount/quantity, period, attribution_method, status, approved_by |

## Ordem de dependência dos dados

`KPI definido → Baseline medido → intervenção → Outcome medido → Value atribuído`

Baseline e Outcome são **medições do mesmo KPI em momentos diferentes** — não modelos distintos.

## Mudanças

- [ ] Criar Feasibility/PROVE **sem remover** `JourneyPhase`/`ProjectPhase` (fase é progresso; o agregado é conteúdo da decisão)
- [ ] Extrair `KPI` e `Measurement` de `DigitalEmployee`; o DigitalEmployee passa a **referenciar** KPIs, não a possuí-los
- [ ] Migrar `kpi_baseline` → `Measurement(kind=baseline)` e `kpi_current` → `Measurement(kind=outcome)`
- [ ] **Lacuna preservada como `null`, nunca zero.** Zerar afirma que o processo não custa nada
- [ ] Criar `ValueLedgerEntry`; derivar `Case` de Outcomes/Value aprovados
- [ ] Suportar vários KPIs por PROVE

## Invariantes (viram teste)

- [ ] PROVE não começa sem KPI, critério de sucesso e Baseline definidos — ou lacuna aprovada explicitamente
- [ ] Exatamente uma medição `baseline` por KPI e janela experimental
- [ ] Baseline e Outcome comparados usam o mesmo KPI, unidade e método de cálculo
- [ ] `GateDecision` nunca é tratado como Outcome de negócio
- [ ] `ValueLedgerEntry` aponta para um Outcome e registra método de atribuição
- [ ] `Case` publicado deriva de dado aprovado; não é fonte primária de medição

Depende de: Fase 4.
BODY
mk "[ontology][P2] Fase 5 — Feasibility, PROVE, KPI/Measurement, Value Ledger" "ontology:P2" "$TMP/8.md"

cat > "$TMP/9.md" <<'BODY'
## Objetivo

Fechar a migração. Só depois de comportamento e dados estabilizados.

## Checklist

- [ ] Medir consumidores das rotas e nomes legados (log de acesso por alias, por versão de cliente)
- [ ] Remover dual-write **somente após** reconciliação automática passar limpa
- [ ] Deprecar aliases em versão explícita da API, com prazo anunciado
- [ ] Remover campos redundantes após prova de equivalência e backup validado
- [ ] Encolher `docs/ontology/legacy-allowlist.txt` até zero
- [ ] Trocar a classificação do repositório de `ONTOLOGY_ALIGNMENT_REQUIRED` para `ONTOLOGY_ALIGNED`

## Critério de parada

Nenhum consumidor no alias por duas versões consecutivas + reconciliação sem divergência + backup restaurável testado.

Depende de: todas as fases anteriores.
BODY
mk "[ontology][P3] Fase 6 — remover dual-write e aliases de compatibilidade" "ontology:P3" "$TMP/9.md"

rm -rf "$TMP"
echo "Pronto: 9 issues criadas em $REPO"
