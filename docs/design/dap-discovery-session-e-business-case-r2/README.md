# Design Approval Package — Discovery Session, Business Case e o próximo passo da conta

Classificação: `INTERFACE_CHANGE` · `BROWSER_REQUIRED`
Revisão: **2**
Status: **Decisões aprovadas · desenho pendente de aprovação**
Data: 2026-09-05
Produzido por: Claude Code (harness), a partir da **ADR 0069**
Supersede: `dap-discovery-session-e-business-case-r1` (mesma data)

> Governado por `docs/engineering-os/workflows/design-approval.md`. Este artefato é evidência para
> um gate humano. Não é implementação e não deve ser copiado para dentro do código da aplicação.

---

## Por que existe um gate

A ADR 0069 decidiu construir as três peças que a ADR 0030 adiou, e as três têm superfície. Duas
delas — Business Case e o próximo passo — poderiam nascer como um bloco a mais numa tela existente,
que é exatamente como se acumula tela sem desenho. A terceira é uma **superfície nova de tipo que o
produto não tem**: uma tela usada *durante* uma reunião de duas horas, com uma pessoa digitando
enquanto outra fala.

Esse tipo tem uma propriedade que nenhuma tela atual tem: **perder o que foi digitado custa a
reunião inteira**, e a reunião não se repete. O produto hoje não tem autosave, polling, websocket ou
rascunho local — a varredura por `setInterval`, `EventSource`, `WebSocket` e `refetch` em
`frontend/src` não retorna nada. Toda tela salva no clique e recarrega. Decidir se essa regra
continua valendo aqui era a razão principal deste gate — **e a r2 registra que ela não continua**:
a decisão D2 traz o primeiro mecanismo de escrita periódica do produto.

---

## O que mudou da r1 para a r2

A r1 foi aprovada em 2026-09-05 **com uma emenda**: a decisão **D** passou de D1 (salvar explícito)
para **D2 (autosave)**. As outras seis foram aceitas como recomendadas.

A emenda não é um ajuste de preferência — ela troca o mecanismo, e o mecanismo arrasta consequências
que a r1 não desenhou. Por isso existe uma r2 em vez de uma errata: **o board da r1 desenha o estado
"alterações não salvas" e um botão "Salvar bloco", e nenhum dos dois é o que foi aprovado.** O
próprio pacote separa as duas aprovações (decisões e desenho), e é essa separação que se está
honrando aqui.

Duas coisas mudam neste documento:

1. A **decisão D** é reescrita com D2 como escolhida, e com as três perguntas que só o autosave
   obriga a responder — o que a tela diz enquanto salva, o que ela diz quando **falha**, e o que
   acontece com o texto já digitado.
2. Nasce a **decisão H**, que a r1 não tinha porque não precisava: com salvamento a cada poucos
   segundos, duas abas na mesma sessão passam a se sobrescrever **em silêncio**. Com salvar-no-clique
   isso era raro o bastante para ninguém desenhar; com autosave é o caso comum de uma reunião com
   dois consultores anotando.

---

## Uma correção de nome, antes das decisões

**O roadmap e a ADR 0030 chamam esta tela de "cockpit de reunião de Discovery". "Cockpit" é termo
banido** — a §5 do Language Map o lista como nome antigo e genérico do One:

| Termo | Por quê | Usar |
| --- | --- | --- |
| "Cockpit", "portal do cliente" | Nome antigo/genérico do One | **One** |

A tela conduz uma `DiscoverySession`, que já é termo canônico na tabela mestra (Pulse:
`DiscoverySession`; Notion: *Discovery Session*). **O nome da superfície é Discovery Session**, e
nenhum termo novo entra por causa dela. Sem esta correção, a primeira linha de código já nasceria
como dívida de linguagem — do tipo que a issue #122 acabou de passar quatro dias pagando.

---

## Artefato

| Arquivo | O que é |
| --- | --- |
| `board.html` | Renderização auto-contida. Abre sem build, sem toolchain e sem rede — nenhum `<script>`. |
| `board-desktop.png` | Captura congelada em 1280px (`deviceScaleFactor: 2`). É a isto que a aprovação se refere. |
| `board-mobile.png` | Captura congelada em 390px. |

A fonte Inter não é embutida; sem ela a página cai no fallback do próprio token `--font-sans`, e o
que muda é o desenho da letra, não a decisão em aprovação.

---

## Onde cada superfície mora

| Superfície | Onde | Situação |
| --- | --- | --- |
| Business Case | dentro de `frontend/src/pages/PriorizacaoPage.tsx`, na oportunidade priorizada | **acrescenta bloco** |
| Próximo passo da conta | `frontend/src/pages/AccountDetailPage.tsx`, acima de "Saúde da relação" | **acrescenta painel** |
| Discovery Session | rota nova `/projetos/:id/sessoes/:sessionId`, `frontend/src/App.tsx` | **nova** |
| Porta da Discovery Session | seção de reuniões de `ProjectDetailPage.tsx` (o formulário e a lista já vivem lá, :772-790) | **acrescenta link por sessão** |

Nenhuma das três entra no menu lateral. Business Case e próximo passo são sempre *de uma conta*, e a
Discovery Session é sempre *de um projeto* — um item de menu que abre perguntando "qual?" é o beco já
recusado duas vezes (DAP priorização r1 decisão A1; `dap-prove-e-valor-r1` decisão D1).

---

## O que está sendo pedido

Oito decisões. **Todas nasceram como recomendação do harness** — nenhuma vem de linguagem já
estabelecida do projeto, e `design-approval.md` exige que isso fique dito, porque sem essa marca o
aprovador não sabe o que está de fato decidindo. O contra-argumento de cada uma fica escrito junto, e
nenhuma vira consenso por ter sido aceita.

**A · B · C · E · F · G** foram aprovadas como recomendadas. **D** foi decidida contra a
recomendação — o aprovador escolheu D2. **H** é nova nesta revisão e segue pendente.

### Decisão A — onde mora o Business Case · **decidida: A1** ✅

| | |
| --- | --- |
| **A1** ✅ | **Dentro da tela de priorização**, expandindo a oportunidade priorizada. A porta só aparece quando há `SolutionHypothesis` escolhida. |
| A2 | Tela própria `/contas/:id/business-cases`. |
| A3 | No detalhe do projeto. |

**Por quê.** O business case é o elo seguinte de uma cadeia que já tem tela — `PainPoint` →
`ImprovementOpportunity` → `PriorityAssessment` → `SolutionHypothesis` mora inteira em
`/contas/:id/priorizacao`. A decisão de investir é sobre a oportunidade priorizada que está na
frente do operador; mandá-lo para outra rota para decidir sobre o que ele já está olhando é perder o
contexto que a tela existe para dar.

**Contra-argumento registrado.** A `PriorizacaoPage` já tem 482 linhas e quatro entidades; esta é a
quinta. Se ela ficar longa demais, o recorte natural é por **conta inteira** (uma tela de decisões de
investimento), não por entidade — e isso é r2, não julgamento na implementação. A3 foi recusada por
erro de ordem: o business case é anterior ao projeto, e frequentemente é o que decide se ele existe.

### Decisão B — onde mora o próximo passo da conta · **decidida: B1** ✅

| | |
| --- | --- |
| **B1** ✅ | **Painel no detalhe da conta**, acima de "Saúde da relação", dizendo qual é a próxima oportunidade e **o que falta nela**. A recomendação que já existe em `/indicadores` passa a ler a mesma função. |
| B2 | Só no topo da tela de priorização. |
| B3 | Continuar só em `/indicadores`, como hoje. |

**Por quê.** A pergunta "onde atuo em seguida neste cliente?" é feita olhando o cliente. Hoje a
resposta existe (`recommendations.py:87` emite `prioritization`) e mora numa lista global de quatro
tipos de sugestão, junto de cobrança e prazo — onde ninguém a procura. **B1 não constrói sinal
novo: constrói leitor**, que é a mesma fatia que a FDD 038 fez para saúde e `dunning_signal`.

O que o painel acrescenta ao que existe é **o que falta**, no molde de
`prove.o_que_falta_para_iniciar`: uma função pura que devolve **chaves, nunca frases** — os rótulos
são da superfície —, com os degraus `escolher hipótese` → `montar business case` → `decidir
investimento` → `abrir venda`.

**Contra-argumento registrado.** Dois lugares mostrando a mesma recomendação podem divergir. Por
isso a decisão inclui a metade que evita isso: **uma função só**, lida pelos dois — se
`recommendations.py` continuar com a query própria dele, a divergência é questão de tempo.

### Decisão C — o que a Discovery Session faz, e o que ela não faz · **decidida: C1** ✅

| | |
| --- | --- |
| **C1** ✅ | **Captura texto por bloco de perguntas.** Estruturar em `Process`/`Evidence`/`Finding` continua sendo o ato explícito que já existe (`POST /meetings/{id}/estruturar/`), disparado depois, com revisão. |
| C2 | A tela grava `Finding` direto, conforme o consultor digita. |
| C3 | A tela captura e a IA estrutura ao vivo, durante a reunião. |

**Por quê.** C2 e C3 quebram a invariante 8 do Language Map (*Finding criado por extração de IA
nasce `hypothesis`*) pelo lado que ninguém vigia: não é a IA classificando errado, é **a tela
gravando achado sem passar pelo caminho que impõe o rótulo**. O coletor da `estruturar`
(`views.py:3261`) atribui `epistemic_status=hypothesis` por constante, e o prompt sequer menciona a
chave — desenho que existe para que o modelo não pareça decidir. Uma segunda porta de gravação
recria exatamente o defeito que aquela decisão fechou.

Há ainda a razão de campo, escrita na própria base de perguntas: *"Não diagnostique na hora.
Enxergou a solução? Anote como hipótese e continue escutando."* Uma tela que estrutura ao vivo
convida o consultor a fazer o que o método proíbe.

**Contra-argumento registrado.** C3 é a promessa mais vistosa das três, e é literalmente o que a
ficha do Notion imagina para a Fase 3 (*"o copiloto pode sugerir perguntas em tempo real"*). Fica
**reservada e desenhada como reserva** — não como botão desligado.

### Decisão D — como o trabalho da sessão é salvo · **decidida: D2** ✅ *(contra a recomendação)*

| | |
| --- | --- |
| **D2** ✅ | **Autosave**: o bloco salva sozinho, com estado visível — e o botão manual reaparece quando o automático falha. O primeiro mecanismo de escrita periódica do produto. |
| D1 ⭐ (recusada) | Salvar explícito por bloco, com indicador de pendência. Era a recomendação da r1. |
| D3 | Rascunho em `localStorage` + salvar explícito. |

**Por que foi escolhida.** O risco que a r1 aceitava é real, e o aprovador recusou aceitá-lo: uma
queda de aba no minuto 90 leva o bloco corrente, e a reunião de duas horas não se repete. Salvar no
clique transfere para o consultor — no meio de uma conversa que ele está conduzindo — a
responsabilidade de lembrar de uma tecla.

**O que D2 obriga a desenhar, e a r1 não desenhava.** Três perguntas, e a segunda é a que sustenta a
decisão:

1. **Enquanto salva.** Indicador discreto no cabeçalho do bloco, no mesmo lugar onde a r1 mostrava
   "Salvo às 14:38". **Nunca bloqueia o campo** — travar a digitação durante a reunião é pior que o
   risco que o autosave resolve.
2. **Quando falha.** `.alert--error` fixo no bloco, dizendo **qual foi a última versão salva com
   sucesso** ("última versão salva às 14:38"), e **o botão manual reaparece** como saída. Autosave
   não elimina o botão: ele o esconde enquanto está funcionando. *Um autosave que falha calado é a
   única variante pior que salvar no clique* — foi o contra-argumento da r1, e este desenho é a
   resposta a ele.
3. **O que acontece com o texto.** Nada. O texto digitado permanece no campo em qualquer estado de
   falha, e a tela continua tentando. **Nenhum caminho deste desenho descarta o que a pessoa
   escreveu** — nem no conflito da decisão H.

**Gatilho:** 2 s após a última tecla, mais salvamento imediato ao trocar de bloco e ao sair da
página. O intervalo é escolha, não medição, e está escrito aqui para ser corrigido pela primeira
sessão real — como o teto de 90 s da ADR 0064, que a própria ADR registra como folga escolhida.

**O que fica devendo, e é honesto dizer.** O produto não tem nada de onde herdar: nem retentativa,
nem fila, nem tratamento de rede intermitente. O desenho acima é o mínimo que torna o mecanismo
seguro de usar numa reunião; fila offline e reenvio em ordem são issue própria e **não** estão neste
pacote.

### Decisão E — de onde vêm as perguntas · **decidida: E1** ✅

| | |
| --- | --- |
| **E1** ✅ | **Constante congelada no backend**, espelho da ficha *Discovery Questions* do Notion, servida por rota — no molde de `kickoff.KICKOFF_TEMPLATES` e `invoices.INVOICE_SCHEDULES`. |
| E2 | Entidade editável no Pulse (uma base de perguntas com CRUD). |
| E3 | Constantes no frontend. |

**Por quê.** As perguntas são método, e o método tem fonte: a ficha do Notion, com os blocos A–F, os
momentos de uso e a regra de saída (*tudo o que sai daqui entra como evidência declarada, nunca como
Baseline*). E2 duplicaria essa fonte como dado editável, e a mesma pergunta passaria a existir em
dois lugares divergindo em silêncio — a alternativa que a ADR 0069 já recusou por escrito. E3 põe
método no cliente, onde nem o corpus nem os agentes o alcançam.

**Contra-argumento registrado.** E1 significa que mudar uma pergunta é PR, não edição de tela. Isso é
fricção deliberada — a mesma do corpus de conhecimento, que é artefato gerado e commitado.

### Decisão F — a lacuna do custo no Business Case · **decidida: F1** ✅

| | |
| --- | --- |
| **F1** ✅ | **`—`, com a frase do servidor dizendo por que**, quando nenhum processo da oportunidade tem custo sustentado. |
| F2 | `R$ 0,00`. |
| F3 | Esconder a linha. |

**Por quê.** É a regra do `nao_apurado` (`process.py:71`), literalmente: *"`total = 0` com
`nao_apurado` cheio não significa 'custa zero'. Significa 'não há insumo para dizer'"* — e a mesma
regra que a decisão C1 do `dap-prove-e-valor-r1` já aplicou ao KPI (*a lacuna é `—`, nunca `0`*).
F3 é pior que F2: esconder faz o operador aprovar um investimento sem notar que o lado do custo
está vazio.

**Contra-argumento registrado.** Nenhum sério. Fica listada para o registro ficar completo.

### Decisão G — rota e porta da Discovery Session · **decidida: G1** ✅

| | |
| --- | --- |
| **G1** ✅ | `/projetos/:id/sessoes/:sessionId`, com a porta na seção de reuniões do detalhe do projeto. |
| G2 | `/discovery-sessions/:id`, rota de primeiro nível. |
| G3 | Modal sobre o detalhe do projeto. |

**Por quê.** A `DiscoverySession` pende de `Discovery`, que pende de `Project` — a rota espelha a
posse. G3 foi recusada por tipo de uso: um modal de duas horas não é modal, e o produto usa modal
para ato curto (`components/Modal.tsx`).

**Contra-argumento registrado.** G2 seria mais curta e é o que o backend expõe (`/discovery-sessions/`).
A rota da SPA e a da API não precisam coincidir — e aqui a da SPA carrega contexto que o operador
precisa ver no breadcrumb.

### Decisão H — duas pessoas na mesma sessão · **recomendada: H1** ⭐ *(nova na r2)*

| | |
| --- | --- |
| **H1** ⭐ | **Última escrita vence, e a tela avisa.** Se o bloco mudou no servidor desde que esta aba o carregou, aparece um aviso nomeando quem editou e quando, com o texto do outro à vista antes de qualquer sobrescrita. |
| H2 | Bloqueio por bloco: quem abre primeiro edita, os demais leem. |
| H3 | Última escrita vence, em silêncio. |

**Por quê, e por que ela só existe agora.** Uma sessão de Discovery costuma ter dois da casa — um
conduz, o outro anota. Com salvar-no-clique, duas abas colidiam raramente e o autor percebia. **Com
autosave a cada 2 s, H3 é perda de dado invisível**: o bloco do colega desaparece sem que ninguém
tenha visto acontecer, e o que se perde é a anotação de uma reunião que não se repete. A decisão D2
criou esta pergunta; ela não existia na r1.

H2 foi recusada por custo desproporcional: bloqueio exige heartbeat, expiração e uma tela para
"destravar", e nada disso é barato num produto que até ontem não tinha escrita periódica. H1 aceita
que a última escrita vença — mas nunca em silêncio, que é a única parte que importa.

**Contra-argumento registrado.** H1 não impede a sobrescrita, só a torna visível; dois consultores
digitando no mesmo bloco ao mesmo tempo ainda produzem um resultado que nenhum dos dois escreveu por
inteiro. A mitigação real é de uso (um bloco por pessoa), e o aviso é o que a torna possível.

---

## Estados desenhados

| Superfície | Estado | No pacote | O que diz |
| --- | --- | --- | --- |
| Business Case | oportunidade sem hipótese escolhida | sim | não oferece a porta; diz o que falta antes |
| Business Case | hipótese escolhida, sem business case | sim | porta para criar |
| Business Case | rascunho | sim | os dois números editáveis, custo congelado ao lado |
| Business Case | **custo não apurado** | sim | `—` e a frase do servidor (F1) |
| Business Case | aprovado | sim | imutável, com autor e carimbo da decisão |
| Business Case | recusado | sim | idem, e a oportunidade aceita outro |
| Próximo passo | conta sem nada priorizado | sim | vazio honesto, com link para a priorização |
| Próximo passo | os quatro degraus do que falta | sim | um por vez, o primeiro que falta |
| Próximo passo | tudo encaminhado | sim | estado neutro, sem inventar urgência |
| Discovery Session | bloco em captura, salvo | sim | carimbo do último salvamento |
| Discovery Session | **salvando** | sim | indicador discreto, campo nunca bloqueia (D2) |
| Discovery Session | **falha ao salvar** | sim | alerta com a última versão salva + botão manual de volta (D2) |
| Discovery Session | **editado por outra pessoa** | sim | aviso com autor e horário, sem descartar texto (H1) |
| Discovery Session | sessão encerrada | sim | leitura, com a porta para estruturar |
| Discovery Session | estruturação já feita | sim | selo e link para os processos gerados |

---

## Procedência de cada valor visual

Tudo o que o board usa vem de `frontend/src/index.css`: `.panel`, `.panel--flush`, `.panel-heading`,
`.panel-rows`, `.row`, `.row-main`, `.row-meta`, `.eyebrow`, `.page-head`, `.btn` (+ `--secondary`),
`.form-label`, `.field`, `.empty-state`, `.state` (+ `--0/--1/--2/--off/--active`), `.filter-chip`,
`.alert--warn`, `.back-link` e os papéis tipográficos `.type-*`.

**Nenhum valor visual novo é introduzido.** Dois usos merecem nota:

| Valor | Origem | Novo? |
| --- | --- | --- |
| Indicador de "não salvo" | `.state--2` (warning), o mesmo par já medido | não |
| Faixa de blocos A–F | `.filter-chip` / `--on`, o padrão de filtro já usado em Contas | não |

Design system referenciado: `frontend/src/index.css` e a skill `portal-design` (matiz **clay**
`#bd4a30` — este é o portal operacional; roxo é o do cliente e nunca aparece aqui). Se este pacote e
essa fonte divergirem, **a fonte vence e este pacote está velho**.

Contraste: nenhum par novo. `e2e/a11y.spec.ts` cobre as telas novas como cobre as outras 24, e a
Discovery Session entra na matriz por uma linha.

---

## Fronteira entre entregue e reservado

| Elemento | Esta feature | Reservado para | Vira real quando |
| --- | --- | --- | --- |
| Os três blocos/telas com os estados acima | entrega | — | — |
| Perguntas A–F servidas do backend | entrega | — | — |
| **Cronometragem do shadowing** (ativo vs. espera, por marco) | desenha espaço apenas | issue própria | Existir onde gravar o par ativo/espera — hoje `ProcessStep.tempo` é texto livre |
| **Sugestão de pergunta por IA ao vivo** (C3) | desenha como reserva | issue própria | A ADR 0031 autorizar canal novo e o custo por reunião ser medido |
| **Autosave com estado visível e saída manual** (D2) | entrega | — | — |
| **Aviso de edição concorrente** (H1) | entrega | — | — |
| **Fila offline e reenvio em ordem** | **não desenha** | issue própria | Rede intermitente aparecer em sessão real |
| **Gráfico de retorno do Business Case** | **não desenha** | — | Nunca por padrão: dois números não pedem gráfico |

O reservado aparece com a hachura `.reserved` (borda tracejada `brand-200`) e é **inerte**: não é
botão desligado, é bloco que anuncia o que virá.

---

## O que a aprovação **não** cobre

- **O backend do Business Case**, em construção com aceite de API (precedente da FDD 040). Este
  pacote decide a tela, não o modelo.
- **A invariante "todo achado nasce hipótese"** — a decisão C1 a preserva, não a discute.
- **A copy das perguntas.** Elas são espelho da ficha do Notion; reescrever uma pergunta é mudança
  na fonte e passa pela §8, não por este gate.
- **Regra nova de papel.** Quem escreve a cadeia PRIORITIZE decide o business case, como hoje.
- **O que atravessa para o One.** `BusinessCase` não atravessa (Language Map v1.5), e a Discovery
  Session já não atravessava.
- **Mudar `recommendations.py` de contrato** — o `kind` `prioritization` continua saindo como sai.

---

## Notas para quem implementa

- **Intencional, preserve:** a porta do business case só existe com hipótese escolhida (A1); o
  próximo passo mostra **um** degrau, o primeiro que falta, e a função devolve chave, não frase (B1);
  a tela nunca grava `Finding` (C1); o autosave **nunca bloqueia o campo**, **nunca descarta texto** e
  **devolve o botão manual quando falha** (D2); o aviso de edição concorrente nomeia autor e horário
  (H1); a lacuna é `—` (F1).
- **A parte de D2 que é fácil errar:** o estado de falha. Um `catch` silencioso com retentativa
  invisível reproduz exatamente o defeito que a decisão existe para evitar. Se o salvamento falhar, a
  tela **diz**, mostra a hora da última versão salva e devolve o controle.
- **Ilustrativo, não é especificação:** os dados de exemplo (a conta, os processos, os números do
  custo, os nomes das pessoas). Nenhum é real.
- **O que o artefato não mostra:** ordem de foco no teclado durante a sessão (é a tela mais usada por
  teclado do produto e merece atenção), o `aria-label` por bloco, o comportamento com transcrição
  muito longa, e o que acontece se dois consultores abrirem a mesma sessão.
- **A guarda de primitivas vale aqui** (`src/test/primitivas.test.ts`, ADR 0026): use `.panel`,
  `.row`, `.state`, `.btn`, nunca o literal equivalente. Mapa de estado devolve **variante**.
- **"Cockpit" não aparece em nome de arquivo, rota, componente, módulo ou copy.** É termo banido.

---

## Registro de aprovação

| Campo | Valor |
| --- | --- |
| O que foi aprovado | **As decisões** — o texto das oito seções acima |
| Aprovado por | Daniel Campos |
| Data | 2026-09-05 |
| Revisão aprovada | r1 para A · B · C · E · F · G; **r2** para D e H |
| Decisões escolhidas | **A1 · B1 · C1 · D2 · E1 · F1 · G1**; **H1** pendente |
| Explicitamente não aprovado | O **desenho** desta revisão: `board-desktop.png` e `board-mobile.png` da r2 mudaram nos estados de salvamento e ainda não foram aprovados |

Duas aprovações são distintas e devem ser registradas separadamente: **as sete decisões** (o texto
acima) e **o desenho** (as capturas congeladas `board-desktop.png` e `board-mobile.png`, não uma
renderização futura de `board.html`).

Nenhum agente aprova design, inclusive o que o produziu.

---

## Referências

- **ADR 0069** — o que a 0030 adiou entra sem o gatilho que ela pediu
- ADR 0030 e ADR 0034 — a regra de espera e o teste que a exerceu
- `docs/ontology/language-map.md` v1.5 — `BusinessCase` cunhado; "Cockpit" banido (§5)
- `dap-prove-e-valor-r1` — a lacuna `—` e o "fora do menu lateral"
- `dap-publicacao-discovery-r1` — o molde deste pacote
- FDD 039, 045, 048, 049 — a cadeia que estas telas fecham
