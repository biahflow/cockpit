# ADR 0051 — A projeção ganha versão e hora, e quem carimba é quem muda o estado

**Status:** aceita
**Data:** 2026-08-28
**Fase:** transversal — integração com o One (portal do cliente)
**Completa:** ADR 0003 (e as cinco emendas dela), ADR 0027

## Contexto

O `build_snapshot` (`backend/apps/core/portal.py`) é a projeção que o One consome por
`GET /api/v1/portal/projects/{pk}/snapshot/`. Ele nunca disse **quando** aquele estado foi
observado nem **qual versão** dele é: o snapshot chega, o outro lado aplica, e pronto.

Isso funciona enquanto as leituras são sequenciais. Deixa de funcionar no primeiro par de
requisições concorrentes, ou no primeiro backfill manual disparado enquanto um webhook do mesmo
projeto está em voo: dois snapshots do mesmo projeto chegam fora de ordem, o mais antigo chega
por último, e o read model do cliente volta para um estado que já não existe. Nada acusa — os dois
lados fizeram exatamente o que deveriam.

**O consumidor implementou primeiro.** A ADR 0076 do repo `one` ("O snapshot que precisava de
versão e hora", aceita em 26/08/2026) já está de pé: o `sync_snapshot` de lá recusa snapshot com
`projection_version` menor que o persistido, resolve empate por `observed_at`, e loga
`projection.stale_rejected`. **O leitor existe e o produtor nunca existiu** — o campo chegava
ausente, e a ADR 0076 declara que versão ausente de um lado não recusa nada, então a proteção
inteira estava desligada por falta da outra metade.

## Decisão

**`Project` ganha `projection_version` (inteiro monotônico, `default=0`) e
`projection_observed_at` (`DateTimeField` nulo), e quem os carimba é quem muda o estado.**

O nome `observed_at` não é novo aqui: `GithubDeliveryProjection.observed_at` é a projeção inversa
(GitHub → Pulse) e usa a palavra com o mesmo sentido — *quando este lado confirmou aquele estado*,
que não é `updated_at` nem a hora do envio.

### Por que o carimbo não pode ficar na leitura

O One **puxa**. A rota do snapshot é um `GET`, e é por isso que o lugar óbvio é o errado:

- **incrementar a cada projeção emitida seria escrita no banco a cada leitura.** Duas requisições
  concorrentes produziriam versões iguais ou fora de ordem — precisamente o sinal que o comparador
  do outro lado usa para decidir o que é obsoleto. A proteção passaria a produzir o defeito que
  existe para impedir;
- **`observed_at = now()` no momento do build seria a hora do envio.** É o colapso que a ADR 0076
  nomeia como o erro a evitar: a hora da observação e a hora da entrega são coisas diferentes, e
  igualá-las torna o desempate por hora inútil exatamente quando ele é necessário.

### O ponto de estrangulamento

`portal.emit(event, object_type, project_id)` é por onde passam **todos** os onze receivers
`_emit_*` de `signals.py`. O carimbo mora lá, e três decisões vão junto:

1. **`F("projection_version") + 1`, resolvido no banco.** Ler-e-somar em Python perderia
   incremento sob escrita simultânea. Não havia precedente de `F() + 1` neste repositório; este é
   o primeiro, e a razão está escrita no lugar em que ele aparece.
2. **Antes da guarda de flag.** A projeção mudou de fato mesmo com o webhook desligado pela tela
   (ADR 0018). Carimbar só quando o aviso sai faria o One, ao religar a integração, receber estado
   novo com versão velha e **recusá-lo**.
3. **`.update()` não dispara signal**, então carimbar o `Project` de dentro do `post_save` do
   próprio `Project` não recursa. É a primeira pergunta de quem revisa, e ela merece resposta no
   código e não na memória de quem escreveu.

`_emit_project_deleted` (o único `post_delete` do repositório) chega ao `emit` com a pk de um
projeto que já não existe: o filtro casa zero linhas e o `update` é inócuo. Não é caso especial.

### Sem backfill

Projeto que não mudou desde o deploy fica em `version=0` / `observed_at=None`. Um `RunPython`
teria de escolher uma hora para "quando este lado observou", e a única resposta disponível seria a
hora da migração — que é a hora do deploy. A ADR 0076 declara que versão ausente de um lado não
recusa nada, então a janela atravessa sem quebrar o comparador, e o primeiro salvamento carimba.

## Consequências

- **Duas leituras seguidas devolvem a mesma versão, e isso é o caso comum deste desenho.** A
  projeção não mudou; não há o que versionar. O `sync_snapshot` do outro lado trata empate
  aplicando o snapshot, porque é idempotente por substituição. Há teste que reprova se alguém
  "consertar" isso movendo o incremento para o `build_snapshot`.
- **O limite é herdado, e é o mesmo do webhook: a cobertura do carimbo é a cobertura dos
  receivers.** `bulk_update`, `queryset.update()`, shell e migração de dados **não** disparam
  `post_save` e portanto **não** avançam a versão. O pior caso é perder a proteção contra
  obsolescência para aquele projeto até o próximo salvamento normal — nunca perder o dado, que
  continua saindo inteiro no snapshot seguinte.
- **A rota do snapshot ganhou `select_related`.** O bloco novo lê `engagement` e a conta dele;
  sem isso cada leitura somaria consultas a uma projeção que já é montada por requisição.
- **Contrato `/api/v1/` preservado:** as duas chaves são aditivas, e o consumidor que não as lê
  continua funcionando como sempre.
