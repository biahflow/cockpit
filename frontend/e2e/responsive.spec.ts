/**
 * Responsividade: a mesma matriz de telas em três larguras (FDD 022).
 *
 * Três asserções, escolhidas por serem as que pegam defeito de verdade em vez de descrever o
 * CSS de novo em outra linguagem: nada estoura na horizontal, a navegação continua alcançável,
 * e o que se toca tem tamanho de dedo.
 */

import { expect, test } from "./fixtures";

import { abrir, ROUTES } from "./matrix";

/** Acima disto o `Layout` mostra a sidebar; abaixo, o menu hambúrguer (`lg` do Tailwind). */
const LG = 1024;

for (const screen of ROUTES) {
  test(`${screen.name} não rola na horizontal`, async ({ page }) => {
    await abrir(page, screen);

    // 1px de folga: subpixel de borda arredondada não é defeito de layout.
    const excesso = await page.evaluate(
      () => document.documentElement.scrollWidth - document.documentElement.clientWidth,
    );
    expect(excesso, "a página inteira rola na horizontal — conteúdo largo precisa rolar dentro do próprio container (overflow-x-auto)").toBeLessThanOrEqual(1);
  });
}

test("a navegação é alcançável na largura do viewport", async ({ page }, testInfo) => {
  const largura = testInfo.project.use.viewport?.width ?? 0;
  await abrir(page, { path: "/", name: "Visão geral", role: "admin" });

  const sidebar = page.locator("aside");
  const hamburguer = page.getByRole("button", { name: "Abrir menu" });

  if (largura >= LG) {
    await expect(sidebar).toBeVisible();
    await expect(hamburguer).toBeHidden();
    return;
  }

  // Abaixo de `lg` a sidebar sai de cena e o único caminho para navegar é o hambúrguer.
  // Sem esta asserção, um `lg:hidden` trocado por `hidden` deixaria o portal sem navegação
  // no celular e nenhum teste veria.
  await expect(sidebar).toBeHidden();
  await expect(hamburguer).toBeVisible();
  await hamburguer.click();
  await expect(page.locator("nav").getByRole("link", { name: "Comercial", exact: true })).toBeVisible();
});

test("os controles do cabeçalho têm alvo de toque suficiente", async ({ page }) => {
  await abrir(page, { path: "/", name: "Visão geral", role: "admin" });

  // WCAG 2.5.8 (AA, 2.2) pede 24×24 CSS px para alvo de ponteiro.
  const controles = page.locator("header button");
  for (const controle of await controles.all()) {
    if (!(await controle.isVisible())) continue;
    const caixa = await controle.boundingBox();
    expect(caixa?.width, `alvo estreito: ${await controle.getAttribute("aria-label")}`).toBeGreaterThanOrEqual(24);
    expect(caixa?.height, `alvo baixo: ${await controle.getAttribute("aria-label")}`).toBeGreaterThanOrEqual(24);
  }
});
