# FDD 025 — Arquivar e restaurar pela interface

## Jornada

O portal arquiva desde sempre: `TimestampedModel.archive()` grava `archived_at`, e
`ArchiveModelViewSet` esconde o arquivado da listagem. Dezesseis modelos usam esse campo. Mas o
recurso existia só pela metade, e as três metades que faltavam apareceram juntas quando um admin
pediu para "excluir um lead, um cliente, um projeto".

**Não havia botão.** Cliente, oportunidade e projeto não tinham como ser arquivados por nenhuma
tela — o `DELETE` existia na API e ninguém o alcançava. Lead, documento e serviço tinham botão.

**Não havia volta.** `archived_at` não aparece em serializer nenhum, não há endpoint de
restauração, e o registro some de toda listagem. Desfazer exigia Django admin ou `manage.py shell`.
Dar botão de arquivar cliente e projeto sem isso seria transformar um clique acidental em problema
de infraestrutura.

**Não havia confirmação.** Os sete botões de excluir do portal disparavam o `DELETE` no clique.

E havia um defeito silencioso por baixo: o soft delete é por registro, e nada cascateia.
`ProjectViewSet` e `OpportunityViewSet` filtram o próprio `archived_at` e nunca o do cliente. Então
arquivar um cliente sumia com ele da tela de Clientes e **mantinha** os projetos e oportunidades
dele nas listas, cada um exibindo o nome de um cliente que a interface já não mostra. O backend
respondia 204, em silêncio.

## Regras

- **"Arquivar" ≠ "Excluir".** O portal já usava os dois termos, e agora a distinção é regra:
  *Arquivar* para soft delete (lead, cliente, oportunidade, projeto, documento, serviço); *Excluir*
  só onde o `DELETE` é real — etapa do pipeline e fase da jornada, que são `ModelViewSet` sobre
  modelos sem `archived_at`. Um botão "Excluir" que arquiva ensina a pessoa errada a coisa errada.
- **Toda ação destrutiva pede confirmação.** `ConfirmDialog` (`components/Modal.tsx`) sobre o mesmo
  `Modal` que já resolve foco preso e `Escape` (FDD 022). O texto diz o que acontece e se dá para
  desfazer — não "tem certeza?".
- **Arquivar não pode deixar órfão visível.** `ClientViewSet.perform_destroy` recusa com **409**
  enquanto houver projeto ou oportunidade ativos, e a mensagem diz quantos: quem tentou precisa
  saber o que fazer antes. `OpportunityViewSet.perform_destroy` recusa enquanto o projeto convertido
  estiver **ativo** — ele é o outro lado dela, e a conversão não roda duas vezes.
- **Toda recusa precisa ter saída, e a instrução dela precisa ser verdade.** É a outra metade da
  regra acima, e faltava. A guarda da oportunidade testava `hasattr(instance, "project")`, que
  continua verdadeiro com o projeto arquivado — a relação reversa não some com o `archived_at`. A
  mensagem mandava arquivar o projeto e isso não desbloqueava nada; a oportunidade também não
  reconverte (o `OneToOneField` segue ocupado) e, viva, ainda bloqueava o cliente. Uma recusa cujo
  caminho de saída não existe é pior que nenhuma recusa: manda a pessoa trabalhar à toa. A condição
  passou a ser o **estado** do projeto, e a corrente projeto → oportunidade → cliente fecha.
- **Estado em vez de ação que não existe.** Com o projeto arquivado, `OpportunitySerializer` expõe
  `project_archived` e o card do pipeline mostra "Projeto arquivado", sem link. `project` continua
  preenchido de propósito: anulá-lo faria a tela voltar a oferecer "Criar projeto", que responderia
  409 — trocaria um link morto por um botão morto.
- **409, não 400.** O pedido está bem formado e a permissão existe; o que impede é o **estado**, e é
  ele que muda para o pedido passar. `StateConflict` em `views.py` (nasceu `ArchiveConflict`; ver
  a seção sobre os dois "Excluir" de verdade).
- **O contato acompanha em vez de bloquear.** Ninguém lista contato fora do cliente, então ele não
  produz órfão visível — mas deixá-lo ativo restauraria depois um cliente com contatos vivos pela
  metade. Arquiva junto, na mesma transação.
- **Projeto não tem guarda.** Tarefas, marcos, reuniões e pendências só são listados via
  `?project=`, então não vazam para lugar nenhum.
- **`?archived=1` e `POST /unarchive/` valem para todo `ArchiveModelViewSet`.** A ação resolve o
  objeto pela queryset **crua**: `get_object()` passa pelo `get_queryset()`, que esconde justamente
  o que se quer restaurar, e devolveria 404 em toda restauração. A permissão de objeto continua
  sendo a mesma do `destroy` — Entrega não restaura projeto de que não participa.
- **A política de permissão não mudou.** `RolePermission` não distingue `DELETE` de `PATCH`: quem
  edita, arquiva. A restrição a admin é da interface (`user?.is_admin`), não da API.
- **A aba Arquivados fala com o viewset, não com o agregador.** Em Clientes ela chama
  `/clients/?archived=1` e não `/clients/overview/`: o overview é montado à mão e não passa pelo
  `get_queryset` do `ArchiveModelViewSet`, então nunca enxergaria o arquivado.
- **Quem promete restauração precisa oferecê-la.** Os **sete** recursos arquiváveis pela interface
  têm caminho de volta: aba em Clientes e Projetos, chip de filtro em Leads, alternador em
  Documentos, Serviços e no roster de Funcionários Digitais, e uma lista que substitui o quadro em
  Comercial — o kanban não comporta uma coluna de arquivadas. Na primeira entrega três diálogos
  diziam "pode ser restaurada depois" sem que houvesse onde, que é a mesma classe de mentira que a
  FDD 024 existe para consertar.
- **E o `DigitalEmployee` ficou de fora até 07/08/2026.** A regra "não havia botão" valia para ele
  também, e passou despercebida porque ele mora **dentro** do detalhe do projeto, não numa listagem
  própria — o levantamento olhou as telas de lista. O viewset é `ArchiveModelViewSet` desde sempre e
  a tela não tinha arquivar, restaurar nem edição: dos oito campos do serializer, o formulário
  alcançava dois. Como seis deles cruzam ao painel do cliente pelo snapshot (ADR 0003), o efeito ia
  além do arquivamento — a narrativa de valor do "produto central" não tinha como ser escrita por
  tela nenhuma. Ver FDD 026.
- **Diálogos empilham.** O `Modal` mantém uma pilha por **ordem de abertura** (não por ordem no
  JSX): o topo recebe o `zIndex` maior e é o único que escuta o `Escape`; os de baixo ficam `inert`.
  Sem isso, a confirmação aberta de dentro do detalhe da oportunidade pintava atrás dele — mesmo
  `z-40`, mesmo contexto de empilhamento, empate resolvido por ordem de DOM — e um `Escape` fechava
  os dois, porque `stopPropagation()` não interrompe outros listeners registrados no **mesmo**
  `EventTarget` (isso seria `stopImmediatePropagation`) e ambos vivem no `document`. O `inert`
  resolve de carona os dois `aria-modal="true"` visíveis ao mesmo tempo, que eram inválidos.

## A outra metade: os dois "Excluir" de verdade

A regra "Arquivar ≠ Excluir" separou os seis recursos que arquivam dos **dois** que apagam de
verdade — etapa do pipeline e fase da jornada. Os seis ganharam guarda, 409 e caminho de volta. Os
dois ganharam botão e confirmação e **nenhum caminho de recusa**, o que é exatamente o que esta FDD
existe para não deixar acontecer.

Os dois batem em FK `PROTECT` (`Opportunity.stage`, `ProjectPhase.phase`) e o `ProtectedError` não
era tratado em lugar nenhum. Saía **500** — que o SPA mostra como "Não foi possível concluir a
operação." e ainda **reporta ao Sentry**, porque `api.ts` reporta todo status ≥ 500. Uso legítimo da
interface virava incidente, e a única informação útil (o que ainda depende do registro) não chegava
a quem tinha clicado.

O caso da fase era pior que intermitente. `journey.materialize_journey` copia o template inteiro
para **todo** projeto, então bastava um projeto na base para o botão "Excluir" da tela Jornada estar
morto para **qualquer** fase — enquanto o diálogo prometia o contrário: *"Projetos que já
materializaram esta fase não são afetados"*.

- **Recusa por estado é 409 também na exclusão real.** `ArchiveConflict` virou **`StateConflict`**:
  o nome estava estreito, a razão é a mesma (o pedido está bem formado, o que impede é o estado) e a
  forma também — contagem do que depende, mais o que fazer antes.
- **A contagem inclui o arquivado, e diz que inclui.** `PROTECT` não sabe o que é `archived_at`.
  Contar só o ativo produziria "0 oportunidade(s)" numa recusa, ou mandaria mover o que a tela
  esconde — a mesma classe de mentira que a guarda da oportunidade tinha. Quando há oportunidade
  arquivada segurando a etapa, a mensagem manda restaurar, mover e arquivar de novo; o caminho de
  volta existe desde esta FDD.
- **A recusa da fase tem saída: desativar** (`JourneyPhase.active`, FDD 011). Excluir uma fase por
  onde passaram projetos reais seria apagar o histórico deles; o que se quer ao aposentar uma fase é
  que ela pare de valer daqui para frente. Excluir continua valendo para a fase que **ninguém**
  materializou, que é o caso da fase criada por engano.
- **E uma rede por baixo:** `apps.core.exceptions.api_exception_handler`, registrado em
  `REST_FRAMEWORK["EXCEPTION_HANDLER"]`, traduz qualquer `ProtectedError` em 409. Não substitui a
  mensagem específica — dá o status certo. Existe porque são **doze** FKs `PROTECT` no `models.py` e
  nada obriga a próxima rota de exclusão a lembrar de contar os seus dependentes.

## Fronteira com o portal do cliente (ADR 0003)

Arquivar um projeto **emite webhook** — `archive()` é um `save()` — e o portal vem buscar o estado
novo em `GET /api/v1/portal/projects/{id}/snapshot/`. Essa rota filtrava `archived_at__isnull=True`,
o mesmo filtro do `get_queryset` do `ArchiveModelViewSet`, onde ele está certo: quem lista não quer
ver o arquivado. Aqui produzia o efeito oposto do pretendido — o portal levava **404**, que ele não
tem como distinguir de "este id nunca existiu", e por isso congelava o projeto no último estado bom,
exibindo como ativo, na tela do cliente, um projeto encerrado. Só voltava a concordar se alguém
desarquivasse.

**Arquivar não pode fazer o projeto sumir desta rota — só declarar que acabou.** O snapshot passou a
carregar `project.archived_at` (`None` quando ativo, e o portal desfaz igual ao restaurar), a rota
responde 200 para arquivado, e o 404 volta a significar uma coisa só.

## Fronteira com a retenção (ADR 0017)

`retention.py` conta o prazo de expurgo a partir de `archived_at`, para as famílias `lead` e
`document`. **Restaurar zera esse relógio** — o registro volta a estar ativo e deixa de ser
candidato ao `purge_archived`. É o comportamento correto, e é intencional: um dado que voltou ao
uso não deve ser apagado pelo prazo que corria enquanto ele estava fora.

O expurgo continua sendo a única operação que destrói de propósito, e continua inerte por padrão.

## Onde está

- Backend: `ArchiveModelViewSet` (`?archived=1`, `unarchive`), `StateConflict`,
  `ClientViewSet.perform_destroy`, `OpportunityViewSet.perform_destroy`,
  `PipelineStageViewSet.perform_destroy`, `JourneyPhaseViewSet.perform_destroy` e
  `PortalProjectSnapshotView` — todos em `backend/apps/core/views.py`; o campo `archived_at` do
  snapshot em `backend/apps/core/portal.py`; a rede do `ProtectedError` em
  `backend/apps/core/exceptions.py` (`api_exception_handler`), ligada em `config/settings.py`.
- Frontend: `components/Modal.tsx` (`Modal` extraído da `CommercialPage` + `ConfirmDialog`); botões
  em `ClientDetailPage`, `ProjectDetailPage` e no detalhe da `CommercialPage`; abas Arquivados em
  `ClientsPage` e `ProjectsPage`; alternador "Herdada por projetos novos" em `JourneyConfigPage`;
  Editar/Arquivar/Mostrar arquivados no roster de Funcionários Digitais (`ProjectDetailPage`).
- Testes: `backend/tests/regression/test_archive_nao_deixa_orfao.py`,
  `backend/tests/regression/test_arquivar_tem_saida.py`,
  `backend/tests/regression/test_excluir_recusa_em_vez_de_quebrar.py`,
  `backend/apps/core/tests/test_archive_restore.py`, `backend/apps/core/tests/test_portal.py`
  (`test_snapshot_serve_projeto_arquivado_declarando_o_arquivamento`),
  `frontend/src/components/Modal.test.tsx`, `frontend/src/pages/JourneyConfigPage.test.tsx`.
