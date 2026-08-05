# ADR 0014 — Gate de carga por custo de query no CI, k6 como procedimento operado

**Status:** aceito

## Contexto

Último item aberto do bloco "Prontidão para produção" do `roadmap.md`: *ampliar a matriz de testes —
acessibilidade, responsividade e carga*. O que existia de carga era `loadtests/dashboard.js`: 20 VUs
por 30 s contra uma rota, fora do CI.

Ele não era só pequeno — **não podia passar**. Mandava o mesmo `SESSION_COOKIE` para os 20 VUs, e o
teto do DRF é por usuário: `USER_RATE` a 2000/hour é ≈0,55 req/s (ADR 0009). Vinte VUs em laço
somam milhares de requisições no mesmo contador, e o `http_req_failed: rate<0.01` do próprio script
reprovaria em 429 muito antes de encostar no Django. O número que ele produziria seria a velocidade
do throttle.

A FDD 021 estabeleceu o precedente forte deste repositório: o drill de backup roda **a cada PR**,
porque garantia que ninguém exercita não é garantia. A pergunta aqui é se carga cabe no mesmo molde.

Dois fatos empurram para lados diferentes.

**Latência em runner compartilhado é ruído.** O runner do GitHub Actions divide CPU e disco com
outros trabalhos. Um `p(95)<1000` medido ali oscila com o vizinho de máquina, e um gate que reprova
sem que nada tenha mudado ensina o time a reexecutar até passar — que é o pior estado possível para
um gate: ele existe, consome tempo e não é levado a sério.

**O que quebra em produção não é a constante, é a inclinação.** `/clients/overview/` emitia ~14
queries por cliente do grid; `/risk/` e `/health/`, 2 e 4 por projeto. Com a base de
desenvolvimento isso é imperceptível — e nenhum teste de latência sobre 3 clientes veria o que
acontece com 300. Esse defeito é **determinístico** e mensurável sem cronômetro.

## Decisão

**No CI, o gate de carga é contagem de query; o k6 fica fora, como procedimento operado.**

O gate (`backend/tests/regression/test_aggregate_query_budget.py`) mede a mesma rota com duas bases
de tamanhos diferentes — 3 e 12 clientes — e cobra que a contagem de queries **não mude**. Roda
dentro do `pytest` que já existe: nenhum job novo, segundos a mais, nenhuma dependência nova
(`CaptureQueriesContext` é do Django).

A asserção é comparativa e não um teto numérico de propósito. Um número mágico envelhece a cada
refatoração legítima e vira ruído a ser atualizado sem pensar; a comparação se auto-calibra e
reprova exatamente a propriedade que interessa — custo independente do tamanho da base.

O k6 (`loadtests/`) passa a ter sessão por VU, cenário de leitura sobre os agregadores e cenário de
escrita sobre a conversão em projeto, com procedimento em `docs/runbooks/testes-de-carga.md`. É
rodado sob demanda, contra ambiente com volume de verdade e com os tetos de requisição elevados.

## Consequências

**O CI passa a reprovar N+1 antes de ele existir.** As três rotas que já eram N+1
(`/clients/overview/`, `/risk/`, `/health/`) foram corrigidas para carga em lote nesta entrega,
porque o teste as reprovou.

**`/analytics/` fica protegido no que importa.** Ele é o mais pesado em SQL de todos, mas laça sobre
`Service.Tier` e `Artifact.Kind` — enums de tamanho fixo, não dados. Passou de primeira, e a partir
de agora essa propriedade é cobrada: é a diferença entre "caro" e "cresce com a base".

**Latência continua sem gate automático.** Uma regressão que dobre o tempo de uma query sem mudar a
contagem passa pelo CI. Aceito: é o preço de não ter falha intermitente, e o k6 do runbook é onde
esse eixo é medido. Se algum dia houver runner dedicado, a decisão merece revisão.

**Contagem de query não é tempo.** Uma query que varre a tabela inteira conta 1. O gate cobre a
forma do acesso, não o plano de execução; índice ausente é outro assunto.

**A avaliação em lote duplicou um caminho.** `risk.assess_project` e `health.assess_project_health`
continuam existindo para o detalhe de um projeto, ao lado de `assess_projects`/
`assess_projects_health`. Duas formas de calcular a mesma coisa podem divergir, então um teste
compara as duas item a item — sem ele, um agrupamento errado por `project_id` mostraria a saúde do
projeto vizinho e nenhum orçamento de query perceberia.

**Rodar k6 exige preparar o ambiente.** Sem elevar `USER_RATE`, mede-se o throttle. Isso é
manual e está no runbook, com o aviso em destaque — mesma natureza dos alertas da FDD 020, que
também moram fora do código.
