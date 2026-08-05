# ADR 0010 — Equipe do projeto como fronteira de acesso

**Status:** aceito

## Contexto

A ADR 0009 restringiu os documentos da Entrega aos projetos em que a pessoa atua e deixou
registrado que estender a regra ao resto "muda o modelo de acesso da área inteira e pede RFC
próprio". É o RFC 0003. Aqui ficam as decisões de modelagem que ele exigiu.

O problema de fundo: não existia como dizer "esta pessoa é deste projeto". A única ligação
pessoa↔trabalho era `owner`, sempre igual a quem criou o registro e read-only em todos os
serializers. Na conversão, o dono do projeto e de todos os marcos e tarefas é o vendedor
(`kickoff.seed_work_items` usa `project.owner`), então nenhum usuário de Entrega era dono de
nada. Aplicar a regra sem resolver isso deixaria a área inteira sem ver projeto algum.

## Decisão

**`ProjectMember` é a única fonte da regra.** Um modelo com `project`, `user` e `added_by`,
sem papel interno: quem é da equipe, é. O papel de produto já vive em `User.role`, e um
segundo eixo agora seria adivinhar requisito. `added_by` existe porque conceder acesso é ato
de segurança e precisa de cadeia auditável.

A unicidade é **condicional ao arquivamento** (`UniqueConstraint` com
`condition=Q(archived_at__isnull=True)`, mesmo padrão de `Service.tier`): sair da equipe e
voltar depois é rotina, e uma constraint cega sobre as linhas arquivadas travaria a readmissão.

**"Participar" substitui "atuar", e não convive com ele.** Descartamos "membro OU dono": dois
critérios em paralelo foi exatamente o que produziu a divergência anterior entre a versão
Python de `_acts_on_project` e a versão SQL dentro de `DocumentViewSet`. Pior, como `owner` é
obrigatório e `PROTECT`, a união tornaria impossível revogar o acesso de quem já é dono de
alguma coisa. Um critério só, expresso uma vez: `Project.objects.visible_to(user)` e
`project_scope_q(user, path)`, ambos em `models.py`, de onde `views.py` e `permissions.py`
derivam. Ficam no model, e não num módulo novo, porque `permissions.py` importa de `models.py`
e `views.py` importa de `permissions.py` — a regra em `views.py` faria ciclo.

**O dono é sempre membro**, por invariante em `post_save` de `Project`. No signal, e não no
`perform_create` da view, porque precisa valer nos três caminhos que criam projeto: API, admin
do Django e as factories dos testes. Sem isso, transferir a titularidade deixaria o novo dono
sem acesso ao próprio projeto.

**A permissão de objeto nega por padrão.** O ramo de Entrega em `has_object_permission`
terminava em `return True`, inofensivo enquanto nada era escondido e vazamento residual assim
que os querysets estreitaram. Agora há um mapa explícito de modelo → caminho até o projeto e
um `return False` no fim: recurso novo nasce fechado.

**Só admin monta a equipe.** Quem tem essa caneta concede acesso a dado de projeto. Vendas e
Entrega leem a equipe dos projetos que já enxergam, porque precisam saber quem toca a conta.

**Entrega não cria nem apaga projeto.** O corte é por *ação* (`create`/`destroy`), não por
método HTTP: as ações de detalhe — assistente, resumo, próximos passos, avançar fase — também
são `POST` e precisam continuar passando.

## Consequências

O acesso passa a ser explícito e revogável: tirar alguém da equipe corta a visão na hora, o
que antes não tinha como fazer sem mexer na titularidade de registros de trabalho.

O custo aparece na conversão: quando **Vendas** converte, o projeto nasce sem equipe e fica
invisível para a Entrega até um admin montá-la. É consequência direta de concentrar a gestão no
admin, está no runbook, e é o ponto a revisitar se virar atrito — a alternativa natural seria
deixar quem já é do projeto convidar colegas.

Um mixin (`ProjectScopedMixin`) carrega o recorte de leitura e escrita nos dez viewsets de
projeto. Os caminhos que não passam por queryset — `/clients/overview/`, `/risk/`, `/health/`,
`/dashboard/`, o contexto do agente de entrega e a materialização preguiçosa da jornada —
precisaram de tratamento individual, e cada um tem teste próprio justamente porque não são
alcançados por construção.

`build_client_overview` ganhou um parâmetro de projetos porque o agregado é **por cliente**:
estreitar a lista de clientes não bastava — quem participa de um projeto do cliente X veria
ROI, saúde e AI Score dos outros projetos de X.

Os docstrings dos mixins viraram comentários: o drf-spectacular usa o docstring da classe como
`description` de cada endpoint, e um mixin no topo da MRO vaza o próprio texto para dezenas de
rotas alheias — o que já havia acontecido com o `QueryParamFilterMixin` e sujava o contrato.
