# ADR 0047 — A escada FDE é eixo da conta, e a jornada de entrega fica onde está

**Status:** aceita
**Data:** 27/08/2026
**Fase:** transversal — domínio, API e front-end do portal operacional
**Consome:** ADR 0010 (escopo de entrega) · ADR 0026 (primitivas) · ADR 0030 (a metodologia no repositório) · ADR 0041 (design system)
**Não revisa:** ADR 0003 · FDD 011 — a jornada de entrega **não muda**
**Gate de design:** [DAP GH-42 r1](../design/dap-gh42-r1/README.md), aprovado em 27/08/2026

## Contexto

`docs/metodologia-fde.md` descreve a escada da casa — `DISCOVER → PRIORITIZE →
[ TECHNICAL FEASIBILITY ] → PROVE → SCALE → OPTIMIZE` — e diz, na linha 50, onde ela vive:

> Comercialmente, cada degrau é uma **Opportunity separada na mesma conta** (Account ≠
> Opportunity).

O sistema não tinha esse eixo. Tinha dois outros, e os dois respondem a outra pergunta:

| Eixo | Vocabulário | Granularidade |
| --- | --- | --- |
| `PipelineStage` | Prospecção → … → Ganho/Perdido | uma `Opportunity` |
| `JourneyPhase`/`ProjectPhase` (FDD 011) | Welcome → … → Optimize | um `Project` |
| **escada FDE** | Discover → … → Optimize | uma **conta** (`Client`) |

O nome das duas últimas colide quase inteiro — as duas terminam em `Scale` e `Optimize` —, e é
justamente essa colisão que torna o defeito fácil de cometer e difícil de ver: **renomear as fases
da FDD 011 para os nomes da metodologia e declarar a escada implementada.** Ficaria plausível na
tela e errado no domínio. `Welcome` não é `Discover`: Welcome é o onboarding de um projeto **já
vendido**, e Discover é diagnóstico anterior à existência do projeto — é uma venda própria
("Discovery Sprint"), que pode nem chegar a virar projeto.

A consequência prática da ausência: a pergunta "onde esta conta está na escada?" não tinha
resposta em lugar nenhum do produto. A resposta que existia era por projeto, e uma conta com três
projetos tinha três respostas e nenhuma sobre ela mesma.

## Decisão

**A escada FDE é um eixo novo, no nível da conta, e a jornada de entrega da FDD 011 fica
exatamente como está.** As duas se relacionam por **aninhamento**, não por concorrência: a escada
da conta *contém* as jornadas de entrega dos projetos que a realizam, e por isso o degrau ativo é
o único expandido e a jornada aparece dentro dele — referenciada, nunca redesenhada.

Cinco decisões seguem daí, e cada uma contraria um reflexo:

**1. Doutrina, não template configurável.** `JourneyPhase` é vocabulário editável pelo admin, e o
reflexo é copiar o padrão. Mas os seis degraus são a metodologia da casa, e uma tabela editável
criaria uma segunda escada que diverge do documento em silêncio — configurabilidade que ninguém
pediu é a camada especulativa que os princípios de arquitetura recusam. São `TextChoices`
(`FdeRung`), com os rótulos na **grafia do documento**, incluindo os colchetes de
`[ Technical Feasibility ]`, que são a forma como a condicionalidade está escrita lá.

**2. Um degrau pode compartilhar a venda com o anterior.** A FK para `Opportunity` é anulável e
**não é unique**. O caso real mais comum é *Discover* e *Prioritize* saírem da mesma "Discovery
Sprint"; uma constraint 1:1 recusaria a operação que a casa de fato tem.

**3. O histórico é append-only, e cancelar não apaga.** `AccountRungEvent` registra
`from_status → to_status` com carimbo e autor, e **não estende `TimestampedModel`** — um
`archived_at` aqui ofereceria justamente a operação que o modelo existe para negar. Replanejar um
degrau vira mais uma linha, e as datas em que ele esteve ativo permanecem.

**4. Nenhuma regra equipara `PR merged` a `DONE`.** Um degrau fecha por decisão de gate registrada
(`metodologia-fde.md:42-48`), e a Issue [#42](https://github.com/biahflow/pulse/issues/42) exclui
explicitamente *"automatic phase transitions driven only by PR merge"*. Não existe caminho
automático para `done`: `ladder.transition` é a porta única, o serializer é inteiramente
read-only, e há regressão que provisiona uma GitHub Issue e afirma que o degrau **não** se moveu.
Estado de engenharia é projeção de outra fonte, e por isso ganhou pele própria (`.eng-ref`),
deliberadamente fora da família `.state`.

**5. A Entrega vê a forma da escada e não o conteúdo comercial.** O DAP deixou esta em aberto;
aqui ela se fecha. Quem é da Entrega enxerga os seis degraus e seus estados — inclusive os
realizados por projetos de que não participa, marcados **"Sem acesso"** —, e não enxerga
oportunidade, título de venda, datas nem histórico desses degraus. O recorte de quais projetos ela
alcança sai de `Project.objects.visible_to`, a única expressão da regra (ADR 0010, RFC 0003), e
não é reescrito: a conta é visível quando tem ao menos um projeto visível.

## Consequências

Nascem `AccountRung` e `AccountRungEvent` (migração aditiva), o módulo de domínio
`apps/core/ladder.py` — onde moram as recusas, e não nas views, pela regra que a FDD 033 registra
— e a rota `/api/v1/account-rungs/`, que é **somente leitura** com uma única action de escrita
(`transition/`). Vendas e admin escrevem, ao lado de `opportunity` e pelo mesmo motivo: cada
degrau é uma venda. Os seis degraus são materializados na criação da conta e, para as contas
anteriores, de forma preguiçosa na primeira leitura — o molde do `ProjectPhaseViewSet`.

No front-end nasce a primitiva `.timeline` (e suas sete variantes, mais `--nested` e
`--compact`), que o design system não tinha e que a `JourneySection` vinha suprindo com literal
escrito à mão. **As variantes mudam forma e continuidade do trilho; a tinta continua vindo de
`.state--*`** — trilho contínuo diz que a conta passou por aqui, tracejado diz que a escada não
chegou, e é o que separa *pulada* de *não vendido* sem inventar matiz. Entram também
`.state--gate` (a única pastilha sólida do produto) e `.eng-ref`.

O que esta decisão **não** autoriza, e fica nomeado para não ser confundido com pendência
esquecida: refatorar a `JourneySection` para consumir a `.timeline` (reserva declarada no DAP), a
projeção da escada no One, cobrança por degrau, notificação de Human Gate pendente e qualquer
transição automática de degrau.

## Alternativas consideradas

**Renomear as fases da FDD 011 para o vocabulário da metodologia.** Rejeitada, e é a alternativa
que este ADR existe para recusar: sobrescreveria o eixo do projeto com o eixo da conta, apagaria o
histórico de fase de todo projeto em andamento e deixaria a pergunta "onde esta conta está?" sem
resposta com a aparência de tê-la.

**Modelar os degraus como `JourneyPhase` de um segundo template configurável.** Rejeitada: os
degraus não são vocabulário, são a metodologia; e a tela de configuração que viria junto seria uma
oferta para divergir de `metodologia-fde.md`.

**Uma coluna `position` no degrau, em vez da ordem por expressão.** Rejeitada: a posição não é dado
da conta, é doutrina — uma coluna que a repete é a segunda cópia dela, e é onde a deriva entra.

**Um painel único "Histórico da escada" ao pé da tela.** Rejeitada no DAP e mantida aqui: separa a
transição do degrau a que se refere, e a pergunta que se faz olhando um degrau é sempre "o que
aconteceu *aqui*".
