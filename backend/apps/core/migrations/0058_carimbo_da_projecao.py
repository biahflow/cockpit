"""O carimbo da projeção do portal: versão monotônica e hora de observação (ADR 0051).

Duas colunas aditivas em `Project`. O consumidor — o repo `one`, ADR 0076 de lá — já implementou
o leitor: o `sync_snapshot` recusa snapshot com `projection_version` menor que o persistido,
resolve empate por `observed_at` e loga `projection.stale_rejected`. O leitor estava de pé e o
produtor nunca existiu; estas colunas são o produtor.

## Sem backfill, de propósito

`projection_version` nasce `0` e `projection_observed_at` nasce `None` para todo projeto já
existente. Não há `RunPython`, e a ausência dele é decisão e não esquecimento: um backfill teria
de escolher uma hora para "quando este lado observou o estado", e a única resposta honesta seria
a hora da migração — que é a hora do deploy, não a hora em que o estado mudou. É exatamente o
colapso que a ADR 0076 nomeia como o erro a evitar.

A ADR 0076 declara que versão ausente de um lado não recusa nada, então `0`/`None` atravessa a
janela sem quebrar o comparador. O primeiro salvamento que passe por um receiver `_emit_*`
carimba o projeto, e a partir dali a proteção contra obsolescência vale para ele.
"""

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("core", "0057_project_engagement_obrigatorio"),
    ]

    operations = [
        migrations.AddField(
            model_name="project",
            name="projection_version",
            field=models.PositiveIntegerField(default=0),
        ),
        migrations.AddField(
            model_name="project",
            name="projection_observed_at",
            field=models.DateTimeField(blank=True, null=True),
        ),
    ]
