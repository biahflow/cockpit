from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('core', '0021_signaturerequest_document_ref_and_more'),
    ]

    operations = [
        migrations.AddField(
            model_name='signaturerequest',
            name='sign_url',
            field=models.URLField(blank=True, default=''),
        ),
    ]
