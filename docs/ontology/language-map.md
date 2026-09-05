# Biahflow Language Map v1.5 — Pulse · One · Notion · Biahflow

> Espelho do documento canônico no Notion: **Language Map — Pulse · One · Notion · Biahflow**
> <https://app.notion.com/p/3ca82225ad278115bd44c2d90247f44e>
> A precedência é assimétrica: o repositório é fonte do método; o Language Map do Notion é
> normativo para os rótulos por superfície. Em divergência de método, o repositório vence; em
> divergência de vocabulário, a página do Notion vence.

**Status:** normativo · **Depende de:** Biahflow Operating Ontology v1 · **Data:** 28/08/2026 ·
**v1.5 (05/09/2026):** `BusinessCase` cunhado — a justificativa do investimento, distinta do `Case`
(ADR 0069). Cunhado primeiro na página do Notion, como manda a §8, e espelhado aqui em seguida.

A Ontology v1 define **o que cada termo significa**. Esta página define **onde cada termo aparece e com que nome**, nas quatro superfícies em que a Biahflow fala: Pulse, One, Notion e material de mercado. Quando as duas divergirem, a Ontology v1 vence no significado e esta página vence no rótulo.

Regra de ouro: **um conceito, um nome, quatro superfícies.** Se uma superfície precisa de outra palavra, ela não precisa de outra palavra — ela precisa de outro conceito.

---

## 0. Decisões desta versão

Dez conflitos reais entre Pulse, Notion e material comercial, resolvidos aqui. Cada um mudava o significado de dado já persistido, então nenhum ficou em aberto.

| # | Conflito | Decisão | Quem muda |
| --- | --- | --- | --- |
| D1 | Ontology v1 §3 diz que Qualification "não é entidade"; o gap doc do Pulse pede um agregado `Qualification` | Qualification **é entidade persistida**: a avaliação fica registrada, com autor, data e resultado. Não é container comercial nem de entrega | Ontology v1 §3 · Pulse |
| D2 | Quatro vocabulários para o resultado da Qualification | Enum único: `qualified` · `nurture` · `disqualified`. Só `qualified` abre CommercialOpportunity | Ontology v1 · Pulse · script comercial |
| D3 | Ontology v1 §9 diz Project → Engagement `0..1`; gap doc diz obrigatório | **Obrigatório.** Todo Project pertence a exatamente um Engagement. Venda avulsa cria um Engagement de escopo único | Ontology v1 §9 · Pulse · One |
| D4 | Qualification Call listada como um dos "sete degraus vendáveis" | **Sai da escada comercial.** Vira oferta de aquisição (`service.category=acquisition`). Nunca gera CommercialOpportunity nem Project. Restam **seis degraus vendáveis** | Notion (Sistema Operacional) · Pulse |
| D5 | "Opportunity Score" existe na FDE, mas não há entidade que o carregue | O score é `priority_assessment.score`. **"Opportunity Score" é rótulo de UI/cliente**, aplicável só a ImprovementOpportunity — nunca a CommercialOpportunity | Pulse · One · Executive Readout |
| D6 | FATO / HIPÓTESE / DESCONHECIDO vive dentro de `Evidencia` | Vira `finding.epistemic_status` = `fact` · `hypothesis` · `unknown`. Finding extraído por IA nasce `hypothesis`; promoção a `fact` é ato humano | Pulse · FDE |
| D7 | `GateOutcome` colide com Outcome de negócio | Renomeado para `GateDecision`, valores `go` · `conditional_go` · `redesign` · `no_go` | Pulse · One · FDE |
| D8 | Ontology v1 dizia que Engagement nasce após uma CommercialOpportunity `Won`; um design partner não tem venda, e sem Engagement não se pode criar Project (D3) | Engagement nasce de **instrumento contratual assinado** — CommercialOpportunity `Won` **ou** Design Partner Agreement. Novo atributo obrigatório `engagement.commercial_model` = `design_partner` · `paid`. A continuidade de um design partner nasce como CommercialOpportunity **dentro** do Engagement existente | Ontology v1 §4 · §9 · Pulse · One |
| D9 | `gate_decision` declarado válido para Feasibility **e** PROVE, misturando dois vocabulários de decisão | **Cada gate tem seu vocabulário.** Feasibility → `go` · `conditional_go` · `redesign` · `no_go`. PROVE → `scale` · `iterate` · `stop`. Nunca misturar (ADR 0053) | Pulse · One · FDE · Notion |
| D10 | Valores de enum em português deixavam modelo, banco e API bilíngues mesmo quando classe e campo já tinham nome canônico em inglês | **Valor de enum é termo de domínio e segue a regra de idioma:** inglês canônico em modelo, banco e API. Valores portugueses existentes permanecem aliases de entrada da `/api/v1/`; a migração de cada família ocorre junto do respectivo renome e os aliases morrem na `/api/v2/` | Pulse · One |

---

## 1. As quatro superfícies

| Superfície | O que é | Quem lê | Papel na linguagem |
| --- | --- | --- | --- |
| **Pulse** | Portal operacional interno da Biahflow (repo `pulse`) | Biahflow | Fonte da verdade do **dado**. Nomes canônicos em modelo, banco, API e UI interna |
| **One** | Portal do cliente (repo `one`) | Sponsor e time do cliente | **Projeção de leitura** do Pulse. Mesmos nomes, subconjunto visível. Não inventa termo |
| **Notion** | Estratégia, método, playbooks, verticais | Biahflow | **Espelho do método.** A fonte é `docs/` no repositório do Pulse; o sistema Pulse manda no **dado** (ADR 0035). Nenhuma ficha do Notion se declara fonte da verdade do método. Prosa em português, termos canônicos em inglês |
| **Biahflow** | Site, decks, propostas, one-pagers, conteúdo | Mercado | Mesma palavra, sem jargão de banco. Nunca um sinônimo criado para "soar melhor" |

**Regra de idioma:** termos canônicos **em inglês nas quatro superfícies**. `snake_case` em código, banco e API; `Title Case` em UI e prosa. **Valores de enum também são termos canônicos:** persistem e atravessam APIs em inglês; a UI traduz apenas o rótulo exibido. Valores portugueses anteriores a D10 são aliases de compatibilidade da `/api/v1/`, nunca valores novos. Não se traduz o termo — traduz-se o texto em volta dele. "A Account tem três Engagements ativos" está certo; "A Conta tem três Compromissos ativos" está errado.

---

## 2. Tabela mestra de termos

| Termo canônico | Pulse (modelo · API) | One (o cliente vê) | Notion | Comercial | Nunca chamar de |
| --- | --- | --- | --- | --- | --- |
| **Lead** | `Lead` · `/leads` | — | Lead | contato de entrada | Cliente, Oportunidade |
| **Qualification** | `Qualification` · `/qualifications` | — | Qualification | Qualification Call (o encontro) | Oportunidade, Projeto, Lead status |
| **CommercialOpportunity** | `CommercialOpportunity` · `/commercial-opportunities` | — | Commercial Opportunity | Proposta / negociação | `Opportunity` sozinho |
| **Account** | `Account` (era `Client`) · `/accounts` | sua organização | Account | Cliente (só com `lifecycle_status=active`) | Client (no modelo), Empresa |
| **Engagement** | `Engagement` · `/engagements` · `commercial_model` | Engagement | Engagement | Programa de transformação | Projeto, Conta, Contrato |
| **Project** | `Project` · `/projects` | Project | Project | Discovery Sprint · Feasibility · PROVE · Scale | Engagement, Entrega |
| **Process** | `Process` (era `Processo`) | Process (mapa AS-IS) | Process | Processo | Fluxo, Projeto |
| **ProcessStep** | `ProcessStep` (era `ProcessoEtapa`) | Step | Process Step | Etapa | Tarefa |
| **Discovery** | `Discovery` · `/discoveries` | Discovery | Discovery | Discovery Sprint (o produto) | Reunião, Documento, Fase |
| **DiscoverySession** | `DiscoverySession` | sessão na agenda | Discovery Session | sessão de Discovery | Meeting |
| **ProcessObservation** | `ProcessObservation` | — | Process Observation | — | Evidence |
| **Evidence** | `Evidence` (split de `Evidencia`) | Evidence (só a revisada) | Evidence | evidência | Finding, Achado, Conclusão |
| **Finding** | `Finding` (split de `Evidencia`) | Finding | Finding | achado / descoberta | Evidência, Opinião, Insight |
| **PainPoint** | `PainPoint` | Pain Point | Pain Point | gargalo / dor | Oportunidade, "problema" solto |
| **ImprovementOpportunity** | `ImprovementOpportunity` · `/improvement-opportunities` | Improvement Opportunity (no backlog) | Improvement Opportunity | oportunidade (no Opportunity Map) | Commercial Opportunity, Projeto |
| **PriorityAssessment** | `PriorityAssessment` | Opportunity Score | Priority Assessment | Opportunity Score | Prioridade (campo), `ai_score` |
| **SolutionHypothesis** | `SolutionHypothesis` | Solution Hypothesis | Solution Hypothesis | hipótese de solução | Solução, Proposta, Escopo |
| **BusinessCase** | `BusinessCase` · `/business-cases` | — | Business Case | business case / justificativa do investimento | `Case` (a prova social), Proposta, ROI |
| **FeasibilityAssessment** | `FeasibilityAssessment` | Technical Feasibility (o laudo) | Feasibility Assessment | Technical Feasibility Brief | Feasibility (a fase), POC |
| **ProveExperiment** | `ProveExperiment` | PROVE | PROVE | PROVE | Piloto, POC, MVP |
| **KPI** | `KPI` (extraído de `DigitalEmployee`) | KPI | KPI | indicador | Outcome, Meta |
| **Measurement** | `Measurement(kind=…)` | leitura do KPI | Measurement | medição | KPI |
| **Baseline** | `Measurement(kind=baseline)` | Baseline | Baseline | Baseline | Meta, Outcome, estimativa |
| **Outcome** | `Measurement(kind=outcome)` | Outcome | Outcome | resultado medido | Gate, promessa, ROI projetado |
| **Value** | `ValueLedgerEntry` → Value Ledger | Value Ledger | Value · Client Value Ledger | valor gerado | ROI projetado, Case |
| **GateDecision** | `GateDecision` (era `GateOutcome`) | decisão da fase | Gate Decision | GO / CONDITIONAL GO / REDESIGN / NO-GO | Outcome |
| **DigitalEmployee** | `DigitalEmployee` | Digital Employee | Funcionário Digital | Funcionário Digital | Solução, SolutionHypothesis, Agente |
| **Service** | `Service` (catálogo de ofertas) | nome do produto contratado | degrau / produto | Discovery Sprint, PROVE… | Estágio, Fase, Tier de trabalho |
| **JourneyPhase / ProjectPhase** | idem | timeline da fase | fase FDE | DISCOVER · PRIORITIZE · … | os agregados Feasibility/PROVE |
| **Case** | `Case` | só com autorização | Case Library | Case | Outcome, Value, `BusinessCase` |

---

## 3. O que o One mostra — e o que nunca mostra

O One é uma **projeção de leitura** do Pulse. Ele não tem vocabulário próprio: se um termo não existe no Pulse, não existe no One.

| No One | Nunca no One |
| --- | --- |
| Engagement · Project · fase e progresso | Lead |
| Process · ProcessStep (o AS-IS validado) | Qualification e seu resultado |
| Finding · PainPoint (revisados) | CommercialOpportunity, `PipelineStage`, valor, probabilidade |
| Evidence marcada como revisada e publicável | Evidence não revisada, transcrição bruta |
| ImprovementOpportunity + Opportunity Score | `PriorityAssessment.rationale` interno |
| SolutionHypothesis · FeasibilityAssessment · GateDecision | preço de tabela, margem, `Service.price`, `BusinessCase` |
| ProveExperiment · KPI · Baseline · Outcome | Case de outros clientes |
| Value Ledger · Deliverables · DigitalEmployee | qualquer dado de outra Account |

Três regras que sustentam isso:

1. **Nada aparece no One antes de ser revisado por humano.** Finding com `epistemic_status=hypothesis` aparece rotulado como hipótese ou não aparece — nunca aparece como fato.
2. **O One nunca renomeia.** O que o Pulse chama de Engagement, o One chama de Engagement.
3. **O One nunca é fonte primária.** Nenhuma medição nasce lá.

---

## 4. Enums canônicos

| Campo | Valores | Observação |
| --- | --- | --- |
| `qualification.outcome` | `qualified` · `nurture` · `disqualified` | Só `qualified` abre CommercialOpportunity (D2) |
| `finding.epistemic_status` | `fact` · `hypothesis` · `unknown` | Extração por IA nasce `hypothesis` (D6) |
| `gate_decision` | `go` · `conditional_go` · `redesign` · `no_go` | Vale **só** para Feasibility (D7 · D9). A decisão do PROVE é `scale` · `iterate` · `stop` |
| `measurement.kind` | `baseline` · `outcome` · `monitoring` | Uma única `baseline` por KPI e janela |
| `journey_phase.canonical_stage` | `discover` · `prioritize` · `feasibility` · `prove` · `scale` · `optimize` | Enum canônico e fechado (ADR 0053). A fase `VALUE` **não existe**; o Priority Assessment é a fase `prioritize`, e "Fase" nomeia só o ciclo do cliente |
| `account.lifecycle_status` | `prospect` · `active` · `inactive` | Rótulo "cliente" só em `active` |
| `service.category` | `acquisition` · `commercial` | `qualification_call` é `acquisition` (D4) |
| `engagement.status` | `active` · `paused` · `closed` | |
| `engagement.commercial_model` | `design_partner` · `paid` | Obrigatório. `design_partner` não exige CommercialOpportunity de origem (D8) |
| `activity.dunning_signal` | `forgot` · `unable_to_pay` · `dissatisfied` | Aliases v1: `esqueceu` · `nao_pode` · `insatisfeito` (D10) |
| `dunning_step` | `pre_notice` · `reminder` · `firm` · `escalation` · `renegotiation` | Aliases v1: `pre_aviso` · `lembrete` · `firme` · `escalada` · `renegociacao` (D10) |
| `satisfaction_record.source` | `declared` · `perceived` | Aliases v1: `declarada` · `percebida` (D10) |
| `satisfaction_record.level` | `promoter` · `satisfied` · `neutral` · `dissatisfied` | Aliases v1: `promotor` · `satisfeito` · `neutro` · `insatisfeito` (D10) |
| `digital_employee_blueprint.area` | `commercial` · `finance` · `hr` · `legal` · `support` | Aliases v1: `comercial` · `financeiro` · `rh` · `juridico` · `atendimento` (D10) |

---

## 5. Termos banidos

| Termo | Por quê | Usar |
| --- | --- | --- |
| `Opportunity` sem qualificador | Colide entre venda e melhoria operacional | `CommercialOpportunity` ou `ImprovementOpportunity`. Únicas exceções: os rótulos de artefato **Opportunity Score**, **Opportunity Map** e **Improvement Opportunity Backlog** — nomes de entregável, não entidades |
| `Client` como nome de modelo | A organização é Account desde prospect | `Account` (rótulo "cliente" só na UI, com `lifecycle_status=active`) |
| `Evidencia`, `Processo`, `ProcessoEtapa` | Nomes em português no modelo | `Evidence`, `Process`, `ProcessStep` |
| `GateOutcome` | Colide com Outcome de negócio | `GateDecision` |
| "Cockpit", "portal do cliente" | Nome antigo/genérico do One | **One** |
| "portal Biahflow", "o CRM" | Nome genérico do Pulse | **Pulse** |
| "POC", "piloto" para o PROVE | PROVE é produção controlada com critério prévio | **PROVE** |
| "Opportunity Score" de uma venda | O score mede melhoria operacional, não receita | Score só em ImprovementOpportunity |
| `Lead.ai_score` como qualificação | É score de aquisição, insumo — não decisão | `Qualification.outcome` |
| `Project.ai_opportunity` como prioridade | É maturidade de IA da conta | `PriorityAssessment` |
| "ROI" como resultado | ROI projetado não é resultado medido | `Outcome`, depois `Value` |

---

## 6. Invariantes de linguagem

Estas viram teste automatizado no Pulse e revisão de PR nos dois repos.

1. Nenhum identificador novo (modelo, campo, rota, componente, prop) contém `opportunity` sem qualificador.
2. Nenhum identificador novo contém `client` como sinônimo de organização.
3. Nenhum identificador novo contém `outcome` referindo-se a decisão de gate.
4. Nenhum modelo novo tem nome em português.
5. `Qualification.outcome != qualified` não abre CommercialOpportunity.
6. Nenhum Project nasce de um `Service` com `category=acquisition`.
7. Todo Project tem `engagement_id` não nulo.
8. `Finding` criado por extração de IA nasce `epistemic_status=hypothesis`.
9. `Finding` com `epistemic_status=fact` tem ao menos uma `Evidence` viva e revisor humano.
10. Nenhum endpoint do One expõe `Lead`, `Qualification`, `CommercialOpportunity` ou `PipelineStage`.
11. Todo texto voltado ao cliente que diga "Outcome" aponta para um `Measurement(kind=outcome)` com `Baseline` comparável.
12. `ValueLedgerEntry` aponta para um `Outcome` e registra método de atribuição.
13. Todo `Engagement` tem `commercial_model` preenchido e referência ao instrumento assinado que o originou.
14. `Engagement.commercial_model=design_partner` não exige `CommercialOpportunity` de origem — e não dispensa o Engagement.
15. Todo valor novo de enum é inglês canônico. Valores portugueses existentes são aliases de compatibilidade explícitos da `/api/v1/` e não sobrevivem à `/api/v2/`.

---

## 7. O que muda em cada superfície

### Pulse (repo `pulse`)
Seis fatias, na ordem do gap doc: Qualification antes de CommercialOpportunity → Engagement entre Account e Project → split Evidence/Finding → PainPoint/ImprovementOpportunity/Priority/SolutionHypothesis → KPI/Measurement/ValueLedger → renomes físicos e remoção de aliases.

### One (repo `one`)
Renomear a superfície para o vocabulário canônico antes de crescer: `Client`→`Account`, introduzir Engagement como raiz de navegação, expor Finding/PainPoint/ImprovementOpportunity com o rótulo certo, e implementar o guard de visibilidade da seção 3.

### Notion
**Feito em 28/08/2026.** Ontology v1 corrigida (§3, §4, §9, §10, §13 — bump para v1.1); Sistema Operacional — PULSE com pipeline de dois trilhos, seis degraus vendáveis e "Opportunity" sempre qualificado; Metodologia FDE com o enum de Qualification, `finding.epistemic_status` e `gate_decision`; Material Comercial com os três resultados de Qualification. O que sobra daqui em diante é manutenção: termo novo entra primeiro nesta página.

### Biahflow (mercado)
Script de Qualification passa a terminar em `qualified` / `nurture` / `disqualified`. Escada comercial mostra seis degraus. Executive Readout chama o número de Opportunity Score e nunca aplica a palavra a uma venda.

---

## 8. Evolução

Mudança de significado gera **nova versão desta página e da Ontology**, com registro explícito. Nunca se altera em silêncio o sentido de um termo já persistido. Termo novo entra primeiro aqui, depois no Pulse, depois no One.

---

## 9. Pendências abertas — decisão do Daniel

A varredura de 28/08/2026 cobriu as 20 páginas de conteúdo do workspace e os schemas das 4
databases vivas. Corrigi tudo que era violação de vocabulário. Sobraram cinco pontos que **não são
de vocabulário — são decisão de negócio**, e por isso ficaram intocados. A **ADR 0053** decidiu
quatro deles — **A1, A3, A4 e A5** —, marcados como resolvidos abaixo. Continua aberta apenas a
**A2**.

| # | Pendência | Onde | Status — por que não decidi por você |
| --- | --- | --- | --- |
| A1 | **"Implementation Project"** aparece como venda direta de implementação, sem PROVE. Se existe, é um sétimo caminho comercial fora dos seis degraus | PROVE Framework | ✅ **Resolvida pela ADR 0053:** "Implementation Project" / "IMPLEMENTATION" deixa de existir. O caminho é **Scale** (R$ 80k) |
| A2 | **"Design Partner"** funciona como oferta de entrada (Discovery sem cobrança), mas o único gratuito no catálogo é a Qualification Call | Home Care KB · Igreja — Entrada via Design Partner · Founding Client Program | **Parcialmente resolvido em D8:** o Design Partner Agreement já é origem válida de Engagement, e `commercial_model` marca a condição. O que continua aberto é só o catálogo: se for condição comercial de um degrau ("Discovery Sprint em condição Design Partner"), são seis degraus; se for oferta própria, sete |
| A3 | Duração da **Qualification Call**: `30-45min` em três páginas, `45–60 min` em uma | Discovery Questions × Metodologia FDE / Founding Client / Discovery Sprint | ✅ **Resolvida pela ADR 0053:** a duração canônica é **45–60 min**. Onde estiver "30–45 min", corrige-se |
| A4 | Preço da **Technical Feasibility**: `R$ 2.500–5.000` no Feasibility Framework, `R$ 5.000` no Financeiro & Precificação | Feasibility Framework × Financeiro & Precificação | ✅ **Resolvida pela ADR 0053:** **R$ 5.000**, preço único. A faixa R$ 2.500–5.000 deixa de existir |
| A5 | O Playbook de Nova Vertical diz "PROVE operando — cobrança: **Não** — concedido dentro do acordo de Design Partner" na tabela do **Passo 3–4**, e a §12 trata das alternativas ao PROVE gratuito fora desse acordo | Playbook — Entrada em Nova Vertical | ✅ **Resolvida pela ADR 0053:** o PROVE é gratuito **apenas dentro de um acordo de Design Partner**; para todos os demais é pago. Cada degrau concedido entra no funil como `CommercialOpportunity` no preço de tabela, com o subsídio como desconto — nunca zero |

### Dívida estrutural conhecida

As databases do Notion (Projects · Tasks · Meetings · Docs) **não implementam o modelo canônico**
— `Project` é a raiz da hierarquia lá, sem `Account` nem `Engagement` acima. Isso é coerente com a
decisão de que o CRM vive no Pulse, mas significa que essas databases são camada de execução
operacional, **não** fonte da verdade do modelo. Quem quiser saber a estrutura da relação com um
cliente olha o Pulse, não o Notion.

Na varredura, `Projects.Lead` foi renomeado para `Owner` (colidia com a entidade `Lead`) e
`Projects.Stage` para `Execution Status` (não são fases da jornada).

### Regra de manutenção

Termo novo entra **primeiro nesta página**, depois no Pulse, depois no One. Página nova no Notion
que use vocabulário de domínio referencia esta página. Divergência encontrada em campo se registra
aqui antes de ser corrigida na página de origem — assim o mapa nunca fica atrás da realidade.
