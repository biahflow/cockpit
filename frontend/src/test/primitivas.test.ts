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
  // Exige `bg-`: um selo tem fundo. `rounded-lg px-2 py-1 text-xs font-semibold text-slate-600`
  // é um **botão de texto**, e flagrá-lo mandaria trocar um controle por um rótulo.
  [/rounded-(?:full|lg) px-[\d.]+ py-[\d.]+ text-xs font-semibold bg-|bg-\S+ [^"]*rounded-full px-[\d.]+ py-[\d.]+ text-xs font-semibold/, ".state + variante"],
  // `font-semibold` é o que distingue **selo** de tinta de ícone: um quadradinho âmbar com um
  // ícone dentro é decoração legítima e não tem primitiva; um selo com texto tem.
  [/bg-(?:emerald|amber)-50 [^"]*font-semibold|font-semibold[^"]*bg-(?:emerald|amber)-50/, "uma variante de .state"],
  [/text-3xl font-semibold tracking-tight text-ink/, ".page-head (o h1 já vem estilizado)"],
  // Só o rótulo **solto** acima do título; um `text-accent` dentro de uma pastilha com fundo é
  // outra coisa, e o `(?<!\S )` sozinho não separaria os dois — daí exigir início do literal.
  [/className="(?:mt-\d+ )?text-sm font-semibold text-accent"/, ".eyebrow"],
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
