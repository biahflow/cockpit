# A paleta anterior do portal Biahflow — snapshot de 07/08/2026

Este arquivo existe para uma coisa só: **poder voltar**. Ele guarda o `frontend/src/index.css`
exatamente como estava antes do redesenho da ADR 0024, com os hex originais e — a parte que
importa mais — **as razões que os acompanham**.

O marco no git é `design/antes-do-redesenho` (commit `99ce39e`). Voltar os três arquivos que
a fatia tocou:

```bash
git checkout design/antes-do-redesenho -- \
  frontend/src/index.css \
  frontend/src/components/Layout.tsx \
  frontend/src/pages/LoginPage.tsx
```

**Uma tag sozinha não bastava, e é por isso que este arquivo existe.** Ela ajuda quem lembra
que ela existe. Daqui a seis meses, quem quiser entender por que o laranja era `#bd4a30` e
não `#d05d45` vai procurar num documento, não num `git show`.

## Os cinco tokens, como estavam

| Token | Hex | Papel |
|---|---|---|
| `--color-ink` | `#102a2a` | texto principal — verde-petróleo bem escuro, não preto |
| `--color-ocean` | `#0d5f5a` | **primário**: botão, link, item ativo, anel de foco |
| `--color-mint` | `#eaf7f2` | tinte do primário: sidebar, avatar, chip |
| `--color-sand` | `#f7f8f5` | fundo da página — off-white levemente esverdeado |
| `--color-signal` | `#bd4a30` | acento clay: prazo vencido, erro, contador |

Fonte: `"Inter Variable", "Inter", "Avenir Next", ui-sans-serif, system-ui, sans-serif`.

## As duas correções que estão embutidas — e que um "voltar atrás" reintroduziria

Estas não são preferências de estilo. São defeitos consertados, e o comentário no CSS era o
único lugar onde elas estavam registradas.

### 1. `--color-signal` foi **escurecido** de `#d05d45` para `#bd4a30` (FDD 022)

O tom antigo dava **3,9:1** sobre branco e reprovava em AA. A cor aparece como **texto** —
prazo vencido, mensagem de erro — e como fundo do contador de notificação, que é branco sobre
ela e reprovava pelo mesmo motivo. O tom novo dá **4,96:1** nas duas direções.

*O redesenho da ADR 0024 preserva este hex exato, e de propósito: inventar um laranja novo
seria refazer a medição do zero e arriscar repetir o defeito.*

### 2. O `focus:outline-none` foi **removido inteiro** (FDD 022, WCAG 2.4.7)

Havia `button, input, select { @apply focus:outline-none }`, que apagava o indicador de foco
de **todo** controle. Alguns campos recompunham com `focus:ring`; **nenhum botão recompunha**,
e navegar de teclado pelo portal era navegar às cegas.

Saiu por dois motivos, e o segundo é o que impede alguém de "consertar" colando de volta:

1. Deixou de ser necessária — browser moderno só desenha o anel padrão em `:focus-visible`,
   isto é, no foco por teclado.
2. **Ela impedia a correção.** O `outline-none` do Tailwind v4 não zera só o contorno: grava
   `--tw-outline-style: none` no elemento. Como `outline-2` desenha com
   `outline-style: var(--tw-outline-style)`, qualquer `:focus-visible` escrito depois
   resolvia para `none` e não aparecia — **em silêncio**.

O que ficou no lugar: `:focus-visible { @apply outline-2 outline-offset-2 outline-ocean; }`.
No redesenho, o mesmo com `outline-accent`.

*Existe teste para isto e ele não é do axe:* `e2e/a11y.spec.ts` tem um caso separado que
tabula até o primeiro `<button>` e lê o `outlineStyle` computado, porque **o axe não cobre
foco visível** — a regra é de verificação manual. Foi medido: com o `focus:outline-none` cru
de volta, as 63 varreduras do axe continuavam passando.

## O arquivo, íntegro

```css
@import "tailwindcss";
/* A Inter estava **declarada e nunca carregada**: `--font-sans` a nomeava, mas não havia
   `@font-face`, `<link>` nem dependência que a trouxesse — o produto inteiro caía no
   Avenir Next / system UI sem ninguém notar.

   Auto-hospedada, e não `<link>` para o Google Fonts, por três motivos: some uma requisição a
   terceiro no caminho crítico, funciona em rede fechada e offline, e o Google Fonts entrega o IP
   de quem acessa a um terceiro — que é exatamente o tipo de coisa que uma política de retenção
   teria de justificar depois. A variável traz todos os pesos num arquivo só. */
@import "@fontsource-variable/inter";

@theme {
  --color-ink: #102a2a;
  --color-ocean: #0d5f5a;
  --color-mint: #eaf7f2;
  --color-sand: #f7f8f5;
  /* Escurecido de #d05d45 para passar em AA (FDD 022). O tom antigo dava 3,9:1 sobre branco,
     e a marca aparece como **texto**: prazo vencido, mensagem de erro, contador de
     notificação. O mesmo ajuste conserta o contador, que é branco sobre `bg-signal` e
     também reprovava. Continua o mesmo clay laranja, um degrau mais fundo. */
  --color-signal: #bd4a30;
  --font-sans: "Inter Variable", "Inter", "Avenir Next", ui-sans-serif, system-ui, sans-serif;
}

@layer base {
  * { @apply border-slate-200; }
  body { @apply min-h-screen bg-sand font-sans text-slate-800 antialiased; }
  /* Foco visível (WCAG 2.4.7). Aqui havia `button, input, select { @apply focus:outline-none }`,
     que apagava o indicador de foco de **todo** controle: alguns campos recompunham com
     `focus:ring`, nenhum botão recompunha, e navegar de teclado pelo portal era navegar às
     cegas. A supressão saiu inteira, por dois motivos — FDD 022:

     1. Ela não é mais necessária. Browser moderno já só desenha o anel padrão em
        `:focus-visible`, isto é, no foco por teclado; suprimir `:focus` era resolver um
        problema que deixou de existir e, de quebra, apagar o foco de quem depende dele.
     2. Ela impedia a correção. `outline-none` do Tailwind v4 não só zera o contorno: grava
        `--tw-outline-style: none` no elemento. Como `outline-2` desenha com
        `outline-style: var(--tw-outline-style)`, qualquer regra de `:focus-visible` escrita
        depois resolvia para `none` e não aparecia — silenciosamente. */
  :focus-visible { @apply outline-2 outline-offset-2 outline-ocean; }
}

@utility field {
  @apply w-full rounded-xl border bg-white px-3 py-3 text-sm text-slate-800 transition focus:border-ocean focus:ring-4 focus:ring-ocean/10;
}
```

## O que o redesenho **não** mudou

- O `@import "@fontsource-variable/inter"` e a razão de a fonte ser auto-hospedada.
- O valor `#bd4a30` do laranja.
- A ausência de `focus:outline-none`, e o `:focus-visible` explícito no lugar.
- A regra `* { @apply border-slate-200 }` — só o tom, que passou a `line`.
