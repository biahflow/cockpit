"""Biblioteca de Funcionários Digitais — catálogo, variantes e instanciação (FDD 026)."""

from decimal import Decimal

import pytest
from django.db import IntegrityError, transaction
from rest_framework.test import APIClient

from apps.core import blueprints
from apps.core.models import (
    BlueprintVariant,
    DigitalEmployee,
    DigitalEmployeeBlueprint,
    KpiDirection,
    KpiUnit,
    Service,
    Vertical,
)

from .factories import AccountFactory, ProjectFactory, ProjectMemberFactory, UserFactory


def _admin_client() -> APIClient:
    client = APIClient()
    client.force_authenticate(UserFactory(role="admin"))
    return client


def _blueprint(**overrides) -> DigitalEmployeeBlueprint:
    campos = {
        "name": "SDR",
        "area": DigitalEmployeeBlueprint.Area.COMMERCIAL,
        "description": "Qualifica lead fora do horário comercial.",
        "kpi_label": "Leads qualificados/mês",
        "default_hours_saved_month": Decimal("40.0"),
        "default_roi_month": Decimal("8000.00"),
    }
    return DigitalEmployeeBlueprint.objects.create(**{**campos, **overrides})


def _vertical(name: str = "Igrejas", slug: str = "igrejas", **overrides) -> Vertical:
    return Vertical.objects.create(name=name, slug=slug, **overrides)


# --- a invariante que impede duplicata silenciosa ---------------------------------------------


@pytest.mark.django_db
def test_second_variant_for_the_same_vertical_is_rejected():
    blueprint, vertical = _blueprint(), _vertical()
    client = _admin_client()
    payload = {"blueprint": blueprint.pk, "vertical": vertical.pk, "description": "Dízimo."}

    assert client.post("/api/v1/blueprint-variants/", payload, format="json").status_code == 201
    repetida = client.post("/api/v1/blueprint-variants/", payload, format="json")

    assert repetida.status_code == 400
    with pytest.raises(IntegrityError), transaction.atomic():
        BlueprintVariant.objects.create(blueprint=blueprint, vertical=vertical)


# --- resolução: a variante sobrescreve, o branco herda ------------------------------------------


@pytest.mark.django_db
def test_variant_overrides_only_what_it_fills():
    blueprint, vertical = _blueprint(), _vertical()
    BlueprintVariant.objects.create(
        blueprint=blueprint, vertical=vertical,
        description="Qualifica visitante de culto e agenda visita pastoral.",
        default_roi_month=Decimal("12000.00"),
    )
    blueprint.refresh_from_db()

    resolvido = blueprints.resolve(blueprint, vertical)

    assert resolvido["description"] == "Qualifica visitante de culto e agenda visita pastoral."
    assert resolvido["roi_month"] == Decimal("12000.00")
    # Em branco na variante herda o do blueprint — a variante diz o que muda, não repete o resto.
    assert resolvido["kpi_label"] == "Leads qualificados/mês"
    assert resolvido["hours_saved_month"] == Decimal("40.0")


@pytest.mark.django_db
def test_resolution_without_vertical_falls_back_to_the_blueprint():
    blueprint = _blueprint()
    BlueprintVariant.objects.create(
        blueprint=blueprint, vertical=_vertical(), description="Só para igrejas."
    )
    blueprint.refresh_from_db()

    resolvido = blueprints.resolve(blueprint, None)

    assert resolvido["description"] == "Qualifica lead fora do horário comercial."


@pytest.mark.django_db
def test_unidade_e_direcao_do_kpi_nao_passam_pela_variante():
    """O rótulo do KPI é do setor; a unidade e a direção são o que torna os cases comparáveis.

    Deixar uma variante trocá-las faria duas instâncias do **mesmo bloco** deixarem de se comparar
    sem nada dizer — que é o que a FDD 027 existe para impedir.
    """
    blueprint = _blueprint(kpi_unit=KpiUnit.COUNT, kpi_direction=KpiDirection.UP)
    vertical = _vertical()
    BlueprintVariant.objects.create(
        blueprint=blueprint, vertical=vertical, kpi_label="Visitantes qualificados/mês"
    )
    blueprint.refresh_from_db()

    resolvido = blueprints.resolve(blueprint, vertical)

    assert resolvido["kpi_label"] == "Visitantes qualificados/mês"
    assert resolvido["kpi_unit"] == KpiUnit.COUNT
    assert resolvido["kpi_direction"] == KpiDirection.UP


# --- instanciar copia ---------------------------------------------------------------------------


@pytest.mark.django_db
def test_instantiating_copies_the_catalog_into_the_project():
    vertical = _vertical()
    project = ProjectFactory(engagement__account=AccountFactory(vertical=vertical))
    blueprint = _blueprint()
    BlueprintVariant.objects.create(
        blueprint=blueprint, vertical=vertical, description="Agenda visita pastoral.",
        default_hours_saved_month=Decimal("55.0"),
    )
    client = _admin_client()

    created = client.post(
        f"/api/v1/projects/{project.pk}/digital-employees/from-blueprint/",
        {"blueprint": blueprint.pk}, format="json",
    )

    assert created.status_code == 201
    corpo = created.json()
    assert corpo["name"] == "SDR"
    # O rótulo, não o slug: é o que a tela mostra e o que o snapshot leva ao cliente.
    assert corpo["area"] == "Comercial"
    assert corpo["description"] == "Agenda visita pastoral."  # veio da variante da vertical
    assert corpo["kpi_label"] == "Leads qualificados/mês"  # herdado do blueprint
    assert corpo["hours_saved_month"] == "55.0"
    assert corpo["status"] == "building"
    assert corpo["blueprint"] == blueprint.pk  # procedência


@pytest.mark.django_db
def test_editing_the_blueprint_does_not_rewrite_what_was_delivered():
    """A razão de ser da cópia (FDD 011, FDD 026): o catálogo muda, o entregue não."""
    project = ProjectFactory()
    blueprint = _blueprint()
    _admin_client().post(
        f"/api/v1/projects/{project.pk}/digital-employees/from-blueprint/",
        {"blueprint": blueprint.pk}, format="json",
    )

    blueprint.name = "SDR 2.0"
    blueprint.description = "Outra coisa completamente."
    blueprint.default_roi_month = Decimal("99999.00")
    blueprint.save()

    employee = DigitalEmployee.objects.get(project=project)
    assert employee.name == "SDR"
    assert employee.description == "Qualifica lead fora do horário comercial."
    assert employee.roi_month == Decimal("8000.00")


@pytest.mark.django_db
def test_client_without_vertical_still_instantiates_from_the_generic_catalog():
    project = ProjectFactory(engagement__account=AccountFactory(vertical=None))
    blueprint = _blueprint()
    BlueprintVariant.objects.create(
        blueprint=blueprint, vertical=_vertical(), description="Só para igrejas."
    )

    created = _admin_client().post(
        f"/api/v1/projects/{project.pk}/digital-employees/from-blueprint/",
        {"blueprint": blueprint.pk}, format="json",
    )

    assert created.status_code == 201
    assert created.json()["description"] == "Qualifica lead fora do horário comercial."


@pytest.mark.django_db
def test_inactive_blueprint_is_not_instantiable():
    project = ProjectFactory()
    blueprint = _blueprint(active=False)

    recusa = _admin_client().post(
        f"/api/v1/projects/{project.pk}/digital-employees/from-blueprint/",
        {"blueprint": blueprint.pk}, format="json",
    )

    assert recusa.status_code == 400
    assert not DigitalEmployee.objects.filter(project=project).exists()


@pytest.mark.django_db
def test_blueprint_is_read_only_on_the_digital_employee():
    """Gravável, seria um segundo caminho que aponta para o template sem copiar nada."""
    project = ProjectFactory()
    blueprint = _blueprint()
    person = UserFactory(role="delivery")
    ProjectMemberFactory(project=project, user=person)
    client = APIClient()
    client.force_authenticate(person)

    created = client.post("/api/v1/digital-employees/", {
        "project": project.pk, "name": "Feito à mão", "blueprint": blueprint.pk,
    }, format="json")

    assert created.status_code == 201
    assert created.json()["blueprint"] is None
    assert DigitalEmployee.objects.get(pk=created.json()["id"]).blueprint_id is None


# --- listagem resolvida --------------------------------------------------------------------------


@pytest.mark.django_db
def test_listing_with_a_vertical_resolves_without_filtering_anything_out():
    vertical = _vertical()
    com_variante = _blueprint()
    BlueprintVariant.objects.create(
        blueprint=com_variante, vertical=vertical, description="Ajustado ao setor."
    )
    _blueprint(name="Agente Financeiro", area=DigitalEmployeeBlueprint.Area.FINANCE)

    listado = _admin_client().get(f"/api/v1/digital-employee-blueprints/?vertical={vertical.pk}")

    assert listado.status_code == 200
    linhas = {row["name"]: row for row in listado.json()}
    # O genérico continua na lista: filtrar por vertical esconderia o que serve a qualquer setor.
    assert set(linhas) == {"SDR", "Agente Financeiro"}
    assert linhas["SDR"]["has_variant"] is True
    assert linhas["SDR"]["resolved"]["description"] == "Ajustado ao setor."
    assert linhas["Agente Financeiro"]["has_variant"] is False
    assert linhas["Agente Financeiro"]["resolved"]["description"] == (
        "Qualifica lead fora do horário comercial."
    )


@pytest.mark.django_db
def test_listing_can_ask_only_for_the_active_catalog():
    _blueprint()
    _blueprint(name="Aposentado", active=False)
    client = _admin_client()

    assert len(client.get("/api/v1/digital-employee-blueprints/").json()) == 2
    ativos = client.get("/api/v1/digital-employee-blueprints/?active=1").json()
    assert [row["name"] for row in ativos] == ["SDR"]


# --- aposentar é desativar (FDD 025) --------------------------------------------------------------


@pytest.mark.django_db
def test_blueprint_with_a_live_instance_refuses_deletion_and_points_at_the_way_out():
    project = ProjectFactory()
    blueprint = _blueprint()
    client = _admin_client()
    client.post(
        f"/api/v1/projects/{project.pk}/digital-employees/from-blueprint/",
        {"blueprint": blueprint.pk}, format="json",
    )

    recusa = client.delete(f"/api/v1/digital-employee-blueprints/{blueprint.pk}/")

    assert recusa.status_code == 409
    assert "Desative" in recusa.json()["detail"]
    assert DigitalEmployeeBlueprint.objects.filter(pk=blueprint.pk).exists()
    # E a saída que a recusa oferece funciona.
    assert client.patch(
        f"/api/v1/digital-employee-blueprints/{blueprint.pk}/", {"active": False}, format="json"
    ).status_code == 200


@pytest.mark.django_db
def test_unused_blueprint_is_deleted_for_real():
    blueprint = _blueprint()
    assert _admin_client().delete(
        f"/api/v1/digital-employee-blueprints/{blueprint.pk}/"
    ).status_code == 204
    assert not DigitalEmployeeBlueprint.objects.filter(pk=blueprint.pk).exists()


@pytest.mark.django_db
def test_vertical_in_use_refuses_deletion_instead_of_silently_clearing_clients():
    """`Account.vertical` é `SET_NULL`: sem a guarda, o setor de todo cliente sumiria calado."""
    vertical = _vertical()
    AccountFactory(vertical=vertical)

    recusa = _admin_client().delete(f"/api/v1/verticals/{vertical.pk}/")

    assert recusa.status_code == 409
    assert "cliente(s)" in recusa.json()["detail"]
    assert Vertical.objects.filter(pk=vertical.pk).exists()


@pytest.mark.django_db
def test_vertical_with_variants_refuses_deletion():
    vertical = _vertical()
    BlueprintVariant.objects.create(blueprint=_blueprint(), vertical=vertical)

    recusa = _admin_client().delete(f"/api/v1/verticals/{vertical.pk}/")

    assert recusa.status_code == 409
    assert "variante(s)" in recusa.json()["detail"]


# --- acesso: catálogo global, leitura para todos, escrita só admin --------------------------------


@pytest.mark.django_db
@pytest.mark.parametrize("role", ["sales", "delivery"])
def test_catalog_is_readable_by_any_authenticated_role(role):
    blueprint, vertical = _blueprint(), _vertical()
    client = APIClient()
    client.force_authenticate(UserFactory(role=role))

    assert client.get("/api/v1/digital-employee-blueprints/").status_code == 200
    assert client.get("/api/v1/verticals/").status_code == 200
    # O **detalhe** também: é dele que sai a instanciação, e antes disso a Entrega tomava 403 aqui
    # (o mesmo buraco valia para `/services/{id}/`).
    assert client.get(f"/api/v1/digital-employee-blueprints/{blueprint.pk}/").status_code == 200
    assert client.get(f"/api/v1/verticals/{vertical.pk}/").status_code == 200


@pytest.mark.django_db
def test_delivery_reads_a_service_detail_too():
    """O buraco que a Biblioteca revelou já valia para o catálogo de serviços (FDD 015)."""
    service = Service.objects.get(tier=Service.Tier.DISCOVERY_SPRINT)
    client = APIClient()
    client.force_authenticate(UserFactory(role="delivery"))
    assert client.get(f"/api/v1/services/{service.pk}/").status_code == 200


@pytest.mark.django_db
@pytest.mark.parametrize("role", ["sales", "delivery"])
def test_only_admin_writes_the_catalog(role):
    client = APIClient()
    client.force_authenticate(UserFactory(role=role))

    assert client.post(
        "/api/v1/digital-employee-blueprints/", {"name": "X", "area": "comercial"}, format="json"
    ).status_code == 403
    assert client.post(
        "/api/v1/verticals/", {"name": "X", "slug": "x"}, format="json"
    ).status_code == 403


@pytest.mark.django_db
def test_delivery_instantiates_inside_its_own_project_only():
    blueprint = _blueprint()
    meu, alheio = ProjectFactory(), ProjectFactory()
    person = UserFactory(role="delivery")
    ProjectMemberFactory(project=meu, user=person)
    client = APIClient()
    client.force_authenticate(person)

    assert client.post(
        f"/api/v1/projects/{meu.pk}/digital-employees/from-blueprint/",
        {"blueprint": blueprint.pk}, format="json",
    ).status_code == 201
    assert client.post(
        f"/api/v1/projects/{alheio.pk}/digital-employees/from-blueprint/",
        {"blueprint": blueprint.pk}, format="json",
    ).status_code == 404
    assert not DigitalEmployee.objects.filter(project=alheio).exists()


@pytest.mark.django_db
def test_sales_reads_the_roster_but_does_not_instantiate():
    project = ProjectFactory()
    blueprint = _blueprint()
    client = APIClient()
    client.force_authenticate(UserFactory(role="sales"))

    recusa = client.post(
        f"/api/v1/projects/{project.pk}/digital-employees/from-blueprint/",
        {"blueprint": blueprint.pk}, format="json",
    )

    assert recusa.status_code == 403
    assert not DigitalEmployee.objects.filter(project=project).exists()


# --- a vertical no cliente ------------------------------------------------------------------------


@pytest.mark.django_db
def test_client_carries_a_vertical_and_the_project_exposes_it():
    vertical = _vertical()
    cliente = AccountFactory()
    project = ProjectFactory(engagement__account=cliente)
    client = _admin_client()

    atualizado = client.patch(
        f"/api/v1/clients/{cliente.pk}/", {"vertical": vertical.pk}, format="json"
    )

    assert atualizado.status_code == 200
    assert atualizado.json()["vertical_name"] == "Igrejas"
    projeto = client.get(f"/api/v1/projects/{project.pk}/").json()
    assert projeto["client_vertical"] == vertical.pk
    assert projeto["client_vertical_name"] == "Igrejas"
