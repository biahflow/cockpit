"""Regressão: o grupo nasceu do outro lado e a referência dele não se perde (issue #111).

**O defeito é medido, não hipotético.** Na primeira chamada real de `whatsapp.create_group` contra
a UAZAPI, em 03/09/2026, o teto de 15s estourou; o adaptador classificou `UNCERTAIN` — e classificou
**certo**, porque `TimeoutError` pode ter entregado (ADR 0062) — e devolveu um resultado sem
`group_id`. Só que o grupo tinha sido criado: `120363431743499021@g.us`, 11:47:18Z. Ninguém no
produto ficou sabendo dele.

O conserto tem duas metades, e a segunda é a que importa:

1. **teto por operação** — criar grupo não é falar com o provedor, é o provedor falando com a rede
   do WhatsApp e esperando o grupo existir. Mesmo teto para operações de ordens de grandeza
   diferentes era o erro de origem;
2. **reconciliação** — um teto maior sozinho torna o caso raro, e caso raro não tratado é o pior
   tipo. Depois do `UNCERTAIN`, o módulo pergunta ao **mesmo** provedor se existe grupo com aquele
   nome, e aceita **só** o casamento exato e único: escolher entre dois seria gravar a referência
   errada, e uma referência errada é pior do que nenhuma — com ela, quem opera acha que sabe.

Nada aqui atravessa a rede (ADR 0059): a costura substituída é `whatsapp._request`.
"""

import pytest
from django.test import override_settings

from apps.core import kickoff, whatsapp
from apps.core.models import Contact, Service
from apps.core.tests.factories import ProjectFactory
from apps.core.whatsapp import Delivery, HttpAnswer

pytestmark = pytest.mark.django_db

# O grupo que existia do outro lado no dia do incidente.
GRUPO_QUE_NASCEU = {"JID": "120363431743499021@g.us", "invite_link": "https://chat.whatsapp.com/x"}

SO_UAZAPI = override_settings(
    WHATSAPP_ENABLED=True, WHATSAPP_PROVIDERS="uazapi", WHATSAPP_UAZAPI_TOKEN="uaz"
)


class _Rede:
    """Fila de respostas do fornecedor, na ordem em que as chamadas saírem."""

    def __init__(self, *answers: HttpAnswer) -> None:
        self.answers = list(answers)
        self.calls: list[tuple[str, str, float | None]] = []

    def __call__(
        self,
        url: str,
        headers: dict,
        payload: dict | None = None,
        method: str = "POST",
        timeout: float | None = None,
    ) -> HttpAnswer:
        self.calls.append((url, method, timeout))
        return self.answers.pop(0)


@SO_UAZAPI
def test_o_teto_de_criar_grupo_nao_e_o_teto_de_mandar_texto(monkeypatch) -> None:
    """15s para as duas operações foi o erro de origem. O default de mensagem não se mexeu."""
    rede = _Rede(HttpAnswer(status_code=200, body=GRUPO_QUE_NASCEU))
    monkeypatch.setattr(whatsapp, "_request", rede)

    whatsapp.create_group("ACME · Discovery", ["5511999990001"])

    assert rede.calls[0][2] == 90
    assert whatsapp._timeout(None) == 15


@SO_UAZAPI
def test_a_resposta_que_se_perdeu_nao_leva_o_grupo_junto(monkeypatch) -> None:
    """O caso exato de 03/09/2026: teto estourado, grupo criado, referência recuperada."""
    rede = _Rede(
        HttpAnswer(error=TimeoutError("timed out")),
        HttpAnswer(status_code=200, body={"groups": [{**GRUPO_QUE_NASCEU, "name": "ACME · Kick"}]}),
    )
    monkeypatch.setattr(whatsapp, "_request", rede)

    grupo = whatsapp.create_group("ACME · Kick", ["5511999990001"])

    assert grupo.status is Delivery.DELIVERED
    assert grupo.group_id == "120363431743499021@g.us"
    # O rastro não pode fingir que respondeu na hora: quem lê o log precisa dos dois fatos.
    assert whatsapp.RECONCILIADO in grupo.detail
    assert [tentativa.status for tentativa in grupo.attempts] == [
        Delivery.UNCERTAIN,
        Delivery.DELIVERED,
    ]


@SO_UAZAPI
def test_dois_grupos_com_o_mesmo_nome_nao_viram_um_palpite(monkeypatch) -> None:
    """Gravar a referência errada é pior do que não gravar: quem opera passa a achar que sabe."""
    rede = _Rede(
        HttpAnswer(error=TimeoutError("timed out")),
        HttpAnswer(
            status_code=200,
            body={
                "groups": [
                    {**GRUPO_QUE_NASCEU, "name": "ACME · Kick"},
                    {"JID": "999@g.us", "name": "ACME · Kick"},
                ]
            },
        ),
    )
    monkeypatch.setattr(whatsapp, "_request", rede)

    grupo = whatsapp.create_group("ACME · Kick", ["5511999990001"])

    assert grupo.status is Delivery.UNCERTAIN
    assert grupo.group_id == ""


@SO_UAZAPI
def test_o_kickoff_guarda_a_referencia_recuperada_no_projeto(monkeypatch) -> None:
    """A reconciliação só serve para alguma coisa porque existe quem guarde o que ela achou.

    É a costura entre as duas issues: a #110 criou o chamador que guarda, e sem ele o id
    recuperado morreria dentro do `GroupResult` do mesmo jeito que morreu no dia do incidente.
    """
    projeto = ProjectFactory(service=Service.objects.get(tier=Service.Tier.DISCOVERY_SPRINT))
    conta = projeto.engagement.account
    Contact.objects.create(account=conta, first_name="Ana", phone="5511999990001")
    nome = f"{conta.name} · {projeto.name}"
    rede = _Rede(
        HttpAnswer(error=TimeoutError("timed out")),
        HttpAnswer(status_code=200, body={"groups": [{**GRUPO_QUE_NASCEU, "name": nome}]}),
    )
    monkeypatch.setattr(whatsapp, "_request", rede)

    kickoff.finalize(projeto)

    projeto.refresh_from_db()
    assert projeto.whatsapp_group_id == "120363431743499021@g.us"
    assert projeto.whatsapp_group_invite_url == "https://chat.whatsapp.com/x"
