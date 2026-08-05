# Changelog

Todas as mudanças relevantes deste projeto serão registradas neste arquivo.

## Não lançado

### Alterado (incompatível)

- **Entrega vê apenas os projetos de que participa** — RFC 0003, ADR 0010, FDD 018. A FDD 017 tinha tirado dela os documentos comerciais, mas o resto do projeto seguia aberto: todos os projetos, marcos, reuniões, pendências, fases, entregáveis, funcionários digitais e artefatos, mais o risco e a saúde de cada projeto da casa e o ROI de cada cliente por `/clients/overview/`, `/risk/`, `/health/`, `/dashboard/` e o agente de entrega. Agora existe **equipe do projeto** (`ProjectMember`, `/api/v1/project-members/`, com painel no detalhe do projeto): participar é o que dá acesso, e ser dono de um marco ou tarefa deixou de bastar. A escrita fecha junto — Entrega cria e edita só dentro dos seus projetos, não cria nem apaga projeto e não move um objeto próprio para projeto alheio (antes, criar uma tarefa em projeto alheio bastava para virar dona dela e se auto-conceder acesso). A permissão de objeto passou a **negar por padrão**. **A mudança é incompatível em semântica**: para um consumidor autenticado como Entrega, as mesmas rotas devolvem menos linhas e o detalhe de projeto alheio passa de 200 para 404. A migração `0025` faz o backfill a partir de quem era dono de projeto, marco ou tarefa, então ninguém perde acesso no deploy — mas o acesso preservado é justamente o largo demais, e as alocações merecem revisão depois de subir. **Só admin monta a equipe**: quando Vendas converte uma oportunidade, o projeto nasce sem equipe e fica invisível para a Entrega até um admin incluí-la.

### Segurança

- Revisão de segurança de aplicação (RBAC, rate limiting, upload, dependências) — FDD 017, ADR 0009, RFC 0001:
  - **Documentos por função:** Entrega passa a ver apenas o documento do projeto em que atua (dona do projeto ou de um marco/tarefa dele) e não vincula documento a cliente ou oportunidade. Antes, proposta e contrato salvos como `.txt` pelo painel de artefatos ficavam ligados à oportunidade e qualquer pessoa da Entrega os baixava — o mesmo conteúdo que a FDD 016 tinha acabado de esconder dela no `Artifact`. A segregação dos artefatos, que valia só na leitura, passa a valer também na escrita, e as duas camadas do RBAC (queryset e permissão de objeto) agora concordam.
  - **Teto de requisições:** `anon`/`user` como padrão do DRF, mais escopo próprio em `login`, `invitation_accept` e `portal_read`. Errar a senha deixa de ser ilimitado e o Bearer do snapshot deixa de ser um oráculo de força bruta. Todas as taxas por variável de ambiente (`docs/operacao.md`).
  - **Arquivo privado de verdade:** o Django não serve mais `MEDIA_ROOT` em ambiente nenhum. Servi-lo sob `if DEBUG` — com `DJANGO_DEBUG=true` sendo o default do `.env.example` e do compose — deixava contrato e proposta acessíveis por URL adivinhável, contornando o gate de acesso.
  - **Upload:** allowlist de tipos de arquivo e sanitização do nome antes de gravar (o nome segue cru para o Drive, o fornecedor de assinatura e o snapshot do portal).
  - **Aceite de convite** com username já em uso responde 400 em vez de estourar 500.
  - **Dependências:** `pip-audit` e `npm audit` limpos; as 17 dependências de frontend declaradas como `"latest"` foram fixadas nas versões do lockfile.

### Adicionado

- Artefatos da jornada como entidade: Discovery, Assessment, Proposta e Contrato viram `Artifact` (um modelo com `kind`) com conteúdo, estado próprio (`rascunho → em revisão → enviado → aceito/recusado`) e carimbos de tempo. O texto gerado pela IA deixa de ser efêmero — as quatro actions passam a registrá-lo em rascunho para revisão humana, ligado ao `AiInteraction` que o auditou e à reunião de origem (antes, Discovery e Assessment sumiam ao recarregar a página, e proposta e contrato só sobreviviam como `.txt` salvo à mão). Contrato assinado no fornecedor fecha o artefato sozinho pelo webhook, e Indicadores ganha o funil de conversão por etapa da jornada — FDD 016, ADR 0008, RFC 0002.
- Autentique como fornecedor de assinatura: adaptador sobre o mesmo protocolo de provider (GraphQL multipart com o arquivo real, modo sandbox e webhook `x-autentique-signature`), homologado contra o sandbox da conta. `ESIGN_DELIVERY` escolhe quem avisa o signatário — o fornecedor (padrão) ou o portal, que passa a guardar o link de assinatura, mostrá-lo em Documentos e repeti-lo no lembrete — FDD 009, ADR 0007.
- Assinatura eletrônica com provedor homologado: adaptador Clicksign atrás de um protocolo de provider (`ESIGN_PROVIDER`; sem um reconhecido segue o comportamento antigo) e **webhook de status** em `POST /api/v1/esign/webhook/`, autenticado por HMAC-SHA256 do corpo cru (`Content-Hmac`), com de-para explícito de eventos e idempotente na reentrega — a assinatura passa a `signed`/`declined` sozinha e notifica quem enviou o documento; `mark-signed` fica como fallback manual — FDD 009, ADR 0007.
- Três níveis de produto sobre o catálogo de `Service` (Discovery Express gratuito, Discovery + Assessment e Implantação, um ativo por nível): a oportunidade carrega o nível vendido, o lead convertido entra pela porta gratuita, a conversão em projeto herda o nível, o kickoff semeia um cronograma por nível, a proposta gerada por IA respeita escopo e preço de tabela, e Indicadores ganha o funil de conversão por nível — FDD 015, RFC 0002.
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

- Documentação alinhada ao estado atual: o `PRD.md` deixa de descrever apenas o MVP e passa a cobrir a jornada assistida por IA (com o que segue fora de escopo), o mapa etapa → primitivo do RFC 0002 deixa de apontar como pendentes etapas já entregues, e `docs/architecture.md` descreve o armazenamento real de documentos (Drive ou disco local) e registra que o MinIO do compose está provisionado mas não conectado.
- Conversão de lead: o lead é arquivado e o cliente nasce como "prospect", promovido a "ativo" quando a oportunidade é ganha.
- Flags de integração (IA, Drive, Calendário, Assinatura, Sincronia de tarefas) passam a ser ligáveis/desligáveis em runtime; o `.env` segue como default e casa dos segredos.

### Base

- Fundação do MVP Biahflow (CRM, pipeline, projetos, documentos privados, IA com auditoria e limites, API `/api/v1/`, CI e testes).
