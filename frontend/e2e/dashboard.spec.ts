import { expect, test } from "@playwright/test";

test("apresenta o painel operacional", async ({ page }) => {
  await page.route("**/api/v1/auth/me/", route => route.fulfill({ json: { id: 1, username: "admin", first_name: "Ana", last_name: "", email: "ana@example.test", role: "admin", is_admin: true } }));
  await page.route("**/api/v1/dashboard/", route => route.fulfill({ json: {
    pipeline: [], active_projects: 3, overdue_count: 1,
    upcoming_tasks: [{ id: 9, title: "Enviar proposta", due_date: "2026-08-10", project_id: 1 }],
  } }));
  await page.goto("/");
  await expect(page.getByRole("heading", { name: "Sua operação, em movimento." })).toBeVisible();
  await expect(page.getByText("Enviar proposta")).toBeVisible();
});
