# ADR 0016 — Autenticação com o Google sem chave de conta de serviço

- **Status:** aceita
- **Data:** 06/08/2026
- **Contexto:** FDD 024 (sondas e homologação), FDD 012 (calendário), FDD 013 (agendamento),
  FDD 003 (documentos)

## Contexto

O Drive e o Calendário nasceram autenticando por **chave de conta de serviço**: um JSON lido de
`GOOGLE_SERVICE_ACCOUNT_INFO` (inline) ou `GOOGLE_SERVICE_ACCOUNT_FILE` (arquivo montado). Nunca
houve ADR sobre essa escolha — ela veio junto com o primeiro código e ficou.

A rodada 3 da homologação (FDD 024) foi tentar apontar a credencial real e **não conseguiu criar a
chave**: a organização aplica a política

```
iam.managed.disableServiceAccountKeyCreation
```

que bloqueia a criação de chaves de conta de serviço. Não é preferência de quem opera — é política,
e é a recomendação do próprio Google, que chama chave de conta de serviço de risco de segurança e
pede uma alternativa "sempre que possível".

Isso reclassifica o problema. O desenho não era subótimo: era **inconstruível** nesta organização.
As duas únicas variáveis que o código sabia ler são exatamente o artefato proibido. É, quase com
certeza, por que esta integração nunca foi homologada — e o `docs/operacao.md` seguia prometendo um
caminho que ninguém podia tomar, que é a mesma classe de mentira que a FDD 024 existe para
consertar.

Um segundo fato pesa junto: conta de serviço **não convida participante** em evento sem delegação
em todo o domínio (`forbiddenForServiceAccounts`). O convite é o que faz o agendamento pelo site
valer alguma coisa — sem ele, o lead não recebe nada.

## Decisão

A credencial passa a ser montada em **um lugar só** (`apps/core/google_auth.py`), com dois modos, e
**nenhum deles é uma chave no ambiente**:

- **`adc`** (default) — Application Default Credentials. `google.auth.default()` resolve, nesta
  ordem: o arquivo apontado por `GOOGLE_APPLICATION_CREDENTIALS` — que pode ser uma configuração de
  **Workload Identity Federation**, sem chave —, as credenciais de `gcloud auth
  application-default login`, e o **metadata server**, que é como um pod no GKE ou um serviço no
  Cloud Run se autenticam sem ter segredo algum no ambiente. É o caminho de container/pod e também
  o de desenvolvimento local.
- **`oauth`** — credencial de **usuário**, por refresh token
  (`GOOGLE_OAUTH_CLIENT_ID`/`_SECRET`/`_REFRESH_TOKEN`). Existe para quando o portal precisa agir
  *como uma pessoa*, que é o que o convite em evento exige.

O caminho dedicado à chave de conta de serviço **sai**. Quem tiver uma chave e puder usá-la não
perde nada: `GOOGLE_APPLICATION_CREDENTIALS` aponta para ela e o ADC a lê. O que deixou de existir
é o tratamento especial para o único artefato que a política proíbe.

`google-auth` já traz ADC, external_account (WIF) e credencial OAuth de usuário — **não entra
dependência nova**.

## Consequências

- **A instalação mais segura passa a ser a default.** Em container, a credencial não existe como
  arquivo nem como variável: é emitida sob demanda e tem vida curta. Não há o que vazar em backup,
  log, imagem ou `docker inspect`.
- **`configured()` não tem o que cobrar no modo `adc`, e isso é correto.** Num pod com Workload
  Identity não existe variável de ambiente para conferir. Cobrar uma recusaria justamente a
  instalação mais segura. Quem responde "isto funciona?" nesse caso é a **sonda** do
  `check_integrations`, que pergunta ao provedor em vez de ao ambiente — a tese da FDD 024 aplicada
  ao próprio mecanismo de autenticação. No modo `oauth` há o que cobrar, e o trio é exigido.
- **Mudança incompatível de configuração.** `GOOGLE_SERVICE_ACCOUNT_INFO` e
  `GOOGLE_SERVICE_ACCOUNT_FILE` deixam de ser lidas. Como as duas flags nascem `false` e a
  integração nunca foi homologada, não há instalação afetada — mas a linha precisa estar dita.
- **O modo `oauth` amarra a integração a uma pessoa.** Os arquivos passam a pertencer a ela, e se
  ela sai ou revoga o acesso, a integração para. É o preço de poder convidar participante. Onde
  isso não for necessário, `adc` é preferível justamente por ser identidade institucional.
- **Armadilha operacional do OAuth:** enquanto o app estiver como "Testing" no Google Cloud, o
  refresh token **expira em 7 dias**. Precisa estar "In production". Vai no runbook.
- **A rodada 3 volta a ser possível**, agora sobre um mecanismo que a organização permite — e a
  homologação passa a exercitar o desenho que vai para produção, em vez de um que seria
  substituído.

## Alternativas consideradas

- **Pedir exceção à política.** Um admin pode desativar a restrição. Rejeitada: resolveria com
  processo um problema que o código tem — e recriaria a chave de vida longa que a política existe
  para evitar.
- **Delegação em todo o domínio, mantendo a conta de serviço.** Era o plano da rodada 3 e continua
  sendo a saída *sem código* para o convite em evento. Mas ela **também precisa de uma chave** para
  a impersonação clássica, então a política a bloqueia junto.
- **OAuth por usuário do portal** (cada pessoa conecta a sua conta). Rejeitada por ora: multiplica
  armazenamento de token, revogação e escopo por usuário, e nada no produto hoje pede que o arquivo
  pertença a quem subiu — o dono natural é a organização.
