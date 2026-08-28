"""Regressão: o backfill traduz a conversa que estava gravada como venda (migração 0052).

A migração 0052 é o que impede a fatia nova de deixar a base contando as conversas de qualificação
como pipeline. Ela roda uma vez em produção, sobre dado comercial existente — e por isso o teste
executa **a função da migração**, e não uma simulação dela, no molde de
`test_project_member_backfill.py`.

Os dois casos que ela trata com cuidado são os que este arquivo protege: oportunidade **sem lead**
não vira avaliação (inventar um lead sintético é dado falso na base), e oportunidade **com
projeto** vira avaliação mas **não** é arquivada (a origem do projeto é `PROTECT`, e a tela do
projeto lê a oportunidade).
"""

import importlib
from datetime import timedelta

import pytest
from django.apps import apps as django_apps
from django.utils import timezone

from apps.core.models import (
    Activity,
    CommercialOpportunity,
    Lead,
    PipelineStage,
    Qualification,
    Service,
)
from apps.core.tests.factories import (
    AccountFactory,
    CommercialOpportunityFactory,
    LeadFactory,
    ProjectFactory,
    UserFactory,
)

pytestmark = pytest.mark.django_db

MIGRACAO = "apps.core.migrations.0052_backfill_qualification"


# O registro vivo falando o vocabulário de 2026-08, que é o que a 0052 conhece.
#
# A 0052 é história congelada: sob `migrate` ela recebe o estado daquele ponto, onde a classe se
# chama `Opportunity` e `Activity` tem um campo `opportunity` — e continua correta para sempre.
# Este teste, porém, a executa contra o **registro vivo** e um banco no HEAD (é o que
# `_rodar_backfill` explica), e a issue #67 renomeou a classe e o campo. Sem esta ponte o teste
# precisaria virar uma simulação da migração, que é justamente o que este arquivo existe para
# não ser.
#
# São três pontos de contato e nada mais: o nome do modelo e as duas chamadas em que a 0052
# nomeia o campo da `Activity`. O comportamento sob teste — quais linhas nascem, quais são
# arquivadas — não passa por aqui.
_MODELOS = {"Opportunity": "CommercialOpportunity", "Client": "Account"}
_CAMPOS = {
    "opportunity": "commercial_opportunity",
    "opportunity_id__in": "commercial_opportunity_id__in",
    "client_id": "account_id",
}


def _traduzir(kwargs: dict) -> dict:
    return {_CAMPOS.get(chave, chave): valor for chave, valor in kwargs.items()}


@pytest.fixture(autouse=True)
def _nome_historico_da_conta(monkeypatch: pytest.MonkeyPatch) -> None:
    """A quarta ponte: `opportunity.client_id`, que a fatia 2 da issue #67 renomeou.

    A 0052 lê o id da conta pelo nome que a coluna tinha quando ela foi escrita, e continua
    correta sob `migrate` — lá ela recebe o estado histórico. Aqui, que roda contra o registro
    vivo, o id é reposto como propriedade de leitura; o `monkeypatch` a desfaz por teste, então
    o nome banido não sobrevive ao arquivo.
    """
    monkeypatch.setattr(
        CommercialOpportunity, "client_id", property(lambda self: self.account_id), raising=False
    )


class _ManagerDaEpoca:
    def __init__(self, real) -> None:
        self._real = real

    def create(self, **kwargs):
        return self._real.create(**_traduzir(kwargs))

    def filter(self, *args, **kwargs):
        return self._real.filter(*args, **_traduzir(kwargs))

    def __getattr__(self, nome: str):
        return getattr(self._real, nome)


class _ActivityDaEpoca:
    objects = _ManagerDaEpoca(Activity.objects)


class _RegistroDaEpoca:
    def get_model(self, app_label: str, model_name: str):
        if model_name == "Activity":
            return _ActivityDaEpoca
        return django_apps.get_model(app_label, _MODELOS.get(model_name, model_name))


REGISTRO = _RegistroDaEpoca()


def _rodar_backfill() -> None:
    """Importa a migração pelo nome de módulo (o número no início impede o `import` normal).

    O registro **vivo** (via `REGISTRO`) e não o estado histórico da 0052, porque o banco de
    teste está no HEAD: modelos históricos consultariam colunas que já foram renomeadas. É por
    isso que a 0052 resolve o reverso do projeto por `_tem_projeto`, e não por um nome fixo; ver
    a nota "Sobre o reverso do projeto" no cabeçalho dela.
    """
    importlib.import_module(MIGRACAO).backfill_qualification(REGISTRO, None)


def _reverter_backfill() -> None:
    importlib.import_module(MIGRACAO).desfazer_backfill(REGISTRO, None)


@pytest.fixture
def porta() -> Service:
    return Service.objects.get(tier=Service.Tier.QUALIFICATION_CALL)


def _oportunidade_de_qualificacao(porta: Service, **kwargs) -> tuple[CommercialOpportunity, Lead]:
    conta = kwargs.pop("account", None) or AccountFactory()
    opportunity = CommercialOpportunityFactory(account=conta, service=porta, scope="Conversa inicial", **kwargs)
    lead = LeadFactory(account=conta, commercial_opportunity=opportunity)
    return opportunity, lead


def test_backfill_cria_qualificacao_e_auditoria_e_arquiva(porta: Service) -> None:
    opportunity, lead = _oportunidade_de_qualificacao(porta)

    _rodar_backfill()

    qualification = Qualification.objects.get()
    assert qualification.lead_id == lead.pk
    assert qualification.account_id == opportunity.account_id
    assert qualification.legacy_opportunity_id == opportunity.pk
    assert qualification.assessor_id == opportunity.owner_id
    assert qualification.happened_at == opportunity.created_at
    assert qualification.rationale == "Conversa inicial"
    # A auditoria de que a linha existiu — sem ela, a oportunidade some da tela sem explicação.
    nota = Activity.objects.get(commercial_opportunity=opportunity)
    assert nota.summary == f"Qualificação migrada da oportunidade #{opportunity.pk}"
    assert nota.account_id == opportunity.account_id
    opportunity.refresh_from_db()
    assert opportunity.archived_at is not None
    assert CommercialOpportunity.objects.filter(pk=opportunity.pk).exists()  # nada é apagado


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
    ProjectFactory(client=opportunity.account, originating_commercial_opportunity=opportunity)

    _rodar_backfill()

    assert Qualification.objects.get(legacy_opportunity=opportunity).outcome == "qualified"
    opportunity.refresh_from_db()
    assert opportunity.archived_at is None


def test_oportunidade_sem_lead_e_pulada(porta: Service) -> None:
    """Avaliação sem lead não existe; inventar um lead sintético seria dado falso na base."""
    orfa = CommercialOpportunityFactory(service=porta)

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
    assert Activity.objects.filter(commercial_opportunity=opportunity).count() == 0
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
    ProjectFactory(client=opportunity.account, originating_commercial_opportunity=opportunity)  # a ida não arquiva
    _rodar_backfill()
    depois = timezone.now() + timedelta(days=1)
    CommercialOpportunity.objects.filter(pk=opportunity.pk).update(archived_at=depois)

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
    orfa = CommercialOpportunityFactory(service=porta, title="Sem lead")
    _rodar_backfill()

    call_command("reconciliar_qualification")

    saida = capsys.readouterr().out
    assert "Oportunidades de qualification_call: 2" in saida
    assert "Traduzidas em Qualification: 1" in saida
    assert f"#{orfa.pk} — Sem lead" in saida
    assert "Pendentes de tradução: 1" in saida


def test_avaliador_nulo_nao_impede_a_traducao(porta: Service) -> None:
    """`CommercialOpportunity.owner` é `PROTECT` e nunca é nulo — mas `assessor` é `SET_NULL` e sobrevive."""
    opportunity, _ = _oportunidade_de_qualificacao(porta, owner=UserFactory())
    _rodar_backfill()

    qualification = Qualification.objects.get()
    assert qualification.assessor_id is not None
