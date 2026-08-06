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
    settings.GOOGLE_DRIVE_ROOT_FOLDER_ID = "pasta-raiz"  # sem credencial nada liga (ADR 0018)
    settings.GOOGLE_DRIVE_ENABLED = True
    assert drive.is_enabled() is True
    settings.GOOGLE_DRIVE_ENABLED = False
    assert drive.is_enabled() is False


# --- id da pasta raiz: aceitar o que a pessoa tem em mãos (rodada 3) ----------------------------


def test_id_da_pasta_aceita_o_proprio_id() -> None:
    assert drive.parse_root_folder_id("0AAu4rVaHw9hLUk9PVA") == "0AAu4rVaHw9hLUk9PVA"


def test_id_da_pasta_aceita_a_url_colada_do_navegador() -> None:
    """O id só existe **dentro** da URL — é de lá que a pessoa o copia. Colar a URL inteira é o
    erro natural, e ele não pode virar um 404 do Drive parecendo problema de permissão.
    Observado na rodada 3 da homologação (FDD 024).
    """
    url = "https://drive.google.com/drive/u/0/folders/0AAu4rVaHw9hLUk9PVA?ms=pt:1458%3Bs:539"

    assert drive.parse_root_folder_id(url) == "0AAu4rVaHw9hLUk9PVA"


def test_id_da_pasta_aceita_url_simples_sem_query() -> None:
    assert drive.parse_root_folder_id(
        "https://drive.google.com/drive/folders/1A2b3C4d5E6f"
    ) == "1A2b3C4d5E6f"


def test_id_da_pasta_ignora_espaco_em_volta() -> None:
    assert drive.parse_root_folder_id("  0AAu4rVaHw9hLUk9PVA  ") == "0AAu4rVaHw9hLUk9PVA"


def test_url_sem_folders_fica_como_veio() -> None:
    """Não inventamos id: o que não casa com o padrão segue igual, e quem reclama é a sonda."""
    assert drive.parse_root_folder_id("https://drive.google.com/qualquer") == (
        "https://drive.google.com/qualquer"
    )
