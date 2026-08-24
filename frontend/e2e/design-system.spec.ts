import { expect, test } from "./fixtures";
import { abrir } from "./matrix";

test("design system r2 aplica tokens, estados e foco no runtime", async ({ page }) => {
  await abrir(page, { path: "/design-system", name: "Design system", role: "admin" });

  const estado = await page.locator(".state--0").evaluate(elemento => {
    const estilo = getComputedStyle(elemento);
    return { fundo: estilo.backgroundColor, texto: estilo.color };
  });
  expect(estado).toEqual({ fundo: "rgb(239, 246, 255)", texto: "rgb(29, 78, 216)" });
  const semanticos = [[".state--0", "rgb(239, 246, 255)"], [".state--1", "rgb(236, 253, 245)"], [".state--2", "rgb(255, 251, 235)"], [".state--3", "rgb(254, 242, 242)"]] as const;
  for (const [seletor, fundo] of semanticos) {
    await expect(page.locator(`${seletor} svg`)).toBeVisible();
    await expect(page.locator(seletor)).toHaveCSS("background-color", fundo);
  }

  for (let salto = 0; salto < 40; salto++) {
    await page.keyboard.press("Tab");
    if (await page.getByTestId("ds-primary").evaluate(elemento => document.activeElement === elemento)) break;
  }
  await expect(page.getByTestId("ds-primary")).toBeFocused();
  const foco = await page.getByTestId("ds-primary").evaluate(elemento => {
    const estilo = getComputedStyle(elemento);
    return { largura: estilo.outlineWidth, offset: estilo.outlineOffset };
  });
  expect(foco).toEqual({ largura: "2px", offset: "2px" });
  const tokenDeFoco = await page.evaluate(() => getComputedStyle(document.documentElement).getPropertyValue("--color-brand-500").trim());
  expect(tokenDeFoco).toBe("#bd4a30");

  for (const botao of [page.getByTestId("ds-primary"), page.getByTestId("ds-secondary")]) {
    await expect(botao).toHaveCSS("min-height", "44px");
    await botao.hover();
  }
  await page.getByTestId("ds-primary").hover();
  await expect(page.getByTestId("ds-primary")).toHaveCSS("background-color", "rgb(156, 60, 38)");
  await page.getByTestId("ds-secondary").hover();
  await expect(page.getByTestId("ds-secondary")).toHaveCSS("background-color", "rgb(253, 241, 236)");
  for (const botao of [page.getByTestId("ds-primary-disabled"), page.getByTestId("ds-secondary-disabled")]) {
    await expect(botao).toHaveCSS("opacity", "1");
    await expect(botao).toHaveCSS("color", "rgb(87, 83, 78)");
  }

  const overflow = await page.evaluate(() => document.documentElement.scrollWidth > window.innerWidth);
  expect(overflow, "a página de prova não pode criar rolagem horizontal").toBe(false);

  if (process.env.PULSE_DAP_EVIDENCE_DIR) {
    const nome = await page.evaluate(() => window.innerWidth < 600 ? "browser-mobile.png" : "browser-desktop.png");
    await page.screenshot({ path: `${process.env.PULSE_DAP_EVIDENCE_DIR}/${nome}`, fullPage: true });
    if (nome === "browser-desktop.png") await page.screenshot({ path: `${process.env.PULSE_DAP_EVIDENCE_DIR}/focus-desktop.png`, fullPage: true });
  }
});
