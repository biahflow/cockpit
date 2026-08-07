import { expect, test } from "./fixtures";

const user = { id: 1, username: "bia", first_name: "Bia", last_name: "", email: "bia@example.test", role: "admin", is_admin: true };

test("autentica e libera o painel", async ({ page }) => {
  await page.route("**/api/v1/auth/me/", route => route.fulfill({ status: 403, json: { detail: "Credenciais ausentes." } }));
  await page.route("**/api/v1/auth/csrf/", route => route.fulfill({ json: { csrfToken: "test" } }));
  await page.route("**/api/v1/auth/login/", route => route.fulfill({ json: user }));
  await page.route("**/api/v1/dashboard/", route => route.fulfill({ json: { pipeline: [], active_projects: 0, overdue_count: 0, upcoming_tasks: [] } }));

  await page.goto("/");
  await expect(page.getByRole("heading", { name: "Entre na sua operação" })).toBeVisible();
  await page.getByLabel("Usuário").fill("bia");
  await page.getByLabel("Senha").fill("SenhaSegura123!");
  await page.getByRole("button", { name: "Entrar no portal" }).click();
  await expect(page.getByRole("heading", { name: "Sua operação, em movimento." })).toBeVisible();
});

test("mostra erro quando as credenciais são inválidas", async ({ page }) => {
  await page.route("**/api/v1/auth/me/", route => route.fulfill({ status: 403, json: { detail: "Credenciais ausentes." } }));
  await page.route("**/api/v1/auth/csrf/", route => route.fulfill({ json: { csrfToken: "test" } }));
  await page.route("**/api/v1/auth/login/", route => route.fulfill({ status: 400, json: { detail: "Credenciais inválidas." } }));

  await page.goto("/");
  await page.getByLabel("Usuário").fill("bia");
  await page.getByLabel("Senha").fill("errada");
  await page.getByRole("button", { name: "Entrar no portal" }).click();
  await expect(page.getByRole("alert")).toHaveText("Credenciais inválidas.");
});
