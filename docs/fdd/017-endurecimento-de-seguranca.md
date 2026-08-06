# FDD 017 — Endurecimento de segurança

## Jornada

Item `roadmap.md` do bloco "Prontidão para produção": *revisão de segurança completa (RBAC, CSRF,
rate limiting amplo, upload, dependências)*. O RFC 0001 já obrigava que "uploads são privados e os
testes devem cobrir tentativa de acesso entre usuários e funções" — obrigação que nenhum teste
cumpria. Esta entrega é o recorte de **aplicação**: o que é domínio, HTTPS, cofre de segredos,
backup e monitoramento fica no item de infraestrutura do mesmo bloco.

A revisão varreu RBAC, endpoints públicos, CSRF, CORS, upload, download, sessão e dependências.
Três achados eram vazamento real, dois eram defeito, e a maior parte da superfície estava correta.

## Regras

- **Entrega vê o documento do projeto em que atua.** `DocumentViewSet` estreita `get_queryset` por
  função, como `OpportunityViewSet` já fazia; "atuar" é ser dono do projeto ou de um marco/tarefa
  dele (`_acts_on_project`). A escrita acompanha: Entrega não vincula documento a cliente nem a
  oportunidade, e não vincula artefato a oportunidade. Antes, proposta e contrato salvos como
  `.txt` pelo painel de artefatos ficavam ligados à oportunidade e Entrega baixava os dois — o
  mesmo conteúdo que a FDD 016 tinha acabado de esconder dela no `Artifact`. Ver ADR 0009.
- **As duas camadas de RBAC concordam.** `has_object_permission` devolvia `True` para qualquer
  `Document` e não tinha ramo para `Artifact`; agora nega o que o queryset esconde, para que um
  caminho novo não reabra o que o outro fechou.
- **Teto de requisições em toda a API.** `AnonRateThrottle` + `UserRateThrottle` como padrão, mais
  escopos nomeados em `login`, `invitation_accept` e `portal_read`, ao lado dos quatro que já
  existiam. Todas as taxas por variável de ambiente. O `/auth/csrf/` fica de fora de escopo
  próprio de propósito: o SPA o chama antes de **cada** mutação.
- **O arquivo do documento só sai pela rota autenticada.** `config/urls.py` servia `MEDIA_ROOT` sob
  `if DEBUG`, e `DJANGO_DEBUG=true` é o default do `.env.example` e do compose — ou seja, era a
  configuração real de desenvolvimento e homologação. Com caminhos previsíveis em
  `documents/%Y/%m/`, qualquer anônimo baixava contrato e proposta por `/media/...`, contornando o
  gate da ADR 0002. A rota deixou de existir em qualquer ambiente; o SPA nunca a usou.
- **Upload com allowlist.** Além do limite de 10 MB que já existia, o tipo do arquivo é conferido
  contra `ALLOWED_DOCUMENT_EXTENSIONS`, e `original_name` é sanitizado antes de gravar. O download
  não era o risco (o Django já faz `basename` e escapa o header) — os consumidores do valor cru
  são o Drive, o fornecedor de assinatura (`"path": f"/{original_name}"`) e o snapshot do portal
  do cliente, que é outro app.
- **Aceite de convite não estoura.** Username já em uso virava `IntegrityError` não tratado — 500,
  que de quebra distinguia "existe" de "livre" para quem não está autenticado. Agora é erro de
  campo.
- **Dependências.** `pip-audit` e `npm audit --omit=dev` rodaram limpos. As 17 dependências de
  frontend declaradas como `"latest"` foram fixadas nas versões do lockfile: o `npm ci` do CI já
  estava protegido, mas `npm install` local puxava versão arbitrária.
- **A tela decide pelo mesmo critério que a API.** `/auth/me/`, `/auth/login/`, o aceite de convite
  e `/users/` passam a devolver **`is_admin`**, vindo da propriedade `User.is_admin_role`
  (`role == ADMIN or is_superuser`) que já autoriza em 14 lugares no backend. O SPA **consome** o
  predicado; não o reconstrói como `is_superuser || role === "admin"`, que seria uma segunda
  expressão da mesma regra — o mesmo princípio que a ADR 0010 aplica a `visible_to`.

  O defeito que isto fecha nascia no primeiro comando de qualquer instalação: `createsuperuser` não
  pergunta papel, então o usuário fica com o default `delivery`, e o SPA — que filtrava só por
  `role` — escondia **Leads, Indicadores, Jornada, Equipe e Configurações** de quem a API já
  autorizava em tudo. Não havia conserto pela interface: `UserViewSet` é read-only e papel só se
  define em convite, então o runbook mandava rodar um `manage.py shell`. Eram **dez** pontos de
  decisão no SPA, não só o menu — o painel de agentes, o pipeline da Visão geral (que o backend
  mandava preenchido e a tela descartava), o CTA de Projetos, os vínculos de Documentos e o painel
  de equipe do projeto. Mudança **aditiva** de contrato: campo novo, `readOnly`, nenhum existente
  alterado.

## Fora deste recorte

Hardening de transporte (`SECURE_SSL_REDIRECT`, `SECURE_HSTS_SECONDS`, `SECURE_PROXY_SSL_HEADER`),
expiração de sessão, validadores de senha adicionais e `manage.py check --deploy` no CI dependem de
domínio e HTTPS resolvidos — vão com o item de infraestrutura do roadmap.

Verificado e **descartado** por não proceder: CSRF (o `SessionAuthentication` do DRF já força a
checagem, e `CSRF_TRUSTED_ORIGINS`/`SameSite`/`Secure` estão postos); os quatro endpoints públicos
(todos com `hmac.compare_digest`, honeypot no intake, token de booking assinado com validade e
HMAC sobre o corpo cru no webhook); CORS (restrito por regex só ao intake); XSS no frontend (sem
`dangerouslySetInnerHTML`, `innerHTML` ou `eval`); e injeção de header pelo nome do arquivo no
download.

## Aceite

Uma pessoa de Entrega que não é dona de nenhum projeto abre **Documentos** e não vê nada; o
seletor "Vincular a" só oferece "Projeto". Dona de um projeto — ou de uma tarefa dele — ela vê e
baixa os arquivos daquele projeto e só deles. Vendas e admin não perdem acesso a nada. Errar a
senha repetidas vezes no login passa a responder 429 em vez de aceitar tentativas indefinidamente.
Subir um `.html` é recusado com a lista do que é aceito. `curl` em `/media/...` responde 404.

## Regressão crítica

Entrega não lista, não abre por id e não baixa documento de oportunidade nem de projeto alheio, e
recebe 403 ao tentar criar qualquer um dos dois; ser dona de uma tarefa do projeto basta para
voltar a ver. Entrega não cria artefato ligado a oportunidade e recebe 404 ao tentar lê-lo ou
editá-lo por id. Vendas mantém acesso total aos documentos. Login, aceite de convite e snapshot do
portal respondem 429 no excesso, e o login legítimo continua passando dentro do limite; a API
autenticada tem teto próprio. Nenhuma rota serve `MEDIA_ROOT`. Nome de arquivo nunca chega ao
banco com caminho ou caractere de controle. Aceitar convite com username repetido é 400, não 500.
