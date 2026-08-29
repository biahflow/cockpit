"""Move a medição de dentro do ativo de solução para `KPI` + `Measurement`, e só então tira as colunas.

Issue #69, ADR 0055, FDD 049, decisão **C1** do DAP `docs/design/dap-prove-e-valor-r1/`. Até aqui
`DigitalEmployee.kpi_baseline` e `kpi_current` **eram** o "antes" e o "depois": duas colunas do
ativo, afirmando que eram dois fatos de naturezas distintas. São o mesmo fato lido em duas janelas,
e é isso que o par `KPI`/`Measurement` passa a dizer. Sem backfill, o modelo novo nasceria vazio e
todo baseline já medido iria embora com a coluna — que é jogar fora exatamente o dado que a FDD 027
existiu para capturar no instante certo.

## Por que o `RunPython` e o `RemoveField` moram no **mesmo** arquivo

A ordem é obrigatória — copiar antes de remover —, e ela seria respeitada também com uma `0068`
separada. O que a separação abriria é uma **janela de deploy** em que a `0067` rodou e a `0068`
não: o mesmo fato gravado em dois lugares (a coluna e a medição), com a última escrita vencendo.
É precisamente a duplicação que a decisão C1 existe para remover, e ela não pode existir nem por
um passo do deploy. Juntos, o par não tem esse estado intermediário.

A reversa se compõe sozinha e na ordem certa: o Django desfaz as operações de trás para a frente,
então os dois `RemoveField` voltam a criar as colunas **antes** de `desfaz_backfill` ter de
escrever nelas.

## As aproximações declaradas

Nenhuma delas está no dado de origem, e por isso ficam escritas aqui em vez de escondidas no código:

1. **Nulo não vira zero, e nulo não vira medição.** Funcionário digital sem `kpi_baseline` **não**
   ganha `Measurement(kind=baseline)` nenhuma — ganha a ausência, que é o que ele tem. Este é o
   ponto exato em que uma migração pode mentir, e mentir aqui é pior que a lacuna: um "antes" igual
   a zero afirma que o processo não custava nada (FDD 027, `Process.custo_do_estado_atual`).
2. **A janela e a hora da leitura são aproximadas pelos carimbos do ativo.** O modelo antigo não
   registrava quando a medição foi tomada. O baseline era pedido na instanciação, então
   `created_at` é a melhor aproximação auditável do "antes"; o atual era editado depois, então
   `updated_at` aproxima o "depois". A marca de que a data veio da migração é o KPI **sem**
   `prove_experiment`.
3. **Arquivados vêm junto, com o carimbo preservado.** Deixá-los fora faria o par novo divergir do
   legado justamente no que já tinha sido decidido guardar, e desarquivar o funcionário digital
   passaria a produzir um ativo sem KPI nenhum.

Idempotente por existência (`if empregado.kpi_id: continue`), no molde da `0054`.
"""

from django.db import migrations


def _texto(valor: str | None) -> str:
    return (valor or "").strip()


def backfill_kpi(apps, schema_editor):
    """Cria um `KPI` por funcionário digital que já tinha número, e as medições que ele tinha."""
    DigitalEmployee = apps.get_model("core", "DigitalEmployee")
    KPI = apps.get_model("core", "KPI")
    Measurement = apps.get_model("core", "Measurement")

    medidos = DigitalEmployee.objects.filter(kpi__isnull=True).exclude(
        kpi_baseline__isnull=True, kpi_current__isnull=True
    )
    for empregado in medidos.iterator():
        kpi = KPI.objects.create(
            project_id=empregado.project_id,
            # **Nunca inventado.** Um `ProveExperiment` fabricado aqui teria aparência de
            # histórico e não aconteceu; é por isto que `KPI.prove_experiment` é nulável, contra
            # a lista de campos da issue (ver a docstring do modelo).
            prove_experiment=None,
            # O rótulo livre da era anterior é o melhor nome que existe. Sem ele, o nome do ativo
            # identifica a linha para quem for reler — em branco, o KPI ficaria anônimo na tela.
            name=_texto(empregado.kpi_label) or f"KPI — {empregado.name}",
            unit=empregado.kpi_unit,
            direction=empregado.kpi_direction,
            archived_at=empregado.archived_at,
        )
        if empregado.kpi_baseline is not None:
            Measurement.objects.create(
                kpi=kpi,
                kind="baseline",
                value=empregado.kpi_baseline,
                period_start=empregado.created_at.date(),
                period_end=empregado.created_at.date(),
                measured_at=empregado.created_at,
                archived_at=empregado.archived_at,
            )
        if empregado.kpi_current is not None:
            Measurement.objects.create(
                kpi=kpi,
                kind="outcome",
                value=empregado.kpi_current,
                period_start=empregado.updated_at.date(),
                period_end=empregado.updated_at.date(),
                measured_at=empregado.updated_at,
                archived_at=empregado.archived_at,
            )
        empregado.kpi = kpi
        # `update_fields` para não reescrever `updated_at`: ele é a aproximação que a medição de
        # "depois" acabou de usar, e um backfill que o carimba com a hora do deploy apagaria a
        # única data que existia.
        empregado.save(update_fields=["kpi"])


def desfaz_backfill(apps, schema_editor):
    """Devolve os números às colunas e apaga **só** o que o backfill criou.

    O recorte é pelo ponteiro, como a `0054` faz com `legacy_evidencia`: um KPI apontado por um
    funcionário digital **e sem `prove_experiment`** é a assinatura desta migração. A imprecisão
    residual está declarada: um KPI escrito à mão depois, sem experimento e ligado a um ativo, é
    indistinguível — e é o preço de não criar uma coluna `legacy_` só para a reversa.

    A reversa **recusa** quando uma `ValueLedgerEntry` já pende da medição (`PROTECT` levanta
    `ProtectedError`), e recusar é o certo: desfazer schema não pode apagar valor atribuído.
    """
    DigitalEmployee = apps.get_model("core", "DigitalEmployee")
    KPI = apps.get_model("core", "KPI")

    for empregado in DigitalEmployee.objects.filter(
        kpi__isnull=False, kpi__prove_experiment__isnull=True
    ).select_related("kpi").iterator():
        kpi = empregado.kpi
        medicoes = list(kpi.measurements.all())
        baseline = next((m for m in medicoes if m.kind == "baseline"), None)
        atual = sorted(
            (m for m in medicoes if m.kind == "outcome"),
            key=lambda m: (m.measured_at, m.pk),
        )
        empregado.kpi_baseline = baseline.value if baseline is not None else None
        empregado.kpi_current = atual[-1].value if atual else None
        empregado.kpi = None
        empregado.save(update_fields=["kpi", "kpi_baseline", "kpi_current"])
        for medicao in medicoes:
            medicao.delete()
        KPI.objects.filter(pk=kpi.pk).delete()


class Migration(migrations.Migration):

    dependencies = [
        ('core', '0066_prove_e_valor'),
    ]

    operations = [
        migrations.RunPython(backfill_kpi, desfaz_backfill),
        migrations.RemoveField(
            model_name='digitalemployee',
            name='kpi_baseline',
        ),
        migrations.RemoveField(
            model_name='digitalemployee',
            name='kpi_current',
        ),
    ]
