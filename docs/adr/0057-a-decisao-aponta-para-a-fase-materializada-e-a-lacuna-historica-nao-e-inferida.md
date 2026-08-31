# ADR 0057 — A decisão aponta para a fase materializada, e a lacuna histórica não é inferida

**Status:** aceita
**Data:** 2026-08-31
**Depende de:** ADR 0003 (webhook para o portal) · ADR 0027 (contrato fechado do snapshot) · ADR
0051 (versão e hora da projeção) · FDD 032
**Implementada por:** issue #46 · DAP GH-46 r1, aprovado em 31/08/2026

## Contexto

O snapshot já envia a jornada como `journey.phases[]`, com a identidade da fase materializada no
campo `id`. As decisões publicadas, porém, levavam título, racional, autoria e data sem dizer em
qual fase ocorreram. O One só conseguiria colocá-las na timeline inferindo por janela de datas ou
comparando nomes — isto é, criando estado que a fonte da verdade nunca afirmou.

Há duas fases distintas no domínio. `JourneyPhase` é o template global e editável; `ProjectPhase`
é a instância daquela fase naquele projeto, com status e história próprios. Uma decisão do projeto
acontece na segunda. Apontar para o template faria decisões de projetos diferentes compartilharem
uma identidade que não representa a passagem concreta de nenhum deles.

Também há decisões publicadas anteriores a este campo. Não existe backfill determinístico: a data
pode cair entre fases, o nome pode ter mudado e escolher a fase ativa hoje reescreveria o passado.

## Decisão

`Decisao` ganha `project_phase`, uma FK anulável para `ProjectPhase`, com `SET_NULL`. O campo é
anulável por dois motivos delimitados: rascunhos extraídos por IA ainda esperam revisão humana, e
registros históricos não recebem fase inventada.

A fronteira de publicação fecha a invariante para fatos novos:

- `status=published` exige `project_phase`;
- a fase precisa pertencer ao mesmo `project` da decisão;
- a interface não preseleciona fase ativa nem deriva por data ou texto;
- rascunho sem fase continua possível, mas “Publicar” fica bloqueado até a escolha humana.

Cada item de `decisions[]` no snapshot ganha:

```json
{"phase_ref": 123}
```

O valor é exatamente `Decisao.project_phase_id`, a mesma identidade que o próprio envelope já
envia em `journey.phases[].id`. Para o legado sem vínculo, a chave existe com `null`: a lacuna é
declarada em vez de mascarada por heurística.

`projection_version` **não é versão de schema**. É o contador monotônico do estado observado de
um projeto (ADR 0051). Salvar o vínculo passa pelo receiver `_emit_decisao`, que chama
`portal.emit`; esse ponto carimba o projeto e incrementa a versão antes de emitir. Portanto a
entrada de `phase_ref` e cada correção humana já produzem uma versão nova sem constante global,
backfill de contador ou incremento na leitura.

## Consequências

- O One recasa decisão e fase por duas identidades afirmadas pelo Pulse, sem originar estado.
- Novas decisões publicadas sempre têm fase; integrações de IA continuam podendo propor
  rascunhos incompletos com segurança.
- O legado permanece visivelmente incompleto até revisão humana. Isto é dívida operacional
  explícita, não dado perdido nem dado fabricado.
- Remover excepcionalmente uma `ProjectPhase` não apaga a decisão: `SET_NULL` preserva o fato e
  volta a declarar a lacuna.
- O contrato `/api/v1/` é aditivo: `project_phase` entra na entidade e `phase_ref` no snapshot.

## Alternativas consideradas

- **Inferir pela janela de `decided_on`.** Recusada: intervalos são ambíguos e uma inferência no
  consumidor viola a fonte da verdade.
- **Preencher com a fase ativa na migração ou no formulário.** Recusada: “ativa agora” não prova
  “fase da decisão”, e um default invisível transforma ausência de escolha em fato.
- **Apontar para `JourneyPhase`.** Recusada: é identidade do template, não da passagem do projeto.
- **Usar nome ou slug no `phase_ref`.** Acrescentaria uma segunda identidade e política de renome
  quando a pk necessária já atravessa o mesmo envelope.
- **Tornar a coluna `NOT NULL` com backfill.** Exigiria escolher uma heurística ou impedir o deploy
  até uma correção manual completa; nenhuma das duas melhora a veracidade do dado histórico.
