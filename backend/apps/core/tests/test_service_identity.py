"""Como este serviço se identifica para outro serviço nosso (ADR 0029).

O que estes testes protegem, em ordem de importância:

1. **Fora do Cloud Run não há tentativa.** É o caso do compose, da sua máquina e do CI, e
   é o caminho que mais roda. Sem a guarda, cada webhook pagaria o timeout do metadata
   server inexistente dentro de uma thread daemon que tem 5 s no total — o webhook
   chegaria tarde ou não chegaria, num ambiente onde barreira nenhuma existe.
2. **A audiência é a origem, não a URL.** Um token cunhado para a URL inteira é recusado
   pelo Cloud Run com mensagem sobre audiência, que não parece erro de caminho.
3. **O cache existe.** São doze emissores de webhook; uma ida ao metadata por evento é
   custo puro.
"""

from __future__ import annotations

import pytest

from apps.core import portal, service_identity


@pytest.fixture(autouse=True)
def _cache_limpo() -> None:
    service_identity.limpar_cache()


def test_fora_do_cloud_run_nao_ha_token(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("K_SERVICE", raising=False)
    assert service_identity.id_token_para("https://portal-api-1.run.app/api/v1/x") is None


def test_a_audiencia_e_a_origem_e_nao_o_caminho() -> None:
    audiencia = service_identity.audiencia_de(
        "https://portal-api-209400815796.us-east1.run.app/api/v1/integrations/biahflow/webhook"
    )
    assert audiencia == "https://portal-api-209400815796.us-east1.run.app"


def test_url_sem_esquema_nao_produz_audiencia() -> None:
    assert service_identity.audiencia_de("portal-api/webhook") is None


def test_dentro_do_cloud_run_cunha_com_a_audiencia_certa(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("K_SERVICE", "biahflow-api")
    pedidas: list[str] = []

    def fake_fetch(request: object, audiencia: str) -> str:
        pedidas.append(audiencia)
        return "id-token-de-mentira"

    _instala_fetch(monkeypatch, fake_fetch)

    token = service_identity.id_token_para("https://portal-api-1.run.app/api/v1/hook")

    assert token == "id-token-de-mentira"
    assert pedidas == ["https://portal-api-1.run.app"]


def test_o_cache_evita_uma_ida_por_evento(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("K_SERVICE", "biahflow-api")
    idas: list[str] = []
    _instala_fetch(monkeypatch, lambda request, audiencia: idas.append(audiencia) or "t")

    for _ in range(3):
        service_identity.id_token_para("https://portal-api-1.run.app/api/v1/hook")

    assert len(idas) == 1


def test_falha_ao_cunhar_nao_estoura(monkeypatch: pytest.MonkeyPatch) -> None:
    """Sem token o webhook sai como saía. Levantar mudaria o contrato best-effort."""
    monkeypatch.setenv("K_SERVICE", "biahflow-api")

    def explode(request: object, audiencia: str) -> str:
        raise RuntimeError("metadata fora do ar")

    _instala_fetch(monkeypatch, explode)
    assert service_identity.id_token_para("https://portal-api-1.run.app/x") is None


def test_o_post_leva_o_token_quando_ha(monkeypatch: pytest.MonkeyPatch) -> None:
    """A metade que importa para o Cloud Run: o header sai no `Authorization`."""
    visto: dict[str, object] = {}

    class FakeResponse:
        def __enter__(self) -> FakeResponse:
            return self

        def __exit__(self, *args: object) -> bool:
            return False

        def read(self) -> bytes:
            return b""

    def fake_urlopen(request, timeout):  # type: ignore[no-untyped-def]
        visto["auth"] = request.get_header("Authorization")
        visto["assinatura"] = request.get_header("X-biahflow-signature")
        return FakeResponse()

    monkeypatch.setattr(portal.urllib.request, "urlopen", fake_urlopen)
    monkeypatch.setattr(portal.service_identity, "id_token_para", lambda url: "tok")

    portal._post("https://portal-api-1.run.app/hook", b"{}", "abc")

    assert visto["auth"] == "Bearer tok"
    # A assinatura continua sendo o que autentica na aplicação — o token é do provedor.
    assert visto["assinatura"] == "sha256=abc"


def test_o_post_sem_token_manda_o_que_mandava(monkeypatch: pytest.MonkeyPatch) -> None:
    """O caminho do compose. Um `Authorization` vazio seria pior que nenhum."""
    visto: dict[str, object] = {}

    class FakeResponse:
        def __enter__(self) -> FakeResponse:
            return self

        def __exit__(self, *args: object) -> bool:
            return False

        def read(self) -> bytes:
            return b""

    def fake_urlopen(request, timeout):  # type: ignore[no-untyped-def]
        visto["auth"] = request.get_header("Authorization")
        return FakeResponse()

    monkeypatch.setattr(portal.urllib.request, "urlopen", fake_urlopen)
    monkeypatch.setattr(portal.service_identity, "id_token_para", lambda url: None)

    portal._post("http://portal/hook", b"{}", "abc")

    assert visto["auth"] is None


def _instala_fetch(monkeypatch: pytest.MonkeyPatch, funcao: object) -> None:
    """Troca o `fetch_id_token` que o módulo importa tardiamente.

    O import é dentro da função de propósito (fora do Cloud Run nem o import acontece),
    então o alvo do monkeypatch é o módulo do Google, não um atributo nosso.
    """
    import google.oauth2.id_token as google_id_token

    monkeypatch.setattr(google_id_token, "fetch_id_token", funcao)
