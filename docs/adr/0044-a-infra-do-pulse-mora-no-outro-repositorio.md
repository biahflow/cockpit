# ADR 0044 — A infraestrutura do Pulse mora no repositório do outro produto

**Status:** aceito
**Data:** 25/08/2026
**Fase:** transversal — infraestrutura e esteira de entrega
**Completa:** ADR 0042 · **Contexto de marca:** ADR 0035 e ADR 0043
**Descoberto em:** [#32](https://github.com/biahflow/pulse/issues/32) · **Decidido em:** [#34](https://github.com/biahflow/pulse/issues/34)

## Contexto

A pergunta que abriu a issue era pequena: o produto virou **Pulse** (ADR 0035, ADR 0043) e os
recursos de HML continuam se chamando `cockpit-api`, `cockpit-web`, `cockpit-migrate`,
`cockpit-scheduler` e `cockpit-check` — nomes herdados do repositório, que a ADR 0030 rebatizou
de `portal` para `cockpit` e que só depois virou `pulse`. Renomear, ou registrar por escrito que
o prefixo é histórico?

Responder exigiu achar quem é dono desses recursos, e é aí que estava a coisa que valia registrar.

O cabeçalho de `.github/workflows/deploy-hml.yml` diz que o deploy de aplicação não roda
`terraform apply` porque "infraestrutura, rede, registros, segredos e identidades continuam no
repositório de infraestrutura compartilhado". A frase está certa sobre a fronteira e **não diz
qual repositório é**. Existe um chamado `biahflow/infra`, cuja descrição promete exatamente isso
— "Terraform: módulos, envs hml/prd, DNS, WIF e Cloud Run" —, e ele **não tem stack nenhum do
Pulse**: `envs/hml/servicos` declara só o `eliseu-hml`, `envs/prd/servicos` é scaffold comentado,
e "cockpit" aparece lá em duas linhas de comentário sobre o rename do repositório no GitHub.

A conclusão fácil, e errada, é que os recursos foram criados à mão. O que desmente é um label nos
cinco: `goog-terraform-provisioned: 'true'`, que só o provider Terraform escreve.

A configuração está em **`biahflow/portal-cliente`**, em
`infra/terraform/ambientes/hml-biahflow/servicos.tf`. Ou seja: **a infraestrutura do portal
operacional é declarada no repositório do portal do cliente.** E não é um resto esquecido — é um
desenho deliberado, em duas camadas, com módulos próprios (`modulos/fundacao`,
`servico-cloudrun`, `worker-pool`, `job`), `plan` automático em PR e `apply` só por
`workflow_dispatch` com uma flag explícita (`infra-hml.yml`). O `servicos.tf` é uma camada
portátil que descreve o serviço sem citar GCP, e cada linha não óbvia carrega o comentário do
motivo.

O guardrail de infraestrutura, portanto, **não está violado**. O que existe é outra coisa.

### Dois patrimônios Terraform no mesmo bucket

`gs://biahflow-hml-tfstate` guarda duas convenções que não se conhecem:

| Prefixo | Repositório | Governa |
| --- | --- | --- |
| `ambientes/hml` | `biahflow/portal-cliente` | a fundação de HML: rede, NAT, Artifact Registry, WIF, service accounts, segredos, buckets e a borda Cloudflare |
| `ambientes/hml-biahflow` | `biahflow/portal-cliente` | **os cinco recursos do Pulse** |
| `ambientes/hml-site` | `biahflow/site` | o site de marketing e a captação |
| `envs/**` | `biahflow/infra` | croquito, eliseu, DNS e WIF |

Os dois lados resolvem o mesmo problema com módulos diferentes (`servico-cloudrun` de um lado,
`cloud-run-service` do outro) e nomes de diretório diferentes (`ambientes/` e `envs/`). Nada
quebra por causa disso — os states são disjuntos. O que custa é achar: a frase "repositório de
infraestrutura compartilhado" tem hoje **dois referentes plausíveis**, e o que a descrição do
`biahflow/infra` promete é o que ele não entrega para este produto.

### O que o inventário mostrou sobre o rename

- O nome do serviço **não é superfície de usuário**. O host público é `app.biahflow.ai`, definido
  na fundação (`ambientes/hml/nomes.tf`) e servido por um Worker da Cloudflare.
- Dentro de `servicos.tf`, o nome **é** a chave do mapa, e `url_interna`, `DJANGO_ALLOWED_HOSTS`
  e `API_UPSTREAM` são derivados dela. Renomear a chave propaga sozinho.
- Mas a fundação crava o literal: `ambientes/hml/cloudflare.tf` monta a origem do Worker como
  `"cockpit-web-${número do projeto}.${região}.run.app"`. É **outro state**, e o comentário logo
  acima registra que esse acoplamento já quebrou uma vez — exatamente quando os serviços foram
  renomeados de `biahflow-*` para `cockpit-*`.
- Produção não existe: nenhuma variável `PROD_*` configurada, sem environments, `promote-prod`
  nunca rodou. E os nomes de lá não são literais no workflow: saem de `vars.PROD_API_SERVICE` e
  afins.

## Decisão

### 1. O deploy diz onde a infraestrutura dele mora, pelo nome

O cabeçalho de `deploy-hml.yml` passa a nomear o repositório e o diretório. A frase genérica
custou uma investigação inteira, e custaria de novo: quem procura infraestrutura do Pulse procura
no repositório do Pulse, depois no que se chama `infra`, e desiste antes de procurar no do outro
produto.

### 2. A infraestrutura do Pulse migra para `biahflow/infra`

A direção fica decidida: é lá que ela deve estar, porque é o repositório cuja razão de existir é
essa. A migração **não** acontece nesta ADR — ela tem trabalho e risco próprios, e três
condições que precisam ser resolvidas antes:

- **A fundação vem junto ou fica?** `ambientes/hml-biahflow` lê `ambientes/hml` por
  `terraform_remote_state`. Mover só o produto deixa a dependência atravessando repositórios;
  mover a fundação arrasta o portal do cliente e o site, que também a lêem.
- **Duas convenções viram uma.** `servico-cloudrun` e `cloud-run-service` não são o mesmo módulo,
  e a camada portátil do `servicos.tf` — que descreve o serviço sem citar GCP — é uma
  propriedade que a migração não pode perder para caber no formato do destino.
- **State se move sem downtime, e é onde o erro é caro.** É mudança de backend, não `destroy`;
  qualquer passo que recrie recurso em vez de mover entrada de state é defeito, não plano.

Até que isso esteja planejado, `biahflow/portal-cliente` continua sendo o dono, e é o que esta
ADR registra para quem for procurar.

### 3. O rename `cockpit-*` → `pulse-*` acontece agora, no repositório de hoje

Em um PR do `biahflow/portal-cliente`, tocando os **dois** stacks no mesmo lote, porque o
acoplamento entre eles é justamente o que já falhou uma vez:

- as chaves de `local.servicos_http`, `local.processos_longos` e `local.trabalhos` em
  `ambientes/hml-biahflow/servicos.tf` — e os derivados acompanham;
- o literal `origem_do_crm` em `ambientes/hml/cloudflare.tf`;
- os nomes de imagem em `deploy-hml.yml`, `promote-prod.yml` e
  `.github/scripts/release_evidence.py` deste repositório, com os fixtures junto.

É `destroy` mais `create` dos cinco recursos, com janela de indisponibilidade em HML. Os dois
`plan` vão publicados no PR, e a ordem entre eles é parte do plano, não detalhe de execução.

### 4. Produção nasce `pulse-*`

`envs/prd/servicos` — ou o que ocupar o lugar dele depois da migração — declara os recursos já
com o nome novo, e as `vars.PROD_*` são configuradas com ele. Produção nunca conhece o prefixo
histórico. Isso é de graça hoje e deixa de ser no dia do primeiro `promote-prod`.

### 5. `apply` continua sendo Human Gate

`infra-hml.yml` já implementa isso: `plan` automático em PR, `apply` só por `workflow_dispatch`
com a flag `aplicar`. Nada aqui autoriza `apply`, e renomear por console ou `gcloud` imperativo
continua proibido.

## Consequências

- A frase "repositório de infraestrutura compartilhado" deixa de existir sem referente. Quem lê o
  deploy passa a saber onde procurar, que é o defeito que esta ADR conserta primeiro.
- Fica registrada uma dívida com dono e direção — a migração para `biahflow/infra` — em vez de
  uma divergência que ninguém escreveu.
- O rename tem custo real e conhecido: indisponibilidade de HML e um acoplamento entre states com
  histórico de falha. Ele é feito por valer a coerência de nome, não por ser barato.
- Uma dúvida levantada durante a investigação está **respondida**:
  `google_cloud_run_v2_worker_pool` existe no provider e já está em uso — `cockpit-scheduler` está
  no state como worker pool. Não há exceção a declarar.
- A ADR 0030, que nomeia o cockpit como sistema primário e renomeia o repositório para ele,
  continua válida como registro histórico. Ela não é afetada.
- **`deploy-hml` verde não prova que alguém alcança o produto, e isso ficou medido em vez de
  suposto.** A sonda de fumaça deste workflow bate na URL `run.app` do serviço, que é a que o
  próprio deploy acabou de publicar. O host que o usuário digita é `app.biahflow.ai`, que passa
  pela borda Cloudflare — outro state, outro repositório. Em 25/08/2026 os dois discordavam: a
  borda apontava para `biahflow-web`, serviço que não existe desde 19/08, e seis dias de deploy
  verde não acusaram nada. A lacuna fica registrada aqui; fechá-la é escopo próprio, e esbarra no
  Cloudflare Access, que responde 302 antes de a origem ser exercida — foi ele que escondeu a
  falha de qualquer sonda anônima.

## Verificação

- `backend/tests/test_indice_de_adrs.py` — a entrada desta ADR no índice espelha o `#` do
  arquivo.
- Rename (no `biahflow/portal-cliente`): os `plan` dos dois stacks publicados no PR, e o
  `destroy`/`create` esperado **explicitamente conferido** contra os cinco recursos — nem um a
  mais. `apply` só com a flag e com humano.
- Depois do rename: `deploy-hml` verde ponta a ponta. Ele já confere por `assert_ref` que o
  digest implantado é o construído, e faz smoke na URL do serviço web.
- Migração para `biahflow/infra`, quando for planejada: `terraform state list` idêntico antes e
  depois, e `plan` limpo no destino. Recurso recriado é defeito.
