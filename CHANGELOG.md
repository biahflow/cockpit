# Changelog

Todas as mudanças relevantes deste projeto serão registradas neste arquivo.

## Não lançado

### Adicionado

- AI Score: índice de maturidade/oportunidade de IA por cliente, gerado por IA a partir da transcrição de uma reunião (Discovery/Assessment) e gravado no projeto como rascunho; após revisão humana e publicação, cruza ao portal do cliente pelo snapshot e agrega na visão multi-cliente — FDD 014, RFC 0002.
- Agendamento: qualificação de leads por IA no intake do site e **booking automático** por leads qualificados — horários livres reais (free/busy do Google) e reunião agendada com evento no calendário + confirmação; endpoints públicos `booking/slots/` e `booking/book/` atrás de token efêmero, e widget de agendamento no site — FDD 013, RFC 0002.
- Calendário → tarefas: eventos do Google Calendar compartilhado com um marcador `#proj-<id>` viram tarefas do projeto (command `manage.py sync_calendar` e ação admin "Sincronizar agora"), idempotente e atrás da flag `calendar` — FDD 012, RFC 0002.
- Notificações por e-mail (espelho das in-app) e digest diário por IA (`manage.py send_daily_digest`), atrás da flag `email` alternável em Configurações — FDD 010, RFC 0002.
- Contrato assistido: geração de rascunho de contrato por IA a partir de modelo, lembrete de assinatura aos pendentes e registro de assinatura (`signed`) — FDD 009, RFC 0002.
- Kickoff automático na conversão de oportunidade em projeto: cronograma inicial (marcos/tarefas de template), pasta no Drive (quando ligado) e e-mail + notificação de kickoff ao dono — FDD 008, RFC 0002.
- Discovery e Assessment por IA sobre a transcrição da reunião (`Meeting`), como rascunho para revisão humana, auditados e avaliáveis — FDD 007, ADR 0006, RFC 0002.
- Motor de agentes de IA especializados por área (Comercial/Entrega/Financeiro), com RBAC, contexto restrito, auditoria e avaliação contínua (👍/👎 + métricas) — ADR 0006, RFC 0002.
- Previsão de atrasos de projeto com explicação dos sinais (heurística explicável).
- Reuniões, pendências e resultados do projeto, alimentando o portal do cliente via webhook/snapshot — ADR 0005.
- Sincronia bidirecional de tarefas com Linear/GitHub, atrás de flag — ADR 0004.
- Toggles de integração em runtime e página de Configurações somente-admin.
- Recomendações revisáveis, indicadores de ROI e captação de leads pelo site (intake).

### Alterado

- Conversão de lead: o lead é arquivado e o cliente nasce como "prospect", promovido a "ativo" quando a oportunidade é ganha.
- Flags de integração (IA, Drive, Calendário, Assinatura, Sincronia de tarefas) passam a ser ligáveis/desligáveis em runtime; o `.env` segue como default e casa dos segredos.

### Base

- Fundação do MVP Biahflow (CRM, pipeline, projetos, documentos privados, IA com auditoria e limites, API `/api/v1/`, CI e testes).
