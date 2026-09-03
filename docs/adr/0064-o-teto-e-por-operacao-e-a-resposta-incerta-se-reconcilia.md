# ADR 0064 — O teto é por operação, e a resposta incerta se reconcilia

**Status:** aceita
**Data:** 2026-09-03
**Depende de:** ADR 0031 (WhatsApp é canal novo, não gate novo) · ADR 0059 (a suíte não atravessa a
rede para provar um adapter) · ADR 0062 (o fallback de WhatsApp não assume quando não sabe, e
`UNCERTAIN` não cai para o próximo provedor) · FDD 008 (emenda de 03/09/2026 — o kickoff é o
chamador)
**Implementada por:** `backend/apps/core/whatsapp.py` (`_timeout`, `_body`,
`UazapiProvider.find_group`/`read_group_list`, `_reconcile_group`) ·
`WHATSAPP_GROUP_TIMEOUT_SECONDS` em `config/settings.py`

## Contexto

A ADR 0062 entregou o adaptador de WhatsApp com o desenho do fallback decidido sozinho, de
propósito, antes de existir chamador. O preço dessa escolha foi uma temporada inteira sem ninguém
exercitá-lo contra o fornecedor real. A primeira chamada real de `create_group` contra a UAZAPI, em
**03/09/2026**, cobrou o preço:

- o adaptador devolveu `Delivery.UNCERTAIN`, sem `group_id`;
- **o grupo tinha sido criado**: `120363431743499021@g.us`, 11:47:18Z;
- nada no produto ficou sabendo dele.

**A classificação não errou.** `_from_error` trata `TimeoutError` como `UNCERTAIN` de propósito —
distinguir "estourou antes de enviar" de "estourou esperando resposta" não é confiável, e o erro
caro é o duplicado. O que estava errado era o teto, e o que faltava era o que fazer depois dele.

`WHATSAPP_TIMEOUT_SECONDS` valia 15s e `_request` o aplicava a **toda** chamada. Mandar um texto é
falar com o provedor. Criar um grupo é o provedor falando com a rede do WhatsApp e esperando o grupo
existir do outro lado. Outra ordem de grandeza de latência, mesmo teto.

## Decisão

### O teto é por operação, e não um só para tudo

`_request` ganha `timeout: float | None = None`, e o teto efetivo sai de `_timeout(timeout)`:
`timeout or settings.WHATSAPP_TIMEOUT_SECONDS`. Os dois `create_group` de provedor passam
`WHATSAPP_GROUP_TIMEOUT_SECONDS` (default 90); `send_text`, `send_group_text` e `ping` não passam
nada e continuam exatamente onde estavam.

**O que se mediu e o que não se mediu, explicitamente:** mediu-se que 15s é curto — o grupo nasceu e
a resposta não voltou. **Não** se mediu quanto a UAZAPI leva de fato. 90 é folga escolhida, não
número apurado.

A resolução mora em `_timeout`, e não escondida dentro de `_request`, pelo motivo de `classify`:
`_request` é a única função que toca a rede e fica fora da cobertura (ADR 0059), então regra
enterrada ali é regra que nenhum teste alcança.

### Um teto maior não é o conserto — ele só torna o caso raro

Caso raro não tratado é o pior tipo: acontece pouco o bastante para ninguém desenhar tratamento, e
o bastante para doer. Por isso o teto vem **acompanhado** de reconciliação.

Quando `create_group` termina em `UNCERTAIN`, o módulo pergunta ao provedor se existe um grupo com
aquele nome. Achou **exatamente um** → o resultado vira `DELIVERED` com o `group_id` recuperado, e
o `detail` diz que veio de reconciliação. Zero, dois ou mais, ou provedor que não sabe responder →
fica `UNCERTAIN`, como antes.

Três restrições, e nenhuma é zelo:

**Contra o mesmo provedor que respondeu**, o da última tentativa (`result.attempts[-1].provider`), e
não contra todos: um grupo criado pela Z-API não existe do lado da UAZAPI — a mesma razão já escrita
na docstring de `send_group_text`.

**Casamento exato e único de nome.** Dois grupos com o mesmo nome significam que não se sabe qual é o
novo; escolher um seria gravar a **referência errada**, que é pior do que não gravar nenhuma — com
ela quem opera acha que sabe, sem ela sabe que não sabe. O nome é comparado com `strip()` dos dois
lados e nada mais: normalizar acento ou caixa abriria casamento falso entre grupos que o WhatsApp
considera diferentes.

**Uma `Attempt` a mais no rastro.** "Por onde isto passou?" tem de continuar respondendo a verdade,
e o `detail` do resultado reconciliado precisa separar "respondeu na hora" de "achamos depois" —
os dois chegam ao chamador como `DELIVERED`.

### A capacidade é opcional, porque um dos provedores não tem endpoint verificado

`find_group` **não** entra no `Protocol` como método obrigatório. A UAZAPI documenta
`GET /group/list`; a Z-API **não tem endpoint verificado** para isso. Declarar o método obrigatório
obrigaria a inventar o caminho da Z-API, e **endpoint suposto em código de produção é pior do que
capacidade ausente** — a ausência ao menos aparece no `detail` e no log.

O consumo é por `getattr(provider, "find_group", None)`, o mesmo padrão com que
`integrations._probe_esign` e `_probe_payments` tratam o `ping` opcional. A Z-API entra no dia em
que o endpoint for **verificado** na documentação dela, não suposto.

### `_body` para de descartar array no topo

`_body` devolvia `{}` para qualquer JSON que não fosse objeto. Uma listagem de grupos é justamente a
resposta que chega como array no topo, e a reconciliação receberia corpo vazio: **nunca acharia
nada, e não erraria** — o pior modo de falha possível aqui. O array passa a ser embrulhado
(`{"items": [...]}`), preservando o dado e mantendo o retorno `dict`, de que `classify` e
`_provider_error` dependem. A leitura aceita as duas formas (`groups` ou `items`), porque a
documentação do fornecedor não fixa qual delas vem.

## Consequências

- **A ADR 0062 fica de pé, e esta não a revoga.** `UNCERTAIN` continua **não** caindo para o próximo
  provedor: reconciliar é perguntar, não reenviar, e por isso não duplica nada.
- **Um `UNCERTAIN` reconciliado com sucesso vira `DELIVERED` para o chamador.** A distinção
  sobrevive no `detail` e no `attempts`; quem só olha o `status` a perde, e é uma perda aceita —
  o chamador quer saber se tem referência para guardar.
- **Grupo criado com nome duplicado continua perdido.** Por desenho: o produto prefere a lacuna
  declarada à referência inventada. Quem opera tem o log com o nome procurado e a contagem de
  casamentos.
- **A reconciliação da Z-API não existe.** Um `UNCERTAIN` criando grupo pela Z-API permanece
  `UNCERTAIN`, sem estourar.
- **90 segundos seguram quem chamou.** O chamador é `kickoff.finalize`, que roda depois do commit e
  é best-effort, então o custo é latência de uma resposta HTTP já concluída — não de uma transação
  aberta. Se um dia o kickoff for chamado de dentro de um request síncrono com transação viva, este
  número precisa ser revisitado.

## Alternativas consideradas

**Só aumentar o teto.** Rejeitada: torna o caso raro sem tratá-lo, e é o caso raro que perde
referência de grupo criado com cliente dentro.

**Deixar `UNCERTAIN` cair para o segundo provedor na criação de grupo.** Rejeitada pela razão da
ADR 0062, agravada aqui: dois grupos com o mesmo cliente é pior que duas mensagens iguais — o
cliente vê duas janelas de conversa e não sabe em qual falar.

**Escolher o mais recente entre vários casamentos de nome.** Rejeitada: exigiria confiar num campo
de data que a documentação do fornecedor não garante, para decidir qual referência gravar. Uma
referência errada é pior do que nenhuma.

**Chave de idempotência na criação.** É a solução correta, e nenhum dos dois provedores a oferece —
a mesma conclusão da ADR 0062 para o envio. Se algum passar a oferecer, esta ADR merece revisão.

**Reconciliar por polling num job do scheduler.** Rejeitada por ora: o `UNCERTAIN` é raro, a
resposta do provedor é imediata, e uma pergunta síncrona logo depois resolve sem tabela nova. Se o
volume justificar, o desenho correto é outbox — o mesmo que a ADR 0062 já reserva para o envio.
