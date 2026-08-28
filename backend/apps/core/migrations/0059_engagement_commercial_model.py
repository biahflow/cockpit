"""Registra em que condição comercial o mandato nasceu (FDD 046, emenda).

`Engagement` não dizia se a conta paga ou se entrou como `design_partner` — recebe Discovery sem
cobrança em troca de servir de caso e de campo de prova. Sem o campo, os dois eram a mesma linha.

## Sem `RunPython`, e o motivo não é preguiça

`AddField` com `default=paid` carimba as linhas existentes como pagas, e isso é **inferência**, não
registro: elas vieram do backfill da `0056`, que criou um mandato por conta que **tinha projeto**,
e projeto veio de venda — nenhuma delas foi observada como design partner, foi deduzida como paga.

A correção de quem de fato é design partner (hoje, ao menos a Cartas Vivas) é trabalho humano sobre
uma lista de contas que cresce por venda, não por deploy — uma lista de nome de cliente dentro de
migração histórica envelhece na primeira renomeação, e um comando de terminal precisaria ser
rodado de novo a cada conta nova. Por isso a correção é o admin do Django (`EngagementAdmin`,
`backend/apps/core/admin.py`), e não um `RunPython` aqui.
"""

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("core", "0058_carimbo_da_projecao"),
    ]

    operations = [
        migrations.AddField(
            model_name="engagement",
            name="commercial_model",
            field=models.CharField(
                choices=[("design_partner", "Design partner"), ("paid", "Pago")],
                default="paid",
                max_length=16,
            ),
        ),
    ]
