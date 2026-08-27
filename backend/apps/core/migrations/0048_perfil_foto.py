"""Foto de perfil do próprio usuário (Issue #56, DAP perfil-e-contato r1).

Aditiva e não destrutiva: dois campos opcionais em `User`. `avatar` é `FileField` e não
`ImageField` porque o segundo exige Pillow — a validação de "isto é mesmo uma imagem" mora em
`ProfileAvatarSerializer`, que confere tamanho, extensão e bytes de assinatura.

Nota de merge, no mesmo espírito da nota da 0046: **a folha da graph é a 0046**, e não a 0047,
porque a 0046 (projeção GitHub, PR #53) foi linearizada *depois* da 0047 (linha do tempo, PR #52)
— o número do arquivo e a ordem topológica divergem desde então. Depender da 0046 já inclui a
0047 por transitividade. O número 0048 evita um terceiro arquivo com prefixo 0047.
"""

from django.db import migrations, models

import apps.core.models


class Migration(migrations.Migration):

    dependencies = [
        ("core", "0046_github_delivery_projection"),
    ]

    operations = [
        migrations.AddField(
            model_name="user",
            name="avatar",
            field=models.FileField(blank=True, upload_to=apps.core.models.avatar_upload_to),
        ),
        migrations.AddField(
            model_name="user",
            name="avatar_updated_at",
            field=models.DateTimeField(blank=True, null=True),
        ),
    ]
