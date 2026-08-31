"""O registro de satisfação do cliente (FDD 037, ADR 0032).

Liga ao **cliente** e não ao projeto, ao contrário dos três registros vizinhos (`Pendencia`,
`Decisao`, `Risco`) — e é essa diferença que o bloco de permissão deste arquivo exercita: a
fronteira da Entrega não passa por `PROJECT_OF`, passa pela pergunta "existe projeto meu neste
cliente?".

A janela de validade e a separação por fonte moram em `apps/core/satisfacao.py` e são testadas
aqui sem banco, no molde da escada de `test_cobranca.py`: o oráculo do resto é "que registro vale
hoje?" respondido por função pura.
"""

from datetime import date, timedelta

import pytest
from django.core.exceptions import ValidationError
from django.urls import reverse
from rest_framework.test import APIClient

from apps.core import satisfacao as satisfacao_module
from apps.core.models import Satisfacao, User

from .factories import AccountFactory, ProjectFactory, ProjectMemberFactory, UserFactory

HOJE = date(2026, 9, 2)


@pytest.fixture
def client() -> APIClient:
    return APIClient()


def _payload(account_id: int, **overrides: object) -> dict:
    base: dict = {
        "account": account_id,
        "nivel": Satisfacao.Nivel.SATISFEITO,
        "fonte": Satisfacao.Fonte.DECLARADA,
        "happened_on": "2026-09-01",
        "note": "Elogiou o ritmo das entregas na call de sexta.",
    }
    base.update(overrides)
    return base


def _registro(**kwargs: object) -> Satisfacao:
    """Um registro **não salvo**, para exercitar a janela sem banco."""
    campos: dict = {
        "nivel": Satisfacao.Nivel.INSATISFEITO,
        "fonte": Satisfacao.Fonte.DECLARADA,
        "happened_on": HOJE,
        "note": "n",
    }
    campos.update(kwargs)
    return Satisfacao(**campos)


# --- A janela de validade, sem banco ------------------------------------------


@pytest.mark.parametrize(
    ("dias", "vale"),
    [(0, True), (1, True), (89, True), (90, True), (91, False), (400, False)],
)
def test_o_sinal_envelhece_e_a_janela_e_fechada_nos_dois_lados(dias: int, vale: bool) -> None:
    """Critério de aceite 4: 91 dias não move nada, 89 move.

    O corte é `SATISFACAO_VALIDA_DIAS` e não um "registro recente" a julgar por quem estiver de
    plantão — um insatisfeito de oito meses não é o estado de hoje.
    """
    registro = _registro(happened_on=HOJE - timedelta(days=dias))

    assert (satisfacao_module.vigente([registro], HOJE) is registro) is vale


def test_registro_com_data_futura_nao_e_o_estado_de_hoje() -> None:
    """Dedo errado no formulário não pode valer por noventa dias a partir do erro."""
    assert satisfacao_module.vigente([_registro(happened_on=HOJE + timedelta(days=1))], HOJE) is None


def test_a_vigente_e_a_mais_recente_da_fonte_pedida() -> None:
    """O parâmetro `fonte` escolhe **antes** de decidir qual é a mais recente.

    Se filtrasse depois, a percebida de ontem esconderia a declarada de anteontem — e o Health
    Score passaria a depender de alguém do time ter anotado uma impressão.
    """
    declarada = _registro(happened_on=HOJE - timedelta(days=2))
    percebida = _registro(
        happened_on=HOJE - timedelta(days=1), fonte=Satisfacao.Fonte.PERCEBIDA
    )
    registros = [declarada, percebida]

    assert satisfacao_module.vigente(registros, HOJE) is percebida
    assert (
        satisfacao_module.vigente(registros, HOJE, fonte=Satisfacao.Fonte.DECLARADA) is declarada
    )


@pytest.mark.django_db
def test_arquivado_nao_e_vigente_nem_em_lote_nem_na_lista() -> None:
    cliente = AccountFactory()
    registro = Satisfacao.objects.create(
        account=cliente, nivel=Satisfacao.Nivel.INSATISFEITO,
        fonte=Satisfacao.Fonte.DECLARADA, happened_on=HOJE, note="Reclamou do prazo.",
    )
    registro.archive()

    assert satisfacao_module.vigente([registro], HOJE) is None
    assert satisfacao_module.vigentes_por_cliente([cliente.pk], HOJE) == {}


@pytest.mark.django_db
def test_o_lote_devolve_uma_vigente_por_cliente_em_uma_query() -> None:
    um, outro = AccountFactory(), AccountFactory()
    antiga = Satisfacao.objects.create(
        account=um, nivel=Satisfacao.Nivel.NEUTRO, fonte=Satisfacao.Fonte.DECLARADA,
        happened_on=HOJE - timedelta(days=30),
    )
    nova = Satisfacao.objects.create(
        account=um, nivel=Satisfacao.Nivel.PROMOTOR, fonte=Satisfacao.Fonte.DECLARADA,
        happened_on=HOJE - timedelta(days=1),
    )
    Satisfacao.objects.create(
        account=outro, nivel=Satisfacao.Nivel.SATISFEITO, fonte=Satisfacao.Fonte.PERCEBIDA,
        happened_on=HOJE - timedelta(days=200),  # fora da janela
    )

    vigentes = satisfacao_module.vigentes_por_cliente([um.pk, outro.pk], HOJE)

    assert vigentes == {um.pk: nova}
    assert antiga.pk not in {registro.pk for registro in vigentes.values()}
    assert satisfacao_module.vigentes_por_cliente([], HOJE) == {}


# --- O modelo -----------------------------------------------------------------


@pytest.mark.django_db
def test_o_clean_recusa_projeto_de_outro_cliente() -> None:
    cliente = AccountFactory()
    alheio = ProjectFactory()

    with pytest.raises(ValidationError) as erro:
        Satisfacao(
            account=cliente, project=alheio, nivel=Satisfacao.Nivel.NEUTRO,
            fonte=Satisfacao.Fonte.DECLARADA, happened_on=HOJE,
        ).clean()

    assert "project" in erro.value.message_dict


@pytest.mark.django_db
def test_o_clean_exige_nota_no_insatisfeito_e_so_nele() -> None:
    """É o único nível que muda comportamento — Health Score e escada da régua —, e um sinal que
    muda comportamento sem motivo escrito é o que apodrece."""
    cliente = AccountFactory()

    with pytest.raises(ValidationError) as erro:
        Satisfacao(
            account=cliente, nivel=Satisfacao.Nivel.INSATISFEITO,
            fonte=Satisfacao.Fonte.DECLARADA, happened_on=HOJE, note="   ",
        ).clean()
    assert "note" in erro.value.message_dict

    Satisfacao(
        account=cliente, nivel=Satisfacao.Nivel.NEUTRO,
        fonte=Satisfacao.Fonte.DECLARADA, happened_on=HOJE,
    ).clean()


# --- O contrato ---------------------------------------------------------------


@pytest.mark.django_db
def test_vendas_cria_le_edita_e_arquiva(client: APIClient) -> None:
    """Vendas **escreve**, e é a diferença deste recurso para o `risco` (só Entrega)."""
    sales = UserFactory(role=User.Role.SALES)
    cliente = AccountFactory()
    client.force_authenticate(sales)

    created = client.post(reverse("satisfacao-list"), _payload(cliente.id), format="json")
    assert created.status_code == 201
    assert created.data["registered_by"] == sales.id
    assert created.data["nivel_display"] == "Satisfeito"
    assert created.data["fonte_display"] == "Declarada pelo cliente"
    registro_id = created.data["id"]

    updated = client.patch(
        reverse("satisfacao-detail", args=[registro_id]),
        {"nivel": Satisfacao.Nivel.PROMOTOR},
        format="json",
    )
    assert updated.status_code == 200
    assert updated.data["nivel"] == Satisfacao.Nivel.PROMOTOR

    archived = client.delete(reverse("satisfacao-detail", args=[registro_id]))
    assert archived.status_code == 204
    assert Satisfacao.objects.get(pk=registro_id).archived_at is not None
    assert registro_id not in [row["id"] for row in client.get(reverse("satisfacao-list")).data]

    restored = client.post(reverse("satisfacao-unarchive", args=[registro_id]))
    assert restored.status_code == 200
    assert registro_id in [row["id"] for row in client.get(reverse("satisfacao-list")).data]


@pytest.mark.django_db
def test_entrega_registra_no_cliente_de_projeto_seu(client: APIClient) -> None:
    delivery = UserFactory(role=User.Role.DELIVERY)
    projeto = ProjectFactory()
    ProjectMemberFactory(project=projeto, user=delivery)
    client.force_authenticate(delivery)

    created = client.post(
        reverse("satisfacao-list"),
        _payload(
            projeto.engagement.account_id, project=projeto.id, fonte=Satisfacao.Fonte.PERCEBIDA,
            nivel=Satisfacao.Nivel.NEUTRO,
        ),
        format="json",
    )

    assert created.status_code == 201
    assert created.data["project"] == projeto.id
    assert client.get(reverse("satisfacao-detail", args=[created.data["id"]])).status_code == 200


@pytest.mark.django_db
def test_entrega_nao_alcanca_cliente_sem_projeto_seu_nem_para_ler(client: APIClient) -> None:
    """As duas metades da fronteira, no molde do `test_riscos.py` — e aqui a pergunta é sobre o
    cliente, porque o projeto do registro é opcional."""
    delivery = UserFactory(role=User.Role.DELIVERY)
    meu = ProjectFactory()
    ProjectMemberFactory(project=meu, user=delivery)
    alheio = AccountFactory(name="Cliente alheio")
    registro_alheio = Satisfacao.objects.create(
        account=alheio, nivel=Satisfacao.Nivel.INSATISFEITO, fonte=Satisfacao.Fonte.DECLARADA,
        happened_on=HOJE, note="Segredo do cliente alheio.",
    )
    client.force_authenticate(delivery)

    listed = client.get(reverse("satisfacao-list"))
    detalhe = client.get(reverse("satisfacao-detail", args=[registro_alheio.id]))
    criacao = client.post(reverse("satisfacao-list"), _payload(alheio.id), format="json")

    assert [row["id"] for row in listed.data] == []
    assert detalhe.status_code == 404  # fora da queryset: nem existe, do ponto de vista dela
    assert criacao.status_code in {403, 404}
    assert Satisfacao.objects.filter(account=alheio).count() == 1


@pytest.mark.django_db
def test_entrega_nao_move_registro_proprio_para_cliente_alheio(client: APIClient) -> None:
    """O caminho inverso da mesma fronteira: sem ele, mover é o atalho para criar lá dentro."""
    delivery = UserFactory(role=User.Role.DELIVERY)
    meu = ProjectFactory()
    ProjectMemberFactory(project=meu, user=delivery)
    alheio = AccountFactory()
    registro = Satisfacao.objects.create(
        account=meu.engagement.account, nivel=Satisfacao.Nivel.NEUTRO, fonte=Satisfacao.Fonte.PERCEBIDA,
        happened_on=HOJE,
    )
    client.force_authenticate(delivery)

    response = client.patch(
        reverse("satisfacao-detail", args=[registro.id]), {"account": alheio.id}, format="json"
    )

    assert response.status_code == 403
    registro.refresh_from_db()
    assert registro.account_id == meu.engagement.account_id


@pytest.mark.django_db
def test_quem_nao_foi_liberado_nao_alcanca_o_recurso(client: APIClient) -> None:
    """Recurso novo nasce fechado: o papel sem nenhuma linha para ele cai no `return False`."""
    cliente = AccountFactory()
    registro = Satisfacao.objects.create(
        account=cliente, nivel=Satisfacao.Nivel.NEUTRO, fonte=Satisfacao.Fonte.PERCEBIDA,
        happened_on=HOJE,
    )
    sem_papel = UserFactory(role="")
    client.force_authenticate(sem_papel)

    assert client.get(reverse("satisfacao-list")).status_code == 403
    assert client.get(reverse("satisfacao-detail", args=[registro.id])).status_code == 403
    assert client.post(
        reverse("satisfacao-list"), _payload(cliente.id), format="json"
    ).status_code == 403


@pytest.mark.django_db
def test_o_autor_nao_entra_pelo_corpo(client: APIClient) -> None:
    admin = UserFactory(role=User.Role.ADMIN)
    outro = UserFactory(role=User.Role.DELIVERY)
    cliente = AccountFactory()
    client.force_authenticate(admin)

    created = client.post(
        reverse("satisfacao-list"),
        _payload(cliente.id, registered_by=outro.id),
        format="json",
    )

    assert created.status_code == 201
    assert created.data["registered_by"] == admin.id


@pytest.mark.django_db
def test_a_api_recusa_projeto_de_outro_cliente_com_400(client: APIClient) -> None:
    admin = UserFactory(role=User.Role.ADMIN)
    cliente = AccountFactory()
    alheio = ProjectFactory()
    client.force_authenticate(admin)

    response = client.post(
        reverse("satisfacao-list"), _payload(cliente.id, project=alheio.id), format="json"
    )

    assert response.status_code == 400
    assert "project" in response.data


@pytest.mark.django_db
def test_insatisfeito_sem_nota_e_recusado_com_400(client: APIClient) -> None:
    """Critério de aceite 8: 400 e não 500 — a regra do `clean()` repetida no serializer."""
    admin = UserFactory(role=User.Role.ADMIN)
    cliente = AccountFactory()
    client.force_authenticate(admin)

    response = client.post(
        reverse("satisfacao-list"),
        _payload(cliente.id, nivel=Satisfacao.Nivel.INSATISFEITO, note="  "),
        format="json",
    )

    assert response.status_code == 400
    assert "note" in response.data
    assert not Satisfacao.objects.exists()


@pytest.mark.django_db
def test_os_filtros_separam_cliente_nivel_e_fonte(client: APIClient) -> None:
    admin = UserFactory(role=User.Role.ADMIN)
    um, outro = AccountFactory(), AccountFactory()
    declarada = Satisfacao.objects.create(
        account=um, nivel=Satisfacao.Nivel.INSATISFEITO, fonte=Satisfacao.Fonte.DECLARADA,
        happened_on=HOJE, note="Reclamou do prazo do marco 2.",
    )
    percebida = Satisfacao.objects.create(
        account=um, nivel=Satisfacao.Nivel.NEUTRO, fonte=Satisfacao.Fonte.PERCEBIDA,
        happened_on=HOJE,
    )
    Satisfacao.objects.create(
        account=outro, nivel=Satisfacao.Nivel.PROMOTOR, fonte=Satisfacao.Fonte.DECLARADA,
        happened_on=HOJE,
    )
    client.force_authenticate(admin)

    def _ids(**params: object) -> list[int]:
        return [row["id"] for row in client.get(reverse("satisfacao-list"), params).data]

    assert set(_ids(account=um.id)) == {declarada.id, percebida.id}
    assert _ids(fonte=Satisfacao.Fonte.PERCEBIDA) == [percebida.id]
    assert _ids(nivel=Satisfacao.Nivel.INSATISFEITO) == [declarada.id]
