import { defineConfig } from "vitest/config";
import tailwindcss from "@tailwindcss/vite";
import react from "@vitejs/plugin-react";

export default defineConfig({
  plugins: [react(), tailwindcss()],
  server: {
    proxy: { "/api": process.env.VITE_PROXY_TARGET || "http://localhost:8000" },
  },
  test: {
    include: ["src/**/*.test.{ts,tsx}"],
    environment: "jsdom",
    setupFiles: ["./src/test/setup.ts"],
    coverage: { provider: "v8", reporter: ["text", "html"], thresholds: { lines: 80 } },
  },
});
