# ADR 0066 — A /api/v2/ nasce por versão no caminho, e um mapa só governa o alias

**Status:** aceita
**Data:** 2026-09-04
**Depende de:** ADR 0052 (o renome de classe vem antes da Fase 6) · ADR 0049 (a ontologia entra
pela linguagem) · ADR 0055 (a medição sai do ativo) · `docs/ontology/aliases.md` §2, §2c e §2d
**Implementada por:** issue #122, fatia 1

## Contexto

`docs/ontology/aliases.md` desfaz "renome" em três coisas com prazos distintos: o nome da
**classe** morreu na issue #67, o nome da **tabela** na Fase 6 (migrações `0068`–`0072`), e a
**rota** com a **chave de payload** morrem na `/api/v2/`. A Fase 6 fechou, e o próprio documento
diz que a v2 "pode nascer" — o que torna esta a primeira fatia em que a dívida de rota e de chave
tem para onde ir. Alias sem morte não é compatibilidade: é o nome novo virando sinônimo permanente
do antigo.

A v2 não é produto novo. São os mesmos viewsets e os mesmos serializers sob outro prefixo, sem as
rotas legadas (`/clients/`, `/opportunities/`, `/processos/`, `/processo-etapas/`) e sem as chaves
legadas (`client`, `status`, `opportunity`, `gate_outcome`, `ai_opportunity`, `client_consent`,
`kpi_baseline`/`kpi_current`, `processo`). A regra 2 do `aliases.md` continua valendo em cima disso:
**a `/api/v1/` não quebra** — ela responde como sempre respondeu, até um sunset que ninguém decidiu.

Quatro perguntas precisavam de resposta antes de qualquer linha: como o servidor sabe qual versão
está falando; quem decide o que some da v2; o que acontece quando alguém manda a chave antiga para
ela; e o que o contrato publicado diz enquanto as duas versões dividem os mesmos componentes.

## Decisão

### 1. A versão sai do prefixo do caminho, por classe própria

`apps/core/versioning.py` declara `VersaoPeloCaminho`, um `BaseVersioning` de um método:
`request.path.startswith("/api/v2/")`. Ela entra como `DEFAULT_VERSIONING_CLASS` e não recebe
`ALLOWED_VERSIONS` nem `DEFAULT_VERSION` — tudo que não é `/api/v2/` já é `v1` por construção.

As duas classes prontas do DRF foram consideradas e recusadas, cada uma por um custo medido:

- **`URLPathVersioning`** exige a versão como **kwarg de toda rota** (`/api/<version>/…`), e o
  `reverse()` dela reinjeta esse kwarg em toda reversão feita pelo `rest_framework.reverse`. Adotá-la
  reescreveria as 57 rotas do router e quebraria a raiz da API, que reverte cada lista por nome.
- **`NamespaceVersioning`** resolve pelo **namespace** do resolver, o que renomeia o alvo de todo
  `reverse("client-detail")` do repositório — exatamente os nomes que a issue #67 fixou explícitos
  em `urls.py` para não quebrarem no renome de classe. Trocar o motivo da quebra não é evitá-la.

O prefixo já **é** a versão; lê-lo do caminho é o mecanismo inteiro e não toca em nome de rota
nenhum. O preço é declarado: o drf-spectacular só reconhece as três classes dele
(`plumbing.is_versioning_supported`) e emite **um** aviso na geração do esquema dizendo que a view
será tratada como não versionada — que é precisamente o comportamento desejado enquanto a v2 fica
fora do contrato (decisão 5).

### 2. Um mapa só — `ALIASES_DEPRECIADOS` — com três consumidores

O mapa componente → propriedades-alias de `apps/core/openapi_aliases.py` já marcava
`deprecated: true` no `openapi.yaml` desde a issue #67. Ele passa a governar também a **remoção**
dessas chaves na resposta da v2, lido por `serializers.AliasesDaV1Mixin`. A terceira consumidora é
a recusa de escrita, que lê `ALIASES_DE_ENTRADA` porque ali é preciso saber também o nome canônico
de cada chave.

A alternativa — cada serializer declarar a lista do que some — foi recusada pelo motivo de sempre
neste repositório: duas listas do mesmo fato divergem, e a divergência aqui não deixa nada
vermelho. O contrato prometeria uma ausência que a resposta não cumpre. `openapi_aliases.py` já
explica por que o mapa é escrito à mão e não inferido de `source=`; o que esta ADR acrescenta é
que ele deixou de **anunciar** a depreciação para também **executá-la**.

O mapa ganhou a entrada que faltava: `DigitalEmployee: ("kpi_baseline", "kpi_current")`. A
docstring daquele serializer prometia a depreciação no esquema desde a ADR 0055 e o mapa não a
cumpria — entrada em falta, não alias novo.

`backend/tests/test_aliases_da_v2.py` itera o mapa e reprova componente sem serializer que o
execute. É a guarda que impede o mapa e a adoção de divergirem.

### 3. Chave legada na v2 é **400 dizendo o nome canônico**, nunca silêncio

Vale para o corpo (`A chave 'client' não existe na /api/v2/; use 'account'.`) e para a query string
(`O parâmetro '?client=' não existe na /api/v2/; use '?account='.`). As duas frases moram em
`versioning.py`, num lugar só, porque quem recusa o corpo é o serializer e quem recusa o parâmetro
é o viewset.

Ignorar é o **default** do DRF para chave desconhecida, e é ele que esta decisão recusa: um `POST`
com `client` na v2 responderia 201 sem ter gravado o vínculo, e um `GET ?client=3` devolveria a
lista inteira com cara de lista filtrada. Nos dois casos o chamador lê sucesso onde não houve
nada — o modo de falha mudo. O mapa sabe responder o nome certo de graça, então recusar custa uma
linha e entrega a instrução junto do erro.

400 e não 409: é o **pedido** que está errado, não o estado (`exceptions.InvalidInput`, a mesma
distinção de `journey.apply_gate`).

### 4. Os nomes de URL da v2 levam o prefixo `v2-`, todos

O router da v2 registra cada rota com `basename=f"v2-{basename}"`, e as rotas fora do router
recebem `name="v2-…"` pela mesma razão — inclusive a raiz (`v2-api-root`). Sem o prefixo, os nomes
das duas versões colidiriam e `reverse("client-detail")` devolveria o alvo da última incluída: a
`/api/v1/` quebrando sem ninguém ter tocado nela.

**A tabela das rotas é o `registry` do router da v1, não uma segunda lista.** `SimpleRouter.registry`
já é `(prefixo, viewset, basename)` na ordem de registro; a v2 é uma transformação dele com um
dicionário de **quatro** renomes de prefixo. Uma lista paralela com as 57 rotas repetidas
divergiria da primeira no dia em que alguém registrasse a 58ª só de um lado, e as duas versões
continuariam respondendo — sem nada vermelho. Derivar preserva de graça a ordem que
`cobranca/suspensoes` exige e deixa a `/api/v1/` byte a byte igual à de antes, porque nenhuma linha
dela é reescrita. Como efeito lateral desejável, as duas dívidas de rota que
`docs/ontology/legacy-allowlist.txt` declara continuam onde a guarda do vocabulário as vê: numa
tabela de dados, as strings `"clients"` e `"opportunities"` sairiam do alcance de
`test_vocabulario.py` e a allowlist teria de perder duas linhas sem que a dívida tivesse sido paga.

### 5. A v2 fica **fora** do `openapi.yaml` até a fatia 3

Um `PREPROCESSING_HOOKS` (`openapi_aliases.excluir_a_v2_do_contrato`) filtra todo caminho
`/api/v2/` antes da montagem do esquema.

Nesta fatia as duas versões compartilham **componente**, e o componente ainda declara as
chaves-alias. Publicar a v2 agora emitiria ~240 caminhos novos apontando para componentes que
dizem que `GET /api/v2/accounts/` devolve `status` — que é exatamente o que a v2 não faz.
`deprecated: true` não é `ausente`, e uma mentira publicada é pior que o silêncio de não descrever.
O contrato da v2 nasce quando a forma dele for verdadeira: na fatia 3, como artefato próprio
(`openapi-v2.yaml`), depois de as chaves terem morrido de fato.

Filtrar **antes** da montagem, e não depois, tem uma segunda razão: o drf-spectacular estima o
prefixo comum a partir dos caminhos, e com a v2 na lista ele cairia de `/api/v1` para `/api`,
mudando todo `operationId` do arquivo commitado.

## Consequências

- A `/api/v2/` responde com as rotas canônicas; as quatro legadas são 404 nela, e as canônicas
  continuam 404 na v1. A `/api/v1/` não mudou: as seis regressões `*_sobrevive_na_v1.py` passam
  sem edição, e é essa a prova.
- `AliasDeEntradaMixin` virou `AliasesDaV1Mixin`: ele deixou de fazer só a normalização de entrada
  e passa a responder pelas três metades do alias na travessia de versão. Seis serializers que só
  tinham alias de leitura (`ProjectPhase`, `PhaseEvent`, `Case`, `DigitalEmployee`, `Lead`,
  `CobrancaContato`) passaram a herdá-lo — sem `ALIASES_DE_ENTRADA`, porque neles não há escrita
  pela chave antiga.
- O `openapi.yaml` regenerado difere em quatro linhas — as duas marcas novas do `DigitalEmployee`,
  no componente e no `Patched`. Nenhum caminho novo.
- A geração do esquema passa a imprimir um aviso a mais (a classe de versão não reconhecida),
  emitido uma única vez pela deduplicação do drf-spectacular. O CI não usa `--fail-on-warn`.
- **Continua vivo na v2 desta fatia**, e morre na fatia 3: os aliases de corpo de `@action`
  (`signer_email` em `request-signature`, `outcome` em `apply-gate`), o dicionário cru de
  `GET /cobranca/painel/` e a chave `processos` da action de IA. Nada disso passa por serializer
  com `ALIASES_DE_ENTRADA`, então o mecanismo desta fatia não os alcança — e alcançá-los pela
  metade seria pior que declarar a lacuna.
- A SPA continua na `/api/v1/` (`baseUrl`), e é a fatia 4 que a atravessa. Até lá, a v2 não tem
  consumidor interno — o que é dito aqui de propósito: a fatia 4 é a prova de que o contrato novo
  é completo.

## Alternativas consideradas

**`URLPathVersioning` e `NamespaceVersioning`** — recusadas na decisão 1, cada uma por reescrever
algo que a issue #67 acabou de fixar (as rotas, num caso; os nomes de URL, no outro).

**Um app Django separado para a v2**, com serializers próprios sem as chaves legadas. Dobraria
1.200 linhas de serializer para expressar uma diferença de dezoito chaves, e a divergência entre as
duas cópias seria questão de semanas — o mesmo defeito de ter duas listas do que some, em escala
maior.

**Deixar a v2 ignorar a chave legada em silêncio**, como o DRF faz com chave desconhecida.
Recusada na decisão 3: é o modo de falha mudo, e o chamador não tem como descobrir que a escrita
não aconteceu.

**Publicar a v2 no mesmo `openapi.yaml`**, marcando as chaves como `deprecated`. Recusada na
decisão 5: `deprecated` descreve o que ainda sai, e na v2 elas não saem.

**Uma lista de dados paralela para as 57 rotas das duas versões.** Recusada na decisão 4: derivar
do `registry` entrega a mesma tabela única sem reescrever a v1 e sem tirar as duas dívidas de rota
do alcance da guarda de vocabulário.

## Emenda (issue #122, fatia 3a — 04/09/2026) — os quatro pontos que faltavam, e a lacuna do read-only

A decisão 2 desta ADR já declarava que os aliases de corpo de `@action` (`signer_email`,
`outcome`), o dicionário cru do painel de cobrança e a chave `processos` da action de IA não
passavam por `serializers.AliasesDaV1Mixin` — nada com `source=` para o mapa ler, então o mecanismo
central não os alcançava. A fatia 3a fecha os quatro à mão, cada um no seu lugar:

- `signer_email` (`views._signers_do_pedido`) e `outcome` (`ProjectViewSet.apply_gate`) passam a
  recusar a chave legada com o mesmo `InvalidInput` + `frase_da_chave_removida` da decisão 3, só
  que chamado da view em vez do serializer — `_signers_do_pedido` passou a receber a versão do
  chamador para isso.
- `cobranca.painel()` passou a emitir **os dois pares** (`account`/`account_name` canônicos,
  `client`/`client_name` legados) em cada linha — o mesmo comportamento de todo alias de leitura da
  v1 — e a view (`CobrancaViewSet.painel`) remove os dois legados quando `versao_de(request) == V2`.
  O helper (`_painel_sem_chaves_legadas`) é local porque o dict é cru: não há componente de schema
  para `ALIASES_DEPRECIADOS` indexar.
- A chave da action de IA (`MeetingViewSet.estruturar`) **troca** por versão em vez de conviver —
  `processos` na v1, `processes` na v2 — porque duplicar a lista inteira pagaria o corpo da resposta
  duas vezes; é a única das quatro em que a v1 e a v2 nunca compartilham a chave.

**A lacuna que a decisão 3 não previa**: ela recusa a chave legada só para `ALIASES_DE_ENTRADA`, o
mapa dos aliases que também precisam de **tradução** na v1. As chaves só-de-leitura de
`ALIASES_DEPRECIADOS` — `client` em `Project`, `kpi_baseline`/`kpi_current` em `DigitalEmployee`,
etc. — nunca precisaram de tradução, então não tinham `ALIASES_DE_ENTRADA`, e mandá-las no corpo da
v2 caía no campo `read_only` do DRF: aceito e ignorado, o mesmo silêncio que a decisão 3 recusou
para as outras. `AliasesDaV1Mixin.to_internal_value` passou a recusar também as chaves de
`ALIASES_DEPRECIADOS[componente]` presentes no corpo, na v2. O nome canônico de cada uma (para a
frase da recusa) vem de um mapa novo, `openapi_aliases.CANONICO_DA_CHAVE` — `None` para o par do
§2d, cuja escrita já havia parado na `/api/v1/` (ADR 0055): a frase delas
(`frase_da_chave_sem_sucessora`) aponta para `/kpis/` e `/measurements/`, porque não há campo
canônico de escrita para apontar.

A recusa continua por **componente**, nunca por nome global de chave — é a mesma leitura de
`ALIASES_DEPRECIADOS` que já valia para `to_representation`. `status` continua um campo real e
gravável em `Invoice` e `Engagement`, que não estão no mapa; só os componentes que
`ALIASES_DEPRECIADOS` lista para `status` (`Account`) recusam a chave na v2.

`backend/tests/test_aliases_da_v2.py` ganhou a guarda simétrica à do mapa de depreciação: todo
valor não nulo de `CANONICO_DA_CHAVE` cobre a união das chaves de `ALIASES_DEPRECIADOS`, para uma
chave nova não nascer recusada sem frase.

## Emenda (issue #122, fatia 3b — 04/09/2026) — o contrato nasceu, e o mecanismo é o alvo

`backend/openapi-v2.yaml` passa a existir ao lado do `openapi.yaml`: o contrato da `/api/v2/`, com
só os caminhos `/api/v2/…` e com componentes **sem** as chaves-alias — a promessa da decisão 5
("a v2 entra no contrato quando a forma dele for verdadeira"), cumprida agora que as chaves morrem
de fato desde a fatia 3a.

O mecanismo é uma variável de ambiente, `OPENAPI_ALVO` (`v1`, o default, ou `v2`), e não
introspecção do `generator`: os hooks do drf-spectacular recebem os endpoints já enumerados ou o
esquema já montado, nunca o urlconf que os produziu, e nada nesses dois formatos permite inferir
sozinho qual geração está em curso. `apps.core.openapi_aliases.alvo_da_geracao()` lê essa variável,
e os três hooks passam a obedecê-la:

- `excluir_a_v2_do_contrato` (o `PREPROCESSING_HOOKS` da decisão 5) vira **no-op** no alvo v2 — o
  urlconf dedicado à geração (`config.urls_v2_schema`, mínimo: só inclui `apps.core.urls_v2`) já
  enumera unicamente a árvore da v2, e filtrá-la ali de novo esvaziaria a geração inteira.
- `marcar_aliases_depreciados` (a decisão 2 desta ADR) continua marcando `deprecated: true` no
  alvo v1 e vira no-op no v2.
- `remover_aliases_do_contrato`, hook novo, é o espelho exato: no-op no v1, e no v2 apaga cada
  propriedade-alias de `properties` **e** de `required` quando presente — deixar `required`
  apontando para uma propriedade removida reprova o `--validate` do spectacular tão bem quanto
  reprovaria um cliente gerado a partir do contrato.

Os dois comandos de geração, lado a lado:

```bash
uv run python manage.py spectacular --file openapi.yaml --validate
OPENAPI_ALVO=v2 uv run python manage.py spectacular --urlconf config.urls_v2_schema \
  --file openapi-v2.yaml --validate
```

`SPECTACULAR_SETTINGS["VERSION"]` segue o mesmo `OPENAPI_ALVO`: `"2.0.0"` no alvo v2, `"1.0.0"`
no v1 — `TITLE` não muda, porque a v2 não é produto novo (decisão da ADR). Nenhum serializer, view
ou rota mudou nesta fatia: o `openapi.yaml` da v1 tem diff vazio, e é o próprio CI
(`.github/workflows/quality.yml`) que passa a provar isso a cada geração — `git diff --exit-code`
sobre os dois arquivos, na sequência dos dois comandos acima.

## Emenda (issue #122, fatia 4a — 04/09/2026) — o que o contrato verdadeiro deixou à vista

Ler o `openapi-v2.yaml` da fatia 3b foi o que mostrou o limite do mecanismo: o contrato só é
verdadeiro sobre o que o mapa conhece, e havia dezesseis propriedades com «client» que **nunca
tinham entrado nele** — `client_name` em onze componentes, a chave `clients` que envolve a resposta
de `GET /accounts/overview/`, o par `client`/`client_name` do componente inline do painel de
cobrança, e `client_vertical`/`client_vertical_name` no projeto.

Elas escaparam da issue #67 por uma razão só, e é ela que dá o nome à decisão desta fatia: **nenhuma
era renome de campo.** `client_name` sempre foi `source="account.name"`; `client_vertical` sempre
atravessou `engagement.account.vertical`. A #67 renomeou classes e colunas, e projeção não tem
coluna — então o renome passou ao lado, e o nome errado ficou onde mais dura, na chave de payload.
Decisão do mantenedor em 04/09/2026: as dezesseis entram no escopo da #122 agora, pelo mecanismo
que já existe — canônica aditiva na v1, legada ausente na v2.

### 6. O mapa do esquema é a união de dois, e o segundo existe para a guarda continuar valendo

`ALIASES_DEPRECIADOS` sempre teve uma guarda que é o que impede o contrato de mentir: todo
componente listado precisa de um `<Componente>Serializer` que herde `AliasesDaV1Mixin` e execute a
remoção. Dois dos componentes desta fatia — `CobrancaPainelLinha` e `DeliveryTimelineOverview` —
são `inline_serializer` de `@extend_schema` sobre um dicionário cru, e não têm serializer nenhum:
quem remove a chave na v2 é a view (`views._sem_chaves_legadas`, o antigo
`_painel_sem_chaves_legadas`, generalizado ao ganhar o segundo chamador).

Pô-los no mesmo dicionário exigiria afrouxar a guarda, e afrouxá-la desligaria exatamente o defeito
que ela pega — a entrada nova que anuncia uma depreciação que ninguém executa. Por isso são dois
mapas com nomes que dizem a diferença (`ALIASES_DEPRECIADOS` e
`ALIASES_DEPRECIADOS_DE_DICT_CRU`), cada um com a sua guarda, e uma união
(`ALIASES_DEPRECIADOS_NO_ESQUEMA`) que é a **única** coisa que os hooks do drf-spectacular leem —
porque para quem lê o contrato a origem da propriedade é indiferente. Não são duas listas do mesmo
fato: são dois fatos (quem executa a remoção) com uma consequência comum (o que sai do esquema).

### 7. A chave que envolve a lista **troca**, e o esquema troca junto

`GET /accounts/overview/` respondia `{"clients": [...]}`. Aqui não vale a convivência do resto do
payload legado: a chave envolve o grid inteiro, e emitir as duas pagaria o corpo da resposta duas
vezes. É o caso que a fatia 3a já tinha resolvido uma vez (`processos`/`processes` na action de IA),
e o precedente se aplica igual — `clients` na v1, `accounts` na v2.

O que a fatia 3a não precisou enfrentar é o **componente**: aquela action não tem `@extend_schema`,
então não havia esquema a acertar. Esta tem, e um componente que dissesse `clients` numa resposta
que só tem `accounts` seria a mesma mentira publicada que a decisão 5 recusa. `chave_da_geracao`
(em `openapi_aliases.py`, ao lado de `alvo_da_geracao`) é o par do `versao_de(request)` da view: a
view escolhe a chave da resposta pela versão da requisição, o `@extend_schema` escolhe a do esquema
pelo alvo da geração.

### Consequências

- O `openapi.yaml` da v1 cresce e não perde nada: dezesseis propriedades canônicas novas e as
  marcas `deprecated` nas legadas correspondentes. As sete regressões de alias existentes passam
  sem edição, e a nova (`test_o_alias_de_nome_de_conta_sobrevive_na_v1.py`) é o que segura as
  chaves desta fatia — pelo motivo de sempre, agravado aqui: sem coluna nem `ALIASES_DE_ENTRADA`,
  não há nada além dela apontando para essas linhas de dentro do repositório.
- O `openapi-v2.yaml` deixa de ter qualquer propriedade com «client», e o critério passou a ser
  medido no artefato (`test_nenhuma_chave_client_sobra_na_v2`) em vez de no mapa — um teste que
  itera o mapa não teria pegado nenhuma das dezesseis, que é como elas duraram até aqui. A única
  tolerada é `recebido_do_cliente`, declarada em `docs/ontology/aliases.md` e com teste que a
  remove da allowlist quando a fatia 5 a traduzir.
- **Não houve migração.** O plano previa um `RenameField` de `Project.client_vertical`, e esse campo
  nunca existiu: o campo do modelo é `Account.vertical` (migração `0030`), e as duas chaves são
  projeção sobre ele. Fica registrado porque "renomear a coluna" e "renomear a chave" são coisas
  distintas desde a ADR 0052, e este é o caso em que só a segunda tinha dívida.
- Continua fora desta fatia, e declarado: `client_id` e `status` dentro de **cada linha** de
  `/accounts/overview/`. São dict cru sem descrição no esquema (`ListField` sem item tipado), então
  não aparecem em contrato nenhum e o critério de aceite desta fatia não os alcança — a dívida é de
  resposta, não de contrato, e paga-se junto da fatia que atravessar a SPA.

## Emenda (issue #122, fatia 4c — 04/09/2026) — a lacuna declarada foi paga

A emenda da fatia 4a registrou `client_id`/`status` de cada linha de `/accounts/overview/` (lista e
detalhe) como fora daquela fatia — dict cru sem item tipado no esquema, dívida de resposta e não de
contrato — e adiou o pagamento para a fatia que atravessasse a SPA. A 4b atravessou; esta fatia paga.

`build_account_overview` ganhou `account_id` ao lado de `client_id` (`lifecycle_status` já saía ao
lado de `status`), e as duas legadas somem na `/api/v2/` pelo mesmo `views._sem_chaves_legadas` que
já tirava `client_name` da visão compacta da entrega — o detalhe (uma linha só) envolve e
desembrulha a lista em vez de duplicar a lógica de remoção. A SPA (`AccountsPage.tsx`, `types.ts`)
passou a ler `account_id`. Nenhum componente do esquema muda: `AccountOverviewList.items` e
`AccountOverviewDetail` continuam sem tipo, então `ALIASES_DEPRECIADOS`/
`ALIASES_DEPRECIADOS_DE_DICT_CRU` não ganham entrada nova — os dois `openapi*.yaml` têm diff vazio.

## Emenda (issue #122, fatia 5.1 — 04/09/2026) — o VALOR do enum atravessa por versão, e nasce o molde da migração de dado

Até aqui toda travessia de versão desta ADR foi sobre **chave** de payload ou de query string — o
campo mudou de nome, o valor dentro dele nunca mudou. `docs/ontology/aliases.md` sempre teve uma
quarta dimensão em aberto: a decisão D10 da Language Map v1.4 torna o **valor** de um enum parte do
mesmo contrato de idioma da classe e do campo, e quatro famílias em português esperavam essa
condição. `DigitalEmployeeBlueprint.Area` foi a primeira com o pré-requisito completo — a classe já
nascera inglesa — e por isso é a primeira a atravessar, estabelecendo os dois moldes que as três
famílias restantes (cobrança e satisfação) reusam.

### 8. A migração de valor persistido, com reversa — o primeiro caso do repositório

Toda migração de ontologia até aqui (`0067`–`0072`, `0069`) foi `RenameModel`/`RenameField`/
`AlterModelTable`: preserva linha e pk, nunca lê nem escreve o dado. A `0084` é diferente —
`AlterField` troca os `choices` e o `default` para inglês, e um `RunPython` traduz as cinco linhas
existentes (`comercial→commercial`, ...) com reversa simétrica (en→pt). A reversa não é
formalidade: valor persistido sem caminho de volta é migração destrutiva disfarçada, o mesmo
argumento que justificou a prova de equivalência da `0070`. O par que autoriza a migração é a linha
da tabela de `docs/ontology/aliases.md` mais a nota D10 abaixo dela — não uma decisão desta ADR
isolada.

### 9. A normalização de entrada de VALOR na v1 — segunda tabela do mixin, e por que a v2 não ganha frase própria

`AliasesDaV1Mixin` ganhou `VALORES_DE_ENTRADA: dict[str, dict[str, str]]` (campo → {valor legado:
valor canônico}), ao lado de `ALIASES_DE_ENTRADA` (campo → campo canônico) que já existia. São duas
tabelas porque resolvem defeitos diferentes: uma diz "este campo mudou de nome", a outra diz "este
campo é o mesmo, e o que persiste dentro dele mudou de idioma". Na v1, um valor legado no corpo é
traduzido para o canônico **antes** da validação — quem escrevia `"comercial"` continua
funcionando. Na v2 a chave errada não tem onde cair (o DRF a ignoraria em silêncio, o modo de falha
mudo da decisão 3), mas o **valor** errado tem: cai sozinho na validação de `choices` do campo, que
já é um 400 listando o vocabulário inteiro. Escrever uma frase nossa aqui seria a segunda definição
de um erro que o DRF já produz de graça — por isso a v2 não ganha recusa dedicada de valor no
corpo, ao contrário do que a decisão 3 faz para chave.

### 10. O filtro de query string é a exceção — porque lá ninguém valida nada

`QueryParamFilterMixin` ganhou `filter_valores_legados: dict[str, dict[str, str]]`, o par de
`filter_field_aliases` para valor em vez de nome de parâmetro. Na v1 o valor legado em
`filter_exact_fields` continua filtrando, traduzido pelo mesmo mapa do corpo (por referência —
`DigitalEmployeeBlueprintViewSet.filter_valores_legados` aponta para
`DigitalEmployeeBlueprintSerializer.VALORES_DE_ENTRADA`, não uma segunda cópia). Na v2, ao
contrário do corpo, o valor legado **é** recusado com frase dedicada
(`versioning.frase_do_valor_removido`, o par de `frase_do_parametro_removido`): um filtro não passa
pelo `choices` de nenhum serializer, e `?area=comercial` sem tradução casaria zero linhas —
devolvendo 200 com uma lista vazia, o mesmo silêncio mentiroso que a decisão 3 recusa para chave e
parâmetro. Custava uma frase a mais evitar esse silêncio, e foi essa a diferença que decidiu o
tratamento: corpo tem validador que fala por conta própria, filtro não tem nenhum.

### Consequências

- `backend/apps/core/migrations/0084_a_area_do_blueprint_fala_ingles.py` é o molde citado por
  `docs/ontology/aliases.md`: `AlterField` + `RunPython` com reversa, cinco `.update()` por par.
- `openapi.yaml` e `openapi-v2.yaml` mudam só no enum de `area` (os dois passam a listar os cinco
  valores ingleses) — nenhum caminho novo, nenhuma chave-alias nova em `ALIASES_DEPRECIADOS`: o
  mecanismo desta fatia é outro, e não usa aquele mapa.
- `backend/tests/test_vocabulario.py::test_os_valores_de_enum_em_portugues_ficam_congelados_ate_a_v2`
  passa a congelar `DigitalEmployeeBlueprint.Area` em inglês; as outras três famílias continuam
  congeladas em português.

## Emenda (issue #122, fatia 5.2 — 04/09/2026) — os três renomes chegam juntos pela primeira vez, e a família 2 atravessa

A fatia 5.1 estabeleceu os dois moldes reaproveitáveis (migração de valor com reversa; normalização
de entrada de valor no mixin) sobre a única das quatro famílias em português cuja **classe** já
nascera inglesa. `Activity.CobrancaSinal` é a segunda família a atravessar, e a primeira em que os
**três** renomes — classe, campo, valor — chegam na mesma fatia: D10 (§4 do language-map) trata o
valor de um enum como parte do mesmo contrato de idioma da classe e do campo, e uma classe ainda em
português não tinha para onde adiar sozinha.

### 11. `RenameField` antes da tradução de valor, no mesmo arquivo

`0085_o_sinal_de_cobranca_fala_ingles.py` encadeia três operações na ordem: `RenameField`
(`cobranca_sinal` → `dunning_signal`, coluna renomeada, linha e pk sobrevivem — §2b), `AlterField`
trocando `choices` para os três valores ingleses, e `RunPython` traduzindo as linhas existentes
(molde exato da `0084`, com reversa simétrica). O `RenameField` vem primeiro porque o `RunPython`
já opera sobre o nome de coluna novo — não há estado intermediário em que a migração fale metade
dos dois nomes de campo.

### 12. Campo `read_only` não ganha `ALIASES_DE_ENTRADA` nem `VALORES_DE_ENTRADA`

`Activity.dunning_signal` só é gravado pela action `classificar` — nunca por `POST`/`PATCH` direto
(a distinção "campo" vs. "ato" da FDD 028). Sem caminho de escrita, não há o que normalizar: o
`ActivitySerializer` ganhou as duas chaves-alias de leitura de sempre (`cobranca_sinal`,
`cobranca_sinal_display`, `source=` apontando para o campo canônico) e uma entrada nova em
`ALIASES_DEPRECIADOS["Activity"]`, que é o que faz o mixin também **recusar** as duas no corpo da
v2 — a mesma lacuna que a decisão 3 desta ADR fechou para `client`/`kpi_baseline`. É a primeira
família de D10 em que o mecanismo de valor (fatia 5.1) e o mecanismo de chave (decisão 2 desta ADR)
convivem no mesmo serializer: um mapa para a chave que sai da resposta, e nenhum mapa de valor
porque não há entrada de valor a aceitar.

### 13. O prompt pede os canônicos; a extração tolera os legados

O prompt de `classificar` dizia à IA para responder `"esqueceu"`/`"nao_pode"`/`"insatisfeito"`.
Passar a pedir os três tokens ingleses diretamente — em vez de manter o prompt em português e
traduzir a resposta depois — é o mesmo argumento da FDD 039 sobre não deixar no prompt a aparência
de que o modelo decide o vocabulário: quem decide é o código, e o prompt já pede o que o código
persiste. `views.sinal_do_texto` ganhou `_SINAIS_LEGADOS`, um mapa de três entradas que traduz o
token antigo para o canônico antes de validar contra `Activity.DunningSignal.values` — tolerância
barata de release para a IA responder com cache ou variação do prompt anterior, não um segundo
caminho de entrada permanente: não há alias de escrita para o cliente da API, só para o texto que o
modelo pode devolver.

### Consequências

- `backend/apps/core/migrations/0085_o_sinal_de_cobranca_fala_ingles.py` é a segunda migração de
  valor do repositório, e a primeira a combinar `RenameField` com o molde de tradução da `0084`.
- `openapi.yaml` ganha `dunning_signal`/`dunning_signal_display` (marcados `deprecated` nas duas
  chaves legadas correspondentes) e o enum do sinal passa a listar os três valores ingleses;
  `openapi-v2.yaml` não emite as duas chaves legadas.
- `docs/ontology/legacy-allowlist.txt` perde a linha `modelo-em-portugues::CobrancaSinal`, e
  `TETO_DA_ALLOWLIST` desce de 23 para 22 (`backend/tests/test_vocabulario.py`).
- `test_os_valores_de_enum_em_portugues_ficam_congelados_ate_a_v2` passa a congelar
  `Activity.DunningSignal` em inglês; as famílias 1 (degraus de cobrança) e 3 (satisfação) seguem
  congeladas em português.
- `docs/ontology/aliases.md` §"Termos ainda sem nome canônico" deixa de citar `Activity.CobrancaSinal`
  — tem nome canônico e código que o usa —, mantendo `CobrancaContato`, `CobrancaSuspensao` e o
  restante da família `Cobranca*` sem nome ainda.

## Emenda (issue #122, fatia 5.3 — 04/09/2026) — a tabela atravessa junto, e a rota canônica ganha o quinto par

A fatia 5.2 foi a primeira em que classe, campo e valor chegaram juntos. `Satisfacao` é a terceira
família de D10 a atravessar e traz o que faltava ao conjunto: o renome de **tabela** no mesmo
arquivo, um par de rota novo no dicionário da v2, e a primeira família com **dois** enums de valor
no mesmo modelo.

### 14. `RenameModel` que de fato renomeia a tabela — e o que autoriza isso

`docs/ontology/aliases.md` §2b é normativa: todo renome de modelo se faz com `RenameModel`, nunca
com modelo novo mais migração de dados. Na issue #67 cada fatia fixava `Meta.db_table` no nome
legado **antes** da operação, para que ela não emitisse SQL nenhum — a proteção existia porque o
One deriva chave de identidade de seis pks deste repositório e as **persiste**.

A pk de satisfação não é uma das seis, e a razão é mais forte que a lista: o registro **não
atravessa** para o portal do cliente (ADR 0032), então não existe do outro lado nada de que se
despregar. Por isso `0086_a_satisfacao_fala_ingles.py` abre com um `RenameModel` puro
(`core_satisfacao` → `core_satisfactionrecord`), que emite o `ALTER TABLE … RENAME TO` e preserva
linha e pk pelo mesmo mecanismo da `0069`. A reversa o desfaz. A verificação de que a §2b não
proíbe está escrita no cabeçalho da própria migração, e não só aqui: quem lê a migração daqui a um
ano precisa achar o argumento ali.

### 15. O mapa de pares ganha um nível, porque a família tem dois enums

A `0084` e a `0085` traduziram um campo cada, e `_PARES_PT_PARA_EN` era uma tupla de pares. Aqui
são dois (`nivel` e `fonte`), e o mapa passa a ser campo → pares. Duas tuplas soltas fariam a
reversa — a metade que ninguém exercita até precisar dela — depender de o leitor lembrar qual lista
pertence a qual coluna. O teste percorre o mapa em vez de repetir os seis pares, pelo motivo de
sempre: uma cópia envelhece sozinha.

### 16. Os campos não renomeiam, e a ausência é declarada em vez de suposta

O language-map §4 cunha `satisfaction_record.level` e `satisfaction_record.source` na tabela de
**enums** — é a linha que enumera os valores. Não há, em seção nenhuma, coinagem do nome do
*campo*, e a chave de payload é justamente o que a §2c congela até a `/api/v2/`. Renomear a coluna
sem ter para onde levar a chave pagaria metade de uma dívida e criaria outra, então `nivel` e
`fonte` ficam — e a ausência de canônico vai por escrito para a seção "Termos ainda sem nome
canônico" da `aliases.md`, ao lado de `recebido_do_cliente` e das chaves `sinal_*`/`satisfacao_*`
do painel de cobrança. **A frase que vale para as três é uma só: o valor atravessou, a chave espera
coinagem.**

Como os dois campos **são graváveis** — ao contrário do `dunning_signal` da 5.2, lavrado só pela
action `classificar` —, esta é a primeira família a usar os dois moldes da fatia 5.1 com mais de um
campo: `VALORES_DE_ENTRADA` no serializer (a v1 traduz o valor legado antes da validação; a v2 cai
no 400 de `choices` do DRF) e `filter_valores_legados` no viewset, que aqui é o mapa **inteiro** do
serializer por referência, e não uma entrada extraída dele.

### 17. O quinto par de rota, e por que ele não existia antes

`PREFIXOS_CANONICOS_DA_V2` tinha quatro entradas — as quatro que a issue #67 renomeou de classe. A
rota `/satisfacoes/` não estava entre elas porque não havia nome canônico para onde apontar:
enquanto a classe se chamava `Satisfacao`, `/satisfaction-records/` seria uma invenção da v2, e não
o cumprimento de um prazo declarado. Com a classe renomeada, a rota passa a ter destino, e o
`basename` da v1 vira explícito (`basename="satisfacao"`) pelo motivo de `clients`/`opportunities`:
o derivado do queryset viraria `satisfactionrecord` e quebraria todo `reverse("satisfacao-…")` do
repositório.

### Consequências

- `backend/apps/core/migrations/0086_a_satisfacao_fala_ingles.py` é a terceira migração de valor do
  repositório, a primeira a renomear tabela numa fatia de idioma e a primeira a traduzir dois enums.
- `openapi.yaml` troca o componente (`Satisfacao` → `SatisfactionRecord`, e o `Patched…` junto) e os
  dois enums passam a listar os valores ingleses; **a rota da v1 não muda** (`/api/v1/satisfacoes/`).
- `openapi-v2.yaml` troca a rota para `/api/v2/satisfaction-records/`, com os `operationId` e as
  tags acompanhando.
- `docs/ontology/legacy-allowlist.txt` perde **três** linhas (`Satisfacao`, `SatisfacaoSerializer`,
  `SatisfacaoViewSet`) e `TETO_DA_ALLOWLIST` desce de 22 para 19.
- `test_os_valores_de_enum_em_portugues_ficam_congelados_ate_a_v2` passa a congelar
  `SatisfactionRecord.Nivel`/`.Fonte` em inglês; resta a família 1 (degraus de cobrança).
- `RolePermission` passa a ler `resource = "satisfaction_record"`, no molde das fatias da #67, que
  renomeavam o `resource` junto da classe.

## Emenda (issue #122, fatia 5.4 — 04/09/2026) — a última família atravessa, e a série fecha

`CobrancaContato` é a quarta e última família que a decisão D10 marcou, e nela os **quatro**
renomes chegam no mesmo arquivo: classe, tabela, campo (`dunning_step`) e valor. Depois dela não
resta enum persistido em português no repositório, e o teste de congelamento inverte de sentido —
deixa de guardar o português para guardar o estado novo, porque a volta é o mesmo defeito visto do
outro lado. As decisões novas são cinco, e nenhuma delas altera as anteriores.

### 18. A coinagem veio pelo espelho, e o precedente é `DunningSignal`

O caminho normal da §8 do language-map é Notion → espelho → Pulse. Aqui ele se inverteu, pela
segunda vez na mesma issue: o campo (`dunning_step`) e os cinco valores **já estavam** cunhados no
language-map §4, então a decisão de significado já existia — faltava só o substantivo da classe que
os carrega. `DunningContact` foi cunhado em `docs/ontology/aliases.md`, com a mesma justificativa
que a fatia 5.2 usou para `DunningSignal`, e a página do Notion recebe depois.

O que autoriza a inversão é estritamente isso: **existir campo já cunhado que dita o nome**. Não
vale para `Pendencia`, `Decisao`, `Risco` nem para o resto da família `Cobranca*`, e a `aliases.md`
diz isso por escrito para a exceção não virar regra na próxima fatia.

### 19. As `key` da régua **são** o valor persistido, e por isso não havia como partir a fatia

`cobranca.DunningStep` (a dataclass da régua) carrega uma `key` por degrau, e essa `key` é o que
`DunningContact.dunning_step` guarda. Traduzir a coluna sem traduzir as chaves — ou o contrário —
faria `_degrau_gasto` deixar de casar com o banco **em silêncio**: a idempotência nunca mais
encontraria o degrau já gasto, e o mesmo e-mail sairia de novo para o cliente, sem nada ficar
vermelho. É a única das quatro famílias em que o valor do enum tem uma segunda expressão em código,
e é por isso que o teste de congelamento afirma as duas listas no mesmo lugar, mais a inclusão de
uma na outra.

### 20. Valor legado em corpo de `@action` precisa de recusa própria — a exceção da decisão 9

A decisão 9 registrou que a v2 **não** ganha frase própria para valor legado no corpo: o
`ModelSerializer` cai sozinho na validação de `choices` do DRF, que já é um 400 listando o
vocabulário inteiro, e escrever uma frase nossa seria a segunda definição do mesmo erro. O degrau é
a exceção, e a diferença é mecânica: ele chega no corpo de `rascunhar`/`enviar`, que **não montam
serializer** — quem valida é a própria action, contra as réguas de `cobranca.py`. Sem tradução,
`pre_aviso` na v2 cairia no "Degrau desconhecido", que é um erro mentiroso: o degrau existe, o nome
dele é que mudou. A recusa vive em `views._degrau_do_corpo` e usa a frase que já existia
(`versioning.frase_do_valor_removido`), a mesma do filtro — duas redações do mesmo "não existe
mais, use este nome" divergiriam na primeira edição.

### 21. `filter_field_aliases` passa a valer nos dois laços do mixin

Em `filter_exact_fields`, o nome do parâmetro **é** o caminho do ORM, como já era em
`filter_fields`. Com o campo renomeado, `?degrau=lembrete` deixaria de filtrar **em silêncio** na
v1 — devolvendo a lista inteira como se ninguém tivesse filtrado, que é pior que o `FieldError`
que o mesmo caso produz no outro laço, e é exatamente o modo de falha mudo que a decisão 3 recusa.
O laço de `filter_exact_fields` passou a consultar `filter_field_aliases` na mesma forma do
primeiro: a v1 aceita o nome antigo, a canônica vence quando as duas vêm, e a v2 responde 400
dizendo qual usar. A mudança é inerte para todo viewset em que os dois mapas não se tocam.

### 22. A rota `/cobranca/` **não** ganha par canônico — ao contrário da 5.3

Na 5.3, `/satisfacoes/` era o nome da classe em português, e a classe renomeada deu destino à rota.
Aqui o prefixo nomeia a **família** de cobrança — `CobrancaSuspensao`, `cobranca.py`, a flag e o
`kind` de notificação —, que segue sem coinagem. Inventar `/dunning-contacts/` batizaria em inglês
o que ninguém decidiu, que é o oposto do que esta issue faz. `PREFIXOS_CANONICOS_DA_V2` continua com
cinco entradas. O que acompanhou a classe foi o `resource` do viewset
(`cobranca` → `dunning_contact`), no molde das fatias da #67: `resource` é nome interno de
autorização, não contrato público.

### Consequências

- `backend/apps/core/migrations/0087_o_contato_de_cobranca_fala_ingles.py` é a quarta e última
  migração de valor da série, e a única em que renome de tabela e de campo andam juntos — o que
  arrasta `RenameIndex` (índice de `Meta.indexes` sem nome declarado, derivado da tabela) e o par
  `RemoveConstraint`/`AddConstraint` **abraçando** o `RenameField`, sem o qual a reversa morre
  tentando recriar a `UniqueConstraint` sobre uma coluna que já não existe.
- `openapi.yaml` ganha `dunning_step`/`dunning_step_display` e marca `degrau`/`degrau_display` como
  `deprecated`; o componente vira `DunningContact` e o enum, `DunningStepEnum`. `openapi-v2.yaml`
  não emite o par legado. **A rota da v1 e a da v2 continuam `/cobranca/`.**
- `docs/ontology/legacy-allowlist.txt` perde **três** linhas (`CobrancaContato`,
  `CobrancaContatoSerializer`, `CobrancaViewSet`) e `TETO_DA_ALLOWLIST` desce de 19 para 16.
- `test_os_valores_de_enum_em_portugues_ficam_congelados_ate_a_v2` foi renomeado para
  `test_os_quatro_enums_da_d10_falam_ingles_e_ficam_congelados_assim`: não há mais família
  congelada em português, e o que ele guarda agora é o estado novo das quatro.
- `RolePermission` passa a ler `resource = "dunning_contact"`.
- A SPA troca `CobrancaDegrau`/`CobrancaContato` por `DunningStep`/`DunningContact` e passa a ler
  `dunning_step_display` no histórico — ela consome a v2, onde `degrau_display` não sai.

## Emenda (issue #122, fatia 6 — 04/09/2026) — a série fecha, e o que a issue entregou por inteiro

A fatia 6 é limpeza, não travessia de contrato: nenhum `openapi.yaml`/`openapi-v2.yaml` muda —
critério de aceite verificado por `git diff` vazio dos dois, na mesma disciplina da fatia 3b. O que
ela paga é o rastro que as fatias 5.1–5.4 deixaram para trás ao mover classe, tabela, campo e valor
em código, e que a documentação e os identificadores puramente locais não tinham acompanhado:

- as FDDs vivas (036, 037, 038, e mais duas ocorrências achadas na varredura completa — FDD 039 e
  FDD 049) passaram a afirmar os nomes/valores canônicos onde descreviam o estado atual do código,
  com uma nota datada por página; a narrativa histórica de cada uma (a "Jornada" que motivou a
  fatia, escrita antes de D10 existir) não foi reescrita — reescrever contexto de decisão já
  tomada é reescrever história, e as ADRs desta série valem o mesmo tratamento e por isso não
  foram tocadas;
- o módulo `satisfacao.py` virou `satisfaction.py` (molde de `processos.py`→`process.py` da #67),
  com a constante `SATISFACAO_VALIDA_DIAS`→`SATISFACTION_VALID_DAYS` e o alias de import
  `satisfacao_module`→`satisfaction_module` nos três chamadores (`agents.py`, `health.py`,
  `cobranca.py`); em `cobranca.py`, `TENSAO_SATISFACAO` e os vizinhos puramente internos que
  nomeavam a satisfação em português (`satisfacoes_por_cliente`, `satisfacao_vigente`,
  `insatisfacao_declarada`) atravessaram para inglês — **o valor** de `TENSAO_SATISFACAO`
  (`"satisfacao"`, a chave de payload de `tensao_causa`) não mudou, porque não tem canônico ainda
  (ver "Termos ainda sem nome canônico" em `docs/ontology/aliases.md`);
- o ponteiro rançoso da nota do snapshot em `docs/ontology/aliases.md` ("a quarta linha de baixo
  para cima") passou a nomear a linha em vez de contar posição — a tabela cresceu quatro vezes
  desde que a nota foi escrita, e contagem de posição numa tabela que cresce é o tipo de ponteiro
  que apodrece sozinho;
- `docs/ontology/aliases.md` ganhou a seção "A série 5.x fechou", que registra as quatro famílias,
  o molde nascido na 5.1 e o que continua vivo no documento por não ser dívida desta série.

**Nenhum identificador de contrato mudou.** Chave de payload, rota e valor de enum já expostos
continuam exatamente como as fatias 5.1–5.4 os deixaram; o que a fatia 6 renomeou foi só o que o
`docs/ontology/language-map.md` §6 chama de "batismo" em território puramente interno — arquivo,
constante, variável e função sem chamador fora do processo Python. `docs/ontology/legacy-allowlist.txt`
e `TETO_DA_ALLOWLIST` não mudam nesta fatia: nenhum dos identificadores renomeados estava
declarado ali — a heurística de `modelo-em-portugues` casa `class X(`, não nome de arquivo, de
constante ou de função.

Com isto a issue #122 entrega, de ponta a ponta: a `/api/v2/` nascida por versão no caminho (fatia
1), os quatro pontos de alias que só a view alcançava (fatia 3a), o contrato próprio da v2 (fatia
3b), as chaves «client» que nunca tinham entrado no mapa (fatia 4a) e a lacuna que sobrou dela
(4c), a travessia da SPA para a v2 (4b), as quatro famílias de enum em português (5.1–5.4) e,
nesta fatia, o rastro documental e de nomenclatura interna que elas deixaram. Fica fora, como
sempre esteve: o sunset da `/api/v1/`, decisão que ninguém tomou.
