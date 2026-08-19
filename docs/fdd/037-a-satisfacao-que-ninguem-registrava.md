# FDD 037 — A satisfação que ninguém registrava

> **Camada 5 da RFC 0004**, sobre as camadas 0 e 1 da FDD 028 e as camadas 3 e 4 da FDD 036. Fecha
> a última das seis camadas, e fecha também a lacuna que o `health.py` declarava desde a Fase 2.

## Jornada

Três lugares deste repositório dizem, por escrito, que falta um registro de satisfação do cliente.
Nenhum deles é uma nota de melhoria — os três são o mesmo buraco, visto de ângulos diferentes.

O primeiro é o Health Score. A docstring de `health.py` abre a lista de sinais e fecha com uma
ressalva: *"Satisfação, bugs e 'acessos liberados' ficam de fora até existir onde registrá-los."*
O produto tem um índice chamado "saúde da relação" que mede entrega atrasada, reunião não
realizada, decisão pendente e ROI negativo — quatro coisas que **nós** fazemos. O único sinal que
vem da outra parte da relação não está lá.

O segundo é a régua de cobrança. A FDD 036 nomeou a própria ausência ao listar o que ficava fora:
*"A camada 5 completa da RFC (travas plugadas em satisfação e nos sinais de entrega). […]
Satisfação continua sem onde ser registrada — a mesma lacuna que o `health.py` declara desde a
Fase 2."*

O terceiro já virou código morto, e é o mais eloquente. A RFC 0004 exige que a régua distinga
três problemas que a mesma cobrança estraga: *esqueceu*, *não pôde*, e *está insatisfeito e está
retendo pagamento como sinal* — que *"não é problema de cobrança, é problema de relação
disfarçado, e onde insistir piora tudo"*. A FDD 036 construiu a classificação: a IA lê a resposta
do cliente e grava `Activity.cobranca_sinal`. **E nada lê esse campo.** Não entra em `avaliar`,
não entra no contexto do painel, não entra na escolha da escada. O rótulo é produzido, gravado, e
morre ali — porque não existia para onde o sinal ir.

Esta fatia constrói o lugar.

## O que esta fatia entrega

O modelo `Satisfacao`, ligado ao cliente e opcionalmente ao projeto e à reunião de origem, com
`nivel` (promotor / satisfeito / neutro / insatisfeito), `fonte`, data do acontecido, nota e
autor; o CRUD em `/api/v1/satisfacoes/` com o arquivamento reversível da casa; o sexto sinal do
Health Score; a terceira escada da régua de cobrança; e a satisfação vigente na tela de quem
decide o próximo degrau.

Nada sai da casa. Não há canal novo, não há credencial, não há flag: é registro interno,
digitado por quem conversou com o cliente, no molde da `Decisao` (FDD 032) e da `Activity`
(FDD 035).

### As duas fontes, que são a decisão inteira

`fonte=declarada` é o cliente tendo dito. `fonte=percebida` é a leitura de quem entrega. **Só a
declarada move número** — Health Score e escada de cobrança. A percebida aparece na tela e no
contexto do agente de Entrega, e não altera nada que seja calculado.

Sem essa separação, o primeiro sinal do produto cuja fonte está **fora** da casa vira a opinião do
time sobre si mesmo com aparência de medição, que é pior que não ter sinal: um número errado é
consultado com a mesma confiança de um número certo. A ADR 0032 registra por quê, junto com a
alternativa que parecia óbvia (um campo só) e as três que foram recusadas.

Isso não rebaixa a percebida a enfeite. Ela é o que existe **antes** de alguém perguntar, e é ela
que faz alguém perguntar.

### A escada que não cala

A camada 5 pede travas de relação plugadas na satisfação. A seção Segurança da mesma RFC diz que
recuar precisa ser declarado, porque a regra de suspender *"é a que mais apodrece na prática: vira
desculpa para nunca cobrar, e o recebível estraga invisível"*. Uma trava automática que silencia a
régua atende a primeira exigência violando a segunda.

A saída é uma terceira escada. Com insatisfação **declarada** vigente, o cliente entra na
`RELACAO_TENSA`: o degrau `firme` **não existe** e a escalada interna ocupa a janela que era dele.
A régua não fica muda — ela **para de endurecer e passa a acordar gente**, que então declara a
suspensão com dono, prazo e motivo, pelo mecanismo que a FDD 036 já construiu. O robô nunca
silencia; quem recua é gente, com nome e data de validade.

A tensão é avaliada **antes** da relação longa. Um cliente de anos que está insatisfeito é o caso
mais perigoso da carteira, e a régua desenhada para proteger o cliente antigo não pode absorvê-lo
em silêncio.

### O sinal envelhece

A janela é de 90 dias. Um "insatisfeito" de oito meses não é o estado de hoje, e tratá-lo como
estado de hoje produziria exatamente o recebível que estraga invisível — um cliente que reclamou
uma vez, em março, nunca mais cobrado com firmeza. É a mesma forma que a FDD 036 adotou ao trocar
offset por janela, e pela mesma razão: um degrau que não cabe mais deve deixar o próximo assumir.

## Critérios de aceite

1. **A percebida não move número.** Registro `fonte=percebida` com nível insatisfeito produz Health
   Score idêntico ao de um projeto sem registro nenhum, e a escada continua `PADRAO` ou
   `RELACAO_LONGA`. Tem regressão dedicada, porque é a invariante que um refactor apaga em
   silêncio: somar as duas fontes num filtro só deixa todos os testes de comportamento passando.
2. **A declarada tira o degrau firme e antecipa a escalada**, e o cliente com mais de um ano de
   casa e insatisfeito cai na `RELACAO_TENSA`, não na `RELACAO_LONGA`.
3. **A régua nunca fica muda por causa da satisfação.** Nenhum caminho novo faz `avaliar` devolver
   uma avaliação sem degrau, e nenhuma constante de motivo nova existe. Quem recua é gente.
4. **O sinal envelhece.** Registro de 91 dias não move nada; o de 89 move.
5. **Recurso novo nasce fechado**, e o autor não entra pelo corpo. Entrega não alcança — nem para
   ler — cliente sem projeto seu, pela mesma expressão de `visible_to` que a ADR 0010 tornou única.
6. **Os agregadores não crescem com a base.** `/health/`, `/clients/overview/` e
   `/cobranca/painel/` mantêm contagem constante de queries com quatro vezes a base (ADR 0014).
7. **A satisfação não volta ao cliente.** Não entra no snapshot, em chave nenhuma.
8. **Insatisfeito sem nota é recusado** (400), na viewset e no `clean()`: é o único nível que muda
   comportamento, e um sinal que muda comportamento sem motivo escrito é o que apodrece.

## Contrato

Rota nova em `/api/v1/`:

| Rota | Quem |
| --- | --- |
| `/satisfacoes/` (CRUD + `?client=` + `?project=` + `?nivel=` + `?fonte=` + `?archived=1` + `unarchive`) | vendas / delivery no cliente com projeto seu / admin |

Aditivo em duas rotas existentes: `/health/` e `/projects/{id}/health/` podem trazer o sexto sinal
na lista `signals`, e `/cobranca/painel/` ganha a satisfação vigente por linha. Nada foi removido
nem mudou de forma.

**Vendas e Entrega escrevem**, e é a diferença deste recurso para os dois vizinhos: `risco` é só
de Entrega, `activity` é escrita por Vendas e só lida por Entrega. Aqui quem conversa com o
cliente é de ambas as áreas, e um registro que só metade da casa pode fazer é um registro que não
acontece.

## Decisões

### Por que liga ao cliente, e não ao projeto

Os três registros vizinhos (`Pendencia`, `Decisao`, `Risco`) ligam a `Project`, e este liga a
`Client` com `project` opcional — o molde da `Activity`. A razão é que os dois consumidores
perguntam coisas diferentes: o Health Score pergunta por projeto, a régua de cobrança pergunta por
cliente, e cliente sem projeto ativo ainda pode ter fatura vencida. Ligar só ao projeto deixaria a
camada 5 sem alcance justamente em quem não está mais em entrega — que é onde a cobrança dói.

O `clean()` exige que `project.client` seja o mesmo `client`, pela mesma forma que a `Activity` já
usa para `opportunity` e `invoice`.

### Por que a nova escada reusa as chaves de degrau

A idempotência da régua é `UniqueConstraint(invoice, degrau)`. Se um cliente trocasse de escada
entre duas execuções — foi registrada uma insatisfação ontem —, uma chave própria faria o mesmo
lembrete sair duas vezes. O que muda entre as três escadas é a janela, não a identidade do degrau.
É a mesma decisão que a FDD 036 já tinha registrado para a relação longa, e ela não é
generalização: é a razão pela qual a régua nova não precisou de nada novo para ser idempotente.

### Por que promotor não soma pontos

O Health Score parte de 100 e só subtrai; cada sinal declara quanto tirou, e é isso que o mantém
explicável. Um sinal que soma faria "saúde 100" deixar de significar "nenhum problema conhecido" e
passar a significar "os problemas foram compensados" — e os cinco sinais existentes teriam de ser
reescritos para conviver com isso. Promotor aparece na tela e no contexto do agente; o lugar dele
não é o denominador de um escore de problemas.

### Por que a satisfação não atravessa para o portal do cliente

No molde do Risk Register (FDD 034), e por uma razão que a fonte `percebida` torna literal:
devolver ao cliente a nossa leitura sobre ele não é uma feature com recorte ruim, é uma feature
que não pode existir. A guarda estrutural da ADR 0027 já reprova chave nova não declarada no
snapshot; sobre ela entra a afirmação explícita de que esta chave não é para existir.

## Testes

- `apps/core/tests/test_satisfacao.py` — o CRUD com arquivar e restaurar, as duas metades da
  fronteira de Entrega (não lê o cliente alheio, não escreve nele), Vendas escrevendo, o autor que
  não entra pelo corpo, o `project` de outro cliente recusado, o insatisfeito sem nota recusado com
  400, e os filtros.
- `tests/regression/test_satisfacao_percebida_nao_move_a_regua.py` — a invariante central, nos dois
  motores: mesma pontuação de saúde e mesma escada, com e sem registro percebido.
- `tests/regression/test_satisfacao_nao_volta_ao_cliente.py` — a fronteira do snapshot, em duas
  camadas: o comportamento (nenhuma chave carrega o registro) e a estrutura (a fonte não menciona o
  modelo), no desenho que a FDD 036 usou para custo e margem.
- `tests/regression/test_aggregate_query_budget.py` — os três agregadores continuam constantes com
  a query nova.
- `apps/core/tests/test_health.py`, `test_cobranca.py` e `test_agents.py` — o sexto sinal, a
  terceira escada com a janela de validade, e o bloco novo no contexto de Entrega com o recorte.

## Fora deste recorte

- **Congelar a satisfação no `Case`.** O health precisou ser congelado porque é função pura sobre o
  *agora* — um projeto encerrado com 68 é recalculado meses depois como 100. A satisfação já nasce
  carimbada em `happened_on` e não muda sozinha, então congelá-la seria duplicar um registro que já
  é histórico. O que faltaria é **citar a frase do cliente** no case, e isso é consentimento:
  território do `client_consent`, com decisão própria.
- **Pesquisa respondida pelo cliente (NPS/CSAT).** É canal novo para fora da casa, com o gate da
  ADR 0031 valendo inteiro. Se existir um dia, entra como uma terceira fonte ao lado das duas — e
  é o caminho natural para o pedido de indicação que a FDD 030 deixou aberto.
- **A IA gravar satisfação a partir do `cobranca_sinal`.** Fechar o laço sozinho seria uma linha,
  e é a pior linha disponível: o rótulo mudaria o comportamento de uma cobrança sem ninguém ter
  decidido (ADR 0006). Quem registra é gente, lendo a resposta do cliente na timeline do cliente,
  onde o rótulo já aparece desde a FDD 036.
- **Levar o `cobranca_sinal` ao painel de cobrança.** O campo continua sem leitor, e esta fatia
  não o dá: ela constrói o registro **ao lado** dele, não em cima dele. Pôr os dois na mesma linha
  é defensável e é trabalho próprio — com o cuidado que a FDD 030 nomeou ao recusar um segundo
  score, porque dois sinais parecidos na mesma tela viram dois números discordando sem que
  ninguém saiba qual olhar.
- **Bugs e "acessos liberados"** — os outros dois sinais que a docstring do `health.py` declara
  faltando. Seguem sem onde ser registrados, e esta fatia não os inventou para fechar a lista.
- **Suspensão automática por health crítico** — a outra metade da camada 5 ("travas plugadas nos
  sinais de entrega"). O sinal de entrega já existe e já está na tela de quem decide; automatizar
  o recuo esbarra na mesma frase da RFC que esta fatia respeitou, e pede decisão própria.

## O que a construção decidiu

Oito pontos em que construir mudou o desenho. Ficam aqui, e não no commit, porque é esta página que
a próxima pessoa lê.

**A pré-carga escolhe por fonte, e não escolhe antes de filtrar.** Foi o achado mais sutil da
construção. A forma óbvia — pegar a satisfação vigente do cliente e conferir o campo `fonte`
depois — tem um defeito silencioso: uma **percebida registrada ontem esconderia a declarada de
anteontem**, e a régua deixaria de reagir a uma insatisfação real porque alguém do time anotou uma
impressão depois. O filtro tem de entrar **antes** da escolha do mais recente, e por isso
`satisfacao.vigente` recebe `fonte=` em vez de devolver um registro que o chamador peneira.

**O contexto do painel guarda a lista, não a escolhida.** As duas leituras da mesma dimensão são
diferentes: a linha da tela mostra a vigente de **qualquer** fonte (a percebida é exatamente o que
ajuda a decidir) e a escada reage só à **declarada**. Pré-escolher uma faria a segunda se contentar
com a sobra — e a tela passaria a discordar do relógio no único caso que esta fatia existe para
tratar. O contexto carrega o insumo; quem decide é a regra.

**A guarda de escrita não existia no molde, e foi achada por teste.** O recorte veio do
`ActivityViewSet`, que tem só a metade de leitura — e podia, porque para a Entrega `activity` é
só-leitura. Aqui a Entrega **escreve**, e sem a guarda uma requisição bastava para registrar
satisfação num cliente que a listagem dela esconde: 201, sem erro. É o mesmo argumento do
`ProjectScopedMixin`, que cobre leitura e escrita no mesmo lugar precisamente porque só a leitura é
contornável.

**`vigentes_por_projeto` foi especificada e não existe.** Nenhum consumidor apareceu: o Health
Score pergunta pelo cliente **do** projeto, a régua pelo cliente da fatura, o agente pelo cliente.
Função sem chamador é a dívida que este repositório trata como invariante, e a versão por projeto
seria a primeira a divergir.

**A janela é fechada nos dois lados.** O limite superior não é simetria: um registro com data
futura — dedo errado no formulário — passaria a valer por noventa dias **a partir do erro**, e
nada ficaria vermelho.

**`contexto_do_painel` foi para onze queries, não oito.** O `health` embutido também cresceu
(quatro para cinco) e a satisfação por cliente-de-fatura é consulta própria, porque nem todo
cliente com fatura tem projeto. Número medido e escrito no docstring, como o anterior.

**`fonte` nasce sem default**, ao contrário de quase todo `choices` da casa. Um default faria a
distinção que decide se o registro move número ser escolhida por omissão — e o campo existe
justamente para ninguém escolher por omissão.

**O teste de recorte do agente ficou com os irmãos.** `tests/regression/test_delivery_aggregates_are_scoped.py`
é onde vivem os três recortes anteriores do `build_delivery_context`, inclusive o do Risco; separar
o quarto num arquivo de app faria a próxima pessoa achar três e concluir que era a lista inteira.
