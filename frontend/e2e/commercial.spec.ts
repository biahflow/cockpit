import { expect, test } from "@playwright/test";

const services = [
  { id: 10, name: "Discovery Express", active: true, tier: "discovery_express", tier_display: "Discovery Express", list_price: "0.00", summary: "Diagnóstico gratuito." },
  { id: 11, name: "Implantação", active: true, tier: "implantacao", tier_display: "Implantação", list_price: "90000.00", summary: "Funcionários digitais." },
];

test("movimenta uma oportunidade pelo pipeline", async ({ page }) => {
  await page.route("**/api/v1/auth/me/", route => route.fulfill({ json: { id: 1, username: "sales", first_name: "Bia", last_name: "", email: "bia@example.test", role: "sales", is_admin: false } }));
  const stages = [
    { id: 1, name: "Prospecção", kind: "open", position: 10 },
    { id: 2, name: "Negociação", kind: "open", position: 20 },
  ];
  const opportunities = [{
    id: 7, client: 1, title: "Diagnóstico Biahflow", scope: "", estimated_value: "1000.00",
    stage: 1, stage_name: "Prospecção", owner: 1, expected_close_date: "2026-08-10",
    service: 10, service_name: "Discovery Express", service_tier: "discovery_express",
  }];
  await page.route("**/api/v1/pipeline-stages/", route => route.fulfill({ json: stages }));
  await page.route("**/api/v1/opportunities/", route => route.fulfill({ json: opportunities }));
  await page.route("**/api/v1/clients/", route => route.fulfill({ json: [] }));
  await page.route("**/api/v1/services/", route => route.fulfill({ json: services }));
  await page.route("**/api/v1/auth/csrf/", route => route.fulfill({ json: { csrfToken: "test" } }));
  await page.route("**/api/v1/opportunities/7/", async route => {
    opportunities[0].stage = 2;
    await route.fulfill({ json: opportunities[0] });
  });
  await page.goto("/comercial");
  await expect(page.getByText("Diagnóstico Biahflow")).toBeVisible();
  const opportunity = page.locator("article").filter({ hasText: "Diagnóstico Biahflow" });
  await expect(opportunity.getByText("Discovery Express")).toBeVisible();
  const negotiation = page.locator("section.w-72", { has: page.getByRole("heading", { name: "Negociação" }) });
  await opportunity.dragTo(negotiation);
  await expect(negotiation.getByText("Diagnóstico Biahflow")).toBeVisible();
});

test("cria uma oportunidade escolhendo o nível de produto", async ({ page }) => {
  await page.route("**/api/v1/auth/me/", route => route.fulfill({ json: { id: 1, username: "sales", first_name: "Bia", last_name: "", email: "bia@example.test", role: "sales", is_admin: false } }));
  await page.route("**/api/v1/pipeline-stages/", route => route.fulfill({ json: [{ id: 1, name: "Prospecção", kind: "open", position: 10 }] }));
  await page.route("**/api/v1/clients/", route => route.fulfill({ json: [{ id: 1, name: "ACME", legal_name: "", tax_id: "", owner: 1, status: "prospect" }] }));
  await page.route("**/api/v1/services/", route => route.fulfill({ json: services }));
  await page.route("**/api/v1/auth/csrf/", route => route.fulfill({ json: { csrfToken: "test" } }));

  let posted: Record<string, unknown> = {};
  await page.route("**/api/v1/opportunities/", async route => {
    if (route.request().method() === "POST") {
      posted = JSON.parse(route.request().postData() ?? "{}");
      return route.fulfill({ status: 201, json: { id: 8 } });
    }
    return route.fulfill({ json: [] });
  });

  await page.goto("/comercial");
  await page.getByRole("button", { name: "Nova oportunidade" }).click();
  const dialog = page.getByRole("dialog", { name: "Nova oportunidade" });
  await dialog.getByLabel("Título").fill("Implantação ACME");
  await dialog.getByLabel("Cliente").selectOption("1");
  await dialog.getByLabel("Nível de produto").selectOption("11");
  await dialog.getByLabel("Valor estimado").fill("90000");
  await dialog.getByLabel("Previsão de fechamento").fill("2026-10-01");
  await dialog.getByRole("button", { name: "Adicionar ao pipeline" }).click();

  await expect.poll(() => posted.service).toBe(11);
});
