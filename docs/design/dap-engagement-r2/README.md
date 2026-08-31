# Design Approval Package — origem contratual do Engagement

Classificação: `INTERFACE_CHANGE` · `BROWSER_REQUIRED`
Revisão: **2**
Status: **Approved**
Data: 2026-08-31
Produzido por: Codex, sob `docs/engineering-os/workflows/design-approval.md`

> Este artefato é evidência para um gate humano. Não é implementação e não deve ser copiado para
> o código da aplicação. A revisão 1 continua sendo a aprovação da seção; esta revisão decide
> somente como o instrumento assinado entra na criação de um `Engagement`.

## Registro de aprovação

| Campo | Valor |
| --- | --- |
| O que foi aprovado | Visual e copy da seleção condicional do instrumento de origem |
| Aprovado por | Daniel Campos, via conversa com Codex |
| Data | 2026-08-31 |
| Revisão aprovada | r2 |
| Explicitamente não aprovado | Superfície de remediação em lote; criação/upload/assinatura do acordo dentro do formulário; mudança visual da lista |

## Artefato

| Arquivo | O que é |
| --- | --- |
| `board.html` | Renderização auto-contida; abre sem build, toolchain ou rede |
| `board-desktop.png` | Captura congelada da decisão principal em viewport desktop |
| `board-states-desktop.png` | Captura congelada dos estados de pré-requisito e da seção |
| `board-mobile.png` | Captura congelada em viewport mobile |

## Decisão proposta

O formulário mantém o `Modelo comercial` como primeiro discriminador e mostra um único campo
condicional logo abaixo:

- `paid` → **Oportunidade ganha de origem**;
- `design_partner` → **Design Partner Agreement assinado**.

Os selects só oferecem instrumentos elegíveis da mesma Account. Se não houver opção elegível, o
campo explica o pré-requisito e o envio fica desabilitado. O formulário não cria oportunidade,
faz upload nem solicita assinatura: esses fluxos continuam nas superfícies que já os possuem.

O instrumento aparece somente na criação. Na edição ele é leitura contextual, não um campo para
trocar a origem histórica. Engagements legados continuam válidos com `needs_review`; a remediação
humana permanece no admin/API e está fora desta aprovação.

## Estados incluídos

| Superfície | Estado | No pacote |
| --- | --- | --- |
| Criação paga | oportunidade ganha disponível | sim |
| Criação Design Partner | acordo assinado disponível | sim |
| Criação | nenhum instrumento elegível | sim |
| Seção | erro de carregamento | sim |
| Seção | carregamento | sim |
| Seção | não autorizado para escrita | sim, preserva a leitura da revisão 1 |
| Seção | vazia | sim, sem mudança em relação à revisão 1 |

## Proveniência visual

Nenhum valor visual novo. `panel`, `field`, `form-label`, `form-grid`, `btn`, `alert--error`,
`empty-state`, `state` e os tokens de cor, tipografia, raio e sombra são cópias das fundações em
`frontend/src/index.css`, já aprovadas e consumidas pela revisão 1. O campo condicional usa o
mesmo `<select class="field">` dos campos `Modelo comercial`, `Status` e `Patrocinador`.

## Entregue versus reservado

| Elemento | Esta revisão | Reservado para | Condição |
| --- | --- | --- | --- |
| Seleção do instrumento elegível | entrega | — | — |
| Mensagem quando não há instrumento | entrega | — | — |
| Upload/assinatura no próprio formulário | não desenha | trabalho futuro | contrato específico e novo DAP |
| Remediação em lote dos legados | não desenha | trabalho futuro | fluxo operacional definido |

## Fora da aprovação

- Alterar a posição, os selos ou as ações da lista aprovada na revisão 1.
- Expor `needs_review` ao One ou à equipe de Entrega.
- Inferir ou criar contratos retroativamente.
- Definir o catálogo comercial pendente A2 do Language Map.
- Permitir que uma oportunidade não ganha ou um documento sem assinatura seja escolhido.

## Notas para implementação

- O vínculo deve pertencer à mesma Account do Engagement.
- `design_partner` não cria nem exige `CommercialOpportunity`.
- Trocar o modelo comercial limpa a seleção incompatível antes do envio.
- O botão permanece desabilitado enquanto não houver instrumento válido; o backend repete todas
  as invariantes porque a interface não é fronteira de confiança.
- Ordem de foco: nome, modelo comercial, instrumento, status, patrocinador, datas, textos, ação.
