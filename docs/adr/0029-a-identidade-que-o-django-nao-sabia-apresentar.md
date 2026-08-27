# ADR 0029 — A identidade que o Django não sabia apresentar

**Status:** aceita
**Data:** 12/08/2026
**Fecha:** metade do "fica aberto" da ADR 0048 do portal do cliente — o nosso lado
**Relacionadas:** ADR 0003 (integração com o portal), ADR 0016 (auth do Google sem chave),
ADR 0048 e 0051 do `biahflow-portal-cliente`

## Contexto

Em homologação na GCP, a `portal-api` do portal do cliente sobe com ingress interno **e**
`run.invoker` concedido a uma conta só. Conferido na nuvem: a política daquele serviço tem
exatamente uma ligação, para `hml-execucao`.

O `_post` deste repositório mandava dois headers — `Content-Type` e
`X-Biahflow-Signature` — e **nenhuma identidade**. A chamada levaria **403 do Cloud Run,
antes de a aplicação existir**: sem corpo, sem log nosso, e sem nada que distinga isso de
um webhook que não saiu.

Havia um segundo bloqueio, e ele **escondia o primeiro**: `PORTAL_WEBHOOK_URL` não estava
declarada no Terraform de HML. Sem a URL, `emit` retorna na primeira linha e nada é
emitido — de modo que o 403 nunca chegava a acontecer, e a falha se parecia com "ainda não
configuramos". Os dois entram juntos por isso.

**A identidade já estava certa.** Este processo roda como `hml-execucao`, que é a conta
com a permissão. Não faltava IAM, nem segredo, nem Terraform de permissão: faltava
apresentar.

## Decisão

### `service_identity.py`, e não `google_auth.py`

São perguntas diferentes, e misturá-las seria o começo de um módulo que responde duas.
`google_auth.py` é **como o portal se autentica no Google** (ADR 0016): token de acesso
com escopo, para Drive e Calendar. Este é **como este serviço se identifica para outro
serviço nosso**: ID token com audiência, cunhado no metadata server.

O módulo é a tradução de `app/lib/serviceIdentity.ts` do outro repositório, e a ADR 0048
de lá previu esta falta com todas as letras: *"não há equivalente em Python"*.

### `Authorization` puro, e não `X-Serverless-Authorization`

É a diferença que o outro lado não tinha. O BFF precisou de um header próprio porque o
`Authorization` dele **já carregava o token do usuário**, e o Cloud Run consome o
`Authorization` sem repassá-lo — sobrepor os dois faria a API perder o principal e
responder 401 a uma chamada autorizada.

Aqui não há o que preservar: a rota do webhook autentica por HMAC em header próprio
(`X-Biahflow-Signature`) e **nunca lê `Authorization`**. Usar o header padrão é o mais
simples que funciona, e o comentário no código diz por quê — senão alguém "corrige" para
o header do BFF por simetria e perde a razão.

### A guarda de `K_SERVICE` é obrigatória, não zelo

Fora do Cloud Run não existe metadata server. Sem a guarda, **cada webhook pagaria um
timeout** — e o lugar onde isso aconteceria é o pior possível: `_post` roda numa thread
daemon com 5 s no total, então a espera comeria o orçamento inteiro da entrega. No compose
o alvo é `host.docker.internal`, onde barreira nenhuma existe: seria custo pago para não
comprar nada.

Fora do Cloud Run a função devolve `None`, e `_post` manda o que sempre mandou.

### Sem token não é erro

`emit` é best-effort por decisão registrada (ADR 0003, emenda da ADR 0018): sem retry, sem
fila, com o motivo escrito. Transformar "não consegui cunhar" em exceção mudaria esse
contrato pela porta dos fundos — e num caminho que roda em thread, uma exceção não teria
nem quem a lesse.

## Consequências

- **Fecha um sentido, não dois.** O outro chamador Python — `portal-api → biahflow-api` —
  mora no *outro* repositório, e continua sem identidade de serviço. Ele só não dói porque
  aquela API está com `allUsers`; se voltar a ser interna, quebra de novo e em silêncio,
  exatamente como a ADR 0048 escreveu. **Este módulo não a conserta**, e vale dizer isso
  porque a suposição contrária é fácil.
- **Zero dependência nova.** `google-auth` já estava no `pyproject.toml` para Drive e
  Calendar, e `requests` já vinha transitivo.
- **O cache é por audiência e tem margem antes da expiração.** São doze receivers
  emitindo webhook; uma ida ao metadata por evento seria custo puro, e um token que vence
  no voo vira 403 intermitente — o pior tipo, porque some quando alguém vai olhar.
- **Fica aberto: a entrega continua sem rede de segurança.** Um webhook perdido se perde,
  e a recuperação é backfill manual. Esta ADR melhora a chance de a entrega **começar**;
  não muda o que acontece quando ela falha.
- **Fica aberto: a sonda de `portal` continua não sondável.** `check_integrations` reporta
  a flag como sem sonda disponível, então "ligada" continua significando "as duas
  variáveis estão preenchidas" e não "o outro lado responde". Com o ID token isso passou a
  ser testável de verdade — bastaria um `HEAD` autenticado —, e não foi feito aqui.
