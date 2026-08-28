"""Cria o `Engagement` e abre espaço para ele — **passo 1 de 3** (ADR 0050, FDD 046).

Esta migração é só de esquema, e deixa o banco num estado deliberadamente frouxo:
`Project.engagement` nasce **nullable**, mesmo sendo obrigatório no modelo alvo. A coluna é
populada pela 0056 e fechada em NOT NULL pela 0057. A justificativa dos três passos está na
docstring da 0057; aqui basta registrar que o passo 1 não pode exigir o que ainda não existe.

O outro ato é a mudança de cardinalidade: `Project.opportunity` (`OneToOneField`) vira
`Project.originating_commercial_opportunity` (`ForeignKey`). `RenameField` **antes** de
`AlterField`, nesta ordem, porque o rename preserva os dados da coluna — invertido, o Django
dropa e recria, e a origem comercial de toda a carteira vira nula sem que nada acuse.

A troca **remove do banco** a garantia de que uma oportunidade vira no máximo um projeto. Isso é
o requisito (venda recorrente origina vários projetos) e não um efeito colateral; a garantia que
importa preservar — o botão "converter" não duplica projeto — migrou para a action, com
`select_for_update`. Ver ADR 0050.
"""

import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
        ("core", "0052_backfill_qualification"),
        # A fase 3 (`0053`/`0054`) foi escrita em paralelo a esta, e as duas saíram de `0050`.
        # Depender das duas pontas aqui fecha as folhas sem migração de merge: nada nesta migração
        # toca `Evidence`/`Finding`/`Discovery`, então a ordem entre elas é indiferente — o que não
        # é indiferente é o `makemigrations --check` reprovando um grafo com duas cabeças.
        ("core", "0054_backfill_evidence_finding"),
    ]

    operations = [
        migrations.CreateModel(
            name="Engagement",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False,
                                           verbose_name="ID")),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("archived_at", models.DateTimeField(blank=True, null=True)),
                ("name", models.CharField(max_length=255)),
                ("mandate", models.TextField(blank=True, default="")),
                ("status", models.CharField(
                    choices=[("active", "Ativo"), ("paused", "Pausado"), ("closed", "Encerrado")],
                    default="active", max_length=16,
                )),
                ("started_at", models.DateField(blank=True, null=True)),
                ("ended_at", models.DateField(blank=True, null=True)),
                ("success_definition", models.TextField(blank=True, default="")),
                ("needs_review", models.BooleanField(default=False)),
                ("account", models.ForeignKey(
                    on_delete=django.db.models.deletion.PROTECT, related_name="engagements",
                    to="core.client",
                )),
                ("owner", models.ForeignKey(
                    on_delete=django.db.models.deletion.PROTECT, related_name="owned_engagements",
                    to=settings.AUTH_USER_MODEL,
                )),
                ("sponsor", models.ForeignKey(
                    blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL,
                    related_name="sponsored_engagements", to="core.contact",
                )),
            ],
            options={"ordering": ["-started_at", "-id"]},
        ),
        migrations.AddField(
            model_name="opportunity",
            name="engagement",
            field=models.ForeignKey(
                blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL,
                related_name="commercial_opportunities", to="core.engagement",
            ),
        ),
        migrations.AddField(
            model_name="project",
            name="engagement",
            field=models.ForeignKey(
                null=True, on_delete=django.db.models.deletion.PROTECT, related_name="projects",
                to="core.engagement",
            ),
        ),
        migrations.RenameField(
            model_name="project",
            old_name="opportunity",
            new_name="originating_commercial_opportunity",
        ),
        migrations.AlterField(
            model_name="project",
            name="originating_commercial_opportunity",
            field=models.ForeignKey(
                blank=True, null=True, on_delete=django.db.models.deletion.PROTECT,
                related_name="projects", to="core.opportunity",
            ),
        ),
    ]
