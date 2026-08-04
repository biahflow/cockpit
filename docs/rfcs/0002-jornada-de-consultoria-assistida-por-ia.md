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

## Mapa etapa → primitivo (o que já existe)

- Lead → `Lead` + intake do site. **Agendamento → qualificação por IA no intake + booking automático
  por leads qualificados (`qualification.py` + `booking.py` + `calendar_sync.freebusy`, FDD 013).**
- Discovery → `Meeting` + transcrição (falta extração por IA). Assessment → `Document` + `ai.py`.
- Proposta → ação IA `proposal`. Contrato → `esign` + `SignatureRequest` (falta gerar + lembrar).
- Kickoff → `convert-to-project` (falta automatizar marcos/tarefas/pasta/e-mail).
- Implantação/Testes → portal do cliente + tarefas/pendências. Go-live/Hypercare → notificações
  (falta e-mail + digest). Operação → `recommendations`.
- **Entrega (fases nomeadas) → `JourneyPhase`/`ProjectPhase` (FDD 011).** A jornada de
  transformação virou modelo concreto: fases configuráveis (Welcome → … → Optimize),
  entregáveis que desbloqueiam por fase, avanço manual e tracker no projeto. Fonte da
  verdade no Biahflow; o portal do cliente consome depois (ADR 0003).

## Princípios

Revisão humana obrigatória; contexto mínimo por área (anti-vazamento); auditoria e avaliação
contínua de qualidade; nada comercial vaza para o cliente (ADR 0003). Cada etapa vira uma FDD com
critérios de aceite antes de liberar.

## Compatibilidade

Aditivo ao contrato `/api/v1/`. Recursos de IA ficam atrás de flag (`AI_ENABLED`); desligados, a
plataforma opera normalmente.
