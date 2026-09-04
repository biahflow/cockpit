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
