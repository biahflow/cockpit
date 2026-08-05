import { afterEach, expect, test, vi } from "vitest";

import { getLastRequestId, initSentry, isSentryEnabled, reportError, setLastRequestId } from "./observability";

afterEach(() => {
  vi.unstubAllEnvs();
  vi.resetModules();
  vi.restoreAllMocks();
});

test("sem DSN o Sentry não é inicializado", async () => {
  // A suíte roda sem `VITE_SENTRY_DSN`, que é o caminho default: o fornecedor é opcional e o
  // chunk do SDK nem chega a ser baixado.
  expect(await initSentry()).toBe(false);
  expect(isSentryEnabled()).toBe(false);
});

test("reportar erro com o Sentry desligado não explode", () => {
  expect(() => reportError(new Error("qualquer"), { path: "/clients/" })).not.toThrow();
});

test("guarda o request-id da última resposta", () => {
  setLastRequestId("abc123");

  expect(getLastRequestId()).toBe("abc123");
});

// O DSN é lido na importação do módulo (é assado no bundle), então exercitar o caminho ligado
// exige reimportar com o ambiente trocado — e com o SDK dublado, para nenhum teste falar com a
// rede. O namespace de um módulo ESM não é espionável, daí `doMock` em vez de `spyOn`.
async function comDsn() {
  const escopo = { setTag: vi.fn(), setContext: vi.fn() };
  const sentry = {
    init: vi.fn(),
    captureException: vi.fn(),
    withScope: vi.fn((cb: (s: typeof escopo) => void) => cb(escopo)),
  };
  vi.stubEnv("VITE_SENTRY_DSN", "https://chave@o0.ingest.sentry.io/1");
  vi.stubEnv("VITE_SENTRY_ENVIRONMENT", "producao");
  vi.stubEnv("VITE_SENTRY_RELEASE", "2026.08.05");
  vi.resetModules();
  vi.doMock("@sentry/react", () => sentry);
  return { sentry, escopo, observability: await import("./observability") };
}

test("com DSN o Sentry sobe sem PII", async () => {
  const { sentry, observability } = await comDsn();

  expect(await observability.initSentry()).toBe(true);
  expect(observability.isSentryEnabled()).toBe(true);
  expect(sentry.init).toHaveBeenCalledWith(expect.objectContaining({
    sendDefaultPii: false,
    environment: "producao",
    release: "2026.08.05",
  }));
});

test("o erro reportado leva o request-id como tag", async () => {
  const { sentry, escopo, observability } = await comDsn();
  await observability.initSentry();
  observability.setLastRequestId("req-77");

  observability.reportError(new Error("explodiu"), { path: "/projects/" });

  expect(sentry.captureException).toHaveBeenCalledOnce();
  expect(escopo.setTag).toHaveBeenCalledWith("request_id", "req-77");
  expect(escopo.setContext).toHaveBeenCalledWith("biahflow", { path: "/projects/" });
});
