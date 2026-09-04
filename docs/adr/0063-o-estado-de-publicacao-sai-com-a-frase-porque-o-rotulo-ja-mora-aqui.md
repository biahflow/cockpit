# ADR 0063 — O estado de publicação sai com a frase, porque o rótulo já mora no servidor

**Status:** aceita
**Data:** 2026-09-03
**Depende de:** ADR 0060 (publicável é campo próprio) · ADR 0026 (mapa de estado devolve variante) ·
ADR 0056 (valor de enum também é vocabulário) · `docs/ontology/language-map.md` §3
**Implementada por:** FDD 052 · issue #108 · DAP `docs/design/dap-publicacao-discovery-r1/`

## Contexto

A ADR 0060 entregou a marca de publicável em cinco modelos e as cinco portas que a defendem, e
deixou escrito que a superfície ficava devendo: *"publicar hoje é chamada de API"*. A issue #108
fecha essa pendência, e a primeira pergunta dela é de contrato, não de tela: **como a tela sabe se
um item pode subir, e o que dizer quando não pode.**

`apps/core/publication.py` já respondia as duas perguntas para as portas. `o_que_falta_para_publicar`
devolve chaves (`published_evidence`, `published_finding`, `published_pain_point`,
`published_process`); `dependentes_publicados_de` devolve os registros publicados que impedem a
saída. E já havia, no mesmo módulo, **os rótulos em português**: `ROTULOS` e `_IMPEDIMENTO`, que
compõem a mensagem do 400 de `publish` e a do 409 de `unpublish`.

O produto tem um molde estabelecido para "o que falta", e ele diz o contrário do que esta ADR
decide. `prove.o_que_falta_para_iniciar` é descrito no `CLAUDE.md` assim:

> *devolve **chaves e nunca frases** — os rótulos são da superfície*

Seguir o molde por simetria significaria a tela traduzir `published_evidence` para "ao menos uma
evidência publicada e viva" em TypeScript. E aí a mesma frase passaria a existir em dois lugares:
no `ROTULOS` que o 400 usa, e no mapa do front.

## Decisão

**`publication_state` sai dos cinco serializers com chaves *e* frases, e as frases vêm de
`publication.py`.**

```json
"publication_state": {
  "state": "published" | "ready" | "blocked",
  "missing": ["published_evidence"],
  "missing_phrase": "ao menos uma evidência publicada e viva",
  "blocked_by": 2,
  "blocked_phrase": "Este processo é a âncora de 2 achado(s) ou dor(es) publicado(s). Despublique-os primeiro."
}
```

### 1. A divergência com o molde do PROVE é factual, não de gosto

No PROVE os rótulos **não existiam** no backend: `o_que_falta_para_iniciar` nasceu devolvendo
chaves, e a superfície foi o primeiro lugar a nomeá-las. Ali "os rótulos são da superfície" descreve
onde eles moram, e a regra impede que passem a morar em dois lugares.

Aqui eles **já moram no servidor**, e não como detalhe interno: são a copy que o operador lê no 400
e no 409 desde a ADR 0060. A pergunta não é "onde criar o rótulo", é "o que fazer com o rótulo que
existe". Reescrevê-lo em TypeScript criaria a segunda definição que a regra do PROVE existe para
evitar — aplicar a regra literalmente produziria exatamente o defeito que ela previne.

As duas ADRs concordam na regra e divergem na aplicação porque o mundo é diferente: **uma definição
por conceito**.

### 2. As chaves continuam saindo, e não são decoração

`missing` carrega as chaves porque elas são o que permite teste sem parsear texto e ramificação de
superfície sem depender de redação. A tela de publicação as usa para a cascata de seleção — dado um
`published_process` faltando, marcar o mapa que o item cita. **Isso é consumir a resposta, não
reescrever a pergunta:** quem diz o que falta continua sendo o servidor; a tela só sabe qual
registro da árvore é candidato àquele degrau.

### 3. Cada ramo calcula um lado só

`published_at is not None` → calcula `blocked_by`/`blocked_phrase` e devolve `missing` vazio.
`published_at is None` → calcula `missing`/`missing_phrase` e devolve `blocked_by` zero.

A omissão é medida, não economia arbitrária: **um registro não publicado não pode ter dependente
publicado** — é a invariante que as cinco portas defendem —, e um registro publicado já passou pelo
que faltava. Calcular os dois lados sempre dobraria a consulta por linha sem o resultado poder mudar
de valor.

### 4. Campo derivado no serializer, não endpoint de leitura

A alternativa óbvia era `GET /<recurso>/{id}/publication-state/` nos cinco. Recusada porque o caso
de uso principal é uma tela que desenha o Discovery **inteiro** de uma conta: um mapa, n evidências,
n achados, n dores e n oportunidades. Um endpoint por item cobraria uma requisição por linha
exatamente ali. O campo derivado chega junto das listagens que a tela já faz.

### 5. `ImprovementOpportunity` sai com `blocked_by: 0` sempre, e isso é estado normal

Ela é o topo da escada: `dependentes_publicados_de` devolve `[]` para ela e `_IMPEDIMENTO` não tem
entrada com o nome dela. Zero ali não é "não apurado" — é "nada pende disto", que é fato do domínio.
É a exceção deliberada à regra do `nao_apurado`, e está testada.

## Consequências

- **A frase de recusa passa a ter dois leitores**, a mensagem de erro e o campo derivado, e um
  lugar só que a escreve. Mudar a redação de `ROTULOS` muda os dois de uma vez — que é o ponto.
- **Um teste guarda a igualdade.** `test_publicacao_estado.py` compara `missing_phrase` com
  `frase_do_que_falta` e `blocked_phrase` com `frase_do_impedimento`, pela API e pela função. Sem
  ele, a próxima varredura atrás de simetria com o PROVE reescreve o rótulo no front e nada fica
  vermelho.
- **O custo de consulta subiu 1 query por item** na listagem de `Process`, `PainPoint` e
  `ImprovementOpportunity` (`Evidence` e `Finding` em hipótese não pagam nada). É o N+1 que
  `_tem_publicado_vivo` já tinha por linha nas portas, agora também na leitura. Medido e registrado
  na FDD 052; não otimizado, porque otimizar sem uma conta grande de verdade é escolher o alvo pelo
  palpite.
- **O front fica proibido de ter mapa chave→rótulo**, e a proibição é testável: há teste que injeta
  uma frase inexistente em `publication.py` e afirma que a tela a renderiza tal e qual. Um mapa em
  TypeScript escreveria a canônica no lugar.

## Alternativas consideradas

**Só chaves, seguindo o molde do PROVE.** Recusada pelo motivo da decisão 1: aqui produziria a
duplicação que lá ela evita. Mantê-la teria a vantagem real de uma regra só para os dois casos, ao
custo de a mesma frase existir em dois idiomas de implementação.

**Só a frase, sem as chaves.** Recusada: deixaria teste e superfície dependentes de comparação de
texto, e qualquer ramificação por requisito viraria parsing.

**Endpoint de leitura por item.** Recusada na decisão 4 — mesma regra no servidor, custo no lugar
errado.

**O front inferir de `published_at` e da cadeia.** Recusada sem hesitação: é a duplicação da regra
que `publication.py` existe para concentrar, e as duas divergem no primeiro conserto sem nada ficar
vermelho.
