import { expect, test } from "@playwright/test";

test("movimenta uma oportunidade pelo pipeline", async ({ page }) => {
  await page.route("**/api/v1/auth/me/", route => route.fulfill({ json: { id: 1, username: "sales", first_name: "Bia", last_name: "", email: "bia@example.test", role: "sales" } }));
  const stages = [
    { id: 1, name: "Prospecção", kind: "open", position: 10 },
    { id: 2, name: "Negociação", kind: "open", position: 20 },
  ];
  const opportunities = [{
    id: 7, client: 1, title: "Diagnóstico Biahflow", scope: "", estimated_value: "1000.00",
    stage: 1, stage_name: "Prospecção", owner: 1, expected_close_date: "2026-08-10",
  }];
  await page.route("**/api/v1/pipeline-stages/", route => route.fulfill({ json: stages }));
  await page.route("**/api/v1/opportunities/", route => route.fulfill({ json: opportunities }));
  await page.route("**/api/v1/clients/", route => route.fulfill({ json: [] }));
  await page.route("**/api/v1/auth/csrf/", route => route.fulfill({ json: { csrfToken: "test" } }));
  await page.route("**/api/v1/opportunities/7/", async route => {
    opportunities[0].stage = 2;
    await route.fulfill({ json: opportunities[0] });
  });
  await page.goto("/comercial");
  await expect(page.getByText("Diagnóstico Biahflow")).toBeVisible();
  const opportunity = page.locator("article").filter({ hasText: "Diagnóstico Biahflow" });
  const negotiation = page.locator("section.w-72", { has: page.getByRole("heading", { name: "Negociação" }) });
  await opportunity.dragTo(negotiation);
  await expect(negotiation.getByText("Diagnóstico Biahflow")).toBeVisible();
});
