# ADR 0046 — A projeção de engenharia é somente leitura, e a idempotência é por identidade de entrega

**Status:** aceita
**Data:** 27/08/2026
**Fase:** transversal — integração Pulse ↔ GitHub

## Contexto

A [ADR 0040](0040-pulse-github-one-sem-clickup-ou-make.md) deu ao GitHub a verdade de Issue, PR e
CI, e ao Pulse a operação de negócio. A [FDD 040](../fdd/040-provisionamento-de-issue-github.md)
entregou o primeiro sentido dessa ligação: o Pulse provisiona a Issue e guarda `repository`,
`github_issue_number`, URL e `correlation_id`. O sentido de volta ficou explicitamente fora daquele
recorte — "webhooks GitHub, sync de PR, One, LangGraph, RabbitMQ e Outbox ficam fora desta fatia".

O resultado prático é que quem opera a entrega no Pulse não tem como saber se o trabalho de
engenharia daquele projeto está aberto, se virou PR, ou se aquele PR passou. A pergunta é
respondida hoje trocando de ferramenta, e a resposta que volta não tem como ser conferida contra
nada.

Três decisões precisam ser tomadas juntas, porque cada uma sozinha produz um defeito diferente:
**quem pode escrever**, **como uma entrega repetida se comporta** e **o que a tela mostra quando o
Pulse deixou de saber**.

## Decisão

**D1. O Pulse projeta e referencia; não bifurca estado técnico e não escreve de volta.** A
superfície é `ReadOnlyModelViewSet`, e isso é estrutura e não convenção — a Issue #41 diz que
edição normal do Pulse não reescreve estado de engenharia sem um contrato de comando separadamente
autorizado. Reabrir Issue, re-disparar CI e reprovisionar estão **desenhados** no
[DAP GH-41 r1](../design/dap-gh41-r1/README.md) e **não construídos**; até existirem, não são
renderizados — nem desabilitados, nem cinzas, nem escondidos atrás de menu. Controle inerte no
produto é defeito, não marcador de lugar.

**D2. A projeção pendura no `EngineeringHandoff`, não no `Project`.** `Project.engineering_handoffs`
é 0..N. Pendurá-la no projeto obrigaria a eleger "a" referência de cada projeto, e essa eleição não
existe no modelo de dados — é a razão de o painel ser uma lista e não um cartão.

**D3. A idempotência é em dois níveis, e os dois são obrigatórios.**

1. **Por identidade de entrega.** `X-GitHub-Delivery` é único em `GithubDelivery`; a reentrega bate
   na unicidade e vira no-op, com 200. É o `event_id` que a
   [ADR 0037](0037-backbone-event-driven-outbox-e-idempotencia.md) elegeu como chave padrão de
   deduplicação, e é o nível que os dois webhooks anteriores deste repositório **não** têm: e-sign
   e pagamento deduplicam por *igualdade de estado*, o que resolve a reentrega idêntica e não
   resolve nem a entrega atrasada nem o replay de uma entrega capturada.
2. **Por ordem.** Um evento cujo `source_updated_at` — o carimbo **do GitHub** — seja anterior ao já
   persistido é descartado, e o descarte vai para o log. O GitHub entrega *at least once* e não
   garante ordem: sem esta guarda, um `pull_request` de dez minutos atrás chegando depois do de
   agora derrubaria o `head` atual, e o painel afirmaria com confiança uma revisão que já não é a
   revisão.

Registrar a entrega e aplicar o evento acontecem na **mesma transação**. Separá-las abre a pior
combinação possível: entrega marcada como processada, efeito nenhum gravado, e o GitHub sem motivo
para reentregar.

**D4. Isto não é o backbone da ADR 0037, e não finge ser.** Nada de Outbox, RabbitMQ ou envelope de
evento versionado. `GithubDelivery` é registro de entrega processada e nada mais. O que se adota
aqui é a **regra** de idempotência daquela ADR, não a sua infraestrutura — que continua pendente e
continua tendo o próprio custo a justificar.

**D5. Falha fechada, como toda integração desta casa.** Sem `GITHUB_WEBHOOK_SECRET`, o endpoint
**recusa** em vez de aceitar o que não consegue verificar — é a
[ADR 0018](0018-integracao-ligada-por-padrao-quando-configurada.md) aplicada: sem credencial não
existe ligada. Evento desconhecido, em compensação, responde **200 "ignorado"**: um erro faria o
GitHub reentregar em laço e, depois de uma sequência de respostas ruins, desabilitar o hook.

Duas coisas do esquema do Stripe (`payments.py`) **não** foram copiadas, e a razão é que elas não
existem do outro lado. Tolerância de timestamp: o header do GitHub não carrega carimbo, e o que
fecha a janela de replay aqui é a unicidade da entrega. Múltiplas assinaturas: lá elas existem
porque o Stripe manda dois `v1` durante a rotação de segredo, e o GitHub manda exatamente uma.

**D6. Webhook e reconciliação, e não um dos dois.** O webhook é o caminho rápido; um job periódico
relê no GitHub o que envelheceu e cria a projeção que nunca chegou. **Um evento que não chegou não
avisa que não chegou** — entrega perdida, hook desligado por engano e janela de indisponibilidade do
GitHub só se recuperam por releitura. O job reusa `github_issues.GithubIssuesApi`, estendido com as
leituras que faltavam: um segundo cliente HTTP para o mesmo fornecedor traria uma segunda política
de timeout, de erro e de redação de token.

**D7. O que é "obsoleto" é decisão do backend.** `GITHUB_PROJECTION_STALE_AFTER_SECONDS` é o único
lugar onde o limiar existe, e `is_stale`/`age_seconds` chegam calculados à tela. O mesmo limiar
recorta a varredura da reconciliação. Deixar o cálculo para o frontend criaria duas definições de
"velho" — a da tela e a do job — divergindo em silêncio na primeira vez que alguém mexesse numa
delas, e abriria a janela em que o painel já diz que não sabe mais enquanto o job ainda acha cedo
para reler.

**D8. Erro nunca apaga a projeção anterior, e os três erros são três.** Rede ou 5xx →
`unavailable`; 401/403 → `forbidden`; 404 → `missing`. A separação é pela **ação corretiva** e não
pela severidade: GitHub fora do ar passa sozinho, permissão negada exige alguém mexer no token,
referência ausente exige consertar o vínculo. Uma copy única ("não foi possível carregar")
esconderia justamente a diferença que decide quem age. Numa projeção que ainda não existe, a falha
**não cria linha**: uma linha sem estado observado mostraria os defaults do modelo como se fossem
observação.

**D9. `merge` não é `DONE`.** "PR merged" é verde de terminal esperado *em engenharia*, e nem o
modelo nem a tela escrevem qualquer palavra de conclusão de negócio. O aceite continua sendo do One
(ADR 0040).

## Consequências

O Pulse passa a responder "como está a engenharia deste projeto?" sem trocar de ferramenta, e a
resposta vem sempre com a proveniência colada — quando e por onde foi observada. A superfície fica
somente-leitura por construção, então nenhuma tela pode acidentalmente virar um segundo lugar onde
o estado de engenharia é decidido.

Em troca: um segredo novo a operar (`GITHUB_WEBHOOK_SECRET`), um job a mais no agendador e uma
tabela de entregas que só cresce. Não há purga de `GithubDelivery` neste recorte — a linha é
pequena (id, evento, carimbo), mas o crescimento é linear no volume de eventos do repositório e
precisará de uma política própria antes de a integração ficar ligada por muito tempo.

Fica também uma dependência declarada: o vínculo PR → Issue sai das **palavras de fechamento** do
GitHub (`closes #41`, `fixes acme/repo#37`). É o mecanismo que o próprio fornecedor documenta, e é
o único determinístico — inferir por nome de branch seria adivinhar. Um PR que não escreve a palavra
não aparece no painel até que a reconciliação o encontre por outro caminho, e hoje ela não tem
esse caminho: a descoberta do PR é do webhook, e a reconciliação atualiza o que já se conhece.

## Alternativas consideradas

**Deduplicar por igualdade de estado, como o e-sign e o pagamento.** Rejeitada: resolve a reentrega
idêntica e nada mais. Uma entrega atrasada carrega um estado *diferente* — o anterior — e passaria
pela comparação de igualdade sem hesitar.

**Só webhook, sem reconciliação.** Rejeitada pela assimetria do silêncio: o webhook que chega é
observável e o que não chega não é. Uma integração cujo modo de falha é "nada acontece" precisa de
alguém que pergunte de tempos em tempos.

**Só reconciliação, sem webhook.** Rejeitada pelo custo e pela latência: transformaria cada mudança
de CI numa espera de até um ciclo de varredura, e multiplicaria as chamadas à API por projeção e
não por evento.

**Guardar o payload bruto de cada entrega.** Rejeitada: é o começo de um outbox sem ser um outbox,
e traria conteúdo de terceiro para dentro do banco sem que ninguém tenha decidido retê-lo.

**Bifurcar o estado técnico em modelos próprios de PR e de check run.** Rejeitada pela ADR 0040:
"Pulse não replica o detalhe técnico do GitHub". A linha do painel responde "aquela revisão passou?",
e enumerar jobs ali seria reconstruir a tela do GitHub dentro do Pulse.
