# FDD 002 — Conversão em projeto

## Jornada

Ao marcar uma oportunidade como ganha, Vendas confirma um formulário pré-preenchido com nome, responsável, início e fim do projeto.

## Regras

- Uma oportunidade gera no máximo um projeto.
- A criação do projeto e o vínculo com a oportunidade são atômicos.
- Entrega visualiza o contexto comercial do projeto, mas gerencia a execução.

## Aceite

O projeto criado preserva cliente e oportunidade de origem e aparece no painel operacional.

## Regressão crítica

Conversão por pessoa sem permissão, com cliente diferente, datas inválidas ou conflito de persistência não cria projeto parcial.
