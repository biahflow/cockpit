"""Fase 6 (ADR 0052, issue #70): remove a `Evidencia` legada e o dual-write.

A `Evidencia` da FDD 039 foi dividida em `Evidence` + `Finding` na Fase 3 (FDD 045, ADR 0049), e
desde então o `MeetingViewSet.estruturar` gravava as duas formas — o modelo fundido continuava de
pé só porque `process.custo_do_estado_atual` e a tela `ProcessDetailPage` liam dele. Esta fatia
reponta o custo para o `Finding(epistemic_status=fact)` e migra a tela para o split; sem leitor, o
legado sai.

**A remoção não perde dado.** O backfill da migração `0054` já copiou cada `Evidencia` para o par
`Evidence`/`Finding`, e o `legacy_evidencia` era só o ponteiro de reconciliação entre as duas
formas. Removê-lo é `SET_NULL` sobre um campo que ninguém mais lê; o `DeleteModel` derruba a tabela
`core_evidencia`, cujo conteúdo já vive, traduzido, no split.

**O gate operacional é a reconciliação, e ela roda antes deste deploy.** O critério da issue #70 é
"remover o dual-write **somente após** a reconciliação automática passar limpa": rodar
`manage.py reconciliar_evidence_finding` na base alvo e conferir "Split reconciliado: todo legado
tem par" **antes** de aplicar esta migração. O comando foi removido no mesmo PR porque importa o
modelo que some — o relatório é pré-condição de deploy, não código que sobrevive ao corte.

Sem `AlterModelTable`/`RenameModel` aqui: a `Evidencia` **não** é renome (as tabelas de `Account`,
`Process` e `CommercialOpportunity` é que esperam a Fase 6 com o `db_table` fixado). Ela é a metade
legada do split, e o que se faz com ela é apagar.
"""

from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ('core', '0067_backfill_kpi_measurement'),
    ]

    operations = [
        # Os dois ponteiros de reconciliação primeiro — são FK para `Evidencia`, e o `DeleteModel`
        # abaixo falharia com a tabela ainda referenciada.
        migrations.RemoveField(
            model_name='evidence',
            name='legacy_evidencia',
        ),
        migrations.RemoveField(
            model_name='finding',
            name='legacy_evidencia',
        ),
        migrations.DeleteModel(
            name='Evidencia',
        ),
    ]
