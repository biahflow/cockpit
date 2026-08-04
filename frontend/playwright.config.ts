import { defineConfig, devices } from "@playwright/test";

export default defineConfig({
  testDir: "./e2e",
  timeout: 30_000,
  use: { baseURL: process.env.E2E_BASE_URL || "http://localhost:5173", ...devices["Desktop Chrome"] },
  webServer: process.env.CI ? undefined : { command: "npm run dev -- --host 127.0.0.1", url: "http://127.0.0.1:5173", reuseExistingServer: true },
});

