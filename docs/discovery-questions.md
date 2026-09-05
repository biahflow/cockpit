# Discovery Questions — base genérica

> **Espelho** da ficha canônica no Notion: **Discovery Questions — base genérica**
> <https://app.notion.com/p/3c982225ad278196bb95cd0fe4b4129e>
> Não se edita aqui. Mudar uma pergunta é mudança na fonte, e passa pela §8 do Language Map —
> o termo (ou a pergunta) entra primeiro na página do Notion, depois no Pulse.
> Trazido para o repositório pela **ADR 0069**: é daqui que a Discovery Session serve os blocos
> (DAP `dap-discovery-session-e-business-case-r2`, decisão E1) e é daqui que o corpus da FDD 029
> passa a responder sobre condução de Discovery.

Perguntas que valem para **qualquer vertical**. O que for específico de um setor mora na Vertical
Knowledge Base correspondente, nunca aqui — é essa separação que faz a próxima vertical começar com
boa parte do trabalho pronto.

## Como usar

| Momento | O que usar |
| --- | --- |
| Qualification Call (45–60 min) | Blocos A e E + o bloco de dores da vertical |
| Executive Discovery (Dia 1) | Blocos A, D e E, agora com profundidade |
| Entrevistas com a operação (Dia 2) | Bloco B |
| Process walkthrough e sistemas (Dia 3) | Blocos B e C |
| Validação e Readout (Dias 6–7) | Bloco F |

## Regras de condução

- **Deixe a pessoa falar.** A ordem em que ela lista as dores revela a prioridade real melhor do que
  qualquer descrição.
- **Anote as palavras exatas.** Elas voltam no Executive Readout e no depoimento.
- **Não diagnostique na hora.** Enxergou a solução? Anote como hipótese e continue escutando.
  Diagnóstico de quinze minutos é exatamente o que a Biahflow diz que não faz.
- **Separe medido de declarado.** Toda resposta numérica ganha a pergunta seguinte: *"vocês sabem
  esse número ou é impressão?"* — e a resposta vai para a coluna de evidência do baseline.
- **Se você falar mais de 40% do tempo, a conversa falhou** — mesmo que termine em sim.

## Bloco A — Contexto executivo

- Como está o negócio hoje? Cresceu, encolheu ou estabilizou nos últimos 12 meses?
- Quando você olha o resultado do mês, o que mais te incomoda?
- Se o ano fechasse hoje, o que teria dado errado?
- O que mudou nos últimos meses que fez isso virar prioridade agora?
- Quando você diz que precisa reduzir custo, é cortar despesa ou fazer a mesma coisa com menos
  esforço? (levam a caminhos diferentes)
- Se você pudesse resolver um único problema operacional nos próximos 90 dias, qual seria?
- O que vocês já tentaram melhorar aí e não foi para frente? Por que parou?

## Bloco B — Follow the work (com quem executa)

- Me leva por um caso real, do começo ao fim. Pega um caso recente — o que aconteceu, na ordem?
- Onde nesse caminho alguém precisou interpretar, adivinhar ou ligar para outra pessoa?
- Que planilha existe fora do sistema? (quase toda operação tem pelo menos uma; se disserem que não,
  pergunte de outro jeito)
- Quando a informação passa de uma pessoa para outra, ela passa por onde: sistema, WhatsApp, papel,
  voz?
- Quantos casos desse tipo passam por aqui num mês?
- Quanto tempo leva um caso simples? E um complicado? Qual a proporção entre eles?
- Com que frequência falta informação para você conseguir trabalhar? O que você faz quando falta?
- O que volta para refazer, e por quê?
- Se você pudesse mudar uma coisa nesse fluxo, qual seria?

### Cronometragem (shadowing)

Acompanhe um caso real com o relógio, não com a estimativa. Registre marco a marco: quando abriu,
quando interpretou, quando procurou algo que faltava, quando ficou esperando resposta, quando
terminou. Classifique cada trecho em **ativo** ou **espera** — o tempo de espera costuma ser o achado
que ninguém esperava.

## Bloco C — Sistemas e dados

- Quais sistemas participam desse processo, e quem usa cada um?
- Onde a informação nasce? Onde ela mora depois?
- Esses sistemas conversam entre si ou alguém redigita?
- Dá para exportar dados desses sistemas? Em que formato?
- Quantos meses de histórico existem?
- Quem consegue extrair? Precisa do fornecedor?
- Qual a confiança de vocês na qualidade desses dados, de 1 a 5?

## Bloco D — Sponsor, acesso e abertura a mudança

- Se aparecer uma mudança de processo que exige decisão sua, você bate o martelo ou passa por mais
  alguém?
- Vou precisar conversar com quem executa. Isso é possível nas próximas duas semanas?
- Se o diagnóstico apontar que o problema não é tecnologia e sim como a informação é coletada hoje,
  vocês topariam mudar isso?
- Existe alguma data ou compromisso que torna isso urgente?
- Quem nessa operação provavelmente vai resistir à mudança, e por quê?

## Bloco E — Magnitude (ordem de grandeza)

Faça para as duas ou três dores priorizadas. Não busque número perfeito — busque magnitude.

- Quantas vezes isso acontece por mês?
- Quem resolve quando acontece, e quanto tempo essa pessoa gasta?
- Quanto ganha, por mês, uma pessoa nessa função?
- Quando dá errado de vez, quanto custa o erro?
- Vocês sabem esse número ou é impressão?

> Tudo o que sair daqui entra como **evidência declarada** (`Finding.epistemic_status = hypothesis`),
> nunca como Baseline. Baseline é `Measurement(kind=baseline)` — medição, não estimativa de reunião.
> O Discovery é que converte um no outro.

## Bloco F — Fechamento e aprendizado

- **Nunca pergunte** "gostou do trabalho?".
- **Pergunte:** *"O que vocês entendem agora sobre a operação que não estava claro antes do
  Discovery?"* — a resposta costuma virar o melhor depoimento possível.
- *"Se a gente fizesse isso de novo, o que você faria diferente?"*
- *"Teve alguma pergunta minha que não fez sentido para vocês?"* (alimenta esta base)

## Como esta base evolui

Depois de cada engagement, volte à ficha do Notion e registre: qual pergunta abriu a conversa, qual
caiu no vazio, qual pergunta faltou. Perguntas que provaram valor em duas verticais diferentes sobem
para a base genérica; as que só funcionam num setor descem para a Vertical Knowledge Base.

O registro é uma tabela na ficha do Notion (data · account/vertical · pergunta que funcionou ·
pergunta que falhou · pergunta nova a incorporar), e **está vazia** — a operação ainda não teve o
engagement que a preencheria. É o mesmo contador que a ADR 0069 cita ao decidir construir sem
esperá-lo.
