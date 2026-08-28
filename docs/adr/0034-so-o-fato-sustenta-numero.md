# ADR 0034 — Só o fato sustenta número

**Status:** aceita
**Data:** 20/08/2026
**Contexto:** FDD 039 (Discovery estruturado), ADR 0030 (o cockpit como sistema primário, e o
adiamento desta camada), ADR 0032 (só a declarada move número — a irmã desta), ADR 0033 (a
camada 5 não suspende sozinha), FDD 027 / ADR 0020 (o case como fotografia, e a ausência dita),
FDD 029 / ADR 0023 (citar ou declarar a lacuna), FDD 016 / ADR 0008 (artefatos da jornada)

## Contexto

A ADR 0030 adiou a camada de Discovery estruturado — *"Processes, Pain Points, Evidence, Business
Cases, Value Ledger, Opportunity Backlog só é modelada depois de Discoveries reais"* —, e a razão
declarada foi que materializar antes seria *"inventar um processo que ainda não aconteceu"*.

Ela também deixou, nas consequências, o teste que governa o desadiamento:

> cada bloco novo da camada FDE precisa provar que já estabilizou antes de virar modelo — o teste
> é existir no material como **regra pronta** (checklist, gate, escada), **não como ideia**.

Aplicado peça a peça contra `docs/metodologia-fde.md`, esse teste não devolve "sim" nem "não" para
o bloco: ele o **parte em dois**.

| Peça | O que existe no material | Passa |
| --- | --- | --- |
| P-S-D-T-E-R por etapa | `:75-79` — seis atributos nomeados, com a pergunta de cada um | **sim** |
| As cinco formas de evidência | `:81-84` — enum fechado | **sim** |
| FATO / HIPÓTESE / DESCONHECIDO | `:86` — enum fechado, com a regra de uso | **sim** |
| Custo do estado atual | `:87-88` — fórmula literal | **sim** |
| "Processes" como entidade | só `L1 — Process: fluxo ponta a ponta` (`:60`) | não |
| Pain Points | o termo **não aparece** no documento | não |
| Business Cases | uma menção (`:63`), sem estrutura | não |
| Value Ledger | **zero ocorrências** | não |
| Opportunity Backlog | só como pauta mensal (`:123`) | não |
| Next Best Opportunity, cockpit de reunião | existem **só** em `roadmap.md:531` | não |
| Opportunity Score | o gate de Discovery **cobra** (`:109`); a fórmula não existe | não |

O contador de Discoveries reais continua onde a ADR 0030 o encontrou. O que mudou não foi a
realidade da operação: foi termos aplicado o teste que aquela ADR escreveu e ainda não tinha
exercido.

## Decisão

**A ADR 0030 não é revogada. Ela é aplicada, peça a peça.** Entra o que passa no teste dela; o que
reprova segue nomeado e não feito, agora com o motivo escrito ao lado do nome — que é a diferença
entre backlog e lacuna.

E, para o que entra, a regra que dá nome a esta ADR: **só o fato sustenta número.**

- **`Evidencia.rotulo` é obrigatório e não tem default.** É o precedente literal do
  `Satisfacao.fonte` (ADR 0032), com o comentário que já está no modelo: *"justamente para ninguém
  escolher por omissão"*. Um default não é neutro — ele faz a casa escolher pelo silêncio de quem
  não escolheu, e o erro cai sempre para o mesmo lado, o de chamar de fato o que ninguém
  confirmou.
- **`desconhecido` é valor de primeira classe, não ausência.** Um Discovery que nomeia o que ainda
  não sabe está fazendo exatamente o que o método pede (`:97-98`: *"ainda não sei a melhor solução,
  mas sei exatamente quais perguntas precisamos responder"*). Tratá-lo como campo em branco
  apagaria a única saída honesta entre afirmar e omitir.
- **O custo do estado atual sai sempre, e carimbado.** `sustentado` quando existe evidência viva
  com `rotulo=fato` no processo; `hipotese` caso contrário. O número não é escondido de quem
  levantou — é a conta de trabalho da equipe.
- **Só o sustentado atravessa para a proposta.** Citar ao cliente um custo apoiado apenas em
  suposição é literalmente o que o material proíbe em `:86`.
- **Ausência é dita, nunca preenchida com zero.** Fator faltando manda a parcela para
  `nao_apurado`; ela não entra como `0`. "Não medimos o retrabalho" e "não há retrabalho" são
  conclusões opostas, e somar zero afirma a segunda.
- **O que a IA extrai nasce hipótese.** A extração da transcrição grava todo achado como
  `rotulo=hipotese`, `forma=entrevista`, e o prompt sequer menciona essas chaves — elas são
  impostas no coletor. Um modelo lendo transcrição produz **o que foi dito**, e "o que dizem" é uma
  das cinco formas de evidência, não prova. Promover a fato é ato de gente, pela mesma razão que a
  ADR 0032 recusou a IA gravar satisfação e a ADR 0033 manteve o registro na mão.

## Consequências

- O rótulo passa a governar comportamento, e não só a decorar a tela. É o que o distingue de um
  campo de categoria: `fato` muda o que a casa aceita afirmar para fora.
- **A lacuna é declarada, não silenciada.** Quando o custo não está sustentado, o contexto da
  proposta diz isso com todas as letras em vez de omitir o processo. Silenciar convidaria o modelo
  a preencher — foi o defeito que a rodada 5 de homologação achou na base de conhecimento (FDD 029,
  ADR 0023): diante de lacuna, o modelo completa.
- Uma segunda extração da mesma reunião é recusada com 409. `Decisao` podia repetir porque nasce em
  rascunho, um estado visível; `Processo` não tem rascunho, e um duplo clique dobraria o mapa de
  processos do cliente em silêncio.
- O mapa é do **cliente**, não do projeto — ele sobrevive à venda que o descobriu, porque a
  metodologia separa conta de oportunidade (`:50-53`). O custo é ancorar a fronteira de acesso no
  cliente à mão, como a `Satisfacao` já fazia, em vez de herdá-la do `ProjectScopedMixin`.
- Nada disto atravessa para o portal do cliente. É mais forte aqui que na satisfação: uma hipótese
  cruzando a fronteira seria a casa afirmando ao cliente, com autoridade de painel, o que ela mesma
  rotulou como ainda não sabido.
- **O Opportunity Score fica em aberto e incômodo.** O quality gate de Discovery já o cobra
  (`:109`) e o material nunca o definiu — hoje só se responde "sim" no braço. Esta ADR não o
  inventa; registra a pergunta.

## Alternativas consideradas

- **Modelar o bloco inteiro, inventando os campos que faltam** (Pain Point, Business Case, Value
  Ledger, Opportunity Backlog, Next Best Opportunity). Rejeitada pelo motivo da própria ADR 0030:
  seria inventar um processo que ainda não aconteceu, e desta vez com cinco entidades desenhadas
  sem um Discovery real para corrigi-las. O custo de errar não é escrever código à toa — é que uma
  entidade errada é preenchida por meses antes de alguém perceber, e aí os dados também estão
  errados.
- **Continuar adiando o bloco inteiro.** Rejeitada porque o teste da ADR 0030 é sobre o material,
  não sobre o calendário: P-S-D-T-E-R e o Evidence Log já estão no documento como regra fechada, e
  esperar não os deixa mais prontos. Manteria também a situação em que a IA grava prosa que ninguém
  filtra, e em que o gate pergunta por hipóteses rotuladas sem que exista onde rotulá-las.
- **`rotulo` com default `hipotese`.** Tentadora, porque parece o lado seguro. Rejeitada: o default
  seguro ainda é a casa decidindo por quem não decidiu, e apaga a diferença entre "achamos que é
  hipótese" e "ninguém classificou". Erro que se parece com preenchimento é pior que campo vazio,
  porque ninguém volta para conferir.
- **O modelo classificar o rótulo na extração.** Rejeitada pela ADR 0032/0033: seria a IA
  afirmando o que só a evidência sustenta. E a variante branda — pedir ao modelo e sobrescrever
  depois — é pior que ambas, porque deixa no prompt a aparência de que ele decide, e a primeira
  pessoa a "melhorar" o prompt reativa o caminho sem saber que existia uma regra.
- **Persistir o custo calculado no `Processo`.** Rejeitada: seria uma segunda verdade sobre o mesmo
  dado, e mudar o volume deixaria o número gravado dizendo o antigo. Diferente do `Case` (ADR
  0020), onde congelar é o ponto — lá o número descreve um instante encerrado; aqui descreve uma
  operação que ainda está de pé.

## Emenda (issue #67, fatia 4 — 28/08/2026) — os nomes das duas classes

Onde esta ADR diz `Processo` e `ProcessoEtapa`, os modelos hoje se chamam `Process` e `ProcessStep`
(ADR 0052), e `processos.custo_do_estado_atual` mora em `apps/core/process.py`. **Nenhuma das
decisões muda**: o custo continua derivado e não persistido, a segunda extração continua sendo 409,
o rótulo continua sem default e promover a fato continua sendo ato humano.

As tabelas seguem `core_processo` e `core_processoetapa`, e as rotas seguem `/processos/` e
`/processo-etapas/` — o renome da tabela é a Fase 6 e o da rota é a `/api/v2/`. `Evidencia` **não**
foi renomeada aqui: a Fase 3 já a dividiu em `Evidence` + `Finding` (FDD 045), e quem a remove é a
Fase 6, junto com o dual-write.
