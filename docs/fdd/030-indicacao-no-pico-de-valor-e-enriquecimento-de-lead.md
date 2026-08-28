# FDD 030 — Indicação no pico de valor e enriquecimento de lead

> **Status: parcial.** FDD curta de propósito: a captação já está muito mais construída do
> que parece, e o que falta é estreito. **Entregues: a medição por origem até o negócio
> fechado** (`funnel.by_source` em `/api/v1/analytics/`, seção "Origem do negócio" em
> Indicadores) **e o enriquecimento de lead** (`enrichment.py`, flag `enrichment`, provedor
> BrasilAPI). **Aberto:** o pedido de indicação no pico de valor — e ele depende do teto de
> frequência e dos gatilhos do portal do cliente (FDD 022 de lá, ela própria bloqueada por
> ordem até o laço de ação do funil fechar).
>
> **Sobre o enriquecimento.** O provedor é **cadastro público de CNPJ** (BrasilAPI), e a
> escolha carrega o argumento da própria FDD: o instrumento de nicho é a `Vertical`, e o CNAE
> é a única fonte que a preenche com dado oficial em vez de inferência de vendor. Ele entra no
> **mesmo** contexto de `qualify_lead`, nunca num prompt paralelo — o objetivo é melhorar o
> `ai_fit`, e um segundo score seria dois números discordando sem que ninguém saiba qual olhar.
> A flag nasce **sem `requires`**, o que é correto e não descuido: cadastro público não tem
> chave, então não existe variável cuja ausência denuncie falta de configuração (precedente do
> modo `adc` da ADR 0016). Ela também nasce **desligada**, e não pela razão de sempre — a
> BrasilAPI é gratuita, então não há custo por chamada a evitar; a razão é que isto manda o
> CNPJ digitado no formulário público para um terceiro, e isso é decisão de fluxo de dado que
> a instalação toma de propósito. O CNPJ é **opcional** no intake: exigi-lo trocaria volume de
> lead por qualidade de cadastro, que é o negócio errado para quem depende de demanda de topo.
>
> A medição saiu primeiro por uma razão de ordem, não de conveniência: ela é a única metade
> que **não** depende do portal do cliente, e é a que diz se a indicação vale o esforço. Pedir
> indicação sem saber quanto indicação fecha seria construir o canal e continuar sem a
> resposta que esta FDD abre dizendo que quer.
>
> E ela não custou coluna nenhuma. A travessia `projeto → oportunidade → lead → source` já
> existia em chaves desde a FDD 013 — `Lead.opportunity` é FK, `Project.opportunity` é
> OneToOne —, de modo que "a origem sobrevive à conversão" era **verdade sem leitor**, e não
> uma lacuna de modelo. O que se construiu foi a leitura, com duas armadilhas medidas e
> fixadas em regressão (`tests/regression/test_origem_do_lead_sobrevive_a_conversao.py`): o
> lead convertido está **arquivado**, então contar a entrada com o filtro `active` habitual
> apagaria justamente quem fechou; e `CommercialOpportunity.leads` é reverso de FK, então agrupar por
> `join` somaria a **receita duas vezes** — a origem sai de `Subquery`.

## Jornada

"Tenho um formulário no site que salva no CRM" descreve bem menos do que existe. O `Lead`
já carrega **qualificação por IA completa** — `ai_fit` (alto, médio, baixo), `ai_score`,
`ai_summary`, `ai_recommended_action`, `qualified_at` — e converte para `Client` e
`CommercialOpportunity` sem duplicar contexto. E o **agendamento automático já está construído**:
`booking.py` gera os horários livres a partir da grade de horário comercial **menos o
free/busy real do Google menos as reservas existentes**, e materializa a reserva criando o
evento no Calendar, atrás da flag `calendar`, com a geração de slots pura e testável. É a
FDD 013, e está entregue.

Isso reordena a conversa sobre demanda. Para consultoria de ticket alto, demanda eficiente
não é volume no formulário — é **confiança chegando antes do formulário**. Tráfego frio não
fecha ticket alto: a pessoa não confia o bastante para uma conversa cara, o lead sai caro e
converte mal. Todo canal eficiente é, no fundo, um mecanismo de transferir confiança.

Sob essa lente, o que falta construir é pequeno e específico: **pedir indicação no momento
em que o valor foi realizado**, e **enriquecer o lead** para que a qualificação que já existe
decida melhor. O resto do que costuma ser proposto sob "SDR e agentes de vendas" ou já
existe, ou é o canal errado para este perfil.

## Regras

- **Não há decisão de ferramenta de agendamento a tomar.** O argumento para adotar um
  provedor externo — "não construa detecção de conflito e fuso horário, é uma carreira de
  dor" — chega **depois** de construído e rodando. Trocar agora seria descartar código
  testado em troca de dependência de fornecedor, o inverso exato de "compre commodity". O
  assunto só reabre com **dor concreta nomeada**: tratamento de fuso horário, remarcação ou
  cancelamento pelo próprio lead, ou o I/O com o Google que hoje está fora da cobertura de
  teste. Sem uma dessas, é não-problema, e a energia gasta escolhendo ferramenta é
  desperdício.
- **Pedir indicação no pico de valor.** O pedido pendura nos gatilhos que o portal do cliente
  passa a ter com o funil de onboarding e a pesquisa por evento — fase concluída, primeiro
  ROI visto —, com o **mesmo teto de frequência** desses avisos, para não virar mais um
  toque. O pedido chega com o texto pronto para o cliente encaminhar: indicação num B2B de
  ticket alto fecha com uma fração do esforço de um lead frio porque a confiança viaja junto,
  e o erro comum é deixá-la no acaso e pedir por e-mail genérico, descolado de qualquer
  entrega.
- **Indicação nasce como `Lead` com `source` próprio.** Nada de caminho paralelo: entra no
  mesmo funil, passa pela mesma qualificação, e o `source` é o que permite medir depois
  quanto a indicação realmente fecha.
- **Enriquecimento entra atrás de adapter e flag**, no padrão da casa, e **alimenta a
  qualificação existente** em vez de criar uma paralela — o objetivo é melhorar `ai_fit`,
  não produzir um segundo score. Escopo mínimo: o que o `qualification.py` consegue usar.
  Falha do provedor não bloqueia o lead; sem enriquecimento, a qualificação roda como hoje.
- **Vertical é o instrumento de nicho, e já está proposto.** A `Vertical` da FDD 026 torna
  "a consultoria de IA para *este* setor" uma dimensão de primeira classe, do blueprint ao
  case (FDD 027) — dominar um vertical estreito é dramaticamente mais barato que gerar
  demanda ampla, porque dentro de uma comunidade fechada o boca a boca viaja sozinho. O
  enriquecimento deve preencher a vertical do cliente quando conseguir inferi-la.
- **Medir até o cliente fechado, não até o formulário.** O desperdício de demanda mora em
  canal que gera lead e não gera cliente. O `source` do `Lead` precisa sobreviver à conversão
  em `CommercialOpportunity` e em `Project`, para que a pergunta "que canal produz negócio fechado"
  tenha resposta — é o "medir para agir" apontado para o topo do funil.

## Aceite

Ao concluir uma fase com o ROI já visível para o cliente, a equipe recebe a sugestão de pedir
indicação àquele cliente, com o texto pronto — e o pedido respeita o mesmo teto de frequência
dos demais avisos, de modo que um cliente não recebe dois toques na mesma semana. A indicação
que chega entra como `Lead` com origem própria, passa pela qualificação por IA como qualquer
outro e aparece no funil já com o fit sugerido. Em **Indicadores**, é possível ver quantos
negócios **fechados** vieram de cada origem, e não apenas quantos leads entraram.

## Regressão crítica

Pedido de indicação respeita o teto de frequência por cliente e nunca é disparado sem que
haja valor realizado registrado — pedir indicação a quem ainda não recebeu nada é o modo de
falha desta feature. Falha do provedor de enriquecimento não impede a criação do lead nem a
qualificação. A origem do lead sobrevive à conversão em oportunidade e em projeto. E
nenhuma rota de agendamento muda: `booking.py` continua sendo o dono dos horários.

## Fora deste recorte

**SDR outbound.** Os agentes de `agents.py` são copilotos internos por área — Comercial,
Entrega, Financeiro —, não prospecção ativa, e transformá-los nisso é outra categoria de
produto e de risco.

**Tráfego pago.** Registrado com o motivo, para não voltar como sugestão óbvia: anúncio serve
a retargeting de público morno ou a volume de ticket baixo. Para ticket alto, um punhado de
visitantes que já confiam vale mais que uma enxurrada de frios.

**A dependência que não se automatiza.** Para uma consultoria pequena de ticket alto, a
visibilidade e as relações de quem funda são o motor de demanda inicial, e isso não é
delegável cedo. É a única parte do negócio onde depender de uma pessoa é a resposta certa —
e vale dizer isso aqui, porque contradiz o objetivo declarado em todas as outras FDDs.
