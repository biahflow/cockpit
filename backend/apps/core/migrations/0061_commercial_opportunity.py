"""`Opportunity` → `CommercialOpportunity`, e os cinco campos que apontam para ela.

`Opportunity` sem qualificador é termo banido (`docs/ontology/language-map.md` §5): ele colide
entre a venda no pipeline e a melhoria operacional que a Fase 4 vai chamar de
`ImprovementOpportunity`. A ADR 0052 é o que autoriza renomear a **classe** agora, em vez de
esperar a Fase 6.

## A tabela não se move, e a ordem das operações é o que garante isso

`AlterModelTable` vem **antes** do `RenameModel`, e é no-op no banco por construção: a tabela já
se chama `core_opportunity`. Ela existe para fixar o `db_table` **no estado da migração**, de modo
que a operação seguinte também seja no-op — `RenameModel.database_forwards` delega a
`alter_db_table`, que abre com `if old_db_table == new_db_table: return` (Django 5.2.17).

Sem ela a ordem se inverte de fato: o banco renomearia `core_opportunity` para
`core_commercialopportunity` e o `AlterModelTable` seguinte a renomearia de volta — duas
`ALTER TABLE` para chegar onde já se estava, num caminho em que falhar no meio deixa a tabela com
o nome errado. O `sqlmigrate` desta migração não contém nenhum `RENAME TO`; só `RENAME COLUMN`.

O nome da tabela é a Fase 6. O que a `aliases.md` §2b protege é a **pk** — seis delas saíram deste
repositório e o One as persiste —, e pk só se move se a linha se mover.

## Os campos são `RenameField`, e esses movem coluna

Renome de coluna preserva linha e pk, que é a invariante que importa. `Qualification`
**não** entra na lista: o campo dela se chama `legacy_opportunity`, que é o escape reservado da
`aliases.md` §3 — o prefixo declara, no próprio nome, que aponta para o registro antigo.

`Project.ai_opportunity` também fica: é o AI Score de maturidade, escalar, sem relação nenhuma com
a venda. A colisão de nome é léxica, e o campo vira `PriorityAssessment` na Fase 4.

A chave de payload da `/api/v1/` não muda (`aliases.md` §2c): os serializers continuam emitindo e
aceitando `opportunity`, com regressão em
`backend/tests/regression/test_o_alias_de_venda_sobrevive_na_v1.py`.
"""

from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ("core", "0060_gate_decision"),
    ]

    operations = [
        migrations.AlterModelTable(name="opportunity", table="core_opportunity"),
        migrations.RenameModel(old_name="Opportunity", new_name="CommercialOpportunity"),
        migrations.RenameField(
            model_name="document", old_name="opportunity", new_name="commercial_opportunity"
        ),
        migrations.RenameField(
            model_name="lead", old_name="opportunity", new_name="commercial_opportunity"
        ),
        migrations.RenameField(
            model_name="activity", old_name="opportunity", new_name="commercial_opportunity"
        ),
        migrations.RenameField(
            model_name="aiinteraction", old_name="opportunity", new_name="commercial_opportunity"
        ),
        migrations.RenameField(
            model_name="artifact", old_name="opportunity", new_name="commercial_opportunity"
        ),
    ]
