# FDD 006 — Agentes por área, previsão de atrasos e avaliação da IA

## Jornada

Nas telas de Comercial, Projetos e Indicadores, o usuário (conforme seu papel) tem um agente de IA
da sua área para perguntar sobre pipeline, entrega ou finanças. A resposta é sempre para revisão
humana e pode ser avaliada com 👍/👎. Na entrega, o projeto passa a mostrar uma previsão de término
e o atraso previsto pelo ritmo atual.

## Regras

- Cada agente só é acessível aos papéis definidos (Comercial: admin/vendas; Entrega: admin/entrega;
  Financeiro: admin); fora disso → 403. Admin sempre acessa.
- Depende de `AI_ENABLED`; desligado → 503. Respeita o limite diário de uso de IA (429).
- O contexto de cada agente só lê os dados da sua área (anti-vazamento); nada é executado sozinho.
- Cada resposta é auditada (`AiInteraction`) e pode receber uma avaliação (só o dono avalia).
- A previsão de atraso é heurística explicável (ritmo atual), sem ML; ausente quando não há progresso.

## Aceite

Um usuário pergunta ao agente da sua área e recebe resposta com o id da interação; avalia com 👍/👎;
o projeto exibe a previsão de término quando há progresso.

## Regressão crítica

Papel sem acesso recebe 403; IA desligada retorna 503; só o dono avalia sua interação; métricas são
restritas a admin.
