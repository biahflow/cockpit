"""Issue #122, fatia 5.2 — a família 2 (`Activity.CobrancaSinal`) vira `DunningSignal`, e fala inglês.

`docs/ontology/aliases.md` sempre tratou "renome" como três coisas com prazos distintos (ADR
0052): classe, campo e — desde a decisão D10 do language-map — **valor**. A família 4
(`DigitalEmployeeBlueprint.Area`, migração `0084`) foi a primeira a atravessar porque era a única
das quatro com o pré-requisito completo: a classe já nascera inglesa. Esta é a segunda, e a
primeira em que os **três** renomes (classe, campo e valor) chegam juntos, na mesma fatia — D10
exige isso quando a classe também está em português: adiar o campo ou o valor deixaria
`Activity.DunningSignal` (classe inglesa) persistindo em `cobranca_sinal` com valores `esqueceu`/
`nao_pode`/`insatisfeito`, uma contradição que a própria decisão veio fechar.

## Os três renomes, e a ordem entre eles

1. **Classe**: `Activity.CobrancaSinal` → `Activity.DunningSignal` (inner `TextChoices`, sem
   impacto de tabela — não emite SQL).
2. **Campo**: `Activity.cobranca_sinal` → `dunning_signal`, via `RenameField` — a coluna renomeia,
   linha e pk sobrevivem (`docs/ontology/aliases.md` §2b).
3. **Valor**: `esqueceu`→`forgot`, `nao_pode`→`unable_to_pay`, `insatisfeito`→`dissatisfied`, no
   molde exato da `0084` (`AlterField` dos choices + `RunPython` com reversa simétrica).

O `RenameField` vem **primeiro**, e a tradução de valor depois, no mesmo arquivo: o `RunPython`
já opera sobre o nome de coluna novo, e não há um estado intermediário em que a migração fale
metade dos dois nomes.

## Por que há reversa, e ela não é formalidade

Valor persistido sem caminho de volta é migração destrutiva disfarçada — o mesmo argumento da
`0084` e da `0070`. A reversa aqui é simétrica (en→pt), três `.update()` no sentido contrário,
depois de o `RenameField` reverter o nome da coluna de volta a `cobranca_sinal` (o Django desfaz a
lista de operações na ordem inversa).

## O par que autoriza

`docs/ontology/aliases.md`, a linha "valores `esqueceu` / `nao_pode` / `insatisfeito`" da tabela de
aliases vivos, e a nota D10 logo abaixo dela.

## A checagem que a fatia pediu

Nenhuma migração ou seed anterior cria `Activity` com sinal fora do vocabulário: `0041_regua_de_
cobranca` só declara o campo (`AddField`), sem `RunPython` de dados. A forward abaixo não precisa
cobrir linhas criadas por outra migração.
"""

from django.db import migrations, models

# Três updates por par — não `RunPython` linha a linha — pelo mesmo motivo da `0084`: a tradução é
# sobre o **valor** fechado do enum, não sobre uma coluna livre.
_PARES_PT_PARA_EN: tuple[tuple[str, str], ...] = (
    ("esqueceu", "forgot"),
    ("nao_pode", "unable_to_pay"),
    ("insatisfeito", "dissatisfied"),
)


def traduzir_para_ingles(apps, schema_editor):  # type: ignore[no-untyped-def]
    """Forward: três `.filter(dunning_signal=antigo).update(dunning_signal=novo)`, um por par."""
    Activity = apps.get_model("core", "Activity")
    for antigo, novo in _PARES_PT_PARA_EN:
        Activity.objects.filter(dunning_signal=antigo).update(dunning_signal=novo)


def traduzir_para_portugues(apps, schema_editor):  # type: ignore[no-untyped-def]
    """Reversa simétrica: valor persistido sem caminho de volta é migração destrutiva disfarçada."""
    Activity = apps.get_model("core", "Activity")
    for antigo, novo in _PARES_PT_PARA_EN:
        Activity.objects.filter(dunning_signal=novo).update(dunning_signal=antigo)


class Migration(migrations.Migration):

    dependencies = [
        ('core', '0084_a_area_do_blueprint_fala_ingles'),
    ]

    operations = [
        migrations.RenameField(
            model_name='activity',
            old_name='cobranca_sinal',
            new_name='dunning_signal',
        ),
        migrations.AlterField(
            model_name='activity',
            name='dunning_signal',
            field=models.CharField(
                blank=True,
                choices=[
                    ('forgot', 'Esqueceu'),
                    ('unable_to_pay', 'Não pôde pagar'),
                    ('dissatisfied', 'Insatisfeito'),
                ],
                default='',
                max_length=16,
            ),
        ),
        migrations.RunPython(traduzir_para_ingles, traduzir_para_portugues),
    ]
