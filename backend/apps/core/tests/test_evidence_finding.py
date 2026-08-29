"""O split Evidence/Finding e o Discovery (FDD 045, ADR 0049).

A `Evidencia` da FDD 039 guarda três coisas numa linha só — a forma da fonte, a afirmação já
interpretada e o rótulo epistemológico —, e é por isso que a hipótese e o trecho que a sustenta
são o mesmo registro. O que se exercita aqui é o que a separação passa a permitir dizer:

- **um fato tem embaixo dele uma evidência viva e um revisor com nome** (invariante §6.9 do
  language map). As duas metades são cobradas, e nas duas pontas: a criação e a promoção;
- **arquivar a última evidência de um fato é recusado**, e não silenciosamente aceito — o achado
  ficaria de pé afirmando algo sobre a operação do cliente sem nada por baixo;
- **transição inválida é 400**, lendo `FINDING_TRANSITIONS` como o artefato lê o dele;
- **a fronteira da conta vale nas duas metades**, como em `test_processos.py`;
- **o mesmo processo cabe em dois Discoveries**, que é a proveniência única que a
  `ProcessObservation` desfaz;
- **`content_hash` acompanha o trecho**, que é o que faz "este fato ainda se apoia no mesmo texto?"
  ter resposta.
"""

from datetime import timedelta

import pytest
from django.core.exceptions import ValidationError
from django.urls import reverse
from django.utils import timezone
from rest_framework.test import APIClient

from apps.core.models import Discovery, Evidence, Finding, ProcessObservation, User, hash_do_trecho

from .factories import (
    AccountFactory,
    DiscoveryFactory,
    DiscoverySessionFactory,
    EvidenceFactory,
    FindingFactory,
    MeetingFactory,
    ProcessFactory,
    ProcessObservationFactory,
    ProcessStepFactory,
    ProjectFactory,
    ProjectMemberFactory,
    UserFactory,
)

pytestmark = pytest.mark.django_db


@pytest.fixture
def api() -> APIClient:
    client = APIClient()
    client.force_authenticate(UserFactory(role=User.Role.ADMIN))
    return client


def _payload_finding(account_id: int, **overrides: object) -> dict:
    base: dict = {
        "account": account_id,
        "statement": "O fechamento leva dois dias.",
        "epistemic_status": Finding.EpistemicStatus.HYPOTHESIS,
    }
    base.update(overrides)
    return base


# --- A invariante §6.9: fato exige evidência viva e revisor -----------------------------------


def test_fato_sem_revisor_e_recusado(api: APIClient) -> None:
    conta = AccountFactory()
    evidencia = EvidenceFactory(account=conta)

    resposta = api.post(
        reverse("finding-list"),
        _payload_finding(
            conta.pk,
            epistemic_status=Finding.EpistemicStatus.FACT,
            evidences=[evidencia.pk],
        ),
        format="json",
    )

    assert resposta.status_code == 400, resposta.data
    assert "reviewed_by" in resposta.data


def test_fato_com_revisor_e_sem_evidencia_viva_e_recusado(api: APIClient) -> None:
    """A metade que o `clean()` não alcança: o M2M só existe depois do save."""
    conta = AccountFactory()
    revisor = UserFactory()
    arquivada = EvidenceFactory(account=conta)
    arquivada.archive()

    sem_nenhuma = api.post(
        reverse("finding-list"),
        _payload_finding(
            conta.pk, epistemic_status=Finding.EpistemicStatus.FACT, reviewed_by=revisor.pk
        ),
        format="json",
    )
    so_arquivada = api.post(
        reverse("finding-list"),
        _payload_finding(
            conta.pk,
            epistemic_status=Finding.EpistemicStatus.FACT,
            reviewed_by=revisor.pk,
            evidences=[arquivada.pk],
        ),
        format="json",
    )

    assert sem_nenhuma.status_code == 400, sem_nenhuma.data
    assert so_arquivada.status_code == 400, so_arquivada.data
    assert "evidences" in so_arquivada.data


def test_fato_com_revisor_e_evidencia_viva_passa_e_carimba_a_data(api: APIClient) -> None:
    conta = AccountFactory()
    revisor = UserFactory()
    evidencia = EvidenceFactory(account=conta)

    resposta = api.post(
        reverse("finding-list"),
        _payload_finding(
            conta.pk,
            epistemic_status=Finding.EpistemicStatus.FACT,
            reviewed_by=revisor.pk,
            evidences=[evidencia.pk],
        ),
        format="json",
    )

    assert resposta.status_code == 201, resposta.data
    achado = Finding.objects.get(pk=resposta.data["id"])
    assert achado.reviewed_by == revisor
    # O carimbo sai do estado, e não do corpo — quem promove não escolhe a data da promoção.
    assert achado.reviewed_at is not None


def test_promover_pelo_patch_cobra_as_duas_metades(api: APIClient) -> None:
    conta = AccountFactory()
    achado = FindingFactory(account=conta)
    evidencia = EvidenceFactory(account=conta)
    achado.evidences.add(evidencia)

    sem_revisor = api.patch(
        reverse("finding-detail", args=[achado.pk]),
        {"epistemic_status": Finding.EpistemicStatus.FACT},
        format="json",
    )
    com_revisor = api.patch(
        reverse("finding-detail", args=[achado.pk]),
        {
            "epistemic_status": Finding.EpistemicStatus.FACT,
            "reviewed_by": UserFactory().pk,
        },
        format="json",
    )

    assert sem_revisor.status_code == 400, sem_revisor.data
    assert com_revisor.status_code == 200, com_revisor.data


def test_o_modelo_tambem_recusa_fato_sem_revisor() -> None:
    """A guarda do modelo, para quem entra pelo admin ou pelo shell."""
    achado = FindingFactory(epistemic_status=Finding.EpistemicStatus.HYPOTHESIS)
    achado.epistemic_status = Finding.EpistemicStatus.FACT

    with pytest.raises(ValidationError) as erro:
        achado.full_clean()

    assert "reviewed_by" in erro.value.message_dict


# --- Arquivar a última evidência de um fato ---------------------------------------------------


def test_arquivar_a_ultima_evidencia_de_um_fato_e_recusado(api: APIClient) -> None:
    """409, e não um rebaixamento silencioso: desfazer promoção de gente é ato de gente."""
    conta = AccountFactory()
    evidencia = EvidenceFactory(account=conta)
    achado = FindingFactory(
        account=conta,
        epistemic_status=Finding.EpistemicStatus.FACT,
        reviewed_by=UserFactory(),
    )
    achado.evidences.add(evidencia)

    resposta = api.delete(reverse("evidence-detail", args=[evidencia.pk]))

    assert resposta.status_code == 409, resposta.data
    evidencia.refresh_from_db()
    assert evidencia.archived_at is None
    achado.refresh_from_db()
    assert achado.epistemic_status == Finding.EpistemicStatus.FACT


def test_arquivar_a_penultima_evidencia_de_um_fato_passa(api: APIClient) -> None:
    conta = AccountFactory()
    primeira = EvidenceFactory(account=conta)
    segunda = EvidenceFactory(account=conta, kind=Evidence.Kind.DATA)
    achado = FindingFactory(
        account=conta,
        epistemic_status=Finding.EpistemicStatus.FACT,
        reviewed_by=UserFactory(),
    )
    achado.evidences.add(primeira, segunda)

    resposta = api.delete(reverse("evidence-detail", args=[primeira.pk]))

    assert resposta.status_code == 204
    primeira.refresh_from_db()
    assert primeira.archived_at is not None


def test_arquivar_a_unica_evidencia_de_uma_hipotese_passa(api: APIClient) -> None:
    """A recusa é sobre o **fato**: hipótese sem evidência continua sendo uma hipótese honesta."""
    conta = AccountFactory()
    evidencia = EvidenceFactory(account=conta)
    FindingFactory(account=conta).evidences.add(evidencia)

    resposta = api.delete(reverse("evidence-detail", args=[evidencia.pk]))

    assert resposta.status_code == 204


def test_arquivar_evidencia_de_fato_ja_arquivado_passa(api: APIClient) -> None:
    """Achado arquivado não afirma mais nada — segurar a evidência dele seria segurar por nada."""
    conta = AccountFactory()
    evidencia = EvidenceFactory(account=conta)
    achado = FindingFactory(
        account=conta,
        epistemic_status=Finding.EpistemicStatus.FACT,
        reviewed_by=UserFactory(),
    )
    achado.evidences.add(evidencia)
    achado.archive()

    resposta = api.delete(reverse("evidence-detail", args=[evidencia.pk]))

    assert resposta.status_code == 204


# --- Transições ------------------------------------------------------------------------------


def test_de_fato_nao_se_vai_direto_a_desconhecido(api: APIClient) -> None:
    """`FINDING_TRANSITIONS`: rebaixar para hipótese, sim; apagar o erro, não."""
    conta = AccountFactory()
    achado = FindingFactory(
        account=conta,
        epistemic_status=Finding.EpistemicStatus.FACT,
        reviewed_by=UserFactory(),
    )
    achado.evidences.add(EvidenceFactory(account=conta))

    invalida = api.patch(
        reverse("finding-detail", args=[achado.pk]),
        {"epistemic_status": Finding.EpistemicStatus.UNKNOWN},
        format="json",
    )
    valida = api.patch(
        reverse("finding-detail", args=[achado.pk]),
        {"epistemic_status": Finding.EpistemicStatus.HYPOTHESIS},
        format="json",
    )

    assert invalida.status_code == 400, invalida.data
    assert valida.status_code == 200, valida.data


def test_de_desconhecido_se_vai_aos_dois_lados(api: APIClient) -> None:
    achado = FindingFactory(epistemic_status=Finding.EpistemicStatus.UNKNOWN)

    resposta = api.patch(
        reverse("finding-detail", args=[achado.pk]),
        {"epistemic_status": Finding.EpistemicStatus.HYPOTHESIS},
        format="json",
    )

    assert resposta.status_code == 200, resposta.data


# --- Evidence: o que ela exige e o que ela carimba --------------------------------------------


def test_evidencia_sem_trecho_e_sem_localizador_e_recusada(api: APIClient) -> None:
    conta = AccountFactory()

    resposta = api.post(
        reverse("evidence-list"),
        {"account": conta.pk, "kind": Evidence.Kind.INTERVIEW},
        format="json",
    )

    assert resposta.status_code == 400, resposta.data


def test_so_o_localizador_basta(api: APIClient) -> None:
    """A gravação de duas horas é evidência mesmo antes de alguém transcrever o trecho."""
    conta = AccountFactory()

    resposta = api.post(
        reverse("evidence-list"),
        {
            "account": conta.pk,
            "kind": Evidence.Kind.SYSTEM,
            "reference": "https://exemplo.test/gravacao/42#00:14:32",
        },
        format="json",
    )

    assert resposta.status_code == 201, resposta.data
    assert Evidence.objects.get(pk=resposta.data["id"]).content_hash == ""


def test_o_hash_muda_quando_o_trecho_muda(api: APIClient) -> None:
    evidencia = EvidenceFactory(raw_excerpt="São quatrocentas notas por mês.")
    antes = evidencia.content_hash
    assert antes == hash_do_trecho("São quatrocentas notas por mês.")

    resposta = api.patch(
        reverse("evidence-detail", args=[evidencia.pk]),
        {"raw_excerpt": "São quatro mil notas por mês."},
        format="json",
    )

    assert resposta.status_code == 200, resposta.data
    evidencia.refresh_from_db()
    assert evidencia.content_hash != antes
    assert evidencia.content_hash == hash_do_trecho("São quatro mil notas por mês.")


def test_a_etapa_da_evidencia_precisa_ser_do_mesmo_processo(api: APIClient) -> None:
    conta = AccountFactory()
    processo = ProcessFactory(account=conta)
    outra_etapa = ProcessStepFactory(process=ProcessFactory(account=conta))

    resposta = api.post(
        reverse("evidence-list"),
        {
            "account": conta.pk,
            "process": processo.pk,
            "step": outra_etapa.pk,
            "kind": Evidence.Kind.OBSERVATION,
            "raw_excerpt": "Vi a conferência nota a nota.",
        },
        format="json",
    )

    assert resposta.status_code == 400, resposta.data
    assert "step" in resposta.data


def test_o_processo_da_evidencia_precisa_ser_da_mesma_conta(api: APIClient) -> None:
    """A fronteira de conta por campo opcional, que é a pior forma de vazar."""
    resposta = api.post(
        reverse("evidence-list"),
        {
            "account": AccountFactory().pk,
            "process": ProcessFactory(account=AccountFactory()).pk,
            "kind": Evidence.Kind.OBSERVATION,
            "raw_excerpt": "Vi a conferência nota a nota.",
        },
        format="json",
    )

    assert resposta.status_code == 400, resposta.data
    assert "process" in resposta.data


def test_o_modelo_tambem_recusa_evidencia_sem_conteudo() -> None:
    conta = AccountFactory()

    with pytest.raises(ValidationError):
        Evidence(account=conta, kind=Evidence.Kind.INTERVIEW).full_clean()


def test_o_discovery_da_evidencia_precisa_ser_da_mesma_conta(api: APIClient) -> None:
    """A terceira ponta da mesma fronteira: dois vínculos cobrados e um solto seria assimetria."""
    resposta = api.post(
        reverse("evidence-list"),
        {
            "account": AccountFactory().pk,
            "discovery": DiscoveryFactory(project=ProjectFactory(client=AccountFactory())).pk,
            "kind": Evidence.Kind.INTERVIEW,
            "raw_excerpt": "Disseram que leva dois dias.",
        },
        format="json",
    )

    assert resposta.status_code == 400, resposta.data
    assert "discovery" in resposta.data


def test_o_discovery_da_propria_conta_passa(api: APIClient) -> None:
    """Controle positivo, sem o qual o teste acima passaria por recusar todo Discovery."""
    conta = AccountFactory()

    resposta = api.post(
        reverse("evidence-list"),
        {
            "account": conta.pk,
            "discovery": DiscoveryFactory(project=ProjectFactory(client=conta)).pk,
            "kind": Evidence.Kind.INTERVIEW,
            "raw_excerpt": "Disseram que leva dois dias.",
        },
        format="json",
    )

    assert resposta.status_code == 201, resposta.data


def test_a_sessao_da_evidencia_precisa_ser_do_mesmo_discovery(api: APIClient) -> None:
    """Tendo os dois, eles precisam concordar — proveniência que se contradiz não é proveniência."""
    conta = AccountFactory()
    discovery = DiscoveryFactory(project=ProjectFactory(client=conta))

    resposta = api.post(
        reverse("evidence-list"),
        {
            "account": conta.pk,
            "discovery": discovery.pk,
            "source_session": DiscoverySessionFactory().pk,
            "kind": Evidence.Kind.INTERVIEW,
            "raw_excerpt": "Disseram que leva dois dias.",
        },
        format="json",
    )

    assert resposta.status_code == 400, resposta.data
    assert "source_session" in resposta.data


def test_a_sessao_do_proprio_discovery_passa(api: APIClient) -> None:
    conta = AccountFactory()
    discovery = DiscoveryFactory(project=ProjectFactory(client=conta))

    resposta = api.post(
        reverse("evidence-list"),
        {
            "account": conta.pk,
            "discovery": discovery.pk,
            "source_session": DiscoverySessionFactory(discovery=discovery).pk,
            "kind": Evidence.Kind.INTERVIEW,
            "raw_excerpt": "Disseram que leva dois dias.",
        },
        format="json",
    )

    assert resposta.status_code == 201, resposta.data


def test_o_modelo_tambem_recusa_discovery_e_sessao_incoerentes() -> None:
    """As duas guardas do lado do modelo, para quem entra pelo admin ou pelo shell."""
    conta = AccountFactory()
    de_outra_conta = DiscoveryFactory(project=ProjectFactory(client=AccountFactory()))
    evidencia = EvidenceFactory(account=conta)

    evidencia.discovery = de_outra_conta
    with pytest.raises(ValidationError) as conta_errada:
        evidencia.full_clean()

    proprio = DiscoveryFactory(project=ProjectFactory(client=conta))
    evidencia.discovery = proprio
    evidencia.source_session = DiscoverySessionFactory()
    with pytest.raises(ValidationError) as sessao_errada:
        evidencia.full_clean()

    assert "discovery" in conta_errada.value.message_dict
    assert "source_session" in sessao_errada.value.message_dict


# --- Discovery e as suas datas ----------------------------------------------------------------


def test_discovery_concluido_exige_data_de_conclusao(api: APIClient) -> None:
    projeto = ProjectFactory()

    resposta = api.post(
        reverse("discovery-list"),
        {"project": projeto.pk, "status": Discovery.Status.COMPLETED},
        format="json",
    )

    assert resposta.status_code == 400, resposta.data
    assert "completed_at" in resposta.data


def test_discovery_nao_termina_antes_de_comecar(api: APIClient) -> None:
    projeto = ProjectFactory()
    hoje = timezone.localdate()

    resposta = api.post(
        reverse("discovery-list"),
        {
            "project": projeto.pk,
            "started_at": hoje.isoformat(),
            "completed_at": (hoje - timedelta(days=1)).isoformat(),
        },
        format="json",
    )

    assert resposta.status_code == 400, resposta.data


def test_o_modelo_tambem_recusa_as_duas_datas_invertidas() -> None:
    hoje = timezone.localdate()
    discovery = DiscoveryFactory(started_at=hoje)
    discovery.completed_at = hoje - timedelta(days=1)

    with pytest.raises(ValidationError):
        discovery.full_clean()


def test_a_sessao_precisa_ser_do_projeto_do_discovery(api: APIClient) -> None:
    discovery = DiscoveryFactory()
    reuniao_alheia = MeetingFactory()

    resposta = api.post(
        reverse("discoverysession-list"),
        {
            "discovery": discovery.pk,
            "meeting": reuniao_alheia.pk,
            "happened_at": timezone.now().isoformat(),
        },
        format="json",
    )

    assert resposta.status_code == 400, resposta.data
    assert "meeting" in resposta.data


def test_a_sessao_da_propria_reuniao_passa(api: APIClient) -> None:
    discovery = DiscoveryFactory()
    reuniao = MeetingFactory(project=discovery.project)

    resposta = api.post(
        reverse("discoverysession-list"),
        {
            "discovery": discovery.pk,
            "meeting": reuniao.pk,
            "happened_at": timezone.now().isoformat(),
        },
        format="json",
    )

    assert resposta.status_code == 201, resposta.data


# --- ProcessObservation: a proveniência que deixa de ser única --------------------------------


def test_o_mesmo_processo_cabe_em_dois_discoveries(api: APIClient) -> None:
    """O defeito que esta tabela desfaz: `Process.source_project` responde por **uma** origem."""
    conta = AccountFactory()
    processo = ProcessFactory(account=conta)
    primeiro = DiscoveryFactory(project=ProjectFactory(client=conta))
    segundo = DiscoveryFactory(project=ProjectFactory(client=conta))

    for discovery, tipo in (
        (primeiro, ProcessObservation.Kind.INITIAL),
        (segundo, ProcessObservation.Kind.REVISIT),
    ):
        resposta = api.post(
            reverse("processobservation-list"),
            {
                "discovery": discovery.pk,
                "process": processo.pk,
                "observed_at": timezone.localdate().isoformat(),
                "observation_type": tipo,
            },
            format="json",
        )
        assert resposta.status_code == 201, resposta.data

    assert processo.observations.count() == 2
    assert set(processo.observations.values_list("observation_type", flat=True)) == {
        ProcessObservation.Kind.INITIAL,
        ProcessObservation.Kind.REVISIT,
    }


def test_a_sessao_da_observacao_precisa_ser_do_mesmo_discovery(api: APIClient) -> None:
    discovery = DiscoveryFactory()
    sessao_alheia = DiscoverySessionFactory()

    resposta = api.post(
        reverse("processobservation-list"),
        {
            "discovery": discovery.pk,
            "process": ProcessFactory().pk,
            "observed_at": timezone.localdate().isoformat(),
            "source_session": sessao_alheia.pk,
        },
        format="json",
    )

    assert resposta.status_code == 400, resposta.data
    assert "source_session" in resposta.data


def test_o_modelo_tambem_recusa_sessao_de_outro_discovery() -> None:
    observacao = ProcessObservationFactory()
    observacao.source_session = DiscoverySessionFactory()

    with pytest.raises(ValidationError):
        observacao.full_clean()


# --- A fronteira: entrega fora do projeto ------------------------------------------------------


def test_entrega_nao_ve_discovery_evidence_nem_finding_de_outra_conta() -> None:
    """Espelha `test_processo_nao_volta_ao_cliente.py`: a listagem recorta pela participação."""
    minha = AccountFactory()
    alheia = AccountFactory()
    entrega = UserFactory(role=User.Role.DELIVERY)
    meu_projeto = ProjectFactory(client=minha)
    ProjectMemberFactory(project=meu_projeto, user=entrega)

    DiscoveryFactory(project=meu_projeto)
    DiscoveryFactory(project=ProjectFactory(client=alheia))
    EvidenceFactory(account=minha)
    EvidenceFactory(account=alheia)
    FindingFactory(account=minha)
    FindingFactory(account=alheia)

    api = APIClient()
    api.force_authenticate(entrega)

    for rota in ("discovery-list", "evidence-list", "finding-list"):
        resposta = api.get(reverse(rota))
        assert resposta.status_code == 200, (rota, resposta.data)
        assert len(resposta.data) == 1, (rota, resposta.data)


def test_entrega_nao_escreve_evidencia_em_conta_alheia() -> None:
    """Sem a guarda de escrita, uma requisição bastaria para escrever dentro do cliente oculto."""
    alheia = AccountFactory()
    entrega = UserFactory(role=User.Role.DELIVERY)
    ProjectMemberFactory(project=ProjectFactory(), user=entrega)
    api = APIClient()
    api.force_authenticate(entrega)

    resposta = api.post(
        reverse("evidence-list"),
        {
            "account": alheia.pk,
            "kind": Evidence.Kind.INTERVIEW,
            "raw_excerpt": "Disseram que leva dois dias.",
        },
        format="json",
    )

    assert resposta.status_code == 403, resposta.data
    assert not Evidence.objects.filter(account=alheia).exists()


def test_entrega_nao_escreve_achado_em_conta_alheia() -> None:
    alheia = AccountFactory()
    entrega = UserFactory(role=User.Role.DELIVERY)
    ProjectMemberFactory(project=ProjectFactory(), user=entrega)
    api = APIClient()
    api.force_authenticate(entrega)

    resposta = api.post(reverse("finding-list"), _payload_finding(alheia.pk), format="json")

    assert resposta.status_code == 403, resposta.data


def test_entrega_nao_pendura_processo_alheio_no_proprio_discovery() -> None:
    """A segunda fronteira da observação: o Discovery é meu, o processo é de outra conta."""
    entrega = UserFactory(role=User.Role.DELIVERY)
    meu_projeto = ProjectFactory()
    ProjectMemberFactory(project=meu_projeto, user=entrega)
    discovery = DiscoveryFactory(project=meu_projeto)
    api = APIClient()
    api.force_authenticate(entrega)

    resposta = api.post(
        reverse("processobservation-list"),
        {
            "discovery": discovery.pk,
            "process": ProcessFactory(account=AccountFactory()).pk,
            "observed_at": timezone.localdate().isoformat(),
        },
        format="json",
    )

    assert resposta.status_code == 403, resposta.data
    assert not ProcessObservation.objects.exists()


def test_entrega_nao_cria_discovery_em_projeto_alheio() -> None:
    entrega = UserFactory(role=User.Role.DELIVERY)
    ProjectMemberFactory(project=ProjectFactory(), user=entrega)
    api = APIClient()
    api.force_authenticate(entrega)

    resposta = api.post(
        reverse("discovery-list"), {"project": ProjectFactory().pk}, format="json"
    )

    assert resposta.status_code == 403, resposta.data


# --- Arquivar e restaurar, o básico da FDD 025 -------------------------------------------------


def test_o_achado_arquivado_sai_da_lista_e_volta_pelo_unarchive(api: APIClient) -> None:
    achado = FindingFactory()

    assert api.delete(reverse("finding-detail", args=[achado.pk])).status_code == 204
    assert api.get(reverse("finding-list")).data == []
    assert len(api.get(f"{reverse('finding-list')}?archived=1").data) == 1
    assert api.post(reverse("finding-unarchive", args=[achado.pk])).status_code == 200
    assert len(api.get(reverse("finding-list")).data) == 1


def test_a_lista_de_evidencias_filtra_por_conta_e_por_forma(api: APIClient) -> None:
    conta = AccountFactory()
    EvidenceFactory(account=conta, kind=Evidence.Kind.INTERVIEW)
    EvidenceFactory(account=conta, kind=Evidence.Kind.DATA)
    EvidenceFactory(account=AccountFactory())

    por_conta = api.get(f"{reverse('evidence-list')}?account={conta.pk}")
    por_forma = api.get(f"{reverse('evidence-list')}?account={conta.pk}&kind=data")

    assert len(por_conta.data) == 2
    assert len(por_forma.data) == 1
