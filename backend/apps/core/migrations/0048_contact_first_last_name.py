"""Quebra `Contact.name` em `first_name`/`last_name` (issue #55, FDD 001).

Sobrenome é opcional, então a divisão é no **primeiro espaço** — "Ana Paula Sá" vira "Ana" +
"Paula Sá", não três fragmentos; "Madonna" vira "Madonna" + "" (ver `apps/core/contact_names.py`,
testado à parte). `name` volta a existir na API como campo derivado e só-leitura
(`ContactSerializer.name` / `Contact.full_name`); a mudança de contrato de **escrita** é
deliberada e está registrada no CHANGELOG e na FDD 001 — quem lê a API não percebe nada, quem
escreve passa a mandar `first_name`/`last_name`.

Reversível: a função de volta recompõe `name` juntando os dois campos com um espaço, igual à
regra de `Contact.full_name` — duplicada aqui porque o estado histórico da migração (`apps.
get_model`) não carrega properties do modelo atual.
"""

from django.db import migrations, models

from apps.core.contact_names import split_full_name


def dividir_nomes(apps, schema_editor):
    Contact = apps.get_model("core", "Contact")
    for contact in Contact.objects.all().iterator():
        first_name, last_name = split_full_name(contact.name)
        Contact.objects.filter(pk=contact.pk).update(first_name=first_name, last_name=last_name)


def recompor_nome(apps, schema_editor):
    Contact = apps.get_model("core", "Contact")
    for contact in Contact.objects.all().iterator():
        nome = f"{contact.first_name} {contact.last_name}".strip()
        Contact.objects.filter(pk=contact.pk).update(name=nome)


class Migration(migrations.Migration):
    dependencies = [
        # A folha real desta app é `0046_github_delivery_projection`, não `0047_delivery_timeline`
        # (o spec de handoff desta tarefa citava 0047 — desvio consciente, ver relatório final):
        # 0046 já linearizou 0047 como sua dependência ao aterrissar (comentário no topo de
        # 0046), então depender de 0047 aqui reabriria as duas folhas que aquele merge fechou.
        ("core", "0046_github_delivery_projection"),
    ]

    operations = [
        migrations.AddField(
            model_name="contact",
            name="first_name",
            field=models.CharField(default="", max_length=128),
            preserve_default=False,
        ),
        migrations.AddField(
            model_name="contact",
            name="last_name",
            field=models.CharField(blank=True, default="", max_length=128),
            preserve_default=False,
        ),
        migrations.RunPython(dividir_nomes, recompor_nome),
        migrations.RemoveField(
            model_name="contact",
            name="name",
        ),
        migrations.AlterModelOptions(
            name="contact",
            options={"ordering": ["first_name", "last_name"]},
        ),
    ]
