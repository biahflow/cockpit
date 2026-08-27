# ADR 0021 — Registro financeiro não arquiva: a exceção declarada ao soft delete da casa

**Status:** aceita
**Data:** 07/08/2026
**Contexto:** FDD 028 (contas a receber), RFC 0004 (cobrança relacional), FDD 025 (arquivar e
restaurar pela interface), ADR 0017 (retenção de dado pessoal arquivado), ADR 0020 (case como
fotografia)

## Contexto

O portal tem uma regra transversal e antiga: **arquiva-se, não se apaga**. Dezesseis modelos
estendem `TimestampedModel`, `ArchiveModelViewSet.perform_destroy` chama `archive()` em vez de
`delete()`, e o `AGENTS.md` a escreve como norma — "use exclusão lógica quando houver registros de
negócio". A FDD 025 fechou o ciclo dando botão, aba de arquivados e caminho de volta, e reservou a
palavra "Excluir" para os **dois** recursos que apagam de verdade (etapa de pipeline e fase da
jornada), porque um botão "Excluir" que arquiva ensina a pessoa errada a coisa errada.

A `Invoice` da FDD 028 é o primeiro registro do domínio que **não cabe em nenhuma das duas
categorias**. Fatura emitida não se apaga — óbvio — mas também **não se arquiva**. E é preciso dizer
por que, porque arquivar parece a resposta certa e é a que qualquer pessoa daria por reflexo.

**Arquivar um recebível é pior que apagá-lo.** As duas operações escondem a linha da tela; a
diferença é o que a pessoa acredita ter feito. Quem apaga sabe que destruiu. Quem arquiva acha que
guardou — e, no caso do recebível, o que aconteceu foi que o valor **saiu do total em aberto** sem
que ninguém tenha decidido perdoá-lo, cobrá-lo ou renegociá-lo. O número que alguém vai olhar para
decidir se contrata, se corta custo ou se aperta o caixa fica menor, e nada na tela diz por quê. É
a definição de recebível que estraga invisível, que a própria RFC 0004 nomeia como o modo de falha
mais caro deste assunto.

## Decisão

**A fatura emitida não é apagada nem arquivada. A saída é cancelar, e o registro sobrevive ao
próprio cancelamento** — inclusive com o número, que não é liberado.

A invariante é sustentada por **quatro camadas**, em ordem crescente de força, e cada uma existe
porque a anterior tem um furo:

1. **`InvoiceViewSet` é `ModelViewSet` puro.** Não herda `ArchiveModelViewSet`, não tem ação
   `unarchive`, e `perform_destroy` não chama `archive()`. Remove o caminho da API.
2. **`perform_destroy` recusa com 409 e nomeia a saída** — "já foi emitida e não se apaga.
   Cancele-a, se for o caso." É a camada que **explica**, no registro que a FDD 025 estabeleceu
   para `StateConflict`: 409 e não 400 porque o pedido está bem formado e a permissão existe; o
   que impede é o estado.
3. **Um `pre_delete` levanta `ProtectedError`** para tudo que não passa pela viewset: shell,
   migração de dados, um `queryset.delete()` em cascata escrito sem pensar na fatura. É
   `ProtectedError` de propósito, e não uma exceção nova — o `api_exception_handler` já a traduz
   para 409 desde a FDD 025, então até um caminho que escape da view responde com o status certo em
   vez de 500. É a mesma divisão de trabalho que a casa já mantém: a view diz o que fazer, a camada
   de baixo garante que não aconteça.
4. **`CheckConstraint(archived_at__isnull=True)`.** Custa uma linha e é a única que o Python não
   contorna: `Invoice.objects.update(archived_at=...)` passa por cima de qualquer guarda em
   `archive()`, e não passa por cima do banco.

A quarta camada tem um segundo propósito, que é o motivo de ela existir apesar das três anteriores:
**ela vale para código que ainda não foi escrito.** `ArchiveModelViewSet` é o reflexo de toda
viewset nova deste repositório. No dia em que alguém acrescentar um recurso financeiro e herdar dele
por hábito, o primeiro `DELETE` falha alto — em vez de esconder um recebível de uma lista, em
silêncio, e ninguém descobrir por um trimestre.

## Alternativas consideradas

**Sobrescrever `archive()` para levantar.** Rejeitada: é guarda em Python, e `update()` a ignora
inteira. É exatamente o "caminho que a gente combina não usar" que a ADR 0020 recusou ao tornar o
congelamento do case estrutural em vez de convencional.

**Uma base abstrata `TimestampedOnlyModel`, sem `archived_at`.** É a forma mais limpa a longo prazo
e foi **adiada, não descartada**: mexer numa classe base compartilhada por dezesseis modelos é
refatoração transversal, e este recorte não deve arrastá-la. A `CheckConstraint` compra a mesma
garantia por uma linha, e a FDD 028 pede `TimestampedModel` explicitamente pelos carimbos.

**Tratar cancelamento como arquivamento** (`archived_at` preenchido no cancelamento). Rejeitada
porque confunde duas perguntas diferentes: "esta cobrança deixou de valer" é fato de negócio, com
autor, data e motivo; "esta linha sumiu da tela" é decisão de interface. Uma fatura cancelada
**continua aparecendo** na lista, com o selo e o motivo — é assim que se aprende por que o
recebível daquele mês fechou menor.

## Consequências

- **A sequência de numeração tem buracos**, e isso está correto. Fatura cancelada mantém o número,
  então `2026-0007` pode não existir entre `0006` e `0008`. Numeração sem lacuna é exigência
  **fiscal**, da NFS-e, que a FDD 028 exclui explicitamente do recorte. Vale dizer isto em voz alta
  aqui porque alguém vai reportar a lacuna como defeito.
- **`archived_at` fica herdado e morto** na `Invoice`. É peso que o modelo carrega para ter
  `created_at`/`updated_at`, e o docstring do modelo o registra — um campo herdado que não se usa é
  precisamente o tipo de coisa que o próximo leitor "conserta" por engano.
- **`retention.FAMILIAS` continua `("lead", "document")`.** O expurgo por retenção (ADR 0017) só
  alcança linha arquivada, e a `CheckConstraint` torna impossível — não apenas desaconselhável —
  acrescentar `invoice` ali.
- **`Invoice` não é registrada no `admin.py`.** O `admin.site.register([...])` em bloco dá permissão
  de delete a tudo que entra na lista; a camada 3 fecharia o buraco, mas não depender dela é mais
  barato que depender.
- **O 409 é contrato**, e a regressão `test_fatura_emitida_nao_se_apaga.py` prova as quatro camadas
  mais o lado permitido: rascunho — que nunca foi cobrado — se descarta normalmente. Uma regra sem
  lado permitido é parede, não regra.
