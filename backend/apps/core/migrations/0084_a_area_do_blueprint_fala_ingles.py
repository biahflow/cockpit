"""Issue #122, fatia 5.1 — `DigitalEmployeeBlueprint.Area` fala inglês.

`docs/ontology/aliases.md` sempre deu um prazo diferente a esta família: "depois de o conceito
canônico estar no mapa", porque ela precisava primeiro de um lugar na Language Map onde ancorar o
valor. A decisão D10 (v1.4, `docs/ontology/language-map.md` §4) cumpriu essa condição — valor de
enum é termo de domínio e segue a regra de idioma como classe e campo — e esta é a primeira família
das quatro em português com o pré-requisito completo: a classe já era `DigitalEmployeeBlueprint`
(inglesa) desde que nasceu, faltava só o valor.

## Por que esta é a primeira migração de **valor**, e o molde que ela estabelece

Toda migração histórica de ontologia (`0067`–`0072`, `0069`) foi `RenameModel`, `RenameField` ou
`AlterModelTable`: o rótulo muda, a linha e a pk sobrevivem, e nenhuma delas lê ou escreve o dado
que a coluna carrega. Aqui é diferente — as cinco strings que `area` persiste (`comercial`,
`financeiro`, `rh`, `juridico`, `atendimento`) viram inglês (`commercial`, `finance`, `hr`, `legal`,
`support`). Os MEMBROS do enum (`Area.COMMERCIAL` etc.) e os LABELS pt-BR ("Comercial", ...) não
mudam: rótulo é superfície, valor é contrato (D10). `default=Area.COMMERCIAL` acompanha sozinho,
porque continua sendo o mesmo membro Python.

## Por que há reversa, e ela não é formalidade

Valor persistido sem caminho de volta é migração destrutiva disfarçada: reverter o deploy sem
reverter o dado deixaria `area` com valores que os `choices` da versão anterior do código não
reconhecem — o mesmo argumento que `0070` fez de outra forma (prova de equivalência antes de
remover a coluna). A reversa aqui é simétrica (en→pt), cinco `.update()` no sentido contrário.

## O par que autoriza

`docs/ontology/aliases.md`, a linha "áreas `comercial` / `financeiro` / `rh` / `juridico` /
`atendimento`" da tabela de aliases vivos, e a nota D10 logo abaixo dela.

## A checagem que a fatia pediu

Nenhuma migração ou seed anterior cria `DigitalEmployeeBlueprint` com área em português:
`0030_vertical_blueprint_and_client_vertical` só declara o campo (`CreateModel`), sem `RunPython`
de dados, e não há `management command` de seed para este modelo. A forward abaixo não precisa
cobrir linhas criadas por outra migração.
"""

from django.db import migrations, models

# Cinco updates por par — não `RunPython` linha a linha — porque a tradução é sobre o **valor**
# fechado do enum, não sobre uma coluna livre: cada par é uma condição, não uma transformação de
# texto por linha.
_PARES_PT_PARA_EN: tuple[tuple[str, str], ...] = (
    ("comercial", "commercial"),
    ("financeiro", "finance"),
    ("rh", "hr"),
    ("juridico", "legal"),
    ("atendimento", "support"),
)


def traduzir_para_ingles(apps, schema_editor):  # type: ignore[no-untyped-def]
    """Forward: cinco `.filter(area=antigo).update(area=novo)`, um por par."""
    DigitalEmployeeBlueprint = apps.get_model("core", "DigitalEmployeeBlueprint")
    for antigo, novo in _PARES_PT_PARA_EN:
        DigitalEmployeeBlueprint.objects.filter(area=antigo).update(area=novo)


def traduzir_para_portugues(apps, schema_editor):  # type: ignore[no-untyped-def]
    """Reversa simétrica: valor persistido sem caminho de volta é migração destrutiva disfarçada."""
    DigitalEmployeeBlueprint = apps.get_model("core", "DigitalEmployeeBlueprint")
    for antigo, novo in _PARES_PT_PARA_EN:
        DigitalEmployeeBlueprint.objects.filter(area=novo).update(area=antigo)


class Migration(migrations.Migration):

    dependencies = [
        ('core', '0083_o_grupo_de_whatsapp_passa_ao_mandato'),
    ]

    operations = [
        migrations.AlterField(
            model_name='digitalemployeeblueprint',
            name='area',
            field=models.CharField(choices=[('commercial', 'Comercial'), ('finance', 'Financeiro'), ('hr', 'RH'), ('legal', 'Jurídico'), ('support', 'Atendimento')], default='commercial', max_length=24),
        ),
        migrations.RunPython(traduzir_para_ingles, traduzir_para_portugues),
    ]
