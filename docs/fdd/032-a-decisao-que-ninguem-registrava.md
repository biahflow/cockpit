# FDD 032 — A decisão que ninguém registrava

## Jornada

O portal do cliente tem, desde a Fase 1, uma tabela `decision` com modelo, RLS e `GRANT SELECT`.
Ela nunca teve uma linha. `DecisionRepository` tem corpo vazio, nenhum chamador, e `search.py` de
lá carrega o motivo por escrito:

> *"`Decision` tem modelo desde a Fase 1 e não é projetada em `build_dashboard`: um hit dela levaria
> a lugar nenhum. **Quando existir aba de decisões, entra aqui junto.**"*

A aba não existe porque **não há escritor** — e não há escritor porque o portal não origina status
(ADR 0006/0008 de lá; o `roadmap.md` daqui tem o CRUD interno de decisões **riscado**, com a razão).
Deste lado a decisão nunca teve entidade própria: ela está colapsada na `Pendencia`, cujo docstring
diz literalmente *"Pendência/decisão do projeto"* e cuja FDD 005 repete — *"pendências
(**decisões/aprovações**, com responsável fornecedor ou cliente)"*.

**Colapsar as duas custa três coisas, e a terceira é a que dói.** O estado de uma pendência é
`aberta/resolvida`, e o de uma decisão é `rascunho/publicada`. Uma pendência diz *de quem é a bola*
(`party`); uma decisão diz *quem decidiu*, que muitas vezes é alguém do cliente e não tem conta
aqui. E o valor de uma decisão está no **porquê** — que a `Pendencia` guarda em `description` e que
**não atravessa o snapshot**: ao cliente vai título e estado. Uma decisão sem o porquê é um título.

O porquê é justamente o que o cliente não consegue reconstituir sozinho, e é o que ele volta para
consultar meses depois: *por que escolhemos isto e não aquilo?* Hoje essa resposta mora numa
transcrição de reunião que ele não tem, ou na memória de quem estava na sala.

## O que esta fatia entrega

Uma entidade `Decisao` de projeto, com o porquê, a autoria e a proveniência; a extração dela a
partir da transcrição por IA, **em rascunho**; e a travessia para o portal, só do que foi publicado.

## Critérios de aceite

1. **O rascunho não atravessa.** Só `status=published` entra no snapshot. É esta linha que faz a
   extração por IA ser aceitável: nenhum palpite de modelo alcança a tela do cliente antes de uma
   pessoa publicar.
2. **A extração parte da transcrição, e recusa sem ela.** A action mora no `MeetingViewSet` — o
   insumo é a ata, e o precedente é o `discovery`, que já mora lá. Reunião sem transcrição responde
   400 antes de qualquer chamada ao provedor.
3. **Uma resposta inutilizável não grava nada.** Se o modelo não devolver uma lista legível, a
   resposta é 502 e zero linhas — nunca "gravei zero decisões" com 200, que é indistinguível de
   "a reunião não decidiu nada".
4. **O carimbo de publicação não se apaga.** Despublicar esconde a decisão do cliente e **mantém**
   `published_at`. A data em que uma decisão passou a valer é fato histórico, não estado corrente.
5. **Arquivar avisa o portal.** `archive()` é um `save()`, e o receiver não tem guarda de `created`:
   arquivar tira a decisão do snapshot, que é a mudança mais silenciosa das três.
6. **O racional atravessa, e isso está registrado.** É texto novo cruzando a fronteira, contra o
   corte que a `Pendencia` faz de propósito. Emenda na ADR 0003.

## Telemetria

`AiInteraction` com `feature="meeting_decisoes"` — a extração conta na cota diária de quem a pediu,
como as outras oito actions de IA. Não é `AUTOMATED_FEATURES`: parte de uma pessoa.

## Testes

- `test_decisoes_ia.py` — o parser (JSON limpo, prosa e cerca de markdown em volta, item malformado
  descartado, nenhuma lista, truncagem nas colunas), a recusa sem transcrição, o caminho feliz
  gravando rascunho com proveniência, o 502 sem escrita, e o RBAC.
- `test_portal.py` — publicada atravessa e rascunho não, arquivada some, e os três caminhos de
  emissão (criar, publicar, arquivar).
- `test_portal_entities.py` — vendas recusada, escopo de projeto, e o carimbo que não se move.
- `ProjectDetailPage.test.tsx` — o selo de rascunho e o botão de extração.

## Eval de IA

O prompt pede saída estruturada e diz, como o `discovery` diz, que é rascunho para revisão humana.
O caso adversarial que importa é o de **transcrição sem decisão**: o prompt manda devolver array
vazio em vez de inferir, e o parser trata a ausência de lista como falha em vez de silêncio.

## Fora deste recorte

- **A aba no portal do cliente.** É a fatia seguinte, no outro repositório, e nasce depois do
  escritor por regra escrita (`ROADMAP.md` de lá: *"painel só nasce depois do escritor"*).
- ~~**Decisão pendurada em fase.**~~ Entregue na emenda de 31/08/2026 abaixo. Marco e entregável
  continuam fora: são identidades diferentes e não foram pedidos pelo consumidor.

## Emenda (31/08/2026) — a decisão passa a dizer em qual fase aconteceu

A issue #46 e a ADR 0057 fecham a lacuna que este FDD deixou deliberadamente fora. `Decisao`
ganha a FK anulável `project_phase` para a fase materializada do mesmo projeto, e o snapshot leva
`phase_ref` com exatamente a pk que já aparece em `journey.phases[].id`.

A nulabilidade não enfraquece a publicação. Ela preserva dois estados honestos: rascunho de IA
ainda não revisado e registro histórico para o qual não existe backfill determinístico. A API
recusa `published` sem fase e recusa fase de outro projeto. A interface exige escolha explícita,
sem preselecionar a fase ativa, e deixa o botão de publicar inerte até o vínculo existir.

O legado publicado aparece com `phase_ref=null` até correção humana. Data, texto e fase atual não
são usados como heurística. Salvar o vínculo já passa por `_emit_decisao`; como `portal.emit` é o
ponto que carimba a projeção (ADR 0051), a correção incrementa `projection_version` antes do
webhook sem mover versão para `build_snapshot`.

Testes de contrato cobrem: identidade igual à da jornada, rascunho sem fase, publicação recusada
sem fase, recusa de fase alheia e lacuna histórica explícita. A superfície segue o DAP GH-46 r1,
aprovado em 31/08/2026.
