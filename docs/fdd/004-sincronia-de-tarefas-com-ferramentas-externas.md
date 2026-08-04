# FDD 004 — Sincronia de tarefas com ferramentas externas (Linear/GitHub)

## Jornada

A equipe de entrega trabalha as tarefas onde prefere (Linear/GitHub), mas o Biahflow continua
sendo a fonte da verdade (ADR 0004). Um usuário vincula uma tarefa a uma issue existente
(`link-external`) ou cria a issue a partir da tarefa (`push-external`). A partir daí, quando a
issue muda no fornecedor, um webhook de entrada atualiza o status da tarefa no Biahflow; quando a
tarefa muda no Biahflow, a issue vinculada é atualizada. A mudança de status também repropaga
automaticamente para o portal do cliente (sinal já existente).

## Regras

- A integração fica atrás de flag (`tasksync`), desligada por padrão; sem ela, os endpoints de
  saída retornam 503 e o webhook de entrada retorna 401 (token vazio = recusado).
- O webhook de entrada autentica por token compartilhado (header `X-Sync-Token`), no padrão do
  intake de leads.
- A entrada acha a tarefa por `(source, external_id)`; sem vínculo → 404; status externo fora do
  de-para → 422. O de-para de status é explícito e não perde informação.
- O vínculo `(source, external_id)` é único por tarefa (constraint parcial); duplicar → 409.
- A aplicação da entrada é feita sob um guard de eco: o salvamento resultante não repropaga para o
  fornecedor, evitando loop.
- Nenhum dado comercial é enviado ao fornecedor; só título, descrição e status.

## Aceite

Com a flag ligada, uma mudança de status na issue vinculada atualiza a tarefa (e o portal), e uma
mudança na tarefa vinculada atualiza a issue, sem loop.

## Regressão crítica

A entrada nunca dispara a saída (guard de eco); um vínculo duplicado é recusado com 409; com a
integração desligada, nenhuma chamada externa é feita.
