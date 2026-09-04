"""Issue #122, fatia 5.3 — a família 3 (`Satisfacao`) vira `SatisfactionRecord`, e fala inglês.

Terceira das quatro famílias que a decisão D10 (`docs/ontology/language-map.md` §4) marcou, e a
segunda em que os **três** renomes chegam juntos — classe, tabela e valor. A diferença para a
`0085` está justamente aí: lá o que atravessava com a classe era o **campo** (`RenameField`), e a
tabela ficava intacta porque `CobrancaSinal` é um `TextChoices` interno, sem tabela própria. Aqui
é o contrário: os campos (`nivel`, `fonte`) **não** renomeiam — a §2c congela a chave de payload
até a `/api/v2/`, e o language-map cunha `satisfaction_record.level`/`.source` como nome de enum,
não como nome de coluna — e o que atravessa junto é a **tabela**.

## Por que o `RenameModel` pode renomear a tabela aqui, e por que ele não podia na #67

`docs/ontology/aliases.md` §2b é normativa sobre isto: o renome de modelo se faz com `RenameModel`,
que preserva tabela, linhas e **pk**. Na issue #67 cada fatia fixava `Meta.db_table` no nome legado
**antes** da operação, para o `RenameModel` não emitir SQL nenhum: as seis pks que o One deriva e
**persiste** (§2b) não podiam correr risco enquanto a Fase 6 não chegasse.

A pk de satisfação **não é uma das seis** — a tabela da §2b lista `Client`(→`Account`), `Project`,
`Engagement`, `ProjectDeliverable`, `Document` e `Pendencia`, e nenhum id de satisfação sequer
atravessa a fronteira: o registro **não vai** para o portal do cliente (ADR 0032), então não há
consumidor externo de que se despregar. Por isso não há `AlterModelTable` a escrever antes: o
`RenameModel` emite o `ALTER TABLE core_satisfacao RENAME TO core_satisfactionrecord`, que preserva
linha e pk pelo mesmo mecanismo da `0069` — e a reversa o desfaz.

## Os dois enums, e por que o mapa de pares ganhou um nível

A `0084` e a `0085` traduziram **um** campo cada, e o molde era uma tupla de pares. Esta é a
primeira família com **dois** enums no mesmo modelo (`nivel` e `fonte`), então o mapa passa a ser
campo → pares. Duas listas soltas fariam a reversa precisar saber, de cabeça, qual pertence a qual
coluna — e a reversa é a metade que ninguém exercita até precisar dela.

## Por que há reversa, e ela não é formalidade

Valor persistido sem caminho de volta é migração destrutiva disfarçada — o mesmo argumento da
`0084`, da `0085` e da `0070`. A reversa aqui é simétrica (en→pt), seis `.update()` no sentido
contrário, e o Django desfaz a lista de operações na ordem inversa: primeiro o dado volta ao
português, depois os `choices`, e só então a tabela volta a se chamar `core_satisfacao`.

## O par que autoriza

`docs/ontology/aliases.md`, a linha "valores `declarada` / `percebida` e níveis em português" da
tabela de aliases vivos, e a nota D10 logo abaixo dela.

## A checagem que a fatia pediu

Nenhuma migração ou seed anterior cria `Satisfacao` com nível ou fonte em português:
`0042_satisfacao` só cria o modelo (`CreateModel`), sem `RunPython` de dados, e não há
`management command` que semeie o registro. A forward abaixo não precisa cobrir linhas criadas por
outra migração.
"""

from django.db import migrations, models

# Campo → pares (pt, en). Um nível a mais que a `0084`/`0085` porque esta é a primeira família com
# **dois** enums na mesma tabela: sem a chave do campo, a reversa teria de reconstituir de cabeça
# qual lista pertence a qual coluna.
_PARES_PT_PARA_EN: dict[str, tuple[tuple[str, str], ...]] = {
    "nivel": (
        ("promotor", "promoter"),
        ("satisfeito", "satisfied"),
        ("neutro", "neutral"),
        ("insatisfeito", "dissatisfied"),
    ),
    "fonte": (
        ("declarada", "declared"),
        ("percebida", "perceived"),
    ),
}


def traduzir_para_ingles(apps, schema_editor):  # type: ignore[no-untyped-def]
    """Forward: um `.filter(campo=antigo).update(campo=novo)` por par, nos dois campos."""
    SatisfactionRecord = apps.get_model("core", "SatisfactionRecord")
    for campo, pares in _PARES_PT_PARA_EN.items():
        for antigo, novo in pares:
            SatisfactionRecord.objects.filter(**{campo: antigo}).update(**{campo: novo})


def traduzir_para_portugues(apps, schema_editor):  # type: ignore[no-untyped-def]
    """Reversa simétrica: valor persistido sem caminho de volta é migração destrutiva disfarçada."""
    SatisfactionRecord = apps.get_model("core", "SatisfactionRecord")
    for campo, pares in _PARES_PT_PARA_EN.items():
        for antigo, novo in pares:
            SatisfactionRecord.objects.filter(**{campo: novo}).update(**{campo: antigo})


class Migration(migrations.Migration):

    dependencies = [
        ('core', '0085_o_sinal_de_cobranca_fala_ingles'),
    ]

    operations = [
        migrations.RenameModel(
            old_name='Satisfacao',
            new_name='SatisfactionRecord',
        ),
        migrations.AlterField(
            model_name='satisfactionrecord',
            name='nivel',
            field=models.CharField(
                choices=[
                    ('promoter', 'Promotor'),
                    ('satisfied', 'Satisfeito'),
                    ('neutral', 'Neutro'),
                    ('dissatisfied', 'Insatisfeito'),
                ],
                max_length=16,
            ),
        ),
        migrations.AlterField(
            model_name='satisfactionrecord',
            name='fonte',
            field=models.CharField(
                choices=[
                    ('declared', 'Declarada pelo cliente'),
                    ('perceived', 'Percebida por quem entrega'),
                ],
                max_length=16,
            ),
        ),
        migrations.RunPython(traduzir_para_ingles, traduzir_para_portugues),
    ]
