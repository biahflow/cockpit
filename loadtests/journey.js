/**
 * Perfil de escrita: o caminho comercial até a conversão em projeto (FDD 022).
 *
 * Leitura é o que mais acontece, mas não é o que trava: a conversão
 * (`convert-to-project`) é a ação central do domínio e a única que abre transação, cria
 * projeto, semeia o kickoff inteiro (marcos, tarefas, pasta, e-mail) e depende de um
 * `OneToOneField` para garantir que uma oportunidade ganha vire projeto **exatamente uma vez**
 * (FDD 002, FDD 008). É onde a contenção aparece sob concorrência.
 *
 * **Não toca em nenhuma ação de IA.** Cada `/summary/`, `/proposal/` ou `/contract/` custa uma
 * chamada a um LLM externo: o número medido seria a latência do fornecedor, e a conta viria
 * junto. Carga de IA é outro exercício, com o cliente mockado.
 *
 * Roda contra ambiente de carga descartável — ele **cria dado** e não limpa atrás de si.
 */

import http from "k6/http";
import { check, sleep } from "k6";

import { BASE_URL, conferir, credenciais, login } from "./lib/session.js";

export const options = {
  vus: 5,  // baixo de propósito: escrita mede contenção, não vazão
  duration: "1m",
  thresholds: {
    http_req_failed: ["rate<0.01"],
    "http_req_duration{rota:convert}": ["p(95)<3000"],  // abre transação e semeia o kickoff
    "http_req_duration{rota:criar-oportunidade}": ["p(95)<1000"],
  },
};

let headers;
let etapaGanha;
let cliente;

function preparar() {
  headers = login(...credenciais());

  const etapas = http.get(`${BASE_URL}/api/v1/pipeline-stages/`, { headers }).json();
  etapaGanha = etapas.find(etapa => etapa.kind === "won");
  check(etapaGanha, { "existe etapa 'ganha' no pipeline": Boolean });

  const criado = http.post(
    `${BASE_URL}/api/v1/clients/`,
    JSON.stringify({ name: `Carga ${__VU}-${Date.now()}`, status: "prospect" }),
    { headers, tags: { rota: "criar-cliente" } },
  );
  conferir(criado, "criar-cliente");
  cliente = criado.json("id");
}

export default function () {
  if (!headers) preparar();

  const oportunidade = http.post(
    `${BASE_URL}/api/v1/opportunities/`,
    JSON.stringify({
      client: cliente,
      title: `Discovery de automação ${__VU}-${__ITER}`,
      scope: "Mapeamento de processos.",
      estimated_value: "150000.00",
      stage: etapaGanha.id,
      expected_close_date: new Date().toISOString().slice(0, 10),
    }),
    { headers, tags: { rota: "criar-oportunidade" } },
  );
  if (!conferir(oportunidade, "criar-oportunidade")) return;

  // A action recebe o corpo de um `Project` (ela valida com o `ProjectSerializer`), e o
  // cliente precisa ser o mesmo da oportunidade — senão responde 400.
  const hoje = new Date();
  const prazo = new Date(hoje.getTime() + 30 * 864e5);
  const projeto = http.post(
    `${BASE_URL}/api/v1/opportunities/${oportunidade.json("id")}/convert-to-project/`,
    JSON.stringify({
      client: cliente,
      name: `Implantação ${__VU}-${__ITER}`,
      start_date: hoje.toISOString().slice(0, 10),
      due_date: prazo.toISOString().slice(0, 10),
    }),
    { headers, tags: { rota: "convert" } },
  );
  // 201 é o caminho feliz aqui; `conferir` cobra 200, então a checagem é própria.
  check(projeto, {
    "convert-to-project criou o projeto": r => r.status === 201,
    "convert-to-project não bateu no teto (429)": r => r.status !== 429,
  });

  sleep(1);
}
