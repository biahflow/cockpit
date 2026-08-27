# ADR 0030 — A operação sai do texto: o cockpit vira o sistema primário

**Status:** superada em parte pela ADR 0035
**Data:** 19/08/2026
**Fase:** transversal — posicionamento do produto e fonte primária da operação
**Relacionadas:** RFC 0002 (jornada de consultoria assistida por IA), ADR 0006 (agentes
especializados), ADR 0008 (artefatos da jornada), FDD 011 (Jornada de Transformação),
FDD 029 (base de conhecimento interna), FDD 032 (decisões extraídas de reunião)

## Contexto

A operação da Biahflow foi desenhada fora deste repositório: um hub no Notion ("🧭 Biahflow")
e uma longa conversa de estratégia definiram a metodologia FDE (Forward Deployed
Engineering) — a escada Discovery Sprint → Technical Feasibility → PROVE → Scale com decision
gate de quatro saídas, a regra Account ≠ Opportunity no CRM, os quality gates por fase, os
registros de Delivery (Decision Log, Evidence Log, Risk Register) e o Client Success (Value
Ledger, Opportunity Backlog). Esse material trazia uma regra explícita sobre ferramenta:
*"Notion enquanto o processo estiver sendo descoberto. Portal quando o processo estiver
estabilizado"* — e mandava o CRM do portal nascer só depois de 5–10 Discoveries reais.

A regra falhou na prática antes de qualquer Discovery: o Notion acumulou texto demais para
ser lido. Operar por documento exige reler páginas longas para achar a regra do momento, e a
metodologia que ninguém consegue consultar no ato não governa nada — vira prosa. Enquanto
isso, este portal já cobria mais da metodologia do que o material assumia: CRM com múltiplas
oportunidades por cliente e pipeline configurável, conversão venda→projeto com kickoff por
nível de produto, jornada de fases configurável (FDD 011), decisões extraídas de reunião por
IA (FDD 032), base de conhecimento com resposta citada (FDD 029, ADR 0022/0023). O que falta
é a camada FDE fina — gates, riscos, interações de CRM, e mais adiante o Discovery como dado.

## Decisão

**Este produto passa a ser o sistema primário da operação da Biahflow, sob o nome Cockpit.**
O Notion deixa de ser fonte operacional e vira referência/rascunho. A regra
"Notion enquanto descobre" é conscientemente substituída — não porque o processo estabilizou,
mas porque operar por documento se mostrou impraticável antes disso.

O princípio que governa a migração: **contexto vira comportamento do sistema, não página para
ler.** Checklist de qualidade vira gate que trava a conclusão de fase; decisão de continuidade
vira campo obrigatório com quatro saídas; metodologia consultável entra no corpus de
conhecimento e é servida com citação pelo agente (`/conhecimento`), não lida em documento.
Texto longo só entra no repositório se alimentar o corpus ou virar regra executável.

Da regra antiga sobrevive a metade que continua certa: **a camada de Discovery estruturado
(Processes, Pain Points, Evidence, Business Cases, Value Ledger, Opportunity Backlog) só é
modelada depois de Discoveries reais.** Materializar agora seria inventar um processo que
ainda não aconteceu; o que entra já é apenas o que o material estabilizou de fato — o decision
gate de quatro saídas e os quality gates da jornada (FDD 033), o Risk Register (FDD 034) e as
Activities do CRM (FDD 035).

## Consequências

- O repositório é renomeado para `cockpit`; a marca visual continua Biahflow (o design system
  da ADR 0024/0025 não muda). Título da SPA e referências de nome acompanham. O nome do produto
  foi superado em parte pela ADR 0035, que renomeia o produto para Pulse; o restante desta
  decisão permanece.
- A metodologia FDE entra destilada em `docs/metodologia-fde.md` e no manifesto do corpus
  (`KB_SOURCES`), consultável com citação — o antídoto declarado ao "texto demais".
- FDD 033, 034 e 035 nascem desta decisão e entram no roadmap como próximos work items.
- A migração dos dados do Notion (as databases Accounts/Contacts/Opportunities/Activities)
  fica **nomeada e não feita**: os equivalentes diretos existem (`Client`, `Contact`,
  `Opportunity` e a `Activity` da FDD 035), mas importar é trabalho separado, com decisão
  própria de dedupe e corte.
- O risco assumido: sem a disciplina do "portal só depois de estabilizar", cada bloco novo da
  camada FDE precisa provar que já estabilizou antes de virar modelo — o teste é existir no
  material como regra pronta (checklist, gate, escada), não como ideia.

## Alternativas consideradas

- **Manter o Notion primário** (o que o próprio material mandava): rejeitado pelo motivo
  registrado no contexto — o custo de leitura tornou a regra inoperante.
- **Híbrido** (cockpit assume Delivery; Notion segue com o CRM comercial): rejeitado por
  duplicar a fonte de verdade exatamente na fronteira mais movimentada — a conversão de
  oportunidade em projeto, que é a ação central deste produto.
