"""Ancora a decisão na fase materializada do projeto (issue #46, ADR 0057).

Sem backfill de propósito: data, fase ativa e texto seriam heurísticas apresentadas como fato.
Rascunhos e registros históricos ficam com a lacuna explícita; novas publicações são fechadas no
serializer até uma pessoa escolher a fase.
"""

import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("core", "0072_rename_client_consent"),
    ]

    operations = [
        migrations.AddField(
            model_name="decisao",
            name="project_phase",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name="decisions",
                to="core.projectphase",
            ),
        ),
    ]
