"""`Processo` → `Process`, `ProcessoEtapa` → `ProcessStep`, e os três campos que apontam para eles.

O `docs/ontology/language-map.md` §1 exige o termo canônico em inglês nas quatro superfícies, e
§2 nomeia `Process` e `ProcessStep`. A ADR 0052 é o que autoriza renomear a **classe** agora, na
issue #67, em vez de esperar a Fase 6. Esta é a quarta e última fatia: com ela a issue fecha.

## A tabela não se move, e a ordem das operações é o que garante isso

`AlterModelTable` vem **antes** de cada `RenameModel`, e é no-op no banco por construção: as
tabelas já se chamam `core_processo` e `core_processoetapa`. Elas existem para fixar o `db_table`
**no estado da migração**, de modo que a operação seguinte também seja no-op —
`RenameModel.database_forwards` delega a `alter_db_table`, que abre com
`if old_db_table == new_db_table: return` (Django 5.2.17).

Sem elas a ordem se inverte de fato: o banco renomearia `core_processo` para `core_process` e o
`AlterModelTable` seguinte a renomearia de volta — duas `ALTER TABLE` para chegar onde já se
estava, num caminho em que falhar no meio deixa a tabela com o nome errado. O `sqlmigrate` desta
migração não contém nenhum `RENAME TO "core_process"` nem `RENAME TO "core_processstep"`; o
`ALTER TABLE "new__core_X" RENAME TO "core_X"` que ele mostra é o idioma de rebuild que o SQLite
usa para `RENAME COLUMN`.

O nome da tabela é a Fase 6. O que a `docs/ontology/aliases.md` §2b protege é a **pk**, e pk só se
move se a linha se mover.

## Os campos são `RenameField`, e esses movem coluna

Renome de coluna preserva linha e pk, que é a invariante que importa. São **três**:
`ProcessStep.processo` → `process`, e o par `Evidencia.processo`/`Evidencia.etapa` → `process`/
`step`. Nenhum índice nem constraint é declarado sobre eles, então não há o `RemoveIndex` que a
`0062` precisou intercalar em `CobrancaContato`. O `related_name` de `ProcessStep.process`
acompanha o campo (`etapas` → `steps`) num `AlterField` que é no-op no banco: `related_name` não é
coluna, e ele existe para o estado da migração não divergir do modelo.

`ProcessObservation.process`, `Evidence.process`/`step` e `Finding.process`/`step` já nasceram com
o nome certo (a regra 1 da `aliases.md`) e só trocaram de alvo — nada a renomear neles.

**`Evidencia` não é renomeada, e é o único dos quatro nomes em português que não é só renome.** A
Fase 3 já a **dividiu** em `Evidence` + `Finding`; a classe legada segue de pé porque tem leitor
vivo (`process.custo_do_estado_atual` e a tela do processo), e quem a remove é a Fase 6, junto com
o dual-write. Aqui ela só troca o alvo das FKs e o nome dos dois campos.

Os campos em português **dentro** dos dois modelos ficam: os nove insumos do custo (`volume_mes`,
`custo_hora`, …) e as seis letras do P-S-D-T-E-R. O `language-map` §2 nomeia `Process` e
`ProcessStep` e não diz nada sobre os campos deles, e termo sem nome canônico entra primeiro no
mapa (§8). É a dívida que a ADR 0052 já declarou nas consequências: classe em inglês, coluna em
português.

A chave de payload da `/api/v1/` não muda (`aliases.md` §2c): os serializers continuam emitindo e
aceitando `processo` e `etapa`, e as rotas continuam sendo `/processos/` e `/processo-etapas/`,
com regressão em
`backend/tests/regression/test_o_alias_de_processo_sobrevive_na_v1.py`.
"""

import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("core", "0062_account_lifecycle_status"),
    ]

    operations = [
        migrations.AlterModelTable(name="processo", table="core_processo"),
        migrations.AlterModelTable(name="processoetapa", table="core_processoetapa"),
        migrations.RenameModel(old_name="Processo", new_name="Process"),
        migrations.RenameModel(old_name="ProcessoEtapa", new_name="ProcessStep"),
        migrations.RenameField(model_name="processstep", old_name="processo", new_name="process"),
        migrations.RenameField(model_name="evidencia", old_name="processo", new_name="process"),
        migrations.RenameField(model_name="evidencia", old_name="etapa", new_name="step"),
        # O `related_name` acompanha o campo: `processo.etapas` vira `process.steps`. É acessor
        # interno e não sai em payload nenhum, mas ele fica no estado da migração, e sem esta
        # operação o `makemigrations --check` acusa a divergência para sempre. No banco é no-op —
        # `related_name` não é coluna.
        migrations.AlterField(
            model_name="processstep",
            name="process",
            field=models.ForeignKey(
                on_delete=django.db.models.deletion.CASCADE,
                related_name="steps",
                to="core.process",
            ),
        ),
    ]
