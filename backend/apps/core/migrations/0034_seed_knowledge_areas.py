"""Semeia as cinco áreas de conhecimento (FDD 029).

**Com `owner=None`, e isso é a entrega e não descuido.** A semente não inventa responsável: quem
responde por uma área é decisão da casa, e um dono chutado seria pior que nenhum — daria ao
inventário a aparência de organizado sem ninguém ter combinado nada. "Sem dono" é o estado inicial
honesto, e é justamente ele que faz a tela ser útil no primeiro dia: a primeira coisa que aparece
é o que falta decidir.

Ao contrário do catálogo de blueprints (FDD 026), que deliberadamente **não** foi semeado: lá o
conteúdo é produto da casa e semeá-lo seria inventar oferta. Aqui as cinco áreas espelham as áreas
que o domínio já tem (os três agentes, mais operação e produto), então semear é reconhecer o que
existe, não inventar.
"""

from django.db import migrations

AREAS = [
    ("Comercial", "comercial", 10),
    ("Entrega", "entrega", 20),
    ("Financeiro", "financeiro", 30),
    ("Operação", "operacao", 40),
    ("Produto", "produto", 50),
]


def semear(apps, schema_editor):
    KnowledgeArea = apps.get_model("core", "KnowledgeArea")
    for nome, slug, posicao in AREAS:
        KnowledgeArea.objects.get_or_create(
            slug=slug, defaults={"name": nome, "position": posicao}
        )


def desfazer(apps, schema_editor):
    KnowledgeArea = apps.get_model("core", "KnowledgeArea")
    KnowledgeArea.objects.filter(slug__in=[slug for _, slug, _ in AREAS]).delete()


class Migration(migrations.Migration):
    dependencies = [("core", "0033_knowledge")]
    operations = [migrations.RunPython(semear, desfazer)]
