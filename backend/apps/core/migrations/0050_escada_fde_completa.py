"""A escada FDE completa nos níveis de produto.

Até aqui `Service.tier` tinha três degraus, e o docstring do modelo dizia que a Technical
Feasibility não tinha tier porque criá-lo "mexe na constraint de um ativo por nível e na
semente, e é decisão de produto que espera o primeiro caso real que a exija". O caso apareceu:
a escada operada é a do material — Qualification Call, Discovery Express + Assessment,
Discovery Sprint, Feasibility, PROVE, Scale, Transformation Partnership.

**Duas chaves são renomeadas**, e não recriadas: `discovery_express` vira `discovery_sprint` e
`implantacao` vira `prove`. Recriar quebraria o vínculo das oportunidades e projetos que já
apontam para o serviço; renomear preserva. `discovery_assessment` mantém a chave e ganha nome
novo, porque o que mudou nele foi o rótulo comercial, não o degrau.

**Nome e resumo só são reescritos quando ainda são os semeados pela 0020.** Quem já editou o
catálogo na tela decidiu alguma coisa, e uma migração que sobrescreve decisão de gente é uma
migração que ninguém confia — o mesmo cuidado que a 0020 teve ao usar `get_or_create`.

PRIORITIZE não entra: não se fatura separado, é o entregável do Discovery Sprint.
"""

from django.db import migrations, models

# (chave antiga, chave nova, nome semeado antigo, nome novo, resumo novo)
RENOMEACOES = [
    ("discovery_express", "discovery_sprint", "Discovery Express", "Discovery Sprint",
     "Discovery pago de 5–7 dias: walkthrough do processo com P-S-D-T-E-R, achados rotulados "
     "(fato / hipótese / desconhecido), custo do estado atual apurado e Executive Readout com o "
     "ranking por Opportunity Score."),
    ("implantacao", "prove", "Implantação", "PROVE (piloto)",
     "Produção controlada com baseline e critérios de sucesso definidos antes de construir. "
     "Fecha em decision gate SCALE / ITERATE / STOP, sustentado por pelo menos 10 casos reais."),
]

# (chave, nome semeado antigo, nome novo, resumo novo)
RERROTULACOES = [
    ("discovery_assessment", "Discovery + Assessment", "Discovery Express + Assessment",
     "Discovery estruturado do processo mais assessment de maturidade em IA, fechando com o "
     "próximo passo recomendado. Gratuito no programa de founding client; pago para os demais."),
]

# (chave, nome, preço de tabela, resumo)
#
# O preço nasce em 0 onde ainda não foi decidido — e 0 aqui **não** quer dizer gratuito, o que é
# a mesma ambiguidade que a 0020 deixou e que o seletor do Comercial ainda exibe como "gratuito".
# Só `qualification_call` é gratuito de verdade. Os demais preços vêm do material e são o ponto
# de partida: ajustar é na tela Serviços.
NOVOS_TIERS = [
    ("qualification_call", "Qualification Call", 0,
     "Call gratuita de 30–45 minutos para entender o contexto e decidir se há caso. Termina em "
     "avançar para o Discovery ou NO-GO — e o NO-GO também é entrega."),
    ("feasibility", "Technical Feasibility (T.O.E.)", 5000,
     "Só quando há dúvida real de que a tecnologia dá conta. Meta definida antes da amostra, "
     "falhas classificadas em E1–E5, Ceiling de Input calculado e decision gate de quatro saídas."),
    ("scale", "Scale", 80000,
     "Expansão do que o PROVE sustentou: produção plena, treinamento da operação e captura de "
     "valor registrada no Value Ledger."),
    ("transformation", "Transformation Partnership", 0,
     "Parceria contínua com revisão mensal do Value Ledger e do Opportunity Backlog. ATENÇÃO: o "
     "valor é MENSAL e o catálogo ainda não sabe representar recorrência — confira na mão."),
]


def aplicar(apps, schema_editor):
    Service = apps.get_model("core", "Service")

    for chave_antiga, chave_nova, nome_semeado, nome_novo, resumo in RENOMEACOES:
        for service in Service.objects.filter(tier=chave_antiga):
            service.tier = chave_nova
            if service.name == nome_semeado:
                service.name = nome_novo
                service.summary = resumo
            service.save()

    for chave, nome_semeado, nome_novo, resumo in RERROTULACOES:
        for service in Service.objects.filter(tier=chave, name=nome_semeado):
            service.name = nome_novo
            service.summary = resumo
            service.save()

    for chave, nome, preco, resumo in NOVOS_TIERS:
        Service.objects.get_or_create(
            tier=chave,
            archived_at=None,
            defaults={"name": nome, "list_price": preco, "summary": resumo, "active": True},
        )


def reverter(apps, schema_editor):
    """Desfaz as renomeações e remove só os degraus novos que ninguém usou.

    Simétrico ao `unseed` da 0020: degrau já vinculado a oportunidade ou projeto fica onde está,
    porque apagá-lo levaria histórico junto.
    """
    Service = apps.get_model("core", "Service")

    for chave_antiga, chave_nova, nome_semeado, nome_novo, _resumo in RENOMEACOES:
        for service in Service.objects.filter(tier=chave_nova):
            service.tier = chave_antiga
            if service.name == nome_novo:
                service.name = nome_semeado
            service.save()

    for chave, nome_semeado, nome_novo, _resumo in RERROTULACOES:
        Service.objects.filter(tier=chave, name=nome_novo).update(name=nome_semeado)

    chaves = [chave for chave, *_ in NOVOS_TIERS]
    Service.objects.filter(
        tier__in=chaves, projects__isnull=True, opportunities__isnull=True
    ).delete()


class Migration(migrations.Migration):
    dependencies = [("core", "0049_merge_0048_contact_first_last_name_0048_perfil_foto")]

    operations = [
        migrations.AlterField(
            model_name="service",
            name="tier",
            field=models.CharField(
                blank=True,
                choices=[
                    ("qualification_call", "Qualification Call"),
                    ("discovery_assessment", "Discovery Express + Assessment"),
                    ("discovery_sprint", "Discovery Sprint"),
                    ("feasibility", "Technical Feasibility (T.O.E.)"),
                    ("prove", "PROVE (piloto)"),
                    ("scale", "Scale"),
                    ("transformation", "Transformation Partnership"),
                ],
                default="",
                max_length=32,
            ),
        ),
        migrations.RunPython(aplicar, reverter),
    ]
