// Rastreamento de erro do SPA (FDD 020, ADR 0012).
//
// O DSN é **assado no bundle**: `import.meta.env` é substituído em tempo de build, não lido em
// runtime. Por isso ele entra como build arg da imagem do `web` (ver `frontend/Dockerfile`), e
// não no `.env` do servidor. Um DSN de Sentry é público por desenho — ele identifica o projeto e
// só aceita escrita —, então não é segredo de cofre.
//
// O SDK entra por **import dinâmico**, e isso importa porque ele é grande: 475 kB (156 kB gzip),
// mais que o bundle inteiro do portal. Com DSN, ele vira um chunk à parte carregado em paralelo,
// em vez de atrasar a primeira pintura; sem DSN, o `return` abaixo torna o `import()` código morto
// e o Rollup remove o SDK do build — desligado, não sobra um byte de Sentry no `dist/`
// (verificado: `grep sentry dist/assets/*.js` não acha nada). O preço é uma janela de alguns
// milissegundos no boot em que um erro ainda não tem para onde ir.

type SentrySdk = typeof import("@sentry/react");

const dsn = import.meta.env.VITE_SENTRY_DSN ?? "";

let sentry: SentrySdk | null = null;

export async function initSentry(): Promise<boolean> {
  if (!dsn) return false;
  const sdk = await import("@sentry/react");
  sdk.init({
    dsn,
    environment: import.meta.env.VITE_SENTRY_ENVIRONMENT || undefined,
    // Mesma release do backend, para um erro de browser e um de API caírem no mesmo deploy.
    release: import.meta.env.VITE_SENTRY_RELEASE || undefined,
    // Nem PII nem replay: o portal mostra proposta, contrato e dado de cliente na tela.
    sendDefaultPii: false,
    integrations: [],
  });
  sentry = sdk;
  return true;
}

export function isSentryEnabled(): boolean {
  return sentry !== null;
}

// O id que o backend devolveu na última resposta. É o que a tela mostra ao usuário para que
// alguém consiga achar a requisição exata no log do servidor.
let ultimoRequestId = "";

export function setLastRequestId(requestId: string): void {
  ultimoRequestId = requestId;
}

export function getLastRequestId(): string {
  return ultimoRequestId;
}

export function reportError(erro: unknown, contexto: Record<string, unknown> = {}): void {
  const sdk = sentry;
  if (!sdk) return;
  sdk.withScope(escopo => {
    const requestId = (contexto.requestId as string) || ultimoRequestId;
    if (requestId) escopo.setTag("request_id", requestId);
    escopo.setContext("biahflow", contexto);
    sdk.captureException(erro);
  });
}
