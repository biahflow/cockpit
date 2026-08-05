# Runbook — testes de carga

Como medir o portal sob concorrência (FDD 022, ADR 0014). O gate que roda a cada PR **não** está
aqui: é o orçamento de query em `backend/tests/regression/test_aggregate_query_budget.py`, que roda
dentro do `pytest`. Este documento é sobre o k6, que é operado à mão.

A pergunta que tudo aqui existe para responder: **quantos clientes cabem antes de o painel ficar
lento — e qual rota cede primeiro?**

## Antes de qualquer coisa: suba os tetos

> **Sem isto, você mede o throttle, não a aplicação.**

O teto de requisição do DRF é **por usuário** (ADR 0009). O default de `USER_RATE` é 2000/hour, isto
é, **≈0,55 requisição por segundo**. Qualquer perfil sério colhe 429 antes de encostar no Django, e
o relatório do k6 vai descrever a velocidade com que o portal recusa gente.

Foi exatamente o defeito do `loadtests/dashboard.js` original: 20 VUs em um cookie só, contra um
teto por usuário. Ele não podia passar nos próprios thresholds.

No ambiente de carga — **nunca em produção**:

```bash
export USER_RATE=1000000/hour
export ANON_RATE=1000000/min
export LOGIN_RATE=10000/min   # o escopo 'login' é 10/min: cada VU faz o próprio login
docker compose -f docker-compose.prod.yml up -d
```

Os scripts já fazem um login por VU (e **não** um por iteração, que estouraria o escopo `login`),
mas o teto de usuário continua valendo para as leituras.

## Preparar o ambiente

Carga contra base vazia não mede nada: os agregadores varrem a base inteira, e é o volume que os
faz doer. Um ambiente útil tem centenas de clientes e projetos, com marcos, tarefas, reuniões e
pendências — a mesma forma que a fixture `seed()` do teste de orçamento usa, em outra escala.

```bash
# usuário dedicado à carga, com papel admin (os agregadores são fechados por função)
docker compose -f docker-compose.prod.yml exec api uv run python manage.py createsuperuser
export LOAD_USER=carga LOAD_PASSWORD='...'
export BASE_URL=http://localhost:19000
```

Use dados sintéticos. Nunca aponte um teste de carga para a base de um cliente.

## Rodar

```bash
# leitura: os agregadores que varrem a base (dashboard, overview, risk, health, analytics)
k6 run -e BASE_URL -e LOAD_USER -e LOAD_PASSWORD loadtests/aggregates.js

# escrita: o caminho comercial até a conversão em projeto
k6 run -e BASE_URL -e LOAD_USER -e LOAD_PASSWORD loadtests/journey.js
```

`journey.js` **cria dado e não limpa atrás de si** — ambiente descartável. Ele não toca em nenhuma
ação de IA: cada `/summary/`, `/proposal/` ou `/contract/` custa uma chamada a um LLM externo, e o
número medido seria a latência do fornecedor (com a conta junto).

## Ler o resultado

Os thresholds são **por rota** (`http_req_duration{rota:...}`), não um p95 global. Um p95 global é
dominado pela rota mais chamada e esconde justamente a que degradou.

| Sintoma no k6 | O que costuma ser |
|---|---|
| `http_req_failed` alto com status 429 | teto de requisição — releia a primeira seção |
| `/api/v1/analytics/` acima do orçamento e o resto bem | esperado até certo ponto: é o mais pesado em SQL (funil, ROI por cliente e por serviço). Se piorou sem mudança de código, olhe o volume da base |
| **todas** as rotas degradando juntas | saturação de CPU ou de pool de conexão, não uma rota específica |
| uma rota degradando **com a base**, as outras estáveis | N+1 novo. O gate do CI deveria ter pego: confira se a rota está no `AGGREGATES` de `test_aggregate_query_budget.py` |
| latência boa e `/readyz` lento | banco ou cache no limite (a sonda toca nos dois) |

Para achar uma requisição específica no servidor, use o `X-Request-ID` que volta na resposta: ele é
o mesmo da linha de log da aplicação e da tag do Sentry (FDD 020, `monitoramento.md`).

`/healthz` e `/readyz` são middleware — respondem sem sessão, sem throttle e antes do
`ALLOWED_HOSTS`. Servem de ramp-up e, durante a corrida, de sinal de saturação: `/readyz` lento
enquanto o resto ainda responde é o banco cedendo antes da aplicação.

## O que o CI cobre sozinho

O orçamento de query reprova o PR quando um agregador passa a emitir mais queries com a base maior —
isto é, N+1 novo. Ele **não** cobre latência: uma query que dobre de tempo sem mudar a contagem passa
pelo CI, e é para isso que este runbook existe. Decisão e justificativa na ADR 0014.

```bash
cd backend && uv run pytest tests/regression/test_aggregate_query_budget.py -v
```
