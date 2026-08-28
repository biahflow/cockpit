"""`Client` → `Account`, os dez campos que apontam para ela, e `status` → `lifecycle_status`.

"Cliente" era o nome da entidade e o nome de um dos estados dela ao mesmo tempo. O nome canônico
da organização é `Account` desde antes de ela comprar (`docs/ontology/language-map.md` §2), e
"Cliente" passa a ser o **rótulo** de `lifecycle_status=active`. A ADR 0052 é o que autoriza
renomear a **classe** agora, na issue #67, em vez de esperar a Fase 6.

## A tabela não se move, e é aqui que isso mais importa

Esta é a primeira das seis pks que a `docs/ontology/aliases.md` §2b inventaria: o One deriva
`organization.slug = biahflow-client-{id}` **e a persiste**. Se a linha se mover, a organização
fica órfã e o cliente perde acesso ao projeto — em silêncio, sem exceção de nenhum dos dois lados.
Pk só se move se a linha se mover, e a linha só se move se a tabela se mover; por isso
`Account.Meta.db_table` fica fixado em `core_client` e o nome da tabela continua sendo a Fase 6.

`AlterModelTable` vem **antes** do `RenameModel`, e é no-op no banco por construção: a tabela já se
chama `core_client`. Ela existe para fixar o `db_table` **no estado da migração**, de modo que a
operação seguinte também seja no-op — `RenameModel.database_forwards` delega a `alter_db_table`,
que abre com `if old_db_table == new_db_table: return` (Django 5.2.17).

Sem ela a ordem se inverte de fato: o banco renomearia `core_client` para `core_account` e o
`AlterModelTable` seguinte a renomearia de volta — duas `ALTER TABLE` para chegar onde já se
estava, num caminho em que falhar no meio deixa a tabela com o nome errado. O `sqlmigrate` desta
migração não contém nenhum `RENAME TO "core_account"`; o `ALTER TABLE "new__core_X" RENAME TO
"core_X"` que ele mostra é o idioma de rebuild que o SQLite usa para `RENAME COLUMN`.

## Os campos são `RenameField`, e esses movem coluna

Renome de coluna preserva linha e pk, que é a invariante que importa. São **dez**, e o décimo
primeiro fica de fora: `Project.client` **não** é renomeado. Ele é a projeção temporária cuja fonte
canônica é `engagement.account` (ADR 0050) e cuja remoção é a Fase 6; chamá-lo de `account` criaria
duas coisas com o nome canônico no mesmo objeto — `project.account` e `project.engagement.account`
— que podem divergir, e o nome canônico deixaria de identificar a fonte.

`Engagement.account`, `Qualification.account`, `Evidence.account` e `Finding.account` já nasceram
com o nome certo (a regra 1 da `aliases.md`) e só trocaram de alvo.

## `lifecycle_status` ganha um terceiro valor, e ele não precisa de migração de dado

`inactive` é valor novo: nenhuma linha o tem. Quem já era `prospect` ou `active` continua igual, e
a coluna só muda de nome.

A chave de payload da `/api/v1/` não muda (`aliases.md` §2c): os serializers continuam emitindo e
aceitando `client` e `status`, com regressão em
`backend/tests/regression/test_o_alias_de_conta_sobrevive_na_v1.py`.
"""

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("core", "0061_commercial_opportunity"),
    ]

    operations = [
        migrations.AlterModelTable(name="client", table="core_client"),
        migrations.RenameModel(old_name="Client", new_name="Account"),
        migrations.RenameField(model_name="contact", old_name="client", new_name="account"),
        migrations.RenameField(
            model_name="commercialopportunity", old_name="client", new_name="account"
        ),
        migrations.RenameField(model_name="document", old_name="client", new_name="account"),
        migrations.RenameField(model_name="lead", old_name="client", new_name="account"),
        migrations.RenameField(model_name="activity", old_name="client", new_name="account"),
        migrations.RenameField(model_name="satisfacao", old_name="client", new_name="account"),
        migrations.RenameField(model_name="processo", old_name="client", new_name="account"),
        migrations.RenameField(model_name="invoice", old_name="client", new_name="account"),
        # O índice de `CobrancaContato` é declarado sobre `client` e carrega o nome da coluna no
        # próprio nome, então ele **sai antes** do renome e volta depois com o nome novo — o
        # `RenameField` não conseguiria remontar a tabela com um índice apontando para uma coluna
        # que já não existe no estado. É `DROP INDEX` + `CREATE INDEX` sobre a mesma tabela: a
        # linha e a pk não se movem.
        migrations.RemoveIndex(
            model_name="cobrancacontato", name="core_cobran_client__44ea63_idx"
        ),
        migrations.RenameField(
            model_name="cobrancacontato", old_name="client", new_name="account"
        ),
        migrations.AddIndex(
            model_name="cobrancacontato",
            index=models.Index(
                fields=["account", "sent_on"], name="core_cobran_account_b3dc5c_idx"
            ),
        ),
        migrations.RenameField(
            model_name="cobrancasuspensao", old_name="client", new_name="account"
        ),
        migrations.RenameField(
            model_name="account", old_name="status", new_name="lifecycle_status"
        ),
        # O terceiro valor entra no `choices` da coluna já renomeada. Não há migração de dado:
        # `inactive` é valor novo e nenhuma linha o tem.
        migrations.AlterField(
            model_name="account",
            name="lifecycle_status",
            field=models.CharField(
                choices=[
                    ("prospect", "Prospect"),
                    ("active", "Ativo"),
                    ("inactive", "Inativo"),
                ],
                default="prospect",
                max_length=16,
            ),
        ),
    ]
