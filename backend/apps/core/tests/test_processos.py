"""O Discovery estruturado: processo, etapa e o custo do estado atual (FDD 039).

Duas coisas são exercitadas aqui:

- **a fronteira do cliente nas duas metades** (processo e etapa), como em `test_satisfacao.py` —
  e aqui ela se estende pelo processo pai, que é por onde a etapa chegaria ao cliente alheio;
- **a lacuna dita e não preenchida** no custo do estado atual: fator ausente vai para
  `nao_apurado` e não vira zero no total, no molde do KPI sem base registrada da FDD 027.

O achado deixou de morar aqui: a `Evidencia` fundida saiu na Fase 6 (ADR 0052), e o par
`Evidence`/`Finding` do split (FDD 045) tem suíte própria em `test_evidence_finding.py`. O que
sobrou do achado neste arquivo é o que o processo pergunta a ele — `sustentacao`, que agora lê o
`Finding(epistemic_status=fact)` vivo em vez do `Evidencia(rotulo=fato)` legado.

O oráculo do cálculo é função pura (`apps/core/process.py`), testado sem banco onde dá — o
resto precisa de banco porque `sustentacao` pergunta pelos achados vivos do processo.
"""

import json
from decimal import Decimal

import pytest
from django.urls import reverse
from rest_framework.test import APIClient

from apps.core import process as process_module
from apps.core.models import Finding, Process, ProcessStep, User

from .factories import (
    AccountFactory,
    FindingFactory,
    ProcessFactory,
    ProcessStepFactory,
    ProjectFactory,
    ProjectMemberFactory,
    UserFactory,
)


@pytest.fixture
def client() -> APIClient:
    return APIClient()


def _fato_vivo(processo: Process, **overrides: object) -> Finding:
    """Um `Finding` **fato** ligado ao processo — o que sustenta o custo (§6.9, `:117`).

    A fábrica não passa por `full_clean`, então o fato nasce sem revisor aqui de propósito: o que
    `sustentacao` pergunta é `epistemic_status=fact` e `archived_at` nulo, e é só isso que estes
    testes precisam montar. A guarda do revisor é da API, exercitada em `test_evidence_finding.py`.
    """
    base: dict = {
        "process": processo,
        "account": processo.account,
        "epistemic_status": Finding.EpistemicStatus.FACT,
    }
    base.update(overrides)
    return FindingFactory(**base)


# --- O cálculo do custo do estado atual ---------------------------------------


def _rotulos(parcelas: list[dict]) -> list[str]:
    return [parcela["label"] for parcela in parcelas]


@pytest.mark.django_db
def test_o_nucleo_multiplica_os_quatro_fatores() -> None:
    """`Volume × Tempo × Pessoas × Custo` (`docs/metodologia-fde.md:118-119`), em `Decimal`."""
    processo = ProcessFactory(
        volume_mes=40, tempo_horas=Decimal("2.50"), pessoas=2, custo_hora=Decimal("60.00")
    )

    custo = process_module.custo_do_estado_atual(processo)

    assert custo["parcelas"] == [
        {"label": process_module.ROTULO_NUCLEO, "valor": Decimal("12000.00")}
    ]
    assert custo["total"] == Decimal("12000.00")
    assert custo["nao_apurado"] == [rotulo for _, rotulo in process_module.ADITIVOS]


@pytest.mark.django_db
def test_o_nucleo_soma_com_os_cinco_aditivos() -> None:
    processo = ProcessFactory(
        volume_mes=10, tempo_horas=Decimal("1.00"), pessoas=1, custo_hora=Decimal("100.00"),
        retrabalho_mes=Decimal("500.00"), erros_mes=Decimal("250.00"),
        perdas_mes=Decimal("125.00"), espera_mes=Decimal("75.00"), risco_mes=Decimal("50.00"),
    )

    custo = process_module.custo_do_estado_atual(processo)

    assert _rotulos(custo["parcelas"]) == list(process_module.ROTULOS_CUSTO)
    assert custo["total"] == Decimal("2000.00")
    assert custo["nao_apurado"] == []


@pytest.mark.django_db
@pytest.mark.parametrize("faltante", process_module.FATORES_NUCLEO)
def test_fator_ausente_manda_o_nucleo_para_nao_apurado_e_nao_zera_o_total(faltante: str) -> None:
    """Critério de aceite: **basta um fator faltar** e a parcela inteira não é apurada.

    Zerar seria afirmar que executar o processo não custa nada — e "não medimos" não é "não
    custa". Os aditivos que existem continuam somando: o total é o que se sabe, não o que se
    supõe.
    """
    campos = {
        "volume_mes": 10, "tempo_horas": Decimal("1.00"), "pessoas": 1,
        "custo_hora": Decimal("100.00"), "erros_mes": Decimal("300.00"),
    }
    campos[faltante] = None
    processo = ProcessFactory(**campos)

    custo = process_module.custo_do_estado_atual(processo)

    assert process_module.ROTULO_NUCLEO in custo["nao_apurado"]
    assert _rotulos(custo["parcelas"]) == ["Erros"]
    assert custo["total"] == Decimal("300.00")


@pytest.mark.django_db
def test_aditivo_ausente_tambem_e_dito_e_nao_entra_como_zero() -> None:
    processo = ProcessFactory(
        volume_mes=1, tempo_horas=Decimal("1.00"), pessoas=1, custo_hora=Decimal("10.00"),
        retrabalho_mes=Decimal("40.00"),
    )

    custo = process_module.custo_do_estado_atual(processo)

    assert custo["nao_apurado"] == ["Erros", "Perdas", "Espera", "Risco"]
    assert custo["total"] == Decimal("50.00")


@pytest.mark.django_db
def test_processo_sem_insumo_nenhum_nao_afirma_que_custa_zero() -> None:
    """Total zero **com as seis entradas em `nao_apurado`** é "não há insumo para dizer".

    É a distinção que o consumidor precisa fazer, e por isso ela é do `nao_apurado` e não do
    total: apresentar "R$ 0,00" a um cliente cujo processo ninguém mediu seria a casa afirmando o
    oposto do que ela sabe.
    """
    custo = process_module.custo_do_estado_atual(ProcessFactory())

    assert custo["parcelas"] == []
    assert custo["total"] == Decimal("0")
    assert custo["nao_apurado"] == list(process_module.ROTULOS_CUSTO)
    assert len(custo["nao_apurado"]) == 6


@pytest.mark.django_db
def test_a_sustentacao_pede_fato_vivo_e_volta_a_hipotese_quando_ele_e_arquivado() -> None:
    """O número vale conforme o que o sustenta (`docs/metodologia-fde.md:117`).

    Achado em hipótese não sustenta, e registro arquivado deixa de sustentar — desfazer o registro
    é desfazer o que ele afirmava. A fonte é o `Finding` do split (Fase 6): é o mesmo achado que a
    tela promove e que o custo consulta.
    """
    processo = ProcessFactory()
    FindingFactory(process=processo, account=processo.account)  # hipótese

    assert process_module.custo_do_estado_atual(processo)["sustentacao"] == "hipotese"

    fato = _fato_vivo(
        processo, statement="Relatório do ERP: 412 pedidos em agosto."
    )
    assert process_module.custo_do_estado_atual(processo)["sustentacao"] == "sustentado"

    fato.archive()
    assert process_module.custo_do_estado_atual(processo)["sustentacao"] == "hipotese"


def test_processo_ainda_nao_salvo_calcula_e_nao_se_diz_sustentado() -> None:
    """Sem banco: a conta é aritmética e não depende de o processo existir em tabela nenhuma.

    Quem pede a prévia antes de gravar recebe `"hipotese"`, que é a resposta certa — nenhum achado
    foi registrado ainda, e o gerente reverso nem poderia ser consultado.
    """
    custo = process_module.custo_do_estado_atual(
        Process(volume_mes=2, tempo_horas=Decimal("1.00"), pessoas=1, custo_hora=Decimal("30.00"))
    )

    assert custo["total"] == Decimal("60.00")
    assert custo["sustentacao"] == "hipotese"


@pytest.mark.django_db
def test_fato_de_outro_processo_nao_sustenta_este() -> None:
    processo = ProcessFactory()
    _fato_vivo(ProcessFactory())  # fato de outro processo (e de outra conta)

    assert process_module.custo_do_estado_atual(processo)["sustentacao"] == "hipotese"


# --- O contrato: papéis --------------------------------------------------------


@pytest.mark.django_db
@pytest.mark.parametrize("papel", [User.Role.ADMIN, User.Role.SALES, User.Role.DELIVERY])
def test_os_tres_papeis_criam_leem_editam_e_arquivam_nas_duas_rotas(
    client: APIClient, papel: str
) -> None:
    """Quem conduz Discovery é das duas áreas (FDD 037 aplicada de novo), e o admin sempre.

    A Entrega entra pelo cliente de um projeto seu — é a única forma de ela alcançar as rotas de
    processo e etapa. O achado do split tem o mesmo contrato de papéis, exercitado em
    `test_evidence_finding.py`.
    """
    usuario = UserFactory(role=papel)
    projeto = ProjectFactory()
    ProjectMemberFactory(project=projeto, user=usuario)
    client.force_authenticate(usuario)

    criado = client.post(
        reverse("processo-list"),
        {"account": projeto.engagement.account_id, "name": "Fechamento de mês", "volume_mes": 20},
        format="json",
    )
    assert criado.status_code == 201
    assert criado.data["registered_by"] == usuario.id
    assert criado.data["client_name"] == projeto.engagement.account.name
    processo_id = criado.data["id"]

    etapa = client.post(
        reverse("processoetapa-list"),
        {"process": processo_id, "name": "Conferência", "tempo": "cerca de 3h"},
        format="json",
    )
    assert etapa.status_code == 201

    editado = client.patch(
        reverse("processo-detail", args=[processo_id]), {"pessoas": 3}, format="json"
    )
    assert editado.status_code == 200
    assert editado.data["pessoas"] == 3

    for rota, item in (
        ("processoetapa", etapa.data["id"]),
        ("processo", processo_id),
    ):
        assert client.delete(reverse(f"{rota}-detail", args=[item])).status_code == 204
        assert item not in [row["id"] for row in client.get(reverse(f"{rota}-list")).data]
        assert client.post(reverse(f"{rota}-unarchive", args=[item])).status_code == 200


@pytest.mark.django_db
def test_quem_nao_foi_liberado_nao_alcanca_nenhuma_das_duas_rotas(client: APIClient) -> None:
    """Recurso novo nasce fechado: o papel sem nenhuma linha para ele cai no `return False`."""
    processo = ProcessFactory()
    etapa = ProcessStepFactory(process=processo)
    client.force_authenticate(UserFactory(role=""))

    assert client.get(reverse("processo-list")).status_code == 403
    assert client.get(reverse("processoetapa-list")).status_code == 403
    assert client.get(reverse("processo-detail", args=[processo.id])).status_code == 403
    assert client.get(reverse("processoetapa-detail", args=[etapa.id])).status_code == 403


# --- O contrato: a fronteira do cliente, nas duas metades ----------------------


@pytest.mark.django_db
def test_entrega_sem_projeto_no_cliente_nao_le_as_duas_entidades(client: APIClient) -> None:
    delivery = UserFactory(role=User.Role.DELIVERY)
    ProjectMemberFactory(project=ProjectFactory(), user=delivery)
    alheio = ProcessFactory(account=AccountFactory(name="Cliente alheio"))
    etapa_alheia = ProcessStepFactory(process=alheio)
    client.force_authenticate(delivery)

    assert [row["id"] for row in client.get(reverse("processo-list")).data] == []
    assert [row["id"] for row in client.get(reverse("processoetapa-list")).data] == []
    # Fora da queryset: do ponto de vista dela, nem existe.
    assert client.get(reverse("processo-detail", args=[alheio.id])).status_code == 404
    assert client.get(reverse("processoetapa-detail", args=[etapa_alheia.id])).status_code == 404


@pytest.mark.django_db
def test_entrega_sem_projeto_no_cliente_nao_escreve_as_duas_entidades(client: APIClient) -> None:
    """A metade que a listagem não protege: sem a guarda de escrita, uma requisição bastaria para
    mapear a operação de um cliente que a tela esconde — e na etapa o cliente é alcançado **só pelo
    processo pai**, que é onde a guarda é fácil de esquecer."""
    delivery = UserFactory(role=User.Role.DELIVERY)
    ProjectMemberFactory(project=ProjectFactory(), user=delivery)
    alheio = ProcessFactory(account=AccountFactory(name="Cliente alheio"))
    client.force_authenticate(delivery)

    criacao = client.post(
        reverse("processo-list"), {"account": alheio.account_id, "name": "x"}, format="json"
    )
    etapa = client.post(
        reverse("processoetapa-list"), {"process": alheio.id, "name": "x"}, format="json"
    )

    assert criacao.status_code in {403, 404}
    assert etapa.status_code in {403, 404}
    assert Process.objects.filter(account=alheio.account).count() == 1
    assert not ProcessStep.objects.exists()


@pytest.mark.django_db
def test_entrega_nao_move_registro_proprio_para_cliente_alheio(client: APIClient) -> None:
    """O caminho inverso da mesma fronteira: sem ele, mover é o atalho para escrever lá dentro."""
    delivery = UserFactory(role=User.Role.DELIVERY)
    meu = ProjectFactory()
    ProjectMemberFactory(project=meu, user=delivery)
    processo = ProcessFactory(account=meu.engagement.account)
    etapa = ProcessStepFactory(process=processo)
    alheio = ProcessFactory(account=AccountFactory())
    client.force_authenticate(delivery)

    mudou_cliente = client.patch(
        reverse("processo-detail", args=[processo.id]),
        {"account": alheio.account_id},
        format="json",
    )
    mudou_pai_da_etapa = client.patch(
        reverse("processoetapa-detail", args=[etapa.id]), {"process": alheio.id}, format="json"
    )

    assert mudou_cliente.status_code == 403
    assert mudou_pai_da_etapa.status_code == 403
    processo.refresh_from_db()
    etapa.refresh_from_db()
    assert processo.account_id == meu.engagement.account_id
    assert etapa.process_id == processo.id


# --- O contrato: o custo derivado ----------------------------------------------


@pytest.mark.django_db
def test_o_processo_devolve_a_conta_do_custo_no_corpo(client: APIClient) -> None:
    """O custo é derivado e read-only: mandá-lo no corpo não grava nada, porque a fórmula é a
    única verdade sobre os nove insumos."""
    processo = ProcessFactory(
        volume_mes=100, tempo_horas=Decimal("0.50"), pessoas=1, custo_hora=Decimal("80.00"),
        erros_mes=Decimal("1000.00"),
    )
    client.force_authenticate(UserFactory(role=User.Role.ADMIN))

    corpo = client.get(reverse("processo-detail", args=[processo.id])).data

    assert corpo["custo"]["total"] == "5000.00"
    assert corpo["custo"]["sustentacao"] == "hipotese"
    assert "Retrabalho" in corpo["custo"]["nao_apurado"]
    assert [parcela["label"] for parcela in corpo["custo"]["parcelas"]] == [
        process_module.ROTULO_NUCLEO, "Erros"
    ]


@pytest.mark.django_db
def test_o_autor_nao_entra_pelo_corpo(client: APIClient) -> None:
    admin = UserFactory(role=User.Role.ADMIN)
    outro = UserFactory(role=User.Role.DELIVERY)
    cliente = AccountFactory()
    client.force_authenticate(admin)

    criado = client.post(
        reverse("processo-list"),
        {"account": cliente.id, "name": "Compras", "registered_by": outro.id},
        format="json",
    )

    assert criado.status_code == 201
    assert criado.data["registered_by"] == admin.id


# --- O contrato: arquivamento --------------------------------------------------


@pytest.mark.django_db
def test_arquivar_o_processo_leva_as_etapas_mas_nao_os_achados() -> None:
    """A regra transversal da FDD 025 vale para a etapa; o achado tem outra ancoragem.

    A etapa é filha do processo (`/processo-etapas/?process=`) e cascateia — sem isso ela ficaria
    visível apontando para um pai oculto. O `Finding` não: ele é da **conta** (Fase 6, ADR 0052),
    e sobrevive ao arquivamento do mapa que o citava, porque uma afirmação sobre a operação do
    cliente não deixa de valer quando a entrada do processo é guardada. Some a sustentação **deste**
    processo — que `custo_do_estado_atual` recalcula —, não o achado.
    """
    processo = ProcessFactory()
    etapa = ProcessStepFactory(process=processo)
    achado = FindingFactory(process=processo, account=processo.account)

    processo.archive()

    etapa.refresh_from_db()
    achado.refresh_from_db()
    assert etapa.archived_at == processo.archived_at
    assert achado.archived_at is None


@pytest.mark.django_db
def test_desarquivar_devolve_so_o_que_este_arquivamento_levou() -> None:
    """A armadilha simétrica, e a razão de o carimbo ser o mesmo nas etapas.

    A etapa arquivada **antes**, de propósito, não pode voltar junto: restaurar tudo o que está
    arquivado desfaria uma decisão que ninguém pediu para desfazer.
    """
    processo = ProcessFactory()
    removida_antes = ProcessStepFactory(process=processo)
    removida_antes.archive()
    junto = ProcessStepFactory(process=processo)

    processo.archive()
    processo.unarchive()

    junto.refresh_from_db()
    removida_antes.refresh_from_db()
    assert processo.archived_at is None
    assert junto.archived_at is None
    assert removida_antes.archived_at is not None


@pytest.mark.django_db
def test_a_rota_de_desarquivar_passa_pelo_modelo_e_nao_devolve_processo_vazio(
    client: APIClient,
) -> None:
    """O `unarchive` genérico escreve `archived_at = None` direto e pularia a cascata."""
    admin = UserFactory(role=User.Role.ADMIN)
    processo = ProcessFactory()
    etapa = ProcessStepFactory(process=processo)
    client.force_authenticate(admin)
    client.delete(reverse("processo-detail", args=[processo.id]))

    resposta = client.post(reverse("processo-unarchive", args=[processo.id]))

    assert resposta.status_code == 200
    etapa.refresh_from_db()
    assert etapa.archived_at is None
    listadas = client.get(reverse("processoetapa-list"), {"process": processo.id}).data
    assert [linha["id"] for linha in listadas] == [etapa.id]


@pytest.mark.django_db
def test_arquivar_o_achado_tira_a_sustentacao_do_calculo() -> None:
    """Consequência que precisa ser verdade e não só coerente: fato arquivado não sustenta.

    `custo_do_estado_atual` ignora achado arquivado. Arquivar o processo **não** arquiva o achado
    (ele é da conta), então quem tira a sustentação é arquivar o próprio fato — e é o mesmo achado
    que a tela promove.
    """
    processo = ProcessFactory(volume_mes=10, tempo_horas=Decimal("2"), pessoas=1,
                              custo_hora=Decimal("50"))
    fato = _fato_vivo(processo)
    assert process_module.custo_do_estado_atual(processo)["sustentacao"] == "sustentado"

    fato.archive()

    assert process_module.custo_do_estado_atual(processo)["sustentacao"] == "hipotese"


@pytest.mark.django_db
def test_o_dinheiro_do_custo_viaja_como_texto_no_json_renderizado(client: APIClient) -> None:
    """Afirma sobre `response.content`, e não sobre `.data` — é a única camada que pega isto.

    `get_custo` é `SerializerMethodField`: o que ele devolve vai direto ao renderizador, e o
    encoder do DRF converte `Decimal` em `float`. Um teste sobre `.data` continua vendo `Decimal`
    e passa com o formato de fio errado — que foi exatamente como isto entrou.

    O que está em jogo não é estética: `Invoice.amount` viaja como string, então dois formatos de
    dinheiro na mesma API obrigam cada consumidor a adivinhar qual está lendo. E `float` de
    dinheiro é o que o `process.py` evita por dentro, com a razão escrita na docstring dele.
    """
    processo = ProcessFactory(
        volume_mes=100, tempo_horas=Decimal("0.50"), pessoas=1, custo_hora=Decimal("80.00"),
        erros_mes=Decimal("18.99"),
    )
    client.force_authenticate(UserFactory(role=User.Role.ADMIN))

    resposta = client.get(reverse("processo-detail", args=[processo.id]))
    corpo = json.loads(resposta.content)

    assert corpo["custo"]["total"] == "4018.99"
    assert isinstance(corpo["custo"]["total"], str)
    valores = {parcela["label"]: parcela["valor"] for parcela in corpo["custo"]["parcelas"]}
    assert valores["Erros"] == "18.99"
    # Os centavos são o ponto: como `float`, `4000.00` vira `4000.0` e o valor perde a forma em
    # que foi digitado.
    assert valores[process_module.ROTULO_NUCLEO] == "4000.00"


def test_as_parcelas_somam_exatamente_o_total() -> None:
    """A conta que a tela mostra tem de fechar — e é o arredondamento que decide isso.

    `Decimal` soma expoentes na multiplicação, então o núcleo sai com quatro casas. Arredondar só
    o total (e não cada parcela) produziria linhas que não somam o número embaixo delas, em uma
    tela cujo propósito é justamente mostrar a conta. Quem vê parcela que não bate com total para
    de confiar nas duas.
    """
    processo = Process(
        volume_mes=3, tempo_horas=Decimal("0.335"), pessoas=7, custo_hora=Decimal("99.99"),
        retrabalho_mes=Decimal("0.005"), erros_mes=Decimal("0.005"),
    )

    custo = process_module.custo_do_estado_atual(processo)

    assert sum(parcela["valor"] for parcela in custo["parcelas"]) == custo["total"]
    # Duas casas em toda parcela e no total: é dinheiro, e a forma tem de ser a de `Invoice.amount`.
    assert all(-parcela["valor"].as_tuple().exponent == 2 for parcela in custo["parcelas"])
    assert -custo["total"].as_tuple().exponent == 2
