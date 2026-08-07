# A referência: o design system do portal do cliente

De onde o redesenho da ADR 0024 foi portado, e o bastante para refazer o port sem adivinhar.

**Este arquivo não é backup do portal do cliente.** Aquele repositório não foi alterado por
esta fatia — ele é a fonte, não o alvo. O que está aqui é a fotografia do que copiamos, para
que "portamos do portal do cliente" seja uma afirmação conferível em vez de uma lembrança.

## A fonte

| | |
|---|---|
| Repositório | `biahflow-portal-cliente` |
| Arquivo | `app/globals.css` (**761 linhas**) |
| `HEAD` na data do port | `90417bc` |
| Último commit que tocou o arquivo | `3bc06eb` — *"o projeto encerrado, e o 404 que não distingue"* |

*Ressalva honesta:* na data do port o `globals.css` daquele repo tinha alteração **não
commitada** — o bloco `.setting-field` da ADR 0043 de lá, para o campo de telefone da tela de
Configurações. Nada disso entrou neste port; é registrado para quem comparar os arquivos não
concluir que a diferença veio daqui.

## O que foi portado

**A ideia central, e é ela que explica a diferença de acabamento:** aquele arquivo tem uma
`@layer components` com ~200 classes semânticas, e o markup referencia `.panel` em vez de
repetir doze utilitários. O Biahflow tinha 45 linhas e **nenhuma** camada de componentes — o
estilo vivia inline nas 22 páginas, sem uma definição única de "o que é um card aqui".

Portadas (adaptadas à paleta preta e laranja):

| Nossa classe | Origem | O que mudou na adaptação |
|---|---|---|
| `.panel`, `.panel-heading` | `.panel` / `.panel-heading` | `border-line` na nossa escala |
| `.eyebrow` | `.eyebrow` | roxo → **laranja** (`accent`) |
| `.page-head` | `.hero` / `.hero-copy` | simplificada: sem a coluna de ação decorativa |
| `.metric-card`, `.metric-icon` | idem | tinte roxo → tinte laranja |
| `.btn` e variantes | `.admin-submit`, `.text-button` | primário roxo → **preto** (`ink`) |
| `.nav-item`, `.nav-item--active` | idem | ativo em `accent-50`, e branco sobre a sidebar escura |
| `.state`, `.state--0..3` | idem | mesma forma, tons de estado próprios |
| Sombras em camadas | `--shadow-card/raised/pop` | mesma geometria, sombra recolorida para o preto quente |

**Não** portadas, e o motivo é o mesmo para todas: descrevem telas que este produto não tem —
`.journey-*`, `.chat-*`, `.message-*`, `.pending-*`, `.employee-*`, `.milestone*`. Copiar
classe sem consumidor seria trazer para cá o defeito que aquele repositório passou nove ADRs
consertando.

## O que **não** foi portado, e é deliberado

- **A paleta.** Lá a marca é roxa (`brand-500 #6e56cf`) sobre `canvas #f6f8fc`. O ponto do
  pedido era justamente **não** ficarem iguais em cor: o Biahflow fica branco, preto e
  laranja. O que se aproxima é a linguagem — superfície, sombra, hierarquia tipográfica —,
  não a identidade.
- **A arquitetura.** Lá é Next.js com server components; aqui é React + Vite com
  `AuthContext`. A regra do design system vale: *portar o visual, não o mecanismo*.

## Como refazer o port

```bash
git -C ../biahflow-portal-cliente show 90417bc:app/globals.css | less
```

As primitivas relevantes estão no `@layer components`, a partir de `.panel`.
