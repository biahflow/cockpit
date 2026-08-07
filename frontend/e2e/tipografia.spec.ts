/**
 * A fonte declarada é a fonte carregada.
 *
 * Existe por um defeito real: `--font-sans` nomeava a Inter e **nada a trazia** — nem
 * `@font-face`, nem `<link>`, nem dependência. O produto inteiro caía no Avenir Next / system UI,
 * e ninguém notou porque a página fica bonita do mesmo jeito, só com outra tipografia.
 *
 * Só o browser pega isto. `document.fonts` não existe em jsdom, e nenhum teste de unidade
 * distingue "a família está declarada" de "a família foi baixada e aplicada" — que é exatamente a
 * distinção que falhou. É a mesma lição da FDD 022 sobre o axe não enxergar foco visível.
 */

import { expect, test } from "./fixtures";

import { abrir, ROUTES } from "./matrix";

const TELA = ROUTES[0]; // Visão geral: qualquer uma serve, a fonte é do documento inteiro

test("a Inter é de fato carregada, e não só declarada", async ({ page }) => {
  await abrir(page, TELA);
  await page.waitForFunction(() => document.fonts.status === "loaded");

  const carregada = await page.evaluate(() =>
    [...document.fonts].some(face => face.family.includes("Inter") && face.status === "loaded"),
  );

  expect(carregada).toBe(true);
});

test("o texto da página resolve para a Inter, não para o fallback", async ({ page }) => {
  await abrir(page, TELA);
  await page.waitForFunction(() => document.fonts.status === "loaded");

  // **Não use `document.fonts.check` para isto.** Ele responde "as webfonts necessárias estão
  // carregadas?", e uma família **ausente** não precisa de nenhuma — então devolve `true`
  // justamente no caso que se quer pegar. As duas primeiras versões deste teste caíram nessa
  // armadilha e passavam com a fonte removida.
  //
  // O que responde de verdade é compor dois fatos observáveis: qual família o `body` pede, e se
  // existe uma `FontFace` carregada com esse nome. Uma coisa é declarar, a outra é ter.
  const { pedida, temFace } = await page.evaluate(() => {
    const primeira = getComputedStyle(document.body).fontFamily.split(",")[0].trim()
      .replace(/^["']|["']$/g, "");
    return {
      pedida: primeira,
      temFace: [...document.fonts].some(f => f.family.replace(/^["']|["']$/g, "") === primeira),
    };
  });

  expect(pedida).toContain("Inter");
  expect(temFace).toBe(true);
});
