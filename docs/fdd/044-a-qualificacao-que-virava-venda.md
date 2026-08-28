# FDD 044 — A qualificação que virava venda

> **Primeira fatia da ontologia operada (ADR 0049).** A avaliação de um lead passa a ser entidade,
> com autor, data e resultado; a Qualification Call sai da escada comercial e vira oferta de
> aquisição. A sequência normativa é `Lead → Qualification → (qualified) → CommercialOpportunity`,
> e o passo do meio, que existia na cabeça de quem vende, passa a existir no banco.

## Jornada

Alguém preenche o formulário do site. O lead cai na lista, o comercial olha, gosta do que vê e
clica em **Converter em oportunidade**. Nesse clique o Pulse criava três coisas: uma `Account` em
estado prospect, uma `CommercialOpportunity` no degrau gratuito da escada (`service.tier =
qualification_call`) e um lead arquivado apontando para as duas.

O problema não é o clique — é o que ele afirmava. Uma conversa de qualificação de trinta minutos,
que ainda não tem escopo, não tem valor e pode terminar em "não é para nós", entrava no sistema
como **venda registrada**. Ela somava no funil, aparecia no pipeline com R$ 0,00, contava no
`by_tier` da analítica e, sendo uma oportunidade como qualquer outra, podia ser levada a Ganho e
convertida em `Project`. O produto tinha um degrau comercial cujo propósito é descobrir se há
negócio, e o tratava como se o negócio já existisse.

Do outro lado, a decisão que realmente aconteceu na conversa não ficava em lugar nenhum. Quem
avaliou, quando, com base em quê, e por que o resultado foi esse — nada disso tinha coluna. O
`Lead.status` guardava um rótulo (`qualified`), mas rótulo não é avaliação: ele não tem autor, não
tem data própria, não tem motivo e é sobrescrito pelo próximo que passar. E o caso mais comum do
comercial — "boa empresa, momento errado, volta em seis meses" — não tinha como ser registrado:
ou o lead virava oportunidade que ninguém ia trabalhar, ou era descartado e esquecido.

## O que esta fatia entrega

**`Qualification`, a avaliação como entidade.** Liga-se ao lead (obrigatório) e à conta (opcional
enquanto não houver), guarda `happened_at`, `assessor`, os cinco eixos do roteiro (`fit`, `need`,
`urgency`, `authority`, `capacity`), a `evidence` que sustentou a leitura, o `rationale`, o
`next_step` e o resultado:

| `outcome` | O que significa | O que acontece com o lead |
| --- | --- | --- |
| `qualified` | Há negócio a perseguir | status `qualified`, lead arquivado |
| `nurture` | Boa empresa, momento errado | status `contacted`, **lead segue na lista ativa** |
| `disqualified` | Não é para nós | status `discarded`, lead arquivado |

**Um lead tem várias avaliações**, e não há constraint de unicidade: o `nurture` de hoje vira
`qualified` daqui a seis meses, e as duas são fatos distintos. Sobrescrever a primeira apagaria
justamente o histórico que a entidade existe para guardar. A reavaliação **reusa a conta** que a
primeira criou — criar uma segunda `Account` para a mesma empresa é o defeito que o campo
`account_id` do corpo existe para evitar quando a escolha é explícita, e que o reuso de
`lead.client` evita quando ela não é.

**`nurture_until` é obrigatória em `nurture` e proibida fora dele.** As duas metades vêm do mesmo
argumento: uma nutrição sem data de retorno é um lead esquecido com etiqueta bonita, e uma data de
retorno em quem foi qualificado ou descartado promete um follow-up que ninguém vai fazer — a lista
de nutrição passaria a mostrar quem não está em nutrição.

**A IA é insumo, nunca decisão.** `ai_suggested_outcome` e `ai_score_snapshot` guardam o que o
modelo achou no momento da avaliação, e **nada os copia** para `outcome`. Quem qualifica é o
`assessor`. É a mesma disciplina que a FDD 013 já aplicava ao rascunho de qualificação e a ADR 0031
ao sinal de cobrança: a máquina grava e não age.

**`Service.category`, e a Qualification Call fora da escada.** `acquisition` é oferta de aquisição;
`commercial` é degrau vendável, e é o default — serviço novo nasce para vender. A distinção é por
categoria e **não por preço**: o Discovery + Assessment do programa de founding client também é
gratuito e é degrau. Restam seis degraus vendáveis (FDD 015 continua descrevendo a escada; o que
muda é que a porta não é um deles).

**`POST /leads/{id}/convert/` deixa de criar venda.** Ele resolve ou cria a conta, registra a
qualificação e marca o lead. Some do corpo da action a busca por `PipelineStage` aberto e pelo
`Service` de entrada — e os dois 400 que elas produziam: qualificar um lead não depende mais de o
pipeline estar configurado. A resposta muda de forma, de `Lead` para
`{"lead": {...}, "qualification": {...}}`.

**`POST /qualifications/{id}/open-opportunity/` é o único caminho lead→venda.** Recusa com 409
quando `outcome != qualified` ou quando a avaliação já abriu uma oportunidade; recusa com 400
quando o `Service` escolhido é de aquisição, quando o contato é de outro cliente ou quando a
avaliação ainda não tem conta. Abrir a venda passa a ser um **ato explícito** — que é toda a
diferença: antes ela nascia de graça, no mesmo clique que registrava a conversa.

## Invariantes

As duas primeiras são as invariantes 5 e 6 do mapa de linguagem, e as duas vivem **no modelo**, não
só na view — shell, Django admin e migração futura não passam por rota nenhuma:

1. `Qualification.outcome != qualified` não abre `CommercialOpportunity`. Na porta: 409. No modelo:
   `CommercialOpportunity.clean()` recusa `origin_qualification` cuja avaliação não é `qualified`.
2. Nenhum `Project` nasce de um `Service` com `category=acquisition`. Na porta: 400 em
   `convert-to-project`. No modelo: `Project.clean()`.
3. A conta da avaliação é a mesma do lead, quando os dois já a têm (`Qualification.clean()`) — sem
   isso, um campo opcional pendura a avaliação na organização de outro lead.
4. `origin_qualification` é **só de leitura** na API: o único caminho que a preenche é a action, que
   confere a avaliação antes. Editável, um `PATCH` cru gravaria a coluna sem passar pela regra.
5. A Entrega não alcança `/qualifications/` — nem leitura. A qualificação é ato comercial e nunca
   atravessa para o portal do cliente (mapa de linguagem §3), como já acontece com `lead`. O 403 vem
   do `return False` do `RolePermission`: recurso novo nasce fechado.

## O backfill

`0052_backfill_qualification` traduz cada `CommercialOpportunity` de tier `qualification_call` que
já existe.
O `outcome` é **derivado do estado comercial**, a única evidência que resta do que se decidiu na
época: estágio `won` (ou já com projeto) foi `qualified`; `lost` foi `disqualified`; qualquer
estágio aberto vira `nurture` — o resultado que não afirma nada, que é literalmente o estado
daquela linha. Cada tradução deixa uma `Activity` de nota no cliente: a oportunidade sai da lista, e
sem a nota ela sairia sem explicação.

Três cuidados, cada um com teste em `tests/regression/test_qualification_backfill.py`:

- **A oportunidade com projeto não é arquivada.** `Project.originating_commercial_opportunity` é
  `PROTECT` e a tela do projeto lê a oportunidade para montar o histórico comercial — o mesmo argumento do
  `perform_destroy` da FDD 025.
- **A oportunidade sem lead é pulada.** Uma avaliação sem lead não é avaliação de ninguém, e
  inventar um lead sintético colocaria dado falso na base para satisfazer uma chave estrangeira.
  `manage.py reconciliar_qualification` lista essas linhas depois do deploy: uma migração que aponta
  o que não conseguiu traduzir vale mais que uma que finge cobertura total.
- **Nada é apagado.** O arquivamento é soft, `legacy_opportunity` guarda o vínculo, e a reversa
  desfaz os dois lados — desarquivando **só** o que a ida arquivou. O critério é uma **assinatura**
  e não uma janela de tempo: a ida carimba `archived_at` com o mesmo instante da avaliação que
  criou, e a volta compara por igualdade. "Carimbo posterior ao da avaliação" pareceria equivalente
  e erraria nos dois sentidos — ressuscitaria a oportunidade que alguém arquivou **depois** do
  deploy, que é a mesma perda que o critério existe para evitar, do outro lado da linha do tempo.

## O que a construção decidiu

**`Lead.commercial_opportunity` continua sendo ligado — agora na abertura da venda.** A análise
de origem da FDD 030 atravessa `projeto → oportunidade → lead → source` por essa chave. Movendo a criação da
oportunidade para fora do `convert` sem religar o lead, todo negócio nascido de lead passaria a
contar como "Cadastro direto": uma tela de decisão de investimento errando em silêncio, com a
tabela continuando a renderizar. O vínculo canônico da fatia é `origin_qualification`; este é o
atalho da analítica, e some no dia em que ela souber ler a avaliação no meio do caminho.

**`convert` mantém o 409 de "lead já convertido".** Não é resíduo: `qualified` arquiva o lead, mas
`POST /leads/{id}/unarchive/` existe desde a FDD 025, e sem a guarda a restauração devolveria o
botão de qualificar e criaria uma segunda conta para a mesma empresa.

**Dois enums ganharam nome fixo no OpenAPI.** `Qualification.outcome` disputava `OutcomeEnum` com o
`outcome` do corpo do `apply-gate`, e o desempate por sufixo numérico (`Outcome4e6Enum`) é o mesmo
defeito que o `SourceEnum` já tinha documentado: instável entre gerações, faz o `openapi.yaml`
divergir sem ninguém ter mudado nada.

## Regressões

- `apps/core/tests/test_qualification_model.py` — a fatia inteira pela API e pelo modelo. Arquivo
  separado de `test_qualification.py`, que testa a **qualificação por IA** do lead (FDD 013): nome
  parecido, assunto diferente — lá a IA sugere, aqui alguém decide.
- `tests/regression/test_qualification_backfill.py` — a migração 0052 rodada sobre dado real, com
  os dois casos que ela pula e a reversa que não desarquiva de mais.
- `tests/regression/test_lead_archived_on_convert.py` — a asserção original (qualificado sai da
  lista) mais o seu contrário (nutrido fica).
- `tests/regression/test_origem_do_lead_sobrevive_a_conversao.py` — a travessia da FDD 030 com o
  elo novo no meio.

## Fora deste recorte

- **Tela de Qualification.** Não há listagem de avaliações nem formulário com os cinco eixos: a API
  os aceita e a interface ainda não os oferece. Interface nova exige Design Approval Package, e não
  há um aprovado para esta superfície. A tela de Leads passou a falar em qualificação e a mostrar o
  resultado, e nada além disso.
- **Os renomes físicos.** `Client`→`Account` foi a fatia 2 da issue #67 (ADR 0052); a tabela
  `core_client` é a Fase 6. `Qualification.account` já usa o nome
  canônico apontando para o modelo legado — é o alias previsto, não um descuido.
  **Emenda de 28/08/2026:** `Opportunity`→`CommercialOpportunity` deixou de ser fatia futura — a
  fatia 3 da issue #67 (ADR 0052) a executou, com a tabela `core_opportunity` e a rota
  `/api/v1/opportunities/` intactas. `Qualification.legacy_opportunity` **não** mudou de nome:
  `legacy_` é o escape reservado da `aliases.md` §3.
- **`Engagement` entre Account e Project** (invariante 7 do mapa de linguagem), o split
  `Evidence`/`Finding` e o resto da ontologia: fatias próprias, cada uma com o seu backfill.
- **A recorrência do Transformation Partnership**, que a FDD 015 já deixou nomeada e não feita.
- **Os testes automatizados de linguagem** (as invariantes 1 a 4 do mapa como guarda de CI), que
  saem com a ADR 0049.
