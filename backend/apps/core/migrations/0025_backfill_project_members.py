"""Traduz o acesso que já existia em linhas de `ProjectMember` (RFC 0003, ADR 0010).

A regra nova é "Entrega vê o projeto de que participa". Aplicada sobre a base como está, ela
zeraria o acesso de todo mundo: até aqui a única noção de pertencimento era `owner`, e na
conversão o dono do projeto e de todos os marcos/tarefas é o vendedor.

O backfill reproduz o critério antigo — dono do projeto, de um marco ou de uma tarefa — para
que quem via um projeto na véspera do deploy continue vendo depois. A mudança de regra não
pode virar uma perda de acesso silenciosa.

Dois detalhes de fidelidade, deliberados:
- **Não filtra `archived_at` em marcos e tarefas.** O critério antigo também não filtrava: ser
  dono de uma tarefa arquivada dava acesso. Apertar isso é decisão separada desta migração.
- **Não inclui `Pendencia.owner`**, que nunca concedeu acesso — incluir seria ampliar, não
  preservar.

`added_by` fica nulo: a concessão é do sistema, não de uma pessoa.
"""

from django.db import migrations


def backfill_members(apps, schema_editor):
    Project = apps.get_model("core", "Project")
    ProjectMember = apps.get_model("core", "ProjectMember")
    for project in Project.objects.all().iterator():
        owners = {project.owner_id}
        owners.update(project.milestone_items.values_list("owner_id", flat=True))
        owners.update(project.task_items.values_list("owner_id", flat=True))
        ProjectMember.objects.bulk_create(
            [
                ProjectMember(project=project, user_id=owner_id)
                for owner_id in owners
                if owner_id is not None
            ],
            ignore_conflicts=True,
        )


def drop_members(apps, schema_editor):
    apps.get_model("core", "ProjectMember").objects.all().delete()


class Migration(migrations.Migration):

    dependencies = [
        ("core", "0024_projectmember"),
    ]

    operations = [
        migrations.RunPython(backfill_members, drop_members),
    ]
