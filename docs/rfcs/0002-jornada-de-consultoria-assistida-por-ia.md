# RFC 0002 — Jornada de consultoria assistida por IA

## Proposta

Transformar a consultoria em produto: uma jornada única, do primeiro contato à operação contínua,
com um **agente de IA especializado por etapa** e **revisão humana obrigatória** em tudo (nada
executa ação sozinho). O Biahflow segue como fonte da verdade; a IA acelera, não decide.

Etapas: Lead → Agendamento → Discovery → Assessment → Proposta → Contrato → Kickoff → Implantação →
Go-live → Hypercare → Operação contínua.

## Estratégia

Construir um **motor de agentes** reutilizável uma vez (contexto restrito por área, RBAC,
auditoria via `AiInteraction`, avaliação/feedback) e **plugar cada etapa incrementalmente**. Cada
agente é uma configuração sobre o mesmo motor. A primeira leva (Versão 4) entrega o motor + agentes
por área (Comercial/Entrega/Financeiro) + previsão de atrasos + avaliação contínua.

## Mapa etapa → primitivo

Atualizado em 05/08/2026. Salvo onde marcado, todas as etapas já têm primitivo implementado.

- Lead → `Lead` + intake do site. Agendamento → qualificação por IA no intake + booking automático
  por leads qualificados (`qualification.py` + `booking.py` + `calendar_sync.freebusy`, FDD 013).
- Discovery e Assessment → `Meeting` + transcrição, com extração por IA (`ai.py`, FDD 007) e
  **AI Score** de maturidade/oportunidade gravado no `Project` (`ai_score.py`, FDD 014).
- Proposta → ação IA `proposal`. Contrato → geração por IA a partir de modelo + lembrete de quem
  falta assinar + **assinatura no provedor homologado** (`esign` com adaptador Clicksign e webhook
  de status assinado por HMAC, idempotente — FDD 009, ADR 0007); `mark-signed` vira fallback manual.
- **Artefatos das etapas → `Artifact` (FDD 016, ADR 0008).** Discovery, Assessment, Proposta e
  Contrato deixam de ser texto efêmero e viram registro com conteúdo e estado próprio
  (`rascunho → em revisão → enviado → aceito/recusado`), ligado ao `AiInteraction` que o gerou e à
  reunião de origem. O contrato acompanha a decisão do signatário pelo webhook, e a conversão
  **entre etapas** passa a ser medida em `funnel.by_stage`.
- **Nível de produto → `Service.tier` (FDD 015).** Discovery Express (grátis), Discovery +
  Assessment e Implantação estruturam o catálogo: a `Opportunity` carrega o nível vendido, o
  projeto o herda na conversão, e ele define o cronograma de kickoff e o escopo/preço da proposta.
- Kickoff → `convert-to-project` com marcos/tarefas de template por nível, pasta no Drive e
  e-mail + notificação ao dono (`kickoff.py`, FDD 008).
- Implantação/Testes → portal do cliente + tarefas/pendências. Go-live/Hypercare → notificações
  por e-mail e digest diário por IA (`digest.py`, FDD 010). Operação → `recommendations`.
- **Entrega (fases nomeadas) → `JourneyPhase`/`ProjectPhase` (FDD 011).** A jornada de
  transformação virou modelo concreto: fases configuráveis (Welcome → … → Optimize),
  entregáveis que desbloqueiam por fase, avanço manual e tracker no projeto. Fonte da
  verdade no Biahflow; o portal do cliente **consome** depois (ADR 0003) — trilho separado.

## Princípios

Revisão humana obrigatória; contexto mínimo por área (anti-vazamento); auditoria e avaliação
contínua de qualidade; nada comercial vaza para o cliente (ADR 0003). Cada etapa vira uma FDD com
critérios de aceite antes de liberar.

## Compatibilidade

Aditivo ao contrato `/api/v1/`. Recursos de IA ficam atrás de flag (`AI_ENABLED`); desligados, a
plataforma opera normalmente.
