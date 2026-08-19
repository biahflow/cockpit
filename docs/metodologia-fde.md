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

**Feasibility é condicional:** entra somente quando há dúvida se a tecnologia sustenta a
tarefa. Quando a tecnologia é sabida e a dúvida é de resultado operacional, vai-se direto ao
PROVE.

**Decision gate (obrigatório ao fim de Feasibility e de PROVE)** — exatamente uma de quatro
saídas, decidida por humano:

- **GO** — segue para a próxima fase.
- **CONDITIONAL GO** — segue com ressalvas nomeadas e monitoradas.
- **REDESIGN** — muda a abordagem técnica e testa de novo (volta à fase anterior).
- **NO-GO** — a tecnologia/hipótese não sustenta a tarefa como está; não segue.

Comercialmente, cada degrau é uma **Opportunity separada na mesma conta** (Account ≠
Opportunity): a empresa é uma conta; cada venda — Discovery Sprint, Feasibility, PROVE,
Scale, partnership — é uma oportunidade própria no pipeline, o que torna a expansão de
receita visível.

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
