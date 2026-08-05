# Roadmap — Portal Biahflow

Atualizado em 05/08/2026. Separa o que já compõe a plataforma do que falta, e aponta o norte
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
- [x] Domínio, HTTPS, variáveis de produção e segredos em cofre apropriado — FDD 019, ADR 0011.
      O recorte de **código, configuração e runbook**: comprar domínio, terminar TLS, escolher
      provedor e popular o cofre seguem manuais, agora documentados em
      `docs/runbooks/producao.md`. Fecha os quatro itens que a FDD 017 adiou (SSL redirect, HSTS,
      header de proxy, expiração de sessão, validadores de senha e `check --deploy` no CI) e a
      ressalva de `LocMemCache` da ADR 0009. Nasce um caminho de produção de fato:
      `docker-compose.prod.yml` com nginx + gunicorn + Redis, imagem em dois estágios com
      `uv.lock`, `collectstatic` e usuário sem privilégio, documentos em volume nomeado. E
      configuração insegura **deixa de subir**: sete system checks de deploy recusam o segredo do
      repositório, SQLite efêmero, cache por processo, `ALLOWED_HOSTS` de localhost e origem
      `http://` — rodados pelo entrypoint da imagem e pelo CI.
- [x] Monitoramento: logs centralizados, alertas, health checks e rastreamento de erros — FDD 020,
      ADR 0012. Fecha o que a FDD 019 tinha adiado nominalmente. Toda requisição ganha um
      **`X-Request-ID`** que nasce na borda, entra em toda linha de log, vira tag no Sentry e volta
      na resposta — o SPA mostra o código na tela de erro, e é por ele que se acha a requisição nos
      três logs (nginx, gunicorn, aplicação). Log estruturado em **JSON** em produção, texto em
      desenvolvimento. **Sondas de verdade**: `/healthz` (vivo, não toca em nada) e `/readyz`
      (pronto: banco + cache, 503 quando algum falha), como middleware — porque precisam responder
      antes de `ALLOWED_HOSTS` e do redirect de https. **Sentry** atrás de flag nos dois lados, sem
      PII; desligado, não sobra um byte do SDK no bundle do SPA. E um defeito de deploy corrigido de
      carona: a sonda anterior mandava `Host: 127.0.0.1` e levava **400** assim que
      `DJANGO_ALLOWED_HOSTS` virava o domínio real — o container nunca ficava saudável e o `web`
      nunca subia. Alertas ficam no fornecedor (`docs/runbooks/monitoramento.md`).
- [x] Retenção, backup testado e restauração do banco e dos documentos — FDD 021, ADR 0013. Fecha
      o último item que bloqueava ir ao ar. O portal ganha um **sidecar `backup`** que sobe junto
      com a stack (quem faz `up -d` já tem backup) e copia as **duas metades** do estado — Postgres
      (`pg_dump --format=custom`) e os documentos do `MEDIA_ROOT` —, com retenção por dias e envio
      **offsite opt-in** para storage compatível com S3. Ele é construído da mesma imagem do `db`
      porque `pg_dump` de major menor **recusa rodar**, e a imagem da API é bookworm (cliente 15)
      contra um servidor 16. Mas a entrega central não é a cópia: é o **teste de mesa**
      (`.github/scripts/backup-drill.sh`), que a cada PR sobe a topologia de produção, semeia dado,
      faz backup, **destrói banco e mídia**, restaura e confere que voltaram — inclusive que a
      destruição foi real, senão o drill passaria por não ter destruído nada. Ele já pegou dois
      defeitos: um `compose run` que reaproveitava a imagem antiga (e aprovou um `restore.sh`
      sabotado) e a cópia de boot que, em host novo, gravaria um dump vazio por cima do desastre. A
      aplicação não faz backup — só reclama: `manage.py backup_status` sai com código 1 quando a
      última cópia passa de 26 h, e é o gancho do alerta que faltava à FDD 020.
- [x] Revisão de segurança **de aplicação** (RBAC, CSRF, rate limiting amplo, upload, dependências)
      — FDD 017, ADR 0009. Fechou três vazamentos: Entrega baixava proposta e contrato ligados a
      oportunidade (agora só vê documento de projeto em que atua), o login não tinha teto de
      tentativas (agora `anon`/`user` + escopos nomeados) e o Django servia `MEDIA_ROOT` sob
      `DEBUG`, que é o default do compose. Mais allowlist de upload, sanitização do nome do
      arquivo, 400 em vez de 500 no aceite de convite e dependências de frontend fixadas.
      CSRF, CORS, endpoints públicos e XSS no frontend foram verificados e estavam corretos.
      O hardening de transporte (HSTS, SSL redirect, `check --deploy`) depende do item abaixo.
- [x] **Visibilidade de projeto por participação** — RFC 0003, ADR 0010, FDD 018. Fecha a
      assimetria que a ADR 0009 havia registrado como aceita: Entrega via todos os projetos e
      tudo o que pende deles, além do risco, da saúde e do ROI de toda a base pelos
      agregadores. Nasce a **equipe do projeto** (`ProjectMember`), que passa a ser o critério
      único de acesso, com backfill que preserva o que existia. Mudança **incompatível em
      semântica** para consumidores autenticados como Entrega.
- [x] Ampliar a matriz de testes: acessibilidade, responsividade e carga — FDD 022, ADR 0014.
      Fecha o bloco. Nasce uma **matriz dirigida por tabela** (`frontend/e2e/matrix.ts`): 17 telas ×
      3 larguras (390/768/1280), varridas pelo axe nas tags WCAG A e AA e conferidas contra rolagem
      horizontal, navegação alcançável e alvo de toque — tela nova entra por **uma linha**. Ela
      acendeu defeito real: o portal apagava o próprio indicador de foco (`focus:outline-none` sem
      substituto, WCAG 2.4.7), o contraste reprovava em três tons de uma vez (`text-slate-400` a
      2,5:1, `text-slate-500` a 4,47:1 sobre o fundo do próprio portal e a **cor da marca** a 3,9:1
      como texto), quatro controles do detalhe do projeto não tinham nome acessível, o kanban e a
      tabela de projetos rolavam sem receber foco, a linha de projeto só respondia a mouse, o login
      ficava **sem `h1`** no celular e o detalhe do projeto estourava a horizontal em duas frentes.
      Do lado da carga, o CI ganha um gate **determinístico** em vez de cronômetro (ADR 0014):
      mede-se a mesma rota com 3 e com 12 clientes e cobra-se que a contagem de queries não mude —
      o que reprovou três agregadores de saída (`/clients/overview/` ia de 43 a 169 queries,
      `/risk/` de 13 a 49, `/health/` de 25 a 97) e agora protege `/analytics/`, que é caro mas
      **constante**. O k6 sai do limbo: sessão por VU (o script anterior mandava um cookie só para
      20 VUs contra um teto de ≈0,55 req/s — não podia passar), cenário de leitura, cenário de
      escrita e runbook próprio. Sabotagem deliberada em cada gate revelou o que mais importa: o
      **axe não vê foco visível** (2.4.7 é verificação manual), então a correção de foco ficaria sem
      rede — daí um teste explícito de teclado. E a primeira tentativa de corrigir o foco não
      funcionou, porque `outline-none` do Tailwind v4 envenena `--tw-outline-style`; só o teste
      mostrou.

## Versão 2 — Assistente de IA (essencialmente entregue)

- [x] Chat contextual por projeto, com controle de acesso.
- [x] Resumos e sugestão de próximos passos. [x] **Discovery/Assessment sobre a transcrição da `Meeting`** (FDD 007).
- [x] Geração assistida de **propostas** (revisão humana). [x] Geração de **contratos** (FDD 009).
- [x] Auditoria (`AiInteraction`), limites de uso, anti-vazamento e **avaliação de qualidade** (👍/👎 + métricas).

## Versão 3 — Automação e portal do cliente (parcial)

- [x] Calendário: add ao Google Calendar + **criação automática de tarefas a partir de eventos** (marcador `#proj-<id>`, idempotente, atrás de flag — FDD 012).
- [x] Notificações por e-mail (espelho das in-app) + digest diário por IA, atrás de flag (FDD 010).
- [x] Assinatura eletrônica: `esign` + `SignatureRequest` + lembrete de pendentes + **adaptador
      de provedor homologado (Clicksign) e webhook de status assinado (HMAC), idempotente**
      (FDD 009, ADR 0007); `mark-signed` fica como fallback manual.
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
- [x] Contrato: geração por IA a partir de modelo + lembrete de quem falta assinar + adaptador
      de provedor homologado com webhook de status (FDD 009, ADR 0007).
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
- [x] **3 níveis de produto — Fase 4.** Estruturados sobre `Service` (`tier`, `list_price`,
      `summary`, um ativo por nível): Discovery Express (grátis), Discovery + Assessment (pago) e
      Implantação, semeados pela migração `0020`. `Opportunity.service` leva o nível no pipeline
      (selo no card e funil `by_tier` em Indicadores), a conversão de lead entra pelo nível
      gratuito, `convert-to-project` herda o nível para o projeto, o kickoff usa um cronograma por
      nível (`kickoff.KICKOFF_TEMPLATES`) e a proposta por IA respeita escopo e preço de tabela.
      Ver FDD 015 e testes em `apps/core/tests/test_services.py`.
- [x] **Assessment/Proposta/Contrato de 1ª classe — Fase 4.** Discovery, Assessment, Proposta e
      Contrato viraram `Artifact` (um modelo com `kind`), com conteúdo, estado próprio
      (`rascunho → em revisão → enviado → aceito/recusado`) e carimbos de tempo. O texto gerado
      pela IA deixa de ser efêmero: as quatro actions passam a registrá-lo em rascunho, ligado ao
      `AiInteraction` e à `Meeting` de origem. Contrato assinado no fornecedor fecha o artefato
      sozinho pelo webhook, e Indicadores ganha `funnel.by_stage` — clientes distintos por etapa,
      que é a queda entre elas. Ver FDD 016, ADR 0008 e testes em `apps/core/tests/test_artifacts.py`.

## Princípios de entrega

- Cada item relevante tem FDD, critérios de aceite e testes automatizados antes de liberar.
- Decisões técnicas duradouras exigem ADR; alterações transversais ou incompatíveis exigem RFC.
- Recursos de IA têm supervisão humana, rastreabilidade e métricas de segurança e qualidade.
