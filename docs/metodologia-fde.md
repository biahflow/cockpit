# Metodologia FDE — Forward Deployed Engineering

> Destilado normativo do material de estratégia da Biahflow (hub Notion "🧭 Biahflow" e a
> conversa que o originou), trazido para o repositório pela ADR 0030. Este documento é a
> versão consultável da metodologia: regras e checklists, sem a prosa de origem. O que aqui
> for checklist ou gate deve existir também como comportamento do sistema (FDD 033); quando
> as duas coisas divergirem, o sistema é que está errado ou este documento envelheceu —
> registrar `SOURCE_OF_TRUTH_CONFLICT` e decidir.

## O que é FDE

Forward Deployed Engineer: o perfil na interseção de engenharia, produto, consultoria e
negócio. A postura que o define: *entrar na operação do cliente, entender o problema de
negócio, desenhar a solução, construir, integrar, colocar em produção e verificar se gerou
resultado.* Difere do engenheiro tradicional (espera requisito), do consultor (recomenda e
sai) e do sales engineer (demonstra produto). A Biahflow se posiciona como empresa de
**engenharia de IA aplicada à operação**, não como agência de automação.

O manifesto: **nós não começamos pela IA; começamos pelo problema.** IA (agente, RAG, visão
computacional) é uma das tecnologias possíveis ao lado de automação tradicional, integração,
regra determinística e intervenção humana — o decisor compra resultado, não tecnologia.

## A escada

```
DISCOVER → PRIORITIZE → [ TECHNICAL FEASIBILITY ] → PROVE → SCALE → OPTIMIZE
```

| Fase | Pergunta que responde |
| --- | --- |
| Discover | O que está acontecendo? |
| Prioritize | Onde devemos atuar? |
| Technical Feasibility | A tecnologia consegue fazer a tarefa? *(condicional)* |
| Prove | Isso realmente funciona em produção controlada? |
| Scale | Como capturamos o valor? |
| Optimize | Como continuamos melhorando? |

**Feasibility é sempre gate e às vezes produto (ADR 0053).** O Decision Gate T.O.E. acontece em
100% dos casos e sai no Executive Readout do Discovery, sem cobrança — ninguém o pula. A
*Technical Feasibility* como degrau vendido entra somente quando responder ao gate exige
**medição**: puxar amostra de dado real ainda não vista, medir o Ceiling de Input, testar a
integração. Quando a tecnologia é sabida e a dúvida é de resultado operacional, não há o que medir
e vai-se direto ao PROVE.

**Cada gate tem seu vocabulário (ADR 0053)** — exatamente uma saída, decidida por humano.

Ao fim de **Feasibility**, que responde *"a tecnologia consegue fazer a tarefa?"*:

- **GO** — segue para a próxima fase.
- **CONDITIONAL GO** — segue com ressalvas nomeadas e monitoradas.
- **REDESIGN** — muda a abordagem técnica e testa de novo (volta à fase anterior).
- **NO-GO** — a tecnologia/hipótese não sustenta a tarefa como está; não segue.

Ao fim de **PROVE**, que responde *"funcionou em produção controlada?"*:

- **SCALE** — o resultado se sustenta; expande.
- **ITERATE** — a hipótese vale, a execução ainda não; ajusta e mede de novo.
- **STOP** — não se sustenta (técnica, econômica ou operacionalmente); não segue.

**"Fase" nomeia o ciclo do cliente, e só ele (ADR 0053).** A entrada da casa numa vertical nova se
chama **Passo 0 a 6** — palavra diferente para escala diferente. Nenhum documento chama de "fase" a
numeração de entrada em vertical.

Comercialmente, cada degrau é uma **CommercialOpportunity separada na mesma conta** (Account ≠
CommercialOpportunity): a empresa é uma conta; cada venda — Discovery Sprint, Feasibility, PROVE,
Scale, partnership — é uma oportunidade própria no pipeline, o que torna a expansão de
receita visível.

## Design Partner — o modo de entrada em vertical nova (ADR 0053)

Até **três** organizações por vertical nova entram sem cobrança. O acordo fixa **escopo, não
calendário**: um Discovery, um gate, uma Feasibility quando disparar, e um PROVE, sobre **um**
processo-alvo. Sem teto por fase; encerramento automático em 120 dias se o cliente travar.

A conversa comercial acontece **no go-live do PROVE**, não no fim de uma janela — continuar rodando
já é Transformation Partnership, paga desde o primeiro mês, e a medição corre em paralelo sem
segurar a cobrança.

A contrapartida é contratual, não moral: acesso a dado real, sponsor nomeado, horas semanais
comprometidas do time do cliente, e case + depoimento + referência por escrito. Descumprimento
encerra o acordo.

No funil, o gratuito aparece como **oportunidade real**: `estimated_value` no preço de tabela e o
subsídio registrado como desconto. Valor concedido é número que se olha; oportunidade zerada some.

## Discovery

### Níveis de profundidade

- **L0 — Executive**: negócio, objetivos, grandes dores.
- **L1 — Process**: fluxo ponta a ponta.
- **L2 — Operational**: tarefas, pessoas, exceções, tempos, volumes.
- **L3 — Technical**: sistemas, APIs, dados, segurança, integrações.
- **L4 — Economic**: custo atual, perdas, ROI, business case.

### As 7 perguntas

1. Me mostra um caso real do início ao fim?
2. Quem faz isso?
3. Onde faz?
4. Quanto tempo leva e quantas vezes acontece?
5. O que acontece quando dá errado?
6. Quanto isso custa ou impacta a operação?
7. O que eu ainda não perguntei que é importante?

### P-S-D-T-E-R (para cada etapa de um processo)

**P**essoas (quem faz) · **S**istema (onde faz) · **D**ados (o que entra/sai) ·
**T**empo (quanto demora) · **E**rro (o que pode dar errado) · **R**etrabalho (o que
acontece quando dá errado).

### As 5 formas de evidência — nunca só entrevista

Entrevista (o que dizem) · Observação/shadowing (o que fazem) · Artefatos (planilhas, PDFs,
croquis) · Sistemas (ERP, CRM, CAD, WhatsApp) · Dados (volumes, tempos, custos, erros).

Todo achado é rotulado **FATO / HIPÓTESE / DESCONHECIDO** — nunca se apresenta hipótese como
fato. Custo do estado atual: `Volume × Tempo × Pessoas × Custo + Retrabalho + Erros +
Perdas + Espera + Risco`.

### Regras de conduta na reunião

- Não ir buscando "onde colocar um agente"; ir entender como a organização funciona e onde
  existe perda. Sem jargão técnico na primeira reunião.
- Sempre um caso real recente do começo ao fim — nunca "como deveria funcionar".
- Não propor solução cedo; anotar como HIPÓTESE e continuar perguntando "por quê".
- Sintetizar na própria reunião e validar ("está correto?"); fechar com a pergunta 7.
- Postura ideal ao sair: *"ainda não sei a melhor solução, mas sei exatamente quais
  perguntas precisamos responder para descobri-la."*

### Princípio da entrada

**Antes de sofisticar a automação, melhore a entrada.** Padronizar a captura (formulário,
levantamento guiado) costuma resolver mais que IA pesada corrigindo entrada ruim depois.

## Quality gates (antes de entregar qualquer coisa ao cliente)

| Fase | Checklist |
| --- | --- |
| Discovery | AS-IS validado com o cliente? Números sustentados por evidência? Hipóteses identificadas e rotuladas? Opportunity Score calculado? Próximo passo (PROVE/Feasibility) recomendado? |
| Feasibility | Baseline definido? Amostra adequada? Erros classificados? T.O.E. avaliado (Technical/Operational/Economic)? Economics calculado? Decision gate registrado? |
| PROVE | Baseline registrado? Critérios de sucesso definidos **antes** de construir? Evidência de produção controlada? Decision gate registrado? |

## Princípio dos 3 ativos

Toda entrega deixa três ativos: (1) resultado para o cliente, (2) padrão reutilizável para a
Biahflow, (3) prova social para vender o próximo cliente. Entrega que só gera o primeiro
indica captura falha do processo.

## Ritmo

Semanal: Pipeline Review (oportunidades por estágio), Delivery Sync (projetos ativos, riscos
abertos, decisões pendentes), Content & Pipeline Planning. Mensal: Monthly Business Review e
— por cliente ativo — Monthly Transformation Review (valor gerado, backlog de oportunidades,
próximos passos).
