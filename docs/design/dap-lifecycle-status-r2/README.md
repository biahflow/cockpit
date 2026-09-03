# Design Approval Package — "cliente" para de nomear a entidade

Classificação: `INTERFACE_CHANGE` · `BROWSER_REQUIRED`
Revisão: **2**
Status: **Proposed**
Data: 2026-09-02
Produzido por: harness (Claude Code), sob `docs/engineering-os/workflows/design-approval.md`

> Este artefato é evidência para um gate humano. A revisão 1 continua valendo integralmente; esta
> revisão só estende o alcance dela às telas que a r1 declarou fora de escopo.

## Por que existe um gate — e por que ele é uma r2, e não um conserto

A r1 (28/08) decidiu que a entidade se chama **Conta** e que "Cliente" é o rótulo de **um** dos
estados dela (`lifecycle_status = active`). Ela renomeou o menu, a rota `/contas`, o formulário e
as pastilhas.

E declarou, com todas as letras, o que ficava de fora:

> **As outras telas.** `ClientDetailPage`, `LeadsPage`, `CommercialPage` e o Dashboard citam
> "cliente" em copy que **não** é rótulo de estado. Elas não estão neste pacote e **não mudam**.

Portanto isto não é corrigir um esquecimento: é **rever uma decisão de escopo** tomada
deliberadamente. Daí a revisão.

O que mudou desde então, e motiva revê-la: um usuário abriu o detalhe de uma conta marcada
*"Prospect — ainda não fechou"* sob um cabeçalho que dizia **"Dados do cliente"** e perguntou se
ela já era cliente. A ambiguidade que a r1 identificou na listagem existe igual no detalhe — e a
r1 a resolveu em metade do produto.

## Inventário — oito strings, quatro telas

| Onde | Linha | Hoje |
| --- | --- | --- |
| `AccountDetailPage` | 455 | título do diálogo: "Arquivar cliente" |
| `AccountDetailPage` | 456 | "O cliente **X** e os contatos dele saem das listagens ativas…" |
| `AccountDetailPage` | 461 | "Dados cadastrais e contatos do cliente." |
| `AccountDetailPage` | 462 | botão "Arquivar cliente" |
| `AccountDetailPage` | 643 | seção "Dados do cliente" |
| `CommercialPage` | 172 | campo "Cliente" no formulário de oportunidade |
| `FinanceiroPage` | 148 | campo "Cliente" no formulário de fatura |
| `DocumentsPage` | 14, 129 | alvo do vínculo: "Cliente" |

## Dois achados que reforçam a mudança

**O campo do Comercial nomeia errado por definição.** Uma oportunidade se abre para quem
**ainda não fechou** — é o que `prospect` significa. O formulário de "Nova oportunidade" chama de
"Cliente" exatamente a conta que, na maioria das vezes, ainda não é.

**O campo do Financeiro promete um recorte que não existe.** O rótulo diz "Cliente", e o `<select>`
oferece **todas** as contas, sem filtrar por `lifecycle_status`. Dá para emitir fatura contra um
prospect com o campo afirmando que ele é cliente. Trocar o rótulo não conserta o recorte — ele não
está errado, faturar antes de fechar acontece —, mas para de afirmar o que não se verificou.

## Decisão A — a palavra

- **A1 — "Conta" nas oito.** O rótulo passa a nomear a entidade, e "Cliente" fica reservado ao
  estado.
- **A2 — "Conta" só no detalhe da conta**, mantendo "Cliente" no Comercial e no Financeiro, onde
  quem lê pensa em cliente.
- **A3 — manter tudo**, e a regra do §4 vale só para a pastilha.

**Recomendação: A1.** A A2 é o pior dos dois mundos e é o estado de hoje: o mesmo registro chamado
de duas coisas a dois cliques de distância, que é precisamente o que o mapa de linguagem existe
para impedir. A A3 mantém a pergunta que motivou a revisão.

O preço da A1 está declarado: "Conta" é palavra de sistema, e o time comercial fala "cliente" no
dia a dia. A defesa é que a r1 já pagou esse preço no menu e na listagem — as pessoas já entram por
"Contas". Deixar o miolo em outro vocabulário é que fica estranho.

## O que **não** muda, e é importante dizer

Duas ocorrências de "Cliente" estão **certas** e não devem ser tocadas por quem for "terminar o
serviço" depois:

- `components/AccountLifecycle.tsx` — `active: "Cliente"` é o **rótulo do estado**, e é o ponto
  inteiro da r1. Trocá-lo desfaria a decisão.
- `pages/ProjectDetailPage.tsx` — `partyLabel` (`Fornecedor` · `Cliente`) responde *de quem é a
  pendência*, um eixo diferente: ali "Conta" seria errado.

Também não muda a prosa em que "cliente" nomeia a **pessoa ou a empresa** como parte da relação —
"o cliente declarou insatisfação", "enviar ao cliente". A regra é sobre nomear o **registro**.

## Estados incluídos

| Superfície | Estado | No pacote |
| --- | --- | --- |
| Detalhe da conta | cabeçalho, seção e diálogo de arquivar | sim |
| Comercial | formulário de nova oportunidade | sim |
| Financeiro | formulário de nova fatura | sim |
| Documentos | alvo do vínculo, no formulário e na listagem | sim |
| Pastilha de `lifecycle_status` | — | **não muda** (r1) |
| `Fornecedor`/`Cliente` de pendência | — | **não muda** |

## Proveniência visual

Nenhum valor visual novo, nenhuma primitiva nova, nenhuma mudança de forma ou de posição. É troca
de texto em rótulos que já existem.

## Fora da aprovação

- Filtrar o `<select>` do Financeiro por `lifecycle_status` — é comportamento, não copy, e precisa
  de decisão própria.
- Renomear a rota `/contas/:id/…` ou qualquer chave de payload.
- Tocar na pastilha de estado ou no eixo `Fornecedor`/`Cliente`.
- Copy de Leads e do Dashboard, que a r1 também citou e que não entraram neste inventário.
