import pytest

from apps.core import drive
from apps.core.models import Document

from .factories import ClientFactory, OpportunityFactory, ProjectFactory


@pytest.mark.django_db
def test_para_bucket_for_follows_link_type():
    client = ClientFactory()
    opportunity = OpportunityFactory(client=client)
    project = ProjectFactory(client=client)

    assert drive.para_bucket_for(Document(client=client)) == drive.CLIENT_BUCKET
    assert drive.para_bucket_for(Document(opportunity=opportunity)) == drive.OPPORTUNITY_BUCKET
    assert drive.para_bucket_for(Document(project=project)) == drive.PROJECT_BUCKET


@pytest.mark.django_db
def test_client_of_resolves_owner_from_any_link():
    client = ClientFactory()
    opportunity = OpportunityFactory(client=client)
    project = ProjectFactory(client=client)

    assert drive.client_of(Document(client=client)) == client
    assert drive.client_of(Document(opportunity=opportunity)) == client
    assert drive.client_of(Document(project=project)) == client
    assert drive.client_of(Document()) is None


@pytest.mark.django_db
def test_is_enabled_reflects_setting(settings):
    settings.GOOGLE_DRIVE_ENABLED = True
    assert drive.is_enabled() is True
    settings.GOOGLE_DRIVE_ENABLED = False
    assert drive.is_enabled() is False
