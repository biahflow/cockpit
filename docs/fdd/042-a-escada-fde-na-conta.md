# FDD 042 — A escada FDE na conta

> GitHub Issue [#42](https://github.com/biahflow/pulse/issues/42).
> Superfície: `INTERFACE_CHANGE`. Browser: `BROWSER_REQUIRED` — gate de design em
> [DAP GH-42 r1](../design/dap-gh42-r1/README.md), aprovado (revisão 1, visual e copy) em
> 27/08/2026, com evidência de runtime nas capturas `browser-*.png` do mesmo diretório.
> Decisão de modelagem em [ADR 0047](../adr/0047-a-escada-fde-e-eixo-da-conta-e-a-jornada-da-entrega-fica-onde-esta.md).

## Jornada

Uma conta caminha pela escada da metodologia FDE —
`Discover → Prioritize → [ Technical Feasibility ] → Prove → Scale → Optimize` — e **cada degrau é
uma venda própria na mesma conta** (`docs/metodologia-fde.md:50`). A tela do cliente passa a
responder "onde esta conta está, de quem é a bola e há quanto tempo isso não anda", e a visão geral
passa a responder a mesma coisa para a carteira inteira, numa linha por conta.

## Os três eixos, e o que **não** muda

| Eixo | Granularidade | Onde vive |
| --- | --- | --- |
| `PipelineStage` | uma `Opportunity` | Comercial |
| `JourneyPhase`/`ProjectPhase` (FDD 011) | um `Project` | `JourneySection`, na tela do projeto |
| **escada FDE** (esta FDD) | uma **conta** (`Client`) | `/clientes/:id` e `/` |

A jornada de entrega da FDD 011 **fica exatamente como está**: não é renomeada, não é reordenada,
não é refatorada. Ela aparece **aninhada** dentro do degrau ativo da escada, recuada e em
superfície sutil, e continua sendo operada na tela do projeto. `Welcome` não é `Discover` — Welcome
é o onboarding de um projeto já vendido, Discover é o diagnóstico anterior à existência dele.

## Regras

- **Os seis degraus são doutrina, não template.** `FdeRung` é `TextChoices`, na ordem e na grafia
  de `metodologia-fde.md:26`, incluindo os colchetes de `[ Technical Feasibility ]`. Não há tela de
  configuração e não deve haver (ADR 0047).
- **Materialização automática e idempotente.** Ao criar um `Client` (`post_save`), os seis degraus
  nascem `not_sold`. Contas anteriores a esta fatia são materializadas de forma **preguiçosa** na
  primeira leitura de `/account-rungs/?client=`. A materialização **não emite evento** — ela não é
  uma decisão sobre a conta, e seis linhas de "não vendido" afogariam a primeira transição de
  verdade.
- **A escrita entra por uma porta só.** `POST /api/v1/account-rungs/{id}/transition/` com `status`
  e, opcionalmente, `note`, `waiting_on`, `blocker`, `skip_reason`, `opportunity` e `project`. O
  recurso é `ReadOnlyModelViewSet`: não se cria degrau, não se apaga e **não se arquiva** — fica
  fora do `ArchiveModelViewSet` de propósito.
- **As recusas moram no domínio** (`apps/core/ladder.py`), não na view, pela regra que a FDD 033
  registra: só o Feasibility aceita `skipped`; pular exige o motivo escrito; bloquear exige dizer o
  quê; transição para o mesmo estado é recusada com 409, porque um evento que não diz o que mudou é
  um histórico que ninguém lê.
- **O histórico é append-only.** `AccountRungEvent` grava `from_status → to_status`, carimbo e
  autor. Nunca é editado, apagado nem arquivado; cancelar e replanejar viram evento, e as datas em
  que o degrau esteve ativo permanecem.
- **Um degrau pode compartilhar a venda com o anterior.** A FK para `Opportunity` é anulável e
  **não é unique** — *Discover* e *Prioritize* saindo da mesma "Discovery Sprint" é o caso comum.
- **Nada equipara `PR merged` a `DONE`.** Um degrau fecha por decisão de gate registrada. Não há
  transição automática, e a regressão
  `backend/tests/regression/test_pr_merged_nao_conclui_degrau.py` é a forma executável disso.
- **"Parado há N dias" é aritmética do backend**, sobre o último evento, com limiar em
  `ACCOUNT_RUNG_STALE_AFTER_DAYS` (padrão **14**). Fica fora do SPA porque duas definições de
  "parado" divergem em silêncio, e é esta que roteia a atenção de quem varre a carteira. Sem token
  de modelo — a Issue #42 proíbe gastar modelo nisto.
- **O bloco da visão geral** lista só as contas com degrau em aberto (`active`, `blocked`,
  `awaiting_gate`), ordenadas por tempo parado decrescente, com teto de **8** linhas
  (`ladder.ACCOUNT_LADDER_LIMIT`). Não é uma listagem: é uma varredura, e uma lista completa
  empurraria a linha que importa para baixo da dobra.

## Autorização e escopo

`resource = "account_rung"`. **Vendas e admin escrevem** — ao lado de `opportunity` e pelo mesmo
motivo: cada degrau é uma venda. **Entrega é somente leitura e escopada.**

O escopo da Entrega é por participação em projeto, e a fonte é `Project.objects.visible_to(user)`,
nunca reexpressa (RFC 0003, ADR 0010, FDD 018): a conta é visível quando tem ao menos um projeto
visível àquela pessoa.

**O que a Entrega vê é a *forma* da escada, e não o conteúdo comercial** — a questão que o DAP
deixou aberta e que a ADR 0047 fecha:

| Campo | Entrega |
| --- | --- |
| degrau, posição, estado | vê |
| `opportunity` / título da venda | **sempre nulo**, mesmo no degrau que ela alcança |
| `project`, datas, bloqueio, motivo do pulo, histórico | vê **só** nos degraus realizados por projeto de que participa |
| degrau realizado por projeto alheio | vem `no_access`, rotulado **"Sem acesso"**, sem projeto, sem datas e sem histórico |

## Interface

**A · `/clientes/:id`** — painel "Escada FDE" logo abaixo de "Saúde da relação". Os seis degraus
numa `<ol>` (a ordem é o significado), com o degrau ativo expandido, a jornada de entrega do
projeto correspondente aninhada e visivelmente subordinada, próximo gate, de quem é a bola e uma
gaveta de histórico por degrau (`<details>` nativo — teclado de graça). As quatro saídas do gate
aparecem como **texto**, não como botões: o gate se decide na tela do projeto, e desenhar aqui
quatro controles inertes seria defeito, não placeholder.

**B · `/`** — bloco compacto, uma linha por conta: a escada inteira em miniatura
(`.timeline--compact`, decorativa), nome, degrau, estado, dono e tempo parado. A linha inteira é um
link para a conta; não há controle nenhum.

**Onze estados**, cada um com rótulo escrito por extenso: concluído, ativo, não vendido, pulada,
bloqueado, aguardando decisão de gate, replanejado, vazio, carregando, sem acesso e erro de
carregamento. **"Pulada" e "não vendido" não podem parecer a mesma coisa** — as duas são neutras,
porque nenhuma é aviso, e o que as separa é *estrutura*: marcador sólido e trilho **contínuo** na
pulada (a conta passou por aqui e alguém decidiu), marcador oco e trilho **tracejado** no não
vendido (a escada não chegou aqui). Distinguir por cor exigiria matiz novo, que
`docs/design/pulse-design-system.md` proíbe.

Os cinco valores de quem-espera têm pele própria e são legíveis sem `title` e sem hover:
`biahflow` → `.state--0`, `client` → `.state--2`, `engineering` → **`.eng-ref`**, `external` →
`.state--off`, `human_gate` → **`.state--gate`**. `WorkItem.Party` tem dois valores e não serve:
não distingue engenharia de Biahflow, não tem lugar para dependência externa e não nomeia o Human
Gate.

## Aceite

Toda conta expõe os seis degraus com o estado atual. Mudar um degrau gera evento com carimbo e
autor, e nada é apagado. `skipped` e `not_sold` são visualmente distinguíveis, e `skipped` carrega
motivo, autor e carimbo. Feasibility é o único degrau que aceita `skipped`. Próximo gate visível e
bloqueio legível sem abrir nota. A Entrega vê a forma e não o conteúdo comercial. A visão geral
mostra as contas paradas primeiro.

## Regressão crítica

Materialização idempotente (não duplica na segunda leitura nem no segundo save da conta); pular
`Prove` responde **409**; pular `Feasibility` sem motivo responde 409; transição para o mesmo
estado responde 409 e **não** grava evento; Entrega recebe 403 em `transition` e 200 na leitura;
degrau de conta alheia não aparece para a Entrega; amarrar um degrau a projeto de outra conta
responde 403; e **provisionar uma GitHub Issue não move o degrau**
(`backend/tests/regression/test_pr_merged_nao_conclui_degrau.py`).

## Fora de escopo

Refatorar a `JourneySection` para consumir a `.timeline` (reserva declarada no DAP), a projeção da
escada no One, cobrança ou faturamento por degrau, notificação de Human Gate pendente além do
limiar, e qualquer transição automática de degrau.
