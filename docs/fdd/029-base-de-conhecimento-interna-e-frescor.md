# FDD 029 — Base de conhecimento interna e disciplina de frescor

> **Status: proposta.** Nada aqui está implementado. O KB **voltado ao cliente já existe**,
> maduro, no repositório `biahflow-portal-cliente` — esta FDD não o reespecifica.

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
