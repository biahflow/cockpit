# FDD 041 — O estado de engenharia que o Pulse não sabia dizer

> GitHub Issue [#41](https://github.com/biahflow/pulse/issues/41), workstream **M1.4**.
> Superfície: `INTERFACE_CHANGE` — aprovada no [DAP GH-41 r1](../design/dap-gh41-r1/README.md),
> revisão 1, visual e copy, em 27/08/2026. Browser: `BROWSER_REQUIRED`; a evidência de runtime está
> em `browser-desktop.png` e `browser-mobile.png` no mesmo diretório do DAP.
> Decisão de contrato: **[ADR 0046](../adr/0046-a-projecao-de-engenharia-e-somente-leitura-e-idempotente-por-entrega.md)**.
> Merge de PR ≠ Done operacional.

## Jornada

A [FDD 040](040-provisionamento-de-issue-github.md) ligou o Pulse ao GitHub num sentido só: o
planejamento de negócio decide que um item exige engenharia, o backend provisiona a Issue, e o
Pulse guarda `repository`, `github_issue_number`, URL e `correlation_id`. Dali em diante o Pulse
fica em silêncio. Ele sabe **que** existe trabalho de engenharia e não sabe nada sobre **como ele
está**.

Quem opera a entrega convive com isso trocando de ferramenta: abre o GitHub, procura a Issue,
procura o PR, olha o CI, volta. A resposta que ele traz de lá não fica registrada em lugar nenhum,
não tem carimbo de quando foi olhada, e some no minuto seguinte.

O recorte entrega a projeção somente-leitura desse estado dentro do detalhe do projeto, alimentada
por webhook e reconciliada por job. **O GitHub continua sendo a fonte da verdade de engenharia**
(ADR 0040); o Pulse projeta e referencia.

## A regra que o pacote de design existe para decidir

**Estado obsoleto nunca se apresenta com a cor do estado observado.**

Quando a projeção envelhece, todo selo cai para `.state--off` e a linha de proveniência vira o dado
principal — "observado há 3 h", e não "CI verde". Um selo verde que na verdade é de anteontem é
pior que nenhum selo: ele afirma com confiança algo que o Pulse não sabe mais.

O âmbar **troca de lugar** em vez de aparecer: sai dos selos e vai para a proveniência, para
continuar querendo dizer uma coisa só na tela inteira. Nenhum matiz novo entra.

O custo está assumido: ao cair para o neutro, o painel deixa de responder "o CI passou?" num relance
justamente quando alguém tem pressa. A troca é deliberada — o Pulse prefere dizer "não sei mais" a
arriscar afirmar algo que o GitHub já desmentiu.

## Regras

- A projeção pendura no `EngineeringHandoff` (`OneToOneField`, `related_name="projection"`), não no
  `Project`. Um projeto tem **0..N** referências, e por isso o painel é lista e não cartão.
- **Somente leitura, por decisão.** `GithubProjectionViewSet` é `ReadOnlyModelViewSet`: `POST`,
  `PATCH` e `DELETE` respondem 405. Comando sobre o GitHub é contrato próprio (ADR 0046, D1).
- **Idempotência em dois níveis.** `X-GitHub-Delivery` é único (`GithubDelivery`) e a reentrega é
  no-op com 200; um evento cujo `source_updated_at` seja **anterior** ao persistido é descartado e
  logado. Registrar a entrega e aplicar o evento acontecem na mesma transação.
- **`POST /api/v1/github/webhook/`**: sem sessão, assinado por HMAC-SHA256 do **corpo cru**
  (`X-Hub-Signature-256`), teto próprio (`github_webhook`). Sem `GITHUB_WEBHOOK_SECRET` configurado
  o endpoint **recusa** (503, fail closed — ADR 0018); assinatura inválida é 401; entrega sem
  identidade é 400; evento desconhecido é **200 "ignorado"**, sempre.
- Eventos tratados: `issues`, `pull_request`, `check_suite`, `check_run`, `status`.
- **Só um evento que observou o estado da Issue cria projeção.** `pull_request` e os de CI sabem do
  PR e do CI e não sabem se a Issue está aberta; criar a linha a partir deles carimbaria o default
  do modelo como se fosse observação. Quem cria o que falta sem webhook é a reconciliação, que lê.
- **SHA novo apaga o CI do SHA velho.** Sem isso o painel mostraria o verde da revisão anterior ao
  lado do endereço da nova — um selo certo sobre a coisa errada.
- **Um `check_run` isolado não promove o conjunto a verde.** Um job que passou não diz nada sobre os
  outros doze; um que reprovou, ou que ainda roda, já basta para o conjunto não estar verde. Quem
  afirma "tudo passou" é o `check_suite`, que é o evento agregado.
- **Reconciliação** (`manage.py reconcile_github_projections`, job `github_projection` a cada
  `SCHEDULER_GITHUB_RECONCILE_EVERY_MINUTES`): relê o que passou do limiar de obsolescência e cria a
  projeção dos handoffs `provisioned` que ainda não têm uma. Reusa `GithubIssuesApi`. Sem
  `GITHUB_TOKEN` não toca em projeção nenhuma — erro de configuração não se disfarça de incidente do
  fornecedor.
- **O backend decide o que é obsoleto.** `GITHUB_PROJECTION_STALE_AFTER_SECONDS` é o único lugar do
  limiar; `is_stale`, `age_seconds` e `last_error_age_seconds` chegam calculados à tela.
- **Erro nunca apaga a projeção anterior.** Os três — `unavailable` (rede/5xx), `forbidden`
  (401/403) e `missing` (404) — carimbam `last_error_kind`/`last_error_at` e deixam o último estado
  conhecido inteiro. Numa projeção que ainda não existe, a falha **não cria linha**.
- **Vendas não alcança o recurso** (`return False` de `RolePermission`), e o painel continua na
  tela dela com a copy invariante. Entrega vê pelo `ProjectScopedMixin` (`handoff__project`);
  handoff arquivado tira a projeção da listagem.
- **Nada de segredo em tela, log ou mensagem de erro** (NFR-004): o Estado 4 fala de credencial e
  não ecoa token, escopo concedido nem resposta da API.
- Zero LLM neste fluxo, como na FDD 040.

## Contrato

Rotas aditivas em `/api/v1/`. Nada foi removido nem alterado.

| Rota | Quem |
| --- | --- |
| `GET /github-projections/` (+ `?project=`) e `GET /github-projections/{id}/` | delivery no próprio projeto / admin |
| `POST /github/webhook/` | GitHub, por assinatura — sem sessão |

## Aceite

Um projeto expõe suas 0..N referências com estado e proveniência. A mesma entrega duas vezes é
no-op e responde 200. Uma entrega atrasada com SHA velho não derruba o SHA atual. Assinatura
inválida é 4xx; sem segredo, o endpoint recusa; evento desconhecido é 200. Os três erros são
distinguíveis e nenhum apaga a projeção. Com `is_stale`, todo selo é `.state--off` e a proveniência
é `.state--2`. Vendas toma 403 e vê a mesma copy com ou sem referência. A reconciliação recupera o
evento perdido.

## Regressão crítica

`backend/tests/regression/test_webhook_do_github_e_idempotente.py` entra pelo HTTP e trava os dois
níveis: a mesma entrega duas vezes não reaplica nada, e a entrega atrasada não derruba o `head`
atual. Os oito estados da tela estão em
`frontend/src/components/EngineeringPanel.test.tsx`, e as asserções olham a `className` da pastilha
— um selo verde que na verdade é de anteontem passa em qualquer teste que só olhe texto.

## Decisões que este recorte tomou sobre questões que o DAP deixou em aberto

O DAP registrou o que não se resolve num quadro. Duas delas precisavam de resposta para o código
existir, e a resposta está aqui — não no quadro:

- **Ordem das referências na lista.** `-source_updated_at`, depois `-observed_at`, depois `-id`:
  mais recentemente mexida no GitHub primeiro. O carimbo é o **de lá**, o mesmo que decide ordem
  entre entregas — usar o nosso faria a lista se reordenar por causa de uma releitura.
- **Quantos minutos é "obsoleto".** 30 min por padrão, com a reconciliação a cada 10. É valor de
  operação e muda por variável de ambiente, sem redeploy.

E duas continuam em aberto, agora com o motivo escrito:

- **Referência a PR sem Issue.** O modelo ancora na Issue; um PR avulso não tem onde morar, e
  continua não tendo.
- **Review/readiness.** Não há selo de revisão: derivar "aprovado" de review do GitHub é decisão de
  contrato, e ela não foi tomada.

## Fora deste recorte

- **Comando sobre o GitHub** — reabrir Issue, re-disparar CI, reprovisionar. Desenhado no DAP como
  reservado; exige contrato de comando separadamente autorizado.
- Vincular/desvincular referência pela interface.
- Outbox, RabbitMQ e o envelope de evento versionado da ADR 0037 — este recorte adota a **regra** de
  idempotência daquela ADR, não a sua infraestrutura.
- Purga de `GithubDelivery`: a tabela só cresce, e a política de retenção é trabalho próprio.
- O painel em qualquer tela que não `/projetos/:id`; superfície equivalente no One; tema escuro.
- Criar o webhook no GitHub e qualquer mudança de infraestrutura.
