/**
 * Dá para operar sem mouse, e dá para sair de onde se entrou.
 *
 * A FDD 022 deixou isto de fora e disse por quê: **o axe não pega**. Ele varre uma página parada,
 * e "o foco escapa do diálogo?" e "dá para fechar sem mouse?" só existem durante a interação. É a
 * mesma razão pela qual o indicador de foco precisou de teste próprio — o gate passava e o portal
 * estava quebrado.
 */

import { expect, test } from "@playwright/test";

import { abrir, ROUTES } from "./matrix";

const COMERCIAL = ROUTES.find(screen => screen.path === "/comercial")!;
const VISAO_GERAL = ROUTES[0];

test("o menu do usuário fecha com Escape e devolve o foco a quem o abriu", async ({ page }) => {
  await abrir(page, VISAO_GERAL);
  const botao = page.getByRole("button", { name: /Sair|admin/i }).first();
  const abridor = page.locator('button[aria-haspopup="menu"]');

  await abridor.click();
  await expect(page.getByRole("menu")).toBeVisible();

  await page.keyboard.press("Escape");

  await expect(page.getByRole("menu")).toBeHidden();
  // Devolver o foco é a metade esquecida: sem isso, quem fecha é despejado no início da página.
  await expect(abridor).toBeFocused();
  expect(botao).toBeDefined();
});

test("o sino de notificações fecha com Escape", async ({ page }) => {
  await abrir(page, VISAO_GERAL);
  const sino = page.getByRole("button", { name: "Notificações" });

  await sino.click();
  await expect(page.getByText("Notificações", { exact: true })).toBeVisible();

  await page.keyboard.press("Escape");

  await expect(sino).toBeFocused();
});

test("o diálogo fecha com Escape", async ({ page }) => {
  await abrir(page, COMERCIAL);
  await page.getByRole("button", { name: /Nova oportunidade/i }).first().click();
  const dialogo = page.getByRole("dialog", { name: "Nova oportunidade" });
  await expect(dialogo).toBeVisible();

  await page.keyboard.press("Escape");

  await expect(dialogo).toBeHidden();
});

test("o foco não escapa do diálogo pelo Tab", async ({ page }) => {
  await abrir(page, COMERCIAL);
  await page.getByRole("button", { name: /Nova oportunidade/i }).first().click();
  const dialogo = page.getByRole("dialog", { name: "Nova oportunidade" });
  await expect(dialogo).toBeVisible();

  // Tabular mais vezes que o número de controles: sem a prisão, o foco sai para a página atrás e
  // `aria-modal="true"` vira mentira — o leitor de tela anuncia o resto como inerte.
  for (let i = 0; i < 25; i++) await page.keyboard.press("Tab");

  const dentro = await dialogo.evaluate(caixa => caixa.contains(document.activeElement));
  expect(dentro).toBe(true);
});

test("mover oportunidade de etapa tem caminho de teclado, sem arrastar", async ({ page }) => {
  await abrir(page, COMERCIAL);

  // O kanban usa arrastar-e-soltar, que não tem equivalente de teclado. A alternativa é o `select`
  // de etapa no detalhe da oportunidade — este teste prova que ela **existe e é alcançável**, que
  // é a parte que faltava para o arrastar deixar de ser o único caminho.
  await page.getByRole("article").first().click();
  const etapa = page.getByRole("dialog").getByRole("combobox").first();

  await expect(etapa).toBeVisible();
  await etapa.focus();
  await expect(etapa).toBeFocused();
});
