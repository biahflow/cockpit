# ADR 0028 — O documento que não sobrevivia à revisão

**Status:** aceito
**Data:** 12/08/2026
**Fase:** transversal — armazenamento de documento
**Fecha:** a pendência de `docs/architecture.md` ("migrar os blobs para S3/MinIO — ou remover o
serviço do compose — continua pendente e merece um ADR quando for decidido")
**Relacionadas:** ADR 0002 (documento é recurso privado), ADR 0016 (auth do Google sem chave),
ADR 0017 (armazenamento e retenção do portal do cliente), FDD 017, ADR 0050 do portal do cliente

## Contexto

`STORAGES["default"]` era `FileSystemStorage` e `MEDIA_ROOT` um caminho no contêiner. No compose
isso é correto e durável: há um volume nomeado, e o sidecar de backup leva a mídia junto do banco —
a razão está escrita lá, *"sem eles, restaurar o banco devolve um portal cheio de registros
apontando para arquivos que não existem mais"*.

**Fora do compose, não há volume.** No Cloud Run a `biahflow-api` sobe com `min = 1` e `max = 4`, e
o sistema de arquivos é da instância: o arquivo enviado fica onde foi recebido, invisível para as
outras réplicas, e desaparece na revisão seguinte. Não é o caso raro — é o caminho normal, e todo
deploy o exerce.

O que se perde não é um anexo qualquer. `Document` é o que segue para o Google Drive, para o
fornecedor de assinatura eletrônica e para o snapshot do portal do cliente; é o alvo do e-sign e o
objeto que a retenção da LGPD promete apagar. Um documento que some sozinho quebra as três
promessas ao mesmo tempo, e **em silêncio** — nenhum log, nenhuma métrica, e a linha continua no
banco apontando para um arquivo que não existe.

Havia ainda uma decisão pendente e registrada: o compose sobe um MinIO desde sempre, com
`MINIO_ENDPOINT` entregue à API, e o `settings.py` **nunca leu essa variável**. Serviço
provisionado e não conectado, que o `architecture.md` marcava como dívida esperando um ADR.

## Decisão

### O bucket entra por ausência de variável, não por flag de produto

`GCS_MEDIA_BUCKET` preenchida troca o `STORAGES["default"]` para `GoogleCloudStorage`; vazia,
mantém o sistema de arquivos. É a forma de `DATABASE_URL` e `REDIS_URL`, e não a de `AI_ENABLED`.

**Para onde o arquivo vai não é um interruptor.** Desligar deixaria órfão todo objeto já gravado no
bucket, e ligar não traria de volta o que está no disco — as duas direções perdem dado. Por isso a
flag `storage` existe na tela mas nasce `toggleable=False`, e a tela diz o motivo com a frase que
já existia para esse caso: *"Controlada por variáveis de ambiente"*. É a primeira flag a usar
aquele ramo.

### Nenhuma linha do caminho do arquivo muda, e isso foi medido antes de decidir

O `FileField` continua sem `storage=` explícito; não há migração. Upload
(`serializers.py`: `document.file = uploaded_file`), download (`views.py`: `document.file.open("rb")`
dentro de um `FileResponse`), e-sign (`esign.py`) e expurgo (`retention.py`:
`document.file.delete()`) já eram agnósticos de storage.

A única quebra dura do repositório inteiro era **um teste**: `test_retention.py` guardava
`doc.file.path`, que só existe em storage de sistema de arquivos e levanta `NotImplementedError`
num bucket. Virou `storage.exists(nome)`, que exprime a mesma pergunta nos dois.

### O download continua streaming pela rota autenticada — e essa é a decisão que **não** foi tomada

A alternativa barata seria `redirect()` para uma URL assinada de vida curta: tira o byte do
processo e o worker do caminho. É o que a ADR 0017 do portal do cliente escolheu para o produto de
lá, e ali está certo.

**Aqui não**, e a razão é que o modelo inteiro da ADR 0002 e da FDD 017 se apoia numa premissa: o
**único** caminho para o arquivo é a rota que passa por `check_object_permissions`. Uma URL
assinada é um bearer token — expira, mas enquanto vale não conhece RBAC. Foi exatamente para matar
o segundo caminho que a FDD 017 removeu o `/media/` servido sob `DEBUG`, e reintroduzi-lo por outra
porta seria desfazer aquilo com outro nome.

Daí as duas opções do backend, que existem para preservar a regra e não por afinação:
`querystring_auth = False` (senão `file.url` devolve URL assinada) e `default_acl = None` (o bucket
tem acesso uniforme, e mandar ACL por objeto faz o GCS recusar a escrita inteira, com uma mensagem
sobre permissão que não fala de configuração).

O preço está declarado: cada download atravessa a rede duas vezes e segura um worker do gunicorn
pela duração. Se isso doer, a saída é medir e voltar aqui — não é mudar em silêncio.

### A credencial é o ADC, e nunca uma chave de conta de serviço

`google-cloud-storage` resolve por Application Default Credentials: no Cloud Run, o metadata server
entrega a `hml-execucao`, que tem `roles/storage.objectAdmin` no bucket. É a regra da ADR 0016, e
deliberadamente **não** se usa `apps/core/google_auth.py`: aquele módulo serve Drive e Calendar, e
em HML roda em modo `oauth` com um trio de credenciais que ali é de marcação.

### A sonda escreve, lê e apaga

Ao contrário da de e-mail — que só abre a conexão, porque sonda que manda mensagem vira spam
diário —, aqui o ciclo completo é barato e é o único que prova o que importa: um `objectAdmin` sem
`create` ou sem `delete` deixa o upload passar e o **expurgo de retenção falhar**, e o expurgo falha
calado.

## Consequências

- **O MinIO do compose continua provisionado e não conectado**, e agora com uma resposta: o
  caminho escolhido é o SDK do GCS, não a API S3. Remover o serviço do `docker-compose.yml` é
  trabalho separado e fica nomeado aqui; o `architecture.md` deixa de dizer que a decisão está
  pendente.
- **A suíte é fixada em `FileSystemStorage` no `conftest.py`, e isso é obrigatório.** Sem essa
  guarda, uma variável de ambiente vazada faria dezenas de testes gravarem objeto de verdade — os
  que sobem documento, e os nove que fazem `override_settings(MEDIA_ROOT=...)`, que com storage
  remoto viram no-op **silencioso**: continuam verdes afirmando sobre um diretório que ninguém usa.
- **O backup de mídia não muda, e o motivo é que ele não precisa.** No compose `GCS_MEDIA_BUCKET`
  fica vazia, o storage continua o disco, e `backup.sh`, `restore.sh` e o `backup-drill.sh` de todo
  PR seguem exercitando exatamente o que exercitavam. **Fica aberto, e é a pendência mais
  importante desta ADR:** um ambiente que use o bucket **não tem backup de mídia**. O `tar` de um
  diretório vazio passa, o carimbo grava `media_bytes` de 45 bytes e o alerta de idade continua
  verde sobre nada — o modo de falha que a ADR 0013 chamou de "guarda que morre muda", agora do
  lado dos dados. Enquanto isso não for resolvido, o que protege o objeto é o versionamento do
  bucket, que é proteção contra remoção acidental e não contra perda do projeto.
- **Não há comando de migração dos arquivos existentes**, e em HML isso é indiferente porque não
  havia arquivo durável para migrar. Num host com volume, mudar a variável **não** move nada: os
  documentos antigos ficam no disco e param de ser encontrados. Quem fizer essa troca precisa de um
  `gcloud storage rsync` antes — os prefixos batem (`documents/%Y/%m/`).
- **A ameaça equivalente muda de nome.** `test_media_is_not_publicly_served.py` continua valendo e
  continua sendo sobre a rota; o que passa a existir ao lado é "o bucket está público?", e a
  resposta mora no Terraform do portal do cliente (`public_access_prevention = "enforced"`), onde
  nenhum teste deste repositório olha.
