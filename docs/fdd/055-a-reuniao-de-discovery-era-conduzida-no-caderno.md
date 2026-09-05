# FDD 055 — A reunião de Discovery era conduzida no caderno

> **A tela usada *durante* a reunião de Discovery.** É a terceira e maior das três peças que a
> ADR 0069 liberou sem o gatilho da ADR 0030, e a única que é **superfície de tipo novo**: o produto
> não tinha nenhuma tela usada com uma pessoa digitando enquanto outra fala. Esse tipo tem uma
> propriedade que nenhuma tela atual tem — perder o que foi digitado custa a reunião inteira, e a
> reunião não se repete.

## Jornada

A FDD 039 nomeou o problema no título: *o achado que não sobrevivia à reunião*. Ela resolveu metade
— o que sai da transcrição vira `Process`/`Evidence`/`Finding`, com o rótulo epistemológico imposto
por quem grava. A outra metade nunca teve tela: **a reunião continuava sendo conduzida no caderno**,
e o que ela produzia continuava morrendo ali. A ADR 0030 tinha razão em adiar a modelagem do
Discovery estruturado até haver Discoveries reais; a ADR 0069 registrou por que, *para esta peça*,
aquele critério era circular — esperar Discoveries reais para construir a ferramenta que os conduz é
esperar que o processo estabilize sem instrumento.

Três coisas faltavam, e nenhuma delas é falta de dado.

**As perguntas eram método fora do repositório.** A ficha *Discovery Questions — base genérica* do
Notion tem os seis blocos A–F, o momento de uso de cada um e a regra de saída (*tudo o que sai daqui
entra como evidência declarada, nunca como Baseline*). Nada disso alcançava o Pulse, nem o corpus da
FDD 029.

**`DiscoverySession` existia como registro e não como lugar de trabalho.** Ela guardava
`happened_at`, `participants`, `transcript` e o vínculo com a reunião desde a FDD 045 — o *quando* e
o *quem* do levantamento. O que se anotou durante ela não tinha onde ficar.

**A extração tinha uma origem só.** O coletor que impõe `epistemic_status=hypothesis` era função
aninhada dentro de `MeetingViewSet.estruturar`, o que estava certo enquanto a reunião era a única
porta.

## O que esta fatia entrega

**Uma tela**, `/projetos/:id/sessoes/:sessionId`, com a porta na seção de reuniões do detalhe do
projeto; **uma base de perguntas** servida do backend; **um campo** onde as respostas moram; e **um
coletor só**, agora nomeado, para as duas origens de extração.

Governada pelo DAP `docs/design/dap-discovery-session-e-business-case-r2/`, revisão 2, decisões
**C1 · D2 · E1 · G1 · H3** — mudar a superfície exige revisão nova do pacote, não julgamento na
hora.

## Decisões

### Por que id estável de pergunta, e não índice

A resposta é gravada sob o **id** da pergunta. Guardá-la por posição seria um defeito silencioso com
data marcada: a própria ficha do Notion descreve como a base evolui (*"perguntas que provaram valor
em duas verticais sobem para a base genérica"*), e inserir uma pergunta no meio de um bloco faria a
resposta de ontem aparecer sob a pergunta de hoje — sem erro, sem log, sem nada vermelho. Quem lesse
a sessão veria uma citação de reunião respondendo a outra pergunta, que é a pior forma de dado
errado: plausível.

O id é slug e não número (`q3` seria um índice com outro nome), e é **único na base inteira**, não só
no bloco: uma pergunta que sobe de vertical pode mudar de bloco, e id repetido faria essa mudança
parecer pergunta nova quando é a mesma.

A consequência da remoção fica declarada em vez de escondida: **a resposta de uma pergunta que saiu
da base continua gravada** e deixa de ser exibida. O registro de uma reunião que não se repete não é
apagado por edição de catálogo.

### Por que JSON aqui, e tabela na ADR 0019

A ADR 0019 escolheu tabela para a variante de blueprint, e o argumento dela não era economia de
peças — era a `UniqueConstraint(blueprint, vertical)`: *num JSON a chave duplicada nem chega a
existir, o último valor escrito apaga o anterior em silêncio*.

Aqui a chave **é** o id da pergunta dentro de um dicionário. Duplicata é impossível por construção,
não há segunda coluna para restringir, e nada consulta resposta isolada — o que se lê é a sessão
inteira, na tela que a conduz e na extração que vem depois. Uma tabela `DiscoverySessionAnswer` seria
modelo, serializer, viewset e rota para reproduzir uma unicidade que o tipo já dá de graça.

Sem este parágrafo escrito, a próxima pessoa a ler o campo vai achar que a ADR 0019 foi ignorada.

### Por que o coletor é um só, e por que ele precisou de nome

`grava_o_mapa_extraido` é a única linha do fluxo que decide o que um achado vale, e ela o decide como
constante: `Finding.EpistemicStatus.HYPOTHESIS` e `Evidence.Kind.INTERVIEW`. O `_PROMPT_PROCESSOS`
não pergunta e o `processos_do_texto` não lê — desenho que existe para que o modelo não pareça
decidir.

Enquanto havia uma action só, "o coletor impõe o rótulo" e "toda extração impõe o rótulo" eram a
mesma frase. Com duas, deixaram de ser: uma segunda porta de gravação faria a **invariante 8** do
mapa de linguagem (*`Finding` criado por extração de IA nasce `hypothesis`*) depender de duas
implementações concordarem, e a divergência não deixaria nada vermelho — o banco continuaria
gravando, a tela continuaria desenhando, e o que mudaria seria só o significado.

É exatamente o defeito que a decisão **C1** existe para fechar, visto pelo lado que ninguém vigia:
não é a IA classificando errado, é a tela gravando achado sem passar pelo caminho que impõe o
rótulo. Por isso **a tela nunca grava `Finding`** — ela captura texto, e estruturar continua sendo o
ato explícito, disparado depois, com revisão.

### O autosave: três estados, e o segundo é o que sustenta a decisão

A decisão **D2** foi tomada **contra a recomendação da r1** e traz o primeiro mecanismo de escrita
periódica do produto — não havia de onde herdar: nem `setInterval`, nem `EventSource`, nem
`WebSocket`, nem rascunho local.

1. **Salvando.** Indicador discreto no cabeçalho do bloco (`.state--0`). **Nunca bloqueia o campo**:
   travar a digitação durante a reunião é pior que o risco que o autosave resolve.
2. **Falha.** `.alert--error` fixo no bloco, dizendo **qual foi a última versão salva com sucesso**
   ("a última versão salva é a das 14:38"), e **o botão manual reaparece**. Autosave não elimina o
   botão: ele o esconde enquanto está funcionando. *Um autosave que falha calado é a única variante
   pior que salvar no clique* — foi o contra-argumento da r1, e este estado é a resposta a ele. A
   tela continua tentando, e a retentativa **não apaga o alerta** — nem depois de falhar, nem
   **enquanto está no ar**: voltar o selo para "salvando" ali esconderia o aviso a cada ciclo, e com
   uma requisição que leva segundos para expirar ele acenderia e apagaria sem parar, lendo como "ora
   está salvo, ora não". O alerta sai quando um salvamento **dá certo**, não quando outro começa.
   Reenvio invisível é o defeito, não
   a correção.
3. **O texto nunca é descartado.** Nenhum caminho de falha tira do campo o que a pessoa escreveu, e
   nenhuma resposta do servidor sobrescreve o que está sendo digitado.

**E estruturar espera o pendente.** É o único chamador que aguarda o salvamento — se ele ficou para
trás, a extração **não acontece** e a tela diz por quê. Extrair é ato de uma vez só (o segundo é
409), e fazê-lo sobre um bloco que não chegou ao servidor congelaria o mapa da operação sem ele, sem
ninguém ver falta.

**O intervalo de 2 s é escolha, não medição**, e está escrito para ser corrigido pela primeira sessão
real — como o teto de 90 s da ADR 0064, que a própria ADR registra como folga escolhida. Curto o
bastante para o risco de perder o bloco caber num parágrafo digitado, longo o bastante para não
mandar uma requisição por palavra. O gatilho é a pausa de 2 s, mais salvamento imediato **ao trocar
de bloco** e **ao sair da página** — este último é melhor esforço declarado: o navegador pode
encerrar a requisição antes de ela chegar. A garantia é o intervalo; a saída da página é última
chance, não promessa.

### Por que o **bloco** é a unidade de escrita, e o que H3 aceita

A decisão **H3** também foi tomada contra a recomendação: última escrita vence, **sem aviso**. A tela
não compara versões e não avisa ninguém. A consequência está aceita e escrita no DAP — a anotação do
colega desaparece sem que ninguém veja acontecer, e o que se perde é o registro de uma reunião que
não se repete, o mesmo bem que D2 foi escolhida para proteger. **D2 protege contra a máquina; H3
aceita o risco entre as pessoas.**

O que torna isso administrável é a mitigação de uso que o DAP registra: **um bloco por pessoa durante
a sessão**. Ela só funciona porque a unidade de escrita é o bloco: com a sessão inteira como unidade,
dois consultores em blocos diferentes se apagariam mutuamente a cada dois segundos, e a mitigação
seria letra morta. Por isso a escrita é `POST /discovery-sessions/{id}/notes/` com **um** bloco, e
não um `PATCH` de `notes` — o mesmo argumento de `POST /prove-experiments/{id}/start/` e das duas
portas de publicação: o que se escreve depende do estado corrente, e um `PATCH` do campo inteiro
apagaria os cinco blocos que não vieram no corpo.

`select_for_update` na gravação pela razão do `convert-to-project`: gravar é leitura-modificação-
escrita sobre um JSON, e sem o cadeado dois salvamentos simultâneos de **blocos diferentes**
perderiam um dos dois — a colisão que H3 **não** aceitou, porque ela aceitou a de dentro do bloco.

**O caminho de volta é curto.** Se a perda aparecer em sessão real, **H1** (avisar nomeando quem
editou e quando) é uma issue pequena: comparar `updated_at` do bloco com o que a aba carregou e
mostrar o aviso. Nada nesta fatia fecha essa porta.

### Por que a `ProcessObservation` nasce junto da estruturação da sessão

É o registro que a FDD 045 criou para o mapa revisitado, e é ele que faz *"esta sessão já foi
estruturada"* ser fato no schema em vez de heurística — inclusive para o processo que não rendeu
achado nenhum e por isso não tem `Evidence`. É dele que sai o 409 da segunda extração, pelo motivo da
reunião: `Process` não tem estado de rascunho, e a segunda extração dobraria o mapa da operação do
cliente em silêncio.

## Contrato

Rota nova e duas actions, aditivas, nas duas versões:

| Rota | Método | O que faz |
| --- | --- | --- |
| `/discovery-questions/` | `GET` | A base de perguntas: seis blocos A–F, com id e texto de cada pergunta |
| `/discovery-sessions/{id}/notes/` | `POST` | Grava **um** bloco de respostas, preservando os outros |
| `/discovery-sessions/{id}/estruturar/` | `POST` | O ato explícito: `Process`/`ProcessStep`/`Evidence`/`Finding` + `ProcessObservation` |

Elas nascem nas duas versões de uma vez: o router da `/api/v2/` é derivado do `registry` da v1
(`urls.py`), e a rota fora do router entra pela mesma fábrica `_rotas`.

```json
{
  "blocks": [
    {
      "id": "b",
      "label": "Follow the work (com quem executa)",
      "short_label": "Follow the work",
      "note": "",
      "questions": [{ "id": "casos-por-mes", "text": "Quantos casos desse tipo passam por aqui num mês?" }]
    }
  ]
}
```

`/discovery-questions/` usa `IsAuthenticated` e não `RolePermission`, como o `ConfigView`: não há
objeto, não há escrita, e o método é da casa inteira — quem conduz Discovery é das duas áreas, que é
o mesmo argumento que põe `process` e `evidence` nos dois conjuntos de papel.

Campos novos, todos aditivos e de leitura:

| Campo | Onde | O que é |
| --- | --- | --- |
| `notes` | `DiscoverySession` | `{"<bloco>": {"<id da pergunta>": "<texto>"}}` — sai no `GET`, **não** entra por `PATCH` |
| `structured_finding_count` | `DiscoverySession` | quantos achados vivos saíram desta sessão, anotado na queryset |
| `process_name` · `account` | `ProcessObservation` | o rótulo e o `href` do caminho até quem revisa o processo |
| `source_session` | filtro de `/process-observations/` | ao lado de `discovery` e `process`, como já está em `/evidence/` |

**Nome canônico e nenhum alias**: `notes`, `block`, `answers`, `discovery-questions` e
`structured_finding_count` nascem certos — não há chave antiga que a `/api/v1/` tenha prometido.

`structured_finding_count` é anotação da queryset e não `SerializerMethodField` com consulta própria:
o detalhe do projeto lista as sessões, e uma consulta por linha seria N+1 numa tela que já faz quinze
chamadas. O caminho é `Evidence.source_session` → `findings`, o único elo entre a sessão e o achado —
`Finding` ancora na conta e não conhece sessão nenhuma.

## Superfície

Tela nova em `frontend/src/pages/DiscoverySessionPage.tsx`, rota `/projetos/:id/sessoes/:sessionId`
(decisão **G1**: a `DiscoverySession` pende de `Discovery`, que pende de `Project` — a rota espelha a
posse). **Fora do menu lateral**: a sessão é sempre *de um projeto*, e um item de menu que abre
perguntando "qual?" é o beco já recusado três vezes. A porta é um link por sessão na seção de
reuniões do detalhe do projeto.

A tela usa as primitivas — `.panel`, `.panel-heading`, `.filter-bar`/`.filter-chip`, `.form-label`,
`.field`, `.state`, `.alert--error`, `.btn`, `.eyebrow`, `.page-head`, `.back-link`, `.empty-state` —
e o mapa de estado devolve **variante**, nunca a cor (ADR 0026).

**Nenhuma primitiva nova**, e isso é correção de rumo desta fatia. A primeira versão construiu o
bloco reservado da cronometragem na tela, com uma `.panel--reserved` própria — e o handoff pedia
isso. Estava errado por duas razões que só aparecem lendo os dois pacotes juntos: o DAP irmão diz
que o reservado aparece **no board**, e a tabela de procedência deste declara que *"nenhum valor
visual novo é introduzido"*. O reservado comunica a fronteira ao **aprovador**, não ao operador.

Numa tela usada durante uma reunião de duas horas, um cartão anunciando o que virá ocupa a atenção
que ela existe para poupar — e traria uma classe de CSS cujo único consumidor seria ele mesmo, que é
a dívida que o `CLAUDE.md` cobra desde que `.btn--ghost` e `.card-grid` saíram. O bloco e a classe
foram removidos, e um teste guarda a ausência.

**Três divergências conscientes do board**, e todas por o dado não existir no contrato:

1. **Não há estado "sessão encerrada".** `DiscoverySession` não tem campo de estado, e derivá-lo de
   `happened_at < agora` chamaria a sessão de encerrada **enquanto ela acontece** — a sessão é criada
   com a hora de início. A porta para estruturar fica sempre visível, abaixo dos blocos, e o selo
   "Estruturada" aparece quando ela já foi feita.
2. **O subtítulo não diz o momento da jornada** ("Entrevistas com a operação"). Aquilo é a coluna
   "Momento" da ficha do Notion e não é campo de `DiscoverySession`; a tela mostra os participantes e
   o escopo do Discovery, que são o que existe.
3. **A faixa de blocos usa a forma curta do rótulo**, que vem do backend (`short_label`) e não do
   TypeScript: encurtar o nome na tela criaria uma segunda definição de como o bloco se chama, fora
   da fonte.

A rota entra em `frontend/e2e/matrix.ts` **com fixture cheia** — anotações nos campos e a sessão já
estruturada —, porque um mock vazio aprovaria a tela com os `<textarea>` em branco e sem o painel do
que saiu dela, que é onde moram a faixa de pastilhas e o link, as duas superfícies que 390px aperta.

## Testes

- `backend/apps/core/tests/test_discovery_session.py` — a base pelas duas versões, o id único e em
  minúsculas, **reordenar a base não move resposta gravada** (com o controle positivo de que a
  posição mudou de verdade), a resposta de pergunta removida que continua gravada sem travar o bloco
  vizinho, gravar um bloco preservando os outros, a regravação que vence (H3), o texto em branco
  gravado como veio, bloco e pergunta desconhecidos recusados com o nome do que não existe, a
  pergunta do bloco vizinho que não entra neste, `notes` sem caminho de escrita por `PATCH`, o
  recorte da Entrega, a estruturação com processo/achado/observação, a posição que entra depois do
  que foi mapeado à mão, a sessão vazia que não vai à IA, o 409 da segunda extração, o
  `structured_finding_count` (inclusive com achado arquivado), a criação que não passa pela queryset
  anotada, e as duas metades do contexto que vai ao modelo.
- `backend/tests/regression/test_a_extracao_nasce_hipotese.py` — ganhou a terceira camada: **as duas
  origens passam pelo mesmo coletor**, nenhuma delas grava `Finding`/`Evidence` por conta própria, e
  a extração pela sessão nasce `hypothesis` com o modelo mandando o contrário.
- `frontend/src/pages/DiscoverySessionPage.test.tsx` — as perguntas que vêm do servidor (com a guarda
  de forma de que nenhuma está escrita no arquivo), a gravação sob o id, o campo que nunca bloqueia,
  a troca de bloco que salva antes, o estado de falha com a hora da última versão salva e o botão de
  volta, a retentativa que **não** apaga o alerta, o botão manual, a sessão em branco que não finge
  ter sido salva, a extração que **não acontece** sobre um bloco que ficou para trás, o painel da
  sessão estruturada, o alerta que não pisca durante a retentativa e a ausência do reservado.
- `frontend/src/test/tela-da-sessao-de-discovery.test.ts` — as duas guardas de **forma do código**,
  no molde de `primitivas.test.ts` e fora do `tsconfig.app.json` pelo mesmo motivo (`node:fs` é
  ferramenta, não código de tela): a tela não tem caminho para `/findings` nem `/evidence`, e
  nenhuma pergunta da base está escrita nela.
- `frontend/src/pages/ProjectDetailDiscoverySessions.test.tsx` — a porta: um link por sessão, o selo
  só na estruturada, o projeto sem Discovery e a falha que não derruba a seção de reuniões.

## Fora deste recorte

- **Sugestão de pergunta por IA ao vivo** (C3). Reservada e desenhada como reserva; vira real quando
  a ADR 0031 autorizar canal novo e o custo por reunião for medido.
- **Aviso de edição concorrente** (H1). Recusado em favor de H3; o caminho de volta está nomeado
  acima.
- **Fila offline e reenvio em ordem.** Issue própria, declarada no DAP: o produto não tem de onde
  herdar retentativa, fila nem tratamento de rede intermitente, e o desenho entregue é o mínimo que
  torna o mecanismo seguro de usar numa reunião.
- **Cronometragem do shadowing.** Desenha o espaço e não implementa: vira real quando existir onde
  gravar o par ativo/espera — hoje `ProcessStep.tempo` é texto livre.
- **Estado de sessão** (`encerrada`). Ver a primeira divergência acima; um campo novo aqui é decisão
  de modelo e não cabia nesta fatia.
- **O portal do cliente.** `portal.build_snapshot` não leva nada desta fatia: a Discovery Session já
  não atravessava, e o que vira dado publicável para o cliente é o `Process`/`Finding` que a
  estruturação produz, pela porta da FDD 051.
- **A copy das perguntas.** Elas são espelho da ficha do Notion; reescrever uma pergunta é mudança na
  fonte e passa pela §8 do mapa de linguagem, não por esta FDD.
