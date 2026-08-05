/**
 * Sessão autenticada por VU (FDD 022).
 *
 * O script anterior (`dashboard.js`) mandava **um** `SESSION_COOKIE` para os 20 VUs, vindo de
 * fora por variável de ambiente. Duas consequências, e as duas invalidam a medição:
 *
 * 1. O teto de requisição do DRF é **por usuário** (`USER_RATE`, ADR 0009). Vinte VUs num
 *    cookie só somam no mesmo contador, e o que se mede vira a velocidade do `throttle`, não a
 *    da aplicação. Com o default de 2000/hour (≈0,55 req/s) o 429 chega em segundos.
 * 2. Um cookie colhido à mão expira, e o teste passa a medir a latência do 403.
 *
 * Aqui cada VU faz o próprio login no `setup`/primeira iteração e carrega o próprio jar de
 * cookies. Ainda assim, **suba os tetos no ambiente de carga** — ver
 * `docs/runbooks/testes-de-carga.md`. Mesmo um usuário por VU esbarra em 2000/hour.
 */

import http from "k6/http";
import { check, fail } from "k6";

export const BASE_URL = __ENV.BASE_URL || "http://localhost:19000";

/**
 * Autentica e devolve os headers a usar nas requisições seguintes.
 *
 * A sessão é cookie + CSRF (não token): o `jar` do k6 guarda `sessionid` e `csrftoken`
 * sozinho, mas o header `X-CSRFToken` precisa ser mandado à mão em toda escrita, como o SPA
 * faz em `src/api.ts`.
 */
export function login(username, password) {
  const jar = http.cookieJar();

  const semente = http.get(`${BASE_URL}/api/v1/auth/csrf/`);
  if (!check(semente, { "csrf respondeu 200": r => r.status === 200 })) {
    fail(`não foi possível iniciar sessão segura: ${semente.status}`);
  }
  const csrf = semente.json("csrfToken");

  const entrada = http.post(
    `${BASE_URL}/api/v1/auth/login/`,
    JSON.stringify({ username, password }),
    { headers: { "Content-Type": "application/json", "X-CSRFToken": csrf } },
  );
  if (!check(entrada, { "login respondeu 200": r => r.status === 200 })) {
    // Falhar alto e cedo: sem isto o teste inteiro roda contra 403 e reporta uma latência
    // ótima — a de negar acesso.
    fail(`login falhou (${entrada.status}). Confira LOAD_USER/LOAD_PASSWORD e o teto 'login' (10/min).`);
  }

  // O `csrftoken` roda no login; o de escrita tem de ser o de depois.
  const cookies = jar.cookiesForURL(`${BASE_URL}/`);
  return {
    "Content-Type": "application/json",
    "X-CSRFToken": cookies.csrftoken ? cookies.csrftoken[0] : csrf,
  };
}

/** Credenciais do ambiente de carga. Nunca as de produção. */
export function credenciais() {
  return [__ENV.LOAD_USER || "carga", __ENV.LOAD_PASSWORD || ""];
}

/**
 * Marca a resposta e devolve se ela serve.
 *
 * 429 vira uma mensagem explícita porque é o erro que mais confunde aqui: parece saturação da
 * aplicação e é só o teto de requisição do próprio portal.
 */
export function conferir(resposta, rota) {
  return check(resposta, {
    [`${rota} respondeu 200`]: r => r.status === 200,
    [`${rota} não bateu no teto (429)`]: r => r.status !== 429,
  });
}
