/** Evidência de runtime do DAP Engagement r2 e da invariante 13 (ADR 0058). */

import AxeBuilder from "@axe-core/playwright";
import { expect, test } from "./fixtures";

import { mockApi } from "./matrix";

test("novo engagement escolhe o instrumento assinado antes de permitir o envio", async ({ page }, testInfo) => {
  await mockApi(page, "sales");
  await page.goto("/contas/1");
  await page.waitForLoadState("networkidle");

  const panel = page.getByTestId("engagements-panel");
  await panel.getByRole("button", { name: "Novo engagement" }).click();

  const paidOrigin = panel.getByLabel("Oportunidade ganha de origem");
  await expect(paidOrigin).toHaveValue("1");
  await expect(paidOrigin.getByRole("option")).toHaveCount(1);
  await expect(panel.getByRole("button", { name: "Adicionar engagement" })).toBeEnabled();

  await panel.getByLabel("Modelo comercial").selectOption("design_partner");
  const agreementOrigin = panel.getByLabel("Design Partner Agreement assinado");
  await expect(agreementOrigin).toHaveValue("1");
  await expect(agreementOrigin.getByRole("option")).toHaveCount(1);
  await expect(paidOrigin).toHaveCount(0);

  const controls = panel.locator("form input, form select, form textarea, form button");
  await expect(controls.nth(0)).toHaveAccessibleName("Nome");
  await expect(controls.nth(1)).toHaveAccessibleName("Modelo comercial");
  await expect(controls.nth(2)).toHaveAccessibleName("Design Partner Agreement assinado");
  await expect(controls.nth(3)).toHaveAccessibleName("Status");

  const horizontalOverflow = await page.evaluate(
    () => document.documentElement.scrollWidth - document.documentElement.clientWidth,
  );
  expect(horizontalOverflow).toBeLessThanOrEqual(1);

  const { violations } = await new AxeBuilder({ page })
    .include('[data-testid="engagements-panel"]')
    .withTags(["wcag2a", "wcag2aa", "wcag21a", "wcag21aa"])
    .analyze();
  expect(violations).toEqual([]);

  await page.screenshot({
    path: testInfo.outputPath("engagement-origin-runtime.png"),
    fullPage: true,
  });
});
