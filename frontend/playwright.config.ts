import { defineConfig, devices } from "@playwright/test";

// `127.0.0.1` e não `localhost`: em runner de CI o `localhost` pode resolver para ::1 enquanto o
// Vite escuta em IPv4, e o teste falha com ERR_CONNECTION_REFUSED sem dizer por quê.
const baseURL = process.env.E2E_BASE_URL || "http://127.0.0.1:5173";

// A matriz de a11y/responsividade (FDD 022) roda em três larguras; os e2e de fluxo continuam
// só no desktop, porque multiplicá-los por três triplicaria o tempo sem cobrir nada novo.
//
// 390 é celular. 768 não é enfeite: é a fronteira `md` do Tailwind e, como o corte estrutural
// do `Layout` é `lg` (1024), é a largura em que o tablet **cai no menu hambúrguer** — a faixa
// que ninguém testava e onde `md:` aparece 4 vezes no código inteiro.
const MATRIZ = /(a11y|responsive)\.spec\.ts/;

export default defineConfig({
  testDir: "./e2e",
  timeout: 30_000,
  use: { baseURL, ...devices["Desktop Chrome"] },
  projects: [
    { name: "e2e", use: { ...devices["Desktop Chrome"] }, testIgnore: MATRIZ },
    { name: "mobile", use: { ...devices["Desktop Chrome"], viewport: { width: 390, height: 844 } }, testMatch: MATRIZ },
    { name: "tablet", use: { ...devices["Desktop Chrome"], viewport: { width: 768, height: 1024 } }, testMatch: MATRIZ },
    { name: "desktop", use: { ...devices["Desktop Chrome"], viewport: { width: 1280, height: 800 } }, testMatch: MATRIZ },
  ],
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
