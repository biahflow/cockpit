# ADR 0043 — A marca Pulse no shell, e as fundações r2 finalmente consumidas

**Status:** aceita
**Data:** 25/08/2026
**Fase:** transversal — front-end do portal operacional
**Revisa:** ADR 0024 e ADR 0025 (na parte de marca) · **Consome:** ADR 0041
**Gate de design:** [DAP GH-26 r1](../design/dap-gh26-r1/README.md), aprovado em 25/08/2026

## Contexto

Havia três coisas verdadeiras ao mesmo tempo, e nenhuma delas conversava com as outras.

A **ADR 0041** aprovou o Pulse Design System: tokens semânticos, escala tipográfica com papéis
nomeados, contrato de raio e de elevação. O DAP r2 que a sustenta diz, em uma linha, o que ela não
cobria: *"Fora: redesign amplo/shell"* (`docs/design/dap-gh19-r2/README.md:44`). As fundações
existiam e o shell não as consumia.

O **PR #27** entregou `pulse-mark.svg` e o componente `PulseBrand`, e a documentação do próprio
asset avisava que aquilo não era autorização para usá-lo: *"Broad shell adoption remains an
`INTERFACE_CHANGE`"* (`assets/brand/README.md:18`). A marca existia e ninguém a via.

A **ADR 0030** havia chamado o produto de Cockpit; a **0041** o chama de Pulse. Enquanto isso a
barra lateral dizia "Biahflow", o rastro do topo dizia "Biahflow", o login dizia "Biahflow" e o
convite mandava a pessoa "entrar no Portal Biahflow". Um produto com nome novo em três documentos e
nome antigo em toda superfície que o usuário abre.

O custo disso não é estético. É que **cada uma das três ficava esperando a outra**: quem fosse
aplicar a marca teria de decidir sozinho o raio do item de menu, e quem fosse aplicar as fundações
teria de decidir sozinho o que escrever na barra lateral. As duas decisões cabem no mesmo diff
porque tocam os mesmos quatro arquivos, e separá-las produziria dois commits que ninguém consegue
revisar isoladamente.

## Decisão

### 1. O produto se apresenta como **Pulse**; Biahflow é a casa

A barra lateral, a gaveta do celular e a raiz do rastro dizem Pulse. Biahflow permanece — e
permanece de propósito — onde é a empresa que fala: o subtítulo do sidebar ("Operação Biahflow"), o
eyebrow do login (a mesma frase, no lugar de "Portal operacional"), o rodapé do login ("Biahflow ·
processos que fluem", intocado) e a copy de acesso ("Seu acesso é gerenciado pela administração da
Biahflow").

Aprovar visual não aprova copy, e por isso o DAP registra as duas aprovações separadas, com as
strings exatas escritas no quadro. O convite passou de "Portal Biahflow" para "Pulse".

A `roadmap.md:512` continua chamando o produto de Cockpit. **Esta ADR não reconcilia aquilo** —
está registrado como questão em aberto no DAP, e trocá-lo aqui seria mexer em planejamento a
pretexto de mexer em CSS.

### 2. A marca é o asset canônico, e ganha uma variante para o escuro

O glifo `B` desenhado em CSS sai; entra o `<img>` do `pulse-mark.svg`, consumido pelo `PulseBrand`.
Nunca colado inline: duplicar o SVG é duplicar a geometria da marca, e a segunda cópia é a que
diverge.

O escuro precisou de um arquivo próprio, e a razão é medida:

| Par | Razão | |
|---|---|---|
| Mark clay `#BD4A30` sobre `brand-900` `#5C2317` | **2,45:1** | o mark **some** |
| Mark invertido `#FFFFFF` sobre `brand-900` | 12,3:1 | legível com folga |
| Traço clay dentro do tile branco | 5,02:1 | passa AA |

`pulse-mark-inverse.svg` tem a **mesma geometria** — mesmo `viewBox`, mesmo `rx`, mesmo path, mesma
espessura, mesmos remates. Troca-se o preenchimento e nada mais.

Vale nomear o que isto ensina, porque é o inverso do que a ADR 0025 aprendeu: **o axe não teria
pego este**. O mark é decorativo (`aria-hidden`), e a regra `color-contrast` mede texto. Lá o gate
automático decidiu contra o gosto; aqui não havia gate, e a medição teve de ser feita à mão. Ter um
portão não dispensa medir o que ele não olha.

### 3. `PulseBrand` ganha nome acessível, e o modo que podia não ter nome **sai**

O componente entregue pelo PR #27 renderizava o mark com `alt=""` e `aria-hidden="true"`, e no modo
`compact` não sobrava texto nenhum: o `<a href="/">` que o embrulha ficaria **sem nome acessível** —
violação `link-name` do axe, nas três larguras. É defeito latente, não regressão: o modo não tinha
chamador.

Havia duas saídas — dar ao modo um nome escondido (`sr-only`, ou `alt="Pulse"` condicional) ou
tirar o modo. Ficou a segunda, **pela mesma regra que faz `.brand-mark` sair neste diff**: a prop
não tinha um único chamador, e não se remove uma classe por ter perdido o consumidor na mesma
entrega em que se faz crescer um ramo que nunca teve nenhum. `subtitle={null}` já entrega o lockup
denso, que é a única compressão que este produto pediu.

O que sobra é mais simples de justificar do que a alternativa: o wordmark é **sempre visível**, o
`<img>` é **sempre decorativo**, e o nome acessível do link é o texto que a pessoa lê. Um nome que
só existe para leitor de tela é o primeiro a divergir do wordmark quando alguém troca um dos dois; e
um `alt` que alterna entre decorativo e portador do nome conforme uma prop é o tipo de condicional
que diverge sozinha quando aparece o terceiro modo.

O subtítulo default deixou de ser "Biahflow operational command center". Um produto em pt-BR não
tem por que se apresentar em inglês na primeira linha que a pessoa lê.

### 4. As fundações r2 passam a ser consumidas pelo shell, não só declaradas

**Raio.** O contrato é 4 detalhe · 8 controles · 12 cartões e popover · `full` só status e avatar.
`.nav-item`, `.icon-button`, `field` e o novo `.user-button` caem para 8; `.metric-icon` cai para 8
por ser quadrado de ícone; o cartão do login sobe de 24 para 12. `.panel`, `.popover`,
`.metric-card` e `.sidebar-note` já estavam certos.

Duas exceções ficam **de pé e declaradas**: `.icon-button` continua em `size-10` porque 40px é
WCAG 2.5.8 e `e2e/responsive.spec.ts` mede — muda o raio, não o alvo; e `.filter-chip` continua
`rounded-full` contra o contrato, porque está explicitamente reservado no DAP para quando Leads e
Clientes entrarem em escopo. Exceção escrita é dívida; exceção não escrita é defeito.

**Tipografia.** Pixel cravado vira papel: `.nav-item` de `text-[13px]/500` para *label* (12/16,
600); `.nav-label` de `text-[10px]/800` para *meta* (11/16) com peso 700; `.breadcrumb` e
`.metric-card span` para *meta*; a rota atual do rastro para *label*; os popovers para *corpo*.

O item de menu é **a decisão mais discutível do pacote**, e foi aprovada explicitamente: cai um
pixel e sobe o peso. A alternativa registrada — manter 13px e acrescentar um papel "nav" ao design
system — foi **rejeitada**, porque seria estender o contrato em vez de consumi-lo, e um contrato que
ganha um papel toda vez que uma tela não cabe nele deixa de ser contrato.

Onde o papel foi consumido pela metade, está escrito por quê: `.nav-label` e `.avatar` ficam com o
corpo do papel *meta* e um peso maior, porque caixa alta com `tracking` largo e duas iniciais dentro
de um círculo de 32px viram borrão no peso 500.

**Elevação.** A sombra clay `rgba(189,74,48,.32)` do `.brand-mark` e o `shadow-lg shadow-ink/10` do
cartão de pipeline saem. Cartão é `--shadow-card`, popover é `--shadow-pop`, o cartão do login é
`--shadow-raised`. Não sobra sombra avulsa no shell.

### 5. O literal vira primitiva, e a classe sem chamador sai no mesmo diff

Três nascem já chamadas: `.metric-card--dark` (o cartão de pipeline, que era literal integral e não
chamava primitiva nenhuma), `.metric-icon--danger` (que substitui `bg-red-50` pelo token
`danger-50`) e `.user-button` (o botão de usuário da topbar, a única forma do shell sem nome).

E `.brand-mark` **sai**, porque perdeu o último consumidor quando o `<img>` entrou. É a regra da ADR
0024 aplicada de novo, e ela vale nas duas direções: classe nova sem chamador e classe velha que
perdeu o dela são a mesma dívida.

Uma nota de especificidade que custou uma armadilha: dentro de um `.metric-card`, o seletor
`.metric-card span` (0,1,1) é mais específico que `.metric-icon` (0,1,0) e venceria a cor do ícone —
**foi por isso que a versão anterior escreveu `bg-red-50 text-danger` inline**. As variantes são
`.metric-icon.metric-icon--danger` (0,2,0) para ganharem sem o literal. Quem escreve uma primitiva
que perde para o contexto acaba de fabricar o próximo literal inline.

## Consequências

- O `Layout.test.tsx` cobria **só** o filtro de menu por papel: nada ficaria vermelho se a marca
  sumisse ou se o shell voltasse a se chamar Biahflow. Ganhou três regressões — a marca Pulse, a
  raiz do rastro, e o nome acessível do link. Um teste de shell que consulta por papel e por texto
  sobrevive a um redesenho de shell; um que consulta por classe, não.
- `field` em raio 8 alcança **toda tela com formulário**, não só o shell. É mudança visual ampla
  vinda de uma linha, e foi validada pela matriz inteira do axe.
- A API pública do `PulseBrand` **encolheu**: `compact` saiu, `tone` entrou, `subtitle` aceita
  `null`. Quem precisar de um lockup só de mark — favicon de aplicação, e-mail, exportação — abre a
  discussão do nome acessível junto, em vez de herdar um modo que já vinha sem ele.
- O que **não** mudou, e é o que a Issue cobra: o filtro de navegação por papel com `is_admin` antes
  de `role`, o `nav()` único servindo as duas larguras, o `useEscape` devolvendo foco ao botão que
  abriu, as notificações, o logout e todos os atributos ARIA. A forma da ADR 0025 — barra clara,
  254px, menu rolando por dentro, breakpoint `lg` — está preservada inteira. **O que muda é a
  marca e as fundações, não o shell.**
- A gaveta do celular continua **sem** overlay, `focus trap`, `aria-modal` e `Escape`. Ela não tem
  nenhum deles hoje; acrescentá-los está reservado no DAP para Issue própria. Preservada, não
  melhorada.
- Tema escuro, `.filter-chip` e as outras 20 telas de produto seguem fora. Cada um exige o próprio
  gate: aprovar esta revisão não aprova a próxima.

## Verificação

`npm run lint`, `npm test` (33 arquivos, 279 testes · linhas 82,93%), `npm run build` e `npm run e2e`
(172 testes), todos verdes. O gate que decide cor aqui é `e2e/a11y.spec.ts` — 24 telas × 3 larguras,
com contraste AA —, e ele passou sem exceção nova. `src/test/primitivas.test.ts` segue com a
allowlist **vazia**.

A entrega é `BROWSER_REQUIRED`, e três afirmações dela não sobrevivem ao jsdom: **qual arquivo** o
`<img>` foi buscar, se o **contorno de foco** aparece no link da marca, e se a **gaveta aberta**
passa no axe. `e2e/marca.spec.ts` mede as três, e afirma pelo conteúdo do asset e não pelo nome do
arquivo — o Vite embute SVG abaixo de `assetsInlineLimit` como `data:` URI, então o nome do arquivo
passaria numa configuração e reprovaria na outra sem que nada de verdade tivesse mudado.

**A gaveta aberta era o ponto cego, e agora tem gate.** A matriz do `a11y.spec.ts` varre 390px com
a gaveta **fechada**: o menu do celular nunca esteve no DOM na hora da varredura, e era justamente
a superfície que esta entrega mudou. Aberta, o axe devolve **zero violações** — o que também mostra
que os dois links `href="/"` que passam a coexistir no celular (o da barra escondida e o da gaveta)
não criam achado. O mesmo spec produz a evidência de runtime do DAP quando
`PULSE_DAP_EVIDENCE_DIR` está no ambiente, no desenho que a r2 já usava.
