# FDD 038 — Os dois sinais que ninguém lia

> **Fecha a camada 5 da RFC 0004**, sobre a metade que a FDD 037 entregou. As duas coisas que esta
> fatia liga já existiam no banco há semanas: a saúde do projeto e o rótulo que a IA grava na
> resposta do cliente. Nenhuma das duas mudava o comportamento de nada.

## Jornada

Uma fatia que não constrói sinal nenhum. Constrói **leitor**.

O primeiro sinal é a saúde do projeto. O `health.py` calcula, desde a Fase 2, um índice com faixas
explícitas — abaixo de 50 é `crítico` —, e desde a FDD 036 esse nível chega à linha do painel de
cobrança, ao lado do tempo de casa e do valor já recebido, porque a RFC 0004 exige que quem decide
o próximo degrau veja a relação inteira *"na mesma tela, não a dois cliques"*. Ele está lá. E não
muda nada: a régua escolhe a escada olhando apenas para tempo de casa, reincidência e satisfação
declarada. Um cliente cuja entrega está em frangalhos recebe exatamente a mesma cobrança que um
cliente cujo projeto vai bem — inclusive o degrau `firme`, que é o de tom duro.

O segundo é mais curto de contar, porque é código morto. A FDD 036 construiu a classificação da
resposta do cliente: a IA lê o que ele respondeu e grava `Activity.cobranca_sinal` como *esqueceu*,
*não pôde* ou *insatisfeito*. A FDD 037 foi escrita inteira em volta desse rótulo — ele é o
terceiro dos três lugares que diziam faltar um registro de satisfação — e mesmo assim o deixou
onde estava, dizendo por quê: fechar o laço sozinho *"seria uma linha, e é a pior linha
disponível"*, porque o rótulo mudaria o comportamento de uma cobrança sem ninguém ter decidido
(ADR 0006). O campo continuou com um único leitor em todo o repositório — a timeline do cliente,
que o exibe. Nenhum motor.

Os dois casos têm a mesma forma: o dado existe, custou caro, aparece na tela e não alcança a
decisão. E têm a mesma armadilha, que é a razão de a fatia precisar de uma ADR: a maneira óbvia de
ligar qualquer um dos dois é a que a RFC 0004 proíbe na sua seção Segurança.

## O que esta fatia entrega

A quarta condição da escada de cobrança — entrega em estado crítico leva à `RELACAO_TENSA`, a
mesma escada que a insatisfação declarada já produzia —, a causa da tensão nomeada no painel, o
health da linha corrigido para o cliente inteiro, e o rótulo da IA transformado em atalho de
registro. Mais uma FK de proveniência, `Satisfacao.source_activity`, que é o que faz o atalho
parar de insistir depois de atendido.

Nada sai da casa e nada é ligado: a flag `dunning` continua desligada, pelas duas razões que a
FDD 036 registrou e que seguem verdadeiras.

### A trava que não cala

A camada 5 pede travas plugadas nos sinais de saúde e satisfação. A mesma RFC diz que *"recuar
precisa ser declarado […] nunca um 'pular' silencioso"*. A saída é a que a FDD 037 já provou para a
outra metade, e agora vira princípio na **ADR 0033**: sinal ruim **troca a escada, não cria
silêncio**.

Com um projeto ativo em `crítico`, o cliente entra na `RELACAO_TENSA`: o degrau `firme` não existe
e a escalada interna ocupa a janela D+10 que era dele. O destino desse degrau é a casa, não o
cliente. A régua fica mais barulhenta, não menos — e o que ela produz é uma pessoa sendo avisada de
que há uma fatura vencida num cliente cuja entrega está ruim, que é precisamente a conversa que
ninguém quer que um template tenha.

A escada é a **mesma tupla**, não uma quarta. O comportamento pedido é idêntico, e chaves de
degrau próprias fariam o mesmo lembrete sair duas vezes para quem trocasse de escada entre duas
execuções — a idempotência é `UniqueConstraint(invoice, degrau)`, e é o terceiro registro seguido
desse mesmo argumento.

### Por que a guarda pergunta por cliente, e o que isso quebrou na tela

A FDD 037 já tinha decidido o eixo: *"o Health Score pergunta por projeto, a régua de cobrança
pergunta por cliente"*. A condição é, então, "o cliente tem algum projeto **não concluído** em
`crítico`" — não o projeto daquela fatura, que pode nem existir.

Isso quebrou uma coisa que estava certa antes. A linha do painel mostrava o health **do projeto da
fatura**, e com a guarda olhando todos os projetos ativos do cliente os dois passariam a discordar:
a tela diria "saudável" e o relógio estaria tenso. A linha passa a mostrar o **pior nível entre os
projetos ativos do cliente**, pela mesma razão que a FDD 037 deu ao guardar a lista de satisfações
em vez da escolhida — uma tela que discorda do relógio é pior que uma tela sem o dado, porque quem
a lê decide com ela.

O projeto **concluído** não conta, e essa exclusão é a diferença entre uma trava e uma desculpa:
sem ela, um contrato encerrado com health ruim abrandaria a cobrança do saldo para sempre, que é
literalmente o recebível que estraga invisível.

### O rótulo vira atalho, e continua sem gravar nada

O painel passa a mostrar, na linha da fatura, a última resposta classificada do cliente que ainda
**não virou registro** — o rótulo, a data, e a ação que abre o formulário de satisfação
pré-preenchido com `fonte=declarada` e a nota editável. Quem confere e salva é uma pessoa.

É o que a ADR 0032 pediu quando recusou fechar o laço automaticamente: *"quem registra é gente,
lendo a resposta do cliente na timeline"*. A mudança é só de distância — a leitura passa a estar na
tela onde a decisão de cobrança acontece, em vez de a dois cliques. A IA continua não gravando
satisfação, e há regressão dedicada para isso.

A `source_activity` existe para o atalho saber quando parar. Sem ela o painel insistiria para
sempre em um sinal já atendido, e um aviso que não some é um aviso que se aprende a ignorar. É o
molde de `source_meeting`, com o mesmo `SET_NULL` e a mesma razão: apagar a atividade não desfaz o
que o cliente disse; o que se perde é só de onde veio.

**A satisfação vigente e o rótulo não são a mesma coisa na tela, e a linha diz isso.** Um é
registro, o outro é leitura ainda não registrada. É a armadilha que a FDD 030 nomeou ao recusar um
segundo score: dois sinais parecidos na mesma tela viram dois números discordando sem que ninguém
saiba qual olhar.

## Critérios de aceite

1. **A régua nunca fica muda por causa de entrega.** Nenhuma constante de motivo de silêncio nova
   existe, e `avaliar` não devolve avaliação sem degrau por causa de saúde. Tem regressão dedicada,
   junto da segunda metade da mesma invariante: nenhuma `CobrancaSuspensao` nasce fora de
   requisição.
2. **Entrega crítica troca a escada e reusa as chaves.** O cliente cai na `RELACAO_TENSA`, sem
   degrau `firme` e com a escalada interna em D+10, com as mesmas chaves de degrau.
3. **A tensão por entrega vence a relação longa**, como a tensão por satisfação já vencia.
4. **Projeto concluído não trava nada**, e cliente sem projeto continua na `PADRAO`.
5. **A tela não discorda do relógio.** O `health_level` da linha é o pior entre os projetos ativos
   do cliente, e a causa da tensão é nomeada (`satisfacao` / `entrega` / `ambas`).
6. **A IA não registra satisfação.** Classificar uma resposta como `insatisfeito` não cria
   `Satisfacao`, não muda Health Score e não troca escada.
7. **O atalho para de insistir** quando existe `Satisfacao` apontando para aquela atividade.
8. **Os agregadores não crescem com a base.** `/cobranca/painel/` mantém contagem constante de
   queries com quatro vezes a base, com as dimensões novas ocupadas (ADR 0014).

## Contrato

Nenhuma rota nova. Aditivo em duas:

| Rota | O que ganha |
| --- | --- |
| `/cobranca/painel/` | `tensao_causa` e o bloco do sinal pendente (`sinal_kind`, `sinal_display`, `sinal_em`, `sinal_activity`) por linha; `health_level` passa a ser do cliente, não da fatura |
| `/satisfacoes/` | aceita `source_activity` na escrita |

Migração aditiva. Nada foi removido nem mudou de forma — exceto o **significado** de
`health_level` na linha do painel, que é mudança de conteúdo e não de tipo, e está registrada aqui
porque um consumidor futuro leria "saúde" e suporia "do projeto desta fatura".

## Decisões

### Por que o job passou a montar o contexto

`executar` chamava `avaliar` fatura a fatura sem contexto, o que já era N+1 para suspensão,
satisfação, reincidência e teto — tolerável num job noturno. Somar saúde de projeto a isso não
era: é o agregado mais caro da casa. O job passa a montar `contexto_do_painel` uma vez, no molde do
painel, e a equivalência entre os dois caminhos continua travada pelo teste que já existia para
ela.

O contexto troca a **fonte** do dado, nunca a regra. É a mesma disciplina que `assess_project_health`
usa com `milestones=`/`tasks=`, e é o que impede a tela e o relógio de terem duas cópias da decisão.

### Por que a causa é calculada à parte

`regua_para` continua devolvendo só a escada, e a causa sai de uma função própria consumida apenas
pelo painel. Se a causa entrasse na decisão, a próxima pessoa teria dois lugares para mudar o
comportamento e um deles seria a camada de exibição.

## Testes

- `apps/core/tests/test_cobranca.py` — a quarta condição, o reuso das chaves, a tensão vencendo a
  relação longa, o projeto concluído que não conta, o cliente sem projeto, a causa `ambas`, o pior
  health do cliente na linha e o sinal pendente aparecendo e sumindo.
- `tests/regression/test_a_camada_5_nao_suspende_sozinha.py` — a invariante da ADR 0033 nas duas
  metades: nenhuma constante de silêncio nova e nenhuma suspensão criada por domínio.
- `tests/regression/test_o_sinal_da_ia_nao_registra_satisfacao.py` — a fronteira da ADR 0006/0032:
  o rótulo não move número sozinho.
- `tests/regression/test_aggregate_query_budget.py` — as dimensões novas semeadas, para a
  constância não ser provada sobre dimensão vazia.
- `tests/regression/test_satisfacao_percebida_nao_move_a_regua.py` — segue verde sem alteração; se
  precisasse mudar, seria sinal de que a guarda nova vazou nas fontes.
- `src/pages/CobrancaPage.test.tsx` — o sinal rotulado como não registrado, distinto da satisfação
  vigente, e a ação que o resolve.

## O que a construção decidiu

Quatro pontos em que construir mudou o desenho. Ficam aqui, e não no commit, porque é esta página
que a próxima pessoa lê.

**O teto de frequência é a única dimensão que a passada altera, e pré-carregá-lo quebrava a
cobrança.** Foi o achado mais caro, e não estava no plano. Com o contexto lido uma vez antes do
laço, um cliente com três faturas vencidas receberia **três e-mails no mesmo dia**: o contexto foi
montado antes do primeiro envio e continuaria dizendo que a franquia estava livre. A consulta
fatura a fatura fazia isso de graça, e é o preço de pré-carregar aquilo que o próprio laço muda.
`executar` passou a registrar o envio no contexto. As outras dimensões — suspensão, reincidência,
satisfação, saúde — não mudam por a régua ter falado, e por isso continuam congeladas.

**Um campo só para o health, e não dois.** O plano previa manter `health_por_projeto` para a linha
e um conjunto à parte para a guarda. Com a linha passando a mostrar o pior nível do cliente, o
primeiro ficaria sem consumidor — e dois campos derivados do mesmo dado são a forma exata de a tela
e o relógio divergirem. Um campo só faz *"a tela não contradiz a régua"* ser verdade por
construção: a guarda lê exatamente o valor que a linha mostra.

**A ordem entre os níveis mora no `health.py`.** Escolher o pior exigia saber que crítico é pior
que atenção, e digitar essa ordem — ou o literal `"crítico"` — dentro do `cobranca.py` criaria uma
segunda definição do vocabulário do health. A que erra o acento não fica vermelha; ela só nunca
casa. O limiar não mudou.

**Três filtros de arquivado que ninguém tinha pedido.** Atividade arquivada não vira sinal por
registrar; `Satisfacao` arquivada não conta como registro, e o sinal volta a estar por registrar;
projeto arquivado não entra na guarda de entrega. Os três seguem do soft delete da casa, e cada um
seria um defeito mudo — o mais feio é o do meio, porque um registro desfeito que continuasse
contando deixaria o atalho invisível para sempre.

## Fora deste recorte

- **Suspensão automática por qualquer sinal.** É a decisão da ADR 0033, e ela é a fatia.
- **Bugs e "acessos liberados"** — as duas ausências que restam na docstring do `health.py`. Seguem
  sem onde ser registrados, e esta fatia não os inventou para fechar a lista.
- **A IA gravar satisfação sozinha**, que o atalho existe justamente para não precisar.
- **Homologação do Stripe e ligar a flag `dunning`.** Continua sendo o gate de tudo o que as
  camadas 3, 4 e 5 construíram. Construir não é ligar.
- **Pesquisa respondida pelo cliente** (a terceira `fonte`) e **congelar satisfação no `Case`**,
  ambas nomeadas pela FDD 037 e ambas com decisão própria.
