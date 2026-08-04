# FDD 001 — CRM e pipeline comercial

## Jornada

Vendas cria ou seleciona cliente e contato, registra uma oportunidade com título, escopo, valor estimado, responsável e previsão de fechamento, e a movimenta pelo pipeline.

## Regras

- Etapas abertas podem ser renomeadas e reordenadas por administradores.
- Há exatamente uma etapa terminal `Ganho` e uma `Perdido`.
- Apenas Vendas e Administração editam oportunidades.

## Aceite

O pipeline mostra oportunidades por etapa e cada registro mantém cliente, valor, responsável e previsão.

## Regressão crítica

Vendas pode alterar o CRM, mas não criar projetos diretamente; Entrega consulta apenas oportunidades ganhas e não as edita.
