# ADR 0003 — Webhook para o portal do cliente

**Status:** aceito

## Contexto

O portal do cliente (repositório `portal_cliente`) é um serviço externo separado que exibe
o andamento do projeto para o cliente. Ele precisa do status mantido aqui (Project,
Milestone, Task, Document), mas não deve reimplementar esse cadastro — o Biahflow é a fonte
da verdade.

## Decisão

O Biahflow **emite webhooks** quando muda qualquer objeto que o snapshot carrega (incluindo
arquivamento), com entrega assíncrona e **assinatura HMAC** por segredo compartilhado. A lista
cresceu com o produto e hoje é: Project, Milestone, Task, Document, Meeting e Pendencia (ADR 0005),
mais ProjectPhase e ProjectDeliverable — a jornada, que o snapshot já levava desde esta ADR mas
nenhum sinal anunciava, deixando a barra "Você está aqui" do portal dependente do salvamento de
outro objeto. **O que entra no snapshot precisa de emissor**, sob pena de o portal exibir um estado
que já mudou. Um
**token de leitura** (escopo read-only) permite ao portal fazer backfill/reconciliação via
`GET /api/v1/`. Nenhum dado comercial (Opportunity, PipelineStage, valores) é enviado ao
portal. As mudanças são **aditivas** e preservam o contrato `/api/v1/`.

## Consequências

O portal recebe mudanças em quase tempo real sem duplicar digitação; o Biahflow continua
como sistema de registro. É preciso configurar `PORTAL_WEBHOOK_URL` e `PORTAL_WEBHOOK_SECRET`
e proteger o token de leitura. Ver `portal_cliente/docs/adr/0006`.


## Emenda (ADR 0018, 06/08/2026)

A flag `portal` deixou de ser controlada **apenas** por ambiente. Ela continua nascendo do par
`PORTAL_WEBHOOK_URL` + `PORTAL_WEBHOOK_SECRET`, mas passou a ser alternável em runtime na tela
Configurações, e `portal.emit()` consulta `flags.is_enabled("portal")` antes de agendar a entrega.

O motivo é operacional: pausar a emissão durante um incidente do portal exigia deploy. A entrega
segue best-effort e sem retentativa — desligar e religar **não** reenvia o que se perdeu no meio, e
a recuperação continua sendo o backfill manual descrito acima.


## Emenda (FDD 025, 07/08/2026)

O snapshot passou a carregar `archived_at` do projeto, e a rota de leitura
(`GET /api/v1/portal/projects/{id}/snapshot/`) **serve projeto arquivado**, com 200.

"O que entra no snapshot precisa de emissor" já valia para o arquivamento — `archive()` é um
`save()` e emite. Faltava a outra ponta: a rota escondia o arquivado, então a busca disparada pelo
próprio webhook levava 404, que o portal não distingue de "este id nunca existiu". O estado que já
mudou continuava na tela do cliente, agora por omissão do lado que deveria contá-lo. O 404 desta rota
volta a significar só "não existe", e quem declara o encerramento é o `archived_at` do snapshot.

Mudança **aditiva** ao contrato `/api/v1/`: um campo novo, e um id que antes respondia 404 passando a
responder 200.


## Emenda (07/08/2026) — o emissor que faltava, e o único `post_delete`

Duas lacunas na regra desta ADR, "o que entra no snapshot precisa de emissor".

**`DigitalEmployee` entrou no snapshot sem emissor nenhum.** Ele não está na lista da Decisão acima
porque chegou depois dela, e ninguém voltou aqui: criar, mexer no KPI e **arquivar** um funcionário
digital não avisavam o portal. Arquivar era o pior dos três — `archive()` tira a linha do snapshot,
de modo que o roster do cliente ficava com alguém que este lado já considerava fora. Agora tem
`post_save`, sem guarda de `created`: o cadastro é um a um pela tela, não é materializado em laço
como a jornada, então não há enxurrada a conter.

**A exclusão definitiva não avisava, e agora avisa — só do projeto.** `emit("deleted", "project", …)`
num `post_delete` de `Project` é o único `post_delete` do repositório, e a escolha tem medição
atrás. Exclusão de filho não é alcançável pelo produto: os nove viewsets que o portal enxerga são
`ArchiveModelViewSet` (o `DELETE` da API **arquiva**), o Django admin não registra entidade de
projeto nenhuma, e `retention.executar()` só alcança linha já arquivada — que a essa altura já saiu
do snapshot e já foi propagada pelo webhook do arquivamento. Sobra o projeto, apagado por shell ou
migração de dados, e sem aviso o portal ficava com ele marcado como **ativo para sempre**: nenhum
evento sairia, e não haveria evento seguinte daquele projeto, porque não há mais projeto.

Registrar `post_delete` nos filhos custaria mais do que resolve: numa cascata o coletor do Django
apaga filho primeiro e `on_commit` roda na ordem de registro, então cada filho agendaria um webhook
**antes** do webhook do projeto — cada um provocando uma busca de snapshot que já responde 404.
Como está, um projeto inteiro sai daqui como **um** aviso, e há teste que reprova se isso mudar.

O custo declarado: a entrega segue best-effort e sem retentativa, e um `deleted` perdido é
**definitivo** — ao contrário de um `updated`, que o próximo salvamento daquele projeto corrige.


## Emenda (07/08/2026) — a data de aceitação do artefato, e a linha "nenhum dado comercial"

Terceira lacuna na mesma regra, e desta vez ela estava um degrau antes: o fato **não entrava no
snapshot**, então não havia sequer o que emitir.

O portal do cliente instrumentou um funil de onboarding (RFC 001 de lá) e listou entre os degraus
"artefato aceito (`sent → accepted`)". Ele nasceu com o degrau **declarado ausente do enum**, e a
razão escrita no código de lá aponta para cá: *"o snapshot do Biahflow não carrega nada de
artefato […] ele entra quando o outro lado o afirmar"*. Aqui o dado existe inteiro desde a FDD 016
— `Artifact.status`, `Artifact.decided_at` carimbado no `save()`, e o e-sign fechando o contrato
sozinho quando o signatário assina —, e o docstring do próprio modelo diz para que ele serve:
*"permite medir onde a jornada trava entre uma etapa e a seguinte"*. O que faltava era atravessar.

**O que atravessa é um instante e nada mais.** `artifact_accepted_at` é a data da **primeira**
aceitação daquele cliente. Não vai `kind` (diria em que etapa do funil comercial ele está), não vai
`title`, não vai `content` (o texto que a IA daqui redige é dado interno da casa), não vai valor e
não vai contagem.

Isso mantém a frase da Decisão acima — *"nenhum dado comercial (Opportunity, PipelineStage,
valores) é enviado ao portal"* — verdadeira, e vale dizer por quê em vez de deixar por conta da
leitura: nenhuma das três coisas nomeadas cruza. O que cruza é a data em que **o próprio cliente
aprovou** alguma coisa, que é um fato dele sobre ele. Do lado de lá ela também não chega a tela
nenhuma do cliente: alimenta uma tabela que o papel de requisição do portal não consegue ler.

**O cálculo é por cliente, não por projeto**, porque o funil de lá é escopado por organização e um
cliente pode ter vários projetos. Os dois vínculos possíveis do artefato (`project` e
`opportunity`) chegam ao mesmo `Client`, e é pelo lado da oportunidade que o contrato quase sempre
vive — a aceitação dele é o que *cria* o projeto depois.

**O emissor tem um limite declarado.** `post_save` de `Artifact` emite só em `ACCEPTED`: rascunho,
revisão e envio mudam a linha várias vezes sem mover degrau, e `REJECTED` também não move, porque
o funil mede o que o cliente **recebeu**. O projeto é resolvido — o do artefato quando há, senão o
projeto vivo mais antigo do mesmo cliente, um só e nunca fan-out. E quando não há projeto nenhum
**nada é emitido**, o que é limite e não esquecimento: sem projeto o portal ainda não conhece
aquela organização, e como `build_snapshot` calcula o campo sobre o cliente, o fato chega inteiro
no primeiro snapshot depois que o projeto nascer.

## Emenda (FDD 032, 12/08/2026) — o racional da decisão, e por que ele atravessa

`decisions[]` entra no snapshot, e com ele entra **texto**: o `rationale` de cada decisão. É a
segunda qualificação que a frase "nenhum dado comercial é exposto" precisa, e ela merece ser escrita
porque contraria um corte que este arquivo já fazia de propósito.

**A `Pendencia` leva título e estado. O `description` dela fica de fora.** A assimetria é
deliberada: uma pendência é um item de acompanhamento, e o que o cliente precisa saber dela é se
está aberta e de quem é a bola. Uma decisão é outra coisa — **uma decisão sem o porquê é um
título**. O que ela responde é *por que escolhemos isto e não aquilo*, e é a única pergunta desta
lista que o cliente não consegue reconstituir sozinho meses depois: hoje a resposta mora numa
transcrição que ele não tem, ou na memória de quem estava na sala.

**O limite continua onde estava, e ele é o estado.** Sai o racional da decisão **publicada** — nunca
o rascunho, que é onde a extração por IA grava, e nunca anotação interna. `status=published` é o
filtro do `build_snapshot`, e é ele que faz a IA caber nesta integração sem que um palpite de modelo
alcance a tela do cliente antes de uma pessoa publicar.

**A proveniência atravessa como pk, não como texto.** `meeting_id` é a chave da reunião daqui, e o
portal a recasa com a reunião que ele acabou de espelhar. A transcrição em si continua sem
atravessar — o snapshot informa `has_transcript` e nada mais, como desde a FDD 005.

E a regra que abre esta ADR ganhou finalmente um portão derivado, em vez de seis asserções escritas
à mão: ver a ADR 0027.
