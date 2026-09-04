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
