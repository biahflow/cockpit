# FDD 039 — O achado que não sobrevivia à reunião

> **Discovery estruturado, no recorte que passa no teste da ADR 0030.** A camada foi adiada por
> aquela ADR, que deixou junto o critério para desadiá-la — e o critério, aplicado peça a peça,
> parte o bloco em dois. Entra o que o material define como regra pronta; o resto segue nomeado e
> não feito, agora com o motivo escrito. A decisão está na **ADR 0034**.

## Jornada

Uma reunião de Discovery dura duas horas e produz muito. Um consultor sai dela sabendo quem faz o
quê, em que sistema, quanto demora, o que costuma dar errado e quanto isso custa por mês. Nada
disso sobrevive à reunião.

O que sobrevive hoje é **prosa**. `MeetingViewSet.discovery` chama `_ai_run` com
`formato=_FORMATO_TEXTO` e grava um blob em `Artifact.content`; o prompt pede "situação atual,
dores, objetivos, stakeholders, restrições" e recebe parágrafos. Aquele texto tem valor — é a
narrativa que se entrega — mas ele não filtra, não agrega, não vira entidade e, principalmente,
**não distingue o que foi observado do que foi suposto**.

Essa última perda é a que o método trata como grave. `docs/metodologia-fde.md:86` é literal: *"Todo
achado é rotulado FATO / HIPÓTESE / DESCONHECIDO — nunca se apresenta hipótese como fato."* E o
quality gate de Discovery (`:109`) já pergunta *"Hipóteses identificadas e rotuladas?"* — uma
pergunta que, hoje, só se responde "sim" no braço, porque não existe onde rotular.

Há um segundo lugar onde a perda aparece, e ele custa dinheiro. O material traz a fórmula do custo
do estado atual (`:87-88`) e a proposta por IA já cita nível de produto, blueprint e case com
número real (FDD 026, FDD 027) — mas nunca **o custo da operação do cliente**, que é o argumento
mais forte que um Discovery produz. Ele não é citado porque não existe em lugar nenhum: mora na
cabeça de quem levantou, e na planilha que ninguém abre de novo.

E há uma terceira, que só aparece na segunda venda para a mesma empresa. O mapa AS-IS de um cliente
não pertence à venda que o descobriu. A metodologia diz isso na regra comercial (`:50-53`,
Account ≠ Opportunity): a empresa é uma conta, e cada degrau — Discovery Sprint, Feasibility,
PROVE, Scale — é uma oportunidade própria. Um mapa preso ao projeto obrigaria a redesenhar o AS-IS
do zero a cada degrau, que é exatamente o defeito que o `DigitalEmployee` tinha antes da FDD 026.

## O que esta fatia entrega

**Três entidades, ancoradas no cliente.**

- **`Processo`** — um processo da operação, com nome, ordem, proveniência (de que projeto e de que
  reunião veio) e os nove insumos da fórmula do custo. Ele nasce com isso e **nada mais**: sem
  `status`, sem `dono`, sem `nivel`. A entidade existe porque o esquema do material é "para cada
  etapa de um processo" — o processo é exigido pelo próprio esquema, não inventado por este modelo.
- **`ProcessoEtapa`** — a etapa, com os seis campos do **P-S-D-T-E-R** (`:75-79`), exatamente as
  seis letras, na ordem em que a pergunta é feita na reunião: pessoas, sistema, dados, tempo, erro,
  retrabalho.
- **`Evidencia`** — o achado, com a **forma** de onde veio (uma das cinco de `:81-84`) e o
  **rótulo** (`:86`). Liga ao processo, e opcionalmente à etapa.

**O custo do estado atual, com a conta à vista.** `processos.custo_do_estado_atual` é função pura
no molde de `health.py`: devolve as **parcelas**, o total, o que ficou **não apurado** e o carimbo
`sustentado`/`hipotese`. Um número sem a conta que o produziu não se discute — se aceita ou se
rejeita —, e é isso que o método proíbe ao exigir o rótulo.

**A extração da transcrição, que nasce hipótese.** Uma action `estruturar` no `MeetingViewSet`, no
molde de `extrair_decisoes` (FDD 032): a transcrição vira processos, etapas e achados em uma
transação. Todo achado extraído grava `rotulo=hipotese`, `forma=entrevista`, **sempre** — e o
prompt não menciona essas chaves, porque elas são impostas no coletor e não pedidas ao modelo.

**O custo na proposta, só quando sustentado.** `ai.build_opportunity_context` passa a levar o mapa
qualitativo do processo e — apenas quando há evidência `fato` viva — o número.

## Critérios de aceite

- Uma `Evidencia` não se cria sem `rotulo` e sem `forma`; omiti-los é erro de validação, não
  default silencioso.
- Uma `Evidencia` não aponta para etapa de outro processo (é como uma evidência alcançaria a
  operação de **outro cliente** por um campo opcional).
- Entrega que não participa de nenhum projeto do cliente não **lê** e não **escreve** nenhuma das
  três entidades — nem pelo caminho do filho, que chega ao cliente pelo processo pai.
- Fator ausente no custo aparece em `nao_apurado` e **não** entra como zero no total.
- Achado extraído pela IA nunca grava `fato`, mesmo que o modelo mande `"rotulo": "fato"`.
- Segunda extração da mesma reunião devolve 409 e não duplica nada.
- Custo não sustentado não vira número na proposta, e a lacuna é **declarada**.
- Nada das três entidades aparece no snapshot do portal do cliente.

## Contrato

Rotas novas em `/api/v1/`:

| Rota | Quem |
| --- | --- |
| `/processos/` (CRUD + `?client=` + `?archived=1` + `unarchive`) | vendas / delivery no cliente com projeto seu / admin |
| `/processo-etapas/` (CRUD + `?processo=`) | idem |
| `/evidencias/` (CRUD + `?processo=` + `?etapa=` + `?rotulo=` + `?forma=`) | idem |
| `POST /meetings/{id}/estruturar/` | quem alcança a reunião |

Aditivo, sem remover nem mudar forma: o contexto da proposta por IA passa a poder conter o mapa de
processos e o custo sustentado.

**Vendas e Entrega escrevem**, pelo argumento que a FDD 037 usou para `satisfacao`: quem conduz
Discovery é das duas áreas — o comercial levanta a operação na venda, a entrega continua levantando
dentro do projeto —, e um registro que só metade da casa pode fazer é um registro que não acontece.

## Decisões

### Por que só metade do bloco

É a ADR 0034, e ela não revoga a ADR 0030 — aplica o teste que aquela escreveu. Passam P-S-D-T-E-R,
as cinco formas, os três rótulos e a fórmula do custo. Reprovam Pain Point (o termo não aparece no
documento), Business Case (uma menção, sem estrutura), Value Ledger (zero ocorrências), Opportunity
Backlog (só como pauta mensal), Next Best Opportunity e o cockpit de reunião (existem só no
roadmap) e o Opportunity Score (o gate cobra, a fórmula não existe).

### Por que o rótulo não tem default

Precedente literal do `Satisfacao.fonte` (ADR 0032): *"justamente para ninguém escolher por
omissão"*. Um default não é neutro — faz a casa escolher pelo silêncio de quem não escolheu, e o
erro cai sempre para o mesmo lado. Nem mesmo `hipotese` como default serve: ele apagaria a
diferença entre "achamos que é hipótese" e "ninguém classificou", e erro que se parece com
preenchimento é pior que campo vazio, porque ninguém volta para conferir.

### Por que `_mes` no nome dos insumos

`ProcessoEtapa` tem `tempo`, `erro` e `retrabalho` que são **descrição** ("quanto demora", "o que
acontece quando dá errado"); os campos homônimos do `Processo` são **dinheiro e quantidade**. Nomes
iguais para perguntas diferentes fariam a segunda vencer em silêncio. A separação é por nome, e não
só por comentário, porque comentário não aparece no autocompletar.

### Por que o arquivamento cascateia

Etapa e evidência são listáveis por conta própria, então a regra transversal da FDD 025 se aplica:
quem tem filho listável escolhe entre recusar com 409 ou arquivar junto. Aqui é arquivar junto — um
mapa de processo se guarda inteiro, e obrigar a apagar vinte etapas antes de guardar o processo
transformaria "arquivar" em trabalho manual; o que não se consegue guardar acaba sendo apagado de
verdade.

A metade que quase se perde é a simétrica: **desarquivar não pode ressuscitar o que alguém removeu
de propósito antes**. O critério é o carimbo idêntico ao do pai — quem foi arquivado junto volta
junto. É por isso que os três recebem o mesmo instante, e não três chamadas de `now()`.

### Por que a extração nasce hipótese

Um modelo lendo transcrição produz **o que foi dito**, e "o que dizem" é uma das cinco formas de
evidência, não prova. A imposição é no coletor e o prompt sequer menciona as chaves: pedir ao
modelo e sobrescrever depois deixaria no prompt a aparência de que ele decide, e a primeira pessoa
a "melhorar" o prompt reativaria o caminho sem saber que existia uma regra.

### Por que a lacuna do custo é dita, e não silenciada

Quando o custo não está sustentado, o contexto da proposta declara isso em vez de omitir o
processo. Silenciar convidaria o modelo a preencher — foi o defeito que a rodada 5 de homologação
achou na base de conhecimento (FDD 029, ADR 0023): diante de lacuna, o modelo completa.

## Testes

- `apps/core/tests/test_processos.py` — o cálculo (cada fator faltando manda a parcela para
  `nao_apurado` sem zerar o total), a sustentação, o `clean()` da evidência, o CRUD pelos três
  papéis, a fronteira de cliente **nas duas metades** e pelo caminho do filho, o caminho inverso do
  `PATCH`, os filtros de texto fechado e a cascata de arquivamento com a sua metade simétrica.
- `apps/core/tests/test_processos_ia.py` — a extração, incluindo o modelo mandando
  `"rotulo": "fato"` e sendo ignorado, o descarte de item malformado, o 502 sem lista, o 409 na
  reexecução e a transação sem parcial.
- `tests/regression/test_processo_nao_volta_ao_cliente.py` — duas camadas, comportamental e
  estrutural sobre a fonte de `portal.py`.
- `tests/regression/test_a_extracao_nasce_hipotese.py` — a regra da ADR 0034, também em duas
  camadas: o que fica no banco, e o prompt não podendo voltar a pedir as chaves.
- `tests/regression/test_hipotese_nao_sustenta_numero.py` — o número só atravessa para a proposta
  com fato vivo, e some quando ele é arquivado.

## O que a construção decidiu

Três coisas que a revisão do diff mudou, e nenhuma estava no plano.

**O dinheiro viajava como `float`.** `get_custo` é `SerializerMethodField`, e o que ele devolve vai
direto ao renderizador: o encoder do DRF converte `Decimal` em `float`, e o comentário do próprio
DRF diz que aquele ramo existe para quem escapa de um `DecimalField`. `Decimal("5000.00")` chegava
ao cliente como `5000.0`, na mesma API em que `Invoice.amount` viaja como string. O teste que
existia não podia pegar — ele afirmava sobre `response.data`, onde o valor ainda é `Decimal`, e a
conversão só acontece na renderização. A regressão nova afirma sobre `json.loads(response.content)`.

**As parcelas não somavam o total.** Ao corrigir o formato apareceu `"5000.0000"`: `Decimal` soma
expoentes na multiplicação, então o núcleo carrega quatro casas. Arredondar só na exibição
resolveria a aparência e criaria coisa pior — linhas que não somam o número embaixo delas, numa
tela cujo propósito inteiro é mostrar a conta. O arredondamento ficou na origem: **cada parcela vai
a centavos e o total é a soma das parcelas já arredondadas**, não o arredondamento da soma.

**O custo não tinha como sair de zero.** A extração traz o mapa, e os nove insumos nascem nulos;
sem formulário para eles, `nao_apurado` ficaria cheio para sempre e a tela mostraria um total que
nunca poderia ser outra coisa. O formulário entrou com a regra que o espelha no backend: **campo em
branco vira `null`, nunca `0`** — mandar zero por omissão apagaria a diferença entre "não medimos" e
"medimos e não há", e o total pareceria fechado sem nunca ter sido. Junto, o vínculo opcional do
achado com a etapa, que esta FDD dizia existir "para ser preenchida por gente depois" sem que
houvesse onde.

## Fora deste recorte

- **As sete peças que reprovam no teste da ADR 0030**: Pain Point, Business Case, Value Ledger,
  Opportunity Backlog, Next Best Opportunity, o cockpit de reunião de Discovery e o **Opportunity
  Score**. O Score é o mais incômodo, porque o quality gate já o cobra e a fórmula não existe em
  lugar nenhum — é pergunta para o material responder antes de virar código.
- **A migração dos dados do Notion**, que a ADR 0030 já deixara nomeada e não feita.
- **`agents.build_delivery_context`**, o ROI e o `Case` não enxergam os três modelos. O custo do
  estado atual é insumo de proposta, não de saúde de entrega, e trocar a fonte do ROI segue pedindo
  ADR própria (RFC 0004).
- **Vincular achado a etapa na extração.** O modelo não distingue com confiança a qual etapa um
  achado pertence, e vínculo errado é pior que vínculo nenhum — `Evidencia.etapa` é opcional
  exatamente para ser preenchida por gente depois.
- **Persistir o custo calculado.** Seria uma segunda verdade sobre o mesmo dado: mudar o volume
  deixaria o número gravado dizendo o antigo (ADR 0034).
