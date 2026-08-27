import { expect, test } from "./fixtures";

test("apresenta o painel operacional", async ({ page }) => {
  await page.route("**/api/v1/auth/me/", route => route.fulfill({ json: { id: 1, username: "admin", first_name: "Ana", last_name: "", email: "ana@example.test", role: "admin", is_admin: true } }));
  await page.route("**/api/v1/dashboard/", route => route.fulfill({ json: {
    pipeline: [], active_projects: 3, overdue_count: 1,
    upcoming_tasks: [{ id: 9, title: "Enviar proposta", due_date: "2026-08-10", project_id: 1 }],
    // A escada FDE por conta (FDD 042) faz parte do contrato de `/dashboard/`. Uma linha aqui
    // porque este spec é o único que abre o painel num browser de verdade, com o CSS aplicado:
    // sem ela, a superfície B só seria medida em jsdom.
    account_ladder: [{
      client_id: 7, client_name: "Metalúrgica Vale", rung: "prove", rung_display: "Prove",
      status: "blocked", status_display: "Bloqueado",
      waiting_on: "client", waiting_on_display: "Cliente", days_stalled: 31, is_stale: true,
      steps: [
        { rung: "discover", rung_display: "Discover", status: "done" },
        { rung: "prioritize", rung_display: "Prioritize", status: "done" },
        { rung: "feasibility", rung_display: "[ Technical Feasibility ]", status: "skipped" },
        { rung: "prove", rung_display: "Prove", status: "blocked" },
        { rung: "scale", rung_display: "Scale", status: "not_sold" },
        { rung: "optimize", rung_display: "Optimize", status: "not_sold" },
      ],
    }],
  } }));
  await page.goto("/");
  await expect(page.getByRole("heading", { name: "Sua operação, em movimento." })).toBeVisible();
  await expect(page.getByText("Enviar proposta")).toBeVisible();
  const conta = page.getByRole("link", { name: /Metalúrgica Vale/ });
  await expect(conta).toHaveAttribute("href", "/clientes/7");
  await expect(conta.getByText("parado há 31 dias")).toBeVisible();
});
