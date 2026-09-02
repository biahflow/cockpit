"""Regressão: a cadeia de publicação do Discovery tem cinco portas, e nenhuma vaza (FDD 051).

O que o cliente vê precisa ter sustentação **publicada** embaixo. Sem isso, `finding_ids` e
`pain_point_ids` apontam para o que não atravessou, e o One renderiza uma afirmação sobre a
operação do cliente com nada atrás — pior que a omissão, porque parece completo.

A invariante é fácil de afirmar e tem cinco portas por onde se desfaz. Quatro delas não existiam
como código antes desta fatia, e nenhuma delas deixaria nada vermelho:

1. **`publish/`** — subir sem sustentação publicada. É a porta óbvia, e a única que a issue pediu.
2. **`unpublish/`** — a metade que sempre vaza: publicar confere a cadeia no instante em que o
   item sobe; despublicar a desfaz depois, item a item.
3. **`DELETE` (arquivar)** — arquivar some da projeção exatamente como despublicar. As guardas de
   `Evidence` e `Finding` já existiam para a dimensão do `fact`/`confirmed`; a da publicação entra
   **em cima** delas, e as de `PainPoint` e `Process` nasceram aqui.
4. **`PATCH` promovendo a `fact`** — um achado publicado como hipótese não exige nada; promovido
   depois, passaria a dizer "fato" com evidência interna embaixo.
5. **`PATCH` movendo a âncora** de um registro publicado para um mapa não publicado. É a porta que
   menos parece porta: as quatro anteriores olham a **marca**, e esta não toca em `published_at`
   nenhum — mas `findings[].process_id` passa a apontar para fora de `processes[]` igual.

Mais a regra de forma que sustenta todas: **publicar é ato com autor**, e `published_at` sem
`published_by` é `ValidationError` nos cinco modelos — a forma do `gap_waiver`/`gap_waiver_by` do
`ProveExperiment` e do `status=approved`/`approved_by` do `ValueLedgerEntry`.

## A âncora: o `Process` também tem marca, e ele é raiz do próprio ramo

São **cinco** modelos marcados, e não quatro. "O AS-IS *validado*" da §3 do `language-map` era um
qualificador tão sem lastro no schema quanto "Evidence marcada como revisada e publicável": não
havia campo nenhum dizendo que o mapa tinha sido conferido com o cliente, e a caracterização da
casa sobre onde o time dele erra (`ProcessStep.erro`/`.retrabalho`) atravessava sem ninguém ter
decidido mostrá-la.

O `Process` não pede nada para subir — as etapas andam com ele —, mas `findings[].process_id` e
`pain_points[].process_id` atravessam, e um achado publicado citando um mapa fora de `processes[]`
é referência pendurada. Daí as três metades: **exige a âncora publicada para o achado subir**,
**recusa a saída da âncora** enquanto alguém publicado a citar, e **recusa que a âncora se mude
por baixo** de quem já subiu.
"""

import pytest
from django.core.exceptions import ValidationError
from django.urls import reverse
from django.utils import timezone
from rest_framework.test import APIClient

from apps.core import portal
from apps.core.models import (
    Evidence,
    Finding,
    ImprovementOpportunity,
    PainPoint,
    Process,
    ProcessStep,
    User,
)
from apps.core.tests.factories import (
    AccountFactory,
    EvidenceFactory,
    FindingFactory,
    ImprovementOpportunityFactory,
    PainPointFactory,
    ProcessFactory,
    ProjectFactory,
    UserFactory,
)

pytestmark = pytest.mark.django_db


@pytest.fixture
def autor() -> User:
    return UserFactory(role=User.Role.ADMIN)


@pytest.fixture
def api(autor: User) -> APIClient:
    client = APIClient()
    client.force_authenticate(autor)
    return client


def _publica(obj, autor: User):  # type: ignore[no-untyped-def]
    obj.published_at = timezone.now()
    obj.published_by = autor
    obj.save(update_fields=["published_at", "published_by", "updated_at"])
    return obj


# --- 1. `publish/`: subir exige sustentação publicada -------------------------


def test_publicar_um_fato_sem_evidencia_publicada_e_400_e_diz_o_que_falta(
    api: APIClient, autor: User
) -> None:
    """400 via `InvalidInput`, e nunca 409: o pedido é que está errado.

    409 mandaria quem lê procurar num estado que está perfeitamente bom — é a contrapartida exata
    que `exceptions.py` documenta, e a escolha de `journey.apply_gate` e de `start/`.
    """
    conta = AccountFactory()
    interna = EvidenceFactory(account=conta)
    fato = FindingFactory(
        account=conta, epistemic_status=Finding.EpistemicStatus.FACT, reviewed_by=autor
    )
    fato.evidences.add(interna)

    resposta = api.post(reverse("finding-publish", args=[fato.pk]))

    assert resposta.status_code == 400, resposta.data
    assert "evidência publicada" in str(resposta.data["detail"])
    fato.refresh_from_db()
    assert fato.published_at is None


def test_publicar_uma_hipotese_nao_exige_evidencia_publicada(api: APIClient) -> None:
    """A hipótese publicada é honesta **por não afirmar** sustentação que não tem.

    É o que se leva à reunião, rotulado como hipótese, e a regra 1 da §3 do `language-map` permite
    exatamente isso: o que a marca garante é que alguém leu e decidiu mostrar.
    """
    achado = FindingFactory(account=AccountFactory())

    resposta = api.post(reverse("finding-publish", args=[achado.pk]))

    assert resposta.status_code == 200, resposta.data
    achado.refresh_from_db()
    assert achado.published_at is not None
    assert achado.published_by_id is not None


def test_publicar_evidencia_nao_exige_nada_porque_ela_e_a_folha(api: APIClient) -> None:
    evidencia = EvidenceFactory(account=AccountFactory())

    resposta = api.post(reverse("evidence-publish", args=[evidencia.pk]))

    assert resposta.status_code == 200, resposta.data
    assert resposta.data["published_by"] is not None


def test_publicar_dor_sem_achado_publicado_e_oportunidade_sem_dor_publicada_sao_400(
    api: APIClient, autor: User
) -> None:
    conta = AccountFactory()
    dor = PainPointFactory(account=conta)
    dor.findings.add(FindingFactory(account=conta))
    oportunidade = ImprovementOpportunityFactory(account=conta)
    oportunidade.pain_points.add(dor)

    da_dor = api.post(reverse("painpoint-publish", args=[dor.pk]))
    da_oportunidade = api.post(
        reverse("improvementopportunity-publish", args=[oportunidade.pk])
    )

    assert da_dor.status_code == 400, da_dor.data
    assert "achado publicado" in str(da_dor.data["detail"])
    assert da_oportunidade.status_code == 400, da_oportunidade.data
    assert "dor publicada" in str(da_oportunidade.data["detail"])

    # E a escada sobe inteira quando cada degrau tem o de baixo publicado.
    _publica(dor.findings.get(), autor)
    assert api.post(reverse("painpoint-publish", args=[dor.pk])).status_code == 200
    assert api.post(
        reverse("improvementopportunity-publish", args=[oportunidade.pk])
    ).status_code == 200


def test_publicar_duas_vezes_e_409(api: APIClient, autor: User) -> None:
    """409 via `StateConflict`: o pedido está bem formado, o que impede é o estado."""
    achado = _publica(FindingFactory(account=AccountFactory()), autor)

    resposta = api.post(reverse("finding-publish", args=[achado.pk]))

    assert resposta.status_code == 409, resposta.data


# --- 2. `unpublish/`: a metade que sempre vaza --------------------------------


def test_despublicar_a_ultima_sustentacao_de_algo_publicado_e_409_nos_tres_degraus(
    api: APIClient, autor: User
) -> None:
    """Recusar, e nunca despublicar o de cima em silêncio.

    É o argumento das duas guardas de arquivamento que já existiam (FDD 045, FDD 048): desfazer
    sozinho uma decisão que uma pessoa tomou é pior que o 409 que diz qual estado impede e como
    sair dele. A mensagem manda despublicar o de cima primeiro.
    """
    conta = AccountFactory()
    evidencia = _publica(EvidenceFactory(account=conta), autor)
    fato = FindingFactory(
        account=conta, epistemic_status=Finding.EpistemicStatus.FACT, reviewed_by=autor
    )
    fato.evidences.add(evidencia)
    _publica(fato, autor)
    dor = PainPointFactory(account=conta)
    dor.findings.add(fato)
    _publica(dor, autor)
    oportunidade = ImprovementOpportunityFactory(account=conta)
    oportunidade.pain_points.add(dor)
    _publica(oportunidade, autor)

    da_evidencia = api.post(reverse("evidence-unpublish", args=[evidencia.pk]))
    do_achado = api.post(reverse("finding-unpublish", args=[fato.pk]))
    da_dor = api.post(reverse("painpoint-unpublish", args=[dor.pk]))

    assert da_evidencia.status_code == 409, da_evidencia.data
    assert "Despublique o achado primeiro" in str(da_evidencia.data["detail"])
    assert do_achado.status_code == 409, do_achado.data
    assert "Despublique a dor primeiro" in str(do_achado.data["detail"])
    assert da_dor.status_code == 409, da_dor.data
    assert "Despublique a oportunidade primeiro" in str(da_dor.data["detail"])

    # A escada desce inteira na ordem inversa — que é o caminho de saída que a mensagem indica.
    assert api.post(
        reverse("improvementopportunity-unpublish", args=[oportunidade.pk])
    ).status_code == 200
    assert api.post(reverse("painpoint-unpublish", args=[dor.pk])).status_code == 200
    assert api.post(reverse("finding-unpublish", args=[fato.pk])).status_code == 200
    assert api.post(reverse("evidence-unpublish", args=[evidencia.pk])).status_code == 200


def test_despublicar_deixa_de_recusar_quando_sobra_outra_sustentacao_publicada(
    api: APIClient, autor: User
) -> None:
    """A recusa é sobre ser a **última**, e não sobre sustentar alguma coisa."""
    conta = AccountFactory()
    uma = _publica(EvidenceFactory(account=conta, reference="Entrevista"), autor)
    outra = _publica(EvidenceFactory(account=conta, reference="Planilha"), autor)
    fato = FindingFactory(
        account=conta, epistemic_status=Finding.EpistemicStatus.FACT, reviewed_by=autor
    )
    fato.evidences.add(uma, outra)
    _publica(fato, autor)

    assert api.post(reverse("evidence-unpublish", args=[uma.pk])).status_code == 200
    assert api.post(reverse("evidence-unpublish", args=[outra.pk])).status_code == 409


def test_despublicar_o_que_nao_esta_publicado_e_409(api: APIClient) -> None:
    achado = FindingFactory(account=AccountFactory())

    resposta = api.post(reverse("finding-unpublish", args=[achado.pk]))

    assert resposta.status_code == 409, resposta.data


# --- 3. A porta do `DELETE` ---------------------------------------------------


def test_arquivar_a_ultima_sustentacao_publicada_e_409_nos_tres_degraus(
    api: APIClient, autor: User
) -> None:
    """Arquivar some da projeção exatamente como despublicar — mesma pergunta, outra porta.

    A guarda da `Evidence` entra **em cima** da que já existia: aquela pergunta se sobra evidência
    viva para o fato, esta se sobra evidência **publicada** para o fato publicado. Um arquivamento
    pode passar na primeira e cair na segunda.
    """
    conta = AccountFactory()
    publicada = _publica(EvidenceFactory(account=conta, reference="Entrevista"), autor)
    interna = EvidenceFactory(account=conta, reference="Rascunho")
    fato = FindingFactory(
        account=conta, epistemic_status=Finding.EpistemicStatus.FACT, reviewed_by=autor
    )
    fato.evidences.add(publicada, interna)
    _publica(fato, autor)
    dor = PainPointFactory(account=conta)
    dor.findings.add(fato)
    _publica(dor, autor)
    oportunidade = ImprovementOpportunityFactory(account=conta)
    oportunidade.pain_points.add(dor)
    _publica(oportunidade, autor)

    # A guarda antiga deixaria passar: sobra a `interna` viva sustentando o fato.
    da_evidencia = api.delete(reverse("evidence-detail", args=[publicada.pk]))
    do_achado = api.delete(reverse("finding-detail", args=[fato.pk]))
    da_dor = api.delete(reverse("painpoint-detail", args=[dor.pk]))

    assert da_evidencia.status_code == 409, da_evidencia.data
    assert do_achado.status_code == 409, do_achado.data
    assert da_dor.status_code == 409, da_dor.data
    publicada.refresh_from_db()
    dor.refresh_from_db()
    assert publicada.archived_at is None
    assert dor.archived_at is None


def test_a_guarda_antiga_do_fato_continua_de_pe_sem_publicacao_nenhuma(
    api: APIClient, autor: User
) -> None:
    """A dimensão nova entrou **em cima** da antiga, e não no lugar dela (FDD 045).

    Nada aqui está publicado: a recusa vem inteira da guarda que já existia, e a mensagem dela é a
    que aparece.
    """
    conta = AccountFactory()
    evidencia = EvidenceFactory(account=conta)
    fato = FindingFactory(
        account=conta, epistemic_status=Finding.EpistemicStatus.FACT, reviewed_by=autor
    )
    fato.evidences.add(evidencia)

    resposta = api.delete(reverse("evidence-detail", args=[evidencia.pk]))

    assert resposta.status_code == 409, resposta.data
    assert "Rebaixe o achado" in str(resposta.data["detail"])


# --- 4. A porta do `PATCH` ----------------------------------------------------


def test_promover_a_fato_um_achado_publicado_sem_evidencia_publicada_e_400(
    api: APIClient, autor: User
) -> None:
    """A porta pela qual a invariante vazaria depois de o achado já ter atravessado.

    Publicar uma hipótese não exige nada — e é certo que não exija. Mas um `PATCH` que a promova a
    fato faria o cliente ler "fato" com evidência interna embaixo, sem passar por `publish/` de
    novo.
    """
    conta = AccountFactory()
    interna = EvidenceFactory(account=conta)
    achado = FindingFactory(account=conta)
    achado.evidences.add(interna)
    _publica(achado, autor)

    resposta = api.patch(
        reverse("finding-detail", args=[achado.pk]),
        {"epistemic_status": Finding.EpistemicStatus.FACT, "reviewed_by": autor.pk},
        format="json",
    )

    assert resposta.status_code == 400, resposta.data
    assert "evidência publicada" in str(resposta.data["evidences"][0])

    # Publicada a evidência, a mesma promoção passa.
    _publica(interna, autor)
    de_novo = api.patch(
        reverse("finding-detail", args=[achado.pk]),
        {"epistemic_status": Finding.EpistemicStatus.FACT, "reviewed_by": autor.pk},
        format="json",
    )
    assert de_novo.status_code == 200, de_novo.data


def test_promover_a_fato_um_achado_interno_nao_exige_evidencia_publicada(
    api: APIClient, autor: User
) -> None:
    """A regra nova vale só para o que o cliente lê. Dentro de casa, a invariante §6.9 basta."""
    conta = AccountFactory()
    achado = FindingFactory(account=conta)
    achado.evidences.add(EvidenceFactory(account=conta))

    resposta = api.patch(
        reverse("finding-detail", args=[achado.pk]),
        {"epistemic_status": Finding.EpistemicStatus.FACT, "reviewed_by": autor.pk},
        format="json",
    )

    assert resposta.status_code == 200, resposta.data


# --- A forma: publicar é ato com autor ----------------------------------------


@pytest.mark.parametrize(
    "fabrica",
    [
        ProcessFactory,
        EvidenceFactory,
        FindingFactory,
        PainPointFactory,
        ImprovementOpportunityFactory,
    ],
    ids=["process", "evidence", "finding", "pain_point", "improvement_opportunity"],
)
def test_published_at_sem_published_by_e_recusado_nos_cinco_modelos(fabrica) -> None:  # type: ignore[no-untyped-def]
    """Sem nome, "alguém revisou" é alegação de ninguém.

    E a metade simétrica também: `published_by` sem `published_at` não registra publicação
    nenhuma — é um autor para um ato que não aconteceu.
    """
    obj = fabrica(account=AccountFactory())

    obj.published_at = timezone.now()
    obj.published_by = None
    with pytest.raises(ValidationError) as sem_autor:
        obj.full_clean()
    assert "published_by" in sem_autor.value.message_dict

    obj.published_at = None
    obj.published_by = UserFactory()
    with pytest.raises(ValidationError) as sem_data:
        obj.full_clean()
    assert "published_at" in sem_data.value.message_dict


def test_a_marca_nao_e_escrita_por_patch(api: APIClient, autor: User) -> None:
    """Os dois campos são só de leitura: quem carimba é a action, que confere a cadeia.

    Um `PATCH` que pudesse publicar contornaria a invariante inteira sem nada ficar vermelho — é a
    razão de `journey.apply_gate` e de `prove-experiments/{id}/start/` serem actions.
    """
    dor = PainPointFactory(account=AccountFactory())

    resposta = api.patch(
        reverse("painpoint-detail", args=[dor.pk]),
        {"published_at": timezone.now().isoformat(), "published_by": autor.pk},
        format="json",
    )

    assert resposta.status_code == 200, resposta.data
    dor.refresh_from_db()
    assert dor.published_at is None
    assert dor.published_by_id is None


def test_nada_nasce_publicado(api: APIClient) -> None:
    """A migração `0075` não fez backfill, e o default dos cinco é o estado seguro.

    O schema não pode decidir retroativamente que uma afirmação sobre a operação de um cliente
    pode ser mostrada a ele.
    """
    conta = AccountFactory()

    assert ProcessFactory(account=conta).published_at is None
    assert EvidenceFactory(account=conta).published_at is None
    assert FindingFactory(account=conta).published_at is None
    assert PainPointFactory(account=conta).published_at is None
    assert ImprovementOpportunityFactory(account=conta).published_at is None
    assert not Process.objects.filter(published_at__isnull=False).exists()
    assert not Evidence.objects.filter(published_at__isnull=False).exists()
    assert not Finding.objects.filter(published_at__isnull=False).exists()
    assert not PainPoint.objects.filter(published_at__isnull=False).exists()
    assert not ImprovementOpportunity.objects.filter(published_at__isnull=False).exists()


# --- 5. A âncora: o AS-IS também tem marca ------------------------------------


def test_o_mapa_do_as_is_so_atravessa_publicado_e_leva_as_etapas_vivas(
    api: APIClient, autor: User
) -> None:
    """A metade de projeção da marca no `Process`, exercida pela action e não pelo campo.

    Não publicado, o mapa não existe para o cliente — e o que fica de fora com ele é a
    caracterização da casa sobre onde o time dele erra, que é o motivo de a marca ter chegado
    até aqui (ADR 0060). Publicado, ele sai com as etapas **vivas** dentro: a etapa não tem marca
    própria e anda com o pai, porque as seis letras do P-S-D-T-E-R são um formulário só.
    """
    projeto = ProjectFactory()
    mapa = ProcessFactory(account=projeto.engagement.account, name="Faturamento")
    ProcessStep.objects.create(process=mapa, name="Conferir pedidos", position=0)
    removida = ProcessStep.objects.create(process=mapa, name="Passo removido", position=1)
    removida.archive()

    assert portal.build_snapshot(projeto)["processes"] == []

    assert api.post(reverse("processo-publish", args=[mapa.pk])).status_code == 200

    blocos = portal.build_snapshot(projeto)["processes"]
    assert [bloco["name"] for bloco in blocos] == ["Faturamento"]
    assert [passo["name"] for passo in blocos[0]["steps"]] == ["Conferir pedidos"]


def test_publicar_o_mapa_nao_exige_nada_e_publicar_duas_vezes_e_409(
    api: APIClient, autor: User
) -> None:
    """Ele é a raiz do próprio ramo: nada pende embaixo dele, então nada há a conferir.

    O 409 do segundo `POST` é o mesmo dos outros quatro — o pedido está bem formado, o que impede
    é o estado.
    """
    mapa = ProcessFactory(account=AccountFactory())

    primeira = api.post(reverse("processo-publish", args=[mapa.pk]))
    segunda = api.post(reverse("processo-publish", args=[mapa.pk]))

    assert primeira.status_code == 200, primeira.data
    assert primeira.data["published_by"] is not None
    assert segunda.status_code == 409, segunda.data


def test_publicar_achado_e_dor_que_citam_um_mapa_nao_publicado_e_400(
    api: APIClient, autor: User
) -> None:
    """Sem esta guarda, `process_id` apontaria para o que não está em `processes[]`.

    É o mesmo defeito que `finding_ids`/`pain_point_ids` filtrados evitam do outro lado da
    referência, e a mensagem lista **o que falta** em vez de mandar adivinhar.
    """
    conta = AccountFactory()
    mapa = ProcessFactory(account=conta)
    achado = FindingFactory(account=conta, process=mapa)
    dor = PainPointFactory(account=conta, process=mapa)
    dor.findings.add(_publica(FindingFactory(account=conta), autor))

    do_achado = api.post(reverse("finding-publish", args=[achado.pk]))
    da_dor = api.post(reverse("painpoint-publish", args=[dor.pk]))

    assert do_achado.status_code == 400, do_achado.data
    assert "processo que ele cita" in str(do_achado.data["detail"])
    assert da_dor.status_code == 400, da_dor.data
    assert "processo que ele cita" in str(da_dor.data["detail"])

    # Publicado o mapa, os dois sobem — a âncora era a única falta.
    _publica(mapa, autor)
    assert api.post(reverse("finding-publish", args=[achado.pk])).status_code == 200
    assert api.post(reverse("painpoint-publish", args=[dor.pk])).status_code == 200


def test_o_achado_ancorado_so_na_etapa_tambem_exige_o_mapa_publicado(
    api: APIClient, autor: User
) -> None:
    """`step_id` atravessa como o `process_id`, e a etapa só sai **dentro** do mapa publicado.

    Olhar só `process` deixaria a referência pendurada pelo outro FK — os dois são `SET_NULL` e
    independentes no schema, e `publication._processos_ancorados` conta os dois justamente para
    `publish/` e `unpublish/` fazerem a mesma pergunta.
    """
    conta = AccountFactory()
    mapa = ProcessFactory(account=conta)
    etapa = ProcessStep.objects.create(process=mapa, name="Conferir pedidos")
    achado = FindingFactory(account=conta, step=etapa)

    recusado = api.post(reverse("finding-publish", args=[achado.pk]))

    assert recusado.status_code == 400, recusado.data
    assert "processo que ele cita" in str(recusado.data["detail"])

    _publica(mapa, autor)
    assert api.post(reverse("finding-publish", args=[achado.pk])).status_code == 200


def test_o_achado_sem_processo_nenhum_publica_sem_ancora(api: APIClient) -> None:
    """A âncora só é exigida de quem cita alguma coisa.

    `Finding.process` é opcional desde a FDD 045 — o achado é da conta, e nem todo levantamento
    começa pelo mapa. Exigir mapa de quem não o tem transformaria a guarda em regra de negócio
    inventada, que é o oposto do que ela existe para fazer.
    """
    achado = FindingFactory(account=AccountFactory())

    assert api.post(reverse("finding-publish", args=[achado.pk])).status_code == 200


def test_tirar_do_ar_o_mapa_que_ancora_algo_publicado_e_409_nas_duas_portas(
    api: APIClient, autor: User
) -> None:
    """Despublicar e arquivar desfazem a mesma coisa, e as duas recusam.

    Sem "ou publique outro" na mensagem: o achado cita **um** mapa, então não há segunda âncora a
    oferecer — a única saída é pelo de cima, e a recusa diz isso em vez de sugerir um caminho que
    não existe. E arquivar é a porta mais perigosa das duas, porque `Process.archive()` cascateia
    para as etapas no mesmo instante: a guarda vem **antes** dele.
    """
    conta = AccountFactory()
    mapa = _publica(ProcessFactory(account=conta), autor)
    etapa = ProcessStep.objects.create(process=mapa, name="Conferir pedidos")
    _publica(FindingFactory(account=conta, process=mapa), autor)
    _publica(PainPointFactory(account=conta, step=etapa), autor)

    despublicar = api.post(reverse("processo-unpublish", args=[mapa.pk]))
    arquivar = api.delete(reverse("processo-detail", args=[mapa.pk]))

    assert despublicar.status_code == 409, despublicar.data
    assert "âncora de 2" in str(despublicar.data["detail"])
    assert arquivar.status_code == 409, arquivar.data
    mapa.refresh_from_db()
    etapa.refresh_from_db()
    assert mapa.published_at is not None
    assert mapa.archived_at is None
    assert etapa.archived_at is None, "a cascata não pode ter rodado antes da recusa"


def test_o_mapa_sai_do_ar_quando_nada_publicado_o_cita(api: APIClient, autor: User) -> None:
    """A recusa é sobre o estado, e não sobre o mapa ser mapa: despublicado o de cima, ele desce.

    O achado **interno** que o cita não impede nada — ele não atravessa, então não há referência
    a pendurar.
    """
    conta = AccountFactory()
    mapa = _publica(ProcessFactory(account=conta), autor)
    achado = _publica(FindingFactory(account=conta, process=mapa), autor)
    FindingFactory(account=conta, process=mapa)

    assert api.post(reverse("processo-unpublish", args=[mapa.pk])).status_code == 409
    assert api.post(reverse("finding-unpublish", args=[achado.pk])).status_code == 200
    assert api.post(reverse("processo-unpublish", args=[mapa.pk])).status_code == 200
    assert api.delete(reverse("processo-detail", args=[mapa.pk])).status_code == 204


# --- 6. A quinta porta: mover a âncora por baixo do publicado -----------------


def test_mover_o_achado_publicado_para_um_mapa_nao_publicado_e_400(
    api: APIClient, autor: User
) -> None:
    """A porta que não passa perto de `published_at`, e por isso nenhuma das quatro a vê.

    Publicar confere a âncora; despublicar e arquivar o mapa recusam a saída dele. Mas o `PATCH`
    que troca `process` num achado **já publicado** não mexe na marca de ninguém — e mesmo assim
    faz `findings[].process_id` apontar para fora de `processes[]`, que é a referência pendurada
    de novo.
    """
    conta = AccountFactory()
    publicado = _publica(ProcessFactory(account=conta), autor)
    rascunho = ProcessFactory(account=conta)
    achado = _publica(FindingFactory(account=conta, process=publicado), autor)

    resposta = api.patch(
        reverse("finding-detail", args=[achado.pk]),
        {"process": rascunho.pk},
        format="json",
    )

    assert resposta.status_code == 400, resposta.data
    assert "publicado e vivo" in str(resposta.data["process"][0])
    achado.refresh_from_db()
    assert achado.process_id == publicado.pk, "a âncora não pode ter se movido"


def test_mover_o_achado_publicado_para_uma_etapa_de_mapa_nao_publicado_e_400(
    api: APIClient, autor: User
) -> None:
    """A citação conta por `step` como conta por `process`: a etapa só sai **dentro** do mapa.

    Olhar só o `process` deixaria a mesma referência pendurada pelo outro FK — os dois são
    `SET_NULL` e independentes, e é por isso que `publication.falta_a_ancora` recebe os dois.
    """
    conta = AccountFactory()
    rascunho = ProcessFactory(account=conta)
    etapa = ProcessStep.objects.create(process=rascunho, name="Conferir pedidos")
    achado = _publica(FindingFactory(account=conta), autor)

    resposta = api.patch(
        reverse("finding-detail", args=[achado.pk]),
        {"step": etapa.pk},
        format="json",
    )

    assert resposta.status_code == 400, resposta.data
    assert "publicado e vivo" in str(resposta.data["step"][0])
    achado.refresh_from_db()
    assert achado.step_id is None


def test_mover_a_dor_publicada_para_um_mapa_nao_publicado_e_400(
    api: APIClient, autor: User
) -> None:
    """A dor emite `process_id`/`step_id` como o achado, então a porta é a mesma nos dois."""
    conta = AccountFactory()
    publicado = _publica(ProcessFactory(account=conta), autor)
    rascunho = ProcessFactory(account=conta)
    dor = PainPointFactory(account=conta, process=publicado)
    dor.findings.add(_publica(FindingFactory(account=conta), autor))
    _publica(dor, autor)

    resposta = api.patch(
        reverse("painpoint-detail", args=[dor.pk]),
        {"process": rascunho.pk},
        format="json",
    )

    assert resposta.status_code == 400, resposta.data
    assert "publicado e vivo" in str(resposta.data["process"][0])
    dor.refresh_from_db()
    assert dor.process_id == publicado.pk


def test_mover_a_ancora_do_publicado_para_outro_mapa_publicado_passa(
    api: APIClient, autor: User
) -> None:
    """A recusa é sobre a âncora atravessar junto, e não sobre a âncora se mexer.

    Corrigir o mapa que o achado cita é edição legítima — o que a guarda impede é o destino que o
    cliente não veria.
    """
    conta = AccountFactory()
    origem = _publica(ProcessFactory(account=conta), autor)
    destino = _publica(ProcessFactory(account=conta), autor)
    achado = _publica(FindingFactory(account=conta, process=origem), autor)

    resposta = api.patch(
        reverse("finding-detail", args=[achado.pk]),
        {"process": destino.pk},
        format="json",
    )

    assert resposta.status_code == 200, resposta.data
    achado.refresh_from_db()
    assert achado.process_id == destino.pk


def test_mover_a_ancora_de_um_achado_interno_nao_exige_nada(api: APIClient) -> None:
    """A regra é só para o que o cliente lê, como a do `PATCH` que promove a `fact`.

    Dentro de casa o levantamento se reorganiza o tempo todo, e nenhum mapa precisa estar
    publicado para o achado apontar para ele.
    """
    conta = AccountFactory()
    rascunho = ProcessFactory(account=conta)
    achado = FindingFactory(account=conta)

    resposta = api.patch(
        reverse("finding-detail", args=[achado.pk]),
        {"process": rascunho.pk},
        format="json",
    )

    assert resposta.status_code == 200, resposta.data
    achado.refresh_from_db()
    assert achado.process_id == rascunho.pk
