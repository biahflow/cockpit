"""Fase 6 — renomeia `ai_opportunity` → `ai_potential` (issue #70, language-map §5).

O campo mede "potencial de ganho com IA" e colidia com a regra §5 do language-map que bane
`opportunity` sem qualificador. `ai_potential` preserva o significado sem a colisão.

`RenameField` renomeia a coluna e preserva dados e pk — sem migração de dados.
"""

from django.db import migrations


class Migration(migrations.Migration):
    dependencies = [
        ("core", "0070_remove_project_client"),
    ]

    operations = [
        migrations.RenameField(
            model_name="project",
            old_name="ai_opportunity",
            new_name="ai_potential",
        ),
    ]
