import pytest
from rest_framework.test import APIClient

from apps.core.models import DigitalEmployee

from .factories import ProjectFactory, ProjectMemberFactory, UserFactory


@pytest.mark.django_db
def test_delivery_can_create_and_list_digital_employees():
    project = ProjectFactory()
    person = UserFactory(role="delivery")
    ProjectMemberFactory(project=project, user=person)
    client = APIClient()
    client.force_authenticate(person)

    created = client.post("/api/v1/digital-employees/", {
        "project": project.pk, "name": "Agente Financeiro", "area": "Financeiro",
        "description": "Concilia contas a pagar.", "status": "active",
        "kpi_label": "Conciliação", "kpi_value": "80%",
        "hours_saved_month": "120.0", "roi_month": "14000.00",
    }, format="json")
    assert created.status_code == 201

    listed = client.get(f"/api/v1/digital-employees/?project={project.pk}")
    assert listed.status_code == 200
    names = [row["name"] for row in listed.json()]
    assert "Agente Financeiro" in names


@pytest.mark.django_db
def test_sales_cannot_write_digital_employees():
    project = ProjectFactory()
    client = APIClient()
    client.force_authenticate(UserFactory(role="sales"))
    response = client.post("/api/v1/digital-employees/", {"project": project.pk, "name": "X"}, format="json")
    assert response.status_code == 403


@pytest.mark.django_db
def test_archived_employee_is_hidden_from_list():
    project = ProjectFactory()
    employee = DigitalEmployee.objects.create(project=project, name="Agente Atendimento")
    employee.archive()
    client = APIClient()
    client.force_authenticate(UserFactory(role="delivery"))
    listed = client.get(f"/api/v1/digital-employees/?project={project.pk}")
    assert listed.json() == []
