# FDD 026 — Biblioteca de Funcionários Digitais

> **Status: entregue.** Em duas metades. A primeira documentou o que já existia sem FDD e deu
> tela aos oito campos do roster; a segunda — o catálogo reutilizável — está agora construída.
> A decisão de modelar a variante como tabela própria virou a **ADR 0019**, como esta FDD
> previa que precisaria virar.

## Jornada

O `DigitalEmployee` é, nas palavras do próprio docstring, **"o produto central"** — e é a
única entidade central do domínio **sem FDD**. Ele nasceu como código na Fase 3 do bloco de
lacunas (`roadmap.md`), sem FDD, sem ADR e sem entrada no `CHANGELOG.md`. Esta FDD fecha
essa dívida antes de propor qualquer coisa nova, no precedente da FDD 025, que documentou o
`archive()` antigo no mesmo movimento em que fechou o que faltava.

O que existe hoje é uma **linha plana por projeto**: `DigitalEmployee` pendura em `Project`
por FK com `CASCADE`, `area` é texto livre e o KPI são duas strings soltas
(`kpi_label`/`kpi_value`). Não há catálogo, template, nem vínculo com `Service`. Cada
entrega **recria** o Funcionário Digital do zero — e na tela recria pela metade: o
formulário de `ProjectDetailPage` aceita só nome, área e status, de modo que descrição, KPI,
horas e ROI não são editáveis pela interface, só pela API ou pelo admin.

Falta a camada de **blueprint**: um catálogo interno de Funcionários Digitais parametrizados
por área e por vertical, que a entrega **instancia** em vez de recriar. É o que transforma
um agente em bloco produtizado — o mesmo "SDR" servindo imobiliária, saúde, telecom e
automotiva com a mesma espinha e parâmetros diferentes. Encurta a entrega, dá ao comercial
algo concreto para mostrar, e é o passo que falta para o PRD cumprir a própria promessa de
conduzir a consultoria como **produto repetível**.

O molde já existe e está provado duas vezes: `JourneyPhase → ProjectPhase` e
`PhaseDeliverable → ProjectDeliverable` (FDD 011) são template global editável mais cópia
por instância, com `active` para aposentar sem reescrever histórico e o `name` **copiado**
na instância justamente para o template não reescrever o passado. O blueprint é a terceira
aplicação do mesmo padrão.

## Regras — o que já existe

- **Modelo.** `DigitalEmployee` (`apps/core/models.py`) estende `TimestampedModel`, logo tem
  `archived_at` e segue o arquivamento em vez do apagamento. Campos: `project` (FK
  `CASCADE`, `related_name="digital_employees"`), `name`, `area` (texto livre),
  `description`, `status` (`building`/`active`/`paused`), `kpi_label`, `kpi_value`,
  `hours_saved_month` e `roi_month` (ambos `Decimal`, preenchidos à mão pela equipe).
- **API.** `DigitalEmployeeViewSet` (`apps/core/views.py`) combina `ProjectScopedMixin`,
  `QueryParamFilterMixin` e `ArchiveModelViewSet`, com `resource = "digital_employee"` e
  filtro por `project`. Rota `/api/v1/digital-employees/` (`apps/core/urls.py`).
- **Acesso.** `permissions.py` registra o modelo em `PROJECT_OF` (o projeto do objeto é o do
  próprio `project`), dá a Vendas **só leitura** e à Entrega escrita **dentro dos projetos de
  que participa** (FDD 018, ADR 0010). Admin alcança tudo.
- **Portal do cliente.** `portal.build_snapshot` projeta o roster na chave
  `digital_employees` — é a única superfície do Funcionário Digital voltada ao cliente, e
  nada técnico vaza junto. Do outro lado, o portal já tem modelo próprio e o exibe na Visão
  geral e em Resultados (FDD 006 do `biahflow-portal-cliente`).
- **Interface.** `ProjectDetailPage.tsx` mostra o roster com selo de status, área, descrição
  e a linha de métricas (`kpi_label: kpi_value`, horas/mês, ROI/mês). Cada cartão tem **Editar**
  — um `Modal` com os oito campos — e **Arquivar** com `ConfirmDialog`, mais um alternador
  **Mostrar arquivados** com Restaurar; tudo gated por admin/Entrega, que é a permissão do
  backend (Vendas lê e não mexe). O formulário rápido embaixo do roster continua criando com
  nome e área, e o resto se preenche no Editar.

  Até 07/08/2026 a tela alcançava **dois** dos oito campos: o formulário de criação mandava só
  nome e área (o `status` era `"building"` fixo, sem input), os cartões eram de leitura e não
  havia arquivar nem restaurar, embora o viewset seja um `ArchiveModelViewSet` completo desde
  sempre. Como o snapshot leva `description`, `status`, `kpi_label`, `kpi_value`,
  `hours_saved_month` e `roi_month` ao painel do cliente, o Funcionário Digital chegava lá como
  "Em construção", sem KPI, 0h e R$ 0 de ROI — e ficava assim, porque preencher exigia a API
  crua ou o Django admin. Era a mesma falha que a FDD 025 nomeia ("não havia botão"), no único
  recurso arquivável que ela não fechou.

## Regras — o catálogo

- **`Vertical` é taxonomia, não enum.** Modelo próprio (`name`, `slug`, `position`,
  `active`), editável pelo admin, na forma de `PipelineStage` e `JourneyPhase` — o domínio
  não tinha **nenhum eixo de setor**, e cravar um enum no código repetiria o erro de
  `area`. `Client` ganhou `vertical` (`SET_NULL`, opcional): campo aditivo, sem quebra do
  contrato `/api/v1/`. `ProjectSerializer` expõe `client_vertical`/`client_vertical_name`
  (read-only), para o detalhe do projeto pedir o catálogo resolvido sem carregar o cliente
  inteiro por causa de um id.
- **`DigitalEmployeeBlueprint` é catálogo global**, sem FK para projeto: `name`, `area` em
  **choices fechadas** (comercial, financeiro, RH, jurídico, atendimento), `description`,
  `kpi_label` **canônico**, `default_hours_saved_month`, `default_roi_month`, `active`, e FK
  opcional para `Service` para sugerir blueprints pelo nível de produto (FDD 015). A `area`
  fechada é o ponto — livre, ela não filtra, não agrega e não aparece em consulta nenhuma.
  **Só no blueprint**: em `DigitalEmployee` ela continua `CharField` livre, porque fechá-la
  ali quebraria o contrato `/api/v1/` (um PATCH com a área digitada à mão passaria a receber
  400) e o que o snapshot já entrega ao cliente. A instanciação copia o **rótulo**
  (`get_area_display`), não o slug: gravar `"rh"` faria o cliente ler "rh".
- **`BlueprintVariant` é a parametrização por vertical:** FK `blueprint` (`CASCADE`), FK
  `vertical` (`PROTECT`), sobrescritas de descrição, KPI e defaults, com
  `UniqueConstraint(blueprint, vertical)` — a mesma forma de invariante que o
  `PipelineStage` ganho/perdido e o `Service` por `tier` já usam. Um blueprint, N
  parametrizações: é esta tabela que produtiza o bloco. **Em branco herda** (string vazia ou
  decimal nulo): a variante diz o que muda para aquele setor, não repete o que não muda —
  daí os decimais dela serem `null=True`, e não `default=0`, que seria sobrescrever com zero.
  A escolha de tabela própria em vez de JSON no blueprint está na **ADR 0019**.
- **`?vertical=` resolve, não filtra.** `GET /digital-employee-blueprints/?vertical=<id>`
  devolve o catálogo **inteiro** com um bloco `resolved` (os valores já com a variante
  aplicada) e `has_variant` por linha. Filtrar esconderia o bloco genérico de quem tem
  vertical e deixaria sem catálogo nenhum quem não tem — e é regra desta FDD que cliente sem
  vertical continue funcionando. `?active=1` é o recorte que a instanciação pede; a tela de
  configuração não o passa, porque precisa ver o que desativou.
- **Instanciar copia, não referencia.** `DigitalEmployee` ganhou `blueprint` (`SET_NULL`) e
  `blueprints.instantiate` **copia** nome, descrição, KPI e defaults no momento da criação. O
  precedente é `ProjectDeliverable`, que copia o `name` do template pela mesma razão: editar
  o catálogo amanhã não pode reescrever o que foi entregue ontem. O campo é **read-only** no
  serializer: gravável, abriria um segundo caminho que aponta para o template sem copiar —
  exatamente o que a cópia existe para impedir.
- **Sem signal, e isso é deliberado.** A jornada é materializada em `post_save` de `Project`
  porque é igual para todo projeto; o roster de Funcionários Digitais **não é**. A
  instanciação é ação explícita — `POST /projects/{id}/digital-employees/from-blueprint/` —
  com a vertical do cliente como padrão. A rota mora em `ProjectViewSet` e daí sai a
  permissão certa de graça: Entrega alcança as ações de detalhe de `project` que não sejam
  `create`/`destroy`, o objeto ainda passa por `_participates`, e Vendas é barrada.
- **Acesso: catálogo é global, não de projeto.** Blueprint, variante e vertical seguem o
  padrão do recurso `service` — leitura para todos, escrita só admin — agrupados no conjunto
  `CATALOG` de `permissions.py`. **Não** entram em `PROJECT_OF`, que só descreve objeto
  pendurado em projeto. Lembrar que `RolePermission` **nega por padrão**: cada `resource`
  novo nasce fechado e precisa de política explícita.
- **Proposta por IA.** `ai.build_opportunity_context` injeta os blueprints aplicáveis — ativos
  e ou amarrados ao nível vendido ou genéricos —, resolvidos pela vertical do cliente, ao lado
  do bloco de nível de produto que já existe, com teto de `OPPORTUNITY_BLUEPRINT_LIMIT`
  blocos, porque catálogo cresce sem limite e prompt que cresce junto é custo por chamada que
  ninguém pediu. Sem vertical ou sem blueprint, o comportamento anterior é preservado, e o
  antivazamento segue intacto: só dados desta oportunidade e do catálogo, que é da casa.
- **Interface.** `BibliotecaPage` (`/biblioteca`) clona a estrutura de `JourneyConfigPage`
  (cartões editáveis em linha, sub-lista, formulário de criação e `ConfirmDialog`),
  registrada em `App.tsx` e no menu de `Layout.tsx` com `["admin"]`, ao lado de `/servicos` e
  `/jornada` — os dois itens de metodologia já agrupados ali. `api.ts` não mudou: recurso CRUD
  é chamado com `api<T>("/rota/")` direto na página. No detalhe do projeto, "Adicionar da
  biblioteca" aparece **acima** do formulário livre, e só quando há catálogo — um `<select>`
  sem opção prometeria um caminho que não existe. A vertical do cliente é editável em
  Clientes.
- **Aposentar é desativar.** Blueprint e vertical em uso não se excluem: seguem a decisão da
  FDD 025 e da FDD 011 — `active = False` como saída, e `DELETE` recusado com 409 quando
  houver dependente. Na vertical a guarda é a recusa, não só a boa mensagem sobre ela:
  `Client.vertical` é `SET_NULL`, então o banco aceitaria de bom grado e zeraria o setor de
  todos os clientes que a tinham, com 204 na tela e nada dizendo o que se perdeu.

## Aceite

Em **Biblioteca**, o admin cadastra a vertical "Igrejas" e o blueprint "SDR" na área
Comercial, com o KPI canônico e os valores padrão de horas e ROI; em seguida cria a variante
de "Igrejas" ajustando a descrição. Em **Clientes**, um cliente recebe a vertical. Ao abrir
um projeto desse cliente, "Adicionar da biblioteca" oferece os blueprints do catálogo já
resolvidos pela vertical do cliente, marcando os que têm variante para ela; escolhido um, o
Funcionário Digital nasce com nome, descrição, KPI e valores padrão preenchidos — não mais um
cartão vazio a completar à mão.
Editar o blueprint depois **não** altera os Funcionários Digitais já instanciados. Com IA
ligada, a proposta gerada para uma oportunidade daquele cliente cita o Funcionário Digital
concreto, e não apenas o nível de produto.

## Regressão crítica

Duas variantes do mesmo blueprint na mesma vertical são rejeitadas (400 na API,
`IntegrityError` no banco). Instanciar copia os campos: alterar o blueprint em seguida não
muda o `DigitalEmployee` já criado. Blueprint com instância viva não é excluído — a rota
recusa com 409 e aponta a desativação; vertical com cliente ou variante, idem, e o cliente
mantém o setor. O catálogo é legível por qualquer papel autenticado, **na lista e no
detalhe**, e gravável só por admin; um usuário de Entrega que tente criar blueprint recebe
403, e segue podendo instanciar dentro dos projetos de que participa — em projeto alheio,
não. Cliente sem vertical continua funcionando: a instanciação oferece o catálogo inteiro com
os valores genéricos e a proposta não inventa um bloco de vertical no contexto da IA. O
snapshot do portal do cliente não carrega blueprint, variante nem vertical — só a cópia.
Testes em `apps/core/tests/test_blueprints.py`, `test_ai.py` e `test_portal.py`; a recusa da
vertical também em `backend/tests/regression/test_excluir_recusa_em_vez_de_quebrar.py`, porque
é o primeiro caso do arquivo em que o banco **não** recusaria sozinho.

## Fora deste recorte

**Versionamento de blueprint** — saber qual versão do template cada cliente recebeu. A cópia
por instância já protege o histórico do que foi entregue, que é o problema urgente; versionar
o template é outro, e só compensa quando o catálogo for grande o bastante para alguém
perguntar "o que mudou no SDR desde março".

**Catálogo exposto ao cliente.** Atravessa a fronteira do portal e revisita a ADR 0003, cujo
snapshot é por projeto — pede RFC, não uma emenda aqui.

**Semente do catálogo.** Verticais e blueprints não são semeados por migração, ao contrário
dos três `tier` da `0020`. Os níveis de produto **são** a metodologia; o catálogo é conteúdo
da casa, e semeá-lo seria inventar produto. A tela nasce com estado vazio e diz o que fazer.

**Agregar Funcionário Digital por área.** `DigitalEmployee.area` segue texto livre, então
somar entregas por área continua impossível. É problema da FDD 027, que precisa tipar o KPI de
qualquer forma — fechar a `area` aqui teria custado uma quebra de contrato para entregar meia
resposta.

**`BlueprintVariant` como modelo separado vs. JSON no blueprint.** Decidido na construção, como
esta FDD previa: **ADR 0019**, pelo modelo separado.
