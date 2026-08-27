# Design Approval Package — GH-41 · Estado de engenharia do GitHub no detalhe do projeto

Classificação: `INTERFACE_CHANGE` · `BROWSER_REQUIRED`
Revisão: **1**
Status: **Approved**
Data: 2026-08-27
Produzido por: harness (Claude Code), sob [`workflows/design-approval.md`](../../engineering-os/workflows/design-approval.md)

> Este artefato é evidência para um gate humano. Não é implementação e não deve ser copiado para
> dentro do código de aplicação.

## Por que existe um gate novo

A [Issue #41](https://github.com/biahflow/pulse/issues/41) se declara `INTEGRATION_CHANGE` e
`BROWSER_REQUIRED`, e no escopo pede duas coisas que são superfície e não backend:

- *"expose the projected engineering state on the relevant Pulse project/delivery surface"*;
- *"define failure/degraded states for GitHub unavailable, permission denied, reference missing and
  stale projection"*.

Estado degradado, erro, vazio e não autorizado são superfícies que um humano percebe — e são
exatamente as que o `design-approval.md` diz serem descobertas tarde. Classificar isto como
integração e seguir para o Planner deixaria a decisão visual mais importante do recorte (**como o
Pulse mostra que não sabe mais**) para quem estivesse escrevendo o componente.

Não existe aprovação vigente que cubra esta superfície. A [r2](../dap-gh19-r2/README.md) aprovou
fundações e excluiu redesign de tela; o [GH-26 r1](../dap-gh26-r1/README.md) aprovou marca e shell,
e listou "as outras 20 telas de produto" como não entregues. O detalhe do projeto nunca teve DAP.

A camada de dados já existe e **não** é objeto deste pacote: `EngineeringHandoff`
([FDD 040](../../fdd/040-provisionamento-de-issue-github.md)) persiste `repository`,
`github_issue_number`, `github_issue_url`, `correlation_id` e `status`. O que a Issue #41
acrescenta é a projeção de Issue/PR/CI e a sua exposição. Este pacote decide só a exposição.

## Registro de aprovação

| Campo | Valor |
| --- | --- |
| O que foi aprovado | **visual e copy** da revisão 1, como está no `approved-board.png` |
| Aprovado por | o solicitante, explicitamente, nesta sessão |
| Data | 2026-08-27 |
| Revisão aprovada | **1** |
| Explicitamente **não** aprovado | tudo o que a seção *O que a aprovação NÃO cobre* nomeia, sem exceção |

Esta tabela foi preenchida **transcrevendo uma decisão humana explícita**, que é o que
`design-approval.md` permite a um agente (`RECORD_APPROVAL`); `APPROVE_DESIGN` continua vedado, e
**nenhum agente aprova design, inclusive o que o produziu**.

A aprovação veio sem ressalva, cobrindo visual e copy de uma vez. Se a intenção era mais estreita —
aprovar o visual e reter a copy, por exemplo —, esta linha é o lugar de corrigir, e a correção
produz uma revisão nova.

Aprovar o **visual** não aprova a **copy**: são duas decisões, como no GH-26 r1. Toda string do
quadro é copy sendo proposta.

Aprovação da revisão 1 não é aprovação de uma revisão posterior.

## O que é proposta do agente, e não a linguagem estabelecida do projeto

Exigido por `design-approval.md`: *"An agent that produced a package must state which parts are its
proposal rather than the project's established language."*

**Linguagem estabelecida — não está sendo decidida aqui:** a forma `.panel` com cabeçalho
`.metric-icon` + título + descrição; `.panel--flush`/`.panel-rows`/`.row` para lista dividida por
dentro; as cinco variantes `.state--0/1/2/3/off`; `.empty-state`; `.alert--error`; a paleta inteira;
os papéis tipográficos e os raios da r2.

**Proposta do agente — é isto que o humano decide:**

1. a regra do obsoleto (selos ao neutro, proveniência promovida a pastilha `.state--2`);
2. o papel tipográfico **monoespaçado** para SHA e `owner/repo#numero` — o único valor visual novo;
3. o mapa `estado de engenharia → variante` (qual selo cada estado recebe);
4. a posição do painel na página;
5. o tratamento do não autorizado (painel visível com `.empty-state`, em vez de painel oculto);
6. toda a copy;
7. o painel ser uma **lista** de referências e não um cartão único.

## Artefato

| Arquivo | O que é |
| --- | --- |
| [`board.html`](board.html) | Renderização auto-contida. Abre sem build, sem toolchain e sem rede. 44 KB. |
| [`approved-board.png`](approved-board.png) | Captura congelada do quadro. **É a isto que a aprovação se refere.** |

SHA-256 de `approved-board.png`:

```text
c7d2e677c18b50ad89450993de9e65f6b647c68a1a3b1e7cbbd8a813e6f89cb5
```

A captura foi produzida com o Chromium do Playwright já instalado no projeto, a 1280 px de largura
e `deviceScaleFactor: 2`, em página inteira, a partir do `board.html` desta revisão. O carregamento
registrou **zero requisições falhas** — o que prova a auto-contenção exigida pelo item 1 em runtime,
e não apenas por inspeção do fonte.

Uma renderização depende de fonte, navegador e plataforma; a captura congelada é o que a aprovação
de fato nomeia. Se o `board.html` mudar, esta captura e este hash deixam de descrevê-lo, e o que
existe passa a ser uma revisão nova precisando do próprio registro.

## A superfície

Um painel novo — **Engenharia** — no detalhe do projeto (`/projetos/:id`), somente leitura, na mesma
forma dos painéis que já vivem ali (`.panel`, cabeçalho com `.metric-icon`). Cada referência de
GitHub é uma linha, e cada linha carrega quatro obrigações:

| Elemento | Conteúdo |
| --- | --- |
| Identidade | `owner/repo#numero` como link canônico, com o título da Issue ao lado |
| Estado da Issue | aberta / fechada |
| Estado do PR | sem PR / aberto / merged / fechado sem merge |
| Head SHA | sete caracteres, tipografia monoespaçada |
| Estado do CI | verde / vermelho / rodando / sem check configurado |
| Proveniência | **sempre visível** — "Observado há 2 min · webhook" ou "· reconciliação" |

**Nunca se mostra estado sem dizer quando e por onde foi observado.** A linha de proveniência não é
opcional em nenhum dos oito estados, inclusive nos três de erro.

## A regra que este pacote existe para decidir

**Estado obsoleto nunca se apresenta com a cor do estado observado.** Quando a projeção envelhece,
todo selo cai para `.state--off` (neutro) e a linha de proveniência passa a ser o dado principal —
"observado há 3 h", e não "CI verde". Um selo verde que na verdade é de anteontem é pior que nenhum
selo: ele afirma com confiança algo que o Pulse não sabe mais.

O `board.html` renda isso **lado a lado** — o mesmo projeto, com os mesmos dados, fresco e obsoleto —
porque é essa diferença, e não cada quadro isolado, que está sendo aprovada.

O âmbar **troca de lugar** em vez de aparecer: sai dos selos, vai para a proveniência. Assim o âmbar
continua querendo dizer uma coisa só na tela inteira ("atenção neste dado") e não vira sinônimo de
"velho". Nenhum matiz novo entra na regra.

O custo está assumido e escrito: ao cair para o neutro, o painel deixa de responder "o CI passou?"
num relance justamente quando alguém tem pressa. A troca é deliberada.

## Superfícies e estados no pacote

Os oito estados estão no quadro, cada um em seu frame rotulado.

| Superfície | Estado | No pacote |
| --- | --- | --- |
| Painel Engenharia | 1 · sincronizado (sucesso) | sim |
| Painel Engenharia | 2 · **obsoleto** — lado a lado com o 1 | sim |
| Painel Engenharia | 3 · erro: GitHub indisponível | sim |
| Painel Engenharia | 4 · erro: permissão negada | sim |
| Painel Engenharia | 5 · erro: referência ausente (404) | sim |
| Painel Engenharia | 6 · vazio (projeto sem referência) | sim |
| Painel Engenharia | 7 · carregando (esqueleto) | sim |
| Painel Engenharia | 8 · sem autorização (papel `sales`) | sim |
| Painel Engenharia | comando sobre o GitHub | **desenhado como reservado**, não entregue |
| Painel Engenharia | seleção/foco por teclado | **não** — runtime, `BROWSER_REQUIRED` |
| Painel Engenharia | atualização ao vivo com a tela aberta | **não** — comportamento, não forma |
| Lista de projetos, visão geral | qualquer estado | **não** — o painel só existe em `/projetos/:id` |
| One (portal do cliente) | qualquer estado | **não** — fora deste pacote e da Issue #41 |

Os três erros são **três frames e não um**, porque a ação corretiva de cada um é diferente: GitHub
fora do ar passa sozinho; permissão negada exige alguém mexer no token; referência ausente exige
consertar o vínculo. Uma copy única ("não foi possível carregar") esconderia a diferença que decide
quem age.

## Proveniência dos valores visuais

Regra: prefere-se o que já existe. **Nenhum matiz novo entra neste pacote.**

| Valor | Origem | Novo? |
| --- | --- | --- |
| `.panel` (raio 12, borda `line`, `--shadow-card`) e o cabeçalho `.metric-icon` + título + descrição | `frontend/src/index.css` · [`pulse-design-system.md`](../pulse-design-system.md) · composição já em `ProjectDetailPage.tsx:473` e `:804` | não |
| `.panel--flush` + `.panel-rows` + `.row` | `frontend/src/index.css` (`@layer components`) | não |
| `.state`, `.state--0`, `.state--1`, `.state--2`, `.state--3`, `.state--off` | `frontend/src/index.css` · `pulse-design-system.md` | não |
| `.empty-state` | `frontend/src/index.css` · `pulse-design-system.md` | não |
| `.alert--error` | `frontend/src/index.css` · `pulse-design-system.md` | não |
| `.metric-icon` (quadrado `brand-50`/`brand-500`) | `frontend/src/index.css` · cinco painéis desta mesma tela | não |
| Paleta: `ink`, `muted`, `line`, `line-strong`, `canvas`, `surface`, `surface-subtle`, `brand-50/500/600/700`, `info*`, `success*`, `warning*`, `danger*` | `pulse-design-system.md` (tabela de tokens) · `index.css` `@theme` | **não — nenhum matiz novo** |
| Papéis tipográficos *título* 16/24 650, *corpo* 14/22 400, *label* 12/16 600, *meta* 11/16 500 | [`dap-gh19-r2/README.md`](../dap-gh19-r2/README.md) · `.type-*` em `index.css` | não |
| Raios 4 / 8 / 12 e `full` só para pastilha de estado | `dap-gh19-r2/README.md` | não |
| Ícone do painel (*git-branch*) | `lucide-react`, a mesma biblioteca dos outros painéis da tela | não — mas o SVG do quadro é mock |
| **Papel tipográfico monoespaçado** para o head SHA e para `owner/repo#numero` | **Não existe no contrato.** Ver abaixo. | **sim — decidido aqui** |
| **Regra do obsoleto**: selos a `.state--off`, proveniência promovida a pastilha `.state--2` | compõe primitivas existentes; a *regra* não existe | **sim — decidido aqui** |
| **Mapa estado de engenharia → variante** | — | **sim — decidido aqui** |
| **Posição do painel** em `/projetos/:id` | — | **sim — decidido aqui** |
| **Tratamento do não autorizado** (painel visível com `.empty-state`) | — | **sim — decidido aqui** |
| **Toda a copy** | — | **sim — decidido aqui, e separadamente do visual** |

Design system consultado: [`docs/design/pulse-design-system.md`](../pulse-design-system.md) e
[`docs/design/dap-gh19-r2/README.md`](../dap-gh19-r2/README.md), lidos em 2026-08-27.
**Se este pacote e essa fonte divergirem, a fonte vence e este pacote está velho.**

### O único valor visual novo: a monoespaçada

Verificado em `frontend/src/index.css`: o bloco `@theme` declara **apenas** `--font-sans`
(`"Inter Variable", "Inter", "Avenir Next", ui-sans-serif, system-ui, sans-serif`). Não há
`--font-mono`, e `pulse-design-system.md` não lista papel de código na sua tabela de tipografia nem
na de primitivas.

O produto tem hoje **exatamente um** consumidor de monoespaçada, escrito à mão e fora do contrato:
`frontend/src/components/ErrorBoundary.tsx:40` usa o utilitário `font-mono` do Tailwind para o
código da ocorrência. Ele funciona porque o Tailwind v4 traz um `--font-mono` padrão — o que é
diferente de o Pulse ter decidido um.

Por que a decisão importa: SHA e `owner/repo#numero` são identificadores que se comparam caractere a
caractere, e proporcional confunde `1`/`l` e `0`/`O`. Aprovar aqui promove aquele literal a papel
nomeado no contrato — e, pela invariante do repositório de que **toda classe tem consumidor**, o
papel nasce com dois: o SHA deste painel e o código de ocorrência que já existe.

Isto é o que o `design-approval.md` chama de "part of what is being approved". Se for **rejeitado**,
a consequência está escrita: o SHA sai em Inter, e a comparação visual de revisão fica pior.

## Medições de contraste

Todos os pares passam AA para texto normal, e **nenhum depende de cor nova**.

| Par | Razão | Onde aparece |
| --- | --- | --- |
| `slate-600` `#475569` sobre `slate-100` `#f1f5f9` | **6,92:1** | `.state--off` — todo selo neutralizado do Estado 2. É o par que carrega o pacote inteiro. |
| `warning` sobre `warning-50` | **4,84:1** | pastilha de proveniência quando obsoleto; "PR fechado sem merge" |
| `info` sobre `info-50` | **6,16:1** | Issue aberta, PR aberto, CI rodando |
| `success` sobre `success-50` | **5,21:1** | Issue fechada, PR merged, CI verde |
| `danger` sobre `danger-50` | **5,91:1** | CI vermelho, 404 e o `.alert--error` dos Estados 3, 4 e 5 |
| `ink` `#12110f` sobre `surface-subtle` `#f5f5f4` | **17,30:1** | o SHA monoespaçado dentro do chip de código |
| `muted` sobre `surface` | **7,63:1** | linha de proveniência quando fresca; descrição do painel |
| `brand-600` `#a8412a` sobre `surface` | **6,08:1** | o link canônico da referência |

Os quatro pares semânticos são os já medidos e aprovados na r2; os quatro restantes foram calculados
para este pacote e conferem com as medições existentes de `ink`/`muted` do contrato.

**Cor nunca é o único portador.** Cada selo diz em texto o que a cor repete ("CI verde", "CI
vermelho"), e o obsoleto se anuncia por escrito na proveniência — não só pela perda de cor. É o que
faz a regra sobreviver a daltonismo e a impressão em preto e branco. O gate real continua sendo
`frontend/e2e/a11y.spec.ts`: **quando o axe e o tom discordam, cede o tom.**

## Entregue vs. reservado

| Elemento | Esta entrega | Reservado para | Vira real quando |
| --- | --- | --- | --- |
| Painel **Engenharia** somente-leitura e os oito estados | entrega | — | — |
| Linha de proveniência em todos os estados | entrega | — | — |
| Link canônico para a Issue no GitHub | entrega | — | — |
| **Comando sobre o GitHub** — reabrir Issue, re-disparar CI, reprovisionar | **não entrega** | contrato de comando próprio | existir contrato de comando separadamente autorizado |
| Vincular/desvincular referência pela interface | não entrega | mesma reserva | o mesmo contrato de comando |
| Superfície equivalente no One | não entrega | Issue própria | o One entrar em escopo ([ADR 0040](../../adr/0040-pulse-github-one-sem-clickup-ou-make.md)) |
| Tema escuro | não entrega | — | DAP próprio |

A reserva não é conveniência: a própria Issue #41 diz *"do not allow normal Pulse edits to rewrite
GitHub engineering state unless a separately authorized command contract exists"*. Comando é, por
contrato, outro pacote.

**Como o reservado se comporta antes de ser real: ele é ausente.** Na entrega, nenhum dos três
controles é renderizado — nem desabilitado, nem cinza, nem escondido atrás de menu. Controle inerte
no produto é defeito, não marcador de lugar. Eles existem **apenas no `board.html`**, numa faixa
hachurada e tracejada, para que a diferença entre "desenhado" e "construído" não dependa da memória
de quem aprova.

## Decisões que este pacote carrega

1. **Obsoleto nunca veste a cor do observado.** A decisão central, com o custo assumido acima.
2. **O âmbar troca de lugar em vez de aparecer.** Obsolescência poderia ter pintado os selos de
   âmbar; em vez disso os selos ficam neutros e o âmbar vai para a proveniência, preservando um
   significado único para o âmbar na tela.
3. **Os três erros são três frames.** Distinguidos pela ação corretiva, não pela severidade.
4. **O painel é uma lista, não um cartão único.** `EngineeringHandoff.project` é FK com
   `related_name="engineering_handoffs"`: um projeto tem zero, uma ou várias referências. Um cartão
   único obrigaria a eleger "a" referência, e essa eleição não existe no modelo de dados.
5. **Tipografia monoespaçada entra no contrato.** O único valor visual novo do pacote.
6. **Vendas vê o painel, e vê que não vê.** A copy é invariante — a mesma com ou sem referência —,
   então não vaza a existência de trabalho de engenharia; e um painel que some por papel faz a mesma
   tela ter duas formas por motivo invisível. *Alternativa registrada:* não renderizar o painel para
   Vendas. Confirmado em `backend/apps/core/permissions.py:146`: `engineering_handoff` está no
   conjunto de Entrega, não no de Vendas, que cai no `return False`.
7. **Merge não é `DONE`.** "PR merged" é verde de terminal esperado *em engenharia*, e o painel não
   escreve nenhuma palavra de conclusão de negócio — o aceite é do One (ADR 0040).
8. **Posição na página:** depois da Jornada de Transformação e do AI Score, antes de "Equipe do
   projeto". A faixa de "como a entrega está indo" vem antes do elenco e dos catálogos.
9. **O mapa devolve variante, nunca cor** ([ADR 0026](../../adr/0026-as-telas-passam-a-chamar-o-design-system.md)),
   e `frontend/src/test/primitivas.test.ts` é quem cobra isso na implementação.

## O que a aprovação NÃO cobre

- **Tema escuro.** Continua exigindo DAP próprio.
- **A superfície equivalente no One.** Este pacote é o Pulse e só ele.
- **O painel em qualquer tela que não `/projetos/:id`** — visão geral, lista de projetos,
  Configurações, e-mail, documento gerado ou exportação.
- **A copy dos mocks.** Aprovar o visual não aprova a copy.
- **O desenho do endpoint de webhook**, o formato do payload, a chave de idempotência e o algoritmo
  de reconciliação: é contrato de backend, não superfície, e não se decide num quadro.
- **O limiar de obsolescência** em minutos, e se ele é único ou por campo.
- **Qualquer revisão posterior deste pacote.** Aprovar a revisão 1 não aprova a revisão 2.

## Questões em aberto

Nada aqui é resolvido por agente durante a implementação.

- **Quantos minutos é "obsoleto"?** O quadro usa 2 min como fresco e 3 h como velho para que a
  diferença seja legível; é ilustração. O limiar real é decisão de operação.
- **"Revise o token e o escopo da integração em Configurações"** pressupõe um lugar em Configurações
  onde isso se revisa. Hoje a flag `github_provisioning` aparece lá (FDD 040), mas não há tela de
  credencial — sem ela, a frase manda a pessoa a um lugar que não resolve.
- **Review/readiness** aparece no escopo da Issue #41 "quando derivável". O quadro **não** desenha
  selo de revisão: derivar "aprovado" de review do GitHub é decisão de contrato, não de forma.
- **Ordem das referências** na lista — mais recente primeiro, aberta primeiro, ou ordem de criação.
  O quadro mostra duas linhas e não afirma a regra.
- **Referência a PR sem Issue.** O modelo de hoje ancora na Issue; um PR avulso não tem onde morar.

## Notas para quem implementa

- **Intencional e a preservar:** a linha de proveniência em *todos* os oito estados; a queda ao
  neutro sem esconder nem apagar dado; os três erros distintos; o texto de cada selo dizendo o que a
  cor repete; o SHA em sete caracteres; e o painel na mesma forma `.panel` dos vizinhos, sem borda,
  sombra ou raio próprios.
- **Ilustrativo e a não tratar como especificação:** os números de Issue (41, 37), os SHAs
  (`a1b2c3d`, `9f0e7c2`), os títulos, os intervalos de tempo, a largura das colunas e os SVGs
  desenhados à mão no quadro — no produto o ícone vem de `lucide-react`, como nos outros painéis.
- **Este HTML não é fonte.** As classes `.pnl`, `.row`, `.state` do `board.html` são transcrição de
  mock; no produto usam-se as primitivas reais de `index.css`. O `design-approval.md` chama "a mock
  that is also the implementation" de anti-padrão, e a razão é prática: código copiado de mock chega
  sem teste, sem acessibilidade e sem tratamento de estado.
- **O que o quadro não consegue mostrar:** ordem de foco, leitura por leitor de tela do selo
  neutralizado, atualização ao vivo quando o webhook chega com a tela aberta, *reflow* entre 390 e
  1280 px, truncamento de título longo, e movimento. Tudo isso é `BROWSER_REQUIRED` e se valida em
  runtime.
- **Nada de segredo na tela.** O Estado 4 fala de credencial e **não** ecoa token, escopo concedido
  nem resposta da API — a mesma regra que a FDD 040 já impõe a log e a mensagem de erro (NFR-004).
