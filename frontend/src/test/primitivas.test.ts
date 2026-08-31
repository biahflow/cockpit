/**
 * A guarda das primitivas (ADR 0026).
 * ---------------------------------------------------------------------------
 * **Um card escrito à mão renderiza *quase* igual a um `.panel`, e a divergência não deixa nada
 * vermelho.** Foi assim que este produto ficou com 1.331 utilitários inline e zero uso de
 * `.panel`, `.btn`, `.page-head` ou `.state`: o design system existia, as telas não o chamavam, e
 * nenhum teste tinha como perceber. O shell tinha ficado igual ao do portal do cliente e as telas,
 * não.
 *
 * É o mesmo desenho do `inertButtons()` de lá, que existe porque um `<button>` sem handler
 * renderiza HTML idêntico a um que funciona: são as duas asserções deste ecossistema que olham a
 * **forma do código** em vez de um valor.
 *
 * Nem o axe nem o vitest pegariam isto. O axe mede contraste e papel — um card inline passa; os
 * testes de página consultam por papel e texto — um card inline passa. O que se perde não é
 * acessibilidade nem comportamento, é a única coisa que faz dois produtos parecerem o mesmo
 * produto: a definição única de "o que é um card aqui".
 *
 * A allowlist nasce **vazia**, e a meta é que continue. Página que legitimamente precise de um
 * literal ganha linha com o motivo escrito.
 */

import { readFileSync, readdirSync } from "node:fs";
import { join } from "node:path";

import { expect, test } from "vitest";

/** Literal proibido → a primitiva que existe para ele. A mensagem tem de dizer o que usar. */
const PROIBIDOS: ReadonlyArray<readonly [RegExp, string]> = [
  [/rounded-2xl border(?: border-line)? bg-white p-[45]/, ".panel"],
  [/overflow-hidden rounded-2xl border(?: border-line)? bg-white"/, ".panel .panel--flush"],
  [/grid gap-2 text-sm font-medium text-slate-700/, ".form-label"],
  [/rounded-xl bg-ink px-\d[\d.]* py-[\d.]+ text-sm font-semibold text-white/, ".btn"],
  // O secundário, que a primeira versão desta guarda não via: o padrão acima só descreve o
  // **primário** (`bg-ink … text-white`), e a forma de contorno era o literal mais copiado que
  // sobrou da ADR 0026 — 13 ocorrências em 9 arquivos, todas idênticas a menos do padding. Uma
  // guarda que cobre só metade de um par convida a escrever a outra metade à mão.
  // `bg-white` é opcional porque metade delas o omitia e herdava o branco do cartão.
  [/rounded-xl border(?: border-line)?(?: bg-white)? px-[\d.]+ py-[\d.]+ text-sm font-semibold text-ink/, ".btn .btn--secondary"],
  // Arquivar/remover em tamanho de botão: neutro em repouso, vermelho na intenção. Quatro
  // consumidores, e a forma é estável o bastante para ter nome.
  [/text-(?:slate-600|muted) hover:border-danger/, ".btn .btn--secondary .btn--secondary-danger"],
  // A base é o que define a pastilha; a cor pode chegar por `${variant}` e por isso **não** faz
  // parte do padrão (issue #45). A versão anterior exigia `bg-` adjacente e era cega exatamente
  // aos seis selos condicionais que deveria reprovar. `rounded-full` + padding nos dois eixos +
  // peso 600 é estreito o bastante para não confundir ponto, avatar nem barra de progresso.
  [/rounded-full px-(?:2|2\.5|3) py-(?:0\.5|1|1\.5) (?:text-(?:xs|sm) )?font-semibold/, ".state + variante"],
  // `font-semibold` é o que distingue **selo** de tinta de ícone: um quadradinho âmbar com um
  // ícone dentro é decoração legítima e não tem primitiva; um selo com texto tem.
  [/bg-(?:emerald|amber)-50 [^"]*font-semibold|font-semibold[^"]*bg-(?:emerald|amber)-50/, "uma variante de .state"],
  [/text-3xl font-semibold tracking-tight text-ink/, ".page-head (o h1 já vem estilizado)"],
  // A geometria que a primitiva realmente protege (issue #44): corpo pequeno, peso forte, caixa
  // alta, tracking largo e tinta da marca. Aceita a divergência histórica 12px/600/`wide` para
  // flagrá-la, além da cópia exata 11px/700/0.18em. `brand-200` inclui a superfície escura, que
  // agora tem `.eyebrow--dark`; não há mais motivo legítimo para reescrever a base.
  [/className="[^"]*text-(?:\[11px\]|xs|sm) [^"]*font-(?:bold|semibold) [^"]*uppercase [^"]*tracking-(?:wide|\[(?:0\.)?18em\]|\[\.18em\]) [^"]*text-(?:accent|brand-(?:200|500))[^"]*"/, ".eyebrow + variante"],
  // O neutro é outro papel e ganhou primitiva própria. O cabeçalho de `ProjectsPage` não casa:
  // não tem `font-semibold`, porque é deliberadamente sem peso e segue fora deste pacote.
  [/className="[^"]*text-xs font-semibold uppercase tracking-wide text-(?:slate-600|muted)[^"]*"/, ".section-label"],
  [/rounded-xl bg-red-50 p-3 text-sm text-danger/, ".alert--error"],
  [/rounded-(?:xl|2xl) border border-dashed[^"]*text-center/, ".empty-state"],
  [/hover:bg-ink"/, ".btn (um `hover:bg-ink` sobre `bg-ink` não faz nada)"],
];

/**
 * Arquivo → motivo. **Vazia de propósito.** Uma entrada aqui é uma dívida declarada, não uma
 * saída fácil: quem a acrescenta escreve por que aquela tela não cabe na primitiva.
 */
const PERMITIDOS: Readonly<Record<string, string>> = {};

/**
 * Caminho relativo, resolvido pelo Node contra o diretório de onde o vitest roda (`frontend/`).
 * **Não** `import.meta.url`: sob o ambiente jsdom aquele não é URL de arquivo. **Não** `cwd()`:
 * `node:process` não está nos tipos do `tsconfig.app.json`, e alargá-los para uma asserção
 * levaria os globais do Node para dentro do bundle do navegador.
 */
const RAIZ = "src";

function fontes(): string[] {
  return ["pages", "components"].flatMap(dir =>
    readdirSync(join(RAIZ, dir))
      .filter((nome: string) => nome.endsWith(".tsx") && !nome.includes(".test."))
      .map((nome: string) => join(dir, nome)),
  );
}

test("nenhuma tela reescreve à mão uma primitiva que já existe", () => {
  const achados: string[] = [];

  for (const arquivo of fontes()) {
    if (arquivo in PERMITIDOS) continue;
    const linhas = readFileSync(join(RAIZ, arquivo), "utf8").split("\n");
    for (const [indice, linha] of linhas.entries()) {
      for (const [padrao, primitiva] of PROIBIDOS) {
        if (padrao.test(linha)) achados.push(`${arquivo}:${indice + 1} — use ${primitiva}`);
      }
    }
  }

  expect(achados, "literal reescrito à mão onde há primitiva (ADR 0026)").toEqual([]);
});

test("a guarda enxerga as formas que escapavam por literal e interpolação", () => {
  const amostras: ReadonlyArray<readonly [string, string]> = [
    ['className="text-xs font-semibold uppercase tracking-wide text-accent"', ".eyebrow + variante"],
    ['className="mb-4 text-sm font-semibold uppercase tracking-[.18em] text-brand-200"', ".eyebrow + variante"],
    ['className="mb-1 text-xs font-semibold uppercase tracking-wide text-slate-600"', ".section-label"],
    ['className={`rounded-full px-2 py-0.5 text-xs font-semibold ${tone}`}', ".state + variante"],
    ['className={`inline-flex items-center gap-1.5 rounded-full px-3 py-1.5 text-xs font-semibold ${tone}`}', ".state + variante"],
  ];

  for (const [literal, primitiva] of amostras) {
    expect(
      PROIBIDOS.some(([padrao, destino]) => destino === primitiva && padrao.test(literal)),
      `a guarda deveria mandar ${literal} para ${primitiva}`,
    ).toBe(true);
  }
});

/**
 * A outra direção, e ela é a que a ADR 0033 do portal do cliente ensinou: uma allowlist que
 * ninguém revisa vira permissão permanente. Se o arquivo isento deixou de ter o literal, a linha
 * tem de sair — senão ela isenta silenciosamente o próximo defeito que aparecer ali.
 */
test("a allowlist não guarda linha desnecessária", () => {
  const obsoletos = Object.keys(PERMITIDOS).filter(arquivo => {
    const fonte = readFileSync(join(RAIZ, arquivo), "utf8");
    return !PROIBIDOS.some(([padrao]) => padrao.test(fonte));
  });

  expect(obsoletos, "isenção sem defeito correspondente — remova a linha").toEqual([]);
});
