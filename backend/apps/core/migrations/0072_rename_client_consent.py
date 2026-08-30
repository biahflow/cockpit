"""Fase 6 — renomeia `client_consent` → `account_consent` (issue #70, language-map §5).

O consentimento é da **conta** (a organização), não do "cliente" — o nome legado feria a regra
§5 do language-map que bane `client` como organização. `RenameField` renomeia a coluna e
preserva dados e pk.
"""

from django.db import migrations


class Migration(migrations.Migration):
    dependencies = [
        ("core", "0071_rename_ai_opportunity"),
    ]

    operations = [
        migrations.RenameField(
            model_name="case",
            old_name="client_consent",
            new_name="account_consent",
        ),
    ]
