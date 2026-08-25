# ADR 0044 — Adotar antes de renomear: os recursos que nenhum Terraform declarava

**Status:** aceito
**Data:** 25/08/2026
**Fase:** transversal — infraestrutura e esteira de entrega
**Completa:** ADR 0042 · **Contexto de marca:** ADR 0035 e ADR 0043
**Descoberto em:** [#32](https://github.com/biahflow/pulse/issues/32) · **Decidido em:** [#34](https://github.com/biahflow/pulse/issues/34)

## Contexto

A pergunta que abriu a issue era pequena: o produto virou **Pulse** (ADR 0035, ADR 0043) e os
recursos de HML continuam se chamando `cockpit-api`, `cockpit-web`, `cockpit-migrate`,
`cockpit-scheduler` e `cockpit-check` — nomes herdados do repositório, que a ADR 0030 rebatizou
de `portal` para `cockpit` e que só depois virou `pulse`. Renomear, ou registrar por escrito que o
prefixo é histórico?

Nenhuma das duas respostas cabia, porque as duas pressupunham um Terraform que não existe.

O cabeçalho de `.github/workflows/deploy-hml.yml` diz, desde que foi escrito, que o deploy de
aplicação não roda `terraform apply` porque "infraestrutura, rede, registros, segredos e
identidades continuam no repositório de infraestrutura compartilhado". A frase está certa sobre
a fronteira e errada sobre o fato. O repositório existe — `biahflow/infra`, com `modules/`,
`envs/hml/` e `envs/prd/` —, mas **não há stack do Pulse nele**: `envs/hml/servicos` declara um
único módulo, o `eliseu-hml`; `envs/prd/servicos` é um scaffold inteiramente comentado; e a única
ocorrência de "cockpit" no repositório inteiro são duas linhas de comentário em
`envs/hml/wif/variables.tf`, que apenas narram o rename do repositório no GitHub.

Os cinco recursos foram criados à mão e não são governados por nada. Isso viola o guardrail de
infraestrutura — todo recurso que um provider Terraform sabe gerenciar é provisionado por
configuração versionada, com `plan` revisado — e viola **independentemente do nome**. A issue
achava que tinha encontrado uma pendência de nomenclatura; tinha encontrado uma pendência de
propriedade.

Dois fatos decidiram a ordem em que isso se resolve.

O primeiro é que **a configuração viva desses serviços não está escrita em lugar nenhum.**
`deploy-hml.yml` só executa `gcloud run services update --image`; nunca define variável de
ambiente. Logo `DJANGO_ALLOWED_HOSTS`, `CSRF_TRUSTED_ORIGINS` e `FRONTEND_ORIGIN` existem apenas
nos serviços vivos, postos à mão em algum momento que ninguém registrou. Renomear um serviço
Cloud Run não é editar texto: é `destroy` mais `create`, com URL nova. Fazer isso antes de a
configuração estar declarada seria destruir a única cópia dela.

O segundo é que **produção não existe.** Nenhuma das variáveis `PROD_*` está configurada no
repositório, não há environments e `promote-prod` nunca rodou. E, diferente de HML, os nomes de
produção não são literais no workflow: saem de `vars.PROD_API_SERVICE`, `vars.PROD_WEB_SERVICE` e
afins. Produção não precisa ser renomeada — precisa nascer com o nome certo, e isso é escolher o
valor de uma variável.

## Decisão

### 1. Adotar primeiro, renomear depois

O trabalho de nomenclatura fica **represado atrás da adoção**. Os cinco recursos de HML são
declarados em um stack novo do `biahflow/infra` e importados para o estado — com `plan` revisado
mostrando **zero destroy e zero replace** — antes que qualquer rename seja planejado.

A ordem não é preferência de processo. É a diferença entre um rename que o Terraform mostra como
`destroy`/`create` revisável, carregando a configuração declarada junto, e um rename que perde
`ALLOWED_HOSTS`, `CSRF_TRUSTED_ORIGINS` e `FRONTEND_ORIGIN` porque a única cópia deles estava no
recurso destruído.

### 2. Até lá, `cockpit-*` é prefixo histórico do Pulse

Os nomes ficam como estão, e o caráter histórico fica registrado no cabeçalho de
`deploy-hml.yml` — que é onde quem lê o deploy tropeça neles. Nome de recurso interno não é
superfície de usuário, e um deploy que funciona não é motivo para pressa.

O que **não** vale é a leitura de que manter o nome encerra o assunto. O assunto não é o nome.

### 3. A fronteira de propriedade com o CI não muda

Vale a mesma linha que o módulo `cloud-run-service` já implementa e que a ADR 0042 sustenta: o
Terraform é dono da **existência do recurso e da configuração estável** — região, ingress, rede,
escala, quem pode invocar, service account de runtime na criação. O CI da aplicação é dono da
**revisão e da imagem**, por digest. Adotar os recursos no Terraform não transfere o deploy para
o Terraform, e `deploy-hml.yml` continua sendo quem publica revisão.

### 4. Produção nasce `pulse-*`

Quando `envs/prd/servicos` deixar de ser scaffold, os recursos nascem com o nome novo, e as
variáveis `PROD_*` são configuradas já com ele. Produção nunca conhece o prefixo histórico.

Isso é de graça hoje e deixa de ser no dia em que o primeiro `promote-prod` rodar.

### 5. `apply` continua sendo Human Gate

Nada disto autoriza `apply`. O caminho é o do próprio `biahflow/infra`: PR, `plan` publicado no
resumo do job, aprovação humana explícita, e só então `apply`. Renomear por console ou por
`gcloud` imperativo continua proibido.

## Consequências

- A issue de nomenclatura passa a ter uma dependência real em outro repositório, e deixa de ser
  fechável só com documentação. É mais trabalho do que a pergunta original sugeria, e é o
  trabalho certo.
- Enquanto a adoção não acontece, os cinco recursos seguem sem `plan` que os proteja: qualquer
  mudança neles continua sendo mudança à mão, e continua invisível para revisão.
- O inventário da configuração viva (`gcloud run services describe` e equivalentes) vira
  pré-requisito da adoção, porque é a única fonte que existe. Ele é leitura, mas é leitura que
  precisa acontecer antes de qualquer `destroy`.
- Há uma incógnita técnica declarada: `cockpit-scheduler` é um worker pool, publicado hoje por
  `gcloud beta run worker-pools`. Se `google_cloud_run_v2_worker_pool` não existir no provider
  fixado do `biahflow/infra` (`hashicorp/google`, `~> 6.0`), a adoção do worker pool ou exige
  declarar `google-beta` — coisa que nenhum stack de lá faz hoje — ou fica **declaradamente**
  fora, escrita como exceção. Improvisar aqui é como os recursos chegaram ao estado atual.
- A ADR 0030, que nomeia o cockpit como sistema primário e renomeia o repositório para ele,
  continua válida como registro histórico. Ela não é afetada por esta decisão.

## Verificação

- `backend/tests/test_indice_de_adrs.py` — a entrada desta ADR no índice espelha o `#` do
  arquivo.
- Adoção (no `biahflow/infra`): `terraform plan` do stack novo publicado no resumo do PR, com
  **zero destroy e zero replace**. Qualquer `-/+` significa que a declaração divergiu do recurso
  vivo, e é defeito a corrigir antes de aplicar — não um plano a aprovar.
- Rename (depois): `deploy-hml` verde ponta a ponta. Ele já confere, por `assert_ref`, que o
  digest implantado é o que foi construído, e já faz smoke na URL do serviço web — que é
  exatamente a URL que o rename muda.
