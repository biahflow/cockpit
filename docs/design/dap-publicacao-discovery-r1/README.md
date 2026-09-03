# Design Approval Package — Publicação do Discovery

Classificação: `INTERFACE_CHANGE` · `BROWSER_REQUIRED`
Revisão: **1**
Status: **Aprovado**
Data: 2026-09-03
Produzido por: Claude Code (harness), a partir da issue `#108`

> Governado por `docs/engineering-os/workflows/design-approval.md`. Este artefato é evidência para
> um gate humano. Não é implementação e não deve ser copiado para dentro do código da aplicação.

---

## Por que existe um gate

A `#106` entregou a marca de publicável em cinco modelos, as cinco portas que a defendem e a
emissão do Discovery no snapshot do portal. Do outro lado, `biahflow/one#90` entregou a aba
Discovery que consome esse bloco. As duas fatias estão de pé e **somam zero valor para o cliente**,
porque publicar hoje só existe como chamada de API — `POST /<recurso>/{id}/publish/` nos cinco
(`backend/apps/core/views.py:325-352`). Sem tela, as quatro listas do One renderizam vazias para
todo cliente, e continuam renderizando.

Isso não é defeito: é a invariante correta ("nada atravessa sem publicação humana") encontrando a
ausência do fluxo que a torna exercível.

O gate não é formalidade aqui, e as duas fontes escritas dizem por quê:

**ADR 0060** (`docs/adr/0060-…md:165-167`) e **FDD 051** (`docs/fdd/051-…md:345-347`), com a mesma
frase:

> *"A superfície de publicação fica devendo. Publicar hoje é chamada de API. A tela é pacote
> próprio com DAP, porque decidir* o que o cliente vê *merece board revisado e não um botão
> improvisado ao lado de 'Arquivar'."*

E `design-approval.md` põe o gate **antes do planejamento**, não antes da construção — um plano que
decompõe superfície não decidida produz tarefas que precisam ser recortadas de novo.

---

## Uma correção de fato, antes das decisões

**A issue `#108` descreve `unpublish` como uma ação que derruba dependentes. Ela não derruba: ela é
recusada por eles.** O código é explícito (`views.py:363-368`):

```python
presos = publication.dependentes_publicados_de(obj)
if presos:
    raise StateConflict(publication.frase_do_impedimento(obj, presos))   # 409
```

Não existe "quem cai se este sair". Existe "quem impede este de sair". A consequência é de desenho,
não de redação: o critério de aceite *"despublicar mostra os dependentes que caem antes de
executar"* vira **"o item preso não oferece o botão, e diz quem o prende"** — e o número de estados
por item passa de três para **quatro**:

| Estado | O que é | De onde sai |
| --- | --- | --- |
| **Visível · solto** | publicado, e nada publicado depende dele | `published_at` + `dependentes_publicados_de(obj) == []` |
| **Visível · preso** | publicado, e algo publicado depende dele | `published_at` + `dependentes_publicados_de(obj) != []` |
| **Oculto · pronto** | não publicado, e nada falta | `published_at is None` + `o_que_falta_para_publicar(obj) == []` |
| **Oculto · bloqueado** | não publicado, e falta sustentação acima | `published_at is None` + lista não-vazia |

Os quatro estão desenhados no board. Um botão habilitado para um `POST` que o servidor nega é
exatamente o defeito que `CLAUDE.md` nomeia para o PROVE — *"habilitaria o botão de um `POST` que o
servidor nega, sem nada ficar vermelho"*.

---

## Artefato

| Arquivo | O que é |
| --- | --- |
| `board.html` | Renderização auto-contida. Abre sem build, sem toolchain e sem rede — nenhum `<script>`. |
| `board-desktop.png` | Captura congelada em 1280px (`deviceScaleFactor: 2`). É a isto que a aprovação se refere. |
| `board-mobile.png` | Captura congelada em 390px. |

A fonte Inter não é embutida; sem ela a página cai no fallback declarado no próprio token
`--font-sans`, e o que muda é o desenho da letra, não a decisão em aprovação.

---

## Onde a superfície mora

| Superfície | Onde | Situação |
| --- | --- | --- |
| Tela de publicação | rota nova `/contas/:id/publicacao`, `frontend/src/App.tsx` (ao lado de `priorizacao` e `valor`, acima de `accountDetail` por especificidade) | **nova** |
| Porta de entrada | `frontend/src/pages/AccountDetailPage.tsx:633-638`, terceiro botão da faixa que já tem "Abrir a priorização" e "Abrir o valor gerado" | **acrescenta um botão** |
| Selo de leitura | `frontend/src/pages/ProcessDetailPage.tsx` — cabeçalho do processo (`:296-299`), linhas de achado (`:415`) e de pain point (`:428-460`) | **acrescenta selo, não acrescenta ação** |

A tela **não entra no menu lateral**, pela razão já registrada duas vezes: publicação é sempre *de
uma conta*, e um item de menu que abre perguntando "qual conta?" é um beco (DAP priorização r1
decisão A1; DAP `dap-prove-e-valor-r1` decisão D1).

---

## O que está sendo pedido

Sete decisões, **todas escolhidas por humano em 2026-09-03** e registradas como decididas.

A distinção que importa e que fica marcada: **A · B · C** foram escolha direta, entre opções
apresentadas; **D · E · F · G** nasceram como *recomendação do harness* e foram aceitas. Elas ficam
identificadas como tal em cada seção, porque `design-approval.md` exige que um agente diga quais
partes do pacote são proposta sua em vez de linguagem estabelecida do projeto — sem isso o
aprovador não sabe o que está de fato decidindo. O contra-argumento de cada uma continua escrito
junto, e nenhuma delas vira consenso por ter sido aceita.

**O que este gate ainda julga é o desenho**, não as decisões: se `board.html` e as capturas cumprem
o que as sete prometem. Ver "Registro de aprovação".

### Decisão A — onde mora o ato de publicar · **decidida: A1**

| | |
| --- | --- |
| **A1** ✅ | **Tela de revisão da conta**, `/contas/:id/publicacao`: o Discovery inteiro na ordem da cadeia, com seleção e publicação em lote. A `ProcessDetailPage` ganha **só o selo** (leitura) e um link para cá. |
| A2 | Item a item na `ProcessDetailPage`, ao lado do "Promover a fato" que já existe. |
| A3 | As duas superfícies. |

**Por quê.** O ato é sobre o conjunto: decidir *o que o cliente vê* é uma decisão sobre o Discovery
da conta, não sobre uma linha. E a cadeia impõe ordem (`Process` → `Evidence` → `Finding` →
`PainPoint` → `ImprovementOpportunity`); numa tela por processo o operador sobe essa ordem por
tentativa e erro, navegando entre telas. O custo aceito: uma rota nova.

**Contra-argumento registrado.** A2 seria a entrega mais barata, e a `ProcessDetailPage` já tem o
padrão de linha com ação. Foi recusada porque o operador nunca veria o conjunto que o cliente verá
— que é a pergunta que ele precisa responder.

### Decisão B — de onde a tela tira "pode subir?" e "o que falta?" · **decidida: B1**

| | |
| --- | --- |
| **B1** ✅ | **Campo derivado read-only** nos cinco serializers, calculado por `publication.py`. |
| B2 | `GET /<recurso>/{id}/publication-state/` nos cinco. |
| B3 | O front infere de `published_at` e da cadeia. |

**Por quê.** B3 duplica no front a regra que `apps/core/publication.py` existe para concentrar — e
as duas divergem no primeiro conserto sem nada ficar vermelho. B2 mantém a regra no servidor, mas
cobra uma requisição por item exatamente no caso de uso principal: a tela da conta desenha um mapa
+ n evidências + n achados + n dores + n oportunidades de uma vez. B1 entrega o estado junto das
listas que a tela já faz.

**Consequência.** Os cinco serializers passam a emitir um campo derivado. Hoje nenhum emite:
`ProcessSerializer:1033`, `EvidenceSerializer:1194`, `FindingSerializer:1318`,
`PainPointSerializer:1417`, `ImprovementOpportunitySerializer:1488` só carregam o par bruto
`published_at`/`published_by`, todos já `read_only`.

### Decisão C — onde `Evidence` ganha superfície · **decidida: C1**

| | |
| --- | --- |
| **C1** ✅ | **Aninhada sob o achado** que ela sustenta, com selo e ação próprios. |
| C2 | Seção própria, listando todas as evidências da conta. |
| C3 | Fora do recorte. |

**Por quê.** `Evidence` é um dos cinco publicáveis e hoje não tem linha própria em lugar nenhum —
aparece só como `fonte.kind_display` dentro do achado (`ProcessDetailPage.tsx:410`). C2 separaria a
evidência do achado que ela sustenta, que é justamente o par que a ADR 0049 criou. C3 deixaria uma
das cinco portas sem tela, e a §3 do Language Map do One é explícita sobre evidência revisada.

**Consequência de desenho.** A hierarquia visual (mapa → achado → evidência) **é** a cadeia, e é
assim que a tela ensina a ordem em vez de deixar descobrir — a resposta à quarta pergunta da issue.

### Decisão D — o selo, e a colisão com os dois selos que já existem na mesma linha

> **Proposta do harness.** É o que este gate decide.

| | |
| --- | --- |
| **D1** ⭐ recomendada | **Dois selos, não quatro**, sempre com ícone: **"Visível ao cliente"** (`.state--active`, `Eye`) e **"Oculto do cliente"** (`.state--off`, `EyeOff`). O que falta / o que prende vira **frase** em `.row-main span`, não um terceiro selo. |
| D2 | Quatro selos coloridos — publicado / preso / pronto / bloqueado. |

**O problema que D resolve.** Na linha de um achado convivem, hoje, dois selos que respondem
*outras* perguntas, e os dois já ocupam a paleta inteira de `.state`:

| Selo existente | Pergunta que responde | Variantes usadas |
| --- | --- | --- |
| `STATUS_BADGE` (`ProcessDetailPage.tsx:102-104`) | qual o status epistêmico? | `state--1` fato · `state--2` hipótese · `state--off` desconhecido |
| `sustentacaoBadgeClass` (`StatusDot.tsx:47-58`) | o custo está sustentado? | `state--1` sustentado · `state--2` hipótese |

D2 colidiria de frente: um "bloqueado" em `state--2` fica âmbar ao lado de um "Hipótese" âmbar, e um
"pronto" em `state--off` fica cinza ao lado de um "Desconhecido" cinza — mesma pastilha, mesma cor,
significados diferentes, mesma linha.

**Como D1 separa.** Por três eixos ao mesmo tempo, e nenhum deles é só matiz:

1. **Forma** — o selo de publicação é o único **sólido escuro** (`.state--active`, `bg-ink`
   `text-white`, `index.css:414`) ou o único com **ícone de olho**. Os dois vizinhos são pastel e
   nunca têm ícone.
2. **Copy** — "Visível ao cliente" / "Oculto do cliente" não compartilha uma palavra com
   "Fato"/"Hipótese"/"Desconhecido" nem com "Sustentado por evidência"/"Ainda em hipótese". A
   palavra *hipótese* aparece nos outros dois e em nenhum lugar neste.
3. **Posição** — o selo de publicação é sempre o último da `.row-meta`, encostado na ação.

**Por que dois e não quatro.** A pergunta que o selo responde é binária — *o cliente vê isto?* — e é
essa a pergunta do operador. "Preso" e "bloqueado" não são estados de visibilidade: são respostas a
*"posso mudar isto?"*, que é pergunta de ação e por isso mora junto da ação, como frase. Um selo
para cada uma das quatro combinações transforma em enfeite o que precisa ser leitura de relance.

**Contra-argumento registrado.** D2 deixaria os quatro estados visíveis sem ler frase nenhuma, e a
contagem do cabeçalho ("3 visíveis · 5 prontos · 2 bloqueados") ficaria redundante com as linhas em
vez de complementá-las. Foi recusada pela colisão acima, que é medida e não estética.

### Decisão E — o que o campo derivado carrega

> **Proposta do harness.**

| | |
| --- | --- |
| **E1** ⭐ recomendada | `publication_state` carrega **chaves e frases**: `{state, missing: [chaves], missing_phrase, blocked_by, blocked_phrase}`. As frases vêm de `publication.frase_do_que_falta` e `frase_do_impedimento`. |
| E2 | Só as chaves, no molde de `ProveExperiment.missing_to_start` — os rótulos seriam da superfície. |

**Por quê E1 e não o molde do PROVE.** `CLAUDE.md` registra, para o PROVE, que
`prove.o_que_falta_para_iniciar` *"devolve chaves e nunca frases — os rótulos são da superfície"*. A
diferença aqui é factual: **os rótulos de publicação já existem no backend e já são copy de
produto.** `publication.ROTULOS` (`publication.py:82-87`) e `_IMPEDIMENTO` (`:91-103`) estão
escritos em português e já compõem a mensagem do 400 e do 409 que o operador leria de qualquer
jeito. Reescrevê-los em TypeScript criaria a segunda definição — e seria a mesma frase saindo de
dois lugares, divergindo no primeiro conserto. O critério de aceite da issue é literal: *"a frase
vem de `publication.py` — nunca de uma regra reescrita no front"*.

**As chaves continuam saindo**, e não são decoração: são o que permite teste e futura ramificação
por requisito sem parsear texto. `ImprovementOpportunity` não tem entrada em `ROTULOS` nem em
`_IMPEDIMENTO` — ela é o topo da escada, nunca é "o que falta" e `dependentes_publicados_de`
devolve `[]` para ela (`publication.py:246`). O campo dela sai com `blocked_by: 0` e
`blocked_phrase: ""`, e isso é estado normal, não lacuna.

**Contra-argumento registrado.** E2 mantém a simetria com o PROVE, que é um molde vivo do produto.
Foi recusada porque a simetria custaria a duplicação exata que a issue proíbe.

### Decisão F — o lote, e quem conhece a ordem da cadeia

> **Proposta do harness.**

| | |
| --- | --- |
| **F1** ⭐ recomendada | **Seleção por subárvore + publicação sequencial na ordem canônica.** Marcar o mapa marca o que pende dele; a tela dispara os `POST` na ordem `Process → Evidence → Finding → PainPoint → ImprovementOpportunity`; falha parcial é relatada item a item com a frase do servidor. |
| F2 | Sem lote: um botão por item. |
| F3 | Endpoint de lote novo no backend. |

**Por quê.** Publicar um Discovery é uma decisão sobre o conjunto (decisão A), e sem lote o operador
dá quinze cliques em ordem que precisa deduzir. F3 seria contrato novo — a issue não o pede e o
recorte não o exige.

**O item bloqueado é selecionável, e é isso que faz o lote existir.** A caixa de seleção existe em
**todo** item não publicado — inclusive no bloqueado —, e marcar cascateia nos dois sentidos: para
baixo, marcando a subárvore; **para cima, marcando o que aquele item precisa que suba antes**. Sem
isso o lote não resolve o caso mais comum, que é a conta onde nada está publicado ainda: ali todo
filho está bloqueado até o pai subir, e o operador voltaria a publicar um por vez esperando a tela
recarregar entre cliques — que é a F2 com passos a mais.

A frase do que falta **continua na linha do item bloqueado**, e o papel dela muda de "por que você
não pode" para "o que precisa ir junto". Ela é a mesma frase do servidor nos dois casos.

**O que a tela passa a saber, e o que ela nunca sabe.** Ela conhece **a ordem** da cadeia, e só a
ordem. Ela nunca decide *se* um item pode ser publicado: quem decide é o servidor, item a item, e
cada falha volta com a frase dele. Isso é deliberado e é o limite: ordenar não é reexpressar a
regra; concluir "isto vai passar" seria.

**A falha parcial é estado desenhado, não caso de borda.** O board a desenha num **momento
diferente** do que a árvore da seção 1 mostra, e com uma seleção maior — nove itens, dois
recusados; a árvore mostra sete. Os dois são ilustração da mesma conta em instantes distintos, e
nenhum número ali é especificação. Nove itens selecionados, dois recusados:
a tela mantém os sete publicados, marca os dois com o motivo do servidor, e não desfaz nada. Está
no board.

**Contra-argumento registrado.** F1 põe no front um conhecimento (a ordem) que hoje só existe no
backend, ainda que não seja a regra em si. F3 removeria isso por completo, ao custo de superfície de
API nova e de um segundo lugar que precisa concordar sobre a ordem.

### Decisão G — ocultar do cliente

> **Proposta do harness.**

| | |
| --- | --- |
| **G1** ⭐ recomendada | No item **preso**, o botão não é oferecido: fica desabilitado, com `blocked_phrase` visível na linha. No item **solto**, `ConfirmDialog` (`Modal.tsx:106-121`) antes de executar. |
| G2 | Botão sempre habilitado; o 409 vira alerta depois do clique. |

**Por quê.** G2 é o botão que sempre falha — o defeito nomeado no PROVE. E o diálogo no caso solto
não é cerimônia: ocultar é retirar do cliente algo que ele **já está vendo**, e o `ConfirmDialog` já
é o padrão da casa para isso em oito páginas, incluindo a `ProcessDetailPage:287`.

**Contra-argumento registrado.** Um botão desabilitado esconde a razão de quem não lê a linha. É por
isso que a frase do impedimento fica **na linha**, não num `title=` — e o board a desenha assim.

---

## Estados desenhados

| Superfície | Estado | No pacote | O que diz |
| --- | --- | --- | --- |
| `/contas/:id/publicacao` | sucesso | sim | A árvore da conta com os quatro estados por item |
| | carregando | sim | Esqueleto (`.skeleton`), sem texto de espera |
| | vazio — conta sem Discovery | sim | `.empty-state`: "Nenhum processo mapeado para esta conta." |
| | vazio — nada pendente | sim | `.empty-state`: tudo já visível; a árvore continua listada |
| | erro de carga | sim | `.alert--error`, texto de `mensagemDeFalha` (`erros.ts:25-32`) |
| | lote em progresso | sim | Botão em "Aguarde…", itens em curso marcados |
| | lote com falha parcial | sim | `.alert--error` de resumo + motivo do servidor por item |
| | diálogo de ocultar | sim | `ConfirmDialog` sobre a árvore |
| | não autorizado | **não** | Inalcançável: os três papéis têm os cinco recursos (`permissions.py:159-166` Vendas, `:205-216` Entrega; admin pelo `is_admin_role`), e sem sessão o `App` nunca resolve a rota (`App.tsx:99`). Declarado, não omitido. |
| `ProcessDetailPage` | selo no processo, no achado e na dor | sim | Leitura, sem ação — a ação é na tela de publicação |
| `AccountDetailPage` | porta de entrada | sim | Terceiro botão da faixa (`:633-638`) |

---

## Procedência de cada valor visual

Nada neste pacote é valor novo. Quase tudo é cópia literal de `frontend/src/index.css`, lido em
2026-09-03; **três elementos vêm de arquivo de componente e não da folha**, e estão nomeados na
segunda tabela — origem em `frontend/src/` continua sendo procedência, mas a distinção fica escrita
em vez de diluída.

| Valor | Origem | Novo? |
| --- | --- | --- |
| `.panel`, `.panel--flush`, `.panel-heading`, `.panel-rows` | `index.css:194-210` | não |
| `.row`, `.row-main`, `.row-meta` | `index.css:213-233` | não |
| `.state` + `--active` (visível) | `index.css:402, 414` | não |
| `.state--off` (oculto) | `index.css:411` | não |
| `.state--1/--2` (selos vizinhos, só para mostrar a convivência) | `index.css:404-405` | não |
| `.btn`, `.btn--secondary`, `.btn--danger` | `index.css` `@layer components` | não |
| `.empty-state` | `index.css:334` | não |
| `.alert--error` | `index.css:338` | não |
| `.eyebrow`, `.page-head`, `.back-link` | `index.css:237, 245-252` | não |
| `.filter-chip` (contadores do cabeçalho) | `index.css:351-355` | não |
| Ícones `Eye` / `EyeOff` | `lucide-react`, mesma família de `PowerOff` (`CobrancaPage.tsx:467`) e `Lock` (`ProjectDetailPage.tsx:941`), ambos já dentro de `.state` com `size-3` | não |
| `ink` `#12110f`, `brand-500` `#bd4a30`, `canvas` `#fafaf9`, `line` `#e7e5e4` | `index.css:38-85` | não |
| `.toolbar` (faixa dos contadores) | `index.css:330` | não |
| `.filter-bar` (agrupador dos `.filter-chip`) | `index.css:350` | não |
| Papéis `--text-display/-title/-body/-label/-meta` | `index.css`, fundações r2 (ADR 0043) | não |

**Os três que não vêm de `index.css`**, e por que não são exceção:

| Valor | Origem | Novo? |
| --- | --- | --- |
| Geometria do `ConfirmDialog` — overlay `bg-ink/45`, painel `rounded-2xl bg-white p-5 shadow-2xl`, botão de fechar `size-8 rounded-lg` | `components/Modal.tsx:78-95` — o diálogo é componente, não classe de folha | não |
| Caixa de seleção — `size-4 rounded border-slate-300`, marca em `brand-500` | `pages/JourneyConfigPage.tsx:88-89`, a única seleção múltipla do produto hoje | não |
| Recuo da árvore (`.nest` no board) — filete `line`, fundos `canvas` e `surface-subtle`, `padding-left` | posicionamento sobre tokens que já existem (`index.css:42, 47, 49`); nenhuma cor nova | não |

O terceiro é o mesmo argumento com que a `.row-meta` foi aprovada no DAP da priorização (a sexta
decisão daquele pacote): compor posição sobre tokens existentes não é valor visual novo. Se a
implementação precisar de uma primitiva para isto, ela é decisão à parte e entra pelo mesmo caminho
que a `.row-meta` entrou — não por julgamento na hora.

Design system referenciado: `frontend/src/index.css` e a skill `portal-design` (matiz **clay**
`#bd4a30` — este é o portal operacional; roxo é o do cliente e nunca aparece aqui). Se este pacote e
essa fonte divergirem, **a fonte vence e este pacote está velho**.

Contraste: os pares em uso já passam AA e estão medidos em `index.css:31-33`. O único par que este
pacote introduz em combinação nova é branco sobre `ink` no `.state--active` — **18,9:1**, o mesmo
par já medido para texto do produto. `e2e/a11y.spec.ts` cobre a tela nova como cobre as outras 24.

---

## Fronteira entre entregue e reservado

| Elemento | Esta feature | Reservado para | Vira real quando |
| --- | --- | --- | --- |
| Tela `/contas/:id/publicacao` com os quatro estados | entrega | — | — |
| Publicação e ocultação em lote | entrega | — | — |
| Selo de leitura na `ProcessDetailPage` | entrega | — | — |
| `published_at`/`published_by` nos cinco tipos TS | entrega | — | — |
| `publication_state` nos cinco serializers | entrega | — | — |
| **Pré-visualização "como o cliente vê"** | desenha espaço apenas | issue própria | Existir um render do bloco do One deste lado; hoje o único jeito de conferir é abrir o portal |
| **Histórico de publicação** (quem publicou o quê, quando) | **não desenha** | issue própria | Existir mais que o carimbo do último ato — `published_by` guarda um autor, não uma trilha |

O elemento reservado aparece no board com a hachura `.reserved` (borda tracejada `brand-200`), e é
**inerte**: não é um botão desligado, é um bloco que anuncia o que virá. Botão inerte é defeito, não
placeholder.

---

## O que a aprovação **não** cobre

- **Backfill.** A ADR 0060 decidiu que nada nasce publicado, e a migração `0075_marca_de_publicavel.py`
  não tem `RunPython` de propósito. Publicar o acervo existente é decisão de operação, e issue
  própria.
- **Mudar a invariante ou as cinco portas.** Entregues, com regressão, e esta issue não as questiona.
- **Regra nova de papel.** Quem escreve o recurso publica, como hoje.
- **`Discovery`, `DiscoverySession`, `ProcessObservation`** — não atravessam, por decisão do contrato
  da `#106`.
- **`ProcessStep` com marca própria.** Anda com o processo pai; decisão registrada na FDD 051, não
  pendência.
- **Endpoint de lote** (F3, recusada) e **`GET /publication-state/`** (B2, recusada).
- **Copy final dos rótulos do servidor.** `ROTULOS` e `_IMPEDIMENTO` já existem e este pacote os
  exibe como estão; reescrevê-los é mudança de copy e precisa de aprovação própria.

---

## Notas para quem implementa

- **Intencional, preserve:** a hierarquia visual mapa → achado → evidência **é** a cadeia (decisão
  C1); o selo de publicação sempre com ícone e sempre no fim da `.row-meta` (D1); a frase do que
  falta e do que prende sempre vinda do servidor (E1); o botão ausente/desabilitado no item preso
  (G1).
- **Ilustrativo, não é especificação:** os dados de exemplo (a conta, os nomes de processo, os
  achados, os números do custo). Nenhum é real e nenhum é conteúdo a ser reproduzido.
- **O que o artefato não mostra:** ordem de foco no teclado, o `aria-label` por linha (a tela tem um
  botão destes por item, e "Publicar" repetido dez vezes não localiza nenhum — mesmo caso já
  resolvido em `ProcessDetailPage.tsx:418`), leitura por leitor de tela dos contadores, e o
  comportamento de rolagem durante o lote.
- **A guarda de primitivas vale aqui** (`src/test/primitivas.test.ts`, ADR 0026): a tela usa
  `.panel`/`.row`/`.state`/`.btn`, nunca o literal equivalente. O mapa de variante do selo devolve
  **variante** (`"state--active"`), nunca a cor.
- **`ConfirmDialog` vive em `components/Modal.tsx:106-121`**, não em um `ConfirmDialog.tsx`.

---

## A oitava decisão, que não estava no pacote quando ele foi escrito

Descoberta na construção, no molde da "sexta decisão" do DAP da priorização: registrada aqui em vez
de virar julgamento silencioso na implementação. **Aprovada em 2026-09-03 por Daniel Campos**, em
registro separado do das sete — elas não a cobriam.

**O item órfão precisa de porta, e o board não desenhou nenhuma.** O pacote desenha a árvore como se
todo `Finding` e todo `PainPoint` citassem um `Process`, e como se toda `Evidence` fosse citada por
algum achado. O schema não garante nada disso: `Finding.process` e `PainPoint.process` são
`SET_NULL` (é o que faz arquivar o processo **não** arquivar os achados, decisão registrada na
FDD 045), e uma `Evidence` pode existir sem achado que a cite.

Numa árvore estritamente hierárquica esses registros simplesmente não apareceriam — e como esta é a
**única** tela que publica, um dos cinco publicáveis ficaria sem porta, atingível só por `curl`.
Isso é o defeito que a issue existe para fechar, reaparecendo pela borda.

**O que foi construído:** eles entram no fim da árvore, em nível raiz, com a descrição dizendo o
quê — "sem mapa citado", "sem achado que a cite". Sem componente novo: são `.row` da mesma lista,
com os mesmos dois selos e a mesma frase do servidor.

**A alternativa recusada** era escondê-los, que é a que o board involuntariamente propõe ao não
desenhá-los. Ela troca uma lista honesta por uma lista bonita e devolve à linha de comando um ato
que este pacote existe para tirar de lá.

**Errata menor, do mesmo lote.** O board desenha selo e botão à direita, na mesma faixa do título; a
primitiva real (`.row-meta`, `index.css:233`) é `flex: 1 1 100%` e **sempre** quebra para a linha de
baixo. A tela seguiu a primitiva. É a regra que o próprio pacote escreve na seção de procedência —
*"se este pacote e essa fonte divergirem, a fonte vence e este pacote está velho"* — aplicada pela
primeira vez, e não uma licença tomada na hora.

## Errata de 2026-09-03 — os números de linha citam o código de antes

Este pacote foi escrito **antes** da implementação e cita o código daquele momento. A entrega
deslocou parte dele — o `PublicationStateSerializer` entrou acima dos cinco serializers e empurrou
todos, entre outras coisas. Os pares mais consultados:

| Citado aqui | Onde está hoje |
| --- | --- |
| `views.py:363-368` (a recusa do `unpublish`) | `views.py:371-373` |
| `ProcessDetailPage.tsx:296-299 / :415 / :428-460` | `:298 / :422 / :466` |
| Serializers em `:1033 :1194 :1318 :1417 :1488` | `:1048 :1211 :1337 :1439 :1510` |

**O pacote não foi corrigido, e a escolha é a mesma do DAP da priorização:** um pacote aprovado é
evidência congelada de um gate, e reescrevê-lo depois faz a aprovação apontar para um texto que
ninguém aprovou. Quem quiser o número de agora consulta a **FDD 052**, que foi escrita a partir do
código entregue. Nenhuma dessas derivas é divergência de comportamento.

## Registro de aprovação

| Campo | Valor |
| --- | --- |
| O que foi aprovado | **As sete decisões e o visual.** Copy: aprovada no que o board mostra; a copy dos rótulos do servidor fica fora (ver "O que a aprovação não cobre"). |
| Aprovado por | Daniel Campos |
| Data | 2026-09-03 |
| Revisão aprovada | 1 |
| Decisões escolhidas | **A1 · B1 · C1** (escolha direta) · **D1 · E1 · F1 · G1** (recomendações do harness, aceitas) · **a oitava** (o item órfão, aprovada depois da construção) |
| Explicitamente **não** aprovado | tudo que está em "O que a aprovação não cobre" |

**Foram duas aprovações, na ordem certa, e o registro guarda as duas.** As sete decisões foram
escolhidas em 2026-09-03, antes de `board.html` e das capturas existirem; o **visual** foi aprovado
depois, sobre o artefato pronto. A distinção não é cerimônia — `design-approval.md` é literal sobre
o que uma aprovação de fato referencia:

> *"A rendering depends on fonts, browser, and platform; the frozen capture is what the approval
> actually refers to."*

O que esta linha aprova é, portanto, `board-desktop.png` e `board-mobile.png` na revisão 1 — não a
descrição delas, e não uma renderização futura de `board.html` em outra máquina.

**Correções aplicadas entre a escolha das decisões e a aprovação visual**, ambas achadas na revisão
do board e registradas para que a leitura do pacote não pareça mais linear do que foi:

1. a caixa de seleção passou a existir em **todo** item não publicado, inclusive no bloqueado — o
   primeiro board a omitia, contra a decisão F1;
2. a tabela de procedência ganhou `.toolbar`, `.filter-bar` e a **segunda tabela** com os três
   valores que vêm de arquivo de componente e não da folha.

Nenhum agente aprova design, inclusive o que o produziu.

A aprovação desta revisão não é aprovação de uma posterior. Um pacote materialmente alterado é uma
revisão nova e precisa do seu próprio registro.

---

## Referências

- Issue `#108` — o pedido; `#106` (contrato e emissão), `#69` (os modelos)
- `biahflow/one#90` e a ADR 0086 de lá — a superfície que espera por esta
- ADR 0060 — publicabilidade é campo próprio, e publicar é o ato de revisão humana da §3
- FDD 051 — o Discovery como dado no snapshot
- `backend/apps/core/publication.py`, `views.py:307-389`
- `frontend/src/pages/ProcessDetailPage.tsx`, `PriorizacaoPage.tsx`, `components/Modal.tsx`
- DAP `docs/design/dap-priorizacao-r1/` — o molde deste pacote
