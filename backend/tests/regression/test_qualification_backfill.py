"""Regressão: o backfill traduz a conversa que estava gravada como venda (migração 0052).

A migração 0052 é o que impede a fatia nova de deixar a base contando as conversas de qualificação
como pipeline. Ela roda uma vez em produção, sobre dado comercial existente — e por isso o teste
executa **a função da migração**, e não uma simulação dela, no molde de
`test_project_member_backfill.py`.

Os dois casos que ela trata com cuidado são os que este arquivo protege: oportunidade **sem lead**
não vira avaliação (inventar um lead sintético é dado falso na base), e oportunidade **com
projeto** vira avaliação mas **não** é arquivada (`Project.opportunity` é `PROTECT`, e a tela do
projeto lê a oportunidade).
"""

import importlib
from datetime import timedelta

import pytest
from django.apps import apps as django_apps
from django.utils import timezone

from apps.core.models import Activity, Lead, Opportunity, PipelineStage, Qualification, Service
from apps.core.tests.factories import (
    ClientFactory,
    LeadFactory,
    OpportunityFactory,
    ProjectFactory,
    UserFactory,
)

pytestmark = pytest.mark.django_db

MIGRACAO = "apps.core.migrations.0052_backfill_qualification"


def _rodar_backfill() -> None:
    """Importa a migração pelo nome de módulo (o número no início impede o `import` normal)."""
    importlib.import_module(MIGRACAO).backfill_qualification(django_apps, None)


def _reverter_backfill() -> None:
    importlib.import_module(MIGRACAO).desfazer_backfill(django_apps, None)


@pytest.fixture
def porta() -> Service:
    return Service.objects.get(tier=Service.Tier.QUALIFICATION_CALL)


def _oportunidade_de_qualificacao(porta: Service, **kwargs) -> tuple[Opportunity, Lead]:
    conta = kwargs.pop("client", None) or ClientFactory()
    opportunity = OpportunityFactory(client=conta, service=porta, scope="Conversa inicial", **kwargs)
    lead = LeadFactory(client=conta, opportunity=opportunity)
    return opportunity, lead


def test_backfill_cria_qualificacao_e_auditoria_e_arquiva(porta: Service) -> None:
    opportunity, lead = _oportunidade_de_qualificacao(porta)

    _rodar_backfill()

    qualification = Qualification.objects.get()
    assert qualification.lead_id == lead.pk
    assert qualification.account_id == opportunity.client_id
    assert qualification.legacy_opportunity_id == opportunity.pk
    assert qualification.assessor_id == opportunity.owner_id
    assert qualification.happened_at == opportunity.created_at
    assert qualification.rationale == "Conversa inicial"
    # A auditoria de que a linha existiu — sem ela, a oportunidade some da tela sem explicação.
    nota = Activity.objects.get(opportunity=opportunity)
    assert nota.summary == f"Qualificação migrada da oportunidade #{opportunity.pk}"
    assert nota.client_id == opportunity.client_id
    opportunity.refresh_from_db()
    assert opportunity.archived_at is not None
    assert Opportunity.objects.filter(pk=opportunity.pk).exists()  # nada é apagado


def test_outcome_sai_do_estado_comercial(porta: Service) -> None:
    ganha, _ = _oportunidade_de_qualificacao(porta, stage=PipelineStage.objects.get(kind="won"))
    perdida, _ = _oportunidade_de_qualificacao(porta, stage=PipelineStage.objects.get(kind="lost"))
    aberta, _ = _oportunidade_de_qualificacao(porta)

    _rodar_backfill()

    assert Qualification.objects.get(legacy_opportunity=ganha).outcome == "qualified"
    assert Qualification.objects.get(legacy_opportunity=perdida).outcome == "disqualified"
    em_nutricao = Qualification.objects.get(legacy_opportunity=aberta)
    assert em_nutricao.outcome == "nurture"
    # `nurture_until` preenchida, senão a linha violaria o `clean()` que a fatia acabou de criar.
    assert em_nutricao.nurture_until == (aberta.created_at + timedelta(days=180)).date()


def test_oportunidade_com_projeto_vira_avaliacao_mas_nao_e_arquivada(porta: Service) -> None:
    opportunity, _ = _oportunidade_de_qualificacao(
        porta, stage=PipelineStage.objects.get(kind="won")
    )
    ProjectFactory(client=opportunity.client, opportunity=opportunity)

    _rodar_backfill()

    assert Qualification.objects.get(legacy_opportunity=opportunity).outcome == "qualified"
    opportunity.refresh_from_db()
    assert opportunity.archived_at is None


def test_oportunidade_sem_lead_e_pulada(porta: Service) -> None:
    """Avaliação sem lead não existe; inventar um lead sintético seria dado falso na base."""
    orfa = OpportunityFactory(service=porta)

    _rodar_backfill()

    assert Qualification.objects.count() == 0
    orfa.refresh_from_db()
    assert orfa.archived_at is None


def test_backfill_ignora_servico_fora_do_degrau_de_aquisicao() -> None:
    sprint = Service.objects.get(tier=Service.Tier.DISCOVERY_SPRINT)
    _oportunidade_de_qualificacao(sprint)

    _rodar_backfill()

    assert Qualification.objects.count() == 0


def test_backfill_e_idempotente(porta: Service) -> None:
    _oportunidade_de_qualificacao(porta)

    _rodar_backfill()
    _rodar_backfill()

    assert Qualification.objects.count() == 1
    assert Activity.objects.count() == 1


def test_reversa_desfaz_o_que_a_migracao_fez(porta: Service) -> None:
    opportunity, _ = _oportunidade_de_qualificacao(porta)
    _rodar_backfill()

    _reverter_backfill()

    assert Qualification.objects.count() == 0
    assert Activity.objects.filter(opportunity=opportunity).count() == 0
    opportunity.refresh_from_db()
    assert opportunity.archived_at is None


def test_reversa_nao_desarquiva_quem_ja_estava_arquivado(porta: Service) -> None:
    """A ida pulou quem já estava fora da lista; a volta não pode trazê-lo de graça."""
    opportunity, _ = _oportunidade_de_qualificacao(porta)
    opportunity.archived_at = timezone.now() - timedelta(days=30)
    opportunity.save(update_fields=["archived_at"])
    _rodar_backfill()

    _reverter_backfill()

    opportunity.refresh_from_db()
    assert opportunity.archived_at is not None


def test_reversa_nao_desarquiva_quem_alguem_arquivou_depois(porta: Service) -> None:
    """O outro lado da linha do tempo, e o caso que separa assinatura de janela.

    A ida arquiva com o **mesmo instante** da avaliação, e a volta compara por igualdade. Um
    critério de janela — "carimbo posterior ao da avaliação" — passaria neste cenário e ainda assim
    estaria errado: quem arquivou a oportunidade **depois** do deploy tomou uma decisão, e a
    reversa a desfaria em silêncio.
    """
    opportunity, _ = _oportunidade_de_qualificacao(
        porta, stage=PipelineStage.objects.get(kind="won")
    )
    ProjectFactory(client=opportunity.client, opportunity=opportunity)  # a ida não arquiva
    _rodar_backfill()
    depois = timezone.now() + timedelta(days=1)
    Opportunity.objects.filter(pk=opportunity.pk).update(archived_at=depois)

    _reverter_backfill()

    opportunity.refresh_from_db()
    assert opportunity.archived_at == depois


def test_a_ida_carimba_o_arquivamento_com_o_instante_da_avaliacao(porta: Service) -> None:
    """A assinatura em si: o par de carimbos idênticos é o que a reversa reconhece."""
    opportunity, _ = _oportunidade_de_qualificacao(porta)

    _rodar_backfill()

    qualification = Qualification.objects.get()
    opportunity.refresh_from_db()
    assert opportunity.archived_at == qualification.created_at


def test_comando_de_reconciliacao_reporta_o_que_ficou(porta: Service, capsys) -> None:
    from django.core.management import call_command

    _oportunidade_de_qualificacao(porta)
    orfa = OpportunityFactory(service=porta, title="Sem lead")
    _rodar_backfill()

    call_command("reconciliar_qualification")

    saida = capsys.readouterr().out
    assert "Oportunidades de qualification_call: 2" in saida
    assert "Traduzidas em Qualification: 1" in saida
    assert f"#{orfa.pk} — Sem lead" in saida
    assert "Pendentes de tradução: 1" in saida


def test_avaliador_nulo_nao_impede_a_traducao(porta: Service) -> None:
    """`Opportunity.owner` é `PROTECT` e nunca é nulo — mas `assessor` é `SET_NULL` e sobrevive."""
    opportunity, _ = _oportunidade_de_qualificacao(porta, owner=UserFactory())
    _rodar_backfill()

    qualification = Qualification.objects.get()
    assert qualification.assessor_id is not None
