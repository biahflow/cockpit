"""API `/account-rungs/` (FDD 042): forma da escada, escrita por Vendas, recorte da Entrega.

O que estes testes protegem, em uma frase: **a Entrega vê a forma da escada e não o conteúdo
comercial**, e o recorte de quais projetos ela alcança sai de `Project.objects.visible_to` — nunca
reescrito (RFC 0003, ADR 0010).
"""

from __future__ import annotations

import pytest
from django.urls import reverse
from rest_framework.test import APIClient

from apps.core import ladder
from apps.core.models import AccountRung, AccountRungEvent, FdeRung, User

from .factories import (
    ClientFactory,
    OpportunityFactory,
    ProjectFactory,
    ProjectMemberFactory,
    UserFactory,
)


@pytest.fixture
def api() -> APIClient:
    return APIClient()


def _lista(api: APIClient, client_id: int):  # type: ignore[no-untyped-def]
    return api.get(reverse("accountrung-list"), {"client": client_id})


@pytest.mark.django_db
def test_toda_conta_expoe_os_seis_degraus_com_estado(api: APIClient) -> None:
    admin = UserFactory(role=User.Role.ADMIN)
    conta = ClientFactory()
    api.force_authenticate(admin)

    resposta = _lista(api, conta.id)

    assert resposta.status_code == 200
    assert [linha["rung"] for linha in resposta.data] == [
        "discover", "prioritize", "feasibility", "prove", "scale", "optimize"
    ]
    assert resposta.data[2]["rung_display"] == "[ Technical Feasibility ]"
    assert {linha["status"] for linha in resposta.data} == {"not_sold"}
    assert resposta.data[0]["status_display"] == "Não vendido"


@pytest.mark.django_db
def test_conta_antiga_e_materializada_na_primeira_leitura(api: APIClient) -> None:
    """Molde do `ProjectPhaseViewSet`: quem existia antes desta fatia não fica sem escada."""
    admin = UserFactory(role=User.Role.ADMIN)
    conta = ClientFactory()
    AccountRung.objects.filter(client=conta).delete()
    api.force_authenticate(admin)

    assert len(_lista(api, conta.id).data) == 6
    assert len(_lista(api, conta.id).data) == 6  # idempotente na segunda leitura


@pytest.mark.django_db
def test_um_degrau_compartilha_a_venda_com_o_anterior(api: APIClient) -> None:
    """Discover e Prioritize saem da mesma "Discovery Sprint" — a FK não é 1:1."""
    admin = UserFactory(role=User.Role.ADMIN)
    conta = ClientFactory()
    venda = OpportunityFactory(client=conta, title="Discovery Sprint · Vale")
    api.force_authenticate(admin)

    for degrau in (FdeRung.DISCOVER, FdeRung.PRIORITIZE):
        alvo = AccountRung.objects.get(client=conta, rung=degrau)
        resposta = api.post(
            reverse("accountrung-transition", args=[alvo.id]),
            {"status": "done", "opportunity": venda.id},
            format="json",
        )
        assert resposta.status_code == 200

    assert AccountRung.objects.filter(client=conta, opportunity=venda).count() == 2
    assert _lista(api, conta.id).data[0]["opportunity_title"] == "Discovery Sprint · Vale"


@pytest.mark.django_db
def test_transicao_registra_historico_visivel_na_escada(api: APIClient) -> None:
    admin = UserFactory(role=User.Role.ADMIN, first_name="Daniel", last_name="Campos")
    conta = ClientFactory()
    degrau = AccountRung.objects.get(client=conta, rung=FdeRung.PROVE)
    api.force_authenticate(admin)

    api.post(
        reverse("accountrung-transition", args=[degrau.id]),
        {"status": "active", "waiting_on": "biahflow", "note": "oportunidade convertida"},
        format="json",
    )
    resposta = api.post(
        reverse("accountrung-transition", args=[degrau.id]),
        {"status": "blocked", "blocker": "Acesso ao ERP pendente", "waiting_on": "client"},
        format="json",
    )

    assert resposta.status_code == 200
    assert resposta.data["status"] == "blocked"
    assert resposta.data["blocker"] == "Acesso ao ERP pendente"
    assert resposta.data["waiting_on_display"] == "Cliente"
    historico = resposta.data["events"]
    assert [(item["from_status"], item["to_status"]) for item in historico] == [
        ("not_sold", "active"), ("active", "blocked")
    ]
    assert historico[0]["by_name"] == "Daniel Campos"
    assert historico[0]["to_status_display"] == "Ativo"


@pytest.mark.django_db
def test_pular_prove_e_recusado_com_409(api: APIClient) -> None:
    admin = UserFactory(role=User.Role.ADMIN)
    conta = ClientFactory()
    prove = AccountRung.objects.get(client=conta, rung=FdeRung.PROVE)
    api.force_authenticate(admin)

    resposta = api.post(
        reverse("accountrung-transition", args=[prove.id]),
        {"status": "skipped", "skip_reason": "não precisamos"},
        format="json",
    )

    assert resposta.status_code == 409


@pytest.mark.django_db
def test_pulada_carrega_motivo_autor_e_carimbo(api: APIClient) -> None:
    admin = UserFactory(role=User.Role.ADMIN, first_name="Daniel", last_name="Campos")
    conta = ClientFactory()
    feasibility = AccountRung.objects.get(client=conta, rung=FdeRung.FEASIBILITY)
    api.force_authenticate(admin)

    resposta = api.post(
        reverse("accountrung-transition", args=[feasibility.id]),
        {"status": "skipped", "skip_reason": "tecnologia sabida"},
        format="json",
    )

    assert resposta.status_code == 200
    assert resposta.data["skip_reason"] == "tecnologia sabida"
    assert resposta.data["skipped_by_name"] == "Daniel Campos"
    assert resposta.data["skipped_at"] is not None


@pytest.mark.django_db
def test_degrau_de_outra_conta_e_recusado(api: APIClient) -> None:
    """A conta é a fronteira: amarrar o degrau a um projeto alheio seria o furo do escopo."""
    admin = UserFactory(role=User.Role.ADMIN)
    conta = ClientFactory()
    outra = ClientFactory()
    projeto_alheio = ProjectFactory(client=outra)
    degrau = AccountRung.objects.get(client=conta, rung=FdeRung.PROVE)
    api.force_authenticate(admin)

    resposta = api.post(
        reverse("accountrung-transition", args=[degrau.id]),
        {"status": "active", "project": projeto_alheio.id},
        format="json",
    )

    assert resposta.status_code == 403


@pytest.mark.django_db
def test_vendas_escreve_a_escada(api: APIClient) -> None:
    """Cada degrau **é uma venda** na mesma conta (`metodologia-fde.md:50`)."""
    vendas = UserFactory(role=User.Role.SALES)
    conta = ClientFactory()
    degrau = AccountRung.objects.get(client=conta, rung=FdeRung.DISCOVER)
    api.force_authenticate(vendas)

    resposta = api.post(
        reverse("accountrung-transition", args=[degrau.id]), {"status": "active"}, format="json"
    )

    assert resposta.status_code == 200


@pytest.mark.django_db
def test_a_entrega_le_e_nao_escreve(api: APIClient) -> None:
    entrega = UserFactory(role=User.Role.DELIVERY)
    conta = ClientFactory()
    projeto = ProjectFactory(client=conta)
    ProjectMemberFactory(project=projeto, user=entrega)
    degrau = AccountRung.objects.get(client=conta, rung=FdeRung.PROVE)
    api.force_authenticate(entrega)

    assert _lista(api, conta.id).status_code == 200
    recusa = api.post(
        reverse("accountrung-transition", args=[degrau.id]), {"status": "active"}, format="json"
    )
    assert recusa.status_code == 403
    assert AccountRungEvent.objects.count() == 0


@pytest.mark.django_db
def test_a_entrega_nao_alcanca_conta_sem_projeto_seu(api: APIClient) -> None:
    entrega = UserFactory(role=User.Role.DELIVERY)
    alheia = ClientFactory()
    ProjectFactory(client=alheia)
    api.force_authenticate(entrega)

    assert _lista(api, alheia.id).data == []


@pytest.mark.django_db
def test_a_entrega_ve_a_forma_e_nao_o_conteudo_comercial(api: APIClient) -> None:
    """O estado 10 do DAP: a escada aparece, o degrau de projeto alheio vira "Sem acesso"."""
    entrega = UserFactory(role=User.Role.DELIVERY)
    admin = UserFactory(role=User.Role.ADMIN)
    conta = ClientFactory()
    venda = OpportunityFactory(client=conta, title="PROVE · Triagem de NF")
    meu = ProjectFactory(client=conta, name="PROVE Triagem de NF")
    alheio = ProjectFactory(client=conta, name="Discovery Vale")
    ProjectMemberFactory(project=meu, user=entrega)

    discover = AccountRung.objects.get(client=conta, rung=FdeRung.DISCOVER)
    ladder.transition(
        discover, to_status=AccountRung.Status.DONE, by=admin, opportunity=venda, project=alheio
    )
    prove = AccountRung.objects.get(client=conta, rung=FdeRung.PROVE)
    ladder.transition(
        prove,
        to_status=AccountRung.Status.ACTIVE,
        by=admin,
        opportunity=venda,
        project=meu,
        waiting_on=AccountRung.WaitingOn.BIAHFLOW,
    )

    api.force_authenticate(entrega)
    linhas = {linha["rung"]: linha for linha in _lista(api, conta.id).data}

    sem_acesso = linhas["discover"]
    assert sem_acesso["no_access"] is True
    assert sem_acesso["status"] == "done"  # a forma continua
    assert sem_acesso["project"] is None and sem_acesso["project_name"] == ""
    assert sem_acesso["started_at"] is None and sem_acesso["completed_at"] is None
    assert sem_acesso["events"] == []

    meu_degrau = linhas["prove"]
    assert meu_degrau["no_access"] is False
    assert meu_degrau["project_name"] == "PROVE Triagem de NF"
    assert meu_degrau["waiting_on_display"] == "Biahflow"
    # Conteúdo **comercial** some mesmo no degrau que a pessoa alcança.
    assert meu_degrau["opportunity"] is None and meu_degrau["opportunity_title"] == ""

    # E o admin continua vendo tudo, para a asserção acima não passar por a API estar vazia.
    api.force_authenticate(admin)
    do_admin = {linha["rung"]: linha for linha in _lista(api, conta.id).data}
    assert do_admin["prove"]["opportunity_title"] == "PROVE · Triagem de NF"
    assert do_admin["discover"]["no_access"] is False


@pytest.mark.django_db
def test_a_escada_nao_se_cria_nem_se_arquiva_pela_api(api: APIClient) -> None:
    """Doutrina materializada, não coleção: sem POST de criação, sem DELETE, sem `unarchive`."""
    admin = UserFactory(role=User.Role.ADMIN)
    conta = ClientFactory()
    degrau = AccountRung.objects.get(client=conta, rung=FdeRung.PROVE)
    api.force_authenticate(admin)

    assert api.post(reverse("accountrung-list"), {"client": conta.id}, format="json").status_code == 405
    assert api.delete(reverse("accountrung-detail", args=[degrau.id])).status_code == 405


@pytest.mark.django_db
def test_o_bloco_da_visao_geral_chega_no_dashboard(api: APIClient) -> None:
    admin = UserFactory(role=User.Role.ADMIN)
    conta = ClientFactory(name="Metalúrgica Vale")
    degrau = AccountRung.objects.get(client=conta, rung=FdeRung.PROVE)
    ladder.transition(
        degrau,
        to_status=AccountRung.Status.AWAITING_GATE,
        by=admin,
        waiting_on=AccountRung.WaitingOn.HUMAN_GATE,
    )
    api.force_authenticate(admin)

    resposta = api.get(reverse("dashboard"))

    assert resposta.status_code == 200
    linha = resposta.data["account_ladder"][0]
    assert linha["client_name"] == "Metalúrgica Vale"
    assert linha["rung_display"] == "Prove"
    assert linha["status_display"] == "Aguardando decisão de gate"
    assert linha["waiting_on_display"] == "Human Gate"
    assert [passo["status"] for passo in linha["steps"]] == [
        "not_sold", "not_sold", "not_sold", "awaiting_gate", "not_sold", "not_sold"
    ]
