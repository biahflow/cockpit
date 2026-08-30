"""Fase 6 — remove a projeção `Project.client` (issue #70, ADR 0050/0052).

A conta canônica do projeto é `engagement.account`; `Project.client` era uma projeção temporária.
`Project.clean()` recusava divergência nos caminhos que o chamavam, mas não era constraint de banco
e `save()` não o executa automaticamente. Por isso a remoção **não confia** na convenção: o
`RunPython` abaixo mede todas as linhas na própria base alvo e interrompe a migração se encontrar
qualquer `client_id != engagement.account_id`. A coluna só cai depois da prova de equivalência.

Consequência de acesso: nenhuma. Todo filtro que era `filter(client=account)` virou
`filter(engagement__account=account)`, e o custo de query é o mesmo — o índice de
`Engagement.account_id` já existia.

Consequência de contrato `/api/v1/`: nenhuma quebra. `ProjectSerializer.client` continua saindo no
`GET`, derivado de `engagement.account_id`, e `POST`/`PATCH` continuam validando `client` no corpo
contra o engagement (ou contra a oportunidade em `convert-to-project`). O que muda é que
**`client` deixa de ser gravável**: a escrita passa a ser controlada exclusivamente por
`engagement`.

A pk da `Account` não muda. O campo era `on_delete=PROTECT` e `related_name="projects"`; a remoção
não toca nenhuma outra tabela.
"""

from django.db import migrations, models


def exigir_equivalencia_da_projecao(apps, schema_editor) -> None:  # type: ignore[no-untyped-def]
    """Interrompe o deploy antes de apagar uma projeção que divergiu da fonte canônica."""
    Project = apps.get_model("core", "Project")
    divergentes = Project.objects.exclude(client_id=models.F("engagement__account_id"))
    ids = list(divergentes.order_by("pk").values_list("pk", flat=True)[:10])
    if ids:
        raise RuntimeError(
            "Project.client diverge de engagement.account; reconcilie antes da migração 0070. "
            f"Primeiros project ids: {ids}"
        )


class Migration(migrations.Migration):
    dependencies = [
        ("core", "0069_renomeia_tabelas_da_ontologia"),
    ]

    operations = [
        migrations.RunPython(
            exigir_equivalencia_da_projecao,
            migrations.RunPython.noop,
        ),
        migrations.RemoveField(
            model_name="project",
            name="client",
        ),
    ]
