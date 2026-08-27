# ADR 0031 — O degrau sai sozinho, o texto da IA não

**Status:** aceita
**Data:** 19/08/2026
**Contexto:** RFC 0004 (cobrança relacional, camadas 3 e 4), FDD 036 (a régua), FDD 028
(contas a receber), FDD 023 / ADR 0015 (trabalho periódico agendado), ADR 0006 (agentes por
área), FDD 010 (digest diário)

## Contexto

A régua de cobrança é a primeira coisa que este produto manda **para fora da casa sem uma
pessoa apertando o botão naquele instante**. Tudo o que saía antes era ou disparado por
clique (proposta, contrato, convite, pedido de assinatura) ou dirigido a quem trabalha aqui
(o digest diário, o alerta de backup, o aviso de conhecimento vencido). Um lembrete de
cobrança sai por relógio e chega a um cliente.

Isso obriga a responder, em voz alta, uma pergunta que nunca tinha aparecido: **onde fica o
gate humano num caminho de comunicação automatizada?** A resposta reflexa — "toda mensagem é
revisada antes de sair" — mata a régua: uma escada que exige aprovação por envio é uma lista
de tarefas com aparência de automação, e ela apodrece na primeira semana movimentada. A
resposta oposta — "o agente escreve e manda" — é exatamente o que a RFC 0004 recusa
frontalmente na seção Segurança, e o que a ADR 0006 já proibia.

Some-se um segundo problema, mais silencioso. A camada 3 é determinística e a camada 4 é IA,
e as duas produzem a mesma coisa aos olhos de quem lê a caixa de entrada: um e-mail de
cobrança. Sem uma regra escrita, elas vão convergir — alguém vai ligar o rascunho de IA no
job, "porque o texto fica melhor", e ninguém vai notar que o gate mudou de lugar.

## Decisão

**O degrau determinístico sai sozinho. O texto gerado por IA nunca sai sozinho.**

O que distingue os dois não é o canal nem o destinatário — é **o que está sendo decidido**.

No degrau determinístico, o texto é constante de código, revisada uma vez, igual em todo
envio. O que o relógio decide é *se* a mensagem cabe hoje, e isso é uma função pura sobre o
estado da fatura, testada como qualquer outra regra da casa. É a mesma classe de ato que o
digest diário da FDD 010, que sai por `ScheduledJobRun` desde a FDD 023 sem revisão por
envio, e que ninguém considerou automação perigosa.

No rascunho de IA, o que muda é **a redação** — e a redação é precisamente o que uma pessoa
revisaria. Aprovar em bloco um gerador de texto de cobrança é aprovar todos os textos que ele
ainda não escreveu, incluindo o que vai chamar de caloteiro um cliente de cinco anos por uma
fatura de trinta dias. Então o rascunho é **pedido** na tela, revisado e enviado por uma
pessoa, e o registro guarda quem enviou e qual `AiInteraction` produziu o texto.

**Corolário: nenhuma feature de IA entra na tabela de jobs do `scheduler.py` para falar com o
cliente.** A exceção existente — o digest — fala com quem trabalha aqui, e é o limite.

## A segunda decisão: a régua é derivada do estado, nunca uma fila

Não existe mensagem agendada. A cada execução, o job olha o estado **atual** da fatura e
pergunta que degrau cabe hoje. `paid` e `cancelled` são terminais no `INVOICE_TRANSITIONS`
(FDD 028) e não têm degrau, então **o pagamento não precisa cancelar nada**: não há nada
pendente para cancelar.

Isso é o desenho respondendo ao que a RFC 0004 chama de pecado capital da cobrança — *"o
pecado capital é cobrar quem já pagou; destrói confiança num toque"*. Uma fila de mensagens
agendadas pode ser ultrapassada pelo pagamento: a baixa entra às 14h, o worker já tinha o
e-mail na mão, e o cliente que pagou de manhã recebe a cobrança à tarde. Depois disso alguém
escreve uma rotina de cancelamento de fila, ela tem uma corrida, e a corrida aparece uma vez
por trimestre com um cliente irritado do outro lado.

Uma régua derivada não tem esse modo de falha, e não o tem **por construção** — que é a mesma
propriedade que a ADR 0020 buscou ao congelar o case estruturalmente e a ADR 0021 ao pôr a
invariante do recebível numa `CheckConstraint`. Está escrito aqui porque "otimizar" isto para
uma tabela de mensagens agendadas é uma refatoração que parece boa e que reintroduz o defeito
inteiro.

## O que não muda

Dar desconto, baixar, renegociar, escalar e suspender seguem sendo atos humanos, com autor e
carimbo. A ADR 0006 já proibia efeito colateral autônomo de agente, e a RFC 0004 é explícita:
*"Nada que toca dinheiro é decisão de modelo."* A camada 4 **classifica** e **rascunha**; ela
não age. O sinal que ela grava numa `Activity` é leitura, não comando.

## Alternativas consideradas

**Aprovação humana por envio, inclusive no degrau determinístico.** Rejeitada: transforma a
régua numa fila de aprovação, e o item que mais importa — o pré-aviso, que a RFC chama de "o
maior ganho isolado, porque pega quem apenas esqueceu" — é justamente o de menor risco e o de
maior volume. Exigir clique nele é garantir que ele não saia.

**Deixar a IA escrever e mandar, com amostragem humana depois.** Rejeitada pela RFC e pela
ADR 0006. Amostragem funciona para achar tendência, não para impedir a mensagem específica que
perde o cliente específico — e cobrança é um domínio onde um único evento paga o prejuízo.

**Um `Flag` que permitisse ligar o rascunho de IA no job**, para quem quisesse. Rejeitada
porque é a decisão disfarçada de configuração: a opção existiria para ser ligada, e o gate
teria virado preferência.

## Consequências

- **A régua funciona com a IA desligada**, e é assim que ela nasce. O texto do degrau é
  constante; `flags.is_enabled("ai")` falso tira o botão de rascunho da tela e não tira um
  único lembrete do ar.
- **Existem dois caminhos até `CobrancaContato`** — o job e a ação humana — e eles se
  distinguem no registro: `sent_by` nulo significa automático, e `ai_interaction` preenchida
  significa que uma pessoa revisou um texto de modelo. Um relatório futuro de "quanto da nossa
  cobrança é automática" é uma query, não uma arqueologia.
- **O `scheduler.py` ganha um job que pode não mandar nada**, e isso é sucesso, não falha. Fim
  de semana, teto de frequência, suspensão ativa e degrau já gasto são todos "não hoje". O
  resumo do comando conta os calados e por quê, senão a única leitura possível de um job
  silencioso é supor que ele quebrou.
- **A próxima integração de comunicação com o cliente herda esta regra**, e não a redescobre.
  WhatsApp é canal novo, não gate novo.
