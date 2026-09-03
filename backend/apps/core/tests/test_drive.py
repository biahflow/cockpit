import pytest

from apps.core import drive
from apps.core.models import Document

from .factories import AccountFactory, CommercialOpportunityFactory, ProjectFactory


@pytest.mark.django_db
@pytest.mark.parametrize("kind, pasta", list(drive.PASTA_POR_FINALIDADE.items()))
def test_pasta_do_documento_segue_a_finalidade(kind: str, pasta: str):
    account = AccountFactory()

    assert drive.pasta_do_documento(Document(kind=kind, account=account)) == pasta


@pytest.mark.django_db
def test_pasta_do_documento_sem_finalidade_cai_em_outros():
    account = AccountFactory()

    assert drive.pasta_do_documento(Document(account=account)) == drive.PASTA_SEM_FINALIDADE
    assert drive.pasta_do_documento(Document(kind="", account=account)) == drive.PASTA_SEM_FINALIDADE


def test_mapa_de_pasta_e_exaustivo_sobre_document_kind():
    """Paga o preço de o mapa ser uma segunda definição do rótulo de `Document.Kind`: sem este
    teste, um `Kind` novo cairia calado em 'Outros' e ninguém veria (issue #113)."""
    chaves_do_kind = {value for value, _ in Document.Kind.choices}

    assert set(drive.PASTA_POR_FINALIDADE) == chaves_do_kind


@pytest.mark.django_db
def test_pasta_do_documento_nao_depende_do_vinculo():
    """A troca de critério (issue #113): o mesmo `kind` em vínculos diferentes dá a mesma pasta —
    o vínculo decidia antes, e não decide mais."""
    account = AccountFactory()
    opportunity = CommercialOpportunityFactory(account=account)
    project = ProjectFactory(engagement__account=account)

    pasta_conta = drive.pasta_do_documento(Document(kind="nda", account=account))
    pasta_oportunidade = drive.pasta_do_documento(
        Document(kind="nda", commercial_opportunity=opportunity)
    )
    pasta_projeto = drive.pasta_do_documento(Document(kind="nda", project=project))

    assert pasta_conta == pasta_oportunidade == pasta_projeto == "NDAs"


@pytest.mark.django_db
def test_account_of_resolves_owner_from_any_link():
    account = AccountFactory()
    opportunity = CommercialOpportunityFactory(account=account)
    project = ProjectFactory(engagement__account=account)

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
