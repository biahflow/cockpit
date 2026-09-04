# Aliases de compatibilidade — o que ainda se chama errado, e até quando

**Normativo.** Complementa [`language-map.md`](language-map.md) §5 e §7. A página do Notion vence
no significado; este espelho vence no rótulo dentro do repositório. `CLAUDE.md` e `AGENTS.md`
apontam para cá e não podem enfraquecê-lo.

O vocabulário canônico chegou ao Pulse antes do schema. A consequência é que, por algumas fases, o
repositório tem **dois nomes para a mesma coisa**: o nome que o modelo carrega desde 2025 e o nome
que a Ontology v1 diz que ele tem. Este documento lista esses pares, diz qual é o canônico e
declara **em que fase cada alias morre** — porque alias sem data de morte não é compatibilidade, é
o nome novo virando sinônimo permanente do antigo.

A guarda que sustenta isto é `backend/tests/test_vocabulario.py`, e a dívida que ela tolera está
declarada, linha a linha, em [`legacy-allowlist.txt`](legacy-allowlist.txt).

## Os aliases vivos

**"Renome" eram três coisas, e a ADR 0052 as separou.** O nome da **classe** morre na issue #67,
uma fatia por PR; o nome da **tabela** morre na Fase 6; a **rota** e a **chave de payload** morrem
na `/api/v2/`. A tabela abaixo tem uma linha por prazo, e não uma por conceito, porque era a
compressão delas em "renome físico na Fase 6" que fazia o mesmo termo significar duas coisas.

| Alias vivo hoje | Nome canônico | Onde vive | Morre em |
| --- | --- | --- | --- |
| rota `/api/v1/clients/` e chaves `client` / `status` | `/accounts/`, `account`, `lifecycle_status` | `urls.py`, `serializers.py` | `/api/v2/` |
| rota `/api/v1/opportunities/` e chave `opportunity` | `/commercial-opportunities/` e `commercial_opportunity` | `urls.py`, `serializers.py` | `/api/v2/` |
| chave de payload `gate_outcome` | `gate_decision` | `serializers.py` | `/api/v2/` |
| rotas `/processos/` e `/processo-etapas/` | `/processes/` e `/process-steps/` | `urls.py` | `/api/v2/` |
| chaves `kpi_baseline` / `kpi_current` (só leitura) | `Measurement(kind=baseline)` / `Measurement(kind=outcome)` | `serializers.py` | `/api/v2/` |
| chave `ai_opportunity` (só leitura) | `ai_potential` | `serializers.py` | `/api/v2/` |
| chave `client_consent` (só leitura) | `account_consent` | `serializers.py` | `/api/v2/` |
| chave `client_name` (só leitura) — case, fatura, processo, contato e suspensão de cobrança | `account_name` | `serializers.py` | `/api/v2/` (pago na fatia 4a) |
| chaves `client` / `client_name` do painel de cobrança e `client_name` da visão compacta da entrega | `account` / `account_name` | `cobranca.py`, `views.py` | `/api/v2/` (pago nas fatias 3a e 4a) |
| chaves `client_vertical` / `client_vertical_name` (só leitura) | `account_vertical` / `account_vertical_name` | `serializers.py` | `/api/v2/` (pago na fatia 4a) |
| chave `clients` que envolve a lista de `GET /clients/overview/` | `accounts` | `views.py` | `/api/v2/` (pago na fatia 4a — **troca**, não convive) |
| chaves `client_id` / `status` de cada linha crua de `GET /clients/overview/` e do detalhe dela | `account_id` / `lifecycle_status` | `views.py` | `/api/v2/` (pago na fatia 4c) |
| chave `roi.by_client` que envolve o recorte do ROI por conta em `GET /analytics/` | `roi.by_account` | `views.py` | `/api/v2/` (pago na fatia 4d — **troca**, não convive) |
| chave de entrada `signer_email` (um signatário) | `signers[]`, lista de `{email, role}` | `views.py` (`_signers_do_pedido`) | `/api/v2/` |
| chaves `cobranca_sinal` / `cobranca_sinal_display` (só leitura; classe/campo/valor pagos na fatia 5.2 da #122, 04/09/2026 — só resta a leitura) | `dunning_signal` / `dunning_signal_display` | `ActivitySerializer` | `/api/v2/` |
| chaves `degrau` / `degrau_display` (só leitura) e valor de entrada `pre_aviso` / `lembrete` / `firme` / `escalada` / `renegociacao` (**classe, tabela, campo e valor persistido já pagos**, fatia 5.4, 04/09/2026 — só restam a leitura e a entrada) | `dunning_step` / `dunning_step_display` e `pre_notice` / `reminder` / `firm` / `escalation` / `renegotiation` | `DunningContactSerializer`, `views.VALORES_LEGADOS_DO_DEGRAU` (corpo das actions e filtro) | `/api/v2/` |
| parâmetro de filtro `?degrau=` | `?dunning_step=` | `DunningContactViewSet.filter_field_aliases` | `/api/v2/` |
| valor de entrada `declarada` / `percebida` e os quatro níveis `promotor` / `satisfeito` / `neutro` / `insatisfeito` (**valor persistido já pago**, fatia 5.3, 04/09/2026 — só resta a entrada) | `declared` / `perceived` e `promoter` / `satisfied` / `neutral` / `dissatisfied` | `SatisfactionRecordSerializer.VALORES_DE_ENTRADA` e `SatisfactionRecordViewSet.filter_valores_legados` | `/api/v2/` |
| rota `/api/v1/satisfacoes/` | `/satisfaction-records/` | `urls.py` | `/api/v2/` (a canônica nasceu na fatia 5.3) |
| valor de entrada `comercial` / `financeiro` / `rh` / `juridico` / `atendimento` (área do blueprint; **valor persistido já pago**, fatia 5.1, 04/09/2026 — só resta a entrada) | `commercial` / `finance` / `hr` / `legal` / `support` | `DigitalEmployeeBlueprintSerializer.VALORES_DE_ENTRADA` e `DigitalEmployeeBlueprintViewSet.filter_valores_legados` | `/api/v2/` |
| chaves `digital_employees[].kpi_label` / `kpi_value` / `hours_saved_month` / `roi_month` no snapshot do portal | `digital_employees[].kpi_ids` + `kpis[]` | `portal.py` | quando o One parar de lê-las |

> **A linha das chaves `digital_employees[]` do snapshot é do snapshot, não da `/api/v1/`, e por
> isso o prazo dela tem outra forma.** (Nomeada assim, e não por posição na tabela, desde a fatia
> 5.4 da issue #122: contar linhas de baixo para cima é ponteiro que apodrece sozinho quando a
> tabela cresce — era "a quarta de baixo para cima" e a contagem já tinha quebrado quando esta nota
> foi lida de novo.) Até a FDD 050 os quatro campos legados do funcionário digital eram a *única* coisa
> que o portal do cliente tinha sobre medição: texto livre, sem unidade tipada, sem janela e sem
> como comparar duas leituras. Agora eles têm sucessor — `kpi_ids` aponta para `kpis[]`, onde moram
> a unidade, o método, a baseline, o outcome e o monitoramento. Continuam saindo, inalterados, pela
> convivência de sempre (§2c): o consumidor é o One, e quem declara que parou de ler é ele. A data,
> portanto, não é a `/api/v2/` — é a confirmação do outro lado, e ela é registrada aqui quando
> chegar. Ver ADR 0003 (emenda de 01/09/2026).

> A decisão D10 da Language Map v1.4 torna o **valor** do enum parte do mesmo contrato de idioma
> do nome da classe e do campo. Esta tabela não autoriza migração isolada: os dados do grupo de
> cobrança e satisfação mudam junto do renome de cada família, com reversa e normalização de
> entrada na v1. **A área do blueprint foi a primeira a mudar** (fatia 5.1 da issue #122,
> 04/09/2026) — a única das quatro famílias com o pré-requisito completo: a classe
> (`DigitalEmployeeBlueprint`) já nascera inglesa, e o conceito já estava no mapa (`language-map.md`
> §4). É dali que vêm os dois moldes que as famílias restantes reusam: a **migração de valor
> persistido, com reversa simétrica** (`0084_a_area_do_blueprint_fala_ingles` — a primeira migração
> do repositório que traduz dado, não classe/tabela/campo), e a **normalização de entrada de valor
> na v1**, a segunda tabela do mixin de serializer (`AliasesDaV1Mixin.VALORES_DE_ENTRADA`, ao lado
> de `ALIASES_DE_ENTRADA` que já existia para chave). Até as fatias das outras três famílias
> chegarem, os valores portugueses delas seguem sendo os persistidos e expostos pela `/api/v1/`;
> nenhum valor novo nasce em português.

> **A família 2 (`Activity.CobrancaSinal`) foi a segunda a mudar** (fatia 5.2 da issue #122,
> 04/09/2026) — e a primeira em que os **três** renomes (classe, campo e valor) chegam juntos: ao
> contrário do blueprint, cuja classe já nascera inglesa, `CobrancaSinal` ainda dizia errado nos
> três níveis, e D10 exige que os três atravessem na mesma fatia quando isso acontece — adiar
> qualquer um deixaria `DunningSignal` (classe inglesa) persistindo `esqueceu`/`nao_pode`/
> `insatisfeito` num campo chamado `cobranca_sinal`, a contradição que a decisão existe para
> fechar. A migração (`0085_o_sinal_de_cobranca_fala_ingles`) encadeia `RenameField` (a coluna
> renomeia, linha e pk sobrevivem — §2b) e só depois o molde de tradução de valor da `0084`, no
> mesmo arquivo. O campo é **só de leitura** (a escrita é a action `classificar`), então não há
> `ALIASES_DE_ENTRADA` nem `VALORES_DE_ENTRADA` a declarar — o que sobrevive na `/api/v1/` é o
> alias de leitura das duas chaves (`cobranca_sinal`/`cobranca_sinal_display`), pelo mecanismo de
> sempre (§2c). O prompt de `classificar` passou a pedir os três tokens canônicos ingleses
> diretamente à IA — pedir em português e traduzir a resposta depois deixaria no prompt a aparência
> de que o modelo decide o idioma (mesmo argumento da FDD 039) —, e `views.sinal_do_texto` tolera
> os três tokens legados por barato custo de release, traduzindo-os antes de validar contra o
> vocabulário novo.

> **A família 3 (`Satisfacao`) foi a terceira a mudar** (fatia 5.3 da issue #122, 04/09/2026), e é
> a primeira em que o renome de **tabela** anda junto: `RenameModel(Satisfacao → SatisfactionRecord)`
> sem `Meta.db_table` a fixar antes, porque a pk desta família **não é uma das seis** que a §2b
> protege — o registro sequer atravessa para o portal do cliente (ADR 0032), então não há
> consumidor externo de que se despregar. Na #67 a mesma operação era escrita em duas partes
> justamente para não emitir SQL; aqui ela emite o `ALTER TABLE … RENAME TO`, que é o mesmo
> mecanismo da `0069` e preserva linha e pk. A migração (`0086_a_satisfacao_fala_ingles`) traduz
> **dois** enums no mesmo modelo, e por isso o mapa de pares da `0084`/`0085` ganhou um nível
> (campo → pares): com duas listas soltas, a reversa teria de saber de cabeça qual pertence a qual
> coluna.
>
> **Os campos `nivel` e `fonte` não renomearam, e a ausência de canônico deles está declarada na
> seção "Termos ainda sem nome canônico", ao lado de `recebido_do_cliente`.** O
> language-map §4 cunha `satisfaction_record.source` e `satisfaction_record.level` como nomes de
> **enum** — é a linha que enumera os valores —, e não como nomes de coluna; e a chave de payload é
> o que a §2c congela até a `/api/v2/`. Renomear a coluna sem ter para onde levar a chave pagaria
> metade de uma dívida e criaria outra. É a mesma situação de `sinal_*` e `satisfacao_*` no dict
> cru do painel de cobrança: o valor atravessou, a chave espera coinagem. Diferente da 5.2, aqui os
> dois campos **são graváveis**, então há `VALORES_DE_ENTRADA` no serializer (a v1 traduz o valor
> legado antes da validação) e `filter_valores_legados` no viewset (a v1 traduz o filtro, a v2
> recusa com `frase_do_valor_removido`) — os dois moldes da fatia 5.1, agora com dois campos no
> mesmo mapa.
>
> Os quatro níveis estão **enumerados** na linha da tabela acima porque era ali que a enumeração
> faltava: a linha anterior dizia "níveis em português", e alias sem os nomes escritos é alias que
> ninguém consegue conferir. O vocabulário em si já estava cunhado no language-map §4 — não houve
> coinagem nova nesta fatia, só o registro dela aqui.

> **A família 1 (`CobrancaContato`) foi a quarta e última** (fatia 5.4 da issue #122, 04/09/2026),
> e nela os **quatro** renomes chegam juntos: classe, tabela, campo (`dunning_step`) e valor. Com
> ela não sobra enum persistido em português no repositório, e o teste de congelamento
> (`test_os_quatro_enums_da_d10_falam_ingles_e_ficam_congelados_assim`) deixou de guardar português
> para passar a guardar o estado novo — a volta é o mesmo defeito visto do outro lado.
>
> **`DunningContact` é coinagem deste espelho, e a página do Notion recebe depois.** É o inverso do
> fluxo da §8 do language-map ("Notion → espelho → Pulse"), pelo precedente explícito de
> `DunningSignal` — cunhado aqui na fatia 5.2 — e pelo mesmo motivo: o campo (`dunning_step`) e os
> cinco valores **já estavam** cunhados no language-map §4, então a decisão de significado já
> existia e o que faltava era o substantivo da classe que os carrega. Esperar a página para escrever
> um nome que o campo já ditava adiaria a fatia por um ato de secretaria.
>
> A migração (`0087_o_contato_de_cobranca_fala_ingles`) é a mais longa da série porque é a única em
> que renome de tabela e de campo chegam no mesmo arquivo, e isso arrasta três operações que as
> anteriores não tiveram: `RenameIndex` (o índice de `Meta.indexes` não tem nome declarado e o
> Django o deriva do nome da **tabela**) e o par `RemoveConstraint`/`AddConstraint`, que **abraça**
> o `RenameField` — a `UniqueConstraint` cita o campo pelo nome e `RenameField` não reescreve
> `Meta.constraints`; escritas depois do renome, a reversa morria tentando recriar a constraint
> sobre uma coluna `degrau` que já não existe. O `RenameModel` renomeia a tabela em lugar, como na
> 5.3: a pk do contato de cobrança não é uma das seis da §2b e não atravessa para o portal.
>
> **A metade que não está na migração é a que mais importava.** As `key` da dataclass
> `cobranca.DunningStep` (a régua: `PADRAO`, `RELACAO_LONGA`, `RELACAO_TENSA`) **são** os valores
> persistidos na coluna. Traduzir uma sem a outra faria `_degrau_gasto` deixar de casar com o banco
> **em silêncio** — a idempotência nunca mais encontraria o degrau gasto, e o mesmo e-mail sairia
> de novo para o cliente. Por isso as duas atravessaram na mesma fatia, e por isso o teste de
> congelamento afirma as duas listas juntas.
>
> Duas superfícies aqui não existiam nas fatias anteriores, e cada uma exigiu mecanismo:
>
> * **o valor chega no corpo de uma `@action`** (`rascunhar`/`enviar`), onde o mixin de serializer
>   não passa e — diferente de um `ModelSerializer` — **não há validação de `choices` do DRF** para
>   recusar de graça na v2: quem valida é a própria action, contra as réguas. Sem tradução,
>   `pre_aviso` na v2 viraria "Degrau desconhecido", um erro mentiroso (o degrau existe; o nome
>   mudou). A recusa usa a frase de sempre, `versioning.frase_do_valor_removido`;
> * **o nome do parâmetro de filtro mudou junto com o campo** (`?degrau=` → `?dunning_step=`),
>   porque em `filter_exact_fields` o nome do parâmetro **é** o caminho do ORM. Sem alias, o filtro
>   legado deixaria de filtrar em silêncio na v1, devolvendo a lista inteira — pior que o
>   `FieldError` que o mesmo caso produz em `filter_fields`. Por isso `filter_field_aliases` passou
>   a valer nos **dois** laços do `QueryParamFilterMixin`, na mesma forma.
>
> **A rota `/cobranca/` não ganha par canônico**, e é a diferença para a 5.3: lá o prefixo
> (`/satisfacoes/`) **era** o nome da classe em português, então havia para onde ir. Aqui ele nomeia
> a **família** de cobrança, que segue sem coinagem (`CobrancaSuspensao`, `cobranca.py`, a flag e o
> `kind` de notificação `cobranca`) — inventar `/dunning-contacts/` batizaria em inglês o que
> ninguém decidiu. O que acompanhou a classe foi o `resource` do viewset
> (`cobranca` → `dunning_contact`), que é nome interno de autorização, não contrato.

> **O recorte físico da Fase 6 foi concluído; a issue #70 foi encerrada por decisão do mantenedor.** Tabelas renomeadas
> (migração `0069`), dual-write e `Evidencia` removidos (migração `0068`), `Project.client`
> removido após prova automática de equivalência (migração `0070`), `ai_opportunity` renomeado
> para `ai_potential` (migração `0071`) e `client_consent` renomeado para `account_consent`
> (migração `0072`). Os aliases de rota, payload e enum continuam com prazo na `/api/v2/`; por
> isso encerrar a issue não torna a allowlist zero nem revoga os critérios operacionais registrados.

> **`signer_email` é alias de *entrada*, e não renome de campo — é a segunda linha da tabela com
> essa natureza, junto de `gate_outcome`.** Nada foi rebatizado: o `request-signature` passou a
> aceitar uma **lista** de signatários com papel (`signers`), porque a casa, a parte contratante e as
> testemunhas assinam o mesmo documento e só a lista permite pedir isso numa chamada (ADR 0065). A
> chave antiga continua sendo aceita e vira um único `counterparty`; a canônica vence quando as duas
> vêm no mesmo corpo, pela regra da §2c. A regressão que a §2c exige está em
> `backend/tests/regression/test_o_alias_signer_email_sobrevive_na_v1.py`.
>
> **Desde a issue #120 essa regressão é o *único* chamador da chave antiga dentro do repositório**,
> e é por isso que ela deixou de ser formalidade e passou a ser o que segura o alias. O DAP
> `dap-assinatura-com-papeis-r1` foi aprovado e construído: a SPA agora escreve `signers`, com papel
> por signatário. O argumento anterior — "sobrevive porque a SPA ainda a escreve" — **caducou**, e o
> alias segue vivo por outro motivo, que é o de sempre: quem já integrou contra a `/api/v1/` manda a
> chave antiga, e ela tem prazo na `/api/v2/`, não antes. Sem o teste, a linha que a normaliza
> (`views._signers_do_pedido`) fica sem chamador daqui de dentro, e a próxima varredura atrás do
> nome antigo a remove achando que paga dívida — quebrando a `/api/v1/` sem nada ficar vermelho.

### A série 5.x fechou — fatia 6 da #122, 04/09/2026

As quatro famílias que a decisão D10 marcou atravessaram, uma por fatia: `DigitalEmployeeBlueprint.Area`
(5.1, 04/09/2026), `Activity.DunningSignal` (5.2), `SatisfactionRecord` (5.3) e `DunningContact`
(5.4). Não sobra enum persistido em português no repositório — `test_os_quatro_enums_da_d10_falam_ingles_e_ficam_congelados_assim`
(`backend/tests/test_vocabulario.py`) guarda o estado novo das quatro, e o guarda contra a volta.

**O molde nasceu na 5.1, e as três famílias seguintes o reusaram sem reabri-lo.** Duas peças, uma
por dimensão do problema:

- a **migração de valor persistido, com reversa simétrica** — `AlterField` trocando `choices`
  para inglês mais um `RunPython` que traduz as linhas existentes (pt→en) e desfaz (en→pt) —,
  primeiro em `0084_a_area_do_blueprint_fala_ingles`, depois combinada com `RenameField`/
  `RenameModel` em `0085`-`0087` conforme a família precisasse de renome de campo e/ou de tabela
  junto (a tabela só quando a pk não era uma das seis da §2b);
- a **normalização de entrada de valor na v1**, segunda tabela do mixin de serializer
  (`AliasesDaV1Mixin.VALORES_DE_ENTRADA`, ao lado de `ALIASES_DE_ENTRADA` que já existia para
  chave) mais `filter_valores_legados` no viewset, para o campo gravável cujo valor legado ainda
  chega em query string ou corpo.

Cada fatia é exceção declarada de alguma peça do molde quando a família não precisava dela: a 5.2
não ganhou `VALORES_DE_ENTRADA` porque o campo é só de leitura (a escrita é a action
`classificar`); a 5.4 precisou de uma recusa de valor legado em corpo de `@action`
(`views._degrau_do_corpo`) porque `rascunhar`/`enviar` não montam serializer, a única exceção à
regra de que a v2 não ganha frase própria para valor legado no corpo (decisão 9 da ADR 0066).

**O que resta vivo neste documento, e não é dívida da série 5.x:**

- as **chaves de payload sem coinagem** que a §2c continua protegendo até a `/api/v2/` — `nivel`,
  `fonte`, `degrau`/`degrau_display` (alias de leitura de `dunning_step`/`dunning_step_display`),
  `cobranca_sinal`/`cobranca_sinal_display` (alias de leitura de `dunning_signal`/
  `dunning_signal_display`), o parâmetro `?degrau=` e os valores de entrada `pre_aviso`/
  `lembrete`/`firme`/`escalada`/`renegociacao` e `declarada`/`percebida` — porque D10 moveu o
  **valor** do contrato de idioma, e a §2c continua sendo quem move a **chave**, no seu próprio
  prazo;
- as chaves **sem canônico nenhum** — `sinal_*`/`satisfacao_*`/`proximo_degrau*` do dict cru do
  painel de cobrança e `recebido_do_cliente` —, listadas em "Termos ainda sem nome canônico"
  abaixo, que D10 não alcança porque não é renome de valor de enum, é ausência de nome;
- a família `Cobranca*` restante — `CobrancaSuspensao`, o módulo `cobranca.py`, a rota
  `/cobranca/` com o seu `basename`, a flag de feature e o `kind` de notificação `cobranca` —, e
  `Pendencia`/`Decisao`/`Risco`, todos sem nome canônico na Ontology v1 (ver "Termos ainda sem
  nome canônico");
- o **snapshot do portal** (`digital_employees[].kpi_label`/`kpi_value`/`hours_saved_month`/
  `roi_month`), cujo prazo não é a `/api/v2/` — é a confirmação do One de que parou de ler, ver a
  nota logo abaixo da tabela de aliases vivos.

A limpeza de identificador **local** que a fatia 6 fez em cima disso — nome de módulo, de
constante, de função interna — não muda nenhuma das linhas acima: é dívida de legibilidade, não de
contrato, e por isso não tem entrada nesta tabela nem em `legacy-allowlist.txt`.

### Já pagos pela #67 — 28/08/2026

Quatro renomes de classe saíram da tabela porque deixaram de ser alias: o nome antigo não existe
mais em código. **Sair daqui não é o fim da dívida** — é o fim de *uma* das três, e as outras duas
continuam listadas acima.

**A #67 fechou com a fatia 4, e a Fase 6 já pagou as tabelas.** O que a #67 deixou para trás eram as
**tabelas** (`core_client`, `core_opportunity`, `core_processo`, `core_processoetapa`) e
`Project.client`. As tabelas **saíram** na Fase 6 (migração `0069`, renome em lugar), e a classe
`Evidencia` também (migração `0068`, com o dual-write). Resta `Project.client`, que é projeção e não
alias. As **rotas** (`/clients/`, `/opportunities/`, `/processos/`, `/processo-etapas/`) e as
**chaves de payload** (`client`, `status`, `opportunity`, `gate_outcome`, `processo`, `etapa`)
morrem na `/api/v2/` — que agora **pode nascer**, porque as tabelas já foram concluídas.

> **`etapa` morreu antes do prazo, e não pela v2.** Ela era chave de payload da `Evidencia`, e a
> Fase 6 (issue #70, migração `0068`) removeu a classe inteira com o dual-write. A lista acima a
> mantém por ser história: o prazo dela **era** a `/api/v2/`, e o que a alcançou primeiro foi a
> remoção do modelo que a emitia. Apagá-la daqui esconderia que uma dívida foi paga por um caminho
> diferente do declarado — que é informação, não ruído.

| Foi | É | Fatia |
| --- | --- | --- |
| `GateOutcome` / `gate_outcome` | `GateDecision` / `gate_decision` | 1 |
| classe `Opportunity` e 5 campos `opportunity` | `CommercialOpportunity` / `commercial_opportunity` | 3 |
| classe `Client`, 10 campos `client`, `status` | `Account` / `account` / `lifecycle_status` | 2 |
| classes `Processo` / `ProcessoEtapa` e 3 campos `processo`/`etapa` | `Process` / `ProcessStep` / `process` / `step` | 4 |

**`Project.client` saiu na Fase 6** (migração `0070`). Ele era a projeção temporária cuja fonte
canônica é `engagement.account` (ADR 0050). A chave `client` continua saindo no `GET` como alias
de leitura (`source="engagement.account_id"`, `read_only`), e morre na `/api/v2/`.

`Evidencia` era o único que não é só renome, e por isso foi o único que **não** entrou na #67: a
Fase 3 a **dividiu** em `Evidence` (o registro bruto) e `Finding` (a conclusão, com
`epistemic_status`), conforme a decisão D6. Trocar o nome sem dividir resolveria o idioma e
preservaria o defeito de linguagem que a divisão existe para corrigir. A classe legada ficou de pé
enquanto teve leitor vivo (`process.custo_do_estado_atual` e `ProcessDetailPage`); a **Fase 6
(issue #70, migração `0068`) a removeu** quando o custo passou a ler o `Finding(fact)` e a tela
migrou para o split — ver a nota de Fase 6 abaixo. Os **campos** dela já haviam passado a `process`
e `step` na fatia 4 — renome de campo é `RenameField`, e ele preserva linha e pk.

Depois da #67 sobrava uma dívida com forma nova e nome antigo: a tabela `core_processo` guardando
linhas de uma classe chamada `Process`. Era desconfortável no `dbshell` e proposital — o risco que a
espera protegia é o da **pk**, e pk é o que a §2b trata. A **Fase 6 pagou** essa dívida (migração
`0069`): renomeou as tabelas em lugar, sem tocar na pk (nota abaixo).

### Fase 6 (issue #70) — o dual-write e a `Evidencia` saíram

A primeira fatia do recorte físico da Fase 6 removeu o dual-write e a `Evidencia` legada
(migração `0068`). O gatilho era ter um leitor: enquanto `process.custo_do_estado_atual` e
`ProcessDetailPage` liam o modelo fundido, ele não podia sair. A fatia repontou o custo para o
`Finding(epistemic_status=fact)` vivo do processo e migrou a tela para o split; sem leitor, a classe
foi apagada. **Não houve perda de dado**: o backfill da `0054` já traduzira cada `Evidencia` para o
par `Evidence`/`Finding`, e `legacy_evidencia` era só o ponteiro de reconciliação — removido junto,
com o comando `reconciliar_evidence_finding` que o lia. O gate operacional é rodar esse comando na
base alvo **antes** do deploy (`"Split reconciliado: todo legado tem par"`) e conferir backup
restaurável, na ordem que a issue #70 fixa. Consequência da ancoragem na conta: arquivar o processo
deixou de arquivar os achados — `Evidence`/`Finding` têm `process` `SET_NULL`, não são filhos do
processo, e uma afirmação sobre a operação do cliente sobrevive ao arquivamento do mapa que a citava.

### Fase 6 (issue #70) — as tabelas foram renomeadas

A segunda fatia (migração `0069`) pagou as quatro tabelas que a #67 fixou em `Meta.db_table`:
`core_client`→`core_account`, `core_opportunity`→`core_commercialopportunity`,
`core_processo`→`core_process`, `core_processoetapa`→`core_processstep`. Cada uma saiu por um
`AlterModelTable(table=None)`, que emite um `ALTER TABLE ... RENAME TO` e **preserva linha e pk** —
a garantia normativa da §2b, porque o One deriva chave de identidade de seis dessas pks e a persiste,
e o renome da tabela não toca o `id`. Fazer com modelo novo + migração de dados criaria pk nova e
desgrudaria os registros externos em silêncio; por isso a §2b proíbe esse caminho e por isso os pins
saíram do `Meta` sem nenhuma outra operação junto. A reversa reaplica o `db_table` legado. Com as
tabelas concluídas, a `/api/v2/` — onde morrem as **rotas** e as **chaves de payload** — pode
finalmente nascer.

### A `/api/v2/` nasceu — fatia 1 da #122, 04/09/2026

O mecanismo cabe em três frases. A versão sai do **prefixo do caminho**
(`apps/core/versioning.py`), sobre os mesmos viewsets e os mesmos serializers — nenhuma rota da v1
foi reescrita, porque o router da v2 é derivado do `registry` do da v1 com um dicionário de quatro
renomes de prefixo. O **mesmo** `ALIASES_DEPRECIADOS` que marca `deprecated: true` no `openapi.yaml`
passou a governar também a remoção dessas chaves na resposta da v2, lido por
`serializers.AliasesDaV1Mixin`. E chave legada mandada para a v2 — no corpo ou na query string —
recebe **400 dizendo o nome canônico**, nunca o silêncio com que o DRF ignora chave desconhecida.
Ver [ADR 0066](../adr/0066-a-api-v2-nasce-por-versao-no-caminho-e-um-mapa-so-governa-o-alias.md).

**Nascer a v2 não tira nenhuma linha da tabela de aliases vivos.** A regra 2 continua inteira: os
aliases vivem enquanto a `/api/v1/` viver, e o sunset dela é uma decisão que ninguém tomou. O que
mudou é que agora existe o lugar onde eles **não** estão.

O que **ainda vivia na v2** depois desta fatia — e que a fatia 3a, abaixo, mata — eram os aliases
que não passavam por serializer com `ALIASES_DE_ENTRADA`, então o mecanismo acima não os alcançava:

- `signer_email` no corpo da action `request-signature` e `outcome` no da `apply-gate` — aliases de
  **entrada de action**, normalizados na view (`views._signers_do_pedido`, `journey.apply_gate`);
- o dicionário cru de `GET /cobranca/painel/`, que emite `client`/`client_name` sem serializer;
- a chave `processos` da action de IA.

> Alcançá-los pela metade seria pior que declarar a lacuna — e por isso ficaram declarados até a
> fatia 3a resolvê-los de vez, e não meio resolvidos por um `if` avulso nesta fatia.

### A fatia 3a mata os quatro pontos que restavam, mais uma lacuna — issue #122, 04/09/2026

Os quatro pontos acima morreram: `signer_email` e `outcome` respondem 400 dizendo `signers` e
`decision` na `/api/v2/` (a recusa mora na view, porque a action não passa por serializer); o
painel de cobrança ganhou o par canônico (`account`/`account_name`) em toda linha, e a view tira os
dois legados quando a requisição é da v2; e a chave da action de IA **troca** por versão —
`processos` na v1, `processes` na v2 — em vez de conviver, porque duplicar a lista inteira pagaria
o corpo duas vezes.

**A lacuna que a fatia 1 registrou e não nomeou aqui**: um alias só-de-leitura mandado no *corpo*
da v2 (`POST /api/v2/projects/` com `client: 5`) era ignorado em silêncio — o campo é `read_only`,
o DRF descarta chave desconhecida, e a resposta 201 escondia que o vínculo não foi gravado. É o
mesmo modo de falha mudo que a decisão 3 da ADR 0066 recusou para `ALIASES_DE_ENTRADA`, só que pela
porta que aquele mecanismo não cobria — `AliasesDaV1Mixin.to_internal_value` passou a recusar
também as chaves de `ALIASES_DEPRECIADOS[componente]` presentes no corpo, com o nome canônico de
cada uma vindo de um mapa novo, `openapi_aliases.CANONICO_DA_CHAVE` (`None` para o par do §2d, cuja
frase aponta para `/kpis/` e `/measurements/` em vez de um nome de campo). A recusa é sempre por
**componente**, nunca por nome global de chave — `status` continua um campo real em `Invoice` e
`Engagement`, e só é recusado nos componentes que `ALIASES_DEPRECIADOS` lista.

Regra dos testes em `backend/tests/test_aliases_da_v2.py`. O que resta para as fatias seguintes da
#122: o contrato próprio `openapi-v2.yaml` (fatia 3b), a travessia da SPA para a `/api/v2/` (fatia
4) e as famílias de enum ainda em português (fatia 5) — nenhuma delas nasce antes da anterior.

### O contrato da v2 nasceu, e nasceu verdadeiro — fatia 3b da #122, 04/09/2026

`backend/openapi-v2.yaml` é o artefato: só caminhos `/api/v2/…` e componentes sem as chaves-alias
que `ALIASES_DEPRECIADOS` lista — a v2 não anuncia depreciação, ela simplesmente não emite a
chave. Gerado por um comando próprio, com o urlconf dedicado à geração
(`config.urls_v2_schema`) e `OPENAPI_ALVO=v2`, que é o que os hooks (`marcar_aliases_depreciados`/
`remover_aliases_do_contrato`, os dois em `openapi_aliases.py`) leem para saber qual dos dois
contratos estão montando. `info.version` marca a travessia: `2.0.0` na v2, `1.0.0` na v1, que não
mudou nesta fatia. Ver [ADR 0066](../adr/0066-a-api-v2-nasce-por-versao-no-caminho-e-um-mapa-so-governa-o-alias.md),
emenda da fatia 3b, e o teste em `backend/tests/test_openapi_aliases.py`.

### As chaves «client» que nunca tinham entrado no mapa — fatia 4a da #122, 04/09/2026

O contrato da fatia 3b nasceu verdadeiro sobre o mapa que existia, e foi lê-lo que mostrou o que o
mapa não tinha: `openapi-v2.yaml` ainda dizia `client_name` em onze componentes, `clients` na
resposta do grid de contas, `client`/`client_vertical`/`client_vertical_name` — chaves que
atravessaram a issue #67 inteira **sem serem alias de nada**, porque nenhuma delas era renome de
campo. Eram projeções: `client_name` sempre foi `source="account.name"`, `client_vertical` sempre
atravessou `engagement.account.vertical`. Não havendo coluna com o nome errado, o renome de classe
passou ao lado delas, e o que sobrou foi o pior caso do §2c — o nome errado na **chave de
payload**, que é onde ele mais dura. A decisão foi trazê-las todas para o mecanismo de sempre.

Três tratamentos, e a diferença entre eles é quem consegue executar a remoção:

- **Serializer** (`Case`, `Invoice`, `Process`, `DunningContact` — então `CobrancaContato` —,
  `CobrancaSuspensao`, e as duas
  chaves de vertical em `Project`): a canônica entra ao lado, a legada vira alias de leitura e a
  entrada do componente cresce em `ALIASES_DEPRECIADOS` — `AliasesDaV1Mixin` cuida do resto.
- **Dict cru** (o painel de cobrança, que a fatia 3a já resolvia, e a visão compacta da entrega, que
  entrou agora): o agregador emite os dois nomes e a **view** tira o legado na v2. O contrato,
  esse, perde a chave pelo mesmo mapa dos outros — `ALIASES_DEPRECIADOS_DE_DICT_CRU`, a segunda
  metade que os hooks do esquema leem. São dois dicionários porque a guarda "todo componente do
  mapa tem um serializer que o executa" só vale para o primeiro, e afrouxá-la para caber o
  `inline_serializer` desligaria justamente o defeito que ela pega.
- **Chave que troca** (`clients` → `accounts` em `GET /accounts/overview/`): não convive, pelo
  precedente de `processos`/`processes` da fatia 3a — ela envolve a lista inteira, e duplicá-la
  pagaria o corpo do grid duas vezes. O esquema troca junto, por `openapi_aliases.chave_da_geracao`.

O critério de aceite é o artefato, não o mapa: nenhuma propriedade de componente do
`openapi-v2.yaml` diz `client`, e a única exceção — `recebido_do_cliente` — está declarada abaixo.
A guarda é `test_nenhuma_chave_client_sobra_na_v2`, e ela varre o contrato inteiro em vez de iterar
o mapa, porque as quatro chaves desta fatia sobreviveram meses justamente por **não estarem** nele.
A regressão da §2c está em
`backend/tests/regression/test_o_alias_de_nome_de_conta_sobrevive_na_v1.py`.

> **Não houve migração, e a ausência é o achado.** O plano desta fatia previa um `RenameField` de
> `Project.client_vertical`; esse campo **nunca existiu** — o campo do modelo é `Account.vertical`
> (migração `0030`), e as duas chaves são projeção sobre ele. Registrado aqui porque "renomear a
> coluna" e "renomear a chave" são coisas diferentes desde a ADR 0052, e este é o caso em que só a
> segunda existia.

O que resta para as fatias seguintes da #122: a travessia da SPA para a `/api/v2/` (fatia 4b) e as
famílias de enum ainda em português (fatia 5) — nenhuma delas nasce antes da anterior.

### O recorte do ROI por conta troca de chave — fatia 4d da #122, 04/09/2026

`roi.by_client` de `GET /analytics/` era a última chave «client» que a fatia 4a deixou de fora, e a
razão de ter ficado está escrita no comentário que ela deixou no `@extend_schema` de
`AnalyticsView`: **tipá-la a faria aparecer no `openapi-v2.yaml`**, e `test_nenhuma_chave_client_sobra_na_v2`
varre o contrato inteiro reprovando toda propriedade com «client». O esquema, por isso, ficava
silencioso sobre ela — um objeto sem `additionalProperties: false` admite a chave —, que é o menos
ruim entre calar e mentir, mas não deixava de ser dívida: a única chave do `roi` sem tipo, num
contrato cujo critério de aceite é o artefato.

Ela **troca**, não convive, pelo precedente de `clients`/`accounts` da fatia 4a e de
`processos`/`processes` da 3a: a chave envolve a lista inteira do recorte, e duplicá-la pagaria o
recorte duas vezes. O par **não** entra em `ALIASES_DEPRECIADOS_DE_DICT_CRU` — aquele mapa marca a
propriedade como depreciada na v1 e a **remove** da v2, e aqui não há o que remover, porque a chave
da v2 já nasce `by_account`. É o mesmo motivo pelo qual `clients`/`accounts` também não está em mapa
nenhum.

**São dois mecanismos, e a fatia precisa dos dois.** `openapi_aliases.chave_da_geracao` lê
`OPENAPI_ALVO` e decide a chave na **geração do esquema**; `versioning.versao_de` lê a versão do
caminho e decide a chave **em runtime**. Nada liga um ao outro — `request.version` não existe na
hora de montar o contrato, e `OPENAPI_ALVO` não existe na hora de responder —, então mexer em só um
deles publicaria um contrato que discorda do corpo devolvido, que é a mentira publicada que a
decisão 5 da ADR 0066 recusa. Com os dois, `openapi.yaml` descreve `by_client` tipado e
`openapi-v2.yaml` descreve `by_account` tipado, e nenhum dos dois tem a chave do outro.

**A SPA fez parte da fatia, e não de uma seguinte.** `frontend/src/api.ts` já aponta para
`/api/v2`, então trocar a chave só no servidor deixaria `data.roi.by_account` `undefined`, e
`RoiTable` faz `rows.map` sem guarda — a tela de Indicadores **quebraria no render**, não
renderizaria uma tabela vazia. Aqui a falha é barulhenta por acidente da implementação do
componente, não por desenho: o mesmo descompasso numa tabela que tolerasse `undefined` sairia
como seção vazia e ninguém saberia. É a mesma travessia que a fatia 4a fez em `AccountsPage`
quando `clients` virou `accounts`. O **rótulo** da tela continua dizendo "ROI por cliente": "Cliente" é rótulo legítimo de
interface para a conta em `lifecycle_status=active` (`language-map.md` §4), e o que morre na
`/api/v2/` é a chave de payload, nunca o texto.

A regressão está em `backend/tests/test_aliases_da_v2.py`
(`test_o_recorte_do_roi_por_conta_troca_a_chave_por_versao`), e ela cria conta com projeto, receita
e custo de propósito: um recorte vazio sai `[]` nas duas versões e passaria o teste sem provar nada
sobre a chave que o envolve.

## As três regras

### 1. Alias é dívida com data

Enquanto o alias vive, **campo novo e código novo usam o nome canônico apontando para o modelo
legado**. É o que a Fase 1 fez: `Qualification.account` é uma `ForeignKey` para o modelo que ainda
se chamava `Client` quando ela foi escrita. O nome do campo é o compromisso público; o nome da
tabela é detalhe que a Fase 6 acerta.

A #67 não revoga essa regra — ela reduz o alcance dela. Depois de cada fatia, o modelo legado que
aquela fatia renomeou deixa de existir sob o nome antigo, e a regra passa a valer só para os que
ainda não foram renomeados. Enquanto isso, um campo canônico apontando para um modelo já renomeado
é só um campo com o nome certo apontando para a classe certa, que é onde tudo isto queria chegar.

Escrever `Qualification.client` "porque o modelo se chama Client" seria criar o alias de novo, em
código que nasceu depois da decisão — e é exatamente isso que a regra `client-como-organizacao`
reprova. Ela casa `client`, nunca `account`.

### 2. `/api/v1/` não quebra

A remoção dos aliases de rota é a **`/api/v2/`**, e a v2 só nasce depois de a Fase 6 concluir os
renomes físicos. Até lá `/api/v1/clients/` e `/api/v1/opportunities/` respondem como sempre
responderam, com o mesmo payload — inclusive depois de o modelo Python trocar de nome, porque
`basename` e `queryset` do router são independentes do nome da classe.

**Não há data de calendário; há ordem de fases.** Uma data que ninguém pode cumprir vira um
comentário `# TODO(2026)` que sobrevive a três reorganizações do time. A ordem, não: a Fase 6 não
começa antes da 5, e a v2 não nasce antes da 6.

### 2b. Seis pks são identidade pública — e a Fase 6 tem de preservá-las

**Normativo.** Todo renome de modelo desta migração se faz com `RenameModel`, que preserva tabela,
linhas e **pk**. Nunca com modelo novo mais migração de dados, ainda que a tabela nova ficasse mais
limpa.

Na #67 ele preserva ainda mais do que isso, e é o que autoriza antecipar o renome de classe: com
`Meta.db_table` fixado no nome legado **antes** da operação, `RenameModel` não emite SQL nenhum —
`alter_db_table` abre com `if old_db_table == new_db_table: return`. Cada fatia escreve as duas
operações na ordem, e a primeira é no-op por já ser verdade:

```python
migrations.AlterModelTable(name="client", table="core_client"),
migrations.RenameModel(old_name="Client", new_name="Account"),
```

Invertê-las, ou omitir a primeira, faz o banco renomear a tabela e renomeá-la de volta — duas
`ALTER TABLE` para chegar onde já se estava, num caminho em que falhar no meio deixa a tabela com
o nome errado. Ver ADR 0052.

A proibição não é estética. **Estas pks saíram deste repositório.** O snapshot do portal
(`portal.build_snapshot`) emite onze ids, e o One deriva chave de identidade de seis deles e a
**persiste** — medido no código de lá em 28/08/2026, não estimado:

| pk daqui | o que o One persiste | o que quebra se ela mudar |
| --- | --- | --- |
| `Client` (→ `Account`) | `organization.slug` = `biahflow-client-{id}` | organização órfã: o cliente perde acesso ao projeto, em silêncio |
| `Project` | `project.slug` = `biahflow-{id}` | o projeto inteiro é recriado ao lado, com membership, documentos indexados e histórico apontando para a linha velha |
| `Engagement` | `engagement.slug` = `biahflow-engagement-{id}` | duplicata do programa; os projetos ficam apontando para o antigo |
| `ProjectDeliverable` | `phase_deliverable.external_ref` | **o pior dos seis — ver abaixo** |
| `Document` | `document.external_id` | documento duplicado e reindexado; citação já dada ao cliente passa a apontar para a linha antiga |
| `Pendencia` | `pending_item.external_ref` | pendência duplicada, e o cliente recebe o aviso de novo |

**O entregável é o pior, e vale saber por quê.** O `external_ref` dele é o caminho da rota de
aceite do One (`/api/v1/me/deliverables/{external_ref}/acceptance`) e é por ele — **não por chave
estrangeira** (ADR 0077 de lá) — que a tabela de aceites se liga ao entregável. Aquela tabela
guarda a decisão do cliente: quem aprovou, quando, e o comentário de quem pediu ajuste. Se a pk
mudar, o registro da aprovação não some: ele **desgruda**, e passa a ser o aceite de um entregável
que ninguém mais acha. É o único dos seis em que o dado órfão é uma afirmação que o cliente fez.

Duas notas que completam o inventário, e que existem para ninguém generalizar demais:

- **`Meeting` não guarda id externo de propósito** — o One a recria por inteiro a cada sync. A pk
  de reunião pode mudar à vontade.
- **`notification.dedupe_key` congela alguns desses ids na linha** (`document:{external_id}`,
  `pending:{external_ref}:opened`). A consequência ali é de outra natureza e menor: não há órfão,
  há **reaviso** — o cliente recebe de novo um aviso que já tinha lido.

Os cinco ids restantes que o snapshot emite (`ProjectPhase`, `Milestone`, `Decisao`,
`DigitalEmployee`, `Meeting`) **não** são persistidos hoje do lado de lá. Isso é uma medição, não
uma garantia: se o One passar a derivar chave de um deles, ele entra nesta tabela **antes** de
entrar no código. A fronteira que importa é o snapshot — id que atravessa é id que alguém pode
começar a guardar.

O modo de falha, em todos os casos, é o pior possível: não é erro, é silêncio. Nenhum dos dois
lados levanta exceção, e o registro duplicado parece apenas um cadastro novo.

A projeção `Project.client` foi removida na Fase 6 (migração `0070`). A invariante de igualdade
entre `project.engagement.account_id` e o antigo `project.client_id` já não precisa ser guardada —
a fonte canônica é a única que resta.

**Identidade tem de ser a pk estável da linha**, nunca valor recalculável — slug, hash do nome,
número de sequência por conta. Identificador que alguém pode recalcular é identificador que alguém
vai recalcular diferente.

Regra prática: **em toda travessia de nome, a linha e a pk sobrevivem; só o rótulo muda.** O
renome de tabela da `0069` seguiu isso à risca — `AlterModelTable` não toca a pk. Uma migração
que crie linha nova para o mesmo fato precisa dizer, no próprio arquivo, como o consumidor externo
continua achando o registro antigo.

### 2c. Campo renomeia; **chave de payload** não

A #67 renomeia o campo junto da classe — `Document.opportunity` vira
`Document.commercial_opportunity`, `Contact.client` vira `Contact.account`, `Evidencia.etapa` vira
`Evidencia.step`. É `RenameField`, que
renomeia coluna e preserva linha e pk.

**O que não muda é o corpo da requisição.** Cada chave legada continua saindo no `GET` e continua
sendo aceita no `POST`/`PATCH`, com um mecanismo só para todas elas, e não uma cópia por
serializer:

- **leitura** — a chave antiga é um campo declarado com `source=` apontando para o canônico,
  `read_only=True`. As duas saem, com o mesmo valor.
- **escrita** — um mixin de serializer normaliza a chave antiga para a canônica antes da
  validação. Quando as duas vêm no mesmo corpo, **a canônica vence**: um corpo com as duas é
  confusão do chamador, e resolver pela nova é o que não trava quem já migrou. É a mesma regra que
  `apply-gate` usa desde a fatia 1.

O mecanismo é um só porque a alternativa é `if` de compatibilidade espalhado por dezessete
serializers, e o décimo oitavo esquece — que é a mesma razão de `StatusDot.tsx` guardar os mapas de
estado num lugar em vez de um por tela (ADR 0026).

Cada alias de escrita precisa de regressão. Sem ela, a linha do serializer não tem chamador
**dentro** do repositório — a SPA escreve o nome canônico — e a próxima varredura atrás do último
resquício do nome antigo a remove achando que está pagando dívida. Estaria quebrando a `/api/v1/`
em silêncio, no único lugar onde nada aqui dentro fica vermelho.

**A depreciação, desde a issue #67, é visível no próprio contrato — não só nesta página.** Até
aqui, quem lia `openapi.yaml` ou o Swagger de `/api/docs/` não tinha como distinguir `client` de
`account`: as duas chaves apareciam como campo comum, sem nenhum sinal de que uma delas morre na
`/api/v2/`. `backend/apps/core/openapi_aliases.py` declara `ALIASES_DEPRECIADOS`, o espelho manual
desta seção para o vocabulário do OpenAPI (componente do schema → propriedades-alias), e um
`POSTPROCESSING_HOOKS` em `SPECTACULAR_SETTINGS` (`backend/config/settings.py`) marca
`deprecated: true` em cada uma na geração do esquema. É manual e não inferido de `source=` por
regex, de propósito: a maioria dos `source=` do repositório é projeção legítima, não alias — marcar
os dois igual mentiria sobre o que vai morrer. Um teste (`backend/tests/test_openapi_aliases.py`) garante que
o mapa não fica atrás do código nem apodrece com entrada morta.

### 2d. A exceção da regra 2: `kpi_baseline` e `kpi_current` pararam de **aceitar** escrita

A regra 2 diz que a `/api/v1/` não quebra. Esta é a única exceção viva, e ela é **deliberada,
aprovada num gate humano e datada**: a decisão **C1** do DAP `docs/design/dap-prove-e-valor-r1/`
(28/08/2026), implementada pela ADR 0055 e pela FDD 049.

O que aconteceu: `DigitalEmployee.kpi_baseline` e `kpi_current` eram colunas do ativo de solução e
viraram `Measurement` de um `KPI`. Se as duas chaves continuassem **graváveis**, passariam a existir
dois lugares escrevendo a mesma medição, e a que valeria seria a última salva — a fonte da verdade
voltaria a ser o ativo de solução, que é precisamente o que a extração desfaz.

| Verbo | Antes | Agora | Por quê |
| --- | --- | --- | --- |
| `PATCH /digital-employees/{id}/` com `kpi_baseline`/`kpi_current` | gravava as colunas | aceito com 200 e **ignorado** | campos derivados, só de leitura — a forma dos três snapshots congelados do `Case` (ADR 0020) |
| `POST /projects/{id}/digital-employees/from-blueprint/` com `kpi_baseline` | gravava a coluna | chave fora do corpo aceito e do esquema | `blueprints.instantiate` perdeu o parâmetro |

**A leitura não quebrou, e não vai quebrar antes da hora.** As duas chaves continuam saindo no
`GET`, derivadas da baseline viva e do `Outcome` mais recente do KPI referenciado — `null` quando
não há, nunca zero. Elas morrem na `/api/v2/`, como toda chave de payload (§2c e ADR 0052), e é por
isso que entram na tabela de aliases vivos acima.

Como todo alias, a leitura precisa de regressão, e pelo motivo da §2c: um campo derivado sem
chamador **dentro** do repositório — a SPA lê, o backend não — é o que a próxima varredura atrás de
campo morto remove achando que paga dívida. Ela está em
`backend/tests/regression/test_a_medicao_do_ativo_sobrevive_na_v1.py`.

### 3. `legacy_` é o escape reservado

`legacy_opportunity` e `legacy_evidencia` são nomes **legítimos em código novo**, e a guarda os
deixa passar de propósito. Um campo com esse prefixo declara, no próprio nome, que aponta para o
registro antigo — que é o oposto de esconder o mapeamento atrás de um nome bonito. É o que permite
backfill e leitura dupla durante a transição sem que a coluna nova finja ser a canônica.

O prefixo não é permissão geral: `legacy_` diz "isto mapeia para o legado", não "isto está isento".
Um campo `legacy_client` que na verdade é a organização corrente continua sendo defeito — só que um
defeito que o revisor humano precisa pegar, porque a guarda não consegue.

## O que a guarda **não** reprova, e por quê

Referência ao nome legado é livre: `self.opportunity`, `opportunity_id`, `Client.objects.filter(…)`
e `from .models import Client` são uso do modelo que existe hoje, e o modelo existe hoje por
decisão. A guarda casa **declaração** — o ato de batizar. O detalhe está na docstring de
`backend/tests/test_vocabulario.py` e a decisão, na [ADR 0049](../adr/0049-a-ontologia-entra-pela-linguagem-antes-do-schema.md).

A única exceção é `GateOutcome`/`gate_outcome`: ali o identificador inteiro está errado em qualquer
posição, porque não existe uso legítimo do nome antigo.

**Chave de payload de agregação também não é batismo, e `opportunities`/`opportunity_count` são o
caso examinado.** As duas ficaram visíveis no contrato quando o PR #125 tipou os dicts crus, e
parecem violar a §5 do language-map — que bane `Opportunity` sem qualificador. Não violam, por três
razões que convém deixar escritas para a próxima varredura não as levantar de novo:

1. A invariante §6.1 enumera o que não pode conter o termo sem qualificador: **modelo, campo, rota,
   componente, prop**. Chave de payload não está na lista, e a omissão não é descuido — é a mesma
   fronteira da §2c, que separa o nome do campo (renomeia) do nome da chave (só na `/api/v2/`).
2. O que a regra exigia já foi feito: o componente do esquema chama-se `FunnelCommercialOpportunities`,
   e não `FunnelOpportunities`. O comentário no `@extend_schema` de `AnalyticsView` registra a
   escolha e diz por que a chave ficou.
3. **Elas nunca tiveram nome errado.** `opportunity_count` sai de `Count("opportunities")`, o
   `related_name` das FKs de `CommercialOpportunity`; `opportunities` é o bloco `open`/`won`/`lost`
   do funil comercial, onde o qualificador é o próprio funil. Não são alias de nada — não há nome
   canônico anterior nem posterior —, e renomeá-las na v2 criaria dívida em vez de pagar: um par
   novo para manter, sem um lado legado para aposentar.

`test_vocabulario.py` confirma isso por construção, e não por tolerância: nenhuma das suas regras
casa `campo = serializers.…`, dict literal ou `.values(...)`. Uma chave de payload jamais poderia
ser reprovada por ele, nem se fosse português puro — que é exatamente por que a lista de "termos
ainda sem nome canônico" acima precisa existir à mão.

## Termos ainda sem nome canônico

`Pendencia`, `Decisao`, `Risco` e o resto da família `Cobranca*` (`CobrancaSuspensao` e o
`resource`/viewset dela, o módulo `cobranca.py`, a rota `/cobranca/` com o seu `basename`, a flag e
o `kind` de notificação `cobranca`) estão em português no modelo e **a Ontology v1 não os cobre** —
não há para onde renomeá-los ainda. Eles estão na allowlist mesmo assim, e isso é deliberado: sem a
linha, a ausência de decisão viraria ausência de dívida.

`CobrancaContato` **saiu desta lista na fatia 5.4 da issue #122** (04/09/2026): virou
`DunningContact`, com a tabela, o campo (`dunning_step`) e os cinco valores juntos, e com o
`resource` do viewset (`cobranca` → `dunning_contact`). Ele saiu por um caminho que os vizinhos não
têm: o nome **não** existia no language-map, e foi **cunhado neste espelho** pelo precedente de
`DunningSignal` — ver a nota da fatia 5.4 acima. `Pendencia`, `Decisao`, `Risco` e o resto da
família continuam sem nenhum, e nenhum deles tem campo já cunhado a puxar a coinagem, que é
exatamente o que faltava aqui e não falta lá.

**As chaves `proximo_degrau` / `proximo_degrau_display` / `proximo_degrau_em` do dict cru do painel
entram no lugar dele**, ao lado de `sinal_*` e `satisfacao_*` logo abaixo e pelo mesmo motivo: o
language-map cunha `dunning_step` como nome de **campo do contato**, não como nome de chave do
painel, e o painel é um agregador de faturas, não a serialização do contato. Sem canônico elas não
são alias de nada: não cabem em `ALIASES_DEPRECIADOS`, não morrem na `/api/v2/` e continuam saindo
nas duas versões. **O valor delas atravessou** — é o do enum —, e é a mesma frase de sempre: o
valor atravessou, a chave espera coinagem.

`Satisfacao` **saiu desta lista na fatia 5.3 da issue #122** (04/09/2026): virou
`SatisfactionRecord`, com a tabela e os dois enums de valor juntos. Ela estava aqui por um motivo
diferente do dos vizinhos, e é o que explica ter saído antes deles: o language-map §4 já enumerava
`satisfaction_record.source` e `satisfaction_record.level`, então o **nome** existia — o que
faltava era o código dizê-lo. `Pendencia`, `Decisao` e `Risco` continuam sem nenhum.

**Os campos `nivel` e `fonte` do registro de satisfação entram no lugar dela**, com as duas chaves
derivadas (`nivel_display`, `fonte_display`), e pelo motivo de `recebido_do_cliente` abaixo: o
language-map cunha `satisfaction_record.level` e `.source` na tabela de **enums** — a linha que
enumera os valores —, e nenhuma seção cunha o nome do *campo*. Sem canônico, eles não são alias de
nada: não cabem em `ALIASES_DEPRECIADOS`, não morrem na `/api/v2/` e continuam saindo e sendo
aceitos nas duas versões. É a mesma forma de `sinal_kind`/`sinal_display` e `satisfacao_nivel`/
`satisfacao_fonte`/`satisfacao_dias` no dict cru do painel de cobrança, e a frase que vale para as
três famílias é uma só: **o valor atravessou, a chave espera coinagem.**

`Activity.CobrancaSinal` **saiu desta lista na fatia 5.2 da issue #122** (04/09/2026): tem nome
canônico (`DunningSignal`) e código que o usa desde essa fatia, então continuar aqui seria negar
uma decisão já tomada. Era o único membro da família `Cobranca*` com nome próprio já cunhado no
language-map (`activity.dunning_signal`, §4) — o que faltava era a classe, o campo e o valor
persistido atravessarem, e a fatia 5.2 pagou os três juntos (D10).

`recebido_do_cliente` — a chave do painel de cobrança que diz quanto a conta já pagou — entra na
mesma lista, e por escrito, desde a fatia 4a da #122. Ela **não é alias de `client`**: é um nome
que nunca teve canônico, então não cabe em `ALIASES_DEPRECIADOS` nem morre na `/api/v2/` por conta
disso. É a única chave com «client» que a guarda do contrato da v2 tolera
(`test_nenhuma_chave_client_sobra_na_v2`), e a isenção tem teste próprio para não sobreviver ao dia
em que a fatia 5 traduzir a família de cobrança inteira. **A fatia 5.4 fechou a série sem alcançá-la**,
e isso é informação, não pendência esquecida: o que a fatia 5 traduziu foram os quatro **enums** que
a D10 marcou, e `recebido_do_cliente` é chave de dict cru sem canônico — a mesma categoria de
`proximo_degrau*` acima. Ela continua esperando coinagem.

`parcelas`, `valor`, `nao_apurado` e `sustentacao` — as quatro chaves do custo do estado atual de
um processo (`ProcessCost` e `ProcessCostLine`, servidas em `Process.custo`) — entram na lista por
esta linha, e o motivo de estarem chegando só agora é o que as torna interessantes: **elas
existiam desde a FDD 039, mas viviam atrás de um `DictField()` sem `child=`**. Não estavam
escondidas de propósito; estavam invisíveis ao contrato, e por isso invisíveis a toda varredura que
lê o `openapi.yaml`. O PR #125 as tipou, e tipar é o que as trouxe para cá.

Nenhuma das quatro é alias: não há nome inglês do outro lado esperando, e por isso elas não morrem
na `/api/v2/`. `sustentacao` é o caso mais claro — ela carrega os valores `sustentado`/`hipotese`,
que são vocabulário epistemológico da casa e vizinhos diretos do `epistemic_status`
(`fact`/`hypothesis`/`unknown`) que **já** está em inglês no `Finding`. É a mesma distinção dita em
duas línguas em dois lugares, e a coinagem vai ter de resolver isso junto, não chave a chave.

O caminho é o da §8 do language-map: o termo entra primeiro na página do Notion, depois aqui,
depois no Pulse.
