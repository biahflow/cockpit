# FDD 034 — O risco que só o prazo denunciava

## Jornada

Este produto já respondia "qual o risco deste projeto" — e respondia **sempre olhando para trás**.
`risk.py` calcula um escore a partir de marco vencido, tarefa parada e prazo estourado; `health.py`
faz o mesmo com outros sinais. Os dois são bons no que fazem, e o que fazem é **detectar o que já
escorregou**. Quando o sinal acende, a coisa já aconteceu: o marco já venceu, a tarefa já parou.

O Delivery System da metodologia FDE (ADR 0030, `docs/metodologia-fde.md`) mantém a outra metade —
um **Risk Register** por projeto, com o risco declarado, sua probabilidade, seu impacto e o plano de
mitigação — e a Delivery Sync semanal existe para consultá-lo. Aqui essa metade não tinha onde
morar. O que se temia ficava numa página do Notion, numa mensagem, ou na cabeça de quem estava na
reunião de kickoff; e o registro que ninguém consulta no ato é o mesmo que não existir, que é
exatamente o defeito que a ADR 0030 nomeou ao trazer a operação para dentro do sistema.

A diferença entre os dois não é de precisão, é de **momento**. O risco calculado chega quando
mitigar já não é possível; o declarado existe enquanto ainda é. Por isso eles convivem na mesma
tela sem se substituir, e por isso o recurso novo é `risco` e não uma extensão de `risk`.

## O que esta fatia entrega

O modelo `Risco` por projeto — título, descrição, probabilidade, impacto, plano de mitigação,
estado e dono —, o CRUD em `/api/v1/riscos/` com o arquivamento reversível da casa, o painel
"Riscos" no detalhe do projeto, e os riscos abertos no contexto do agente de Entrega.

O estado tem **quatro saídas**, e nenhuma delas é sinônimo da outra: `open` (o risco vive),
`mitigated` (foi tratado), `accepted` (a equipe decidiu conviver com ele) e `materialized`
(aconteceu). Colapsar as três últimas em "fechado" apagaria a única informação que um registro de
risco produz ao longo do tempo — a de quantos dos riscos que se temeu viraram fato.

## Critérios de aceite

1. **A Entrega escreve dentro do que é dela.** `risco` entra em `PROJECT_OF` e no conjunto de
   escrita da Entrega, ao lado de `pendencia`: quem é da equipe cria, edita e arquiva nos projetos
   de que participa, e não alcança — nem para ler — o registro de um projeto alheio. Mover um risco
   próprio para um projeto de terceiros é recusado pelo mesmo `ProjectScopedMixin`.
2. **Vendas não aparece em lista nenhuma, e isso não custou uma linha.** O recurso não entra em
   nenhum dos conjuntos de Vendas e o `has_permission` termina em `return False` — recurso novo
   nasce fechado. É a melhor propriedade deste modelo de permissão, e é a mesma que a FDD 028
   registrou para `invoice`.
3. **`resolved_at` é estado corrente, e só de quem resolveu.** Mitigado e aceito carimbam; reabrir
   apaga o carimbo, como na `Pendencia` e ao contrário do `published_at` da `Decisao`.
   **Materializado não carimba** — ver a decisão abaixo.
4. **Os riscos abertos entram no contexto do agente de Entrega, com o mesmo recorte.**
   `build_delivery_context` é um dos agregadores que não passa por queryset de viewset e precisa ser
   estreitado à mão (RFC 0003, ADR 0010, FDD 018); ele já tinha um teste de regressão para o nome do
   projeto e outro para o título do item atrasado, e agora tem o terceiro, para o texto do risco.
5. **O filtro por estado funciona de verdade.** `?status=open` é o recorte que a Delivery Sync pede,
   e ele vai em `filter_exact_fields` — ver a decisão abaixo.
6. **A tela usa as primitivas.** O estado devolve **variante** (`state--1`), nunca a cor (ADR 0026),
   e "Aceito" usa o neutro `state--off`: conviver com um risco é decisão, não alerta pendente.

## Contrato

Rota nova em `/api/v1/`:

| Rota | Quem |
| --- | --- |
| `/riscos/` (CRUD + `?project=` + `?status=` + `?archived=1` + `unarchive`) | delivery no próprio projeto / admin |

`riscos` em português, e não `risks`, porque `/risk/` e `/projects/{id}/risk/` já existem e são a
avaliação calculada. Dois recursos diferentes com o mesmo nome em dois idiomas seria a pior forma
possível de distingui-los. A mudança é aditiva: nada foi removido ou alterado no contrato existente.

## Decisões

### Por que "materializado" não carimba `resolved_at`

Os três estados terminais tiram o risco da fila dos abertos, mas só dois o **resolvem**. Carimbar
"resolvido em" no dia em que o risco virou fato faria o campo afirmar o oposto do que aconteceu — e
a data que interessa nesse caso ("quando materializou") é outra pergunta, que pede campo próprio
quando alguém precisar dela, não este emprestado.

### Por que a ordenação não copia a da `Pendencia`

`Pendencia.Meta.ordering` é `["status", "-created_at"]` e funciona por acidente de alfabeto: lá
`open` vem antes de `resolved`. Aqui `open` vem **depois** de `accepted`, `materialized` e
`mitigated`, e a mesma linha enterraria os riscos abertos embaixo dos encerrados — o inverso do que
um registro de risco serve para mostrar. A ordenação é `["-created_at"]`, e quem quer só os abertos
usa `?status=open`, que é filtro e não ordem.

### Por que `status` vai em `filter_exact_fields`

`QueryParamFilterMixin` tem dois conjuntos: `filter_fields` só aplica o filtro quando o valor é
dígito (serve para chave estrangeira) e `filter_exact_fields` aplica sempre. Um `?status=open`
declarado no primeiro cairia no chão **sem erro nenhum**: a lista voltaria inteira e a tela mostraria
risco encerrado como aberto. É o pior tipo de defeito de filtro, porque a resposta continua 200.

### Por que dois `TextChoices` com os mesmos três valores

`Probability` e `Impact` guardam `low`/`medium`/`high` e diferem só nos rótulos, porque o português
concorda: a probabilidade é *baixa*, o impacto é *baixo*. Uma classe só economizaria oito linhas e
faria o contexto do agente — que usa `get_probability_display()` — dizer "probabilidade baixo".

## Testes

- `apps/core/tests/test_riscos.py` — o CRUD completo da Entrega no próprio projeto (com arquivar e
  restaurar), as duas metades da fronteira (não lê o risco alheio, não cria dentro dele), a recusa
  de mover um risco para projeto de terceiros, Vendas fechada nos três verbos, admin em qualquer
  projeto, o carimbo que aparece e some, o materializado que não carimba, o filtro por estado, e o
  dono/carimbo que não entram pelo corpo.
- `tests/regression/test_delivery_aggregates_are_scoped.py` — o terceiro conteúdo do contexto do
  agente de Entrega: o risco do projeto de que participo entra, o do projeto alheio não, e o
  encerrado não ocupa espaço.
- `ProjectDetailPage.test.tsx` — o risco na tela com os dois eixos e a mitigação, o registro de um
  risco novo, a troca de estado entre as quatro saídas, e o arquivamento com confirmação.

## Fora deste recorte

- **Snapshot do portal do cliente.** O risco **não atravessa**. Um registro de risco é linguagem
  interna de entrega, escrita para ser franca; publicá-la produziria um registro cauteloso, que é
  um registro inútil. Se um dia houver uma leitura do risco para o cliente, ela é decisão própria,
  com emenda na ADR 0003.
- **Severidade derivada de probabilidade × impacto.** Uma matriz que devolvesse "crítico" seria uma
  segunda definição de gravidade convivendo com o escore do `risk.py`, e as duas divergiriam em
  silêncio. Os dois eixos ficam visíveis e a leitura é de quem lê.
- **Ligar risco a fase, marco ou gate.** O risco é filho de `Project` e nada mais. Amarrá-lo ao
  decision gate da FDD 033 ("NO-GO por risco X") é vocabulário novo e pede sua própria fatia.
- **Extração de riscos da transcrição por IA.** O caminho existe e está provado pela FDD 032, mas
  ele merece o mesmo cuidado de lá (rascunho, revisão humana) e não cabe junto da entidade.
- **A avaliação calculada (`risk.py`, `health.py`).** Não foi tocada.
