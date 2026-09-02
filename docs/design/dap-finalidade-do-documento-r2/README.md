# Design Approval Package — a finalidade classifica o documento

Classificação: `INTERFACE_CHANGE` · `BROWSER_REQUIRED`
Revisão: **2**
Status: **Approved**
Data: 2026-09-02

## Registro de aprovação

| Campo | Valor |
| --- | --- |
| O que foi aprovado | Presença condicional das opções e exibição da finalidade na listagem de `/documentos` |
| Aprovado por | Daniel Campos, nesta sessão |
| Data | 2026-09-02 |
| Revisão aprovada | r2 |
| Decisões | **A1-r2** (campo sempre visível, opções que abrem mandato só no vínculo com conta) · **B1** (pastilha neutra na linha, e "Documento comum" sem pastilha) |
| Explicitamente não aprovado | Filtrar ou buscar por finalidade (reservado, C1); editar a finalidade depois do envio; valores novos no enum; qualquer outra mudança no formulário ou na listagem |

**A A1-r2 revoga a A1 da r1**, e o motivo fica registrado para não parecer inconsistência: a A1 era
certa quando o campo tinha um valor só. O que exigia âncora na conta nunca foi *o campo*, era
**abrir mandato** — e amarrar a condição às opções, e não ao campo, é a mesma regra aplicada no
lugar certo.
Produzido por: harness (Claude Code), sob `docs/engineering-os/workflows/design-approval.md`

> Este artefato é evidência para um gate humano. A revisão 1 continua sendo a aprovação do campo;
> esta revisão decide o que muda quando ele deixa de ter um valor só.

## Por que existe um gate — e por que ele revê a r1

A r1 aprovou o campo "Finalidade" com **um** valor, e a decisão **A1** dizia: *só aparece quando o
vínculo é Conta*. A razão era boa e continua verdadeira para aquele valor — um Design Partner
Agreement só se ancora numa conta, e oferecer a opção nos outros vínculos seria mostrar o que a
API nega.

O primeiro uso mostrou o limite: **um NDA e um contrato comercial caíam em "Documento comum"**. Lê
estranho para um contrato assinado, e impede achar o NDA depois.

A decisão de 02/09 foi a terceira via entre as três que estavam na mesa:

> **Um campo só, que classifica — e a lista de quais valores disparam comportamento mora no
> código.**

Quem preenche responde **uma** pergunta ("que documento é este?"). O efeito é da casa. As recusadas:
um campo onde toda etiqueta vira gatilho (classificar um contrato para organizar a pasta abriria um
mandato), e dois campos (a mesma resposta pedida duas vezes).

Isso quebra a A1: o campo passa a ser **classificação de qualquer documento**, e escondê-lo fora do
vínculo com conta o esconderia justamente onde NDA e contrato vivem.

## Artefato

| Arquivo | O que é |
| --- | --- |
| `board.html` | Renderização auto-contida; abre sem build, toolchain ou rede |
| `board-desktop.png` | Captura congelada a 1280px |
| `board-mobile.png` | Captura congelada a 390px |

## Decisão A — quando o campo aparece (revê a A1 da r1)

- **A1-r2 — sempre visível**, com as opções que abrem mandato oferecidas **só** quando o vínculo é
  Conta.
- **A2-r2 — sempre visível com todas as opções**, deixando o servidor recusar.
- **A3-r2 — manter a A1**: campo só no vínculo com conta.

**Recomendação: A1-r2.** Ela preserva a razão da A1 no lugar certo. O que exigia conta nunca foi *o
campo*, era **abrir mandato** — `Engagement.clean()` compara a conta do acordo com a do mandato.
Amarrando a condição às opções em vez de ao campo, a regra da casa continua valendo ("a tela deixa
de mostrar o que a API recusaria") e o NDA passa a poder ser classificado onde ele de fato está.

A A2-r2 devolveria um 400 que a tela poderia ter evitado. A A3-r2 mantém o defeito que motivou a
revisão.

**Consequência registrada:** trocar o vínculo de Conta para Projeto com "Design Partner Agreement"
escolhido **limpa a escolha** — o mesmo cuidado que a r1 já tomava, agora pela opção e não pelo
campo inteiro.

## Decisão B — a finalidade aparece na listagem

Sem isto, classificar não resolve o problema que motivou a revisão: "achar o NDA depois".

- **B1 — pastilha `.state--off` ao lado do vínculo**, na linha do documento, só quando há
  finalidade.
- **B2 — texto simples junto do vínculo** ("Cliente A · NDA").
- **B3 — não exibir**; a finalidade fica só no formulário.

**Recomendação: B1.** A linha já usa `.state` para o status de assinatura, e a pastilha neutra
(`--off`) é o que a ADR 0026 reserva para o que **não é aviso** — finalidade não é estado nem
alerta, é etiqueta. "Documento comum" **não** ganha pastilha: o padrão não precisa se anunciar, e
uma pastilha em toda linha viraria ruído em vez de sinal.

## Decisão C — filtrar por finalidade

- **C1 — não nesta revisão.** A listagem já tem o par Ativos/Arquivados, e acrescentar um segundo
  eixo de filtro pede decidir como os dois se combinam.
- **C2 — pastilhas de filtro por finalidade**, ao lado das duas existentes.

**Recomendação: C1.** Exibir já resolve "achar o NDA" numa lista do tamanho da de hoje. Filtro
entra quando a lista crescer o bastante para justificá-lo — e aí com decisão própria sobre a
combinação dos eixos. Fica **reservado**, não negado.

## Estados incluídos

| Superfície | Estado | No pacote |
| --- | --- | --- |
| Formulário | vínculo Conta, todas as opções | sim |
| Formulário | vínculo Oportunidade/Projeto, sem as que abrem mandato | sim |
| Formulário | troca de vínculo limpando escolha incompatível | sim |
| Listagem | linha com finalidade | sim |
| Listagem | linha sem finalidade (documento comum) | sim |
| Listagem | filtro por finalidade | **não** — reservado (C1) |

## Proveniência visual

Nenhum valor visual novo. `.state--off` e `.field` dentro de `.form-label` já são consumidos pela
mesma tela.

## Fora da aprovação

- Filtrar ou buscar por finalidade.
- Editar a finalidade depois do envio.
- Acrescentar valores ao enum — cada um precisa de consumidor e de decisão própria.
- Qualquer mudança no restante do formulário ou da listagem.
