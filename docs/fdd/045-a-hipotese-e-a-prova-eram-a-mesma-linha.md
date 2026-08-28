# FDD 045 — A hipótese e a prova eram a mesma linha

> **O split `Evidencia` → `Evidence` + `Finding`, mais o `Discovery` que dá tempo e autoria ao
> levantamento.** É a terceira fatia da ontologia (ADR 0049): o rótulo epistemológico sai de dentro
> do registro de evidência e vira `finding.epistemic_status`, e o dado bruto passa a existir por si.
> A gravação legada **continua**, porque o custo do estado atual e a tela ainda leem dela.

## Jornada

A FDD 039 resolveu o problema certo — "nada do que se levanta numa reunião de Discovery sobrevive
a ela" — e deixou um defeito estrutural dentro da solução. A `Evidencia` guarda **três coisas numa
linha só**:

- a **forma da fonte** (`forma`: entrevista / observação / artefato / sistema / dado),
- a **afirmação já interpretada** (`content`),
- o **rótulo epistemológico** (`rotulo`: fato / hipótese / desconhecido).

Enquanto o Discovery cabe numa reunião, isso passa. Depois da segunda, não: a hipótese e o trecho
que a sustenta são o **mesmo registro**, e quem edita o texto para melhorar a redação do achado
está editando, sem saber, a prova. Pior: um achado só pode ter uma fonte, quando o material pede
justamente o contrário — *"nunca só entrevista"* (`docs/metodologia-fde.md:112-115`) só se verifica
quando as fontes são contáveis, e aqui elas não são; são um campo `CharField`.

Há uma segunda perda, e ela aparece na segunda venda para a mesma empresa.
`Process.source_project` e `Process.source_meeting` respondem por **uma** origem. O mesmo
processo revisitado noutro Discovery não tem onde ser registrado: ou a segunda leitura sobrescreve
a primeira em silêncio, ou o processo é duplicado e o AS-IS da conta passa a ter duas versões sem
que nada diga qual é a de quando. É a mesma classe de defeito que a FDD 039 corrigiu ao ancorar o
processo no cliente — só que um nível acima.

E há uma terceira, que é a que o language map (D6) nomeia: **promover a fato não custava nada.**
Um `PATCH {"rotulo": "fato"}` bastava. Nada exigia que existisse evidência viva por baixo, e nada
registrava quem afirmou. `process.custo_do_estado_atual` lê exatamente esse campo para decidir
se o número mais persuasivo de um Discovery entra na proposta que o cliente lê — de modo que o
caminho mais curto entre "alguém achou" e "a casa afirmou ao cliente" era um clique.

## O que esta fatia entrega

**Cinco entidades, e a divisão do trabalho entre elas é a fatia inteira.**

- **`Discovery`** — o levantamento como unidade: projeto, escopo, estado, datas e responsável. É o
  que dá ao mapa a resposta para "de quando?".
- **`DiscoverySession`** — a sessão: reunião, visita ou leitura de sistema. `meeting` é opcional
  porque nem toda sessão é uma reunião registrada no portal, e quando vem preenchida precisa ser
  do mesmo projeto do Discovery.
- **`ProcessObservation`** — a observação de um processo **dentro de um** Discovery, com tipo
  (primeira leitura / revisita / validação). É esta tabela que desfaz a proveniência única: o mesmo
  processo observado em dois Discoveries são duas linhas aqui, e nenhuma sobrescreve a outra.
- **`Evidence`** — o dado bruto: `raw_excerpt` (o trecho como foi dito ou observado) e/ou
  `reference` (o localizador — URL, arquivo, timestamp). **Um dos dois é obrigatório**: uma
  evidência sem conteúdo e sem localizador não é evidência, é uma linha dizendo que existe alguma
  coisa em algum lugar.
  Os quatro vínculos opcionais dela (`process`, `step`, `discovery`, `source_session`) são
  validados contra a conta e entre si — a fronteira por campo opcional é a pior forma de vazar,
  porque ninguém preenche o campo pensando nisso.
- **`Finding`** — a afirmação, com `epistemic_status` ∈ `fact` · `hypothesis` · `unknown`,
  `confidence` opcional, revisor, data de revisão e **M2M** para as evidências que a sustentam.

**Duas invariantes com dente** (`docs/ontology/language-map.md` §6.8-9, ADR 0049):

1. **Achado criado por extração nasce `hypothesis`.** O valor é carimbado no código do coletor,
   nunca lido do que o modelo devolveu — é a mesma imposição que a FDD 039 já fazia na `Evidencia`,
   e o `_PROMPT_PROCESSOS` continua sem mencionar as chaves.
2. **`fact` exige revisor humano e ao menos uma `Evidence` viva.** As duas metades moram em lugares
   diferentes porque o M2M não existe antes do save: o revisor é cobrado no `clean()` do modelo **e**
   no serializer; a evidência viva, só no serializer.

**O carimbo de integridade.** `Evidence.content_hash` é o `sha256` do `raw_excerpt`, recalculado a
cada gravação. Ele não é enfeite: um `fact` afirma que existe um trecho que o sustenta, e sem
carimbo do trecho, editar o `raw_excerpt` depois muda o que a casa alega ter observado sem deixar
rastro. É a mesma ideia do case congelado (FDD 027), no tamanho de um campo.

**A extração por IA passa a escrever nos dois modelos, na mesma transação.** Continua criando
`Process`/`ProcessStep`/`Evidencia` **e** cria, ao lado, uma `Evidence` por processo (a reunião
como fonte) e um `Finding` por achado, ligados entre si. `Finding.legacy_evidencia` aponta para a
linha fundida de onde ele saiu. **A resposta da action não muda de forma** — segue
`{"processos": [...]}`, e nenhuma tela precisou mudar.

**O backfill traduz tudo o que já existe** (migração `0054`), sem apagar nem alterar nada.

## Critérios de aceite

- Um `Finding` em `fact` sem revisor é 400; com revisor e sem `Evidence` viva, 400; com os dois,
  passa — e `reviewed_at` é carimbado pelo estado, não pelo corpo.
- Arquivar a **última** `Evidence` viva de um `Finding` em `fact` é recusado com 409, e não aceito
  em silêncio nem convertido num rebaixamento que ninguém pediu.
- `fact` → `unknown` é 400; `fact` → `hypothesis` passa.
- Achado extraído pela IA nunca nasce `fact`, e o texto do achado **não** aparece em
  `Evidence.raw_excerpt` — a conclusão vai para `Finding.statement`, a evidência fica com o
  localizador da reunião.
- Entrega que não participa de nenhum projeto do cliente não lê e não escreve `Evidence` nem
  `Finding`; e não pendura processo de outra conta num Discovery próprio.
- Os quatro vínculos opcionais da `Evidence` respondem à mesma pergunta: `process`, `step` e
  `discovery` são cobrados contra a conta, e `source_session`, quando há `discovery`, contra ele.
- O mesmo processo aceita observação em dois Discoveries diferentes.
- `content_hash` muda quando `raw_excerpt` muda, e é vazio quando não há trecho.
- Depois do backfill, cada `Evidencia` — inclusive a arquivada — tem o par correspondente, com
  `legacy_evidencia` preenchido, e nenhuma `Evidencia` foi apagada ou alterada.
- `process.custo_do_estado_atual` continua idêntico: quem sustenta o número nesta fase ainda é a
  `Evidencia` legada.

## Contrato

Rotas novas em `/api/v1/`, todas com `?archived=1` e `POST /unarchive/`:

| Rota | Âncora do recorte | Quem |
| --- | --- | --- |
| `/discoveries/` (`?project=`, `?owner=`, `?status=`) | projeto | vendas / entrega no projeto / admin |
| `/discovery-sessions/` (`?discovery=`, `?meeting=`) | projeto do Discovery | idem |
| `/process-observations/` (`?discovery=`, `?process=`, `?observation_type=`) | projeto do Discovery **e** conta do processo | idem |
| `/evidence/` (`?account=`, `?discovery=`, `?process=`, `?step=`, `?kind=`) | conta | vendas / entrega no cliente com projeto seu / admin |
| `/findings/` (`?account=`, `?process=`, `?step=`, `?epistemic_status=`) | conta | idem |

Aditivo: nada foi removido nem mudou de forma. `POST /meetings/{id}/estruturar/` responde
exatamente como antes.

`evidence` no singular porque é substantivo incontável em inglês — "evidences" é o verbo, e um
plural inventado seria um sinônimo criado para soar melhor, que é o que o language map proíbe.

**Vendas e Entrega escrevem os cinco**, pelo argumento que a FDD 039 herdou da FDD 037: quem conduz
Discovery é das duas áreas, e um registro que só metade da casa pode fazer é um registro que não
acontece.

## Decisões

### Por que o dual-write, e não a troca

`process.custo_do_estado_atual` (FDD 039) pergunta por `Evidencia` viva com `rotulo=fato`, e
`ProcessDetailPage` lista `Evidencia`. Desligar a gravação legada nesta fatia derrubaria as duas
no mesmo commit — e derrubaria em silêncio: o custo passaria a nunca ser sustentado, o que **é** um
estado válido, e nenhum teste ficaria vermelho por isso. A troca da fonte é uma decisão própria,
com o seu próprio teste; aqui ela fica travada de propósito, e há regressão afirmando que promover
um `Finding` **não** move o cálculo. No dia em que a troca for deliberada, é esse teste que precisa
mudar junto — e é essa a diferença entre uma migração e um acidente.

### Por que `epistemic_status` tem default e `rotulo` não

A ADR 0034 recusou default à `Evidencia.rotulo`, e o argumento continua de pé: um default faz a
casa escolher pelo silêncio de quem não escolheu, e o erro cai sempre para o mesmo lado. A
diferença aqui é que subir de `hypothesis` deixou de ser de graça. O default é o valor **menos**
afirmativo, e promover exige revisor e evidência viva — o erro por omissão cai para o lado seguro,
que é o oposto do que acontecia quando qualquer `PATCH` bastava para chamar suposição de fato.

### Por que `reviewed_by` vem do corpo, e não da sessão

`registered_by` e `captured_by` saem da sessão porque respondem "quem digitou". `reviewed_by`
responde outra coisa: **quem confirmou**. O consultor que validou o número no chão de fábrica pode
não ser quem registra a promoção, e forçar o usuário da sessão gravaria um nome errado com
aparência de auditoria. O que a invariante exige é que a promoção **tenha nome** — omiti-lo é 400,
nunca carimbo silencioso.

### Por que arquivar a última evidência de um fato é 409

A FDD 025 diz que quem tem filho listável escolhe entre recusar com 409 e arquivar junto. Aqui a
escolha é recusar, e por uma razão que não vale no caso geral: o "órfão" seria uma **afirmação**
sobre a operação de um cliente ficando de pé sem nada por baixo, e nada ficaria vermelho — o achado
continuaria dizendo "fato" na tela e na proposta. A alternativa (rebaixar o achado junto) desfaria
em silêncio uma promoção que uma pessoa fez, sem que ela pedisse.

### De `fact` só se volta a `hypothesis`

`FINDING_TRANSITIONS` é assimétrico de propósito, no molde de `ARTIFACT_TRANSITIONS`. Rebaixar
precisa ser possível — é assim que se corrige um erro, e um estado do qual não se sai transforma
engano em verdade permanente. Mas ir de `fact` direto a `unknown` apagaria a diferença entre
"estávamos errados" e "nunca soubemos".

### As três aproximações do backfill, declaradas

A migração `0054` afirma três coisas que o dado de origem não registrava. Ficam escritas aqui
porque uma aproximação silenciosa vira fato histórico na primeira consulta:

1. **`raw_excerpt` recebe `content`.** É conhecidamente impreciso: o `content` legado pode ser
   conclusão interpretada, e não trecho bruto. É a única fonte que existe, e inventar uma separação
   que o dado não tem seria pior. A marca de "veio do modelo fundido" é o próprio
   `legacy_evidencia` preenchido.
2. **`rotulo=fato` vira `reviewed_by=registered_by` e `reviewed_at=updated_at`.** O modelo antigo
   não registrava revisão; alguém marcou aquilo como fato, e quem registrou o achado é a melhor
   aproximação auditável de quem e quando. Quando nem `registered_by` existia, o fato fica **sem
   revisor** — dívida herdada, contada pelo comando `reconciliar_evidence_finding` em vez de
   escondida. Esta é a única afirmação da fatia sobre revisão humana derivada de dado que não a
   registrava.
3. **As arquivadas vêm junto, com o carimbo preservado.** Deixá-las fora faria o par novo divergir
   do legado justamente no que já se decidira guardar, e desarquivar do lado antigo passaria a
   produzir um registro sem contraparte.

### Por que os quatro vínculos são validados, e não só os dois caros

`process` e `step` exigiram resolver caminho (`step.processo.client`); `discovery` é um hop mais
curto que os dois, e `source_session` reusa a regra que a `ProcessObservation` já aplica. Validar
dois e deixar o terceiro solto seria pior que não validar nenhum: quem lesse o `clean()` depois
veria dois campos opcionais cobrados contra a conta e um fora, e concluiria que há uma razão. Não
há — é a mesma classe de vínculo cruzado. Não é vazamento (a queryset recorta por `account`, e a
evidência alheia não aparece de qualquer jeito); é dado inconsistente, e dado inconsistente é o
que faz a fatia seguinte, a que ligar Discovery e Evidence numa tela, descobrir que o vínculo não
vale.

### `content_hash` recalculado sempre, e vazio quando não há trecho

Comparar com o banco para saber "mudou?" custaria uma leitura por gravação e ainda erraria em
`bulk_create`, onde não há instância anterior. Trecho vazio fica com hash vazio de propósito:
`sha256("")` é uma constante, e gravá-la faria "não há trecho" parecer um trecho carimbado.

## Testes

- `apps/core/tests/test_evidence_finding.py` — as duas metades da invariante §6.9 na criação e na
  promoção, a recusa 409 do arquivamento com as suas três metades simétricas (penúltima evidência,
  hipótese, achado já arquivado), as transições, o par trecho/localizador, o hash, as datas do
  Discovery, a sessão de outro projeto, o mesmo processo em dois Discoveries, a fronteira de conta
  nas quatro pontas (com controle positivo em cada uma) e o comando de reconciliação.
- `tests/regression/test_a_conclusao_nao_vira_evidencia.py` — a fusão não volta pela extração: o
  achado vai para `Finding.statement`, a `Evidence` fica com o localizador, e o `Finding` nasce
  `hypothesis` ligado a ela.
- `tests/regression/test_o_dual_write_nao_muda_o_custo.py` — os dois lados são gravados, a resposta
  da action não muda de forma, e quem sustenta o número continua sendo a `Evidencia` legada.
- `tests/regression/test_backfill_do_split_preserva_o_legado.py` — a função da migração rodada
  sobre dados reais: as cinco formas e os três rótulos um a um, a aproximação de revisão, as
  arquivadas com o carimbo, o legado intacto, a idempotência e a reversa que só apaga o migrado.

## Fora deste recorte

- **Tela.** Nenhuma. O dual-write mantém `ProcessDetailPage` e `AccountDetailPage` funcionando
  sobre o modelo legado; tela de Discovery e painel de achados são interface nova e exigem Design
  Approval Package, que não existe. Entraram só os tipos em `frontend/src/types.ts`, sem consumidor,
  para a próxima fatia não começar do zero.
- **`Engagement`.** A issue original cita `discovery.engagement`, e o modelo **não existe ainda** —
  ele é a Fase 2 da ontologia. O campo é aditivo e entra lá.
- **Descontinuar a `Evidencia`.** É a fatia seguinte, e ela começa por trocar a fonte de
  `process.custo_do_estado_atual`.
- **Renomear `Processo`/`ProcessoEtapa`/`Evidencia`.** Era "fora deste recorte" quando esta FDD
  foi escrita, e a issue #67 (ADR 0052) pagou os dois primeiros: `Processo`/`ProcessoEtapa` viraram
  `Process`/`ProcessStep` na fatia 4, em 28/08/2026, junto de `Client`→`Account` na fatia 2. As
  **tabelas** dos quatro continuam sendo a Fase 6. `Evidencia` **não** entrou, e é o único dos
  quatro que não é só renome: ela é a metade legada deste split, e quem a remove é a Fase 6, com o
  dual-write. Aqui o nome canônico aparecia só como **nome de campo** (`account`, `process`,
  `step`) apontando para o modelo legado; depois da #67 esses campos apontam para a classe de nome
  certo.
- **`PainPoint`, `ImprovementOpportunity`, `PriorityAssessment`, `SolutionHypothesis`.** Fase 4.
