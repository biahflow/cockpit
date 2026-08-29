"""Fase 6 (ADR 0052, issue #70): renomeia as tabelas dos quatro modelos que a #67 já renomeou.

A #67 renomeou as **classes** (`Client`→`Account`, `Opportunity`→`CommercialOpportunity`,
`Processo`/`ProcessoEtapa`→`Process`/`ProcessStep`) e fixou `Meta.db_table` no nome legado para o
`RenameModel` não emitir SQL — a tabela ficava para a Fase 6. Esta migração paga essa dívida: os
pins saíram do `Meta`, e `AlterModelTable(table=None)` faz cada tabela voltar ao nome default do
Django (`core_account`, `core_commercialopportunity`, `core_process`, `core_processstep`).

**`AlterModelTable` renomeia em lugar — um `ALTER TABLE ... RENAME TO`.** A linha e a **pk**
sobrevivem intactas: só o nome da tabela muda. É a garantia que a `docs/ontology/aliases.md` §2b
exige, porque o One deriva chave de identidade de seis dessas pks e a persiste (`organization.slug
= biahflow-client-{id}`, etc.) — e o `{id}` é a pk, que este renome não toca. Fazer isso com modelo
novo + migração de dados criaria linhas com pk nova e desgrudaria os registros externos em silêncio;
por isso a §2b **proíbe** esse caminho.

A operação é reversível: a reversa reaplica o `db_table` legado, renomeando de volta. Não há
migração de dados, nenhum `RunSQL`, nenhuma referência crua a nome de tabela no código (conferido).
Sequências e índices mantêm os nomes antigos no Postgres — são referenciados por OID, não por nome,
e não afetam pk nem dado.
"""

from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ('core', '0068_remove_evidencia_legada'),
    ]

    operations = [
        migrations.AlterModelTable(
            name='account',
            table=None,
        ),
        migrations.AlterModelTable(
            name='commercialopportunity',
            table=None,
        ),
        migrations.AlterModelTable(
            name='process',
            table=None,
        ),
        migrations.AlterModelTable(
            name='processstep',
            table=None,
        ),
    ]
