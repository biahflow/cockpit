# ADR 0062 — O fallback de WhatsApp não assume quando não sabe

**Status:** aceita
**Data:** 2026-09-02
**Depende de:** ADR 0016 (como o portal se autentica no Google) · ADR 0018 (`is_enabled` passa a
respeitar `configured`) · ADR 0031 (o degrau sai sozinho, o texto da IA não) · ADR 0059 (a suíte não
atravessa a rede para provar um adapter) · ADR 0060 (publicável é campo próprio) ·
`docs/ontology/language-map.md` §3 e §6, invariante 15
**Implementada por:** `backend/apps/core/whatsapp.py` · sonda em `integrations.py` · flag `whatsapp`

## Contexto

O ciclo do Design Partner passou a mandar e-mail ao cliente (ADR 0061). O passo seguinte pedido foi
WhatsApp — canal onde o cliente já está — para coordenação do Discovery, incluindo um grupo por
projeto.

Três coisas moldam a decisão, e nenhuma é sobre código:

**A casa já decidiu o escopo do canal.** A ADR 0031 fecha com *"a próxima integração de comunicação
com o cliente herda esta regra, e não a redescobre. **WhatsApp é canal novo, não gate novo**"*, e a
FDD 036 repete. A regra operacional adotada agora: **WhatsApp carrega coordenação; o One carrega
conteúdo.** Achado, decisão, custo apurado e entregável atravessam pelo One, atrás da marca de
publicável — mandá-los por WhatsApp **contornaria o gate de revisão humana da ADR 0060 sem ninguém
perceber**. O módulo não impede isso; a docstring é onde a regra fica para quem chamar.

**Os provedores são não oficiais.** Z-API e UAZAPI operam por fora do protocolo oficial da Meta. O
risco assumido, explicitamente, é o número ser banido — e é o número que fala com os clientes. A
API oficial de grupos existe desde 2026, mas exige Official Business Account e limita a 8 membros;
a escolha por ora foi a não oficial, com o custo registrado aqui.

**E o problema que decide o desenho:** com dois provedores, *quando* o segundo assume?

## Decisão

### O resultado tem quatro estados, e não um booleano

O `_http_raw` do `esign.py` engole todo erro em `None`, e o runbook de homologação registra que isso
já produziu um defeito lá: `None` ficou **indistinguível de sucesso**, e a view respondia 201 para
uma assinatura que nunca sairia. Um booleano aqui repetiria o erro num lugar pior, porque decidiria
reenvio.

| Estado | O que significa | Cai para o próximo? |
| --- | --- | --- |
| `DELIVERED` | o provedor aceitou | não |
| `UNAVAILABLE` | **este** provedor não pôde, outro poderia — 401/403, instância fora, conexão recusada | **sim** |
| `REFUSED` | a mensagem é inválida em si — número mal formado, payload rejeitado | não |
| `UNCERTAIN` | timeout, 5xx, conexão cortada — **pode ter entregado** | não |

Os nomes são inglês canônico pela invariante 15. A regra do fallback mora numa **property do enum**
(`tries_the_next_provider`) e não no laço que itera os provedores: é o que impede a decisão de
regredir para "tenta sempre" numa refatoração que ninguém releu.

### O fallback assume só em falha inequívoca

`UNCERTAIN` **não** reenvia. Se a Z-API aceitou e o retorno se perdeu no caminho, tentar a UAZAPI
manda a **mesma mensagem duas vezes** ao cliente — e para "sua sessão é amanhã às 10h", dois avisos
fazem ele ligar perguntando qual vale.

**Aceita-se deixar de enviar para nunca duplicar.** É a escolha entre *at-most-once* e
*at-least-once*, e ela foi feita: numa mensagem de coordenação com pessoa do outro lado, o ruído do
duplicado custa mais que o silêncio de um envio perdido, porque o silêncio tem quem o perceba (o
log, o `attempts`) e o duplicado chega direto ao cliente.

`TimeoutError` é sempre `UNCERTAIN`, mesmo parecendo ter sido na conexão: distinguir "estourou antes
de enviar" de "estourou esperando resposta" não é confiável, e o erro caro é o duplicado.

`REFUSED` também não cai, por outro motivo: o segundo provedor recusaria igual, e insistir só
duplica a falha.

### A mensagem não se perde por escrita dupla — outbox, não fila

Para o envio sobreviver a provedor fora do ar, a intenção é gravada **na mesma transação que gravou
o fato que a causou**, e um job do scheduler drena reprocessando **só** `UNAVAILABLE`.

SQS (com Floci emulando em desenvolvimento) foi considerado e **recusado por ora**: publicar na fila
depois do commit é escrita dupla, e se a publicação falhar a mensagem se perde **exatamente** no
caso que a fila existiria para cobrir. A tabela não tem esse buraco, é durável no Postgres que já
tem backup, roda no `run_scheduler` que já existe com reivindicação por `select_for_update`, e é
testável no pytest — o argumento que o próprio `scheduler.py` faz: *"um crontab não se testa com
pytest, uma tabela de jobs em Python se testa"*. O custo é latência de um tique, irrelevante para
coordenação.

Quando o volume ou o desacoplamento justificarem, o desenho correto é outbox **mais** relay para
fila — não fila no lugar da tabela.

## Consequências

- **Uma mensagem pode não sair, e isso é o comportamento escolhido.** Quem opera vê a tentativa no
  log e no `attempts` de cada resultado, com o provedor e o estado de cada uma.
- **`UNCERTAIN` hoje só é registrada em log.** `notifications.notify` exige destinatário, e o
  adaptador não tem como escolher um — quem sabe de quem era a mensagem é o chamador. **É a dívida
  mais concreta desta entrega**, e o primeiro chamador precisa fechá-la.
- **A Z-API não publica tabela de erros.** Se ela responder 400 para "instância desconectada", o
  módulo classifica `REFUSED` e **não** cai para a UAZAPI — exatamente o caso em que o fallback
  existiria para ajudar. Não corrigido por heurística de string, que seria inventar contrato; quem
  detecta desconexão é a sonda, que usa endpoint próprio e determinístico. **A verificar em uso.**
- **O fallback de mensagem de grupo é mais estreito do que parece:** um id de grupo criado na Z-API
  não existe na UAZAPI. A ordem é respeitada, mas a segunda tentativa só faz sentido para 1:1.
- **Nada dispara mensagem ainda.** O adaptador e a sonda entram sozinhos, de propósito: o desenho do
  fallback se decide sem a pressa de outra feature.

## Alternativas consideradas

**Sempre tentar o segundo provedor.** Rejeitada: maximiza entrega e aceita duplicar sem nunca saber
quando duplicou — porque o caso ambíguo é, por definição, aquele que não respondeu.

**Nunca fazer fallback automático.** Defensável, e teria sido mais simples: uma falha vira aviso e
alguém decide. Rejeitada porque `UNAVAILABLE` é inequívoco e reprocessá-lo é seguro — deixar de
tentar ali seria perder entrega sem ganhar garantia nenhuma.

**Chave de idempotência para tornar o reenvio seguro.** É a solução correta do problema, e nenhum
dos dois provedores a oferece. Se algum passar a oferecer, esta ADR merece revisão: com ela,
`UNCERTAIN` poderia reenviar sem duplicar.

**SQS puro.** Rejeitada pela escrita dupla, acima.

**API oficial de grupos da Meta.** Não rejeitada — adiada. Exige Official Business Account
(verificação junto à Meta) e limita grupos a 8 membros. O teto, aliás, trabalha a favor da regra de
escopo: força o grupo a ser o time de trabalho, não "todo mundo".
