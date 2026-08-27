# ADR 0032 — Só a declarada move número

**Status:** aceita
**Data:** 19/08/2026
**Contexto:** FDD 037 (o registro de satisfação), RFC 0004 (cobrança relacional, camada 5),
FDD 036 / ADR 0031 (a régua de cobrança), FDD 034 (Risk Register — o precedente do registro
declarado), ADR 0006 (agentes por área), ADR 0010 (visibilidade por participação),
ADR 0014 (custo constante nos agregadores)

## Contexto

Até aqui, todo sinal que este produto usa para julgar a saúde de uma relação foi produzido
**por ele mesmo**. `risk.py` lê prazo estourado, `health.py` lê entrega atrasada e reunião não
realizada, `cases.py` congela ROI. São medidas do nosso trabalho, feitas com os nossos dados, e
nenhuma delas depende de o cliente dizer coisa alguma.

Satisfação quebra esse padrão, porque é a primeira informação do domínio **cuja fonte está fora
da casa**. E ela chega por dois caminhos que se parecem na tela e não se parecem em nada:

- o cliente disse — na reunião, no e-mail, na ligação;
- alguém daqui achou — pela cara da última call, pelo tom da resposta, pelo tempo que ele levou
  para responder.

Os dois são úteis. Um deles é evidência; o outro é hipótese. O material da metodologia FDE já
tinha esse vocabulário no Evidence Log (FATO / HIPÓTESE / DESCONHECIDO), e a ADR 0030 adiou
aquela camada — mas a distinção reaparece aqui pela porta dos fundos, porque a satisfação vai
alimentar dois motores que produzem número e comportamento.

O risco não é teórico. Sem separar os dois, o Health Score passa a subtrair pontos por palpite,
e a régua de cobrança passa a abrandar por palpite. O sinal do cliente vira **a opinião do time
sobre si mesmo, com aparência de medição** — que é pior que não ter sinal nenhum, porque um
número errado é consultado com a mesma confiança de um número certo.

O segundo problema é de desenho, e vem da RFC 0004. A camada 5 pede *"travas de relação plugadas
nos sinais de saúde e satisfação"*. A seção Segurança da mesma RFC diz que *"recuar precisa ser
declarado. A regra de suspender a cobrança quando o cliente está insatisfeito é correta e é a que
mais apodrece na prática: vira desculpa para nunca cobrar, e o recebível estraga invisível."* Uma
trava automática que cala a régua atende a primeira frase e viola a segunda.

## Decisão

**Primeira: `fonte` é campo obrigatório do registro, e só `declarada` move número.**

`declarada` — o cliente disse — altera o Health Score e a escada da cobrança. `percebida` — a
leitura de quem entrega — aparece na tela, entra no contexto do agente de Entrega, e **não move
número nenhum**. Uma regra só, para os dois motores, fácil de lembrar e fácil de testar.

Isso não rebaixa a percebida a enfeite. Ela é o que existe **antes** de alguém perguntar, e é ela
que faz alguém perguntar. O que ela não faz é decidir sozinha, porque a decisão que ela tomaria
— tirar 20 pontos de saúde, abrandar uma cobrança — é grande demais para uma impressão.

**Segunda: a insatisfação declarada troca a escada da régua; ela nunca cala a régua.**

Não existe guarda nova em `avaliar`, nem constante nova de motivo. O que existe é uma terceira
escada, `RELACAO_TENSA`, ao lado de `PADRAO` e `RELACAO_LONGA`: o degrau `firme` **não existe** e
a escalada interna ocupa a janela que era dele. A régua para de endurecer e passa a **acordar
quem responde pela relação** — que então declara a suspensão com dono, prazo e motivo, pelo
mecanismo que a FDD 036 já construiu.

É o que reconcilia as duas frases da RFC. A trava existe, e ela não é silêncio: o robô nunca
fica mudo, e quem recua é gente, com nome e data de validade.

**Terceira, que é consequência das duas: o sinal envelhece.** A janela é de 90 dias. Um
"insatisfeito" de oito meses não é o estado de hoje, e tratá-lo como estado de hoje produziria
exatamente o recebível que estraga invisível — um cliente que reclamou uma vez, em março, nunca
mais cobrado com firmeza. É a mesma forma que a FDD 036 adotou ao trocar offset por janela.

## Consequências

- Health Score ganha o sexto sinal, e a docstring que declarava a lacuna desde a Fase 2 perde uma
  das três ausências. Bugs e "acessos liberados" continuam nela, e não foram inventados aqui.
- A régua ganha uma terceira escada sem ganhar um caminho de silêncio. Os degraus **reusam as
  chaves existentes**, porque a idempotência é `UniqueConstraint(invoice, degrau)` e uma chave
  própria faria o mesmo lembrete sair duas vezes para quem trocasse de escada entre duas
  execuções — a mesma razão que a FDD 036 já tinha registrado para a relação longa.
- A separação por fonte precisa de **regressão dedicada**, e não só de teste de unidade: é a
  invariante que um refactor desatento apaga em silêncio, porque somar as duas fontes num
  filtro só faz todos os testes de comportamento continuarem passando.
- Os dois agregadores que consultam satisfação (`/health/`, `/clients/overview/`) e o painel de
  cobrança carregam em lote. É a ADR 0014 outra vez: contagem de queries constante com a base,
  cobrada por `test_aggregate_query_budget.py`.
- A satisfação **não atravessa** para o portal do cliente, e a fonte `percebida` torna isso
  literal — mandar de volta ao cliente a nossa leitura sobre ele não é uma feature com recorte
  ruim, é uma feature que não pode existir. Segue o precedente do Risk Register (FDD 034).
- O registro é interno e não estreia canal nenhum: não há flag, não há credencial, não há
  pesquisa enviada. Se um dia houver pesquisa respondida pelo cliente, ela entra como uma
  terceira fonte — e o gate da ADR 0031 vale inteiro para o envio.

## Alternativas consideradas

**Um campo só, sem fonte.** Rejeitada: é a alternativa que produz o defeito descrito no contexto.
O custo de ter errado é alto e silencioso — ninguém descobre que o Health Score está medindo
palpite, porque o número continua saindo.

**NPS de 0 a 10.** Padrão de mercado, comparável entre clientes, e conectaria com o pedido de
indicação no pico de valor que a FDD 030 deixou aberto. Rejeitada **para este recorte**: NPS só
significa alguma coisa quando é pesquisa respondida pelo cliente, e enviar pesquisa é canal novo
para fora da casa, com o gate da ADR 0031 valendo inteiro. Perguntado de boca e digitado por quem
atendeu, o número finge um rigor que não tem — e um índice falso é pior que quatro níveis
honestos. Fica nomeado como o caminho natural se a pesquisa existir.

**CSAT por reunião ou por entrega.** Rejeitada por responder a pergunta errada: mede "aquela
reunião foi boa?", e o que a régua e o Health Score precisam saber é "este cliente está conosco?".

**Deixar a IA gravar satisfação a partir do `cobranca_sinal`.** A classificação da resposta do
cliente (FDD 036) já produz o rótulo `insatisfeito`, e fechar o laço sozinho seria uma linha de
código. Rejeitada pela ADR 0006 — nenhum agente executa efeito colateral autônomo — e porque este
é exatamente o pior lugar para abrir a exceção: o rótulo mudaria o comportamento de uma cobrança.
Quem registra é gente, lendo a resposta na timeline do cliente. O campo segue sem leitor, e ligá-lo
ao painel é trabalho próprio.

**Trava que cala a régua** (uma guarda em `avaliar`, no molde de `suspensao_ativa`). Mais simples
de implementar e de testar, e rejeitada por ser literalmente o "pular silencioso" que a RFC
recusa. O recebível estragaria invisível, e ninguém teria decidido nada.
