"""Mensagens por WhatsApp: os quatro estados, e quando o fallback assume (ADR 0031).

Nenhum teste atravessa a rede (ADR 0059): a única costura de I/O do módulo é `whatsapp._request`,
e é ela que cada teste substitui — o resto do adaptador roda de verdade.
"""

from __future__ import annotations

import http.client
import socket
import urllib.error

import pytest
from django.test import override_settings

from apps.core import flags, integrations, whatsapp
from apps.core.whatsapp import Delivery, HttpAnswer

LIGADO = override_settings(
    WHATSAPP_ENABLED=True,
    WHATSAPP_PROVIDERS="zapi,uazapi",
    WHATSAPP_ZAPI_INSTANCE_ID="inst",
    WHATSAPP_ZAPI_TOKEN="tok",
    WHATSAPP_ZAPI_CLIENT_TOKEN="",
    WHATSAPP_UAZAPI_TOKEN="uaz",
)

# Corpo de sucesso de cada fornecedor, reduzido ao que o adaptador lê.
ZAPI_OK = HttpAnswer(status_code=200, body={"zaapId": "Z1", "messageId": "M1", "id": "M1"})
UAZAPI_OK = HttpAnswer(status_code=200, body={"id": "U1", "messageid": "U1"})


class Rede:
    """Fila de respostas na ordem em que os provedores forem chamados; guarda o que foi pedido."""

    def __init__(self, *answers: HttpAnswer) -> None:
        self.answers = list(answers)
        # O `timeout` entra **no fim** da tupla de propósito: dezenas de asserções já leem
        # `calls[n][2]` (payload) e `calls[n][3]` (método), e mudar a posição delas trocaria a
        # correção de um teto pela reescrita da suíte inteira.
        self.calls: list[tuple[str, dict, dict | None, str, float | None]] = []

    def __call__(
        self,
        url: str,
        headers: dict,
        payload: dict | None = None,
        method: str = "POST",
        timeout: float | None = None,
    ) -> HttpAnswer:
        self.calls.append((url, dict(headers), payload, method, timeout))
        return self.answers.pop(0)

    @property
    def urls(self) -> list[str]:
        return [call[0] for call in self.calls]

    @property
    def timeouts(self) -> list[float | None]:
        return [call[4] for call in self.calls]


@pytest.fixture
def rede(monkeypatch: pytest.MonkeyPatch):
    def instalar(*answers: HttpAnswer) -> Rede:
        fake = Rede(*answers)
        monkeypatch.setattr(whatsapp, "_request", fake)
        return fake

    return instalar


# --- 1. Os quatro estados, cada um a partir da falha que o produz ---------------------------


def test_entregue_quando_o_provedor_aceita():
    assert whatsapp.classify(ZAPI_OK) == (Delivery.DELIVERED, "")
    assert whatsapp.ZApiProvider.read_message(ZAPI_OK).status is Delivery.DELIVERED


@pytest.mark.parametrize(
    "answer",
    [
        HttpAnswer(status_code=401, body={"error": "token inválido"}),
        HttpAnswer(status_code=403, body={}),
        HttpAnswer(status_code=404, body={"error": "instância não encontrada"}),
        HttpAnswer(status_code=429, body={"error": "limite excedido"}),
        HttpAnswer(error=ConnectionRefusedError("conexão recusada")),
        HttpAnswer(error=socket.gaierror("nome não resolve")),
        HttpAnswer(error=urllib.error.URLError("proxy fora do ar")),
    ],
)
def test_indisponivel_quando_este_provedor_nao_pode_mas_outro_poderia(answer: HttpAnswer):
    estado, motivo = whatsapp.classify(answer)
    assert estado is Delivery.UNAVAILABLE
    assert motivo


@pytest.mark.parametrize("code", [400, 422])
def test_recusada_quando_a_mensagem_e_invalida_em_si(code: int):
    """400/422 é payload inválido — o segundo provedor recusaria igual, então não há o que tentar."""
    estado, motivo = whatsapp.classify(HttpAnswer(status_code=code, body={"error": "número"}))
    assert estado is Delivery.REFUSED
    assert "número" in motivo


@pytest.mark.parametrize(
    "answer",
    [
        HttpAnswer(error=TimeoutError("estourou o teto")),
        HttpAnswer(error=urllib.error.URLError(TimeoutError("estourou no handshake"))),
        HttpAnswer(error=ConnectionResetError("conexão cortada")),
        HttpAnswer(error=http.client.IncompleteRead(b"metade")),
        HttpAnswer(status_code=500, body={"error": "erro interno"}),
        HttpAnswer(status_code=502, body={}),
        HttpAnswer(status_code=302, body={}),
        HttpAnswer(error=RuntimeError("nada disso")),
    ],
)
def test_incerta_quando_pode_ter_entregado(answer: HttpAnswer):
    estado, motivo = whatsapp.classify(answer)
    assert estado is Delivery.UNCERTAIN
    assert motivo


def test_timeout_e_sempre_incerto_mesmo_parecendo_falha_de_conexao():
    """Distinguir "timeout antes de enviar" de "timeout esperando resposta" não é confiável.

    `TimeoutError` é subclasse de `OSError`, como `ConnectionRefusedError`; se a ordem das guardas
    invertesse, um timeout viraria `UNAVAILABLE` e o fallback duplicaria a mensagem.
    """
    estado, _ = whatsapp.classify(HttpAnswer(error=TimeoutError("conectando")))
    assert estado is Delivery.UNCERTAIN


def test_duzentos_sem_id_de_mensagem_nao_e_entrega():
    """Os dois fornecedores respondem 200 com corpo de erro em casos que nenhum documenta.

    Sem id não se afirma entrega — e também não se reenvia, que é o caminho conservador.
    """
    resultado = whatsapp.ZApiProvider.read_message(
        HttpAnswer(status_code=200, body={"error": "null not allowed"})
    )
    assert resultado.status is Delivery.UNCERTAIN
    assert resultado.reference == ""
    assert "null not allowed" in resultado.detail


# --- 2. A decisão inteira: `INCERTA` não cai para o segundo provedor -------------------------


@pytest.mark.django_db
@LIGADO
def test_incerta_nao_tenta_o_segundo_provedor(rede):
    """Se a Z-API aceitou e o retorno se perdeu, tentar a UAZAPI manda a mesma mensagem duas vezes.

    Para "sua sessão é amanhã às 10h", dois avisos fazem o cliente ligar perguntando qual vale.
    Aceita-se deixar de enviar para nunca duplicar — e sem este teste a decisão regride para
    "tenta sempre" na primeira refatoração.
    """
    chamadas = rede(HttpAnswer(error=TimeoutError("estourou")), UAZAPI_OK)

    resultado = whatsapp.send_text("5511999999999", "Estou entrando na sala")

    assert resultado.status is Delivery.UNCERTAIN
    assert len(chamadas.calls) == 1, "o segundo provedor não pode ser chamado: duplicaria a mensagem"
    assert [tentativa.provider for tentativa in resultado.attempts] == ["zapi"]


@pytest.mark.django_db
@LIGADO
def test_incerta_por_erro_do_servidor_tambem_nao_cai(rede, caplog):
    chamadas = rede(HttpAnswer(status_code=500, body={"error": "boom"}), UAZAPI_OK)

    with caplog.at_level("INFO"):
        resultado = whatsapp.send_text("5511999999999", "atrasei dez minutos")

    assert resultado.status is Delivery.UNCERTAIN
    assert len(chamadas.calls) == 1
    # Não duplicar não pode virar não avisar: o único estado que ninguém sabe como terminou sobe
    # para `warning`, com a mesma cor de um problema.
    assert [r.levelname for r in caplog.records] == ["WARNING"]


# --- 3. `INDISPONIVEL` cai, e o retorno diz quem entregou -----------------------------------


@pytest.mark.django_db
@LIGADO
def test_indisponivel_cai_para_o_segundo_e_o_retorno_diz_quem_entregou(rede):
    chamadas = rede(HttpAnswer(status_code=401, body={"error": "token"}), UAZAPI_OK)

    resultado = whatsapp.send_text("5511999999999", "quem participa amanhã?")

    assert resultado.status is Delivery.DELIVERED
    assert resultado.provider == "uazapi"
    assert resultado.reference == "U1"
    # E o rastro diz por onde passou — sem isso, depurar "o cliente não recebeu" vira arqueologia.
    assert [(t.provider, t.status) for t in resultado.attempts] == [
        ("zapi", Delivery.UNAVAILABLE),
        ("uazapi", Delivery.DELIVERED),
    ]
    assert len(chamadas.calls) == 2


@pytest.mark.django_db
@LIGADO
def test_indisponivel_nos_dois_devolve_o_ultimo_com_as_duas_tentativas(rede):
    rede(
        HttpAnswer(error=ConnectionRefusedError("recusada")),
        HttpAnswer(status_code=401, body={"error": "token"}),
    )

    resultado = whatsapp.send_text("5511999999999", "oi")

    assert resultado.status is Delivery.UNAVAILABLE
    assert len(resultado.attempts) == 2


# --- 4. `RECUSADA` não cai ------------------------------------------------------------------


@pytest.mark.django_db
@LIGADO
def test_recusada_nao_cai_para_o_segundo_provedor(rede):
    """O outro provedor recusaria igual: número mal formado é mal formado nos dois."""
    chamadas = rede(HttpAnswer(status_code=400, body={"error": "phone inválido"}), UAZAPI_OK)

    resultado = whatsapp.send_text("abc", "oi")

    assert resultado.status is Delivery.REFUSED
    assert len(chamadas.calls) == 1
    assert resultado.provider == "zapi"


# --- 5. Sem provedor nomeado, o `NullProvider` registra e não promete ------------------------


@override_settings(WHATSAPP_PROVIDERS="")
def test_sem_provedor_nomeado_cai_no_null_provider():
    assert whatsapp.has_provider() is False
    assert [type(p) for p in whatsapp.get_providers()] == [whatsapp.NullProvider]


@pytest.mark.django_db
@override_settings(WHATSAPP_ENABLED=True, WHATSAPP_PROVIDERS="")
def test_null_provider_registra_a_intencao_e_nao_promete_nada(caplog, rede):
    chamadas = rede()

    with caplog.at_level("INFO"):
        mensagem = whatsapp.send_text("5511999999999", "coordenação")
        grupo = whatsapp.create_group("Projeto ACME", ["5511999999999"])
        no_grupo = whatsapp.send_group_text("120363-group", "coordenação")

    assert mensagem.status is Delivery.UNAVAILABLE
    assert mensagem.reference == ""
    assert grupo.status is Delivery.UNAVAILABLE
    assert grupo.group_id == ""
    assert no_grupo.status is Delivery.UNAVAILABLE
    assert chamadas.calls == [], "o NullProvider não fala com fornecedor nenhum"
    assert whatsapp.SEM_PROVEDOR in caplog.text
    # E o telefone não vai inteiro para o log: é dado pessoal.
    assert "5511999999999" not in caplog.text


def test_null_provider_nao_promete_na_sonda():
    assert whatsapp.NullProvider().ping() == (True, whatsapp.SEM_PROVEDOR)


# --- 6. A flag desligada impede o envio ------------------------------------------------------


@pytest.mark.django_db
@override_settings(
    WHATSAPP_ENABLED=False,
    WHATSAPP_PROVIDERS="zapi",
    WHATSAPP_ZAPI_INSTANCE_ID="inst",
    WHATSAPP_ZAPI_TOKEN="tok",
)
def test_flag_desligada_impede_o_envio(rede):
    chamadas = rede(ZAPI_OK, ZAPI_OK, ZAPI_OK)

    mensagem = whatsapp.send_text("5511999999999", "oi")
    grupo = whatsapp.create_group("Projeto ACME", ["5511999999999"])
    no_grupo = whatsapp.send_group_text("120363-group", "oi")

    assert chamadas.calls == []
    for resultado in (mensagem, grupo, no_grupo):
        assert resultado.status is Delivery.UNAVAILABLE
        assert resultado.detail == whatsapp.DESLIGADA
        assert resultado.attempts == ()


@pytest.mark.django_db
@override_settings(WHATSAPP_ENABLED=True, WHATSAPP_PROVIDERS="zapi", WHATSAPP_ZAPI_TOKEN="")
def test_provedor_nomeado_sem_credencial_nao_liga_a_flag():
    """Mesma regra da ADR 0018: sem credencial não existe "ligada", nem pelo default do ambiente."""
    assert flags.desired("whatsapp") is True
    assert flags.missing("whatsapp") == ["WHATSAPP_ZAPI_INSTANCE_ID", "WHATSAPP_ZAPI_TOKEN"]
    assert flags.is_enabled("whatsapp") is False


@override_settings(WHATSAPP_PROVIDERS="")
def test_sem_provedor_nomeado_nao_se_cobra_credencial():
    """O `NullProvider` é um modo que roda; cobrar credencial dele desligaria um caminho válido."""
    assert flags.missing("whatsapp") == []


@override_settings(WHATSAPP_PROVIDERS="zap")
def test_provedor_desconhecido_aparece_como_faltando():
    """Ignorar o nome errado em silêncio faria a tela dizer "configurado" e nada sair."""
    assert flags.missing("whatsapp") == ["WHATSAPP_PROVIDERS (provedor desconhecido: 'zap')"]


# --- 7. A resolução respeita a ordem configurada ---------------------------------------------


@override_settings(WHATSAPP_PROVIDERS="uazapi,zapi")
def test_a_ordem_configurada_e_a_ordem_da_tentativa():
    assert [p.name for p in whatsapp.get_providers()] == ["uazapi", "zapi"]


@override_settings(WHATSAPP_PROVIDERS=" ZAPI , uazapi ")
def test_a_lista_tolera_espaco_e_caixa():
    assert whatsapp.provider_names() == ["zapi", "uazapi"]
    assert [p.name for p in whatsapp.get_providers()] == ["zapi", "uazapi"]


@pytest.mark.django_db
@override_settings(
    WHATSAPP_ENABLED=True,
    WHATSAPP_PROVIDERS="uazapi,zapi",
    WHATSAPP_UAZAPI_TOKEN="uaz",
    WHATSAPP_ZAPI_INSTANCE_ID="inst",
    WHATSAPP_ZAPI_TOKEN="tok",
)
def test_a_ordem_invertida_manda_pela_uazapi_primeiro(rede):
    chamadas = rede(UAZAPI_OK)

    resultado = whatsapp.send_text("5511999999999", "oi")

    assert resultado.provider == "uazapi"
    assert chamadas.urls == ["https://free.uazapi.com/send/text"]


# --- Os adaptadores: URL, credencial e leitura do corpo --------------------------------------


@pytest.mark.django_db
@LIGADO
def test_zapi_monta_a_url_com_instancia_e_token_e_manda_o_texto(rede):
    chamadas = rede(ZAPI_OK)

    resultado = whatsapp.send_text("+55 (11) 99999-9999", "coordenação")

    url, headers, payload, method, _ = chamadas.calls[0]
    assert url == "https://api.z-api.io/instances/inst/token/tok/send-text"
    assert method == "POST"
    assert payload == {"phone": "5511999999999", "message": "coordenação"}
    # Sem `Client-Token` configurado o header não vai — ele só existe se a conta ligou a validação.
    assert "Client-Token" not in headers
    assert resultado.reference == "M1"


@pytest.mark.django_db
@override_settings(
    WHATSAPP_ENABLED=True,
    WHATSAPP_PROVIDERS="zapi",
    WHATSAPP_ZAPI_INSTANCE_ID="inst",
    WHATSAPP_ZAPI_TOKEN="tok",
    WHATSAPP_ZAPI_CLIENT_TOKEN="conta",
    WHATSAPP_ZAPI_API_BASE="https://proxy.interno",
)
def test_zapi_leva_o_client_token_da_conta_e_respeita_a_base(rede):
    chamadas = rede(ZAPI_OK)

    whatsapp.send_text("5511999999999", "oi")

    url, headers, _, _, _ = chamadas.calls[0]
    assert url.startswith("https://proxy.interno/instances/inst/token/tok/")
    assert headers["Client-Token"] == "conta"


@pytest.mark.django_db
@LIGADO
def test_uazapi_leva_o_token_no_header(rede):
    chamadas = rede(HttpAnswer(status_code=401, body={"error": "token"}), UAZAPI_OK)

    whatsapp.send_text("5511999999999", "oi")

    url, headers, payload, _, _ = chamadas.calls[1]
    assert url == "https://free.uazapi.com/send/text"
    assert headers["token"] == "uaz"
    assert payload == {"number": "5511999999999", "text": "oi"}


@pytest.mark.django_db
@LIGADO
def test_criacao_de_grupo_devolve_id_e_link_de_convite(rede):
    rede(
        HttpAnswer(
            status_code=200,
            body={
                "phone": "120363019502650977-group",
                "invitationLink": "https://chat.whatsapp.com/GONwbGG",
                "phonesNotAdded": ["5544777777777"],
            },
        )
    )

    grupo = whatsapp.create_group("Projeto ACME", ["55 44 99999-9999"])

    assert grupo.status is Delivery.DELIVERED
    assert grupo.provider == "zapi"
    assert grupo.group_id == "120363019502650977-group"
    assert grupo.invite_url == "https://chat.whatsapp.com/GONwbGG"


@pytest.mark.django_db
@override_settings(
    WHATSAPP_ENABLED=True, WHATSAPP_PROVIDERS="uazapi", WHATSAPP_UAZAPI_TOKEN="uaz"
)
def test_criacao_de_grupo_na_uazapi_le_jid_e_invite_link(rede):
    chamadas = rede(
        HttpAnswer(status_code=200, body={"JID": "1203@g.us", "invite_link": "https://chat/x"})
    )

    grupo = whatsapp.create_group("Projeto ACME", ["5544999999999"])

    assert (grupo.group_id, grupo.invite_url) == ("1203@g.us", "https://chat/x")
    assert chamadas.calls[0][2] == {"name": "Projeto ACME", "participants": ["5544999999999"]}


@pytest.mark.parametrize("provider", [whatsapp.ZApiProvider, whatsapp.UazapiProvider])
def test_grupo_nao_criado_carrega_o_estado_da_falha(provider):
    resultado = provider.read_group(HttpAnswer(status_code=401, body={"error": "token"}))
    assert resultado.status is Delivery.UNAVAILABLE
    assert (resultado.group_id, resultado.invite_url) == ("", "")


def test_grupo_criado_sem_id_e_incerto():
    resultado = whatsapp.ZApiProvider.read_group(HttpAnswer(status_code=200, body={}))
    assert resultado.status is Delivery.UNCERTAIN
    assert resultado.group_id == ""


# --- O teto por operação (ADR 0064, issue #111) -----------------------------------------------
#
# Criar grupo não é falar com o provedor: é o provedor falando com a rede do WhatsApp e esperando
# o grupo existir. Em 03/09/2026 o teto único de 15s estourou, o adaptador devolveu `UNCERTAIN`
# sem id — e o grupo **tinha** nascido do outro lado.


def test_o_teto_default_e_o_de_mensagem_e_o_de_grupo_e_proprio():
    """A regra do teto mora fora de `_request` justamente para caber num teste."""
    assert whatsapp._timeout(None) == 15
    assert whatsapp._timeout(90) == 90


@pytest.mark.django_db
@LIGADO
def test_mandar_texto_usa_o_teto_de_mensagem_e_criar_grupo_usa_o_de_grupo(rede):
    chamadas = rede(ZAPI_OK, HttpAnswer(status_code=200, body={"phone": "1203-group"}))

    whatsapp.send_text("5511999999999", "oi")
    whatsapp.create_group("Projeto ACME", ["5511999999999"])

    # `None` no envio significa "sem teto próprio", e `_timeout` o resolve no de mensagem.
    assert chamadas.timeouts == [None, 90]
    assert whatsapp._timeout(chamadas.timeouts[0]) == 15


@pytest.mark.django_db
@LIGADO
@override_settings(WHATSAPP_TIMEOUT_SECONDS=7, WHATSAPP_GROUP_TIMEOUT_SECONDS=300)
def test_mexer_num_teto_nao_mexe_no_outro(rede):
    chamadas = rede(ZAPI_OK, HttpAnswer(status_code=200, body={"phone": "1203-group"}))

    whatsapp.send_text("5511999999999", "oi")
    whatsapp.create_group("Projeto ACME", ["5511999999999"])

    assert chamadas.timeouts == [None, 300]
    assert whatsapp._timeout(chamadas.timeouts[0]) == 7


# --- A reconciliação depois do `UNCERTAIN` (ADR 0064) -----------------------------------------

SO_UAZAPI = override_settings(
    WHATSAPP_ENABLED=True, WHATSAPP_PROVIDERS="uazapi", WHATSAPP_UAZAPI_TOKEN="uaz"
)
SO_ZAPI = override_settings(
    WHATSAPP_ENABLED=True,
    WHATSAPP_PROVIDERS="zapi",
    WHATSAPP_ZAPI_INSTANCE_ID="inst",
    WHATSAPP_ZAPI_TOKEN="tok",
)
GRUPO_ACHADO = {"JID": "120363431743499021@g.us", "name": "ACME · Discovery"}


def test_um_array_no_topo_nao_se_perde_na_leitura_do_corpo():
    """`_body` devolvia `{}` para qualquer JSON que não fosse objeto.

    Uma listagem de grupos é justamente o que chega como array no topo: a reconciliação receberia
    um corpo vazio, nunca acharia nada e **não erraria** — o pior modo de falha possível aqui.
    """
    assert whatsapp._body(b'[{"JID": "1203@g.us"}]') == {"items": [{"JID": "1203@g.us"}]}
    assert whatsapp._body(b'{"groups": []}') == {"groups": []}
    assert whatsapp._body(b"3") == {}
    assert whatsapp._body(b"nao e json") == {}


@pytest.mark.parametrize(
    "body",
    [
        pytest.param({"groups": [GRUPO_ACHADO]}, id="objeto-com-chave"),
        pytest.param({"items": [GRUPO_ACHADO]}, id="array-no-topo-embrulhado"),
    ],
)
def test_a_listagem_e_lida_nas_duas_formas_de_corpo(body: dict):
    """A documentação do fornecedor não fixa qual das duas vem, e adivinhar uma falha na outra."""
    achado = whatsapp.UazapiProvider.read_group_list(
        "ACME · Discovery", HttpAnswer(status_code=200, body=body)
    )

    assert achado.status is Delivery.DELIVERED
    assert achado.group_id == "120363431743499021@g.us"


@pytest.mark.django_db
@SO_UAZAPI
def test_grupo_incerto_e_reconciliado_quando_o_nome_casa_exatamente_uma_vez(rede):
    """O defeito medido em 03/09/2026: o teto estourou e o grupo tinha nascido do outro lado."""
    chamadas = rede(
        HttpAnswer(error=TimeoutError("timed out")),
        HttpAnswer(status_code=200, body={"groups": [GRUPO_ACHADO, {"name": "Outra conta"}]}),
    )

    grupo = whatsapp.create_group("ACME · Discovery", ["5511999999999"])

    assert grupo.status is Delivery.DELIVERED
    assert grupo.group_id == "120363431743499021@g.us"
    # Quem lê o log precisa separar "respondeu na hora" de "achamos depois".
    assert whatsapp.RECONCILIADO in grupo.detail
    assert "timeout" in grupo.detail
    # O rastro continua respondendo "por onde isto passou?": a tentativa e a reconciliação.
    assert [a.status for a in grupo.attempts] == [Delivery.UNCERTAIN, Delivery.DELIVERED]
    assert chamadas.calls[1][3] == "GET"
    assert chamadas.urls[1] == "https://free.uazapi.com/group/list"


@pytest.mark.django_db
@SO_UAZAPI
def test_nenhum_casamento_de_nome_continua_incerto(rede):
    rede(
        HttpAnswer(error=TimeoutError("timed out")),
        HttpAnswer(status_code=200, body={"groups": [{"name": "Outra conta · Outro"}]}),
    )

    grupo = whatsapp.create_group("ACME · Discovery", ["5511999999999"])

    assert grupo.status is Delivery.UNCERTAIN
    assert grupo.group_id == ""


@pytest.mark.django_db
@SO_UAZAPI
def test_dois_grupos_com_o_mesmo_nome_continuam_incertos_e_nada_e_escolhido(rede):
    """Escolher entre dois seria gravar a referência errada — pior do que não gravar nenhuma."""
    rede(
        HttpAnswer(error=TimeoutError("timed out")),
        HttpAnswer(
            status_code=200,
            body={"groups": [GRUPO_ACHADO, {"JID": "999@g.us", "name": "ACME · Discovery"}]},
        ),
    )

    grupo = whatsapp.create_group("ACME · Discovery", ["5511999999999"])

    assert grupo.status is Delivery.UNCERTAIN
    assert grupo.group_id == ""
    assert "2 grupos" in grupo.attempts[-1].detail


@pytest.mark.django_db
@SO_ZAPI
def test_provedor_que_nao_sabe_listar_grupos_nao_estoura_e_segue_incerto(rede):
    """A Z-API não tem endpoint de listagem **verificado**, e a capacidade é opcional (`getattr`)."""
    chamadas = rede(HttpAnswer(error=TimeoutError("timed out")))

    grupo = whatsapp.create_group("ACME · Discovery", ["5511999999999"])

    assert grupo.status is Delivery.UNCERTAIN
    assert not hasattr(whatsapp.ZApiProvider, "find_group")
    assert len(chamadas.calls) == 1, "sem capacidade de listar, não há segunda chamada"


@pytest.mark.django_db
@SO_UAZAPI
def test_o_caminho_feliz_nao_chama_a_reconciliacao(rede):
    chamadas = rede(HttpAnswer(status_code=200, body={"JID": "1203@g.us", "invite_link": "u"}))

    grupo = whatsapp.create_group("ACME · Discovery", ["5511999999999"])

    assert grupo.status is Delivery.DELIVERED
    assert whatsapp.RECONCILIADO not in grupo.detail
    assert len(chamadas.calls) == 1, "grupo criado na hora não se reconcilia com ninguém"


def test_a_reconciliacao_nao_normaliza_acento_nem_caixa():
    """O nome é o que a casa mandou criar; normalizar abriria casamento falso."""
    quase = HttpAnswer(status_code=200, body={"groups": [{"name": "acme · discovery"}]})

    assert whatsapp.UazapiProvider.read_group_list("ACME · Discovery", quase).status is (
        Delivery.UNCERTAIN
    )
    # Espaço em volta, sim: é ruído de digitação, não outro nome.
    com_espaco = HttpAnswer(
        status_code=200,
        body={"groups": [{"JID": "1203@g.us", "name": " ACME · Discovery "}]},
    )
    assert whatsapp.UazapiProvider.read_group_list(
        "ACME · Discovery", com_espaco
    ).status is Delivery.DELIVERED


def test_listagem_com_corpo_irreconhecivel_nao_inventa_grupo():
    """200 com um corpo que não traz lista nenhuma é lacuna, e lacuna não vira palpite."""
    achado = whatsapp.UazapiProvider.read_group_list(
        "ACME · Discovery", HttpAnswer(status_code=200, body={"detalhe": "sem grupos"})
    )

    assert achado.status is Delivery.UNCERTAIN
    assert "nenhum grupo" in achado.detail


def test_listagem_que_o_provedor_recusa_nao_vira_reconciliacao():
    recusada = HttpAnswer(status_code=401, body={"error": "token"})
    achado = whatsapp.UazapiProvider.read_group_list("ACME · Discovery", recusada)

    assert achado.status is Delivery.UNAVAILABLE
    assert achado.group_id == ""


@pytest.mark.django_db
@LIGADO
def test_mensagem_ao_grupo_usa_a_referencia_do_grupo_como_destino(rede):
    """O id do grupo não é telefone e não pode perder caractere ao ser normalizado."""
    chamadas = rede(ZAPI_OK)

    whatsapp.send_group_text("120363019502650977-group", "coordenação")

    assert chamadas.calls[0][2] == {
        "phone": "120363019502650977-group",
        "message": "coordenação",
    }


# --- A sonda ----------------------------------------------------------------------------------


def test_a_sonda_esta_registrada_para_a_flag():
    """Sem entrada em `PROBES` a sonda cai no `except` largo e reporta `KeyError` como motivo."""
    assert "whatsapp" in integrations.PROBES


@pytest.mark.django_db
@override_settings(WHATSAPP_ENABLED=True, WHATSAPP_PROVIDERS="")
def test_sonda_sem_provedor_nao_reprova():
    ok, detalhe = integrations.PROBES["whatsapp"]()
    assert ok is True
    assert integrations.NAO_SONDAVEL in detalhe


@pytest.mark.django_db
@LIGADO
def test_sonda_pergunta_a_cada_provedor_e_nao_manda_mensagem(rede):
    chamadas = rede(
        HttpAnswer(status_code=200, body={"connected": True, "error": "already connected"}),
        HttpAnswer(status_code=200, body={"status": {"connected": True, "loggedIn": True}}),
    )

    ok, detalhe = integrations.PROBES["whatsapp"]()

    assert ok is True
    assert detalhe == "zapi: instância conectada; uazapi: instância conectada"
    assert [call[3] for call in chamadas.calls] == ["GET", "GET"]
    assert chamadas.urls == [
        "https://api.z-api.io/instances/inst/token/tok/status",
        "https://free.uazapi.com/instance/status",
    ]


@pytest.mark.django_db
@LIGADO
def test_sonda_reprova_quando_o_segundo_provedor_esta_desconectado(rede):
    """A cadeia meio quebrada parece saudável até o dia em que o primeiro cair."""
    rede(
        HttpAnswer(status_code=200, body={"connected": True}),
        HttpAnswer(status_code=200, body={"status": {"connected": False}}),
    )

    ok, detalhe = integrations.PROBES["whatsapp"]()

    assert ok is False
    assert "uazapi: instância desconectada" in detalhe


@pytest.mark.parametrize(
    "answer,esperado",
    [
        (HttpAnswer(status_code=200, body={"connected": True}), True),
        (HttpAnswer(status_code=200, body={"connected": False, "error": "restaure a sessão"}), False),
        (HttpAnswer(status_code=401, body={"error": "token"}), False),
    ],
)
def test_zapi_read_ping(answer: HttpAnswer, esperado: bool):
    ok, motivo = whatsapp.ZApiProvider.read_ping(answer)
    assert ok is esperado
    assert motivo


@pytest.mark.parametrize(
    "answer,esperado",
    [
        (HttpAnswer(status_code=200, body={"status": {"connected": True}}), True),
        (HttpAnswer(status_code=200, body={"status": "connected"}), True),
        (HttpAnswer(status_code=200, body={"status": {"connected": False}}), False),
        (HttpAnswer(status_code=404, body={}), False),
        (HttpAnswer(error=TimeoutError()), False),
    ],
)
def test_uazapi_read_ping(answer: HttpAnswer, esperado: bool):
    ok, motivo = whatsapp.UazapiProvider.read_ping(answer)
    assert ok is esperado
    assert motivo


# --- Normalização de destino -----------------------------------------------------------------


@pytest.mark.parametrize(
    "cru,esperado",
    [
        ("+55 (11) 99999-9999", "5511999999999"),
        ("55 11 99999 9999", "5511999999999"),
        ("120363019502650977-group", "120363019502650977-group"),
        ("1203@g.us", "1203@g.us"),
        ("", ""),
    ],
)
def test_destino_preserva_id_de_chat_e_limpa_telefone(cru: str, esperado: str):
    assert whatsapp._to(cru) == esperado


def test_o_log_nunca_leva_o_telefone_inteiro():
    assert whatsapp._mask("5511999999999") == "…9999"
    assert whatsapp._mask("12") == "…"
