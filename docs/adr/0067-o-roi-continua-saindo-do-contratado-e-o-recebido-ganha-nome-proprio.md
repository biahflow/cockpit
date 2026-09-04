# ADR 0067 — O ROI continua saindo do contratado, e o recebido ganha nome próprio

**Status:** aceita
**Data:** 2026-09-04
**Depende de:** FDD 028 (contas a receber) · RFC 0004 (cobrança relacional) · ADR 0021 (a fatura
não arquiva nem apaga) · ADR 0032 e ADR 0034 (só o fato sustenta número) · ADR 0020 (os snapshots
congelados do `Case`)
**Fecha:** a pendência que o roadmap (Fase 7) declarou por escrito — *"trocar a fonte do ROI, que
segue pedindo ADR próprio"*

## Contexto

A FDD 028 trouxe a fatura, e com ela a colisão que a RFC 0004 tinha nomeado como o **maior risco**
da fase: no instante em que a fatura existe, passam a existir **duas verdades sobre receita**.
`Project.actual_value`, que sempre alimentou o ROI, e a soma das faturas pagas.

A decisão daquele momento foi adiar a escolha e proteger o estado: `actual_value` é o valor
**contratado**, a soma das faturas pagas é o **recebido**, e nenhum consumidor muda. A guarda é
`backend/tests/regression/test_roi_nao_muda_com_faturas.py`, e o docstring dela declara o contrato
melhor do que qualquer prosa nova conseguiria:

> *"É a maior ameaça declarada da RFC 0004, e ela não é um bug — é uma **deriva**. (…) Sem decisão
> explícita, alguém 'corrige' o `_roi` para somar faturas num commit de terça, e o número muda em
> seis lugares de uma vez — inclusive no bloco de ROI que `portal.build_snapshot` **já entrega à
> tela do cliente**."*

Adiar era certo então. Mas dívida com prazo aberto é dívida que decide sozinha no primeiro commit
de terça — e este ADR existe para que a escolha seja um ato, não uma omissão.

### Os seis leitores, medidos

Todos leem `project.actual_value` diretamente, e são o que a troca moveria de uma vez:

| Leitor | Onde | O que faz com o número |
| --- | --- | --- |
| Contexto do agente comercial | `apps/core/agents.py:190,194` | soma a receita ativa e a receita por conta |
| Health Score | `apps/core/health.py:127` | penaliza margem negativa (`actual_value - cost < 0`) |
| Visão da conta | `apps/core/views.py:869` | soma a receita dos projetos visíveis |
| Indicadores | `apps/core/views.py:4997-5082` | ROI agregado, por conta, por serviço, e o funil |
| **Portal do cliente** | `apps/core/portal.py:653` | **`revenue`/`cost` que atravessam ao cliente** |
| `Case` | `apps/core/cases.py:77` | congela receita, custo e ROI no caso publicado |

### Onde os dois números divergem — por construção, não por defeito

1. **Projeto sem fatura**: todo projeto anterior à FDD 028, e todo projeto cujo cronograma ainda é
   rascunho. A soma de pagas é zero, e o ROI viraria −100% para trabalho que a casa fez e cobrou.
2. **Fatura cancelada** (ADR 0021: ela não arquiva nem apaga, e o cancelamento é o caminho): sai do
   recebido, não sai do contratado.
3. **Pagamento a menor, parcelado ou em atraso**: o recebido é uma série no tempo; o contratado é
   um fato do dia da venda.
4. **Design Partner**: o Discovery é gratuito por decisão (ADR 0053), e o valor concedido vive como
   desconto no `estimated_value`. Não há fatura a pagar, e não deveria haver ROI negativo por isso.
5. **A semente do cronograma já depende do contratado**: `invoices.contracted_value`
   (`apps/core/invoices.py:100-120`) usa `actual_value` **primeiro**, e o docstring diz por quê —
   *"semear um cronograma que não soma exatamente isso faria os dois números se contradizerem no
   primeiro dia"*. Ou seja: as faturas derivam do contratado. Fazer o ROI derivar das faturas
   fecharia um ciclo em que o número explica a si mesmo.

## Decisão

### 1. O ROI continua saindo do contratado. A fonte não muda.

`Project.actual_value` permanece a receita de todos os seis leitores. O `test_roi_nao_muda_com_faturas`
continua sendo a guarda, e passa a ter esta ADR como referência em vez de um prazo em aberto.

Três razões, na ordem em que pesam:

- **São perguntas diferentes, e "ROI" responde a primeira.** *Quanto esta relação vale para a
  casa* é o contratado contra o custo. *Quanto entrou no caixa até hoje* é o recebido. Somar faturas
  no ROI não corrige o ROI — troca a pergunta sem trocar o rótulo, que é exatamente o que o
  `language-map` proíbe (um conceito, um nome).
- **O número já atravessou ao cliente.** `portal.build_snapshot` entrega `revenue`/`cost` desde a
  Fase 1. Trocar a fonte não produz um número novo a partir de hoje: **reescreve o passado** na tela
  de quem já leu. E o `Case` é explícito sobre isso — `cases.py` diz que é *"uma fotografia e não
  pode mudar de significado depois de tirada"*.
- **O recebido é volátil por natureza, e o ROI não pode ser.** Um cliente que paga no dia 10 faria
  o Health Score do dia 9 dizer que a relação está no vermelho. O Health já tem a régua de cobrança
  para falar de inadimplência (FDD 036) — ela é o lugar certo, e ela já funciona.

### 2. O recebido ganha nome próprio, e nunca o rótulo do ROI

O que faltava não era trocar a fonte: era **o segundo número não existir com nome**. Hoje só há
`Invoice.status == PAID` linha a linha; não há agregado de recebido em lugar nenhum
(`grep` por soma de pagas devolve apenas os filtros da régua e do painel).

Fica decidido que, quando a operação precisar dele, ele nasce como `recebido` — número próprio,
rótulo próprio, ao lado do contratado e nunca no lugar dele. Onde ele cabe (Financeiro, painel de
cobrança) é decisão de superfície e pede DAP; **o que este ADR fixa é que ele não pode se chamar
ROI nem substituir a receita de nenhum dos seis leitores.**

### 3. O que atravessa ao cliente não muda, e isso é a parte normativa

O portal continua recebendo `revenue`/`cost` do contratado. Se algum dia o recebido precisar
atravessar, ele atravessa **com nome próprio e ao lado**, nunca substituindo — a regra da ADR 0003
sobre o snapshot, e a da ADR 0034 sobre número sustentado.

## Consequências

- A dívida sai do roadmap como **decidida**, não como paga: nada muda no código hoje, e é esse o
  ponto. O que muda é que a próxima pessoa a olhar `_roi` encontra a razão escrita, em vez de um
  silêncio que convida ao commit de terça.
- `test_roi_nao_muda_com_faturas` deixa de ser um congelamento à espera de decisão e passa a ser a
  guarda **desta** decisão. O docstring dele ganha a referência a esta ADR.
- O roadmap (Fase 7) perde a pendência nomeada; a FDD 028 ganha a emenda que diz onde a decisão
  mora.
- Quando o recebido for construído, ele nasce sob esta ADR — e um PR que o faça sob o nome "ROI"
  contradiz uma decisão aceita, que é o tipo de coisa que a revisão pega.

## Alternativas consideradas

**Trocar a fonte para a soma das faturas pagas.** Recusada pelos cinco casos de divergência: ela
tornaria negativo o ROI de todo projeto sem fatura (incluindo os anteriores à FDD 028 e todo Design
Partner), faria o número oscilar com o calendário de pagamento, e reescreveria o que o cliente já
viu no portal e o que o `Case` congelou. O argumento a favor dela — *"receita é o que entrou"* — é
verdadeiro em contabilidade e falso aqui: o ROI da casa mede a relação, não o caixa.

**Emitir os dois com o mesmo nome, escolhendo por contexto** (contratado internamente, recebido no
Financeiro). Recusada por ser a definição de deriva silenciosa: dois números com um rótulo só é
como a colisão nasce, e a RFC 0004 já a nomeou.

**Deixar em aberto até alguém precisar.** Recusada porque é o estado atual, e ele tem prazo de
validade: a guarda protege o comportamento, não a intenção. No dia em que alguém mudar a fórmula
por um motivo legítimo, o teste diferencial passa a exigir a atualização dos dois lados — e sem
decisão escrita, a atualização vira palpite.

## Aprovação

Alterar a fonte de um número que atravessa ao cliente é mudança de contrato, e a
`workflows/feature.md` a coloca sob aprovação humana.

| Campo | Valor |
| --- | --- |
| Aprovador | Daniel Campos |
| Data | 2026-09-04 |

A decisão aprovada é a recomendada: **a fonte não muda**, e o recebido ganha nome próprio quando
for construído.
