"""Semeia os três níveis de produto sobre o catálogo de `Service`.

Nome, preço e resumo são editáveis pelo admin depois; este é só o ponto de partida com o
vocabulário Biahflow. Idempotente por `tier`: quem já tem o nível cadastrado não é tocado, e
o preço fica em 0 (a definir na tela) exceto pelo Discovery Express, gratuito por definição.
"""

from django.db import migrations

# (tier, nome, preço de tabela, resumo do que está incluso)
DEFAULT_TIERS = [
    ("discovery_express", "Discovery Express", 0,
     "Sessão única de diagnóstico gratuita: entendimento do contexto, mapeamento das dores e "
     "identificação de oportunidades de IA. Entrega um resumo com os próximos passos sugeridos."),
    ("discovery_assessment", "Discovery + Assessment", 0,
     "Discovery aprofundado mais assessment de maturidade em IA: diagnóstico por dimensões "
     "(dados, processos, pessoas e ferramentas), recomendações priorizadas e plano de ação."),
    ("implantacao", "Implantação", 0,
     "Construção e entrada em operação dos Funcionários Digitais: piloto, go-live, treinamento "
     "da operação e acompanhamento assistido, com KPIs e ROI acompanhados no portal."),
]


def seed(apps, schema_editor):
    Service = apps.get_model("core", "Service")
    for tier, name, list_price, summary in DEFAULT_TIERS:
        Service.objects.get_or_create(
            tier=tier,
            archived_at=None,
            defaults={"name": name, "list_price": list_price, "summary": summary, "active": True},
        )


def unseed(apps, schema_editor):
    Service = apps.get_model("core", "Service")
    tiers = [tier for tier, *_ in DEFAULT_TIERS]
    # Só remove os níveis que nunca foram usados; os demais mantêm o histórico de projetos.
    Service.objects.filter(tier__in=tiers, projects__isnull=True, opportunities__isnull=True).delete()


class Migration(migrations.Migration):
    dependencies = [("core", "0019_service_tier_and_opportunity_service")]

    operations = [migrations.RunPython(seed, unseed)]
