from decimal import Decimal

import pytest
from django.test import override_settings

from apps.core import ai
from apps.core.models import AiInteraction, Service

from .factories import (
    MeetingFactory,
    OpportunityFactory,
    ProjectFactory,
    ServiceFactory,
    UserFactory,
)


@pytest.mark.django_db
def test_build_project_context_has_name_and_status():
    project = ProjectFactory()
    context = ai.build_project_context(project)
    assert project.name in context
    assert project.status in context


@pytest.mark.django_db
def test_build_meeting_context_has_title_and_transcript():
    meeting = MeetingFactory(title="Discovery Acme", transcript="Processo manual de faturamento.")
    context = ai.build_meeting_context(meeting)
    assert "Discovery Acme" in context
    assert "Processo manual de faturamento." in context
    assert meeting.project.name in context


@pytest.mark.django_db
def test_build_opportunity_context_has_client_and_value():
    opportunity = OpportunityFactory()
    context = ai.build_opportunity_context(opportunity)
    assert opportunity.client.name in context
    assert opportunity.title in context
    assert "Nível de produto" not in context  # oportunidade sem nível não inventa um


@pytest.mark.django_db
def test_build_opportunity_context_describes_the_product_tier():
    express = Service.objects.get(tier=Service.Tier.DISCOVERY_EXPRESS)
    context = ai.build_opportunity_context(OpportunityFactory(service=express))

    assert f"Nível de produto: {express.name} (Discovery Express)" in context
    assert "Preço de tabela: gratuito" in context
    assert express.summary in context


@pytest.mark.django_db
def test_build_opportunity_context_prices_a_paid_tier():
    paid = Service.objects.get(tier=Service.Tier.DISCOVERY_ASSESSMENT)
    paid.list_price = Decimal("18000.00")
    paid.save(update_fields=["list_price"])

    context = ai.build_opportunity_context(OpportunityFactory(service=paid))

    assert "Preço de tabela: 18000.00" in context


@pytest.mark.django_db
def test_build_opportunity_context_names_a_service_without_tier():
    context = ai.build_opportunity_context(OpportunityFactory(service=ServiceFactory(name="Avulso")))

    assert "Nível de produto: Avulso" in context
    assert "()" not in context


@pytest.mark.django_db
@override_settings(AI_DAILY_LIMIT=1)
def test_within_daily_limit_counts_interactions():
    user = UserFactory()
    assert ai.within_daily_limit(user) is True
    AiInteraction.objects.create(user=user, feature="project_chat")
    assert ai.within_daily_limit(user) is False


@pytest.mark.django_db
@override_settings(AI_ENABLED=True)
def test_is_enabled_reflects_setting():
    assert ai.is_enabled() is True


# --- teto de tokens por feature ----------------------------------------------


def test_completion_kwargs_sem_teto_nao_manda_max_tokens():
    """Sem teto explícito a chave nem aparece: mandar `max_tokens: None` ao SDK é diferente de não
    mandar, e a proposta e o contrato dependem de **não** ter teto — truncar um contrato no meio de
    uma cláusula é pior que o gasto que o teto economizaria."""
    argumentos = ai.completion_kwargs("sistema", "usuário")

    assert "max_tokens" not in argumentos
    assert argumentos["messages"] == [
        {"role": "system", "content": "sistema"},
        {"role": "user", "content": "usuário"},
    ]


def test_completion_kwargs_com_teto_o_repassa():
    assert ai.completion_kwargs("s", "u", max_tokens=300)["max_tokens"] == 300


def test_teto_vale_so_onde_a_saida_tem_forma_fixa():
    """A rodada 2 mediu a saída real: média ~225 tokens, máximo 854 no contrato. Um teto global
    seria alto demais para ser teto, ou truncaria contrato. Então ele existe só nos dois pontos que
    consomem JSON curto — e este teste trava a escolha contra um "simplifiquemos" futuro."""
    from apps.core import ai_score, qualification

    assert qualification._MAX_TOKENS < ai_score._MAX_TOKENS  # o JSON do lead é o menor dos dois
    assert ai_score._MAX_TOKENS >= 2 * 178  # folga sobre o que a rodada 2 mediu de fato
