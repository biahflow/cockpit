"""O `Engagement` entre a conta e o projeto (ADR 0050, FDD 046).

O que este arquivo fixa é a espinha dorsal `Account → Engagement → Project`: o modelo e as suas
três validações, a obrigatoriedade em `POST /projects/`, o mandato de escopo único que a conversão
cria sozinha, o recorte de `/engagements/` para cada papel, e a condição comercial
(`commercial_model`) que o mandato passou a registrar (emenda de 28/08/2026).

As duas invariantes que **não** são sobre o engajamento em si, e que por isso moram em
`tests/regression/`, são a conversão de uso único e o fato de o engajamento visível não conceder
acesso a projeto nenhum.
"""

from datetime import timedelta

import pytest
from django.core.exceptions import ValidationError
from django.urls import reverse
from django.utils import timezone
from rest_framework.test import APIClient

from apps.core.models import (
    CommercialOpportunity,
    Contact,
    Engagement,
    PipelineStage,
    Project,
    User,
)

from .factories import (
    AccountFactory,
    CommercialOpportunityFactory,
    EngagementFactory,
    ProjectFactory,
    ProjectMemberFactory,
    UserFactory,
)

pytestmark = pytest.mark.django_db


def _api(role: str = User.Role.ADMIN) -> tuple[APIClient, User]:
    user = UserFactory(role=role)
    client = APIClient()
    client.force_authenticate(user)
    return client, user


# --------------------------------------------------------------------------- modelo


def test_engagement_recusa_data_final_anterior_a_inicial() -> None:
    hoje = timezone.localdate()
    engagement = EngagementFactory.build(
        account=AccountFactory(), owner=UserFactory(), started_at=hoje, ended_at=hoje - timedelta(1)
    )

    with pytest.raises(ValidationError) as erro:
        engagement.clean()

    assert "ended_at" in erro.value.message_dict


def test_engagement_encerrado_exige_data_final() -> None:
    engagement = EngagementFactory.build(
        account=AccountFactory(), owner=UserFactory(),
        status=Engagement.Status.CLOSED, ended_at=None,
    )

    with pytest.raises(ValidationError) as erro:
        engagement.clean()

    assert "ended_at" in erro.value.message_dict


def test_patrocinador_precisa_ser_contato_da_mesma_conta() -> None:
    """Um patrocinador de outra organização exibiria, na tela do mandato, um nome que não pertence
    àquela conta — e nada acusaria."""
    conta = AccountFactory()
    engagement = EngagementFactory.build(
        account=conta, owner=UserFactory(),
        sponsor=Contact.objects.create(account=AccountFactory(), first_name="Alheia"),
    )

    with pytest.raises(ValidationError) as erro:
        engagement.clean()

    assert "sponsor" in erro.value.message_dict


def test_patrocinador_da_propria_conta_passa() -> None:
    conta = AccountFactory()
    engagement = EngagementFactory.build(
        account=conta, owner=UserFactory(),
        sponsor=Contact.objects.create(account=conta, first_name="Patrocinadora"),
    )

    engagement.clean()  # não levanta


def test_projeto_recusa_engajamento_de_outra_conta() -> None:
    """A validação que mantém honesta a projeção `Project.client` (ADR 0050): sem ela, o projeto
    apareceria na carteira de uma conta e no mandato de outra."""
    projeto = ProjectFactory.build(
        client=AccountFactory(), engagement=EngagementFactory(), owner=UserFactory(),
        start_date=timezone.localdate(), due_date=timezone.localdate() + timedelta(days=10),
    )

    with pytest.raises(ValidationError) as erro:
        projeto.clean()

    assert "engagement" in erro.value.message_dict


def test_todo_projeto_de_fabrica_tem_engajamento_coerente() -> None:
    """Invariante 7 do mapa de linguagem, no caminho mais banal que existe."""
    projeto = ProjectFactory()

    assert projeto.engagement_id is not None
    assert projeto.engagement.account_id == projeto.client_id


# ------------------------------------------------------------- commercial_model (emenda)


def test_engagement_nasce_pago_por_padrao() -> None:
    engagement = EngagementFactory(account=AccountFactory(), owner=UserFactory())

    assert engagement.commercial_model == Engagement.CommercialModel.PAID


def test_design_partner_so_quando_explicito() -> None:
    engagement = EngagementFactory(
        account=AccountFactory(), owner=UserFactory(),
        commercial_model=Engagement.CommercialModel.DESIGN_PARTNER,
    )

    assert engagement.commercial_model == Engagement.CommercialModel.DESIGN_PARTNER


def test_post_engagement_aceita_e_devolve_commercial_model() -> None:
    api, vendedora = _api(User.Role.SALES)
    conta = AccountFactory()

    resposta = api.post(
        reverse("engagement-list"),
        {
            "account": conta.pk, "name": "Discovery gratuito", "owner": vendedora.pk,
            "commercial_model": "design_partner",
        },
        format="json",
    )

    assert resposta.status_code == 201
    assert resposta.data["commercial_model"] == "design_partner"
    assert resposta.data["commercial_model_display"] == "Design partner"


def test_commercial_model_fora_do_enum_e_recusado() -> None:
    api, vendedora = _api(User.Role.SALES)
    conta = AccountFactory()

    resposta = api.post(
        reverse("engagement-list"),
        {"account": conta.pk, "name": "X", "owner": vendedora.pk, "commercial_model": "gratis"},
        format="json",
    )

    assert resposta.status_code == 400
    assert "commercial_model" in resposta.data


def test_design_partner_nasce_sem_nenhuma_oportunidade_e_projeto_pende_dele() -> None:
    """A invariante que motivou a emenda: hoje não existe FK de `Engagement` para `CommercialOpportunity`
    (a direção é a inversa), então um mandato de design partner já pode nascer — e um projeto
    pendurar nele — sem nenhuma oportunidade no banco."""
    api, vendedora = _api(User.Role.SALES)
    conta = AccountFactory()

    criado = api.post(
        reverse("engagement-list"),
        {
            "account": conta.pk, "name": "Cartas Vivas — Discovery", "owner": vendedora.pk,
            "commercial_model": "design_partner",
        },
        format="json",
    )
    assert criado.status_code == 201
    engagement = Engagement.objects.get(pk=criado.data["id"])
    projeto = ProjectFactory(client=conta, engagement=engagement)

    assert projeto.engagement_id is not None
    assert projeto.engagement.commercial_model == Engagement.CommercialModel.DESIGN_PARTNER
    assert not CommercialOpportunity.objects.exists()


# ------------------------------------------------------------------- POST /projects/


def _payload_de_projeto(conta, engagement=None) -> dict:
    corpo = {
        "client": conta.pk,
        "name": "Projeto novo",
        "start_date": str(timezone.localdate()),
        "due_date": str(timezone.localdate() + timedelta(days=10)),
    }
    if engagement is not None:
        corpo["engagement"] = engagement.pk
    return corpo


def test_criar_projeto_sem_engajamento_e_recusado() -> None:
    api, _ = _api()
    conta = AccountFactory()

    resposta = api.post(reverse("project-list"), _payload_de_projeto(conta), format="json")

    assert resposta.status_code == 400
    assert "engagement" in resposta.data


def test_criar_projeto_com_engajamento_de_outra_conta_e_recusado() -> None:
    api, _ = _api()
    conta = AccountFactory()
    alheio = EngagementFactory()

    resposta = api.post(
        reverse("project-list"), _payload_de_projeto(conta, alheio), format="json"
    )

    assert resposta.status_code == 400
    assert "engagement" in resposta.data


def test_criar_projeto_com_engajamento_da_conta_passa() -> None:
    api, _ = _api()
    conta = AccountFactory()
    engagement = EngagementFactory(account=conta)

    resposta = api.post(
        reverse("project-list"), _payload_de_projeto(conta, engagement), format="json"
    )

    assert resposta.status_code == 201
    assert resposta.data["engagement"] == engagement.pk
    assert resposta.data["engagement_name"] == engagement.name


def test_segundo_projeto_da_mesma_origem_nasce_por_post_projects() -> None:
    """O caminho da venda recorrente: o banco deixou de proibir 1-N, e é aqui que ele se usa."""
    api, _ = _api()
    conta = AccountFactory()
    engagement = EngagementFactory(account=conta)
    origem = CommercialOpportunityFactory(account=conta, stage=PipelineStage.objects.get(kind="won"))
    corpo = _payload_de_projeto(conta, engagement) | {
        "originating_commercial_opportunity": origem.pk
    }

    primeiro = api.post(reverse("project-list"), corpo, format="json")
    segundo = api.post(reverse("project-list"), corpo | {"name": "Segunda onda"}, format="json")

    assert primeiro.status_code == 201 and segundo.status_code == 201
    assert origem.projects.count() == 2
    # O alias de compatibilidade continua entregando a mesma forma de antes.
    assert primeiro.data["opportunity"] == origem.pk


def test_a_origem_comercial_nao_se_reescreve_por_patch() -> None:
    """A proveniência é fato histórico: o funil e o ciclo médio a leem como tal."""
    api, _ = _api()
    projeto = ProjectFactory()
    outra = CommercialOpportunityFactory(account=projeto.client)

    resposta = api.patch(
        reverse("project-detail", args=[projeto.pk]),
        {"originating_commercial_opportunity": outra.pk},
        format="json",
    )

    assert resposta.status_code == 200
    projeto.refresh_from_db()
    assert projeto.originating_commercial_opportunity_id is None


# ------------------------------------------------------- convert-to-project e a D3


def _converter(api: APIClient, opportunity, **extra) -> object:
    corpo = {
        "client": opportunity.account_id,
        "name": "Projeto convertido",
        "start_date": str(timezone.localdate()),
        "due_date": str(timezone.localdate() + timedelta(days=10)),
    } | extra
    return api.post(
        reverse("opportunity-convert-to-project", args=[opportunity.pk]), corpo, format="json"
    )


def test_conversao_sem_engajamento_cria_um_de_escopo_unico() -> None:
    """D3 em código: a venda avulsa não vira caso especial, ela cria o próprio mandato."""
    api, user = _api()
    opportunity = CommercialOpportunityFactory(
        stage=PipelineStage.objects.get(kind="won"), title="Discovery da Acme", scope="Escopo X"
    )

    resposta = _converter(api, opportunity)

    assert resposta.status_code == 201
    engagement = Engagement.objects.get(account_id=opportunity.account_id)
    assert resposta.data["engagement"] == engagement.pk
    assert engagement.name == "Discovery da Acme"
    assert engagement.mandate == "Escopo X"
    assert engagement.owner_id == user.pk
    assert engagement.started_at == timezone.localdate()
    assert engagement.status == Engagement.Status.ACTIVE
    # Pago por construção: a action só converte oportunidade em "Ganho".
    assert engagement.commercial_model == Engagement.CommercialModel.PAID


def test_conversao_com_engajamento_no_payload_usa_o_informado() -> None:
    api, _ = _api()
    opportunity = CommercialOpportunityFactory(stage=PipelineStage.objects.get(kind="won"))
    engagement = EngagementFactory(account=opportunity.account)

    resposta = _converter(api, opportunity, engagement=engagement.pk)

    assert resposta.status_code == 201
    assert resposta.data["engagement"] == engagement.pk
    # Não criou um segundo mandato por baixo.
    assert Engagement.objects.filter(account=opportunity.account).count() == 1


def test_conversao_recusa_engajamento_de_outra_conta() -> None:
    api, _ = _api()
    opportunity = CommercialOpportunityFactory(stage=PipelineStage.objects.get(kind="won"))

    resposta = _converter(api, opportunity, engagement=EngagementFactory().pk)

    assert resposta.status_code == 400
    assert "engagement" in resposta.data


# --------------------------------------------------------------- /api/v1/engagements/


def test_vendas_escreve_e_entrega_so_le() -> None:
    """O engajamento é o mandato comercial: quem entrega precisa sabê-lo, não redefini-lo."""
    conta = AccountFactory()
    vendas, vendedora = _api(User.Role.SALES)
    entrega, pessoa = _api(User.Role.DELIVERY)
    engagement = EngagementFactory(account=conta)
    ProjectMemberFactory(project=ProjectFactory(client=conta, engagement=engagement), user=pessoa)

    criado = vendas.post(
        reverse("engagement-list"),
        {"account": conta.pk, "name": "Transformação 2027", "owner": vendedora.pk},
        format="json",
    )
    lido = entrega.get(reverse("engagement-detail", args=[engagement.pk]))
    negado = entrega.patch(
        reverse("engagement-detail", args=[engagement.pk]), {"name": "Outro"}, format="json"
    )

    assert criado.status_code == 201
    assert lido.status_code == 200
    assert negado.status_code == 403


def test_entrega_ve_so_o_mandato_de_projeto_que_participa() -> None:
    entrega, pessoa = _api(User.Role.DELIVERY)
    meu = EngagementFactory()
    ProjectMemberFactory(project=ProjectFactory(client=meu.account, engagement=meu), user=pessoa)
    alheio = EngagementFactory()
    ProjectFactory(client=alheio.account, engagement=alheio)
    EngagementFactory()  # sem projeto nenhum

    resposta = entrega.get(reverse("engagement-list"))

    assert resposta.status_code == 200
    assert [linha["id"] for linha in resposta.data] == [meu.pk]
    assert entrega.get(reverse("engagement-detail", args=[alheio.pk])).status_code in {403, 404}


def test_o_mandato_nao_se_duplica_por_ter_dois_projetos() -> None:
    """Sem `.distinct()`, o join pelo reverso `projects` devolve uma linha por projeto casado."""
    entrega, pessoa = _api(User.Role.DELIVERY)
    engagement = EngagementFactory()
    for _ in range(3):
        projeto = ProjectFactory(client=engagement.account, engagement=engagement)
        ProjectMemberFactory(project=projeto, user=pessoa)

    resposta = entrega.get(reverse("engagement-list"))

    assert [linha["id"] for linha in resposta.data] == [engagement.pk]


def test_filtros_por_conta_e_status() -> None:
    api, _ = _api()
    conta = AccountFactory()
    ativo = EngagementFactory(account=conta)
    EngagementFactory(account=conta, status=Engagement.Status.PAUSED)
    EngagementFactory()

    por_conta = api.get(reverse("engagement-list"), {"account": conta.pk})
    por_status = api.get(reverse("engagement-list"), {"account": conta.pk, "status": "active"})

    assert len(por_conta.data) == 2
    assert [linha["id"] for linha in por_status.data] == [ativo.pk]


def test_arquivar_mandato_com_projeto_vivo_e_recusado() -> None:
    """Regra de órfão da FDD 025: `ProjectViewSet` nunca olha o `archived_at` do engajamento."""
    api, _ = _api()
    engagement = EngagementFactory()
    projeto = ProjectFactory(client=engagement.account, engagement=engagement)

    bloqueado = api.delete(reverse("engagement-detail", args=[engagement.pk]))
    api.delete(reverse("project-detail", args=[projeto.pk]))
    liberado = api.delete(reverse("engagement-detail", args=[engagement.pk]))

    assert bloqueado.status_code == 409
    assert "projeto(s) em aberto" in bloqueado.data["detail"]
    assert liberado.status_code == 204


def test_arquivar_a_conta_leva_o_mandato_junto() -> None:
    """O mandato é listado sozinho em `/engagements/?account=`: deixá-lo vivo sob uma conta
    arquivada é o órfão visível que a FDD 025 existe para não produzir."""
    api, _ = _api()
    engagement = EngagementFactory()

    resposta = api.delete(reverse("client-detail", args=[engagement.account_id]))

    assert resposta.status_code == 204
    engagement.refresh_from_db()
    assert engagement.archived_at is not None


def test_serializer_recusa_encerrado_sem_data_final() -> None:
    api, user = _api()
    conta = AccountFactory()

    resposta = api.post(
        reverse("engagement-list"),
        {"account": conta.pk, "name": "Encerrado", "owner": user.pk, "status": "closed"},
        format="json",
    )

    assert resposta.status_code == 400
    assert "ended_at" in resposta.data


def test_o_engajamento_nao_e_fronteira_de_acesso() -> None:
    """A invariante que separa mandato de escopo: ver o engajamento **não** dá acesso ao projeto.

    O recorte da Entrega continua sendo `ProjectMember` (RFC 0003, ADR 0010). Se um dia
    `/engagements/` virar raiz de navegação, é esta asserção que impede que ela vire porta.
    """
    entrega, pessoa = _api(User.Role.DELIVERY)
    engagement = EngagementFactory()
    meu = ProjectFactory(client=engagement.account, engagement=engagement)
    ProjectMemberFactory(project=meu, user=pessoa)
    # Mesmo mandato, mesma conta — e a pessoa não é membro deste.
    vizinho = ProjectFactory(client=engagement.account, engagement=engagement)

    assert entrega.get(reverse("engagement-detail", args=[engagement.pk])).status_code == 200
    assert entrega.get(reverse("project-detail", args=[vizinho.pk])).status_code == 404
    assert [
        linha["id"] for linha in entrega.get(reverse("project-list")).data
    ] == [meu.pk]
    assert Project.objects.visible_to(pessoa).filter(pk=vizinho.pk).exists() is False


# ------------------------------------------------- a superfície da seção (DAP dap-engagement-r1)
#
# O payload que a seção de Engagements do detalhe do cliente consome, e a copy que a decisão A1
# arrasta para o servidor. O pacote aprovado é `docs/design/dap-engagement-r1/`.


def test_sponsor_name_vem_preenchido_e_e_nulo_sem_patrocinador() -> None:
    """O board desenha "Patrocínio de {nome}", e `sponsor` é opcional: sem patrocinador a linha
    não mostra a frase, em vez de mostrar uma frase pela metade."""
    api, _ = _api()
    conta = AccountFactory()
    com_patrocinio = EngagementFactory(
        account=conta,
        sponsor=Contact.objects.create(account=conta, first_name="Marina", last_name="Alencar"),
    )
    sem_patrocinio = EngagementFactory(account=conta)

    linhas = {
        linha["id"]: linha
        for linha in api.get(reverse("engagement-list"), {"account": conta.pk}).data
    }

    assert linhas[com_patrocinio.pk]["sponsor_name"] == "Marina Alencar"
    assert linhas[sem_patrocinio.pk]["sponsor_name"] is None


def test_a_contagem_de_projetos_e_recortada_pelo_escopo_de_quem_le() -> None:
    """O agregador narrowed by hand desta seção, e o teste que o `CLAUDE.md` exige de cada um.

    **Dois usuários veem números diferentes para o mesmo mandato**, e isso é honesto: cada um vê o
    que alcança. Um total cru contaria, para a Entrega, projetos fora do recorte dela — sinal
    fraco, mas ainda assim informação sobre o que ela não pode ver.
    """
    admin, _ = _api()
    entrega, pessoa = _api(User.Role.DELIVERY)
    engagement = EngagementFactory()
    projetos = [ProjectFactory(client=engagement.account, engagement=engagement) for _ in range(3)]
    ProjectMemberFactory(project=projetos[0], user=pessoa)

    do_admin = admin.get(reverse("engagement-detail", args=[engagement.pk])).data
    da_entrega = entrega.get(reverse("engagement-detail", args=[engagement.pk])).data

    assert do_admin["projects_count"] == 3
    assert da_entrega["projects_count"] == 1


def test_a_contagem_ignora_projeto_arquivado() -> None:
    """`archived_at__isnull=True` no `filter` do `Count`: um mandato cujo projeto foi arquivado
    não tem trabalho em aberto, e mostrar "1 projeto" ali convidaria a procurá-lo na tela."""
    admin, _ = _api()
    engagement = EngagementFactory()
    ProjectFactory(client=engagement.account, engagement=engagement)
    arquivado = ProjectFactory(client=engagement.account, engagement=engagement)
    admin.delete(reverse("project-detail", args=[arquivado.pk]))

    resposta = admin.get(reverse("engagement-detail", args=[engagement.pk]))

    assert resposta.data["projects_count"] == 1


def test_a_contagem_nao_infla_com_o_join_da_entrega() -> None:
    """A armadilha do `distinct=True`: o recorte atravessa `projects__members` e o filtro da
    Entrega atravessa `projects` de novo, então a linha do projeto se repete no join. Sem o
    `distinct`, dois membros no mesmo projeto virariam "2 projetos"."""
    entrega, pessoa = _api(User.Role.DELIVERY)
    engagement = EngagementFactory()
    projeto = ProjectFactory(client=engagement.account, engagement=engagement)
    ProjectMemberFactory(project=projeto, user=pessoa)
    ProjectMemberFactory(project=projeto, user=UserFactory(role=User.Role.DELIVERY))

    linhas = entrega.get(reverse("engagement-list")).data

    assert [linha["projects_count"] for linha in linhas] == [1]


def test_criar_sem_owner_grava_quem_esta_logado() -> None:
    """O formulário aprovado não expõe "Responsável": a seção vive dentro do detalhe do cliente,
    onde quem cria é quem está logado. Mesmo precedente da `convert-to-project`."""
    api, vendedora = _api(User.Role.SALES)
    conta = AccountFactory()

    resposta = api.post(
        reverse("engagement-list"),
        {"account": conta.pk, "name": "Transformação Financeira"},
        format="json",
    )

    assert resposta.status_code == 201
    assert resposta.data["owner"] == vendedora.pk
    assert Engagement.objects.get(pk=resposta.data["id"]).owner_id == vendedora.pk


def test_criar_com_owner_no_payload_respeita_o_informado() -> None:
    """Relaxar a exigência não é tirar o campo: `owner` continua gravável no contrato."""
    api, _ = _api()
    conta = AccountFactory()
    outra = UserFactory(role=User.Role.SALES)

    resposta = api.post(
        reverse("engagement-list"),
        {"account": conta.pk, "name": "Mandato de outra pessoa", "owner": outra.pk},
        format="json",
    )

    assert resposta.status_code == 201
    assert resposta.data["owner"] == outra.pk


def test_a_recusa_de_arquivar_diz_engagement_e_nao_engajamento() -> None:
    """Consequência da decisão A1 do DAP: com o título em inglês na tela, a mensagem do servidor
    em português deixaria **três** palavras para o mesmo conceito diante de quem lê."""
    api, _ = _api()
    engagement = EngagementFactory()
    ProjectFactory(client=engagement.account, engagement=engagement)

    resposta = api.delete(reverse("engagement-detail", args=[engagement.pk]))

    assert resposta.status_code == 409
    assert resposta.data["detail"] == (
        "Este engagement ainda tem 1 projeto(s) em aberto. "
        "Arquive esses projetos antes de arquivar o engagement."
    )


def test_a_guarda_de_conta_da_conversao_e_inalcancavel_pelo_serializer() -> None:
    """**A segunda troca de copy que o spec pediu está em ramo morto, e isto o registra.**

    `convert_to_project` compara `engagement.account_id` com `opportunity.account_id` depois de já
    ter passado por dois filtros que juntos tornam a divergência impossível:
    `ProjectSerializer.validate` recusa `engagement.account != account`, e a própria action recusa
    `account != opportunity.account`. Quem chega à terceira comparação já tem as duas igualdades.

    A mensagem que a pessoa de fato lê nesse caminho é a **do serializer**, e ela continua em
    português — mas é da superfície de Projetos/Comercial, não da seção de Engagements que o DAP
    `dap-engagement-r1` aprovou. Trocá-la é varredura própria, fora deste escopo.
    """
    api, _ = _api()
    opportunity = CommercialOpportunityFactory(stage=PipelineStage.objects.get(kind="won"))

    resposta = _converter(api, opportunity, engagement=EngagementFactory().pk)

    assert resposta.status_code == 400
    assert resposta.data["engagement"] == [
        "O engajamento deve pertencer ao mesmo cliente do projeto."
    ]
