# FDD 029 — Base de conhecimento interna e disciplina de frescor

> **Status: entregue** (07/08/2026). O KB **voltado ao cliente já existia**, maduro, no repositório
> `biahflow-portal-cliente` — esta FDD não o reespecifica. A bifurcação de arquitetura que ela
> deixou pendente foi decidida e virou a **ADR 0022**; a regra de citar-ou-lacuna virou a
> **ADR 0023**. Ver "O que a construção decidiu", no fim: a rodada 5 de homologação achou **dois
> defeitos**, e um deles matou o desenho original do roteamento.

## Jornada

"Assistente de base de conhecimento" parece um produto novo e, aqui, não é: é o **corpus
sobre o qual os agentes que já existem se apoiam**. A pergunta certa não é "construo um
chatbot de wiki?", é "em qual corpus curado meus agentes se ancoram?".

E a resposta começa com uma inversão que a exploração apurou. O KB **cliente-facing está
pronto**: o portal do cliente tem ingestão de documento, pedaços ancorados em página com
embeddings, citação no formato "Documento: Contrato — página 3", conector de Drive por
projeto, varredura de arquivo antes do parser, retenção com prazo, busca no projeto, memória
de conversa com avaliação, prompt versionado com registro de digests e avaliações
adversariais contra um modelo hostil. As duas exigências obrigatórias de um KB com IA —
**resposta ancorada com citação** e **"não sei" honesto** — são a razão de ser daquele repo.

O que **não existe é o KB interno**. Aqui não há embedding, recuperação nem indexação de
conteúdo: `ai.build_project_context` passa os documentos **só como nomes**, deliberadamente,
por anti-vazamento. O assistente interno não consegue ler o conteúdo de um documento. E o
corpus da metodologia — PRD, ADRs, FDDs, RFCs, runbooks — vive no repositório, fora do
alcance dos agentes de Comercial, Entrega e Financeiro.

O objetivo por trás disso, dito com honestidade, não é "o serviço parar de depender de
pessoas" — isso é inalcançável, e persegui-lo leva ao lugar errado. É fazer a dependência
virar **explícita, limitada e recuperável**. O teste não é "um documento substitui essa
pessoa"; é "se ela sumir por duas semanas, o serviço **degrada ou para**?". Degradar é
aceitável. Parar é o que se caça.

## Regras

- **Escopo é a lista curta do que para o serviço**, não a wiki inteira. Documentar tudo é
  desperdício; o backlog real é o inventário do que só uma pessoa sabe fazer.
- **Uma bifurcação de arquitetura, que é ADR e não detalhe de FDD.** Ou se constrói
  recuperação aqui — duplicando um pipeline já resolvido, em outra pilha, e com outro
  fornecedor de embedding, já que este repositório fala com um provedor e o portal com
  outro — ou se **reusa o índice do portal** como serviço, com corpus interno isolado. A
  segunda parece mais barata e mais correta, mas atravessa a fronteira dos dois
  repositórios. Esta FDD **registra a decisão como pendente** em vez de escolher sem uso
  real.
- **Não é plataforma de wiki: é recuperação onde os documentos já moram.** O corpus já existe
  e já é disciplinado. Recuperação sobre documento é commodity; o diferencial é o
  conhecimento curado e a integração com o fluxo.
- **Capturar no fluxo, nunca como ritual separado.** Documentar compete com o trabalho e
  sempre perde. O conserto é o artefato do trabalho **ser** a documentação — o que a cultura
  de ADR já faz na engenharia, e o que `Meeting` (com decisões e próximos passos) e os
  `Artifact` de discovery e assessment já fazem no domínio. A IA rascunha a primeira versão,
  o humano edita: é o "a IA acelera, não decide" do PRD apontado para dentro.
- **Três tipos de conhecimento, três meias-vidas, três governanças.** *Decisões* (por quê) são
  ADRs: quase imutáveis — não se editam, se **substituem** com um novo que referencia o
  antigo, datado e append-only. *Procedimentos* (como) são runbooks: apodrecem rápido porque
  a realidade muda, e pedem o laço de frescor mais apertado. *Referência* (o quê) apodrece em
  silêncio, e o melhor conserto é **não documentar o que dá para derivar do sistema**.
- **Uma fonte única por fato**, tudo o mais liga para ela — regra que o `CLAUDE.md` já
  pratica. No instante em que o mesmo fato mora em dois lugares, eles divergem, e um KB que
  se contradiz é pior que KB nenhum.
- **Frescor precisa de dono e gatilho, senão não acontece.** Dono **por área** de
  conhecimento, não por documento — "todo mundo mantém" é ninguém mantém. Duas formas de
  gatilho: carimbo de "verificado em" que faz o conteúdo velho aflorar para revisão, ou
  revisão presa a evento. O veículo já existe: o `ScheduledJobRun` do trabalho periódico
  (FDD 023, ADR 0015) foi construído exatamente para "o que venceu" ser uma tabela testável
  em vez de um crontab que ninguém verifica.
- **Testar o conhecimento, não confiar nele.** Um runbook que só o autor seguiu é hipótese,
  não procedimento. O precedente é o exercício de restauração, que roda porque conhecimento
  não exercitado não é conhecimento. E o melhor teste de KB é **onboarding real**: se alguém
  novo entrega a partir dos documentos, eles funcionam; onde essa pessoa empaca é exatamente
  a lacuna tácita a preencher. Usar eventos reais — entrada de alguém, passagem de bastão,
  férias — como auditoria, em vez de auditoria encenada.
- **O modo de falha específico da IA sobre KB.** Um humano que não sabe diz "não tenho
  certeza". Um modelo sobre corpus incompleto **inventa resposta plausível**, e sobre corpus
  velho lava informação desatualizada com fluência confiante — que é **pior que não ter KB**.
  Por isso resposta ancorada com citação da fonte e "não sei" honesto não são refinamento:
  são a condição de existir.

## Aceite

O admin abre o inventário de conhecimento e vê, por área, quem é o dono e quando cada peça
foi verificada pela última vez; o que passou do prazo aparece destacado, e o trabalho
periódico avisa o dono sem ninguém lembrar. Ao perguntar ao agente de Entrega sobre o
procedimento de uma fase da metodologia, a resposta vem **com a citação do documento** de
onde saiu, e um "não encontrei isso no material" quando não houver base — nunca uma resposta
plausível sem fonte. Uma pessoa nova consegue conduzir a primeira entrega seguindo o
material, e os pontos onde ela trava viram itens do inventário.

## Regressão crítica

O agente não responde sobre a metodologia sem citar a fonte, e declara a lacuna quando não
há base — resposta sem citação é defeito, não estilo. Conteúdo vencido aparece como vencido,
e não é servido como corrente. O corpus interno nunca é servido a um contexto de cliente, e
o anti-vazamento existente segue valendo: documento de um projeto não alcança outro. E o
inventário não regride para "todos são donos": peça sem dono é peça em falta.

## Fora deste recorte

**Plataforma de wiki.** O que falta é recuperação, não um lugar novo para escrever.

**KB por cliente.** Já entregue no `biahflow-portal-cliente`; esta FDD aponta para lá em vez
de reespecificar.

**E a parte que não é KB — e é a maior.** A forma mais independente de pessoa que o
conhecimento assume não é a wiki que alguém precisa lembrar de consultar: é **método
codificado no produto**. A biblioteca de blueprints (FDD 026), o template de kickoff (FDD
008) e a jornada em fases (FDD 011) são metodologia executável, que dispara sozinha na
conversão. Wiki serve ao conhecimento que exige julgamento humano; o resto vira template,
blueprint e fase. Quanto mais do método vira sistema, menos ele depende de quem executa — e
esse trilho já está andando em outras FDDs.

**A trave: não sobre-governar.** O instinto de quem gosta de sistema puxa para um processo
de conhecimento maior do que o conhecimento vale, e processo maior que o problema é o próprio
modo de falha. Uma consultoria enxuta precisa de ADR para o que não quer redecidir, runbook
testado para o que para o serviço, e método no produto para o resto. O KB pequeno em que o
time confia ganha, toda vez, do KB completo e abandonado.

## O que a construção decidiu

Seis pontos em que construir mudou o desenho, e dois deles só apareceram contra o modelo real.

**O limiar de similaridade não pode decidir se a citação é obrigatória — foi a maior mudança.** O
desenho previa um piso: acima dele, material injetado e citação exigida; abaixo, o agente responde
como sempre. A rodada 5 mediu as três classes de pergunta contra o corpus real e as faixas **se
sobrepõem** — metodologia 51–69%, operacional 47–56%, ruído 22–49%. Não é imprecisão de medida: o
corpus *descreve o domínio*, então perguntar "o que está atrasado?" de fato se parece com o texto de
uma FDD sobre atraso. Com o piso planejado de 30%, uma resposta operacional correta seria
substituída por "não encontrei isso no material". Agora **o modelo declara o regime** (`FONTE: [K1]`
ou `FONTE: dados da área`), e o limiar só evita gastar token com material fora do assunto.

**A citação que o modelo dá vem na linha de declaração — e a primeira versão a descartava.** O
prompt manda terminar com `FONTE: [K1]`, e o `gpt-4o-mini` cita **só** ali. O código removia essa
linha antes de procurar marcador, então nada resolvia e a lacuna **substituía uma resposta certa**,
com os comandos exatos do runbook. Nenhum dublê acharia: ele citaria onde o teste mandasse.

**O corpus é um artefato gerado e commitado**, não leitura de `docs/` em tempo de execução. O
runtime não tem `docs/` — o `Dockerfile` usa contexto `./backend` —, e mudar o contexto para a raiz
tornaria **inerte** o `backend/.dockerignore`, cujo propósito é manter documento real de cliente
fora da imagem que vai ao registry. O preço é a fricção de regerar, e ela é a mesma do
`openapi.yaml`.

**O fatiador precisou de duas guardas que a medição pediu.** Bloco de código com comentário `#`
virava seção fantasma titulada com uma linha de shell; e as seções "Regras" das FDDs são listas
**sem linha em branco entre os itens**, então a fronteira de parágrafo sozinha deixava blocos de
quase mil palavras. A fronteira passou a incluir o item de lista — quebrar *entre* regras preserva
cada uma inteira, e quebrar *dentro* seria pior que não quebrar: meia lista de regras lê como a
lista completa.

**`review_interval_days` tem três significados, e colapsá-los quebra o laço.** Nulo **herda da
área**; zero significa **não vence**, que é o valor certo para ADR (ela se substitui, não se
atualiza — cobrar revisão semestral da ADR 0001 é ruído, e ruído é o que faz o laço inteiro ser
ignorado); e um número é o prazo. Junto: `source_path` precisou de constraint **parcial**, senão
existiria uma única lacuna tácita no sistema inteiro — a segunda vez que o repositório precisa dessa
forma, depois de `Invoice.number`.

**O job não sai com erro.** Dívida editorial não é incidente, e transformar runbook vencido em
evento de Sentry ensina quem opera a silenciar o Sentry. É a diferença deliberada em relação ao
`backup_status`, que sai com código 1 porque ali o que falta é a cópia de segurança.

## Fora deste recorte — o que ficou nomeado

**Ingerir o conteúdo dos `Document` de projeto.** O corpus aqui é a **metodologia**, versionada e já
revisada. Trazer arquivo de cliente mexeria no anti-vazamento que hoje passa só nomes e exigiria
varredura e parser por formato — outra natureza de problema.

**Registro de digest de prompt e avaliação adversarial**, que o repositório vizinho tem. Vale, e é
FDD própria: `FONTE:` virou protocolo entre código e modelo, e mudá-lo sem mudar o parser quebraria
a citação em silêncio — que é precisamente o que um registro de digest pega.

**Índice ANN**, nomeado com o limiar (~50 mil trechos) na ADR 0022 em vez de omitido.

**Plataforma de wiki**, **KB por cliente** e **onboarding como auditoria** — os três já estavam
fora, e seguem.
