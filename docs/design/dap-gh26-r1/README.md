# Design Approval Package — GH-26 · Marca Pulse v1 e fundações r2 no shell

Classificação: `INTERFACE_CHANGE` · `BROWSER_REQUIRED`
Revisão: **1**
Status: **Approved**
Data: 2026-08-25
Produzido por: harness (Claude Code), sob `workflows/design-approval.md`

> Este artefato é evidência para um gate humano. Não é implementação e não deve ser copiado para
> dentro do código de aplicação.

## Por que existe um gate novo

A r2 (Issue #19) aprovou tokens, tipografia, espaço, raio e elevação — e **excluiu explicitamente
"redesign amplo/shell"** do que estava sendo decidido (`docs/design/dap-gh19-r2/README.md:44`). O
asset da marca (PR #27) declara na própria documentação que *"broad shell adoption remains an
`INTERFACE_CHANGE` and must follow the applicable EngineeringOS Design Approval / browser
validation lifecycle"* (`frontend/src/assets/brand/README.md:18`).

Não existe, portanto, aprovação vigente que cubra esta superfície. Aprovar a r2 não aprova esta
revisão, do mesmo modo que aprovar esta revisão não aprovará a próxima.

## Registro de aprovação

| Campo | Valor |
| --- | --- |
| O que foi aprovado | **visual e copy** da composição do shell, da visão geral e das telas de autenticação |
| Aprovado por | o solicitante, explicitamente, nesta sessão |
| Data | 2026-08-25 |
| Revisão aprovada | **1** |
| Explicitamente **não** aprovado | tema escuro; as outras 20 telas de produto; `focus trap`/`Escape`/`aria-modal` na gaveta mobile; `.filter-chip` em `rounded-full`; nomenclatura do `roadmap.md`; favicon e `<title>`; marca em e-mail, documento gerado ou exportação |

A aprovação foi dada em duas decisões separadas, porque aprovar visual não aprova copy:

1. **Visual** — a revisão 1 como está, incluindo o item de menu no papel _label_ (12/16, 600). A
   alternativa registrada na decisão 3 abaixo (manter 13 px e estender o contrato com um papel
   "nav") foi **rejeitada**.
2. **Copy** — as strings exatas: sidebar `Pulse` + `Operação Biahflow`; raiz do breadcrumb `Pulse`;
   login com eyebrow `Operação Biahflow` e rodapé `Biahflow · processos que fluem` (inalterado);
   convite passa de `Portal Biahflow` para `Pulse`.

Esta é a autoridade de design para a implementação da Issue #26. Aprovação da revisão 1 não é
aprovação de uma revisão posterior: um pacote materialmente alterado é revisão nova e precisa do
próprio registro.

## Artefato

| Arquivo | O que é |
| --- | --- |
| `board.html` | Renderização auto-contida. Abre sem build, sem toolchain e sem rede. |
| `approved-board.png` | Captura congelada do quadro. **É a isto que a aprovação se refere.** |

SHA-256 de `approved-board.png`:

```text
f4c661f5faa28e1573700d4b88dfdda1920610c11ecd61e171115094dd7bd944
```

Uma renderização depende de fonte, navegador e plataforma; a captura congelada é o que a aprovação
de fato nomeia.

## Superfícies e estados no pacote

| Superfície | Estado | No pacote |
| --- | --- | --- |
| Sidebar desktop | sucesso (antes e depois) | sim |
| Gaveta mobile | aberta | sim |
| Topbar + breadcrumb | sucesso | sim |
| Popover de notificações | com itens | sim |
| Popover de notificações | vazio | sim |
| Popover de usuário | sucesso | sim |
| Visão geral | sucesso | sim |
| Visão geral | vazio | sim |
| Visão geral | erro | sim |
| Visão geral | carregando | sim |
| Painel de login | superfície escura, antes e depois | sim |
| Aceitar convite | — | **não** — a mudança é só de copy (`"Portal Biahflow"`), sem alteração estrutural ou visual |
| Não autorizado | — | **não** — o shell não tem esse estado: sem sessão o roteador devolve o login (`App.tsx:65`) |
| Sidebar com nome longo / truncamento | — | **não** — é comportamento de runtime, validado em browser e não neste quadro |

## Proveniência dos valores visuais

| Valor | Origem | Novo? |
| --- | --- | --- |
| Paleta (`ink`, `muted`, `line`, `line-strong`, `canvas`, `surface`, `brand-*`, `danger*`, `success*`, `warning*`, `info*`) | `docs/design/pulse-design-system.md` · `frontend/src/index.css` `@theme` | não |
| Escala tipográfica, espaço, raio, elevação | `docs/design/dap-gh19-r2/README.md` (fundações normativas) | não |
| Geometria do mark (`viewBox 0 0 48 48`, `rx 10`, path do pulso, traço 3,25) | `frontend/src/assets/brand/pulse-mark.svg` (v1, PR #27) | não |
| Forma do shell: barra clara, 254 px, menu rolando por dentro, breakpoint `lg` | ADR 0025 | não — **preservada** |
| **Variante invertida do mark** (tile branco, traço `brand-500`) | — | **sim — decidido aqui** |
| **Subtítulo "Operação Biahflow"** | — | **sim — decidido aqui** |
| **Raiz do breadcrumb "Pulse"** | — | **sim — decidido aqui** |
| **`.metric-card--dark`** | formaliza o literal de `DashboardPage.tsx:30` | **sim — decidido aqui** |
| **`.metric-icon--danger`** | substitui `bg-red-50` literal pelo token `danger-50` | **sim — decidido aqui** |

Design system consultado: `docs/design/pulse-design-system.md` e `docs/design/dap-gh19-r2/README.md`,
lidos em 2026-08-25. **Se este pacote e essa fonte divergirem, a fonte vence e este pacote está velho.**

## Medições de contraste

| Par | Razão | Veredito |
| --- | --- | --- |
| Mark clay `#BD4A30` sobre `brand-900` `#5C2317` | 2,45:1 | o mark **some** — é por isso que a variante invertida existe |
| Mark invertido `#FFFFFF` sobre `brand-900` | 12,3:1 | legível com folga |
| Traço clay `#BD4A30` dentro do tile branco | 5,02:1 | passa AA |
| Eyebrow `brand-200` sobre `brand-900` | 4,6:1 | inalterado (ADR 0025) |
| Meta do cartão escuro, hoje `text-white/50` sobre `ink` | ≈4,7:1 | passa, com margem fina — sobe para `text-white/70` |

O mark é decorativo (`aria-hidden`), então o axe **não** reprovaria o clay sobre escuro: a regra
`color-contrast` mede texto. Esta é uma decisão de legibilidade tomada aqui, e não um portão
automático que teria pego o problema sozinho.

## Entregue vs. reservado

| Elemento | Esta entrega | Reservado para | Vira real quando |
| --- | --- | --- | --- |
| Sidebar, gaveta mobile, topbar/breadcrumb, popovers | entrega | — | — |
| Visão geral (sucesso, vazio, erro, carregando) | entrega | — | — |
| Login e aceitar convite | entrega — **ampliação de escopo autorizada por humano nesta sessão** | — | — |
| `focus trap`, `Escape` e `aria-modal` na gaveta mobile | não entrega | Issue própria | o defeito preexistente for priorizado |
| `.filter-chip` em `rounded-full` (pill de controle, contra a regra "`full` só status/avatar") | não entrega | Issue própria | Leads e Clientes entrarem em escopo |
| As outras 20 telas de produto | não entrega | — | Issue própria por tela ou família |
| Tema escuro | não entrega | — | DAP próprio (`dap-gh19-r2/README.md:44`) |

Nenhum elemento reservado é desenhado como controle inerte: o que não entra simplesmente não muda.
Não há placeholder ligado sem função.

## Decisões que este pacote carrega

1. **O produto se chama Pulse no shell.** Biahflow permanece como guarda-chuva no subtítulo do
   sidebar ("Operação Biahflow"), no rodapé do login ("Biahflow · processos que fluem") e na copy
   do convite. Aprovar o visual **não** aprova copy automaticamente — por isso cada string está
   escrita no quadro.
2. **A variante escura do mark é decidida aqui.** Sem ela, o mark clay sobre `brand-900` dá 2,45:1
   e desaparece. A geometria não muda; muda o preenchimento — o que atende à restrição da Issue de
   não alterar a geometria canônica em silêncio.
3. **O item de menu adota o papel _label_ (12/16, 600).** É a decisão mais discutível do pacote:
   hoje são 13 px com peso 500, e o contrato r2 não tem papel intermediário. Cai um pixel e sobe o
   peso. _Alternativa registrada:_ manter 13 px e acrescentar um papel "nav" ao design system — o
   que seria estender o contrato, não consumi-lo.
4. **O cartão escuro da visão geral continua escuro**, mas deixa de ser literal e passa a variante
   nomeada.
5. **Toda classe tem consumidor.** `.brand-mark` perde o último e sai no mesmo diff; as variantes
   novas nascem já chamadas.
6. **`PulseBrand` ganha nome acessível.** Hoje `PulseBrand.tsx:11` traz `alt=""` + `aria-hidden`, e
   em `compact` não sobra texto — o link do sidebar ficaria sem nome acessível (violação
   `link-name` do axe). É defeito do componente entregue pela PR #27, corrigido nesta entrega.

## Questões em aberto

Nada aqui é resolvido por agente durante a implementação.

- `roadmap.md:512` ainda chama o produto de **Cockpit** (ADR 0030), enquanto a ADR 0041 o chama de
  **Pulse**. Esta entrega não reconcilia a nomenclatura do roadmap.
- Favicon e `<title>` do documento não estão neste pacote e não mudam nesta entrega.
- Não há decisão sobre a marca em e-mail transacional, documento gerado ou exportação.

## Notas para quem implementa

- **Intencional e a preservar:** a forma da ADR 0025 (barra clara, 254 px, menu rolando por dentro,
  breakpoint `lg`); `.icon-button` em 40 px por WCAG 2.5.8; `.nav-label` em `muted` e nunca
  `slate-400`; o filtro de navegação por papel e `is_admin`; `useEscape` devolvendo foco ao botão
  que abriu; um único `nav()` servindo as duas larguras.
- **Ilustrativo e a não tratar como especificação:** os números (12, 3, R$ 480.000), os nomes
  ("Daniel", "Acme", "Onboarding"), os ícones desenhados à mão no quadro e o recorte exato dos
  _blobs_ do login.
- **O que este quadro não consegue mostrar:** ordem de foco, comportamento de teclado, leitor de
  tela, truncamento com nome longo, _reflow_ entre 390 e 1280 px, e movimento. Tudo isso é validado
  em runtime (`BROWSER_REQUIRED`), não aqui.
- **Consumir o asset canônico.** O SVG do quadro é _mock_. No produto importa-se
  `assets/brand/pulse-mark.svg`; nunca se cola o SVG inline (`assets/brand/README.md:20`).
