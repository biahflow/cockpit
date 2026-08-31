import { sentryVitePlugin } from "@sentry/vite-plugin";
import { defineConfig } from "vitest/config";
import tailwindcss from "@tailwindcss/vite";
import react from "@vitejs/plugin-react";

// O upload de sourcemap para o Sentry é opt-in por `SENTRY_AUTH_TOKEN` (FDD 020): ele exige um
// token de escrita, que nem o build local nem o CI têm. Sem o token o plugin nem entra na lista e
// o build é exatamente o de antes. `sourcemap: "hidden"` gera o mapa sem referenciá-lo no bundle:
// o Sentry desminifica o stack trace e o nginx não passa a servir o código-fonte do portal.
const sentryToken = process.env.SENTRY_AUTH_TOKEN;

export default defineConfig({
  plugins: [
    react(),
    tailwindcss(),
    ...(sentryToken
      ? [sentryVitePlugin({
        authToken: sentryToken,
        org: process.env.SENTRY_ORG,
        project: process.env.SENTRY_PROJECT,
        release: { name: process.env.VITE_SENTRY_RELEASE },
      })]
      : []),
  ],
  build: { sourcemap: sentryToken ? "hidden" : false },
  server: {
    proxy: { "/api": process.env.VITE_PROXY_TARGET || "http://localhost:8000" },
  },
  test: {
    include: ["src/**/*.test.{ts,tsx}"],
    environment: "jsdom",
    setupFiles: ["./src/test/setup.ts"],
    // As páginas de detalhe montam árvores grandes em jsdom. Deixar o Vitest usar todos os cores
    // põe dezenas delas em paralelo e faz interações simples estourarem o timeout de 5s por
    // starvation; limitar trabalhadores estabiliza a suíte sem alargar timeout nem reduzir gate.
    maxWorkers: 4,
    coverage: { provider: "v8", reporter: ["text", "html"], thresholds: { lines: 80 } },
  },
});
