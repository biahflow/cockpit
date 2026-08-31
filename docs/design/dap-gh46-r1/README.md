# Design Approval Package — GH-46 · Fase da decisão

Classificação: `INTERFACE_CHANGE` · `BROWSER_REQUIRED`
Revisão: **1**
Status: **Approved**
Data: 2026-08-31
Produzido por: Codex, sob `workflows/design-approval.md`

> Este artefato é evidência para um gate humano. Não é implementação e não deve ser copiado para
> o código da aplicação.

## Registro de aprovação

| Campo | Valor |
| --- | --- |
| O que foi aprovado | Decisões e limites da revisão 1 conforme `board.png`, incluindo compatibilidade histórica sem inferência |
| Aprovado por | Daniel Campos, via conversa com Codex |
| Data | 2026-08-31 |
| Revisão aprovada | 1 |
| Explicitamente **não** aprovado | inferência automática de fase; mudança de copy fora do formulário e dos cards de decisão; redesign da página |

## Artefato

| Arquivo | O que é |
| --- | --- |
| `board.html` | Renderização autocontida, sem build, toolchain ou rede. |
| `board.png` | Captura congelada da revisão 1. É a ela que a aprovação se refere. |

SHA-256 de `board.png`: `5124abb383ef04e833447b684c6cba2306ee983b55394170d3230e8e718712d9`.

## Superfícies e estados incluídos

| Superfície | Estado | No pacote |
| --- | --- | --- |
| Formulário de nova decisão | fases disponíveis | sim — campo obrigatório sem valor presumido |
| Decisão rascunho criada sem fase por integração | pendente de vínculo | sim — publicação bloqueada até escolha humana |
| Decisão publicada | fase vinculada | sim — rótulo somente leitura |
| Jornada sem fases | vazio | sim — criação/publicação indisponível com orientação |
| Carregando e erro | existentes | preservados; nenhuma nova linguagem visual |
| Não autorizado | existente | preservado; nenhuma mudança de permissão |

## Proveniência dos valores visuais

O pacote reutiliza campos, botões, estados, cores e espaçamentos já presentes em
`ProjectDetailPage`; não introduz token nem primitiva. A única decisão visual nova é a posição e o
comportamento do seletor “Fase da jornada”. Design system consultado em 2026-08-31:
`docs/design/pulse-design-system.md`, ADRs 0024, 0025, 0026 e 0041, e
`frontend/src/index.css`.

## Entregue vs. reservado

| Elemento | Esta entrega | Reservado para | Vira real quando |
| --- | --- | --- | --- |
| Seleção explícita de fase ao criar decisão manual | entrega | — | — |
| Vínculo de rascunho legado/integrado antes de publicar | entrega | — | — |
| Exibição da fase na decisão publicada | entrega | — | — |
| Inferência por data, fase ativa ou texto | não entrega | — | não será usada neste contrato |
| Reorganização geral do painel de decisões | não entrega | issue própria | contrato próprio aprovado |

## Decisões que este pacote carrega

1. **A fase é escolha humana.** O formulário não preseleciona a fase ativa nem deriva por data.
2. **Rascunho pode existir sem fase; publicação não.** Isso preserva ingestão por integrações sem
   publicar um vínculo inventado.
3. **O vínculo pode ser corrigido antes da publicação.** O rascunho mostra o seletor no próprio
   card e mantém “Publicar” desabilitado até uma fase ser escolhida.
4. **A fase publicada fica visível.** O card publicado mostra o nome da fase como metadado.
5. **Sem jornada, não há decisão publicável.** A interface explica que é preciso configurar as
   fases antes de criar ou publicar.

## Questões em aberto

- Nenhuma. A compatibilidade para registros históricos sem fase — lacuna explícita, sem
  inferência — foi aprovada junto desta revisão e formalizada na ADR 0057.

## Notas para quem implementa

- O valor enviado e exposto pelo contrato será a identidade já presente em `journey.phases[].id`.
- Validar no backend que a fase pertence ao mesmo projeto da decisão.
- Runtime deve provar 390, 768 e 1280 px, teclado, foco e axe.
