"""Regressão: o backfill do split traduz tudo o que já foi levantado, e não apaga nada (FDD 045).

A migração `0054` é o que impede o modelo novo de nascer vazio. Sem ela, `Evidence` e `Finding`
começariam do zero no dia do deploy e todo Discovery já feito ficaria só do lado antigo — o que na
prática é jogar fora o levantamento de todos os clientes e pedir para refazer.

Ela roda uma vez em produção, então o teste roda **a função da migração** sobre dados reais, no
molde de `test_project_member_backfill.py`, e não uma simulação do que ela faria.

Três coisas são afirmadas porque as três podem regredir sem sintoma visível:

- **a tradução dos dois vocabulários** (`forma` → `kind`, `rotulo` → `epistemic_status`). Um mapa
  errado não derruba nada: produz um Discovery inteiro dizendo "entrevista" onde alguém observou;
- **o legado intacto**, porque o dual-write depende dele — apagar a `Evidencia` "já migrada"
  derrubaria o custo do estado atual e a tela no mesmo commit;
- **as arquivadas vindo junto, com o carimbo**, senão desarquivar do lado antigo passaria a
  produzir um registro sem contraparte no novo.
"""

import importlib

import pytest
from django.apps import apps as django_apps
from django.utils import timezone

from apps.core.models import Evidence, Evidencia, Finding, hash_do_trecho
from apps.core.tests.factories import (
    ClientFactory,
    EvidenciaFactory,
    ProcessoEtapaFactory,
    ProcessoFactory,
    UserFactory,
)

pytestmark = pytest.mark.django_db

MIGRACAO = importlib.import_module("apps.core.migrations.0054_backfill_evidence_finding")


def _backfill() -> None:
    MIGRACAO.split_evidencias(django_apps, None)


def test_cada_evidencia_vira_um_par_ligado() -> None:
    processo = ProcessoFactory(client=ClientFactory())
    etapa = ProcessoEtapaFactory(processo=processo)
    legada = EvidenciaFactory(
        processo=processo, etapa=etapa, content="Disseram que leva dois dias.",
        registered_by=UserFactory(),
    )

    _backfill()

    evidencia = Evidence.objects.get(legacy_evidencia=legada)
    achado = Finding.objects.get(legacy_evidencia=legada)
    assert evidencia.account_id == processo.client_id
    assert evidencia.process_id == processo.pk
    assert evidencia.step_id == etapa.pk
    assert evidencia.raw_excerpt == legada.content
    assert evidencia.content_hash == hash_do_trecho(legada.content)
    assert evidencia.captured_by_id == legada.registered_by_id
    assert evidencia.captured_at == legada.created_at
    assert achado.statement == legada.content
    assert list(achado.evidences.all()) == [evidencia]


@pytest.mark.parametrize(
    ("forma", "kind"),
    [
        (Evidencia.Forma.ENTREVISTA, Evidence.Kind.INTERVIEW),
        (Evidencia.Forma.OBSERVACAO, Evidence.Kind.OBSERVATION),
        (Evidencia.Forma.ARTEFATO, Evidence.Kind.ARTIFACT),
        (Evidencia.Forma.SISTEMA, Evidence.Kind.SYSTEM),
        (Evidencia.Forma.DADO, Evidence.Kind.DATA),
    ],
)
def test_as_cinco_formas_traduzem_uma_a_uma(forma: str, kind: str) -> None:
    legada = EvidenciaFactory(forma=forma)

    _backfill()

    assert Evidence.objects.get(legacy_evidencia=legada).kind == kind


@pytest.mark.parametrize(
    ("rotulo", "status"),
    [
        (Evidencia.Rotulo.FATO, Finding.EpistemicStatus.FACT),
        (Evidencia.Rotulo.HIPOTESE, Finding.EpistemicStatus.HYPOTHESIS),
        (Evidencia.Rotulo.DESCONHECIDO, Finding.EpistemicStatus.UNKNOWN),
    ],
)
def test_os_tres_rotulos_traduzem_um_a_um(rotulo: str, status: str) -> None:
    legada = EvidenciaFactory(rotulo=rotulo)

    _backfill()

    assert Finding.objects.get(legacy_evidencia=legada).epistemic_status == status


def test_o_fato_migrado_carrega_a_aproximacao_de_revisao() -> None:
    """Aproximação declarada: o modelo antigo não registrava revisão, e o fato já foi promovido."""
    quem = UserFactory()
    legada = EvidenciaFactory(rotulo=Evidencia.Rotulo.FATO, registered_by=quem)

    _backfill()

    achado = Finding.objects.get(legacy_evidencia=legada)
    assert achado.reviewed_by_id == quem.pk
    assert achado.reviewed_at == legada.updated_at


def test_a_hipotese_migrada_nao_ganha_revisor() -> None:
    """A metade complementar: sem ela o teste acima passaria carimbando revisor em tudo."""
    legada = EvidenciaFactory(rotulo=Evidencia.Rotulo.HIPOTESE, registered_by=UserFactory())

    _backfill()

    achado = Finding.objects.get(legacy_evidencia=legada)
    assert achado.reviewed_by_id is None
    assert achado.reviewed_at is None


def test_a_arquivada_vem_junto_com_o_carimbo_preservado() -> None:
    legada = EvidenciaFactory()
    legada.archive()
    legada.refresh_from_db()

    _backfill()

    assert Evidence.objects.get(legacy_evidencia=legada).archived_at == legada.archived_at
    assert Finding.objects.get(legacy_evidencia=legada).archived_at == legada.archived_at


def test_nada_do_legado_e_apagado_ou_alterado() -> None:
    """O dual-write depende do legado: apagar a linha "já migrada" derrubaria o custo e a tela."""
    legada = EvidenciaFactory()
    antes = (legada.content, legada.forma, legada.rotulo, legada.archived_at)

    _backfill()

    legada.refresh_from_db()
    assert Evidencia.objects.count() == 1
    assert (legada.content, legada.forma, legada.rotulo, legada.archived_at) == antes


def test_o_backfill_e_idempotente() -> None:
    legada = EvidenciaFactory()

    _backfill()
    _backfill()

    assert Evidence.objects.filter(legacy_evidencia=legada).count() == 1
    assert Finding.objects.filter(legacy_evidencia=legada).count() == 1


def test_a_reversa_apaga_so_o_que_veio_do_backfill() -> None:
    legada = EvidenciaFactory()
    _backfill()
    nascido_depois = Finding.objects.create(
        account=legada.processo.client, statement="Achado registrado na tela."
    )
    evidencia_nova = Evidence.objects.create(
        account=legada.processo.client, kind=Evidence.Kind.DATA,
        raw_excerpt="400 notas no relatório de outubro.", captured_at=timezone.now(),
    )

    MIGRACAO.desfaz_split(django_apps, None)

    assert not Evidence.objects.filter(legacy_evidencia__isnull=False).exists()
    assert not Finding.objects.filter(legacy_evidencia__isnull=False).exists()
    assert Finding.objects.filter(pk=nascido_depois.pk).exists()
    assert Evidence.objects.filter(pk=evidencia_nova.pk).exists()
    assert Evidencia.objects.filter(pk=legada.pk).exists()
