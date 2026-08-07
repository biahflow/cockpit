# ADR 0023 — Resposta ancorada: citar ou declarar a lacuna, e quem declara o regime é o modelo

- **Status:** aceita
- **Data:** 07/08/2026
- **Contexto:** FDD 029 (base de conhecimento interna), ADR 0006 (motor de agentes), ADR 0022
  (recuperação com pgvector), FDD 024 (homologação como método)

## Contexto

A FDD 029 nomeia um modo de falha que é específico da IA sobre base de conhecimento, e que faz a
citação ser **condição de existir** e não refinamento: um humano que não sabe diz "não tenho
certeza"; **um modelo sobre corpus incompleto inventa resposta plausível**, e sobre corpus velho
lava informação desatualizada com fluência confiante — *pior que não ter KB nenhum*.

Isso contraria um reflexo forte: "o prompt manda citar, logo ele cita". Não manda coisa nenhuma. O
prompt é pedido; a garantia tem de ser código.

## Decisão

**Duas regras, e as duas nasceram de medição contra o modelo real (rodada 5 de homologação).**

### 1. Quem declara de onde veio a resposta é o modelo, não o cosseno

O desenho original tinha um **limiar de similaridade** decidindo se a regra de citar-ou-lacuna
valia: acima do piso, material injetado e citação obrigatória; abaixo, o agente responde como
sempre. Parecia limpo. A rodada 5 mediu as três classes de pergunta contra o corpus real:

```
metodologia     51  56  58  61  62  69      (mín. 50,6%)
operacional     47  47  51  52  53  56      (máx. 56,4%)
fora do corpus  22  25  37  49
```

**As faixas se sobrepõem.** Não existe limiar que separe "perguntar sobre o método" de "perguntar
sobre os dados" — e não é ruído de medição: o corpus **descreve o domínio**, então uma pergunta
sobre projetos atrasados de fato se parece com o texto de uma FDD sobre projetos atrasados. Com o
limiar de 30% que estava planejado, "o que está atrasado?" — resposta operacional correta — seria
substituída por "não encontrei isso no material".

Então o modelo **declara o regime** numa última linha: `FONTE: [K1], [K2]` quando qualquer afirmação
veio do material, ou `FONTE: dados da área` quando veio só dos dados operacionais. Ele sabe qual
pergunta está respondendo; o cosseno não. O limiar continua existindo, mas **não carrega correção**
— serve só para não gastar token injetando material claramente fora do assunto.

O prompt separa os dois regimes com cuidado, porque a homologação da FDD 024 já cobrou uma vez o
oposto (`views.py:756`): proibir conhecimento externo **sem** proibir raciocinar. "Use apenas o
contexto" cru degenerou numa resposta literal "Não sei." para pergunta que o contexto respondia.

### 2. A imposição é código, e o que o modelo alegou não conta

`enforce_citations` resolve cada marcador contra os trechos **realmente enviados**:

- Marcador que não resolve — um `[K9]` quando seis foram mandados — **some do texto e vale zero**.
- Alegou metodologia e nenhuma citação resolve → a lacuna **substitui** o texto. Substitui, e não
  anota: um aviso pendurado numa resposta que continua na tela deixa o texto sem fonte **onde a
  pessoa lê**, que é exatamente o modo de falha.
- Declarou `dados da área`, ou já escreveu a lacuna → passa intacto.
- Nem declarou nem citou → passa (pode ser operacional), com **`warning` no log**: a deriva aparece
  antes de virar defeito.
- Trecho vencido pode ser citado, mas vai marcado `(VENCIDO)`, e a citação devolvida carrega
  `stale` — citar sem avisar legitimaria material velho.

### 3. Um único ponto de chamada

O material entra em `_ai_run(grounding=…)`, e só o `AgentView` o preenche. Os outros oito chamadores
seguem idênticos. Isso faz o anti-vazamento ser **estrutural**: não há segundo caminho por onde o
corpus interno saia — em particular ele não alcança `build_opportunity_context`, que alimenta
proposta e contrato, que o **cliente lê**.

`AiInteraction.sources` guarda a trilha, no mesmo movimento que a ADR 0006 fez com `rating`: torna
"resposta sem citação é defeito" auditável **depois do fato**, e não só no instante em que a tela
mostrou.

## Consequências

- **Um defeito caro foi achado justamente aqui, e só o modelo real o acharia.** O prompt manda
  terminar com `FONTE: [K1]`, e o `gpt-4o-mini` faz exatamente isso — cita **só** ali. A primeira
  versão removia a linha de declaração *antes* de procurar marcador, então nada resolvia e a lacuna
  **substituía uma resposta correta**, com os comandos exatos do runbook de restauração. Nenhum
  dublê acharia: ele citaria onde o teste mandasse. Fica como o argumento mais concreto a favor da
  disciplina de homologação da FDD 024.
- **O limiar é botão de ajuste, e vai estar errado de novo.** Ele depende do corpus, do modelo de
  embedding e do jeito como as pessoas perguntam. Mudou qualquer um dos três, remede — as faixas
  acima são o método, não a resposta.
- **Uma resposta sobre metodologia sem `FONTE:` passa**, com log. É escolha de assimetria: destruir
  uma resposta operacional correta é pior que deixar passar uma afirmação sem citação que o prompt
  pediu para citar. O log é o que impede isso de virar norma silenciosa.
- **A saída ganhou um protocolo entre código e modelo.** `FONTE:` nunca vai para a tela, mas passa a
  ser parte do contrato do prompt — mudá-lo sem mudar o parser quebra a citação inteira, em silêncio.
  É o argumento para a FDD futura de **registro de digest de prompt**, que o repositório vizinho já
  tem e este ainda não.
