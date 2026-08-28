"""Fecha `Project.engagement` em NOT NULL — **passo 3 de 3** (ADR 0050, FDD 046).

É a invariante 7 do mapa de linguagem virando restrição de banco: *todo Project tem
`engagement_id` não nulo*. Uma linha de `AlterField`, e um arquivo só para ela.

## Por que três migrações e não uma

Nenhuma migração deste repositório fazia isso antes — `0025_backfill_project_members`,
`0048_contact_first_last_name` e `0050_escada_fde_completa` resolvem esquema e dado no mesmo
arquivo. Aqui a separação é o ponto, e vale escrever o motivo porque este é o precedente.

Numa migração só, o `AlterField` para NOT NULL roda no mesmo passo do `RunPython` que popula a
coluna. Isso funciona, e produz um deploy **irreversível na prática**: o instante em que o código
novo passa a rodar é o mesmo em que a coluna deixa de aceitar nulo, e voltar atrás exige desfazer
esquema e dado juntos, sob pressão.

Separadas, existe uma **janela** — depois da 0056, antes da 0057 — em que a coluna está populada
e ainda aceita nulo. Nessa janela:

- o código antigo continua rodando (ele nunca escreveu a coluna, e nulo ainda é aceito);
- o código novo também roda (a coluna está populada);
- e a volta é `migrate core 0055`, que não perde dado nenhum.

É o que torna o deploy reversível. O custo é um arquivo a mais; o benefício é que a decisão de
apertar a restrição deixa de estar acoplada à decisão de subir o código.

## Ordem, não opcionalidade

Este passo **falha** se a 0056 deixou algum projeto sem engajamento — e falhar aqui é o
comportamento certo: um projeto órfão significa que o backfill não cobriu um caso, e descobrir
isso no `ALTER TABLE` é infinitamente melhor que descobrir num `NULL` que atravessa a aplicação
inteira porque a coluna nunca foi fechada.
"""

import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("core", "0056_backfill_engagement"),
    ]

    operations = [
        migrations.AlterField(
            model_name="project",
            name="engagement",
            field=models.ForeignKey(
                on_delete=django.db.models.deletion.PROTECT, related_name="projects",
                to="core.engagement",
            ),
        ),
    ]
