import pytest

from apps.core import drive
from apps.core.models import Document

from .factories import AccountFactory, CommercialOpportunityFactory, ProjectFactory


@pytest.mark.django_db
def test_para_bucket_for_follows_link_type():
    account = AccountFactory()
    opportunity = CommercialOpportunityFactory(account=account)
    project = ProjectFactory(client=account)

    assert drive.para_bucket_for(Document(account=account)) == drive.CLIENT_BUCKET
    assert drive.para_bucket_for(Document(commercial_opportunity=opportunity)) == drive.OPPORTUNITY_BUCKET
    assert drive.para_bucket_for(Document(project=project)) == drive.PROJECT_BUCKET


@pytest.mark.django_db
def test_account_of_resolves_owner_from_any_link():
    account = AccountFactory()
    opportunity = CommercialOpportunityFactory(account=account)
    project = ProjectFactory(client=account)

    assert drive.account_of(Document(account=account)) == account
    assert drive.account_of(Document(commercial_opportunity=opportunity)) == account
    assert drive.account_of(Document(project=project)) == account
    assert drive.account_of(Document()) is None


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


class _RespostaFalsa:
    """O mínimo do `HttpError` do SDK que a classificação lê: `exc.resp.status`."""

    def __init__(self, status: int) -> None:
        self.status = status


class _ErroDoSdk(Exception):
    def __init__(self, status: int) -> None:
        super().__init__(f"HTTP {status}")
        self.resp = _RespostaFalsa(status)


def _service_que_recusa(status: int):  # type: ignore[no-untyped-def]
    class _Files:
        def delete(self, **kwargs):  # type: ignore[no-untyped-def]
            return self

        def execute(self):  # type: ignore[no-untyped-def]
            raise _ErroDoSdk(status)

    class _Service:
        def files(self):  # type: ignore[no-untyped-def]
            return _Files()

    return lambda: _Service()


def test_apagar_o_que_ja_sumiu_do_drive_e_sucesso(monkeypatch: pytest.MonkeyPatch) -> None:
    """404 não é falha: apagar o que já não existe **é** o estado desejado do expurgo (ADR 0017).

    Sem isto, um arquivo removido à mão na interface do Google prendia a linha para sempre — toda
    execução do expurgo falhava igual, e o dado pessoal ficava impossível de esquecer.
    """
    monkeypatch.setattr(drive, "_service", _service_que_recusa(404))

    drive.delete_document(Document(drive_file_id="ja-nao-existe"))  # não levanta


def test_qualquer_outra_recusa_do_drive_continua_levantando(monkeypatch: pytest.MonkeyPatch) -> None:
    """A trava que não pode afrouxar: credencial ausente **não** é "já foi apagado".

    Tratar as duas como a mesma coisa apagaria o índice deixando o conteúdo no Drive — o pior
    resultado possível de um expurgo, e o que o módulo inteiro existe para evitar.
    """
    monkeypatch.setattr(drive, "_service", _service_que_recusa(403))

    with pytest.raises(drive.DriveProviderError):
        drive.delete_document(Document(drive_file_id="sem-permissao"))
