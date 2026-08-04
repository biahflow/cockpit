# Roadmap — Portal Biahflow

Atualizado em 04/08/2026. Separa o que já compõe a plataforma do que falta, e aponta o norte
(jornada de consultoria assistida por IA). Marcações: `[x]` entregue, `[~]` parcial, `[ ]` pendente.

## Base atual — entregue

- Autenticação por sessão, convite de usuários e permissões por função (RBAC).
- Clientes, contatos, oportunidades e pipeline comercial; **captação de leads** pelo site (intake).
- Conversão de oportunidade ganha em projeto, com marcos, tarefas e documentos privados.
- **Lead arquivado na conversão** e **cliente prospect → ativo** ao ganhar a oportunidade.
- **Reuniões, pendências e resultados** do projeto (alimentam o portal do cliente — ADR 0005).
- **Sincronia de tarefas** com Linear/GitHub, bidirecional e atrás de flag (ADR 0004).
- **Toggles de integração em runtime** + página de Configurações só-admin.
- Painel operacional/comercial, indicadores/ROI, API versionada (`/api/v1/`) e docs (ADR/FDD/RFC).
- Testes unitários, de API, regressão e E2E; **CI** com lint, tipos, testes, cobertura, build e E2E.

## Prontidão para produção — adiada deliberadamente

> Bloco adiado a pedido, para priorizar a jornada assistida por IA. Retomar antes de ir a produção.

- [x] Pipeline de CI (lint, tipos, testes, cobertura mínima, build e E2E) — `quality.yml`.
- [ ] Domínio, HTTPS, variáveis de produção e segredos em cofre apropriado.
- [ ] Monitoramento: logs centralizados, alertas, health checks e rastreamento de erros.
- [ ] Retenção, backup testado e restauração do banco e dos documentos.
- [ ] Revisão de segurança completa (RBAC, CSRF, rate limiting amplo, upload, dependências).
- [ ] Ampliar a matriz de testes: acessibilidade, responsividade e carga (há `backend/loadtests/`).

## Versão 2 — Assistente de IA (essencialmente entregue)

- [x] Chat contextual por projeto, com controle de acesso.
- [x] Resumos e sugestão de próximos passos. [x] **Discovery/Assessment sobre a transcrição da `Meeting`** (FDD 007).
- [x] Geração assistida de **propostas** (revisão humana). [x] Geração de **contratos** (FDD 009).
- [x] Auditoria (`AiInteraction`), limites de uso, anti-vazamento e **avaliação de qualidade** (👍/👎 + métricas).

## Versão 3 — Automação e portal do cliente (parcial)

- [x] Calendário: add ao Google Calendar + **criação automática de tarefas a partir de eventos** (marcador `#proj-<id>`, idempotente, atrás de flag — FDD 012).
- [x] Notificações por e-mail (espelho das in-app) + digest diário por IA, atrás de flag (FDD 010).
- [~] Assinatura eletrônica: `esign` + `SignatureRequest` + **lembrete de pendentes e registro de assinatura** (FDD 009); [ ] adaptador de provedor homologado (webhook de status).
- [x] Portal do cliente: **alimentação** pelo Biahflow (webhook + snapshot, ADR 0003/0005).
      [ ] Consumo no repo `portal_cliente` (isolado por organização) — trilho separado.

## Versão 4 — Inteligência operacional (concluída)

- [x] Indicadores de ROI por cliente, projeto e serviço.
- [x] Previsão de atrasos e riscos, com explicação dos sinais (heurística explicável).
- [x] Recomendações revisáveis (novos negócios, follow-ups, prazos).
- [x] **Agentes especializados por área** (Comercial/Entrega/Financeiro) com RBAC, contexto restrito e avaliação contínua (ADR 0006).

## Norte — Jornada de consultoria assistida por IA (RFC 0002)

Cada etapa da jornada vira um agente sobre o mesmo motor (revisão humana obrigatória):
Lead → Agendamento → Discovery → Assessment → Proposta → Contrato → Kickoff → Implantação →
Go-live → Hypercare → Operação. Próximas etapas a construir:

- [x] Agendamento: qualificação por IA no intake do site + booking automático por leads qualificados (free/busy do Google — FDD 013).
- [x] Discovery → Assessment automáticos sobre a transcrição da reunião (FDD 007).
- [x] Contrato: geração por IA a partir de modelo + lembrete de quem falta assinar (FDD 009). [ ] Adaptador de provedor homologado (webhook de status).
- [x] Kickoff automático: marcos/tarefas/pasta/e-mail a partir do `convert-to-project` (FDD 008).
- [x] Go-live/Hypercare: notificações por e-mail + digest diário por IA (FDD 010).

## Lacunas vs. visão da metodologia (do documento)

Levantado em 04/08/2026 ao comparar o código com a arquitetura de produto do documento
(duas jornadas, orientação a entidades, dois portais, "cérebro" compartilhado). O interno já
cobre ~70% da visão; abaixo o que falta construir aqui. Prioridade em ordem.

- [x] **Estender o snapshot (o "cérebro") — Fase 1.** `GET /portal/projects/<id>/snapshot/`
      agora envia, além de `status` + `milestones`, a **jornada de 7 fases** (`ProjectPhase`)
      com **entregáveis** (`ProjectDeliverable`), o **ROI** do projeto e a próxima reunião
      agendada. Ver `apps/core/portal.py` (`build_snapshot`/`_journey`) e testes em
      `apps/core/tests/test_portal.py`.
- [x] **Health Score composto — Fase 2.** `apps/core/health.py` (`assess_project_health`,
      espelho positivo de `risk.py`: 100 = saudável, níveis saudável/atenção/crítico). Usa os
      sinais com dado real (entregas atrasadas, reuniões não realizadas, decisões pendentes,
      ROI negativo); satisfação/bugs/acessos ficam de fora até haver onde registrá-los.
      Endpoints `/health/` e `/projects/<id>/health/`; exibido em Indicadores e no detalhe do
      projeto. Testes em `apps/core/tests/test_health.py`.
- [x] **Visão multi-cliente 🟢🟡🔴 — Fase 2.** `ClientsPage` como grid com semáforo por saúde
      (componente `StatusDot`); `ClientViewSet.overview` (lista `/clients/overview/` e detalhe
      `/clients/<id>/overview/`) agrega por cliente **fase da jornada, health, risco, ROI somado
      e próxima reunião**; `ClientDetailPage` ganhou o painel "Saúde da relação".
- [x] **Funcionários Digitais como entidade — Fase 3.** Modelo `DigitalEmployee` (projeto,
      nome, área, o que faz, status, KPI, horas/mês, ROI/mês) + CRUD (`/digital-employees/`) +
      roster no `ProjectDetailPage`; flui ao cliente pelo snapshot (`digital_employees`).
      Testes em `apps/core/tests/test_digital_employee.py`.
- [x] **AI Score — Fase 4.** Índice de maturidade/oportunidade de IA por cliente, gerado por IA
      a partir da transcrição da reunião (Discovery/Assessment) e gravado no `Project` (campos
      `ai_*`), como rascunho para revisão humana. Publicado (`ai_score_reviewed`), cruza ao portal
      pelo snapshot (`apps/core/portal.py` `ai_score_snapshot`) e agrega por cliente em
      `build_client_overview`. Ver `apps/core/ai_score.py` e testes em `tests/test_ai_score.py`
      (FDD 014).
- [ ] **3 níveis de produto — Fase 4.** Estruturar sobre `Service`: Discovery Express (grátis),
      Discovery + Assessment (pago) e Implantação — refletindo no pipeline e na proposta.
- [ ] **Assessment/Proposta/Contrato de 1ª classe — Fase 4 (opcional).** Hoje são texto de IA
      + `Document`; promover a entidades com estado próprio para medir conversão entre etapas.

## Princípios de entrega

- Cada item relevante tem FDD, critérios de aceite e testes automatizados antes de liberar.
- Decisões técnicas duradouras exigem ADR; alterações transversais ou incompatíveis exigem RFC.
- Recursos de IA têm supervisão humana, rastreabilidade e métricas de segurança e qualidade.
