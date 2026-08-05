# FDD 001 — CRM e pipeline comercial

## Jornada

Vendas cria ou seleciona cliente e contato, registra uma oportunidade com título, escopo, valor estimado, responsável e previsão de fechamento, e a movimenta pelo pipeline.

## Regras

- O cliente tem duas situações: **prospect** (ainda não fechou) e **ativo** (já fechou). Quem
  cadastra declara qual é — o default é prospect, porque um cadastro não deve alegar uma venda que
  não houve —, e a conversão de lead cria o cliente como prospect. Daí em diante o sistema deriva:
  ganhar uma oportunidade promove o cliente a ativo. **Rebaixar para prospect é recusado quando
  existe oportunidade ganha**: o que o sistema observou não se desfaz por digitação.
- Uma oportunidade pode ser aberta para qualquer cliente, prospect ou ativo — vender de novo para
  quem já é cliente é caso normal, e por isso o seletor do pipeline não filtra por situação.
- Etapas abertas podem ser renomeadas e reordenadas por administradores.
- Há exatamente uma etapa terminal `Ganho` e uma `Perdido`.
- Apenas Vendas e Administração editam oportunidades.

## Aceite

O pipeline mostra oportunidades por etapa e cada registro mantém cliente, valor, responsável e previsão.

## Regressão crítica

Vendas pode alterar o CRM, mas não criar projetos diretamente; Entrega consulta apenas oportunidades ganhas e não as edita.
