# FDD 005 — Reuniões e pendências do projeto

## Jornada

No detalhe do projeto, a equipe de entrega registra reuniões (título, data e links de
gravação/transcrição) e pendências (decisões/aprovações, com responsável fornecedor ou cliente) ao
lado de marcos e tarefas. Cada mudança repropaga ao portal do cliente pelo webhook já existente, e
o snapshot do projeto passa a trazer reuniões, pendências e um resumo de resultados.

## Regras

- Reunião e pendência pertencem a um projeto e usam soft delete (arquivamento), como os demais itens.
- Pendência tem `status` (aberta/resolvida) e `party` (fornecedor/cliente); ao resolver, grava
  `resolved_at` automaticamente (padrão do `WorkItem`).
- Gerenciamento é de entrega/admin (vendas não acessa), coerente com marcos/tarefas.
- Resultados enviados ao portal são apenas KPIs derivados — nunca dado comercial (ADR 0003/0005).
- Documentos no snapshot trazem tipo (extensão) e autor; o Cronograma traz o `party` de cada marco.

## Aceite

Criar reunião e pendência no projeto reflete no snapshot do portal; resolver uma pendência a marca
como resolvida e atualiza o portal.

## Regressão crítica

Nenhum valor comercial vai para o portal; `resolved_at` é setado ao resolver e limpo ao reabrir; a
emissão de webhook dispara para reuniões e pendências.
