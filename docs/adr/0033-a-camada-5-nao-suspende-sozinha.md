# ADR 0033 — A camada 5 não suspende sozinha

- **Status:** aceita
- **Data:** 19/08/2026
- **Contexto:** FDD 038 (esta fatia), RFC 0004 (cobrança relacional, camada 5), FDD 036 /
  ADR 0031 (a régua de cobrança e o que sai sozinho), FDD 037 / ADR 0032 (a satisfação e a
  terceira escada), ADR 0006 (agentes não executam efeito colateral autônomo), ADR 0014 (custo
  constante nos agregadores)

## Contexto

A RFC 0004 descreve a camada 5 em uma frase: *"travas de relação plugadas nos sinais de saúde e
satisfação"*. Lida sozinha, ela pede uma coisa clara — quando o sinal piora, a cobrança para.

A seção Segurança da **mesma** RFC pede o contrário, e com mais palavras:

> *"Recuar precisa ser declarado. A regra de suspender a cobrança quando o cliente está
> insatisfeito ou quando a entrega está atrasada é correta e é a que mais apodrece na prática:
> vira desculpa para nunca cobrar, e o recebível estraga invisível. Então é suspensão com dono e
> prazo de validade, registrada como evento — nunca um 'pular' silencioso."*

As duas frases não se contradizem: a primeira diz que o sinal precisa chegar à régua, a segunda
diz que o sinal não pode ser quem decide parar. Mas a leitura apressada da primeira produz
exatamente o que a segunda proíbe, e é uma leitura fácil de fazer — "plugar a trava no sinal"
descreve, literalmente, um `if health == "crítico": return None`.

A FDD 037 já enfrentou essa tensão na metade da satisfação e resolveu com uma terceira escada: com
insatisfação declarada vigente, o degrau `firme` deixa de existir e a escalada interna ocupa a
janela dele. A régua não cala — ela para de endurecer e passa a acordar gente. Aquela fatia
resolveu o caso e **deixou o princípio sem registro**, nomeando a outra metade como trabalho
próprio: *"suspensão automática por health crítico […] esbarra na mesma frase da RFC que esta
fatia respeitou, e pede decisão própria"*.

Esta ADR é essa decisão. Ela existe porque a recusa acontece agora pela segunda vez, e porque a
terceira vez virá: o `health.py` ainda declara duas ausências (bugs e "acessos liberados"), e cada
sinal novo que chegar à régua trará de volta a mesma pergunta.

## Decisão

**Nenhum sinal suspende a cobrança sozinho. A camada 5 muda a escada, nunca cria silêncio.**

Concretamente, três regras:

**1. Sinal ruim troca a escada, não o resultado.** Entrega em estado crítico leva o cliente à
mesma `RELACAO_TENSA` que a insatisfação declarada já levava: o degrau `firme` não existe e a
escalada interna ocupa a janela D+10 que era dele. A régua continua produzindo um degrau todo dia
em que caberia um degrau.

**2. Nenhuma constante de motivo de silêncio nova.** Os motivos pelos quais a régua se cala são um
conjunto fechado e nomeado (`ESTADO_NAO_COBRAVEL`, `SUSPENSA`, `DEGRAU_GASTO`,
`TETO_DE_FREQUENCIA`, `FIM_DE_SEMANA`, `FLAG_DESLIGADA`). Nenhum sinal de relação entra nessa
lista. É uma invariante verificável, e é assim que ela é cobrada: um teste que exige que `avaliar`
nunca devolva avaliação sem degrau por causa de saúde ou satisfação.

**3. `CobrancaSuspensao` só nasce de requisição.** Nenhum módulo de domínio, nenhum job agendado e
nenhum agente cria uma suspensão. Ela tem dono, prazo e motivo obrigatórios porque é declaração de
uma pessoa, e uma suspensão criada por regra teria os três campos preenchidos por ninguém —
`owner` seria um palpite, `reason` seria uma constante, e `until` seria uma política que ninguém
escolheu para aquele cliente.

## Consequências

- A camada 5 fecha com as duas metades no mesmo formato, e a forma passa a ser reusável: o próximo
  sinal que chegar à régua entra como condição de escada, não como guarda de silêncio.
- **A régua fica mais barulhenta com o cliente em crise, não menos** — e isso é intencional. O que
  ela produz nesse estado é escalada **interna**: o destino do degrau é a casa, não o cliente. Quem
  fala com um cliente cuja entrega está em frangalhos é gente.
- Escalada sem ninguém a quem escalar volta a ser o ponto frágil, e continua coberto pela guarda
  que a FDD 036 ganhou na revisão (`SemDestinatarioInterno`): sem destinatário, o degrau **não é
  gasto**. Esta ADR aumenta o tráfego por aquele caminho, o que torna a guarda mais importante, não
  menos.
- A guarda pergunta por **cliente**, seguindo a FDD 037: *"o Health Score pergunta por projeto, a
  régua de cobrança pergunta por cliente"*. Consequência que precisou de tratamento explícito: a
  linha do painel mostrava o health do projeto **da fatura**, e passa a mostrar o pior nível entre
  os projetos ativos do cliente — senão a tela diria "saudável" enquanto o relógio estaria tenso, e
  uma tela que discorda do relógio é pior que uma tela sem o dado.
- O custo do sinal não é de graça: a régua passou a precisar de saúde de projeto, que é o agregado
  mais caro da casa. O job passa a montar o contexto em lote uma vez, como o painel já fazia, e a
  constância continua cobrada por `test_aggregate_query_budget.py` (ADR 0014).
- Só o `level` do health atravessa para a régua e para a tela — nunca o score nem os sinais. É a
  cerca comercial que a FDD 036 já tinha escrito, e a razão vale igual aqui: *"62 de 100, 2
  entregas atrasadas"* é a nossa medição da nossa própria falha.

## Alternativas consideradas

**Suspensão automática com dono e prazo atribuídos por regra.** É a leitura literal da camada 5, e
foi a alternativa mais séria. Rejeitada porque atribuir o dono é justamente a parte que não se
automatiza: o gerente do projeto é o palpite óbvio e é o errado com frequência — em cobrança quem
recua costuma ser quem tem a relação comercial, não quem entrega. E uma suspensão com dono
atribuído por regra é uma suspensão que ninguém sabe que tem, o que a torna a variante mais
perigosa do "pular silencioso": ela tem registro, e por isso não parece silêncio.

**Uma quarta escada, própria para entrega crítica.** Rejeitada por duplicação sem diferença: o
comportamento pedido é idêntico ao da tensão por satisfação. Pior, chaves de degrau novas
quebrariam a idempotência — a unicidade é `UniqueConstraint(invoice, degrau)`, e um cliente que
trocasse de escada entre duas execuções receberia o mesmo lembrete duas vezes. É o mesmo argumento
que a `RELACAO_LONGA` e a `RELACAO_TENSA` já registram, e ele não enfraqueceu.

**Deixar o health fora da régua e confiar na tela.** O painel já mostra saúde, tempo de casa e
valor do cliente na mesma linha desde a FDD 036, então a informação já estava diante de quem
decide. Rejeitada porque a régua age sozinha nos degraus que vão ao cliente, e nos dias em que
ninguém abre o painel é ela quem escolhe o tom. Um sinal que só existe para humano é um sinal que
não vale nos dias em que ele mais importa.
