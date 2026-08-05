import { defineConfig, devices } from "@playwright/test";

// `127.0.0.1` e não `localhost`: em runner de CI o `localhost` pode resolver para ::1 enquanto o
// Vite escuta em IPv4, e o teste falha com ERR_CONNECTION_REFUSED sem dizer por quê.
const baseURL = process.env.E2E_BASE_URL || "http://127.0.0.1:5173";

export default defineConfig({
  testDir: "./e2e",
  timeout: 30_000,
  use: { baseURL, ...devices["Desktop Chrome"] },
  // Quem sobe o servidor é o Playwright, **inclusive no CI**. Antes era `CI ? undefined`, então no
  // CI nenhum servidor subia e os cinco testes falhavam com ERR_CONNECTION_REFUSED; ninguém via
  // porque o `npm ci` do job quebrava antes de chegar aqui. Só sai de cena se `E2E_BASE_URL`
  // apontar para um ambiente já no ar.
  webServer: process.env.E2E_BASE_URL
    ? undefined
    : {
        command: "npm run dev -- --host 127.0.0.1",
        url: baseURL,
        reuseExistingServer: !process.env.CI,
      },
});
