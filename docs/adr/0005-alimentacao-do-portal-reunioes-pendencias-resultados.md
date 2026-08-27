# ADR 0005 — Alimentação do portal: reuniões, pendências e resultados

**Status:** aceita

## Contexto

O portal do cliente (repo `portal_cliente`) tem telas de Reuniões, Pendências e Resultados que o
Biahflow ainda não alimentava, além de campos faltando em Documentos e do "lado" (fornecedor/cliente)
no Cronograma. O Biahflow é a fonte da verdade (ADR 0003) e não deve expor dado comercial.

## Decisão

O Biahflow ganha os modelos `Meeting` (registro manual, com links de gravação/transcrição) e
`Pendencia` (aberta/resolvida, com `party` fornecedor/cliente), e um campo `party` no `WorkItem`
(alimenta o "lado" do Cronograma). O `build_snapshot` (`portal.py`) passa a incluir `meetings`,
`pendencias`, um bloco `resultados` **apenas com KPIs derivados** (conclusão %, marcos, atrasos,
status — nada de `actual_value`/`cost`/margem) e, em `documents`, `type` (extensão) e `author`
(`uploaded_by`). Os webhooks emitem os novos `object_type` `meeting` e `pendencia` no padrão do
ADR 0003 (assinado, best-effort). Nenhuma mudança é comercial e o contrato `/api/v1/` é preservado
(tudo aditivo).

## Consequências

O portal passa a refletir reuniões, pendências e resultados em quase tempo real, sem duplicar
digitação. O repo `portal_cliente` precisa tratar os novos `object_type` do webhook e os novos
blocos do snapshot — trabalho separado. Resultados seguem seguros por construção (só derivados). O
portal permanece read-only: pendências são resolvidas no Biahflow.
