/// <reference types="vite/client" />

// Explícito porque estas são assadas no bundle em tempo de build (FDD 020): errar o nome de uma
// delas não dá erro de compilação, dá `undefined` silencioso — e o Sentry simplesmente não liga.
interface ImportMetaEnv {
  readonly VITE_API_URL?: string;
  readonly VITE_SENTRY_DSN?: string;
  readonly VITE_SENTRY_ENVIRONMENT?: string;
  readonly VITE_SENTRY_RELEASE?: string;
}

interface ImportMeta {
  readonly env: ImportMetaEnv;
}
