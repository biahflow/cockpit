"""A `Qualification` como entidade, e a categoria que tira a porta da escada (ADR 0049).

Duas mudanças de esquema que só fazem sentido juntas:

- **`Qualification`** passa a existir. Até aqui a avaliação de um lead era um efeito colateral do
  `POST /leads/{id}/convert/`, que criava direto uma `Opportunity` no degrau gratuito — a conversa
  entrava no funil como venda registrada e podia virar `Project`. A avaliação agora tem linha,
  autor, data e resultado (`qualified` · `nurture` · `disqualified`).
- **`Service.category`** separa oferta de **aquisição** de degrau **vendável**. A migração de dados
  abaixo marca a Qualification Call como `acquisition`; todo o resto do catálogo fica `commercial`,
  que é o default do campo e portanto já vale para o que existia.

`Opportunity.origin_qualification` é nula em toda a carteira atual, de propósito: venda que já
existe não ganha origem inventada, e venda que nasce fora do funil de lead (indicação, conta que
volta a comprar) continua legítima sem avaliação. O que a invariante exige é o condicional —
quando há origem, ela é `qualified` —, e isso vive em `Opportunity.clean()`.

O backfill das oportunidades de `qualification_call` que já existem é a **0052**, separada porque
mexe em dado comercial e precisa de reversa própria.
"""

import django.db.models.deletion
import django.utils.timezone
from django.conf import settings
from django.db import migrations, models


def marcar_aquisicao(apps, schema_editor):
    """A Qualification Call é a única oferta de aquisição do catálogo (D4).

    Por `tier` e não por preço: gratuito também é o Discovery + Assessment do programa de founding
    client, e aquele é degrau vendável. Serviço avulso (`tier` vazio) fica `commercial`, o default.
    """
    apps.get_model("core", "Service").objects.filter(tier="qualification_call").update(
        category="acquisition"
    )


def voltar_a_comercial(apps, schema_editor):
    apps.get_model("core", "Service").objects.filter(tier="qualification_call").update(
        category="commercial"
    )


class Migration(migrations.Migration):

    dependencies = [
        ('core', '0050_escada_fde_completa'),
    ]

    operations = [
        migrations.AddField(
            model_name='service',
            name='category',
            field=models.CharField(choices=[('acquisition', 'Aquisição'), ('commercial', 'Comercial')], default='commercial', max_length=16),
        ),
        migrations.RunPython(marcar_aquisicao, voltar_a_comercial),
        migrations.CreateModel(
            name='Qualification',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
                ('archived_at', models.DateTimeField(blank=True, null=True)),
                ('happened_at', models.DateTimeField(default=django.utils.timezone.now)),
                ('fit', models.CharField(blank=True, choices=[('high', 'Alto'), ('medium', 'Médio'), ('low', 'Baixo')], default='', max_length=8)),
                ('need', models.CharField(blank=True, choices=[('high', 'Alto'), ('medium', 'Médio'), ('low', 'Baixo')], default='', max_length=8)),
                ('urgency', models.CharField(blank=True, choices=[('high', 'Alto'), ('medium', 'Médio'), ('low', 'Baixo')], default='', max_length=8)),
                ('authority', models.CharField(blank=True, choices=[('high', 'Alto'), ('medium', 'Médio'), ('low', 'Baixo')], default='', max_length=8)),
                ('capacity', models.CharField(blank=True, choices=[('high', 'Alto'), ('medium', 'Médio'), ('low', 'Baixo')], default='', max_length=8)),
                ('evidence', models.TextField(blank=True, default='')),
                ('outcome', models.CharField(choices=[('qualified', 'Qualificado'), ('nurture', 'Nutrir'), ('disqualified', 'Desqualificado')], max_length=16)),
                ('rationale', models.TextField(blank=True, default='')),
                ('next_step', models.CharField(blank=True, default='', max_length=200)),
                ('nurture_until', models.DateField(blank=True, null=True)),
                ('ai_suggested_outcome', models.CharField(blank=True, choices=[('qualified', 'Qualificado'), ('nurture', 'Nutrir'), ('disqualified', 'Desqualificado')], default='', max_length=16)),
                ('ai_score_snapshot', models.PositiveSmallIntegerField(blank=True, null=True)),
                ('account', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.PROTECT, related_name='qualifications', to='core.client')),
                ('assessor', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='qualifications_assessed', to=settings.AUTH_USER_MODEL)),
                ('lead', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='qualifications', to='core.lead')),
                ('legacy_opportunity', models.OneToOneField(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='backfilled_qualification', to='core.opportunity')),
            ],
            options={
                'ordering': ['-happened_at'],
            },
        ),
        migrations.AddField(
            model_name='opportunity',
            name='origin_qualification',
            field=models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.PROTECT, related_name='commercial_opportunities', to='core.qualification'),
        ),
    ]
