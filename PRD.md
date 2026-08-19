# PRD — Cockpit (Biahflow)

> Atualizado em 19/08/2026. O escopo do MVP original (CRM → conversão → execução) foi entregue e
> o produto avançou para a **jornada de consultoria assistida por IA** (RFC 0002). Desde a ADR
> 0030 o produto se chama **Cockpit** e é o **sistema primário da operação** da Biahflow — o
> Notion vira referência. O estado de entrega, item a item, vive no `roadmap.md`; este documento
> descreve o produto atual.

## Problema

A Biahflow precisa centralizar a passagem da venda para a entrega — antes dispersa entre conversas,
planilhas e documentos — e conduzir a consultoria como um produto repetível, do primeiro contato do
lead à operação contínua dos Funcionários Digitais no cliente.

## Público e objetivo

Usuários internos das áreas Administrativa, Vendas e Entrega. O portal é a **fonte da verdade** da
operação: registra clientes e leads, conduz oportunidades por um pipeline, transforma oportunidades
ganhas em projetos acompanháveis e alimenta o portal do cliente. A IA **acelera, não decide**: tudo
que ela produz é rascunho sujeito a revisão humana.

## Metodologia — FDE

A operação que o Cockpit materializa é a metodologia FDE (Forward Deployed Engineering), descrita
em [`docs/metodologia-fde.md`](docs/metodologia-fde.md): a escada
`Discover → Prioritize → [Feasibility] → Prove → Scale → Optimize`, com decision gate de quatro
saídas (GO / CONDITIONAL GO / REDESIGN / NO-GO) ao fim de Feasibility e de PROVE, quality gates por
fase e a regra comercial Account ≠ Opportunity (cada degrau vendido é uma oportunidade própria na
mesma conta). O princípio da ADR 0030 governa como a metodologia entra no produto: **contexto vira
comportamento** — checklist vira gate de fase, decisão de continuidade vira campo obrigatório,
metodologia consultável entra no corpus de conhecimento — nunca página para ler.

Correspondência com o domínio atual: os três níveis de produto (`Service.tier`) são os degraus
comerciais da escada; a Jornada de Transformação (FDD 011) é onde os gates da metodologia se
aplicam (FDD 033); as interações comerciais, riscos de projeto e registros de decisão são
FDD 035, FDD 034 e FDD 032. A camada de Discovery estruturado (processos, dores, evidências,
business cases, value ledger) é **deliberadamente adiada** até haver Discoveries reais — ADR 0030.

## Escopo

**Comercial.** Captação de leads pelo site (intake), qualificação por IA e agendamento automático de
reunião para leads qualificados. Clientes, contatos e oportunidades com valor e previsão de
fechamento, num pipeline configurável. **Três níveis de produto** (Discovery Express gratuito,
Discovery + Assessment, Implantação) que acompanham a oportunidade e definem escopo, preço e
cronograma inicial.

**Entrega.** Conversão da oportunidade ganha em projeto — sem duplicar cliente ou contexto — com
kickoff automático (marcos, tarefas, pasta no Drive e aviso ao dono). Jornada de transformação em
fases nomeadas com entregáveis, reuniões, pendências, documentos privados e Funcionários Digitais
como entidade acompanhada por KPI e ROI.

**Inteligência.** Assistente contextual por projeto e agentes especializados por área
(Comercial/Entrega/Financeiro), com contexto restrito e auditoria. Discovery, Assessment, AI Score
de maturidade, propostas e contratos gerados a partir da transcrição das reuniões — os quatro
primeiros ficam **registrados como artefatos** com estado próprio, do rascunho à decisão do
cliente, sempre com revisão humana pelo caminho. Indicadores de
ROI, health score, previsão de atrasos com explicação dos sinais e recomendações revisáveis.

**Plataforma.** Convites por e-mail, permissões por função, notificações in-app e por e-mail com
digest diário, nove integrações atrás de flag alternável em runtime (IA, Drive, Calendário,
Assinatura, Pagamento, E-mail, Sincronia de tarefas, Portal do cliente e Enriquecimento de lead) —
nenhuma delas liga sem as credenciais que exige —, a **régua de cobrança**, que é o décimo
interruptor e a única flag que não é integração (não consome credencial nenhuma e nasce desligada
por decisão, não por falta de configuração — FDD 036), arquivamento reversível com confirmação, e
API versionada `/api/v1/`.

## Fora de escopo

- **Consumo** do portal do cliente — o Biahflow emite webhook e snapshot; a interface do cliente é
  o repositório `portal_cliente`, em trilho separado (ADR 0003).
- **Outros provedores de assinatura** — os adaptadores homologados são o Autentique (em uso) e o
  Clicksign (ADR 0007); DocuSign e afins entram como novas classes do mesmo protocolo, ainda não
  construídas.
- **Ações autônomas de IA** — nenhum agente executa efeito colateral sozinho; memória multi-turno e
  ferramentas de ação ficam para decisão futura (ADR 0006).
- **Dados comerciais no portal do cliente** — valor, custo e margem nunca cruzam a fronteira.

## Critérios de sucesso

- Uma oportunidade ganha torna-se um projeto exatamente uma vez, sem duplicar cliente ou contexto
  comercial, e já nasce com o cronograma do nível de produto vendido.
- Pessoas de Entrega acompanham prazos, itens vencidos, saúde e risco dos projetos em um só lugar.
- Documentos não podem ser obtidos por usuários sem permissão.
- Todo artefato gerado por IA é auditável, avaliável e passa por revisão humana antes de sair.
- É possível medir a conversão entre os níveis de produto, a conversão entre as etapas da jornada
  (Discovery → Assessment → Proposta → Contrato) e o ROI por cliente, projeto e serviço.
