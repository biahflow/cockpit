# FDD 054 — O próximo passo existia e morava onde ninguém procura

> **O próximo passo da conta: qual melhoria atacar em seguida, e o que falta nela.** É a segunda
> das três peças que a ADR 0069 liberou sem o gatilho da ADR 0030, e a única que **não constrói
> sinal novo — constrói leitor**. O dado já estava todo lá; o que faltava era responder *o que
> falta*, num lugar onde a pergunta é feita.

## Jornada

A ADR 0069 registrou a peça em uma frase: *"o Next Best Opportunity já existe pela metade e ninguém
percebeu"*. `priority.ranking_da_conta` ordena as `ImprovementOpportunity` por Opportunity Score
desde a FDD 048, e `recommendations.py` emite a recomendação `prioritization` desde a issue #68.
Manter o bloco em "adiado" era inventário errado, não prudência.

A metade que faltava tinha três defeitos, e nenhum deles é falta de dado.

**A resposta morava onde ninguém a procura.** A pergunta *"onde atuo em seguida neste cliente?"* é
feita olhando o cliente — e a resposta vivia numa lista global de quatro tipos de sugestão em
`/indicadores`, ao lado de cobrança e de prazo. É a mesma fatia que a FDD 038 fez para a saúde e o
`dunning_signal`: o sinal existia, o leitor não.

**Ela dizia qual, e não o que fazer.** A recomendação nomeava a oportunidade de maior score sem
hipótese escolhida, e parava ali. Um operador que já escolheu a hipótese não recebia nada — e não
porque estivesse tudo certo, mas porque o único degrau que o produto sabia observar tinha sido
vencido.

**E a de maior score escondia a seguinte.** Ordenar por score responde "qual é a mais importante",
que não é a mesma pergunta que "o que fazer agora". A conta cuja melhor oportunidade já foi
decidida ficava sem próximo passo enquanto a segunda esperava hipótese.

## O que esta fatia entrega

**Uma função pura, e ela é a única expressão da regra.**

`next_step.proximo_passo_da_conta(account)` percorre as oportunidades da conta **na ordem de
`priority.ranking_da_conta`** — que também define o conjunto elegível: viva, não descartada e com
avaliação vigente — e devolve **a primeira com degrau pendente**, com `improvement_opportunity`,
`title`, `score`, `assessment_version` e `missing`. Sem nenhuma pendente, devolve `None`.

Os quatro degraus, nesta ordem, **como chave e nunca como frase**:

| Chave | Quando |
| --- | --- |
| `choose_hypothesis` | sem `SolutionHypothesis` viva com `status=chosen` |
| `build_business_case` | com hipótese escolhida e sem `BusinessCase` vivo |
| `decide_investment` | com `BusinessCase` vivo em `draft` |
| `open_commercial_opportunity` | com `BusinessCase` `approved` vivo **e** a conta sem `CommercialOpportunity` aberta |

**Dois leitores, uma função.** A action `GET /clients/{id}/next-step/` (`/accounts/{id}/next-step/`
na `/api/v2/`) desenha o painel do detalhe da conta, e `recommendations.build_recommendations`
escolhe por ela a oportunidade que anuncia em `/indicadores`. O contra-argumento registrado da
decisão B1 do DAP era exatamente esse — dois lugares mostrando a mesma recomendação divergem —, e a
função única é a metade que o responde.

**Um painel, acima de "Saúde da relação".** Ele mostra **um** degrau: o primeiro que falta na
primeira oportunidade com pendência. Os rótulos são da tela; o degrau, do servidor.

## Critérios de aceite

- Conta sem oportunidade com avaliação vigente devolve `next_step: null` e `ranked_count: 0`; o
  painel mostra o **vazio honesto**, com a porta para a priorização.
- Cada um dos quatro degraus sai como sua chave, e o degrau seguinte tem controle ao lado: hipótese
  apenas *proposta* não encerra o primeiro; hipótese escolhida e **arquivada** devolve ao primeiro;
  business case arquivado não conta como montado; rascunho vence aprovado quando os dois existem.
- **A de maior score já encaminhada não esconde a seguinte.**
- Investimento **recusado** não é pendência: a oportunidade sai da fila e a seguinte assume.
- O quarto degrau some com **qualquer** venda aberta na conta, e não some com venda ganha nem com
  venda aberta de outra conta.
- `/recommendations/` continua com o mesmo `kind`, `label`, `detail` e `url`.
- Entrega não alcança o próximo passo de conta fora do escopo dela (404), e alcança o da conta em
  que participa de projeto.
- Nenhuma migração: a fatia não cria campo nem modelo.

## Contrato

Rota nova, aditiva, nas duas versões:

| Rota | Âncora do recorte | Métodos |
| --- | --- | --- |
| `/clients/{id}/next-step/` · `/accounts/{id}/next-step/` | a própria conta (`AccountViewSet`) | `GET` |

Ela nasce nas duas de uma vez porque o router da `/api/v2/` é derivado do `registry` da v1
(`urls.py`) — uma action no viewset compartilhado não precisa de linha nenhuma lá.

```json
{
  "next_step": {
    "improvement_opportunity": 77,
    "title": "Reconciliação manual de repasses",
    "score": "78.00",
    "assessment_version": 2,
    "missing": "choose_hypothesis"
  },
  "ranked_count": 3
}
```

`score` sai como **texto**, na mesma forma que `ImprovementOpportunitySerializer.get_score` já
publica (ADR 0068), e `assessment_version` vai junto dele pela razão da decisão B1 do DAP de
priorização: um score sem a versão ao lado é um número que não se compara com o da semana passada.

`missing` é publicado como **enum** (`MissingEnum`, derivado de `next_step.DEGRAUS`), e não como
texto livre — ao contrário de `RecommendationItem.kind` logo ao lado, e pela diferença que aquele
comentário registra: lá não existe lista de onde derivar e inventar uma criaria a segunda definição;
aqui a lista existe, e publicá-la é o esquema dizendo o vocabulário fechado em vez de prometer
"qualquer texto".

**Nome canônico e nenhum alias.** `next_step` e `improvement_opportunity` nascem certos, e
`open_commercial_opportunity` carrega o qualificador que a §5 exige — `opportunity` sozinho colide
entre venda e melhoria operacional, e a guarda `backend/tests/test_vocabulario.py` reprovaria a
forma desqualificada nos dois lados.

**A action não entra no `/overview/`.** Aquele agregador tem orçamento determinístico de consultas
(ADR 0014, `loadtests/`) e serve também o **grid** de contas, onde meia dúzia de consultas por conta
se multiplicaria por linha da carteira. A action é do detalhe, e paga o custo de uma conta.

## Decisões

### Por que "a primeira com pendência", e não "a de maior score"

São perguntas diferentes, e a tela de priorização já responde a primeira: ela mostra o ranking
inteiro, com `rank` derivado. O painel existe para dizer **o que fazer agora**, e repetir o topo do
ranking seria uma segunda apresentação do mesmo fato — que, além de redundante, tem um modo de falha
próprio: a conta cuja melhor oportunidade já foi decidida mostraria "nada pendente" com trabalho por
fazer embaixo.

O critério tem um efeito colateral aceito e escrito: uma oportunidade **recusada** não é pendência,
e a fila anda. Insistir nela seria o produto discordando de quem decidiu.

### Por que a função devolve chave, e nunca frase

O molde é `prove.o_que_falta_para_iniciar` (FDD 049), e a razão é a mesma: rótulo é da superfície, e
um servidor que devolvesse "Escolher a hipótese" em português congelaria a copy do board dentro do
backend — o mesmo defeito que o `CLAUDE.md` proíbe em mapa de estado (*"devolve variante, nunca a
cor"*). O mapa chave → rótulo mora em `AccountDetailPage.tsx`, num lugar só.

### Por que o quarto degrau é heurístico, e por que isso não se conserta com uma FK

Não existe elo entre `ImprovementOpportunity` e `CommercialOpportunity`, e **não deve existir**: é a
separação que o `language-map` §5 protege, e a FDD 048 registra que a oportunidade de melhoria não
referencia `PipelineStage` em campo nenhum, com teste sobre o `_meta` do modelo afirmando isso. Uma
FK aqui traria a venda para dentro da melhoria e o funil da casa passaria a somar melhorias que
ninguém vendeu.

Sem o elo, "já abrimos a venda desta melhoria?" só se responde no nível da **conta**, e a
consequência fica declarada em vez de escondida: uma conta com qualquer venda aberta não recebe este
degrau, mesmo que a venda seja de outro assunto. É leitura conservadora de propósito — errar para o
lado de não cobrar quem já tem conversa comercial em aberto custa menos que mandar abrir a segunda
venda do mês.

### Por que `ranked_count` acompanha a resposta

Porque **os dois vazios não são o mesmo vazio**, e o board desenha os dois. Conta sem nada avaliado
mostra o vazio honesto ("o próximo passo aparece quando houver avaliação", com a porta para a
priorização); conta com oportunidades avaliadas e nenhuma pendência mostra o neutro ("nada
pendente"), que é o estado de quem está indo bem. Os dois chegam como `next_step: null`.

Distingui-los no cliente exigiria recontar as oportunidades por `score != null` **e** repetir a
exclusão da descartada — o critério de elegibilidade do ranking reexpresso do lado errado da
fronteira, que é exatamente o que a decisão B1 comprou ao mandar os dois leitores usarem uma função
só.

### Por que a recomendação acompanha o degrau, e não só o primeiro

A primeira versão desta fatia emitia a recomendação **apenas** quando o degrau era
`choose_hypothesis`, para não tornar falsa a frase *"priorizada e ainda sem hipótese de solução
escolhida"*. O raciocínio estava certo sobre a frase e errado sobre o efeito: bastava a oportunidade
de maior score estar no degrau 3 para **a conta inteira desaparecer de `/indicadores`** — enquanto o
painel do detalhe dela mostrava o passo, em letras grandes.

Dois leitores que discordam **por omissão** são exatamente o que a decisão B1 comprou a função única
para evitar. Um deles dizia "decida este investimento" e o outro não dizia nada, e nada não
contradiz — foi por isso que passou pela revisão de código e só apareceu ao ler os dois lados
juntos.

O que estava preso ao primeiro degrau era a **frase**, não a recomendação. Cada degrau ganhou a sua,
num mapa em `recommendations.py` — e não em `next_step.py`, que devolve chave e nunca copy (regra de
`prove.o_que_falta_para_iniciar`). Este endpoint sempre entregou texto pronto: os quatro `kind` têm
`label` e `detail` em português desde a FDD 006, e cada superfície escreve a sua — o painel tem o
mapa dele em TypeScript, a lista tem o dela no servidor.

O `kind`, o `label` e a `url` continuam como estavam; o teste de contrato que os congela segue
valendo, e ganhou o par que trava a existência da recomendação em qualquer degrau.

### Por que `tem_venda_aberta` é pública

`build_recommendations` faz exatamente a mesma pergunta na regra de `upsell`. Deixá-la inline nos
dois lugares criaria duas expressões de "esta conta tem venda em aberto" que divergem na primeira
vez que alguém mexer numa delas — o argumento de `ImprovementOpportunity.current_assessment` e de
`Project.objects.visible_to` (ADR 0010), aplicado a um predicado pequeno o bastante para parecer que
não precisa de casa.

### Por que o cálculo lê em Python o que já foi prefetchado

`_hipotese_escolhida` e `_business_cases_vivos` filtram sobre `.all()`, e não com `.filter()`, pela
razão escrita em `ImprovementOpportunity.current_assessment`: um `.filter()` emite consulta nova e
**ignora** o `prefetch_related` de quem chamou — custo de N+1 com aparência de custo resolvido. Isso
importa aqui mais que no vizinho, porque `build_recommendations` chama esta função **uma vez por
conta da carteira**.

A pergunta da venda aberta chega como função, e não como booleano, pelo mesmo motivo invertido: só o
quarto degrau precisa dela, e avaliá-la para toda oportunidade pagaria a consulta para descartá-la.

## Superfície

Painel em `frontend/src/pages/AccountDetailPage.tsx`, **acima de "Saúde da relação"**, governado
pelo DAP `docs/design/dap-discovery-session-e-business-case-r2/`, decisão **B1** — mudar a
superfície exige revisão nova do pacote, não julgamento na hora. Ele não entra no menu lateral: o
próximo passo é sempre *de uma conta*, e um item de menu que abre perguntando "qual?" é o beco já
recusado duas vezes.

A ordem é a decisão: a saúde diz *como estamos indo* e o próximo passo diz *o que fazer agora*; quem
abre a conta com uma pergunta na cabeça abre com a segunda.

**A tela nunca recalcula o degrau.** Ela recebe a chave e escolhe o rótulo, no molde das três
pastilhas do PROVE (FDD 049). O painel usa as primitivas — `.panel`, `.eyebrow`, `.panel-heading`,
`.row-meta`, `.state`, `.empty-state`, `.back-link` — e o mapa de estado devolve **variante**, nunca
a cor (ADR 0026): o score é `.state--0` e o degrau é `.state--2`, o par que o board mediu.

**Duas divergências conscientes do board**, as duas por o dado não existir no contrato:

1. o board escreve linhas com dado que a API não publica ("Hipótese escolhida em 02/09", "Duas
   hipóteses propostas, nenhuma escolhida"), e o próprio pacote as marca como ilustrativas; a frase
   de cada degrau sai **da chave e de nada mais**, porque inventá-las seria a tela afirmando o que
   não sabe;
2. o neutro do board diz "As três oportunidades priorizadas têm investimento decidido e venda
   aberta", e isso não é verdade em todos os caminhos que chegam ali — uma recusa também zera a fila.
   A tela diz o que é sempre verdade: *"{n} oportunidades priorizadas nesta conta, nenhuma com passo
   pendente"*.

A rota `/contas/1` já estava em `frontend/e2e/matrix.ts`, e o mock ganhou o degrau — axe e ausência
de rolagem horizontal nas três larguras passam a medir o painel com conteúdo, que é onde 390px
quebra.

## Testes

- `backend/apps/core/tests/test_proximo_passo.py` — os quatro degraus com o controle do seguinte ao
  lado, a hipótese proposta que não encerra o primeiro, a escolhida arquivada que devolve a ele, o
  business case arquivado, o rascunho que vence o aprovado, as três formas de a venda não encerrar o
  quarto degrau, a recusa que não é pendência, **a de maior score encaminhada que não esconde a
  seguinte** (com o controle da ordem entre duas pendentes), a descartada e a de outra conta fora da
  fila, os dois vazios distinguidos por `ranked_count`, o vocabulário congelado nos quatro degraus,
  a venda perguntada uma vez por conta, a rota nas duas versões, o recorte da Entrega com controle
  positivo, e as duas metades do segundo leitor — a recomendação que acompanha o degrau e o
  score em texto com duas casas.
- `backend/tests/regression/test_a_recomendacao_de_priorizacao_mantem_o_contrato.py` — o `kind`, o
  `label`, o `detail` e a `url` congelados, mais a forma do item (quatro chaves, todas texto).
- `frontend/src/pages/AccountDetailPage.test.tsx` — o degrau que o servidor devolveu com o score e a
  porta, os quatro rótulos (e o único que leva ao Comercial), o vazio honesto, o neutro nos dois
  números, e a ordem em relação a "Saúde da relação".

## Fora deste recorte

- **A tela do Business Case e a Discovery Session.** São as outras duas fatias do mesmo DAP.
- **Mudar o contrato de `/recommendations/`** ou dar escopo por usuário a `build_recommendations`. A
  rota é fechada à Entrega por papel (`test_delivery_aggregates_are_scoped.py`), e não recortada —
  mudar isso é outra fatia.
- **Qualquer FK entre melhoria e venda.** Ver a decisão acima; a heurística é o preço da separação,
  e ela é o que se quer manter.
- **O `/clients/overview/`.** O próximo passo não entra lá, pelo orçamento de consultas.
- **O portal do cliente.** `portal.build_snapshot` não leva nada desta fatia: o próximo passo é
  leitura interna sobre o que a casa vai fazer, e o `BusinessCase` que dois dos quatro degraus citam
  já não atravessa (FDD 053).
- **Migração.** Nenhuma: a fatia não cria campo nem modelo.
