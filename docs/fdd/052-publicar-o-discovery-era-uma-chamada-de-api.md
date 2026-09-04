# FDD 052 — Publicar o Discovery era uma chamada de API

> **A tela que decide o que o cliente vê — `/contas/:id/publicacao`.** Paga a pendência que a
> FDD 051 registrou: a marca de publicável, as cinco portas e a aba do One já existiam e somavam
> **zero** para o cliente, porque publicar só era alcançável por `POST` em action. Entra
> `publication_state` nos cinco serializers publicáveis (ADR 0063), uma rota nova na SPA com
> seleção em cascata e publicação em lote, o selo de leitura na `ProcessDetailPage` e a porta no
> detalhe da conta. Contrato `/api/v1/` preservado: aditivo, e o campo novo é só de leitura.

## Jornada

A issue `#106` (FDD 051, ADR 0060) entregou a marca de publicável em cinco modelos, a invariante de
cadeia com as cinco portas e as quatro listas do Discovery no snapshot. Do outro lado,
`biahflow/one#90` entregou a aba Discovery que consome esse bloco. As duas fatias estavam de pé,
verdes e com regressão — **e somavam zero para o cliente.**

As quatro listas renderizavam vazias em toda conta, e continuariam renderizando. Nada nasce
publicado: a ADR 0060 recusou o backfill de propósito, e a migração `0075` não tem `RunPython`
nenhum. O único jeito de publicar era `POST /<recurso>/{id}/publish/` nos cinco — rotas alcançáveis
por `curl` e por mais nada.

**Isso não é defeito de integração.** É a invariante correta encontrando a ausência do fluxo que a
torna exercível: a regra que diz "nada atravessa sem revisão humana" foi construída antes do lugar
onde uma pessoa faz essa revisão. As duas fontes escritas já registravam a dívida com a mesma frase
(ADR 0060 e FDD 051, "Fora deste recorte"):

> *"A superfície de publicação fica devendo. Publicar hoje é chamada de API. A tela é pacote
> próprio, com DAP, porque decidir* o que o cliente vê *merece um board revisado e não um botão
> improvisado ao lado de 'Arquivar'."*

Este é o pacote: `docs/design/dap-publicacao-discovery-r1/`, revisão 1, aprovado em 03/09/2026,
decisões **A1 · B1 · C1 · D1 · E1 · F1 · G1** — mais a oitava, descoberta na construção e registrada
no próprio pacote. Mudar a superfície exige revisão nova dele, não julgamento na hora.

## A correção de fato que mudou o desenho

A issue `#108` descreve `unpublish` como uma ação que derruba dependentes. **Ela não derruba: ela é
recusada por eles** (a action `unpublish` do `PublicationMixin`, em `backend/apps/core/views.py`):

```python
presos = publication.dependentes_publicados_de(obj)
if presos:
    raise StateConflict(publication.frase_do_impedimento(obj, presos))   # 409
```

Não existe "quem cai se este sair" — existe "quem impede este de sair". E não é omissão: é a decisão
que a FDD 051 escreveu na segunda das cinco portas, *recusar, e nunca despublicar o de cima em
silêncio*, pelo argumento das duas guardas de arquivamento (FDD 045, FDD 048).

Duas consequências, e nenhuma é de redação:

1. O critério de aceite da issue — *"despublicar mostra os dependentes que caem antes de executar"* —
   vira **"o item preso não oferece o botão, e diz quem o prende"**. Um botão habilitado para um
   `POST` que o servidor nega é o defeito que o `CLAUDE.md` já nomeia para o PROVE.
2. Os estados por item passam de três para **quatro**:

| Estado | O que é | De onde sai |
| --- | --- | --- |
| **Visível · solto** | publicado, e nada publicado depende dele | `published_at` + `dependentes_publicados_de(obj) == []` |
| **Visível · preso** | publicado, e algo publicado depende dele | `published_at` + `dependentes_publicados_de(obj) != []` |
| **Oculto · pronto** | não publicado, e nada falta | `published_at is None` + `o_que_falta_para_publicar(obj) == []` |
| **Oculto · bloqueado** | não publicado, e falta sustentação acima | `published_at is None` + lista não-vazia |

Os quatro estão desenhados no board, e é essa quadratura que o contrato abaixo precisa carregar.

## O que esta fatia entrega

### 1. O contrato: `publication_state` nos cinco serializers

```json
"publication_state": {
  "state": "published" | "ready" | "blocked",
  "missing": ["published_evidence"],
  "missing_phrase": "ao menos uma evidência publicada e viva",
  "blocked_by": 2,
  "blocked_phrase": "Este processo é a âncora de 2 achado(s) ou dor(es) publicado(s). Despublique-os primeiro."
}
```

**A decisão é a ADR 0063** — chaves *e* frases, e as frases vindas de `publication.py` —, e ela não
se repete aqui. O que esta FDD registra é o que foi construído:

- **Um lugar só decide.** `publication.estado_de_publicacao` é a única função
  que responde, e cada ramo calcula um lado só: publicado calcula `blocked_by`/`blocked_phrase` e
  devolve `missing` vazio; não publicado calcula `missing`/`missing_phrase` e devolve `blocked_by`
  zero. A omissão é medida, não economia — um registro que não atravessou não pode ter dependente
  publicado, que é a invariante exata das cinco portas.
- **Um serializer, cinco consumidores.** `PublicationStateSerializer` entra
  nos cinco com `source="*"` — `ProcessSerializer`, `EvidenceSerializer`,
  `FindingSerializer`, `PainPointSerializer`, `ImprovementOpportunitySerializer` —,
  e delega por inteiro à função. Um serializer comum em vez de cinco `SerializerMethodField` sem
  tipo, porque o drf-spectacular gera daí um componente `PublicationState` de verdade em
  `openapi.yaml`, e não um `object` solto repetido cinco vezes.
- **Só de leitura nos cinco**, no campo e em `read_only_fields`. Um `PATCH` que traga a chave no
  corpo é descartado pelo DRF sem 400 de campo desconhecido — o mesmo comportamento já afirmado
  para `published_at`/`published_by` em `test_a_cadeia_de_publicacao_nao_vaza.py`.
- **Aditivo.** Nenhuma chave saiu nem mudou de forma; o `openapi.yaml` ganha o componente novo e a
  propriedade nos cinco schemas de leitura.

`ImprovementOpportunity` sai com `blocked_by: 0` **sempre**, publicada ou não: ela é o topo da
escada, `dependentes_publicados_de` devolve `[]` para ela e `_IMPEDIMENTO` não tem entrada com o
nome dela. Zero ali não é "não apurado" — é "nada pende disto", que é fato do domínio, e é a exceção
deliberada à regra do `nao_apurado` (ADR 0063 §5).

### 2. A superfície

A fonte da superfície é o DAP; esta seção diz o que existe, não redesenha o board.

- **`/contas/:id/publicacao`** (`frontend/src/pages/PublicacaoPage.tsx`), resolvida em
  `App.tsx`, acima da rota da conta por especificidade. **Nada entra no menu lateral**: é a
  terceira tela que pende de uma conta, pelo motivo já registrado em `/contas/:id/priorizacao` e
  `/contas/:id/valor` — publicação é sempre *de uma conta*, e um item de menu que abre perguntando
  "qual conta?" é um beco.
- **A hierarquia visual *é* a cadeia** (C1): mapa → achado → evidência aninhada sob o achado → dor,
  com recuo e fundo, e as `ImprovementOpportunity` num painel próprio no fim — elas agrupam dores de
  mais de um mapa, e pendurá-las sob um deles afirmaria uma origem única que não têm. É assim que a
  tela ensina a ordem em vez de deixar descobrir.
- **Dois selos, não quatro** (D1): "Visível ao cliente" (`.state--active`, ícone `Eye`) e "Oculto do
  cliente" (`.state--off`, `EyeOff`), sempre o último elemento da `.row-meta`. O que falta e o que
  prende são **frase** na `.row-main`, nunca uma terceira pastilha: "preso" e "bloqueado" não
  respondem *o cliente vê isto?*, respondem *posso mudar isto?*, que é pergunta de ação e mora junto
  da ação. O componente é `PublicacaoBadge` (`components/StatusDot.tsx`), e o ícone é metade da
  distinção — na linha de um achado ele convive com o selo epistêmico, e na de uma dor com um
  "Sem oportunidade" que é o mesmo cinza.
- **A cascata de seleção corre nos dois sentidos** (F1). Para baixo, marcar leva a subárvore —
  estrutura pura, nenhuma regra de publicação passa por ali. Para cima, leva **o que o servidor
  disse que falta**: a tela lê `publication_state.missing` e marca os candidatos daquele degrau,
  transitivamente até o ponto fixo. É a diferença entre consumir a resposta e reescrever a pergunta.
  Um degrau marca **todos** os candidatos vivos e não publicados, e não "um": o requisito é *ao menos
  um*, e escolher qual seria a tela decidindo por quem publica, sempre para o mesmo lado. Desmarcar
  leva a subárvore e **não** mexe nos ancestrais — quem foi puxado para cima pode continuar valendo
  para outro item ainda marcado.
- **A caixa de seleção existe em todo item não publicado, inclusive no bloqueado**, e é isso que faz
  o lote existir: na conta em que nada foi publicado ainda, todo filho está bloqueado até o pai
  subir, e sem isso o operador voltaria a publicar um por vez esperando a tela recarregar entre
  cliques. A frase do que falta continua na linha e muda de papel — de *"por que você não pode"* para
  *"o que vai junto"* — sem mudar de texto.
- **O lote é sequencial na ordem canônica** `Process → Evidence → Finding → PainPoint →
  ImprovementOpportunity`. A ordem é o **único** conhecimento de regra que a tela carrega; ela nunca
  conclui que um item *vai* passar. Quem decide é o servidor, item a item.
- **A falha parcial não desfaz nada.** Cada recusa fica na linha do item com a frase do servidor, e o
  resumo diz quantos passaram e que nada foi desfeito. Desfazer o que subiu "para deixar a tela
  consistente" apagaria decisões humanas por causa de recusas alheias a elas — é o argumento das duas
  guardas de arquivamento (FDD 045, FDD 048).
- **A recusa do lote chega crua**, por `motivoDoServidor` e não por `mensagemDeFalha`: a orientação
  por código de `erros.ts` ("recarregue para ver o que vale agora", "confira o degrau") é certa na
  Cobrança e errada aqui — nada mudou desde que a tela carregou, e não há degrau nenhum. A faixa de
  **carga**, essa, segue usando `mensagemDeFalha`, onde a orientação é o que ajuda.
- **Ocultar passa por `ConfirmDialog`** (`components/Modal.tsx`), porque é retirar do cliente algo que
  ele já está vendo; e no item **preso** o botão fica desabilitado com o impedimento **na linha**, e
  não num `title=` (G1).
- **Selo de leitura na `ProcessDetailPage`** — cabeçalho do mapa (`:298`), linha do achado (`:422`) e
  linha da dor (`:466`) —, **sem ação**: acrescenta selo, não acrescenta ato. Publicar e ocultar
  moram na tela da conta, e daqui só se vai até lá, por um `back-link` no fim da página.
- **A porta na `AccountDetailPage:645`**, terceiro botão da faixa que já tem "Abrir a priorização" e
  "Abrir o valor gerado", com o mesmo `Eye` do selo. **Sem contador**: quantos itens pendem é
  informação da tela de destino, e um número ali obrigaria o detalhe da conta a buscar os cinco
  recursos a cada carga.
- **A Entrega fora do escopo da conta lê o motivo.** O recorte do `ProjectMember` (RFC 0003) chega
  como 403/404 na conta; a tela responde com a frase, e não com um alerta genérico. Para admin e
  Vendas o mesmo 404 continua significando "esta conta não existe", e por isso a frase é condicionada
  ao papel.

## O que a construção achou

### O item órfão não tinha porta, e o board não desenhou nenhuma

É a **oitava decisão** do DAP, registrada no pacote em vez de virar julgamento silencioso — no molde
da "sexta decisão" do DAP da priorização.

O board desenha a árvore como se todo `Finding` e todo `PainPoint` citassem um `Process`, e como se
toda `Evidence` fosse citada por algum achado. O schema não garante nada disso: `Finding.process` e
`PainPoint.process` são `SET_NULL` — é justamente o que faz **arquivar o processo não arquivar os
achados** (FDD 045) —, e uma `Evidence` pode existir sem achado que a cite. Numa árvore estritamente
hierárquica esses registros não apareceriam; e como esta é a **única** tela que publica, um dos cinco
publicáveis ficaria sem porta, atingível só por `curl`. O defeito que a fatia existe para fechar,
reaparecendo pela borda.

**O que foi construído:** eles entram no fim da árvore, em nível raiz, com a descrição dizendo o quê
— "sem mapa citado", "sem achado que a cite". Sem componente novo: são `.row` da mesma lista, com os
mesmos dois selos e a mesma frase do servidor. A alternativa recusada era escondê-los, que troca uma
lista honesta por uma lista bonita e devolve à linha de comando o ato que este pacote tira de lá.

### O mapa epistêmico subiu de arquivo quando ganhou o segundo leitor

`STATUS_BADGE` vivia dentro de `ProcessDetailPage.tsx` e virou `epistemicoBadgeClass` em
`components/StatusDot.tsx`. Uma cópia por tela é a segunda definição de "fato", e ela diverge da
primeira sem nada ficar vermelho (ADR 0026) — a mesma razão que já tinha elevado os três mapas
vizinhos.

E o lugar não é acidente: ele ficou **encostado no `sustentacaoBadgeClass`**, porque os dois selos
aparecem na mesma linha de achado e de dor junto com o de publicação, e a decisão D1 é inteira sobre
eles não se confundirem. Pôr os mapas lado a lado no código é o que torna a distinção visível para
quem mexer no próximo; separá-los faria a próxima variante nascer sem ninguém ver o vizinho que ela
precisa não imitar.

### `metaCount` foi de 2 para 3, e o número exato é o ponto

`e2e/responsive.spec.ts` mede, em 390px, se um título longo sem hífen invade o estado ou a ação da
linha do achado, e afirmava `metaCount === 2`. A linha ganhou mesmo um terceiro elemento na
`.row-meta` — selo epistêmico, selo de publicação e "Promover a fato" —, então a asserção passou a 3.
Ela continua **exata** e não virou `>=`: o número existe para provar que a medição alcançou os
elementos, e um `>=` deixaria a asserção passar com a faixa vazia.

### A errata do próprio pacote, aplicada pela regra dele

O board desenha selo e botão à direita, na mesma faixa do título. A primitiva real (`.row-meta`,
`index.css`) é `flex: 1 1 100%` e **sempre** quebra para a linha de baixo. A tela seguiu a primitiva —
é a regra que o próprio DAP escreve na seção de procedência (*"se este pacote e essa fonte
divergirem, a fonte vence e este pacote está velho"*), aplicada pela primeira vez, e não uma licença
tomada na hora.

## O custo medido

`publication_state` cobra **+1 consulta por item** na listagem de `Process`, `PainPoint` e
`ImprovementOpportunity`. `Evidence` e `Finding` em hipótese **não pagam nada**.

| Recurso | 1 item | 4 itens | Incremento por item |
| --- | --- | --- | --- |
| `Process` | 2 | 5 | **1** |
| `Evidence` | 1 | 1 | 0 |
| `Finding` (hipótese) | 2 | 2 | 0 |
| `PainPoint` | 3 | 6 | **1** |
| `ImprovementOpportunity` | 6 | 9 | **1** |

Medido por `apps/core/tests/test_publicacao_estado.py::test_custo_de_consulta_da_listagem_e_medido`,
que compara uma base de 1 e de 4 itens e divide a diferença por 3 — assim a medida não depende do
número fixo de consultas de setup da própria requisição.

É o mesmo `EXISTS` por linha que `_tem_publicado_vivo` já fazia nas cinco portas, agora também na
leitura. Os dois zeros são a escada, não sorte: a `Evidence` é a folha e não pergunta nada, e um
`Finding` em `hypothesis` também não — **só o `fact` consulta o M2M**, então uma conta cheia de fatos
publicados leria 1 também ali.

**Não otimizado, e a ausência é decisão registrada.** Um `Prefetch` ou uma anotação por recurso
resolveria, mas escolher onde otimizar sem uma conta grande de verdade é escolher o alvo pelo
palpite; e o consumidor principal é uma tela por conta, onde *n* é o tamanho de um Discovery e não o
de uma base. O teste que mede já existe e **não é gate** — acrescentar limite a ele é o primeiro
passo do dia em que houver conta que doa.

## Aceite

1. Os quatro estados saem de `publication.estado_de_publicacao`: publicado·solto, publicado·preso
   (com `blocked_by` e a frase do 409), não publicado·pronto e não publicado·bloqueado (com `missing`
   e a frase do 400).
2. `missing_phrase` é, palavra por palavra, `publication.frase_do_que_falta(missing)`, e
   `blocked_phrase` é `publication.frase_do_impedimento(obj, presos)` — afirmado pela função **e**
   pela API.
3. `ImprovementOpportunity` sai com `blocked_by: 0` e `blocked_phrase: ""` publicada e não publicada.
4. Os cinco recursos emitem `publication_state` na listagem e no detalhe, com o mesmo valor nos dois,
   e o campo é só de leitura: o `PATCH` que o traga no corpo é 200 e não publica nada.
5. A conta sem Discovery diz "Nenhum processo mapeado para esta conta." e o botão do lote fica
   desabilitado em `(0)`.
6. Os quatro estados convivem numa mesma tela, cada um com o selo, a frase e a caixa de seleção que
   lhe cabem, e os contadores do cabeçalho somam os três estados do servidor.
7. O item **preso** não oferece o botão de ocultar (desabilitado, com o impedimento na linha); o
   **solto** abre o `ConfirmDialog` antes de executar, e só depois do "Ocultar" a chamada sai.
8. Marcar um mapa marca a subárvore dele; marcar um filho bloqueado marca, transitivamente, o que ele
   precisa que suba antes — e o item já publicado nunca entra na fila. Desmarcar leva a subárvore e
   não desfaz os ancestrais.
9. O lote dispara na ordem `Process → Evidence → Finding → PainPoint → ImprovementOpportunity`; com
   uma recusa no meio, **nada é desfeito** — nenhuma chamada de ocultar sai — e o resumo diz quantos
   passaram.
10. A frase de uma recusa é a que o servidor mandou, inteira e sem a orientação por código de
    `erros.ts`, inclusive quando ela não existe em `publication.py`.
11. Com tudo publicado, a tela diz que nada aguarda publicação **e continua listando a árvore**, com
    o botão de ocultar habilitado no item solto.
12. A falha de carga chega traduzida por `mensagemDeFalha`; a Entrega fora do escopo da conta lê
    "Você não participa de nenhum projeto desta conta." e nenhum alerta.

**Regressões:**

- `backend/apps/core/tests/test_publicacao_estado.py` — os quatro estados pela função; a paridade de
  frase pelos dois lados **através do serializer**, que é o nível que pega alguém reescrevendo o
  rótulo na camada de apresentação; o topo da escada nos dois ramos; a emissão e o `read_only` nos
  cinco recursos; e a medida de custo.
- `frontend/src/pages/PublicacaoPage.test.tsx` — os onze casos do aceite 5–12. **O mais importante é
  "a frase da recusa é a que veio do servidor — a tela não tem mapa de rótulo"**: ele injeta em
  `publish` uma frase que **não existe** em `publication.py` e afirma que a tela a renderiza tal e
  qual. É a guarda contra o mapa chave→rótulo voltar ao front — um mapa em TypeScript escreveria a
  frase canônica, nunca esta, e sem este teste a próxima varredura atrás de simetria com o PROVE o
  reintroduziria sem nada ficar vermelho.
- `frontend/src/pages/ProcessDetailPage.test.tsx` — o caso novo: o selo é leitura, não se confunde com
  os dois vizinhos da mesma linha, e a tela não oferece publicar nem ocultar, só o link para a
  publicação da conta.
- `frontend/e2e/matrix.ts` — a tela entra na matriz da FDD 022 por uma linha (29 telas × 3 larguras,
  axe e rolagem horizontal incluídos), e as fixtures passam a carregar os **quatro** estados por item:
  um mock com tudo no mesmo estado aprovaria a tela sem que metade dela tivesse renderizado uma vez.

## Fora deste recorte

- **Backfill de publicação.** Decisão registrada (ADR 0060), não pendência: nada nasce publicado, e
  publicar o acervo existente é decisão de operação, com issue própria.
- **`ProcessStep` com marca própria.** Decisão registrada na FDD 051: ele anda com o processo pai.
- **`Discovery`, `DiscoverySession` e `ProcessObservation`.** Decisão registrada na FDD 051: dão tempo
  e autoria ao levantamento, que é organização interna do trabalho, e a §3 não os lista.
- **Endpoint de lote** (F3) e **`GET /<recurso>/{id}/publication-state/`** (B2). Decisões registradas:
  recusadas no DAP com motivo, e a ADR 0063 §4 escreve o da segunda — um endpoint por item cobraria
  uma requisição por linha exatamente na tela que desenha o Discovery inteiro.
- **Regra nova de papel.** Não há: quem escreve o recurso publica, e os cinco `resource` já estavam
  nos conjuntos de Vendas e de Entrega desde a FDD 051.
- **Copy dos rótulos do servidor.** `ROTULOS` e `_IMPEDIMENTO` são exibidos como estão; reescrevê-los
  é mudança de copy e precisa de aprovação própria.
- **Pré-visualização "como o cliente vê".** Pendência, com espaço reservado no board (hachura
  `.reserved`, inerte — botão desligado é defeito, não placeholder). Vira real quando existir um
  render do bloco do One deste lado; hoje o único jeito de conferir é abrir o portal.
- **Histórico de publicação.** Pendência: `published_by` guarda **um autor**, não uma trilha, e uma
  tela de "quem publicou o quê, quando" precisa de mais que o carimbo do último ato.
- **A otimização do +1 por item.** Pendência declarada acima, com a medida já no lugar.

## Referências

- ADR 0063 — o estado de publicação sai com a frase, porque o rótulo já mora no servidor.
- ADR 0060 e FDD 051 — a marca de publicável, as cinco portas e a pendência que esta fatia paga.
- DAP `docs/design/dap-publicacao-discovery-r1/` — r1, **A1 · B1 · C1 · D1 · E1 · F1 · G1** mais a
  oitava decisão; a fonte da superfície.
- ADR 0026 — mapa de estado devolve variante, nunca a cor; a razão de o mapa epistêmico ter subido.
- FDD 045 e FDD 048 — o `SET_NULL` que produz o item órfão, e as guardas de arquivamento que
  sustentam "recusar, nunca desfazer sozinho".
- FDD 022 — a matriz de telas em que a rota nova entra.
- Issues `#108` (esta), `#106` (contrato e emissão), `#69` (os modelos) e `biahflow/one#90` — a aba
  que espera do outro lado.
