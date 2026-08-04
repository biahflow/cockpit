import http from "k6/http";
import { check } from "k6";

export const options = {
  vus: 20,
  duration: "30s",
  thresholds: { http_req_failed: ["rate<0.01"], http_req_duration: ["p(95)<1000"] },
};

export default function () {
  const response = http.get(`${__ENV.BASE_URL}/api/v1/dashboard/`, {
    headers: { Cookie: __ENV.SESSION_COOKIE || "" },
  });
  check(response, { "resposta de painel válida": result => result.status === 200 });
}
