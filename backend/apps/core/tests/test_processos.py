"""O Discovery estruturado: processo, etapa e evidência (FDD 039).

Três coisas são exercitadas aqui, e as três são a razão de a fatia existir:

- **a distinção entre observado e suposto** — `rotulo` e `forma` sem default, no molde de
  `Satisfacao.fonte`: o POST sem eles é 400, e não um "fato" escolhido por omissão;
- **a fronteira do cliente nas duas metades**, como em `test_satisfacao.py` — e aqui ela se
  estende pelo processo pai, que é por onde a etapa e a evidência chegariam ao cliente alheio;
- **a lacuna dita e não preenchida** no custo do estado atual: fator ausente vai para
  `nao_apurado` e não vira zero no total, no molde do KPI sem base registrada da FDD 027.

O oráculo do cálculo é função pura (`apps/core/processos.py`), testado sem banco onde dá — o
resto precisa de banco porque `sustentacao` pergunta pelas evidências vivas do processo.
"""

from decimal import Decimal

import pytest
from django.core.exceptions import ValidationError
from django.urls import reverse
from rest_framework.test import APIClient

from apps.core import processos as processos_module
from apps.core.models import Evidencia, Processo, ProcessoEtapa, User

from .factories import (
    ClientFactory,
    EvidenciaFactory,
    ProcessoEtapaFactory,
    ProcessoFactory,
    ProjectFactory,
    ProjectMemberFactory,
    UserFactory,
)


@pytest.fixture
def client() -> APIClient:
    return APIClient()


def _payload_evidencia(processo_id: int, **overrides: object) -> dict:
    base: dict = {
        "processo": processo_id,
        "forma": Evidencia.Forma.OBSERVACAO,
        "rotulo": Evidencia.Rotulo.FATO,
        "content": "Vi a analista conferindo pedido a pedido na planilha.",
    }
    base.update(overrides)
    return base


# --- O cálculo do custo do estado atual ---------------------------------------


def _rotulos(parcelas: list[dict]) -> list[str]:
    return [parcela["label"] for parcela in parcelas]


@pytest.mark.django_db
def test_o_nucleo_multiplica_os_quatro_fatores() -> None:
    """`Volume × Tempo × Pessoas × Custo` (`docs/metodologia-fde.md:87-88`), em `Decimal`."""
    processo = ProcessoFactory(
        volume_mes=40, tempo_horas=Decimal("2.50"), pessoas=2, custo_hora=Decimal("60.00")
    )

    custo = processos_module.custo_do_estado_atual(processo)

    assert custo["parcelas"] == [
        {"label": processos_module.ROTULO_NUCLEO, "valor": Decimal("12000.00")}
    ]
    assert custo["total"] == Decimal("12000.00")
    assert custo["nao_apurado"] == [rotulo for _, rotulo in processos_module.ADITIVOS]


@pytest.mark.django_db
def test_o_nucleo_soma_com_os_cinco_aditivos() -> None:
    processo = ProcessoFactory(
        volume_mes=10, tempo_horas=Decimal("1.00"), pessoas=1, custo_hora=Decimal("100.00"),
        retrabalho_mes=Decimal("500.00"), erros_mes=Decimal("250.00"),
        perdas_mes=Decimal("125.00"), espera_mes=Decimal("75.00"), risco_mes=Decimal("50.00"),
    )

    custo = processos_module.custo_do_estado_atual(processo)

    assert _rotulos(custo["parcelas"]) == list(processos_module.ROTULOS_CUSTO)
    assert custo["total"] == Decimal("2000.00")
    assert custo["nao_apurado"] == []


@pytest.mark.django_db
@pytest.mark.parametrize("faltante", processos_module.FATORES_NUCLEO)
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
    processo = ProcessoFactory(**campos)

    custo = processos_module.custo_do_estado_atual(processo)

    assert processos_module.ROTULO_NUCLEO in custo["nao_apurado"]
    assert _rotulos(custo["parcelas"]) == ["Erros"]
    assert custo["total"] == Decimal("300.00")


@pytest.mark.django_db
def test_aditivo_ausente_tambem_e_dito_e_nao_entra_como_zero() -> None:
    processo = ProcessoFactory(
        volume_mes=1, tempo_horas=Decimal("1.00"), pessoas=1, custo_hora=Decimal("10.00"),
        retrabalho_mes=Decimal("40.00"),
    )

    custo = processos_module.custo_do_estado_atual(processo)

    assert custo["nao_apurado"] == ["Erros", "Perdas", "Espera", "Risco"]
    assert custo["total"] == Decimal("50.00")


@pytest.mark.django_db
def test_processo_sem_insumo_nenhum_nao_afirma_que_custa_zero() -> None:
    """Total zero **com as seis entradas em `nao_apurado`** é "não há insumo para dizer".

    É a distinção que o consumidor precisa fazer, e por isso ela é do `nao_apurado` e não do
    total: apresentar "R$ 0,00" a um cliente cujo processo ninguém mediu seria a casa afirmando o
    oposto do que ela sabe.
    """
    custo = processos_module.custo_do_estado_atual(ProcessoFactory())

    assert custo["parcelas"] == []
    assert custo["total"] == Decimal("0")
    assert custo["nao_apurado"] == list(processos_module.ROTULOS_CUSTO)
    assert len(custo["nao_apurado"]) == 6


@pytest.mark.django_db
def test_a_sustentacao_pede_fato_vivo_e_volta_a_hipotese_quando_ele_e_arquivado() -> None:
    """O número vale conforme o que o sustenta (`docs/metodologia-fde.md:86`).

    Entrevista rotulada como hipótese não sustenta, e registro arquivado deixa de sustentar —
    desfazer o registro é desfazer o que ele afirmava.
    """
    processo = ProcessoFactory()
    EvidenciaFactory(processo=processo)  # entrevista/hipótese

    assert processos_module.custo_do_estado_atual(processo)["sustentacao"] == "hipotese"

    fato = EvidenciaFactory(
        processo=processo, forma=Evidencia.Forma.DADO, rotulo=Evidencia.Rotulo.FATO,
        content="Relatório do ERP: 412 pedidos em agosto.",
    )
    assert processos_module.custo_do_estado_atual(processo)["sustentacao"] == "sustentado"

    fato.archive()
    assert processos_module.custo_do_estado_atual(processo)["sustentacao"] == "hipotese"


def test_processo_ainda_nao_salvo_calcula_e_nao_se_diz_sustentado() -> None:
    """Sem banco: a conta é aritmética e não depende de o processo existir em tabela nenhuma.

    Quem pede a prévia antes de gravar recebe `"hipotese"`, que é a resposta certa — nenhuma
    evidência foi registrada ainda, e o gerente reverso nem poderia ser consultado.
    """
    custo = processos_module.custo_do_estado_atual(
        Processo(volume_mes=2, tempo_horas=Decimal("1.00"), pessoas=1, custo_hora=Decimal("30.00"))
    )

    assert custo["total"] == Decimal("60.00")
    assert custo["sustentacao"] == "hipotese"


@pytest.mark.django_db
def test_evidencia_de_outro_processo_nao_sustenta_este() -> None:
    processo = ProcessoFactory()
    EvidenciaFactory(rotulo=Evidencia.Rotulo.FATO)  # de outro processo

    assert processos_module.custo_do_estado_atual(processo)["sustentacao"] == "hipotese"


# --- Os modelos ---------------------------------------------------------------


@pytest.mark.django_db
def test_o_clean_da_evidencia_recusa_etapa_de_outro_processo() -> None:
    """Sem esta guarda, um campo opcional vaza entre contas: a etapa alheia pode ser de outro
    cliente, e a evidência passaria a apontar para dentro dele."""
    processo = ProcessoFactory()
    alheia = ProcessoEtapaFactory()

    with pytest.raises(ValidationError) as erro:
        Evidencia(
            processo=processo, etapa=alheia, forma=Evidencia.Forma.DADO,
            rotulo=Evidencia.Rotulo.FATO, content="x",
        ).clean()

    assert "etapa" in erro.value.message_dict

    # A etapa do próprio processo passa, e é o caso que a guarda não pode atrapalhar.
    Evidencia(
        processo=processo, etapa=ProcessoEtapaFactory(processo=processo),
        forma=Evidencia.Forma.DADO, rotulo=Evidencia.Rotulo.FATO, content="x",
    ).clean()


@pytest.mark.django_db
def test_a_etapa_e_a_evidencia_ordenam_por_posicao_e_por_recencia() -> None:
    processo = ProcessoFactory()
    segunda = ProcessoEtapaFactory(processo=processo, name="Segunda", position=2)
    primeira = ProcessoEtapaFactory(processo=processo, name="Primeira", position=1)

    assert list(processo.etapas.all()) == [primeira, segunda]
    assert str(primeira) == "Primeira"
    assert str(processo) == "Faturamento mensal"

    velha = EvidenciaFactory(processo=processo, content="Primeiro achado")
    nova = EvidenciaFactory(processo=processo, content="Achado mais recente")
    assert list(processo.evidencias.all())[0] in {nova, velha}  # ordenado por `-created_at, -id`
    assert list(processo.evidencias.all())[0] == nova
    assert str(nova).startswith("Hipótese — ")


# --- O contrato: papéis --------------------------------------------------------


@pytest.mark.django_db
@pytest.mark.parametrize("papel", [User.Role.ADMIN, User.Role.SALES, User.Role.DELIVERY])
def test_os_tres_papeis_criam_leem_editam_e_arquivam_nas_tres_rotas(
    client: APIClient, papel: str
) -> None:
    """Quem conduz Discovery é das duas áreas (FDD 037 aplicada de novo), e o admin sempre.

    A Entrega entra pelo cliente de um projeto seu — é a única forma de ela alcançar qualquer uma
    das três rotas.
    """
    usuario = UserFactory(role=papel)
    projeto = ProjectFactory()
    ProjectMemberFactory(project=projeto, user=usuario)
    client.force_authenticate(usuario)

    criado = client.post(
        reverse("processo-list"),
        {"client": projeto.client_id, "name": "Fechamento de mês", "volume_mes": 20},
        format="json",
    )
    assert criado.status_code == 201
    assert criado.data["registered_by"] == usuario.id
    assert criado.data["client_name"] == projeto.client.name
    processo_id = criado.data["id"]

    etapa = client.post(
        reverse("processoetapa-list"),
        {"processo": processo_id, "name": "Conferência", "tempo": "cerca de 3h"},
        format="json",
    )
    assert etapa.status_code == 201

    evidencia = client.post(
        reverse("evidencia-list"),
        _payload_evidencia(processo_id, etapa=etapa.data["id"]),
        format="json",
    )
    assert evidencia.status_code == 201
    assert evidencia.data["rotulo_display"] == "Fato"
    assert evidencia.data["forma_display"] == "Observação (o que fazem)"
    assert evidencia.data["registered_by"] == usuario.id

    editado = client.patch(
        reverse("processo-detail", args=[processo_id]), {"pessoas": 3}, format="json"
    )
    assert editado.status_code == 200
    assert editado.data["pessoas"] == 3

    for rota, item in (
        ("evidencia", evidencia.data["id"]),
        ("processoetapa", etapa.data["id"]),
        ("processo", processo_id),
    ):
        assert client.delete(reverse(f"{rota}-detail", args=[item])).status_code == 204
        assert item not in [row["id"] for row in client.get(reverse(f"{rota}-list")).data]
        assert client.post(reverse(f"{rota}-unarchive", args=[item])).status_code == 200


@pytest.mark.django_db
def test_quem_nao_foi_liberado_nao_alcanca_nenhuma_das_tres_rotas(client: APIClient) -> None:
    """Recurso novo nasce fechado: o papel sem nenhuma linha para ele cai no `return False`."""
    evidencia = EvidenciaFactory()
    client.force_authenticate(UserFactory(role=""))

    assert client.get(reverse("processo-list")).status_code == 403
    assert client.get(reverse("processoetapa-list")).status_code == 403
    assert client.get(reverse("evidencia-list")).status_code == 403
    assert client.get(reverse("evidencia-detail", args=[evidencia.id])).status_code == 403
    assert client.post(
        reverse("evidencia-list"), _payload_evidencia(evidencia.processo_id), format="json"
    ).status_code == 403


# --- O contrato: a fronteira do cliente, nas duas metades ----------------------


@pytest.mark.django_db
def test_entrega_sem_projeto_no_cliente_nao_le_as_tres_entidades(client: APIClient) -> None:
    delivery = UserFactory(role=User.Role.DELIVERY)
    ProjectMemberFactory(project=ProjectFactory(), user=delivery)
    alheio = ProcessoFactory(client=ClientFactory(name="Cliente alheio"))
    etapa_alheia = ProcessoEtapaFactory(processo=alheio)
    evidencia_alheia = EvidenciaFactory(processo=alheio, etapa=etapa_alheia)
    client.force_authenticate(delivery)

    assert [row["id"] for row in client.get(reverse("processo-list")).data] == []
    assert [row["id"] for row in client.get(reverse("processoetapa-list")).data] == []
    assert [row["id"] for row in client.get(reverse("evidencia-list")).data] == []
    # Fora da queryset: do ponto de vista dela, nem existe.
    assert client.get(reverse("processo-detail", args=[alheio.id])).status_code == 404
    assert client.get(reverse("processoetapa-detail", args=[etapa_alheia.id])).status_code == 404
    assert client.get(reverse("evidencia-detail", args=[evidencia_alheia.id])).status_code == 404


@pytest.mark.django_db
def test_entrega_sem_projeto_no_cliente_nao_escreve_as_tres_entidades(client: APIClient) -> None:
    """A metade que a listagem não protege: sem a guarda de escrita, uma requisição bastaria para
    mapear a operação de um cliente que a tela esconde — e nos filhos o cliente é alcançado
    **só pelo processo pai**, que é onde a guarda é fácil de esquecer."""
    delivery = UserFactory(role=User.Role.DELIVERY)
    ProjectMemberFactory(project=ProjectFactory(), user=delivery)
    alheio = ProcessoFactory(client=ClientFactory(name="Cliente alheio"))
    client.force_authenticate(delivery)

    criacao = client.post(
        reverse("processo-list"), {"client": alheio.client_id, "name": "x"}, format="json"
    )
    etapa = client.post(
        reverse("processoetapa-list"), {"processo": alheio.id, "name": "x"}, format="json"
    )
    evidencia = client.post(reverse("evidencia-list"), _payload_evidencia(alheio.id), format="json")

    assert criacao.status_code in {403, 404}
    assert etapa.status_code in {403, 404}
    assert evidencia.status_code in {403, 404}
    assert Processo.objects.filter(client=alheio.client).count() == 1
    assert not ProcessoEtapa.objects.exists()
    assert not Evidencia.objects.exists()


@pytest.mark.django_db
def test_entrega_nao_move_registro_proprio_para_cliente_alheio(client: APIClient) -> None:
    """O caminho inverso da mesma fronteira: sem ele, mover é o atalho para escrever lá dentro."""
    delivery = UserFactory(role=User.Role.DELIVERY)
    meu = ProjectFactory()
    ProjectMemberFactory(project=meu, user=delivery)
    processo = ProcessoFactory(client=meu.client)
    evidencia = EvidenciaFactory(processo=processo)
    etapa = ProcessoEtapaFactory(processo=processo)
    alheio = ProcessoFactory(client=ClientFactory())
    client.force_authenticate(delivery)

    mudou_cliente = client.patch(
        reverse("processo-detail", args=[processo.id]),
        {"client": alheio.client_id},
        format="json",
    )
    mudou_pai_da_evidencia = client.patch(
        reverse("evidencia-detail", args=[evidencia.id]), {"processo": alheio.id}, format="json"
    )
    mudou_pai_da_etapa = client.patch(
        reverse("processoetapa-detail", args=[etapa.id]), {"processo": alheio.id}, format="json"
    )

    assert mudou_cliente.status_code == 403
    assert mudou_pai_da_evidencia.status_code == 403
    assert mudou_pai_da_etapa.status_code == 403
    processo.refresh_from_db()
    evidencia.refresh_from_db()
    etapa.refresh_from_db()
    assert processo.client_id == meu.client_id
    assert evidencia.processo_id == processo.id
    assert etapa.processo_id == processo.id


# --- O contrato: rótulo, forma e filtros ---------------------------------------


@pytest.mark.django_db
@pytest.mark.parametrize("ausente", ["rotulo", "forma"])
def test_evidencia_sem_rotulo_ou_sem_forma_e_400_e_nao_default_silencioso(
    client: APIClient, ausente: str
) -> None:
    """A decisão central da fatia, no precedente de `Satisfacao.fonte`.

    Um default faria a casa escolher por quem não escolheu, e o erro cairia sempre para o mesmo
    lado — apresentar como fato o que ninguém confirmou, que é o que
    `docs/metodologia-fde.md:86` proíbe.
    """
    processo = ProcessoFactory()
    client.force_authenticate(UserFactory(role=User.Role.ADMIN))
    payload = _payload_evidencia(processo.id)
    del payload[ausente]

    resposta = client.post(reverse("evidencia-list"), payload, format="json")

    assert resposta.status_code == 400
    assert ausente in resposta.data
    assert not Evidencia.objects.exists()


@pytest.mark.django_db
def test_desconhecido_e_valor_de_primeira_classe(client: APIClient) -> None:
    """Nomear o que ainda não se sabe é fazer o trabalho (`docs/metodologia-fde.md:97-98`)."""
    processo = ProcessoFactory()
    client.force_authenticate(UserFactory(role=User.Role.ADMIN))

    resposta = client.post(
        reverse("evidencia-list"),
        _payload_evidencia(
            processo.id, rotulo=Evidencia.Rotulo.DESCONHECIDO,
            content="Ninguém soube dizer quantas devoluções acontecem por mês.",
        ),
        format="json",
    )

    assert resposta.status_code == 201
    assert resposta.data["rotulo_display"] == "Desconhecido"


@pytest.mark.django_db
def test_a_api_recusa_etapa_de_outro_processo_com_400(client: APIClient) -> None:
    """400 e não 500, e sobretudo **não 201**: o `save()` do DRF não chama `full_clean`, então sem
    a regra repetida no serializer o vazamento seria gravado em silêncio."""
    processo = ProcessoFactory()
    alheia = ProcessoEtapaFactory()
    client.force_authenticate(UserFactory(role=User.Role.ADMIN))

    resposta = client.post(
        reverse("evidencia-list"),
        _payload_evidencia(processo.id, etapa=alheia.id),
        format="json",
    )

    assert resposta.status_code == 400
    assert "etapa" in resposta.data
    assert not Evidencia.objects.exists()


@pytest.mark.django_db
def test_os_filtros_separam_processo_etapa_rotulo_e_forma(client: APIClient) -> None:
    """`?rotulo=fato` precisa **filtrar**: em `filter_fields` ele cairia no chão sem erro nenhum,
    e a lista voltaria inteira, com hipótese junto de fato."""
    processo, outro = ProcessoFactory(), ProcessoFactory()
    etapa = ProcessoEtapaFactory(processo=processo)
    fato = EvidenciaFactory(
        processo=processo, etapa=etapa, forma=Evidencia.Forma.DADO,
        rotulo=Evidencia.Rotulo.FATO, content="412 pedidos em agosto (ERP).",
    )
    hipotese = EvidenciaFactory(processo=processo)
    EvidenciaFactory(processo=outro, rotulo=Evidencia.Rotulo.FATO, forma=Evidencia.Forma.DADO)
    client.force_authenticate(UserFactory(role=User.Role.ADMIN))

    def _ids(**params: object) -> list[int]:
        return [row["id"] for row in client.get(reverse("evidencia-list"), params).data]

    assert set(_ids(processo=processo.id)) == {fato.id, hipotese.id}
    assert _ids(etapa=etapa.id) == [fato.id]
    assert _ids(processo=processo.id, rotulo=Evidencia.Rotulo.FATO) == [fato.id]
    assert _ids(processo=processo.id, forma=Evidencia.Forma.ENTREVISTA) == [hipotese.id]


@pytest.mark.django_db
def test_o_processo_devolve_a_conta_do_custo_no_corpo(client: APIClient) -> None:
    """O custo é derivado e read-only: mandá-lo no corpo não grava nada, porque a fórmula é a
    única verdade sobre os nove insumos."""
    processo = ProcessoFactory(
        volume_mes=100, tempo_horas=Decimal("0.50"), pessoas=1, custo_hora=Decimal("80.00"),
        erros_mes=Decimal("1000.00"),
    )
    client.force_authenticate(UserFactory(role=User.Role.ADMIN))

    corpo = client.get(reverse("processo-detail", args=[processo.id])).data

    assert corpo["custo"]["total"] == Decimal("5000.00")
    assert corpo["custo"]["sustentacao"] == "hipotese"
    assert "Retrabalho" in corpo["custo"]["nao_apurado"]
    assert [parcela["label"] for parcela in corpo["custo"]["parcelas"]] == [
        processos_module.ROTULO_NUCLEO, "Erros"
    ]


@pytest.mark.django_db
def test_o_autor_nao_entra_pelo_corpo(client: APIClient) -> None:
    admin = UserFactory(role=User.Role.ADMIN)
    outro = UserFactory(role=User.Role.DELIVERY)
    cliente = ClientFactory()
    client.force_authenticate(admin)

    criado = client.post(
        reverse("processo-list"),
        {"client": cliente.id, "name": "Compras", "registered_by": outro.id},
        format="json",
    )

    assert criado.status_code == 201
    assert criado.data["registered_by"] == admin.id


@pytest.mark.django_db
def test_arquivar_o_processo_leva_etapas_e_evidencias_juntas() -> None:
    """A regra transversal da FDD 025: filho listável não fica visível apontando para pai oculto.

    Sem a cascata, `/processo-etapas/?processo=` e `/evidencias/?processo=` seguiriam devolvendo
    as linhas de um processo que sumiu da tela — e uma evidência órfã continua sendo uma
    afirmação sobre a operação de um cliente, sem o processo que lhe dava contexto.
    """
    processo = ProcessoFactory()
    etapa = ProcessoEtapaFactory(processo=processo)
    evidencia = EvidenciaFactory(processo=processo, etapa=etapa)

    processo.archive()

    etapa.refresh_from_db()
    evidencia.refresh_from_db()
    assert etapa.archived_at == processo.archived_at
    assert evidencia.archived_at == processo.archived_at


@pytest.mark.django_db
def test_desarquivar_devolve_so_o_que_este_arquivamento_levou() -> None:
    """A armadilha simétrica, e a razão de o carimbo ser o mesmo nos três.

    A etapa arquivada **antes**, de propósito, não pode voltar junto: restaurar tudo o que está
    arquivado desfaria uma decisão que ninguém pediu para desfazer.
    """
    processo = ProcessoFactory()
    removida_antes = ProcessoEtapaFactory(processo=processo)
    removida_antes.archive()
    junto = ProcessoEtapaFactory(processo=processo)
    evidencia = EvidenciaFactory(processo=processo)

    processo.archive()
    processo.unarchive()

    junto.refresh_from_db()
    evidencia.refresh_from_db()
    removida_antes.refresh_from_db()
    assert processo.archived_at is None
    assert junto.archived_at is None
    assert evidencia.archived_at is None
    assert removida_antes.archived_at is not None


@pytest.mark.django_db
def test_a_rota_de_desarquivar_passa_pelo_modelo_e_nao_devolve_processo_vazio(
    client: APIClient,
) -> None:
    """O `unarchive` genérico escreve `archived_at = None` direto e pularia a cascata."""
    admin = UserFactory(role=User.Role.ADMIN)
    processo = ProcessoFactory()
    etapa = ProcessoEtapaFactory(processo=processo)
    client.force_authenticate(admin)
    client.delete(reverse("processo-detail", args=[processo.id]))

    resposta = client.post(reverse("processo-unarchive", args=[processo.id]))

    assert resposta.status_code == 200
    etapa.refresh_from_db()
    assert etapa.archived_at is None
    listadas = client.get(reverse("processoetapa-list"), {"processo": processo.id}).data
    assert [linha["id"] for linha in listadas] == [etapa.id]


@pytest.mark.django_db
def test_arquivar_o_processo_tira_a_sustentacao_do_calculo() -> None:
    """Consequência que precisa ser verdade e não só coerente: o fato arquivado junto não sustenta.

    `custo_do_estado_atual` já ignora evidência arquivada; a cascata faz o processo guardado
    parar de afirmar número sustentado sem ninguém ter revisado o registro.
    """
    processo = ProcessoFactory(volume_mes=10, tempo_horas=Decimal("2"), pessoas=1,
                               custo_hora=Decimal("50"))
    EvidenciaFactory(processo=processo, rotulo=Evidencia.Rotulo.FATO)
    assert processos_module.custo_do_estado_atual(processo)["sustentacao"] == "sustentado"

    processo.archive()

    assert processos_module.custo_do_estado_atual(processo)["sustentacao"] == "hipotese"
