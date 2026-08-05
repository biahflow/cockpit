/**
 * Perfil de leitura sobre os agregadores (FDD 022).
 *
 * São as rotas que varrem a base inteira sem paginação — as mesmas que o
 * `tests/regression/test_aggregate_query_budget.py` protege contra N+1 no CI. Lá o gate é
 * contagem de query, determinística; aqui é latência sob concorrência, que só faz sentido
 * contra um banco com volume de verdade.
 *
 * Thresholds **por rota** (`http_req_duration{rota:...}`) em vez de um p95 global: o global é
 * dominado pela rota mais chamada e esconde exatamente a que degradou.
 *
 *   k6 run -e BASE_URL=http://localhost:19000 -e LOAD_USER=carga -e LOAD_PASSWORD=... \
 *     loadtests/aggregates.js
 *
 * Leia `docs/runbooks/testes-de-carga.md` antes: sem subir `USER_RATE`, isto mede o throttle.
 */

import http from "k6/http";
import { sleep } from "k6";

import { BASE_URL, conferir, credenciais, login } from "./lib/session.js";

const ROTAS = [
  "/api/v1/dashboard/",
  "/api/v1/clients/overview/",
  "/api/v1/risk/",
  "/api/v1/health/",
  "/api/v1/analytics/",
  "/api/v1/recommendations/",
];

export const options = {
  stages: [
    { duration: "30s", target: 20 },  // sobe
    { duration: "1m", target: 20 },   // patamar — é daqui que sai o número
    { duration: "15s", target: 0 },   // desce
  ],
  thresholds: {
    http_req_failed: ["rate<0.01"],
    // `/analytics/` é o mais pesado em SQL de todos (funil, ROI por cliente e por serviço) e
    // tem orçamento próprio, maior. Igualar todo mundo em 1s esconderia a degradação das
    // rotas baratas, que é onde a regressão aparece primeiro.
    "http_req_duration{rota:/api/v1/analytics/}": ["p(95)<2000"],
    "http_req_duration{rota:/api/v1/clients/overview/}": ["p(95)<1500"],
    "http_req_duration{rota:/api/v1/dashboard/}": ["p(95)<800"],
    "http_req_duration{rota:/api/v1/risk/}": ["p(95)<1000"],
    "http_req_duration{rota:/api/v1/health/}": ["p(95)<1000"],
    "http_req_duration{rota:/api/v1/recommendations/}": ["p(95)<1000"],
  },
};

// Uma sessão por VU, não por iteração: o escopo `login` tem teto de **10/min** (ADR 0009), e
// relogar a cada volta derruba o teste no próprio endpoint de autenticação. Variável de módulo
// no k6 é por VU, então este `headers` é privado de cada usuário virtual.
let headers;

export default function () {
  if (!headers) headers = login(...credenciais());
  for (const rota of ROTAS) {
    const resposta = http.get(`${BASE_URL}${rota}`, { headers, tags: { rota } });
    conferir(resposta, rota);
  }
  sleep(1);
}
